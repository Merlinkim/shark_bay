from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

from app.experiments import ResearchExperimentRepository
from app.features import build_snapshot
from app.research_analytics import build_research_analytics
from app.strategy_registry import list_strategy_specs

AGENT_VERSION = "research_agent_v0"


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_utc_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _latest_strategy_experiment(experiments: list[dict[str, Any]], strategy_name: str) -> dict[str, Any] | None:
    for row in experiments:
        if row.get("strategy_name") == strategy_name:
            return row
    return None


def _overfit_risk_label(flags: list[str]) -> str:
    if len(flags) >= 3:
        return "high"
    if len(flags) >= 1:
        return "medium"
    return "low"


def _holdout_requested_too_frequently(experiments: list[dict[str, Any]]) -> bool:
    holdout_like = 0
    for row in experiments[:10]:
        if row.get("split_mode") == "holdout" or row.get("include_holdout") is True:
            holdout_like += 1
    return holdout_like >= 4


def build_research_recommendations(
    *,
    symbol: str,
    interval: str,
    strategy: str | None,
    experiments: list[dict[str, Any]],
    strategy_specs: list[dict[str, Any]],
    analytics: dict[str, Any],
    walk_forward_result: dict[str, Any] | None = None,
    feature_snapshot: dict[str, Any] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    selected_specs = [s for s in strategy_specs if strategy is None or s["strategy_name"] == strategy]
    flags: list[str] = []
    strategy_assessments: list[dict[str, Any]] = []
    recommended_experiments: list[dict[str, Any]] = []
    rejected_strategies: list[dict[str, Any]] = []

    if _holdout_requested_too_frequently(experiments):
        flags.append("holdout_requested_too_frequently")

    wf_status = (walk_forward_result or {}).get("aggregate", {}).get("pass_fail_status")

    for spec in selected_specs:
        latest = _latest_strategy_experiment(experiments, spec["strategy_name"])
        trade_count = int((latest or {}).get("trade_count", 0) or 0)
        sharpe = _safe_float((latest or {}).get("sharpe"))
        total_return_pct = _safe_float((latest or {}).get("total_return_pct"))
        max_drawdown_pct = _safe_float((latest or {}).get("max_drawdown_pct"))
        win_rate_pct = _safe_float((latest or {}).get("win_rate_pct"))

        local_flags: list[str] = []
        if trade_count < 8:
            local_flags.append("low_trade_count")
            flags.append(f"{spec['strategy_name']}:low_trade_count")

        if walk_forward_result:
            agg = walk_forward_result.get("aggregate", {})
            degradation = _safe_float(agg.get("degradation_score"))
            if degradation > 0.75:
                local_flags.append("validation_test_degradation")
                flags.append(f"{spec['strategy_name']}:validation_test_degradation")
            if _safe_float(agg.get("avg_train_sharpe")) >= 1.2 and _safe_float(agg.get("avg_test_sharpe")) < 0:
                local_flags.append("train_strong_test_weak")
                flags.append(f"{spec['strategy_name']}:train_strong_test_weak")

        assessment = {
            "strategy_name": spec["strategy_name"],
            "recent_sharpe": round(sharpe, 6),
            "total_return_pct": round(total_return_pct, 6),
            "max_drawdown_pct": round(max_drawdown_pct, 6),
            "win_rate_pct": round(win_rate_pct, 6),
            "trade_count": trade_count,
            "walk_forward_status": wf_status if walk_forward_result else "not_provided",
            "regime_alignment": {
                "intended_regime": spec.get("intended_regime", "unknown"),
                "latest_feature_regime": ((feature_snapshot or {}).get("features") or {}).get("regime_label"),
                "is_aligned": ((feature_snapshot or {}).get("features") or {}).get("regime_label") in (None, spec.get("intended_regime")),
            },
            "risk_profile": spec.get("risk_profile", "unknown"),
            "assessment_flags": local_flags,
        }
        strategy_assessments.append(assessment)

        if walk_forward_result and wf_status == "fail":
            rejected_strategies.append(
                {
                    "strategy_name": spec["strategy_name"],
                    "reason": "walk_forward_failed",
                    "severity": "high",
                    "safety_note": "Rejected for deployment consideration; keep research-only and do not execute trades.",
                }
            )
        else:
            recommended_experiments.extend(
                [
                    {
                        "strategy_name": spec["strategy_name"],
                        "reason": "Increase sample size to verify robustness.",
                        "proposed_params": spec.get("parameters", {}),
                        "proposed_date_range": {
                            "start": _to_utc_iso(start),
                            "end": _to_utc_iso(end),
                            "extension": "extend_backward_180d",
                        },
                        "priority": "high" if trade_count < 8 else "medium",
                        "safety_note": "Research-only recommendation. Never place live/paper orders.",
                    },
                    {
                        "strategy_name": spec["strategy_name"],
                        "reason": "Validate stability with alternative walk-forward windows.",
                        "proposed_params": {"train_days": 120, "validation_days": 45, "test_days": 45, "step_days": 30},
                        "proposed_date_range": {"start": _to_utc_iso(start), "end": _to_utc_iso(end)},
                        "priority": "high",
                        "safety_note": "Research-only recommendation. No autonomous execution.",
                    },
                    {
                        "strategy_name": spec["strategy_name"],
                        "reason": "Conservative parameter mutation around current baseline.",
                        "proposed_params": {**spec.get("parameters", {}), "mutation": "conservative_±10pct"},
                        "proposed_date_range": {"start": _to_utc_iso(start), "end": _to_utc_iso(end)},
                        "priority": "medium",
                        "safety_note": "Only evaluate in deterministic backtests.",
                    },
                ]
            )

    overfit_label = _overfit_risk_label(flags)
    research_summary = {
        "strategy_count": len(selected_specs),
        "latest_experiment_count": len(experiments),
        "analytics_total_experiments": analytics.get("summary", {}).get("total_experiments", 0),
        "notes": [
            "Deterministic rule-based recommendation agent v0.",
            "This component is research-only and cannot trade.",
        ],
    }

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "agent_version": AGENT_VERSION,
        "symbol": symbol,
        "interval": interval,
        "research_summary": research_summary,
        "overfit_risk": {"label": overfit_label, "flags": flags},
        "strategy_assessments": strategy_assessments,
        "recommended_experiments": recommended_experiments,
        "rejected_strategies": rejected_strategies,
        "next_actions": [
            "Run recommended deterministic experiments and persist outcomes.",
            "Review overfit flags before promoting any strategy idea.",
            "Maintain strict research-only scope: no live/paper trading and no order execution.",
        ],
        "safety": {
            "research_only": True,
            "live_trading_enabled": False,
            "paper_trading_enabled": False,
            "order_execution_enabled": False,
            "autonomous_code_modification_enabled": False,
            "direct_exchange_access_enabled": False,
        },
    }


