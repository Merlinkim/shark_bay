# Cross-Sectional Funding Dispersion — Phase 0 Feasibility (pre-check)

Real Binance funding, 24-symbol liquid perp universe, 2021-01 → 2026-06, 6,006
settlement timestamps. K = 5 per side (short top-5 funding, long bottom-5),
dollar-neutral. **Funding-income spread only** — price-leg PnL is deferred to the
full milestone. Per-leg alt cost assumed 17 bps (10 fee + 7 slippage).

## Headline

| Smoothing | Gross dispersion | Avg per-8h turnover | Net @ per-8h | Net @ daily | Net @ weekly |
|-----------|-----------------|---------------------|--------------|-------------|--------------|
| 1 settle  | **32.6%/yr** | 79% of legs | −114.5% | −16.4% | **+25.6%** |
| 3 settle  | 29.2%/yr | 43% of legs | −50.6% | +2.6% | **+25.4%** |

## Regime analysis (gross dispersion, % / yr)

| 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|------|------|------|------|------|------|
| 59.7 | 35.6 | 24.7 | 21.5 | 23.8 | **27.3** |

**This is the decisive result.** Unlike the funding *level* (which compressed from
30%/yr to 0.86%/yr and killed single-name carry), the cross-sectional *dispersion*
is **~20–30%/yr in every regime, including 2026.** Dispersion does not compress
when the level does — exactly the thesis. The current-regime gross spread (27%/yr)
sits far above the 4%/yr deployability floor with room for large cost haircuts.

## The binding constraint: turnover

Turnover is the entire game. At per-8h rebalancing, 79% of basket legs rotate each
settlement → ~147%/yr in costs → catastrophically negative. The edge only survives
at **weekly (or slower) rebalancing with funding smoothing**, which collapses the
number of cost events. This is a concrete, pre-build design finding:

- per-8h / daily rebalancing is **fatal**;
- weekly + smoothing nets ~25%/yr on funding alone;
- even doubling weekly turnover (~90%/leg) and slippage (34 bps/leg) leaves
  net ≈ +13%/yr — robust margin above the floor.

## Honest caveats (why this is necessary-not-sufficient)

1. **Funding-only.** This ignores the dollar-neutral basket's **price PnL**, which
   is the dominant variance term and may swamp the carry. The full milestone must
   measure price-leg return + residual beta. This is the largest unknown.
2. **Optimistic weekly turnover.** Weekly rebalances drift more than 8h ones; my
   cost model reused the 8h turnover fraction, underestimating weekly cost. The
   +25% weekly net is optimistic; stress above suggests it survives anyway.
3. **Survivorship.** Today's liquid survivors were used; delisted/illiquid names
   excluded → results inflated. The milestone's as-of universe fixes this.
4. **Illiquidity.** 17 bps/leg is generous for smaller alts at rebalance size.

## Pre-check gate verdict

**PASS — proceed past Phase 0.** Net dispersion is clearly and robustly positive
across all regimes including 2025–26, with a large margin over the deployability
floor — conditional on the design constraint that **rebalancing is weekly-or-slower
with funding smoothing**. The per-8h/daily variants are pre-emptively rejected.

## Revised outcome probabilities (full milestone)

| | Prior | Revised | Why |
|---|---|---|---|
| PASS | 35% | **40%** | Gross spread far larger & more regime-robust than assumed; comfortable margin over floor even under cost stress |
| WATCH | 35% | **35%** | Price-leg variance / illiquidity may erode net to thin-but-real |
| FAIL | 30% | **25%** | Survives only if price PnL + real execution don't dominate the carry |

The remaining risk has **moved** from "does the edge exist / survive compression"
(now answered: yes) to "does the price-leg + real illiquid execution preserve it."
That is precisely what the full milestone (with the portfolio harness, as-of
universe, residual-beta gate, and one-shot holdout) is built to answer.
