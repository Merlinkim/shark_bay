# Funding Carry — Failure Modes & Modeling Caveats

A verdict is only trustworthy if the ways it could be *wrong* are written down
before it is read. This document enumerates the look-ahead risks, the modeling
simplifications, and the economic failure modes for `funding_carry`.

---

## A. Look-ahead / leakage risks (and how each is closed)

| # | Risk | Mitigation | Test |
|---|------|------------|------|
| 1 | A bar sees a funding rate settled *after* its open_time | Strict as-of join: `align_funding_to_candles` attaches only the latest settlement with `settlement_time ≤ open_time` | `test_asof_alignment_no_future_leak`, `test_shifting_funding_later_cannot_change_past_pnl` |
| 2 | Signal at row k depends on rows > k | Engine prefix-invariance guard recomputes signals on truncated prefixes and rejects any change | `DynamicSignalStrategy._assert_no_lookahead` + `test_funding_signal_is_prefix_invariant` |
| 3 | Funding PnL credited on a position decided *with knowledge of that settlement* | Funding is charged on the position **carried into** the bar (established in a prior bar from prior data), never on the bar's own fresh fill | `test_short_receives_positive_funding_with_flat_price` |
| 4 | Open-interest crowding filter reads a future OI value | Same as-of join; OI attached only as-of open_time | covered by #1 mechanism |

## B. Modeling simplifications (documented, not hidden)

1. **Funding charged on the pre-fill carried position.** In reality the holder at
   the exact settlement snapshot pays/receives. We charge the position carried
   *into* the bar, before the new signal fills at the same open. This is the
   economically correct intent (you must hold across the settlement to be paid)
   and is conservative for an entering position (it collects funding only from the
   second bar of a trade onward).

2. **8h settlement-aligned bars.** The verdict uses native 8h klines whose open
   times coincide with funding settlements. On other intervals the as-of join
   still holds, but funding is credited once per bar at the most recent rate,
   which under-counts if a bar spans multiple settlements (not the case at ≥8h).

3. **Taker fees on every position change (10 bps + 2 bps slippage).** No maker
   rebates are assumed. A real deployment that posts limit orders could do better;
   we deliberately model the pessimistic case.

4. **No funding on the entry bar, full funding thereafter.** See #1 of section A.

5. **Single instrument, directional.** This is *not* a delta-neutral spot-perp
   carry. It carries price risk. A delta-neutral version would need a second
   instrument the engine does not yet model. The directional form is the honest
   thing we *can* test today, and its price risk is precisely what may sink it.

6. **Open-interest history is shallow (~30 days from Binance).** For multi-year
   verdicts the OI crowding filter is disabled (`oi_crowding_mult = 0`); the
   verdict rests on funding alone. OI is plumbed for future short-window use.

## C. Economic failure modes (the thesis may simply be wrong)

1. **Adverse price drift > carry.** Being short crowded longs can lose more on
   price than the funding collected, especially in a strong bull trend where
   funding stays positive *and* price keeps rising.
2. **Carry too small vs. costs.** If trades flip often, 12 bps round-trip costs
   dominate the bps-per-8h carry.
3. **Regime dependence.** Edge concentrated in deleveraging events; absent or
   negative in trending regimes. Walk-forward positive-window fraction is the
   detector.
4. **Crowding never reverts within the holding period** — funding is collected
   but the position is stopped out or bleeds indefinitely.

## D. What would make the verdict UN-trustworthy (abort conditions)

- Any leakage test failing.
- Funding data gaps over the evaluation window (missing settlements silently
  treated as zero carry).
- The holdout being touched more than once, or before all tests pass.
- A PASS that does not survive 1.5× cost stress (treated as FAIL).
