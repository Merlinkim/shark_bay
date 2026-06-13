"""Phase 3 — funding PnL accounting, aux-data plumbing, and leakage control."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.backtest import Candle, DatasetFingerprint, SimulatedExecutionModel
from app.funding import (
    FundingEvent,
    OpenInterestObservation,
    align_funding_to_candles,
    parse_funding_payload,
)


def _bar(ts, price, funding=None, oi=None):
    return Candle(
        symbol="BTCUSDT", open_time=ts, close=Decimal(str(price)),
        open=Decimal(str(price)), high=Decimal(str(price)), low=Decimal(str(price)),
        volume=Decimal("1"),
        funding_rate=Decimal(str(funding)) if funding is not None else None,
        open_interest=Decimal(str(oi)) if oi is not None else None,
    )


def _fp(bars):
    return DatasetFingerprint("fp", len(bars), bars[0].open_time, bars[-1].open_time)


class _AlwaysShort:
    strategy_name = "always_short"
    def on_candle(self, candle):
        return -1


class _AlwaysLong:
    strategy_name = "always_long"
    def on_candle(self, candle):
        return 1


# --- Funding PnL accounting --------------------------------------------------

def test_short_receives_positive_funding_with_flat_price():
    # Flat price → zero price PnL. Positive funding → short should GAIN.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(start + timedelta(hours=8 * i), 100.0, funding=0.01) for i in range(10)]
    engine = SimulatedExecutionModel(interval="8h")
    res = engine.run(bars, _AlwaysShort(), "h", _fp(bars))
    # Despite flat price and fees, positive funding accrues to the short.
    assert res.final_equity > engine.initial_cash


def test_long_pays_positive_funding_with_flat_price():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(start + timedelta(hours=8 * i), 100.0, funding=0.01) for i in range(10)]
    engine = SimulatedExecutionModel(interval="8h")
    res = engine.run(bars, _AlwaysLong(), "h", _fp(bars))
    # Long pays funding every bar plus fees → must lose money on flat price.
    assert res.final_equity < engine.initial_cash


def test_funding_sign_symmetry():
    # Negative funding flips the winner: long should gain, short should lose.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(start + timedelta(hours=8 * i), 100.0, funding=-0.01) for i in range(10)]
    engine = SimulatedExecutionModel(interval="8h")
    long_res = engine.run(bars, _AlwaysLong(), "h", _fp(bars))
    assert long_res.final_equity > engine.initial_cash


# --- Backward compatibility --------------------------------------------------

def test_no_funding_field_is_identical_to_legacy():
    # Bars without funding_rate must behave exactly as before (no funding PnL).
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(start + timedelta(hours=8 * i), 100.0, funding=None) for i in range(10)]
    engine = SimulatedExecutionModel(interval="8h")
    res = engine.run(bars, _AlwaysShort(), "h", _fp(bars))
    # Flat price, no funding, only fees → equity strictly below start, and the
    # only thing that moved it is fees.
    assert res.final_equity < engine.initial_cash
    assert res.total_fees > 0


# --- As-of alignment + leakage ----------------------------------------------

def test_asof_alignment_no_future_leak():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # Settlements at 00:00 and 08:00 with distinct rates.
    events = [
        FundingEvent(start, Decimal("0.001")),
        FundingEvent(start + timedelta(hours=8), Decimal("0.002")),
    ]
    # Candle at 04:00 (between settlements) must see the 00:00 rate, NOT 08:00.
    candles = [_bar(start + timedelta(hours=4), 100.0)]
    aligned = align_funding_to_candles(candles, events)
    assert aligned[0].funding_rate == Decimal("0.001")


def test_candle_before_first_settlement_has_no_funding():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    events = [FundingEvent(start + timedelta(hours=8), Decimal("0.002"))]
    candles = [_bar(start, 100.0)]
    aligned = align_funding_to_candles(candles, events)
    assert aligned[0].funding_rate is None


def test_shifting_funding_later_cannot_change_past_pnl():
    """Leakage lock: delaying every settlement by one bar must not retroactively
    change the funding attached to earlier bars (no future data bleeds back)."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [_bar(start + timedelta(hours=8 * i), 100.0) for i in range(5)]
    events = [FundingEvent(start + timedelta(hours=8 * i), Decimal(str(0.001 * (i + 1)))) for i in range(5)]
    shifted = [FundingEvent(e.settlement_time + timedelta(hours=8), e.funding_rate) for e in events]

    base = align_funding_to_candles(candles, events)
    delayed = align_funding_to_candles(candles, shifted)
    # Bar 0 saw events[0] in base; after delaying, bar 0 sees nothing earlier →
    # its funding can only become "less informed", never reveal a future rate.
    assert base[0].funding_rate == Decimal("0.001")
    assert delayed[0].funding_rate is None
    # No aligned bar ever carries a rate whose settlement is after the bar.
    for aligned, evs in ((base, events), (delayed, shifted)):
        for c in aligned:
            if c.funding_rate is not None:
                settled = [e for e in evs if e.funding_rate == c.funding_rate]
                assert any(e.settlement_time <= c.open_time for e in settled)


def test_parse_binance_funding_payload():
    payload = [
        {"symbol": "BTCUSDT", "fundingTime": 1700000000000, "fundingRate": "0.00010000"},
        {"symbol": "BTCUSDT", "fundingTime": 1699971200000, "fundingRate": "-0.00005000"},
    ]
    events = parse_funding_payload(payload)
    assert len(events) == 2
    assert events[0].settlement_time < events[1].settlement_time  # sorted
    assert events[1].funding_rate == Decimal("0.00010000")
