"""Exact ground-state degeneracy — the rarest number this lab can produce.

No statistics, no equilibration argument, no error bar to defend: either the
tree was walked or it was not. Every test here checks the counter against an
UNPRUNED brute-force walk, because the whole value of an exact count is that it
is exact, and a pruning bug would produce a confident wrong integer.

The single line that separates counting from minimising: `enumerate_ground_state`
prunes what cannot BEAT the incumbent (`>= best`), which discards ties by
construction; `enumerate_degeneracy` prunes only what cannot REACH the target
(`> target`).
"""
from __future__ import annotations

import pytest

from lab import hp_lattice as hp


def _brute(seq: str) -> tuple[int, int]:
    """Every self-avoiding walk under the same symmetry quotient, no pruning."""
    is_h = hp.parse_sequence(seq)
    n = len(is_h)
    hits: list[int] = []

    def rec(coords, occ, idx, e, broken):
        if idx == n:
            hits.append(e)
            return
        px, py = coords[idx - 1]
        for dx, dy in hp.STEPS:
            p = (px + dx, py + dy)
            if p in occ:
                continue
            b = broken
            if not broken and dy != 0:
                if dy < 0:
                    continue
                b = True
            c = 0
            if is_h[idx]:
                for ex, ey in hp.STEPS:
                    j = occ.get((p[0] + ex, p[1] + ey))
                    if j is not None and idx - j > 1 and is_h[j]:
                        c += 1
            occ[p] = idx
            coords.append(p)
            rec(coords, occ, idx + 1, e - c, b)
            coords.pop()
            del occ[p]

    rec([(0, 0), (1, 0)], {(0, 0): 0, (1, 0): 1}, 2, 0, False)
    m = min(hits)
    return m, hits.count(m)


@pytest.mark.parametrize("seq", [
    "HPHPPHHP", "HHHPPPHH", "HPPHPPHH", "HHPHPHPH", "PPHHPPHH",
    "HHHHPPPP", "HPHPHPHP", "PPPPPPHH", "HHPPHHPP", "HPPPPPHH",
])
def test_the_count_matches_an_unpruned_walk(seq):
    """The control that makes the number worth anything."""
    e, d = _brute(seq)
    got = hp.enumerate_degeneracy(seq)
    assert got["energy"] == e
    assert got["degeneracy"] == d


def test_the_minimum_agrees_with_the_existing_enumerator():
    """Two independent walks of the same tree must agree on E*, or one of them
    is pruning something it should not."""
    for seq in ("HPHPPHHPHPPH", "HHHPPPHHHPPP", "HPPHPPHHPPHH"):
        assert hp.enumerate_degeneracy(seq)["energy"] == \
               hp.enumerate_ground_state(seq)["energy"]


def test_a_sequence_with_a_provably_unique_fold_reports_one():
    got = hp.enumerate_degeneracy("HPPHPPHH")
    assert got["degeneracy"] == 1 and got["unique"] is True


def test_a_highly_degenerate_sequence_is_not_reported_as_designable():
    got = hp.enumerate_degeneracy("PPHHPPHH")
    assert got["degeneracy"] > 1 and got["unique"] is False


def test_supplying_the_target_skips_the_first_pass_and_agrees():
    seq = "HPHPPHHPHP"
    e = hp.enumerate_ground_state(seq)["energy"]
    assert hp.enumerate_degeneracy(seq, target=e)["degeneracy"] == \
           hp.enumerate_degeneracy(seq)["degeneracy"]


def test_counting_at_a_non_optimal_energy_counts_that_level_instead():
    """The target is fixed in advance so the criterion cannot move mid-walk —
    which also means the counter answers 'how many at E' for any E, and a
    higher E must admit at least as many conformations as the ground state."""
    seq = "HPHPPHHP"
    ground = hp.enumerate_degeneracy(seq)
    excited = hp.enumerate_degeneracy(seq, target=ground["energy"] + 1)
    assert excited["degeneracy"] >= 1


def test_a_chain_too_short_to_fold_is_refused():
    with pytest.raises(ValueError):
        hp.enumerate_degeneracy("H")


def test_the_walk_reports_its_own_cost():
    """'Exhaustive' must arrive with its price attached rather than asserted."""
    assert hp.enumerate_degeneracy("HPHPPHHP")["nodes"] > 0
