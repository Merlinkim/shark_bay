from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.dataset_splits import build_split_payload, deterministic_date_split, generate_walk_forward_windows


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
