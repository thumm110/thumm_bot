import json
from pathlib import Path
from typing import Any

from kalshi_bot.analysis.backtest_metrics import (
    current_position_value_dollars,
    trade_mark_to_market_pnl_dollars,
    trade_notional_dollars,
    trade_pnl_dollars,
)
from kalshi_bot.config import DATA_DIR, PAPER_STARTING_BANKROLL_DOLLARS, RAW_MARKETS_DIR
from kalshi_bot.storage.market_cache import (
    read_recent_markets_cache,
    rebuild_recent_markets_cache_from_raw,
    write_recent_markets_cache,
)


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


def load_latest_markets_snapshot() -> list[dict[str, Any]]:
    latest_markets = _load_markets_file(DATA_DIR / "markets_latest.json")
    if latest_markets:
        return latest_markets

    if not RAW_MARKETS_DIR.exists():
        return []

    for path in sorted(RAW_MARKETS_DIR.glob("markets_*.json"), reverse=True):
        markets = _load_markets_file(path)
        if markets:
            return markets
    return []


def load_recent_market_by_ticker(ticker: str) -> dict[str, Any]:
    if not ticker or not RAW_MARKETS_DIR.exists():
        return {}

    for path in sorted(RAW_MARKETS_DIR.glob("markets_*.json"), reverse=True):
        markets = _load_markets_file(path)
        for market in markets:
            if market.get("ticker") == ticker:
                return market
    return {}


def load_recent_markets_by_ticker(tickers: set[str]) -> dict[str, dict[str, Any]]:
    if not tickers:
        return {}

    cached_markets = read_recent_markets_cache()
    matches = {ticker: cached_markets[ticker] for ticker in tickers if ticker in cached_markets}
    unresolved = set(tickers) - set(matches)
    if not unresolved:
        return matches

    if not cached_markets and RAW_MARKETS_DIR.exists():
        cached_markets = rebuild_recent_markets_cache_from_raw()
        matches = {ticker: cached_markets[ticker] for ticker in tickers if ticker in cached_markets}
        unresolved = set(tickers) - set(matches)
        if not unresolved:
            return matches

    if not RAW_MARKETS_DIR.exists():
        return matches

    found_markets: dict[str, dict[str, Any]] = {}
    for path in sorted(RAW_MARKETS_DIR.glob("markets_*.json"), reverse=True):
        markets = _load_markets_file(path)
        if not markets:
            continue

        for market in markets:
            ticker = market.get("ticker")
            if ticker not in unresolved:
                continue

            matches[ticker] = market
            found_markets[ticker] = market
            unresolved.remove(ticker)
            if not unresolved:
                break

        if not unresolved:
            break

    if found_markets:
        cached_markets.update(found_markets)
        write_recent_markets_cache(cached_markets)

    return matches


def mark_price_cents(market: dict[str, Any]) -> int | None:
    if not market:
        return None

    last_price = market.get("last_price")
    yes_bid = market.get("yes_bid")
    yes_ask = market.get("yes_ask")

    if last_price is not None:
        return int(last_price)
    if yes_bid is not None and yes_ask is not None:
        return round((yes_bid + yes_ask) / 2)
    if yes_bid is not None:
        return int(yes_bid)
    if yes_ask is not None:
        return int(yes_ask)
    return None


