import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

KNOWN_FEATURES = {
    "return_1m",
    "return_5m",
    "volatility_20",
    "volume_zscore_20",
    "sma_20",
    "ema_20",
    "rsi_14",
    "atr_14",
    "trend_strength",
    "regime_label",
    "latest_close",
}


@dataclass(frozen=True)
class StrategySpec:
    strategy_name: str
    display_name: str
    description: str
    status: str
    mode: str
    symbols: list[str]
    interval: str
    features_used: list[str]
    parameters: dict[str, Any]
    risk_profile: str
    intended_regime: str
    version: str
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_TIMESTAMP = _now_iso()


REGISTRY: list[StrategySpec] = [
    StrategySpec(
        strategy_name="ema_cross_v1",
        display_name="EMA Cross v1",
        description="Trend-following EMA crossover metadata spec for research/backtest workflows.",
        status="research_ready",
        mode="backtest_planned",
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1m",
        features_used=["ema_20", "sma_20", "trend_strength", "regime_label"],
        parameters={"fast_window": 9, "slow_window": 21, "min_trend_strength": 0.0015},
        risk_profile="medium",
        intended_regime="trend",
        version="v0",
        created_at=_TIMESTAMP,
        updated_at=_TIMESTAMP,
    ),
    StrategySpec(
        strategy_name="rsi_mean_reversion_v1",
        display_name="RSI Mean Reversion v1",
        description="Mean-reversion metadata spec keyed on RSI and short-horizon return dislocations.",
        status="research_ready",
        mode="backtest_planned",
        symbols=["BTCUSDT"],
        interval="1m",
        features_used=["rsi_14", "return_1m", "return_5m", "regime_label"],
        parameters={"rsi_buy_threshold": 30, "rsi_sell_threshold": 70, "max_holding_bars": 20},
        risk_profile="medium_high",
        intended_regime="range",
        version="v0",
        created_at=_TIMESTAMP,
        updated_at=_TIMESTAMP,
    ),
    StrategySpec(
        strategy_name="volatility_breakout_v1",
        display_name="Volatility Breakout v1",
        description="Breakout metadata spec designed for volatility expansion regimes.",
        status="research_ready",
        mode="backtest_planned",
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1m",
        features_used=["volatility_20", "atr_14", "volume_zscore_20", "trend_strength", "regime_label"],
        parameters={"volatility_threshold": 0.0012, "atr_multiplier": 1.6, "volume_z_min": 1.0},
        risk_profile="high",
        intended_regime="transition",
        version="v0",
        created_at=_TIMESTAMP,
        updated_at=_TIMESTAMP,
    ),
]


def validate_registry(registry: list[StrategySpec]) -> None:
    names = [spec.strategy_name for spec in registry]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate strategy_name detected")

    required = {
        "strategy_name", "display_name", "description", "status", "mode", "symbols", "interval",
        "features_used", "parameters", "risk_profile", "intended_regime", "version",
    }
    for spec in registry:
        missing = [field for field in required if not getattr(spec, field, None)]
        if missing:
            raise ValueError(f"Missing required fields for {spec.strategy_name}: {missing}")
        unknown = [feature for feature in spec.features_used if feature not in KNOWN_FEATURES]
        if unknown:
            raise ValueError(f"Unknown feature(s) for {spec.strategy_name}: {unknown}")


def list_strategy_specs(status: str | None = None, symbol: str | None = None, interval: str | None = None) -> list[dict[str, Any]]:
    validate_registry(REGISTRY)
    specs = REGISTRY
    if status:
        specs = [s for s in specs if s.status == status]
    if symbol:
        specs = [s for s in specs if symbol in s.symbols]
    if interval:
        specs = [s for s in specs if s.interval == interval]
    return [asdict(spec) for spec in specs]


def main() -> None:
    print(json.dumps({"strategies": list_strategy_specs()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
