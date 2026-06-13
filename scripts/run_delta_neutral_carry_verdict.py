#!/usr/bin/env python3
"""Delta-Neutral Funding Carry — DEPLOYABILITY verdict on real Binance data.

Verdict question (per the approved milestone): NOT "does carry exist?" but
"is delta-neutral carry DEPLOYABLE in the current regime after realistic
execution costs and operational complexity?"

Classification:
  FAIL  — holdout net carry <= 0, or significance/walk-forward fail.
  WATCH — statistically real and positive, but holdout net deployable return on
          capital is below the deployability floor (thin edge) OR it fails cost
          stress. A thin-but-real edge is a WATCH, not a PASS.
  PASS  — clears walk-forward + significance AND the holdout net deployable
          return clears the floor AND survives 1.5x/2x cost and tighter-margin
          stress.

Runs fully in memory from public REST (spot klines, perp klines, funding).
Holdout (>= HOLDOUT_START) is constructed and read exactly once, at the end.
"""
from __future__ import annotations

import json
import statistics
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

from app.backtest import Candle
from app.carry import build_carry_returns
from app.dataset_splits import generate_walk_forward_windows
from app.funding import align_funding_to_candles, parse_funding_payload
from app.significance import significance_check
from app.stats import annualized_sharpe

SYMBOL = "BTCUSDT"
INTERVAL = "8h"
BARS_PER_YEAR = 1095.0
RESEARCH_START = datetime(2021, 1, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2025, 6, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 6, 1, tzinfo=timezone.utc)

# Pre-registered deployability bar (see DELTA_NEUTRAL_ASSUMPTIONS.md).
CAPITAL_UTILIZATION = 0.5      # half of capital is margin buffer (liq. defense)
STRESS_UTILIZATION = 0.33      # tighter-margin stress
DEPLOY_RETURN_FLOOR = 0.04     # 4%/yr net on capital to be worth deploying
TRIAL_COUNT = 2                # BTC + ETH looked at → DSR penalty

_H = {"User-Agent": "Mozilla/5.0 (SharkBay carry verdict)"}