def build_portfolio_snapshot(paper_trades, outcomes, markets):
    outcomes_by_ticker = {entry.get("ticker"): entry for entry in outcomes if entry.get("ticker")}
    markets_by_ticker = {market.get("ticker"): market for market in markets if market.get("ticker")}

    filled_trades = [trade for trade in paper_trades if trade.get("status") == "paper_filled"]
    exit_trades_by_ticker = {}
    for trade in paper_trades:
        if trade.get("status") != "paper_exit_filled":
            continue
        ticker = trade.get("ticker")
        if not ticker:
            continue
        exit_trades_by_ticker.setdefault(ticker, []).append(trade)

    missing_tickers = {
        trade.get("ticker")
        for trade in filled_trades
        if trade.get("ticker")
        and trade.get("ticker") not in outcomes_by_ticker
        and trade.get("ticker") not in markets_by_ticker
    }
    historical_markets_by_ticker = load_recent_markets_by_ticker(missing_tickers)
    open_positions = []
    resolved_positions = []

    for trade in filled_trades:
        ticker = trade.get("ticker")
        prior_exits = exit_trades_by_ticker.get(ticker, [])
        exited_quantity = sum(int(exit_trade.get("quantity", 0) or 0) for exit_trade in prior_exits)
        filled_quantity = int(trade.get("quantity", 0) or 0)
        remaining_quantity = max(0, filled_quantity - exited_quantity)
        realized_exit_pnl = round(
            sum(float(exit_trade.get("realized_pnl_dollars", 0) or 0) for exit_trade in prior_exits),
            2,
        )

        outcome_entry = outcomes_by_ticker.get(ticker)
        resolved_outcome = None
        if outcome_entry:
            resolved_outcome = outcome_entry.get("resolved_outcome")

        if resolved_outcome in {"yes", "no"}:
            remaining_trade = dict(trade)
            remaining_trade["quantity"] = remaining_quantity
            remaining_notional = trade_notional_dollars(remaining_trade, quantity=remaining_quantity) or 0.0
            pnl_dollars = realized_exit_pnl
            if remaining_quantity > 0:
                unresolved_pnl = trade_pnl_dollars(remaining_trade, resolved_outcome)
                pnl_dollars = round(pnl_dollars + (unresolved_pnl or 0), 2)
            resolved_positions.append(
                {
                    "ticker": ticker,
                    "event_ticker": trade.get("event_ticker"),
                    "decision": trade.get("decision"),
                    "price": trade.get("price"),
                    "quantity": filled_quantity,
                    "remaining_quantity": remaining_quantity,
                    "exited_quantity": exited_quantity,
                    "notional_dollars": round(
                        trade_notional_dollars(trade, quantity=filled_quantity) or 0.0,
                        2,
                    ),
                    "remaining_notional_dollars": round(remaining_notional, 2),
                    "resolved_outcome": resolved_outcome,
                    "pnl_dollars": pnl_dollars,
                    "status": "resolved",
                }
            )
            continue

        if remaining_quantity <= 0:
            resolved_positions.append(
                {
                    "ticker": ticker,
                    "event_ticker": trade.get("event_ticker"),
                    "decision": trade.get("decision"),
                    "price": trade.get("price"),
                    "quantity": filled_quantity,
                    "remaining_quantity": 0,
                    "exited_quantity": exited_quantity,
                    "notional_dollars": round(
                        trade_notional_dollars(trade, quantity=filled_quantity) or 0.0,
                        2,
                    ),
                    "remaining_notional_dollars": 0.0,
                    "resolved_outcome": "open",
                    "pnl_dollars": realized_exit_pnl,
                    "status": "closed_via_exit",
                }
            )
            continue

        market = markets_by_ticker.get(ticker, {})
        if not market:
            market = historical_markets_by_ticker.get(ticker, {})
        current_yes_price = mark_price_cents(market)
        remaining_trade = dict(trade)
        remaining_trade["quantity"] = remaining_quantity
        current_value = current_position_value_dollars(
            remaining_trade,
            current_yes_price,
            quantity=remaining_quantity,
        )
        unrealized_pnl = trade_mark_to_market_pnl_dollars(
            remaining_trade,
            current_yes_price,
            quantity=remaining_quantity,
        )
        remaining_notional = trade_notional_dollars(remaining_trade, quantity=remaining_quantity)
        open_positions.append(
            {
                "ticker": ticker,
                "event_ticker": trade.get("event_ticker"),
                "decision": trade.get("decision"),
                "entry_price": trade.get("price"),
                "mark_price": current_yes_price,
                "quantity": remaining_quantity,
                "original_quantity": filled_quantity,
                "exited_quantity": exited_quantity,
                "notional_dollars": round(remaining_notional or 0.0, 2),
                "market_value_dollars": current_value,
                "unrealized_pnl_dollars": unrealized_pnl,
                "realized_pnl_dollars": realized_exit_pnl,
                "score": trade.get("score"),
                "trade_time": trade.get("trade_time"),
                "status": "open" if current_yes_price is not None else "open_unpriced",
            }
        )

    realized_pnl = round(
        sum(position.get("pnl_dollars", 0) or 0 for position in resolved_positions)
        + sum(position.get("realized_pnl_dollars", 0) or 0 for position in open_positions),
        2,
    )
    unrealized_pnl = round(
        sum(position.get("unrealized_pnl_dollars", 0) or 0 for position in open_positions),
        2,
    )
    open_notional = round(
        sum(position.get("notional_dollars", 0) or 0 for position in open_positions),
        2,
    )
    open_market_value = round(
        sum(position.get("market_value_dollars", 0) or 0 for position in open_positions),
        2,
    )
    cash = round(PAPER_STARTING_BANKROLL_DOLLARS + realized_pnl - open_notional, 2)
    equity = round(PAPER_STARTING_BANKROLL_DOLLARS + realized_pnl + unrealized_pnl, 2)

    open_positions.sort(
        key=lambda position: (
            position.get("unrealized_pnl_dollars") is None,
            position.get("unrealized_pnl_dollars", 0),
        ),
    )
    resolved_positions.sort(
        key=lambda position: position.get("pnl_dollars", 0),
        reverse=True,
    )

    return {
        "starting_bankroll_dollars": PAPER_STARTING_BANKROLL_DOLLARS,
        "cash_dollars": cash,
        "equity_dollars": equity,
        "realized_pnl_dollars": realized_pnl,
        "unrealized_pnl_dollars": unrealized_pnl,
        "open_notional_dollars": open_notional,
        "open_market_value_dollars": open_market_value,
        "open_positions": open_positions,
        "resolved_positions": resolved_positions,
        "filled_trade_count": len(filled_trades),
    }
