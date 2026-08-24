"""P01 / HP lattice — the parts that must hold before any fold is believed.

The lab's first biology engine, so the controls carry more weight than usual:
nothing here has thirty milestones of precedent behind it.
"""
from __future__ import annotations

import itertools

import numpy as np
import pytest

from lab import hp_lattice as hp
from lab import p01


def _brute_force(seq: str) -> int:
    """Every walk, no pruning, no symmetry — the slow truth for short chains."""
    is_h = hp.parse_sequence(seq)
    n = len(is_h)
    best = 0
    for combo in itertools.product(range(4), repeat=n - 1):
        pts = [(0, 0)]
        for s in combo:
            dx, dy = hp.STEPS[s]
            pts.append((pts[-1][0] + dx, pts[-1][1] + dy))
        if len(set(pts)) != n:
            continue
        best = min(best, hp.energy(np.array(pts), is_h))
    return best


# ── the energy function, against folds that can be checked by hand ───────────

def test_a_square_of_four_hydrophobics_has_exactly_one_contact():
    """Beads 0 and 3 close the ring and touch; 0-1, 1-2, 2-3 are backbone and
    must not count, or the sequence would be rewarded for merely existing."""
    square = np.array([[0, 0], [1, 0], [1, 1], [0, 1]])
    assert hp.energy(square, hp.parse_sequence("HHHH")) == -1


def test_a_straight_rod_has_no_contacts():
    rod = np.array([[0, 0], [1, 0], [2, 0], [3, 0]])
    assert hp.energy(rod, hp.parse_sequence("HHHH")) == 0


def test_polar_beads_never_contribute():
    square = np.array([[0, 0], [1, 0], [1, 1], [0, 1]])
    assert hp.energy(square, hp.parse_sequence("HPPH")) == -1   # 0-3 only
    assert hp.energy(square, hp.parse_sequence("PPPP")) == 0


@pytest.mark.parametrize("coords", [
    [[0, 0], [1, 0], [0, 0]],          # revisits a site: two beads in one place
    [[0, 0], [5, 0]],                  # a step longer than the lattice allows
    [[0, 0], [1, 1]],                  # diagonal is not a lattice step
])
def test_invalid_walks_are_rejected(coords):
    assert not hp.is_self_avoiding(np.array(coords))


# ── the pruned enumerator, against the unpruned truth ────────────────────────

@pytest.mark.parametrize("seq", [
    "HPHPPHHPHH", "HHPPHPPHPH", "HPHPHPHPHP", "HHHPPPHHHP", "PHPHPHHHPP",
])
def test_pruning_and_symmetry_never_lose_the_optimum(seq):
    """The enumerator fixes the first step and prunes on an optimistic bound.
    Both are only safe if the answer is identical to brute force — an
    admissible bound that is not actually admissible would silently return a
    too-high energy and every downstream 'recovery' would be measured against
    the wrong target."""
    assert hp.enumerate_ground_state(seq)["energy"] == _brute_force(seq)


def test_the_enumerated_witness_is_a_real_fold():
    proof = hp.enumerate_ground_state("HPHPPHHPHH")
    coords = np.array(proof["coords"])
    assert hp.is_self_avoiding(coords)
    assert hp.energy(coords, hp.parse_sequence("HPHPPHHPHH")) == proof["energy"]


def test_enumeration_reports_what_it_cost():
    """'Exhaustive' is a claim about work done; the receipt carries the count
    so it is accompanied by its evidence rather than asserted."""
    assert hp.enumerate_ground_state("HHPPHH")["nodes_visited"] > 0


# ── the parity argument: an exact answer with no search in it ────────────────

@pytest.mark.parametrize("seq", ["HPHPHPHPHP", "HPHPHPHPHPHP", "PHPHPHPHPH"])
def test_single_parity_sequences_cannot_fold_at_all(seq):
    """A square lattice is bipartite: adjacent sites always differ in the parity
    of x+y, and a bead's parity is fixed by its position along the chain. So H
    beads confined to one sequence parity can never touch, and the ground state
    is exactly zero — provable without folding anything."""
    assert hp.enumerate_ground_state(seq)["energy"] == 0
    assert hp.fold(seq, n_sweeps=400, n_replicas=4, seed=3)["energy"] == 0


# ── the sampler ──────────────────────────────────────────────────────────────

def test_the_blind_search_finds_a_proven_optimum():
    seq = "HPHPPHHPHH"
    proof = hp.enumerate_ground_state(seq)
    found = hp.fold(seq, n_sweeps=4000, n_replicas=6, seed=1)
    assert found["energy"] == proof["energy"]


