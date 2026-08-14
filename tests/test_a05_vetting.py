"""A05 vetting tests — the spectral pulsation gate and the blend gates.

The synthetic fixtures reuse test_a04_maturity's synthesis style; the
real-curve tests run only where the publisher's FITS cache exists (CI has no
cache and must stay green). Nothing here encodes a per-TIC special case in
src/ — the cached targets exercise the GENERAL gates on real photometry.
"""
from __future__ import annotations

import numpy as np
import pytest

from lab import a01, a04, a05_vetting as a05v


def _flat(days=27.0, cadence=2.0 / 1440, noise=3e-4, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence)
    return t, 1.0 + rng.normal(0.0, noise, size=len(t))


def _cached(tic: str):
    return a01.CACHE_DIR / f"tess2018234235059-s0002-{int(tic):016d}-0121-s_lc.fits"


def _load_detrended(tic: str):
    curve = a01.read_tess_light_curve(_cached(tic).read_bytes(), ancillary=True)
    t, f, aux = a05v.normalise_with_ancillary(curve)
    td, fd = a04.detrend(t, f)
    return td, fd, aux


needs_pulsator = pytest.mark.skipif(
    not _cached("140940493").exists(), reason="publisher-local cache")
needs_wasp18 = pytest.mark.skipif(
    not _cached("100100827").exists(), reason="publisher-local cache")


# ----------------------------------------------------------------- spectrum ---

def test_amplitude_spectrum_recovers_a_known_sine():
    t, f = _flat(seed=4)
    f = f + 8e-4 * np.sin(2 * np.pi * 12.34 * t + 1.1)
    freqs, amps = a05v.amplitude_spectrum(t, f)
    j = int(np.argmax(amps))
    assert freqs[j] == pytest.approx(12.34, abs=0.02)
    assert amps[j] == pytest.approx(8e-4, rel=0.05)


def test_amplitude_spectrum_is_gap_robust():
    """The downlink gap must not move the peak or scramble the amplitude."""
    t, f = _flat(seed=5)
    keep = (t < 12.5) | (t > 14.0)
    t, f = t[keep], f[keep]
    f = f + 8e-4 * np.sin(2 * np.pi * 12.34 * t + 1.1)
    freqs, amps = a05v.amplitude_spectrum(t, f)
    j = int(np.argmax(amps))
    assert freqs[j] == pytest.approx(12.34, abs=0.02)
    assert amps[j] == pytest.approx(8e-4, rel=0.05)


def test_near_nyquist_degeneracy_reports_zero_not_garbage():
    """On perfectly uniform cadence the sin/cos columns collapse at Nyquist and
    a 3 ppm noise amplitude was observed inflating to 80 ppm — division by a
    vanishing determinant wearing a measurement's units."""
    t, f = _flat(seed=6)
    freqs, amps = a05v.amplitude_spectrum(t, f)
    nyquist_zone = np.abs(freqs - 360.0) < 2e-3
    if nyquist_zone.any():
        assert float(amps[nyquist_zone].max()) == 0.0
    # And nowhere does pure noise fake a coherent-signal amplitude.
    assert float(amps.max()) < 1e-4


def test_prewhiten_extracts_multiple_components():
    t, f = _flat(seed=7)
    f = (f + 9e-4 * np.sin(2 * np.pi * 8.0351 * t + 0.7)
           + 5e-4 * np.sin(2 * np.pi * 21.7 * t + 2.0))
    f_white, comps = a05v.prewhiten(t, f)
    got = sorted(nu for nu, _ in comps)
    assert any(abs(nu - 8.0351) < 0.01 for nu in got)
    assert any(abs(nu - 21.7) < 0.01 for nu in got)
    # The whitened flux carries no residual coherence worth a component.
    _, comps2 = a05v.prewhiten(t, f_white, max_components=2)
    assert all(amp < 1e-4 for _, amp in comps2)


def test_prewhiten_on_pure_noise_finds_nothing():
    t, f = _flat(seed=8)
    _, comps = a05v.prewhiten(t, f)
    assert comps == []


# ------------------------------------------------------- pulsation gate (1) ---

@needs_pulsator
def test_tic140940493_autogrades_from_spectrum():
    """The pilot's δ Scuti, graded by the GENERAL gate: its own blind_search
    detection (P≈0.6222 d) is commensurate with a pulsation frequency measured
    from its own flux — no per-TIC knowledge anywhere in src/."""
    td, fd, _ = _load_detrended("140940493")
    det = a04.blind_search(td, fd)
    assert det.sde >= a04.SDE_THRESHOLD
    f_white, comps = a05v.prewhiten(td, fd)
    row = a05v.extended_vet(td, f_white, det, comps)
    assert row["verdict"] == "stellar-pulsation"
    assert row["pulsation_cpd"] == pytest.approx(8.035, abs=0.05)
    assert row["harmonic_n"] in range(1, a05v.PULSATION_MAX_HARMONIC + 1)


# ------------------------------------------------ transit survival gate (2) ---

