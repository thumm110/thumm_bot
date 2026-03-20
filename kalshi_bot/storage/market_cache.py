import json
from pathlib import Path
from typing import Any

from kalshi_bot.config import RAW_MARKETS_DIR, RECENT_MARKETS_FILE
from kalshi_bot.storage.json_store import write_json


def _read_cache_payload() -> dict[str, Any]:
    try:
        with RECENT_MARKETS_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}
    return payload


def read_recent_markets_cache() -> dict[str, dict[str, Any]]:
    payload = _read_cache_payload()
    markets_by_ticker = payload.get("markets_by_ticker", {})
    if not isinstance(markets_by_ticker, dict):
        return {}
    return {
        ticker: market
        for ticker, market in markets_by_ticker.items()
        if isinstance(ticker, str) and isinstance(market, dict)
    }


def write_recent_markets_cache(markets_by_ticker: dict[str, dict[str, Any]]) -> None:
    payload = {
        "market_count": len(markets_by_ticker),
        "markets_by_ticker": markets_by_ticker,
    }
    write_json(RECENT_MARKETS_FILE, payload)


def upsert_recent_markets_cache(markets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    markets_by_ticker = read_recent_markets_cache()
    for market in markets:
        ticker = market.get("ticker")
        if not ticker:
            continue
        markets_by_ticker[ticker] = market

    write_recent_markets_cache(markets_by_ticker)
    return markets_by_ticker


def _load_markets_file(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    markets = payload.get("markets", [])
    if isinstance(markets, list):
        return markets
    return []


def rebuild_recent_markets_cache_from_raw() -> dict[str, dict[str, Any]]:
    if not RAW_MARKETS_DIR.exists():
        return {}

    markets_by_ticker: dict[str, dict[str, Any]] = {}
    for path in sorted(RAW_MARKETS_DIR.glob("markets_*.json"), reverse=True):
        for market in _load_markets_file(path):
            ticker = market.get("ticker")
            if not ticker or ticker in markets_by_ticker:
                continue
            markets_by_ticker[ticker] = market

    if markets_by_ticker:
        write_recent_markets_cache(markets_by_ticker)
    return markets_by_ticker
