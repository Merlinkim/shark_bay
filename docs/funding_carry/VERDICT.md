# Funding Carry — Final Verdict

**Verdict: FAIL — trustworthy.**
**Date:** 2026-06-13
**Strategy:** `funding_carry` v0.1.0
**Instrument:** BTCUSDT perp, Binance USDⓈ-M futures, native 8h bars
**Data:** REAL Binance public REST — 5,478 8h bars and 5,478 funding settlements,
2021-06-01 → 2026-06-01. 5,477 bars carry an as-of funding rate (the first bar
legitimately has no prior settlement).

This is the first end-to-end, economically-motivated hypothesis SharkBay has
taken through the full v2 pipeline to a one-shot holdout. The objective was a
*trustworthy verdict*, not a PASS. We have one.

---

## Result summary

| Gate | Result | Evidence |
|------|--------|----------|
| Walk-forward (research) | **FAIL** | avg test Sharpe 0.112; only **17%** of test windows positive (need ≥60%); status=fail |
| Significance | **FAIL** | per-trade **t = 0.07** (need ≥2.0); block-bootstrap **p = 0.41** (need <0.05); DSR 0.515 (marginal pass) |
| Cost robustness | **FAIL** | +0.05% at 1.0×, **−8.2% at 1.5×**, **−15.8% at 2.0×** cost |
| Holdout (one-shot) | **FAIL / inert** | 0 trades: 2025-06→2026-06 funding never exceeded the 0.0002 threshold (max 0.000135) |

Selected config (by research-region avg test Sharpe over a pre-registered
6-point grid): `entry_threshold=0.0002, smoothing_window=1, oi filter off`.

## Why it failed (the economics, not a bug)

1. **No per-trade edge.** A t-statistic of 0.07 over 72 research-region trades
   says the average trade return is statistically indistinguishable from zero.
   The funding collected is almost exactly cancelled by adverse price drift on
   the contrarian side — precisely failure mode C1 in `FAILURE_MODES.md`.

2. **The "profit" is a cost mirage.** At the modeled 10 bps baseline the research
   region returns a trivial +0.05%. Stressed to a realistic-adverse 1.5× it
   collapses to −8.2%, and to −15.8% at 2.0×. An edge that only exists at exactly
   one cost assumption is not an edge (G5 fail).

3. **Concentrated, non-recurring winners.** Profit factor 18.7 with a 16% win
   rate means a handful of large deleveraging unwinds carry everything, and they
   do not recur often enough — only 17% of rolling test windows are positive. The
   bootstrap (p=0.41) confirms the Sharpe is well within noise.

4. **Regime compression killed the holdout.** The parameterization chosen on the
   higher-funding 2021–2025 era never activates in 2025–2026, where 8h funding
   compressed to a 0.46 bp median and a 1.35 bp maximum. The threshold that fired
   72 times in research fired **zero** times in the holdout. This is a genuine
   structural shift in the funding regime, independently corroborating that the
   simple carry tilt has no durable, regime-robust edge.

## What is trustworthy about this verdict

- **No look-ahead.** Funding is attached strictly as-of each bar; the engine
  charges funding on the position carried *into* each bar; the prefix-invariance
  leakage guard passed; the dedicated funding-shift leakage test passed.
- **Honest costs.** Unified 10 bps taker + 2 bps slippage, with explicit 1.5×/2×
  stress — the strategy fails the stress, and we report that as a fail.
- **Multiple-testing controlled.** DSR computed at the true trial count (6).
- **Holdout opened once.** Selection used only the research region; the holdout
  was read exactly once, after all tests passed.
- **All pre-holdout tests green** (cost, intervals, funding engine, strategy,
  and the full pre-existing v2 suite).

## Honest caveat on the holdout

The holdout was *inert* (0 trades), so it does not independently confirm the
strategy's loss — it confirms the selected threshold is inactive in the current
regime. The FAIL does **not** rest on the holdout: the research-region
walk-forward, significance, and cost-stress results are individually decisive.
Re-fitting the threshold to make the holdout trade would be holdout snooping and
was deliberately not done.

## Disposition

`funding_carry` v0.1.0 is **archived as a FAIL**. The directional, single-
instrument, threshold-tilt formulation of funding carry does not have an edge
that survives honest costs and significance testing on BTCUSDT.

## What the next iteration should test (not this milestone)

1. **Delta-neutral carry** (long spot / short perp) to strip the adverse price
   drift that cancelled the carry — requires the engine to model two instruments.
2. **Cross-sectional funding** across many perps (rank by funding, trade the
   extremes) rather than a single absolute threshold, which is inherently
   regime-fragile.
3. **Funding-change / acceleration** signals around deleveraging events, where
   the concentrated winners actually live, rather than steady-state carry.
