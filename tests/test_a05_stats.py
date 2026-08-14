"""A05 stats — the FAP engine's contract, anchored to the scalar search.

The deliverable here is the CORRECTNESS ANCHOR: the batched permutation null
must reproduce, bitwise, what feeding each permutation through plain
``a04.blind_search`` produces. Everything else (uniformity, conservatism,
refusal, triage, timing) is graded behavior built on top of that identity.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from lab import a04, a05_stats

#: The one cached curve the publisher-local tests lean on — WASP-18's sector-2
#: SPOC light curve, ~18k good cadences.
WASP18_FITS = Path.home() / ".lab" / "cache" / "a01" / (
    "tess2018234235059-s0002-0000000100100827-0121-s_lc.fits")

needs_cache = pytest.mark.skipif(not WASP18_FITS.exists(),
                                 reason="publisher-local cache")


def _white(days=10.0, cadence=0.02, noise=3e-4, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence)
    return t, 1.0 + rng.normal(0.0, noise, size=t.size)


def _red(days=9.0, cadence=0.02, seed=42, rho=0.995):
    """White noise plus a strong AR(1) walk — correlated structure an iid
    shuffle destroys but a block shuffle partially preserves."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence)
    ar = np.empty(t.size)
    ar[0] = 0.0
    eps = rng.normal(0.0, 1e-4, size=t.size)
    for j in range(1, t.size):
        ar[j] = rho * ar[j - 1] + eps[j]
    return t, 1.0 + rng.normal(0.0, 3e-4, size=t.size) + ar


# ------------------------------------------------------- correctness anchor --

@pytest.mark.parametrize("scheme", a05_stats.SCHEMES)
def test_batched_null_is_bitwise_the_scalar_search(scheme):
    """THE anchor: the same permutations fed down both paths give identical
    SDEs — not close, identical. The batch is only trustworthy because every
    arithmetic step mirrors ``bls_power``/``blind_search`` op-for-op; any
    'optimization' that breaks bit equality (np.add.reduceat did, by its
    last-bit summation order) must be rejected."""
    t, f = _white()
    perms = a05_stats.permutation_indices(t, 6, scheme, seed=7)
    got = a05_stats.batched_null(t, f, B=6, scheme=scheme, seed=7, n_periods=40)
    ref = np.array([a04.blind_search(t, f[p], n_periods=40).sde for p in perms])
    np.testing.assert_array_equal(got, ref)


def test_block_permutation_preserves_block_interiors():
    t = np.arange(0.0, 9.0, 0.02)
    perm = a05_stats.permutation_indices(t, 2, "block", seed=1)[0]
    block_len = max(1, int(round(a05_stats.BLOCK_DAYS / 0.02)))
    # Consecutive indices inside a shuffled block still step by exactly 1.
    steps = np.diff(perm)
    assert np.count_nonzero(steps != 1) <= int(np.ceil(t.size / block_len))
    assert sorted(perm) == list(range(t.size))          # a true permutation


def test_fap_empirical_is_the_add_one_bound():
    maxima = np.array([1.0, 2.0, 3.0, 4.0])
    assert a05_stats.fap_empirical(10.0, maxima) == pytest.approx(1 / 5)
    assert a05_stats.fap_empirical(0.0, maxima) == pytest.approx(1.0)
    assert a05_stats.fap_empirical(3.0, maxima) == pytest.approx(3 / 5)  # tie counts


# ----------------------------------------- calibration of the calibrator -----

def _control_pvalues(kind, n_ctl=40, B=48, seed0=100):
    t = np.arange(0.0, 9.0, 0.02)
    ps = []
    for i in range(n_ctl):
        if kind == "white":
            _, f = _white(days=9.0, seed=seed0 + i)
        else:
            _, f = _red(seed=seed0 + i)
        obs = a04.blind_search(t, f, n_periods=50).sde
        maxima = a05_stats.batched_null(t, f, B=B, scheme="iid",
                                        seed=seed0 + i, n_periods=50)
        ps.append(a05_stats.fap_empirical(obs, maxima))
    return np.array(ps)


def test_pure_noise_pvalues_are_uniform():
    """If the machinery is honest, targets drawn FROM the null grade uniform."""
    stat, ok = a05_stats.uniformity_stat(_control_pvalues("white"))
    assert ok, f"white-noise control ensemble failed uniformity, D={stat:.3f}"


def test_red_noise_graded_iid_only_fails_uniformity():
    """The failure the control exists to catch: an iid shuffle destroys the
    autocorrelation, its null is too clean, and red targets pile up at small
    p — the KS distance must blow past the critical line."""
    ps = _control_pvalues("red")
    stat, ok = a05_stats.uniformity_stat(ps)
    assert not ok, f"red-noise ensemble PASSED uniformity, D={stat:.3f}"
    assert np.mean(ps <= 0.05) > 0.3          # and in the anti-conservative direction


