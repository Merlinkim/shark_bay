"""Generic multi-symbol panel — reusable relative-value research capability.

This module is deliberately FIELD-AGNOSTIC and STRATEGY-AGNOSTIC. It builds an
aligned cross-section/time-series panel over an arbitrary set of symbols and an
arbitrary set of numeric fields, and provides survivorship- and look-ahead-safe
universe construction. It contains NO funding-specific logic.

It is the shared substrate for the relative-value half of the roadmap:
  * Cross-sectional funding   (field = "funding_rate")
  * Cross-sectional momentum   (field = trailing return derived from "close")
  * Pairs / lead-lag           (field = "close")
  * OI-based research          (field = "open_interest")
  * any future relative-value signal over a symbol cross-section

Look-ahead control: every accessor and the as-of universe builder operate on a
time INDEX i and never read rows > i. Survivorship control: eligibility at time i
depends only on each symbol's own history up to i (listing age + liquidity), so a
symbol that delisted or was illiquid earlier is correctly excluded as-of then.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.backtest import Candle

# Fields are pulled from Candle via these accessors so the panel never hard-codes
# a funding-specific column. Adding a field here is the only change needed to
# support a new relative-value signal.
_FIELD_ACCESSORS = {
    "close": lambda c: float(c.close) if c.close is not None else None,
    "open": lambda c: float(c.open_) if c.close is not None else None,
    "high": lambda c: float(c.high_) if c.close is not None else None,
    "low": lambda c: float(c.low_) if c.close is not None else None,
    "volume": lambda c: float(c.volume) if c.volume is not None else None,
    "funding_rate": lambda c: float(c.funding_rate) if c.funding_rate is not None else None,
    "open_interest": lambda c: float(c.open_interest) if c.open_interest is not None else None,
}


@dataclass(frozen=True)
class Panel:
    times: list[datetime]                       # sorted union grid
    symbols: list[str]
    # data[field] is a list over time index i; each entry maps symbol -> value
    data: dict[str, list[dict[str, float]]]

    def value(self, field: str, i: int, symbol: str) -> float | None:
        return self.data[field][i].get(symbol)

    def cross_section(self, field: str, i: int, universe: set[str] | None = None) -> dict[str, float]:
        """All non-null values of `field` at time i, optionally restricted to a universe."""
        row = self.data[field][i]
        if universe is None:
            return dict(row)
        return {s: v for s, v in row.items() if s in universe}

    def trailing(self, field: str, i: int, symbol: str, lookback: int) -> list[float]:
        """Non-null values of field for symbol over (i-lookback, i], past-only."""
        lo = max(0, i - lookback + 1)
        out = []
        for k in range(lo, i + 1):
            v = self.data[field][k].get(symbol)
            if v is not None:
                out.append(v)
        return out


def build_panel(series: dict[str, list[Candle]], fields: list[str]) -> Panel:
    """Align per-symbol candle series onto a common time grid for the given fields.

    series: symbol -> ascending list of Candle. Times need not match across
    symbols; the panel grid is the sorted union of all open_times (so newly
    listed symbols simply have no values before their first bar).
    """
    for f in fields:
        if f not in _FIELD_ACCESSORS:
            raise ValueError(f"Unknown panel field: {f}")

    all_times = sorted({c.open_time for candles in series.values() for c in candles})
    time_index = {t: i for i, t in enumerate(all_times)}
    symbols = sorted(series.keys())

    data: dict[str, list[dict[str, float]]] = {f: [dict() for _ in all_times] for f in fields}
    for symbol, candles in series.items():
        for c in candles:
            i = time_index[c.open_time]
            for f in fields:
                v = _FIELD_ACCESSORS[f](c)
                if v is not None:
                    data[f][i][symbol] = v
    return Panel(times=all_times, symbols=symbols, data=data)


def as_of_universe(
    panel: Panel,
    *,
    min_history_bars: int,
    min_avg_dollar_volume: float = 0.0,
    volume_lookback: int = 30,
    price_field: str = "close",
    volume_field: str = "volume",
) -> list[set[str]]:
    """Eligible symbol set at each time index, using ONLY past data.

    A symbol is eligible at time i if:
      * it has at least `min_history_bars` non-null price observations up to i
        (listing-age / survivorship guard), and
      * its trailing-`volume_lookback` average dollar volume (price*volume) up to
        i is >= `min_avg_dollar_volume` (liquidity guard).

    Returns a list aligned to panel.times; entry i is the eligible set as-of i.
    This is the survivorship + look-ahead control: nothing about i depends on
    rows > i, and a symbol illiquid/unlisted as-of i is excluded as-of i.
    """
    history_count: dict[str, int] = {s: 0 for s in panel.symbols}
    universe_per_time: list[set[str]] = []
    for i in range(len(panel.times)):
        price_row = panel.data[price_field][i]
        for s in price_row:
            history_count[s] += 1
        eligible: set[str] = set()
        for s in panel.symbols:
            if history_count[s] < min_history_bars:
                continue
            if min_avg_dollar_volume > 0.0:
                prices = panel.trailing(price_field, i, s, volume_lookback)
                vols = panel.trailing(volume_field, i, s, volume_lookback)
                n = min(len(prices), len(vols))
                if n == 0:
                    continue
                adv = sum(prices[-n + k] * vols[-n + k] for k in range(n)) / n
                if adv < min_avg_dollar_volume:
                    continue
            else:
                if price_row.get(s) is None:
                    continue
            eligible.add(s)
        universe_per_time.append(eligible)
    return universe_per_time
