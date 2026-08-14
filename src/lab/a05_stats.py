"""A05 statistics — a per-target empirical false-alarm probability for the hunt.

A04 measured a survey-wide false-alarm *floor*: the max SDE seen across the
noise targets of one run. That floor answers "is the threshold above the noise
of THIS sample" and nothing more — it says nothing about how likely *this
particular target*, with its own cadence gaps and its own variability, is to
produce its observed SDE by chance. A05 grades candidates, so every graded
candidate needs its own null distribution, built from its own light curve.

### The null: permute the flux, rerun the whole blind search

The statistic being calibrated is not "box power at the detected period" — it
is ``max over the entire period grid of the SDE``, because that maximum is what
the blind search reports. A null that permutes the flux and re-runs only the
detected period would ignore the look-elsewhere effect of the 3000-period grid
and understate the FAP badly. So each permutation replays the *full* search:
B permuted copies of the detrended flux, each scanned over the same
frequency-uniform grid ``blind_search`` uses, each reduced to its own
``(max - median)/std`` SDE — the exact convention of :func:`lab.a04.blind_search`,
applied to that permutation's OWN periodogram.

### Why the batch is cheap: the binning is a property of (t, P), not of f

At a trial period P, the phase-bin index of every cadence depends only on the
time stamps and P. Permuting the flux never moves a cadence between bins — it
only changes *which flux value* sits at each cadence. So one binning serves all
B permutation columns: sort the cadences by bin once per period, segment-sum
the reordered ``(N, B)`` flux matrix (``np.add.reduceat``), and run the
box-width scan as a cumulative sum along the bin axis with the same doubled-
array phase-wrap handling as :func:`lab.a04.bls_power`. Every arithmetic step
mirrors ``bls_power``'s op-for-op, so a batched column is *bitwise* the
periodogram ``blind_search`` would have produced for that permuted flux — the
correctness anchor test in ``tests/test_a05_stats.py`` asserts exact equality.

### Two shuffles, and which one grades

An iid shuffle destroys ALL time structure, including the red noise (stellar
variability, momentum dumps, scattered light) that survives detrending. Real
TESS residuals are correlated on hours, so an iid null is too clean and its
FAP too small. The block shuffle (contiguous blocks of ``BLOCK_DAYS`` of
cadences, order permuted, interiors intact) preserves short-range
autocorrelation and yields a more honest — larger — FAP on red targets. Both
schemes are computed and stored; **the graded FAP is the more conservative
(larger) of the two**.

### Declared anti-conservatism: the null is built after detrending

.. _permute-after-detrend:

The permutations are of the *detrended* flux. Detrending was fit to the data,
so it has absorbed some genuinely random low-frequency variance; the permuted
copies are therefore slightly quieter than a fresh realisation of the same
star, and every FAP from this module is *anti-conservative by construction* at
some level. This is declared, not hidden: :data:`NULL_CAVEAT` carries the
sentence verbatim so the hunt receipt can quote it, and the block scheme plus
the conservative-of-two rule are the partial compensation.

### Graded vs reported — the contract split

* **Graded**: ``fap_empirical = (1 + k) / (B + 1)`` where k counts null maxima
  ``>= observed``. It is a finite-sample VALID bound (Davison & Hinkley's
  add-one rule): it can never claim a smaller probability than B permutations
  can support (min 1/(B+1)), and it needs no distributional assumption.
* **Reported, never graded**: the Gumbel tail extrapolation. B=256 permutations
  cannot see below ~4e-3, so the fitted extreme-value tail is the only way to
  *report* a smaller number — but it is a model, and it must first pass a bulk
  calibration against the very sample it was fit to, or the whole fit is
  refused (``None``) and the receipt's gumbel block is nulled.
* **Heuristic, never graded**: :func:`triage_level`, the compute-bounding line
  that decides who pays for the bootstrap at all.
"""
from __future__ import annotations

import math

import numpy as np

from . import a04

