"""STR-3 — one lattice kernel, imported by all, never copy-pasted again.

The defect this pins (gauntlet ledger, LANE 4): ``_checkerboard_masks`` was
copy-pasted across six engine modules while *other* modules imported the shared
one, "so a fix in ising reaches wolff and afm automatically and never reaches
potts, xy or heisenberg. Wrong-science time bomb." The unification makes
``ising`` the single canonical home — the import pattern ``wolff`` and
``ising_afm`` already used — and this file is the guard that a future
convenience copy-paste turns red instead of silently forking the physics.

The 3D kernels are deliberately NOT unified with the 2D one and are asserted
distinct here, so the boundary is a statement rather than an accident:
``ising3d`` (numpy, ``(x+y+z)%2`` on one lattice) and
``spin_glass3d._checkerboard_masks_3d`` (torch, no batch axis) answer different
shape contracts on a different lattice graph.
"""
from __future__ import annotations

import torch

from lab import glauber, heisenberg, ising, ising_afm, potts, random_bond, spin_glass, wolff, xy


def test_every_2d_engine_shares_isings_checkerboard():
    """One object, not six equal-looking ones — identity, so a divergence is
    structurally impossible rather than merely untested."""
    for mod in (potts, xy, glauber, spin_glass, random_bond, ising_afm):
        assert mod._checkerboard_masks is ising._checkerboard_masks, (
            f"{mod.__name__} carries its own checkerboard again — the STR-3 "
            "time bomb is being rebuilt; import it from lab.ising instead")


def test_the_neighbor_sum_is_shared_too():
    for mod in (glauber, ising_afm, wolff):
        assert mod._neighbor_sum is ising._neighbor_sum, (
            f"{mod.__name__} forked _neighbor_sum")


def test_heisenbergs_broadcast_variant_wraps_the_canonical_mask():
    """heisenberg's (n, L, L, 1) contract is its own; the mask under it is
    ising's. Squeezing the broadcast axis must recover the canonical output
    exactly — if this drifts, heisenberg has re-derived its own lattice."""
    dev = torch.device("cpu")
    ha, hb = heisenberg._checkerboard_masks(6, 3, dev)
    ia, ib = ising._checkerboard_masks(6, 3, dev)
    assert ha.shape == (3, 6, 6, 1) and ha.dtype == torch.bool
    assert torch.equal(ha.squeeze(-1), ia)
    assert torch.equal(hb.squeeze(-1), ib)


def test_the_masks_are_actually_a_checkerboard():
    """The physics the six engines rely on: complementary masks, equal halves
    on even L, and every masked site's four neighbours on the other colour."""
    a, b = ising._checkerboard_masks(8, 1, torch.device("cpu"))
    assert torch.equal(b, ~a)
    assert int(a.sum()) == int(b.sum()) == 8 * 8 // 2
    for shift in ((1, -2), (-1, -2), (1, -1), (-1, -1)):
        assert torch.equal(torch.roll(a, shift[0], dims=shift[1]), b)


def test_the_3d_kernels_are_deliberately_separate():
    from lab import ising3d, spin_glass3d
    assert ising3d._checkerboard_masks is not ising._checkerboard_masks
    assert spin_glass3d._checkerboard_masks_3d is not ising._checkerboard_masks
