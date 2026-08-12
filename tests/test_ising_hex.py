"""Honeycomb (hexagonal) Ising engine — the geometry is the whole risk surface.

M05's triangular half already proved the *physics* plumbing. What is genuinely
new here is a lattice defined by a **parity rule**, and a parity rule is exactly
the kind of thing that runs happily while being subtly wrong: get the sign
backwards and you still get a 3-regular-looking graph, just one whose vertical
bonds are non-reciprocal at the seam, whose T_c lands somewhere meaningless, and
whose curve still looks like a phase transition.

So the tests below are almost all *exact*, small-lattice, and independent of the
engine's own vectorised code path:

* degree is exactly 3 everywhere (not 2, not 4);
* the adjacency relation is **symmetric** — every claimed bond is claimed from
  both ends (the failure mode odd L produces);
* the graph is **bipartite** under ``(i+j)%2``, which is what licenses the plain
  checkerboard update ``ising_tri`` could not use;
* **girth ≥ 6** — no two sites share two neighbours, so there are no 4-cycles;
  a honeycomb has hexagonal faces and nothing shorter;
* the ground-state energy is exactly ``−1.5`` per spin (z/2 with z = 3), which
  no square (−2.0) or triangular (−3.0) lattice can produce;
* the torch ``_neighbor_sum`` reproduces the loop-written ``neighbor_coords``
  ground truth bond-for-bond on random configurations.

Only after all of that does anything thermal run.
"""
import math

import numpy as np
import pytest
import torch

from lab.ising_hex import (
    TC_HEX,
    HexRunConfig,
    HexRunResult,
    _initial_spins,
    _neighbor_sum,
    _vertical_parity_mask,
    energy_per_spin,
    neighbor_coords,
    require_even_L,
    run,
)


CUDA_AVAILABLE = torch.cuda.is_available()


# ── the exact constant ────────────────────────────────────────────────────────

def test_tc_hex_is_two_over_ln_two_plus_root_three():
    # 2 / ln(2 + √3) ≈ 1.518651 — the exact honeycomb Ising T_c, computed the
    # same way the module does, so the assertion is exact.
    assert TC_HEX == pytest.approx(2.0 / math.log(2.0 + math.sqrt(3.0)), rel=0, abs=1e-15)
    assert abs(TC_HEX - 1.518651) < 1e-5


def test_tc_hex_orders_below_square_and_triangular():
    """z = 3 < 4 < 6 ⇒ T_c(hex) < T_c(square) < T_c(tri). Fewer neighbours holding
    a spin in line means thermal noise wins at a lower temperature — a physical
    ordering the three exact numbers must respect, and a guard against pasting the
    wrong closed form in."""
    square = 2.0 / math.log(1.0 + math.sqrt(2.0))     # 2.2692
    triangular = 4.0 / math.log(3.0)                  # 3.6410
    assert TC_HEX < square < triangular


# ── geometry: degree, reciprocity, bipartiteness, girth ──────────────────────

@pytest.mark.parametrize("L", [4, 6, 8, 12])
def test_every_site_has_exactly_three_distinct_neighbours(L):
    coords = neighbor_coords(L)
    assert coords.shape == (L, L, 3, 2)
    for i in range(L):
        for j in range(L):
            nbrs = {tuple(c) for c in coords[i, j]}
            assert len(nbrs) == 3, f"site ({i},{j}) has {len(nbrs)} distinct neighbours"
            assert (i, j) not in nbrs, "no self-bonds"


@pytest.mark.parametrize("L", [4, 6, 8, 12])
def test_adjacency_is_symmetric(L):
    """Every bond is claimed from both ends — the property the parity rule exists
    to guarantee and the one odd L silently destroys at the row seam."""
    coords = neighbor_coords(L)
    nbr = {(i, j): {tuple(c) for c in coords[i, j]} for i in range(L) for j in range(L)}
    for site, ns in nbr.items():
        for other in ns:
            assert site in nbr[other], f"{site}→{other} is not reciprocated"


@pytest.mark.parametrize("L", [4, 6, 8, 12])
def test_lattice_is_bipartite_under_the_plain_checkerboard(L):
    """``(i+j)%2`` is a proper 2-colouring: no site shares a colour with a
    neighbour. This is precisely what the *triangular* lattice fails and why
    ``ising_tri`` needed a 3-colouring — the honeycomb does not."""
    coords = neighbor_coords(L)
    for i in range(L):
        for j in range(L):
            for (ni, nj) in coords[i, j]:
                assert (i + j) % 2 != (ni + nj) % 2, (
                    f"({i},{j}) and its neighbour ({ni},{nj}) share a colour — "
                    f"the checkerboard update would not be exact"
                )


