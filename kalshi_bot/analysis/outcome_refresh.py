from kalshi_bot.analysis.settlement import build_outcome_entry, is_resolved_market
from kalshi_bot.analysis.paper_portfolio import load_recent_markets_by_ticker
from kalshi_bot.collector.kalshi_client import fetch_market_by_ticker
from kalshi_bot.storage.logger import read_outcomes_log, upsert_outcomes


def unresolved_filled_tickers(paper_trades, outcomes):
    resolved_tickers = {
        entry.get("ticker")
        for entry in outcomes
        if entry.get("ticker") and entry.get("resolved_outcome") in {"yes", "no"}
    }

    tickers = []
    for trade in paper_trades:
        if trade.get("status") != "paper_filled":
            continue
        ticker = trade.get("ticker")
        if not ticker or ticker in resolved_tickers:
            continue
        tickers.append(ticker)

    return list(dict.fromkeys(tickers))


def refresh_outcomes_for_paper_trades(paper_trades, allow_remote=True):
    outcomes = read_outcomes_log()
    tickers = unresolved_filled_tickers(paper_trades, outcomes)
    if not tickers:
        return outcomes

    resolved_entries = []
    local_markets_by_ticker = load_recent_markets_by_ticker(set(tickers))
    pending_remote = []

    for ticker in tickers:
        market = local_markets_by_ticker.get(ticker)
        if not market or not is_resolved_market(market):
            pending_remote.append(ticker)
            continue
        resolved_entries.append(build_outcome_entry(market))

    if allow_remote:
        for ticker in pending_remote:
            market = fetch_market_by_ticker(ticker)
            if not market or not is_resolved_market(market):
                continue
            resolved_entries.append(build_outcome_entry(market))

    if resolved_entries:
        upsert_outcomes(resolved_entries)
        outcomes = read_outcomes_log()

    return outcomes
