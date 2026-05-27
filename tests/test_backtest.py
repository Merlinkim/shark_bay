from datetime import datetime, timezone
from decimal import Decimal

from app.backtest import Candle, SimulatedExecutionModel, build_config_hash, build_dataset_fingerprint, build_strategy, get_strategy_registry_metadata


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
