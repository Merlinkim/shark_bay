import io
import zipfile
from argparse import Namespace

from app import historical_import


def _zip_bytes(csv_text: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sample.csv", csv_text)
    return out.getvalue()


def test_build_url():
    url = historical_import.build_url("BTCUSDT", "1m", "2024-01")
    assert url.endswith("/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip")


def test_parse_zip_rows():
    rows = list(historical_import.parse_zip_rows(_zip_bytes("1,2,3\n4,5,6\n")))
    assert rows == [["1", "2", "3"], ["4", "5", "6"]]


def test_missing_file_handling(monkeypatch):
    class R:
        status_code = 404
        content = b""

        def raise_for_status(self):
            return None

    monkeypatch.setattr(historical_import.requests, "get", lambda *a, **k: R())
    summary = historical_import.run_import(
        Namespace(symbol="BTCUSDT", interval="1m", months=1, start_month="2020-01", end_month="2020-01", dry_run=True, max_months=None, sleep_seconds=0.0, skip_existing=False, run_quality_check=False)
    )
    assert summary.missing_months == ["2020-01"]


def test_dry_run_behavior(monkeypatch):
    csv = "1713744000000,65000,65100,64900,65010,1,1713744059999,0,10,0.5,32500,0\n"

    class R:
        status_code = 200
        content = _zip_bytes(csv)

        def raise_for_status(self):
            return None

    monkeypatch.setattr(historical_import.requests, "get", lambda *a, **k: R())
    summary = historical_import.run_import(
        Namespace(symbol="BTCUSDT", interval="1m", months=1, start_month="2020-01", end_month="2020-01", dry_run=True, max_months=None, sleep_seconds=0.0, skip_existing=False, run_quality_check=False)
    )
    assert summary.imported_rows == 1
    assert summary.upserted_rows == 0
