from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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


@dataclass
class BacktestResult:
    total_return_pct: float
    trades: int
    win_rate_pct: float
    final_equity: float


class SimulatedExecutionModel:
    """Simple deterministic close-to-close executor (no slippage/fees)."""

    def __init__(self, initial_cash: float = 10_000.0):
        self.initial_cash = initial_cash

    def run(self, candles: Iterable[Candle], strategy: Strategy) -> BacktestResult:
        candle_list = list(candles)
        if len(candle_list) < 2:
            return BacktestResult(0.0, 0, 0.0, self.initial_cash)

        equity = self.initial_cash
        position = 0
        trades = 0
        wins = 0

        for i in range(1, len(candle_list)):
            prev_close = float(candle_list[i - 1].close)
            curr_close = float(candle_list[i].close)

            target_position = strategy.on_candle(candle_list[i - 1])
            if target_position != position:
                trades += 1
                position = target_position

            ret = (curr_close - prev_close) / prev_close
            pnl = equity * position * ret
            if pnl > 0:
                wins += 1
            equity += pnl

        total_return_pct = ((equity / self.initial_cash) - 1.0) * 100.0
        win_rate_pct = (wins / max(1, len(candle_list) - 1)) * 100.0
        return BacktestResult(total_return_pct=total_return_pct, trades=trades, win_rate_pct=win_rate_pct, final_equity=equity)


def run_local_backtest(symbol: str, interval: str, limit: int | None, short_window: int, long_window: int) -> BacktestResult:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    repository = CandleRepository(db_url=db_url)
    candles = repository.get_candles(symbol=symbol, interval=interval, limit=limit)
    strategy = SmaCrossoverStrategy(short_window=short_window, long_window=long_window)
    engine = SimulatedExecutionModel()
    return engine.run(candles, strategy)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic local candle replay backtest")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--long-window", type=int, default=20)
    args = parser.parse_args()

    result = run_local_backtest(
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
        short_window=args.short_window,
        long_window=args.long_window,
    )

    print("=== Local Backtest Summary ===")
    print(f"Total Return: {result.total_return_pct:.2f}%")
    print(f"Trades: {result.trades}")
    print(f"Win Rate: {result.win_rate_pct:.2f}%")
    print(f"Final Equity: {result.final_equity:.2f}")


if __name__ == "__main__":
    main()
