# Delta-Neutral Carry — Pre-Registered Assumptions

Every favorable assumption is listed here so the verdict can be audited. These
were fixed *before* the holdout was opened.

## Position

- LONG spot + SHORT perp, equal notional, continuously held.
- 1:1 notional ⇒ delta-neutral at any price ⇒ **no price-rebalancing drag**.
- Funding direction: short perp **receives** funding when funding > 0 (the normal
  regime, positive ~85% of settlements), pays when < 0. Signed funding is used —
  negative-funding periods are not cherry-picked out.

## Return model (per 8h bar, on deployed notional)

    r_notional = (spot_ret − perp_ret) + funding_rate
                  \___ basis tracking ___/   \_ carry _/

`spot_ret − perp_ret` captures basis convergence; `funding_rate` is as-of the
bar's open (leakage-controlled by `align_funding_to_candles`).

## Costs (realistic, taker)

- Per leg: 10 bps fee + 2 bps slippage = 12 bps (the unified Phase 0 baseline).
- Entry and exit each touch **both** legs → 4 fills round trip.
- Optional periodic rebalancing adds 2-leg cost per event (off by default; the
  continuous 1:1 hold needs little).
- Cost stress: 1.0× / 1.5× / 2.0×.

## Operational complexity → deployability haircut

- **capital_utilization = 0.5 (baseline), 0.33 (stress).** Only half of capital
  is deployed as carry notional; the rest is a margin buffer that must sit idle
  to keep the short perp leg from being liquidated on a sharp rally. Return **on
  capital** is therefore the notional carry × utilization. Sharpe is unchanged by
  this haircut (it scales return and vol equally) — which is exactly why the
  verdict is gated on **return**, not Sharpe.

## Deployability bar (the milestone's actual question)

- **DEPLOY_RETURN_FLOOR = 4%/yr** net return on capital, measured **in the
  holdout (current regime)**. Rationale: a market-neutral book carries real
  operational and liquidation-tail risk that the smooth analytical series does
  not capture; below ~4%/yr on capital it does not compensate for that risk or
  beat simpler stablecoin yield, so it is not worth deploying.
- A statistically real, positive, but sub-floor edge is **WATCH**, not PASS.

## What the model deliberately omits (and why it caps a PASS)

The analytical series is smooth and omits: simultaneous two-leg fill risk, basis
dislocation during deleveraging, and **short-perp liquidation tail risk**. Real
cash-and-carry Sharpe is ~2–4, not the ~10–20 this series shows. Therefore an
analytical PASS would be *necessary but not sufficient* — deployment is gated on
a later execution/paper-trading milestone, never on this number alone.

## Trial accounting

`TRIAL_COUNT = 2` (BTC and ETH were both inspected) feeds the Deflated Sharpe.
