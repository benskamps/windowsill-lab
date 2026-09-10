"""weird — the anomaly loop, and the controls that decide whether to believe it.

The load-bearing tests are not the ones checking that a detector FINDS a planted
anomaly. They are the ones checking it WITHHOLDS its report when it fails to.
Two earlier dead-gate linters written the same day reported a clean floor
because they could not see the floor; only a control caught them. A detector
whose silence has never been tested is a detector whose silence means nothing.
"""
import math

import pytest

from lab import weird


def _corpus(n=400, seed=7):
    """A synthetic corpus with a known relation and one planted violator."""
    rows = []
    x = seed
    for i in range(n):
        x = (1103515245 * x + 12345) % (1 << 31)          # deterministic
        base = 1.0 + (x % 1000) / 10000.0
        rows.append({"_id": f"t{i}", "_src": "a.json",
                     "a": base, "b": base * 2.0, "c": 0.5})
    rows[123]["b"] = rows[123]["a"] * 2000.0              # the planted anomaly
    rows[123]["_id"] = "PLANTED"
    return rows


# ── the detectors see what is there ─────────────────────────────────────────

def test_ratio_family_finds_a_planted_violation():
    rep = weird.ratio_violations(_corpus(), control_id="PLANTED")
    assert rep.saw_control
    assert any(f.subject == "PLANTED" for f in rep.findings)


def test_censored_family_finds_values_pinned_to_a_ceiling():
    rows = [{"_id": f"t{i}", "_src": "a.json", "d": 0.002} for i in range(50)]
    rows += [{"_id": f"c{i}", "_src": "a.json", "d": 0.010} for i in range(10)]
    rep = weird.censored_values(rows, {"d": (0.002, 0.004, 0.010)},
                                control_field="d")
    assert rep.saw_control
    assert "10 of 60" in rep.findings[0].detail


def test_absent_family_finds_a_field_that_starts_partway_through():
    rows = [{"_id": f"a{i}", "_src": "01.json", "x": 1.0} for i in range(10)]
    rows += [{"_id": f"b{i}", "_src": "02.json", "x": 1.0, "late": 2.0}
             for i in range(10)]
    rep = weird.absent_fields(rows, control_field="late")
    assert rep.saw_control
    assert any("first appears" in f.detail for f in rep.findings)


def test_signature_family_finds_what_a_group_shares():
    rows = [{"_id": f"t{i}", "_src": "a.json", "slow": 20.0} for i in range(400)]
    for i in range(4):
        rows.append({"_id": f"g{i}", "_src": "a.json", "slow": 900.0})
    rep = weird.group_signature(rows, {"g0", "g1", "g2", "g3"},
                                control_field="slow")
    assert rep.saw_control


# ── the detectors REFUSE when they cannot see. This is the point. ───────────

def test_a_detector_that_misses_its_control_withholds_everything():
    rep = weird.ratio_violations(_corpus(), control_id="A-STAR-THAT-IS-NOT-HERE")
    assert rep.saw_control is False
    assert bool(rep) is False
    out = rep.render()
    assert "BLIND" in out and "withheld" in out
    # the findings still exist on the object — they are simply not reportable
    assert "PLANTED" not in out


def test_censored_family_withholds_when_its_control_is_not_censored():
    rows = [{"_id": f"t{i}", "_src": "a.json", "d": 0.002} for i in range(50)]
    rep = weird.censored_values(rows, {"d": (0.002, 0.004, 0.010)},
                                control_field="d")
    assert rep.saw_control is False
    assert "BLIND" in rep.render()


def test_blind_report_is_falsey_so_a_caller_cannot_use_it_by_accident():
    rep = weird.Report("x", [weird.Finding("x", "s", "d")], False, "ctl")
    assert not rep


# ── properties that keep findings honest ────────────────────────────────────

def test_a_star_in_many_sources_is_one_anomaly_not_many():
    """The row-vs-star distinction that made the shelf read 10 leads for 9."""
    rows = _corpus()
    dup = dict(rows[123]); dup["_src"] = "b.json"
    rows.append(dup)
    rep = weird.ratio_violations(rows, control_id="PLANTED")
    planted = [f for f in rep.findings if f.subject == "PLANTED"]
    keys = {(f.evidence["field_a"], f.evidence["field_b"]) for f in planted}
    assert len(planted) == len(keys), "same star + same field pair counted twice"


def test_a_loose_relation_is_not_treated_as_a_norm():
    """A ratio that scatters is not a relation, so nothing can violate it."""
    rows = []
    x = 3
    for i in range(400):
        x = (1103515245 * x + 12345) % (1 << 31)
        rows.append({"_id": f"t{i}", "_src": "a.json",
                     "a": 1.0, "b": 1.0 + (x % 10000) / 100.0})
    rep = weird.ratio_violations(rows, control_id="PLANTED")
    assert not any(f.evidence.get("field_a") == "a"
                   and f.evidence.get("field_b") == "b" for f in rep.findings)


def test_too_few_rows_is_not_a_relation():
    rows = [{"_id": f"t{i}", "_src": "a.json", "a": 1.0, "b": 2.0}
            for i in range(weird.MIN_PAIRS - 1)]
    rows[0]["b"] = 500.0
    rep = weird.ratio_violations(rows, control_id="t0")
    assert rep.findings == []


def test_booleans_are_not_numbers():
    """A True that flattens to 1.0 invents a relation out of a flag."""
    flat = weird.flatten({"ok": True, "n": 3, "nested": {"x": 1.5}})
    assert "ok" not in flat
    assert flat == {"n": 3.0, "nested.x": 1.5}


def test_non_finite_values_are_dropped_not_propagated():
    flat = weird.flatten({"a": float("nan"), "b": float("inf"), "c": 2.0})
    assert flat == {"c": 2.0}


# ── against the real corpus, when it is present ─────────────────────────────

@pytest.mark.skipif(
    not (weird.Path(__file__).resolve().parent.parent / "reports" / "hunts"
         ).exists(), reason="no committed hunt receipts")
def test_the_real_corpus_reproduces_its_known_anomalies():
    """The two anomalies this module was built on, on committed data:
    TIC 234518605's depth disagreement and the censored injection ladder."""
    root = weird.Path(__file__).resolve().parent.parent / "reports" / "hunts"
    rows = weird.load_rows(root.glob("hunt-*.json"), "targets")
    if len(rows) < 1000:
        pytest.skip("corpus too small in this checkout")
    assert weird.ratio_violations(rows, control_id="234518605").saw_control
    ladder = {f"d_min.{p}": (0.002, 0.004, 0.010) for p in ("2.3", "3.7", "5.1")}
    rep = weird.censored_values(rows, ladder, control_field="d_min.2.3")
    assert rep.saw_control
