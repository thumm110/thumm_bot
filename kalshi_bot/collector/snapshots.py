from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kalshi_bot.config import DATA_DIR, RAW_MARKETS_DIR
from kalshi_bot.storage.json_store import write_json
from kalshi_bot.storage.market_cache import upsert_recent_markets_cache


def save_market_snapshot(markets: list[dict[str, Any]]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_MARKETS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "market_count": len(markets),
        "markets": markets,
    }

    latest_path = DATA_DIR / "markets_latest.json"
    snapshot_path = RAW_MARKETS_DIR / f"markets_{timestamp}.json"

    write_json(latest_path, payload)
    write_json(snapshot_path, payload)
    upsert_recent_markets_cache(markets)
    return snapshot_path
