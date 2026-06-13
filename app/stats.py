"""Shared statistical helpers for backtest metrics (Engine v2)."""
from __future__ import annotations

import math

# Bars per year for 24/7 crypto markets. Annualization factor is sqrt(bars/year).
BARS_PER_YEAR: dict[str, float] = {
    "1m": 365.0 * 24.0 * 60.0,  # 525,600
    "5m": 365.0 * 24.0 * 12.0,
    "15m": 365.0 * 24.0 * 4.0,
    "1h": 365.0 * 24.0,         # 8,760
    "4h": 365.0 * 6.0,          # 2,190
    "8h": 365.0 * 3.0,          # 1,095 — funding settlement cadence
    "1d": 365.0,
}


def annualized_sharpe(returns: list[float], interval: str = "1m") -> float:
    """Annualized Sharpe ratio of a per-bar strategy return series.

    The series must cover every bar of the evaluated period, including 0.0
    returns for bars where the strategy was flat, so that exposure is priced in.
    Uses population standard deviation. Risk-free rate is assumed 0.
    """
    if interval not in BARS_PER_YEAR:
        raise ValueError(f"Unsupported interval for annualization: {interval}")
    n = len(returns)
    if n < 2:
        return 0.0
    avg = sum(returns) / n
    variance = sum((r - avg) ** 2 for r in returns) / n
    sd = math.sqrt(variance)
    if sd == 0.0:
        return 0.0
    return (avg / sd) * math.sqrt(BARS_PER_YEAR[interval])
