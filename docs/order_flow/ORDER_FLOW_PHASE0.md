# Taker Order Flow Imbalance — Phase 0 Feasibility (pre-check)

Real Binance perp klines (taker-buy volume = array index 9). Aggressor imbalance
`imb_t = (2·taker_buy_base − volume)/volume ∈ [-1,1]`, known at bar close t, tested
against next-bar return. IC = Pearson(imb_t, fwd_ret). BTCUSDT + ETHUSDT, 5m/15m/1h.

## Results

| Symbol | Interval | n | **IC** | Naive sign-strat net @7bps |
|--------|----------|---|--------|----------------------------|
| BTC | 5m  | 148,604 | **−0.0038** | −6,780%/yr |
| BTC | 15m | 84,671  | **−0.0104** | −2,494%/yr |
| BTC | 1h  | 38,687  | **−0.0049** | −636%/yr |
| ETH | 5m  | 148,604 | **−0.0009** | −6,951%/yr |
| ETH | 15m | 84,671  | **−0.0023** | −2,404%/yr |
| ETH | 1h  | 38,687  | **−0.0017** | −626%/yr |

Recent regime (≥2025-06) identical: no signal.

## Verdict: **FAIL — abort.**

The information coefficient is **≈ 0 (and slightly negative) at every frequency
for both symbols.** Aggregated kline aggressor imbalance has no linear predictive
power for next-bar return at any deployable bar size. The naive strategy's
catastrophic losses are secondary (per-bar flipping × turnover cost), but they
underline the point: even if a faint signal existed, it would be buried far below
costs. There is nothing to take to a full milestone.

Caveat: this does not disprove microstructure alpha at sub-second/tick resolution
— but that frequency requires tick data and co-located execution SharkBay does
not have and could not deploy. At the frequencies and data we can actually trade,
order flow is empty.

## Meta-finding (now three families deep)

Funding (carry + dispersion), cross-sectional momentum, and order-flow imbalance
have all failed in deployable form, the latter two with the edge specifically
absent or decayed in the current regime. The accumulating evidence is that
**simple, liquid, free-data signals on Binance perps do not yield a deployable
edge for SharkBay in the current regime.** The binding constraint is shifting
from "which factor" toward regime/execution. Two genuinely untested avenues
remain: the **volatility risk premium** (a structurally different return source —
compensation for tail risk, not a mispricing) and the **forward-collected**
families (OI, liquidations) once they accrue history.
