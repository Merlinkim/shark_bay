from app import rest_backfill


def test_parse_utc_to_ms_and_back():
    ms = rest_backfill.parse_utc_to_ms("2026-05-01T00:00:00Z")
    assert ms == 1777593600000
    assert rest_backfill.ms_to_utc(ms).isoformat() == "2026-05-01T00:00:00+00:00"


def test_pagination_advances_windows(monkeypatch):
    calls = []

    def fake_fetch(**kwargs):
        calls.append(kwargs["start_time_ms"])
        if len(calls) == 1:
            return [
                [1777593600000, "1", "2", "0.5", "1.5", "10", 1777593659999, "0", 1, "0", "0", "0"],
                [1777593660000, "1", "2", "0.5", "1.5", "10", 1777593719999, "0", 1, "0", "0", "0"],
            ]
        return []

    monkeypatch.setattr(rest_backfill, "fetch_klines_page", fake_fetch)
    summary = rest_backfill.run_rest_backfill(
        symbol="BTCUSDT", interval="1m", start="2026-05-01T00:00:00Z", end="2026-05-01T00:03:00Z", dry_run=True, sleep_seconds=0
    )

    assert summary.fetched_rows == 2
    assert calls == [1777593600000, 1777593720000]


def test_dry_run_no_db_write(monkeypatch):
    monkeypatch.setattr(
        rest_backfill,
        "fetch_klines_page",
        lambda **kwargs: [[1777593600000, "1", "2", "0.5", "1.5", "10", 1777593659999, "0", 1, "0", "0", "0"]],
    )

    summary = rest_backfill.run_rest_backfill(
        symbol="BTCUSDT", interval="1m", start="2026-05-01T00:00:00Z", end="2026-05-01T00:01:00Z", dry_run=True, sleep_seconds=0
    )
    assert summary.upserted_rows == 0


def test_empty_api_response(monkeypatch):
    monkeypatch.setattr(rest_backfill, "fetch_klines_page", lambda **kwargs: [])
    summary = rest_backfill.run_rest_backfill(
        symbol="BTCUSDT", interval="1m", start="2026-05-01T00:00:00Z", end="2026-05-01T00:02:00Z", dry_run=True, sleep_seconds=0
    )
    assert summary.api_requests == 1
    assert summary.fetched_rows == 0