def run_agent(*, symbol: str, interval: str, strategy: str | None, start: datetime | None, end: datetime | None, walk_forward_result: dict[str, Any] | None = None) -> dict[str, Any]:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    strategy_specs = list_strategy_specs(symbol=symbol, interval=interval)
    repo = ResearchExperimentRepository(db_url)
    repo.ensure_schema()
    experiments = repo.list_latest(symbol=symbol, interval=interval, limit=200)
    analytics = build_research_analytics(experiments)

    snapshot = None
    try:
        snapshot = build_snapshot(symbol=symbol, interval=interval, lookback_hours=24)
    except Exception:
        snapshot = None

    return build_research_recommendations(
        symbol=symbol,
        interval=interval,
        strategy=strategy,
        experiments=experiments,
        strategy_specs=strategy_specs,
        analytics=analytics,
        walk_forward_result=walk_forward_result,
        feature_snapshot=snapshot,
        start=start,
        end=end,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Research Agent v0 (recommendation-only)")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", required=True)
    parser.add_argument("--strategy", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start.replace("Z", "+00:00")) if args.start else None
    end = datetime.fromisoformat(args.end.replace("Z", "+00:00")) if args.end else None

    payload = run_agent(symbol=args.symbol, interval=args.interval, strategy=args.strategy, start=start, end=end)
    print(json.dumps(payload, separators=(",", ":"), default=str))


if __name__ == "__main__":
    main()
