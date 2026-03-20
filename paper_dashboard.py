import argparse
import os
import time

from kalshi_bot.analysis.outcome_refresh import refresh_outcomes_for_paper_trades
from kalshi_bot.analysis.paper_portfolio import (
    build_portfolio_snapshot,
    load_latest_markets_snapshot,
)
from kalshi_bot.collector.kalshi_client import fetch_markets
from kalshi_bot.collector.snapshots import save_market_snapshot
from kalshi_bot.storage.logger import read_outcomes_log, read_paper_trades_log


def parse_args():
    parser = argparse.ArgumentParser(description="Render a terminal dashboard for paper trades.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch a fresh market snapshot before rendering.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Refresh the dashboard continuously.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Seconds between dashboard refreshes when --loop is used.",
    )
    return parser.parse_args()


def refresh_snapshot():
    markets = fetch_markets()
    if not markets:
        return []
    save_market_snapshot(markets)
    return markets


def render_dashboard(snapshot):
    lines = []
    lines.append("Paper Trading Dashboard")
    lines.append("=" * 80)
    lines.append(
        "Bankroll ${:.2f} | Cash ${:.2f} | Equity ${:.2f} | Realized PnL ${:.2f} | "
        "Unrealized PnL ${:.2f}".format(
            snapshot["starting_bankroll_dollars"],
            snapshot["cash_dollars"],
            snapshot["equity_dollars"],
            snapshot["realized_pnl_dollars"],
            snapshot["unrealized_pnl_dollars"],
        )
    )
    lines.append(
        "Open positions {} | Open notional ${:.2f} | Open mark value ${:.2f} | "
        "Resolved positions {}".format(
            len(snapshot["open_positions"]),
            snapshot["open_notional_dollars"],
            snapshot["open_market_value_dollars"],
            len(snapshot["resolved_positions"]),
        )
    )
    lines.append("")
    lines.append("Open Positions")
    lines.append("-" * 80)

    if not snapshot["open_positions"]:
        lines.append("None")
    else:
        lines.append(
            "Ticker                               Side Qty Entry Mark  Cost    Value   uPnL"
        )
        for position in snapshot["open_positions"]:
            mark_price = position.get("mark_price")
            current_value = position.get("market_value_dollars")
            unrealized_pnl = position.get("unrealized_pnl_dollars")
            lines.append(
                f"{position['ticker'][:35]:35} "
                f"{position.get('decision', '-')[:3]:3} "
                f"{int(position.get('quantity', 0)):3d} "
                f"{int(position.get('entry_price', 0) or 0):5d} "
                f"{('-' if mark_price is None else int(mark_price)):>4} "
                f"{position.get('notional_dollars', 0):7.2f} "
                f"{(0 if current_value is None else current_value):7.2f} "
                f"{(0 if unrealized_pnl is None else unrealized_pnl):6.2f}"
            )

    lines.append("")
    lines.append("Resolved Positions")
    lines.append("-" * 80)
    if not snapshot["resolved_positions"]:
        lines.append("None")
    else:
        lines.append("Ticker                               Side Outcome Qty  Cost    rPnL")
        for position in snapshot["resolved_positions"][:10]:
            lines.append(
                f"{position['ticker'][:35]:35} "
                f"{position.get('decision', '-')[:3]:3} "
                f"{position.get('resolved_outcome', '-')[:3]:7} "
                f"{int(position.get('quantity', 0)):3d} "
                f"{position.get('notional_dollars', 0):7.2f} "
                f"{(position.get('pnl_dollars', 0) or 0):6.2f}"
            )

    return "\n".join(lines)


def run_once(refresh=False):
    paper_trades = read_paper_trades_log()
    if refresh:
        markets = refresh_snapshot()
        outcomes = refresh_outcomes_for_paper_trades(
            paper_trades,
            allow_remote=bool(markets),
        )
    else:
        markets = load_latest_markets_snapshot()
        outcomes = read_outcomes_log()
    snapshot = build_portfolio_snapshot(paper_trades, outcomes, markets)
    print(render_dashboard(snapshot))


def main():
    args = parse_args()

    if not args.loop:
        run_once(refresh=args.refresh)
        return

    while True:
        os.system("clear")
        run_once(refresh=args.refresh)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
