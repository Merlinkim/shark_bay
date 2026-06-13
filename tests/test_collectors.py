"""Durable collector parsing — pure functions, no network/DB required."""
from datetime import timezone

from app.collectors import parse_liquidation_msg


def test_parse_liquidation_msg_direct():
    msg = {"o": {"s": "BTCUSDT", "T": 1700000000000, "S": "SELL",
                 "p": "42000.0", "q": "1.5", "ap": "41950.0", "X": "FILLED"}}
    row = parse_liquidation_msg(msg)
    assert row["symbol"] == "BTCUSDT"
    assert row["side"] == "SELL"          # SELL = a long position was liquidated
    assert row["price"] == "42000.0"
    assert row["quantity"] == "1.5"
    assert row["event_time"].tzinfo == timezone.utc
    assert row["event_time"].year == 2023


def test_parse_liquidation_msg_combined_stream_envelope():
    msg = {"stream": "!forceOrder@arr",
           "data": {"o": {"s": "ETHUSDT", "T": 1700000001000, "S": "BUY",
                          "p": "2200.0", "q": "10", "ap": "2205.0", "X": "FILLED"}}}
    row = parse_liquidation_msg(msg)
    assert row["symbol"] == "ETHUSDT"
    assert row["side"] == "BUY"            # BUY = a short position was liquidated


def test_parse_liquidation_msg_garbage_returns_none():
    assert parse_liquidation_msg({}) is None
    assert parse_liquidation_msg({"x": 1}) is None
