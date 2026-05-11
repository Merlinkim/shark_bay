from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.dataset_splits import (
    build_split_payload,
    deterministic_date_split,
    generate_walk_forward_windows,
    resolve_selected_range,
)


def _candles(start: datetime, count: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(symbol="BTCUSDT", open_time=start + timedelta(minutes=i), close=float(100 + i))
        for i in range(count)
    ]


def test_deterministic_split_is_stable():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 11, tzinfo=timezone.utc)
    s1 = deterministic_date_split(start, end)
    s2 = deterministic_date_split(start, end)
    assert s1 == s2


def test_rolling_windows_non_overlapping_segments():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, train_days=180, validation_days=30, test_days=30, step_days=30)
    assert windows
    for w in windows:
        assert w.train.end == w.validation.start
        assert w.validation.end == w.test.start
        assert w.train.start < w.train.end <= w.validation.end <= w.test.end


def test_rolling_generation_correctness_first_window():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2027, 1, 1, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, train_days=180, validation_days=30, test_days=30, step_days=30)
    first = windows[0]
    assert first.train.start == start
    assert first.train.end == start + timedelta(days=180)
    assert first.validation.end == start + timedelta(days=210)
    assert first.test.end == start + timedelta(days=240)


def test_holdout_excluded_by_default():
    candles = _candles(datetime(2026, 1, 1, tzinfo=timezone.utc), 1000)
    payload = build_split_payload(symbol="BTCUSDT", interval="1m", candles=candles)
    assert "holdout_metrics" not in payload
    assert "holdout_range" not in payload


def test_holdout_included_when_requested():
    candles = _candles(datetime(2026, 1, 1, tzinfo=timezone.utc), 1000)
    payload = build_split_payload(symbol="BTCUSDT", interval="1m", candles=candles, include_holdout=True)
    assert "holdout_metrics" in payload
    assert "holdout_range" in payload


def test_explicit_range_uses_requested_window():
    candles = _candles(datetime(2026, 1, 1, tzinfo=timezone.utc), 100)
    start = candles[10].open_time
    end = candles[90].open_time
    selected_start, selected_end = resolve_selected_range(candles, start, end)
    sliced = [c for c in candles if selected_start <= c.open_time <= selected_end]
    payload = build_split_payload(symbol="BTCUSDT", interval="1m", candles=sliced)
    assert payload["selected_range_start"] == start.isoformat()
    assert payload["selected_range_end"] == end.isoformat()


def test_omitted_range_uses_full_dataset():
    candles = _candles(datetime(2026, 1, 1, tzinfo=timezone.utc), 100)
    selected_start, selected_end = resolve_selected_range(candles, None, None)
    assert selected_start == candles[0].open_time
    assert selected_end == candles[-1].open_time


def test_rolling_windows_within_explicit_range():
    candles = _candles(datetime(2026, 1, 1, tzinfo=timezone.utc), 365 * 24 * 2)
    sliced = [c for c in candles if candles[100].open_time <= c.open_time <= candles[-100].open_time]
    payload = build_split_payload(
        symbol="BTCUSDT",
        interval="1m",
        candles=sliced,
        split_mode="rolling",
        train_days=30,
        validation_days=5,
        test_days=5,
    )
    for w in payload["windows"]:
        assert w["train"]["start"] >= payload["selected_range_start"]
        assert w["test"]["end"] <= payload["selected_range_end"]


def test_invalid_range_returns_clear_error():
    candles = _candles(datetime(2026, 1, 1, tzinfo=timezone.utc), 10)
    with pytest.raises(ValueError, match="Invalid range: end must be greater than start"):
        resolve_selected_range(candles, candles[5].open_time, candles[3].open_time)
