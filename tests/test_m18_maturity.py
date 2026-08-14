"""M18 maturity regressions: the absorbing state, the straddle, and the bracket.

The load-bearing assertions are the ones that stop a bracket from being cheap.
A bracket only bounds anything if the two runs are genuinely on OPPOSITE sides of
p_c, and it only says anything about universality if it is narrow enough to
exclude mean-field. Both are graded, not described.
"""
from __future__ import annotations

import math

import pytest

from lab import checks, dp, m18


# ------------------------------------------------------------- the engine ---

def test_absorbing_state_is_absorbing_even_at_huge_p():
    """The defining property. If this fails, every exponent above it is a fiction."""
    assert dp.absorbing_state_holds(L=32, batch=2, steps=100, p=0.99,
                                    device="cpu", seed=3)


def test_a_single_active_site_can_spread():
    """The other side: activity must be able to grow, or 'absorbing' is trivial."""
    import torch
    gen = torch.Generator(device="cpu")
    gen.manual_seed(11)
    state = torch.zeros((1, 32, 32), dtype=torch.uint8)
    state[0, 16, 16] = 1
    for _ in range(12):
        state = dp.step(state, 0.6, gen)
    assert float(state.sum()) > 1.0


def test_deep_subcritical_dies_and_deep_supercritical_survives():
    sub = dp.run_decay(0.10, L=64, batch=2, t_max=300, device="cpu", seed=5)
    sup = dp.run_decay(0.40, L=64, batch=2, t_max=300, device="cpu", seed=5)
    assert sub.absorbed_at is not None
    assert sup.absorbed_at is None and sup.rho[-1] > 0.1


def test_effective_exponent_decreases_with_p():
    """The monotonicity the whole bracketing argument rests on."""
    lo = dp.run_decay(0.21, L=128, batch=2, t_max=400, device="cpu", seed=9)
    hi = dp.run_decay(0.24, L=128, batch=2, t_max=400, device="cpu", seed=9)
    d_lo, _, _ = dp.fit_exponent(lo.rho, 50, 400)
    d_hi, _, _ = dp.fit_exponent(hi.rho, 50, 400)
    assert d_lo > d_hi


def test_fit_exponent_recovers_a_planted_power_law():
    rho = [0.0] + [float(t) ** -0.4505 for t in range(1, 2001)]
    delta, r2, n = dp.fit_exponent(rho, 100, 2000)
    assert delta == pytest.approx(0.4505, abs=1e-6)
    assert r2 > 0.999999 and n == 1901


def test_exponential_quality_prefers_an_exponential_curve():
    """The control's discriminator: exponential data must fit exponential better."""
    exp_rho = [math.exp(-0.01 * t) for t in range(1, 500)]
    pow_r2 = dp.fit_exponent(exp_rho, 10, 400)[1]
    exp_r2 = dp.exponential_decay_quality(exp_rho, 10, 400)
    assert exp_r2 > pow_r2


def test_correlation_reach_grows_and_bounds_headroom():
    assert dp.correlation_reach(50_000) == pytest.approx(50_000 ** (1 / 1.766))
    assert dp.correlation_reach(50_000) < 2048 / m18.MIN_HEADROOM


# --------------------------------------------------------------- the check ---

