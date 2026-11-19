"""Luck correction: is a strategy's result more than testing many strategies would produce
by chance?

Brought over unchanged in substance from the July rebuild (`trading/research/stats.py`).
This product tests 28 strategies on dozens of stocks; with that many tries some will look
good by luck alone. Two tools answer "which results survive that":

**Deflated Sharpe Ratio (Bailey & López de Prado)** -- the primary. It answers the exact question
the search created: *given N trials with this spread of Sharpes, on a sample this short and this
fat-tailed, is the best one still real?* It deflates the Sharpe threshold for the number of trials
(more trials ⇒ a higher bar), then scores the strategy's Sharpe against that threshold while
correcting for sample length, skew and kurtosis -- all of which bite hard on a short Indian sample.
Accept iff `DSR > 0.95`.

**Benjamini–Hochberg FDR** -- the cross-check for *which* cells are winners. More powerful than
Bonferroni and valid under the positive dependence that correlated equity strategies exhibit. Our
BH is implemented here in numpy (runtime stays dependency-light) and cross-checked against
`scipy.stats.false_discovery_control` in the tests.

**N is the number of *strategies*, not cells. The hypothesis under
test is the strategy; aggregate its cells to one equal-weight return series and set N = strategies ×
variants tried. The trials ledger (`research_trials.py`) is what makes that N auditable rather than a
number someone can quietly shrink.

The component's own proof is a test, not a claim: **100 pure-noise strategies must yield zero
discoveries at q=0.10** -- i.e. this correction catches the failure of picking winners from many untested tries.

No magic numbers are transcribed from papers here (the repo's rule -- run it, don't quote prose);
the tests pin the *mathematical* properties instead: the expected-max-Sharpe asymptotic, monotone
deflation in N, PSR reducing to the plain case at N=1, and BH agreeing with scipy.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np

EULER_MASCHERONI = 0.5772156649015329
DSR_THRESHOLD = 0.95  # accept a strategy iff its Deflated Sharpe exceeds this
_NORM = NormalDist()


def sharpe_ratio(returns) -> float:
    """Per-observation Sharpe (mean / sample-std, ddof=1). NOT annualised -- annualisation is a
    separate, reversible scaling and the DSR machinery works in per-observation units."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        raise ValueError("sharpe_ratio needs >= 2 observations")
    sd = r.std(ddof=1)
    if sd == 0:
        raise ValueError("returns have zero variance: Sharpe is undefined")
    return float(r.mean() / sd)


def skew_kurtosis(returns) -> tuple[float, float]:
    """Sample skewness and NON-excess kurtosis (normal ⇒ 3), population central moments -- the
    convention scipy.stats.skew / kurtosis(fisher=False) use, which is what the PSR formula wants.
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        raise ValueError("skew_kurtosis needs >= 2 observations")
    d = r - r.mean()
    m2 = np.mean(d**2)
    if m2 == 0:
        raise ValueError("returns have zero variance: skew/kurtosis are undefined")
    m3 = np.mean(d**3)
    m4 = np.mean(d**4)
    return float(m3 / m2**1.5), float(m4 / m2**2)


def expected_max_sharpe(sharpe_variance: float, n_trials: int) -> float:
    """The Sharpe you should *expect* the best of `n_trials` null strategies to show, purely from
    selection (SR* in the DSR). Grows with the spread of trial Sharpes and with N. N=1 ⇒ 0: with
    no selection there is nothing to deflate.

    E[max SR] ≈ √V · [ (1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e)) ]  (γ = Euler–Mascheroni).
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if sharpe_variance < 0:
        raise ValueError(f"sharpe_variance must be >= 0, got {sharpe_variance}")
    if n_trials == 1:
        return 0.0
    g = EULER_MASCHERONI
    z1 = _NORM.inv_cdf(1.0 - 1.0 / n_trials)
    z2 = _NORM.inv_cdf(1.0 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(sharpe_variance) * ((1.0 - g) * z1 + g * z2))


