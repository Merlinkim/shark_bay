from app.research_agent import build_research_recommendations


def _spec(name: str):
    return {
        "strategy_name": name,
        "parameters": {"fast_window": 9, "slow_window": 21},
        "intended_regime": "trend",
        "risk_profile": "medium",
    }


def test_low_trade_count_risk():
    payload = build_research_recommendations(
        symbol="BTCUSDT",
        interval="1m",
        strategy="ema_cross_v1",
        experiments=[{"strategy_name": "ema_cross_v1", "trade_count": 2, "sharpe": 0.4}],
        strategy_specs=[_spec("ema_cross_v1")],
        analytics={"summary": {"total_experiments": 1}},
    )
    assert payload["overfit_risk"]["label"] in {"medium", "high"}
    assert any("low_trade_count" in f for f in payload["overfit_risk"]["flags"])


def test_failed_walk_forward_rejection():
    payload = build_research_recommendations(
        symbol="BTCUSDT",
        interval="1m",
        strategy="ema_cross_v1",
        experiments=[{"strategy_name": "ema_cross_v1", "trade_count": 20}],
        strategy_specs=[_spec("ema_cross_v1")],
        analytics={"summary": {"total_experiments": 1}},
        walk_forward_result={"aggregate": {"pass_fail_status": "fail", "degradation_score": 1.0}},
    )
    assert payload["rejected_strategies"]
    assert payload["rejected_strategies"][0]["strategy_name"] == "ema_cross_v1"


def test_recommendation_output_shape():
    payload = build_research_recommendations(
        symbol="BTCUSDT",
        interval="1m",
        strategy=None,
        experiments=[],
        strategy_specs=[_spec("ema_cross_v1")],
        analytics={"summary": {"total_experiments": 0}},
    )
    for key in [
        "generated_at",
        "agent_version",
        "symbol",
        "interval",
        "research_summary",
        "overfit_risk",
        "strategy_assessments",
        "recommended_experiments",
        "rejected_strategies",
        "next_actions",
    ]:
        assert key in payload


def test_no_trading_action_fields_exposed():
    payload = build_research_recommendations(
        symbol="BTCUSDT",
        interval="1m",
        strategy=None,
        experiments=[],
        strategy_specs=[_spec("ema_cross_v1")],
        analytics={"summary": {"total_experiments": 0}},
    )
    assert "trading_actions" not in payload
    assert "execution_plan" not in payload
    assert payload["safety"]["order_execution_enabled"] is False
