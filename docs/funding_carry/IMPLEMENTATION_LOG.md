# Funding Carry Research Program — Implementation Log

Milestone executed end-to-end across five phases. All code changes preserve
backward compatibility with the ten existing strategies; the full pre-existing
v2 test suite remained green throughout (the only failures, 3 in
`test_experiments.py`, predate this work — they reference an unregistered
`rsi_mean_reversion_v1` spec and fail identically on the clean tree).

---

## Phase 0 — Unified transaction costs

- `app/backtest.py`: added `BINANCE_TAKER_FEE_BPS = 10.0`, `DEFAULT_SLIPPAGE_BPS
  = 2.0` as the single source of truth; `ExecutionConfig` now defaults to these
  and adds `cost_multiplier` (applied to both fee and slippage in
  `SimulatedExecutionModel`). `build_execution_config` reads `cost_multiplier`.
- `app/experiments.py`: inline fee 0.0004 → 0.0010 (was 4 bps vs the engine's
  6 bps — a strategy could look profitable in one path and not the other).
- Tests: `tests/test_cost_calibration.py` (4) — baseline, experiments-path parity,
  multiplier scaling, monotonic cost effect.

## Phase 1 — Funding + open-interest ingestion

- `app/migrations/20260613_0007_funding_open_interest.sql` + `app/schema.sql`:
  `funding_rates` and `open_interest` tables.
- `app/funding_backfill.py`: paginated Binance fapi pulls (`/fapi/v1/fundingRate`,
  `/futures/data/openInterestHist`), idempotent upserts, `--dry-run`, JSON
  summary — mirrors `rest_backfill.py`.
- Verified live: 22 settlement-aligned funding rows for a one-week window.

## Phase 2 — Interval generalization

- `app/stats.py`: added `4h` (2,190) and `8h` (1,095) to `BARS_PER_YEAR`.
- `app/backtest.py`: `INTERVAL_MINUTES` map; pure `resample_candles` (OHLCV
  aggregation anchored to UTC buckets); `CandleRepository` resamples coarser
  intervals from 1m with the holdout clamp applied on the 1m timeline first;
  **fixed the hardcoded `interval="1m"` Sharpe bug** — `SimulatedExecutionModel`
  now takes `interval` and annualizes correctly.
- `app/walk_forward.py`: relaxed the 1m-only guard; threads `interval` into the
  engine; added an optional pre-loaded `candles` parameter so a verdict can run
  fully in memory without a database.
- Tests: `tests/test_intervals.py` (7) — resample OHLCV/anchoring/identity,
  interval-aware Sharpe ratio, engine interval propagation.

## Phase 3 — Auxiliary data + funding PnL (leakage-safe)

- `app/backtest.py`: `Candle` gains optional `funding_rate` / `open_interest`;
  `DynamicSignalStrategy._frame` includes them only when present (legacy frame
  shape unchanged); the engine credits funding PnL on the position **carried
  into** each bar (`pnl = -position*size*equity*funding_rate`), a no-op when
  funding is absent → legacy behavior byte-identical.
- `app/funding.py`: Binance payload parsers + `align_funding_to_candles`, a
  STRICT as-of join (a bar sees only the latest settlement ≤ its open_time).
- Tests: `tests/test_funding_engine.py` (8) — funding sign symmetry (short
  receives positive funding on flat price, long pays), backward-compat,
  as-of correctness, **funding-shift leakage lock**, payload parsing.

## Phase 4 — Strategy + research documents

- `strategies/builtin/funding_carry.py`: sandboxed signal strategy — short when
  smoothed funding > threshold (collect funding + fade crowded longs), long when
  < −threshold; optional OI crowding filter. Reads only past/current rows.
- Docs: `FUNDING_CARRY_THESIS.md` (G0), `FAILURE_MODES.md`, `RESEARCH_PROTOCOL.md`.
- Tests: `tests/test_funding_carry_strategy.py` (8) — signal correctness, OI
  filter, smoothing, loader registration, and **prefix-invariance (no-lookahead)**
  through `build_strategy(...).set_candles(...)`.

## Phase 5 — Validation + holdout verdict

- Pre-holdout gate: full suite green (144 passed; 3 unrelated pre-existing fails).
- `scripts/run_funding_carry_verdict.py`: fetches REAL Binance 8h klines +
  funding (2021-06 → 2026-06), as-of joins, splits research (<2025-06) vs holdout
  (≥2025-06), walk-forward over a pre-registered 6-config grid, significance,
  1.0/1.5/2.0× cost stress, and opens the holdout exactly once.
- Raw output archived in `verdict_bundle.txt`.
- **Verdict: FAIL (trustworthy).** See `VERDICT.md`. Research-region walk-forward,
  significance, and cost-stress are each individually decisive; the holdout was
  inert (0 trades) because 2025–2026 funding compressed below the selected
  threshold — a genuine regime shift, not a defect.

## Files changed / added

Changed: `app/backtest.py`, `app/experiments.py`, `app/walk_forward.py`,
`app/stats.py`, `app/schema.sql`.
Added: `app/funding.py`, `app/funding_backfill.py`,
`app/migrations/20260613_0007_funding_open_interest.sql`,
`strategies/builtin/funding_carry.py`,
`scripts/run_funding_carry_verdict.py`,
`tests/test_cost_calibration.py`, `tests/test_intervals.py`,
`tests/test_funding_engine.py`, `tests/test_funding_carry_strategy.py`,
and the four `docs/funding_carry/*.md` documents.

---

## Follow-on milestone — Delta-Neutral Carry deployability verdict

After the directional FAIL, a feasibility study on real funding (2021–2026) showed
the carry itself is robustly positive (positive 85% of settlements, t≈38) — the
directional FAIL was about price risk, not carry. Approved milestone: test whether
DELTA-NEUTRAL carry is *deployable* in the current regime, with a deployability
bar (thin edge → WATCH, not PASS).

- `app/carry.py`: pure delta-neutral carry return construction (long spot / short
  perp; `r = (spot_ret − perp_ret) + funding − costs`, scaled by capital
  utilization). Leakage controlled by the as-of funding join.
- `tests/test_carry.py` (8): funding sign, basis term, utilization scaling,
  entry/exit + rebalance costs, and a carry-level no-future-bleed leakage test.
- `scripts/run_delta_neutral_carry_verdict.py`: real spot+perp+funding, research
  vs holdout, walk-forward + significance + cost/margin stress, FAIL/WATCH/PASS
  with a 4%/yr deployability floor. Holdout read once. Output archived in
  `delta_neutral_verdict_bundle.txt`.
- Docs: `DELTA_NEUTRAL_ASSUMPTIONS.md`, `DELTA_NEUTRAL_VERDICT.md`.
- Bug found & fixed mid-run: Binance spot klines cap at 1000/page (not 1500);
  pagination had silently stopped at 1,000 bars → empty holdout. Fixed to PAGE=1000.

**Verdict: FAIL (trustworthy).** Carry is statistically undeniable (t = 22.1) but
the holdout return on capital is **1.53%/yr** — far below the 4%/yr deployability
floor — and walk-forward positive-window fraction is 56.5% (<60%). The compression
thesis is confirmed: 6.36%/yr research → 1.53%/yr holdout. Single-name delta-neutral
carry is **not deployable in the current regime**; do not build the Stage 2 two-leg
execution engine for it. Evidence points to cross-sectional funding (dispersion)
as the next milestone.