def probabilistic_sharpe_ratio(
    sharpe: float, n_obs: int, skew: float, kurtosis: float, benchmark: float = 0.0
) -> float:
    """P(true Sharpe > `benchmark`) given the estimate, corrected for sample length and the
    non-normality (skew, kurtosis) of the returns. `benchmark=0` is the plain PSR; feed the
    expected-max Sharpe to get the DSR."""
    if n_obs < 2:
        raise ValueError("PSR needs >= 2 observations")
    variance = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    if variance <= 0:
        raise ValueError(
            f"PSR denominator variance is non-positive ({variance:.4g}); "
            "the estimator is invalid for these skew/kurtosis/Sharpe values"
        )
    z = (sharpe - benchmark) * np.sqrt(n_obs - 1) / np.sqrt(variance)
    return float(_NORM.cdf(z))


def deflated_sharpe_ratio(returns, trial_sharpes) -> float:
    """The Deflated Sharpe Ratio of a strategy whose returns are `returns`, selected from a search
    whose per-trial Sharpes are `trial_sharpes` (length N, the trial count). Accept iff it exceeds
    `DSR_THRESHOLD`."""
    r = np.asarray(returns, dtype=float)
    ts = np.asarray(trial_sharpes, dtype=float)
    n_trials = ts.size
    if n_trials < 1:
        raise ValueError("deflated_sharpe_ratio needs >= 1 trial Sharpe")
    variance = float(ts.var(ddof=1)) if n_trials > 1 else 0.0
    sr_star = expected_max_sharpe(variance, n_trials)
    sr = sharpe_ratio(r)
    skew, kurt = skew_kurtosis(r)
    return probabilistic_sharpe_ratio(sr, r.size, skew, kurt, benchmark=sr_star)


def psr_pvalue(returns) -> float:
    """One-sided p-value for H0: true Sharpe <= 0, from the plain PSR. Small ⇒ the strategy's
    positive Sharpe is unlikely to be luck (before any multiple-testing correction)."""
    r = np.asarray(returns, dtype=float)
    sr = sharpe_ratio(r)
    skew, kurt = skew_kurtosis(r)
    return 1.0 - probabilistic_sharpe_ratio(sr, r.size, skew, kurt, benchmark=0.0)


def benjamini_hochberg(pvalues, q: float) -> np.ndarray:
    """The BH rejection mask at FDR level `q`: True where the hypothesis is rejected (a discovery).

    Reject the k hypotheses with the smallest p-values, where k is the largest rank for which
    p_(k) <= (k/m)·q. Everything at or below that p-value is rejected (the step-up rule).
    """
    p = np.asarray(pvalues, dtype=float)
    m = p.size
    if m == 0:
        return np.zeros(0, dtype=bool)
    if not 0 < q < 1:
        raise ValueError(f"q must be in (0, 1), got {q}")
    order = np.argsort(p, kind="stable")
    ranked = p[order]
    thresholds = q * np.arange(1, m + 1) / m
    below = ranked <= thresholds
    if not below.any():
        return np.zeros(m, dtype=bool)
    kmax = np.max(np.flatnonzero(below))  # largest passing rank (0-indexed)
    return p <= ranked[kmax]


def bh_adjusted(pvalues) -> np.ndarray:
    """BH-adjusted p-values (q-values). Reject where the adjusted value <= q. Matches
    `scipy.stats.false_discovery_control(pvalues, method='bh')` -- the tests pin that."""
    p = np.asarray(pvalues, dtype=float)
    m = p.size
    if m == 0:
        return np.zeros(0, dtype=float)
    order = np.argsort(p, kind="stable")
    ranked = p[order]
    scaled = ranked * m / np.arange(1, m + 1)
    # Enforce monotone non-decreasing q-values by a right-to-left running minimum.
    adjusted = np.minimum.accumulate(scaled[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    out = np.empty(m, dtype=float)
    out[order] = adjusted
    return out
