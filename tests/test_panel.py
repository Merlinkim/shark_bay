"""Generic panel + as-of universe: alignment, field-agnosticism, survivorship/leakage."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.backtest import Candle
from app.panel import Panel, as_of_universe, build_panel


def _c(t, close, vol=None, funding=None, oi=None):
    return Candle(
        symbol="X", open_time=t, close=Decimal(str(close)),
        open=Decimal(str(close)), high=Decimal(str(close)), low=Decimal(str(close)),
        volume=Decimal(str(vol)) if vol is not None else None,
        funding_rate=Decimal(str(funding)) if funding is not None else None,
        open_interest=Decimal(str(oi)) if oi is not None else None,
    )


def _series(start, n, base, sym):
    return [
        Candle(symbol=sym, open_time=start + timedelta(hours=8 * i), close=Decimal(str(base + i)),
               open=Decimal(str(base + i)), high=Decimal(str(base + i)), low=Decimal(str(base + i)),
               volume=Decimal("100"))
        for i in range(n)
    ]


def test_panel_aligns_union_grid_with_late_listing():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    a = _series(start, 5, 100, "AAA")
    # BBB lists 2 bars later (shorter history)
    b = _series(start + timedelta(hours=16), 3, 200, "BBB")
    panel = build_panel({"AAA": a, "BBB": b}, ["close"])
    assert len(panel.times) == 5  # union of timestamps
    # BBB has no value at i=0/1
    assert panel.value("close", 0, "BBB") is None
    assert panel.value("close", 2, "BBB") == 200.0
    assert panel.value("close", 0, "AAA") == 100.0


def test_field_agnostic_multiple_fields():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    s = [_c(start + timedelta(hours=8 * i), 100 + i, vol=10, funding=0.001, oi=5000) for i in range(4)]
    panel = build_panel({"X": s}, ["close", "volume", "funding_rate", "open_interest"])
    assert panel.value("funding_rate", 1, "X") == 0.001
    assert panel.value("open_interest", 2, "X") == 5000.0
    assert panel.value("volume", 0, "X") == 10.0


def test_unknown_field_rejected():
    with pytest.raises(ValueError):
        build_panel({"X": [_c(datetime(2024, 1, 1, tzinfo=timezone.utc), 100)]}, ["nope"])


def test_cross_section_restricts_to_universe():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    panel = build_panel({
        "AAA": _series(start, 3, 100, "AAA"),
        "BBB": _series(start, 3, 200, "BBB"),
        "CCC": _series(start, 3, 300, "CCC"),
    }, ["close"])
    cs = panel.cross_section("close", 1, universe={"AAA", "CCC"})
    assert set(cs) == {"AAA", "CCC"}


def test_trailing_is_past_only():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    panel = build_panel({"AAA": _series(start, 10, 100, "AAA")}, ["close"])
    tr = panel.trailing("close", 5, "AAA", lookback=3)
    # values at i=3,4,5 → closes 103,104,105
    assert tr == [103.0, 104.0, 105.0]


def test_as_of_universe_survivorship_listing_age():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    a = _series(start, 6, 100, "AAA")
    b = _series(start + timedelta(hours=8 * 3), 3, 200, "BBB")  # lists at i=3
    panel = build_panel({"AAA": a, "BBB": b}, ["close", "volume"])
    uni = as_of_universe(panel, min_history_bars=2)
    # AAA eligible from i=1 (2 bars of history); BBB only after it has 2 bars (i=4)
    assert "AAA" in uni[1]
    assert "BBB" not in uni[3]   # only 1 bar of history at i=3
    assert "BBB" in uni[4]       # 2 bars by i=4


def test_as_of_universe_no_future_leak():
    # A symbol that only appears LATE must never be eligible early.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    a = _series(start, 6, 100, "AAA")
    late = _series(start + timedelta(hours=8 * 5), 1, 999, "LATE")
    panel = build_panel({"AAA": a, "LATE": late}, ["close", "volume"])
    uni = as_of_universe(panel, min_history_bars=1)
    for i in range(5):
        assert "LATE" not in uni[i], f"future symbol leaked into as-of universe at i={i}"


def test_as_of_universe_liquidity_filter():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # AAA: price ~100, volume 1000 → dollar vol ~100k; BBB: price 1, volume 1 → ~1
    a = [Candle(symbol="AAA", open_time=start + timedelta(hours=8 * i), close=Decimal("100"),
                open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), volume=Decimal("1000")) for i in range(5)]
    b = [Candle(symbol="BBB", open_time=start + timedelta(hours=8 * i), close=Decimal("1"),
                open=Decimal("1"), high=Decimal("1"), low=Decimal("1"), volume=Decimal("1")) for i in range(5)]
    panel = build_panel({"AAA": a, "BBB": b}, ["close", "volume"])
    uni = as_of_universe(panel, min_history_bars=1, min_avg_dollar_volume=1000.0, volume_lookback=3)
    assert "AAA" in uni[4]
    assert "BBB" not in uni[4]   # illiquid, filtered
