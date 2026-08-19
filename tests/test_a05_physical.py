"""Admissibility-gate tests — how big was the thing that made the eclipse.

The positive control is WASP-18 b, whose radius is published (1.19 R_Jup) and
whose light curve is the cache's calibration target; the gate must let it
through. The negative control is TIC 287328866, the F subgiant whose "candidate"
implies a body no planet reaches. Everything else exercises the refusals: an
unknown radius must never read as a small one.
"""
from __future__ import annotations

import pytest

from lab import a05_physical as phys


R_JUP = phys.R_JUP_IN_R_SUN


# ------------------------------------------------------------- the arithmetic ---

def test_radius_is_the_square_root_of_the_depth():
    out = phys.companion_radius(0.01, 1.0)
    assert out["r_companion_sun"] == pytest.approx(0.1)


def test_a_jupiter_on_a_sun_reads_as_one_jupiter():
    depth = R_JUP ** 2                      # (R_Jup / R_Sun)^2
    out = phys.companion_radius(depth, 1.0)
    assert out["r_companion_jup"] == pytest.approx(1.0, rel=1e-9)
    assert out["verdict"] is None


def test_wasp18b_scale_transit_is_admissible():
    """The published planet: 1.35 R_Sun host, ~0.94 % depth."""
    out = phys.companion_radius(0.00937, 1.34658)
    assert out["r_companion_jup"] == pytest.approx(1.27, abs=0.02)
    assert out["verdict"] is None


def test_the_f_subgiant_binary_is_not_admissible():
    """TIC 287328866: 2.146 R_Sun host, 1.44 % detected depth."""
    out = phys.companion_radius(0.0144, 2.14575, crowdsap=0.80576)
    assert out["verdict"] == "companion-too-large"
    assert out["r_companion_jup"] > 2.5


def test_the_threshold_is_approached_from_both_sides():
    r_star = 1.0
    just_under = (2.49 * R_JUP / r_star) ** 2
    just_over = (2.51 * R_JUP / r_star) ** 2
    assert phys.companion_radius(just_under, r_star)["verdict"] is None
    assert phys.companion_radius(just_over, r_star)["verdict"] == "companion-too-large"


# ---------------------------------------------------------------- the crowding ---

def test_crowding_correction_is_reported_but_not_graded():
    """Correcting always inflates the companion; grading on it would refute
    candidates on the strength of a catalog model rather than a measurement."""
    depth = (2.0 * R_JUP) ** 2              # 2 R_Jup uncorrected on a 1 R_Sun star
    out = phys.companion_radius(depth, 1.0, crowdsap=0.4)
    assert out["verdict"] is None                       # graded on uncorrected
    assert out["r_companion_corrected_jup"] > 2.5       # corrected would have fired
    assert out["severely_blended"] is True


def test_the_severe_blend_flag_sits_where_the_constant_says():
    just_clean = phys.companion_radius(0.01, 1.0, crowdsap=phys.CROWDSAP_SEVERE)
    just_blended = phys.companion_radius(0.01, 1.0,
                                         crowdsap=phys.CROWDSAP_SEVERE - 0.01)
    assert just_clean["severely_blended"] is False
    assert just_blended["severely_blended"] is True


def test_a_corrected_depth_over_unity_is_flagged_not_turned_into_a_radius():
    out = phys.companion_radius(0.3, 1.0, crowdsap=0.1)
    assert out["r_companion_corrected_sun"] is None
    assert out["corrected_depth_exceeds_unity"] == pytest.approx(3.0)


def test_a_nonsense_crowdsap_is_ignored_rather_than_used():
    for bad in (0.0, -0.2, 1.5, "x", None):
        out = phys.companion_radius(0.01, 1.0, crowdsap=bad)
        assert out["r_companion_corrected_sun"] is None
        assert out["r_companion_sun"] == pytest.approx(0.1)


# ------------------------------------------------------------------ refusals ---

def test_an_unknown_radius_is_not_a_small_radius():
    """TIC 77044472 (T = 15.8) carries no RADIUS. The gate must abstain."""
    out = phys.companion_radius(0.0614, None)
    assert out["verdict"] is None
    assert out["reason"] == "no-stellar-radius"
    assert out["r_companion_sun"] is None


def test_a_zero_or_negative_radius_is_refused():
    for bad in (0.0, -1.0, float("nan"), "big"):
        assert phys.companion_radius(0.01, bad)["reason"] == "no-stellar-radius"


def test_a_depth_outside_zero_to_one_is_refused():
    for bad in (0.0, -0.01, 1.0, 2.0):
        assert phys.companion_radius(bad, 1.0)["reason"] == "depth-out-of-range"


def test_a_missing_depth_is_refused():
    assert phys.companion_radius(None, 1.0)["reason"] == "no-depth"


# ------------------------------------------------------------- the FITS bridge ---

def test_admissibility_reads_the_curve_keywords():
    curve = {"RADIUS": 2.14575, "CROWDSAP": 0.80576, "TEFF": 6210.0}
    assert phys.admissibility(0.0144, curve)["verdict"] == "companion-too-large"


def test_admissibility_on_a_curve_without_stellar_parameters():
    assert phys.admissibility(0.06, {"CROWDSAP": 0.14})["reason"] == "no-stellar-radius"


def test_admissibility_on_an_empty_or_missing_keyword_dict():
    for arg in ({}, None):
        assert phys.admissibility(0.01, arg)["reason"] == "no-stellar-radius"
