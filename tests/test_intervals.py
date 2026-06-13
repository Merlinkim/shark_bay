"""Phase 2 — interval generalization (1h/4h/8h) and interval-aware Sharpe."""
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.backtest import (
    Candle,
    DatasetFingerprint,
    INTERVAL_MINUTES,
    SimulatedExecutionModel,
    resample_candles,
)
from app.stats import BARS_PER_YEAR, annualized_sharpe


def _candle(ts, o, h, l, c, v="1"):
    return Candle(
        symbol="BTCUSDT", open_time=ts, close=Decimal(c),
        open=Decimal(o), high=Decimal(h), low=Decimal(l), volume=Decimal(v),
    )


def test_bars_per_year_has_funding_intervals():
    assert BARS_PER_YEAR["8h"] == 365.0 * 3.0
    assert BARS_PER_YEAR["4h"] == 365.0 * 6.0
    assert "8h" in INTERVAL_MINUTES and INTERVAL_MINUTES["8h"] == 480


def test_resample_1m_to_8h_ohlcv():
    start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    # 480 one-minute candles = exactly one 8h bucket
    candles = []
    for i in range(480):
        price = 100 + i
        candles.append(_candle(start + timedelta(minutes=i), price, price + 5, price - 5, price, "2"))
    bars = resample_candles(candles, "8h")
    assert len(bars) == 1
    bar = bars[0]
    assert bar.open_time == start
    assert bar.open_ == Decimal(100)          # first open
    assert bar.close == Decimal(100 + 479)     # last close
    assert bar.high_ == Decimal(100 + 479 + 5)  # max high
    assert bar.low_ == Decimal(100 - 5)         # min low
    assert bar.volume == Decimal(480 * 2)       # summed volume


def test_resample_anchors_to_utc_buckets():
    # Two 8h buckets: 00:00 and 08:00
    start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    candles = [_candle(start + timedelta(minutes=i), 100, 100, 100, 100) for i in range(600)]
    bars = resample_candles(candles, "8h")
    assert [b.open_time.hour for b in bars] == [0, 8]


def test_resample_1m_is_identity():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [_candle(start + timedelta(minutes=i), 100, 100, 100, 100) for i in range(10)]
    assert resample_candles(candles, "1m") == candles


def test_unsupported_interval_rejected():
    with pytest.raises(ValueError):
        resample_candles([], "3m")


def test_sharpe_annualization_differs_by_interval():
    returns = [0.01, -0.005, 0.008, -0.002, 0.006] * 20
    s_1m = annualized_sharpe(returns, "1m")
    s_8h = annualized_sharpe(returns, "8h")
    # Same return series, different annualization factor → 8h scaled by sqrt(1095)
    # vs 1m by sqrt(525600). Ratio must equal sqrt(BARS ratio).
    assert s_1m != s_8h
    expected_ratio = math.sqrt(BARS_PER_YEAR["1m"] / BARS_PER_YEAR["8h"])
    assert (s_1m / s_8h) == pytest.approx(expected_ratio, rel=1e-9)


def test_engine_uses_its_interval_for_sharpe():
    # An engine constructed with interval=8h must annualize with the 8h factor,
    # not the old hardcoded 1m. Build a simple winning ramp on 8h bars.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_candle(start + timedelta(hours=8 * i), 100 + i, 100 + i + 1, 100 + i - 1, 100 + i + 0.5)
            for i in range(60)]
    fp = DatasetFingerprint("fp", len(bars), bars[0].open_time, bars[-1].open_time)

    class AlwaysLong:
        strategy_name = "always_long"
        def on_candle(self, candle):
            return 1

    res_8h = SimulatedExecutionModel(interval="8h").run(bars, AlwaysLong(), "h", fp)
    res_1m = SimulatedExecutionModel(interval="1m").run(bars, AlwaysLong(), "h", fp)
    # Identical trades/returns, but the annualized Sharpe must scale with interval.
    assert res_8h.sharpe != res_1m.sharpe
