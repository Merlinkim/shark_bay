# Production Data Audit — Run & Interpretation Guide

Tool: `tools/audit_production_data.py`. **Strictly read-only** — it forces
`default_transaction_read_only = on` on its DB session and issues only SELECTs, so
it cannot mutate production data. It does not start collectors or run research.

## Exact commands (run on the VPS / Mac Mini, where DATABASE_URL points at prod)

Full audit, two core symbols, with funding + Binance fidelity (spot source):
```
DATABASE_URL=postgresql://USER:PASS@HOST:5432/DB \
python -m tools.audit_production_data \
  --symbols BTCUSDT,ETHUSDT \
  --start 2021-01-01 --end 2026-06-01 \
  --funding --sample-size 300 --resample-interval 8h \
  --out-json audit.json --out-md audit.md
```

All symbols, DB-only (no network) — fast structural pass:
```
DATABASE_URL=... python -m tools.audit_production_data \
  --symbols all --start 2021-01-01 --end 2026-06-01 --funding --no-network \
  --out-json audit_all.json --out-md audit_all.md
```

If the production candles are **futures** (not spot), point fidelity at fapi:
```
... --binance-klines https://fapi.binance.com/fapi/v1/klines
```
(Default is spot `api.binance.com/api/v3/klines`, matching `rest_backfill.py`.)

## Output format

Two files plus stdout:
- **JSON** (`--out-json`): machine-readable; `overall_severity` + a `symbols[]`
  array, each a full `SymbolAudit` (row counts, missing ranges, dup count,
  monotonic flag, invalid OHLC/volume counts, funding alignment, fidelity and
  resample mismatch counts/rates, per-symbol `severity`).
- **Markdown** (`--out-md`): a per-symbol table for human review.
- stdout ends with `OVERALL SEVERITY: <level>`.

## Severity scale & interpretation

| Level | Meaning | Action |
|-------|---------|--------|
| NONE | clean on this check | none |
| LOW | a few scattered missing 1m slots (<0.1%) | acceptable (real exchange halts); note it |
| MEDIUM | 0.1–1% missing, or volume/taker anomalies | re-backfill affected ranges before relying on volume/flow research |
| HIGH | dup rows, non-monotonic, any invalid OHLC, funding gaps, or **any** Binance fidelity/resample mismatch | re-ingest affected ranges; do not trust the affected window until fixed |
| CRITICAL | systematic fidelity mismatch (>0.5% of samples) | the DB diverges from source — full re-ingest; treat all DB-derived backtests as suspect until resolved |

Per-check reading:
- **Missing (1) / continuity (3):** clustered gaps = collector outage windows;
  scattered single gaps = normal halts. Check `missing_ranges` for clustering.
- **Duplicates (2):** should be 0 (PK enforces). Non-zero ⇒ schema/ingest breach.
- **OHLC (4):** any non-zero is HIGH — corrupt rows poison intrabar logic.
- **Volume/taker (5):** `taker_buy_base > volume` ⇒ ingest field-mapping bug;
  blocks order-flow research specifically.
- **Funding (6):** `gap_count`/`misaligned_count` > 0 ⇒ funding history unreliable
  (relevant only to funding research, which is already archived).
- **Fidelity (7,10):** the decisive check — a non-zero mismatch rate means the DB
  silently disagrees with Binance. `fidelity_mismatch_rate` is the headline number.
- **Resample (8):** mismatch ⇒ either source rows wrong or the aggregator wrong;
  invalidates all multi-hour-bar research drawn from the DB.

## What a clean result would (and would not) prove

- A clean audit confirms the **production candle DB** is faithful to Binance — it
  validates the *backend engine's* backtest path (orchestrator → CandleRepository).
- It does **not** retroactively change the five research verdicts in this program:
  those were run on **live Binance fetches**, not the production DB, so they were
  never exposed to production-DB risk in the first place. The audit is about
  trusting the DB for *future* DB-backed work, not re-validating past verdicts.

## Tests

`tests/test_audit_tool.py` (11 tests) covers the pure logic — OHLC/volume
predicates, missing-range computation, monotonicity, funding alignment, candle
diffing with tolerance, and severity mapping — with no DB or network. The DB/SQL
and Binance paths are exercised when you run it on the VPS.
