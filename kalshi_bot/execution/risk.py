from collections.abc import Iterable

from kalshi_bot.analysis.backtest_metrics import (
    trade_entry_cost_cents,
    trade_notional_dollars,
    trade_pnl_dollars,
)
from kalshi_bot.config import (
    PAPER_MAX_CAPITAL_UTILIZATION,
    PAPER_MAX_ENTRY_PRICE,
    PAPER_MAX_LONG_EXPIRY_SHARE,
    PAPER_MAX_TRADES_PER_RUN,
    PAPER_MIN_SCORE,
    PAPER_PREFERRED_MAX_HOLD_HOURS,
    PAPER_POSITION_SIZE_DOLLARS,
    PAPER_POSITION_SIZE_FLOOR_RATIO,
    PAPER_STARTING_BANKROLL_DOLLARS,
)


def compute_contract_quantity(position_size_dollars, price_cents, decision):
    entry_cost_cents = trade_entry_cost_cents({"price": price_cents, "decision": decision})
    if entry_cost_cents is None or entry_cost_cents <= 0:
        return 0
    return max(1, int((position_size_dollars * 100) // entry_cost_cents))


def _clamp(value, lower=0.0, upper=1.0):
    return max(lower, min(upper, value))


def target_position_size_dollars(signal: dict) -> float:
    max_size = float(PAPER_POSITION_SIZE_DOLLARS)
    min_size = round(max_size * PAPER_POSITION_SIZE_FLOOR_RATIO, 2)

    score = float(signal.get("score", 0) or 0)
    edge = float(signal.get("edge", 0) or 0)
    spread = float(signal.get("spread", 0) or 0)
    displayed_size = float(signal.get("displayed_size", 0) or 0)
    volume = float(signal.get("volume", 0) or 0)
    hours_to_close = _signal_hours_to_close(signal)

    score_component = _clamp((score - PAPER_MIN_SCORE) / 60)
    edge_component = _clamp(edge / 8)
    spread_component = _clamp((8 - spread) / 8)
    displayed_component = _clamp(displayed_size / 150)
    volume_component = _clamp(volume / 3000)
    liquidity_component = (displayed_component + volume_component) / 2

    if hours_to_close is None:
        horizon_component = 0.7
    elif hours_to_close <= 6:
        horizon_component = 1.0
    elif hours_to_close <= 12:
        horizon_component = 0.95
    elif hours_to_close <= 24:
        horizon_component = 0.85
    else:
        horizon_component = 0.6

    conviction = (
        score_component * 0.35
        + edge_component * 0.2
        + spread_component * 0.2
        + liquidity_component * 0.25
    )
    sizing_ratio = _clamp(conviction * horizon_component)
    position_size = max(min_size, round(max_size * sizing_ratio, 2))
    return min(position_size, max_size)


def paper_trade_notional_dollars(price_cents, quantity, decision):
    entry_cost_cents = trade_entry_cost_cents({"price": price_cents, "decision": decision})
    if entry_cost_cents is None or quantity <= 0:
        return 0.0
    return round((entry_cost_cents * quantity) / 100, 2)


def current_open_position_count(trades: Iterable[dict], resolved_tickers: set[str]) -> int:
    fills_by_ticker = {
        trade.get("ticker"): trade
        for trade in trades
        if trade.get("status") == "paper_filled" and trade.get("ticker")
    }
    exited_quantity_by_ticker = {}
    for trade in trades:
        if trade.get("status") != "paper_exit_filled":
            continue
        ticker = trade.get("ticker")
        if not ticker:
            continue
        exited_quantity_by_ticker[ticker] = exited_quantity_by_ticker.get(ticker, 0) + int(
            trade.get("quantity", 0) or 0
        )

    open_positions = 0
    for ticker, trade in fills_by_ticker.items():
        if not ticker or ticker in resolved_tickers:
            continue
        fill_quantity = int(trade.get("quantity", 0) or 0)
        remaining_quantity = fill_quantity - exited_quantity_by_ticker.get(ticker, 0)
        if remaining_quantity > 0:
            open_positions += 1
    return open_positions


def _filled_trades_by_ticker(trades: Iterable[dict]) -> dict[str, dict]:
    return {
        trade.get("ticker"): trade
        for trade in trades
        if trade.get("status") == "paper_filled" and trade.get("ticker")
    }


def _exit_quantity_by_ticker(trades: Iterable[dict]) -> dict[str, int]:
    quantities = {}
    for trade in trades:
        if trade.get("status") != "paper_exit_filled":
            continue
        ticker = trade.get("ticker")
        if not ticker:
            continue
        quantities[ticker] = quantities.get(ticker, 0) + int(trade.get("quantity", 0) or 0)
    return quantities


def _signal_hours_to_close(signal: dict) -> float | None:
    value = signal.get("hours_to_close")
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_long_expiry_signal(signal: dict) -> bool:
    hours_to_close = _signal_hours_to_close(signal)
    if hours_to_close is None:
        return True
    return hours_to_close > PAPER_PREFERRED_MAX_HOLD_HOURS


def open_duration_mix(trades: Iterable[dict], resolved_tickers: set[str]) -> tuple[int, int]:
    fills_by_ticker = _filled_trades_by_ticker(trades)
    exited_quantities = _exit_quantity_by_ticker(trades)
    total_open = 0
    long_open = 0

    for ticker, trade in fills_by_ticker.items():
        if ticker in resolved_tickers:
            continue
        fill_quantity = int(trade.get("quantity", 0) or 0)
        remaining_quantity = fill_quantity - exited_quantities.get(ticker, 0)
        if remaining_quantity <= 0:
            continue
        total_open += 1
        if is_long_expiry_signal(trade):
            long_open += 1

    return total_open, long_open


def portfolio_cash_state(trades: Iterable[dict], outcomes_by_ticker: dict[str, dict]) -> tuple[float, float]:
    fills_by_ticker = _filled_trades_by_ticker(trades)
    exited_quantities = _exit_quantity_by_ticker(trades)
    realized_pnl = round(
        sum(
            float(trade.get("realized_pnl_dollars", 0) or 0)
            for trade in trades
            if trade.get("status") == "paper_exit_filled"
        ),
        2,
    )
    open_notional = 0.0

    for ticker, trade in fills_by_ticker.items():
        fill_quantity = int(trade.get("quantity", 0) or 0)
        remaining_quantity = max(0, fill_quantity - exited_quantities.get(ticker, 0))
        outcome_entry = outcomes_by_ticker.get(ticker, {})
        resolved_outcome = outcome_entry.get("resolved_outcome")

        if resolved_outcome in {"yes", "no"}:
            if remaining_quantity <= 0:
                continue
            remaining_trade = dict(trade)
            remaining_trade["quantity"] = remaining_quantity
            resolved_pnl = trade_pnl_dollars(remaining_trade, resolved_outcome)
            realized_pnl = round(realized_pnl + (resolved_pnl or 0), 2)
            continue

        if remaining_quantity <= 0:
            continue

        remaining_trade = dict(trade)
        remaining_trade["quantity"] = remaining_quantity
        open_notional += trade_notional_dollars(remaining_trade, quantity=remaining_quantity) or 0.0

    cash_dollars = round(PAPER_STARTING_BANKROLL_DOLLARS + realized_pnl - open_notional, 2)
    return cash_dollars, round(open_notional, 2)


def check_signal_risk(signal, current_run_trades, all_trades, trade_date, outcomes_by_ticker=None):
    if len(current_run_trades) >= PAPER_MAX_TRADES_PER_RUN:
        return False, "run_limit"

    score = float(signal.get("score", 0))
    if score < PAPER_MIN_SCORE:
        return False, "score_below_threshold"

    price = signal.get("price")
    if price is None or price > PAPER_MAX_ENTRY_PRICE:
        return False, "entry_price_too_high"

    ticker = signal.get("ticker")
    event_ticker = signal.get("event_ticker")
    for trade in all_trades:
        if trade.get("status") != "paper_filled":
            continue
        if ticker and trade.get("ticker") == ticker:
            return False, "ticker_already_filled"
        if event_ticker and trade.get("event_ticker") == event_ticker:
            return False, "event_already_filled"

    for trade in current_run_trades:
        if trade.get("event_ticker") and trade.get("event_ticker") == event_ticker:
            return False, "event_already_selected"

    position_size_dollars = target_position_size_dollars(signal)
    quantity = compute_contract_quantity(position_size_dollars, price, signal.get("decision"))
    notional = paper_trade_notional_dollars(price, quantity, signal.get("decision"))
    if notional <= 0:
        return False, "invalid_position_size"

    outcomes_by_ticker = outcomes_by_ticker or {}
    resolved_tickers = {
        ticker
        for ticker, outcome in outcomes_by_ticker.items()
        if ticker and outcome.get("resolved_outcome") in {"yes", "no"}
    }
    total_open, long_open = open_duration_mix(all_trades, resolved_tickers)
    total_open += len(current_run_trades)
    long_open += sum(1 for trade in current_run_trades if is_long_expiry_signal(trade))
    if is_long_expiry_signal(signal):
        projected_total = total_open + 1
        projected_long = long_open + 1
        max_allowed_long = int(projected_total * PAPER_MAX_LONG_EXPIRY_SHARE)
        if projected_long > max_allowed_long:
            return False, "long_expiry_limit"

    cash_dollars, open_notional = portfolio_cash_state(all_trades, outcomes_by_ticker)
    projected_open_notional = open_notional + notional
    projected_open_notional += sum(
        paper_trade_notional_dollars(
            trade.get("price"),
            trade.get("quantity", 0) or 0,
            trade.get("decision"),
        )
        for trade in current_run_trades
    )
    capital_base = cash_dollars + open_notional
    max_open_notional = round(capital_base * PAPER_MAX_CAPITAL_UTILIZATION, 2)
    if projected_open_notional > max_open_notional:
        return False, "cash_utilization_limit"

    return True, "approved"
