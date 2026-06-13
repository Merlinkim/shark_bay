# Cross-Sectional Momentum — Phase 0 Feasibility (pre-check)

Real Binance data, 24 liquid perps, 8h, 2021–2026. Dollar-neutral top-5/bottom-5
by trailing return (skip most-recent day), weekly rebalance, 17 bps/leg, 0.5
utilization. Reused the generic panel + as-of universe + cross-sectional harness.

## Results

| Lookback | Gross/yr | Net/yr | Sharpe | Beta | Regime net % (2021→2026) |
|----------|----------|--------|--------|------|--------------------------|
| 4 wk  | 11.9% | 8.6% | 0.68 | −0.01 | 37.0, 3.5, 9.6, 5.8, **−5.3, −9.8** |
| 8 wk  | 8.3% | 5.8% | 0.47 | −0.02 | 25.6, −10.0, 14.8, 0.9, **+2.2, −5.3** |
| 12 wk | 9.2% | 7.4% | 0.62 | −0.02 | 40.7, −1.8, 0.3, 3.1, **0.0, −5.1** |

## Reading

- **Full sample is genuinely positive and market-neutral** (net 6–9%/yr, beta ≈ 0)
  — far better than funding dispersion (−0.9%). The momentum effect the funding
  byproduct implied is real.
- **But the current regime (2025–26) is negative for every lookback.** 4wk:
  −5.3/−9.8; 8wk: +2.2/−5.3; 12wk: 0.0/−5.1. The edge has decayed/reversed in
  exactly the window the holdout would cover (2025-06 → 2026-06).

## Pre-check gate verdict: **FAIL**

The pre-registered gate was: *abort if net is not clearly positive across regimes,
especially the recent one.* The recent regime is **negative across all lookbacks**.
The holdout would, on this evidence, FAIL or land in WATCH. Spending a full
milestone to confirm a holdout failure I can already see would violate the
Phase 0 discipline. **Abort — no full milestone, no holdout.**

## Meta-finding

Two independent factors — funding carry/dispersion and now cross-sectional price
momentum — were strong pre-2024 and have **decayed in 2025–26**. This is
consistent evidence that simple, liquid, well-known premia on major crypto perps
have compressed in the current regime. Per the pre-committed stopping condition,
the **simple price-based cross-sectional family is declared exhausted in the
current regime**, and the next proposal pivots to the volatility-risk-premium
family (a structurally different return source — compensation for bearing tail
risk, which does not arbitrage away the way carry/momentum do).
