"""M12 3D Edwards–Anderson spin glass — engine correctness, parallel tempering, crossing.

Two layers, matching the house style (cf. ``test_wolff3d.py`` + ``test_m11.py``):

* **NumPy/stdlib reducers** (``pair_crossing`` / ``binder_crossings`` / ``locate_tsg`` /
  ``to_report``) are exercised against hand-built Binder curves with a KNOWN crossing —
  no torch, no engine. These are what ``check_m12`` re-derives.
* **The torch engine** runs on ``device="cpu"`` with tiny lattices (L≤4) and short runs so
  the whole module finishes in a few seconds. The load-bearing facts are pinned exactly:
  the J-weighted neighbour sum and total energy match a brute-force bond sum; parallel-
  tempering swaps are pure permutations with the exact Metropolis-in-β acceptance in the
  forced-accept / forced-reject limits; and — the detailed-balance check — turning
  parallel tempering on vs off does not change the equilibrium energy on a small lattice
  both updaters can equilibrate.
"""
import numpy as np
import torch

from lab.spin_glass3d import (
    SpinGlass3DConfig,
    SpinGlass3DResult,
    run,
    _checkerboard_masks_3d,
    _weighted_neighbor_sum_3d,
    _total_energy_3d,
    _pt_swap_round,
)
from lab.m12 import (
    pair_crossing,
    binder_crossings,
    locate_tsg,
    run_m12,
    to_report,
    M12Result,
    T_SG_BENCHMARK,
    CROSSING_TOL,
)


# ─────────────────────────── stdlib reducers: the crossing ────────────────────────────
def _synthetic_binder(T, Ls, t_sg=0.95):
    """g_L(t) that all cross cleanly at ``t_sg``; steeper slope for larger L."""
    return {L: [0.5 + (t_sg - t) * (0.4 + 0.15 * L) for t in T] for L in Ls}


def test_pair_crossing_clean():
    T = [0.6, 0.8, 0.95, 1.1, 1.3]
    b = _synthetic_binder(T, [4, 8])
    t = pair_crossing(T, b[4], b[8])
    assert t is not None and abs(t - 0.95) < 1e-6


def test_pair_crossing_none_when_parallel():
    # Two curves that never separate (identical) → no sign change → None.
    T = [0.6, 0.9, 1.2]
    flat = [0.3, 0.3, 0.3]
    assert pair_crossing(T, flat, flat) is None


def test_binder_crossings_all_pairs():
    T = [0.6, 0.8, 0.95, 1.1, 1.3]
    b = _synthetic_binder(T, [4, 6, 8])
    pairs = binder_crossings(T, b)
    assert len(pairs) == 3                       # (4,6),(4,8),(6,8)
    for p in pairs:
        assert abs(p["T"] - 0.95) < 1e-6
        assert p["L1"] < p["L2"]


def test_locate_tsg_uses_largest_pair_and_handles_unsorted():
    # Arrays arrive UNSORTED in T; the internal argsort must still read the crossing.
    T = [1.3, 0.6, 0.95, 0.8, 1.1]
    b = {str(L): [0.5 + (0.95 - t) * (0.4 + 0.15 * L) for t in T] for L in (4, 6, 8)}
    crossing_T, pairs, mean_T = locate_tsg(T, b)
    assert abs(crossing_T - 0.95) < 1e-6
    assert abs(mean_T - 0.95) < 1e-6
    assert len(pairs) == 3


def test_locate_tsg_none_when_no_crossing():
    T = [0.6, 0.9, 1.2]
    flat = {4: [0.3, 0.3, 0.3], 6: [0.3, 0.3, 0.3], 8: [0.3, 0.3, 0.3]}
    assert locate_tsg(T, flat) == (None, [], None)