#: Permutations per target. (1+k)/(B+1) floors the graded FAP at 1/257 ≈ 3.9e-3,
#: which is deliberately coarse: the survey grades "not explainable as noise at
#: the level B can resolve", and leaves smaller numbers to the reported tail.
DEFAULT_B = 256

#: Block length for the block shuffle, in days of cadences. TESS 2-minute data
#: carries red noise (pulsation tails, scattered-light ramps) correlated on
#: hours; ~0.75 d ≈ 540 cadences keeps that structure inside a block so the
#: null retains it. Inside the 0.5–1 d bracket argued in the A05 plan.
BLOCK_DAYS = 0.75

#: The two null-scheme names. Receipt schema stores both, grades the max.
SCHEMES = ("iid", "block")

#: Quotable declaration of the permute-after-detrend anti-conservatism — the
#: receipt ships this sentence verbatim (see module docstring).
NULL_CAVEAT = (
    "Permutations are of the detrended flux: the detrend fit has absorbed some "
    "genuinely random low-frequency variance, so the null is slightly quieter "
    "than a fresh realisation of the star and every FAP here is "
    "anti-conservative by construction at some level; the block scheme and the "
    "conservative-of-two grading rule are partial, not full, compensation."
)

#: Euler–Mascheroni constant — mean of a standard Gumbel is MU + EULER*BETA,
#: which seeds the method-of-moments initialisation of the MLE.
EULER_MASCHERONI = 0.5772156649015329

#: Gumbel fit refuses ensembles smaller than this — the bulk-calibration check
#: below has no power on a handful of points.
GUMBEL_MIN_SAMPLES = 32

#: 1-D Newton iteration budget and convergence tolerance for the Gumbel MLE
#: profile equation in beta.
GUMBEL_NEWTON_MAX_ITER = 100
GUMBEL_NEWTON_TOL = 1e-12

#: Bulk calibration tolerance: the fitted 90th percentile must sit within this
#: many fitted BETAs of the empirical 90th percentile. Sized to ~3 standard
#: errors of an n=256 empirical 90th percentile under a true Gumbel (se ≈ 0.2
#: beta), so a genuine Gumbel sample passes and a distribution the model cannot
#: describe does not.
GUMBEL_Q90_TOL_BETAS = 0.6

#: Second bulk guard: max |fitted CDF − ecdf| over the sample (a KS distance
#: against the FITTED model). 0.12 ≈ the 1.9/sqrt(256) asymptotic ~0.1% point;
#: parameter estimation only shrinks the statistic (Lilliefors), so a true
#: Gumbel passes with slack while bimodal or heavy-shouldered ensembles fail.
GUMBEL_BULK_KS_MAX = 0.12

#: The two measured false-alarm-floor points the triage line is drawn through:
#: (n noise targets searched, max SDE seen). n=22 is the A04 graded run,
#: n=153 the 2026-08-14 discovery pilot.
TRIAGE_FLOOR_POINTS = ((22, 6.6), (153, 7.65))

#: mu, beta of the triage line MU + BETA*ln(n), solved exactly through the two
#: floor points above (two equations, two unknowns).
TRIAGE_BETA = (TRIAGE_FLOOR_POINTS[1][1] - TRIAGE_FLOOR_POINTS[0][1]) / (
    math.log(TRIAGE_FLOOR_POINTS[1][0]) - math.log(TRIAGE_FLOOR_POINTS[0][0]))
TRIAGE_MU = TRIAGE_FLOOR_POINTS[0][1] - TRIAGE_BETA * math.log(
    TRIAGE_FLOOR_POINTS[0][0])

#: Safety margin SUBTRACTED from the extrapolated floor: the triage line sits a
#: full SDE unit below the expected noise ceiling, so the error mode is "paid
#: for a bootstrap it didn't need", never "a marginal candidate skipped its FAP".
TRIAGE_SAFETY_MARGIN = 1.0

#: Asymptotic one-sample Kolmogorov–Smirnov 5% coefficient: the critical
#: distance is KS_CRITICAL_COEFF / sqrt(n). Asymptotic form, sized for the
#: n ≈ 50 uniformity control ensemble the receipt schema names.
KS_CRITICAL_COEFF = 1.358


