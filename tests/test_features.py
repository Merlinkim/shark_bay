from datetime import datetime, timedelta, timezone

from app.features import Candle, compute_feature_snapshot


def _candles(n: int):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        p = 100 + i
        out.append(Candle(open_time=start + timedelta(minutes=i), open=p, high=p+1, low=p-1, close=p+0.5, volume=1000+i))
    return out


def test_compute_features_deterministic():
    snapshot = compute_feature_snapshot(_candles(40), "BTCUSDT", "1m", 24)
    assert snapshot["rows_used"] == 40
    assert snapshot["features"]["sma_20"] is not None
    assert snapshot["features"]["ema_20"] is not None
    assert snapshot["features"]["regime_label"] in {"trend", "range", "transition", "unknown"}


def test_insufficient_data_no_crash():
    snapshot = compute_feature_snapshot(_candles(3), "BTCUSDT", "1m", 24)
    assert snapshot["quality"]["status"] == "insufficient_data"
