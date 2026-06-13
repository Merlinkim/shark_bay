"""Phase 0 — unified transaction-cost calibration.

Guards against the historical bug where three engine paths used different fees
(6 bps engine, 4 bps experiments). All paths must now derive from a single
10 bps Binance taker baseline, and the cost_multiplier must scale costs for
stress testing.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app import backtest
from app.backtest import (
    BINANCE_TAKER_FEE_BPS,
    Candle,
    DatasetFingerprint,
    ExecutionConfig,
    SimulatedExecutionModel,
    build_execution_config,
)


def test_default_fee_is_binance_taker_baseline():
    assert BINANCE_TAKER_FEE_BPS == 10.0
    assert ExecutionConfig().fee_bps == 10.0
    assert build_execution_config(None).fee_bps == 10.0


def test_experiments_path_matches_baseline():
    # experiments.py hardcodes its fee inline; assert it equals 10 bps (0.0010).
    import inspect

    from app import experiments

    src = inspect.getsource(experiments.run_real_backtest_experiment)
    assert "fee = 0.0010" in src, "experiments fee drifted from the 10 bps baseline"


def test_cost_multiplier_scales_fee_and_slippage():
    base = SimulatedExecutionModel(ExecutionConfig(cost_multiplier=1.0))
    stress = SimulatedExecutionModel(ExecutionConfig(cost_multiplier=2.0))
    assert stress.fee_rate == 2.0 * base.fee_rate
    assert stress.slippage_rate == 2.0 * base.slippage_rate


def _ramp_candles(n=120):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(symbol="BTCUSDT", open_time=start + timedelta(minutes=i), close=Decimal(100 + i))
        for i in range(n)
    ]


def test_higher_cost_multiplier_never_improves_fees():
    candles = _ramp_candles()
    fp = DatasetFingerprint("fp", len(candles), candles[0].open_time, candles[-1].open_time)

    class AlwaysLong:
        strategy_name = "always_long"

        def on_candle(self, candle):
            return 1

    base = SimulatedExecutionModel(ExecutionConfig(cost_multiplier=1.0)).run(
        candles, AlwaysLong(), "h", fp
    )
    stressed = SimulatedExecutionModel(ExecutionConfig(cost_multiplier=2.0)).run(
        candles, AlwaysLong(), "h", fp
    )
    # More cost can only reduce (or equal) realized equity and raise total fees.
    assert stressed.total_fees >= base.total_fees
    assert stressed.final_equity <= base.final_equity
