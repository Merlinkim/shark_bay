from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.backtest import Candle
from app.walk_forward import run_walk_forward_backtest

PARAMS = {"short_window": 5, "long_window": 20}


def _candles(start: datetime, count: int) -> list[Candle]:
    return [
        Candle(symbol="BTCUSDT", open_time=start + timedelta(minutes=i), close=Decimal(100 + i * 0.01))
        for i in range(count)
    ]


@patch("app.walk_forward.CandleRepository")
def test_candles_loaded_once_and_windows_run(repo_cls):
    repo = repo_cls.return_value
    repo.get_candles.return_value = _candles(datetime(2024, 1, 1, tzinfo=timezone.utc), 8 * 1440)

    payload = run_walk_forward_backtest(
        strategy="sma_crossover",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 9, tzinfo=timezone.utc),
        train_days=3,
        validation_days=1,
        test_days=1,
        step_days=1,
        params=PARAMS,
        db_url="postgresql://local/test",
    )
    repo.get_candles.assert_called_once()
    assert payload["window_count"] > 0
    assert payload["engine_version"] == "v2"
    assert "load_candles_ms" in payload
    assert "backtest_total_ms" in payload
    assert "total_runtime_ms" in payload


@patch("app.walk_forward.CandleRepository")
def test_aggregate_metrics_computed(repo_cls):
    repo_cls.return_value.get_candles.return_value = _candles(datetime(2024, 1, 1, tzinfo=timezone.utc), 7 * 1440)

    payload = run_walk_forward_backtest(
        strategy="sma_crossover",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        train_days=3,
        validation_days=1,
        test_days=1,
        step_days=2,
        params=PARAMS,
        db_url="postgresql://local/test",
    )
    agg = payload["aggregate"]
    assert isinstance(agg["avg_train_sharpe"], float)
    assert isinstance(agg["avg_validation_sharpe"], float)
    assert isinstance(agg["avg_test_sharpe"], float)
    assert agg["pass_fail_status"] in {"pass", "fail"}
    assert 0.0 <= agg["positive_test_window_fraction"] <= 1.0


@patch("app.walk_forward.CandleRepository")
def test_insufficient_windows_graceful(repo_cls):
    repo_cls.return_value.get_candles.return_value = _candles(datetime(2024, 1, 1, tzinfo=timezone.utc), 100)

    payload = run_walk_forward_backtest(
        strategy="sma_crossover",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 20, tzinfo=timezone.utc),
        train_days=10,
        validation_days=10,
        test_days=10,
        params=PARAMS,
        db_url="postgresql://local/test",
    )
    assert payload["window_count"] == 0
    assert payload["windows"] == []
    assert payload["aggregate"]["avg_test_sharpe"] == 0.0
    assert payload["aggregate"]["pass_fail_status"] == "fail"
