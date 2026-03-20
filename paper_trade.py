import argparse
import time

from kalshi_bot.analysis.outcome_refresh import refresh_outcomes_for_paper_trades
from kalshi_bot.analysis.paper_portfolio import load_latest_markets_snapshot
from kalshi_bot.config import SLEEP_TIME2
from kalshi_bot.execution.paper import paper_exit_candidates, paper_trade_candidates
from kalshi_bot.pipeline import run_signal_pipeline
from kalshi_bot.storage.logger import (
    log_paper_trade,
    read_paper_trades_log,
)

history = {}


def run_cycle():
    signals, _snapshot_path = run_signal_pipeline(history)
    latest_markets = load_latest_markets_snapshot()
    markets_by_ticker = {market.get("ticker"): market for market in latest_markets if market.get("ticker")}
    existing_trades = read_paper_trades_log()
    outcomes = refresh_outcomes_for_paper_trades(
        existing_trades,
        allow_remote=bool(signals),
    )
    outcomes_by_ticker = {entry.get("ticker"): entry for entry in outcomes if entry.get("ticker")}
    resolved_tickers = {
        entry.get("ticker")
        for entry in outcomes
        if entry.get("ticker") and entry.get("resolved_outcome") in {"yes", "no"}
    }
    exit_trades = paper_exit_candidates(
        existing_trades,
        markets_by_ticker,
        resolved_tickers,
    )
    for trade in exit_trades:
        log_paper_trade(trade)

    updated_trades = existing_trades + exit_trades
    paper_trades, blocked_trades = paper_trade_candidates(
        signals,
        updated_trades,
        outcomes_by_ticker,
    )

    print("--- Paper Trading ---")
    for trade in exit_trades:
        print(
            f"EXIT {trade['ticker']} | {trade['decision']} | "
            f"qty={trade['quantity']} | mark={trade['exit_price']} | "
            f"pnl=${trade['realized_pnl_dollars']:.2f} | reason={trade['reason']}"
        )

    for trade in paper_trades:
        print(
            f"FILLED {trade['ticker']} | {trade['decision']} | "
            f"qty={trade['quantity']} | price={trade['price']} | "
            f"notional=${trade['notional_dollars']:.2f} | score={trade.get('score', 0)}"
        )
        log_paper_trade(trade)

    for trade in blocked_trades:
        print(
            f"BLOCKED {trade['ticker']} | reason={trade['reason']} | "
            f"price={trade.get('price')} | score={trade.get('score', 0)}"
        )
        log_paper_trade(trade)

    print(f"Paper exits: {len(exit_trades)}")
    print(f"Paper fills: {len(paper_trades)}")
    print(f"Paper blocks: {len(blocked_trades)}")


def parse_args():
    parser = argparse.ArgumentParser(description="Run Kalshi paper-trading simulation.")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously with sleep intervals between paper-trading cycles.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.loop:
        run_cycle()
        return

    while True:
        run_cycle()
        print(f"Sleeping for {SLEEP_TIME2} seconds\n")
        time.sleep(SLEEP_TIME2)


if __name__ == "__main__":
    main()
