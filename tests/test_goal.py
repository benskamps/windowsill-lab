"""The declared goal — and the three properties that make it a commitment.

A goal in a plan document is a preference. This one is published in `pot.json`,
its progress is computed rather than written, and it is allowed to read MISSED.
Each of those is load-bearing and each has a test here, because each is exactly
the kind of thing that quietly stops being true.

Property two stopped being true and nobody noticed for ten days. Until
2026-09-03 the goal's attempt condition was ``"ATTEMPTED" in u.reach_evidence``
— a case-sensitive, unanchored substring search against one physical line of
`UNKNOWNS.md`, the file the grading agent edits — sitting directly beneath a
docstring promising the number was computed and never written. The tests below
that mention *prose* are the ones guarding the repair, and they are written
against the sentence that actually does the damage: not a forged "ATTEMPTED",
but the DENIAL an honest corrector types first.
"""
from __future__ import annotations

import dataclasses
from datetime import date, timedelta

import pytest

from lab import goal as G
from lab import unknowns as U


def _u(**over):
    base = dict(id="U-X01", track="X", question="q?", why_open="w",
                known_to_whom=U.FIELD, who_would_care="us",
                feasibility_test="cheap", if_out_of_reach="buy more",
                status=U.CHARTED, reach=U.IN_REACH)
    base.update(over)
    return U.Unknown(**base)


def _attempt(unknown_id="U-X01", verdict="unresolved",
             receipt="run-2026-09-03-0100-u-x01.json"):
    """One row as ``archive.attempt_ledger`` emits it."""
    return {"unknown_id": unknown_id, "receipt": receipt, "verdict": verdict,
            "observations": 2}


def _ledger(*attempts, **buckets):
    """A receipt ledger, injected. Empty unless a test says otherwise.

    Every test here passes one, so nothing in this file reads the live
    ``reports/receipts/`` except the two that say in their name that they do.
    """
    base = {"attempts": list(attempts), "undecidable": [], "refused": [],
            "unreadable": [], "error": ""}
    base.update(buckets)
    return base


# ── the deadline ─────────────────────────────────────────────────────────────

def test_the_goal_can_fail():
    """A deadline that slides is a wish with a calendar next to it. Past the
    date with conditions unmet, the published state must read MISSED."""
    p = G.progress([_u(track="A")], today=G.DEADLINE + timedelta(days=1),
                   ledger=_ledger())
    assert p["state"] == "MISSED"
    assert p["days_remaining"] < 0


def test_before_the_deadline_an_unmet_goal_is_open_not_failing():
    p = G.progress([_u(track="A")], today=G.DEADLINE - timedelta(days=5),
                   ledger=_ledger())
    assert p["state"] == "OPEN" and p["days_remaining"] == 5


# ── what counts as an attempt ────────────────────────────────────────────────

def test_a_feasibility_test_is_not_an_attempt():
    """The rule that stops the goal being satisfiable by more pricing. Every
    unknown in the catalogue on the day this was set had a measured reach and
    none had been attempted; if reach verdicts counted, the goal would already
    be met without a single question having been asked."""
    priced = _u(track="A", reach=U.IN_REACH,
                reach_evidence="measured 3.1 GPU-hours, in reach")
    p = G.progress([priced], today=G.GOAL.set_on, ledger=_ledger())
    assert p["conditions"]["a_field_unknown_attempted"] is False
    assert p["attempted"] == []


def test_an_attempt_is_a_receipt_not_a_sentence():
    """The condition's only input is the ledger, and the receipt that carried
    it is named in the feed so a stranger can open the thing being counted."""
    p = G.progress([_u(track="A")], today=G.GOAL.set_on,
                   ledger=_ledger(_attempt()))
    assert p["conditions"]["a_field_unknown_attempted"] is True
    assert p["attempted"] == ["U-X01"]
    assert p["attempt_receipts"] == ["run-2026-09-03-0100-u-x01.json"]


def test_the_denial_sentence_an_honest_corrector_reaches_for_is_inert():
    """**The vicious case, and the reason this grader was rewritten.**

    U-A01's catalogue entry was corrected on 2026-08-25 to say the run was a
    re-analysis: *"verdict REANALYSED — NOT an attempt"*. Under the substring
    grader, rewording that same correction to *"NOT ATTEMPTED"* — a strictly
    clearer way to say the identical thing — flipped G01 from OPEN to MET. The
    lever was never a cheat somebody had to intend; it was the denial you reach
    for first, and it graded the lab higher for telling the truth harder.

    Verified live before the repair landed: OPEN on the committed wording, MET
    on the reworded one, same receipts, same everything else.
    """
    for wording in ("verdict REANALYSED — NOT an attempt",
                    "verdict REANALYSED — NOT ATTEMPTED",
                    "NEVER ATTEMPTED",
                    "ATTEMPTED 2026-09-02; verdict unresolved"):
        p = G.progress([_u(track="A", reach_evidence=wording)],
                       today=G.GOAL.set_on, ledger=_ledger())
        assert p["conditions"]["a_field_unknown_attempted"] is False, wording
        assert p["attempted"] == [], wording


