from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Protocol, Any

import psycopg
from psycopg.rows import dict_row

from app.stats import annualized_sharpe


ENGINE_VERSION = "v2"

# Single source of truth for transaction costs (Phase 0, Funding Carry milestone).
# Binance USDⓈ-M futures taker fee is 10 bps (0.04% maker / 0.10% taker at the
# base VIP-0 tier without BNB discount). Research must assume taker fills: a
# signal that only survives at maker fees is not a real edge. SLIPPAGE_BPS is a
# conservative add-on for market-order impact at retail size. cost_multiplier
# stress-tests robustness (1.0 baseline, 1.5x / 2.0x adverse).
BINANCE_TAKER_FEE_BPS = 10.0
DEFAULT_SLIPPAGE_BPS = 2.0


@dataclass(frozen=True)
class Candle:
    symbol: str
    open_time: datetime
    close: Decimal
    # OHLCV (Engine v2). Optional so synthetic/legacy constructors keep working;
    # accessors below fall back to close when absent.
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: Decimal | None = None
    # Auxiliary market-structure data (Funding Carry milestone). Optional so all
    # existing constructors and the ten legacy strategies are unaffected.
    # funding_rate: the funding rate SETTLED at this bar's open_time (8h cadence
    #   on Binance perps). Known at open_time → using it for a decision executed
    #   at the NEXT bar's open is leakage-free.
    # open_interest: total open interest observed as of this bar's open_time.
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None

    @property
    def open_(self) -> Decimal:
        return self.open if self.open is not None else self.close

    @property
    def high_(self) -> Decimal:
        return self.high if self.high is not None else max(self.open_, self.close)

    @property
    def low_(self) -> Decimal:
        return self.low if self.low is not None else min(self.open_, self.close)


# Supported research intervals and their length in minutes. 1m is native;
# everything else is aggregated from 1m bars via resample_candles.
INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "8h": 480,
    "1d": 1440,
}


