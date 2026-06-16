"""M02 finite-size scaling — the pure analysis functions (NumPy only, no GPU)."""
import numpy as np

from lab.fss import (
    GAMMA_OVER_NU, NU, chi_peak, collapse_coords, fit_gamma_over_nu, to_report,
    FSSResult, FSSCurve,
)


def test_chi_peak_finds_max_and_location():
    T = [2.0, 2.2, 2.3, 2.4, 2.6]
    chi = [10.0, 40.0, 95.0, 38.0, 8.0]
    cmax, tpk = chi_peak(T, chi)
    assert cmax == 95.0
    assert tpk == 2.3


def test_fit_recovers_a_known_power_law():
    # Synthesize χ_max = A · L^(7/4) exactly → slope must come back as 7/4.
    Ls = [32, 64, 128, 256, 512]
    A = 0.37
    chimax = [A * L ** GAMMA_OVER_NU for L in Ls]
    slope, intercept, r2 = fit_gamma_over_nu(Ls, chimax)
    assert abs(slope - GAMMA_OVER_NU) < 1e-9
    assert abs(np.exp(intercept) - A) < 1e-6
    assert r2 > 0.9999


def test_fit_distinguishes_a_wrong_exponent():
    # A simulation that scaled like L^1 (wrong) must NOT read as 7/4.
    Ls = [32, 64, 128, 256, 512]
    chimax = [5.0 * L for L in Ls]
    slope, _, r2 = fit_gamma_over_nu(Ls, chimax)
    assert abs(slope - 1.0) < 1e-9
    assert abs(slope - GAMMA_OVER_NU) > 0.5      # clearly separable from theory


def test_collapse_coords_rescale_axes():
    # At the same reduced temperature t=(T-Tc)*L, two L's should map χ to the
    # same rescaled height when χ obeys χ = L^(γ/ν)·g(t).
    tc = 2.2692
    L1, L2 = 64, 256
    # pick T's giving the SAME x = (T-tc)*L  → T = tc + x/L
    x_target = 1.5
    T1 = [tc + x_target / L1]
    T2 = [tc + x_target / L2]
    # χ following the scaling form with master value g=7.0 at this x
    g = 7.0
    chi1 = [g * L1 ** GAMMA_OVER_NU]
    chi2 = [g * L2 ** GAMMA_OVER_NU]
    x1, y1 = collapse_coords(L1, T1, chi1, tc=tc)
    x2, y2 = collapse_coords(L2, T2, chi2, tc=tc)
    assert abs(x1[0] - x2[0]) < 1e-9            # same rescaled temperature
    assert abs(y1[0] - y2[0]) < 1e-9            # collapse onto the same height
    assert abs(y1[0] - g) < 1e-9


def _toy_result(slope=GAMMA_OVER_NU):
    Ls = [32, 64, 128, 256, 512]
    A = 0.4
    curves = [
        FSSCurve(L=L, T=[2.2, 2.27, 2.34], chi=[1.0, A * L ** slope, 1.0],
                 chi_max=A * L ** slope, T_peak=2.27, wall_seconds=1.0)
        for L in Ls
    ]
    s, intercept, r2 = fit_gamma_over_nu(Ls, [c.chi_max for c in curves])
    return FSSResult(curves=curves, slope=s, intercept=intercept, r2=r2,
                     tc=2.2692, gamma_over_nu_theory=GAMMA_OVER_NU, nu=NU,
                     wall_seconds=120.0, config={"seed": 42})


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M02-finite-size-scaling"
    assert rep["L_values"] == [32, 64, 128, 256, 512]
    assert len(rep["curves"]) == 5
    assert all({"L", "chi_max", "T_peak"} <= set(c) for c in rep["curves"])
    assert abs(rep["gamma_over_nu_fit"] - GAMMA_OVER_NU) < 1e-9
    assert rep["gamma_over_nu_theory"] == GAMMA_OVER_NU
    # No top-level T/chi → the M01 check must treat it as not-applicable.
    assert "chi" not in rep and "T" not in rep
    assert "headline" in rep and "L^" in rep["headline"]
