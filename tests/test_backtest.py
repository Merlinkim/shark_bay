from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.backtest import (
    Candle,
    ExecutionConfig,
    RiskConfig,
    SimulatedExecutionModel,
    build_config_hash,
    build_dataset_fingerprint,
    build_strategy,
    get_strategy_registry_metadata,
)


def c(ts: int, close: str) -> Candle:
    return Candle(symbol="BTCUSDT", open_time=datetime.fromtimestamp(ts, tz=timezone.utc), close=Decimal(close))


def test_execution_model_runs_deterministically():
    candles = [c(1, "100"), c(2, "101"), c(3, "102"), c(4, "101"), c(5, "100")]
    strat = build_strategy("sma_crossover", {"short_window": 2, "long_window": 3})
    dataset_fingerprint = build_dataset_fingerprint(candles)
    result = SimulatedExecutionModel(initial_cash=1000).run(candles, strat, config_hash="abc123", dataset_fingerprint=dataset_fingerprint)
    assert isinstance(result.total_return_pct, float)
    assert result.final_equity > 0


def test_config_hash_is_deterministic():
    assert build_config_hash({"a": 1, "b": 2}) == build_config_hash({"b": 2, "a": 1})


def test_registry_has_builtin_strategy():
    assert "sma_crossover" in get_strategy_registry_metadata()


class AlwaysLongStrategy:
    strategy_name = "always_long"
    description = "test"
    parameter_schema = {}
    default_parameters = {}

    def on_candle(self, candle: Candle) -> int:
        return 1


def test_max_holding_minutes_forced_exit_does_not_crash():
    candles = [c(1, "100"), c(61, "101"), c(121, "102"), c(181, "103")]
    dataset_fingerprint = build_dataset_fingerprint(candles)
    engine = SimulatedExecutionModel(
        execution_config=ExecutionConfig(initial_cash=1000.0),
        risk_config=RiskConfig(max_holding_minutes=1, stop_loss_pct=0.5, take_profit_pct=0.5),
    )
    result = engine.run(candles, AlwaysLongStrategy(), config_hash="cfg", dataset_fingerprint=dataset_fingerprint)
    assert result.final_equity > 0
    assert len(result.fills) >= 2


def test_fixed_fraction_position_sizing_works():
    candles = [c(1, "100"), c(61, "102"), c(121, "104")]
    dataset_fingerprint = build_dataset_fingerprint(candles)
    engine = SimulatedExecutionModel(
        execution_config=ExecutionConfig(initial_cash=1000.0, fee_bps=0.0, slippage_bps=0.0),
        risk_config=RiskConfig(position_size_mode="fixed_fraction", risk_per_trade=0.1, max_position_size=0.5),
    )
    result = engine.run(candles, AlwaysLongStrategy(), config_hash="cfg", dataset_fingerprint=dataset_fingerprint)
    assert result.final_equity > 1000.0


def test_invalid_position_size_mode_fails_cleanly():
    candles = [c(1, "100"), c(61, "101"), c(121, "102")]
    dataset_fingerprint = build_dataset_fingerprint(candles)
    engine = SimulatedExecutionModel(
        execution_config=ExecutionConfig(initial_cash=1000.0),
        risk_config=RiskConfig(position_size_mode="bad_mode"),
    )
    with pytest.raises(ValueError, match="Unsupported position_size_mode"):
        engine.run(candles, AlwaysLongStrategy(), config_hash="cfg", dataset_fingerprint=dataset_fingerprint)
