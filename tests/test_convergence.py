"""The limit auditor — the instrument that audits instruments.

Every test here is a synthetic with a KNOWN limit, because that is the only
place the auditor can be checked at all: on real data there is no true value.
Three separate defects in this module were found by these controls and by
nothing else —

1. extrapolating by swapping h^p for h^(p+1) instead of nesting, which reported
   perfectly linear data as undetermined;
2. judging disagreement against the value's magnitude instead of its swept
   range, which passed an order-8 bias as converged;
3. demanding a determined extrapolation from data already flat to 0.1 ppm,
   which reported the estate's most converged results as "undetermined".
"""
from __future__ import annotations

import pytest

from lab import convergence as C

CTRL = (0.1, 0.2, 0.3, 0.4, 0.5)
TRUE = 42.0


def _vals(order, controls=CTRL, amp=3.0):
    return [TRUE - amp * h ** order for h in controls]


# ── it must find a known limit ───────────────────────────────────────────────

@pytest.mark.parametrize("order", [1, 2, 3])
def test_a_known_limit_is_recovered_at_every_order(order):
    ex = C.extrapolate(CTRL, _vals(order))
    assert ex["determined"] is True
    assert ex["limit"] == pytest.approx(TRUE, abs=0.05)


def test_an_estimator_that_ignores_its_control_is_its_own_limit():
    ex = C.extrapolate(CTRL, [7.0] * len(CTRL))
    assert ex["determined"] is True and ex["limit"] == pytest.approx(7.0)


# ── it must refuse when it cannot ────────────────────────────────────────────

def test_a_bias_beyond_the_fitted_orders_is_refused_not_extrapolated():
    """Degrees 3 and 4 fit an order-8 bias badly in the SAME way, so adding a
    term is not enough on its own. Dropping the furthest control is what
    catches it."""
    ex = C.extrapolate((0.3, 0.5, 0.7, 0.9, 1.1), _vals(8, (0.3, 0.5, 0.7, 0.9, 1.1)))
    assert ex["determined"] is False


def test_a_sweep_that_never_approaches_the_limit_is_refused():
    ex = C.extrapolate((1.0, 1.2, 1.4, 1.6, 1.8), _vals(8, (1.0, 1.2, 1.4, 1.6, 1.8)))
    assert ex["determined"] is False
    assert ex["limit"] != pytest.approx(TRUE, rel=0.5)


def test_too_few_points_refuses_rather_than_fitting():
    ex = C.extrapolate((0.1, 0.2, 0.3), [1.0, 2.0, 3.0])
    assert ex["determined"] is False and "fewer than four" in ex["reason"]


# ── the question that makes it useful ────────────────────────────────────────

def test_the_verdict_is_bias_against_tolerance_not_convergence():
    """K03's bias was 11-33% and tilted the fit it fed. A02's was 0.20% of its
    grading tolerance and moved nothing. Identical defects, opposite verdicts —
    a judgement that cannot separate them is worthless."""
    loose = C.audit("loose", lambda h: TRUE - 3.0 * h ** 2, CTRL,
                    shipped=0.5, tolerance=10.0)
    tight = C.audit("tight", lambda h: TRUE - 3.0 * h ** 2, CTRL,
                    shipped=0.5, tolerance=0.001)
    assert loose.verdict == "harmless" and tight.verdict == "MATTERS"
    assert loose.bias == tight.bias, "same defect, same bias, different stakes"


def test_an_estimator_flat_within_tolerance_needs_no_extrapolation():
    """The rule that stops this being a nitpick machine. If the estimator moves
    less than the tolerance across the WHOLE sweep, the limit cannot matter —
    and four of A02's six stars are exactly this, moving under 1 ppm against
    tolerances of thousands."""
    a = C.audit("flat enough", lambda h: TRUE - 1e-9 * h, CTRL,
                shipped=0.5, tolerance=1e-3)
    assert a.verdict == "harmless"
    assert a.swept_range < a.tolerance


def test_a_matters_verdict_says_how_many_tolerances_out_it_is():
    a = C.audit("bad", lambda h: TRUE - 3.0 * h, CTRL, shipped=0.5, tolerance=0.1)
    assert a.verdict == "MATTERS"
    assert any("tolerance" in n for n in a.notes)


def test_the_shipped_value_is_kept_beside_the_limit():
    """A correction nobody can see is a correction nobody can audit."""
    a = C.audit("x", lambda h: TRUE - 3.0 * h ** 2, CTRL, shipped=0.5, tolerance=10.0)
    r = a.to_json()
    assert r["shipped_value"] == pytest.approx(TRUE - 3.0 * 0.25)
    assert r["limit"] == pytest.approx(TRUE, abs=0.05)
    assert r["bias_over_tolerance"] == pytest.approx(a.bias / 10.0)


def test_no_tolerance_means_measured_not_a_pass():
    """Without the scale a result is graded at, the auditor may report the bias
    and must not pretend to judge it."""
    a = C.audit("x", lambda h: TRUE - 3.0 * h, CTRL, shipped=0.5)
    assert a.verdict == "measured"
