"""Shape and the density ceiling.

The controls are the point. WASP-18 b is a confirmed planet with published
geometry, so any gate that calls it grazing, or any "ceiling" its true host
density violates, is broken — and both happened before these tests existed.
"""
import math

import numpy as np
import pytest

from lab import a05_shape


def synth(period, k, b, depth=None, n=19440, span=27.0, noise=0.0, seed=7):
    """A limb-darkened transit on a clean baseline, from the module's own model."""
    t = np.linspace(0.0, span, n)
    x = ((t / period) % 1.0) - 0.5
    ar = math.sqrt((1.0 + k) ** 2 - b * b) / (math.pi * 0.04)
    f = a05_shape.transit_model(x, k, b, ar, *a05_shape.DEFAULT_LIMB_DARKENING)
    if noise:
        f = f + np.random.default_rng(seed).normal(0, noise, n)
    return t, f


# ------------------------------------------------------------- the ceiling --

def test_density_ceiling_holds_for_wasp18():
    """The published host density must not exceed the ceiling. It did before
    the (1+k) term was restored: ceiling 0.803 vs a true 0.873."""
    ceiling = a05_shape.density_ceiling(0.94145299, 0.0950, k=0.1009)
    assert ceiling["rho_max_cgs"] > 0.873


def test_dropping_k_breaks_the_ceiling():
    """Regression on the exact bug: k=0 understates the bound."""
    with_k = a05_shape.density_ceiling(0.94145299, 0.0950, k=0.1009)
    without = a05_shape.density_ceiling(0.94145299, 0.0950, k=0.0)
    assert without["rho_max_cgs"] < 0.873 < with_k["rho_max_cgs"]


def test_density_ceiling_scales_as_one_plus_k_cubed():
    a = a05_shape.density_ceiling(3.0, 0.04, k=0.0)
    b = a05_shape.density_ceiling(3.0, 0.04, k=0.24)
    assert b["rho_max_cgs"] / a["rho_max_cgs"] == pytest.approx(1.24 ** 3, rel=1e-9)


def test_density_ceiling_excludes_dense_dwarfs_when_low():
    """A long duration at a short period means a puffy host; M dwarfs go."""
    out = a05_shape.density_ceiling(2.685728750580555, 0.0375, k=0.24)
    assert out["r_star_min_sun"] is not None
    assert out["excluded"], "a 3 g/cm3 ceiling must forbid the M dwarfs"
    assert out["r_star_min_sun"] <= 1.0


def test_density_ceiling_refuses_nonsense():
    assert a05_shape.density_ceiling(-1, 0.04)["reason"] == "inputs-out-of-range"
    assert a05_shape.density_ceiling(3.0, 0.9)["reason"] == "inputs-out-of-range"


# ----------------------------------------------------------------- the fit --

def test_fit_recovers_a_known_geometry():
    t, f = synth(2.5, k=0.10, b=0.30)
    fit = a05_shape.fit_transit(t, f, 2.5)
    assert fit["k"] == pytest.approx(0.10, abs=0.03)
    assert fit["verdict"] is None          # a planet is not "grazing"


def test_fit_flags_a_grazing_body():
    t, f = synth(2.5, k=0.30, b=1.10)
    fit = a05_shape.fit_transit(t, f, 2.5)
    assert fit["v_ness"] > a05_shape.V_NESS_GRAZING
    assert fit["verdict"] == "grazing-or-v-shaped"


def test_v_ness_is_small_for_a_central_small_planet():
    t, f = synth(2.5, k=0.08, b=0.0)
    fit = a05_shape.fit_transit(t, f, 2.5)
    assert fit["v_ness"] < 0.4


def test_fit_refuses_a_flat_series():
    t = np.linspace(0, 27, 5000)
    fit = a05_shape.fit_transit(t, np.ones_like(t), 2.5)
    assert fit["k"] is None and fit["reason"] is not None


# --------------------------------------------------------- the detrend guard --

def test_detrend_guard_rejects_a_window_near_the_period():
    """The measured failure: a 0.5 d median on a 0.941 d period reported a
    confirmed planet as grazing (k 0.101 -> 0.161, b 0.45 -> 0.98)."""
    assert a05_shape.detrend_safe(0.94145299, 0.5)["safe"] is False


def test_detrend_guard_accepts_a_long_window_and_no_detrend():
    assert a05_shape.detrend_safe(0.94145299, 5.0)["safe"] is True
    assert a05_shape.detrend_safe(0.94145299, None)["safe"] is True


def test_duration_fraction_measures_a_planted_box():
    t = np.linspace(0, 27, 19440)
    f = np.ones_like(t)
    ph = (t / 3.0) % 1.0
    f[np.abs(((ph - 0.5 + 0.5) % 1.0) - 0.5) < 0.02] -= 0.01
    out = a05_shape.duration_fraction(t, f, 3.0)
    assert out["t14_frac"] == pytest.approx(0.04, abs=0.006)
