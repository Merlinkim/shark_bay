#!/usr/bin/env python3
"""Cross-Sectional Funding Dispersion — full deployability verdict on real data.

Uses the generic panel + as-of universe + cross-sectional long-short harness.
Design constraints fixed by Phase 0: WEEKLY rebalance, funding SMOOTHING, as-of
survivorship-controlled universe.

Pipeline:
  1. Fetch klines (8h) + funding for a multi-symbol universe, 2021-01 → 2026-06.
  2. Build the generic panel; build the as-of universe (listing age + liquidity).
  3. Research region (< HOLDOUT_START): run the harness; walk-forward (slice the
     basket return series by test windows), significance, residual beta, cost
     stress.
  4. Holdout opened ONCE — only if research-region pre-holdout gates pass.
  5. Classify PASS / WATCH / FAIL with the 4%/yr deployability floor and a
     neutrality gate. STOP (no holdout) if research invalidates Phase 0.
"""
from __future__ import annotations

import json
import statistics
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

from app.backtest import Candle
from app.dataset_splits import generate_walk_forward_windows
from app.panel import as_of_universe, build_panel
from app.portfolio import run_cross_sectional_long_short
from app.significance import significance_check
from app.stats import annualized_sharpe

INTERVAL = "8h"
BPY = 1095.0
RESEARCH_START = datetime(2021, 1, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2025, 6, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 6, 1, tzinfo=timezone.utc)

UNIVERSE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT",
            "MATICUSDT", "DOTUSDT", "LTCUSDT", "LINKUSDT", "AVAXUSDT", "ATOMUSDT", "UNIUSDT",
            "BCHUSDT", "ETCUSDT", "FILUSDT", "TRXUSDT", "EOSUSDT", "XLMUSDT", "AAVEUSDT",
            "NEARUSDT", "APTUSDT", "ARBUSDT"]

# Pre-registered config (Phase 0 design constraints).
REBALANCE_BARS = 21        # weekly on 8h bars
TOP_K = 5
SMOOTHING = 3
PER_LEG_COST = 0.0017      # 17 bps alt-realistic
CAP_UTIL = 0.5
TRIAL_COUNT = 6            # cadence x smoothing variants considered in Phase 0
DEPLOY_FLOOR = 4.0         # %/yr net on capital
BETA_GATE = 0.20           # |realized beta| must be below this to call it neutral

_H = {"User-Agent": "Mozilla/5.0 (SharkBay xsectional verdict)"}


