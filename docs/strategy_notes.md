# Strategy Notes

## Current Objective

Bias the bot toward shorter-duration paper trades while avoiding capital lock-up, duplicate event exposure, and low-quality illiquid markets.

## Current Rules

### Intake

- Prefer markets closing within 24 hours
- Reserve most scan capacity for short-horizon candidates
- Keep paging the Kalshi market feed longer when short-horizon coverage is thin
- Reject provisional and synthetic markets

### Evaluation

- Require valid bid/ask, non-extreme midpoint, and bounded spread
- Use duration-aware liquidity thresholds
- Score using edge, spread, displayed size, and volume
- Apply a short-horizon boost and longer-dated penalty

### Paper Execution

- No duplicate fill on the same ticker
- No duplicate fill on the same event
- Max deployment is 80% of capital base
- More than 24 hour trades can only make up 20% of the open book

### Exits

- Partial trim at `+100%` ROI
- Full exit at `+200%` ROI
- Resolved outcomes are refreshed from local snapshots first, then live API when available

## What We Learned From Initial Paper Runs

- The paper filter was materially better than the raw signal stream
- The `120-130` score bucket was weak and should be treated cautiously
- The strategy leaned too heavily toward `NO`
- Lack of exit logic caused capital to sit unnecessarily
- Incorrect `NO` cost basis accounting overstated some returns before it was fixed

## Known Weak Spots

- Short-horizon market quality can degrade quickly if liquidity thresholds are too loose
- Public market pagination may still hide some better short-dated candidates
- Event-level deduping can suppress multiple props from a single game or show
- Current logs are good for review, but not yet rich enough for deeper attribution analysis

## Likely Next Improvements

- Add time-based exits for stale positions
- Add score-band penalties directly into risk selection
- Track category-level performance and throttle weak market classes
- Separate ranking rules for sports, weather, mentions, and politics markets
- Add richer review output for partial exits and hold duration
