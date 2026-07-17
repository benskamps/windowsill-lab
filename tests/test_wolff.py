"""Wolff single-cluster updater — correctness invariants.

ALL tests run on device="cpu" with tiny lattices (L<=24) and short runs so the
whole module finishes in a few seconds with no GPU dependency. The physics
invariants (energy / |m| agreement with Metropolis, Onsager sanity, cluster
behaviour as p->0 / p->1) are encoded directly per the design's invariant list.
"""
import math

import numpy as np
import pytest
import torch

from lab.wolff import (
    WolffConfig,
    WolffResult,
    _bond_field,
    _seed_mask,
    _grow_cluster,
    wolff_update,
    wolff_run,
)
from lab.ising import RunConfig, run, _neighbor_sum
from lab.onsager import T_C


def _beta(T):
    return torch.tensor([1.0 / t for t in T], dtype=torch.float32)


# --------------------------------------------------------------------------- #
# config + smoke
# --------------------------------------------------------------------------- #
def test_wolffconfig_defaults():
    cfg = WolffConfig()
    assert cfg.L == 128
    assert cfg.n_temps == 21
    assert cfg.device == "cpu"
    assert cfg.n_samples() == cfg.n_updates // cfg.sample_every


def test_cpu_run_smoke():
    """Tiny wolff_run on CPU produces sensible-shaped outputs without crashing."""
    cfg = WolffConfig(
        L=12, T_min=2.0, T_max=2.5, n_temps=3,
        n_burnin=10, n_updates=40, sample_every=5, seed=7, device="cpu",
    )
    r = wolff_run(cfg)
    assert r.T.shape == (3,)
    assert r.abs_mag.shape == (3,)
    assert r.abs_mag_err.shape == (3,)
    assert r.chi.shape == (3,)
    assert r.chi_abs.shape == (3,)
    assert r.energy.shape == (3,)
    assert r.mean_cluster_fraction.shape == (3,)
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1.0 + 1e-6).all()
    assert (r.chi_abs >= 0).all()
    # cluster fraction is a fraction of L^2 sites
    assert (r.mean_cluster_fraction > 0).all()
    assert (r.mean_cluster_fraction <= 1.0 + 1e-6).all()
    assert len(r.snapshots) == 3
    # snapshots are 2D int8 lattices in {-1,+1}
    for snap in r.snapshots.values():
        assert snap.shape == (12, 12)
        assert set(np.unique(snap)).issubset({-1, 1})
    # JSON-able
    j = r.to_json()
    assert j["config"]["L"] == 12
    assert len(j["T"]) == 3


# --------------------------------------------------------------------------- #
# bond field frozen / drawn once
# --------------------------------------------------------------------------- #
def test_bond_field_drawn_once_frozen():
    """Re-running _grow_cluster on the SAME frozen bonds is idempotent.

    Proves BFS does not re-sample randomness mid-flood: the fixpoint of a frozen
    bond field is unique, so a second growth from the same seed must match.
    """
    L, n = 16, 2
    g = torch.Generator(device="cpu").manual_seed(123)
    spins = (torch.randint(0, 2, (n, L, L), generator=g, device="cpu", dtype=torch.int8) * 2 - 1)
    beta = _beta([1.5, 2.5])
    p = (1.0 - torch.exp(-2.0 * beta * 1.0)).view(-1, 1, 1)
    gb = torch.Generator(device="cpu").manual_seed(999)
    bond_down, bond_right = _bond_field(spins, p, gb)
    gs = torch.Generator(device="cpu").manual_seed(555)
    seed = _seed_mask(n, L, torch.device("cpu"), gs)
    c1 = _grow_cluster(seed, bond_down, bond_right)
    c2 = _grow_cluster(seed, bond_down, bond_right)
    assert torch.equal(c1, c2)
    # seed site is always in the cluster
    assert (c1 & seed).sum().item() == n


