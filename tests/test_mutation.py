"""Auditing the auditor — tests for the mutation harness, and the gate it enables.

Two halves. The first grades `lab.mutation` itself against hand-built checks
whose eyesight is known by construction: a check that reads one field, a check
that reads nothing, a check that crashes. The second turns the harness on
`lab.checks` and asserts two properties that must hold for every check the lab
ships:

1. **No check is vacuous.** A check that cannot be made to fail by corrupting
   any number in a report it passes is not verifying anything.
2. **No check grades a field it does not require.** If corrupting a key makes
   the check go red but DELETING that key leaves it green, then a report that
   lost the field in serialisation keeps its leaf. The 2026-08-19 audit found
   31 such fields across M03, M07 and M14; this test is what stops them coming
   back.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from lab import checks, mutation


# --------------------------------------------------- the harness, on itself ---

def _report():
    return {"experiment": "toy", "headline": 4.0, "ignored": 7.0,
            "arr": [1.0, 2.0, 3.0], "flag": True, "name": "x"}


def _check_headline(report):
    """Sees exactly one field, and requires it."""
    value = report.get("headline")
    if value is None:
        return False, "missing headline"
    return abs(value - 4.0) < 1e-9, f"headline={value}"


def _check_nothing(report):
    """A rubber stamp."""
    return True, "fine"


def _check_crashes(report):
    return 1 / report["arr"][2] > 0, "ratio"


def test_numeric_paths_finds_every_number_and_no_flags():
    paths = mutation.numeric_paths(_report())
    assert ("headline",) in paths
    assert ("arr", 1) in paths
    assert ("flag",) not in paths          # bools are flags, not measurements
    assert ("name",) not in paths


def test_numeric_paths_skips_the_bulk_and_metadata_subtrees():
    report = {"snapshots": [[1.0, 2.0]], "provenance": {"seed": 3.0}, "x": 1.0}
    assert mutation.numeric_paths(report) == [("x",)]


def test_numeric_paths_respects_its_cap():
    big = {"a": [float(i) for i in range(500)]}
    assert len(mutation.numeric_paths(big, max_paths=25)) == 25


def test_mutate_never_touches_the_original():
    report = _report()
    before = json.dumps(report, sort_keys=True)
    mutation.mutate(report, ("headline",), "scale_2x")
    mutation.mutate(report, ("arr", 0), "drop")
    assert json.dumps(report, sort_keys=True) == before


@pytest.mark.parametrize("kind,expected", [
    ("scale_2x", 8.0), ("scale_half", 2.0), ("sign_flip", -4.0)])
def test_mutate_kinds(kind, expected):
    assert mutation.mutate(_report(), ("headline",), kind)["headline"] == expected


def test_mutate_drop_removes_a_dict_key_and_a_list_element():
    assert "headline" not in mutation.mutate(_report(), ("headline",), "drop")
    assert mutation.mutate(_report(), ("arr", 1), "drop")["arr"] == [1.0, 3.0]


def test_mutate_rejects_an_unknown_kind():
    with pytest.raises(ValueError, match="unknown mutation"):
        mutation.mutate(_report(), ("headline",), "nudge")


def test_audit_finds_the_one_field_a_check_reads():
    result = mutation.audit(_check_headline, _report())
    assert result["usable"] is True
    assert result["vacuous"] is False
    assert mutation.graded_fields(result) == ["headline"]
    assert "ignored" in mutation.blind_fields(result)


def test_audit_calls_a_rubber_stamp_vacuous():
    result = mutation.audit(_check_nothing, _report())
    assert result["vacuous"] is True
    assert result["sensitivity"] == 0.0
    assert result["killed"] == []


def test_audit_records_a_crash_as_a_crash_not_a_pass():
    """A check that explodes on a malformed report cannot grade one.

    Deleting ``arr[2]`` leaves the check indexing past the end. That outcome is
    neither a pass nor a kill, and filing it as either would hide it.
    """
    result = mutation.audit(_check_crashes, _report())
    crashed = {(path, kind) for path, kind in result["crashed"]}
    assert (("arr", 2), "drop") in crashed
    assert (("arr", 2), "drop") not in set(result["killed"])
    assert (("arr", 2), "drop") not in set(result["survived"])


def test_audit_refuses_a_report_the_check_does_not_already_pass():
    report = dict(_report(), headline=99.0)
    result = mutation.audit(_check_headline, report)
    assert result["usable"] is False
    assert result["reason"] == "baseline-not-passing"


def test_audit_refuses_when_the_baseline_itself_crashes():
    result = mutation.audit(_check_crashes, {"arr": []})
    assert result["usable"] is False
    assert result["reason"] == "baseline-crashed"


def test_inapplicable_verdicts_count_as_neither_sight_nor_blindness():
    """A check answering 'not applicable' has not been tested by that mutation.

    Counting those as survivals would make an abstaining check look blind;
    counting them as kills would make it look sharp. They are neither, so
    ``sensitivity`` is taken over the mutations that produced a verdict — and a
    check that abstains on everything has no sensitivity to report at all.
    """
    def always_abstains(report):
        if report.get("headline") != 4.0:
            return None, "precondition unmet"
        return True, "graded"
    result = mutation.audit(always_abstains, _report())
    assert result["sensitivity"] == 0.0
    assert result["vacuous"] is True
    assert any(path == ("headline",) for path, _ in result["inapplicable"])


def test_negligible_values_are_not_scaled_into_fake_survivors():
    report = {"experiment": "toy", "headline": 4.0, "tiny": 0.0}
    result = mutation.audit(_check_headline, report)
    assert all(path != ("tiny",) or kind == "drop"
               for path, kind in result["survived"])


# ------------------------------------------------ the harness, on lab.checks ---

REPORT_DIR = pathlib.Path(__file__).resolve().parents[1] / "reports"


def _newest_report_per_code():
    best: dict[str, pathlib.Path] = {}
    for path in sorted(REPORT_DIR.glob("*.json")):
        m = re.match(r"\d{4}-\d{2}-\d{2}-([a-z]\d+)\.json$", path.name)
        if m:
            best[m.group(1).upper()] = path
    return best


def _auditable():
    """(code, check, audit-result) for every check with a passing report on disk.

    Codes whose newest report does not currently pass are skipped rather than
    failed: an honest recorded refusal (I01's hardware null, K03's linearity
    gate) is a real state of the lab, and this test grades eyesight, not colour.
    """
    out = []
    for code, path in sorted(_newest_report_per_code().items()):
        check = checks.CHECKS.get(code)
        if check is None:
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        result = mutation.audit(check, report, max_paths=200)
        if result.get("usable"):
            out.append((code, path.name, result))
    return out


AUDITS = _auditable()


def test_there_is_something_to_audit():
    assert len(AUDITS) >= 10, "no passing reports on disk to audit against"


@pytest.mark.parametrize("code,name,result",
                         AUDITS, ids=[a[0] for a in AUDITS])
def test_no_check_is_vacuous(code, name, result):
    """Every check must be killable by corrupting SOMETHING it reads."""
    assert not result["vacuous"], (
        f"{code} passed {name} under every mutation — it verifies nothing")


@pytest.mark.parametrize("code,name,result",
                         AUDITS, ids=[a[0] for a in AUDITS])
def test_no_check_grades_a_field_it_does_not_require(code, name, result):
    """Corrupting a key fails the check; deleting it must not pass.

    Only dict KEYS are graded here. Dropping a list ELEMENT shortens an array
    into a shorter but self-consistent dataset, which a check may legitimately
    still pass — that is a different question from a missing required field.
    """
    corrupted = {path for path, kind in result["killed"] if kind != "drop"}
    deleted_ok = {path for path, kind in result["survived"] if kind == "drop"}
    offenders = sorted(p for p in (corrupted & deleted_ok) if isinstance(p[-1], str))
    assert not offenders, (
        f"{code} grades but does not require: "
        + ", ".join(".".join(str(x) for x in p) for p in offenders[:8]))
