#!/usr/bin/env python3
"""Funding Carry — full v2 validation and holdout verdict on REAL Binance data.

Runs entirely in memory (no database): fetches native 8h klines and funding-rate
history from Binance public REST, joins funding as-of each bar, then:

  1. Splits into research region (< HOLDOUT_START) and holdout (>= HOLDOUT_START).
  2. Walk-forward over a small PRE-REGISTERED parameter grid on the research
     region; selects the best config by average test Sharpe.
  3. Statistical significance (t-stat, Deflated Sharpe at trial_count, block
     bootstrap) on the research-region full run of the selected config.
  4. Cost-robustness stress at 1.0x / 1.5x / 2.0x.
  5. Opens the HOLDOUT EXACTLY ONCE for the selected config and records the
     out-of-sample result.

Prints a JSON verdict bundle. The holdout is touched only in step 5.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

from app.backtest import (
    Candle,
    DatasetFingerprint,
    SimulatedExecutionModel,
    build_dataset_fingerprint,
    build_execution_config,
    build_risk_config,
    build_strategy,
)
from app.funding import align_funding_to_candles, parse_funding_payload
from app.significance import significance_check
from app.walk_forward import RESEARCH_RISK_DEFAULTS, run_walk_forward_backtest

SYMBOL = "BTCUSDT"
INTERVAL = "8h"
RESEARCH_START = datetime(2021, 6, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2025, 6, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 6, 1, tzinfo=timezone.utc)

# Pre-registered parameter grid. 6 trials → DSR trial_count = 6.
GRID = [
    {"entry_threshold": t, "smoothing_window": s, "oi_crowding_mult": 0.0, "oi_window": 14}
    for t in (0.00005, 0.0001, 0.0002)
    for s in (1, 3)
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (SharkBay funding carry verdict)"}
FAPI_KLINES = "https://fapi.binance.com/fapi/v1/klines"
FAPI_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"


def _get(url: str, params: dict) -> list:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{q}", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_klines(symbol: str, interval: str, start: datetime, end: datetime) -> list[Candle]:
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    out: list[Candle] = []
    cursor = start_ms
    while cursor < end_ms:
        page = _get(FAPI_KLINES, {"symbol": symbol, "interval": interval,
                                  "startTime": cursor, "endTime": end_ms, "limit": 1500})
        if not page:
            break
        for row in page:
            open_ms = int(row[0])
            if open_ms >= end_ms:
                continue
            out.append(Candle(
                symbol=symbol,
                open_time=datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc),
                close=Decimal(str(row[4])), open=Decimal(str(row[1])),
                high=Decimal(str(row[2])), low=Decimal(str(row[3])),
                volume=Decimal(str(row[5])),
            ))
        if len(page) < 1500:
            break
        cursor = int(page[-1][0]) + 1
    # de-dup
    seen = {}
    for c in out:
        seen[c.open_time] = c
    return [seen[k] for k in sorted(seen)]


def fetch_funding(symbol: str, start: datetime, end: datetime):
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    raw: list = []
    cursor = start_ms
    while cursor < end_ms:
        page = _get(FAPI_FUNDING, {"symbol": symbol, "startTime": cursor,
                                   "endTime": end_ms, "limit": 1000})
        if not page:
            break
        raw.extend(page)
        if len(page) < 1000:
            break
        cursor = int(page[-1]["fundingTime"]) + 1
    return parse_funding_payload(raw)


def full_run(candles: list[Candle], params: dict, cost_multiplier: float = 1.0):
    strat = build_strategy("funding_carry", dict(params))
    exec_cfg = build_execution_config({"cost_multiplier": cost_multiplier})
    engine = SimulatedExecutionModel(
        execution_config=exec_cfg,
        risk_config=build_risk_config(RESEARCH_RISK_DEFAULTS),
        interval=INTERVAL,
    )
    return engine.run(candles, strat, "verdict", build_dataset_fingerprint(candles))


def main() -> int:
    print("Fetching real Binance data (8h klines + funding)...", flush=True)
    candles = fetch_klines(SYMBOL, INTERVAL, RESEARCH_START, HOLDOUT_END)
    funding = fetch_funding(SYMBOL, RESEARCH_START, HOLDOUT_END)
    candles = align_funding_to_candles(candles, funding)
    have_funding = sum(1 for c in candles if c.funding_rate is not None)
    print(f"  {len(candles)} 8h bars, {len(funding)} funding settlements, "
          f"{have_funding} bars with funding attached", flush=True)

    research = [c for c in candles if c.open_time < HOLDOUT_START]
    holdout = [c for c in candles if HOLDOUT_START <= c.open_time < HOLDOUT_END]
    print(f"  research region: {len(research)} bars, holdout: {len(holdout)} bars", flush=True)

    # --- Walk-forward grid on research region (no holdout touched) ---
    wf_results = []
    for params in GRID:
        wf = run_walk_forward_backtest(
            strategy="funding_carry", symbol=SYMBOL, interval=INTERVAL,
            start=RESEARCH_START, end=HOLDOUT_START,
            train_days=180, validation_days=30, test_days=30, step_days=30,
            params=params, candles=research,
        )
        agg = wf["aggregate"]
        wf_results.append((params, agg))
        print(f"  WF {params}: test_sharpe={agg['avg_test_sharpe']:.3f} "
              f"pos_frac={agg['positive_test_window_fraction']:.2f} "
              f"status={agg['pass_fail_status']} windows={wf['evaluable_window_count']}", flush=True)

    best_params, best_agg = max(wf_results, key=lambda x: x[1]["avg_test_sharpe"])

    # --- Significance on research-region full run of the selected config ---
    res_run = full_run(research, best_params, 1.0)
    res_returns = [(p2.equity / p1.equity - 1.0)
                   for p1, p2 in zip(res_run.equity_curve, res_run.equity_curve[1:])]
    sig_metrics = {
        "average_trade_return": res_run.average_trade_return_pct,
        "trade_return_std": res_run.trade_return_std_pct,
        "trade_count": res_run.trades,
        "sharpe": res_run.sharpe,
        "avg_test_sharpe": best_agg["avg_test_sharpe"],
    }
    significance = significance_check(sig_metrics, trial_count=len(GRID), bar_returns=res_returns)

    # --- Cost robustness stress ---
    stress = {}
    for mult in (1.0, 1.5, 2.0):
        r = full_run(research, best_params, mult)
        stress[f"{mult}x"] = {
            "total_return_pct": round(r.total_return_pct, 4),
            "sharpe": round(r.sharpe, 4),
            "trades": r.trades,
        }

    # --- HOLDOUT: opened exactly once ---
    print("Opening holdout (one-shot)...", flush=True)
    holdout_run = full_run(holdout, best_params, 1.0)
    holdout_result = {
        "total_return_pct": round(holdout_run.total_return_pct, 4),
        "sharpe": round(holdout_run.sharpe, 4),
        "trades": holdout_run.trades,
        "win_rate_pct": round(holdout_run.win_rate_pct, 2),
        "max_drawdown_pct": round(holdout_run.max_drawdown_pct, 4),
        "bars": len(holdout),
    }

    # --- Verdict logic ---
    wf_pass = best_agg["pass_fail_status"] == "pass"
    sig_pass = significance["pass"]
    cost_robust = stress["1.5x"]["sharpe"] > 0 and stress["2.0x"]["sharpe"] > 0
    holdout_pass = holdout_run.sharpe > 0 and holdout_run.total_return_pct > 0
    overall = "PASS" if (wf_pass and sig_pass and cost_robust and holdout_pass) else "FAIL"

    bundle = {
        "symbol": SYMBOL, "interval": INTERVAL,
        "research_region": {"start": RESEARCH_START.isoformat(), "end": HOLDOUT_START.isoformat(), "bars": len(research)},
        "holdout": {"start": HOLDOUT_START.isoformat(), "end": HOLDOUT_END.isoformat(), "bars": len(holdout)},
        "grid_size_trials": len(GRID),
        "selected_params": best_params,
        "walk_forward_aggregate": best_agg,
        "significance": significance,
        "cost_stress": stress,
        "holdout_result": holdout_result,
        "gate_results": {
            "walk_forward_pass": wf_pass,
            "significance_pass": sig_pass,
            "cost_robust_1.5x_2x": cost_robust,
            "holdout_pass": holdout_pass,
        },
        "verdict": overall,
    }
    print("\n===== VERDICT BUNDLE =====")
    print(json.dumps(bundle, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
