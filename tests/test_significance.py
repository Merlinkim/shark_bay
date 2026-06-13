"""Tests for app/significance.py — Statistical Significance Framework."""
import math
import random

import pytest

from app.significance import (
    _norm_cdf,
    _norm_ppf,
    block_bootstrap_pvalue,
    deflated_sharpe_ratio,
    per_trade_tstat,
    significance_check,
)


# ---------------------------------------------------------------------------
# per_trade_tstat
# ---------------------------------------------------------------------------

class TestPerTradeTstat:
    def test_positive_mean_yields_positive_tstat(self):
        t = per_trade_tstat(mean_return=0.5, std_return=1.0, n=100)
        assert t == pytest.approx(5.0, rel=1e-6)

    def test_zero_mean_yields_zero(self):
        assert per_trade_tstat(0.0, 1.0, 100) == 0.0

    def test_zero_std_yields_zero(self):
        assert per_trade_tstat(1.0, 0.0, 100) == 0.0

    def test_single_trade_yields_zero(self):
        assert per_trade_tstat(1.0, 0.5, 1) == 0.0

    def test_gate_threshold_example(self):
        # mean=0.2, std=1.0, n=100 → t=2.0 exactly
        t = per_trade_tstat(0.2, 1.0, 100)
        assert t == pytest.approx(2.0, rel=1e-6)

    def test_negative_mean_negative_tstat(self):
        t = per_trade_tstat(-0.3, 1.0, 100)
        assert t < 0


# ---------------------------------------------------------------------------
# deflated_sharpe_ratio
# ---------------------------------------------------------------------------

class TestDeflatedSharpe:
    def test_high_sharpe_single_trial_near_one(self):
        dsr = deflated_sharpe_ratio(observed_sharpe=3.0, n_trials=1, n_obs=1000)
        assert dsr > 0.95

    def test_many_trials_lower_dsr(self):
        # n_obs=30 keeps std_sr large enough that SR* depends meaningfully on trial count
        dsr_few = deflated_sharpe_ratio(observed_sharpe=0.5, n_trials=5, n_obs=30)
        dsr_many = deflated_sharpe_ratio(observed_sharpe=0.5, n_trials=500, n_obs=30)
        assert dsr_few > dsr_many

    def test_zero_sharpe_below_half(self):
        # Zero Sharpe should not survive any trial count
        dsr = deflated_sharpe_ratio(observed_sharpe=0.0, n_trials=10, n_obs=500)
        assert dsr < 0.5

    def test_insufficient_obs_returns_zero(self):
        assert deflated_sharpe_ratio(1.5, n_trials=10, n_obs=1) == 0.0

    def test_returns_probability_in_unit_interval(self):
        for sr in [-1.0, 0.0, 0.5, 1.0, 2.0, 3.0]:
            dsr = deflated_sharpe_ratio(sr, n_trials=10, n_obs=200)
            assert 0.0 <= dsr <= 1.0


# ---------------------------------------------------------------------------
# block_bootstrap_pvalue
# ---------------------------------------------------------------------------

class TestBlockBootstrap:
    def _constant_returns(self, n=200, value=0.01):
        return [value] * n

    def _random_returns(self, n=200, seed=0):
        rng = random.Random(seed)
        return [rng.gauss(0, 1) for _ in range(n)]

    def test_strong_positive_drift_low_pvalue(self):
        # Series with clear positive drift and low noise → almost no resample
        # produces a non-positive Sharpe → p ≈ 0 → passes the gate.
        rng = random.Random(7)
        returns = [0.002 + rng.gauss(0, 0.001) for _ in range(300)]
        p = block_bootstrap_pvalue(returns, n_permutations=500, seed=1)
        assert p < 0.05

    def test_zero_mean_returns_high_pvalue(self):
        # Symmetric zero-mean noise → roughly half of resamples have Sharpe ≤ 0
        # → p well above the 0.05 gate → fails (correctly).
        rng = random.Random(3)
        returns = [rng.gauss(0, 1) for _ in range(300)]
        p = block_bootstrap_pvalue(returns, n_permutations=500, seed=42)
        assert p > 0.05

    def test_insufficient_data_returns_one(self):
        assert block_bootstrap_pvalue([0.1, 0.2, 0.3]) == 1.0

    def test_seeded_reproducibility(self):
        returns = [0.01 * i for i in range(100)]
        p1 = block_bootstrap_pvalue(returns, n_permutations=50, seed=99)
        p2 = block_bootstrap_pvalue(returns, n_permutations=50, seed=99)
        assert p1 == p2

    def test_different_seeds_may_differ(self):
        returns = [0.01 * (i % 10 - 5) for i in range(100)]
        p1 = block_bootstrap_pvalue(returns, n_permutations=200, seed=1)
        p2 = block_bootstrap_pvalue(returns, n_permutations=200, seed=2)
        # Not guaranteed to differ but a sanity check that both are valid
        assert 0.0 <= p1 <= 1.0
        assert 0.0 <= p2 <= 1.0


