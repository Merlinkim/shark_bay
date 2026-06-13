# Funding Rate Carry — Research Hypothesis (G0)

**Strategy ID:** `funding_carry`
**Author:** Research Engine v2 milestone
**Status:** G0 hypothesis → under validation
**Instrument:** BTCUSDT perpetual (Binance USDⓈ-M futures), 8h bars

---

## 1. The economic mechanism

Perpetual futures have no expiry. To keep the perp price anchored to spot, the
exchange charges a **funding payment** between longs and shorts every 8 hours
(00:00, 08:00, 16:00 UTC on Binance). The funding rate is set by the
perp-vs-spot basis and the open interest imbalance:

- **Funding > 0:** perp trades above spot, longs are crowded → **longs pay shorts.**
- **Funding < 0:** perp trades below spot, shorts are crowded → **shorts pay longs.**

This is not a statistical pattern in price. It is a **contractual cash flow** with
a known sign and a known settlement schedule. That is what distinguishes it from
the ten textbook indicator strategies the engine has searched so far: there is an
explicit reason for a return to exist.

## 2. The hypothesis (falsifiable)

> Taking the side of the funding payment that *receives* cash — short when
> funding is strongly positive, long when strongly negative — earns a positive
> risk-adjusted return net of 10 bps taker costs, because the harvested funding
> plus the mean-reversion of crowded leveraged positioning together exceed the
> adverse price drift of being on the contrarian side.

There are **two** return sources, and the thesis requires their sum to beat costs:

1. **Carry:** the funding payment itself, collected every 8h the position is held.
2. **Crowding reversion:** crowded leveraged positioning (high |funding|, often
   with elevated open interest) tends to unwind, moving price in favor of the
   contrarian (funding-receiving) side.

## 3. Why it could fail (and we must let it)

- The contrarian price drift may **exceed** the funding collected — you get paid
  funding while the trade bleeds on price. This is the dominant failure mode for
  naive carry.
- Funding may be **too small** relative to 10 bps round-trip taker cost. At 1 bp
  per 8h, three settlements (one day) of carry ≈ 3 bps — less than one round trip.
  The strategy must therefore hold across **many** settlements per trade, which it
  does (it only flips when funding crosses zero through the threshold band).
- Funding regimes are **persistent then violent**: long quiet periods of small
  positive funding punctuated by sharp deleveraging. A strategy tuned to the quiet
  regime can be destroyed by the violent one. Walk-forward + holdout exist to
  catch exactly this.

## 4. Predictions if the thesis is true

- Positive average **test** Sharpe across walk-forward windows, not just train.
- Per-trade t-statistic ≥ 2.0 (the carry edge is real, not a few lucky unwinds).
- Survives the Deflated Sharpe gate at the logged trial count.
- **Robust to 1.5× and 2.0× cost stress** — carry that only survives at 10 bps
  and dies at 15 bps is not a deployable edge.

## 5. What a PASS and a FAIL each mean

- **PASS:** the first economically-grounded edge in SharkBay's history, eligible
  to progress to paper trading (G6).
- **FAIL:** equally valuable — a *trustworthy* rejection of the simplest carry
  formulation, with the failure mode identified (price drift vs. carry, cost
  fragility, or regime dependence), directing the next iteration.

The objective of this milestone is the **trustworthy verdict**, not the PASS.
