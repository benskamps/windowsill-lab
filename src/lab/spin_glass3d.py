"""Batched 3D Edwards–Anderson spin glass with PARALLEL TEMPERING — the finite-T glass.

M12 is the payoff of the Phase-3 spin-glass line. M11 ran the **2D** ±J glass, which
sits at the lower critical dimension: its spin-glass transition is at T_c = 0, so the
only signature is P(q) broadening as T → 0 (no finite-T phase). **In three dimensions
the story changes** — the ±J Edwards–Anderson glass has a genuine *finite-temperature*
spin-glass transition at

    T_SG ≈ 0.95   (±J / bimodal disorder, simple-cubic, the modern MC benchmark)

detected not by any local order parameter (there is none — ⟨s_i⟩ = 0 by the ±J
symmetry) but by the **disorder-averaged Binder cumulant crossing**: curves g_L(T) for
several lattice sizes L intersect at a single temperature, and that intersection *is*
T_SG. Below it the larger lattice is more ordered (g rises toward 1); above it the
larger lattice is less ordered (g falls toward 0); at T_SG the cumulant is
scale-invariant, so every L agrees.

### The Hamiltonian and the observable (unchanged from 2D, one more axis)

    E = -Σ_⟨ij⟩ J_ij s_i s_j        (s_i = ±1, k_B = 1)

with each bond J_ij drawn once as ±1 (equal probability) and then **frozen**. The
frustration lives in the bond *signs*, not the geometry — the simple-cubic lattice is
bipartite, so the (x+y+z)-parity red/black checkerboard still updates each colour in
parallel exactly (a site's six neighbours all sit on the other colour, held fixed).

The order parameter is the **overlap** between two replicas α, β that share the *same*
bonds but run with independent spins:

    q = (1/N) Σ_i s_i^α s_i^β        ∈ [-1, 1]

Histogram q over the run → P(q) for one disorder realization; the physical object is the
**disorder average** over many bond realizations. The Binder cumulant is built from the
disorder-averaged overlap moments,

    g_L(T) = ½ ( 3 − [⟨q⁴⟩] / [⟨q²⟩]² ),

which → 0 in the paramagnet (q ≈ Gaussian at 0, ⟨q⁴⟩/⟨q²⟩² → 3) and → 1 deep in the
glass (double-δ P(q), ⟨q⁴⟩/⟨q²⟩² → 1), crossing scale-invariantly at T_SG.

### Why PARALLEL TEMPERING is the load-bearing correctness piece

⚠️ This is the make-or-break. M11 documented — and directly verified — that single-spin
checkerboard Metropolis **cannot equilibrate** the ±J glass below T ≈ 0.5–0.6: the
free-energy landscape is rugged, autocorrelation times explode, and the coldest points
fall into an under-equilibration *dip*. A naive single-spin sweep near T_SG produces a
**smeared, crossing-free g_L(T)** that can *look* finished while being silently wrong —
exactly M11's failure mode, now fatal because M12's entire claim is a crossing.

Parallel tempering (replica exchange) fixes this. We simulate, for each replica, the
**whole temperature ladder at once** (M copies at β_0 > β_1 > … > β_{M−1}) and, between
sweeps, propose swapping the configurations of *adjacent* ladder rungs with the exact
Metropolis-in-β acceptance

    A( t ↔ t+1 ) = min( 1, exp[ (β_t − β_{t+1}) (E_t − E_{t+1}) ] ).

A cold, stuck configuration can then ride *up* the ladder, decorrelate in the hot,
ergodic phase, and ride back down — so the cold rungs equilibrate in tractable time and
the crossing resolves. Swaps are attempted in the standard **even/odd** alternation so
no rung takes part in two swaps at once. Because we swap *configurations* (not the βs),
ladder rung t always holds a sample at temperature T[t] — measurement stays trivial.

### Batch layout

One pass simulates **(realizations × 2 replicas × M temperatures)** lattices together,
shaped ``(R, 2, M, L, L, L)``. Bonds are per-realization (broadcast across that
realization's 2 replicas and all M temperatures); spins are independent per lattice;
β varies only along the M axis. The overlap is formed between the two replicas of the
*same* (realization, temperature) rung. One engine call is one lattice size L; the M12
runner calls it once per L on a **shared T ladder** and reads off the multi-L crossing.

This engine is device-agnostic torch (``--device cpu`` proves the code end-to-end; the
full disorder-averaged sweep that resolves the crossing is a GPU run). It is the 3D,
parallel-tempered sibling of ``spin_glass.py`` (2D, single-spin Metropolis).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch


@dataclass
class SpinGlass3DConfig:
    L: int = 6
    T_min: float = 0.5             # below T_SG ≈ 0.95 — the ladder must straddle it
    T_max: float = 1.6             # above T_SG — the ergodic end PT decorrelates in
    n_temps: int = 12
    n_realizations: int = 24       # quenched disorder samples to average over
    n_burnin: int = 4000           # equilibration sweeps (with PT swaps interleaved)
    n_sweeps: int = 8000           # measurement sweeps
    sample_every: int = 10
    swap_every: int = 5            # attempt a PT even/odd swap round every N sweeps
    n_qbins: int = 41              # odd → a bin centred on q = 0; histogram on [-1, 1]
    seed: int = 42
    device: str = "cuda"

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class SpinGlass3DResult:
    config: SpinGlass3DConfig
    T: np.ndarray                  # (n_temps,)
    q_bin_edges: np.ndarray        # (n_qbins+1,)
    q_bin_centers: np.ndarray      # (n_qbins,)
    pq: np.ndarray                 # disorder-averaged P(q), (n_temps, n_qbins)
    q2_mean: np.ndarray            # [⟨q²⟩] disorder-averaged, (n_temps,)
    q4_mean: np.ndarray            # [⟨q⁴⟩] disorder-averaged, (n_temps,)
    q_abs_mean: np.ndarray         # [⟨|q|⟩] disorder-averaged, (n_temps,)
    q_mean: np.ndarray             # [⟨q⟩] disorder-averaged, (n_temps,) — ≈0 by symmetry
    binder: np.ndarray             # g_L = ½(3 − [⟨q⁴⟩]/[⟨q²⟩]²), (n_temps,)
    energy: np.ndarray             # mean energy per spin, (n_temps,)
    swap_rate: np.ndarray          # PT acceptance per adjacent T-gap, (n_temps-1,)
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "q_bin_centers": self.q_bin_centers.tolist(),
            "q_bin_edges": self.q_bin_edges.tolist(),
            "pq": self.pq.tolist(),
            "q2_mean": self.q2_mean.tolist(),
            "q4_mean": self.q4_mean.tolist(),
            "q_abs_mean": self.q_abs_mean.tolist(),
            "q_mean": self.q_mean.tolist(),
            "binder": self.binder.tolist(),
            "energy": self.energy.tolist(),
            "swap_rate": self.swap_rate.tolist(),
            "wall_seconds": self.wall_seconds,
        }


def _checkerboard_masks_3d(L: int, device: torch.device):
    """The two simple-cubic sublattice masks, shape ``(L, L, L)`` (broadcast over batch).

    Colour each site by the parity of ``(x+y+z)``. On a periodic simple-cubic lattice
    every site's six nearest neighbours have the opposite parity, so all same-colour
    sites update in parallel exactly — their ΔE depends only on the *other* colour,
    held fixed. Random bonds don't break this: it's the lattice graph that is
    2-colourable, and frustration lives in the bond signs. Needs even L so the
    checkerboard wraps across the periodic seam.
    """
    ix = torch.arange(L, device=device).view(L, 1, 1)
    iy = torch.arange(L, device=device).view(1, L, 1)
    iz = torch.arange(L, device=device).view(1, 1, L)
    even = ((ix + iy + iz) % 2 == 0)
    return even, ~even


def _weighted_neighbor_sum_3d(spins, Jx, Jy, Jz):
    """Σ_j J_ij s_j over the six neighbours, each weighted by its bond coupling.

    ``Jx[...,x,y,z]`` couples site (x,y,z) to its +x neighbour ((x+1)%L, y, z); ``Jy``
    to +y ((x, (y+1)%L, z)); ``Jz`` to +z ((x, y, (z+1)%L)). A site's six contributions:

    * +x ((x+1,y,z)): ``Jx[x,y,z]   · s[x+1,y,z]``
    * −x ((x−1,y,z)): ``Jx[x−1,y,z] · s[x−1,y,z]``  — the −x site's +x bond → ``roll(Jx,+1,x)``
    * +y / −y, +z / −z: the same pattern on axes −2 and −1.

    Getting the −axis bonds from the *rolled* coupling tensors (not from ``Jx``/``Jy``/
    ``Jz`` at the site itself) is the load-bearing bookkeeping — the exact 3D lift of the
    2D engine's verified rule. Spatial axes are the last three (x=−3, y=−2, z=−1); rolls
    wrap (periodic BC). ``Jx``/``Jy``/``Jz`` broadcast against ``spins`` (bonds are
    shared across the replica and temperature axes).
    """
    xp = Jx * torch.roll(spins, -1, dims=-3)
    xm = torch.roll(Jx, 1, dims=-3) * torch.roll(spins, 1, dims=-3)
    yp = Jy * torch.roll(spins, -1, dims=-2)
    ym = torch.roll(Jy, 1, dims=-2) * torch.roll(spins, 1, dims=-2)
    zp = Jz * torch.roll(spins, -1, dims=-1)
    zm = torch.roll(Jz, 1, dims=-1) * torch.roll(spins, 1, dims=-1)
    return xp + xm + yp + ym + zp + zm


def _half_sweep_3d(spins, beta, Jx, Jy, Jz, mask, rng):
    """Metropolis flip of one checkerboard colour with the J-weighted local field.

    The energy that depends on s_i is −s_i·Σ_j J_ij s_j, so flipping s_i costs
    ΔE = 2·s_i·(Σ_j J_ij s_j). The masked colour's six neighbours all lie on the other
    colour (held fixed), so the whole colour updates in parallel exactly. ``beta`` is
    shaped to broadcast over ``(R, 2, M, L, L, L)`` (it varies only on the M axis).
    """
    field = _weighted_neighbor_sum_3d(spins, Jx, Jy, Jz)
    dE = 2.0 * spins.float() * field.float()
    prob = torch.exp(-beta * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, -spins, spins)


def _total_energy_3d(spins, Jx, Jy, Jz):
    """Total configuration energy E = −½ Σ_i s_i (Σ_j J_ij s_j), shape ``(R, 2, M)``.

    The ½ stops each bond being counted from both endpoints. This is the *extensive*
    energy the parallel-tempering swap criterion needs (the Boltzmann weight is
    exp(−β·E_total)), summed over the three spatial axes only.
    """
    field = _weighted_neighbor_sum_3d(spins, Jx, Jy, Jz)
    return -0.5 * (spins.float() * field.float()).sum(dim=(-1, -2, -3))


def _pt_swap_round(spins, energies, beta_ladder, parity, rng):
    """One even/odd parallel-tempering swap pass along the temperature (M) axis.

    ``spins`` is ``(R, 2, M, L, L, L)``; ``energies`` is ``(R, 2, M)`` total energy;
    ``beta_ladder`` is ``(M,)`` inverse temperatures (descending in β = ascending in T).
    ``parity`` 0 attempts pairs (0,1),(2,3),…; 1 attempts (1,2),(3,4),… — the standard
    alternation so no rung is in two swaps at once.

    For each adjacent pair (t, t+1) the configurations are exchanged with probability
    ``min(1, exp[(β_t − β_{t+1})(E_t − E_{t+1})])`` — the exact Metropolis-in-β rule
    that keeps the joint distribution ∝ Π_t exp(−β_t E_t) invariant. Swapping *configs*
    (not βs) means rung t stays pinned to T[t]. Energies are exchanged in lockstep so
    later passes stay consistent without recomputing. Returns the per-pair acceptance
    fraction over the batch (a diagnostic; a healthy ladder swaps a few-tens of %).
    """
    R, two, M = energies.shape
    device = spins.device
    swap_frac = torch.zeros(M - 1, device=device)
    for t in range(parity, M - 1, 2):
        dbeta = beta_ladder[t] - beta_ladder[t + 1]        # > 0 (β descends with T)
        dE = energies[:, :, t] - energies[:, :, t + 1]      # (R, 2)
        acc = torch.exp(dbeta * dE).clamp(max=1.0)          # (R, 2)
        u = torch.rand(acc.shape, generator=rng, device=device)
        do = u < acc                                        # (R, 2) bool
        swap_frac[t] = do.float().mean()
        m = do.view(R, two, 1, 1, 1)
        a = spins[:, :, t].clone()
        b = spins[:, :, t + 1].clone()
        spins[:, :, t] = torch.where(m, b, a)
        spins[:, :, t + 1] = torch.where(m, a, b)
        ea = energies[:, :, t].clone()
        eb = energies[:, :, t + 1].clone()
        energies[:, :, t] = torch.where(do, eb, ea)
        energies[:, :, t + 1] = torch.where(do, ea, eb)
    return swap_frac


def run(cfg: SpinGlass3DConfig) -> SpinGlass3DResult:
    """Run a batched 3D ±J EA sweep with parallel tempering; build [P(q)] and g_L(T).

    Simulates ``(n_realizations × 2 replicas × n_temps)`` lattices in one pass. Each
    realization has its own frozen ±J bonds, shared by its two replicas and every ladder
    rung; the two replicas of a (realization, temperature) start from independent spins
    and form the overlap q = (1/N) Σ_i s_i^α s_i^β each sample. Parallel-tempering swaps
    along the temperature axis (even/odd, every ``swap_every`` sweeps) let the cold rungs
    equilibrate. Returns the disorder-averaged P(q) per T, the overlap moments, and the
    **Binder cumulant g_L(T)** — the array whose multi-L crossing locates T_SG.
    """
    if cfg.L % 2 != 0:
        raise ValueError(f"L must be even for the 3D checkerboard (got {cfg.L})")

    device = torch.device(cfg.device)
    R, M, L = cfg.n_realizations, cfg.n_temps, cfg.L
    N = L * L * L

    g_bond = torch.Generator(device=device).manual_seed(cfg.seed)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed + 1)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 2)
    g_swap = torch.Generator(device=device).manual_seed(cfg.seed + 3)

    T = torch.linspace(cfg.T_min, cfg.T_max, M, device=device, dtype=torch.float32)
    beta_ladder = 1.0 / T                                    # (M,), descending in β
    # β broadcast over (R, 2, M, L, L, L): only the M (temperature) axis varies.
    beta = beta_ladder.view(1, 1, M, 1, 1, 1)

    # Quenched ±J bonds: one set per realization, SHARED across its 2 replicas and all
    # M temperatures. Shape (R, 1, 1, L, L, L) → broadcasts over the (2, M) axes.
    def _bonds():
        b = torch.randint(0, 2, (R, 1, 1, L, L, L), generator=g_bond,
                          device=device, dtype=torch.int8) * 2 - 1
        return b.float()

    Jx, Jy, Jz = _bonds(), _bonds(), _bonds()

    # Independent initial spins for every lattice (both replicas independent).
    spins = (torch.randint(0, 2, (R, 2, M, L, L, L), generator=g_init,
                           device=device, dtype=torch.int8) * 2 - 1)
    mask_a, mask_b = _checkerboard_masks_3d(L, device)

    def _sweep():
        nonlocal spins
        spins = _half_sweep_3d(spins, beta, Jx, Jy, Jz, mask_a, g_step)
        spins = _half_sweep_3d(spins, beta, Jx, Jy, Jz, mask_b, g_step)

    t0 = time.time()
    # ── Burn-in with interleaved parallel-tempering swaps ────────────────────────
    for s in range(cfg.n_burnin):
        _sweep()
        if cfg.swap_every > 0 and s % cfg.swap_every == 0:
            energies = _total_energy_3d(spins, Jx, Jy, Jz)
            _pt_swap_round(spins, energies, beta_ladder, s % 2, g_swap)

    # ── Measurement (swaps continue; overlap sampled at each rung's fixed T) ──────
    edges = torch.linspace(-1.0, 1.0, cfg.n_qbins + 1, device=device)
    pq_hist = torch.zeros(R, M, cfg.n_qbins, device=device)
    q2_acc = torch.zeros(R, M, device=device)
    q4_acc = torch.zeros(R, M, device=device)
    qabs_acc = torch.zeros(R, M, device=device)
    q_acc = torch.zeros(R, M, device=device)
    e_acc = torch.zeros(R, M, device=device)
    swap_acc = torch.zeros(M - 1, device=device)
    swap_attempts = torch.zeros(M - 1, device=device)   # per-gap, for an honest rate
    n_samp = 0

    for s in range(cfg.n_sweeps):
        _sweep()
        if cfg.swap_every > 0 and s % cfg.swap_every == 0:
            energies = _total_energy_3d(spins, Jx, Jy, Jz)
            parity = s % 2
            swap_acc += _pt_swap_round(spins, energies, beta_ladder, parity, g_swap)
            swap_attempts[parity:M - 1:2] += 1          # only this parity's gaps ran
        if s % cfg.sample_every == 0:
            sv = spins.float()                                 # (R, 2, M, L, L, L)
            # Overlap between the two replicas of each (realization, temperature).
            q = (sv[:, 0] * sv[:, 1]).mean(dim=(-1, -2, -3))    # (R, M) ∈ [-1, 1]
            q2_acc += q * q
            q4_acc += q ** 4
            qabs_acc += q.abs()
            q_acc += q
            idx = torch.bucketize(q, edges) - 1
            idx = idx.clamp(0, cfg.n_qbins - 1)                 # (R, M)
            pq_hist.scatter_add_(2, idx.unsqueeze(-1),
                                 torch.ones_like(idx, dtype=pq_hist.dtype).unsqueeze(-1))
            # Energy per spin, averaged over the two replicas.
            e = _total_energy_3d(spins, Jx, Jy, Jz) / N          # (R, 2, M)
            e_acc += e.mean(dim=1)                               # (R, M)
            n_samp += 1
    wall = time.time() - t0

    # Per-realization sample means, then DISORDER-AVERAGE over realizations (axis 0).
    q2_per = q2_acc / n_samp
    q4_per = q4_acc / n_samp
    qabs_per = qabs_acc / n_samp
    q_per = q_acc / n_samp
    e_per = e_acc / n_samp

    q2_mean = q2_per.mean(dim=0)                                # (M,)
    q4_mean = q4_per.mean(dim=0)
    qabs_mean = qabs_per.mean(dim=0)
    q_mean = q_per.mean(dim=0)
    energy = e_per.mean(dim=0)
    # Binder cumulant from the DISORDER-AVERAGED moments (the standard EA definition):
    # g_L = ½(3 − [⟨q⁴⟩]/[⟨q²⟩]²). Its multi-L crossing locates T_SG.
    binder = 0.5 * (3.0 - q4_mean / q2_mean.clamp_min(1e-12) ** 2)

    centers = 0.5 * (edges[:-1] + edges[1:])
    bin_w = float(edges[1] - edges[0])
    pq_density = pq_hist / (pq_hist.sum(dim=2, keepdim=True).clamp_min(1.0) * bin_w)
    pq_mean = pq_density.mean(dim=0)                            # (M, n_qbins)

    swap_rate = swap_acc / swap_attempts.clamp_min(1.0)        # (M-1,) per-gap acceptance

    return SpinGlass3DResult(
        config=cfg,
        T=T.cpu().numpy(),
        q_bin_edges=edges.cpu().numpy(),
        q_bin_centers=centers.cpu().numpy(),
        pq=pq_mean.cpu().numpy(),
        q2_mean=q2_mean.cpu().numpy(),
        q4_mean=q4_mean.cpu().numpy(),
        q_abs_mean=qabs_mean.cpu().numpy(),
        q_mean=q_mean.cpu().numpy(),
        binder=binder.cpu().numpy(),
        energy=energy.cpu().numpy(),
        swap_rate=swap_rate.cpu().numpy(),
        wall_seconds=wall,
    )
