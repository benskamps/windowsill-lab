"""The declared goal — and the three properties that make it a commitment.

A goal in a plan document is a preference. This one is published in `pot.json`,
its progress is computed rather than written, and it is allowed to read MISSED.
Each of those is load-bearing and each has a test here, because each is exactly
the kind of thing that quietly stops being true.
"""
from __future__ import annotations

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


def test_the_goal_can_fail():
    """A deadline that slides is a wish with a calendar next to it. Past the
    date with conditions unmet, the published state must read MISSED."""
    p = G.progress([_u(track="A")], today=G.DEADLINE + timedelta(days=1))
    assert p["state"] == "MISSED"
    assert p["days_remaining"] < 0


def test_before_the_deadline_an_unmet_goal_is_open_not_failing():
    p = G.progress([_u(track="A")], today=G.DEADLINE - timedelta(days=5))
    assert p["state"] == "OPEN" and p["days_remaining"] == 5


def test_a_feasibility_test_is_not_an_attempt():
    """The rule that stops the goal being satisfiable by more pricing. Every
    unknown in the catalogue on the day this was set had a measured reach and
    none had been attempted; if reach verdicts counted, the goal would already
    be met without a single question having been asked."""
    priced = _u(track="A", reach=U.IN_REACH,
                reach_evidence="measured 3.1 GPU-hours, in reach")
    p = G.progress([priced], today=G.GOAL.set_on)
    assert p["conditions"]["a_field_unknown_attempted"] is False
    assert p["attempted"] == []


def test_an_actual_attempt_satisfies_the_condition():
    tried = _u(track="A", reach=U.IN_REACH,
               reach_evidence="ATTEMPTED 2026-09-02; verdict unresolved")
    p = G.progress([tried], today=G.GOAL.set_on)
    assert p["conditions"]["a_field_unknown_attempted"] is True
    assert p["attempted"] == ["U-X01"]


def test_a_killed_or_unresolved_attempt_meets_the_goal():
    """The commitment is to attempt and report, not to succeed. A goal that
    only counts successes buys itself pressure to find them — which is the
    failure this whole estate is built to refuse."""
    for verdict in ("killed", "unresolved", "supported"):
        p = G.progress([_u(track="A",
                           reach_evidence=f"ATTEMPTED; verdict {verdict}")],
                       today=G.GOAL.set_on)
        assert p["state"] == "MET", verdict


def test_an_unpriced_track_blocks_the_goal_and_is_named():
    """Not just a false flag — the tracks holding it up are listed, so the
    published feed says what to do next rather than only that it is unmet."""
    p = G.progress([_u(id="U-A01", track="A", reach_evidence="ATTEMPTED; killed"),
                    _u(id="U-M01", track="M", status=U.CLAIMED, reach=U.UNTESTED)],
                   today=G.GOAL.set_on)
    assert p["conditions"]["every_track_charted"] is False
    assert p["tracks_without_a_charted_unknown"] == ["M"]


def test_a_retired_unknown_neither_blocks_nor_counts():
    """U-C01 is flagged as probably already answered in 2004. Retiring it must
    not be able to move the goal by itself in either direction."""
    p = G.progress([_u(id="U-A01", track="A", reach_evidence="ATTEMPTED; killed"),
                    _u(id="U-C01", track="C", status=U.RETIRED)],
                   today=G.GOAL.set_on)
    assert p["conditions"]["every_track_charted"] is True
    assert p["unknowns_total"] == 1


def test_the_goal_states_its_own_arrival_condition_checkably():
    """`arrived_when` has to name things a stranger can look up in the feed, or
    the goal grades itself."""
    for token in ("pot.json", "charted", "ATTEMPTED", "killed"):
        assert token in G.GOAL.arrived_when


def test_progress_is_derived_and_carries_no_hand_written_state():
    """Every field must be computable from the catalogue. A stored progress
    number is a number somebody can edit when it looks bad."""
    p = G.progress([_u(track="A")], today=G.GOAL.set_on)
    assert set(p) >= {"state", "conditions", "gate_ratio", "unknowns_charted"}
    assert p["gate_ratio"] == 1.0


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
