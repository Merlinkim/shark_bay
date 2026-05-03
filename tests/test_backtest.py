from datetime import datetime, timezone
from decimal import Decimal

from app.backtest import (
    Candle,
    SimulatedExecutionModel,
    SmaCrossoverStrategy,
    build_config_hash,
    build_dataset_fingerprint,
)


def c(ts: int, close: str) -> Candle:
    return Candle(symbol="BTCUSDT", open_time=datetime.fromtimestamp(ts, tz=timezone.utc), close=Decimal(close))


def test_sma_crossover_signals():
    strat = SmaCrossoverStrategy(short_window=2, long_window=3)
    assert strat.on_candle(c(1, "100")) == 0
    assert strat.on_candle(c(2, "101")) == 0
    assert strat.on_candle(c(3, "102")) == 1


def test_execution_model_runs_deterministically():
    candles = [c(1, "100"), c(2, "101"), c(3, "102"), c(4, "101"), c(5, "100")]
    strat = SmaCrossoverStrategy(short_window=2, long_window=3)
    dataset_fingerprint = build_dataset_fingerprint(candles)
    result = SimulatedExecutionModel(initial_cash=1000).run(
        candles,
        strat,
        config_hash="abc123",
        dataset_fingerprint=dataset_fingerprint,
    )

    assert isinstance(result.total_return_pct, float)
    assert result.trades >= 0
    assert result.final_equity > 0
    assert isinstance(result.max_drawdown_pct, float)
    assert isinstance(result.profit_factor, float)
    assert isinstance(result.average_trade_return_pct, float)
    assert len(result.equity_curve) == len(candles)
    assert result.summary_timestamp == "1970-01-01T00:00:05+00:00"
    assert result.config_hash == "abc123"
    assert result.dataset_row_count == 5
    assert result.dataset_min_open_time == "1970-01-01T00:00:01+00:00"
    assert result.dataset_max_open_time == "1970-01-01T00:00:05+00:00"


def test_config_hash_is_deterministic():
    config_a = {"symbol": "BTCUSDT", "short_window": 5, "long_window": 20}
    config_b = {"long_window": 20, "symbol": "BTCUSDT", "short_window": 5}
    assert build_config_hash(config_a) == build_config_hash(config_b)


def test_dataset_fingerprint_reproducible_for_same_window():
    candles_a = [c(100, "100"), c(160, "101"), c(220, "102")]
    candles_b = [c(100, "999"), c(160, "111"), c(220, "122")]
    fp_a = build_dataset_fingerprint(candles_a)
    fp_b = build_dataset_fingerprint(candles_b)

    assert fp_a.fingerprint == fp_b.fingerprint
    assert fp_a.row_count == 3
    assert fp_a.min_open_time == candles_a[0].open_time
    assert fp_a.max_open_time == candles_a[-1].open_time
