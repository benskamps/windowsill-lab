"""M06 3D-Ising — the pure analysis surface (NumPy only), plus report shape.

Mirrors ``tests/test_fss.py`` / ``tests/test_m03.py``: the peak-finders and the
relative-error are exercised against *synthetic* curves with a known peak, so the
tests are parameter-free and never run a Monte-Carlo sweep. ``run_m06`` (the
actual 3D driver) is not invoked here — only the analysis layer is under test.
The real sweep is exercised end-to-end by ``test_ising3d`` and the milestone run.
"""
import numpy as np

from lab.m06 import (
    TC_3D, BETA_3D, GAMMA_3D, NU_3D,
    susceptibility_peak, specific_heat_peak, refine_peak, relative_error,
    to_report, M06Result,
)


def test_susceptibility_peak_finds_max_and_location():
    T = [4.0, 4.3, 4.5, 4.7, 5.0]
    chi = [10.0, 40.0, 95.0, 38.0, 8.0]
    cmax, tpk = susceptibility_peak(T, chi)
    assert cmax == 95.0
    assert tpk == 4.5


def test_specific_heat_peak_is_independent_probe():
    T = [4.0, 4.4, 4.5, 4.6, 5.0]
    cv = [1.0, 2.0, 5.0, 2.2, 0.9]
    cmax, tpk = specific_heat_peak(T, cv)
    assert cmax == 5.0
    assert tpk == 4.5


def test_refine_peak_recovers_subgrid_vertex():
    # A parabola peaking exactly at T=4.5115 sampled on a grid that straddles it
    # but never lands on it: the 3-point refinement must recover the true vertex.
    T = np.linspace(4.1, 4.9, 21)
    true_tc = 4.5115
    y = -(T - true_tc) ** 2 + 5.0          # downward parabola, vertex at true_tc
    refined = refine_peak(T, y)
    coarse = T[int(np.argmax(y))]
    assert abs(refined - true_tc) < 1e-6           # essentially exact for a parabola
    assert abs(refined - true_tc) < abs(coarse - true_tc)  # better than the grid argmax


def test_refine_peak_falls_back_at_endpoint():
    # Monotone data → max on the right endpoint → no bracket → return that T.
    T = [4.0, 4.2, 4.4, 4.6]
    y = [1.0, 2.0, 3.0, 4.0]
    assert refine_peak(T, y) == 4.6


def test_relative_error_against_benchmark():
    assert relative_error(TC_3D) == 0.0
    # A 2% high estimate reads back as ~2%.
    assert abs(relative_error(TC_3D * 1.02) - 0.02) < 1e-12


def _toy_result(tc_refined=4.55):
    T = list(np.linspace(4.1, 4.9, 21))
    chi = [-(t - tc_refined) ** 2 + 10.0 for t in T]
    return M06Result(
        T=T, chi=chi, abs_mag=[0.5] * 21, abs_mag_err=[0.01] * 21,
        energy=[-1.5] * 21, specific_heat=[1.0] * 21, L=10,
        tc_chi=tc_refined, tc_chi_refined=tc_refined, tc_cv=tc_refined,
        tc_benchmark=TC_3D, rel_error=relative_error(tc_refined),
        wall_seconds=120.0, config={"L": 10, "seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M06-3d-ising"
    # Carries top-level T+chi so the M06 check can re-derive the peak,
    # AND a distinct experiment tag (not starting with M01) so the M01 check skips it.
    assert "T" in rep and "chi" in rep and len(rep["T"]) == len(rep["chi"])
    assert rep["tc_benchmark"] == TC_3D
    assert rep["L"] == 10
    # The 3D exponents are carried for context and are NOT the 2D ones.
    assert rep["beta_3d"] == BETA_3D and rep["gamma_3d"] == GAMMA_3D and rep["nu_3d"] == NU_3D
    assert "headline" in rep and "benchmark" in rep["headline"]


def test_report_is_distinguishable_from_2d_ising():
    # An M06 report must not be mistaken for the 2D M01 χ-sweep, even though both
    # carry top-level T+chi — the experiment tag is the discriminator. The real
    # M01 tag is "M01-ising-verification" (see render.py); M06's must differ.
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M06-3d-ising"
    assert not rep["experiment"].startswith("M01")
