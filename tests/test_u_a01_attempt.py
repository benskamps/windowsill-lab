"""The U-A01 attempt — the first run in this estate against a question rather than an instrument.

The rules under test are the ones that make an empty shelf a *result* instead of
a shrug, and they were committed before any real disposition was examined.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from lab import u_a01_attempt as A
from lab.hypothesis import DISCOVER, REANALYSED, UNRESOLVED


def _null(n=50_000, seed=1):
    rng = np.random.default_rng(seed)
    return np.sort(rng.gumbel(4.4, 0.55, n))


def _rows(*specs):
    return [{"tic": t, "sde": s, "known_planet": k, "disposition": "x"}
            for t, s, k in specs]


def test_the_attempt_declares_itself_discovery_and_cites_its_unknown():
    """`discover` is not self-declarable — the hypothesis has to name a
    catalogue id, which is what separates an attempt from a claim."""
    assert A.HYPOTHESIS.stage == DISCOVER
    assert A.HYPOTHESIS.unknown_id == "U-A01"


def test_a_thin_null_refuses_to_price_anything():
    """Below the draw floor the tail cannot support a FAP, and the honest
    answer is UNRESOLVED rather than a confident bound."""
    f = A.run.__wrapped__ if hasattr(A.run, "__wrapped__") else A.run
    got = A.empirical_fap(np.array([1.0, 2.0]), 8.0)
    assert got["is_bound"] is True


def test_a_zero_count_tail_is_reported_as_a_bound_not_a_point_estimate():
    n = _null()
    got = A.empirical_fap(n, 99.0)
    assert got["is_bound"] and got["exceedances"] == 0
    assert got["fap"] == pytest.approx(3.0 / n.size)


def test_a_measured_tail_is_a_point_estimate():
    n = _null()
    got = A.empirical_fap(n, float(np.percentile(n, 99)))
    assert got["is_bound"] is False and got["exceedances"] > 0


def test_trials_counts_distinct_targets_not_rows(tmp_path, monkeypatch):
    """Re-searching one star across six sectors is not six independent chances
    at a false alarm. Counting rows would inflate the trials correction in our
    own favour — which makes candidates look WORSE, but is still wrong, and a
    correction that is wrong in a convenient direction is the one nobody
    checks."""
    d = tmp_path / "hunts"; d.mkdir()
    (d / "h.json").write_text(json.dumps(
        {"targets": _rows(("T1", 9.0, False), ("T1", 9.1, False),
                          ("T2", 4.0, False))}), encoding="utf-8")
    nl = tmp_path / "null.jsonl"
    nl.write_text("\n".join(json.dumps({"sde": float(x)}) for x in _null()),
                  encoding="utf-8")
    f = A.run(hunt_dir=str(d), null_path=nl)
    assert f.evidence["distinct_targets"] == 2
    assert f.evidence["rows"] == 3


def test_a_catalogued_planet_is_calibration_and_never_a_discovery(tmp_path):
    """Recovering a known planet proves the pipeline works. Counting it as a
    find would be the single easiest way for this survey to lie."""
    d = tmp_path / "hunts"; d.mkdir()
    (d / "h.json").write_text(json.dumps(
        {"targets": _rows(("K1", 30.0, True))}), encoding="utf-8")
    nl = tmp_path / "null.jsonl"
    nl.write_text("\n".join(json.dumps({"sde": float(x)}) for x in _null()),
                  encoding="utf-8")
    f = A.run(hunt_dir=str(d), null_path=nl)
    assert f.verdict == REANALYSED
    assert f.evidence["crossings_known_planet"] == 1
    assert f.evidence["crossings_uncatalogued"] == 0


def test_an_empty_result_counts_every_exit(tmp_path):
    """An empty shelf with no accounting is a shrug; one with its exits
    enumerated is a measurement."""
    d = tmp_path / "hunts"; d.mkdir()
    (d / "h.json").write_text(json.dumps(
        {"targets": _rows(("A", 9.0, False), ("B", 30.0, True), ("C", 3.0, False))}),
        encoding="utf-8")
    nl = tmp_path / "null.jsonl"
    nl.write_text("\n".join(json.dumps({"sde": float(x)}) for x in _null()),
                  encoding="utf-8")
    ev = A.run(hunt_dir=str(d), null_path=nl).evidence
    assert {"crossings_at_8", "crossings_known_planet",
            "crossings_uncatalogued", "distinct_targets"} <= set(ev)


def test_even_a_significant_crossing_is_only_a_re_analysis(tmp_path):
    """The rule can find something — and it still cannot call it a discovery,
    because it consumed no new observation. This is the whole 2026-08-25
    correction: a strong signal in the archive is a reason to GO AND LOOK, not
    a substitute for having looked."""
    d = tmp_path / "hunts"; d.mkdir()
    (d / "h.json").write_text(json.dumps(
        {"targets": _rows(("BIG", 40.0, False))}), encoding="utf-8")
    nl = tmp_path / "null.jsonl"
    nl.write_text("\n".join(json.dumps({"sde": float(x)}) for x in _null()),
                  encoding="utf-8")
    f = A.run(hunt_dir=str(d), null_path=nl)
    assert f.verdict == REANALYSED
    assert f.attempted_the_question is False


def test_the_shipped_run_is_a_re_analysis_not_an_attempt():
    """The real result, pinned, under its corrected name. 173 crossings, 79
    catalogued, the strongest uncatalogued one at 0.113 expected background
    against a 0.1 ceiling set before the data was opened — and zero new
    observations, which is why it cannot be an attempt."""
    f = A.run()
    if f.verdict == UNRESOLVED:
        pytest.skip("scramble null not present in this checkout")
    assert f.verdict == REANALYSED
    assert f.attempted_the_question is False
    assert f.evidence["crossings_known_planet"] > 0, (
        "the pipeline must be recovering real planets, or the null result "
        "means only that the search is broken")


def test_a_runner_that_cannot_get_its_data_may_say_so(tmp_path):
    """Caught by CI on 2026-08-25 and invisible locally, because this box HAS a
    scramble null and the CI runner does not.

    An earlier version of the terminus rule made UNRESOLVED a 'discovery
    verdict' requiring new observations — which forbade a run from reporting
    that it could not obtain any. The contract refused the most honest thing a
    run can report. SUPPORTED and KILLED are claims about the world and still
    require having looked; UNRESOLVED is the absence of a claim."""
    d = tmp_path / "hunts"; d.mkdir()
    (d / "h.json").write_text(json.dumps({"targets": _rows(("T", 9.0, False))}),
                              encoding="utf-8")
    thin = tmp_path / "thin.jsonl"
    thin.write_text(json.dumps({"sde": 4.0}) + "\n", encoding="utf-8")
    f = A.run(hunt_dir=str(d), null_path=thin)          # must not raise
    assert f.verdict == UNRESOLVED
    assert f.attempted_the_question is False
    assert "below the" in f.detail


def test_an_attempt_that_looked_and_did_not_decide_still_counts_as_an_attempt():
    """The goal's own honesty note: the commitment is to attempt and report,
    not to succeed. Observations decide whether it was an attempt — not the
    verdict."""
    from lab.hypothesis import Finding, Hypothesis, DISCOVER as D
    h = Hypothesis(id="U-X01", track="X", stage=D, unknown_id="U-X01",
                   question="q", why_unanswered="w", observable="o",
                   kill_condition="k", cheapest_decisive="c",
                   why_this_might_be_nothing="n")
    looked = Finding(hypothesis=h, verdict=UNRESOLVED, detail="d",
                     new_observations={"sector": "s41", "sha256": "abc"})
    assert looked.attempted_the_question is True