def _report(*, d_low_p=0.5450, d_high_p=0.4114, c_low=1.209, c_high=-0.153,
            controls_pass=True, r2=0.995) -> dict:
    return {
        "experiment": "M18-directed-percolation-2plus1d",
        "bracket": [d_high_p, d_low_p],
        "delta_at_p_low": d_low_p, "delta_at_p_high": d_high_p,
        "r2_at_p_low": r2, "r2_at_p_high": r2,
        "curvature_at_p_low": c_low,
        "curvature_at_p_high": c_high,
        "benchmark_delta": dp.DELTA_DP_2P1,
        "mean_field_delta": dp.DELTA_MEAN_FIELD,
        "max_bracket_width": m18.MAX_BRACKET_WIDTH,
        "min_headroom": m18.MIN_HEADROOM,
        "p_c_estimate": 0.22415, "p_c_uncertainty": 5e-5,
        "p_low": 0.22410, "p_high": 0.22420,
        "lattice": {"L": 2048, "t_max": 50_000},
        "controls": {
            "deep_subcritical": {"passed": True, "absorbed_at": 40,
                                 "exponential_r2": 0.995 if controls_pass else 0.90,
                                 "power_law_r2": 0.938},
            "deep_supercritical": {"passed": True,
                                   "plateau_density": 0.736 if controls_pass else 0.0,
                                   "delta_eff": 0.001},
            "absorbing_state": {"passed": True, "stayed_empty": controls_pass},
        },
    }


def test_check_passes_the_shipped_measurement():
    ok, detail = checks.check_m18(_report())
    assert ok is True
    assert "contains the DP value 0.4505" in detail
    assert "excludes mean-field" in detail


def test_a_bracket_that_does_not_straddle_is_refused():
    """Two runs on the same side of p_c bound nothing, even if they span 0.4505."""
    ok, detail = checks.check_m18(_report(c_low=1.2, c_high=0.9))
    assert ok is False
    assert "do not straddle" in detail


def test_a_bracket_that_misses_the_dp_value_fails():
    ok, detail = checks.check_m18(_report(d_low_p=0.30, d_high_p=0.20))
    assert ok is False
    assert "misses DP" in detail


def test_a_bracket_too_wide_to_exclude_mean_field_fails():
    """[0.2, 1.4] contains 0.4505 and says nothing about universality."""
    ok, detail = checks.check_m18(_report(d_low_p=1.4, d_high_p=0.2))
    assert ok is False
    assert "mean-field" in detail or "width" in detail


def test_a_wide_bracket_fails_even_below_mean_field():
    ok, detail = checks.check_m18(_report(d_low_p=0.70, d_high_p=0.20))
    assert ok is False
    assert "width" in detail


def test_correlation_length_reaching_the_box_fails():
    rep = _report()
    rep["lattice"]["L"] = 512
    ok, detail = checks.check_m18(rep)
    assert ok is False
    assert "headroom" in detail


def test_failed_control_fails_the_whole_run():
    ok, detail = checks.check_m18(_report(controls_pass=False))
    assert ok is False
    assert "control(s) failed" in detail


def test_control_pass_booleans_cannot_hide_failed_metrics():
    rep = _report()
    rep["controls"]["deep_supercritical"]["plateau_density"] = 0.0
    assert rep["controls"]["deep_supercritical"]["passed"] is True
    ok, detail = checks.check_m18(rep)
    assert ok is False
    assert "deep_supercritical" in detail


def test_echoed_bracket_and_benchmarks_cannot_grade_the_receipt():
    rep = _report(d_low_p=0.30, d_high_p=0.20)
    rep["bracket"] = [0.40, 0.50]
    rep["benchmark_delta"] = 0.25
    rep["mean_field_delta"] = 99.0
    rep["max_bracket_width"] = 99.0
    ok, detail = checks.check_m18(rep)
    assert ok is False
    assert "misses DP" in detail


def test_poor_power_law_fit_is_refused():
    ok, detail = checks.check_m18(_report(r2=0.8))
    assert ok is False
    assert "power-law fit" in detail


def test_missing_controls_are_unreadable_not_false():
    rep = _report()
    rep["controls"] = {"only_one": {"passed": True}}
    ok, detail = checks.check_m18(rep)
    assert ok is None
    assert "fewer than three named controls" in detail


def test_check_ignores_other_experiments():
    assert checks.check_m18({"experiment": "M17-kpz"})[0] is None


def test_m18_is_registered_everywhere():
    from lab import curriculum
    assert checks.CHECKS["M18"] is checks.check_m18
    assert curriculum.RUNNERS["M18"] == "m18"