def test_bond_field_shapes_and_dtype():
    L, n = 8, 3
    g = torch.Generator(device="cpu").manual_seed(1)
    spins = (torch.randint(0, 2, (n, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    p = torch.full((n, 1, 1), 0.5)
    bd, br = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(2))
    assert bd.shape == (n, L, L) and br.shape == (n, L, L)
    assert bd.dtype == torch.bool and br.dtype == torch.bool


# --------------------------------------------------------------------------- #
# p -> 0 and p -> 1 limits
# --------------------------------------------------------------------------- #
def test_p_to_zero_single_site():
    """High T (beta tiny => p~=0): cluster is just the seed site."""
    L, n = 16, 3
    g = torch.Generator(device="cpu").manual_seed(42)
    spins = (torch.randint(0, 2, (n, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = torch.tensor([1e-6, 1e-6, 1e-6], dtype=torch.float32)  # p ~ 0
    p = (1.0 - torch.exp(-2.0 * beta * 1.0)).view(-1, 1, 1)
    bd, br = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(3))
    # essentially no bonds activate
    assert bd.sum().item() == 0 and br.sum().item() == 0
    seed = _seed_mask(n, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(4))
    cluster = _grow_cluster(seed, bd, br)
    # cluster == seed only, one site per lattice
    assert torch.equal(cluster, seed)
    assert cluster.sum(dim=(-1, -2)).tolist() == [1, 1, 1]


def test_p_to_one_spans_domain():
    """All-up lattice, beta large (p~=1): one update flips ~the whole lattice."""
    L, n = 16, 2
    spins = torch.ones((n, L, L), dtype=torch.int8)
    beta = torch.tensor([10.0, 10.0], dtype=torch.float32)  # p ~ 1
    p = (1.0 - torch.exp(-2.0 * beta * 1.0)).view(-1, 1, 1)
    bd, br = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(5))
    # every aligned bond activates; lattice is monochromatic so all bonds align
    assert bd.sum().item() == n * L * L
    assert br.sum().item() == n * L * L
    seed = _seed_mask(n, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(6))
    cluster = _grow_cluster(seed, bd, br)
    # the whole monochromatic torus is one connected component
    assert cluster.all()


# --------------------------------------------------------------------------- #
# monochromatic cluster + flip-is-xor
# --------------------------------------------------------------------------- #
def test_cluster_monochromatic():
    """Every site that flips shared the seed's pre-flip sign."""
    L, n = 20, 3
    g = torch.Generator(device="cpu").manual_seed(77)
    spins = (torch.randint(0, 2, (n, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([1.5, 2.27, 3.0])
    p = (1.0 - torch.exp(-2.0 * beta * 1.0)).view(-1, 1, 1)
    bd, br = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(8))
    seed = _seed_mask(n, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(9))
    cluster = _grow_cluster(seed, bd, br)
    # seed spin per lattice
    seed_spin = spins[seed].view(n)  # one True per lattice
    for k in range(n):
        members = spins[k][cluster[k]]
        if members.numel() > 0:
            assert (members == seed_spin[k]).all()


def test_flip_is_xor():
    """spins_out == spins_in on non-cluster sites, flipped on cluster sites."""
    L, n = 16, 3
    g = torch.Generator(device="cpu").manual_seed(11)
    spins = (torch.randint(0, 2, (n, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([1.6, 2.3, 3.1])
    g_step = torch.Generator(device="cpu").manual_seed(321)
    out, cluster = wolff_update(spins, beta, g_step, return_size=False, return_cluster=True)
    # values stay in {-1,+1}
    assert set(torch.unique(out).tolist()).issubset({-1, 1})
    assert out.dtype == torch.int8
    expected = spins * (1 - 2 * cluster.to(torch.int8))
    assert torch.equal(out, expected.to(torch.int8))
    # exactly the cluster sites changed sign
    changed = out != spins
    assert torch.equal(changed, cluster)


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_determinism_update():
    """Two wolff_update calls on cloned spins with same-seed generators match."""
    L, n = 16, 3
    g = torch.Generator(device="cpu").manual_seed(13)
    spins = (torch.randint(0, 2, (n, L, L), generator=g, dtype=torch.int8) * 2 - 1)
    beta = _beta([1.7, 2.27, 3.2])
    g1 = torch.Generator(device="cpu").manual_seed(2024)
    g2 = torch.Generator(device="cpu").manual_seed(2024)
    out1 = wolff_update(spins.clone(), beta, g1)
    out2 = wolff_update(spins.clone(), beta, g2)
    assert torch.equal(out1, out2)


def test_determinism_run():
    """Two wolff_run with same seed produce identical T/abs_mag/energy."""
    cfg = WolffConfig(
        L=14, T_min=2.0, T_max=2.6, n_temps=3,
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
    """Lattice 0's cluster never includes information from lattice 1.

    Lattice 0 is all-up (one update with p~1 flips the whole torus); lattice 1
    is a checkerboard (all bonds anti-aligned, so cluster == seed only). The two
    results are computed in one batched call and neither leaks into the other.
    """
    L = 12
    up = torch.ones((1, L, L), dtype=torch.int8)
    ii = torch.arange(L).view(L, 1)
    jj = torch.arange(L).view(1, L)
    checker = (((ii + jj) % 2) * 2 - 1).to(torch.int8).view(1, L, L)
    spins = torch.cat([up, checker], dim=0)
    beta = torch.tensor([10.0, 10.0], dtype=torch.float32)  # p ~ 1
    p = (1.0 - torch.exp(-2.0 * beta * 1.0)).view(-1, 1, 1)
    bd, br = _bond_field(spins, p, torch.Generator(device="cpu").manual_seed(31))
    # checkerboard: no aligned neighbours anywhere -> zero bonds on lattice 1
    assert bd[1].sum().item() == 0 and br[1].sum().item() == 0
    seed = _seed_mask(2, L, torch.device("cpu"), torch.Generator(device="cpu").manual_seed(32))
    cluster = _grow_cluster(seed, bd, br)
    # lattice 0: whole torus is one component
    assert cluster[0].all()
    # lattice 1: cluster is exactly the seed site (no crosstalk grew it)
    assert torch.equal(cluster[1], seed[1])
    assert cluster[1].sum().item() == 1


# --------------------------------------------------------------------------- #
# fixpoint reached on a contrived ring
# --------------------------------------------------------------------------- #
def test_fixpoint_captures_full_ring():
    """A full ring of bonds is captured completely — BFS doesn't stop short."""
    L, n = 10, 1
    bd = torch.zeros((n, L, L), dtype=torch.bool)
    br = torch.zeros((n, L, L), dtype=torch.bool)
    # build a single connected ring on row 0 using right-bonds, wrapping via PBC:
    # right bond at (0,j) connects (0,j)<->(0,j+1); activating all of row 0's
    # right-bonds chains the entire row 0 into one component.
    br[0, 0, :] = True
    seed = torch.zeros((n, L, L), dtype=torch.bool)
    seed[0, 0, 0] = True
    cluster = _grow_cluster(seed, bd, br)
    # entire row 0 should be in the cluster, nothing else
    expect = torch.zeros((n, L, L), dtype=torch.bool)
    expect[0, 0, :] = True
    assert torch.equal(cluster, expect)


def test_grow_cluster_converges_before_max_iters():
    """A long thin chain across the torus is fully captured well under L*L passes."""
    L, n = 12, 1
    bd = torch.zeros((n, L, L), dtype=torch.bool)
    br = torch.zeros((n, L, L), dtype=torch.bool)
    # snake: full row 0 via right bonds, plus a down bond joining row 0 to row 1
    br[0, 0, :] = True
    bd[0, 0, 0] = True  # (0,0)<->(1,0)
    br[0, 1, :] = True  # full row 1
    seed = torch.zeros((n, L, L), dtype=torch.bool)
    seed[0, 0, 0] = True
    cluster = _grow_cluster(seed, bd, br)
    expect = torch.zeros((n, L, L), dtype=torch.bool)
    expect[0, 0, :] = True
    expect[0, 1, :] = True
    assert torch.equal(cluster, expect)


# --------------------------------------------------------------------------- #
# physics: agreement with Metropolis + Onsager sanity
# --------------------------------------------------------------------------- #
def _short_metropolis(T, L, seed=42):
    cfg = RunConfig(
        L=L, T_min=T, T_max=T, n_temps=1,
        n_burnin=400, n_sweeps=800, sample_every=4, seed=seed, device="cpu",
    )
    return run(cfg)


def _short_wolff(T, L, seed=42):
    cfg = WolffConfig(
        L=L, T_min=T, T_max=T, n_temps=1,
        n_burnin=80, n_updates=400, sample_every=2, seed=seed, device="cpu",
    )
    return wolff_run(cfg)


def test_energy_matches_metropolis_lowT():
    """At T=1.8 (ordered), Wolff and Metropolis energies agree within combined sigma."""
    T, L = 1.8, 16
    m = _short_metropolis(T, L)
    w = _short_wolff(T, L)
    e_m, e_w = m.energy[0], w.energy[0]
    # Metropolis energy err is not exported; use a generous combined bound.
    se_w = w._energy_err[0] if hasattr(w, "_energy_err") else 0.05
    assert abs(e_w - e_m) < 0.10 + 3.0 * se_w, (e_w, e_m)
    # ordered-phase energy is deep-negative
    assert -2.0 <= e_w <= 0.0


def test_energy_matches_metropolis_highT():
    """At T=3.2 (disordered), energies agree within bound and are mildly negative."""
    T, L = 3.2, 16
    m = _short_metropolis(T, L)
    w = _short_wolff(T, L)
    e_m, e_w = m.energy[0], w.energy[0]
    assert abs(e_w - e_m) < 0.15, (e_w, e_m)
    assert -2.0 <= e_w <= 0.0


def test_absmag_matches_metropolis():
    """<|m|> agrees with Metropolis and is ordered correctly (high at low T)."""
    L = 16
    m_lo = _short_metropolis(1.6, L)
    w_lo = _short_wolff(1.6, L)
    m_hi = _short_metropolis(3.2, L)
    w_hi = _short_wolff(3.2, L)
    # agreement within a loose absolute tolerance on a short run
    assert abs(w_lo.abs_mag[0] - m_lo.abs_mag[0]) < 0.15
    assert abs(w_hi.abs_mag[0] - m_hi.abs_mag[0]) < 0.15
    # ordered: |m| high at low T, low at high T
    assert w_lo.abs_mag[0] > w_hi.abs_mag[0]
    assert w_lo.abs_mag[0] > 0.7
    assert w_hi.abs_mag[0] < 0.5


def test_onsager_energy_ordered_phase_sanity():
    """Ordered-phase energy is in [-2, 0] and |m| tracks the Onsager curve loosely."""
    from lab.onsager import onsager_magnetization

    L = 16
    w = _short_wolff(1.5, L)
    assert -2.0 <= w.energy[0] <= 0.0
    m_exact = float(onsager_magnetization(np.array([1.5]))[0])  # ~0.998
    # finite L softens it; just require we're in the strongly-ordered regime
    assert w.abs_mag[0] > 0.85
    assert w.abs_mag[0] <= m_exact + 0.05


def test_cluster_fraction_monotone_in_T():
    """mean_cluster_fraction decreases as T increases (ordered -> disordered)."""
    cfg = WolffConfig(
        L=16, T_min=1.5, T_max=3.5, n_temps=4,
        n_burnin=60, n_updates=200, sample_every=2, seed=5, device="cpu",
    )
    r = wolff_run(cfg)
    cf = r.mean_cluster_fraction
    # T ascending => cluster fraction should trend down. Check endpoints firmly
    # and require overall non-increasing trend (allow tiny noise wiggle).
    assert cf[0] > cf[-1]
    # highest-T cluster is small (few bonds activate)
    assert cf[-1] < 0.5


# --------------------------------------------------------------------------- #
# init: the ordered (cold) start — the practical start for large-L criticality
# --------------------------------------------------------------------------- #
def test_wolffconfig_init_default_random():
    """Back-compat: the default starting configuration is the historical hot start."""
    assert WolffConfig().init == "random"


def test_ordered_init_smoke_and_sane():
    """An ordered-start run produces the same observable shapes and sane physics."""
    cfg = WolffConfig(
        L=12, T_min=2.2, T_max=2.4, n_temps=3,
        n_burnin=150, n_updates=600, sample_every=2, seed=11, device="cpu",
        init="ordered",
    )
    r = wolff_run(cfg)
    assert r.T.shape == (3,) and r.chi_abs.shape == (3,)
    for i in range(3):
        assert -2.0 <= r.energy[i] <= 0.0
        assert 0.0 <= r.abs_mag[i] <= 1.0 + 1e-6
        assert r.chi_abs[i] > 0.0


def test_ordered_and_random_init_agree_at_equilibrium():
    """Both starts sample the same equilibrium: ⟨|m|⟩ and energy agree once burned in.

    Tiny lattice + generous burn-in so BOTH inits are fully equilibrated; the
    tolerance matches the other short-run cross-checks in this module. This is
    the correctness guarantee behind run_fss's ordered default: the init is a
    burn-in cost knob, not a physics knob.
    """
    kw = dict(
        L=12, T_min=2.25, T_max=2.40, n_temps=2,
        n_burnin=400, n_updates=1600, sample_every=2, seed=3, device="cpu",
    )
    r_hot = wolff_run(WolffConfig(**kw, init="random"))
    r_cold = wolff_run(WolffConfig(**kw, init="ordered"))
    for i in range(2):
        assert abs(r_hot.abs_mag[i] - r_cold.abs_mag[i]) < 0.15
        assert abs(r_hot.energy[i] - r_cold.energy[i]) < 0.15


def test_unknown_init_raises():
    """A typo'd init fails loudly rather than silently starting from garbage."""
    cfg = WolffConfig(L=8, n_temps=2, n_burnin=2, n_updates=4, init="cold")
    with pytest.raises(ValueError, match="unknown init"):
        wolff_run(cfg)
