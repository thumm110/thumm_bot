from datetime import datetime, timezone

from kalshi_bot.config import (
    DATA_DIR,
    DECISIONS_LOG_FILE,
    OUTCOMES_LOG_FILE,
    PAPER_TRADES_LOG_FILE,
)
from kalshi_bot.storage.json_store import read_json_list, write_json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_entry(entry):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = read_json_list(DECISIONS_LOG_FILE)

        logged_entry = dict(entry)
        logged_entry["timestamp"] = utc_now_iso()
        logged_entry["signal_time"] = logged_entry["timestamp"]
        logged_entry["schema_version"] = 1

        data.append(logged_entry)
        write_json(DECISIONS_LOG_FILE, data)
    except Exception as exc:
        print(f"[ERROR] Logging: {exc}")


def read_signal_log():
    return read_json_list(DECISIONS_LOG_FILE)


def read_outcomes_log():
    return read_json_list(OUTCOMES_LOG_FILE)


def read_paper_trades_log():
    return read_json_list(PAPER_TRADES_LOG_FILE)


def upsert_outcomes(entries):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        existing_entries = read_json_list(OUTCOMES_LOG_FILE)
        outcomes_by_ticker = {
            entry["ticker"]: entry for entry in existing_entries if entry.get("ticker")
        }

        for entry in entries:
            outcome_entry = dict(entry)
            outcome_entry["updated_at"] = utc_now_iso()
            ticker = outcome_entry.get("ticker")
            if not ticker:
                continue
            outcomes_by_ticker[ticker] = outcome_entry

        payload = list(outcomes_by_ticker.values())
        payload.sort(key=lambda item: item.get("ticker", ""))
        write_json(OUTCOMES_LOG_FILE, payload)
    except Exception as exc:
        print(f"[ERROR] Outcome logging: {exc}")


def log_paper_trade(entry):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = read_json_list(PAPER_TRADES_LOG_FILE)

        logged_entry = dict(entry)
        logged_entry["logged_at"] = utc_now_iso()
        data.append(logged_entry)

        write_json(PAPER_TRADES_LOG_FILE, data)
    except Exception as exc:
        print(f"[ERROR] Paper trade logging: {exc}")