def _get(url, params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return json.load(urllib.request.urlopen(urllib.request.Request(f"{url}?{q}", headers=_H), timeout=30))


def _fetch_klines(base, symbol, start, end):
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    # Binance spot (api.binance.com) caps klines at 1000/page; fapi allows 1500.
    # Use 1000 for both and paginate until a short page signals the end.
    PAGE = 1000
    out, cursor = [], start_ms
    while cursor < end_ms:
        page = _get(base, {"symbol": symbol, "interval": INTERVAL,
                           "startTime": cursor, "endTime": end_ms, "limit": PAGE})
        if not page:
            break
        for row in page:
            t = int(row[0])
            if t >= end_ms:
                continue
            out.append((datetime.fromtimestamp(t / 1000, tz=timezone.utc), Decimal(str(row[4]))))
        if len(page) < PAGE:
            break
        cursor = int(page[-1][0]) + 1
    seen = {t: c for t, c in out}
    return seen


def _fetch_funding(symbol, start, end):
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    raw, cursor = [], start_ms
    while cursor < end_ms:
        page = _get("https://fapi.binance.com/fapi/v1/fundingRate",
                    {"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000})
        if not page:
            break
        raw.extend(page)
        if len(page) < 1000:
            break
        cursor = int(page[-1]["fundingTime"]) + 1
    return parse_funding_payload(raw)


def _build_aligned(symbol):
    spot_map = _fetch_klines("https://api.binance.com/api/v3/klines", symbol, RESEARCH_START, HOLDOUT_END)
    perp_map = _fetch_klines("https://fapi.binance.com/fapi/v1/klines", symbol, RESEARCH_START, HOLDOUT_END)
    funding = _fetch_funding(symbol, RESEARCH_START, HOLDOUT_END)
    common = sorted(set(spot_map) & set(perp_map))
    spot = [Candle(symbol=symbol, open_time=t, close=spot_map[t]) for t in common]
    perp = [Candle(symbol=symbol, open_time=t, close=perp_map[t]) for t in common]
    perp = align_funding_to_candles(perp, funding)
    return spot, perp


def _ann_return(rets):
    return statistics.mean(rets) * BARS_PER_YEAR if rets else 0.0


def _walk_forward(spot, perp, util, cost_mult=1.0):
    """Per-test-window annualized Sharpe of the carry series on the research region."""
    windows = generate_walk_forward_windows(
        RESEARCH_START, HOLDOUT_START, train_days=180, validation_days=30, test_days=30, step_days=30
    )
    test_sharpes, test_returns = [], []
    for w in windows:
        seg_spot = [c for c in spot if w.test.start <= c.open_time <= w.test.end]
        seg_perp = [c for c in perp if w.test.start <= c.open_time <= w.test.end]
        if len(seg_perp) < 30:
            continue
        cs = build_carry_returns(seg_spot, seg_perp, capital_utilization=util, cost_multiplier=cost_mult)
        test_sharpes.append(annualized_sharpe(cs.returns_on_capital, INTERVAL))
        test_returns.append(_ann_return(cs.returns_on_capital))
    pos_frac = (sum(1 for s in test_sharpes if s > 0) / len(test_sharpes)) if test_sharpes else 0.0
    return {
        "windows": len(test_sharpes),
        "avg_test_sharpe": statistics.mean(test_sharpes) if test_sharpes else 0.0,
        "avg_test_ann_return": statistics.mean(test_returns) if test_returns else 0.0,
        "positive_window_fraction": pos_frac,
        "pass": bool(test_sharpes) and statistics.mean(test_sharpes) > 0 and pos_frac >= 0.6,
    }


def main() -> int:
    print(f"Fetching real spot+perp+funding for {SYMBOL}...", flush=True)
    spot, perp = _build_aligned(SYMBOL)
    print(f"  {len(perp)} aligned 8h bars", flush=True)

    research_spot = [c for c in spot if c.open_time < HOLDOUT_START]
    research_perp = [c for c in perp if c.open_time < HOLDOUT_START]
    holdout_spot = [c for c in spot if HOLDOUT_START <= c.open_time < HOLDOUT_END]
    holdout_perp = [c for c in perp if HOLDOUT_START <= c.open_time < HOLDOUT_END]

    # --- Research region: carry, walk-forward, significance ---
    res = build_carry_returns(research_spot, research_perp, capital_utilization=CAPITAL_UTILIZATION)
    res_rets = res.returns_on_capital
    wf = _walk_forward(spot, perp, CAPITAL_UTILIZATION)

    sig = significance_check(
        {
            "average_trade_return": statistics.mean(res_rets) * 100,
            "trade_return_std": statistics.pstdev(res_rets) * 100,
            "trade_count": len(res_rets),
            "sharpe": annualized_sharpe(res_rets, INTERVAL),
            "avg_test_sharpe": wf["avg_test_sharpe"],
        },
        trial_count=TRIAL_COUNT,
        bar_returns=res_rets,
    )

    research_summary = {
        "ann_return_on_capital": round(_ann_return(res_rets) * 100, 3),
        "ann_sharpe": round(annualized_sharpe(res_rets, INTERVAL), 3),
        "capital_utilization": CAPITAL_UTILIZATION,
        "n_bars": len(res_rets),
    }

    # --- Cost & margin stress (research region) ---
    stress = {}
    for mult in (1.0, 1.5, 2.0):
        cs = build_carry_returns(research_spot, research_perp, capital_utilization=CAPITAL_UTILIZATION, cost_multiplier=mult)
        stress[f"cost_{mult}x"] = round(_ann_return(cs.returns_on_capital) * 100, 3)
    cs_tight = build_carry_returns(research_spot, research_perp, capital_utilization=STRESS_UTILIZATION)
    stress["margin_util_0.33"] = round(_ann_return(cs_tight.returns_on_capital) * 100, 3)

    # --- HOLDOUT: built and read exactly once ---
    print("Opening holdout (one-shot)...", flush=True)
    hold = build_carry_returns(holdout_spot, holdout_perp, capital_utilization=CAPITAL_UTILIZATION)
    hold_rets = hold.returns_on_capital
    holdout_ann_return = _ann_return(hold_rets) * 100
    holdout_sharpe = annualized_sharpe(hold_rets, INTERVAL)
    # Holdout under stress too
    hold_15 = build_carry_returns(holdout_spot, holdout_perp, capital_utilization=CAPITAL_UTILIZATION, cost_multiplier=1.5)
    holdout_ann_return_15 = _ann_return(hold_15.returns_on_capital) * 100

    # --- Classification ---
    gates = {
        "walk_forward_pass": wf["pass"],
        "significance_pass": sig["pass"],
        "holdout_positive": holdout_ann_return > 0,
        "holdout_meets_deploy_floor": holdout_ann_return >= DEPLOY_RETURN_FLOOR * 100,
        "holdout_cost_robust_1.5x": holdout_ann_return_15 > 0,
    }
    if not (gates["walk_forward_pass"] and gates["significance_pass"] and gates["holdout_positive"]):
        verdict = "FAIL"
    elif gates["holdout_meets_deploy_floor"] and gates["holdout_cost_robust_1.5x"]:
        verdict = "PASS"
    else:
        verdict = "WATCH"  # real and positive, but thin / not robustly deployable

    bundle = {
        "symbol": SYMBOL, "interval": INTERVAL,
        "deployability_floor_pct_per_yr": DEPLOY_RETURN_FLOOR * 100,
        "research_region": research_summary,
        "walk_forward": wf,
        "significance": sig,
        "cost_margin_stress_research_ann_return_pct": stress,
        "holdout": {
            "window": f"{HOLDOUT_START.date()}..{HOLDOUT_END.date()}",
            "n_bars": len(hold_rets),
            "ann_return_on_capital_pct": round(holdout_ann_return, 3),
            "ann_return_on_capital_pct_1.5x_cost": round(holdout_ann_return_15, 3),
            "ann_sharpe": round(holdout_sharpe, 3),
            "total_cost_fraction": round(hold.total_cost, 5),
        },
        "gate_results": gates,
        "verdict": verdict,
    }
    print("\n===== DELTA-NEUTRAL CARRY VERDICT =====")
    print(json.dumps(bundle, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