class A05StatsError(RuntimeError):
    pass


# ------------------------------------------------------------- permutations --

def permutation_indices(t: np.ndarray, B: int = DEFAULT_B,
                        scheme: str = "iid", seed: int = 0) -> np.ndarray:
    """The (B, N) permutation index matrix for one target — the null's identity.

    Exposed as a public function (not an internal detail) for one reason: the
    correctness anchor test feeds THESE EXACT permutations down both paths —
    each row through plain :func:`lab.a04.blind_search`, the whole matrix
    through :func:`batched_null` — and asserts the SDEs agree bitwise. A null
    whose permutations cannot be replayed cannot be audited.

    * ``iid``: each row an independent full shuffle. Destroys all time
      structure, including real red noise — the clean but anti-conservative null.
    * ``block``: cadences are cut into contiguous blocks of ``BLOCK_DAYS``
      worth of the median cadence (last block may run short) and the BLOCK
      ORDER is shuffled, interiors intact. Autocorrelation shorter than a block
      survives into the null, which is what makes it the conservative scheme
      on red targets.

    Deterministic in ``seed`` (one ``default_rng(seed)`` consumed row by row),
    so a receipt that stores ``(B, scheme, seed)`` pins the null exactly.
    """
    t = np.asarray(t, dtype=float)
    n = t.size
    if n < 2:
        raise A05StatsError("need at least 2 cadences to permute")
    rng = np.random.default_rng(seed)
    out = np.empty((B, n), dtype=np.intp)
    if scheme == "iid":
        for b in range(B):
            out[b] = rng.permutation(n)
    elif scheme == "block":
        cadence = float(np.median(np.diff(np.sort(t))))
        if not np.isfinite(cadence) or cadence <= 0:
            raise A05StatsError("cannot derive a cadence for block shuffling")
        block_len = max(1, int(round(BLOCK_DAYS / cadence)))
        starts = np.arange(0, n, block_len)
        blocks = [np.arange(s, min(s + block_len, n)) for s in starts]
        for b in range(B):
            order = rng.permutation(len(blocks))
            out[b] = np.concatenate([blocks[j] for j in order])
    else:
        raise A05StatsError(f"unknown scheme {scheme!r}; expected one of {SCHEMES}")
    return out


# ------------------------------------------------------- the batched search --

def _batched_max_power(t: np.ndarray, f_cols: np.ndarray, periods: np.ndarray,
                       bins: int = a04.BINS, min_width: int = 3,
                       max_frac: float = 0.15) -> np.ndarray:
    """(n_periods, B) best box power — ``a04.bls_power`` replayed over columns.

    Every arithmetic step is deliberately op-for-op identical to
    :func:`lab.a04.bls_power` so each column is BITWISE the periodogram the
    scalar path would produce:

    * the phase-bin index is computed ONCE per trial period and serves all B
      columns — the structural fact that makes the batch cheap: permuting the
      flux never moves a cadence between bins;
    * binned sums use the very same ``np.bincount(idx, weights=...)`` call as
      the scalar path, per column (``np.add.reduceat`` over a stable sort was
      measured to differ from bincount in the last float bits, which is enough
      to break the correctness anchor). ``f_cols`` is Fortran-ordered so each
      column is a contiguous view and the bincount weights walk memory linearly;
    * per-column totals via 1-D ``.sum()`` on the contiguous column, matching
      the scalar ``sums.sum()`` pairwise summation;
    * the doubled-array cumulative sums, the ``n_in > 5`` occupancy gate, the
      ``maximum(n, 1)`` guarded divisions, and the ``depth * sqrt(n_in)``
      power are the same expressions with the bin axis broadcast over B.
    """
    n, B = f_cols.shape
    best = np.zeros((len(periods), B))
    zero_row = np.zeros((1, B))
    w_hi = max(min_width + 1, int(bins * max_frac))
    for k, period in enumerate(periods):
        phase = np.mod(t, period) / period
        idx = np.minimum((phase * bins).astype(int), bins - 1)
        counts = np.bincount(idx, minlength=bins)
        n_total = counts.sum()
        if n_total == 0:
            continue
        sums = np.empty((bins, B), order="F")
        total = np.empty(B)
        for b in range(B):
            col = np.bincount(idx, weights=f_cols[:, b], minlength=bins)
            sums[:, b] = col
            total[b] = col.sum()
        cs = np.concatenate(
            [zero_row, np.cumsum(np.concatenate([sums, sums], axis=0), axis=0)])
        cc = np.r_[0, np.cumsum(np.r_[counts, counts])]
        acc = np.zeros(B)
        for width in range(min_width, w_hi):
            n_in = cc[width:width + bins] - cc[:bins]
            ok = n_in > 5
            if not ok.any():
                continue
            s_in = cs[width:width + bins] - cs[:bins]
            s_out = total[None, :] - s_in
            n_out = n_total - n_in
            with np.errstate(invalid="ignore", divide="ignore"):
                mu_in = np.where(ok[:, None],
                                 s_in / np.maximum(n_in, 1)[:, None], 1.0)
                mu_out = np.where((ok & (n_out > 0))[:, None],
                                  s_out / np.maximum(n_out, 1)[:, None], 1.0)
                depth = mu_out - mu_in
                power = np.where(ok[:, None] & (depth > 0),
                                 depth * np.sqrt(np.maximum(n_in, 0))[:, None],
                                 0.0)
            np.maximum(acc, power.max(axis=0), out=acc)
        best[k] = acc
    return best


