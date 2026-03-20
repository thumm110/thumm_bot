from math import floor


def trade_entry_cost_cents(signal):
    entry_price = signal.get("price")
    if entry_price is None:
        return None

    decision = signal.get("decision")
    if decision == "YES":
        return entry_price
    if decision == "NO":
        return 100 - entry_price
    return None


def trade_notional_dollars(signal, quantity=None):
    entry_cost_cents = trade_entry_cost_cents(signal)
    if entry_cost_cents is None:
        return None

    if quantity is None:
        quantity = signal.get("quantity", 1)
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 1

    return round((entry_cost_cents * quantity) / 100, 2)


def resolved_to_yes_share_value(outcome):
    normalized = (outcome or "").strip().lower()
    if normalized == "yes":
        return 100
    if normalized == "no":
        return 0
    return None


def trade_pnl_cents(signal, outcome):
    entry_price = signal.get("price")
    if entry_price is None:
        return None

    yes_share_value = resolved_to_yes_share_value(outcome)
    if yes_share_value is None:
        return None

    decision = signal.get("decision")
    if decision == "YES":
        return yes_share_value - entry_price
    if decision == "NO":
        no_entry_cost = 100 - entry_price
        no_share_value = 100 - yes_share_value
        return no_share_value - no_entry_cost
    return None


def trade_pnl_dollars(signal, outcome):
    pnl_cents_per_share = trade_pnl_cents(signal, outcome)
    if pnl_cents_per_share is None:
        return None

    quantity = signal.get("quantity", 1)
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 1

    return round((pnl_cents_per_share * quantity) / 100, 2)


def current_position_value_dollars(signal, current_yes_price, quantity=None):
    if current_yes_price is None:
        return None

    if quantity is None:
        quantity = signal.get("quantity", 1)
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 1

    decision = signal.get("decision")
    if decision == "YES":
        return round((current_yes_price * quantity) / 100, 2)
    if decision == "NO":
        return round(((100 - current_yes_price) * quantity) / 100, 2)
    return None


def trade_mark_to_market_pnl_dollars(signal, current_yes_price, quantity=None):
    position_value = current_position_value_dollars(signal, current_yes_price, quantity=quantity)
    if position_value is None:
        return None

    entry_cost = trade_notional_dollars(signal, quantity=quantity)
    if entry_cost is None:
        return None
    return round(position_value - entry_cost, 2)


def bucket_label(score, bucket_size):
    bucket_floor = int(floor(score / bucket_size) * bucket_size)
    bucket_ceiling = bucket_floor + bucket_size
    return f"{bucket_floor:02d}-{bucket_ceiling:02d}"
