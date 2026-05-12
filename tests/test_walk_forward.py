from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.walk_forward import run_walk_forward_backtest


@patch("app.walk_forward.run_real_backtest_experiment")
def test_real_backtest_called_for_each_window(mock_run):
    mock_run.return_value = SimpleNamespace(
        status="real_backtest",
        total_return_pct=1.0,
        sharpe=0.5,
        max_drawdown_pct=-1.0,
        win_rate_pct=55.0,
        trade_count=3,
        dataset_row_count=100,
    )
    payload = run_walk_forward_backtest(
        strategy="ema_cross_v1",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 10, 1, tzinfo=timezone.utc),
        train_days=120,
        validation_days=30,
        test_days=30,
        step_days=30,
        db_url="postgresql://local/test",
    )
    assert payload["window_count"] > 0
    assert mock_run.call_count == payload["window_count"] * 3


@patch("app.walk_forward.run_real_backtest_experiment")
def test_aggregate_metrics_computed(mock_run):
    mock_run.side_effect = [
        SimpleNamespace(status="ok", total_return_pct=10.0, sharpe=2.0, max_drawdown_pct=-2.0, win_rate_pct=70.0, trade_count=4, dataset_row_count=100),
        SimpleNamespace(status="ok", total_return_pct=5.0, sharpe=1.0, max_drawdown_pct=-3.0, win_rate_pct=60.0, trade_count=3, dataset_row_count=100),
        SimpleNamespace(status="ok", total_return_pct=3.0, sharpe=0.5, max_drawdown_pct=-4.0, win_rate_pct=55.0, trade_count=3, dataset_row_count=100),
    ]
    payload = run_walk_forward_backtest(
        strategy="ema_cross_v1",
        symbol="BTCUSDT",
        interval="1m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 7, 29, tzinfo=timezone.utc),
        train_days=120,
        validation_days=30,
        test_days=30,
        step_days=120,
        db_url="postgresql://local/test",
    )
    agg = payload["aggregate"]
    assert agg["avg_train_sharpe"] == 2.0
    assert agg["avg_validation_sharpe"] == 1.0
    assert agg["avg_test_sharpe"] == 0.5
    assert agg["avg_test_return_pct"] == 3.0
    assert agg["worst_test_drawdown_pct"] == -4.0


@patch("app.walk_forward.run_real_backtest_experiment")
def test_insufficient_windows_graceful(mock_run):
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
    mock_run.assert_not_called()
