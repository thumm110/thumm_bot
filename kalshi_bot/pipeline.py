from kalshi_bot.collector.kalshi_client import fetch_markets
from kalshi_bot.collector.snapshots import save_market_snapshot
from kalshi_bot.config import PAPER_PREFERRED_MAX_HOLD_HOURS, SCAN_LIMIT, SHORT_HORIZON_SIGNAL_SHARE
from kalshi_bot.storage.logger import log_entry
from kalshi_bot.strategy.evaluator import evaluate_market


def _take_unique_events(results, limit, seen_events=None):
    seen_events = seen_events or set()
    selected = []
    for result in results:
        event = result.get("event_ticker") or result["ticker"].split("-")[0]
        if event in seen_events:
            continue

        seen_events.add(event)
        selected.append(result)
        if len(selected) >= limit:
            break

    return selected, seen_events


def run_signal_pipeline(history):
    markets = fetch_markets()
    snapshot_path = None
    if markets:
        snapshot_path = save_market_snapshot(markets)

    print(f"\n--- Scan Start ({len(markets)} markets) ---")
    if snapshot_path is not None:
        print(f"Saved raw snapshot to {snapshot_path}")
    else:
        print("No snapshot saved because no markets were fetched")

    results = []
    for market in markets:
        result = evaluate_market(market, history)
        if not result:
            continue

        results.append(result)
        key = result["ticker"]
        history.setdefault(key, [])
        history[key].append(result["decision"])
        history[key] = history[key][-5:]

    results.sort(
        key=lambda item: (
            item.get("hours_to_close") is None,
            item.get("hours_to_close", 10**9),
            -item.get("score", 0),
        )
    )

    short_results = [
        result
        for result in results
        if (result.get("hours_to_close") or 10**9) <= PAPER_PREFERRED_MAX_HOLD_HOURS
    ]
    long_results = [
        result
        for result in results
        if (result.get("hours_to_close") or 10**9) > PAPER_PREFERRED_MAX_HOLD_HOURS
    ]
    short_results.sort(key=lambda item: item.get("score", 0), reverse=True)
    long_results.sort(key=lambda item: item.get("score", 0), reverse=True)

    target_short_count = min(len(short_results), max(1, round(SCAN_LIMIT * SHORT_HORIZON_SIGNAL_SHARE)))
    top_results, seen_events = _take_unique_events(short_results, target_short_count)
    remaining_slots = SCAN_LIMIT - len(top_results)
    if remaining_slots > 0:
        more_short, seen_events = _take_unique_events(short_results, remaining_slots, seen_events)
        top_results.extend(more_short)
        remaining_slots = SCAN_LIMIT - len(top_results)
    if remaining_slots > 0:
        more_long, _ = _take_unique_events(long_results, remaining_slots, seen_events)
        top_results.extend(more_long)

    for rank, result in enumerate(top_results, start=1):
        logged_result = dict(result)
        logged_result["rank"] = rank
        if snapshot_path is not None:
            logged_result["snapshot_path"] = str(snapshot_path)

        print(
            f"{logged_result['ticker']} | {logged_result['decision']} | "
            f"price={logged_result['price']} | volume={logged_result['volume']} | "
            f"score={logged_result.get('score', 0)} | rank={rank}"
        )
        log_entry(logged_result)

    print(f"Logged {len(top_results)} decisions")
    print("--- Scan End ---\n")

    return top_results, snapshot_path