@pytest.mark.parametrize("L", [6, 8, 12])
def test_girth_is_at_least_six_no_four_cycles(L):
    """A honeycomb's faces are hexagons: no two distinct sites share more than one
    neighbour, so there is no 4-cycle. Combined with bipartiteness (no 3- or
    5-cycles) that pins the girth at 6 — a square lattice, by contrast, is full of
    4-cycles, so this test alone separates the two geometries.

    L = 4 is excluded: on a 4×4 torus the wrap is tight enough to create genuine
    short cycles, which is a property of the tiny torus and not of the rule.
    """
    coords = neighbor_coords(L)
    nbr = {(i, j): {tuple(c) for c in coords[i, j]} for i in range(L) for j in range(L)}
    sites = list(nbr)
    for a_idx, a in enumerate(sites):
        for b in sites[a_idx + 1:]:
            shared = nbr[a] & nbr[b]
            assert len(shared) <= 1, (
                f"{a} and {b} share {len(shared)} neighbours → a 4-cycle; the "
                f"honeycomb has girth 6"
            )


@pytest.mark.parametrize("L", [4, 6, 8, 12])
def test_bond_count_is_three_halves_N(L):
    """3-regular ⇒ E = 3N/2 bonds. The square lattice has 2N, triangular 3N."""
    coords = neighbor_coords(L)
    bonds = set()
    for i in range(L):
        for j in range(L):
            for (ni, nj) in coords[i, j]:
                bonds.add(frozenset({(i, j), (int(ni), int(nj))}))
    assert len(bonds) == 3 * L * L // 2


def test_vertical_partner_follows_the_parity_rule_in_the_stated_direction():
    """Pin the *direction*, not just the reciprocity: even ``(i+j)`` reaches UP to
    ``(i+1, j)``, odd reaches DOWN to ``(i−1, j)``. Flipping this convention gives
    an equally valid honeycomb, so it is not a physics bug — but the engine's
    vectorised ``where(even, roll(−1), roll(+1))`` must agree with the reference
    construction, or the two disagree about which sites are which."""
    coords = neighbor_coords(8)
    # (2, 2): i+j = 4, even → up
    assert tuple(coords[2, 2, 2]) == (3, 2)
    # (2, 3): i+j = 5, odd → down
    assert tuple(coords[2, 3, 2]) == (1, 3)
    # Seam, L = 8: (7, 1) has i+j = 8, even → up wraps to row 0
    assert tuple(coords[7, 1, 2]) == (0, 1)
    # and (0, 1) has i+j = 1, odd → down wraps back to row 7. Reciprocal.
    assert tuple(coords[0, 1, 2]) == (7, 1)


def test_odd_L_is_rejected():
    with pytest.raises(ValueError, match="even"):
        require_even_L(7)
    with pytest.raises(ValueError, match="even"):
        neighbor_coords(9)
    with pytest.raises(ValueError, match="even"):
        run(HexRunConfig(L=15, n_temps=1, n_burnin=1, n_sweeps=1, device="cpu"))


# ── the vectorised engine reproduces the reference geometry ──────────────────

@pytest.mark.parametrize("L", [4, 8, 12])
def test_torch_neighbor_sum_matches_the_loop_written_ground_truth(L):
    """The engine's rolls are a *different implementation* of the same graph. If
    the parity ``where`` is inverted, or a roll sign is wrong, this diverges even
    though every other structural test above (which only reads ``neighbor_coords``)
    would still pass."""
    torch.manual_seed(11)
    spins = (torch.randint(0, 2, (3, L, L), dtype=torch.int8) * 2 - 1)
    even = _vertical_parity_mask(L, torch.device("cpu"))
    got = _neighbor_sum(spins, even).numpy()

    coords = neighbor_coords(L)
    s = spins.numpy().astype(np.int64)
    want = np.zeros_like(got, dtype=np.int64)
    for i in range(L):
        for j in range(L):
            for (ni, nj) in coords[i, j]:
                want[:, i, j] += s[:, ni, nj]
    assert np.array_equal(got.astype(np.int64), want)


def test_parity_mask_is_the_checkerboard():
    even = _vertical_parity_mask(6, torch.device("cpu"))
    assert bool(even[0, 0]) and bool(even[1, 1])
    assert not bool(even[0, 1]) and not bool(even[1, 0])
    # Half the sites in each colour — the update visits everything exactly once.
    assert int(even.sum()) == 18


