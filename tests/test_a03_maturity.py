"""A03 maturity regressions: the control gate, the ISCO argument, and recovery.

The load-bearing behaviour is that a failed positive control makes the sky
result UNINTERPRETABLE (None), not negative (False). An early A03 prototype
reported chirp masses of 1.174 and 1.238 M_sun that were pure noise; the
injection test is what caught it, so the check must refuse to grade the sky
whenever that control is absent or failing.
"""
from __future__ import annotations

import numpy as np
import pytest

from lab import a03, checks, pn


# ---------------------------------------------------------------- waveform ---

def test_isco_is_why_a03_avoids_gw150914():
    """A ~66 Msun binary leaves the inspiral band at ~67 Hz."""
    eta = 0.25
    mc_66 = 66.0 * eta ** 0.6          # chirp mass of an equal-mass 66 Msun system
    assert pn.isco_frequency(mc_66, eta) == pytest.approx(66.6, abs=1.5)
    # a binary neutron star stays in band far past any analysis cutoff
    mc_bns = 1.19786
    assert pn.isco_frequency(mc_bns, 0.249) > 1400.0


def test_template_is_confined_to_the_band_and_truncated_at_isco():
    freqs = np.linspace(0.0, 2000.0, 4001)
    h = pn.taylorf2_35(freqs, 1.19786, 0.249, 25.0, 480.0)
    assert np.all(h[freqs < 25.0] == 0)
    assert np.all(h[freqs > 480.0] == 0)
    assert np.any(h[(freqs >= 25.0) & (freqs <= 480.0)] != 0)
    # heavy binary: ISCO, not f_high, sets the cutoff
    heavy = pn.taylorf2_35(freqs, 28.6, 0.25, 25.0, 480.0)
    top = freqs[np.nonzero(heavy)[0].max()]
    assert top < 200.0


def test_phase_bracket_reduces_to_newtonian_as_v_goes_to_zero():
    v = np.array([1e-6])
    assert pn.phase_35pn(v, 0.25)[0] == pytest.approx(1.0, abs=1e-3)


# -------------------------------------------------------------- the filter ---

def test_matched_filter_recovers_an_injected_chirp_mass():
    """End-to-end on synthetic noise: the measurement the sky run could not make."""
    rng = np.random.default_rng(20260807)
    fs, seg = 1024, 64
    n = fs * seg
    t0, event = 0.0, 40.0
    noise = rng.normal(0.0, 1e-21, n)

    flt = a03.MatchedFilter(noise, fs, t0, event)
    mc_true, eta = 1.19786, 0.2490
    injected = a03.inject(noise, flt, mc_true, eta, event, rho=40.0)

    probe = a03.MatchedFilter(injected, fs, t0, event)
    grid = np.arange(mc_true - 0.004, mc_true + 0.004, 2e-5)
    found = probe.scan(grid, eta)

    assert found["peak_snr"] > found["background_max"]
    assert found["mc_detector"] == pytest.approx(mc_true, abs=1e-3)
    assert found["gps_peak"] == pytest.approx(event, abs=0.01)


def test_gate_removes_a_planted_transient():
    rng = np.random.default_rng(7)
    fs, n = 1024, 1024 * 64
    x = rng.normal(0.0, 1e-21, n)
    hit = int(30.5 * fs)
    x[hit:hit + 40] += 4e-19                      # a loud, narrow artefact
    gated, gates = a03.gate_transients(x, fs, 0.0, 40.0)
    assert gates, "the planted transient should be found"
    assert gates[0]["peak_sigma"] > 6.0
    assert np.abs(gated[hit:hit + 40]).max() < np.abs(x[hit:hit + 40]).max() / 10


# --------------------------------------------------------------- the check ---

def _report(*, control_err=2e-5, control_snr=38.0, control_bg=10.0,
            sky_snr=6.6, sky_bg=10.7, sky_mc=1.1520) -> dict:
    pub_src, z = 1.186, 0.01
    pub_det = pub_src * (1 + z)
    det = lambda name: {                                    # noqa: E731
        "detector": name,
        "control": {"peak_snr": control_snr, "background_max": control_bg,
                    "mc_detector": pub_det + control_err, "gps_peak": 0.0},
        "real": {"peak_snr": sky_snr, "background_max": sky_bg,
                 "mc_detector": sky_mc * (1 + z), "gps_peak": 0.0},
        "control_error_msun": abs(control_err),
    }
    return {
        "experiment": "A03-gwosc-chirp-mass",
        "event": "GW170817-v3",
        "redshift": z,
        "published_chirp_mass_source": pub_src,
        "published_chirp_mass_source_lower": 0.001,
        "published_chirp_mass_source_upper": 0.001,
        "published_chirp_mass_detector": pub_det,
        "control_tolerance_msun": 1e-3,
        "detectors": [det("H1"), det("L1")],
        "products": [{"sha256": "a" * 64}, {"sha256": "b" * 64}],
    }


def test_check_grades_the_shipped_null_as_false():
    ok, detail = checks.check_a03(_report())
    assert ok is False
    assert "NOT recovered" in detail
    assert "injection recovered" in detail


def test_check_passes_when_the_sky_is_recovered():
    ok, detail = checks.check_a03(_report(sky_snr=30.0, sky_bg=10.0, sky_mc=1.1863))
    assert ok is True
    assert "reproduced" in detail


def test_failed_control_makes_the_result_uninterpretable_not_negative():
    """The whole point: a broken pipeline must not be read as 'no signal'."""
    ok, detail = checks.check_a03(_report(control_err=0.05))
    assert ok is None
    assert "uninterpretable" in detail

    ok, _ = checks.check_a03(_report(control_snr=3.0, control_bg=10.0))
    assert ok is None


def test_check_requires_pinned_products_and_two_detectors():
    rep = _report()
    rep["products"] = [{"sha256": "not-a-hash"}]
    ok, detail = checks.check_a03(rep)
    assert ok is False and "SHA-256" in detail

    rep = _report()
    rep["detectors"] = rep["detectors"][:1]
    ok, detail = checks.check_a03(rep)
    assert ok is False and "two independent detectors" in detail


def test_check_ignores_other_experiments():
    assert checks.check_a03({"experiment": "A01-tess-hot-jupiter-calibration"})[0] is None


def test_a03_is_registered():
    assert checks.CHECKS["A03"] is checks.check_a03