def test_every_conformation_the_sampler_returns_is_legal():
    """A search that reports an illegal fold has found nothing, however low the
    number attached to it."""
    seq = "HHPPHPPHPH"
    found = hp.fold(seq, n_sweeps=2000, n_replicas=4, seed=2)
    coords = np.array(found["coords"])
    assert hp.is_self_avoiding(coords)
    assert hp.energy(coords, hp.parse_sequence(seq)) == found["energy"]


def test_the_search_never_reports_below_the_true_optimum():
    """The direction that would mean the energy function and the search
    disagree — impossible if both are right, so worth asserting."""
    seq = "HHPPHPPHPH"
    proof = hp.enumerate_ground_state(seq)
    found = hp.fold(seq, n_sweeps=3000, n_replicas=6, seed=5)
    assert found["energy"] >= proof["energy"]


def test_the_temperature_ladder_actually_exchanges():
    """Replica exchange with a dead gap is a set of independent chains wearing
    a ladder's name — the same self-alarm M12's spin glass carries."""
    found = hp.fold("HPHPPHHPHH", n_sweeps=2000, n_replicas=6, seed=4)
    assert found["swap_health"] == "ok", found["swap_health"]


# ── the checker refuses what it should ───────────────────────────────────────

def _receipt(**over):
    seq = "HPHPPHHPHH"
    proof = hp.enumerate_ground_state(seq)
    row = {"sequence": seq, "length": len(seq), "enumerated": proof["energy"],
           "energy": proof["energy"], "coords": proof["coords"],
           "recovered": True, "shuffle_energy": 0, "shuffled_sequence": ""}
    row.update(over)
    return {"experiment": "P01-hp-lattice-folding", "graded": [row],
            "parity_controls": []}


def test_a_true_receipt_grades_true():
    from lab import checks
    ok, detail = checks.check_p01(_receipt())
    assert ok is True, detail


def test_an_edited_energy_is_caught_by_the_geometry():
    """The receipt says one thing, its own coordinates say another."""
    from lab import checks
    ok, detail = checks.check_p01(_receipt(energy=-99))
    assert ok is False and "coordinates give" in detail


def test_an_illegal_conformation_is_refused():
    from lab import checks
    ok, detail = checks.check_p01(_receipt(coords=[[0, 0], [1, 0], [0, 0]]))
    assert ok is False and "self-avoiding" in detail


def test_a_shuffle_may_legitimately_fold_lower():
    """The control this replaced would have failed here on correct physics:
    HHHPPPHHHPP has optimum -2 and a permutation of it reaches -3, because
    clustering hydrophobics lowers energy. A permutation is a different
    sequence, not a null."""
    from lab import checks
    seq = "HHHPPPHHHPP"
    shuffled = "PHHHPHPHHPP"   # the permutation the 2026-08-24 run actually drew
    proof = hp.enumerate_ground_state(seq)
    sproof = hp.enumerate_ground_state(shuffled)
    assert sproof["energy"] < proof["energy"], "the premise of this test"
    ok, detail = checks.check_p01({
        "experiment": "P01-hp-lattice-folding", "parity_controls": [],
        "graded": [{"sequence": seq, "enumerated": proof["energy"],
                    "energy": proof["energy"], "coords": proof["coords"],
                    "shuffled_sequence": shuffled,
                    "shuffle_enumerated": sproof["energy"],
                    "shuffle_energy": sproof["energy"]}]})
    assert ok is True, detail


def test_a_search_that_misses_the_shuffles_optimum_fails():
    from lab import checks
    ok, detail = checks.check_p01(_receipt(shuffled_sequence="HHHHPPPPPH",
                                           shuffle_enumerated=-99,
                                           shuffle_energy=-99))
    assert ok is False and "re-enumeration proves" in detail


def test_a_parity_control_with_both_parities_is_not_a_control():
    from lab import checks
    receipt = _receipt()
    receipt["parity_controls"] = [{"sequence": "HHPP", "energy": 0, "enumerated": 0}]
    ok, detail = checks.check_p01(receipt)
    assert ok is None and "BOTH" in detail


def test_a_foreign_receipt_is_not_graded():
    from lab import checks
    assert checks.check_p01({"experiment": "A02-variable-star-recovery"})[0] is None


# ── the declared sample ──────────────────────────────────────────────────────

def test_the_graded_set_is_short_enough_to_prove():
    """The whole method rests on enumeration being affordable at grading time."""
    assert p01.GRADED
    for seq in p01.GRADED:
        assert len(seq) <= 14, f"{seq} is too long to re-enumerate in a check"


def test_the_parity_controls_really_are_single_parity():
    for seq in p01.PARITY_CONTROLS:
        idx = [i for i, c in enumerate(seq) if c == "H"]
        assert idx and len({i % 2 for i in idx}) == 1, seq


def test_reported_sequences_are_kept_out_of_the_graded_set():
    """Best-found is not a proven optimum, and the two must never be pooled."""
    assert not (set(p01.REPORTED) & set(p01.GRADED))
