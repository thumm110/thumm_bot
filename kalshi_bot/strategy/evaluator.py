from datetime import datetime, timezone

from kalshi_bot.config import (
    EXCLUDE_PROVISIONAL,
    EXCLUDED_EVENT_TICKER_KEYWORDS,
    EXCLUDED_EVENT_TICKER_PREFIXES,
    MIN_ORDERBOOK_SIZE,
    MIN_VOLUME,
    PENALIZED_EVENT_TICKER_PREFIXES,
)


def _hours_to_close(close_time):
    if not close_time:
        return None

    try:
        close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
    except ValueError:
        return None

    now = datetime.now(timezone.utc)
    return (close_dt - now).total_seconds() / 3600


def _short_horizon_thresholds(hours_to_close):
    if hours_to_close is None:
        return MIN_VOLUME, MIN_ORDERBOOK_SIZE
    if hours_to_close <= 6:
        return 150, 20
    if hours_to_close <= 12:
        return 250, 25
    if hours_to_close <= 24:
        return 400, 25
    return MIN_VOLUME, MIN_ORDERBOOK_SIZE


def evaluate_market(market, history=None):
    try:
        ticker = market.get("ticker", "UNKNOWN")
        event_ticker = market.get("event_ticker")
        title = market.get("title") or ticker
        last_price = market.get("last_price")
        yes_bid = market.get("yes_bid")
        yes_ask = market.get("yes_ask")
        status = market.get("status")
        is_provisional = market.get("is_provisional", False)
        volume = market.get("volume", 0)
        yes_bid_size = market.get("yes_bid_size", 0)
        yes_ask_size = market.get("yes_ask_size", 0)
        close_time = market.get("close_time")
        hours_to_close = _hours_to_close(close_time)

        if status not in {"open", "active"}:
            return None

        if EXCLUDE_PROVISIONAL and is_provisional:
            return None

        normalized_event_ticker = (event_ticker or "").upper()
        if any(keyword in normalized_event_ticker for keyword in EXCLUDED_EVENT_TICKER_KEYWORDS):
            return None
        if any(normalized_event_ticker.startswith(prefix) for prefix in EXCLUDED_EVENT_TICKER_PREFIXES):
            return None

        if yes_bid is None or yes_ask is None:
            return None

        reference_price = yes_ask
        if reference_price is None:
            reference_price = last_price
        if reference_price is None:
            reference_price = yes_bid
        if reference_price is None:
            return None

        mid_price = (yes_bid + yes_ask) / 2
        spread = yes_ask - yes_bid
        displayed_size = max(yes_bid_size, yes_ask_size)
        min_volume, min_displayed_size = _short_horizon_thresholds(hours_to_close)

        if mid_price <= 10 or mid_price >= 90:
            return None

        if volume < min_volume or displayed_size < min_displayed_size:
            return None

        if spread > 8:
            return None

        if last_price is None:
            return None

        if hours_to_close is None or hours_to_close <= 0:
            return None

        decision = "SKIP"
        if last_price < yes_ask - 2:
            decision = "YES"
        elif last_price > yes_bid + 2:
            decision = "NO"

        if yes_ask <= mid_price - 2:
            decision = "YES"
        elif yes_bid >= mid_price + 2:
            decision = "NO"

        if decision == "SKIP":
            return None

        edge = 0.0
        if decision == "YES":
            edge = max(yes_ask - last_price, 0)
        elif decision == "NO":
            edge = max(last_price - yes_bid, 0)

        score = (
            edge * 10
            + max(0, 10 - spread) * 4
            + min(volume / 250, 20)
            + min(displayed_size / 50, 10)
        )
        if hours_to_close <= 6:
            score += 10
        elif hours_to_close <= 12:
            score += 7
        elif hours_to_close <= 24:
            score += 4
        else:
            score -= min((hours_to_close - 24) / 12, 18)

        for prefix, penalty in PENALIZED_EVENT_TICKER_PREFIXES.items():
            if normalized_event_ticker.startswith(prefix):
                score -= penalty
                break

        if history is not None:
            decisions = history.get(ticker, [])
            if len(decisions) >= 3 and decisions[-3:] != [decision, decision, decision]:
                return None

        return {
            "ticker": ticker,
            "event_ticker": event_ticker,
            "title": title,
            "status": status,
            "is_provisional": is_provisional,
            "close_time": close_time,
            "hours_to_close": round(hours_to_close, 2),
            "price": reference_price,
            "mid_price": mid_price,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "yes_bid_size": yes_bid_size,
            "yes_ask_size": yes_ask_size,
            "spread": spread,
            "volume": volume,
            "displayed_size": displayed_size,
            "edge": edge,
            "score": round(score, 2),
            "decision": decision,
        }
    except Exception as exc:
        print(f"[ERROR] Strategy: {exc}")
        return None
