import unittest
from datetime import timezone

from app.main import ms_to_dt, parse_kline, parse_symbols, build_combined_stream_url


class TestMain(unittest.TestCase):
    def test_ms_to_dt(self):
        dt = ms_to_dt(0)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 1970)

    def test_parse_kline(self):
        raw = [1700000000000, "35000.10", "35100.10", "34900.10", "35050.10", "123.45", 1700000059999, "0", 1234, "60.1", "2100000.12", "0"]
        parsed = parse_kline("BTCUSDT", raw)
        self.assertEqual(parsed["symbol"], "BTCUSDT")
        self.assertEqual(parsed["trades"], 1234)
        self.assertEqual(str(parsed["open"]), "35000.10")

    def test_parse_symbols(self):
        self.assertEqual(parse_symbols("btcusdt, ethusdt,SOLUSDT"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    def test_combined_stream_url(self):
        self.assertEqual(build_combined_stream_url(["BTCUSDT", "ETHUSDT"]), "/stream?streams=btcusdt@kline_1m/ethusdt@kline_1m")


if __name__ == "__main__":
    unittest.main()