# ─────────────────────────── to_report shape + honesty ────────────────────────────────
def _toy_m12_result(resolved=True):
    T = [0.6, 0.8, 0.95, 1.1, 1.3]
    Ls = [4, 6, 8]
    b = _synthetic_binder(T, Ls)
    ct = 0.95 if resolved else 0.40
    return M12Result(
        T=T,
        L_values=Ls,
        q_bin_centers=[-1.0, 0.0, 1.0],
        pq_ref=[[0.2, 0.6, 0.2]] * len(T),
        pq_ref_L=8,
        binder_by_L={str(L): b[L] for L in Ls},
        q2_by_L={str(L): [0.5, 0.4, 0.3, 0.2, 0.1] for L in Ls},
        q4_by_L={str(L): [0.3, 0.2, 0.15, 0.08, 0.03] for L in Ls},
        q_mean_by_L={str(L): [0.0, 0.01, 0.0, 0.02, 0.0] for L in Ls},
        energy_by_L={str(L): [-1.7, -1.6, -1.5, -1.45, -1.4] for L in Ls},
        swap_rate_by_L={str(L): [0.3, 0.32, 0.31, 0.30] for L in Ls},
        crossing_T=ct,
        crossing_pairs=[{"L1": 4, "L2": 6, "T": ct}, {"L1": 6, "L2": 8, "T": ct}],
        crossing_mean_T=ct,
        t_sg_benchmark=T_SG_BENCHMARK,
        tolerance=CROSSING_TOL,
        crossing_resolved=resolved,
        max_abs_q_mean=0.02,
        n_realizations=200,
        wall_seconds=123.0,
        config={"model": "edwards-anderson-3d"},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_m12_result(resolved=True))
    assert rep["experiment"] == "M12-spin-glass-3d"
    assert rep["T"] == [0.6, 0.8, 0.95, 1.1, 1.3]
    assert set(rep["binder_by_L"].keys()) == {"4", "6", "8"}
    assert len(rep["binder_by_L"]["8"]) == len(rep["T"])
    assert rep["crossing_T"] == 0.95
    assert rep["t_sg_benchmark"] == T_SG_BENCHMARK
    assert "status" not in rep                    # resolved → not a null
    assert "Binder cumulant crossing" in rep["headline"]


def test_to_report_unresolved_is_honest_null():
    rep = to_report(_toy_m12_result(resolved=False))
    assert rep["crossing_resolved"] is False
    assert rep["status"] == "null"                # honest failed-calibration grey leaf
    assert "calibration null" in rep["headline"]


# ─────────────────────────── engine: config + smoke ───────────────────────────────────
def test_config_defaults():
    cfg = SpinGlass3DConfig()
    assert cfg.T_min < T_SG_BENCHMARK < cfg.T_max   # the ladder straddles T_SG
    assert cfg.swap_every > 0
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


def test_odd_L_rejected():
    cfg = SpinGlass3DConfig(L=5, device="cpu")
    try:
        run(cfg)
        assert False, "odd L should raise"
    except ValueError:
        pass


def test_cpu_run_smoke():
    cfg = SpinGlass3DConfig(
        L=4, T_min=0.5, T_max=1.6, n_temps=6, n_realizations=4,
        n_burnin=40, n_sweeps=120, sample_every=6, swap_every=5, seed=1, device="cpu",
    )
    r = run(cfg)
    assert isinstance(r, SpinGlass3DResult)
    assert r.T.shape == (6,)
    for arr in (r.q2_mean, r.q4_mean, r.q_abs_mean, r.q_mean, r.binder, r.energy):
        assert arr.shape == (6,)
    assert r.swap_rate.shape == (5,)                # n_temps - 1 gaps
    assert (r.swap_rate >= 0).all() and (r.swap_rate <= 1.0 + 1e-9).all()
    # ⟨q²⟩ ∈ [0,1]; overlap symmetric (|⟨q⟩| small); P(q) normalised per T.
    assert (r.q2_mean >= 0).all() and (r.q2_mean <= 1.0 + 1e-6).all()
    assert float(np.max(np.abs(r.q_mean))) < 0.3
    bin_w = r.q_bin_edges[1] - r.q_bin_edges[0]
    assert abs(float(r.pq[0].sum()) * bin_w - 1.0) < 1e-5
    # energy per spin on a 6-coordinated ±J lattice lives in [-3, 3]
    assert (r.energy >= -3.001).all() and (r.energy <= 3.001).all()
    j = r.to_json()
    assert j["config"]["L"] == 4 and len(j["T"]) == 6


def test_determinism_run():
    cfg = SpinGlass3DConfig(
        L=4, T_min=0.5, T_max=1.6, n_temps=5, n_realizations=3,
        n_burnin=20, n_sweeps=60, sample_every=6, swap_every=5, seed=99, device="cpu",
    )
    r1, r2 = run(cfg), run(cfg)
    assert np.array_equal(r1.q2_mean, r2.q2_mean)
    assert np.array_equal(r1.binder, r2.binder)
    assert np.array_equal(r1.energy, r2.energy)


def test_q2_broadens_as_T_falls():
    """[⟨q²⟩] grows as T → 0 — even the 3D glass broadens; a sign/bookkeeping bug wouldn't."""
    cfg = SpinGlass3DConfig(
        L=4, T_min=0.5, T_max=1.6, n_temps=6, n_realizations=8,
        n_burnin=120, n_sweeps=400, sample_every=5, swap_every=5, seed=3, device="cpu",
    )
    r = run(cfg)
    order = np.argsort(r.T)
    q2_sorted = r.q2_mean[order]
    assert q2_sorted[0] > q2_sorted[-1] + 0.05      # cold ⟨q²⟩ clearly exceeds hot