def _get(url, params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return json.load(urllib.request.urlopen(urllib.request.Request(f"{url}?{q}", headers=_H), timeout=30))


def _fetch_klines(symbol, start, end):
    s, e = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    out, cur = {}, s
    while cur < e:
        page = _get("https://fapi.binance.com/fapi/v1/klines",
                    {"symbol": symbol, "interval": INTERVAL, "startTime": cur, "endTime": e, "limit": 1000})
        if not page:
            break
        for row in page:
            t = int(row[0])
            if t < e:
                out[t] = (Decimal(str(row[4])), Decimal(str(row[5])))  # close, volume
        if len(page) < 1000:
            break
        cur = int(page[-1][0]) + 1
    return out


def _fetch_funding(symbol, start, end):
    s, e = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    out, cur = {}, s
    while cur < e:
        page = _get("https://fapi.binance.com/fapi/v1/fundingRate",
                    {"symbol": symbol, "startTime": cur, "endTime": e, "limit": 1000})
        if not page:
            break
        for x in page:
            out[int(x["fundingTime"])] = Decimal(str(x["fundingRate"]))
        if len(page) < 1000:
            break
        cur = int(page[-1]["fundingTime"]) + 1
    return out


def _build_series(symbol):
    kl = _fetch_klines(symbol, RESEARCH_START, HOLDOUT_END)
    fr = _fetch_funding(symbol, RESEARCH_START, HOLDOUT_END)
    candles = []
    for t in sorted(kl):
        close, vol = kl[t]
        ot = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        candles.append(Candle(symbol=symbol, open_time=ot, close=close, open=close,
                              high=close, low=close, volume=vol,
                              funding_rate=fr.get(t)))
    return candles


def _ann_return(rets):
    return statistics.mean(rets) * BPY * 100 if rets else 0.0


def _walk_forward_on_series(times, rets):
    windows = generate_walk_forward_windows(
        RESEARCH_START, HOLDOUT_START, train_days=180, validation_days=30, test_days=30, step_days=30)
    idx = {t: i for i, t in enumerate(times)}
    test_sharpes = []
    for w in windows:
        seg = [rets[idx[t]] for t in times if w.test.start <= t <= w.test.end]
        if len(seg) < 10:
            continue
        test_sharpes.append(annualized_sharpe(seg, INTERVAL))
    if not test_sharpes:
        return {"windows": 0, "avg_test_sharpe": 0.0, "positive_window_fraction": 0.0, "pass": False}
    pos = sum(1 for s in test_sharpes if s > 0) / len(test_sharpes)
    avg = statistics.mean(test_sharpes)
    return {"windows": len(test_sharpes), "avg_test_sharpe": avg,
            "positive_window_fraction": pos, "pass": avg > 0 and pos >= 0.6}


def main() -> int:
    print(f"Fetching universe ({len(UNIVERSE)} symbols): klines + funding...", flush=True)
    series = {}
    for sym in UNIVERSE:
        c = _build_series(sym)
        if c:
            series[sym] = c
    print(f"  fetched {len(series)} symbols", flush=True)

    panel = build_panel(series, ["close", "volume", "funding_rate"])
    universe = as_of_universe(panel, min_history_bars=90, min_avg_dollar_volume=5_000_000.0, volume_lookback=30)
    avg_uni = statistics.mean(len(u) for u in universe[90:]) if len(universe) > 90 else 0
    print(f"  panel: {len(panel.times)} bars, avg eligible universe ~{avg_uni:.0f} names", flush=True)

    def run(region_end, region_start=RESEARCH_START, cost_mult=1.0, util=CAP_UTIL):
        res = run_cross_sectional_long_short(
            panel, universe, signal_field="funding_rate", rank_ascending_is_long=True,
            rebalance_every_bars=REBALANCE_BARS, top_k=TOP_K, smoothing_bars=SMOOTHING,
            per_leg_cost=PER_LEG_COST, capital_utilization=util, include_funding_income=True,
            cost_multiplier=cost_mult)
        # restrict to region
        pairs = [(t, r) for t, r in zip(res.times, res.returns_on_capital) if region_start <= t < region_end]
        return res, [t for t, _ in pairs], [r for _, r in pairs]

    # --- Research region ---
    res_full, res_times, res_rets = run(HOLDOUT_START)
    wf = _walk_forward_on_series(res_times, res_rets)
    sig = significance_check(
        {"average_trade_return": statistics.mean(res_rets) * 100,
         "trade_return_std": statistics.pstdev(res_rets) * 100,
         "trade_count": len(res_rets),
         "sharpe": annualized_sharpe(res_rets, INTERVAL),
         "avg_test_sharpe": wf["avg_test_sharpe"]},
        trial_count=TRIAL_COUNT, bar_returns=res_rets)

    stress = {}
    for m in (1.0, 1.5, 2.0):
        _, _, rr = run(HOLDOUT_START, cost_mult=m)
        stress[f"cost_{m}x"] = round(_ann_return(rr), 3)
    _, _, rr33 = run(HOLDOUT_START, util=0.33)
    stress["util_0.33"] = round(_ann_return(rr33), 3)

    research = {
        "ann_return_on_capital_pct": round(_ann_return(res_rets), 3),
        "ann_sharpe": round(annualized_sharpe(res_rets, INTERVAL), 3),
        "realized_beta": round(res_full.realized_beta, 4),
        "rebalances": res_full.rebalance_count,
        "avg_active_names": round(res_full.avg_active_names, 1),
        "n_bars": len(res_rets),
    }
    print("\n--- RESEARCH-REGION RESULT ---")
    print(json.dumps({"research": research, "walk_forward": wf,
                      "significance_pass": sig["pass"], "significance": sig["gates"],
                      "cost_margin_stress": stress}, indent=2, default=str))

    pre_holdout_pass = wf["pass"] and sig["pass"] and abs(res_full.realized_beta) < BETA_GATE
    invalidates_phase0 = research["ann_return_on_capital_pct"] <= 0

    bundle = {"research": research, "walk_forward": wf, "significance": sig,
              "cost_margin_stress": stress, "pre_holdout_pass": pre_holdout_pass}

    if invalidates_phase0 or not pre_holdout_pass:
        bundle["holdout"] = "NOT OPENED — research-region gates failed (stop condition)"
        bundle["verdict"] = "FAIL"
        print("\n===== VERDICT: FAIL (holdout not opened) =====")
        print(json.dumps(bundle, indent=2, default=str))
        return 0

    # --- Holdout: opened once ---
    print("\nResearch gates passed. Opening holdout (one-shot)...", flush=True)
    _, h_times, h_rets = run(HOLDOUT_END, region_start=HOLDOUT_START)
    _, _, h_rets_15 = run(HOLDOUT_END, region_start=HOLDOUT_START, cost_mult=1.5)
    holdout_ann = _ann_return(h_rets)
    holdout = {
        "window": f"{HOLDOUT_START.date()}..{HOLDOUT_END.date()}",
        "n_bars": len(h_rets),
        "ann_return_on_capital_pct": round(holdout_ann, 3),
        "ann_return_on_capital_pct_1.5x": round(_ann_return(h_rets_15), 3),
        "ann_sharpe": round(annualized_sharpe(h_rets, INTERVAL), 3),
    }
    gates = {
        "walk_forward_pass": wf["pass"],
        "significance_pass": sig["pass"],
        "neutrality_pass": abs(res_full.realized_beta) < BETA_GATE,
        "holdout_positive": holdout_ann > 0,
        "holdout_meets_floor": holdout_ann >= DEPLOY_FLOOR,
        "holdout_cost_robust_1.5x": _ann_return(h_rets_15) > 0,
    }
    if not (gates["holdout_positive"] and gates["neutrality_pass"]):
        verdict = "FAIL"
    elif gates["holdout_meets_floor"] and gates["holdout_cost_robust_1.5x"]:
        verdict = "PASS"
    else:
        verdict = "WATCH"

    bundle["holdout"] = holdout
    bundle["gate_results"] = gates
    bundle["verdict"] = verdict
    print("\n===== CROSS-SECTIONAL FUNDING VERDICT =====")
    print(json.dumps(bundle, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
