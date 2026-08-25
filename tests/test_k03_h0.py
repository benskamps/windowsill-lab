"""The h→0 estimator — χ measured where linear response is actually defined.

These negative controls are not decoration. An earlier version of `chi_h0`
extrapolated nested sub-ladder slopes to h_top = 0, which is correct only when
the leading correction is quadratic. On a synthetic CUBIC response it returned
49.1 for a true χ of 42 — a 17% error, in the same direction and roughly the
same size as the bias it was built to remove, and it would have been invisible
in real data because there is no true value to check against there. The defect
was found by `test_a_cubic_response_recovers_its_linear_coefficient` and by
nothing else.
"""
from __future__ import annotations

import numpy as np
import pytest

from lab import k03_gpu

H = np.linspace(0.0, 1e-3, 9)
CHI = 42.0


def _chi(obs, **kw):
    return k03_gpu.chi_h0(H, obs, **kw)


# ── it must recover a known linear coefficient ───────────────────────────────

def test_a_pure_linear_response_is_returned_unchanged():
    r = _chi(CHI * H)
    assert r["chi"] == pytest.approx(CHI, rel=1e-9)
    assert r["bias_fraction"] == pytest.approx(0.0, abs=1e-9)


def test_a_quadratic_response_recovers_its_linear_coefficient():
    """⟨r⟩ above K_c is not odd in h — there is already spontaneous order — so
    an even correction is physically expected on that branch."""
    assert _chi(CHI * H - 5e3 * H ** 2)["chi"] == pytest.approx(CHI, rel=1e-9)


def test_a_cubic_response_recovers_its_linear_coefficient():
    """The test that caught the first estimator. A sub-ladder extrapolation
    assumes the bias is linear in h_top; for a cubic response it is not, and it
    overshot by 17%."""
    assert _chi(CHI * H - 2e7 * H ** 3)["chi"] == pytest.approx(CHI, rel=1e-9)


def test_a_mixed_response_recovers_its_linear_coefficient():
    assert _chi(CHI * H - 3e3 * H ** 2 - 1e7 * H ** 3)["chi"] == pytest.approx(CHI, rel=1e-9)


# ── it must know when it cannot ──────────────────────────────────────────────

def test_a_ladder_reaching_past_the_expansion_is_refused_not_fitted():
    """Sufficiency is checked by ADDING a term: if a quartic fit disagrees with
    the cubic, the expansion has not converged and the linear coefficient is not
    determined. Returning a confident wrong number here is the whole failure
    mode."""
    r = _chi(CHI * H - 8e13 * H ** 5)
    assert r["orders_agree"] is False
    assert r["order_disagreement"] > 0.05


def test_convergence_is_not_judged_against_the_quadratic():
    """Comparing cubic against QUADRATIC would reject a genuine cubic response,
    where the cubic fit is the correct one. That would gate out good columns."""
    r = _chi(CHI * H - 2e7 * H ** 3)
    assert r["orders_agree"] is True, "a real cubic response must not be rejected"
    assert r["chi_quadratic"] != pytest.approx(r["chi"], rel=1e-3), (
        "the quadratic fit genuinely disagrees here — which is why it is not "
        "the convergence criterion")


def test_a_ladder_too_short_for_the_fit_refuses_rather_than_guessing():
    r = k03_gpu.chi_h0(np.linspace(0, 1e-3, 4), np.linspace(0, 4e-2, 4))
    assert r["chi"] is None and "cannot support" in r["reason"]


# ── it must expose the bias rather than silently correcting it ───────────────

def test_the_single_ladder_value_is_reported_beside_the_corrected_one():
    """The receipt has to show what K03's old estimator would have said, or the
    11-33% saturation bias found on 2026-08-24 becomes invisible the moment it
    is fixed — and nobody can audit a correction they cannot see."""
    r = _chi(CHI * H - 2e7 * H ** 3)
    assert r["single_ladder_chi"] < r["chi"]
    assert r["bias_fraction"] > 0.4


def test_the_baseline_is_fitted_not_assumed_zero():
    """Assay rule #1: a through-origin fit absorbs the baseline into the slope.
    That defect once manufactured γ = −0.306 at R² 0.995."""
    r = _chi(0.137 + CHI * H)
    assert r["chi"] == pytest.approx(CHI, rel=1e-9)
    assert r["baseline"] == pytest.approx(0.137, abs=1e-9)


def test_noise_does_not_move_the_estimate_far():
    """Not a precision claim — a sanity floor. With realistic scatter the
    estimator must stay near the truth rather than chasing the curvature."""
    rng = np.random.default_rng(3)
    got = [_chi(CHI * H - 2e7 * H ** 3 + rng.normal(0, 2e-6, H.size))["chi"]
           for _ in range(20)]
    assert np.median(got) == pytest.approx(CHI, rel=0.05)