def batched_null(t: np.ndarray, f: np.ndarray, B: int = DEFAULT_B,
                 scheme: str = "iid", seed: int = 0, *,
                 p_lo: float = a04.P_LO, p_hi: float = a04.P_HI,
                 n_periods: int = a04.N_PERIODS,
                 permutations: np.ndarray | None = None) -> np.ndarray:
    """B max-SDE draws from the permutation null of the FULL blind search.

    Returns a ``(B,)`` array: for each permutation of the detrended flux, the
    maximum SDE that :func:`lab.a04.blind_search` would report on that permuted
    curve over the same frequency-uniform period grid — ``(max - median)/std``
    of that permutation's OWN periodogram, never a shared normalisation. These
    are the ``raw_maxima`` the hunt receipt stores per scheme, so ``check_a05``
    can recompute every FAP without trust.

    The grid replicates ``blind_search`` exactly, including the
    baseline/``MIN_TRANSITS`` cap on ``p_hi`` — a null built on a different
    grid than the observed statistic calibrates nothing.

    ``t, f`` must be the SORTED, DETRENDED curve (what :func:`lab.a04.detrend`
    returns) — see :data:`NULL_CAVEAT` for what building the null after
    detrending costs. ``permutations`` overrides the internally generated
    matrix (rows = permutations) for audit replays.
    """
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    if p_lo <= 0 or p_hi <= p_lo:
        raise a04.A04Error("period range must satisfy 0 < p_lo < p_hi")
    baseline = float(t.max() - t.min())
    p_hi = min(p_hi, baseline / a04.MIN_TRANSITS) if baseline > 0 else p_hi
    if p_hi <= p_lo:
        raise a04.A04Error("baseline too short for the requested period range")
    freqs = np.linspace(1.0 / p_hi, 1.0 / p_lo, n_periods)
    periods = 1.0 / freqs
    if permutations is None:
        permutations = permutation_indices(t, B, scheme, seed)
    B = permutations.shape[0]
    f_cols = f[permutations].T          # (N, B) Fortran-order: contiguous columns
    power = _batched_max_power(t, f_cols, periods)
    maxima = np.empty(B)
    for b in range(B):
        col = np.ascontiguousarray(power[:, b])
        j = int(np.argmax(col))
        spread = float(col.std())
        maxima[b] = float((col[j] - np.median(col)) / spread) if spread > 0 else 0.0
    return maxima


# ---------------------------------------------------------------- the grade --

