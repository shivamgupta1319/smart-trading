"""Multiple-testing tests -- the headline is `test_hundred_noise_strategies_yield_no_discoveries`.

That test IS the component's reason to exist: run the correction on the earlier apps' exact failure mode (a
pile of pure-noise strategies) and prove it reports nothing. The rest pins the mathematical
properties the repo prefers over transcribed magic numbers: the expected-max-Sharpe asymptotic,
monotone deflation in N, PSR reducing to the plain case at N=1, and BH agreeing bit-for-bit with
scipy's reference implementation.
"""

from __future__ import annotations

import numpy as np
import pytest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_stats import (  # noqa: E402
    DSR_THRESHOLD,
    benjamini_hochberg,
    bh_adjusted,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    psr_pvalue,
    sharpe_ratio,
    skew_kurtosis,
)


def normal_returns(rng, n, mean=0.0, sd=0.01):
    return rng.normal(mean, sd, size=n)


class TestSharpeAndMoments:
    def test_sharpe_is_mean_over_sample_std(self):
        r = np.array([0.01, -0.01, 0.02, 0.00, 0.03])
        assert sharpe_ratio(r) == pytest.approx(r.mean() / r.std(ddof=1))

    def test_zero_variance_is_an_error_not_infinity(self):
        with pytest.raises(ValueError, match="zero variance"):
            sharpe_ratio(np.ones(10))

    def test_normal_returns_are_symmetric_and_mesokurtic(self):
        rng = np.random.default_rng(0)
        skew, kurt = skew_kurtosis(normal_returns(rng, 200_000))
        assert abs(skew) < 0.05  # ~0 for a normal
        assert abs(kurt - 3.0) < 0.1  # non-excess kurtosis of a normal is 3


class TestExpectedMaxSharpe:
    def test_single_trial_has_nothing_to_deflate(self):
        assert expected_max_sharpe(sharpe_variance=1.0, n_trials=1) == 0.0

    def test_more_trials_raise_the_bar(self):
        vals = [expected_max_sharpe(1.0, n) for n in (2, 10, 100, 1000)]
        assert vals == sorted(vals)  # monotone increasing in N

    def test_tracks_the_sqrt_2_ln_n_asymptotic(self):
        # The Gumbel estimate sits a little BELOW the crude sqrt(2 ln N) bound, same order.
        for n in (100, 1000, 10000):
            emax = expected_max_sharpe(1.0, n)
            crude = np.sqrt(2 * np.log(n))
            assert 0.6 * crude < emax < crude

    def test_scales_with_the_spread_of_trial_sharpes(self):
        assert expected_max_sharpe(4.0, 100) == pytest.approx(2 * expected_max_sharpe(1.0, 100))


class TestProbabilisticSharpe:
    def test_zero_edge_gives_half(self):
        # SR exactly 0 vs benchmark 0 -> P(true SR > 0) = 0.5.
        assert probabilistic_sharpe_ratio(0.0, n_obs=100, skew=0.0, kurtosis=3.0) == pytest.approx(
            0.5
        )

    def test_more_data_sharpens_the_same_edge(self):
        near = probabilistic_sharpe_ratio(0.1, 50, 0.0, 3.0)
        far = probabilistic_sharpe_ratio(0.1, 5000, 0.0, 3.0)
        assert far > near  # same Sharpe, more observations -> more confident it is real

    def test_negative_skew_and_fat_tails_lower_confidence(self):
        clean = probabilistic_sharpe_ratio(0.2, 500, 0.0, 3.0)
        ugly = probabilistic_sharpe_ratio(0.2, 500, -1.0, 8.0)
        assert ugly < clean  # the same Sharpe is less trustworthy on ugly returns


