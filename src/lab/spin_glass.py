"""Batched 2D Edwards–Anderson spin glass on GPU — quenched ±J disorder, overlap q.

M11 is the first Phase-3 rung and a different *kind* of model: the couplings are
**quenched random**. Each bond J_ij is drawn once (±1 with equal probability, the
±J / bimodal Edwards–Anderson model) and then **frozen** — the disorder is part of
the Hamiltonian, not the dynamics:

    E = -Σ_⟨ij⟩ J_ij s_i s_j            (s_i = ±1, k_B = 1)

The frustration lives in the bond *signs* (a plaquette whose four bonds multiply to
−1 cannot satisfy all four), not in the lattice geometry — the square lattice is
still bipartite, so the red/black checkerboard parallel Metropolis update is still
exact (a site's four neighbours all sit on the other colour, held fixed).

### The headline physics — 2D EA orders ONLY at T = 0

⚠️ In **two dimensions the EA spin glass sits at the lower critical dimension**:
its spin-glass transition is at **T_c = 0**. There is **no finite-temperature glass
phase** (true for both ±J and Gaussian disorder). So M11 is **not** a "find the
transition" milestone — the verification is the *expected approach to a T = 0
critical point*: the disorder-averaged overlap distribution **P(q) broadens** (its
width / ⟨q²⟩ grows) monotonically **as T is lowered**, sharpening toward the T = 0
order, but never developing a stable finite-T phase. The finite-T transition
(T_SG ≈ 0.95, Binder-cumulant crossing) is the **3D** case — that is M12, not this.

### The right observable — the overlap between two replicas

A spin glass has **no local order parameter** (⟨s_i⟩ = 0 by the ±J symmetry; the
order is hidden in correlations *between* configurations). The Edwards–Anderson
order parameter is the **overlap** of two independent replicas α, β that share the
*same bonds* but run with independent spins/RNG:

    q = (1/N) Σ_i s_i^α s_i^β        ∈ [-1, 1]

Histogramming q over the run gives P(q) **for one disorder realization**; the
physically meaningful object is the **disorder average** of P(q) over many bond
realizations (a single realization is sample-specific noise — the disorder average
is mandatory). At high T, P(q) is a narrow peak at q = 0; as T → 0 it broadens and
grows weight at large |q|, and is symmetric P(q) = P(−q) (the ±J / spin-inversion
symmetry).

### What this engine does NOT do (honesty up front)

Spin glasses are genuinely hard to equilibrate: autocorrelation times explode at
low T (rugged free-energy landscape). This engine runs **heavy single-spin
checkerboard Metropolis** with a long burn-in and reports an **equilibration
diagnostic** — the symmetry of the disorder-averaged P(q), |⟨q⟩| (which must be ≈ 0
by symmetry once equilibrated). It does **not** implement parallel tempering.

There is a concrete **equilibration floor** at **T ≈ 0.5–0.6** for L=16: below it,
single-spin Metropolis can no longer equilibrate the glass in tractable time, and
the coldest points fall into an *under-equilibration dip* where ⟨q²⟩ is suppressed
*below* the peak rather than continuing to grow (verified directly — even 4× the
burn-in does not lift the two coldest points out of the dip; that is the textbook
signature that single-spin dynamics is stuck, and the reason parallel tempering
exists). So M11 reports the broadening over the **trustworthy window above the
floor** (default T ≥ 0.6), where ⟨q²⟩ grows cleanly and monotonically (~25× from the
hot end to the floor) and the overlap stays symmetric. The **trend toward T = 0** is
the claim; the un-equilibrable T ≲ 0.5 tail is **not** — going colder needs parallel
tempering (the natural next step, see BACKLOG / M12).

### Batch layout

One GPU pass sweeps **(realizations × temperatures × 2 replicas)** in parallel.
Bonds are per-realization (shared across that realization's 2 replicas and all
temperatures); spins are independent per replica. The overlap is formed between the
two replicas of the *same* (realization, temperature).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch


@dataclass
class SpinGlassConfig:
    L: int = 16
    T_min: float = 0.2
    T_max: float = 2.0
    n_temps: int = 16
    n_realizations: int = 64       # quenched disorder samples to average P(q) over
    n_burnin: int = 20000
    n_sweeps: int = 40000
    sample_every: int = 20
    n_qbins: int = 41              # odd → a bin centred on q = 0; histogram on [-1, 1]
    seed: int = 42
    device: str = "cuda"

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class SpinGlassResult:
    config: SpinGlassConfig
    T: np.ndarray                  # (n_temps,)
    q_bin_edges: np.ndarray        # (n_qbins+1,)
    q_bin_centers: np.ndarray      # (n_qbins,)
    pq: np.ndarray                 # disorder-averaged P(q), (n_temps, n_qbins)
    q2_mean: np.ndarray            # ⟨q²⟩ disorder-averaged, (n_temps,) — the broadening signal
    q4_mean: np.ndarray            # ⟨q⁴⟩ disorder-averaged, (n_temps,)
    q_abs_mean: np.ndarray         # ⟨|q|⟩ disorder-averaged, (n_temps,)
    q_mean: np.ndarray             # ⟨q⟩ disorder-averaged, (n_temps,) — ≈0 by symmetry (equil. diagnostic)
    binder: np.ndarray             # g = ½(3 − ⟨q⁴⟩/⟨q²⟩²), (n_temps,)
    energy: np.ndarray             # mean energy per spin (replica/realization avg), (n_temps,)
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
            "wall_seconds": self.wall_seconds,
        }


def _checkerboard_masks(L: int, batch: int, device: torch.device):
    """The two bipartite sublattice masks, shape ``(batch, L, L)``.

    Random *bonds* don't break the lattice's bipartiteness — it's the lattice graph
    that's 2-colourable, and frustration lives in the bond signs — so the same
    red/black checkerboard the ferromagnet uses parallelises the EA update exactly.
    """
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    a = ((ix + iy) % 2 == 0).unsqueeze(0).expand(batch, L, L).contiguous()
    return a, ~a


def _weighted_neighbor_sum(spins: torch.Tensor, Jx: torch.Tensor, Jy: torch.Tensor) -> torch.Tensor:
    """Σ_j J_ij s_j over the four neighbours, each weighted by its bond coupling.

    ``Jx[...,i,j]`` couples site (i,j) to its RIGHT neighbour (i, j+1); ``Jy[...,i,j]``
    couples it to its DOWN neighbour (i+1, j). So a site's four contributions are:

    * right (i,j+1): ``Jx[i,j]   · s[i,j+1]``
    * left  (i,j-1): ``Jx[i,j-1] · s[i,j-1]``  — the *left* site's right-bond → ``roll(Jx, +1, x)``
    * down  (i+1,j): ``Jy[i,j]   · s[i+1,j]``
    * up    (i-1,j): ``Jy[i-1,j] · s[i-1,j]``  — the *up* site's down-bond → ``roll(Jy, +1, y)``

    Getting the left/up bonds from the *rolled* coupling tensors (not from ``Jx``/``Jy``
    at the site itself) is the load-bearing bookkeeping — verified against a
    brute-force bond sum. Rolls wrap (periodic BC). ``spins``/``Jx``/``Jy`` share shape
    ``(batch, L, L)``.
    """
    right = Jx * torch.roll(spins, -1, dims=-1)
    left = torch.roll(Jx, 1, dims=-1) * torch.roll(spins, 1, dims=-1)
    down = Jy * torch.roll(spins, -1, dims=-2)
    up = torch.roll(Jy, 1, dims=-2) * torch.roll(spins, 1, dims=-2)
    return right + left + down + up


def _half_sweep(spins, beta, Jx, Jy, mask, rng):
    """Metropolis flip of one checkerboard colour with the J-weighted local field.

    The energy that depends on s_i is −s_i·Σ_j J_ij s_j, so flipping s_i costs
    ΔE = 2·s_i·(Σ_j J_ij s_j). The masked colour's neighbours all lie on the other
    colour (held fixed), so the whole colour updates in parallel exactly — exactly
    as the ferromagnet, just with the bond-weighted neighbour sum. ``beta`` is shaped
    to broadcast over ``(batch, L, L)``.
    """
    field = _weighted_neighbor_sum(spins, Jx, Jy)           # Σ_j J_ij s_j
    dE = 2.0 * spins.float() * field.float()                # ΔE for flipping each site
    prob = torch.exp(-beta * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, -spins, spins)


def run(cfg: SpinGlassConfig) -> SpinGlassResult:
    """Run a batched 2D ±J Edwards–Anderson sweep and build the disorder-averaged P(q).

    Sweeps ``(n_realizations × n_temps × 2 replicas)`` lattices in one GPU pass. Each
    realization has its own frozen ±J bonds, shared by its two replicas and all
    temperatures; the two replicas of a (realization, temperature) start from
    independent spins and form the overlap q = (1/N) Σ_i s_i^α s_i^β each sample.
    Returns the disorder-averaged P(q) histogram per temperature plus ⟨q²⟩/⟨q⁴⟩/Binder
    — the broadening of P(q) as T → 0 is M11's signature (no finite-T transition; the
    2D EA glass orders only at T = 0).
    """
    device = torch.device(cfg.device)
    R, M, L = cfg.n_realizations, cfg.n_temps, cfg.L
    N = L * L
    # Two replicas per (realization, temperature). Leading batch axis is
    # B = R*M*2, laid out so reshape(R, M, 2, L, L) recovers the structure.
    B = R * M * 2

    g_bond = torch.Generator(device=device).manual_seed(cfg.seed)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed + 1)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 2)

    T = torch.linspace(cfg.T_min, cfg.T_max, M, device=device, dtype=torch.float32)
    # beta broadcast over (R, M, 2, L, L): only the M (temperature) axis varies.
    beta = (1.0 / T).view(1, M, 1, 1, 1).expand(R, M, 2, 1, 1).reshape(B, 1, 1)

    # Quenched ±J bonds: one set per realization, SHARED across its 2 replicas and
    # all M temperatures. Draw (R, L, L), then broadcast to (R, M, 2, L, L) → (B,L,L).
    Jx_r = (torch.randint(0, 2, (R, L, L), generator=g_bond, device=device, dtype=torch.int8) * 2 - 1).float()
    Jy_r = (torch.randint(0, 2, (R, L, L), generator=g_bond, device=device, dtype=torch.int8) * 2 - 1).float()
    Jx = Jx_r.view(R, 1, 1, L, L).expand(R, M, 2, L, L).reshape(B, L, L).contiguous()
    Jy = Jy_r.view(R, 1, 1, L, L).expand(R, M, 2, L, L).reshape(B, L, L).contiguous()

    # Independent initial spins for every lattice (both replicas independent).
    spins = (torch.randint(0, 2, (B, L, L), generator=g_init, device=device, dtype=torch.int8) * 2 - 1)
    mask_a, mask_b = _checkerboard_masks(L, B, device)

    t0 = time.time()
    for _ in range(cfg.n_burnin):
        spins = _half_sweep(spins, beta, Jx, Jy, mask_a, g_step)
        spins = _half_sweep(spins, beta, Jx, Jy, mask_b, g_step)

    # Histogram bins on [-1, 1]; odd n_qbins centres a bin on q = 0.
    edges = torch.linspace(-1.0, 1.0, cfg.n_qbins + 1, device=device)
    # Per-(realization, temperature) accumulators over the measurement samples.
    pq_hist = torch.zeros(R, M, cfg.n_qbins, device=device)   # counts of q per (R, M)
    q2_acc = torch.zeros(R, M, device=device)
    q4_acc = torch.zeros(R, M, device=device)
    qabs_acc = torch.zeros(R, M, device=device)
    q_acc = torch.zeros(R, M, device=device)
    e_acc = torch.zeros(R, M, device=device)
    n_samp = 0

    for s in range(cfg.n_sweeps):
        spins = _half_sweep(spins, beta, Jx, Jy, mask_a, g_step)
        spins = _half_sweep(spins, beta, Jx, Jy, mask_b, g_step)
        if s % cfg.sample_every == 0:
            sv = spins.view(R, M, 2, L, L).float()
            # Overlap between the two replicas of each (realization, temperature).
            q = (sv[:, :, 0] * sv[:, :, 1]).mean(dim=(-1, -2))     # (R, M) ∈ [-1, 1]
            q2_acc += q * q
            q4_acc += q ** 4
            qabs_acc += q.abs()
            q_acc += q
            # Histogram q into bins per (R, M): bucketize then scatter-add.
            idx = torch.bucketize(q, edges) - 1
            idx = idx.clamp(0, cfg.n_qbins - 1)                   # (R, M)
            pq_hist.scatter_add_(2, idx.unsqueeze(-1), torch.ones_like(idx, dtype=pq_hist.dtype).unsqueeze(-1))
            # Energy per spin, averaged over the two replicas of each realization.
            field = _weighted_neighbor_sum(spins, Jx, Jy).view(R, M, 2, L, L).float()
            e = (-0.5 * (sv * field).mean(dim=(-1, -2)))          # (R, M, 2)
            e_acc += e.mean(dim=-1)
            n_samp += 1
    wall = time.time() - t0

    # Per-realization sample means, then DISORDER-AVERAGE over realizations (axis 0).
    q2_per = q2_acc / n_samp
    q4_per = q4_acc / n_samp
    qabs_per = qabs_acc / n_samp
    q_per = q_acc / n_samp
    e_per = e_acc / n_samp

    q2_mean = q2_per.mean(dim=0)                                  # (M,)
    q4_mean = q4_per.mean(dim=0)
    qabs_mean = qabs_per.mean(dim=0)
    q_mean = q_per.mean(dim=0)
    energy = e_per.mean(dim=0)
    # Binder cumulant from the disorder-averaged moments (the standard definition
    # uses disorder-averaged [⟨q⁴⟩] and [⟨q²⟩]). g = ½(3 − [⟨q⁴⟩]/[⟨q²⟩]²).
    binder = 0.5 * (3.0 - q4_mean / q2_mean.clamp_min(1e-12) ** 2)
    # Disorder-averaged, normalised P(q): normalise each (R,M) histogram to a
    # density, then average over realizations.
    centers = 0.5 * (edges[:-1] + edges[1:])
    bin_w = float(edges[1] - edges[0])
    pq_density = pq_hist / (pq_hist.sum(dim=2, keepdim=True).clamp_min(1.0) * bin_w)
    pq_mean = pq_density.mean(dim=0)                              # (M, n_qbins)

    return SpinGlassResult(
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
        wall_seconds=wall,
    )
