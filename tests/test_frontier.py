"""The frontier board — the reading that asks rather than answers.

Hermetic: every test builds its own ladder and its own charter, so none of these
change meaning when a real milestone is promoted.
"""
from __future__ import annotations

from lab import frontier


TRACKS = """
## Track M — physics on a lattice

**Goal.** Reproduce the canon and know a result from a number.

**Arrived when.** Every rung re-derives from committed bytes.

## Track Z — a track with no goal
"""


def _rung(mid, status="verified", result="", runner=True):
    return {"id": mid, "status": status, "result": result,
            "runner_available": runner, "track": "physics"}


# ── destinations ─────────────────────────────────────────────────────────────

def test_a_track_declares_a_goal_and_an_arrival_test():
    tracks = frontier.parse_tracks(TRACKS)
    assert tracks["M"]["name"] == "physics on a lattice"
    assert "canon" in tracks["M"]["goal"]
    assert "committed bytes" in tracks["M"]["arrived_when"]


def test_a_track_without_a_goal_is_reported_not_scored_as_fine():
    """A missing destination is the quietest possible failure — the ladder still
    looks busy while nobody can say what it is climbing toward."""
    board = frontier.steward([_rung("Z01")], frontier.parse_tracks(TRACKS))
    assert board[0]["charter_missing"] is True


# ── the steward ──────────────────────────────────────────────────────────────

def test_a_pending_rung_with_no_runner_is_named_as_blocked():
    """The scheduler cannot dispatch it, so it will sit on the ladder looking
    like a plan forever. That is a blocker wearing a plan's costume."""
    board = frontier.steward(
        [_rung("M01"), _rung("M02", status="pending", runner=False)],
        frontier.parse_tracks(TRACKS))
    assert board[0]["no_runner"] == ["M02"]


def test_review_and_null_rungs_are_surfaced_separately():
    board = frontier.steward(
        [_rung("M01", status="review"), _rung("M02", status="null")],
        frontier.parse_tracks(TRACKS))
    assert board[0]["awaiting_review"] == ["M01"]
    assert board[0]["nulls"] == ["M02"]


def test_the_open_bench_is_identified():
    board = frontier.steward([_rung("M01", status="open")],
                            frontier.parse_tracks(TRACKS))
    assert board[0]["open"] == "M01"


# ── the harvest ──────────────────────────────────────────────────────────────

def test_an_admitted_limit_is_harvested_with_its_sentence():
    rung = _rung("M14", result="The energy is exact. Precise pinning of p_c is "
                              "deferred to a large-L hero run. Report attached.")
    found = frontier.harvest([rung])
    assert len(found) == 1
    assert found[0]["milestone"] == "M14"
    assert "deferred to a large-L hero run" in found[0]["sentence"]
    assert "The energy is exact" not in found[0]["sentence"], "quoted too widely"


def test_nothing_is_invented():
    """If the lab never wrote it down, it does not appear. The whole point of
    harvesting rather than generating."""
    assert frontier.harvest([_rung("M01", result="Everything worked.")]) == []


def test_a_strength_is_not_mistaken_for_a_confession():
    """The first cut matched 'cannot' and surfaced M17's 'prose and data cannot
    drift apart' — a guarantee — as an open question. A generator that is half
    noise teaches its reader to skip it."""
    rung = _rung("M17", result="The boundary text is derived from the measured "
                               "gaps, so prose and data cannot drift apart.")
    assert frontier.harvest([rung]) == []


def test_the_quoted_sentence_does_not_break_on_decimals():
    """This prose is full of 'L=6,8,10,12' and '0.80-1.60'. A naive split on '.'
    returned fragments like 'on one 0', which read as gibberish and made the
    harvest look broken."""
    rung = _rung("M12", result="The run used a 0.80-1.60 ladder of 16 rungs and "
                               "the question stays unresolved at this size.")
    sentence = frontier.harvest([rung])[0]["sentence"]
    assert "0.80-1.60" in sentence


def test_each_candidate_carries_what_it_still_owes():
    rung = _rung("M14", result="Precise pinning is deferred to a hero run.")
    assert frontier.harvest([rung])[0]["needs"] == list(frontier.HYPOTHESIS_SCHEMA)


def test_a_hypothesis_must_be_able_to_die():
    """The load-bearing field. An idea that cannot say what would refute it is
    not a hypothesis, and one whose proposer will not say how it might be
    nothing has not been thought about."""
    assert "kill_condition" in frontier.HYPOTHESIS_SCHEMA
    assert "why_this_might_be_nothing" in frontier.HYPOTHESIS_SCHEMA


def test_one_confession_per_milestone():
    """A rung that hedges five times is one open question, not five."""
    rung = _rung("M14", result="Pinning the point precisely is deferred to a hero "
                               "run. The asymmetry question remains open at this "
                               "size. The exponent is left unresolved for now.")
    assert len(frontier.harvest([rung])) == 1


# ── the whole board ──────────────────────────────────────────────────────────

def test_the_board_counts_what_a_reader_would_act_on():
    ladder = [_rung("M01"),
              _rung("M02", status="pending", runner=False),
              _rung("M03", status="review"),
              _rung("M04", result="Pinning it is deferred to a hero run.")]
    b = frontier.board(milestones=ladder, tracks_text=TRACKS)
    assert b["totals"]["milestones"] == 4
    assert b["totals"]["awaiting_review"] == 1
    assert b["totals"]["unrunnable"] == 1
    assert b["totals"]["candidates"] == 1


def test_the_board_reads_the_real_ladder_without_crashing():
    """The one non-hermetic check: the shipped TRACKS.md and MILESTONES.md must
    actually parse, or the command is decorative."""
    b = frontier.board()
    assert b["totals"]["tracks"] >= 5
    assert b["totals"]["tracks_without_a_goal"] == 0, "a shipped track has no goal"