def test_nothing_written_in_the_catalogue_can_move_the_attempted_condition():
    """Wider than the sentence above: no `reach_evidence` prose anywhere in the
    real catalogue participates in the grade. Shout the trigger word into every
    entry at once and every published number must be byte-identical."""
    real = U.load()
    if not real:
        pytest.skip("UNKNOWNS.md not present in this checkout")
    shouted = [dataclasses.replace(u, reach_evidence="ATTEMPTED " * 3)
               for u in real]
    before = G.progress(real, today=G.GOAL.set_on, ledger=_ledger())
    after = G.progress(shouted, today=G.GOAL.set_on, ledger=_ledger())
    assert before == after
    assert after["conditions"]["a_field_unknown_attempted"] is False


def test_a_killed_or_unresolved_attempt_meets_the_goal():
    """The commitment is to attempt and report, not to succeed. A goal that
    only counts successes buys itself pressure to find them — which is the
    failure this whole estate is built to refuse."""
    for verdict in ("killed", "unresolved", "supported"):
        p = G.progress([_u(track="A")], today=G.GOAL.set_on,
                       ledger=_ledger(_attempt(verdict=verdict)))
        assert p["state"] == "MET", verdict


def test_an_attempt_on_something_that_does_not_cross_the_gate_does_not_count():
    """G01 asks for a FIELD unknown. A receipt attempting a `us` unknown is
    real work on the calibrate side of the gate and cannot close a discovery
    goal — the join is against the catalogue's own verdict, not the receipt's."""
    ours = _u(track="A", known_to_whom=U.US)
    p = G.progress([ours], today=G.GOAL.set_on, ledger=_ledger(_attempt()))
    assert p["conditions"]["a_field_unknown_attempted"] is False
    assert p["attempted"] == [] and p["attempt_receipts"] == []


# ── the denominator ──────────────────────────────────────────────────────────

def test_an_unpriced_track_blocks_the_goal_and_is_named():
    """Not just a false flag — the tracks holding it up are listed, so the
    published feed says what to do next rather than only that it is unmet."""
    p = G.progress([_u(id="U-A01", track="A"),
                    _u(id="U-M01", track="M", status=U.CLAIMED,
                       reach=U.UNTESTED)],
                   today=G.GOAL.set_on, ledger=_ledger(_attempt("U-A01")))
    assert p["conditions"]["every_track_charted"] is False
    assert p["tracks_without_a_charted_unknown"] == ["M"]


def test_a_retired_unknown_leaves_both_denominators():
    """What retirement actually does — which is not what this test used to say.

    Its docstring claimed retiring an unknown "must not be able to move the
    goal by itself in either direction", printed directly above two
    assertions that hold only BECAUSE it can. Retiring track C's single
    entry drops track C out of ``tracks`` as well as out of
    ``charted_tracks``, so the track stops counting as unpriced. That is
    refutation F3; it is still live, and it belongs to
    ``docs/doctrine/migration-order.md`` item 2(a)/(f) — not 2(c), which is
    all the 2026-09-03 grader repair touched. The assertions are therefore
    left exactly as they are and the sentence above them stops disagreeing
    with them. The lever itself is pinned by the negative control below.
    """
    p = G.progress([_u(id="U-A01", track="A"),
                    _u(id="U-C01", track="C", status=U.RETIRED)],
                   today=G.GOAL.set_on, ledger=_ledger(_attempt("U-A01")))
    assert p["conditions"]["every_track_charted"] is True
    assert p["unknowns_total"] == 1


def test_negative_control_retiring_an_unpriced_track_still_moves_the_goal():
    """The hole above, exercised rather than described.

    An unpriced track holds G01 OPEN. Retiring its only unknown — one status
    word in `UNKNOWNS.md`, no receipt, no work in between — makes the same
    catalogue read MET. The ATTEMPT half of this goal can no longer be moved
    by editing the catalogue; the DENOMINATOR half still can, by subtraction.

    Kept as a negative control so the gap is loud. The day item 2(a) reads
    TRACKS.md out of the goal's own `set_on` commit, this test goes red and
    is deleted — which is how a hole should close: visibly, and on purpose.
    """
    attempted = _ledger(_attempt("U-A01"))
    unpriced = [_u(id="U-A01", track="A"),
                _u(id="U-C01", track="C", status=U.CLAIMED, reach=U.UNTESTED)]
    retired = [_u(id="U-A01", track="A"),
               _u(id="U-C01", track="C", status=U.RETIRED)]
    assert G.progress(unpriced, today=G.GOAL.set_on,
                      ledger=attempted)["state"] == "OPEN"
    assert G.progress(retired, today=G.GOAL.set_on,
                      ledger=attempted)["state"] == "MET"


# ── failing closed ───────────────────────────────────────────────────────────

