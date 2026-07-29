"""One M01 quality decision must drive every public surface."""
from __future__ import annotations

from lab.m01_quality import assess_m01_quality, nonequilibrated_indices


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
