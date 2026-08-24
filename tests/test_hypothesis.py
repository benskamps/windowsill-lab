"""The hypothesis contract, and H01 — the first runner written question-first.

The contract's whole job is to make a certain kind of mistake unconstructible.
Three shipped in one day before it existed: a runner with no test on its order
parameter, a control that could not fail, and a runner never once executed.
"""
from __future__ import annotations

import pytest

from lab import h01_bbp_tail as h01
from lab.hypothesis import (CALIBRATE, DISCOVER, KILLED, SUPPORTED, UNRESOLVED,
                            Finding, Hypothesis)


def _h(**over):
    base = dict(id="HXX", question="q?", why_unanswered="because",
                observable="a number", kill_condition="if it disagrees",
                cheapest_decisive="an afternoon",
                why_this_might_be_nothing="it probably just agrees",
                stage=CALIBRATE)
    base.update(over)
    return Hypothesis(**base)


# ── the contract ─────────────────────────────────────────────────────────────

def test_a_hypothesis_without_a_kill_condition_cannot_be_built():
    """The load-bearing refusal. An idea that cannot say what would refute it
    is not a hypothesis, and the point of the type is that you cannot ship one."""
    with pytest.raises(ValueError) as caught:
        _h(kill_condition="")
    assert "kill_condition" in str(caught.value)


def test_a_proposer_must_say_how_it_might_be_nothing():
    with pytest.raises(ValueError) as caught:
        _h(why_this_might_be_nothing="   ")
    assert "why_this_might_be_nothing" in str(caught.value)


def test_every_missing_field_is_named_at_once():
    """A contract that reports one gap per attempt teaches people to guess."""
    with pytest.raises(ValueError) as caught:
        _h(observable="", cheapest_decisive="")
    message = str(caught.value)
    assert "observable" in message and "cheapest_decisive" in message


def test_killed_is_a_verdict_not_an_error():
    """A hypothesis dying on its predeclared terms is the system working, and
    the vocabulary has to say so — otherwise every run is pressured toward
    'supported' to look like a success."""
    finding = Finding(hypothesis=_h(), verdict=KILLED, detail="it died")
    assert finding.to_report()["verdict"] == "killed"


def test_unresolved_is_available_as_the_honest_third_door():
    assert Finding(hypothesis=_h(), verdict=UNRESOLVED, detail="?").verdict == "unresolved"


def test_an_invented_verdict_is_refused():
    with pytest.raises(ValueError):
        Finding(hypothesis=_h(), verdict="probably-fine", detail="")


def test_the_report_carries_the_question_and_its_kill_condition():
    """A receipt that records only the answer cannot be audited: the reader
    needs what would have counted as a refutation, written beforehand."""
    report = Finding(hypothesis=_h(), verdict=SUPPORTED, detail="d").to_report()
    assert report["hypothesis"]["kill_condition"] == "if it disagrees"
    assert report["hypothesis"]["why_this_might_be_nothing"]


# ── H01's arithmetic ─────────────────────────────────────────────────────────

def test_the_exact_path_reproduces_pi_from_an_independent_route():
    """The safety argument for the whole experiment: an exact implementation
    that has not been shown to match a known answer somewhere cannot be used to
    accuse the float path anywhere. Machin's arctan formula shares no code with
    BBP."""
    from lab import c05
    machin = c05.machin_pi_hex(64)
    for pos in (0, 8, 16, 32):
        assert h01.exact_bbp_window(pos, 8) == machin[pos:pos + 8]


def test_exact_and_float_agree_where_float_is_trusted():
    from lab import c05
    for pos in (0, 100, 5000):
        assert h01.exact_bbp_window(pos, 8) == c05.bbp_window(pos, 8)


def test_more_precision_does_not_change_the_answer():
    """If the scaled-integer bound is real, adding bits changes nothing. If it
    is not, this is where that shows up."""
    assert h01.exact_bbp_window(1234, 8, precision_bits=128) == \
           h01.exact_bbp_window(1234, 8, precision_bits=256)


def test_first_difference_finds_the_digit():
    assert h01.first_difference("ABCD", "ABCD") is None
    assert h01.first_difference("ABCD", "ABXD") == 2
    assert h01.first_difference("AB", "ABCD") == 2


def test_h01_declares_a_kill_condition_that_names_the_retraction():
    """The kill condition must say what is GIVEN UP, not merely that something
    would be wrong — otherwise a failure has nowhere to land."""
    assert "retracted" in h01.HYPOTHESIS.kill_condition
    assert "10^7" in h01.HYPOTHESIS.question


def test_a_broken_exact_path_refuses_to_judge_rather_than_accusing(monkeypatch):
    """If the instrument fails its own control it must return UNRESOLVED, not
    KILLED. Accusing the float path with a broken ruler would be the worst
    possible outcome of this experiment."""
    monkeypatch.setattr(h01, "exact_bbp_window",
                        lambda d, width=8, precision_bits=192: "0" * width)
    finding = h01.run(deep_position=64, control_positions=(0,), width=8)
    assert finding.verdict == UNRESOLVED
    assert "instrument is broken" in finding.detail


def test_a_shallow_run_reaches_a_verdict_end_to_end():
    finding = h01.run(deep_position=2048, control_positions=(0, 16), width=8)
    assert finding.verdict in (SUPPORTED, KILLED)
    assert finding.evidence["position"] == 2048
    assert finding.controls["0"]["exact_matches_machin"]


def test_discovery_cannot_be_self_declared():
    """The load-bearing rule of the gate. A runner may not simply announce that
    it is doing discovery — it has to name a catalogued unknown, so the claim is
    checkable against UNKNOWNS.md instead of asserted in its own docstring."""
    with pytest.raises(ValueError) as caught:
        _h(stage=DISCOVER)
    assert "not self-declarable" in str(caught.value)


def test_discovery_with_a_named_unknown_is_allowed():
    assert _h(stage=DISCOVER, unknown_id="U-K02").stage == DISCOVER


def test_an_invented_stage_is_refused():
    with pytest.raises(ValueError):
        _h(stage="frontier-ish")


def test_the_report_says_which_side_of_the_gate_it_is_on():
    """So `is this lab still only calibrating?` is a number, not a feeling."""
    assert _h().to_json()["crosses_the_gate"] is False
    assert _h(stage=DISCOVER, unknown_id="U-M01").to_json()["crosses_the_gate"] is True


def test_h01_is_labelled_calibration_and_does_not_pretend_otherwise():
    """H01 audits our own arithmetic against a second method. That is the
    definition of the calibrate side, and a lab whose self-audits quietly count
    as discovery has lost the ability to answer the only question about its aim."""
    assert h01.HYPOTHESIS.stage == CALIBRATE


def test_the_board_schema_and_the_dataclass_are_the_same_six_fields():
    """`lab frontier` has been asking proposals for six fields in prose. The
    dataclass now enforces them in code. If those two ever drift, the board is
    demanding one thing and the runners are guaranteeing another — so they are
    pinned to each other here rather than by anybody remembering."""
    from dataclasses import fields
    from lab.frontier import HYPOTHESIS_SCHEMA
    declared = {f.name for f in fields(Hypothesis)} - {"id", "track", "stage",
                                                       "unknown_id"}
    assert declared == set(HYPOTHESIS_SCHEMA)
