"""Unit tests for the production audit tool's pure logic (no DB/network)."""
from datetime import datetime, timedelta, timezone

from tools.audit_production_data import (
    candle_mismatch,
    compute_missing_ranges,
    funding_alignment_issues,
    is_monotonic,
    ohlc_invalid,
    severity_count,
    severity_missing,
    severity_mismatch_rate,
    volume_inconsistent,
    worst,
)


def test_ohlc_invalid():
    assert ohlc_invalid(10, 12, 9, 11) is False         # valid
    assert ohlc_invalid(10, 9, 9, 11) is True           # high < close
    assert ohlc_invalid(10, 12, 11, 9) is True          # low > close
    assert ohlc_invalid(10, 8, 9, 10) is True           # high < low


def test_volume_inconsistent():
    assert volume_inconsistent(100, 40) is False
    assert volume_inconsistent(None, None) is True
    assert volume_inconsistent(-1, 0) is True
    assert volume_inconsistent(100, 150) is True        # taker buy > volume


def test_compute_missing_ranges():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    times = [t0, t0 + timedelta(minutes=1), t0 + timedelta(minutes=5)]  # 3 missing between
    ranges = compute_missing_ranges(times)
    assert len(ranges) == 1
    assert ranges[0]["missing_count"] == 3


def test_compute_missing_ranges_none_when_contiguous():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    times = [t0 + timedelta(minutes=i) for i in range(10)]
    assert compute_missing_ranges(times) == []


def test_is_monotonic():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert is_monotonic([t0, t0 + timedelta(minutes=1)]) is True
    assert is_monotonic([t0 + timedelta(minutes=1), t0]) is False
    assert is_monotonic([t0, t0]) is False  # duplicate breaks strict monotonicity


def test_funding_alignment_issues_clean():
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    settlements = [t0 + timedelta(hours=8 * i) for i in range(10)]
    res = funding_alignment_issues(settlements)
    assert res["misaligned_count"] == 0
    assert res["gap_count"] == 0


def test_funding_alignment_detects_misalignment_and_gap():
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    settlements = [t0, t0 + timedelta(hours=8),
                   t0 + timedelta(hours=15),          # misaligned (not on 8h grid)
                   t0 + timedelta(hours=40)]          # big gap
    res = funding_alignment_issues(settlements)
    assert res["misaligned_count"] >= 1
    assert res["gap_count"] >= 1


def test_candle_mismatch_detects_field_diffs():
    db = {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
    same = dict(db)
    assert candle_mismatch(db, same) == []
    off = dict(db, close=106)            # 106 vs 105 → ~0.95% diff > tol
    assert "close" in candle_mismatch(db, off)


def test_candle_mismatch_tolerates_float_noise():
    db = {"open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1000.0}
    src = {"open": 100.000001, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1000.0}
    assert candle_mismatch(db, src, rel_tol=1e-4) == []


def test_severity_helpers():
    assert severity_missing(0, 1000) == "NONE"
    assert severity_missing(1, 1000) == "LOW"
    assert severity_missing(5, 1000) == "MEDIUM"
    assert severity_missing(50, 1000) == "HIGH"
    assert severity_count(0) == "NONE"
    assert severity_count(1) == "HIGH"
    assert severity_mismatch_rate(0.0) == "NONE"
    assert severity_mismatch_rate(0.001) == "HIGH"
    assert severity_mismatch_rate(0.01) == "CRITICAL"


def test_worst():
    assert worst("NONE", "LOW", "CRITICAL", "HIGH") == "CRITICAL"
    assert worst("NONE", "NONE") == "NONE"
