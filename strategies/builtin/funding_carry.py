"""Funding-rate carry / crowding-reversion strategy (signal_strategy).

Economic thesis (see FUNDING_CARRY_THESIS.md): perpetual-futures funding is a
periodic cash flow between longs and shorts. When funding is strongly positive,
crowded longs pay shorts; taking the SHORT side both (a) collects that funding
and (b) leans into the well-documented tendency of crowded leveraged positioning
to mean-revert. Symmetrically for strongly negative funding.

Signal at row i is computed from the funding rate KNOWN AT row i (settled at that
bar's open) and is executed by the engine at row i+1's open — leakage-free. The
strategy reads only past/current rows, so the engine's prefix-invariance leakage
guard holds.

Auxiliary data is optional: if 'funding_rate' is absent from a row the signal is
flat. 'open_interest', when present, is used as a crowding confirmation filter.
"""

STRATEGY_META = {
    "strategy_id": "funding_carry",
    "name": "Funding Rate Carry",
    "version": "0.1.0",
    "created_by": "builtin",
    "strategy_type": "signal_strategy",
    "research_only": True,
    "description": (
        "Short when 8h funding is strongly positive (collect funding + fade "
        "crowded longs), long when strongly negative. Optional open-interest "
        "crowding filter."
    ),
    "parameter_schema": {
        # Absolute funding threshold (per-8h fraction) to take a position.
        # 0.0001 = 1 bp per 8h ≈ 0.0274%/day ≈ 10.95%/yr of carry.
        "entry_threshold": {"type": "float", "min": 0.0, "max": 0.01},
        # Trailing bars to average funding over (1 = use the latest only).
        "smoothing_window": {"type": "int", "min": 1, "max": 30},
        # If > 0, only act when open_interest >= this multiple of its trailing
        # mean (crowding confirmation). 0 disables the filter.
        "oi_crowding_mult": {"type": "float", "min": 0.0, "max": 5.0},
        # Trailing bars for the OI mean used by the crowding filter.
        "oi_window": {"type": "int", "min": 2, "max": 90},
    },
    "default_parameters": {
        "entry_threshold": 0.0001,
        "smoothing_window": 1,
        "oi_crowding_mult": 0.0,
        "oi_window": 14,
    },
}


def required_features(params) -> list:
    return ["funding_rate"]


def prepare_features(df, params):
    return df


def _trailing_mean(values, i, window):
    lo = max(0, i - window + 1)
    window_vals = [v for v in values[lo : i + 1] if v is not None]
    if not window_vals:
        return None
    return sum(window_vals) / len(window_vals)


def generate_signals(df, params):
    entry_threshold = float(params.get("entry_threshold", 0.0001))
    smoothing_window = int(params.get("smoothing_window", 1))
    oi_crowding_mult = float(params.get("oi_crowding_mult", 0.0))
    oi_window = int(params.get("oi_window", 14))

    funding = [row.get("funding_rate") for row in df]
    open_interest = [row.get("open_interest") for row in df]

    signals = []
    for i in range(len(df)):
        smoothed = _trailing_mean(funding, i, smoothing_window)
        if smoothed is None:
            signals.append({"signal": 0})
            continue

        # Optional crowding filter: require elevated open interest to act.
        crowding_ok = True
        if oi_crowding_mult > 0.0 and open_interest[i] is not None:
            oi_mean = _trailing_mean(open_interest, i, oi_window)
            crowding_ok = oi_mean is not None and open_interest[i] >= oi_crowding_mult * oi_mean

        if not crowding_ok:
            signals.append({"signal": 0})
        elif smoothed > entry_threshold:
            signals.append({"signal": -1})   # crowded longs pay → short to receive
        elif smoothed < -entry_threshold:
            signals.append({"signal": 1})     # crowded shorts pay → long to receive
        else:
            signals.append({"signal": 0})
    return signals
