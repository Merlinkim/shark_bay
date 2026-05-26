from typing import Any

from app.strategy_loader import strategy_loader


def list_strategy_specs(status: str | None = None, symbol: str | None = None, interval: str | None = None) -> list[dict[str, Any]]:
    specs = []
    for meta in strategy_loader.list_metadata().values():
        item = dict(meta)
        item.setdefault("strategy_name", item.get("strategy_id"))
        item.setdefault("display_name", item.get("name", item.get("strategy_id")))
        item.setdefault("description", "")
        item.setdefault("status", "research_ready")
        item.setdefault("mode", "backtest_ready")
        item.setdefault("symbols", ["BTCUSDT"])
        item.setdefault("interval", "1m")
        item.setdefault("features_used", [])
        item.setdefault("parameters", item.get("default_parameters", {}))
        item.setdefault("risk_profile", "research")
        item.setdefault("intended_regime", "unknown")
        item.setdefault("version", item.get("version", "0.1.0"))
        specs.append(item)
    if status:
        specs = [s for s in specs if s.get("status") == status]
    if symbol:
        specs = [s for s in specs if symbol in s.get("symbols", [])]
    if interval:
        specs = [s for s in specs if s.get("interval") == interval]
    return specs
