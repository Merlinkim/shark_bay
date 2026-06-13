# Delta-Neutral Funding Carry — Deployability Verdict

**Verdict: FAIL — trustworthy.** Real but not deployable in the current regime.
**Date:** 2026-06-13
**Instrument:** BTCUSDT spot + perp, 8h, Binance. 5,931 aligned bars, 2021-01 → 2026-06.
**Question answered:** *Is delta-neutral carry deployable in the current regime
after realistic execution costs and operational complexity?* — **No.**

---

## Results

| Measure | Research (2021-01→2025-06) | Holdout (2025-06→2026-06) |
|---|---|---|
| Net return on capital (0.5 util) | 6.36%/yr | **1.53%/yr** |
| Annualized Sharpe (idealized) | 10.5 | 5.2 |
| Cost-robust at 1.5× | yes | yes (1.41%/yr) |

| Gate | Result |
|------|--------|
| Significance (t-stat / DSR / bootstrap) | **PASS** — t = 22.1, DSR = 1.0, p = 0.000 |
| Walk-forward (46 windows) | **FAIL** — avg test Sharpe 1.63 but only **56.5%** positive windows (need ≥60%) |
| Holdout positive | yes (+1.53%/yr) |
| Holdout meets 4%/yr deployability floor | **no** (1.53% ≪ 4%) |

**Classification → FAIL**, on two independent grounds that point the same way:

1. **Not robust.** Walk-forward positive-window fraction is 56.5%. Despite a high
   aggregate Sharpe, the carry has too many losing 30-day stretches — the
   windowing exposes the regime inconsistency the aggregate Sharpe hides.
2. **Not deployable.** Even ignoring (1), the holdout return on capital is
   1.53%/yr — far below the 4%/yr floor. This is precisely the *thin edge* case:
   statistically real (it clears significance overwhelmingly) but too small to
   compensate for the operational and liquidation-tail risk a real two-leg book
   carries. On deployability grounds alone it would be **WATCH**; combined with
   the walk-forward failure it is a **FAIL**.

## What this confirms

The carry **exists and is statistically undeniable** (t = 22) — the previous
directional FAIL was about price risk, not carry, and stripping price risk
confirms that. But the **compression thesis is validated by the holdout**: the
6.36%/yr available across 2021–2025 (inflated by the 2021 bull) collapses to
1.53%/yr in the most recent year. Single-name delta-neutral carry on BTC has
decayed below the deployability floor.

The high analytical Sharpe (5–10) is a trap: it reflects a tiny, consistent
return and **excludes** the liquidation-tail and basis-dislocation risk the model
cannot see. Gating on deployable *return* rather than Sharpe is what produced the
correct rejection — exactly the discipline mandated for this milestone.

## Trustworthiness

- No look-ahead: funding as-of joined; carry-level funding-shift leakage test
  passes; every return term realized at/before bar close.
- Honest costs (10+2 bps/leg, 4-fill round trips), cost stress 1.5×/2×, and a
  capital-utilization haircut for margin buffer.
- Significance at the true trial count.
- Holdout constructed and read exactly once.
- All pre-holdout tests green (152 passed; 3 unrelated pre-existing failures).

## Disposition

Single-name delta-neutral funding carry is **archived FAIL (not deployable in the
current regime).** Do **not** proceed to the expensive Stage 2 two-leg execution
engine for this formulation — the holdout already shows the edge is sub-floor.

## What the evidence now points to

The funding *level* has compressed, but this milestone says nothing about funding
*dispersion across perps*. When all funding compresses toward zero, the spread
between the highest- and lowest-funding perpetuals can persist. The natural,
evidence-driven next milestone is **cross-sectional funding (long-short across
many perps)** — which also needs the multi-symbol ingestion this milestone did
not build. That, not single-name carry, is where the remaining funding edge (if
any) lives.
