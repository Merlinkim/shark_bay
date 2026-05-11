from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.experiments import ResearchExperimentRepository


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_research_analytics(experiments: list[dict[str, Any]], recent_limit: int = 10) -> dict[str, Any]:
    total_experiments = len(experiments)
    if total_experiments == 0:
        return {
            "summary": {
                "total_experiments": 0,
                "best_strategy_by_sharpe": None,
                "best_strategy_by_return": None,
                "worst_strategy_by_drawdown": None,
            },
            "strategy_leaderboard": [],
            "regime_breakdown": [],
            "recent_rankings": [],
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }

    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in experiments:
        by_strategy[str(row.get("strategy_name", "unknown"))].append(row)
        by_regime[str(row.get("intended_regime", "unknown"))].append(row)

    strategy_rows: list[dict[str, Any]] = []
    for strategy, rows in by_strategy.items():
        sharpes = [_safe_float(r.get("sharpe")) for r in rows]
        returns = [_safe_float(r.get("total_return_pct")) for r in rows]
        draws = [_safe_float(r.get("max_drawdown_pct")) for r in rows]
        wins = [_safe_float(r.get("win_rate_pct")) for r in rows]
        trades = [int(r.get("trade_count", 0) or 0) for r in rows]
        strategy_rows.append(
            {
                "strategy_name": strategy,
                "experiments": len(rows),
                "average_sharpe": round(_avg(sharpes), 6),
                "average_return_pct": round(_avg(returns), 6),
                "win_rate_pct": round(_avg(wins), 6),
                "trade_count": sum(trades),
                "average_drawdown_pct": round(_avg(draws), 6),
            }
        )

    strategy_leaderboard = sorted(
        strategy_rows,
        key=lambda x: (x["average_sharpe"], x["average_return_pct"], -x["average_drawdown_pct"]),
        reverse=True,
    )

    best_sharpe = max(experiments, key=lambda x: _safe_float(x.get("sharpe")))
    best_return = max(experiments, key=lambda x: _safe_float(x.get("total_return_pct")))
    worst_drawdown = min(experiments, key=lambda x: _safe_float(x.get("max_drawdown_pct")))

    regime_breakdown = []
    for regime, rows in sorted(by_regime.items()):
        regime_breakdown.append(
            {
                "regime": regime,
                "experiments": len(rows),
                "average_sharpe": round(_avg([_safe_float(r.get("sharpe")) for r in rows]), 6),
                "average_return_pct": round(_avg([_safe_float(r.get("total_return_pct")) for r in rows]), 6),
                "average_drawdown_pct": round(_avg([_safe_float(r.get("max_drawdown_pct")) for r in rows]), 6),
                "average_win_rate_pct": round(_avg([_safe_float(r.get("win_rate_pct")) for r in rows]), 6),
            }
        )

    recent_rows = sorted(experiments, key=lambda x: str(x.get("created_at", "")), reverse=True)[:recent_limit]
    recent_rankings = sorted(
        [
            {
                "experiment_id": r.get("experiment_id"),
                "strategy_name": r.get("strategy_name"),
                "sharpe": round(_safe_float(r.get("sharpe")), 6),
                "total_return_pct": round(_safe_float(r.get("total_return_pct")), 6),
                "max_drawdown_pct": round(_safe_float(r.get("max_drawdown_pct")), 6),
                "created_at": r.get("created_at"),
            }
            for r in recent_rows
        ],
        key=lambda x: (x["sharpe"], x["total_return_pct"], -x["max_drawdown_pct"]),
        reverse=True,
    )

    return {
        "summary": {
            "total_experiments": total_experiments,
            "best_strategy_by_sharpe": {
                "strategy_name": best_sharpe.get("strategy_name"),
                "sharpe": round(_safe_float(best_sharpe.get("sharpe")), 6),
                "experiment_id": best_sharpe.get("experiment_id"),
            },
            "best_strategy_by_return": {
                "strategy_name": best_return.get("strategy_name"),
                "total_return_pct": round(_safe_float(best_return.get("total_return_pct")), 6),
                "experiment_id": best_return.get("experiment_id"),
            },
            "worst_strategy_by_drawdown": {
                "strategy_name": worst_drawdown.get("strategy_name"),
                "max_drawdown_pct": round(_safe_float(worst_drawdown.get("max_drawdown_pct")), 6),
                "experiment_id": worst_drawdown.get("experiment_id"),
            },
        },
        "strategy_leaderboard": strategy_leaderboard,
        "regime_breakdown": regime_breakdown,
        "recent_rankings": recent_rankings,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def fetch_research_analytics(db_url: str, symbol: str, interval: str, limit: int) -> dict[str, Any]:
    repo = ResearchExperimentRepository(db_url)
    repo.ensure_schema()
    rows = repo.list_latest(symbol=symbol, interval=interval, limit=limit)
    return build_research_analytics(rows, recent_limit=min(limit, 20))


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only analytics over persisted research experiments")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    import os

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    payload = fetch_research_analytics(db_url=db_url, symbol=args.symbol, interval=args.interval, limit=args.limit)
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