# ── exact energies ────────────────────────────────────────────────────────────

def test_ground_state_energy_is_exactly_minus_three_halves():
    """All spins up on a 3-regular lattice: E/N = −z/2 = −1.5, exactly. The square
    lattice would give −2.0 and the triangular −3.0, so this single number is a
    coordination-number assay."""
    L = 8
    even = _vertical_parity_mask(L, torch.device("cpu"))
    spins = torch.ones((1, L, L), dtype=torch.int8)
    assert energy_per_spin(spins, even).item() == pytest.approx(-1.5, abs=1e-6)


def test_perfect_antiferromagnet_is_exactly_plus_three_halves():
    """Because the lattice is bipartite, the checkerboard state frustrates *every*
    bond — E/N = +1.5, the exact mirror of the ground state. On a non-bipartite
    lattice (triangular) this is impossible, so the test also re-confirms
    bipartiteness through the energy rather than through the adjacency lists."""
    L = 8
    device = torch.device("cpu")
    even = _vertical_parity_mask(L, device)
    spins = torch.where(even, 1, -1).to(torch.int8).unsqueeze(0)
    assert energy_per_spin(spins, even).item() == pytest.approx(1.5, abs=1e-6)


def test_a_single_flipped_spin_costs_exactly_six():
    """ΔE for flipping one aligned spin = 2·J·z = 6 (total, i.e. 6/N per spin).
    Square would be 8, triangular 12 — the third independent read on z = 3."""
    L = 8
    even = _vertical_parity_mask(L, torch.device("cpu"))
    spins = torch.ones((1, L, L), dtype=torch.int8)
    e0 = energy_per_spin(spins, even).item() * L * L
    flipped = spins.clone()
    flipped[0, 3, 4] = -1
    e1 = energy_per_spin(flipped, even).item() * L * L
    assert e1 - e0 == pytest.approx(6.0, abs=1e-4)


# ── thermal behaviour (CPU, tiny) ─────────────────────────────────────────────

def test_cpu_run_smoke_and_shapes():
    cfg = HexRunConfig(L=12, n_temps=4, n_burnin=20, n_sweeps=40, sample_every=10,
                       device="cpu")
    r = run(cfg)
    assert isinstance(r, HexRunResult)
    for arr in (r.T, r.abs_mag, r.abs_mag_err, r.chi, r.chi_abs, r.energy,
                r.specific_heat):
        assert arr.shape == (4,)
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1).all()
    assert (r.chi_abs >= 0).all()
    assert (r.specific_heat >= 0).all()
    assert len(r.snapshots) == 3
    assert r.wall_seconds > 0
    payload = r.to_json()
    assert payload["config"]["L"] == 12
    assert len(payload["chi_abs"]) == 4


def test_determinism_same_seed_same_numbers():
    kw = dict(L=12, n_temps=3, n_burnin=20, n_sweeps=40, sample_every=10, device="cpu")
    a = run(HexRunConfig(seed=42, **kw))
    b = run(HexRunConfig(seed=42, **kw))
    c = run(HexRunConfig(seed=43, **kw))
    assert np.allclose(a.abs_mag, b.abs_mag)
    assert np.allclose(a.energy, b.energy)
    assert not np.allclose(a.abs_mag, c.abs_mag)


def test_energy_never_leaves_the_exact_bounds():
    """−1.5 ≤ E/N ≤ +1.5 at every temperature, always. A neighbour-sum bug that
    double-counted a bond would blow straight through the floor."""
    cfg = HexRunConfig(L=12, n_temps=5, T_min=0.4, T_max=6.0, n_burnin=30,
                       n_sweeps=60, sample_every=10, device="cpu")
    r = run(cfg)
    assert (r.energy >= -1.5 - 1e-6).all()
    assert (r.energy <= 1.5 + 1e-6).all()


def test_orders_below_tc_and_disorders_far_above():
    """The coarsest physics gate: deep in the cold phase the lattice is nearly
    saturated, deep in the hot phase it is nearly random. T = 0.5 and T = 6.0
    bracket the exact T_c = 1.5187 by a wide margin, so this needs no tolerance
    argument — it would fail loudly for a lattice with the wrong T_c *scale*."""
    cold = run(HexRunConfig(L=24, n_temps=1, T_min=0.5, T_max=0.5, n_burnin=400,
                            n_sweeps=200, sample_every=10, device="cpu"))
    hot = run(HexRunConfig(L=24, n_temps=1, T_min=6.0, T_max=6.0, n_burnin=400,
                           n_sweeps=200, sample_every=10, device="cpu"))
    assert cold.abs_mag[0] > 0.9, f"cold phase not ordered: {cold.abs_mag[0]}"
    assert hot.abs_mag[0] < 0.2, f"hot phase not disordered: {hot.abs_mag[0]}"
    # And the cold energy sits near the exact ground state −1.5.
    assert cold.energy[0] < -1.35


