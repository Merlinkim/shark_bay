"""Engine v2 metric-correction tests (Tasks 1-3): Sharpe annualization and
per-trade win rate / round-trip trade counting.

All tests are deterministic and DB-free.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.backtest import (
    BacktestResult,
    Candle,
    ExecutionConfig,
    RiskConfig,
    SimulatedExecutionModel,
    build_dataset_fingerprint,
)
from app.stats import BARS_PER_YEAR, annualized_sharpe


# ---------------------------------------------------------------------------
# T1 — Sharpe
# ---------------------------------------------------------------------------

def test_sharpe_matches_analytic_value_for_iid_normal_returns():
    """i.i.d. normal per-minute returns: annualized Sharpe = (mu/sigma)*sqrt(525600)."""
    rng = random.Random(42)
    mu, sigma = 1e-5, 1e-4
    returns = [rng.gauss(mu, sigma) for _ in range(525_600)]
    expected = (mu / sigma) * math.sqrt(525_600.0)  # ~72.5
    got = annualized_sharpe(returns, interval="1m")
    assert abs(got - expected) / expected < 0.05, f"got {got}, expected ~{expected}"


def test_sharpe_zero_mean_series_is_near_zero():
    returns = [0.001, -0.001] * 10_000
    assert abs(annualized_sharpe(returns, interval="1m")) < 1e-9


def test_sharpe_constant_series_is_zero():
    assert annualized_sharpe([0.0] * 100, interval="1m") == 0.0
    assert annualized_sharpe([], interval="1m") == 0.0
    assert annualized_sharpe([0.01], interval="1m") == 0.0


def test_old_sqrt60_factor_would_fail():
    """Guard against regression to the old sqrt(60) annualization."""
    rng = random.Random(7)
    mu, sigma = 1e-5, 1e-4
    returns = [rng.gauss(mu, sigma) for _ in range(100_000)]
    correct = annualized_sharpe(returns, interval="1m")
    n = len(returns)
    avg = sum(returns) / n
    sd = math.sqrt(sum((r - avg) ** 2 for r in returns) / n)
    old_value = (avg / sd) * math.sqrt(60.0)
    # The old factor is ~94x too small; the corrected value must not be close to it.
    assert abs(correct) > abs(old_value) * 50


def test_annualization_table():
    assert BARS_PER_YEAR["1m"] == 525_600.0
    assert BARS_PER_YEAR["1d"] == 365.0


# ---------------------------------------------------------------------------
# T2 — Win rate / trade count (main engine)
# ---------------------------------------------------------------------------

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candles(closes: list[float]) -> list[Candle]:
    return [
        Candle(symbol="TESTUSDT", open_time=_BASE + timedelta(minutes=i), close=Decimal(str(c)))
        for i, c in enumerate(closes)
    ]


class _ScriptedStrategy:
    """Replays a fixed target-position script, one value per on_candle call."""

    strategy_name = "scripted"

    def __init__(self, script: list[int]):
        self._script = script
        self._i = 0

    def on_candle(self, candle: Candle) -> int:
        target = self._script[self._i] if self._i < len(self._script) else 0
        self._i += 1
        return target


def _run(closes: list[float], script: list[int], fee_bps: float = 0.0) -> BacktestResult:
    candles = _candles(closes)
    engine = SimulatedExecutionModel(
        execution_config=ExecutionConfig(fee_bps=fee_bps, slippage_bps=0.0, slippage_model="none", initial_cash=10_000.0),
        # Wide limits so risk exits never interfere with the scripted trades.
        risk_config=RiskConfig(
            risk_per_trade=1.0, max_position_size=1.0,
            stop_loss_pct=0.99, take_profit_pct=99.0,
            max_holding_minutes=10_000, max_daily_loss_pct=100.0, max_drawdown_pct=100.0,
        ),
    )
    return engine.run(candles, _ScriptedStrategy(script), config_hash="t", dataset_fingerprint=build_dataset_fingerprint(candles))


def test_four_round_trips_three_winners():
    """4 long round trips on a price path engineered for 3 winners, 1 loser.

    Script index i is consumed at loop iteration i+1 (engine calls on_candle(candle[i-1])
    at iteration i). Position held over bars [entry+1, exit] earns those bar returns.
    """
    closes = [
        100, 100,          # bars 0-1 flat
        110, 110,          # trade 1: long over the +10% move -> win
        100, 100,          # flat (price resets while flat)
        108, 108,          # trade 2: win
        100, 100,
        95, 95,            # trade 3: long over a -5% move -> loss
        100, 100,
        104, 104,          # trade 4: win
        100,
    ]
    #         bar consumed:  1    2    3    4    5    6    7    8    9   10   11   12   13   14
    script = [1, 1, 0, 0,    # enter before the move, exit after
              1, 1, 0, 0,
              1, 1, 0, 0,
              1, 1, 0, 0]
    result = _run(closes, script)
    assert result.trades == 4, f"expected 4 round trips, got {result.trades}"
    assert abs(result.win_rate_pct - 75.0) < 1e-9, f"expected 75.0, got {result.win_rate_pct}"


def test_single_winning_trade_among_many_candles_is_100pct():
    """Adversarial case for the old formula: 1 winning trade, ~1000 candles.

    Old code reported wins/(candles-1) ~= 0.1%. Corrected code must report 100%.
    """
    closes = [100.0] * 500 + [100.0, 120.0, 120.0] + [120.0] * 500
    script = [0] * 499 + [1, 1, 0] + [0] * 501
    result = _run(closes, script)
    assert result.trades == 1
    assert result.win_rate_pct == 100.0


def test_losing_trade_is_0pct():
    closes = [100.0, 100.0, 90.0, 90.0, 90.0]
    script = [1, 1, 0, 0]
    result = _run(closes, script)
    assert result.trades == 1
    assert result.win_rate_pct == 0.0


def test_fees_can_turn_marginal_winner_into_loser():
    """A +1bp gross trade with 50bp fees per side must be counted as a loss."""
    closes = [100.0, 100.0, 100.01, 100.01, 100.01]
    script = [1, 1, 0, 0]
    result = _run(closes, script, fee_bps=50.0)
    assert result.trades == 1
    assert result.win_rate_pct == 0.0


def test_open_trade_at_end_is_not_counted():
    closes = [100.0, 100.0, 110.0, 120.0]
    script = [1, 1, 1]  # never exits
    result = _run(closes, script)
    assert result.trades == 0
    assert result.win_rate_pct == 0.0


def test_flip_counts_one_closed_round_trip():
    """Long -> short flip closes the long as one round trip; short stays open."""
    closes = [100.0, 100.0, 110.0, 110.0, 110.0]
    script = [1, 1, -1, -1]
    result = _run(closes, script)
    assert result.trades == 1  # the closed long; the short is still open at end
    assert result.win_rate_pct == 100.0


def test_engine_sharpe_sign_matches_performance():
    """Always-long on a steadily rising series -> strongly positive Sharpe."""
    closes = [100.0 * (1.0 + 0.0001) ** i for i in range(500)]
    script = [1] * 499
    result = _run(closes, script)
    assert result.sharpe > 0
    # Flat strategy -> zero Sharpe.
    flat = _run(closes, [0] * 499)
    assert flat.sharpe == 0.0