def test_injection_survives_prewhitening():
    """The gate that keeps the prewhitener from eating planets: a transit's
    Fourier comb tops the spectrum after the real sine is gone, but its power
    lives only in the dips, so the robust re-fit collapses and the loop stops
    instead of subtracting the planet harmonic by harmonic."""
    t, f = _flat(seed=11)
    f = f + 9e-4 * np.sin(2 * np.pi * 8.0 * t + 0.3)
    fi = a04.inject_box(t, f, period=3.1, depth=0.01)
    f_white, comps = a05v.prewhiten(t, fi)
    # The sine was found and removed…
    assert any(abs(nu - 8.0) < 0.01 for nu, _ in comps)
    # …and no component sits on a transit harmonic (k/3.1 c/d).
    for nu, _ in comps:
        k = nu * 3.1
        assert abs(k - round(k)) > 0.05
    det = a04.blind_search(t, f_white, n_periods=600)
    assert det.period_days == pytest.approx(3.1, rel=0.01)
    assert det.sde >= a04.SDE_THRESHOLD
    assert det.depth == pytest.approx(0.01, rel=0.10)


# --------------------------------------------------------- WASP-18 gate (3) ---

@needs_wasp18
def test_wasp18_gates_do_not_fire():
    """A real transit on the real target: no pulsation disposition, and the
    centroid gate must not mistake WASP-18's 4-sigma-but-0.014-px on-target
    shift for a blend."""
    td, fd, aux = _load_detrended("100100827")
    det = a04.blind_search(td, fd)
    assert det.period_days == pytest.approx(0.94145, rel=0.01)
    f_white, comps = a05v.prewhiten(td, fd)
    row = a05v.extended_vet(td, f_white, det, comps)
    assert row["verdict"] != "stellar-pulsation"
    cs = a05v.centroid_shift(td, aux["cx"], aux["cy"], det)
    assert cs["verdict"] is None
    assert cs["n_events"] >= a05v.CENTROID_MIN_EVENTS
    assert cs["implied_offset_px"] < a05v.CENTROID_MIN_OFFSET_PX


# ------------------------------------------- a04 verdicts pass through (4) ---

def test_eb_odd_even_lands_unchanged_through_extended_vet():
    t, f = _flat(noise=1e-4)
    period = 2.0
    epoch = np.floor(t / period).astype(int)
    ph = np.mod(t, period) / period
    box = np.abs(ph - 0.3) < 0.02
    f = f.copy()
    f[box & (epoch % 2 == 0)] *= 1 - 0.020
    f[box & (epoch % 2 == 1)] *= 1 - 0.010
    det = a04.Detection(period_days=period, depth=0.015, phase=0.3, sde=12.0)
    assert a05v.extended_vet(t, f, det, ()) == a04.vet_candidate(t, f, det)
    assert a05v.extended_vet(t, f, det, ())["verdict"] == "eclipsing-binary-odd-even"


def test_phased_brightening_lands_unchanged_through_extended_vet():
    t, f = _flat(noise=1e-4)
    period = 3.0
    ph = np.mod(t, period) / period
    f = f.copy()
    f[np.abs(ph - 0.2) < 0.02] *= 1 - 0.010
    f[np.abs(ph - 0.7) < 0.02] *= 1 + 0.008
    det = a04.Detection(period_days=period, depth=0.01, phase=0.2, sde=9.0)
    assert a05v.extended_vet(t, f, det, ())["verdict"] == "phased-brightening"


def test_period_railed_lands_unchanged_through_extended_vet():
    t, f = _flat(noise=1e-4)
    det = a04.Detection(period_days=a04.P_LO, depth=0.01, phase=0.3, sde=9.0)
    assert a05v.extended_vet(t, f, det, ())["verdict"] == "period-railed"


def test_fold_alias_still_fires_when_no_component_was_recorded():
    """A04's fold heuristic remains the fallback: a pulsator whose component
    list is empty (spectrum never run) still gets caught the old way."""
    t, f = _flat(noise=1e-4)
    p_true = 0.6222 / 5.0
    f = f * (1.0 - 0.0009 * (1.0 + np.cos(2 * np.pi * t / p_true)) / 2.0)
    det = a04.blind_search(t, f, n_periods=600)
    row = a05v.extended_vet(t, f, det, ())
    assert row["verdict"] == "harmonic-alias"


def test_spectral_gate_upgrades_the_same_pulsator():
    """The same synthetic pulsator, now WITH its spectrum measured: the general
    gate names the frequency instead of inferring a subharmonic from folds."""
    t, f = _flat(noise=1e-4)
    nu_true = 5.0 / 0.6222            # 8.036 c/d
    f = f * (1.0 - 0.0009 * (1.0 + np.cos(2 * np.pi * nu_true * t)) / 2.0)
    det = a04.blind_search(t, f, n_periods=600)
    f_white, comps = a05v.prewhiten(t, f)
    row = a05v.extended_vet(t, f_white, det, comps)
    assert row["verdict"] == "stellar-pulsation"
    assert row["pulsation_cpd"] == pytest.approx(nu_true, abs=0.05)


