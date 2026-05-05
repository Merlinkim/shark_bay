import argparse
import csv
import io
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


REQUIRED_FIELDS = ["open_time", "open", "high", "low", "close", "volume"]


@dataclass
class ImportStats:
    rows_read: int = 0
    rows_inserted: int = 0
    duplicates_skipped_or_upserted: int = 0
    invalid_rows_skipped: int = 0
    min_open_time: datetime | None = None
    max_open_time: datetime | None = None


def _ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _extract_rows(file_path: str):
    if file_path.lower().endswith(".zip"):
        with zipfile.ZipFile(file_path, "r") as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("zip does not contain any .csv file")
            with zf.open(csv_names[0], "r") as f:
                text = io.TextIOWrapper(f, encoding="utf-8")
                yield from csv.reader(text)
    elif file_path.lower().endswith(".csv"):
        with open(file_path, "r", encoding="utf-8") as f:
            yield from csv.reader(f)
    else:
        raise ValueError("unsupported file type; use .csv or .zip")


def _normalize_kline_row(raw):
    # Binance Vision kline row (no header):
    # open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_buy_base,taker_buy_quote,ignore
    try:
        return {
            "open_time": _ms_to_utc(int(raw[0])),
            "open": Decimal(raw[1]),
            "high": Decimal(raw[2]),
            "low": Decimal(raw[3]),
            "close": Decimal(raw[4]),
            "volume": Decimal(raw[5]),
            "close_time": _ms_to_utc(int(raw[6])) if len(raw) > 6 and raw[6] else _ms_to_utc(int(raw[0]) + 60000),
            "trades": int(raw[8]) if len(raw) > 8 and raw[8] else 0,
            "taker_buy_base": Decimal(raw[9]) if len(raw) > 9 and raw[9] else Decimal("0"),
            "taker_buy_quote": Decimal(raw[10]) if len(raw) > 10 and raw[10] else Decimal("0"),
        }
    except (IndexError, ValueError, InvalidOperation) as exc:
        raise ValueError(f"row parsing failed: {exc}") from exc


def _is_header_row(raw):
    first = (raw[0].strip().lower() if raw else "")
    return first in {"open_time", "open time", "timestamp"}


def _validate_candle(c):
    if c["high"] < c["low"]:
        return False
    if c["high"] < c["open"] or c["high"] < c["close"]:
        return False
    if c["low"] > c["open"] or c["low"] > c["close"]:
        return False
    if c["volume"] < 0:
        return False
    return True


def _interval_ms(interval: str) -> int:
    if interval.endswith("m"):
        return int(interval[:-1]) * 60_000
    if interval.endswith("h"):
        return int(interval[:-1]) * 3_600_000
    if interval.endswith("d"):
        return int(interval[:-1]) * 86_400_000
    raise ValueError(f"unsupported interval: {interval}")


def _upsert_candle(conn, candle):
    from app.main import upsert_candle

    return upsert_candle(conn, candle)


def run_import(file_path: str, symbol: str, interval: str, dry_run: bool = False, max_rows: int | None = None):
    print("import_start", {"file": file_path, "symbol": symbol, "interval": interval, "dry_run": dry_run, "max_rows": max_rows})
    stats = ImportStats()
    expected_step = _interval_ms(interval)
    previous_open_time = None

    conn = None
    if not dry_run:
        import psycopg2
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/market_data")
        conn = psycopg2.connect(db_url)

    try:
        for idx, raw in enumerate(_extract_rows(file_path)):
            if max_rows is not None and stats.rows_read >= max_rows:
                break
            if not raw:
                continue
            if idx == 0 and _is_header_row(raw):
                continue

            stats.rows_read += 1
            try:
                candle = _normalize_kline_row(raw)
                candle["symbol"] = symbol

                missing = [f for f in REQUIRED_FIELDS if candle.get(f) is None]
                if missing:
                    raise ValueError(f"missing required fields: {missing}")

                if not _validate_candle(candle):
                    raise ValueError("ohlc/volume validation failed")

                if previous_open_time and candle["open_time"] < previous_open_time:
                    raise ValueError("open_time is not sorted ascending")

                if previous_open_time and candle["open_time"] > previous_open_time:
                    delta_ms = int((candle["open_time"] - previous_open_time).total_seconds() * 1000)
                    if delta_ms % expected_step != 0:
                        raise ValueError("open_time continuity check failed")

                previous_open_time = candle["open_time"]
                stats.min_open_time = candle["open_time"] if stats.min_open_time is None else min(stats.min_open_time, candle["open_time"])
                stats.max_open_time = candle["open_time"] if stats.max_open_time is None else max(stats.max_open_time, candle["open_time"])

                if dry_run:
                    continue

                inserted = _upsert_candle(conn, candle)
                if inserted:
                    stats.rows_inserted += 1
                else:
                    stats.duplicates_skipped_or_upserted += 1
            except Exception:
                stats.invalid_rows_skipped += 1

        if conn is not None:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()

    print("validation_summary", {"invalid_rows_skipped": stats.invalid_rows_skipped})
    print("import_end", {
        "rows_read": stats.rows_read,
        "rows_inserted": stats.rows_inserted,
        "duplicates_skipped_or_upserted": stats.duplicates_skipped_or_upserted,
        "invalid_rows_skipped": stats.invalid_rows_skipped,
        "min_open_time": stats.min_open_time.isoformat() if stats.min_open_time else None,
        "max_open_time": stats.max_open_time.isoformat() if stats.max_open_time else None,
    })
    return stats


def main():
    parser = argparse.ArgumentParser(description="Import Binance Vision historical klines into PostgreSQL")
    parser.add_argument("--file", required=True, help="Path to .csv or .zip file")
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. BTCUSDT")
    parser.add_argument("--interval", required=True, help="Kline interval, e.g. 1m")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not write to DB")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional maximum rows to process")
    args = parser.parse_args()

    run_import(
        file_path=args.file,
        symbol=args.symbol,
        interval=args.interval,
        dry_run=args.dry_run,
        max_rows=args.max_rows,
    )


if __name__ == "__main__":
    main()
