import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass
class Candle:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url


def fetch_candles(symbol: str, interval: str, lookback_hours: int, db_url: str | None = None) -> list[Candle]:
    if interval != "1m":
        raise ValueError("Only interval=1m is supported")
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    query = """
        SELECT open_time, open, high, low, close, volume
        FROM candles_1m
        WHERE symbol = %s AND open_time >= %s
        ORDER BY open_time ASC
    """
    candles: list[Candle] = []
    with psycopg.connect(db_url or _get_db_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (symbol, since))
            for row in cur.fetchall():
                open_v = _safe_float(row["open"])
                high_v = _safe_float(row["high"])
                low_v = _safe_float(row["low"])
                close_v = _safe_float(row["close"])
                volume_v = _safe_float(row["volume"])
                if None in (open_v, high_v, low_v, close_v):
                    continue
                candles.append(Candle(row["open_time"], open_v, high_v, low_v, close_v, volume_v or 0.0))
    return candles


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _std(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    m = _mean(vals)
    if m is None:
        return None
    var = sum((v - m) ** 2 for v in vals) / len(vals)
    return math.sqrt(var)


def compute_feature_snapshot(candles: list[Candle], symbol: str, interval: str, lookback_hours: int) -> dict[str, Any]:
    status = "ok"
    notes: list[str] = []
    if not candles:
        status = "insufficient_data"
        notes.append("No candles found in lookback window")
    gaps = 0
    for i in range(1, len(candles)):
        dt = candles[i].open_time - candles[i - 1].open_time
        if dt.total_seconds() > 60:
            gaps += 1
    if gaps:
        status = "degraded"
        notes.append(f"Detected {gaps} candle gaps")

    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    rets: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        cur = closes[i]
        if prev == 0:
            rets.append(0.0)
            continue
        rets.append((cur - prev) / prev)

    latest = closes[-1] if closes else None
    return_1m = rets[-1] if rets else None
    return_5m = ((closes[-1] - closes[-6]) / closes[-6]) if len(closes) >= 6 and closes[-6] != 0 else None

    vol_window = rets[-20:] if len(rets) >= 20 else rets
    volatility_20 = _std(vol_window)

    vol20 = volumes[-20:] if len(volumes) >= 20 else volumes
    vol_mean = _mean(vol20)
    vol_std = _std(vol20)
    volume_z = None
    if vol_mean is not None and vol_std not in (None, 0) and volumes:
        volume_z = (volumes[-1] - vol_mean) / vol_std

    sma_20 = _mean(closes[-20:] if len(closes) >= 20 else closes)

    ema_20 = None
    if closes:
        alpha = 2 / (20 + 1)
        ema_20 = closes[0]
        for price in closes[1:]:
            ema_20 = alpha * price + (1 - alpha) * ema_20

    rsi_14 = None
    if len(rets) >= 14:
        gains = [max(r, 0) for r in rets[-14:]]
        losses = [abs(min(r, 0)) for r in rets[-14:]]
        avg_gain = _mean(gains) or 0.0
        avg_loss = _mean(losses) or 0.0
        if avg_loss == 0:
            rsi_14 = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi_14 = 100 - (100 / (1 + rs))

    atr_14 = None
    if len(candles) >= 15:
        trs: list[float] = []
        for i in range(1, len(candles)):
            prev_close = candles[i - 1].close
            c = candles[i]
            tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
            trs.append(tr)
        atr_14 = _mean(trs[-14:]) if len(trs) >= 14 else _mean(trs)

    trend_strength = None
    if sma_20 not in (None, 0) and ema_20 is not None:
        trend_strength = (ema_20 - sma_20) / abs(sma_20)

    regime_label = "unknown"
    if trend_strength is not None and volatility_20 is not None:
        if abs(trend_strength) > 0.002 and volatility_20 > 0.001:
            regime_label = "trend"
        elif volatility_20 < 0.0007:
            regime_label = "range"
        else:
            regime_label = "transition"

    min_rows = 21
    if len(candles) < min_rows:
        status = "insufficient_data"
        notes.append(f"Only {len(candles)} rows; recommend at least {min_rows}")

    features = {
        "return_1m": return_1m,
        "return_5m": return_5m,
        "volatility_20": volatility_20,
        "volume_zscore_20": volume_z,
        "sma_20": sma_20,
        "ema_20": ema_20,
        "rsi_14": rsi_14,
        "atr_14": atr_14,
        "trend_strength": trend_strength,
        "regime_label": regime_label,
        "latest_close": latest,
    }
    for k, v in list(features.items()):
        if isinstance(v, float) and not math.isfinite(v):
            features[k] = None
            notes.append(f"Non-finite value sanitized for {k}")

    return {
        "symbol": symbol,
        "interval": interval,
        "lookback_hours": lookback_hours,
        "rows_used": len(candles),
        "latest_open_time": candles[-1].open_time.isoformat() if candles else None,
        "features": features,
        "quality": {
            "status": status,
            "gaps_detected": gaps,
            "notes": notes,
        },
    }


def build_snapshot(symbol: str = "BTCUSDT", interval: str = "1m", lookback_hours: int = 24) -> dict[str, Any]:
    candles = fetch_candles(symbol=symbol, interval=interval, lookback_hours=lookback_hours)
    return compute_feature_snapshot(candles, symbol=symbol, interval=interval, lookback_hours=lookback_hours)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research feature telemetry snapshot")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--lookback-hours", type=int, default=24)
    args = parser.parse_args()
    payload = build_snapshot(symbol=args.symbol, interval=args.interval, lookback_hours=args.lookback_hours)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
