"""Generic cross-sectional long-short portfolio harness (relative-value).

Strategy-agnostic backtester for any signal that ranks a symbol cross-section.
The caller supplies the FIELD to rank on; the harness handles universe-as-of
selection, rebalancing cadence, smoothing, dollar-neutral weighting, turnover
costs, optional funding (carry) income, capital-utilization haircut, and
realized market-beta measurement.

Reused as-is for:
  * funding dispersion   (signal_field="funding_rate", rank ascending → long low)
  * cross-sectional momentum (precompute a trailing-return field, rank descending)
  * OI-based tilts       (signal_field="open_interest" or a derived divergence)

Leakage control: a rebalance at bar i ranks on the smoothed signal observed
through bar i and on the as-of universe at i; the resulting weights are applied
to returns from bar i+1 onward. Nothing at i reads rows > i.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.panel import Panel


@dataclass(frozen=True)
class PortfolioResult:
    times: list                       # times aligned to returns_on_capital
    returns_on_capital: list[float]
    basket_price_returns: list[float]  # price-only leg return (for beta)
    market_returns: list[float]
    turnover_series: list[float]
    total_cost: float
    realized_beta: float
    rebalance_count: int
    avg_active_names: float
    capital_utilization: float


def _smoothed_signal(panel: Panel, field: str, i: int, symbol: str, smoothing: int) -> float | None:
    vals = panel.trailing(field, i, symbol, smoothing)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _beta(y: list[float], x: list[float]) -> float:
    n = min(len(y), len(x))
    if n < 2:
        return 0.0
    mx = sum(x[:n]) / n
    my = sum(y[:n]) / n
    var = sum((x[k] - mx) ** 2 for k in range(n))
    if var == 0:
        return 0.0
    cov = sum((x[k] - mx) * (y[k] - my) for k in range(n))
    return cov / var


def run_cross_sectional_long_short(
    panel: Panel,
    universe_per_time: list[set[str]],
    *,
    signal_field: str,
    rank_ascending_is_long: bool = True,   # long the lowest signal (e.g. lowest funding)
    return_field: str = "close",
    rebalance_every_bars: int = 21,        # weekly on 8h bars (3*7)
    top_k: int = 5,
    smoothing_bars: int = 3,
    per_leg_cost: float = 0.0017,
    capital_utilization: float = 0.5,
    include_funding_income: bool = True,
    funding_field: str = "funding_rate",
    market_symbol: str = "BTCUSDT",
    cost_multiplier: float = 1.0,
) -> PortfolioResult:
    leg_cost = per_leg_cost * cost_multiplier
    n = len(panel.times)
    weights: dict[str, float] = {}

    out_times, r_cap, r_price, r_mkt, turnover_series = [], [], [], [], []
    total_cost = 0.0
    rebalance_count = 0
    active_counts: list[int] = []

    def _rebalance(i: int) -> dict[str, float]:
        uni = universe_per_time[i]
        scored = []
        for s in uni:
            v = _smoothed_signal(panel, signal_field, i, s, smoothing_bars)
            if v is not None:
                scored.append((s, v))
        if len(scored) < 2 * top_k:
            return {}
        scored.sort(key=lambda kv: kv[1])
        low_names = [s for s, _ in scored[:top_k]]    # lowest signal
        high_names = [s for s, _ in scored[-top_k:]]  # highest signal
        longs = low_names if rank_ascending_is_long else high_names
        shorts = high_names if rank_ascending_is_long else low_names
        w = {}
        for s in longs:
            w[s] = 0.5 / top_k        # gross exposure 1.0 (0.5 long + 0.5 short)
        for s in shorts:
            w[s] = -0.5 / top_k
        return w

    for i in range(1, n):
        # Rebalance decision uses bar i-1's info (signal + universe), applied to
        # bar i's return — leakage-free, mirroring the engine's next-bar fill.
        is_rebalance = (i - 1) % rebalance_every_bars == 0
        if is_rebalance:
            new_w = _rebalance(i - 1)
            if new_w:
                turnover = sum(abs(new_w.get(s, 0.0) - weights.get(s, 0.0))
                               for s in set(new_w) | set(weights))
                cost = turnover * leg_cost
                total_cost += cost * capital_utilization
                turnover_series.append(turnover)
                weights = new_w
                rebalance_count += 1
            else:
                cost = 0.0
        else:
            cost = 0.0

        # Per-bar price PnL + optional funding income on held weights.
        price_pnl = 0.0
        funding_income = 0.0
        active = 0
        for s, w in weights.items():
            p1 = panel.value(return_field, i - 1, s)
            p2 = panel.value(return_field, i, s)
            if p1 and p2 and p1 > 0:
                price_pnl += w * (p2 / p1 - 1.0)
                active += 1
            if include_funding_income:
                f = panel.value(funding_field, i, s)
                if f is not None:
                    funding_income += -w * f   # long pays funding>0; short receives

        gross = price_pnl + funding_income
        net_on_capital = (gross - cost) * capital_utilization

        # Market proxy return for beta.
        m1 = panel.value(return_field, i - 1, market_symbol)
        m2 = panel.value(return_field, i, market_symbol)
        mkt = (m2 / m1 - 1.0) if (m1 and m2 and m1 > 0) else 0.0

        out_times.append(panel.times[i])
        r_cap.append(net_on_capital)
        r_price.append(price_pnl)
        r_mkt.append(mkt)
        active_counts.append(active)

    return PortfolioResult(
        times=out_times,
        returns_on_capital=r_cap,
        basket_price_returns=r_price,
        market_returns=r_mkt,
        turnover_series=turnover_series,
        total_cost=total_cost,
        realized_beta=_beta(r_price, r_mkt),
        rebalance_count=rebalance_count,
        avg_active_names=(sum(active_counts) / len(active_counts)) if active_counts else 0.0,
        capital_utilization=capital_utilization,
    )
