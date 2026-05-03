from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Protocol

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

    def get_candles(self, symbol: str, interval: str = "1m", limit: int | None = None) -> list[Candle]:
        if interval != "1m":
            raise ValueError("Only 1m candles are supported for M4.1")

        limit_clause = ""
        params: list[object] = [symbol]
        if limit is not None:
            limit_clause = "LIMIT %s"
            params.append(limit)

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT symbol, open_time, close
                    FROM candles_1m
                    WHERE symbol = %s
                    ORDER BY open_time ASC
                    {limit_clause}
                    """,
                    params,
                )
                rows = cur.fetchall()

        return [Candle(symbol=row["symbol"], open_time=row["open_time"], close=row["close"]) for row in rows]


class Strategy(Protocol):
    def on_candle(self, candle: Candle) -> int:
        """Return target position: -1 short, 0 flat, +1 long."""


class SmaCrossoverStrategy:
    def __init__(self, short_window: int = 5, long_window: int = 20):
        if short_window >= long_window:
            raise ValueError("short_window must be < long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.closes: list[Decimal] = []

    def on_candle(self, candle: Candle) -> int:
        self.closes.append(candle.close)
        if len(self.closes) < self.long_window:
            return 0
        short_sma = sum(self.closes[-self.short_window :]) / Decimal(self.short_window)
        long_sma = sum(self.closes[-self.long_window :]) / Decimal(self.long_window)
        if short_sma > long_sma:
            return 1
        if short_sma < long_sma:
            return -1
        return 0


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
    summary_timestamp: str
    config_hash: str
    equity_curve: list[EquityPoint]
    fills: list[Fill]


class SimulatedExecutionModel:
    """Simple deterministic close-to-close executor (no slippage/fees)."""

    def __init__(self, initial_cash: float = 10_000.0):
        self.initial_cash = initial_cash

    def run(self, candles: Iterable[Candle], strategy: Strategy, config_hash: str) -> BacktestResult:
        candle_list = list(candles)
        if len(candle_list) < 2:
            return BacktestResult(0.0, 0, 0.0, self.initial_cash, 0.0, 0.0, 0.0, "N/A", config_hash, [], [])

        equity = self.initial_cash
        position = 0
        trades = 0
        wins = 0
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
                trades += 1
                fills.append(
                    Fill(
                        open_time=candle_list[i].open_time,
                        prev_position=position,
                        new_position=target_position,
                        exec_price=curr_close,
                    )
                )
                position = target_position

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
            summary_timestamp=summary_timestamp,
            config_hash=config_hash,
            equity_curve=equity_curve,
            fills=fills,
        )


def build_config_hash(config: dict[str, object]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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


def run_local_backtest(symbol: str, interval: str, limit: int | None, short_window: int, long_window: int, output_dir: str) -> tuple[BacktestResult, Path]:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    config = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "short_window": short_window,
        "long_window": long_window,
        "initial_cash": 10_000.0,
    }
    config_hash = build_config_hash(config)

    repository = CandleRepository(db_url=db_url)
    candles = repository.get_candles(symbol=symbol, interval=interval, limit=limit)
    strategy = SmaCrossoverStrategy(short_window=short_window, long_window=long_window)
    engine = SimulatedExecutionModel(initial_cash=10_000.0)
    result = engine.run(candles, strategy, config_hash=config_hash)
    run_dir = persist_backtest_outputs(output_dir, symbol, interval, result)
    return result, run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic local candle replay backtest")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--long-window", type=int, default=20)
    parser.add_argument("--output-dir", default="backtest_results")
    args = parser.parse_args()

    result, run_dir = run_local_backtest(
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
        short_window=args.short_window,
        long_window=args.long_window,
        output_dir=args.output_dir,
    )

    print("=== Local Backtest Summary ===")
    print(f"Summary Timestamp: {result.summary_timestamp}")
    print(f"Config Hash: {result.config_hash}")
    print(f"Total Return: {result.total_return_pct:.2f}%")
    print(f"Trades: {result.trades}")
    print(f"Win Rate: {result.win_rate_pct:.2f}%")
    print(f"Final Equity: {result.final_equity:.2f}")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"Profit Factor: {result.profit_factor:.4f}")
    print(f"Average Trade Return: {result.average_trade_return_pct:.4f}%")
    print(f"Results Directory: {run_dir}")


if __name__ == "__main__":
    main()
