from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.backtest import Candle
from app.walk_forward import run_walk_forward_backtest


def _candles(start: datetime, count: int) -> list[Candle]:
    return [
        Candle(symbol="BTCUSDT", open_time=start + timedelta(minutes=i), close=Decimal(100 + i * 0.01))
        for i in range(count)
    ]


@patch("app.walk_forward._strategy_lookup")
@patch("app.walk_forward.CandleRepository")
def test_candles_loaded_once_and_windows_run(repo_cls, strategy_lookup):
    strategy_lookup.return_value = {"interval": "1m", "symbols": ["BTCUSDT"], "parameters": {"fast_window": 12, "slow_window": 26}}
    repo = repo_cls.return_value
    repo.get_candles.return_value = _candles(datetime(2024, 1, 1, tzinfo=timezone.utc), 500_000)

    payload = run_walk_forward_backtest(
        strategy="ema_cross_v1",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        train_days=180,
        validation_days=30,
        test_days=30,
        step_days=30,
        db_url="postgresql://local/test",
    )
    repo.get_candles.assert_called_once()
    assert payload["window_count"] > 0
    assert "load_candles_ms" in payload
    assert "backtest_total_ms" in payload
    assert "total_runtime_ms" in payload


@patch("app.walk_forward._strategy_lookup")
@patch("app.walk_forward.CandleRepository")
def test_aggregate_metrics_computed(repo_cls, strategy_lookup):
    strategy_lookup.return_value = {"interval": "1m", "symbols": ["BTCUSDT"], "parameters": {"fast_window": 12, "slow_window": 26}}
    repo_cls.return_value.get_candles.return_value = _candles(datetime(2024, 1, 1, tzinfo=timezone.utc), 350_000)

    payload = run_walk_forward_backtest(
        strategy="ema_cross_v1",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 8, 30, tzinfo=timezone.utc),
        train_days=120,
        validation_days=30,
        test_days=30,
        step_days=60,
        db_url="postgresql://local/test",
    )
    agg = payload["aggregate"]
    assert isinstance(agg["avg_train_sharpe"], float)
    assert isinstance(agg["avg_validation_sharpe"], float)
    assert isinstance(agg["avg_test_sharpe"], float)


@patch("app.walk_forward._strategy_lookup")
@patch("app.walk_forward.CandleRepository")
def test_insufficient_windows_graceful(repo_cls, strategy_lookup):
    strategy_lookup.return_value = {"interval": "1m", "symbols": ["BTCUSDT"], "parameters": {"fast_window": 12, "slow_window": 26}}
    repo_cls.return_value.get_candles.return_value = _candles(datetime(2024, 1, 1, tzinfo=timezone.utc), 100)

    payload = run_walk_forward_backtest(
        strategy="ema_cross_v1",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 20, tzinfo=timezone.utc),
        train_days=10,
        validation_days=10,
        test_days=10,
        db_url="postgresql://local/test",
    )
    assert payload["window_count"] == 0
    assert payload["windows"] == []
    assert payload["aggregate"]["avg_test_sharpe"] == 0.0
