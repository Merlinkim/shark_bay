r"""Delta-neutral funding carry: per-bar return construction.

Models a continuously-held cash-and-carry position: LONG spot + SHORT perp at
equal notional. Because both legs are linear in price, a 1:1 notional hedge stays
delta-neutral at any price with no price-rebalancing. The position's economics
per bar are:

    r_notional_t = (spot_ret_t - perp_ret_t) + funding_t
                   \_______ basis tracking _______/   \__ carry __/

where funding_t is the rate SETTLED at bar t's open (the short perp receives it
when positive). spot_ret - perp_ret is the basis tracking term: small per bar,
and it captures basis convergence over the hold.

Two deployability adjustments, both pre-registered and documented in
DELTA_NEUTRAL_ASSUMPTIONS.md, separate "carry exists" from "carry is deployable":

  * capital_utilization: the deployed notional is only this fraction of capital;
    the rest is a margin buffer that must sit idle to survive an adverse move on
    the short perp leg (liquidation defense). Return ON CAPITAL is scaled by it.
  * two-leg costs: each entry and exit touches BOTH legs (4 fills round trip);
    optional periodic rebalancing adds more. Charged in return terms at the bars
    where they occur.

This module is PURE (no network, no DB) so the carry accounting is unit-testable.
Look-ahead is controlled upstream by the strict as-of funding join
(app.funding.align_funding_to_candles); every term in r_t is realized at or
before bar t's close.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.backtest import Candle


@dataclass(frozen=True)
class CarrySeries:
    open_times: list
    returns_on_capital: list[float]   # per-bar return on total capital (net of costs)
    gross_notional_returns: list[float]  # per-bar return on deployed notional (pre-cost)
    funding_component: list[float]
    basis_component: list[float]
    total_cost: float
    capital_utilization: float
    n_bars: int


def build_carry_returns(
    spot_candles: list[Candle],
    perp_candles: list[Candle],
    *,
    fee_bps_per_side: float = 10.0,
    slippage_bps_per_side: float = 2.0,
    capital_utilization: float = 0.5,
    rebalance_every_bars: int = 0,
    cost_multiplier: float = 1.0,
) -> CarrySeries:
    """Construct the delta-neutral carry return series.

    spot_candles and perp_candles must be on the same timeline (same open_times,
    ascending). perp_candles carry funding_rate (as-of, via
    align_funding_to_candles). Bars where either price or funding is missing are
    treated as flat (no position that bar).

    Costs (per leg, in fraction of notional) are (fee+slippage) * cost_multiplier.
    A full entry or exit = 2 legs. Charged on the first and last active bar, plus
    every `rebalance_every_bars` bars in between (0 disables interim rebalancing).
    """
    if len(spot_candles) != len(perp_candles):
        raise ValueError("spot and perp candle counts must match")
    for s, p in zip(spot_candles, perp_candles):
        if s.open_time != p.open_time:
            raise ValueError(f"timeline mismatch: {s.open_time} != {p.open_time}")

    leg_cost = ((fee_bps_per_side + slippage_bps_per_side) / 10_000.0) * cost_multiplier
    entry_exit_cost = 2.0 * leg_cost          # both legs
    rebalance_cost = 2.0 * leg_cost           # both legs, per rebalance event

    open_times: list = []
    r_cap: list[float] = []
    r_notional: list[float] = []
    funding_comp: list[float] = []
    basis_comp: list[float] = []
    total_cost = 0.0

    n = len(perp_candles)
    # Identify the first and last bar with a complete (price + funding) record.
    active = [
        i for i in range(1, n)
        if perp_candles[i].funding_rate is not None
        and spot_candles[i].close is not None and spot_candles[i - 1].close is not None
        and perp_candles[i].close is not None and perp_candles[i - 1].close is not None
    ]
    first_active = active[0] if active else None
    last_active = active[-1] if active else None

    for i in range(1, n):
        bar_time = perp_candles[i].open_time
        if i not in active:
            open_times.append(bar_time)
            r_cap.append(0.0)
            r_notional.append(0.0)
            funding_comp.append(0.0)
            basis_comp.append(0.0)
            continue

        spot_ret = float(spot_candles[i].close) / float(spot_candles[i - 1].close) - 1.0
        perp_ret = float(perp_candles[i].close) / float(perp_candles[i - 1].close) - 1.0
        funding = float(perp_candles[i].funding_rate)  # short perp receives when > 0

        basis_track = spot_ret - perp_ret
        gross = basis_track + funding

        # Costs at entry, exit, and periodic rebalances.
        cost = 0.0
        if i == first_active or i == last_active:
            cost += entry_exit_cost
        if rebalance_every_bars and i != first_active and i != last_active:
            if (i - first_active) % rebalance_every_bars == 0:
                cost += rebalance_cost
        total_cost += cost * capital_utilization

        net_notional = gross - cost
        open_times.append(bar_time)
        r_notional.append(net_notional)
        r_cap.append(net_notional * capital_utilization)
        funding_comp.append(funding)
        basis_comp.append(basis_track)

    return CarrySeries(
        open_times=open_times,
        returns_on_capital=r_cap,
        gross_notional_returns=r_notional,
        funding_component=funding_comp,
        basis_component=basis_comp,
        total_cost=total_cost,
        capital_utilization=capital_utilization,
        n_bars=len(r_cap),
    )
