# Cross-Sectional Funding Dispersion — Verdict

**Verdict: FAIL — trustworthy. Holdout NOT opened (stop condition triggered).**
**Date:** 2026-06-13
**Universe:** 24 liquid Binance perps, 8h, 2021-01 → 2026-06, 5,931 bars, avg ~23 eligible names.
**Config (Phase 0 constraints):** weekly rebalance, 3-bar funding smoothing, top-5/bottom-5 dollar-neutral, 17 bps/leg, 0.5 utilization.

---

## Result (research region 2021-01 → 2025-06)

| Measure | Value |
|---|---|
| Net return on capital | **−0.93%/yr** |
| Annualized Sharpe | −0.09 |
| Walk-forward (46 windows) | avg test Sharpe **−0.46**, 43% positive → **FAIL** |
| Significance | t = **−0.19**, DSR = 0.0, bootstrap p = 0.565 → **FAIL** |
| Realized beta | −0.027 (genuinely market-neutral ✓) |
| Cost stress 1.5× / 2× | −3.07% / −5.21% |

**Pre-holdout gates failed → holdout was NOT opened**, per the stop condition. There is no point spending the one-shot holdout on a thesis the research region already rejects.

## Why it failed — the price leg, not costs or turnover

Phase 0 measured **funding income only** and showed +25%/yr at weekly cadence. The full harness adds the **price PnL of the long-short basket**, and that flips the result negative. The funding spread (~+25%/yr) is real, but the price PnL of holding those same positions is a comparable **negative drag (~−26%/yr)**: systematically shorting the highest-funding names (crowded-long, high-momentum alts) loses on price in trending markets more than the funding collected, and longing the lowest-funding names does not compensate.

This is **the same failure mode as the two prior funding milestones** — adverse price drift cancels the carry — now confirmed cross-sectionally:
- Cost is not the killer (stress barely moves it; turnover at weekly cadence is fine).
- Neutrality works (beta ≈ 0).
- The **price selection** is the killer.

## The synthesis across three funding milestones

| Milestone | Price risk | Result |
|---|---|---|
| Directional carry | full | FAIL (t=0.07) |
| Delta-neutral single-name | stripped | Real but **+1.53%/yr** — sub-floor (thin) |
| Cross-sectional dispersion | reintroduced (long-short) | FAIL (−0.93%/yr) |

**Conclusion:** the funding signal's *pure* deployable core is real but thin (~1.5%/yr once price risk is fully stripped), and every formulation that takes price risk to amplify it is destroyed by adverse price drift. For SharkBay's deployability bar, the **funding family is exhausted** as a standalone edge.

## What is trustworthy here

- Generic, leakage-tested infrastructure (panel prefix-invariance, as-of universe survivorship, harness prefix-invariance).
- Genuine market-neutrality (measured beta −0.03), so the negative result is not a hidden-beta artifact.
- Honest costs + stress; significance on 4,835 observations.
- Holdout integrity preserved — not opened on a failing thesis.

## Durable asset delivered regardless of the FAIL

The milestone produced reusable, generic infrastructure that survives this verdict and powers the rest of the relative-value roadmap **without modification**:
`app/panel.py` (field-agnostic panel + as-of universe), `app/portfolio.py`
(generic cross-sectional long-short harness), `app/universe_ingest.py` (generic
multi-symbol ingestion). Cross-sectional momentum, pairs, lead-lag, and OI
research now plug into these directly.

## Disposition & next step

Per the pre-committed **family-exhaustion stop condition**: cross-sectional
dispersion FAILed, so the **funding family is declared exhausted**. The next
milestone should pivot to a **different family**. On the roadmap EV ranking, with
the multi-symbol backbone now built, the strongest candidates are:

1. **Cross-sectional momentum** — reuses the exact harness (rank on trailing
   return instead of funding); strong academic base; the price drift that *killed*
   funding dispersion is the *signal* here.
2. **Volatility risk premium** (short vol / variance, Deribit) — different family,
   structural premium, needs options data.

I recommend **cross-sectional momentum next**: it is nearly free given the
infrastructure just built, and the very price-momentum effect that destroyed the
funding basket is direct evidence that a momentum signal has something to capture.
