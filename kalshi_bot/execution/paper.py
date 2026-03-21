from datetime import datetime, timezone

from kalshi_bot.analysis.backtest_metrics import (
    current_position_value_dollars,
    trade_mark_to_market_pnl_dollars,
)
from kalshi_bot.config import PAPER_TRADING_ENABLED
from kalshi_bot.config import PAPER_TAKE_PROFIT_FULL_PCT, PAPER_TAKE_PROFIT_PARTIAL_PCT
from kalshi_bot.execution.risk import (
    check_signal_risk,
    compute_contract_quantity,
    paper_trade_notional_dollars,
    target_position_size_dollars,
)


def build_paper_trade(signal):
    price = signal.get("price")
    decision = signal.get("decision")
    position_size_dollars = target_position_size_dollars(signal)
    quantity = compute_contract_quantity(position_size_dollars, price, decision)
    notional = paper_trade_notional_dollars(price, quantity, decision)
    trade_time = datetime.now(timezone.utc).isoformat()

    return {
        "ticker": signal.get("ticker"),
        "event_ticker": signal.get("event_ticker"),
        "decision": decision,
        "price": price,
        "score": signal.get("score"),
        "close_time": signal.get("close_time"),
        "hours_to_close": signal.get("hours_to_close"),
        "quantity": quantity,
        "notional_dollars": notional,
        "position_size_dollars": position_size_dollars,
        "trade_time": trade_time,
        "trade_date": trade_time[:10],
        "status": "paper_filled",
    }


def _filled_trades_by_ticker(existing_trades):
    return {
        trade.get("ticker"): trade
        for trade in existing_trades
        if trade.get("status") == "paper_filled" and trade.get("ticker")
    }


def _exit_trades_by_ticker(existing_trades):
    exits_by_ticker = {}
    for trade in existing_trades:
        if trade.get("status") != "paper_exit_filled":
            continue
        ticker = trade.get("ticker")
        if not ticker:
            continue
        exits_by_ticker.setdefault(ticker, []).append(trade)
    return exits_by_ticker


def build_paper_exit(trade, current_yes_price, quantity, reason):
    exit_time = datetime.now(timezone.utc).isoformat()
    proceeds = current_position_value_dollars(trade, current_yes_price, quantity=quantity)
    realized_pnl = trade_mark_to_market_pnl_dollars(trade, current_yes_price, quantity=quantity)

    return {
        "ticker": trade.get("ticker"),
        "event_ticker": trade.get("event_ticker"),
        "decision": trade.get("decision"),
        "entry_price": trade.get("price"),
        "exit_price": current_yes_price,
        "score": trade.get("score"),
        "quantity": quantity,
        "proceeds_dollars": proceeds,
        "realized_pnl_dollars": realized_pnl,
        "trade_time": trade.get("trade_time"),
        "exit_time": exit_time,
        "exit_date": exit_time[:10],
        "status": "paper_exit_filled",
        "reason": reason,
    }


def paper_exit_candidates(existing_trades, markets_by_ticker, resolved_tickers=None):
    resolved_tickers = resolved_tickers or set()
    fills_by_ticker = _filled_trades_by_ticker(existing_trades)
    exits_by_ticker = _exit_trades_by_ticker(existing_trades)
    exit_trades = []

    for ticker, trade in fills_by_ticker.items():
        if ticker in resolved_tickers:
            continue

        prior_exits = exits_by_ticker.get(ticker, [])
        realized_exit_pnl = round(
            sum(float(exit_trade.get("realized_pnl_dollars", 0) or 0) for exit_trade in prior_exits),
            2,
        )
        exited_quantity = sum(int(exit_trade.get("quantity", 0) or 0) for exit_trade in prior_exits)
        fill_quantity = int(trade.get("quantity", 0) or 0)
        remaining_quantity = fill_quantity - exited_quantity
        if remaining_quantity <= 0:
            continue

        market = markets_by_ticker.get(ticker)
        if not market:
            continue

        current_yes_price = market.get("last_price")
        if current_yes_price is None:
            current_yes_price = market.get("yes_ask")
        if current_yes_price is None:
            current_yes_price = market.get("yes_bid")
        if current_yes_price is None:
            continue

        remaining_pnl = trade_mark_to_market_pnl_dollars(
            trade,
            current_yes_price,
            quantity=remaining_quantity,
        )
        remaining_notional = paper_trade_notional_dollars(
            trade.get("price"),
            remaining_quantity,
            trade.get("decision"),
        )
        original_notional = paper_trade_notional_dollars(
            trade.get("price"),
            fill_quantity,
            trade.get("decision"),
        )
        if remaining_pnl is None or not remaining_notional or not original_notional:
            continue

        cumulative_pnl = realized_exit_pnl + remaining_pnl
        cumulative_roi = cumulative_pnl / original_notional
        has_partial_exit = any(
            str(exit_trade.get("reason", "")).startswith("take_profit_partial")
            for exit_trade in prior_exits
        )

        if cumulative_roi >= PAPER_TAKE_PROFIT_FULL_PCT:
            exit_trades.append(
                build_paper_exit(
                    trade,
                    current_yes_price,
                    remaining_quantity,
                    reason="take_profit_full",
                )
            )
            continue

        if cumulative_roi >= PAPER_TAKE_PROFIT_PARTIAL_PCT and not has_partial_exit:
            exit_quantity = max(1, remaining_quantity // 2)
            if exit_quantity >= remaining_quantity and remaining_quantity > 1:
                exit_quantity = remaining_quantity - 1
            exit_trades.append(
                build_paper_exit(
                    trade,
                    current_yes_price,
                    exit_quantity,
                    reason="take_profit_partial",
                )
            )

    return exit_trades


def paper_trade_candidates(signals, existing_trades, outcomes_by_ticker=None):
    executed_trades = []
    blocked_trades = []

    if not PAPER_TRADING_ENABLED:
        return executed_trades, [
            {
                "ticker": signal.get("ticker"),
                "event_ticker": signal.get("event_ticker"),
                "status": "paper_blocked",
                "reason": "paper_trading_disabled",
            }
            for signal in signals
        ]

    trade_date = datetime.now(timezone.utc).date().isoformat()
    all_trades = list(existing_trades)

    for signal in signals:
        allowed, reason = check_signal_risk(
            signal,
            executed_trades,
            all_trades,
            trade_date,
            outcomes_by_ticker,
        )
        if not allowed:
            blocked_trades.append(
                {
                    "ticker": signal.get("ticker"),
                    "event_ticker": signal.get("event_ticker"),
                    "decision": signal.get("decision"),
                    "price": signal.get("price"),
                    "score": signal.get("score"),
                    "trade_date": trade_date,
                    "status": "paper_blocked",
                    "reason": reason,
                }
            )
            continue

        trade = build_paper_trade(signal)
        executed_trades.append(trade)
        all_trades.append(trade)

    return executed_trades, blocked_trades
