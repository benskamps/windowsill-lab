"""The golden-seed determinism gate proves the instrument reproduces itself.

Most of these tests are pure (no torch): they exercise the structural + numeric
grading of a fresh measurement against a golden. Two integration tests actually
re-run the pinned CPU smoke config to prove self-determinism and agreement with
the committed golden.
"""
from __future__ import annotations

import copy
import json

import pytest

from lab import determinism as d


# ── pure grading logic (no torch) ────────────────────────────────────────────
def _fake_measurement() -> dict:
    return {
        "config": dict(d.SMOKE_CONFIG),
        "T": [1.6, 2.0, 2.4, 3.0],
        "abs_mag": [0.98, 0.90, 0.51, 0.20],
        "chi": [0.04, 0.6, 33.0, 4.8],
        "chi_abs": [0.03, 0.5, 20.0, 3.0],
        "energy": [-1.9, -1.6, -1.1, -0.7],
        "specific_heat": [0.1, 0.5, 1.4, 0.3],
    }


def test_identical_measurement_agrees():
    m = _fake_measurement()
    ok, detail, max_rel = d._numeric_agreement(m, copy.deepcopy(m))
    assert ok is True
    assert max_rel == 0.0
    assert "reproduces the golden" in detail


def test_tiny_perturbation_within_tolerance_passes():
    m = _fake_measurement()
    perturbed = copy.deepcopy(m)
    # 1% bump on a mid-size value — inside the check-owned band.
    perturbed["abs_mag"][1] *= 1.01
    ok, _detail, max_rel = d._numeric_agreement(m, perturbed)
    assert ok is True
    assert 0.0 < max_rel <= d.GOLDEN_RTOL


def test_large_perturbation_fails_as_regression():
    fresh = _fake_measurement()
    golden = copy.deepcopy(fresh)
    # A 50% shift on the susceptibility peak — a regression, far beyond platform drift.
    golden["chi"][2] *= 0.5
    ok, detail, _max_rel = d._numeric_agreement(fresh, golden)
    assert ok is False
    assert "diverged from the golden beyond tolerance" in detail


def test_structural_mismatch_fails_hard():
    fresh = _fake_measurement()
    # Wrong array length — a structural regression, caught platform-independently.
    golden = copy.deepcopy(fresh)
    golden["chi"] = golden["chi"][:-1]
    ok, detail, _ = d._numeric_agreement(fresh, golden)
    assert ok is False
    assert "structural regression" in detail


def test_config_drift_fails_hard():
    fresh = _fake_measurement()
    golden = copy.deepcopy(fresh)
    golden["config"] = dict(golden["config"], seed=7)
    ok, detail, _ = d._numeric_agreement(fresh, golden)
    assert ok is False
    assert "config" in detail


def test_canonical_sha_is_stable_and_order_independent():
    m = _fake_measurement()
    # Rebuilding the dict in a different key order must not change the sha.
    reordered = {k: m[k] for k in reversed(list(m))}
    assert d.canonical_sha(m) == d.canonical_sha(reordered)


def test_committed_golden_is_well_formed():
    golden = d.load_golden()
    assert golden["schema"] == d.GOLDEN_SCHEMA
    assert len(golden["sha256"]) == 64
    # The stored sha must match the sha of the stored measurement (no drift on disk).
    assert d.canonical_sha(golden["measurement"]) == golden["sha256"]
    assert golden["config"] == {k: d.SMOKE_CONFIG[k] for k in sorted(d.SMOKE_CONFIG)}


def test_gate_missing_golden_is_reported(tmp_path, monkeypatch):
    # A missing golden is an honest failure, not a crash — patch measure() so this
    # stays torch-free and fast.
    m = _fake_measurement()
    monkeypatch.setattr(d, "measure", lambda: copy.deepcopy(m))
    res = d.run_gate(golden_path=tmp_path / "nope.json")
    assert res["ok"] is False
    assert res["self_deterministic"] is True
    assert res["golden"] == "missing"


def test_gate_detects_nondeterminism(monkeypatch):
    # Simulate a nondeterministic engine: two different measurements in a row.
    seq = iter([_fake_measurement(), dict(_fake_measurement(), chi=[9, 9, 9, 9])])
    monkeypatch.setattr(d, "measure", lambda: next(seq))
    res = d.run_gate()
    assert res["ok"] is False
    assert res["self_deterministic"] is False
    assert "NON-DETERMINISTIC" in res["detail"]


# ── integration: really re-run the CPU smoke config (torch) ──────────────────
def test_smoke_run_is_self_deterministic():
    m1 = d.measure()
    m2 = d.measure()
    assert d.canonical_sha(m1) == d.canonical_sha(m2)


def test_gate_passes_against_committed_golden():
    res = d.run_gate()
    assert res["ok"] is True, res["detail"]
    assert res["self_deterministic"] is True
    assert res["golden"] in {"bit-exact", "numeric"}


def test_gate_fails_against_a_perturbed_golden(tmp_path):
    # Bless a golden, corrupt its peak susceptibility well beyond tolerance, and
    # prove the gate rejects it end to end.
    golden = d.build_golden()
    golden["measurement"]["chi"] = [c * 0.25 for c in golden["measurement"]["chi"]]
    golden["sha256"] = d.canonical_sha(golden["measurement"])
    bad = tmp_path / "bad-golden.json"
    bad.write_text(json.dumps(golden), encoding="utf-8")
    res = d.run_gate(golden_path=bad)
    assert res["ok"] is False
    assert res["golden"] == "regression"
