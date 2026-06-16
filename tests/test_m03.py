"""M03 data-collapse — the pure analysis functions (NumPy only, no GPU).

Mirrors ``tests/test_fss.py``: every function here is exercised against
*synthetic* curves built from the exact finite-size-scaling form, so the tests
are parameter-free, GPU-free, and exact by construction. The Wolff torch kernel
and the ``run_m03`` driver are never imported or invoked — only the numpy
analysis surface is under test, keeping the suite fast and CPU-only.
"""
import numpy as np

from lab.m03 import (
    BETA, NU, BETA_OVER_NU, INV_NU, T_C,
    collapse_coords, master_curve, collapse_quality,
    fit_beta_over_nu, fit_collapse, to_report,
    M03Result, M03Curve,
)


def _F(x):
    """A fixed smooth master function F(x) — a sigmoid. Parameter-free."""
    return 1.0 / (1.0 + np.exp(3.0 * np.asarray(x, dtype=float)))


def _synthetic_curves(Ls, xs, beta_over_nu=BETA_OVER_NU, inv_nu=INV_NU, tc=T_C):
    """Build exact ``(L, T, M)`` tuples from the scaling form.

    For each L: ``T = tc + xs · L^(-inv_nu)`` and ``M = L^(-beta_over_nu) · F(xs)``.
    By construction every curve rescales to the IDENTICAL (x, y) = (xs, F(xs)),
    so a correct collapse is exact.
    """
    xs = np.asarray(xs, dtype=float)
    curves = []
    for L in Ls:
        T = tc + xs * L ** (-inv_nu)
        M = L ** (-beta_over_nu) * _F(xs)
        curves.append((L, T, M))
    return curves


# ── collapse_coords ──────────────────────────────────────────────────────────
def test_collapse_coords_rescale_axes():
    # Two L's at the SAME reduced temperature x map M to the SAME rescaled y when
    # M obeys M = L^(-beta/nu)·F(x). (Mirror of test_fss with the SIGN flipped:
    # y is rescaled by +beta/nu because M shrinks with L at criticality.)
    L1, L2 = 16, 64
    x_target = 0.7
    # x = (T - tc)·L^(1/nu) = x_target → T = tc + x_target·L^(-1/nu)
    T1 = [T_C + x_target * L1 ** (-INV_NU)]
    T2 = [T_C + x_target * L2 ** (-INV_NU)]
    f = float(_F(x_target))
    M1 = [L1 ** (-BETA_OVER_NU) * f]
    M2 = [L2 ** (-BETA_OVER_NU) * f]
    x1, y1 = collapse_coords(L1, T1, M1)
    x2, y2 = collapse_coords(L2, T2, M2)
    assert abs(x1[0] - x2[0]) < 1e-9        # same rescaled temperature
    assert abs(y1[0] - y2[0]) < 1e-9        # collapse onto the same height
    assert abs(y1[0] - f) < 1e-9            # and that height is F(x)


def test_collapse_coords_returns_arrays():
    x, y = collapse_coords(16, [2.27, 2.28], [0.5, 0.4])
    assert isinstance(x, np.ndarray) and isinstance(y, np.ndarray)
    assert x.shape == (2,) and y.shape == (2,)


# ── collapse_quality ─────────────────────────────────────────────────────────
def test_perfect_collapse_is_zero_loss():
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 30)
    curves = _synthetic_curves(Ls, xs)
    loss = collapse_quality(curves)
    assert loss < 1e-12


def test_loss_rejects_wrong_beta_over_nu():
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 30)
    curves = _synthetic_curves(Ls, xs)
    good = collapse_quality(curves, beta_over_nu=BETA_OVER_NU)
    bad = collapse_quality(curves, beta_over_nu=0.5)
    assert bad > 1e-3
    assert bad > 50.0 * max(good, 1e-30)


def test_loss_rejects_wrong_inv_nu():
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 30)
    curves = _synthetic_curves(Ls, xs)
    good = collapse_quality(curves, inv_nu=INV_NU)
    bad = collapse_quality(curves, inv_nu=2.0)
    assert bad > 1e-6
    assert bad > 50.0 * max(good, 1e-30)