# ─────────────────────────── the load-bearing bond bookkeeping ─────────────────────────
def _brute_field(spins, Jx, Jy, Jz):
    """Explicit per-site Σ_j J_ij s_j on a single L³ lattice (numpy loops)."""
    L = spins.shape[0]
    out = np.zeros((L, L, L))
    for x in range(L):
        for y in range(L):
            for z in range(L):
                out[x, y, z] = (
                    Jx[x, y, z] * spins[(x + 1) % L, y, z]
                    + Jx[(x - 1) % L, y, z] * spins[(x - 1) % L, y, z]
                    + Jy[x, y, z] * spins[x, (y + 1) % L, z]
                    + Jy[x, (y - 1) % L, z] * spins[x, (y - 1) % L, z]
                    + Jz[x, y, z] * spins[x, y, (z + 1) % L]
                    + Jz[x, y, (z - 1) % L] * spins[x, y, (z - 1) % L]
                )
    return out


def test_weighted_neighbor_sum_matches_bruteforce():
    """The J-weighted neighbour sum equals an explicit bond sum — the −axis bonds come
    from the ROLLED coupling tensors. This is the exact fact the 2D engine verified,
    lifted to 3D; getting it wrong silently corrupts every energy and overlap."""
    L = 4
    g = torch.Generator(device="cpu").manual_seed(7)
    spins = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    Jx = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    Jy = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    Jz = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    # Engine tensors carry replica/temperature batch axes; use singletons here.
    field = _weighted_neighbor_sum_3d(
        spins.view(1, 1, 1, L, L, L), Jx.view(1, 1, 1, L, L, L),
        Jy.view(1, 1, 1, L, L, L), Jz.view(1, 1, 1, L, L, L),
    ).view(L, L, L).numpy()
    brute = _brute_field(spins.numpy(), Jx.numpy(), Jy.numpy(), Jz.numpy())
    assert np.allclose(field, brute)


