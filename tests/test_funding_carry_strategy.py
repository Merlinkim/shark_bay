"""Phase 4 — funding_carry signal correctness and leakage (prefix-invariance)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.backtest import Candle, build_strategy
from app.strategy_loader import strategy_loader

import importlib.util
from pathlib import Path

# Load the strategy module directly for unit-testing its signal function.
_spec = importlib.util.spec_from_file_location(
    "funding_carry_mod", Path("strategies/builtin/funding_carry.py")
)
fc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fc)

DEFAULTS = {"entry_threshold": 0.0001, "smoothing_window": 1, "oi_crowding_mult": 0.0, "oi_window": 14}


def _row(funding=None, oi=None):
    r = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0}
    if funding is not None:
        r["funding_rate"] = funding
    if oi is not None:
        r["open_interest"] = oi
    return r


def test_strong_positive_funding_signals_short():
    df = [_row(funding=0.001)]
    sig = fc.generate_signals(df, DEFAULTS)
    assert sig[0]["signal"] == -1  # collect funding by shorting crowded longs


def test_strong_negative_funding_signals_long():
    df = [_row(funding=-0.001)]
    sig = fc.generate_signals(df, DEFAULTS)
    assert sig[0]["signal"] == 1


def test_funding_within_band_is_flat():
    df = [_row(funding=0.00005)]  # below 0.0001 threshold
    sig = fc.generate_signals(df, DEFAULTS)
    assert sig[0]["signal"] == 0


def test_missing_funding_is_flat():
    df = [_row(funding=None)]
    sig = fc.generate_signals(df, DEFAULTS)
    assert sig[0]["signal"] == 0


def test_oi_crowding_filter_blocks_when_oi_low():
    params = {**DEFAULTS, "oi_crowding_mult": 1.5, "oi_window": 3}
    # Funding says short, but OI is below 1.5x its trailing mean → filtered to flat
    df = [_row(funding=0.001, oi=100), _row(funding=0.001, oi=100), _row(funding=0.001, oi=100)]
    sig = fc.generate_signals(df, params)
    assert sig[-1]["signal"] == 0


def test_smoothing_averages_funding():
    params = {**DEFAULTS, "smoothing_window": 2}
    # Row 1 averages funding [+0.0003, -0.0001] = +0.0001, exactly at threshold → flat
    df = [_row(funding=0.0003), _row(funding=-0.0001)]
    sig = fc.generate_signals(df, params)
    assert sig[1]["signal"] == 0


def test_signal_is_prefix_invariant_no_lookahead():
    """The engine's leakage guard must not fire: signal at row k is identical
    whether computed on the full series or only the prefix through k."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(40):
        fr = 0.001 if (i // 5) % 2 == 0 else -0.001
        candles.append(
            Candle(
                symbol="BTCUSDT", open_time=start + timedelta(hours=8 * i), close=Decimal("100"),
                open=Decimal("100"), high=Decimal("100"), low=Decimal("100"),
                volume=Decimal("1"), funding_rate=Decimal(str(fr)),
            )
        )
    # build_strategy wraps the module in DynamicSignalStrategy; set_candles runs
    # the prefix-invariance assertion and raises LookaheadError if it fails.
    strat = build_strategy("funding_carry", dict(DEFAULTS))
    strat.set_candles(candles)  # must not raise


def test_registered_in_loader():
    defs = strategy_loader.discover()
    assert "funding_carry" in defs
    assert defs["funding_carry"].meta["research_only"] is True
