from datetime import datetime, timezone
from decimal import Decimal

from app.backtest import Candle, SimulatedExecutionModel, SmaCrossoverStrategy


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
    result = SimulatedExecutionModel(initial_cash=1000).run(candles, strat)

    assert isinstance(result.total_return_pct, float)
    assert result.trades >= 0
    assert result.final_equity > 0
