"""Generic cross-sectional long-short harness: accounting, neutrality, costs, leakage."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.backtest import Candle
from app.panel import as_of_universe, build_panel
from app.portfolio import run_cross_sectional_long_short


def _mk(sym, start, n, prices, fundings=None, vol="100000"):
    out = []
    for i in range(n):
        out.append(Candle(
            symbol=sym, open_time=start + timedelta(hours=8 * i), close=Decimal(str(prices[i])),
            open=Decimal(str(prices[i])), high=Decimal(str(prices[i])), low=Decimal(str(prices[i])),
            volume=Decimal(vol),
            funding_rate=Decimal(str(fundings[i])) if fundings else None,
        ))
    return out


def _panel(series):
    return build_panel(series, ["close", "volume", "funding_rate"])


def test_funding_income_dispersion_flat_prices():
    # 4 symbols, flat prices. Two high-funding, two low-funding. Short high, long
    # low → both legs receive funding → positive carry, no price PnL.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    n = 30
    series = {
        "HI1": _mk("HI1", start, n, [100] * n, [0.002] * n),
        "HI2": _mk("HI2", start, n, [100] * n, [0.0015] * n),
        "LO1": _mk("LO1", start, n, [100] * n, [-0.002] * n),
        "LO2": _mk("LO2", start, n, [100] * n, [-0.0015] * n),
        "BTCUSDT": _mk("BTCUSDT", start, n, [100] * n, [0.0] * n),
    }
    panel = _panel(series)
    uni = as_of_universe(panel, min_history_bars=1)
    res = run_cross_sectional_long_short(
        panel, uni, signal_field="funding_rate", top_k=2, smoothing_bars=1,
        rebalance_every_bars=7, per_leg_cost=0.0, capital_utilization=1.0,
    )
    # Positive total carry on flat prices.
    assert sum(res.returns_on_capital) > 0


def test_short_high_funding_long_low_funding_direction():
    # If we (incorrectly) flipped direction we'd lose; confirm sign.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    n = 20
    series = {
        "HI": _mk("HI", start, n, [100] * n, [0.003] * n),
        "LO": _mk("LO", start, n, [100] * n, [-0.003] * n),
        "M1": _mk("M1", start, n, [100] * n, [0.0005] * n),
        "M2": _mk("M2", start, n, [100] * n, [-0.0005] * n),
        "BTCUSDT": _mk("BTCUSDT", start, n, [100] * n, [0.0] * n),
    }
    panel = _panel(series)
    uni = as_of_universe(panel, min_history_bars=1)
    res = run_cross_sectional_long_short(
        panel, uni, signal_field="funding_rate", top_k=1, smoothing_bars=1,
        rebalance_every_bars=5, per_leg_cost=0.0, capital_utilization=1.0,
        rank_ascending_is_long=True,
    )
    assert sum(res.returns_on_capital) > 0


def test_turnover_cost_reduces_return():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    n = 40
    # Alternating funding ranks → forces turnover at each rebalance.
    def alt(sym, hi):
        f = [(0.002 if (i // 5) % 2 == (0 if hi else 1) else -0.002) for i in range(n)]
        return _mk(sym, start, n, [100] * n, f)
    series = {"A": alt("A", True), "B": alt("B", False),
              "C": alt("C", True), "D": alt("D", False),
              "BTCUSDT": _mk("BTCUSDT", start, n, [100] * n, [0.0] * n)}
    panel = _panel(series)
    uni = as_of_universe(panel, min_history_bars=1)
    free = run_cross_sectional_long_short(panel, uni, signal_field="funding_rate", top_k=2,
                                          rebalance_every_bars=5, per_leg_cost=0.0, smoothing_bars=1)
    costly = run_cross_sectional_long_short(panel, uni, signal_field="funding_rate", top_k=2,
                                            rebalance_every_bars=5, per_leg_cost=0.0017, smoothing_bars=1)
    assert costly.total_cost > 0
    assert sum(costly.returns_on_capital) < sum(free.returns_on_capital)


def test_dollar_neutral_zero_beta_when_legs_track_market():
    # If long and short legs move identically with the market, basket price beta ~0.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    n = 30
    # All symbols follow the same price path (perfectly correlated) → long-short
    # price PnL cancels → realized beta ~ 0.
    path = [100 * (1.01 ** i) for i in range(n)]
    series = {
        "HI": _mk("HI", start, n, path, [0.002] * n),
        "LO": _mk("LO", start, n, path, [-0.002] * n),
        "M1": _mk("M1", start, n, path, [0.001] * n),
        "M2": _mk("M2", start, n, path, [-0.001] * n),
        "BTCUSDT": _mk("BTCUSDT", start, n, path, [0.0] * n),
    }
    panel = _panel(series)
    uni = as_of_universe(panel, min_history_bars=1)
    res = run_cross_sectional_long_short(panel, uni, signal_field="funding_rate", top_k=2,
                                         rebalance_every_bars=7, per_leg_cost=0.0, smoothing_bars=1)
    assert abs(res.realized_beta) < 0.05


def test_capital_utilization_scales_returns():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    n = 20
    series = {
        "HI": _mk("HI", start, n, [100] * n, [0.002] * n),
        "LO": _mk("LO", start, n, [100] * n, [-0.002] * n),
        "M1": _mk("M1", start, n, [100] * n, [0.001] * n),
        "M2": _mk("M2", start, n, [100] * n, [-0.001] * n),
        "BTCUSDT": _mk("BTCUSDT", start, n, [100] * n, [0.0] * n),
    }
    panel = _panel(series)
    uni = as_of_universe(panel, min_history_bars=1)
    full = run_cross_sectional_long_short(panel, uni, signal_field="funding_rate", top_k=2,
                                          rebalance_every_bars=5, per_leg_cost=0.0,
                                          capital_utilization=1.0, smoothing_bars=1)
    half = run_cross_sectional_long_short(panel, uni, signal_field="funding_rate", top_k=2,
                                          rebalance_every_bars=5, per_leg_cost=0.0,
                                          capital_utilization=0.5, smoothing_bars=1)
    assert sum(half.returns_on_capital) == \
        __import__("pytest").approx(0.5 * sum(full.returns_on_capital), rel=1e-9)


def test_signal_leakage_shifting_future_does_not_change_past():
    # Truncating the panel to a prefix must not change returns already produced
    # on that prefix (the harness never reads beyond the current bar).
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    n = 40
    import random
    rng = random.Random(0)
    series = {}
    for sym in ("A", "B", "C", "D", "BTCUSDT"):
        f = [rng.uniform(-0.002, 0.002) for _ in range(n)]
        p = [100.0]
        for i in range(1, n):
            p.append(p[-1] * (1 + rng.uniform(-0.01, 0.01)))
        series[sym] = _mk(sym, start, n, p, f)
    panel_full = _panel(series)
    uni_full = as_of_universe(panel_full, min_history_bars=1)
    full = run_cross_sectional_long_short(panel_full, uni_full, signal_field="funding_rate", top_k=2,
                                          rebalance_every_bars=5, smoothing_bars=3)

    cut = 25
    series_cut = {s: c[:cut] for s, c in series.items()}
    panel_cut = _panel(series_cut)
    uni_cut = as_of_universe(panel_cut, min_history_bars=1)
    cutr = run_cross_sectional_long_short(panel_cut, uni_cut, signal_field="funding_rate", top_k=2,
                                          rebalance_every_bars=5, smoothing_bars=3)
    # Returns on the shared prefix must match exactly.
    for a, b in zip(cutr.returns_on_capital, full.returns_on_capital[:len(cutr.returns_on_capital)]):
        assert abs(a - b) < 1e-12
