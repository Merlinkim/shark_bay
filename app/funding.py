"""Funding-rate and open-interest handling for the Funding Carry research program.

Two responsibilities, both leakage-critical:

1. Parse Binance USDⓈ-M futures REST payloads into typed events.
2. Align those events onto a candle timeline with a strict as-of join, so the
   value attached to a bar is only ever what was knowable AT that bar's open.

The as-of rule is the single most important defense against funding look-ahead:
a candle at time T receives the most recent funding settlement with
settlement_time <= T (and the most recent OI observation with ts <= T). It can
never see a future settlement. The engine then charges that funding on the
position carried INTO the next bar, and a strategy may read it to decide a
signal executed at the NEXT bar's open — both leakage-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.backtest import Candle


@dataclass(frozen=True)
class FundingEvent:
    settlement_time: datetime
    funding_rate: Decimal


@dataclass(frozen=True)
class OpenInterestObservation:
    ts: datetime
    open_interest: Decimal


def _ms_to_dt(ms: int | str) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)


def parse_funding_payload(payload: list[dict]) -> list[FundingEvent]:
    """Parse Binance GET /fapi/v1/fundingRate response items."""
    events = [
        FundingEvent(
            settlement_time=_ms_to_dt(item["fundingTime"]),
            funding_rate=Decimal(str(item["fundingRate"])),
        )
        for item in payload
    ]
    events.sort(key=lambda e: e.settlement_time)
    return events


def parse_open_interest_payload(payload: list[dict]) -> list[OpenInterestObservation]:
    """Parse Binance GET /futures/data/openInterestHist response items."""
    obs = [
        OpenInterestObservation(
            ts=_ms_to_dt(item["timestamp"]),
            open_interest=Decimal(str(item["sumOpenInterest"])),
        )
        for item in payload
    ]
    obs.sort(key=lambda o: o.ts)
    return obs


def _asof_index(times: list[datetime], target: datetime) -> int:
    """Index of the latest time <= target, or -1 if none. Bisect on sorted times."""
    lo, hi = 0, len(times)
    while lo < hi:
        mid = (lo + hi) // 2
        if times[mid] <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def align_funding_to_candles(
    candles: list[Candle],
    funding_events: list[FundingEvent],
    open_interest: list[OpenInterestObservation] | None = None,
) -> list[Candle]:
    """Return new candles with funding_rate / open_interest attached as-of open_time.

    STRICT as-of: a candle at time T gets the most recent settlement with
    settlement_time <= T. Candles before the first settlement get funding_rate
    None (the engine then models no funding for them). This function never reads
    a future event for a past bar — that property is what the leakage test locks.
    """
    f_times = [e.settlement_time for e in funding_events]
    oi_times = [o.ts for o in (open_interest or [])]
    out: list[Candle] = []
    for c in candles:
        fr: Decimal | None = None
        fi = _asof_index(f_times, c.open_time)
        if fi >= 0:
            fr = funding_events[fi].funding_rate
        oi: Decimal | None = None
        if oi_times:
            oidx = _asof_index(oi_times, c.open_time)
            if oidx >= 0:
                oi = open_interest[oidx].open_interest
        out.append(
            Candle(
                symbol=c.symbol,
                open_time=c.open_time,
                close=c.close,
                open=c.open,
                high=c.high,
                low=c.low,
                volume=c.volume,
                funding_rate=fr,
                open_interest=oi,
            )
        )
    return out
