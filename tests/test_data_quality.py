from datetime import datetime, timezone
from decimal import Decimal

from app.data_quality import CandleRow, compute_quality_report


def _candle(ts: str, open_: str, high: str, low: str, close: str, volume: str | None):
    return CandleRow(
        open_time=datetime.fromisoformat(ts.replace("Z", "+00:00")),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=None if volume is None else Decimal(volume),
    )


def test_compute_quality_report_counts_issues():
    candles = [
        _candle("2026-05-05T00:00:00Z", "100", "110", "90", "105", "1"),
        _candle("2026-05-05T00:01:00Z", "105", "104", "90", "100", "2"),  # invalid OHLC
        _candle("2026-05-05T00:04:00Z", "100", "110", "95", "105", "0"),  # gap + invalid volume
        _candle("2026-05-05T00:04:00Z", "100", "110", "95", "105", None),  # duplicate + invalid volume
        _candle("2026-05-05T01:30:00Z", "100", "110", "95", "105", "1"),  # future + large gap
    ]

    report = compute_quality_report(
        candles,
        symbol="BTCUSDT",
        interval="1m",
        lookback_hours=24,
        now=datetime(2026, 5, 5, 1, 0, tzinfo=timezone.utc),
    )

    assert report.total_rows_checked == 5
    assert report.gap_count == 87
    assert report.duplicate_count == 1
    assert report.invalid_ohlc_count == 1
    assert report.invalid_volume_count == 2
    assert report.future_timestamp_count == 1
    assert report.latest_candle_timestamp == datetime(2026, 5, 5, 1, 30, tzinfo=timezone.utc)
    assert report.data_lag_seconds == -1800
