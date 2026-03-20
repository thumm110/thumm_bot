RESOLVED_STATUSES = {"settled", "resolved", "finalized"}


def extract_resolved_outcome(market):
    raw = market.get("raw", {})
    result = raw.get("result")
    if isinstance(result, str):
        normalized = result.strip().lower()
        if normalized in {"yes", "no"}:
            return normalized

    expiration_value = raw.get("expiration_value")
    if expiration_value not in (None, ""):
        try:
            numeric_value = float(expiration_value)
        except (TypeError, ValueError):
            numeric_value = None

        if numeric_value is not None:
            if numeric_value >= 1:
                return "yes"
            if numeric_value <= 0:
                return "no"

    return None


def is_resolved_market(market):
    status = (market.get("status") or "").lower()
    outcome = extract_resolved_outcome(market)
    return status in RESOLVED_STATUSES or outcome is not None


def build_outcome_entry(market):
    raw = market.get("raw", {})
    return {
        "ticker": market.get("ticker"),
        "event_ticker": market.get("event_ticker"),
        "status": market.get("status"),
        "resolved_outcome": extract_resolved_outcome(market),
        "result": raw.get("result"),
        "expiration_value": raw.get("expiration_value"),
        "close_time": market.get("close_time"),
        "settlement_ts": market.get("settlement_ts"),
        "last_price": market.get("last_price"),
        "yes_bid": market.get("yes_bid"),
        "yes_ask": market.get("yes_ask"),
    }
