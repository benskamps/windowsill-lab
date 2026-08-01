"""One M01 quality decision must drive every public surface.

Incident fixtures live in ``tests/golden/sick-sweeps/``. When a campaign pass
publishes a sweep this module misgrades, harvest the receipt into a permanent
fixture with:

    git show <commit>:reports/receipts/run-<date>-m01.json \\
        > tests/golden/sick-sweeps/<date>-<short-description>.json

then add it to the verdict table in ``test_sick_sweep_fixtures_grade_invalid``
below, red-first. Every future incident costs exactly one fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab.m01_quality import assess_m01_quality, nonequilibrated_indices

SICK_SWEEPS = Path(__file__).resolve().parent / "golden" / "sick-sweeps"


def _load_sick(name: str) -> dict:
    return json.loads((SICK_SWEEPS / name).read_text(encoding="utf-8"))


def _metastable_report():
    return {
        "experiment": "M01-ising-verification",
        "T": [1.5, 1.6, 2.2, 2.3, 2.4],
        # T=1.5 is a noisy metastable domain.  The sharp rise to T=1.6
        # identifies the noisier left endpoint as non-equilibrated.
        "abs_mag": [0.62, 0.98, 0.82, 0.66, 0.42],
        "abs_mag_err": [0.02, 0.001, 0.004, 0.005, 0.006],
        "chi": [1900.0, 2.0, 20.0, 81.0, 33.0],
    }


def test_quality_excludes_metastable_raw_argmax_and_recovers_peak():
    report = _metastable_report()
    assert nonequilibrated_indices(report) == [0]
    quality = assess_m01_quality(report)
    assert quality["status"] == "degraded"
    assert quality["excluded_indices"] == [0]
    assert quality["peak_index"] == 3
    assert quality["peak_t"] == 2.3
    assert "excluded" in quality["note"]


def test_clean_sweep_is_ok():
    report = {
        "T": [2.2, 2.3, 2.4],
        "abs_mag": [0.8, 0.6, 0.4],
        "abs_mag_err": [0.01, 0.01, 0.01],
        "chi": [2.0, 8.0, 3.0],
    }
    quality = assess_m01_quality(report)
    assert quality["status"] == "ok"
    assert quality["excluded_indices"] == []
    assert quality["peak_t"] == 2.3


def test_nonfinite_sweep_is_invalid_and_claims_no_peak():
    quality = assess_m01_quality({"T": [2.2, 2.3], "chi": [1.0, float("nan")]})
    assert quality["status"] == "invalid"
    assert quality["peak_t"] is None
    assert "no T_c claimed" in quality["note"]


def test_more_than_two_bad_samples_invalidates_whole_sweep():
    report = {
        "T": [1, 2, 3, 4, 5, 6],
        "abs_mag": [0.1, 0.9, 0.1, 0.9, 0.1, 0.9],
        "abs_mag_err": [0.1, 0.001, 0.1, 0.001, 0.1, 0.001],
        "chi": [1, 2, 3, 4, 5, 6],
    }
    quality = assess_m01_quality(report)
    assert len(quality["excluded_indices"]) == 3
    assert quality["status"] == "invalid"
    assert quality["peak_t"] is None


# ── sick-sweep golden fixtures (real published incidents) ────────────────────

@pytest.mark.parametrize("name", [
    # Campaign pass 43 (commit 6877c08, seed 1043): |M| falls monotonically
    # across the metastable T=1.7/1.8 shelf, so the rise-only guard passed the
    # samples whose χ (689.6/856.0) dwarfs their equilibrated scale (~0.05/0.36)
    # and the qualified argmax crowned T=1.8 vs Onsager 2.269 (z=-4.69, red main).
    "2026-07-29-pass43-monotone-metastable.json",
])
def test_sick_sweep_fixtures_grade_invalid(name):
    quality = assess_m01_quality(_load_sick(name))
    assert quality["status"] == "invalid"
    assert quality["peak_t"] is None
    assert quality["peak_index"] is None
    assert "no T_c claimed" in quality["note"]


def test_pass43_names_the_metastable_shelf_in_note_and_exclusions():
    report = _load_sick("2026-07-29-pass43-monotone-metastable.json")
    quality = assess_m01_quality(report)
    # The rise guard alone caught only [0, 4]; the χ-scale guard must also pull
    # the monotone-decreasing shelf at T=1.7/1.8 (indices 2, 3) out of candidacy.
    assert {2, 3} <= set(quality["excluded_indices"])
    assert {2, 3}.isdisjoint(quality["valid_indices"])
    assert "χ-scale" in quality["note"]


def test_pass43_data_shape_is_the_hole_the_rise_guard_misses():
    """Pin the defect mechanism: the shelf falls, so no rise ever fires on it."""
    report = _load_sick("2026-07-29-pass43-monotone-metastable.json")
    mag = [float(m) for m in report["abs_mag"]]
    chi = [float(c) for c in report["chi"]]
    assert mag[1] > mag[2] > mag[3] > mag[4]          # monotone across the shelf
    assert nonequilibrated_indices(report) == [0, 4]  # rise guard alone misses 2, 3
    shelf_peak = max((2, 3, 8), key=lambda i: chi[i])
    assert shelf_peak == 3                            # argmax without χ-scale: T=1.8


def test_chi_scale_suspect_alone_degrades_and_recovers_peak():
    """An ordered-phase χ spike with no |M| rise anywhere is still excluded."""
    T = [round(1.5 + 0.1 * i, 1) for i in range(21)]
    mag = [0.986, 0.980, 0.970, 0.957, 0.938, 0.911, 0.869, 0.784, 0.284, 0.077,
           0.050, 0.037, 0.031, 0.026, 0.023, 0.021, 0.020, 0.018, 0.017, 0.017,
           0.016]
    chi = [0.0, 0.0, 900.0, 0.1, 0.2, 0.3, 0.6, 2.1, 750.0, 63.0,
           25.0, 13.7, 8.7, 6.3, 4.7, 3.9, 3.3, 2.7, 2.3, 2.1, 1.8]
    report = {
        "T": T, "chi": chi, "abs_mag": mag, "abs_mag_err": [0.0005] * 21,
    }
    assert nonequilibrated_indices(report) == []      # |M| never rises
    quality = assess_m01_quality(report)
    assert quality["status"] == "degraded"
    assert quality["excluded_indices"] == [2]
    assert quality["peak_t"] == pytest.approx(2.3)
    assert "χ-scale" in quality["note"]


def test_chi_scale_guard_needs_a_disordered_tail_to_arm():
    """Sweeps that stop near T_c carry no background χ scale — guard stays inert."""
    report = {
        "T": [1.5, 1.6, 2.2, 2.3, 2.4],
        "abs_mag": [0.98, 0.97, 0.82, 0.66, 0.42],
        "abs_mag_err": [0.001] * 5,
        "chi": [1900.0, 2.0, 20.0, 81.0, 33.0],
    }
    quality = assess_m01_quality(report)
    assert quality["status"] == "ok"
    assert quality["peak_t"] == 1.5


# ── malformed guard arrays must fail closed, naming the field ────────────────

def test_corrupt_abs_mag_fails_closed_naming_the_field():
    quality = assess_m01_quality({
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 5.0, 2.0],
        "abs_mag": ["corrupt", "data", "here"],
        "abs_mag_err": [0.1, 0.1, 0.1],
    })
    assert quality["status"] == "invalid"
    assert quality["peak_t"] is None
    assert "abs_mag" in quality["note"]
    assert "passed" not in quality["note"]


def test_corrupt_abs_mag_err_fails_closed_naming_the_field():
    quality = assess_m01_quality({
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 5.0, 2.0],
        "abs_mag": [0.8, 0.6, 0.4],
        "abs_mag_err": ["x", "y", "z"],
    })
    assert quality["status"] == "invalid"
    assert "abs_mag_err" in quality["note"]
    assert "passed" not in quality["note"]


def test_one_corrupt_element_cannot_disarm_the_guard():
    """A bad value anywhere must not silently return the sweep to 'ok'."""
    report = {
        "T": [1.5, 1.6, 2.2, 2.3, 2.4],
        "abs_mag": [0.62, 0.98, 0.82, 0.66, None],   # rise at 0→1 AND a sick tail value
        "abs_mag_err": [0.02, 0.001, 0.004, 0.005, 0.006],
        "chi": [1900.0, 2.0, 20.0, 81.0, 33.0],
    }
    quality = assess_m01_quality(report)
    assert quality["status"] == "invalid"
    assert "abs_mag" in quality["note"]


def test_length_mismatched_abs_mag_fails_closed():
    quality = assess_m01_quality({
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 5.0, 2.0],
        "abs_mag": [0.8, 0.6],
        "abs_mag_err": [0.1, 0.1, 0.1],
    })
    assert quality["status"] == "invalid"
    assert "abs_mag" in quality["note"]


def test_abs_mag_present_without_err_fails_closed():
    quality = assess_m01_quality({
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 5.0, 2.0],
        "abs_mag": [0.8, 0.6, 0.4],
    })
    assert quality["status"] == "invalid"
    assert "abs_mag_err" in quality["note"]


def test_absent_guard_arrays_stay_legacy_ok():
    """Old receipts carry no |M| at all — deliberately no exclusions, not invalid."""
    quality = assess_m01_quality({
        "T": [2.2, 2.3, 2.4],
        "chi": [2.0, 8.0, 3.0],
    })
    assert quality["status"] == "ok"
    assert quality["peak_t"] == 2.3


def test_nonequilibrated_indices_sentinel_distinguishes_malformed_from_absent():
    legacy = {"T": [2.2, 2.3], "chi": [1.0, 2.0]}
    corrupt = {
        "T": [2.2, 2.3],
        "chi": [1.0, 2.0],
        "abs_mag": ["bad", "data"],
        "abs_mag_err": [0.1, 0.1],
    }
    assert nonequilibrated_indices(legacy) == []
    assert nonequilibrated_indices(corrupt) is None
