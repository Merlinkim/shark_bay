# Dynamic Strategy Architecture

Shark Bay now uses dynamic strategy discovery for research-only strategy modules.

## Discovery roots
- `strategies/builtin/`
- `strategies/gawain/`

`app.strategy_loader.StrategyLoader` scans both roots, validates module contract, and builds a unified in-memory registry.

## Strategy contract
Each strategy module must expose:
- `STRATEGY_META` with `strategy_id`, `strategy_type`, and `research_only=True`
- `required_features(params)`
- `prepare_features(df, params)`
- `generate_signals(df, params)`

Only `signal_strategy` is executable now. Future reserved types are recognized for architecture compatibility:
- `event_strategy`
- `pair_strategy`
- `portfolio_strategy`

## Sandbox rules
Loader rejects strategies that contain obvious prohibited I/O/network/db usage patterns (e.g., `psycopg`, `requests`, `socket`, file writes).

## Unified registry
The same StrategyLoader source now powers:
- `/strategies`
- `/strategies/registry`
- `/backtests/run` validation/execution path

This removes dual-registry drift and keeps UI-visible strategies executable unless marked `metadata_only`.

## Engine ownership boundaries
Strategies generate signals only. Backtest engine remains sole owner of execution simulation, fees, slippage, PnL, metrics, and persistence.
