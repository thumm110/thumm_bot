from argparse import ArgumentParser
from collections import Counter

from kalshi_bot.analysis.backtest_metrics import bucket_label, trade_pnl_dollars
from kalshi_bot.storage.logger import read_outcomes_log, read_paper_trades_log


def parse_args():
    parser = ArgumentParser(description="Analyze paper trades against resolved Kalshi outcomes.")
    parser.add_argument(
        "--bucket-size",
        type=int,
        default=10,
        help="Score bucket width for grouped performance stats.",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=1,
        help="Minimum resolved samples required to print a score bucket.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    paper_trades = read_paper_trades_log()
    outcomes = read_outcomes_log()
    outcomes_by_ticker = {entry.get("ticker"): entry for entry in outcomes if entry.get("ticker")}

    filled_trades = [trade for trade in paper_trades if trade.get("status") == "paper_filled"]
    blocked_trades = [trade for trade in paper_trades if trade.get("status") == "paper_blocked"]
    exit_trades = [trade for trade in paper_trades if trade.get("status") == "paper_exit_filled"]
    blocked_reasons = Counter(trade.get("reason", "unknown") for trade in blocked_trades)
    exit_trades_by_ticker = {}
    for trade in exit_trades:
        ticker = trade.get("ticker")
        if not ticker:
            continue
        exit_trades_by_ticker.setdefault(ticker, []).append(trade)

    resolved_rows = []
    unresolved_fills = 0

    for trade in filled_trades:
        ticker = trade.get("ticker")
        outcome_entry = outcomes_by_ticker.get(ticker)
        if not outcome_entry:
            unresolved_fills += 1
            continue

        resolved_outcome = outcome_entry.get("resolved_outcome")
        prior_exits = exit_trades_by_ticker.get(ticker, [])
        realized_exit_pnl = round(
            sum(float(exit_trade.get("realized_pnl_dollars", 0) or 0) for exit_trade in prior_exits),
            2,
        )
        exited_quantity = sum(int(exit_trade.get("quantity", 0) or 0) for exit_trade in prior_exits)
        filled_quantity = int(trade.get("quantity", 0) or 0)
        remaining_quantity = max(0, filled_quantity - exited_quantity)

        pnl_dollars = realized_exit_pnl
        if remaining_quantity > 0:
            remaining_trade = dict(trade)
            remaining_trade["quantity"] = remaining_quantity
            unresolved_pnl = trade_pnl_dollars(remaining_trade, resolved_outcome)
            if unresolved_pnl is None:
                unresolved_fills += 1
                continue
            pnl_dollars = round(pnl_dollars + unresolved_pnl, 2)

        if remaining_quantity <= 0 and not prior_exits and pnl_dollars == 0:
            unresolved_fills += 1
            continue

        resolved_rows.append(
            {
                "ticker": ticker,
                "score": float(trade.get("score", 0)),
                "decision": trade.get("decision"),
                "resolved_outcome": resolved_outcome,
                "pnl_dollars": pnl_dollars,
                "won": pnl_dollars > 0,
            }
        )

    print(f"Paper trades logged: {len(paper_trades)}")
    print(f"Paper fills: {len(filled_trades)}")
    print(f"Paper exits: {len(exit_trades)}")
    print(f"Paper blocks: {len(blocked_trades)}")
    if blocked_reasons:
        print("Blocked reasons:")
        for reason, count in blocked_reasons.most_common():
            print(f"{reason}: {count}")

    print(f"Resolved paper fills: {len(resolved_rows)}")
    print(f"Unresolved paper fills: {unresolved_fills}")

    if not resolved_rows:
        print("No resolved paper fills available yet. Run settlement_updater.py after markets settle.")
        return

    total_pnl = round(sum(row["pnl_dollars"] for row in resolved_rows), 2)
    total_wins = sum(1 for row in resolved_rows if row["won"])
    avg_pnl = total_pnl / len(resolved_rows)
    win_rate = total_wins / len(resolved_rows)

    print(
        f"Overall paper win rate: {win_rate:.1%} | "
        f"avg pnl: ${avg_pnl:.2f} | total pnl: ${total_pnl:.2f}"
    )

    buckets = {}
    for row in resolved_rows:
        label = bucket_label(row["score"], args.bucket_size)
        bucket = buckets.setdefault(
            label,
            {"count": 0, "wins": 0, "pnl_dollars": 0.0, "scores": []},
        )
        bucket["count"] += 1
        bucket["wins"] += int(row["won"])
        bucket["pnl_dollars"] += row["pnl_dollars"]
        bucket["scores"].append(row["score"])

    print("\nPaper trade score bucket summary:")
    for label in sorted(buckets):
        bucket = buckets[label]
        if bucket["count"] < args.min_samples:
            continue

        avg_bucket_pnl = bucket["pnl_dollars"] / bucket["count"]
        bucket_win_rate = bucket["wins"] / bucket["count"]
        avg_score = sum(bucket["scores"]) / bucket["count"]
        print(
            f"{label} | samples={bucket['count']} | win_rate={bucket_win_rate:.1%} | "
            f"avg_pnl=${avg_bucket_pnl:.2f} | avg_score={avg_score:.2f}"
        )


if __name__ == "__main__":
    main()