def test_overlap_window_robustness():
    # Curves with different / partial T-windows still score finite.
    Ls = (16, 32)
    c1 = _synthetic_curves([16], np.linspace(-2.0, 1.0, 20))[0]
    c2 = _synthetic_curves([32], np.linspace(-1.0, 2.0, 20))[0]
    loss = collapse_quality([c1, c2])
    assert np.isfinite(loss)
    # Same scaling form on the overlap → tiny loss (only np.interp discretization
    # error between the two curves' offset x-samples remains, not a collapse error).
    assert loss < 1e-4

    # A genuinely non-overlapping pair returns inf.
    far1 = _synthetic_curves([16], np.linspace(-5.0, -4.0, 10))[0]
    far2 = _synthetic_curves([32], np.linspace(4.0, 5.0, 10))[0]
    assert collapse_quality([far1, far2]) == np.inf


def test_collapse_quality_needs_two_curves():
    one = _synthetic_curves([16], np.linspace(-2.0, 2.0, 20))
    assert collapse_quality(one) == np.inf


# ── master_curve ─────────────────────────────────────────────────────────────
def test_master_curve_shape_and_zero_band():
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 40)
    curves = _synthetic_curves(Ls, xs)
    centers, mean_y, std_y = master_curve(curves, n_bins=20)
    assert len(centers) == len(mean_y) == len(std_y) == 20
    # Perfect collapse → the cross-curve band collapses to ~0.
    assert np.nanmax(std_y) < 1e-9
    # The pooled mean tracks F over the overlap window.
    assert np.all(np.isfinite(mean_y))


# ── fit_beta_over_nu ─────────────────────────────────────────────────────────
def test_fit_recovers_beta_over_nu_exact():
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 40)
    curves = _synthetic_curves(Ls, xs)
    bon_fit, loss = fit_beta_over_nu(curves)
    assert abs(bon_fit - 1.0 / 8.0) < 1e-3
    assert loss < 1e-6


def test_fit_distinguishes_a_wrong_dataset():
    # Build curves from a WRONG exponent and confirm the fit reads the DATA,
    # not the constant (mirror of test_fss.test_fit_distinguishes_a_wrong_exponent).
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 40)
    curves = _synthetic_curves(Ls, xs, beta_over_nu=0.4)
    bon_fit, _ = fit_beta_over_nu(curves)
    assert abs(bon_fit - 0.4) < 1e-2
    assert abs(bon_fit - 1.0 / 8.0) > 0.1   # clearly NOT the theory value


# ── fit_collapse (joint, no-assumptions) ─────────────────────────────────────
def test_joint_fit_recovers_both_exponents():
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 40)
    curves = _synthetic_curves(Ls, xs)
    bon_fit, invnu_fit, loss = fit_collapse(curves)
    assert abs(bon_fit - 1.0 / 8.0) < 1e-2
    assert abs(invnu_fit - 1.0) < 1e-2
    assert loss < 1e-6


# ── constants ────────────────────────────────────────────────────────────────
def test_reference_constants_are_exact():
    assert BETA == 1.0 / 8.0
    assert NU == 1.0
    assert BETA_OVER_NU == 1.0 / 8.0
    assert INV_NU == 1.0
    assert abs(T_C - 2.0 / np.log(1.0 + np.sqrt(2.0))) < 1e-15


# ── to_report ────────────────────────────────────────────────────────────────
def _toy_result(beta_over_nu_fit=BETA_OVER_NU):
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 24)
    raw = _synthetic_curves(Ls, xs)
    curves = [
        M03Curve(L=L, T=T.tolist(), M=M.tolist(),
                 M_err=[0.0] * len(T), wall_seconds=1.0)
        for (L, T, M) in raw
    ]
    return M03Result(
        curves=curves,
        beta_over_nu_fit=beta_over_nu_fit,
        inv_nu_fit=1.0,
        collapse_quality=1e-15,
        tc=float(T_C),
        beta_over_nu_theory=BETA_OVER_NU,
        nu=NU,
        wall_seconds=120.0,
        config={"seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M03-data-collapse"
    assert [c["L"] for c in rep["curves"]] == [16, 24, 32, 48]
    assert all({"L", "T", "M"} <= set(c) for c in rep["curves"])
    assert abs(rep["beta_over_nu_fit"] - BETA_OVER_NU) < 1e-9
    assert rep["beta_over_nu_theory"] == BETA_OVER_NU
    assert rep["collapse_quality"] < 1e-12
    # Master-curve arrays for the page band.
    assert {"centers", "mean_y", "std_y"} <= set(rep["master_curve"])
    # No top-level T/chi → the M01 check must treat it as not-applicable.
    assert "chi" not in rep and "T" not in rep
    assert "headline" in rep and "L^" in rep["headline"]