def resample_candles(candles: list["Candle"], interval: str) -> list["Candle"]:
    """Aggregate 1m candles into a coarser interval, anchored to UTC midnight.

    Aggregation is OHLCV: open = first open, high = max high, low = min low,
    close = last close, volume = sum. Each output bar's open_time is the start
    of its interval bucket. A bucket is emitted only when it contains at least
    one source candle; partial buckets are kept (they reflect real, if
    incomplete, market activity) — gap handling is the caller's concern.

    This is pure and deterministic so it can be unit-tested without a database.
    Auxiliary fields (funding_rate, open_interest) are intentionally NOT carried
    here: they are joined onto the resampled timeline separately, as-of each
    bar, to keep look-ahead control in one place.
    """
    if interval == "1m":
        return list(candles)
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"Unsupported interval: {interval}")
    width = INTERVAL_MINUTES[interval]
    buckets: dict[datetime, list[Candle]] = {}
    order: list[datetime] = []
    for c in candles:
        epoch_min = int(c.open_time.timestamp() // 60)
        bucket_min = (epoch_min // width) * width
        bucket_time = datetime.fromtimestamp(bucket_min * 60, tz=timezone.utc)
        if bucket_time not in buckets:
            buckets[bucket_time] = []
            order.append(bucket_time)
        buckets[bucket_time].append(c)
    out: list[Candle] = []
    for bucket_time in order:
        group = buckets[bucket_time]
        symbol = group[0].symbol
        opens = group[0].open_
        high = max(c.high_ for c in group)
        low = min(c.low_ for c in group)
        close = group[-1].close
        volume = sum((c.volume for c in group if c.volume is not None), Decimal(0))
        out.append(
            Candle(
                symbol=symbol,
                open_time=bucket_time,
                close=close,
                open=opens,
                high=high,
                low=low,
                volume=volume,
            )
        )
    return out


class CandleRepository:
    """Loads historical candles in deterministic time order."""

    def __init__(self, db_url: str):
        self.db_url = db_url

    def get_candles(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        allow_holdout: bool = False,
    ) -> list[Candle]:
        if interval not in INTERVAL_MINUTES:
            raise ValueError(f"Unsupported interval: {interval}")
        # 1m is stored natively; coarser intervals are aggregated from 1m below.
        # The holdout clamp is applied on the 1m timeline before aggregation so a
        # resampled bar can never straddle the boundary.

        if not allow_holdout:
            from app.holdout import clamp_research_end, holdout_start
            boundary = holdout_start()
            if boundary is not None:
                clamped = clamp_research_end(end_time)
                # The boundary itself is exclusive: clamp to strictly before it.
                if clamped is not None and clamped >= boundary:
                    clamped = boundary
                    where_op_end = "open_time < %s"
                else:
                    where_op_end = "open_time <= %s"
                end_time = clamped
            else:
                where_op_end = "open_time <= %s"
        else:
            where_op_end = "open_time <= %s"

        where_clauses = ["symbol = %s"]
        params: list[object] = [symbol]
        if start_time is not None:
            where_clauses.append("open_time >= %s")
            params.append(start_time)
        if end_time is not None:
            where_clauses.append(where_op_end)
            params.append(end_time)

        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT %s"
            params.append(limit)

        where_sql = " AND ".join(where_clauses)

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT symbol, open_time, open, high, low, close, volume
                    FROM candles_1m
                    WHERE {where_sql}
                    ORDER BY open_time ASC
                    {limit_clause}
                    """,
                    params,
                )
                rows = cur.fetchall()

        native = [
            Candle(
                symbol=row["symbol"],
                open_time=row["open_time"],
                close=row["close"],
                open=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                volume=row.get("volume"),
            )
            for row in rows
        ]
        return resample_candles(native, interval) if interval != "1m" else native


class Strategy(Protocol):
    strategy_name: str
    description: str
    parameter_schema: dict[str, dict[str, object]]
    default_parameters: dict[str, object]

    def on_candle(self, candle: Candle) -> int:
        """Return target position: -1 short, 0 flat, +1 long."""


class IndicatorLibrary:
    """Pure deterministic indicator helpers."""

    @staticmethod
    def sma(values: list[Decimal], window: int) -> Decimal | None:
        if window <= 0 or len(values) < window:
            return None
        return sum(values[-window:]) / Decimal(window)

    @staticmethod
    def ema(values: list[Decimal], window: int) -> Decimal | None:
        if window <= 0 or len(values) < window:
            return None
        alpha = Decimal(2) / Decimal(window + 1)
        ema_value = values[0]
        for value in values[1:]:
            ema_value = (value * alpha) + (ema_value * (Decimal(1) - alpha))
        return ema_value

    @staticmethod
    def rsi(values: list[Decimal], window: int = 14) -> Decimal | None:
        if window <= 0 or len(values) < window + 1:
            return None
        gains = Decimal(0)
        losses = Decimal(0)
        for i in range(-window, 0):
            change = values[i] - values[i - 1]
            if change > 0:
                gains += change
            elif change < 0:
                losses += abs(change)
        if losses == 0:
            return Decimal(100)
        rs = (gains / Decimal(window)) / (losses / Decimal(window))
        return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))

    @staticmethod
    def atr(highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], window: int = 14) -> Decimal | None:
        if window <= 0 or len(closes) < window + 1 or len(highs) != len(lows) or len(lows) != len(closes):
            return None
        true_ranges: list[Decimal] = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            true_ranges.append(tr)
        if len(true_ranges) < window:
            return None
        return sum(true_ranges[-window:]) / Decimal(window)

    @staticmethod
    def bollinger_bands(values: list[Decimal], window: int = 20, num_stddev: Decimal = Decimal(2)) -> tuple[Decimal, Decimal, Decimal] | None:
        mean = IndicatorLibrary.sma(values, window)
        if mean is None:
            return None
        sample = values[-window:]
        variance = sum((v - mean) ** 2 for v in sample) / Decimal(window)
        stddev = variance.sqrt()
        upper = mean + num_stddev * stddev
        lower = mean - num_stddev * stddev
        return lower, mean, upper


class SmaCrossoverStrategy:
    strategy_name = "sma_crossover"
    description = "SMA crossover using short and long lookback windows."
    parameter_schema = {
        "short_window": {"type": "int", "min": 1, "max": 500},
        "long_window": {"type": "int", "min": 2, "max": 1000},
    }
    default_parameters = {"short_window": 5, "long_window": 20}

    def __init__(self, short_window: int = 5, long_window: int = 20):
        if short_window >= long_window:
            raise ValueError("short_window must be < long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.closes: list[Decimal] = []

    def on_candle(self, candle: Candle) -> int:
        self.closes.append(candle.close)
        short_sma = IndicatorLibrary.sma(self.closes, self.short_window)
        long_sma = IndicatorLibrary.sma(self.closes, self.long_window)
        if short_sma is None or long_sma is None:
            return 0
        if short_sma > long_sma:
            return 1
        if short_sma < long_sma:
            return -1
        return 0


class BollingerRsiStrategy:
    strategy_name = "bb_rsi_reversion"
    description = "Mean reversion using Bollinger Bands and RSI."
    parameter_schema = {
        "bb_window": {"type": "int", "min": 2, "max": 200},
        "bb_stddev": {"type": "float", "min": 0.1, "max": 5.0},
        "rsi_window": {"type": "int", "min": 2, "max": 100},
        "rsi_lower": {"type": "int", "min": 1, "max": 50},
        "rsi_upper": {"type": "int", "min": 51, "max": 99},
    }
    default_parameters = {
        "bb_window": 20,
        "bb_stddev": 2.0,
        "rsi_window": 14,
        "rsi_lower": 30,
        "rsi_upper": 70,
    }

    def __init__(self, bb_window=20, bb_stddev=2.0, rsi_window=14, rsi_lower=30, rsi_upper=70, **kwargs):
        self.bb_window = int(bb_window)
        self.bb_stddev = Decimal(str(bb_stddev))
        self.rsi_window = int(rsi_window)
        self.rsi_lower = int(rsi_lower)
        self.rsi_upper = int(rsi_upper)
        self.closes: list[Decimal] = []
        self.current_position = 0

    def on_candle(self, candle: Candle) -> int:
        self.closes.append(candle.close)
        bb = IndicatorLibrary.bollinger_bands(self.closes, self.bb_window, self.bb_stddev)
        rsi = IndicatorLibrary.rsi(self.closes, self.rsi_window)

        if bb is None or rsi is None:
            return 0

        lower_band, mid_band, upper_band = bb
        price = candle.close

        # Long Entry: Price below lower band and RSI oversold
        if self.current_position == 0 and price < lower_band and rsi < self.rsi_lower:
            self.current_position = 1
        # Short Entry: Price above upper band and RSI overbought
        elif self.current_position == 0 and price > upper_band and rsi > self.rsi_upper:
            self.current_position = -1
        # Exit Long: Price reaches mid band
        elif self.current_position == 1 and price >= mid_band:
            self.current_position = 0
        # Exit Short: Price reaches mid band
        elif self.current_position == -1 and price <= mid_band:
            self.current_position = 0

        return self.current_position


class LookaheadError(RuntimeError):
    """Raised when a dynamic strategy's signals depend on future candles."""


class DynamicSignalStrategy:
    def __init__(self, strategy_id: str, module: Any, params: dict[str, object]):
        self.strategy_name = strategy_id
        self.module = module
        self.params = params
        self._signals: list[int] = []
        self._cursor = 0

    @staticmethod
    def _frame(candles: list[Candle]) -> list[dict[str, object]]:
        # funding_rate / open_interest are included only when present so existing
        # OHLCV-only strategies see an unchanged frame shape (the keys are simply
        # absent). A funding strategy reads c["funding_rate"] for the value known
        # AT this bar; the prefix-invariance leakage guard then enforces that the
        # row-k signal cannot depend on any row > k, funding included.
        rows: list[dict[str, object]] = []
        for c in candles:
            row: dict[str, object] = {
                "open_time": c.open_time,
                "open": float(c.open_),
                "high": float(c.high_),
                "low": float(c.low_),
                "close": float(c.close),
                "volume": float(c.volume) if c.volume is not None else 0.0,
                "symbol": c.symbol,
            }
            if c.funding_rate is not None:
                row["funding_rate"] = float(c.funding_rate)
            if c.open_interest is not None:
                row["open_interest"] = float(c.open_interest)
            rows.append(row)
        return rows

    def _compute_signals(self, candles: list[Candle]) -> list[int]:
        frame = self._frame(candles)
        prepared = self.module.prepare_features(frame, self.params)
        signal_rows = self.module.generate_signals(prepared, self.params)
        return [int(row.get("signal", 0)) for row in signal_rows]

    def _assert_no_lookahead(self, candles: list[Candle], full_signals: list[int]) -> None:
        """Prefix-invariance check: the signal at row k must be identical when the
        strategy only sees candles[:k+1]. If truncating the future changes a past
        signal, the strategy is reading ahead. Controlled by
        SHARKBAY_LEAKAGE_CHECK (default on; set to 0 to skip, e.g. for benchmarks).
        """
        if os.getenv("SHARKBAY_LEAKAGE_CHECK", "1") != "1":
            return
        n = len(candles)
        if n < 8:
            return
        for cut in sorted({n // 4, n // 2, (3 * n) // 4}):
            if cut < 2:
                continue
            truncated = self._compute_signals(candles[:cut])
            if truncated != full_signals[:cut]:
                first_bad = next(
                    (idx for idx, (a, b) in enumerate(zip(truncated, full_signals[:cut])) if a != b),
                    len(truncated),
                )
                raise LookaheadError(
                    f"Strategy {self.strategy_name} produced a different signal at row {first_bad} "
                    f"when future candles beyond row {cut - 1} were removed. Signals must depend "
                    f"only on past and current rows."
                )

    def set_candles(self, candles: list[Candle]) -> None:
        self._signals = self._compute_signals(candles)
        self._assert_no_lookahead(candles, self._signals)
        self._cursor = 0

    def on_candle(self, candle: Candle) -> int:
        if self._cursor >= len(self._signals):
            return 0
        sig = self._signals[self._cursor]
        self._cursor += 1
        return sig


def _validate_params(meta: dict[str, object], strategy_params: dict[str, object]) -> dict[str, object]:
    schema = meta.get("parameter_schema", {})
    merged = dict(meta.get("default_parameters", {}))
    merged.update(strategy_params)
    for key, spec in schema.items():
        if key not in merged:
            raise ValueError(f"Missing strategy parameter: {key}")
        value = merged[key]
        if spec.get("type") == "int":
            value = int(value)
        elif spec.get("type") == "float":
            value = float(value)
        if "min" in spec and value < spec["min"]:
            raise ValueError(f"Parameter {key} below minimum")
        if "max" in spec and value > spec["max"]:
            raise ValueError(f"Parameter {key} above maximum")
        merged[key] = value
    return merged


def build_strategy(strategy_name: str, strategy_params: dict[str, object]) -> Strategy:
    from app.strategy_loader import strategy_loader
    definition = strategy_loader.get(strategy_name)
    params = _validate_params(definition.meta, strategy_params)
    return DynamicSignalStrategy(strategy_name, definition.module, params)


def get_strategy_registry_metadata() -> dict[str, dict[str, object]]:
    from app.strategy_loader import strategy_loader
    return strategy_loader.list_metadata()


@dataclass(frozen=True)
class EquityPoint:
    open_time: datetime
    equity: float


@dataclass(frozen=True)
class Fill:
    open_time: datetime
    prev_position: int
    new_position: int
    exec_price: float


@dataclass
class BacktestResult:
    total_return_pct: float
    trades: int  # closed round trips, not fills
    win_rate_pct: float  # winning round trips / closed round trips
    sharpe: float
    final_equity: float
    max_drawdown_pct: float
    profit_factor: float
    average_trade_return_pct: float
    trade_return_std_pct: float  # population std of per-round-trip returns; 0 if < 2 trades
    total_fees: float
    summary_timestamp: str
    config_hash: str
    dataset_fingerprint: str
    dataset_row_count: int
    dataset_min_open_time: str | None
    dataset_max_open_time: str | None
    equity_curve: list[EquityPoint]
    fills: list[Fill]
    engine_version: str = ENGINE_VERSION


@dataclass(frozen=True)
class DatasetFingerprint:
    fingerprint: str
    row_count: int
    min_open_time: datetime | None
    max_open_time: datetime | None


@dataclass(frozen=True)
class RiskConfig:
    position_size_mode: str = "notional_fraction"
    risk_per_trade: float = 0.01
    max_position_size: float = 1.0
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04
    max_holding_minutes: int = 240
    max_daily_loss_pct: float = 5.0
    max_drawdown_pct: float = 20.0


@dataclass(frozen=True)
class ExecutionConfig:
    fee_bps: float = BINANCE_TAKER_FEE_BPS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS
    slippage_model: str = "fixed_bps"
    initial_cash: float = 10_000.0
    # Multiplies both fee and slippage. 1.0 = modeled baseline; 1.5 / 2.0 are
    # adverse-cost stress runs. A strategy that only passes below 1.0 is fragile.
    cost_multiplier: float = 1.0


def build_risk_config(raw: dict[str, object] | None) -> RiskConfig:
    raw = raw or {}
    return RiskConfig(
        position_size_mode=str(raw.get("position_size_mode", "notional_fraction")),
        risk_per_trade=float(raw.get("risk_per_trade", 0.01)),
        max_position_size=float(raw.get("max_position_size", 1.0)),
        stop_loss_pct=float(raw.get("stop_loss_pct", 0.02)),
        take_profit_pct=float(raw.get("take_profit_pct", 0.04)),
        max_holding_minutes=int(raw.get("max_holding_minutes", 240)),
        max_daily_loss_pct=float(raw.get("max_daily_loss_pct", 5.0)),
        max_drawdown_pct=float(raw.get("max_drawdown_pct", 20.0)),
    )


def build_execution_config(raw: dict[str, object] | None) -> ExecutionConfig:
    raw = raw or {}
    return ExecutionConfig(
        fee_bps=float(raw.get("fee_bps", BINANCE_TAKER_FEE_BPS)),
        slippage_bps=float(raw.get("slippage_bps", DEFAULT_SLIPPAGE_BPS)),
        slippage_model=str(raw.get("slippage_model", "fixed_bps")),
        initial_cash=float(raw.get("initial_cash", 10_000.0)),
        cost_multiplier=float(raw.get("cost_multiplier", 1.0)),
    )


class SimulatedExecutionModel:
    """Deterministic executor with centralized risk, execution, and position controls."""

    def __init__(
        self,
        execution_config: ExecutionConfig | None = None,
        risk_config: RiskConfig | None = None,
        initial_cash: float | None = None,
        interval: str = "1m",
    ):
        self.execution_config = execution_config or ExecutionConfig()
        self.risk_config = risk_config or RiskConfig()
        # Interval drives Sharpe annualization (sqrt of bars/year). A funding
        # carry run on 8h bars must NOT be annualized as if it were 1m.
        self.interval = interval
        if initial_cash is not None:
            self.execution_config = ExecutionConfig(
                fee_bps=self.execution_config.fee_bps,
                slippage_bps=self.execution_config.slippage_bps,
                slippage_model=self.execution_config.slippage_model,
                initial_cash=initial_cash,
                cost_multiplier=self.execution_config.cost_multiplier,
            )
        self.initial_cash = self.execution_config.initial_cash
        cost_mult = self.execution_config.cost_multiplier
        self.fee_rate = (self.execution_config.fee_bps / 10_000.0) * cost_mult
        self.slippage_rate = (self.execution_config.slippage_bps / 10_000.0) * cost_mult

    def _slippage_multiplier(self, direction: int) -> float:
        base = self.slippage_rate
        model = self.execution_config.slippage_model
        if model == "none":
            return 1.0
        if model == "adaptive":
            base *= 1.5
        if model not in {"fixed_bps", "adaptive", "none"}:
            raise ValueError(f"Unsupported slippage_model: {model}")
        return 1.0 + (direction * base)

    def run(
        self,
        candles: Iterable[Candle],
        strategy: Strategy,
        config_hash: str,
        dataset_fingerprint: DatasetFingerprint,
    ) -> BacktestResult:
        candle_list = list(candles)
        if hasattr(strategy, "set_candles"):
            strategy.set_candles(candle_list)

        if len(candle_list) < 2:
            return BacktestResult(
                total_return_pct=0.0,
                trades=0,
                win_rate_pct=0.0,
                sharpe=0.0,
                final_equity=self.initial_cash,
                max_drawdown_pct=0.0,
                profit_factor=0.0,
                average_trade_return_pct=0.0,
                total_fees=0.0,
                summary_timestamp="N/A",
                config_hash=config_hash,
                dataset_fingerprint=dataset_fingerprint.fingerprint,
                dataset_row_count=dataset_fingerprint.row_count,
                dataset_min_open_time=dataset_fingerprint.min_open_time.isoformat() if dataset_fingerprint.min_open_time else None,
                dataset_max_open_time=dataset_fingerprint.max_open_time.isoformat() if dataset_fingerprint.max_open_time else None,
                equity_curve=[],
                fills=[],
            )

        equity = self.initial_cash
        position = 0
        position_size = 0.0
        entry_price: float | None = None
        entry_time: datetime | None = None
        trades = 0  # closed round trips
        trade_wins = 0  # round trips with positive net P&L (incl. fees)
        open_trade_pnl = 0.0  # running net P&L of the currently open round trip
        total_fees = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        trade_returns: list[float] = []
        bar_returns: list[float] = []  # per-bar strategy return on equity, 0.0 when flat
        equity_curve = [EquityPoint(open_time=candle_list[0].open_time, equity=equity)]
        fills: list[Fill] = []

        day_start_equity = equity
        running_peak = equity
        # Mark price of the currently held exposure within the bar being processed.
        # Engine v2 semantics: the signal computed from completed bar i-1 fills at
        # bar i's OPEN; intrabar stops/TPs trigger on bar i's high/low; positions
        # are settled segment-by-segment so no return preceding a fill is ever
        # credited to that fill.
        for i in range(1, len(candle_list)):
            bar = candle_list[i]
            prev_close = float(candle_list[i - 1].close)
            bar_open = float(bar.open_)
            bar_high = float(bar.high_)
            bar_low = float(bar.low_)
            bar_close = float(bar.close)

            if bar.open_time.date() != candle_list[i - 1].open_time.date():
                day_start_equity = equity

            equity_at_bar_start = equity
            mark = prev_close

            def settle(price: float) -> None:
                nonlocal equity, mark, gross_profit, gross_loss, open_trade_pnl
                if position != 0 and mark > 0:
                    pnl = equity * position * position_size * ((price / mark) - 1.0)
                    if pnl > 0:
                        gross_profit += pnl
                    elif pnl < 0:
                        gross_loss += abs(pnl)
                    equity += pnl
                    open_trade_pnl += pnl
                mark = price

            def close_round_trip(fee: float) -> None:
                nonlocal open_trade_pnl, trades, trade_wins
                open_trade_pnl -= fee
                trades += 1
                if open_trade_pnl > 0:
                    trade_wins += 1
                open_trade_pnl = 0.0

            # --- 0. Funding settlement on the position carried into this bar ---
            # Binance perp funding settles AT the bar boundary and is paid by the
            # holder of the position established in a PRIOR bar. Charging it on the
            # carried (pre-fill) position is both economically correct (you must
            # hold across the settlement to pay/receive) and leakage-free (the
            # carried position was decided before this settlement was knowable).
            # Sign: funding_rate > 0 → longs pay shorts, so a long loses and a
            # short gains: pnl = -position * size * equity * funding_rate.
            # No-op when funding_rate is absent → legacy behavior is byte-identical.
            if position != 0 and bar.funding_rate is not None:
                funding_pnl = -position * position_size * equity * float(bar.funding_rate)
                equity += funding_pnl
                open_trade_pnl += funding_pnl
                if funding_pnl > 0:
                    gross_profit += funding_pnl
                elif funding_pnl < 0:
                    gross_loss += abs(funding_pnl)

            # --- 1. Signal from completed bar i-1, executed at bar i open ---
            target_position = int(strategy.on_candle(candle_list[i - 1]))
            if target_position not in {-1, 0, 1}:
                raise ValueError(f"Invalid strategy signal: {target_position}")

            daily_loss_pct = ((day_start_equity - equity) / day_start_equity) * 100.0 if day_start_equity > 0 else 0.0
            drawdown_pct = ((running_peak - equity) / running_peak) * 100.0 if running_peak > 0 else 0.0
            if daily_loss_pct >= self.risk_config.max_daily_loss_pct or drawdown_pct >= self.risk_config.max_drawdown_pct:
                target_position = 0

            if target_position != position:
                direction = 1 if target_position > position else -1
                exec_price = bar_open * self._slippage_multiplier(direction)
                target_size = 0.0
                if target_position != 0:
                    if self.risk_config.position_size_mode == "notional_fraction":
                        target_size = min(max(self.risk_config.risk_per_trade, 0.0), self.risk_config.max_position_size)
                    elif self.risk_config.position_size_mode == "fixed":
                        target_size = min(max(self.risk_config.max_position_size, 0.0), 1.0)
                    elif self.risk_config.position_size_mode == "fixed_fraction":
                        target_size = min(
                            max(self.risk_config.risk_per_trade, 0.0),
                            self.risk_config.max_position_size,
                        )
                    else:
                        raise ValueError(f"Unsupported position_size_mode: {self.risk_config.position_size_mode}")
                # Settle the outgoing exposure to its actual exit price first.
                settle(exec_price)
                fee = equity * abs(target_size - position_size) * self.fee_rate
                equity -= fee
                total_fees += fee
                if position != 0:
                    close_round_trip(fee)
                else:
                    open_trade_pnl = -fee
                fills.append(Fill(open_time=bar.open_time, prev_position=position, new_position=target_position, exec_price=exec_price))
                position = target_position
                position_size = target_size
                entry_price = exec_price if position != 0 else None
                entry_time = bar.open_time if position != 0 else None

            # --- 2. Intrabar risk exits on the position now held, using high/low ---
            if position != 0 and entry_price is not None:
                holding_minutes = (bar.open_time - entry_time).total_seconds() / 60.0 if entry_time is not None else 0.0
                stop_level = entry_price * (1.0 - self.risk_config.stop_loss_pct) if position == 1 else entry_price * (1.0 + self.risk_config.stop_loss_pct)
                take_level = entry_price * (1.0 + self.risk_config.take_profit_pct) if position == 1 else entry_price * (1.0 - self.risk_config.take_profit_pct)
                stop_hit = bar_low <= stop_level if position == 1 else bar_high >= stop_level
                take_hit = bar_high >= take_level if position == 1 else bar_low <= take_level
                timed_exit = holding_minutes >= self.risk_config.max_holding_minutes

                if stop_hit or take_hit or timed_exit:
                    # Conservative priority: stop before take-profit when both touch.
                    if stop_hit:
                        # Gap handling: if the bar opened beyond the stop, the first
                        # available price is the open, not the stop level.
                        raw_exit = min(stop_level, bar_open) if position == 1 else max(stop_level, bar_open)
                    elif take_hit:
                        raw_exit = max(take_level, bar_open) if position == 1 else min(take_level, bar_open)
                    else:
                        raw_exit = bar_open
                    direction = -1 if position == 1 else 1
                    exec_price = raw_exit * self._slippage_multiplier(direction)
                    settle(exec_price)
                    fee = equity * position_size * self.fee_rate
                    equity -= fee
                    total_fees += fee
                    fills.append(Fill(open_time=bar.open_time, prev_position=position, new_position=0, exec_price=exec_price))
                    close_round_trip(fee)
                    position = 0
                    position_size = 0.0
                    entry_price = None
                    entry_time = None

            # --- 3. Settle remaining exposure to the bar close ---
            settle(bar_close)

            bar_equity_return = (equity / equity_at_bar_start) - 1.0 if equity_at_bar_start > 0 else 0.0
            bar_returns.append(bar_equity_return)
            if position != 0 or equity != equity_at_bar_start:
                trade_returns.append(bar_equity_return * 100.0)

            equity_curve.append(EquityPoint(open_time=bar.open_time, equity=equity))
            running_peak = max(running_peak, equity)

        max_drawdown_pct = 0.0
        for point in equity_curve:
            running_peak = max(running_peak, point.equity)
            if running_peak > 0:
                drawdown_pct = ((running_peak - point.equity) / running_peak) * 100.0
                max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

        total_return_pct = ((equity / self.initial_cash) - 1.0) * 100.0
        win_rate_pct = (trade_wins / trades) * 100.0 if trades else 0.0
        sharpe = annualized_sharpe(bar_returns, interval=self.interval)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
        avg_trade_return_pct = sum(trade_returns) / len(trade_returns) if trade_returns else 0.0
        if len(trade_returns) >= 2:
            _tr_mean = avg_trade_return_pct
            trade_return_std_pct = math.sqrt(sum((r - _tr_mean) ** 2 for r in trade_returns) / len(trade_returns))
        else:
            trade_return_std_pct = 0.0

        summary_timestamp = candle_list[-1].open_time.astimezone(timezone.utc).replace(microsecond=0).isoformat()

        return BacktestResult(
            total_return_pct=total_return_pct,
            trades=trades,
            win_rate_pct=win_rate_pct,
            sharpe=sharpe,
            final_equity=equity,
            max_drawdown_pct=max_drawdown_pct,
            profit_factor=profit_factor,
            average_trade_return_pct=avg_trade_return_pct,
            trade_return_std_pct=trade_return_std_pct,
            total_fees=total_fees,
            summary_timestamp=summary_timestamp,
            config_hash=config_hash,
            dataset_fingerprint=dataset_fingerprint.fingerprint,
            dataset_row_count=dataset_fingerprint.row_count,
            dataset_min_open_time=dataset_fingerprint.min_open_time.isoformat() if dataset_fingerprint.min_open_time else None,
            dataset_max_open_time=dataset_fingerprint.max_open_time.isoformat() if dataset_fingerprint.max_open_time else None,
            equity_curve=equity_curve,
            fills=fills,
        )



def build_config_hash(config: dict[str, object]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_dataset_fingerprint(candles: list[Candle]) -> DatasetFingerprint:
    row_count = len(candles)
    if row_count == 0:
        payload = "rows=0|min=None|max=None"
        return DatasetFingerprint(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16], 0, None, None)

    min_open_time = candles[0].open_time
    max_open_time = candles[-1].open_time
    payload = f"rows={row_count}|min={min_open_time.isoformat()}|max={max_open_time.isoformat()}"
    return DatasetFingerprint(
        fingerprint=hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
        row_count=row_count,
        min_open_time=min_open_time,
        max_open_time=max_open_time,
    )


def persist_backtest_outputs(base_dir: str, symbol: str, interval: str, result: BacktestResult) -> Path:
    timestamp_slug = result.summary_timestamp.replace(":", "-")
    run_dir = Path(base_dir) / symbol / interval / f"{timestamp_slug}_{result.config_hash}"
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "equity_curve.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["open_time", "equity"])
        for point in result.equity_curve:
            writer.writerow([point.open_time.isoformat(), f"{point.equity:.8f}"])

    with (run_dir / "fills.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["open_time", "prev_position", "new_position", "exec_price"])
        for fill in result.fills:
            writer.writerow([fill.open_time.isoformat(), fill.prev_position, fill.new_position, f"{fill.exec_price:.8f}"])

    summary = asdict(result)
    summary["equity_curve"] = len(result.equity_curve)
    summary["fills"] = len(result.fills)
    with (run_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    return run_dir


class BacktestRunRepository:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def create_run(
        self,
        symbol: str,
        interval: str,
        config_hash: str,
        dataset_fingerprint: str,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> str:
        run_id = str(uuid.uuid4())
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO backtest_runs (
                        run_id, status, config_hash, dataset_fingerprint, symbol, interval, start_time, end_time, engine_version
                    ) VALUES (%s, 'running', %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, config_hash, dataset_fingerprint, symbol, interval, start_time, end_time, ENGINE_VERSION),
                )
            conn.commit()
        return run_id

    def mark_failed(self, run_id: str, reason: str) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE backtest_runs
                    SET status = 'failed', failure_reason = %s, updated_at = NOW()
                    WHERE run_id = %s
                    """,
                    (reason[:500], run_id),
                )
            conn.commit()

    def persist_completed(self, run_id: str, result: BacktestResult) -> None:
        summary_time = datetime.fromisoformat(result.summary_timestamp)
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE backtest_runs
                    SET status = 'completed', deterministic_summary_timestamp = %s, updated_at = NOW()
                    WHERE run_id = %s
                    """,
                    (summary_time, run_id),
                )
                cur.execute(
                    """
                    INSERT INTO backtest_metrics (
                        run_id, total_return, final_equity, max_drawdown, profit_factor,
                        average_trade_return, trade_count, win_rate, total_fees, sharpe
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        result.total_return_pct,
                        result.final_equity,
                        result.max_drawdown_pct,
                        result.profit_factor,
                        result.average_trade_return_pct,
                        result.trades,
                        result.win_rate_pct,
                        result.total_fees,
                        result.sharpe,
                    ),
                )
                cur.executemany(
                    """
                    INSERT INTO backtest_equity_curve (run_id, point_index, open_time, equity)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [
                        (run_id, idx, point.open_time, point.equity)
                        for idx, point in enumerate(result.equity_curve)
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO backtest_fills (run_id, fill_index, open_time, prev_position, new_position, exec_price)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (run_id, idx, fill.open_time, fill.prev_position, fill.new_position, fill.exec_price)
                        for idx, fill in enumerate(result.fills)
                    ],
                )
            conn.commit()

    def list_runs(self, limit: int = 50) -> list[dict[str, object]]:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, status, symbol, interval, start_time, end_time,
                           config_hash, dataset_fingerprint, created_at
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return cur.fetchall()

    def get_run_with_metrics(self, run_id: str) -> dict[str, object] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.run_id, r.status, r.symbol, r.interval, r.start_time, r.end_time,
                           r.config_hash, r.dataset_fingerprint, r.created_at,
                           r.deterministic_summary_timestamp, r.failure_reason,
                           m.total_return, m.final_equity, m.max_drawdown, m.profit_factor,
                           m.average_trade_return, m.trade_count, m.win_rate, m.total_fees, m.sharpe
                    FROM backtest_runs r
                    LEFT JOIN backtest_metrics m ON m.run_id = r.run_id
                    WHERE r.run_id = %s
                    """,
                    (run_id,),
                )
                return cur.fetchone()

    def get_fills(self, run_id: str) -> list[dict[str, object]]:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT fill_index, open_time, prev_position, new_position, exec_price
                    FROM backtest_fills
                    WHERE run_id = %s
                    ORDER BY fill_index ASC
                    """,
                    (run_id,),
                )
                return cur.fetchall()

    def get_equity_curve(self, run_id: str) -> list[dict[str, object]]:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT point_index, open_time, equity
                    FROM backtest_equity_curve
                    WHERE run_id = %s
                    ORDER BY point_index ASC
                    """,
                    (run_id,),
                )
                return cur.fetchall()


def run_local_backtest(
    symbol: str,
    interval: str,
    limit: int | None,
    short_window: int,
    long_window: int,
    output_dir: str,
    fee_rate: float = 0.0006,
    slippage_rate: float = 0.0001,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    save_results: bool = True,
) -> tuple[BacktestResult, Path | None, str]:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    config = {
        "symbol": symbol,
        "interval": interval,
        "short_window": short_window,
        "long_window": long_window,
        "fee_rate": fee_rate,
        "slippage_rate": slippage_rate,
        "initial_cash": 10_000.0,
    }
    if limit is not None:
        config["limit"] = limit
    config_hash = build_config_hash(config)

    repository = CandleRepository(db_url=db_url)
    candles = repository.get_candles(
        symbol=symbol,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
    )
    dataset_fingerprint = build_dataset_fingerprint(candles)
    strategy = build_strategy(
        strategy_name="sma_crossover",
        strategy_params={"short_window": short_window, "long_window": long_window},
    )
    engine = SimulatedExecutionModel(
        execution_config=ExecutionConfig(
            fee_bps=fee_rate * 10_000.0,
            slippage_bps=slippage_rate * 10_000.0,
            slippage_model="fixed_bps",
            initial_cash=10_000.0,
        ),
        risk_config=RiskConfig(),
    )
    run_repo = BacktestRunRepository(db_url)
    run_id = run_repo.create_run(
        symbol=symbol,
        interval=interval,
        config_hash=config_hash,
        dataset_fingerprint=dataset_fingerprint.fingerprint,
        start_time=start_time,
        end_time=end_time,
    )
    try:
        result = engine.run(candles, strategy, config_hash=config_hash, dataset_fingerprint=dataset_fingerprint)
        run_dir = persist_backtest_outputs(output_dir, symbol, interval, result) if save_results else None
        run_repo.persist_completed(run_id, result)
    except Exception as exc:
        run_repo.mark_failed(run_id, str(exc))
        raise
    return result, run_dir, run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic local candle replay backtest")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--long-window", type=int, default=20)
    parser.add_argument("--fee-rate", type=float, default=0.0006, help="Trading fee rate (e.g. 0.0006 for 0.06%)")
    parser.add_argument("--slippage-rate", type=float, default=0.0001, help="Slippage rate (e.g. 0.0001 for 0.01%)")
    parser.add_argument("--output-dir", default="backtest_results")
    parser.add_argument("--start-time", default=None, help="Inclusive ISO-8601 UTC lower bound for open_time")
    parser.add_argument("--end-time", default=None, help="Inclusive ISO-8601 UTC upper bound for open_time")
    parser.add_argument("--save-results", choices=["true", "false"], default="true")
    args = parser.parse_args()

    start_time = datetime.fromisoformat(args.start_time) if args.start_time else None
    end_time = datetime.fromisoformat(args.end_time) if args.end_time else None

    result, run_dir, run_id = run_local_backtest(
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
        short_window=args.short_window,
        long_window=args.long_window,
        output_dir=args.output_dir,
        fee_rate=args.fee_rate,
        slippage_rate=args.slippage_rate,
        start_time=start_time,
        end_time=end_time,
        save_results=(args.save_results == "true"),
    )

    print("=== Local Backtest Summary ===")
    print(f"Summary Timestamp: {result.summary_timestamp}")
    print(f"Config Hash: {result.config_hash}")
    print(f"Dataset Fingerprint: {result.dataset_fingerprint}")
    print(f"Dataset Rows: {result.dataset_row_count}")
    print(f"Dataset Min Open Time: {result.dataset_min_open_time}")
    print(f"Dataset Max Open Time: {result.dataset_max_open_time}")
    print(f"Total Return: {result.total_return_pct:.2f}%")
    print(f"Total Fees: {result.total_fees:.4f}")
    print(f"Trades: {result.trades}")
    print(f"Win Rate: {result.win_rate_pct:.2f}%")
    print(f"Final Equity: {result.final_equity:.2f}")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"Profit Factor: {result.profit_factor:.4f}")
    print(f"Average Trade Return: {result.average_trade_return_pct:.4f}%")
    print(f"Results Directory: {run_dir if run_dir is not None else 'not saved (--save-results false)'}")
    print(f"Persisted Run ID: {run_id}")



if __name__ == "__main__":
    main()