class TestDeflatedSharpe:
    def test_a_single_strong_strategy_is_a_discovery(self):
        # N=1 (no selection), a genuinely strong, long, clean track record.
        rng = np.random.default_rng(1)
        r = normal_returns(rng, 2000, mean=0.001, sd=0.01)  # per-obs Sharpe ~0.1
        dsr = deflated_sharpe_ratio(r, trial_sharpes=[sharpe_ratio(r)])
        assert dsr > DSR_THRESHOLD

    def test_the_same_strategy_stops_being_a_discovery_once_it_was_the_best_of_many(self):
        rng = np.random.default_rng(2)
        r = normal_returns(rng, 2000, mean=0.001, sd=0.01)
        sr = sharpe_ratio(r)
        alone = deflated_sharpe_ratio(r, trial_sharpes=[sr])
        # The very same track record, but now the best of 500 trials with a real spread of Sharpes.
        spread = list(np.random.default_rng(3).normal(0.0, 0.06, size=500))
        selected = deflated_sharpe_ratio(r, trial_sharpes=[sr, *spread])
        assert selected < alone  # deflation costs it exactly its selection advantage

    def test_dsr_never_flags_the_luckiest_of_a_hundred_noise_strategies(self):
        """THE test. 100 pure-noise strategies (true edge zero), pick the luckiest, deflate by all
        100 trials -- the DSR must not call it real. This is the earlier apps' exact mistake, caught. Run over
        many seeds because the claim is robustness, not one lucky draw."""
        for seed in range(12):
            rng = np.random.default_rng(seed)
            series = [normal_returns(rng, 750, mean=0.0, sd=0.01) for _ in range(100)]
            sharpes = [sharpe_ratio(s) for s in series]
            best = int(np.argmax(sharpes))
            dsr = deflated_sharpe_ratio(series[best], trial_sharpes=sharpes)
            assert dsr <= DSR_THRESHOLD, f"seed {seed}: DSR falsely flagged noise ({dsr:.3f})"

    def test_bh_controls_the_false_discovery_rate_on_noise(self):
        """BH is the cross-check, and it controls the *rate*, not the count -- on 100 pure nulls it
        rejects >=1 about q of the time, by design. So the honest claim is the rate: over many
        batches the per-test false-discovery fraction stays well under q=0.10, and the share of
        batches with any discovery hovers around q (not above it)."""
        rng = np.random.default_rng(1234)
        batches = 150
        total_rejections = 0
        batches_with_discovery = 0
        for _ in range(batches):
            series = [normal_returns(rng, 500, mean=0.0, sd=0.01) for _ in range(100)]
            pvals = np.array([psr_pvalue(s) for s in series])
            rejected = benjamini_hochberg(pvals, q=0.10)
            total_rejections += int(rejected.sum())
            batches_with_discovery += int(rejected.any())
        per_test_fdr = total_rejections / (batches * 100)
        batch_rate = batches_with_discovery / batches
        assert per_test_fdr < 0.02, f"per-test FDR {per_test_fdr:.4f} too high"
        assert batch_rate < 0.18, f"batch discovery rate {batch_rate:.3f} exceeds q with margin"


class TestBenjaminiHochberg:
    def test_matches_scipy_reference(self):
        scipy_stats = pytest.importorskip("scipy.stats")
        rng = np.random.default_rng(7)
        # A mix: some genuine tiny p-values, plus uniform noise.
        pvals = np.concatenate([rng.uniform(0, 1e-4, 5), rng.uniform(0, 1, 95)])
        ours = bh_adjusted(pvals)
        ref = scipy_stats.false_discovery_control(pvals, method="bh")
        np.testing.assert_allclose(ours, ref, rtol=1e-12, atol=1e-12)

    def test_rejection_mask_agrees_with_adjusted_values(self):
        rng = np.random.default_rng(8)
        pvals = np.concatenate([rng.uniform(0, 1e-3, 8), rng.uniform(0, 1, 92)])
        q = 0.10
        mask = benjamini_hochberg(pvals, q)
        assert np.array_equal(mask, bh_adjusted(pvals) <= q)

    def test_all_null_rejects_nothing(self):
        rng = np.random.default_rng(9)
        pvals = rng.uniform(0, 1, 1000)  # pure noise
        # BH controls FDR; on pure uniform p-values it should reject ~nothing at q=0.10.
        assert benjamini_hochberg(pvals, q=0.10).sum() <= 1

    def test_a_clear_signal_is_rejected(self):
        pvals = np.array([1e-8, 0.9, 0.8, 0.7, 0.6])  # one obvious discovery
        mask = benjamini_hochberg(pvals, q=0.10)
        assert mask[0] and not mask[1:].any()

    def test_invalid_q_raises(self):
        with pytest.raises(ValueError, match="q must be in"):
            benjamini_hochberg(np.array([0.01, 0.5]), q=1.5)
