from argparse import ArgumentParser

from kalshi_bot.analysis.settlement import build_outcome_entry, is_resolved_market
from kalshi_bot.collector.kalshi_client import fetch_market_by_ticker
from kalshi_bot.storage.logger import read_outcomes_log, read_signal_log, upsert_outcomes


def parse_args():
    parser = ArgumentParser(description="Refresh resolved outcomes for logged Kalshi signals.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only inspect this many unresolved tickers.",
    )
    parser.add_argument(
        "--refresh-all",
        action="store_true",
        help="Re-fetch all signal tickers, including ones already stored in outcomes.json.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    signals = read_signal_log()
    existing_outcomes = read_outcomes_log()
    existing_by_ticker = {entry.get("ticker"): entry for entry in existing_outcomes if entry.get("ticker")}

    tickers = []
    for signal in signals:
        ticker = signal.get("ticker")
        if not ticker:
            continue
        if not args.refresh_all and ticker in existing_by_ticker:
            continue
        tickers.append(ticker)

    unique_tickers = list(dict.fromkeys(tickers))
    if args.limit is not None:
        unique_tickers = unique_tickers[: args.limit]

    fetched_count = 0
    resolved_count = 0
    outcome_entries = []

    for ticker in unique_tickers:
        market = fetch_market_by_ticker(ticker)
        fetched_count += 1
        if not market or not is_resolved_market(market):
            continue
        outcome_entries.append(build_outcome_entry(market))
        resolved_count += 1

    if outcome_entries:
        upsert_outcomes(outcome_entries)

    print(f"Signals scanned: {len(unique_tickers)}")
    print(f"Market fetches attempted: {fetched_count}")
    print(f"Resolved outcomes stored: {resolved_count}")


if __name__ == "__main__":
    main()
