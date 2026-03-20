# thumm_bot

`thumm_bot` is a Kalshi market scanner and paper-trading system built around short-horizon opportunity selection, local market snapshotting, bankroll-aware paper execution, and review tooling.

## Features

- Pulls and normalizes open Kalshi markets
- Snapshots market data locally for replay and offline analysis
- Scores `YES` and `NO` setups with a short-horizon bias
- Runs bankroll-constrained paper trading with duplicate-event protection
- Tracks open positions, partial exits, resolved outcomes, and portfolio PnL
- Includes dashboard and post-run review scripts

## Trading Profile

- Prefers markets closing within 24 hours
- Limits longer-dated exposure to a small share of open positions
- Caps deployment at 80% of capital base instead of a fixed position count
- Uses staged profit taking:
  - trim at `+100%` ROI
  - fully exit remaining size at `+200%` ROI

## Requirements

- Python 3.11+
- `requests`
- Live network access to:
  - `https://api.elections.kalshi.com/trade-api/v2`

Install dependencies:

```bash
python3 -m pip install requests
```

## Quick Start

Run the signal scanner:

```bash
python3 main.py
```

Run paper trading once:

```bash
python3 paper_trade.py
```

Run paper trading continuously:

```bash
python3 paper_trade.py --loop
```

Open the paper dashboard:

```bash
python3 paper_dashboard.py
```

Refresh markets before rendering the dashboard:

```bash
python3 paper_dashboard.py --refresh
```

Loop the dashboard:

```bash
python3 paper_dashboard.py --loop
```

## Review

Paper-trade review:

```bash
python3 paper_trade_review.py
```

Raw signal review:

```bash
python3 backtest.py
```

## Project Layout

- [`kalshi_bot/collector`](/home/thumm/kalshi_bot/kalshi_bot/collector) fetch and snapshot logic
- [`kalshi_bot/strategy`](/home/thumm/kalshi_bot/kalshi_bot/strategy) market evaluation and ranking
- [`kalshi_bot/execution`](/home/thumm/kalshi_bot/kalshi_bot/execution) risk rules, fills, and exits
- [`kalshi_bot/analysis`](/home/thumm/kalshi_bot/kalshi_bot/analysis) portfolio, outcomes, and metrics
- [`kalshi_bot/storage`](/home/thumm/kalshi_bot/kalshi_bot/storage) JSON persistence and market cache helpers

Top-level scripts:

- [`main.py`](/home/thumm/kalshi_bot/main.py)
- [`paper_trade.py`](/home/thumm/kalshi_bot/paper_trade.py)
- [`paper_dashboard.py`](/home/thumm/kalshi_bot/paper_dashboard.py)
- [`paper_trade_review.py`](/home/thumm/kalshi_bot/paper_trade_review.py)
- [`backtest.py`](/home/thumm/kalshi_bot/backtest.py)
- [`settlement_updater.py`](/home/thumm/kalshi_bot/settlement_updater.py)

## Runtime Data

Runtime files live under [`data/`](/home/thumm/kalshi_bot/data) and are ignored by git.

- `data/raw_markets/` raw market snapshots
- `data/markets_latest.json` latest fetched market set
- `data/recent_markets.json` ticker-level market cache
- `data/log.json` signal history
- `data/paper_trades.json` paper fills, exits, and blocked attempts
- `data/outcomes.json` resolved outcomes

## Notes

- The repo currently supports paper trading only. There is no live order execution layer yet.
- Collector-side short-horizon targeting depends on what Kalshi exposes through market pagination.
- Strategy tuning notes live in [docs/strategy_notes.md](/home/thumm/kalshi_bot/docs/strategy_notes.md).
