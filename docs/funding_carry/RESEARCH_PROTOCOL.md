# Funding Carry — Research Protocol (G0 → Holdout)

The protocol this milestone follows to reach a trustworthy verdict. Each gate
must pass before the next. The holdout is opened **exactly once**, only after
every test below is green.

---

## Data

- **Instrument:** BTCUSDT perp, Binance USDⓈ-M futures.
- **Bars:** native 8h klines (settlement-aligned).
- **Funding:** `GET /fapi/v1/fundingRate`, as-of joined to bars.
- **Costs:** 10 bps taker + 2 bps slippage (unified Phase 0 baseline), with 1.5×
  and 2.0× stress runs.

## Train / Holdout split

- The full history is split by date. The **research region** (training +
  walk-forward) is everything before `RESEARCH_HOLDOUT_START`. The **holdout** is
  everything on/after it.
- All parameter selection, walk-forward, and significance testing happen on the
  research region only. The holdout is never read during this phase.

## Gates

| Gate | Description | Pass criterion |
|------|-------------|----------------|
| **G0** | Hypothesis written | `FUNDING_CARRY_THESIS.md` exists with a falsifiable claim |
| **G1** | Prototype runs | Strategy loads, runs through the engine, leakage guard passes |
| **G2** | In-sample sanity | Positive in-sample return on the research region at baseline cost |
| **G3** | Walk-forward | `pass_fail_status == pass`: avg test Sharpe > 0, ≥60% positive test windows, validation→test degradation ≤ 0.5 |
| **G4** | Statistical significance | `significance_check` passes: per-trade t ≥ 2.0, DSR > 0.5 at logged trial count, block-bootstrap p < 0.05 |
| **G5** | Cost robustness | G3 + G4 still hold at 1.5× and 2.0× cost |
| **Holdout** | Final confirmation | Opened once, under `RESEARCH_HOLDOUT_UNLOCK=1`, logged; verdict recorded whether PASS or FAIL |

## Test-before-holdout requirement

Before the holdout is opened, the following must all pass:

- `test_cost_calibration.py` — unified costs
- `test_intervals.py` — interval generalization + Sharpe annualization
- `test_funding_engine.py` — funding PnL, as-of alignment, leakage lock
- `test_funding_carry_strategy.py` — signal correctness + prefix-invariance
- the pre-existing v2 suite (engine, walk-forward, significance) remains green

## Trial accounting (for the Deflated Sharpe)

Every parameter set evaluated on the research region is one trial. The trial
count fed to the DSR is the number of `funding_carry` configurations tested. This
milestone tests a small, pre-registered grid (documented in the implementation
log) to keep the multiple-testing penalty honest and small.

## Verdict

The verdict document records: the parameter set, the research-region walk-forward
+ significance results, the cost-stress results, the single holdout result, and a
plain-language PASS/FAIL with the identified failure mode if FAIL.
