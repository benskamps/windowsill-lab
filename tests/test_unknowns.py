"""The catalogue of unknowns, and the first feasibility test run against it.

The rule these tests protect is the one the whole file exists for: a gap in US
must not be able to wear a FIELD unknown's coat. That confusion is how a
calibration bench convinces itself it has crossed the SETI gate, and it is not
caught by any amount of rigour applied downstream — by then the question has
already been mislabelled.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab import u_k01_window as uk
from lab import unknowns as U


def _u(**over):
    base = dict(id="U-X01", track="X", question="q?", why_open="nobody checked",
                known_to_whom=U.FIELD, who_would_care="somebody",
                feasibility_test="a cheap probe", if_out_of_reach="buy a bigger box")
    base.update(over)
    return U.Unknown(**base)


# ── the contract ─────────────────────────────────────────────────────────────

def test_an_unknown_without_a_feasibility_test_is_a_wish():
    with pytest.raises(ValueError) as caught:
        _u(feasibility_test="")
    assert "feasibility_test" in str(caught.value)


def test_an_unknown_must_say_who_does_not_know_it():
    with pytest.raises(ValueError):
        _u(known_to_whom="")
    with pytest.raises(ValueError):
        _u(known_to_whom="sort of everyone")


def test_out_of_reach_must_leave_a_next_step():
    """A reach verdict with no `if_out_of_reach` is a shrug, and a shrug ends
    the line of inquiry silently."""
    with pytest.raises(ValueError) as caught:
        _u(if_out_of_reach="  ")
    assert "if_out_of_reach" in str(caught.value)


def test_only_a_field_unknown_crosses_the_gate():
    """The distinction the file exists to force. A gap in us is calibration —
    frequently the right work, never discovery."""
    assert _u(known_to_whom=U.FIELD).crosses_the_gate is True
    assert _u(known_to_whom=U.US).crosses_the_gate is False
    assert _u(known_to_whom=U.REACH).crosses_the_gate is False


# ── the heartbeat's choice ───────────────────────────────────────────────────

def test_the_heartbeat_tests_reach_before_attempting_the_question():
    """Deliberately not 'the most important unknown'. Attempting a question
    before knowing the instrument can see it is how four GPU-hours buy nothing;
    the feasibility test is always cheaper than the attempt."""
    picked = U.next_to_test([
        _u(id="U-A01", importance=5, reach=U.OUT_OF_REACH),
        _u(id="U-B01", importance=4),
        _u(id="U-C01", importance=5),
    ])
    assert picked.id == "U-C01", "an already-measured wall must not be re-measured"


def test_a_retired_unknown_is_never_picked():
    assert U.next_to_test([_u(status=U.RETIRED, importance=5)]) is None


def test_an_empty_catalogue_returns_nothing_rather_than_inventing_work():
    assert U.next_to_test([]) is None


def test_the_gate_ratio_counts_only_field_unknowns():
    ratio = U.gate_ratio([_u(id="U-A01", known_to_whom=U.FIELD),
                          _u(id="U-B01", known_to_whom=U.US),
                          _u(id="U-C01", known_to_whom=U.REACH),
                          _u(id="U-D01", known_to_whom=U.FIELD, status=U.RETIRED)])
    assert ratio["total"] == 3 and ratio["field"] == 1
    assert ratio["ratio"] == pytest.approx(1 / 3)


# ── the shipped catalogue ────────────────────────────────────────────────────

def test_the_shipped_catalogue_parses_and_every_track_with_a_goal_appears():
    """A track with a destination and no unknown is a track that has stopped
    asking — which looks identical to a healthy one on every other surface."""
    from lab import frontier
    us = U.load()
    assert us, "UNKNOWNS.md must parse to at least one entry"
    tracked = {u.track for u in us}
    goals = set(frontier.parse_tracks(
        (Path(__file__).resolve().parents[1] / "TRACKS.md").read_text(encoding="utf-8")))
    # Track B donates cycles and has no observable of its own to not-know.
    assert (goals - tracked) <= {"B"}, f"tracks with a goal but no unknown: {goals - tracked}"


def test_shipped_unknowns_are_claimed_until_somebody_checks():
    """These were drafted by a machine that is confident but not authoritative
    about the literature. Anything marked `charted` must be charted on evidence
    this repo holds, not on that confidence."""
    for u in U.load():
        if u.status == U.CHARTED:
            assert u.reach_evidence.strip(), (
                f"{u.id} is charted with no evidence recorded")


# ── U-K01: the first reach test ──────────────────────────────────────────────

RECEIPT = (Path(__file__).resolve().parents[1]
           / "reports/receipts/run-2026-08-23-2216-k03.json")


def test_local_exponents_recover_a_clean_power_law():
    """Control: on synthetic data that IS a power law, the local slopes must be
    constant. Without this the drift test could report drift on anything."""
    eps = [0.01, 0.02, 0.04, 0.08]
    chi = [e ** -0.25 for e in eps]
    loc = uk.local_exponents(eps, chi)
    assert all(abs(x["gamma_local"] - 0.25) < 1e-9 for x in loc)
    assert uk.drift(loc)["constant"] is True


def test_drift_is_detected_on_a_deliberate_crossover():
    """The negative control: data with a genuine crossover must NOT be reported
    as constant."""
    eps = [0.01, 0.02, 0.04, 0.08]
    chi = [1.0, 1.5, 2.6, 5.4]
    assert uk.drift(uk.local_exponents(eps, chi))["constant"] is False


def test_nonpositive_susceptibility_is_dropped_not_fitted_around():
    loc = uk.local_exponents([0.01, 0.02, 0.04], [1.0, -3.0, 4.0])
    assert len(loc) == 1


def test_the_reach_verdict_on_the_committed_k03_receipt_is_out_of_reach():
    """The measured result, pinned so a future change to the engine cannot
    quietly turn a window artifact back into a measurement."""
    r = uk.run(RECEIPT)
    assert r["reach"] == "out-of-reach"
    assert r["branches"]["above"]["drift"]["falling_toward_small_eps"] is True
    assert r["branches"]["above"]["drift"]["relative_span"] > uk.DRIFT_TOL


def test_the_reach_test_records_that_the_supercritical_branch_cannot_discriminate():
    """The fact that made this unknown worth charting: Daido and Hong predict
    the SAME supercritical gamma, so the branch K03 measured most cleanly is the
    one that carries no information about which paper is right."""
    from lab import k03
    assert k03.DAIDO["gamma"] == k03.HONG["gamma"]
    assert uk.DISCRIMINATING_GAP == pytest.approx(
        k03.DAIDO["gamma_prime"] - k03.HONG["gamma_prime"])
    assert "no discriminating power" in uk.run(RECEIPT)["note_on_discrimination"]


def test_resolving_power_is_reported_so_the_blocker_is_named():
    """If the instrument had ample precision and still cannot answer, the
    blocker is the window — and saying which one it is decides whether the next
    spend is a bigger N or a smaller epsilon."""
    r = uk.run(RECEIPT)
    assert r["sigma_separation_if_measured"] > 10
