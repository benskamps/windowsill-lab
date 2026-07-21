"""3D simple-cubic Wolff single-cluster updater — correctness invariants.

ALL tests run on device="cpu" with tiny lattices (L<=8) and short runs so the
whole module finishes in a few seconds with no GPU dependency. The structural
facts (3 bonds per site, p→0 / p→1 limits, flip-is-xor, frozen-field idempotence,
batched independence) are *exact*; the physics facts (energy / |m| agreement with
the verified ``ising3d`` Metropolis engine) are the detailed-balance check — if the
cluster construction sampled the wrong distribution, it could not reproduce the
Metropolis curve that already lands the 3D benchmark T_c ≈ 4.5115.
"""
import numpy as np
import torch

from lab.wolff3d import (
    Wolff3DConfig,
    Wolff3DResult,
    _neighbor_sum,
    _bond_field,
    _seed_mask,
    _grow_cluster,
    wolff_update,
    wolff_run,
)
from lab import ising3d


def _beta(T):
    return torch.tensor([1.0 / t for t in T], dtype=torch.float32)


# --------------------------------------------------------------------------- #
# config + smoke
# --------------------------------------------------------------------------- #
def test_config_defaults():
    cfg = Wolff3DConfig()
    assert cfg.L == 16
    assert cfg.n_temps == 21
    assert cfg.device == "cpu"
    assert cfg.n_samples() == cfg.n_updates // cfg.sample_every


def test_cpu_run_smoke():
    """Tiny wolff_run on CPU produces sensible-shaped outputs without crashing."""
    cfg = Wolff3DConfig(
        L=6, T_min=4.0, T_max=5.0, n_temps=3,
        n_burnin=10, n_updates=40, sample_every=5, seed=7, device="cpu",
    )
    r = wolff_run(cfg)
    assert isinstance(r, Wolff3DResult)
    assert r.T.shape == (3,)
    for arr in (r.abs_mag, r.abs_mag_err, r.chi, r.chi_abs, r.energy,
                r.specific_heat, r.mean_cluster_fraction):
        assert arr.shape == (3,)
    # specific heat is a variance-based observable ⇒ non-negative
    assert (r.specific_heat >= -1e-9).all()
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1.0 + 1e-6).all()
    assert (r.chi_abs >= -1e-9).all()
    # cluster fraction is a fraction of L^3 sites
    assert (r.mean_cluster_fraction > 0).all()
    assert (r.mean_cluster_fraction <= 1.0 + 1e-6).all()
    # energy per spin on a 6-coordinated lattice lives in [-3, 3]
    assert (r.energy >= -3.001).all() and (r.energy <= 3.001).all()
    assert len(r.snapshots) == 3
    # snapshots are 2D int8 mid-plane slices in {-1,+1}
    for snap in r.snapshots.values():
        assert snap.shape == (6, 6)
        assert set(np.unique(snap)).issubset({-1, 1})
    # JSON-able
    j = r.to_json()
    assert j["config"]["L"] == 6
    assert len(j["T"]) == 3


# --------------------------------------------------------------------------- #
# neighbour sum: six on a uniform lattice
# --------------------------------------------------------------------------- #
def test_neighbor_sum_is_six_for_uniform_lattice():
    spins = torch.ones((2, 4, 4, 4), dtype=torch.int8)
    nbr = _neighbor_sum(spins)
    assert nbr.shape == (2, 4, 4, 4)
    assert (nbr == 6).all()
    assert (_neighbor_sum(-spins) == -6).all()