@pytest.mark.skipif(not CUDA_AVAILABLE, reason="GPU not available")
def test_tiny_gpu_run_smoke():
    cfg = HexRunConfig(L=16, n_temps=5, n_burnin=20, n_sweeps=40, sample_every=10,
                       device="cuda")
    r = run(cfg)
    assert r.chi_abs.shape == (5,)
    assert (r.chi_abs >= 0).all()
    assert (r.energy >= -1.5 - 1e-5).all()


# ── initial state: the 2026-08-11 metastability fix ──────────────────────────

def test_ordered_is_the_default_and_random_is_opt_in():
    """This engine flips ``ising.RunConfig``'s default. Deliberate: the honeycomb
    reproduced M01's 2026-07-23 stripe-domain incident on its first L=128 run,
    with only three bonds per site making domain walls cheaper and slower to
    dissolve than on the square or triangular lattices."""
    assert HexRunConfig().initial_state == "ordered"
    assert HexRunConfig(initial_state="random").initial_state == "random"


def test_initial_spins_honours_both_states_and_rejects_anything_else():
    device = torch.device("cpu")
    rng = torch.Generator(device=device).manual_seed(7)

    ordered = _initial_spins(HexRunConfig(L=6, n_temps=2, device="cpu"), device, rng)
    assert ordered.shape == (2, 6, 6)
    assert torch.all(ordered == 1)

    rand = _initial_spins(
        HexRunConfig(L=6, n_temps=2, device="cpu", initial_state="random"), device, rng)
    assert set(rand.unique().tolist()) <= {-1, 1}
    assert not torch.all(rand == 1)

    with pytest.raises(ValueError, match="initial_state"):
        _initial_spins(
            HexRunConfig(L=6, n_temps=1, device="cpu", initial_state="mystery"),
            device, rng)


def test_ordered_start_still_disorders_above_tc():
    """The load-bearing control on the ordered default.

    An ordered start is only legitimate if it cannot manufacture order that
    isn't there. Well above T_c = 1.5187 the lattice must forget its initial
    condition entirely — if it did not, the ordered start would bias the χ peak
    upward and the whole measurement would be circular.
    """
    hot = run(HexRunConfig(L=24, n_temps=1, T_min=6.0, T_max=6.0, n_burnin=300,
                           n_sweeps=200, sample_every=10, device="cpu"))
    assert hot.abs_mag[0] < 0.2, f"ordered start did not disorder: {hot.abs_mag[0]}"


def test_both_starts_agree_far_from_the_transition():
    """Ordered and random starts sample the same equilibrium; only the approach
    differs. Away from the critical region — where equilibration is fast either
    way — they must agree on the energy, or the two are not the same physics."""
    kw = dict(L=16, n_temps=1, T_min=4.0, T_max=4.0, n_burnin=400, n_sweeps=400,
              sample_every=10, device="cpu")
    ordered = run(HexRunConfig(initial_state="ordered", **kw))
    rand = run(HexRunConfig(initial_state="random", **kw))
    assert abs(ordered.energy[0] - rand.energy[0]) < 0.02
    assert abs(ordered.abs_mag[0] - rand.abs_mag[0]) < 0.05


def test_magnetization_is_non_increasing_in_temperature():
    """Equilibrium ⟨|m|⟩(T) never rises with T. This is the property the failed
    2026-08-11 run violated at 46σ, and the one ``checks.nonequilibrated_indices``
    grades against — asserted here on the engine itself so the fix is verified at
    the source, not only at the gate. A small tolerance absorbs sampling noise on
    a deliberately short run."""
    r = run(HexRunConfig(L=24, n_temps=8, T_min=0.8, T_max=3.0, n_burnin=300,
                         n_sweeps=300, sample_every=10, device="cpu"))
    for k in range(len(r.T) - 1):
        assert r.abs_mag[k + 1] <= r.abs_mag[k] + 0.03, (
            f"|m| rose from T={r.T[k]:.3f} to T={r.T[k+1]:.3f}: "
            f"{r.abs_mag[k]:.4f} → {r.abs_mag[k+1]:.4f}"
        )
