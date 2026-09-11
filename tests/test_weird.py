"""weird — the anomaly loop, and the controls that decide whether to believe it.

The load-bearing tests are not the ones checking that a detector FINDS a planted
anomaly. They are the ones checking it WITHHOLDS its report when it fails to.
Two earlier dead-gate linters written the same day reported a clean floor
because they could not see the floor; only a control caught them. A detector
whose silence has never been tested is a detector whose silence means nothing.
"""
import math
import re

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
    """Trust is now decided by the SELF-TEST, so a corpus-derived control can no
    longer disqualify a family — disqualify one directly instead."""
    rows = _corpus()
    reps = weird.run_all(rows, {})
    assert any(f.family == "ratio" for f in weird.all_findings(reps))
    reps["ratio"].saw_control = False
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


# ── the control mechanism, rebuilt ──────────────────────────────────────────

def test_every_family_passes_its_own_planted_positive_and_negative():
    """THE design claim, and it was hollow until 2026-09-10.

    `saw_control` used to default to `bool(findings)` — "did I find anything?"
    — which held for 11 of 13 families on the real corpus, made `trusted_only`
    a no-op, and INVERTED: three families ran cleanly, found nothing, and were
    stamped BLIND. A control drawn from the data under study tells you about
    the data, not about the detector.
    """
    for family in sorted(weird._selftests()):
        passed, why = weird.self_test(family)
        assert passed, f"{family}: {why}"


def test_a_family_with_no_self_test_is_never_trusted():
    passed, why = weird.self_test("a-family-that-does-not-exist")
    assert passed is False
    assert "no self-test" in why


def test_trusted_and_quiet_is_expressible_and_is_not_blind():
    """A true negative must not read as blindness. This is the inversion the
    adversarial review caught: `redundant`, `hidden` and `regime` each ran
    correctly, found nothing, and the page called them BLIND."""
    rows = _flat(400, v=lambda i: 1.0 + (i % 97) * 0.01)
    reps = weird.run_all(rows, {})
    quiet = [n for n, r in reps.items() if r.saw_control and not r.findings]
    assert quiet, "no family managed a trusted true negative on clean data"
    for n in quiet:
        out = reps[n].render()
        assert "QUIET" in out and "BLIND" not in out


def test_explain_away_will_not_let_a_blind_family_delete_a_trusted_finding():
    """Confirmed as a live defect by adversarial review: a BLIND `discrete`
    report was authorised to delete `ratio`'s verified planted anomaly."""
    rows = _corpus()
    reps = weird.run_all(rows, {})
    reps["discrete"] = weird.Report(
        "discrete",
        [weird.Finding("discrete", "a", "fake", 1.0, {"distinct": 1})],
        False, "deliberately disqualified")
    kept, notes = weird.explain_away(reps)
    assert any(f.family == "ratio" for f in kept), (
        "a disqualified detector deleted a trusted family's findings")
    assert not any("constant" in n for n in notes)


# ── the defects the self-test and the review exposed ────────────────────────

def test_an_exact_relation_is_visible_at_all():
    """A perfect relation has MAD 0 and used to be SKIPPED — so the tightest,
    most informative relations in any corpus were invisible."""
    rows = _flat(400, a=lambda i: float(i + 1), b=lambda i: float(i + 1) * 3.0)
    rows[50]["b"] = rows[50]["a"] * 99.0
    rep = weird.ratio_violations(rows, control_id="t50")
    assert rep.saw_control


def test_an_exact_relation_over_a_lattice_is_not_a_relation():
    """`d_min` takes 3 values and `fap.B` is a constant, so two thirds of that
    pair 'violated' a relation that never existed. 3,306 findings, ~none real."""
    rows = _flat(400, lattice=lambda i: float(i % 3 + 1),
                 other=lambda i: float(i % 3 + 1) * 2)
    rep = weird.ratio_violations(rows, control_id="never")
    assert not any(f.evidence.get("exact") for f in rep.findings)


def test_terminal_digit_bias_is_monotone_in_roundness():
    """`rstrip("0")` deleted the very zeros that are the evidence, so a
    maximally-round column scored LOWER than unrounded noise."""
    from lab import weird_stats as ws
    import random
    rng = random.Random(3)
    rounded = [float(rng.randrange(1, 400) * 10) for _ in range(600)]
    unrounded = [rng.uniform(1, 4000) for _ in range(600)]
    r_share, _ = ws.terminal_digit_bias(rounded)
    u_share, _ = ws.terminal_digit_bias(unrounded)
    assert r_share > 0.9, f"round column scored only {r_share}"
    assert u_share < 0.4
    assert r_share > u_share