def test_a_broken_ledger_cannot_meet_the_goal_and_says_why():
    """The direction of the failure is the whole point. A ledger this box
    cannot read grades OPEN with its reason attached, never MET — and the
    reason is published rather than rounded to zero."""
    p = G.progress([_u(track="A")], today=G.GOAL.set_on,
                   ledger=_ledger(error="OSError: reports/receipts is gone"))
    assert p["state"] == "OPEN"
    assert p["conditions"]["a_field_unknown_attempted"] is False
    assert p["attempt_ledger_gaps"]["error"].startswith("OSError")


def test_the_gaps_the_grader_could_not_read_are_published():
    """A ledger with a refused receipt in it is a different public fact from a
    ledger with none, and both read OPEN. Publishing only the verdict would
    make those two indistinguishable to the reader who most needs the gap."""
    p = G.progress(
        [_u(track="A")], today=G.GOAL.set_on,
        ledger=_ledger(
            refused=[{"receipt": "run-2026-09-03-0200-u-x01.json",
                      "why": "receipt's headline does not match its verdict"}],
            undecidable=[{"receipt": "run-2026-08-24-1109-h01.json",
                          "why": "predates the 'stage' contract"}],
            unreadable=[{"receipt": "run-2026-09-01-0300-u-x01.json",
                         "why": "receipt will not parse"}]))
    gaps = p["attempt_ledger_gaps"]
    assert [r["receipt"] for r in gaps["refused"]] == \
           ["run-2026-09-03-0200-u-x01.json"]
    assert gaps["undecidable"] and gaps["unreadable"]
    assert p["state"] == "OPEN"


def test_progress_survives_a_ledger_that_explodes(monkeypatch):
    """``publish.py`` wraps this call in a bare ``except Exception: pass`` that
    DELETES the goal key from `pot.json`. So an exception in the ledger does not
    fail a publish — it silently blanks the lab's public commitment from a pass
    that exits 0. `progress()` must therefore return a dict no matter what the
    archive does, carrying the failure instead of becoming it."""
    from lab import archive

    def boom(*a, **kw):
        raise RuntimeError("the ledger is on fire")

    monkeypatch.setattr(archive, "attempt_ledger", boom)
    p = G.progress([_u(track="A")], today=G.GOAL.set_on)
    assert p["state"] == "OPEN"
    assert p["attempted"] == []
    assert "the ledger is on fire" in p["attempt_ledger_gaps"]["error"]


# ── the published shape ──────────────────────────────────────────────────────

def test_the_goal_states_its_own_arrival_condition_checkably():
    """`arrived_when` has to name things a stranger can look up in the feed, or
    the goal grades itself. It already said the right thing while the grader
    lied about it, so it is unchanged by the 2026-09-03 repair."""
    for token in ("pot.json", "charted", "ATTEMPTED", "killed", "receipt"):
        assert token in G.GOAL.arrived_when


def test_progress_is_derived_and_carries_no_hand_written_state():
    """Every field must be computable from the catalogue and the ledger. A
    stored progress number is a number somebody can edit when it looks bad."""
    p = G.progress([_u(track="A")], today=G.GOAL.set_on, ledger=_ledger())
    assert set(p) >= {"state", "conditions", "gate_ratio", "unknowns_charted",
                      "attempt_receipts", "attempt_ledger_gaps"}
    assert p["gate_ratio"] == 1.0


def test_the_committed_ledger_grades_the_goal_open():
    """The regression that pins the repair as INERT.

    Deriving `attempted` from receipts instead of from prose changed no
    published number: over the committed catalogue and the committed receipt
    ledger the goal reads OPEN with nothing attempted, exactly as `pot.json`
    says. The one receipt that carries a hypothesis block and a discovery stage
    is U-A01's, whose verdict is `reanalysed` — a re-reading of the archive,
    which is real work and is not a crossing of the gate.

    This test reads the real `reports/receipts/`, deliberately: an inert landing
    verified only against fixtures is not verified.
    """
    if not U.load():
        pytest.skip("UNKNOWNS.md not present in this checkout")
    p = G.progress(today=date(2026, 9, 3))
    assert p["state"] == "OPEN"
    assert p["conditions"]["a_field_unknown_attempted"] is False
    assert p["attempted"] == [] and p["attempt_receipts"] == []
    assert p["attempt_ledger_gaps"]["error"] == ""
    assert p["attempt_ledger_gaps"]["refused"] == []


def test_the_goal_reaches_the_published_feed():
    """The whole point of publishing it: nobody has to be told the lab missed."""
    import json
    from pathlib import Path
    pot = Path(__file__).resolve().parents[1] / "pot.json"
    if not pot.exists():
        pytest.skip("pot.json not built in this checkout")
    g = json.loads(pot.read_text(encoding="utf-8")).get("goal")
    assert g and g["id"] == G.GOAL.id
    assert g["state"] in ("OPEN", "MET", "MISSED")
    assert "honesty_note" in g
