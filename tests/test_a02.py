"""A02 — the parts that must be true before any star is believed.

Network-free by construction: the sky half is exercised with synthetic signals
whose answer is planted, and the catalogue/resolution halves with fixtures. The
real six-star run is the receipt; these are the controls under it.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from lab import a02


def _sampled(period_days: float, *, days: float = 27.0, cadence_min: float = 2.0,
             amplitude: float = 0.01, noise: float = 0.001, seed: int = 7):
    """A clean sinusoid on a TESS-like cadence, with the answer planted."""
    rng = np.random.default_rng(seed)
    n = int(days * 24 * 60 / cadence_min)
    t = np.linspace(0.0, days, n)
    f = 1.0 + amplitude * np.sin(2 * np.pi * t / period_days) + rng.normal(0, noise, n)
    return t, f


# ── the estimator, against planted answers ──────────────────────────────────

@pytest.mark.parametrize("period", [0.0549, 0.1349, 0.5668, 2.5])
def test_a_planted_period_comes_back(period):
    """The positive control: if the estimator cannot recover a period it was
    handed, nothing it says about a real star means anything.

    Graded on the same criterion the science uses — the Rayleigh element —
    rather than a flat relative bar, which would have been a bar tuned to the
    short periods and unfair to the long ones: at P=2.5 d on a 27-day baseline
    only ~11 cycles are observed, and the resolution element is 0.23 d.
    """
    t, f = _sampled(period)
    m = a02.measure(t, f, seed=1)
    error = abs(m["period_days"] - period)
    resolution = a02.rayleigh_period_resolution(period, m["baseline_days"])
    assert error <= resolution / 50, f"{error:.2e} vs element {resolution:.2e}"


def test_refinement_beats_the_grid_it_sits_on():
    """The reason parabolic refinement exists: the raw grid point caps accuracy
    at the grid step, which is a property of the search and not of the data."""
    period = 0.3771
    t, f = _sampled(period)
    m = a02.measure(t, f, seed=1)
    grid_period = 1.0 / m["grid_frequency_cpd"]
    assert abs(m["period_days"] - period) < abs(grid_period - period)


def test_the_shuffled_control_collapses_on_noise_alone():
    """No signal, so the control must sit next to the 'detection' rather than
    far below it — the margin is what separates a period from a coincidence."""
    rng = np.random.default_rng(3)
    t = np.linspace(0.0, 27.0, 19_000)
    f = 1.0 + rng.normal(0, 0.001, t.size)
    m = a02.measure(t, f, seed=1)
    assert m["control_margin"] < a02.CONTROL_MARGIN


def test_a_real_signal_clears_the_control_by_a_wide_margin():
    t, f = _sampled(0.2)
    m = a02.measure(t, f, seed=1)
    assert m["control_margin"] >= a02.CONTROL_MARGIN


def test_refine_peak_falls_back_at_an_edge():
    freqs = np.array([1.0, 2.0, 3.0])
    amps = np.array([9.0, 1.0, 1.0])
    assert a02.refine_peak(freqs, amps, 0) == 1.0


def test_refine_peak_is_flat_safe():
    freqs = np.array([1.0, 2.0, 3.0])
    amps = np.array([1.0, 1.0, 1.0])
    assert a02.refine_peak(freqs, amps, 1) == 2.0


# ── naming a near-miss for what it is ───────────────────────────────────────

def test_harmonics_are_named_not_scored():
    """An amplitude spectrum peaks where the power is, which for an eclipsing
    binary is twice the orbital frequency. Calling that a recovery is the
    mistake this function exists to refuse."""
    assert a02.harmonic_relation(0.5, 1.0) == "P/2 — the first harmonic"
    assert a02.harmonic_relation(2.0, 1.0) == "2P — the subharmonic"
    assert a02.harmonic_relation(1.0, 1.0) is None


def test_resolution_is_the_rayleigh_element():
    assert a02.rayleigh_period_resolution(0.5, 25.0) == pytest.approx(0.01)


# ── resolution refuses to guess ─────────────────────────────────────────────

def test_two_tics_in_the_cone_is_ambiguous_not_the_first_row(monkeypatch):
    """A05 spent five days on a lead that was the neighbour's planet. A cone
    with two stars in it must refuse, not pick one."""
    monkeypatch.setattr(a02.a01, "_mast", lambda *a, **k: [
        {"target_name": "111", "sequence_number": 14},
        {"target_name": "222", "sequence_number": 14},
    ])
    found = a02.resolve_tess(1.0, 2.0)
    assert found["tic"] is None and "ambiguous" in found["reason"]


def test_an_empty_cone_is_reported_not_crashed(monkeypatch):
    monkeypatch.setattr(a02.a01, "_mast", lambda *a, **k: [])
    found = a02.resolve_tess(1.0, 2.0)
    assert found["tic"] is None and "no SPOC" in found["reason"]


def test_a_star_without_a_catalogue_period_is_skipped_not_invented(monkeypatch):
    monkeypatch.setattr(a02, "fetch_vsx",
                        lambda ident, **k: ({"Name": ident}, {"sha256": "x"}))
    result = a02.run_a02(targets=("Nothing Much",))
    assert result.targets[0]["outcome"] == "skipped-no-catalogue-period"
    assert result.graded == []


# ── the grader re-derives; it does not take the receipt's word ──────────────

def _receipt(tmp_path, monkeypatch, *, tamper=False):
    """A one-target A02 receipt whose caches are real files on disk."""
    from lab import a01 as a01_mod
    from lab import a05 as a05_mod
    from lab import checks

    period = 0.25
    t, f = _sampled(period)
    vsx_dir = tmp_path / "a02"
    vsx_dir.mkdir(parents=True)
    blob = json.dumps({"VSXObject": {"Name": "Fixture", "Period": str(period)}}).encode()
    (vsx_dir / "vsx-Fixture.json").write_bytes(blob)
    fits_dir = tmp_path / "fits"
    fits_dir.mkdir()
    (fits_dir / "curve.fits").write_bytes(b"not really a fits, curve_from_blob is stubbed")

    monkeypatch.setattr(a02, "CACHE_DIR", vsx_dir)
    monkeypatch.setattr(a01_mod, "CACHE_DIR", fits_dir)
    monkeypatch.setattr(a05_mod, "curve_from_blob", lambda raw: {"t": t, "f": f})

    import hashlib
    vsx_sha = hashlib.sha256(blob).hexdigest()
    fits_sha = hashlib.sha256((fits_dir / "curve.fits").read_bytes()).hexdigest()
    receipt = {
        "experiment": "A02-variable-star-recovery",
        "targets": [{
            "ident": "Fixture", "outcome": "measured", "control_seed": 1,
            "vsx": {"period_days": period,
                    "provenance": {"cache_file": "vsx-Fixture.json",
                                   "sha256": "0" * 64 if tamper else vsx_sha}},
            "photometry": {"cache_file": "curve.fits", "sha256": fits_sha},
            # A period the run never measured — the grader must ignore it.
            "period_days": 999.0,
        }],
    }
    return receipt, checks


def test_the_grader_ignores_the_receipts_own_number(tmp_path, monkeypatch):
    receipt, checks = _receipt(tmp_path, monkeypatch)
    ok, detail = checks.check_a02(receipt)
    assert ok is True, detail
    assert "999.0" not in detail, "the grader quoted the receipt instead of re-deriving"
    assert "0.249" in detail, "the grader must report the period it measured itself"


def test_a_broken_pin_is_false_never_a_shrug(tmp_path, monkeypatch):
    receipt, checks = _receipt(tmp_path, monkeypatch, tamper=True)
    ok, detail = checks.check_a02(receipt)
    assert ok is False and "does not match" in detail


def test_absent_evidence_is_its_own_verdict_not_a_failure(tmp_path, monkeypatch):
    """The run's light curves live on the box that downloaded them. On a clean
    checkout they are simply absent, and grading that as a failure would report
    broken science when what is missing is a file. It is also NOT `no-report`,
    which means a gap — this is a known, declared property of the milestone."""
    import pytest as _pytest

    receipt, checks = _receipt(tmp_path, monkeypatch)
    receipt["targets"][0]["photometry"]["cache_file"] = "gone.fits"
    with _pytest.raises(checks.EvidenceNotHere) as caught:
        checks.check_a02(receipt)
    assert "is absent" in str(caught.value)


def test_absent_evidence_grades_as_needs_evidence(tmp_path, monkeypatch):
    receipt, checks = _receipt(tmp_path, monkeypatch)
    receipt["targets"][0]["photometry"]["cache_file"] = "gone.fits"
    status, detail = checks._grade(checks.check_a02, [receipt])
    assert status == "needs-evidence"
    assert "lives on the box that produced it" in detail


def test_a_foreign_receipt_is_not_graded(tmp_path, monkeypatch):
    _unused, checks = _receipt(tmp_path, monkeypatch)
    ok, _detail = checks.check_a02({"experiment": "a05-survey-hunt"})
    assert ok is None
