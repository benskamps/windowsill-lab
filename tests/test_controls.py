"""Published controls: cross-updater agreement (positive) + a J=0 null (negative).

Credibility from a re-derivable probe, not prose: two independent updaters must
agree on one number, and turning the coupling off must NOT manufacture a peak.
"""
from __future__ import annotations

import copy

from lab import controls
from lab.checks import check_controls


def _report():
    # Small CPU run — the same tiny lattice the wolff↔metropolis agreement tests use.
    return controls.build_controls_report(L=16, temps=(1.8, 3.2), seed=42, device="cpu")


def test_report_shape():
    rep = _report()
    assert rep["experiment"] == controls.CONTROLS_EXPERIMENT
    assert len(rep["controls"]) == 4          # 2 temps × (energy, abs_mag)
    for e in rep["controls"]:
        assert e["name"] == "wolff-vs-metropolis"
        assert set(e) >= {"T", "L", "observable", "metropolis", "wolff", "delta", "tol"}
    assert rep["null_control"]["name"] == "null-coupling-J0-flat-chi"


def test_cross_updater_agreement_passes():
    rep = _report()
    ok, detail = check_controls(rep)
    assert ok is True, detail
    # Two independent correct updaters land on the same number.
    for e in rep["controls"]:
        assert e["delta"] <= e["tol"]


def test_null_coupling_shows_no_peak():
    rep = _report()
    null = rep["null_control"]
    # J=0 → χ flat: prominence stays near 1, far below the real-peak cap.
    assert null["peak_to_median_ratio"] <= null["ratio_max"]


def test_check_fails_when_updaters_disagree():
    rep = _report()
    tampered = copy.deepcopy(rep)
    tampered["controls"][0]["delta"] = 0.9      # a silently broken updater
    ok, detail = check_controls(tampered)
    assert ok is False
    assert "✗" in detail or "failed" in detail


def test_check_fails_when_null_grows_a_peak():
    rep = _report()
    tampered = copy.deepcopy(rep)
    tampered["null_control"]["peak_to_median_ratio"] = 15.0   # a spurious peak
    ok, _ = check_controls(tampered)
    assert ok is False


def test_check_ignores_non_controls_report():
    assert check_controls({"experiment": "M01-ising-verification"})[0] is None


def test_registered_in_checks():
    from lab.checks import CHECKS
    assert CHECKS.get("CTRL") is check_controls
