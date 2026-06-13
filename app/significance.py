"""Statistical significance gates for Engine v2 (Milestone: Statistical Significance Framework).

Three complementary filters applied after walk-forward:

1. per_trade_tstat   — per-round-trip return t-statistic.  Gate: t ≥ 2.0.
2. deflated_sharpe   — Deflated Sharpe Ratio (Bailey & López de Prado 2014).
                       Adjusts observed Sharpe downward for non-normality and the
                       number of strategy trials tested.  Gate: DSR > 0.
3. block_bootstrap_pvalue — circular block bootstrap on an OOS return series.
                       Gate: p-value < 0.05 (observed Sharpe beats ≥ 95 % of
                       permuted paths).
4. significance_check — combines all three gates and returns a structured verdict.

All functions are pure (no I/O, no global state) so they are unit-testable without
any database or broker dependency.
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist as _NormalDist

_STD_NORM = _NormalDist()


# ---------------------------------------------------------------------------
# 1. Per-trade t-statistic
# ---------------------------------------------------------------------------

def per_trade_tstat(mean_return: float, std_return: float, n: int) -> float:
    """One-sample t-statistic for the hypothesis that mean per-trade return > 0.

    Args:
        mean_return: Mean per-round-trip return (any unit, e.g. percent).
        std_return:  Population std of per-round-trip returns (same unit).
        n:           Number of closed round trips.

    Returns:
        t-statistic, or 0.0 when std is 0 or n < 2.
    """
    if n < 2 or std_return <= 0.0:
        return 0.0
    se = std_return / math.sqrt(n)
    return mean_return / se


# ---------------------------------------------------------------------------
# 2. Deflated Sharpe Ratio  (Bailey & López de Prado, 2014)
# ---------------------------------------------------------------------------

def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_obs: int,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> float:
    """Probability that the Sharpe is not a false positive given multiple testing.

    Implements the Probabilistic Sharpe Ratio (PSR) deflated by the expected
    maximum Sharpe of an iid Gaussian under n_trials independent trials:

        SR* = sqrt(V[(SR̂)]) × ((1 - γ) × Φ⁻¹(1 - 1/T) + γ × Φ⁻¹(1 - 1/(T×e)))

    where γ is the Euler–Mascheroni constant, T = n_trials, and then:

        DSR = PSR(SR*) = Φ[ (SR_obs - SR*) × √(n-1) / σ_SR ]

    Args:
        observed_sharpe:  Annualized Sharpe of the candidate strategy.
        n_trials:         Total independent trials tested for this strategy family.
        n_obs:            Number of observations (bars) in the OOS evaluation period.
        skewness:         Third standardized moment of the OOS return series.
        excess_kurtosis:  Fourth standardized moment minus 3.

    Returns:
        DSR ∈ [0, 1]: probability the result is not a false positive.
        Values > 0.5 indicate DSR > 0 in the log-odds sense; conventional gate is > 0.
    """
    if n_obs < 2 or n_trials < 1:
        return 0.0

    # Variance of the Sharpe estimator (Lo 2002, adjusted for higher moments)
    # σ²(SR̂) ≈ (1 + 0.5·SR²·(κ-1) - SR·γ₃) / (n-1)
    # where γ₃ = skewness, κ = kurtosis = excess_kurtosis + 3
    sr = observed_sharpe
    variance_sr = (
        1.0
        + 0.5 * sr**2 * excess_kurtosis
        - sr * skewness
    ) / (n_obs - 1)
    std_sr = math.sqrt(max(variance_sr, 1e-12))

    # Expected maximum Sharpe of n_trials iid N(0,1) draws
    # Approximation from Bailey & López de Prado (2014), eq. 9
    euler_gamma = 0.5772156649015328
    if n_trials == 1:
        sr_star = 0.0
    else:
        # E[max of n_trials standard normals]
        z1 = _norm_ppf(1.0 - 1.0 / n_trials)
        z2 = _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
        sr_star = std_sr * ((1.0 - euler_gamma) * z1 + euler_gamma * z2)

    # PSR: probability that SR_obs > SR* under the null
    dsr_z = (sr - sr_star) / std_sr if std_sr > 0 else 0.0
    return _norm_cdf(dsr_z)


# ---------------------------------------------------------------------------
# 3. Block bootstrap p-value
# ---------------------------------------------------------------------------

def block_bootstrap_pvalue(
    returns: list[float],
    n_permutations: int = 1000,
    block_length: int | None = None,
    seed: int | None = 42,
) -> float:
    """Circular block bootstrap one-sided test that the Sharpe ratio is > 0.

    Resamples blocks of consecutive returns (preserving within-block
    autocorrelation structure) to build the bootstrap sampling distribution of
    the Sharpe ratio. The p-value is the fraction of resampled Sharpe ratios
    that are ≤ 0 — i.e. an estimate of P(SR ≤ 0) under H₀: SR ≤ 0.

    A low p-value (< 0.05) means almost no resample produced a non-positive
    Sharpe, so the positive Sharpe is robust to block resampling rather than an
    artifact of a few lucky bars.

    Note: block resampling preserves the empirical drift, so the resampled
    Sharpes are centered on the observed Sharpe. Counting resamples ≤ 0 (rather
    than ≥ observed) is what gives the test power: a strongly positive series
    yields p ≈ 0, a zero-mean series yields p ≈ 0.5.

    Args:
        returns:        Full OOS return series (bar-level, same units throughout).
        n_permutations: Number of bootstrap paths.
        block_length:   Block length in bars; defaults to max(1, ceil(n^(1/3))).
        seed:           RNG seed for reproducibility.

    Returns:
        p-value ∈ [0, 1].  Gate: p < 0.05.
    """
    n = len(returns)
    if n < 4:
        return 1.0

    rng = random.Random(seed)
    if block_length is None:
        block_length = max(1, math.ceil(n ** (1.0 / 3.0)))

    non_positive = 0
    for _ in range(n_permutations):
        resampled = _circular_block_resample(returns, block_length, n, rng)
        if _sharpe(resampled) <= 0.0:
            non_positive += 1

    return non_positive / n_permutations


# ---------------------------------------------------------------------------
# 4. Combined significance check
# ---------------------------------------------------------------------------

_TSTAT_GATE = 2.0
_DSR_GATE = 0.5       # DSR > 0.5 ↔ probability > 50 % not a false positive
_PVALUE_GATE = 0.05


def significance_check(
    metrics: dict,
    trial_count: int = 1,
    bar_returns: list[float] | None = None,
    n_bootstrap: int = 1000,
) -> dict:
    """Run all three significance gates and return a structured verdict.

    Args:
        metrics:      Summary metrics dict from the backtest job.  Expected keys:
                        average_trade_return, trade_return_std, trade_count,
                        sharpe (annualized), avg_test_sharpe (from walk-forward).
        trial_count:  Total trials run for this strategy family (from JSONL obs count).
        bar_returns:  Full OOS bar-level return series for block bootstrap.
                      If None or fewer than 4 bars, bootstrap gate is skipped.
        n_bootstrap:  Number of bootstrap paths.

    Returns:
        {
          "pass": bool,
          "gates": {
            "tstat": {"value": float, "threshold": 2.0, "pass": bool},
            "dsr":   {"value": float, "threshold": 0.5,  "pass": bool},
            "bootstrap": {"pvalue": float, "threshold": 0.05, "pass": bool, "skipped": bool},
          },
          "reasons": list[str],
        }
    """
    reasons: list[str] = []

    # --- t-stat gate ---
    mean_ret = float(metrics.get("average_trade_return") or 0.0)
    std_ret = float(metrics.get("trade_return_std") or 0.0)
    n_trades = int(metrics.get("trade_count") or 0)
    tstat = per_trade_tstat(mean_ret, std_ret, n_trades)
    tstat_pass = tstat >= _TSTAT_GATE
    if not tstat_pass:
        reasons.append(f"per-trade t-stat {tstat:.2f} < {_TSTAT_GATE} (n={n_trades})")

    # --- DSR gate ---
    sharpe = float(metrics.get("avg_test_sharpe") or metrics.get("sharpe") or 0.0)
    # Use OOS bar count proxy: trade_count * avg_bars_per_trade would be ideal;
    # fall back to a conservative 2×trade_count for now.
    n_obs = max(n_trades * 2, 2)
    dsr = deflated_sharpe_ratio(
        observed_sharpe=sharpe,
        n_trials=max(trial_count, 1),
        n_obs=n_obs,
    )
    dsr_pass = dsr > _DSR_GATE
    if not dsr_pass:
        reasons.append(f"DSR {dsr:.3f} ≤ {_DSR_GATE} (trials={trial_count}, sharpe={sharpe:.2f})")

    # --- Block bootstrap gate ---
    bootstrap_skipped = not bar_returns or len(bar_returns) < 4
    if bootstrap_skipped:
        bootstrap_pvalue = 1.0
        bootstrap_pass = True  # skipped gates do not block
    else:
        bootstrap_pvalue = block_bootstrap_pvalue(bar_returns, n_permutations=n_bootstrap)
        bootstrap_pass = bootstrap_pvalue < _PVALUE_GATE
        if not bootstrap_pass:
            reasons.append(
                f"block-bootstrap p-value {bootstrap_pvalue:.3f} ≥ {_PVALUE_GATE}"
            )

    overall = tstat_pass and dsr_pass and bootstrap_pass

    return {
        "pass": overall,
        "gates": {
            "tstat": {"value": tstat, "threshold": _TSTAT_GATE, "pass": tstat_pass},
            "dsr": {"value": dsr, "threshold": _DSR_GATE, "pass": dsr_pass},
            "bootstrap": {
                "pvalue": bootstrap_pvalue,
                "threshold": _PVALUE_GATE,
                "pass": bootstrap_pass,
                "skipped": bootstrap_skipped,
            },
        },
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sharpe(returns: list[float]) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    sd = math.sqrt(variance)
    return mean / sd if sd > 0 else 0.0


def _circular_block_resample(
    returns: list[float], block_length: int, target_n: int, rng: random.Random
) -> list[float]:
    n = len(returns)
    resampled: list[float] = []
    while len(resampled) < target_n:
        start = rng.randrange(n)
        block = [returns[(start + i) % n] for i in range(block_length)]
        resampled.extend(block)
    return resampled[:target_n]


def _norm_cdf(z: float) -> float:
    """Standard normal CDF."""
    return _STD_NORM.cdf(z)


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    return _STD_NORM.inv_cdf(p)
