from decimal import Decimal

STRATEGY_META = {
    "strategy_id": "sma_crossover",
    "name": "SMA Crossover",
    "version": "0.1.0",
    "created_by": "builtin",
    "strategy_type": "signal_strategy",
    "research_only": True,
    "description": "SMA crossover using short and long lookback windows.",
    "parameter_schema": {
        "short_window": {"type": "int", "min": 1, "max": 500},
        "long_window": {"type": "int", "min": 2, "max": 1000},
    },
    "default_parameters": {"short_window": 5, "long_window": 20},
}

def required_features(params) -> list:
    return ["close"]

def prepare_features(df, params):
    return df

def generate_signals(df, params):
    short_window = int(params.get("short_window", 5))
    long_window = int(params.get("long_window", 20))
    if short_window >= long_window:
        raise ValueError("short_window must be < long_window")
    closes = [Decimal(str(row["close"])) for row in df]
    signals = []
    for i in range(len(df)):
        if i + 1 < long_window:
            signals.append({"signal": 0})
            continue
        short = sum(closes[i - short_window + 1 : i + 1]) / Decimal(short_window)
        long = sum(closes[i - long_window + 1 : i + 1]) / Decimal(long_window)
        signals.append({"signal": 1 if short > long else -1 if short < long else 0})
    return signals