# ---------------------------------------------------------------------------
# significance_check (combined gate)
# ---------------------------------------------------------------------------

class TestSignificanceCheck:
    def _passing_metrics(self):
        return {
            "average_trade_return": 0.5,
            "trade_return_std": 1.0,
            "trade_count": 200,
            "sharpe": 2.5,
            "avg_test_sharpe": 2.5,
        }

    def test_strong_strategy_passes_tstat_and_dsr(self):
        result = significance_check(self._passing_metrics(), trial_count=5)
        assert result["gates"]["tstat"]["pass"] is True
        assert result["gates"]["dsr"]["pass"] is True
        # bootstrap is skipped when bar_returns is None
        assert result["gates"]["bootstrap"]["skipped"] is True

    def test_low_trade_count_fails_tstat(self):
        m = self._passing_metrics()
        m["trade_count"] = 5  # too few trades for t ≥ 2
        m["average_trade_return"] = 0.1
        m["trade_return_std"] = 2.0
        result = significance_check(m, trial_count=1)
        assert result["gates"]["tstat"]["pass"] is False

    def test_many_trials_fails_dsr(self):
        # 15 trades → n_obs proxy = 30; SR=0.3 with 500 trials → DSR < 0.5
        m = {
            "average_trade_return": 0.5,
            "trade_return_std": 0.1,   # tstat = 0.5/(0.1/sqrt(15)) ≈ 19 → passes
            "trade_count": 15,
            "sharpe": 0.3,
            "avg_test_sharpe": 0.3,
        }
        result = significance_check(m, trial_count=500)
        assert result["gates"]["dsr"]["pass"] is False

    def test_returns_structured_dict(self):
        result = significance_check(self._passing_metrics())
        assert "pass" in result
        assert "gates" in result
        assert "reasons" in result
        assert set(result["gates"].keys()) == {"tstat", "dsr", "bootstrap"}

    def test_bootstrap_runs_when_bar_returns_provided(self):
        m = self._passing_metrics()
        bar_returns = [0.01] * 200
        result = significance_check(m, trial_count=1, bar_returns=bar_returns)
        assert result["gates"]["bootstrap"]["skipped"] is False
        assert 0.0 <= result["gates"]["bootstrap"]["pvalue"] <= 1.0

    def test_reasons_populated_on_failure(self):
        m = {
            "average_trade_return": -0.1,
            "trade_return_std": 1.0,
            "trade_count": 30,
            "sharpe": -0.5,
            "avg_test_sharpe": -0.5,
        }
        result = significance_check(m, trial_count=100)
        assert result["pass"] is False
        assert len(result["reasons"]) > 0

    def test_zero_metrics_does_not_crash(self):
        result = significance_check({})
        assert isinstance(result["pass"], bool)


# ---------------------------------------------------------------------------
# Internal math helpers
# ---------------------------------------------------------------------------

class TestNormHelpers:
    def test_cdf_at_zero_is_half(self):
        assert _norm_cdf(0.0) == pytest.approx(0.5, abs=1e-6)

    def test_cdf_at_1_96_is_97_5_pct(self):
        assert _norm_cdf(1.96) == pytest.approx(0.975, abs=1e-3)

    def test_ppf_at_half_is_zero(self):
        assert _norm_ppf(0.5) == pytest.approx(0.0, abs=1e-6)

    def test_ppf_is_inverse_of_cdf(self):
        for z in [-2.0, -1.0, 0.0, 1.0, 2.0]:
            assert _norm_ppf(_norm_cdf(z)) == pytest.approx(z, abs=1e-4)
