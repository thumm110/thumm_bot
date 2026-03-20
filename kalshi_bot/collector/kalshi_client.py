import requests
from datetime import datetime, timezone
from typing import Any

from kalshi_bot.config import (
    EXCLUDE_SYNTHETIC_MARKETS,
    KALSHI_API_BASE,
    MARKET_PAGE_LIMIT,
    MAX_MARKET_PAGES,
    MAX_MARKET_PAGES_WITH_SHORT_HORIZON,
    MIN_LIQUIDITY_CENTS,
    MIN_SNAPSHOT_ORDERBOOK_SIZE,
    PAPER_PREFERRED_MAX_HOLD_HOURS,
    REQUEST_TIMEOUT_SECONDS,
    SHORT_HORIZON_MIN_MARKETS,
)


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dollars_to_cents(value: Any) -> int | None:
    dollars = _as_float(value)
    if dollars is None:
        return None
    return round(dollars * 100)


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _is_synthetic_market(market: dict[str, Any]) -> bool:
    return any((market.get("mve_collection_ticker"), market.get("mve_selected_legs")))


def _hours_to_close(close_time: Any) -> float | None:
    if not close_time:
        return None

    try:
        close_dt = datetime.fromisoformat(str(close_time).replace("Z", "+00:00"))
    except ValueError:
        return None

    now = datetime.now(timezone.utc)
    return (close_dt - now).total_seconds() / 3600


def normalize_market(
    market: dict[str, Any],
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    liquidity_cents = _dollars_to_cents(market.get("liquidity_dollars"))
    event = event or {}

    yes_bid = _first_value(
        _dollars_to_cents(market.get("yes_bid_dollars")),
        market.get("yes_bid"),
    )
    yes_ask = _first_value(
        _dollars_to_cents(market.get("yes_ask_dollars")),
        market.get("yes_ask"),
    )
    last_price = _first_value(
        _dollars_to_cents(market.get("last_price_dollars")),
        market.get("last_price"),
    )
    volume = _first_value(_as_float(market.get("volume_fp")), market.get("volume"), 0.0)
    open_interest = _first_value(
        _as_float(market.get("open_interest_fp")),
        market.get("open_interest"),
        0.0,
    )

    return {
        "ticker": market.get("ticker", "UNKNOWN"),
        "event_ticker": market.get("event_ticker") or event.get("event_ticker"),
        "series_ticker": event.get("series_ticker"),
        "event_title": event.get("title"),
        "event_subtitle": event.get("sub_title"),
        "category": event.get("category"),
        "title": market.get("title"),
        "status": market.get("status"),
        "market_type": market.get("market_type"),
        "is_provisional": bool(market.get("is_provisional")),
        "is_synthetic": _is_synthetic_market(market),
        "close_time": market.get("close_time"),
        "hours_to_close": _hours_to_close(market.get("close_time")),
        "settlement_ts": market.get("settlement_ts"),
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "yes_bid_size": _as_float(market.get("yes_bid_size_fp")) or 0.0,
        "yes_ask_size": _as_float(market.get("yes_ask_size_fp")) or 0.0,
        "last_price": last_price,
        "volume": volume,
        "volume_24h": _as_float(market.get("volume_24h_fp")),
        "open_interest": open_interest,
        "liquidity_cents": liquidity_cents,
        "raw": market,
        "event_raw": event,
    }


def should_keep_market(market: dict[str, Any]) -> bool:
    if EXCLUDE_SYNTHETIC_MARKETS and market.get("is_synthetic"):
        return False

    liquidity_cents = market.get("liquidity_cents")
    if liquidity_cents is None or liquidity_cents < MIN_LIQUIDITY_CENTS:
        return False

    displayed_size = max(market.get("yes_bid_size", 0.0), market.get("yes_ask_size", 0.0))
    if displayed_size < MIN_SNAPSHOT_ORDERBOOK_SIZE:
        return False

    return True


def build_session() -> requests.Session:
    return requests.Session()


def _is_short_horizon_market(market: dict[str, Any]) -> bool:
    hours_to_close = market.get("hours_to_close")
    return (
        hours_to_close is not None
        and 0 < hours_to_close <= PAPER_PREFERRED_MAX_HOLD_HOURS
    )


def _market_priority(market: dict[str, Any]) -> tuple[int, float, float]:
    hours_to_close = market.get("hours_to_close")
    if hours_to_close is None or hours_to_close <= 0:
        hours_sort = 10**9
    else:
        hours_sort = hours_to_close

    short_horizon_rank = 0 if _is_short_horizon_market(market) else 1
    liquidity_rank = -max(market.get("volume", 0.0), market.get("open_interest", 0.0))
    return short_horizon_rank, hours_sort, liquidity_rank


def fetch_markets() -> list[dict[str, Any]]:
    session = build_session()
    cursor = None
    pages_fetched = 0
    normalized_markets: list[dict[str, Any]] = []

    short_horizon_count = 0

    while pages_fetched < MAX_MARKET_PAGES_WITH_SHORT_HORIZON:
        params = {
            "limit": MARKET_PAGE_LIMIT,
            "mve_filter": "exclude",
            "status": "open",
        }
        if cursor:
            params["cursor"] = cursor

        try:
            response = session.get(
                f"{KALSHI_API_BASE}/markets",
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"[ERROR] Fetching markets: {exc}")
            break

        payload = response.json()
        page_markets = payload.get("markets", [])
        for market in page_markets:
            normalized_market = normalize_market(market)
            if should_keep_market(normalized_market):
                normalized_markets.append(normalized_market)
                if _is_short_horizon_market(normalized_market):
                    short_horizon_count += 1

        cursor = payload.get("cursor")
        pages_fetched += 1
        if pages_fetched >= MAX_MARKET_PAGES and short_horizon_count >= SHORT_HORIZON_MIN_MARKETS:
            break
        if not cursor:
            break

    normalized_markets.sort(key=_market_priority)
    return normalized_markets


def fetch_market_by_ticker(ticker: str) -> dict[str, Any] | None:
    session = build_session()

    try:
        response = session.get(
            f"{KALSHI_API_BASE}/markets/{ticker}",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[ERROR] Fetching market {ticker}: {exc}")
        return None

    payload = response.json()
    market = payload.get("market")
    if not market:
        return None

    return normalize_market(market)
