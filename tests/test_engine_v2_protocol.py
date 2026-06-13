"""Engine v2 protocol tests: T3 fill timing, T4 leakage guard, T5 walk-forward
unification, T6 holdout protection, T7 archive migration.

All tests are deterministic and DB-free.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.backtest import (
    Candle,
    DynamicSignalStrategy,
    ExecutionConfig,
    LookaheadError,
    RiskConfig,
    SimulatedExecutionModel,
    build_dataset_fingerprint,
)
from app.holdout import (
    HoldoutViolationError,
    assert_range_outside_holdout,
    clamp_research_end,
    holdout_start,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _ohlc_candles(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    return [
        Candle(
            symbol="TESTUSDT",
            open_time=_BASE + timedelta(minutes=i),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(l)),
            close=Decimal(str(c)),
        )
        for i, (o, h, l, c) in enumerate(rows)
    ]


class _ScriptedStrategy:
    strategy_name = "scripted"

    def __init__(self, script: list[int]):
        self._script = script
        self._i = 0

    def on_candle(self, candle: Candle) -> int:
        target = self._script[self._i] if self._i < len(self._script) else 0
        self._i += 1
        return target


def _engine(fee_bps: float = 0.0, slippage_model: str = "none", **risk_overrides) -> SimulatedExecutionModel:
    risk = {
        "risk_per_trade": 1.0, "max_position_size": 1.0,
        "stop_loss_pct": 0.99, "take_profit_pct": 99.0,
        "max_holding_minutes": 10_000, "max_daily_loss_pct": 100.0, "max_drawdown_pct": 100.0,
    }
    risk.update(risk_overrides)
    return SimulatedExecutionModel(
        execution_config=ExecutionConfig(fee_bps=fee_bps, slippage_bps=1.0, slippage_model=slippage_model, initial_cash=10_000.0),
        risk_config=RiskConfig(**risk),
    )


def _run(rows, script, **kwargs):
    candles = _ohlc_candles(rows)
    return _engine(**kwargs).run(candles, _ScriptedStrategy(script), config_hash="t", dataset_fingerprint=build_dataset_fingerprint(candles))


# ---------------------------------------------------------------------------
# T3 — Fill timing / look-ahead elimination
# ---------------------------------------------------------------------------

def test_signal_on_jump_bar_cannot_capture_the_jump():
    """A signal that reacts to the jump at bar k fills at bar k+1 open and must
    NOT capture the jump return. Engine v0 credited the full +10% to the trade."""
    rows = [(100, 100, 100, 100)] * 3
    rows.append((100, 110, 100, 110))   # bar 3: the +10% jump
    rows += [(110, 110, 110, 110)] * 4  # flat afterwards
    # on_candle(candle[i-1]) at iteration i. The jump bar (index 3) is first
    # visible at iteration 4 -> script index 3 turns long.
    script = [0, 0, 0, 1, 1, 1, 0]
    result = _run(rows, script)
    assert result.trades == 1
    # Entered at bar 4 open (110), price never moves again: P&L ~ 0, not +10%.
    assert abs(result.total_return_pct) < 1e-9, f"jump leaked into trade: {result.total_return_pct}%"


def test_fill_price_is_next_bar_open():
    rows = [
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (104, 106, 104, 106),  # bar 2: opens at 104, closes 106
        (106, 106, 106, 106),
        (106, 106, 106, 106),
    ]
    script = [1, 1, 1, 1]  # long from first opportunity
    result = _run(rows, script)
    assert result.fills, "expected at least one fill"
    first = result.fills[0]
    # First fill happens at iteration 1 -> bar 1 open = 100 (slippage model 'none').
    assert abs(first.exec_price - 100.0) < 1e-9
    # Position entered at bar 1 open earns 100 -> 106 by bar 2 close.
    assert result.total_return_pct == pytest.approx(6.0, abs=1e-6)


def test_entry_bar_return_before_fill_is_not_credited():
    """Engine v0 gave the position the full prev_close->curr_close move of the
    fill bar. v2 must credit only from the open it actually filled at."""
    rows = [
        (100, 100, 100, 100),
        (105, 105, 105, 105),  # bar 1: opens already +5% gapped; close 105
        (105, 105, 105, 105),
    ]
    script = [1, 1]
    result = _run(rows, script)
    # Fill at bar 1 open (105). Bar 1 close 105 -> zero gain. v0 credited +5%.
    assert abs(result.total_return_pct) < 1e-9


def test_intrabar_stop_triggers_on_low_not_close():
    """Bar dips through the stop intrabar but closes back above: v2 must stop out."""
    rows = [
        (100, 100, 100, 100),
        (100, 100, 100, 100),   # entry at bar 1 open = 100
        (100, 101, 94, 100),    # bar 2: low 94 pierces 5% stop at 95, closes 100
        (100, 100, 100, 100),
    ]
    script = [1, 1, 1]
    result = _run(rows, script, stop_loss_pct=0.05)
    assert result.trades >= 1
    stop_fills = [f for f in result.fills if f.prev_position == 1 and f.new_position == 0]
    assert stop_fills, "expected a stop-out fill"
    assert stop_fills[0].exec_price == pytest.approx(95.0, abs=1e-9)
    # Loss realized ~ -5% even though the bar closed flat.
    assert result.total_return_pct == pytest.approx(-5.0, abs=0.2)


def test_gap_through_stop_fills_at_open():
    rows = [
        (100, 100, 100, 100),
        (100, 100, 100, 100),   # entry at 100
        (90, 90, 88, 89),       # gaps to 90, far below the 95 stop
        (89, 89, 89, 89),
    ]
    script = [1, 1, 1]
    result = _run(rows, script, stop_loss_pct=0.05)
    stop_fills = [f for f in result.fills if f.new_position == 0]
    assert stop_fills
    # First available price is the open (90), not the stop level (95).
    assert stop_fills[0].exec_price == pytest.approx(90.0, abs=1e-9)


# ---------------------------------------------------------------------------
# T4 — Dynamic strategy leakage guard
# ---------------------------------------------------------------------------

def _leaky_module():
    def prepare_features(df, params):
        return df

    def generate_signals(df, params):
        # Signal at row i = sign of NEXT bar's return: blatant look-ahead.
        out = []
        for i in range(len(df)):
            if i + 1 < len(df):
                out.append({"signal": 1 if df[i + 1]["close"] > df[i]["close"] else 0})
            else:
                out.append({"signal": 0})
        return out

    return SimpleNamespace(prepare_features=prepare_features, generate_signals=generate_signals)


def _clean_module():
    def prepare_features(df, params):
        return df

    def generate_signals(df, params):
        out = []
        for i in range(len(df)):
            if i < 5:
                out.append({"signal": 0})
                continue
            sma = sum(row["close"] for row in df[i - 4 : i + 1]) / 5.0
            out.append({"signal": 1 if df[i]["close"] > sma else 0})
        return out

    return SimpleNamespace(prepare_features=prepare_features, generate_signals=generate_signals)


def _wiggly_candles(n: int = 200) -> list[Candle]:
    closes = [100.0 + ((i * 7) % 13) - 6 for i in range(n)]
    return _ohlc_candles([(c, c, c, c) for c in closes])


def test_leaky_dynamic_strategy_is_rejected(monkeypatch):
    monkeypatch.setenv("SHARKBAY_LEAKAGE_CHECK", "1")
    strategy = DynamicSignalStrategy("leaky_test", _leaky_module(), {})
    with pytest.raises(LookaheadError):
        strategy.set_candles(_wiggly_candles())


def test_clean_dynamic_strategy_passes(monkeypatch):
    monkeypatch.setenv("SHARKBAY_LEAKAGE_CHECK", "1")
    strategy = DynamicSignalStrategy("clean_test", _clean_module(), {})
    strategy.set_candles(_wiggly_candles())  # must not raise
    assert len(strategy._signals) == 200


def test_leakage_check_can_be_disabled(monkeypatch):
    monkeypatch.setenv("SHARKBAY_LEAKAGE_CHECK", "0")
    strategy = DynamicSignalStrategy("leaky_test", _leaky_module(), {})
    strategy.set_candles(_wiggly_candles())  # guard off: no raise


# ---------------------------------------------------------------------------
# T5 — Walk-forward unification
# ---------------------------------------------------------------------------

def test_walk_forward_windows_never_overlap_train_and_test():
    from app.dataset_splits import generate_walk_forward_windows

    windows = generate_walk_forward_windows(
        _BASE, _BASE + timedelta(days=60), train_days=14, validation_days=3, test_days=3, step_days=3
    )
    assert windows
    for w in windows:
        assert w.train.end <= w.validation.start
        assert w.validation.end <= w.test.start


def test_segment_metrics_match_direct_engine_run():
    """The unified walk-forward segment must produce numbers identical to
    running the engine directly on the same slice (same simulator)."""
    from app.walk_forward import RESEARCH_RISK_DEFAULTS, _segment_metrics
    from app.backtest import build_execution_config, build_risk_config, build_strategy

    closes = [100.0 + ((i * 11) % 29) for i in range(2_000)]
    candles = _ohlc_candles([(c, c, c, c) for c in closes])
    left, right = 100, 1_500

    seg = _segment_metrics("sma_crossover", {"short_window": 5, "long_window": 20}, candles, left, right)

    strategy = build_strategy("sma_crossover", {"short_window": 5, "long_window": 20})
    engine = SimulatedExecutionModel(
        execution_config=build_execution_config(None),
        risk_config=build_risk_config(dict(RESEARCH_RISK_DEFAULTS)),
    )
    direct = engine.run(candles[left:right], strategy, config_hash="x", dataset_fingerprint=build_dataset_fingerprint(candles[left:right]))

    assert seg["status"] == "real_backtest"
    assert seg["total_return_pct"] == pytest.approx(direct.total_return_pct)
    assert seg["sharpe"] == pytest.approx(direct.sharpe)
    assert seg["trade_count"] == direct.trades
    assert seg["win_rate_pct"] == pytest.approx(direct.win_rate_pct)


# ---------------------------------------------------------------------------
# T6 — Holdout protection
# ---------------------------------------------------------------------------

_BOUNDARY = "2024-06-01T00:00:00+00:00"


def test_holdout_clamp(monkeypatch):
    monkeypatch.setenv("RESEARCH_HOLDOUT_START", _BOUNDARY)
    boundary = holdout_start()
    assert boundary == datetime(2024, 6, 1, tzinfo=timezone.utc)
    # End beyond the boundary clamps to it; end before it passes through.
    assert clamp_research_end(datetime(2024, 8, 1, tzinfo=timezone.utc)) == boundary
    assert clamp_research_end(None) == boundary
    inside = datetime(2024, 3, 1, tzinfo=timezone.utc)
    assert clamp_research_end(inside) == inside


def test_holdout_rejection_for_jobs(monkeypatch):
    monkeypatch.setenv("RESEARCH_HOLDOUT_START", _BOUNDARY)
    with pytest.raises(HoldoutViolationError):
        assert_range_outside_holdout(
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 7, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(HoldoutViolationError):
        assert_range_outside_holdout(datetime(2024, 1, 1, tzinfo=timezone.utc), None)
    # Fully before the boundary: allowed.
    assert_range_outside_holdout(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 5, 1, tzinfo=timezone.utc),
    )


def test_no_boundary_configured_means_no_restriction(monkeypatch):
    monkeypatch.delenv("RESEARCH_HOLDOUT_START", raising=False)
    assert holdout_start() is None
    end = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert clamp_research_end(end) == end
    assert_range_outside_holdout(None, None)  # no raise


def test_walk_forward_holdout_requires_unlock(monkeypatch):
    monkeypatch.setenv("RESEARCH_HOLDOUT_START", _BOUNDARY)
    monkeypatch.delenv("RESEARCH_HOLDOUT_UNLOCK", raising=False)
    from app.walk_forward import run_walk_forward_backtest

    with pytest.raises(PermissionError):
        run_walk_forward_backtest(
            strategy="sma_crossover",
            symbol="BTCUSDT",
            interval="1m",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 8, 1, tzinfo=timezone.utc),
            train_days=14,
            validation_days=3,
            test_days=3,
            include_holdout=True,
            db_url="postgresql://local/test",
        )


def test_execute_job_rejects_holdout_range(monkeypatch):
    monkeypatch.setenv("RESEARCH_HOLDOUT_START", _BOUNDARY)
    from app.backtest_jobs import execute_job

    job_row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "payload_json": {
            "strategy_id": "sma_crossover",
            "candle_query": {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "start_time": "2024-01-01T00:00:00+00:00",
                "end_time": "2024-07-01T00:00:00+00:00",
            },
            "params": {"short_window": 5, "long_window": 20},
        },
    }
    with pytest.raises(HoldoutViolationError):
        execute_job("postgresql://local/test", job_row)


# ---------------------------------------------------------------------------
# T7 — Archive migration tooling
# ---------------------------------------------------------------------------

def test_migration_archives_and_recreates(tmp_path):
    scripts_dir = Path(__file__).resolve().parents[2] / "SharkBay" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import migrate_engine_v2
    finally:
        sys.path.pop(0)

    root = tmp_path / "research_root"
    (root / "campaigns" / "OLD-CAMPAIGN-1").mkdir(parents=True)
    (root / "campaigns" / "OLD-CAMPAIGN-1" / "99_campaign_summary.md").write_text("old", encoding="utf-8")
    (root / "strategy_memory" / "datasets").mkdir(parents=True)
    (root / "strategy_memory" / "datasets" / "sma.jsonl").write_text('{"score": -1}\n', encoding="utf-8")

    report = migrate_engine_v2.migrate(root, dry_run=False)
    assert all(m["status"] == "archived" for m in report["moves"])

    # Fresh empty dirs exist.
    assert (root / "campaigns").is_dir() and not any((root / "campaigns").iterdir())
    assert (root / "strategy_memory" / "datasets").is_dir()
    # Archives preserved with manifest + checksums.
    legacy = root / "campaigns_legacy_enginev0"
    manifest = json.loads((legacy / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "v0"
    assert manifest["file_count"] == 1
    assert (legacy / "OLD-CAMPAIGN-1" / "99_campaign_summary.md").read_text(encoding="utf-8") == "old"
    # Re-running is a safe no-op (dest exists).
    report2 = migrate_engine_v2.migrate(root, dry_run=False)
    assert all(m["status"] == "skipped_dest_exists" for m in report2["moves"])