def fap_empirical(observed_sde: float, maxima: np.ndarray) -> float:
    """(1 + k)/(B + 1), k = null maxima >= observed — the ONLY graded number.

    The add-one form counts the observed statistic as one more member of its
    own null (it is exchangeable with the permutations under the null
    hypothesis), which makes the estimate a valid finite-sample bound rather
    than an optimistic point estimate: it can never report below 1/(B+1), and
    a permutation tie counts against the candidate (``>=``, not ``>``).
    """
    m = np.asarray(maxima, dtype=float)
    if m.size == 0:
        raise A05StatsError("empty null — no maxima to compare against")
    k = int(np.count_nonzero(m >= observed_sde))
    return float((1 + k) / (m.size + 1))


# --------------------------------------------- reported tail, never graded ---

def gumbel_fit(maxima: np.ndarray) -> dict | None:
    """Numpy-only Gumbel MLE of the B null maxima — REPORTED, NEVER GRADED.

    The max of a large scan plausibly lives in the Gumbel domain of
    attraction, and a fitted tail is the only way to *report* FAPs below the
    1/(B+1) resolution of the empirical bound. But it is a model, so it must
    first prove it describes the bulk of the very sample it was fit to:

    * the fitted 90th percentile must land within :data:`GUMBEL_Q90_TOL_BETAS`
      fitted betas of the empirical 90th percentile, and
    * the max |fitted CDF − ecdf| over the sample must stay under
      :data:`GUMBEL_BULK_KS_MAX`.

    Fail either and the return is ``None`` — the receipt's gumbel block is
    nulled entirely rather than shipping a tail number from a shape the data
    contradicts (a bimodal ensemble, a pulsator-contaminated null, ...).

    Fit: method-of-moments initialisation (``beta = std*sqrt(6)/pi``,
    ``mu = mean - EULER*beta``), then 1-D Newton on the MLE profile equation
    ``g(beta) = beta - mean(x) + sum(x*w)/sum(w) = 0`` with ``w = exp(-x/beta)``,
    whose derivative ``1 + (sum(x^2 w) sum(w) - sum(x w)^2)/(beta^2 sum(w)^2)``
    is strictly positive (Cauchy–Schwarz), so the iteration is monotone-safe.
    ``mu`` then follows in closed form. Returns ``{"mu", "beta",
    "bulk_calibration_pass": True, "q90_fit", "q90_empirical"}``.
    """
    x = np.asarray(maxima, dtype=float)
    if x.size < GUMBEL_MIN_SAMPLES or not np.all(np.isfinite(x)):
        return None
    sd = float(x.std())
    if sd <= 0:
        return None
    beta = sd * math.sqrt(6.0) / math.pi
    xbar = float(x.mean())
    shift = float(x.min())                       # exp underflow guard; cancels
    xs = x - shift
    for _ in range(GUMBEL_NEWTON_MAX_ITER):
        w = np.exp(-xs / beta)
        s0 = float(w.sum())
        s1 = float((x * w).sum())
        s2 = float((x * x * w).sum())
        g = beta - xbar + s1 / s0
        gprime = 1.0 + (s2 * s0 - s1 * s1) / (beta * beta * s0 * s0)
        step = g / gprime
        beta_next = beta - step
        if beta_next <= 0:
            beta_next = beta / 2.0
        if abs(beta_next - beta) < GUMBEL_NEWTON_TOL * max(1.0, beta):
            beta = beta_next
            break
        beta = beta_next
    if not np.isfinite(beta) or beta <= 0:
        return None
    mu = shift - beta * math.log(float(np.mean(np.exp(-xs / beta))))
    if not np.isfinite(mu):
        return None
    # Bulk calibration — the model earns the right to extrapolate, or refuses.
    q90_fit = mu - beta * math.log(-math.log(0.9))
    q90_emp = float(np.quantile(x, 0.9))
    if abs(q90_fit - q90_emp) > GUMBEL_Q90_TOL_BETAS * beta:
        return None
    xs_sorted = np.sort(x)
    cdf = np.exp(-np.exp(-(xs_sorted - mu) / beta))
    n = x.size
    i = np.arange(1, n + 1)
    ks = float(max(np.max(i / n - cdf), np.max(cdf - (i - 1) / n)))
    if ks > GUMBEL_BULK_KS_MAX:
        return None
    return {"mu": float(mu), "beta": float(beta), "bulk_calibration_pass": True,
            "q90_fit": float(q90_fit), "q90_empirical": q90_emp,
            "bulk_ks": ks}