def test_block_scheme_is_more_conservative_on_red_noise():
    """The graded FAP is the max of the two schemes because on correlated flux
    the block null keeps the red power and honestly reports a LARGER FAP."""
    t, f = _red()
    obs = a04.blind_search(t, f, n_periods=60).sde
    fap_iid = a05_stats.fap_empirical(
        obs, a05_stats.batched_null(t, f, B=64, scheme="iid", seed=5, n_periods=60))
    fap_block = a05_stats.fap_empirical(
        obs, a05_stats.batched_null(t, f, B=64, scheme="block", seed=5, n_periods=60))
    assert fap_block > fap_iid


# ------------------------------------------------- reported tail (gumbel) ----

def test_gumbel_fit_recovers_a_true_gumbel_and_calibrates():
    rng = np.random.default_rng(1)
    fit = a05_stats.gumbel_fit(rng.gumbel(5.0, 0.6, 256))
    assert fit is not None and fit["bulk_calibration_pass"]
    assert fit["mu"] == pytest.approx(5.0, abs=0.15)
    assert fit["beta"] == pytest.approx(0.6, abs=0.1)


def test_gumbel_refuses_a_distribution_it_cannot_fit():
    """A bimodal null (e.g. a pulsator contaminating half the permutations)
    is not Gumbel; the fit must return None — nulling the receipt's gumbel
    block — rather than extrapolate a tail from a shape the data contradicts."""
    bimodal = np.concatenate([np.random.default_rng(2).normal(0.0, 0.05, 200),
                              np.random.default_rng(3).normal(20.0, 0.05, 56)])
    assert a05_stats.gumbel_fit(bimodal) is None


def test_gumbel_refuses_tiny_or_degenerate_samples():
    assert a05_stats.gumbel_fit(np.ones(10)) is None
    assert a05_stats.gumbel_fit(np.full(256, 3.3)) is None


def test_gumbel_tail_fap_clamps_instead_of_overflowing():
    """An observed statistic far BELOW the fitted location drives
    exp(-z) toward exp(700+); the clamp returns the honest limit 1.0
    instead of raising OverflowError mid-receipt."""
    p = a05_stats.gumbel_tail_fap(-400.0, mu=8.0, beta=0.5)   # z = -816
    assert p == 1.0
    # And the ordinary tail regime is untouched by the clamp.
    assert 0.0 < a05_stats.gumbel_tail_fap(12.0, mu=8.0, beta=0.5) < 1e-3


# -------------------------------------------------------- uniformity gate ----

def test_uniformity_critical_distance_is_stephens_not_asymptotic():
    """At n=5 a D=0.58 ensemble passes the bare asymptotic 1.358/sqrt(n)
    (0.607) but fails Stephens' finite-n form (0.565) — the finite-n
    denominator is the contract, in both the engine and the check."""
    ps = np.array([0.005, 0.01, 0.02, 0.99, 0.995])
    stat, ok = a05_stats.uniformity_stat(ps)
    assert stat == pytest.approx(0.58)
    crit_asym = a05_stats.KS_CRITICAL_COEFF / np.sqrt(5)
    crit_stephens = a05_stats.KS_CRITICAL_COEFF / (
        np.sqrt(5) + 0.12 + 0.11 / np.sqrt(5))
    assert crit_stephens < stat < crit_asym    # the case the two forms split
    assert ok is False


# ------------------------------------------------------------------ triage ---

def test_triage_level_is_monotone_and_pinned_to_the_floor_points():
    ns = [5, 22, 60, 153, 500, 2000]
    levels = [a05_stats.triage_level(n) for n in ns]
    assert levels == sorted(levels) and len(set(levels)) == len(levels)
    # The line passes exactly through the measured floors minus the margin.
    for n, floor in a05_stats.TRIAGE_FLOOR_POINTS:
        assert a05_stats.triage_level(n) == pytest.approx(
            floor - a05_stats.TRIAGE_SAFETY_MARGIN)


def test_triage_docstring_calls_itself_a_heuristic_not_a_measurement():
    doc = a05_stats.triage_level.__doc__.lower()
    assert "heuristic" in doc
    assert "never graded" in doc


# ------------------------------------------------------------------ timing ---

@needs_cache
def test_timing_smoke_full_scale_batched_null_under_budget():
    """One real 19k-cadence sector curve x B=256 x the full 3000-period grid
    must fit the per-target compute budget on CPU."""
    from lab import a01
    t, f = a01._normalise(a01.read_tess_light_curve(WASP18_FITS.read_bytes()))
    t, f = a04.detrend(t, f)
    assert t.size > 15000
    t0 = time.time()
    maxima = a05_stats.batched_null(t, f, B=256, scheme="iid", seed=1)
    elapsed = time.time() - t0
    assert elapsed < 120.0, f"batched_null took {elapsed:.0f}s"
    assert maxima.shape == (256,) and np.all(np.isfinite(maxima))
    # Sanity: a B=256 null max on one target sits near the measured floors.
    assert 3.0 < float(maxima.max()) < a04.SDE_THRESHOLD + 2.0
