from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.backtest import Candle
from app.experiments import dataset_fingerprint, run_deterministic_placeholder_experiment


def candle(ts: int, close: str) -> Candle:
    return Candle(symbol="BTCUSDT", open_time=datetime.fromtimestamp(ts, tz=timezone.utc), close=Decimal(close))


def test_dataset_fingerprint_is_deterministic():
    candles = [candle(1, "100"), candle(2, "101")]
    assert dataset_fingerprint(candles, "BTCUSDT", "1m") == dataset_fingerprint(candles, "BTCUSDT", "1m")


@patch("app.experiments.CandleRepository.get_candles")
def test_experiment_shape(mock_get):
    mock_get.return_value = [candle(1, "100"), candle(2, "101"), candle(3, "102")]
    result = run_deterministic_placeholder_experiment("ema_cross_v1", "BTCUSDT", "1m", 24, "postgresql://demo")
    assert result.experiment_id
    assert result.strategy_name == "ema_cross_v1"
    assert result.dataset_row_count == 3
    assert result.status.startswith("simulated_placeholder")


@patch("app.experiments.CandleRepository.get_candles")
def test_insufficient_data_does_not_crash(mock_get):
    mock_get.return_value = [candle(1, "100")]
    result = run_deterministic_placeholder_experiment("ema_cross_v1", "BTCUSDT", "1m", 24, "postgresql://demo")
    assert result.status == "simulated_placeholder_insufficient_data"
    assert result.trade_count == 0