def gumbel_tail_fap(observed_sde: float, mu: float, beta: float) -> float:
    """P(null max >= observed) under the fitted Gumbel — the reported tail.

    ``1 - exp(-exp(-(x - mu)/beta))``. Carries every caveat of
    :func:`gumbel_fit`; it may appear in the receipt's ``gumbel.fap_tail``
    field and NOWHERE graded.
    """
    z = (observed_sde - mu) / beta
    return float(-math.expm1(-math.exp(-z)))


# ------------------------------------------------------------------- triage --

def triage_level(n: int) -> float:
    """Compute-bounding HEURISTIC: the SDE above which a target pays for its
    bootstrap. Never a measurement, never graded, never in a graded field.

    A B=256 permutation null costs ~257 full periodograms per target; paying
    it for every target multiplies the survey cost by two orders of magnitude.
    The expected maximum of n independent noise SDEs grows like ``mu + beta *
    ln(n)`` (Gumbel domain), and two runs measured that ceiling directly:
    max SDE 6.6 over n=22 noise targets (A04 graded run) and 7.65 over n=153
    (discovery pilot) — :data:`TRIAGE_FLOOR_POINTS`. The line through those two
    points, MINUS :data:`TRIAGE_SAFETY_MARGIN`, is the triage level: targets
    above it get the full permutation null; targets below it are only sampled
    into the uniformity control subsample.

    This is a heuristic drawn through TWO points, not a measured quantity —
    two points determine a line with zero degrees of freedom left to check it,
    which is exactly why the receipt appends every run's floor to
    ``floor_history`` (making the extrapolation testable later) and why the
    margin is subtracted rather than added: the failure mode is "spent compute
    on a noise target", never "a marginal candidate skipped its FAP".
    Monotone increasing in n by construction (TRIAGE_BETA > 0).
    """
    if n < 1:
        raise A05StatsError("triage_level needs n >= 1 targets")
    return float(TRIAGE_MU + TRIAGE_BETA * math.log(n) - TRIAGE_SAFETY_MARGIN)


# ------------------------------------------- the calibration of the calibrator

def uniformity_stat(p_values: np.ndarray) -> tuple[float, bool]:
    """KS-style distance of the control p-values from Uniform(0,1).

    If the permutation machinery is honest, the FAPs of targets drawn from the
    null (the sub-triage control subsample) are uniform — that is the
    calibration of the calibrator, and it fails loudly when the null is wrong
    for the data (e.g. an iid-only null grading red-noise targets piles the
    p-values near zero). The statistic is the one-sample Kolmogorov–Smirnov
    distance ``max |ecdf - uniform|`` computed on both sides of each step;
    pass/fail compares against the asymptotic 5% critical distance
    :data:`KS_CRITICAL_COEFF```/sqrt(n)``, sized for the n ≈ 50 control
    ensemble the receipt schema names.

    The empirical FAPs live on the grid k/(B+1), which biases the distance
    upward by at most 1/(B+1) — negligible against the ~0.19 critical distance
    at n = 50, and conservative in direction. Returns ``(stat, pass)``.
    """
    ps = np.sort(np.asarray(p_values, dtype=float))
    n = ps.size
    if n < 5:
        raise A05StatsError("uniformity needs at least 5 p-values")
    if np.any(ps < 0) or np.any(ps > 1):
        raise A05StatsError("p-values must lie in [0, 1]")
    i = np.arange(1, n + 1)
    stat = float(max(np.max(i / n - ps), np.max(ps - (i - 1) / n)))
    return stat, bool(stat < KS_CRITICAL_COEFF / math.sqrt(n))
