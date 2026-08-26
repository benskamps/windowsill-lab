"""The objection ledger — additive, artifact-answered, append-only.

The 2026-08-25 audit refused adversarial personas with evidence: `k03.DAIDO` and
`k03.HONG` were both posed, both fully cited, as structured data, and K03 still
got the asymmetric Millikan treatment. Rival-count was never the variable.

What survives is not a persona but a channel, and these three rules are what
keep it from being ceremony.
"""
from __future__ import annotations

import json

import pytest

from lab import objections as O


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "o.jsonl"


def test_any_voice_may_raise(ledger):
    for v in ("ember", "codex", "gemmi", "ben", "stranger", "claude"):
        assert O.raise_objection("U-K02", v, f"{v} doubts it", path=ledger).open


def test_an_unknown_voice_is_refused(ledger):
    with pytest.raises(ValueError):
        O.raise_objection("U-K02", "anonymous", "x", path=ledger)


def test_only_an_artifact_answers_an_objection(ledger):
    """The load-bearing rule. A verdict is an opinion; a re-derivation is a
    fact — applied one level up, so an objection cannot be talked away."""
    o = O.raise_objection("U-K02", "ember", "dt was never audited", path=ledger)
    for prose in ("I checked it", "this is fine", "addressed in the docstring"):
        with pytest.raises(ValueError) as caught:
            O.answer(o.id, prose, path=ledger)
        assert "not an artifact" in str(caught.value)
    O.answer(o.id, "measured:0.04% across dt", path=ledger)
    assert not O.open_against("U-K02", path=ledger)


@pytest.mark.parametrize("ref", ["receipt:run-2026-08-25-1247-u-a01.json",
                                 "commit:e87e0d4", "https://arxiv.org/abs/1",
                                 "measured:0.03% of the limit"])
def test_every_artifact_kind_is_accepted(ledger, ref):
    o = O.raise_objection("X", "ben", "doubt", path=ledger)
    assert O.answer(o.id, ref, path=ledger).status == O.ANSWERED


def test_an_objection_cannot_be_constructed_as_answered_without_a_reference():
    with pytest.raises(ValueError) as caught:
        O.Objection(id="O1", claim="c", voice="ben", objection="o",
                    status=O.ANSWERED)
    assert "ARTIFACT" in str(caught.value)


def test_only_the_holder_may_withdraw_their_own_doubt(ledger):
    """Nobody discharges someone else's objection — including the author of the
    thing objected to, which is the whole point."""
    o = O.raise_objection("U-K02", "ember", "doubt", path=ledger)
    with pytest.raises(ValueError) as caught:
        O.withdraw(o.id, "claude", "I disagree", path=ledger)
    assert "only the holder" in str(caught.value)
    assert O.withdraw(o.id, "ember", "I misread the code", path=ledger).status == O.WITHDRAWN


def test_the_ledger_is_append_only(ledger):
    """An objection that was answered can still be read in the form it was
    raised. That is the difference between a ledger and a database."""
    o = O.raise_objection("U-K02", "ember", "the original doubt", path=ledger)
    O.answer(o.id, "measured:x", path=ledger)
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["status"] == O.RAISED and rows[0]["objection"] == "the original doubt"
    assert len(O.load(path=ledger)) == 1, "replay collapses to current state"


def test_a_claim_with_an_open_objection_publishes_as_disputed(ledger):
    O.raise_objection("U-K02", "ember", "a", path=ledger)
    o2 = O.raise_objection("U-K02", "codex", "b", path=ledger)
    O.answer(o2.id, "commit:abc", path=ledger)
    d = O.disputed(path=ledger)
    assert d["open"] == 1 and d["answered"] == 1
    assert "U-K02" in d["disputed_claims"]
    assert d["disputed_claims"]["U-K02"][0]["voice"] == "ember"


def test_the_objector_does_not_have_to_be_right():
    """Ember's dt objection was WRONG — 0.04% variation — and it was still
    worth having, because the answer is now a measurement instead of an
    assumption. A channel that only admits correct doubts admits none."""
    assert O.ARTIFACT_PREFIXES and "measured:" in O.ARTIFACT_PREFIXES


def test_the_shipped_ledger_parses_and_carries_a_non_claude_voice():
    """Non-hermetic: the point of the channel is decorrelation, so a ledger
    containing only 'claude' rows would be the Little Club with extra steps."""
    live = O.load()
    if not live:
        pytest.skip("no objections raised in this checkout")
    assert {o.voice for o in live} - {"claude"}, "no decorrelated voice present"
