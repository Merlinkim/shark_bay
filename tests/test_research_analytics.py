from app.research_analytics import build_research_analytics


def test_empty_payload_is_graceful():
    payload = build_research_analytics([])
    assert payload["summary"]["total_experiments"] == 0
    assert payload["strategy_leaderboard"] == []


def test_leaderboard_sorting_and_aggregates():
    rows = [
        {"experiment_id": "a", "strategy_name": "s1", "intended_regime": "trend", "sharpe": 1.5, "total_return_pct": 4, "max_drawdown_pct": -3, "win_rate_pct": 55, "trade_count": 3, "created_at": "2026-01-01T00:00:00+00:00"},
        {"experiment_id": "b", "strategy_name": "s1", "intended_regime": "trend", "sharpe": 0.5, "total_return_pct": 2, "max_drawdown_pct": -4, "win_rate_pct": 45, "trade_count": 2, "created_at": "2026-01-02T00:00:00+00:00"},
        {"experiment_id": "c", "strategy_name": "s2", "intended_regime": "mean_reversion", "sharpe": 0.9, "total_return_pct": 3, "max_drawdown_pct": -2, "win_rate_pct": 60, "trade_count": 5, "created_at": "2026-01-03T00:00:00+00:00"},
    ]
    payload = build_research_analytics(rows)
    assert payload["strategy_leaderboard"][0]["strategy_name"] == "s1"
    assert payload["strategy_leaderboard"][0]["trade_count"] == 5
    regimes = {r["regime"]: r for r in payload["regime_breakdown"]}
    assert regimes["trend"]["experiments"] == 2
