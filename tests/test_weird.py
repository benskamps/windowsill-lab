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


# ── the wider suite ─────────────────────────────────────────────────────────

def _flat(n=400, **cols):
    rows = []
    for i in range(n):
        r = {"_id": f"t{i}", "_src": f"{i//100:02d}.json"}
        for k, fn in cols.items():
            r[k] = fn(i)
        rows.append(r)
    return rows


def test_pileup_finds_a_ceiling_it_was_never_told_about():
    rows = _flat(400, v=lambda i: 1.0 if i < 300 else i / 100.0)
    rep = weird.boundary_pileups(rows, control_field="v")
    assert rep.saw_control
    assert "min" in rep.findings[0].detail or "max" in rep.findings[0].detail


def test_secretly_discrete_flags_a_category_wearing_a_float():
    rows = _flat(400, v=lambda i: float(i % 3))
    rep = weird.secretly_discrete(rows, control_field="v")
    assert rep.saw_control


def test_redundant_finds_one_fact_stored_twice():
    rows = _flat(400, a=lambda i: float(i + 1),
                 b=lambda i: float((i + 1) * 2.5))
    rep = weird.redundant_fields(rows, control_pair=("a", "b"))
    assert rep.saw_control


def test_hidden_dependence_sees_a_shape_correlation_cannot():
    """A V: strongly dependent, Spearman near zero. The shape nobody plots."""
    rows = _flat(600, x=lambda i: float(i - 300),
                 y=lambda i: float(abs(i - 300)))
    rep = weird.hidden_dependence(rows, control_pair=("x", "y"))
    assert rep.saw_control, "a V-shape must be found by MI where rho is blind"


def test_regime_change_finds_a_shift_partway_through():
    rows = _flat(400, v=lambda i: 1.0 + (i % 7) * 0.01 + (0 if i < 200 else 50))
    rep = weird.regime_changes(rows, control_field="v")
    assert rep.saw_control


def test_duplicates_need_two_sources_not_one():
    """The same row twice in ONE file is a different defect and not this one."""
    rows = [{"_id": "x", "_src": "a.json", "p": 1.0, "q": 2.0, "r": 3.0,
             "s": 4.0, "t": 5.0} for _ in range(2)]
    assert weird.duplicate_rows(rows).findings == []
    rows[1]["_src"] = "b.json"
    assert weird.duplicate_rows(rows, control_id="x").saw_control


def test_multimodal_finds_a_mixture():
    rows = _flat(600, v=lambda i: float(i % 3) * 100 + (i % 5) * 0.1)
    rep = weird.multimodal_fields(rows, control_field="v")
    assert rep.saw_control


# ── the hypothesis layer ────────────────────────────────────────────────────

def test_hypotheses_and_mechanisms_cluster_identically():
    """THE regression. Both functions clustered findings their own way and
    disagreed 179 to 9 on the same input — two producers of one fact, which is
    the defect this whole module hunts. They share `_cluster_key` now."""
    rows = _corpus()
    rows += _flat(300, w=lambda i: 1.0 if i < 250 else float(i))
    reps = weird.run_all(rows, {"ratio": "PLANTED"})
    kept, _notes = weird.explain_away(reps)
    assert len(weird.hypothesise(kept)) == len(weird.rank_by_surprise(kept))


def test_every_family_has_a_mechanism_or_it_produces_no_hypothesis():
    """A family with no entry in _MECHANISMS silently vanishes from the
    hypotheses while still counting as a mechanism. That is how the two
    clusterings drifted apart the first time."""
    families = {"ratio", "censored", "pileup", "benford", "rounding", "discrete",
                "redundant", "hidden", "regime", "order", "modal", "duplicate",
                "absent", "simpson", "signature"}
    assert families <= set(weird._MECHANISMS), (
        f"no mechanism for: {families - set(weird._MECHANISMS)}")


def test_every_hypothesis_carries_a_falsifier_and_a_cost():
    rows = _corpus()
    reps = weird.run_all(rows, {"ratio": "PLANTED"})
    kept, _ = weird.explain_away(reps)
    for h in weird.hypothesise(kept):
        assert h.falsifier.strip(), "a hypothesis with no way to die is not one"
        assert h.cost in ("free", "cheap", "expensive")


def test_explain_away_suppresses_ratios_against_a_constant():
    """A column with one value makes every ratio against it a rescaling of its
    partner. Reporting those buries the row that breaks something real."""
    rows = _flat(400, k=lambda i: 1.0, v=lambda i: 1.0 + (i % 9) * 0.001)
    rows[7]["v"] = 900.0
    reps = weird.run_all(rows, {})
    kept, notes = weird.explain_away(reps)
    assert any("constant" in n for n in notes)
    assert not any(f.family == "ratio" and "k" in
                   {f.evidence.get("field_a"), f.evidence.get("field_b")}
                   for f in kept)


def test_untrusted_reports_never_reach_the_findings_list():
    rows = _corpus()
    reps = weird.run_all(rows, {"ratio": "NOT-PRESENT"})
    assert all(f.family != "ratio" for f in weird.all_findings(reps))


# ── the statistical floor refuses rather than guesses ───────────────────────

def test_stats_return_none_rather_than_a_number_they_cannot_stand_behind():
    from lab import weird_stats as ws
    assert ws.mad([5.0] * 40) is None, "constant has no scale, not zero scale"
    assert ws.mad([]) is None
    assert ws.robust_z(1.0, [5.0] * 40) is None
    assert ws.spearman([1, 2], [1, 2]) is None          # too few
    assert ws.mutual_information([1.0] * 50, [2.0] * 50) is None
    assert ws.benford_deviation([1.0, 2.0]) is None      # too few
    assert ws.benford_deviation([1.0 + i * 1e-6 for i in range(200)]) is None


def test_spearman_sees_a_monotone_curve_pearson_would_understate():
    from lab import weird_stats as ws
    xs = [float(i) for i in range(200)]
    ys = [float(i) ** 3 for i in range(200)]
    assert ws.spearman(xs, ys) > 0.999


def test_mutual_information_is_zero_for_independent_columns():
    from lab import weird_stats as ws
    xs, ys, x = [], [], 11
    for _ in range(2000):
        x = (1103515245 * x + 12345) % (1 << 31)
        xs.append(float(x % 997))
        x = (1103515245 * x + 12345) % (1 << 31)
        ys.append(float(x % 991))
    assert ws.mutual_information(xs, ys) < 0.05
