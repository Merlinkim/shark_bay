from pathlib import Path

import pytest

from app.backtest import build_strategy, get_strategy_registry_metadata
from app.strategy_loader import StrategyLoader


def test_strategy_discovery():
    meta = get_strategy_registry_metadata()
    assert "sma_crossover" in meta
    assert "bb_rsi_reversion" in meta


def test_registry_consistency():
    ids = set(get_strategy_registry_metadata().keys())
    assert ids == set(StrategyLoader().list_metadata().keys())


def test_backtest_build_from_discovered_strategy():
    strategy = build_strategy("sma_crossover", {"short_window": 2, "long_window": 3})
    assert strategy.strategy_name == "sma_crossover"


def test_missing_function_rejection(tmp_path: Path):
    root = tmp_path / "s"
    root.mkdir()
    (root / "broken.py").write_text('STRATEGY_META={"strategy_id":"x","strategy_type":"signal_strategy","research_only":True}\n')
    with pytest.raises(ValueError, match="Missing required function"):
        StrategyLoader([root]).discover()


def test_duplicate_strategy_id_rejection(tmp_path: Path):
    b = tmp_path / "b"; g = tmp_path / "g"; b.mkdir(); g.mkdir()
    payload = 'STRATEGY_META={"strategy_id":"dup","strategy_type":"signal_strategy","research_only":True}\n\ndef required_features(params): return []\ndef prepare_features(df,params): return df\ndef generate_signals(df,params): return [{"signal":0}]\n'
    (b / "a.py").write_text(payload)
    (g / "b.py").write_text(payload)
    with pytest.raises(ValueError, match="Duplicate strategy_id"):
        StrategyLoader([b, g]).discover()


def test_sandbox_violation_rejection(tmp_path: Path):
    root = tmp_path / "s"; root.mkdir()
    (root / "bad.py").write_text('import requests\nSTRATEGY_META={"strategy_id":"x","strategy_type":"signal_strategy","research_only":True}\n\ndef required_features(params): return []\ndef prepare_features(df,params): return df\ndef generate_signals(df,params): return [{"signal":0}]\n')
    with pytest.raises(ValueError, match="sandbox violation"):
        StrategyLoader([root]).discover()
