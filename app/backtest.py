from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Protocol, Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class Candle:
    symbol: str
    open_time: datetime
    close: Decimal


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
    ) -> list[Candle]:
        if interval != "1m":
            raise ValueError("Only 1m candles are supported for M4.1")

        where_clauses = ["symbol = %s"]
        params: list[object] = [symbol]
        if start_time is not None:
            where_clauses.append("open_time >= %s")
            params.append(start_time)
        if end_time is not None:
            where_clauses.append("open_time <= %s")
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
                    SELECT symbol, open_time, close
                    FROM candles_1m
                    WHERE {where_sql}
                    ORDER BY open_time ASC
                    {limit_clause}
                    """,
                    params,
                )
                rows = cur.fetchall()

        return [Candle(symbol=row["symbol"], open_time=row["open_time"], close=row["close"]) for row in rows]


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


class DynamicSignalStrategy:
    def __init__(self, strategy_id: str, module: Any, params: dict[str, object]):
        self.strategy_name = strategy_id
        self.module = module
        self.params = params
        self._signals: list[int] = []
        self._cursor = 0

    def set_candles(self, candles: list[Candle]) -> None:
        frame = [{"open_time": c.open_time, "close": float(c.close), "symbol": c.symbol} for c in candles]
        prepared = self.module.prepare_features(frame, self.params)
        signal_rows = self.module.generate_signals(prepared, self.params)
        self._signals = [int(row.get("signal", 0)) for row in signal_rows]
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


def build_strategy(strategy_id: str, strategy_params: dict[str, object]) -> Strategy:
    from app.strategy_loader import strategy_loader
    definition = strategy_loader.get(strategy_id)
    params = _validate_params(definition.meta, strategy_params)
    return DynamicSignalStrategy(strategy_id, definition.module, params)


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
    trades: int
    win_rate_pct: float
    final_equity: float
    max_drawdown_pct: float
    profit_factor: float
    average_trade_return_pct: float
    total_fees: float
    summary_timestamp: str
    config_hash: str
    dataset_fingerprint: str
    dataset_row_count: int
    dataset_min_open_time: str | None
    dataset_max_open_time: str | None
    equity_curve: list[EquityPoint]
    fills: list[Fill]


@dataclass(frozen=True)
class DatasetFingerprint:
    fingerprint: str
    row_count: int
    min_open_time: datetime | None
    max_open_time: datetime | None


class SimulatedExecutionModel:
    """Deterministic executor with slippage and fee support."""

    def __init__(
        self,
        initial_cash: float = 10_000.0,
        fee_rate: float = 0.0006,  # Default 0.06% (e.g. Binance spot taker)
        slippage_rate: float = 0.0001,  # Default 0.01%
    ):
        self.initial_cash = initial_cash
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate

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
        trades = 0
        wins = 0
        total_fees = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        trade_returns: list[float] = []
        equity_curve = [EquityPoint(open_time=candle_list[0].open_time, equity=equity)]
        fills: list[Fill] = []

        for i in range(1, len(candle_list)):
            prev_close = float(candle_list[i - 1].close)
            curr_close = float(candle_list[i].close)

            target_position = strategy.on_candle(candle_list[i - 1])
            if target_position != position:
                # Execution with slippage
                # If buying (position increasing), price is higher. If selling, price is lower.
                direction = 1 if target_position > position else -1
                exec_price = curr_close * (1.0 + (direction * self.slippage_rate))
                
                # Fees are calculated on the notion value of the trade
                trade_value = abs(target_position - position) * exec_price
                # In this simple model, 1 unit is 'all in' or 'all out' based on current equity
                # To keep it simple and consistent with the previous model, we assume the trade 
                # size is based on the current equity value at the exec price.
                fee = equity * abs(target_position - position) * self.fee_rate
                equity -= fee
                total_fees += fee

                trades += 1
                fills.append(
                    Fill(
                        open_time=candle_list[i].open_time,
                        prev_position=position,
                        new_position=target_position,
                        exec_price=exec_price,
                    )
                )
                position = target_position

            # PnL calculation remains close-to-close for simplicity, 
            # but we use the adjusted equity from fees.
            ret = (curr_close - prev_close) / prev_close
            pnl = equity * position * ret
            
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)

            if position != 0:
                trade_returns.append(position * ret * 100.0)

            equity += pnl
            equity_curve.append(EquityPoint(open_time=candle_list[i].open_time, equity=equity))

        running_peak = self.initial_cash
        max_drawdown_pct = 0.0
        for point in equity_curve:
            running_peak = max(running_peak, point.equity)
            if running_peak > 0:
                drawdown_pct = ((running_peak - point.equity) / running_peak) * 100.0
                max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

        total_return_pct = ((equity / self.initial_cash) - 1.0) * 100.0
        win_rate_pct = (wins / max(1, len(candle_list) - 1)) * 100.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
        avg_trade_return_pct = sum(trade_returns) / len(trade_returns) if trade_returns else 0.0

        summary_timestamp = candle_list[-1].open_time.astimezone(timezone.utc).replace(microsecond=0).isoformat()

        return BacktestResult(
            total_return_pct=total_return_pct,
            trades=trades,
            win_rate_pct=win_rate_pct,
            final_equity=equity,
            max_drawdown_pct=max_drawdown_pct,
            profit_factor=profit_factor,
            average_trade_return_pct=avg_trade_return_pct,
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
                        run_id, status, config_hash, dataset_fingerprint, symbol, interval, start_time, end_time
                    ) VALUES (%s, 'running', %s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, config_hash, dataset_fingerprint, symbol, interval, start_time, end_time),
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
                        average_trade_return, trade_count, win_rate, total_fees
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                           m.average_trade_return, m.trade_count, m.win_rate, m.total_fees
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
    engine = SimulatedExecutionModel(initial_cash=10_000.0, fee_rate=fee_rate, slippage_rate=slippage_rate)
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
