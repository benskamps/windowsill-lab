"""The terminus: a hunt receipt becomes the finding the goal reads.

The contract (u_a01_field docstring + hypothesis.Finding): a discovery verdict
must carry new observations; a refused receipt yields no observations and does
not count; the verdict is the preregistration's outcome table and nothing
else; and the checker that grades every frontier receipt must accept what this
runner writes.
"""
from __future__ import annotations

import json

import pytest

from lab import u_a01_field as F
from lab.checks import check_hypothesis
from lab.hypothesis import DISCOVER, KILLED, UNRESOLVED

from tests.test_hunt_block import _schema1_receipt, _control_blocks, _control_rows


def _write(tmp_path, receipt, name="hunt-2026-09-11-s96.json"):
    p = tmp_path / name
    p.write_text(json.dumps(receipt), encoding="utf-8")
    return p


def test_every_crossing_dispositioned_and_no_lead_is_killed_with_observations(tmp_path):
    p = _write(tmp_path, _schema1_receipt(sector=96))
    f = F.run(p, preregistration="docs/preregistrations/x.md")
    assert f.verdict == KILLED
    assert f.attempted_the_question
    assert f.new_observations["receipt"] == p.name
    assert f.new_observations["sector"] == 96
    assert f.new_observations["targets_searched"] == 7
    assert f.hypothesis.stage == DISCOVER and f.hypothesis.unknown_id == "U-A01"


def test_a_lead_is_unresolved_never_supported(tmp_path):
    targets = list(_schema1_receipt()["targets"])
    targets[0] = {**targets[0], "disposition": "lead-awaiting-human-review"}
    p = _write(tmp_path, _schema1_receipt(targets=targets, **_control_blocks(targets)))
    f = F.run(p)
    assert f.verdict == UNRESOLVED
    assert f.attempted_the_question            # it looked; it just could not decide
    assert f.evidence["leads"] == ["111"]


def test_a_refused_receipt_is_withheld_and_does_not_count(tmp_path):
    receipt = _schema1_receipt()
    del receipt["targets"][0]["disposition"]    # undispositioned hit → refused
    p = _write(tmp_path, receipt)
    f = F.run(p)
    assert f.verdict == UNRESOLVED
    assert not f.new_observations
    assert not f.attempted_the_question
    assert "refused" in f.detail


def test_not_a_hunt_receipt_is_an_error(tmp_path):
    p = _write(tmp_path, {"experiment": "something-else", "targets": []})
    with pytest.raises(ValueError):
        F.run(p)


def test_the_checker_accepts_what_this_runner_writes(tmp_path):
    """check_hypothesis rebuilds both constructors from the receipt's bytes and
    recomputes headline/boundary/status. The runner's output must survive it,
    or the ledger would file the attempt as refused."""
    p = _write(tmp_path, _schema1_receipt(sector=96))
    report = F.run(p, preregistration="prereg.md").to_report()
    ok, why = check_hypothesis(report)
    assert ok is True, why