# --------------------------------------------------------------------------- #
# bond field: shapes, three orientations, drawn-once/frozen
# --------------------------------------------------------------------------- #
def test_bond_field_shapes_and_dtype():
    L, n = 5, 3
    g = torch.Generator(device="cpu").manual_seed(1)
    spins = (torch.randint(0, 2, (n, L, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    p = torch.full((n, 1, 1, 1), 0.5)
    bx, by, bz = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(2))
    for b in (bx, by, bz):
        assert b.shape == (n, L, L, L)
        assert b.dtype == torch.bool


def test_each_site_owns_exactly_three_bonds():
    """Monochromatic lattice, p≈1: EVERY aligned bond fires, totalling 3·n·L³.

    This is the load-bearing 'enumerate each undirected bond exactly once' fact —
    three orientations per site, never six. A double-counting bug would inflate
    this total.
    """
    L, n = 6, 2
    spins = torch.ones((n, L, L, L), dtype=torch.int8)
    beta = torch.tensor([10.0, 10.0], dtype=torch.float32)  # p ≈ 1
    p = (1.0 - torch.exp(-2.0 * beta)).view(-1, 1, 1, 1)
    bx, by, bz = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(3))
    total = bx.sum().item() + by.sum().item() + bz.sum().item()
    assert total == 3 * n * L ** 3
    # each orientation carries exactly n·L³ bonds on a monochromatic torus
    assert bx.sum().item() == n * L ** 3
    assert by.sum().item() == n * L ** 3
    assert bz.sum().item() == n * L ** 3


def test_bond_field_drawn_once_frozen():
    """Re-growing on the SAME frozen bonds is idempotent (no mid-flood resampling)."""
    L, n = 6, 2
    g = torch.Generator(device="cpu").manual_seed(123)
    spins = (torch.randint(0, 2, (n, L, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([4.0, 5.0])
    p = (1.0 - torch.exp(-2.0 * beta)).view(-1, 1, 1, 1)
    bx, by, bz = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(999))
    seed = _seed_mask(n, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(555))
    c1 = _grow_cluster(seed, bx, by, bz)
    c2 = _grow_cluster(seed, bx, by, bz)
    assert torch.equal(c1, c2)
    # seed site is always in the cluster
    assert (c1 & seed).sum().item() == n


# --------------------------------------------------------------------------- #
# p -> 0 and p -> 1 limits
# --------------------------------------------------------------------------- #
def test_p_to_zero_single_site():
    """High T (beta tiny ⇒ p≈0): no bonds activate, cluster is just the seed."""
    L, n = 6, 3
    g = torch.Generator(device="cpu").manual_seed(42)
    spins = (torch.randint(0, 2, (n, L, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = torch.tensor([1e-6, 1e-6, 1e-6], dtype=torch.float32)
    p = (1.0 - torch.exp(-2.0 * beta)).view(-1, 1, 1, 1)
    bx, by, bz = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(3))
    assert bx.sum().item() == 0 and by.sum().item() == 0 and bz.sum().item() == 0
    seed = _seed_mask(n, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(4))
    cluster = _grow_cluster(seed, bx, by, bz)
    assert torch.equal(cluster, seed)
    assert cluster.sum(dim=(-1, -2, -3)).tolist() == [1, 1, 1]


def test_p_to_one_spans_domain():
    """All-up lattice, beta large (p≈1): one update floods the whole cube."""
    L, n = 6, 2
    spins = torch.ones((n, L, L, L), dtype=torch.int8)
    beta = torch.tensor([10.0, 10.0], dtype=torch.float32)
    p = (1.0 - torch.exp(-2.0 * beta)).view(-1, 1, 1, 1)
    bx, by, bz = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(5))
    seed = _seed_mask(n, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(6))
    cluster = _grow_cluster(seed, bx, by, bz)
    # the whole monochromatic torus is one connected component
    assert cluster.all()


# --------------------------------------------------------------------------- #
# monochromatic cluster + flip-is-xor
# --------------------------------------------------------------------------- #
def test_cluster_monochromatic():
    """Every site that flips shared the seed's pre-flip sign."""
    L, n = 6, 3
    g = torch.Generator(device="cpu").manual_seed(77)
    spins = (torch.randint(0, 2, (n, L, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([3.5, 4.5, 6.0])
    p = (1.0 - torch.exp(-2.0 * beta)).view(-1, 1, 1, 1)
    bx, by, bz = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(8))
    seed = _seed_mask(n, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(9))
    cluster = _grow_cluster(seed, bx, by, bz)
    seed_spin = spins[seed].view(n)  # one True per lattice
    for k in range(n):
        members = spins[k][cluster[k]]
        if members.numel() > 0:
            assert (members == seed_spin[k]).all()


def test_flip_is_xor():
    """spins_out == spins_in off-cluster, flipped on-cluster; values stay ±1."""
    L, n = 6, 3
    g = torch.Generator(device="cpu").manual_seed(11)
    spins = (torch.randint(0, 2, (n, L, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([3.6, 4.5, 6.1])
    g_step = torch.Generator(device="cpu").manual_seed(321)
    out, cluster = wolff_update(spins, beta, g_step, return_cluster=True)
    assert set(torch.unique(out).tolist()).issubset({-1, 1})
    assert out.dtype == torch.int8
    expected = spins * (1 - 2 * cluster.to(torch.int8))
    assert torch.equal(out, expected.to(torch.int8))
    changed = out != spins
    assert torch.equal(changed, cluster)


def test_update_returns_size_matches_cluster():
    """return_size reports the exact cluster cardinality."""
    L, n = 6, 2
    g = torch.Generator(device="cpu").manual_seed(15)
    spins = (torch.randint(0, 2, (n, L, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([3.5, 5.0])
    g_step = torch.Generator(device="cpu").manual_seed(404)
    _, size, cluster = wolff_update(spins, beta, g_step, return_size=True, return_cluster=True)
    assert torch.equal(size, cluster.sum(dim=(-1, -2, -3)))
    assert (size >= 1).all()  # at minimum the seed site


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_determinism_update():
    L, n = 6, 3
    g = torch.Generator(device="cpu").manual_seed(13)
    spins = (torch.randint(0, 2, (n, L, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([3.7, 4.5, 6.2])
    g1 = torch.Generator(device="cpu").manual_seed(2024)
    g2 = torch.Generator(device="cpu").manual_seed(2024)
    out1 = wolff_update(spins.clone(), beta, g1)
    out2 = wolff_update(spins.clone(), beta, g2)
    assert torch.equal(out1, out2)


def test_determinism_run():
    cfg = Wolff3DConfig(
        L=6, T_min=4.0, T_max=5.0, n_temps=3,
        n_burnin=8, n_updates=40, sample_every=5, seed=99, device="cpu",
    )
    r1 = wolff_run(cfg)
    r2 = wolff_run(cfg)
    assert np.array_equal(r1.T, r2.T)
    assert np.array_equal(r1.abs_mag, r2.abs_mag)
    assert np.array_equal(r1.energy, r2.energy)
    assert np.array_equal(r1.chi_abs, r2.chi_abs)


# --------------------------------------------------------------------------- #
# batched independence (no cross-lattice information flow)
# --------------------------------------------------------------------------- #
def test_batched_independence_no_crosstalk():
    """Lattice 0 (all-up, floods) and lattice 1 (3D checkerboard, no bonds) don't leak.

    A 3D checkerboard colours site (x,y,z) by (x+y+z)%2, so every nearest-neighbour
    pair is anti-aligned and no bond can activate — the cluster is the seed alone.
    """
    L = 6
    up = torch.ones((1, L, L, L), dtype=torch.int8)
    ix, iy, iz = torch.meshgrid(
        torch.arange(L), torch.arange(L), torch.arange(L), indexing="ij"
    )
    checker = (((ix + iy + iz) % 2) * 2 - 1).to(torch.int8).view(1, L, L, L)
    spins = torch.cat([up, checker], dim=0)
    beta = torch.tensor([10.0, 10.0], dtype=torch.float32)  # p ≈ 1
    p = (1.0 - torch.exp(-2.0 * beta)).view(-1, 1, 1, 1)
    bx, by, bz = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(31))
    # checkerboard: no aligned neighbours anywhere → zero bonds on lattice 1
    assert bx[1].sum().item() == 0 and by[1].sum().item() == 0 and bz[1].sum().item() == 0
    seed = _seed_mask(2, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(32))
    cluster = _grow_cluster(seed, bx, by, bz)
    assert cluster[0].all()                      # lattice 0: whole cube one component
    assert torch.equal(cluster[1], seed[1])      # lattice 1: seed only, no crosstalk
    assert cluster[1].sum().item() == 1


# --------------------------------------------------------------------------- #
# fixpoint reached on a contrived line through the torus
# --------------------------------------------------------------------------- #
def test_fixpoint_captures_full_line():
    """A full x-line of bonds is captured completely — BFS doesn't stop short."""
    L, n = 8, 1
    bx = torch.zeros((n, L, L, L), dtype=torch.bool)
    by = torch.zeros((n, L, L, L), dtype=torch.bool)
    bz = torch.zeros((n, L, L, L), dtype=torch.bool)
    # +x bonds along the line y=0,z=0 chain (0,0,0)->(1,0,0)->...->(L-1,0,0)->(0,0,0)
    bx[0, :, 0, 0] = True
    seed = torch.zeros((n, L, L, L), dtype=torch.bool)
    seed[0, 0, 0, 0] = True
    cluster = _grow_cluster(seed, bx, by, bz)
    expect = torch.zeros((n, L, L, L), dtype=torch.bool)
    expect[0, :, 0, 0] = True
    assert torch.equal(cluster, expect)


def test_grow_cluster_captures_bent_path():
    """A path that bends across two axes is fully captured well under L³ passes."""
    L, n = 6, 1
    bx = torch.zeros((n, L, L, L), dtype=torch.bool)
    by = torch.zeros((n, L, L, L), dtype=torch.bool)
    bz = torch.zeros((n, L, L, L), dtype=torch.bool)
    # full x-line at (y=0,z=0); then a +y bond joining (0,0,0)->(0,1,0); full x-line at y=1
    bx[0, :, 0, 0] = True
    by[0, 0, 0, 0] = True   # (0,0,0)<->(0,1,0)
    bx[0, :, 1, 0] = True
    seed = torch.zeros((n, L, L, L), dtype=torch.bool)
    seed[0, 0, 0, 0] = True
    cluster = _grow_cluster(seed, bx, by, bz)
    expect = torch.zeros((n, L, L, L), dtype=torch.bool)
    expect[0, :, 0, 0] = True
    expect[0, :, 1, 0] = True
    assert torch.equal(cluster, expect)


# --------------------------------------------------------------------------- #
# physics: detailed-balance check vs the verified 3D Metropolis engine
# --------------------------------------------------------------------------- #
def _short_wolff3d(T, L, seed=42):
    cfg = Wolff3DConfig(
        L=L, T_min=T, T_max=T, n_temps=1,
        n_burnin=120, n_updates=600, sample_every=2, seed=seed, device="cpu",
    )
    return wolff_run(cfg)


def _short_metro3d(T, L, seed=42):
    cfg = ising3d.Run3DConfig(
        L=L, T_min=T, T_max=T, n_temps=1,
        n_burnin=600, n_sweeps=800, sample_every=4, seed=seed,
    )
    return ising3d.run(cfg)


def test_energy_and_absmag_match_metropolis_ordered():
    """T=3.0 (ordered, T<T_c≈4.5115): Wolff reproduces Metropolis |m| and energy.

    Agreement with the engine that already lands T_c is the detailed-balance check:
    a cluster-construction bug (wrong p, double-counted bonds, mid-flood resampling)
    would not sample the same Boltzmann distribution.
    """
    T, L = 3.0, 6
    w = _short_wolff3d(T, L)
    m = _short_metro3d(T, L)
    assert abs(w.abs_mag[0] - m.abs_mag[0]) < 0.05, (w.abs_mag[0], m.abs_mag[0])
    assert abs(w.energy[0] - m.energy[0]) < 0.10, (w.energy[0], m.energy[0])
    assert w.abs_mag[0] > 0.85            # strongly ordered
    assert -3.0 <= w.energy[0] <= 0.0


def test_energy_and_absmag_match_metropolis_disordered():
    """T=7.0 (disordered, T>T_c): Wolff reproduces Metropolis, weakly magnetised."""
    T, L = 7.0, 6
    w = _short_wolff3d(T, L)
    m = _short_metro3d(T, L)
    assert abs(w.abs_mag[0] - m.abs_mag[0]) < 0.06, (w.abs_mag[0], m.abs_mag[0])
    assert abs(w.energy[0] - m.energy[0]) < 0.20, (w.energy[0], m.energy[0])
    assert w.abs_mag[0] < 0.35            # disordered
    assert -3.0 <= w.energy[0] <= 0.0


def test_order_parameter_ordered_above_disordered():
    """|m| is high below T_c and low above it (a sign error would invert this)."""
    w_lo = _short_wolff3d(3.0, 6)
    w_hi = _short_wolff3d(7.0, 6)
    assert w_lo.abs_mag[0] > w_hi.abs_mag[0]
    assert w_lo.abs_mag[0] > 0.8
    assert w_hi.abs_mag[0] < 0.35


def test_cluster_fraction_monotone_in_T():
    """mean_cluster_fraction decreases as T rises (ordered → disordered)."""
    cfg = Wolff3DConfig(
        L=6, T_min=3.0, T_max=7.0, n_temps=4,
        n_burnin=60, n_updates=200, sample_every=2, seed=5, device="cpu",
    )
    r = wolff_run(cfg)
    cf = r.mean_cluster_fraction
    assert cf[0] > cf[-1]
    assert cf[-1] < 0.5
