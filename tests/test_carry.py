"""Delta-neutral carry construction: accounting, leakage, costs, utilization."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.backtest import Candle
from app.carry import build_carry_returns
from app.funding import FundingEvent, align_funding_to_candles


def _series(prices_spot, prices_perp, fundings, start=None):
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    spot, perp = [], []
    for i, (ps, pp, f) in enumerate(zip(prices_spot, prices_perp, fundings)):
        t = start + timedelta(hours=8 * i)
        spot.append(Candle(symbol="BTCUSDT", open_time=t, close=Decimal(str(ps)),
                           open=Decimal(str(ps)), high=Decimal(str(ps)), low=Decimal(str(ps)), volume=Decimal("1")))
        perp.append(Candle(symbol="BTCUSDT", open_time=t, close=Decimal(str(pp)),
                           open=Decimal(str(pp)), high=Decimal(str(pp)), low=Decimal(str(pp)), volume=Decimal("1"),
                           funding_rate=Decimal(str(f)) if f is not None else None))
    return spot, perp


def test_pure_funding_with_no_price_move():
    # Flat prices, constant positive funding → carry ≈ funding each bar (minus
    # entry/exit cost), scaled by utilization, no basis term.
    n = 12
    spot, perp = _series([100] * n, [100] * n, [0.001] * n)
    cs = build_carry_returns(spot, perp, capital_utilization=1.0,
                             fee_bps_per_side=0.0, slippage_bps_per_side=0.0)
    # All interior bars: return == funding (1.0 utilization, no cost)
    interior = cs.returns_on_capital[1:-1]
    assert all(abs(r - 0.001) < 1e-12 for r in interior)
    assert all(abs(b) < 1e-12 for b in cs.basis_component[1:])  # flat prices → no basis


def test_short_perp_pays_on_negative_funding():
    n = 6
    spot, perp = _series([100] * n, [100] * n, [-0.001] * n)
    cs = build_carry_returns(spot, perp, capital_utilization=1.0,
                             fee_bps_per_side=0.0, slippage_bps_per_side=0.0)
    # Negative funding → short perp pays → negative carry
    assert all(r < 0 for r in cs.returns_on_capital[1:-1])


def test_basis_tracking_term():
    # Spot rises 1%, perp flat → long spot gains, short perp flat → +1% basis term.
    spot, perp = _series([100, 101, 101], [100, 100, 100], [0.0, 0.0, 0.0])
    cs = build_carry_returns(spot, perp, capital_utilization=1.0,
                             fee_bps_per_side=0.0, slippage_bps_per_side=0.0)
    # Candle i=1 (spot 100→101) is output index 0: spot_ret=+0.01, perp_ret=0.
    assert cs.basis_component[0] == pytest.approx(0.01, rel=1e-9)


def test_capital_utilization_scales_return_not_sharpe():
    n = 20
    spot, perp = _series([100] * n, [100] * n, [0.001] * n)
    full = build_carry_returns(spot, perp, capital_utilization=1.0,
                               fee_bps_per_side=0.0, slippage_bps_per_side=0.0)
    half = build_carry_returns(spot, perp, capital_utilization=0.5,
                               fee_bps_per_side=0.0, slippage_bps_per_side=0.0)
    # Returns halve; the per-bar ratio is exactly the utilization factor.
    for rf, rh in zip(full.returns_on_capital[1:-1], half.returns_on_capital[1:-1]):
        assert rh == pytest.approx(0.5 * rf, rel=1e-9)


def test_entry_exit_costs_charged_once_each():
    n = 10
    spot, perp = _series([100] * n, [100] * n, [0.0] * n)
    cs = build_carry_returns(spot, perp, capital_utilization=1.0,
                             fee_bps_per_side=10.0, slippage_bps_per_side=2.0)
    leg = (10.0 + 2.0) / 1e4
    # Entry+exit = 2 events x 2 legs = 4 legs total; total_cost on capital.
    assert cs.total_cost == pytest.approx(2 * (2 * leg), rel=1e-9)


def test_rebalancing_adds_cost():
    n = 30
    spot, perp = _series([100] * n, [100] * n, [0.0] * n)
    no_rebal = build_carry_returns(spot, perp, capital_utilization=1.0, rebalance_every_bars=0)
    rebal = build_carry_returns(spot, perp, capital_utilization=1.0, rebalance_every_bars=5)
    assert rebal.total_cost > no_rebal.total_cost


def test_funding_asof_leakage_through_carry():
    # No-future-bleed invariant: the funding used for a bar must come from a
    # settlement at or before that bar's open. We place the ONLY settlement on the
    # last bar; every earlier bar's carry must therefore carry zero funding.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    spot, perp = _series([100] * 5, [100] * 5, [None] * 5, start=start)
    last_time = start + timedelta(hours=8 * 4)
    events = [FundingEvent(last_time, Decimal("0.005"))]

    perp_aligned = align_funding_to_candles(perp, events)
    cs = build_carry_returns(spot, perp_aligned, capital_utilization=1.0,
                             fee_bps_per_side=0.0, slippage_bps_per_side=0.0)
    # output index k corresponds to candle i=k+1; only the final bar (the
    # settlement bar) may carry funding — no earlier bar can see it.
    for k, t in enumerate(cs.open_times):
        if t < last_time:
            assert cs.funding_component[k] == 0.0, f"future funding leaked into bar {t}"
        else:
            assert cs.funding_component[k] == 0.005


def test_timeline_mismatch_rejected():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    spot, perp = _series([100, 100], [100, 100], [0.0, 0.0])
    perp[1] = Candle(symbol="BTCUSDT", open_time=start + timedelta(hours=1), close=Decimal("100"))
    with pytest.raises(ValueError):
        build_carry_returns(spot, perp)
