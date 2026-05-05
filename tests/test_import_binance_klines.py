from datetime import timezone
from decimal import Decimal

from app.import_binance_klines import _normalize_kline_row, _validate_candle, run_import


def test_normalize_binance_vision_row():
    row = [
        "1713744000000", "65000.1", "65100.2", "64950.3", "65010.4", "12.345", "1713744059999",
        "0", "123", "6.1", "400000", "0",
    ]
    candle = _normalize_kline_row(row)
    assert candle["open"] == Decimal("65000.1")
    assert candle["open_time"].tzinfo == timezone.utc
    assert candle["trades"] == 123


def test_validate_candle_rejects_bad_ohlc_or_volume():
    assert _validate_candle({"open": Decimal("10"), "high": Decimal("9"), "low": Decimal("8"), "close": Decimal("9"), "volume": Decimal("1")}) is False
    assert _validate_candle({"open": Decimal("10"), "high": Decimal("11"), "low": Decimal("8"), "close": Decimal("9"), "volume": Decimal("-1")}) is False


def test_run_import_dry_run_with_max_rows(tmp_path):
    csv_path = tmp_path / "k.csv"
    csv_path.write_text(
        "1713744000000,65000,65100,64900,65010,1,1713744059999,0,10,0.5,32500,0\n"
        "1713744060000,65010,65120,65000,65100,2,1713744119999,0,12,1,65100,0\n",
        encoding="utf-8",
    )

    stats = run_import(str(csv_path), symbol="BTCUSDT", interval="1m", dry_run=True, max_rows=1)
    assert stats.rows_read == 1
    assert stats.rows_inserted == 0
    assert stats.invalid_rows_skipped == 0
