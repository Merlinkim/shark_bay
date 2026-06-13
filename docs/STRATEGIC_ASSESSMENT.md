# SharkBay Strategic Assessment — Bottleneck Diagnosis

After five trustworthy FAILs, the question is no longer "which strategy" but
"what is actually limiting us." This memo diagnoses the bottleneck before any
further research family is proposed.

## What the five results actually say (not just "FAIL")

| Result | Nuance — this matters for diagnosis |
|--------|-------------------------------------|
| Directional carry | t=0.07 — genuinely no edge (price risk dominated) |
| Delta-neutral carry | **+1.53%/yr net, REAL** — but below the 4% deployability floor (thin) |
| X-sectional funding | gross funding spread **+25%/yr (real)**; basket price PnL killed net |
| X-sectional momentum | **+6–9%/yr full-sample, beta≈0 (real)** — but NEGATIVE in 2025–26 |
| Order flow | IC≈0 at all deployable frequencies — no signal at our resolution |

The critical observation: **four of five hypotheses detected real economic
effects.** They did not fail because the ideas were nonsense. They failed
because the edge was (a) thin after honest costs, (b) compressed in the current
regime, (c) cancelled by a co-moving risk we couldn't strip cheaply, or (d)
below our data resolution. That pattern points away from "bad hypotheses."

## The four explanations, weighed

### A) The hypotheses are wrong — **~10%**
- *For:* five FAILs.
- *Against (decisive):* the hypotheses were economically grounded and **we
  measured the effects** — momentum +6–9%, funding spread +25% gross, carry
  +1.5% net. These are confirmations, not refutations. The failures are
  downstream of detection (cost/regime/risk), not at the hypothesis.
- Verdict: largely rejected. The research instincts were sound.

### B) The current regime has little deployable edge in liquid markets — **~40%**
- *For (strong):* momentum went **negative in 2025–26** after +37% in 2021;
  funding level compressed 30%→0.86%; dispersion net-negative. **Two independent
  factors decayed in the same recent window** — the signature of crowding as
  crypto liquid markets matured (ETFs, institutional MMs, more sophisticated
  flow 2024–26).
- *Against:* only simple/liquid/well-known factors were tested; VRP and
  illiquid/alt niches untested; delta-neutral carry was still +1.5% (small but
  positive) recently — not literally zero.
- Verdict: the specific claim "**simple factor premia in liquid crypto perps
  have compressed in the current regime**" is well-supported.

### C) SharkBay lacks the DATA advantage to discover edges — **~30%**
- *For (strong):* everything ran on **free, public Binance REST** — the same data
  every participant sees. You cannot find edge others can't when you see exactly
  what they see. Order flow failed on data *resolution* (1m bars, not ticks);
  OI/liquidations are data-*blocked* (no history). We have no proprietary,
  faster, or alternative data.
- *Against:* data wasn't why carry/momentum failed — those had ample data and the
  edge genuinely decayed or was thin.
- Verdict: an **enabling constraint** — the lack of a data edge means we can only
  ever reach commoditized signals, which are exactly the ones that have crowded out.

### D) SharkBay lacks the EXECUTION advantage to monetize edges — **~20%**
- *For:* delta-neutral carry (+1.5% real) fell sub-floor partly on conservative
  cost/margin haircuts; dispersion's +25% gross funding died on turnover; order
  flow needs latency we don't have. We **detect** edge but can't keep it after
  retail execution.
- *Against:* momentum decayed *gross* (negative before heavy costs) — execution
  wasn't the cause there; directional carry had no edge to monetize.
- Verdict: real for the thin/turnover-heavy cases, not universal.

## Synthesis: the bottleneck

These are not mutually exclusive — **B is the dominant story, enabled by C, with
D compounding.** SharkBay built an excellent *measurement and falsification*
engine and pointed it at the universe of edges reachable with **public data +
retail execution**. That universe has been **competed down in the current
regime**. The five FAILs are not a research failure — they are an honest map
showing the *commoditized-edge frontier is exhausted* for us.

**Primary bottleneck: market regime × absence of a structural advantage.**
Ranked: **Regime (primary) → Data (enabling) → Execution (secondary) → Alpha (not
the issue).** It is *not* an alpha-generation problem; our research process is
working correctly. It is that the edges our process can *reach* are crowded.

## "If you were building SharkBay from scratch today, what would you do differently?"

1. **Decide the edge SOURCE before building the measurement engine.** We built a
   beautiful falsification machine first, then searched for edge. Backwards. A
   trading operation must first choose its structural advantage — data, speed, or
   risk-bearing capacity — because *with no advantage you can only find the
   crowded, decaying edges we found.*
2. **Start proprietary/forward data collection on day one.** The single thing
   that would most change today's position is having a year of on-chain,
   cross-venue, OI, and liquidation history *now*. The collectors we just built
   should have been running 12 months ago. Data you hold and others don't is the
   only durable discovery advantage available to a small shop.
3. **Build regime-decay / crowding detection into the first screen,** not the
   holdout. A signal strong in 2021–23 and dead in 2024–26 should be flagged as a
   crowding-decay risk up front.
4. **Be honest about what "deployable edge" means for a small operation:** not
   HFT microstructure (lose to co-located firms), not crowded liquid factors
   (compressed), but one of — (a) capacity-constrained niches too small for large
   players, (b) **risk premia** (VRP, basis) where the return compensates for
   real tail risk others avoid, or (c) **structural/operational** edges (superior
   funding/borrow, venue access, jurisdiction).
5. **Reframe the objective around capacity and risk-bearing, not "alpha."** For
   SharkBay's profile, durable income is more likely from harvesting a risk
   premium with disciplined tail management than from out-predicting the market.

## Decision this teiees up (no strategy proposed yet)

Given the bottleneck is regime × structural-advantage, the next move is a
*strategic* choice, not another liquid-factor backtest:

- **(i) Risk-premium path:** test VRP — explicitly a different return *source*
  (paid to bear tail risk), the one untested family least likely to be crowded out.
- **(ii) Data-advantage path:** run the collectors now, accrue 3–12 months of OI /
  liquidation / on-chain history, then research families that competitors with
  only-Binance-REST cannot — turning our *lack* of data edge into one over time.
- **(iii) Reposition:** accept that deployable directional/factor alpha may not
  exist for this profile and redefine the goal (market-neutral risk-premium
  income, or an execution/infrastructure product).

My recommendation is to **commit to (ii) immediately and in the background
regardless** (it is cheap and compounding), and to choose between (i) and (iii)
as the next *active* milestone — a decision I'll frame only once you confirm the
bottleneck diagnosis above.
