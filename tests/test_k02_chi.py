"""K02's susceptibility exponent — the measurement the ladder was already paying for.

``critical_coherence`` runs a long, well-equilibrated window at exactly K_c to
measure ⟨r⟩. The same window contains Var_t(r) for free, and χ_c = N·Var_t(r)
scaling as N^(γ/ν̄_c) is the second exponent the same run can deliver. These
tests grade the arithmetic and the fit; they do not re-derive Kuramoto physics,
which the K02 maturity tests already own.

The fit tests use synthetic rungs on an exact power law, because a fit that
cannot recover an exponent it was handed has no business reporting one measured
from a simulation.
"""
from __future__ import annotations

import math

import pytest

from lab import k02


# ------------------------------------------------------- the measured moment ---

def test_critical_coherence_reports_a_positive_susceptibility():
    out = k02.critical_coherence(200, seeds=3, t_burn=40.0, t_measure=40.0)
    assert out["chi_critical"] > 0
    assert out["chi_critical_mean"] > 0
    assert len(out["chi_by_seed"]) == 3


def test_the_reported_chi_is_the_median_over_initial_conditions():
    """Median, matching the K-sweep: Var_t(r) is heavy-tailed near criticality."""
    import statistics
    out = k02.critical_coherence(200, seeds=5, t_burn=40.0, t_measure=40.0)
    assert out["chi_critical"] == pytest.approx(
        statistics.median(out["chi_by_seed"]), rel=1e-12)


def test_the_mean_is_reported_alongside_so_the_tail_stays_visible():
    out = k02.critical_coherence(200, seeds=5, t_burn=40.0, t_measure=40.0)
    assert out["chi_critical_mean"] != out["chi_critical"] or len(set(out["chi_by_seed"])) == 1


def test_chi_scales_with_n_times_a_variance():
    """χ = N·Var_t(r): dividing back out must leave a variance, not a rumour."""
    n = 300
    out = k02.critical_coherence(n, seeds=3, t_burn=40.0, t_measure=40.0)
    for chi in out["chi_by_seed"]:
        var = chi / n
        assert 0.0 <= var <= 1.0        # r ∈ [0,1], so Var_t(r) cannot exceed 1/4 in practice


def test_a_single_seed_reports_no_error_bar_rather_than_a_fake_one():
    out = k02.critical_coherence(200, seeds=1, t_burn=20.0, t_measure=20.0)
    assert math.isnan(out["chi_sem"])


def test_the_median_bar_is_wider_than_a_mean_bar_would_be():
    """A median's standard error is ~1.253·σ/√n; reporting σ/√n would understate it."""
    import statistics
    out = k02.critical_coherence(200, seeds=6, t_burn=40.0, t_measure=40.0)
    naive = statistics.stdev(out["chi_by_seed"]) / math.sqrt(6)
    assert out["chi_sem"] == pytest.approx(1.2533 * naive, rel=1e-3)


# ------------------------------------------------------------------- the fit ---

def _rungs(exponent, amplitude=0.5, ns=(250, 500, 1000, 2000, 4000), sem_frac=0.02):
    return [{"n": n, "chi_critical": amplitude * n ** exponent,
             "chi_sem": sem_frac * amplitude * n ** exponent} for n in ns]


@pytest.mark.parametrize("exponent", [0.10, 0.195, 0.25, 0.5])
def test_the_fit_recovers_an_exact_power_law(exponent):
    out = k02.fit_chi_exponent(_rungs(exponent))
    assert out["exponent"] == pytest.approx(exponent, abs=1e-9)
    assert out["r2"] == pytest.approx(1.0, abs=1e-9)
    assert out["points"] == 5


def test_the_exponent_is_reported_positive_because_chi_grows():
    """r(K_c) DECAYS with N and is reported positive; χ GROWS and is too.

    Two exponents from one run with opposite signs is exactly how a sign
    convention gets silently flipped, so both directions are pinned by a test.
    """
    assert k02.fit_chi_exponent(_rungs(0.25))["exponent"] > 0
    assert k02.fit_critical_exponent(
        [{"n": n, "r_critical": 2.0 * n ** -0.4, "r_sem": 0.01 * 2.0 * n ** -0.4}
         for n in (250, 500, 1000, 2000, 4000)])["exponent"] > 0


def test_the_reported_bar_is_the_larger_of_the_two_it_computes():
    out = k02.fit_chi_exponent(_rungs(0.25, sem_frac=0.30))
    assert out["err"] == pytest.approx(max(out["err_regression"], out["err_propagated"]))
    assert out["err_propagated"] > out["err_regression"]      # exact line, fat bars


def test_the_fit_refuses_fewer_than_three_rungs():
    out = k02.fit_chi_exponent(_rungs(0.25, ns=(250, 500)))
    assert math.isnan(out["exponent"])
    assert out["points"] == 2


def test_rungs_without_a_usable_chi_are_dropped_not_fitted():
    rungs = _rungs(0.25) + [{"n": 8000, "chi_critical": 0.0, "chi_sem": 0.0},
                            {"n": 16000, "chi_critical": float("nan"), "chi_sem": 0.0}]
    out = k02.fit_chi_exponent(rungs)
    assert out["points"] == 5
    assert out["exponent"] == pytest.approx(0.25, abs=1e-9)


def test_the_fit_states_that_it_cannot_separate_the_one_sided_exponents():
    """The whole point of the Daido/Hong disagreement is the ASYMMETRY.

    A measurement made at K_c has no side. If this string ever disappears, a
    reader can mistake γ/ν̄_c for a test of γ vs γ', which it is not — and the
    backlog item that motivated this measurement said 'one-line fit' precisely
    because it missed that distinction.
    """
    out = k02.fit_chi_exponent(_rungs(0.25))
    assert "one-sided" in out["measures"]
    assert "NOT separable" in out["measures"]


def test_the_two_exponents_come_from_the_same_rung_dicts():
    """One run, two fits: they must not need different inputs or they will drift."""
    rungs = [{"n": n, "r_critical": 2.0 * n ** -0.4, "r_sem": 0.02,
              "chi_critical": 0.5 * n ** 0.25, "chi_sem": 0.01} for n in
             (250, 500, 1000, 2000, 4000)]
    assert k02.fit_critical_exponent(rungs)["points"] == 5
    assert k02.fit_chi_exponent(rungs)["points"] == 5
