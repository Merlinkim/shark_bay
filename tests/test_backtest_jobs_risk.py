from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.backtest import Candle
from app.backtest_jobs import execute_job


def test_execute_job_applies_risk_config_from_payload():
    candles = [
        Candle(symbol="BTCUSDT", open_time=datetime.fromtimestamp(1, tz=timezone.utc), close=Decimal("100")),
        Candle(symbol="BTCUSDT", open_time=datetime.fromtimestamp(61, tz=timezone.utc), close=Decimal("101")),
    ]

    job_row = {
        "payload_json": {
            "strategy_id": "sma_crossover",
            "params": {"short_window": 2, "long_window": 3},
            "risk_config": {"position_size_mode": "fixed_fraction", "risk_per_trade": 0.05, "max_holding_minutes": 5},
            "execution_config": {"initial_cash": 5000, "fee_bps": 4, "slippage_bps": 2, "slippage_model": "fixed_bps", "save_results": False},
            "candle_query": {"symbol": "BTCUSDT", "interval": "1m"},
        }
    }

    with patch("app.backtest_jobs.CandleRepository") as candle_repo_cls, \
         patch("app.backtest_jobs.build_strategy") as build_strategy, \
         patch("app.backtest_jobs.BacktestRunRepository") as run_repo_cls, \
         patch("app.backtest_jobs.SimulatedExecutionModel") as engine_cls:
        candle_repo_cls.return_value.get_candles.return_value = candles
        build_strategy.return_value = MagicMock()
        run_repo = run_repo_cls.return_value
        run_repo.create_run.return_value = "run-1"

        result = MagicMock()
        result.config_hash = "cfg"
        result.dataset_fingerprint = "fp"
        result.total_return_pct = 1.0
        result.final_equity = 5100.0
        result.max_drawdown_pct = 2.0
        result.profit_factor = 1.5
        result.average_trade_return_pct = 0.5
        result.trades = 3
        result.win_rate_pct = 66.0
        engine_cls.return_value.run.return_value = result

        execute_job("postgresql://test", job_row)

        _, kwargs = engine_cls.call_args
        assert kwargs["risk_config"].position_size_mode == "fixed_fraction"
        assert kwargs["risk_config"].risk_per_trade == 0.05
        assert kwargs["execution_config"].initial_cash == 5000.0