def test_boundary_pileup_reports_both_edges():
    """It returned on the first match, so a doubly-censored column reported one
    end — architecturally unable to see the shape it was written to find."""
    from lab import weird_stats as ws
    hits = ws.boundary_pileup([0.002] * 500 + [0.004] * 100 + [0.010] * 300)
    assert hits is not None
    edges = {e for e, _v, _s in hits}
    assert edges == {"min", "max"}, f"only saw {edges}"


def test_changepoint_scales_within_segments_not_across_the_shift():
    """Dividing by the whole column's MAD — which the shift inflates — made the
    estimator least sensitive to the largest effect it exists to find."""
    from lab import weird_stats as ws
    import random
    rng = random.Random(5)
    xs = [1.0 + rng.gauss(0, 0.01) for _ in range(100)] + \
         [50.0 + rng.gauss(0, 0.01) for _ in range(100)]
    got = ws.changepoint(xs)
    assert got is not None
    idx, gap = got
    # A step has a plateau of near-equal splits — every cut inside the clean
    # run scores enormously. The claim is the REGION and the magnitude, not a
    # single index, and pinning the index would be pinning noise.
    assert 60 <= idx <= 140, f"changepoint landed at {idx}, nowhere near the step"
    assert gap > 100, f"a 50-unit step on 0.01 noise read as only {gap} MADs"


def test_the_selftest_negative_fixture_is_actually_unordered():
    """An LCG sampled at sequential i has runs z ~ 19 against ~1 for real
    randomness — a fine fixture everywhere except as the clean negative for the
    family that tests ordering, where it fires correctly and reads as a bug."""
    from lab import weird_stats as ws
    _fn, _pos, _find, neg = weird._selftests()["order"]
    col = [r["v"] for r in neg]
    z = ws.runs_test(col)
    assert z is not None and abs(z) < 6.0, f"negative fixture is ordered: z={z}"


# ── the wide-aperture families ──────────────────────────────────────────────

def test_the_aperture_is_not_a_share_of_the_corpus():
    """A 5%-of-corpus floor dropped 114 of 131 columns on the real survey —
    every vetting, blend, fold and catalogue field. Those are sparse BECAUSE
    they only exist on rows that crossed threshold, i.e. the interesting ones.
    The tool was auditing plumbing and structurally could not see the science."""
    rows = [{"_id": f"t{i}", "_src": "a.json", "common": 1.0 + (i % 13)}
            for i in range(5000)]
    for i in range(40):
        rows[i]["rare_but_real"] = float(i)
    assert "rare_but_real" in weird._fields(rows)


def test_zero_and_negative_columns_are_visible():
    """`v > 0` made an all-zero constant and a column clamped at -1 invisible
    to every family — including the constant detector `explain_away` needs."""
    rows = [{"_id": f"t{i}", "_src": "a.json", "z": 0.0, "neg": -1.0}
            for i in range(200)]
    assert {"z", "neg"} <= set(weird._fields(rows))


def test_entity_outliers_find_a_row_odd_on_many_axes_and_loud_on_none():
    """The shape no per-column threshold can reach: nothing individually
    alarming, jointly improbable."""
    rows = [{"_id": f"n{i}", "_src": "a.json",
             **{f"f{j}": 1.0 + ((i * 7 + j) % 11) * 0.01 for j in range(9)}}
            for i in range(400)]
    rows.append({"_id": "ODD", "_src": "a.json",
                 **{f"f{j}": 1.35 for j in range(9)}})
    rep = weird.entity_outliers(rows, control_id="ODD")
    assert rep.saw_control
    hit = next(f for f in rep.findings if f.subject == "ODD")
    assert hit.evidence["n_odd"] >= 6


