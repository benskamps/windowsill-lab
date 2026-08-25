"""The frontier lane, graded by the same rule as the calibration ladder.

Until 2026-08-25 the estate had 33 checkers for milestones — where the right
answer is already published — and none for H01 or U-A01, the only two runs that
ever made a claim about the world. The one lane where a self-graded verdict
could do damage was the one lane nothing checked.

The rule under test is the estate's existing doctrine, extended: nothing the
receipt asserts is trusted. `None` means this box cannot re-derive. `False` is
tampering or a contract violation, and is never a shrug.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lab.checks import CHECKS, check_hypothesis
from lab.hypothesis import CALIBRATE, DISCOVER, Finding, Hypothesis, REANALYSED, SUPPORTED


def _hyp(**over):
    base = dict(id="U-A01", track="A", stage=DISCOVER, unknown_id="U-A01",
                question="q?", why_unanswered="w", observable="o",
                kill_condition="k", cheapest_decisive="c",
                why_this_might_be_nothing="n")
    base.update(over)
    return Hypothesis(**base)


def _receipt(**over):
    f = Finding(hypothesis=_hyp(), verdict=REANALYSED, detail="d")
    r = f.to_report()
    r.update(over)
    return r


def test_the_frontier_lane_is_in_the_registry_at_all():
    """The gap this file closes. 33 checkers for the ladder, none for the two
    runs that made claims about the world."""
    assert CHECKS.get("H01") is check_hypothesis
    assert CHECKS.get("U-A01") is check_hypothesis


def test_a_clean_receipt_re_derives():
    ok, why = check_hypothesis(_receipt())
    assert ok is True and "re-derived from its own bytes" in why


def test_a_deleted_kill_condition_fails_rather_than_passing():
    """The receipt cannot be reconstructed without it, so the contract that was
    enforced at write time is enforced again at read time."""
    r = _receipt()
    r["hypothesis"]["kill_condition"] = ""
    ok, why = check_hypothesis(r)
    assert ok is False and "hypothesis contract" in why


def test_a_discovery_verdict_with_no_new_observations_fails():
    """The 2026-08-25 failure, caught from committed bytes. A run that read only
    the archive cannot be relabelled an attempt by editing its verdict."""
    r = _receipt(verdict="killed")
    ok, why = check_hypothesis(r)
    assert ok is False and "terminus rule" in why


def test_flipping_the_stage_to_dress_a_reanalysis_as_an_attempt_fails():
    r = _receipt()
    r["verdict"] = "supported"
    ok, _ = check_hypothesis(r)
    assert ok is False


def test_an_authored_headline_that_the_verdict_does_not_produce_fails():
    """A headline written by the graded party is precisely the defect the
    estate's audit named — 'every scoring surface it publishes is a function of
    prose the graded party wrote'. The reader's line must be derivable."""
    r = _receipt(headline="U-A01: a triumph")
    ok, why = check_hypothesis(r)
    assert ok is False and "headline" in why


def test_an_edited_claim_boundary_fails():
    r = _receipt(claim_boundary="this proves the shelf is empty")
    ok, _ = check_hypothesis(r)
    assert ok is False


def test_a_discover_receipt_citing_a_catalogue_entry_that_does_not_exist_fails():
    r = _receipt()
    r["hypothesis"]["unknown_id"] = "U-Z99"
    ok, why = check_hypothesis(r)
    assert ok is False and "not in" in why


def test_a_receipt_predating_a_contract_field_is_none_not_false():
    """Failing an OLD entry against a NEW standard is honest; calling it
    tampering is not, and the difference is whether the field was ever there to
    violate. Crying wolf here would corrode the one vocabulary that has to stay
    trustworthy."""
    r = _receipt()
    del r["hypothesis"]["stage"]
    ok, why = check_hypothesis(r)
    assert ok is None and "predates" in why


def test_a_non_frontier_receipt_is_none_not_a_failure():
    assert check_hypothesis({"experiment": "M02-fss"})[0] is None


def test_a_calibrate_receipt_needs_no_new_observations():
    """H01 audits our own arithmetic against a second method. It makes no claim
    about the world and must not be forced to acquire anything."""
    f = Finding(hypothesis=_hyp(id="H01", track="C", stage=CALIBRATE,
                                unknown_id=""),
                verdict=SUPPORTED, detail="d")
    assert check_hypothesis(f.to_report())[0] is True


def test_the_shipped_frontier_receipts_grade():
    """Non-hermetic: whatever is committed must actually pass its own checker,
    or the lane is publishing what it cannot re-derive."""
    root = Path(__file__).resolve().parents[1] / "reports" / "receipts"
    seen = 0
    for f in sorted(root.glob("*-u-a01.json")) + sorted(root.glob("*-h01.json")):
        ok, why = check_hypothesis(json.loads(f.read_text(encoding="utf-8")))
        assert ok is not False, f"{f.name}: {why}"
        seen += 1
    if not seen:
        pytest.skip("no frontier receipts committed in this checkout")
