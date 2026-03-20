from argparse import ArgumentParser

from kalshi_bot.analysis.backtest_metrics import bucket_label, trade_pnl_cents
from kalshi_bot.storage.logger import read_outcomes_log, read_signal_log


def parse_args():
    parser = ArgumentParser(description="Analyze logged Kalshi signals against resolved outcomes.")
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
    signals = read_signal_log()
    outcomes = read_outcomes_log()
    outcomes_by_ticker = {entry.get("ticker"): entry for entry in outcomes if entry.get("ticker")}

    resolved_rows = []
    unresolved_count = 0

    for signal in signals:
        ticker = signal.get("ticker")
        outcome_entry = outcomes_by_ticker.get(ticker)
        if not outcome_entry:
            unresolved_count += 1
            continue

        resolved_outcome = outcome_entry.get("resolved_outcome")
        pnl_cents = trade_pnl_cents(signal, resolved_outcome)
        if pnl_cents is None:
            unresolved_count += 1
            continue

        resolved_rows.append(
            {
                "ticker": ticker,
                "score": float(signal.get("score", 0)),
                "decision": signal.get("decision"),
                "resolved_outcome": resolved_outcome,
                "pnl_cents": pnl_cents,
                "won": pnl_cents > 0,
            }
        )

    print(f"Signals logged: {len(signals)}")
    print(f"Resolved signals: {len(resolved_rows)}")
    print(f"Unresolved signals: {unresolved_count}")

    if not resolved_rows:
        print("No resolved signals available yet. Run settlement_updater.py after markets settle.")
        return

    total_pnl = sum(row["pnl_cents"] for row in resolved_rows)
    total_wins = sum(1 for row in resolved_rows if row["won"])
    avg_pnl = total_pnl / len(resolved_rows)
    win_rate = total_wins / len(resolved_rows)

    print(
        f"Overall win rate: {win_rate:.1%} | "
        f"avg pnl: {avg_pnl:.2f} cents | total pnl: {total_pnl:.2f} cents"
    )

    buckets = {}
    for row in resolved_rows:
        label = bucket_label(row["score"], args.bucket_size)
        bucket = buckets.setdefault(
            label,
            {"count": 0, "wins": 0, "pnl_cents": 0.0, "scores": []},
        )
        bucket["count"] += 1
        bucket["wins"] += int(row["won"])
        bucket["pnl_cents"] += row["pnl_cents"]
        bucket["scores"].append(row["score"])

    print("\nScore bucket summary:")
    for label in sorted(buckets):
        bucket = buckets[label]
        if bucket["count"] < args.min_samples:
            continue

        avg_bucket_pnl = bucket["pnl_cents"] / bucket["count"]
        bucket_win_rate = bucket["wins"] / bucket["count"]
        avg_score = sum(bucket["scores"]) / bucket["count"]
        print(
            f"{label} | samples={bucket['count']} | win_rate={bucket_win_rate:.1%} | "
            f"avg_pnl={avg_bucket_pnl:.2f} cents | avg_score={avg_score:.2f}"
        )


if __name__ == "__main__":
    main()