def test_entity_outliers_survive_a_corpus_with_no_spread_at_all():
    """A clean corpus gives MAD(shares) == 0, and the first version `break`-ed
    and discarded the very outlier it exists to find. Third occurrence of that
    shape in this module — see group_signature and ratio."""
    rows = [{"_id": f"n{i}", "_src": "a.json",
             **{f"f{j}": 1.0 for j in range(9)}} for i in range(300)]
    rows.append({"_id": "ODD", "_src": "a.json",
                 **{f"f{j}": 99.0 for j in range(9)}})
    rep = weird.entity_outliers(rows, control_id="ODD")
    assert rep.saw_control, "a constant corpus hid its only outlier"


def test_conditional_relations_find_what_the_pooled_statistic_cannot():
    rows = []
    for i in range(1800):
        g = i % 6
        x = ((i * 2654435761) % 10007) / 10007
        y = x if g == 0 else ((i * 40503) % 9973) / 9973
        rows.append({"_id": f"c{i}", "_src": "a.json",
                     "g": float(g), "x": x, "y": y})
    rep = weird.conditional_relations(rows, control_pair=("x", "y", "g"))
    assert rep.saw_control
    hit = rep.findings[0]
    assert abs(hit.evidence["rho_all"]) < 0.20
    assert abs(hit.evidence["rho_in"]) > 0.55


def test_conditional_declines_a_relation_that_is_visible_corpus_wide():
    """If the pooled statistic already sees it, it is not hidden and this family
    has nothing to add."""
    rows = []
    for i in range(1200):
        x = ((i * 2654435761) % 10007) / 10007
        rows.append({"_id": f"c{i}", "_src": "a.json",
                     "g": float(i % 2), "x": x, "y": x})
    assert weird.conditional_relations(rows).findings == []


def test_impossible_combinations_find_a_hole_in_a_populated_grid():
    rows = [{"_id": f"i{i}", "_src": "a.json", "a": float(i % 3),
             "b": float(0 if i % 3 == 0 else 1)} for i in range(600)]
    rep = weird.impossible_combinations(rows, control_pair=("a", "b"))
    assert rep.saw_control
    assert any("never co-occur" in f.detail for f in rep.findings)


def test_impossible_stays_quiet_when_every_combination_occurs():
    rows = [{"_id": f"i{i}", "_src": "a.json", "a": float(i % 3),
             "b": float(i % 2)} for i in range(600)]
    assert weird.impossible_combinations(rows).findings == []


def test_all_sixteen_families_pass_their_planted_positive_and_negative():
    fams = sorted(weird._selftests())
    assert len(fams) >= 16, f"only {len(fams)} families carry a self-test"
    for f in fams:
        passed, why = weird.self_test(f)
        assert passed, f"{f}: {why}"


def test_every_family_run_by_run_all_has_a_self_test():
    """A family wired into run_all with no self-test would be trusted on the
    word of `self_test`'s fallback, which is False — but it would also never be
    visible as a gap. Derive the list rather than hand-maintaining it."""
    import inspect
    src = inspect.getsource(weird.run_all)
    wired = set(re.findall(r'add\("(\w+)"', src))
    assert wired <= set(weird._selftests()), (
        f"wired but no self-test: {wired - set(weird._selftests())}")


def test_cli_self_test_enumerates_from_the_registry_not_from_a_run(capsys):
    """`lab weird --self-test` must prove EVERY family sees, not most of them.

    The first version listed the families by calling `run_all([], {})`, which
    on empty input yields 15 of 17 — `censored` needs a declared control and
    `simpson` needs a group field, so neither appears until real data does.
    It printed "15 families can see, 0 cannot" and that was a true sentence
    about a false set. Pin the count to the self-test registry, which is the
    one place a family declares it is testable at all.
    """
    from lab import cli
    assert cli.main(["weird", "--self-test"]) == 0
    out = capsys.readouterr().out
    n = len(weird._selftests())
    assert f"{n} of {n} families can see" in out
    for fam in weird._selftests():
        assert fam in out, f"{fam} not exercised by the CLI self-test"


def test_cli_weird_corpora_are_reachable_and_return_rows_or_nothing():
    """Every registered corpus must be callable without a live network or GPU.

    Not that it returns rows — a fresh clone has no receipts — but that asking
    for it raises nothing. A corpus that throws would take the whole command
    down on the one box where its directory happens to be missing.
    """
    from lab import cli
    for name, load in cli._WEIRD_CORPORA.items():
        rows = load()
        assert isinstance(rows, list), name
        for r in rows[:5]:
            assert "_id" in r and "_src" in r, f"{name}: row missing identity"