def test_planet_candidate_survives_extended_vet():
    t, f = _flat(noise=1e-4)
    fi = a04.inject_box(t, f, period=3.0, depth=0.01, duration_days=2.5 / 24)
    det = a04.blind_search(t, fi, n_periods=600)
    f_white, comps = a05v.prewhiten(t, fi)
    assert a05v.extended_vet(t, f_white, det, comps)["verdict"] == "planet-candidate"


# ------------------------------------------------------ reader + blends (5) ---

@needs_wasp18
def test_reader_roundtrip_parses_centroids_and_crowding():
    curve = a01.read_tess_light_curve(_cached("100100827").read_bytes(),
                                      ancillary=True)
    for name in a01.ANCILLARY_COLUMNS:
        assert isinstance(curve[name], np.ndarray)
        assert len(curve[name]) == len(curve["TIME"])
    assert 0.0 < curve["CROWDSAP"] <= 1.0
    assert 0.0 < curve["FLFRCSAP"] <= 1.0
    t, f, aux = a05v.normalise_with_ancillary(curve)
    assert len(aux["cx"]) == len(t)
    assert np.isfinite(aux["cx"]).all() and np.isfinite(aux["cy"]).all()


@needs_wasp18
def test_reader_default_contract_is_unchanged():
    """A05 must not move A01's floor: the legacy call returns exactly the four
    columns every existing caller depends on."""
    curve = a01.read_tess_light_curve(_cached("100100827").read_bytes())
    assert set(curve) == {"TIME", "PDCSAP_FLUX", "PDCSAP_FLUX_ERR", "QUALITY"}


def test_fitsless_path_degrades_to_none_and_no_gate_fires():
    """A curve with no ancillary data (synthetic dict, no FITS anywhere):
    every aux entry is None, and every gate declines to judge."""
    t = np.arange(0.0, 27.0, 2.0 / 1440)
    rng = np.random.default_rng(2)
    curve = {
        "TIME": t,
        "PDCSAP_FLUX": 1.0 + rng.normal(0, 3e-4, len(t)),
        "QUALITY": np.zeros(len(t), dtype=int),
    }
    tt, ff, aux = a05v.normalise_with_ancillary(curve)
    assert all(aux[k] is None for k in
               (*a01.ANCILLARY_COLUMNS, *a01.ANCILLARY_KEYWORDS, "cx", "cy"))
    det = a04.Detection(period_days=3.0, depth=0.01, phase=0.3, sde=9.0)
    cs = a05v.centroid_shift(tt, aux["cx"], aux["cy"], det)
    assert cs["verdict"] is None
    assert cs["reason"] == "no-centroid-data"
    cont = a05v.contamination(0.01, aux["CROWDSAP"])
    assert cont["depth_corrected"] is None
    assert cont["crowded"] is False


def test_centroid_gate_fires_on_a_synthetic_blend():
    """The positive control: an eclipse on a neighbour 2 px away at 1 % depth
    shifts the moment centroid by depth x offset = 0.02 px, repeatably."""
    t, _ = _flat(noise=1e-4, seed=3)
    period, ph0 = 3.0, 0.3
    det = a04.Detection(period_days=period, depth=0.01, phase=ph0, sde=9.0)
    rng = np.random.default_rng(3)
    cx = 100.0 + rng.normal(0, 1e-3, len(t))
    cy = 200.0 + rng.normal(0, 1e-3, len(t))
    phase = np.mod(t, period) / period
    in_tr = np.abs(((phase - ph0 + 0.5) % 1.0) - 0.5) < a04.VET_WINDOW_PHASE
    cx[in_tr] += 0.02
    row = a05v.centroid_shift(t, cx, cy, det)
    assert row["verdict"] == "centroid-shift"
    assert row["shift_sigma"] > a05v.CENTROID_SIGMA
    assert row["implied_offset_px"] == pytest.approx(2.0, rel=0.25)


def test_centroid_gate_needs_enough_events():
    t = np.arange(0.0, 4.0, 2.0 / 1440)          # < 2 full periods
    det = a04.Detection(period_days=3.0, depth=0.01, phase=0.3, sde=9.0)
    cx = np.full(len(t), 100.0)
    cy = np.full(len(t), 200.0)
    row = a05v.centroid_shift(t, cx, cy, det)
    assert row["verdict"] is None
    assert row["reason"] == "insufficient-events"


def test_contamination_reports_both_depths_and_flags_crowding():
    row = a05v.contamination(0.005, 0.5)
    assert row["depth_observed"] == pytest.approx(0.005)
    assert row["depth_corrected"] == pytest.approx(0.010)
    assert row["crowded"] is True
    clean = a05v.contamination(0.005, 0.95)
    assert clean["crowded"] is False
    assert clean["depth_corrected"] == pytest.approx(0.005 / 0.95)
    # A nonsense keyword degrades like a missing one.
    assert a05v.contamination(0.005, 0.0)["depth_corrected"] is None