def test_total_energy_matches_bruteforce_bond_sum():
    """E = −½ Σ_i s_i(Σ_j J_ij s_j) equals −Σ_bonds J_ij s_i s_j (each bond once)."""
    L = 4
    g = torch.Generator(device="cpu").manual_seed(21)
    spins = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    Jx = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    Jy = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    Jz = (torch.randint(0, 2, (L, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    s, jx, jy, jz = (a.numpy() for a in (spins, Jx, Jy, Jz))
    bond_e = 0.0
    for x in range(L):
        for y in range(L):
            for z in range(L):
                bond_e += jx[x, y, z] * s[x, y, z] * s[(x + 1) % L, y, z]
                bond_e += jy[x, y, z] * s[x, y, z] * s[x, (y + 1) % L, z]
                bond_e += jz[x, y, z] * s[x, y, z] * s[x, y, (z + 1) % L]
    brute_total = -bond_e
    engine_total = float(_total_energy_3d(
        spins.view(1, 1, 1, L, L, L), Jx.view(1, 1, 1, L, L, L),
        Jy.view(1, 1, 1, L, L, L), Jz.view(1, 1, 1, L, L, L),
    ).item())
    assert abs(engine_total - brute_total) < 1e-4


# ─────────────────────────── parallel tempering: the make-or-break piece ───────────────
def _two_rung(spins0, spins1, e0, e1, beta0, beta1):
    """Assemble a (R=1, 2 replicas, M=2) batch from two explicit L³ configs + energies."""
    L = spins0.shape[-1]
    spins = torch.stack([spins0, spins1], dim=0).view(1, 1, 2, L, L, L)
    spins = spins.expand(1, 2, 2, L, L, L).contiguous()      # duplicate over the replica axis
    energies = torch.tensor([[[e0, e1], [e0, e1]]], dtype=torch.float32)  # (1,2,2)
    beta = torch.tensor([beta0, beta1], dtype=torch.float32)
    return spins, energies, beta


def test_pt_swap_forced_accept_exchanges_configs():
    """Cold rung holds a HIGH-energy config, hot rung a LOW-energy one → (β_t−β_{t+1})·
    (E_t−E_{t+1}) ≫ 0 → acceptance clamps to 1 → the configs are exchanged, deterministically."""
    L = 4
    up = torch.ones((L, L, L), dtype=torch.int8)
    down = -torch.ones((L, L, L), dtype=torch.int8)
    # rung0 colder (β0>β1) with high E; rung1 hotter with low E.
    spins, energies, beta = _two_rung(up, down, e0=10.0, e1=-10.0, beta0=2.0, beta1=1.0)
    rng = torch.Generator(device="cpu").manual_seed(0)
    frac = _pt_swap_round(spins, energies, beta, parity=0, rng=rng)
    assert frac[0].item() == 1.0
    assert torch.equal(spins[0, 0, 0], down)     # rung0 now holds the old rung1 config
    assert torch.equal(spins[0, 0, 1], up)       # rung1 now holds the old rung0 config
    assert energies[0, 0, 0].item() == -10.0 and energies[0, 0, 1].item() == 10.0


def test_pt_swap_forced_reject_leaves_configs():
    """Cold rung already holds the LOW-energy config → (β_t−β_{t+1})·(E_t−E_{t+1}) ≪ 0 →
    acceptance ≈ 0 → no swap, regardless of the random draw."""
    L = 4
    up = torch.ones((L, L, L), dtype=torch.int8)
    down = -torch.ones((L, L, L), dtype=torch.int8)
    spins, energies, beta = _two_rung(up, down, e0=-10.0, e1=10.0, beta0=2.0, beta1=1.0)
    before = spins.clone()
    rng = torch.Generator(device="cpu").manual_seed(0)
    frac = _pt_swap_round(spins, energies, beta, parity=0, rng=rng)
    assert frac[0].item() == 0.0
    assert torch.equal(spins, before)            # nothing moved


def test_pt_swap_conserves_spins():
    """A swap round only PERMUTES configurations among rungs — the batch spin count is
    invariant and values stay ±1 (it neither creates nor destroys spins)."""
    cfg_shape = (2, 2, 4, 4, 4, 4)               # (R,2,M,L,L,L)
    g = torch.Generator(device="cpu").manual_seed(5)
    spins = (torch.randint(0, 2, cfg_shape, generator=g, dtype=torch.int8) * 2 - 1)
    before_sum = spins.sum().item()
    energies = torch.randn(2, 2, 4, generator=g)
    beta = torch.tensor([2.0, 1.4, 1.0, 0.7], dtype=torch.float32)
    _pt_swap_round(spins, energies, beta, parity=0, rng=torch.Generator(device="cpu").manual_seed(6))
    _pt_swap_round(spins, energies, beta, parity=1, rng=torch.Generator(device="cpu").manual_seed(7))
    assert spins.sum().item() == before_sum
    assert set(torch.unique(spins).tolist()).issubset({-1, 1})


def test_parallel_tempering_preserves_equilibrium():
    """Detailed-balance check: on a small lattice both updaters equilibrate, so turning
    parallel tempering ON vs OFF must give the same equilibrium energy. PT changes the
    DYNAMICS (how fast the cold rungs decorrelate), not the sampled distribution — a
    swap-acceptance sign error would shift the energy."""
    base = dict(L=4, T_min=0.5, T_max=1.6, n_temps=6, n_realizations=10,
                n_burnin=200, n_sweeps=800, sample_every=5, seed=17, device="cpu")
    r_pt = run(SpinGlass3DConfig(swap_every=5, **base))
    r_no = run(SpinGlass3DConfig(swap_every=0, **base))
    # Energy per spin is a robust intensive observable; agree within Monte-Carlo noise.
    assert np.max(np.abs(r_pt.energy - r_no.energy)) < 0.12, (r_pt.energy, r_no.energy)


# ─────────────────────────── run_m12 integration (tiny) ────────────────────────────────
def test_run_m12_integration_tiny():
    """The full multi-L runner returns a check-ready result over ≥3 sizes on a shared
    ladder. Physics is not asserted (too noisy at this scale) — only the pipeline shape."""
    calls = []
    result = run_m12(
        L_values=(4, 6, 8), T_min=0.5, T_max=1.6, n_temps=6, n_realizations=3,
        n_sweeps=120, n_burnin=60, swap_every=5, seed=2, device="cpu",
        progress=lambda L, r: calls.append(L),
    )
    assert isinstance(result, M12Result)
    assert calls == [4, 6, 8]
    assert set(result.binder_by_L.keys()) == {"4", "6", "8"}
    assert len(result.T) == 6
    assert all(len(v) == 6 for v in result.binder_by_L.values())
    assert result.t_sg_benchmark == T_SG_BENCHMARK
    assert isinstance(result.crossing_resolved, bool)
    rep = to_report(result)
    assert rep["experiment"] == "M12-spin-glass-3d"
