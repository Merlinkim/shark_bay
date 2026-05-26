from decimal import Decimal

STRATEGY_META = {
    "strategy_id": "bb_rsi_reversion",
    "name": "Bollinger RSI Reversion",
    "version": "0.1.0",
    "created_by": "builtin",
    "strategy_type": "signal_strategy",
    "research_only": True,
    "description": "Mean reversion using Bollinger Bands and RSI.",
    "parameter_schema": {
        "bb_window": {"type": "int", "min": 2, "max": 200},
        "bb_stddev": {"type": "float", "min": 0.1, "max": 5.0},
        "rsi_window": {"type": "int", "min": 2, "max": 100},
        "rsi_lower": {"type": "int", "min": 1, "max": 50},
        "rsi_upper": {"type": "int", "min": 51, "max": 99},
    },
    "default_parameters": {"bb_window": 20, "bb_stddev": 2.0, "rsi_window": 14, "rsi_lower": 30, "rsi_upper": 70},
}

def required_features(params) -> list:
    return ["close"]

def prepare_features(df, params):
    return df

def _rsi(closes, i, window):
    if i < window:
        return None
    gains = Decimal(0)
    losses = Decimal(0)
    for idx in range(i - window + 1, i + 1):
        ch = closes[idx] - closes[idx - 1]
        if ch > 0:
            gains += ch
        elif ch < 0:
            losses += abs(ch)
    if losses == 0:
        return Decimal(100)
    rs = (gains / Decimal(window)) / (losses / Decimal(window))
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))

def generate_signals(df, params):
    closes = [Decimal(str(row["close"])) for row in df]
    bb_window = int(params.get("bb_window", 20))
    std_mul = Decimal(str(params.get("bb_stddev", 2.0)))
    rsi_window = int(params.get("rsi_window", 14))
    rsi_lower = int(params.get("rsi_lower", 30))
    rsi_upper = int(params.get("rsi_upper", 70))
    out = []
    pos = 0
    for i, price in enumerate(closes):
        if i + 1 < bb_window or i < rsi_window:
            out.append({"signal": pos})
            continue
        sample = closes[i - bb_window + 1 : i + 1]
        mean = sum(sample) / Decimal(bb_window)
        var = sum((v - mean) ** 2 for v in sample) / Decimal(bb_window)
        std = var.sqrt()
        lower, upper = mean - (std_mul * std), mean + (std_mul * std)
        rsi = _rsi(closes, i, rsi_window)
        if pos == 0 and price < lower and rsi is not None and rsi < rsi_lower:
            pos = 1
        elif pos == 0 and price > upper and rsi is not None and rsi > rsi_upper:
            pos = -1
        elif pos == 1 and price >= mean:
            pos = 0
        elif pos == -1 and price <= mean:
            pos = 0
        out.append({"signal": pos})
    return out
