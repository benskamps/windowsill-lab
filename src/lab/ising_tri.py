"""Batched 2D *triangular*-lattice Ising Metropolis simulation on GPU.

M05 leaves the square lattice for the triangular one — same spins, same J=1
ferromagnet, same universality class, but a **different geometry** and so a
different exact critical temperature:

    T_c = 4 / ln(3) ≈ 3.64096        (ferromagnetic, k_B = J = 1)

The triangular lattice is the square grid *plus one diagonal*: each site has
**6** nearest neighbours instead of 4. On the (i, j) integer grid with periodic
boundaries the six neighbours are

    (i±1, j), (i, j±1), (i+1, j−1), (i−1, j+1)

i.e. the four square-lattice neighbours plus the two along one diagonal. (The
other diagonal, (i+1,j+1)/(i−1,j−1), is *not* a bond — that diagonal is the one
the triangulation cuts, so adding it would give the fully-connected square-with-
both-diagonals lattice, a different model.)

### Why this can't reuse ising.py's red/black update

``ising.py`` flips a 2-colour (checkerboard) sublattice at a time, which is exact
only when the lattice is **bipartite** — no two same-colour sites are neighbours.
The triangular lattice is **not** bipartite: its triangles are odd cycles, so a
2-colouring inevitably puts two neighbours in the same colour (the diagonal bond
joins two "red" sites), and flipping them together is physically wrong — their
ΔE would depend on each other.

The fix is a **3-colouring**. A valid one is

    color(i, j) = (i + 2·j) % 3

Each of the six neighbour offsets shifts the colour by a non-zero amount
(the shifts are {1, 2}, never 0), so no site shares a colour with any neighbour;
the three colour classes are independent sets. We update one colour at a time:
within a single colour every site's six neighbours belong to the *other* two
colours, which are held fixed, so the parallel Metropolis flip of that colour is
exact (same guarantee the 2-colour checkerboard gives on a bipartite lattice).

This colouring only wraps cleanly across the periodic seam when **L is a
multiple of 3** (otherwise the toroidal identification glues colour c to colour
c+L mod 3 and two neighbours can collide at the seam). We *enforce* that, the way
``ising3d`` enforces even L for its 3D checkerboard — a physically-correct
geometry is non-negotiable here. The default L = 129 is the multiple of 3 nearest
the square engine's L = 128.

Everything else mirrors ``ising.py``: a batch of ``n_temps`` independent lattices,
one temperature each, run in parallel; the |m|-based susceptibility ``chi_abs``
and the specific heat ``C = (⟨E²⟩−⟨E⟩²)·N/T²`` computed exactly as the square
engine does, just with the 6-neighbour sum (energy per spin still carries the
0.5 that stops each bond being double-counted).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch


@dataclass
class TriRunConfig:
    L: int = 129              # must be a multiple of 3 (periodic 3-colour seam)
    T_min: float = 3.3
    T_max: float = 4.0
    n_temps: int = 25
    n_burnin: int = 8000
    n_sweeps: int = 40000
    sample_every: int = 20
    seed: int = 42
    device: str = "cuda"

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class TriRunResult:
    config: TriRunConfig
    T: np.ndarray              # (n_temps,)
    abs_mag: np.ndarray        # mean |M| per spin, (n_temps,)
    abs_mag_err: np.ndarray    # standard error of mean |M|, (n_temps,)
    chi: np.ndarray            # susceptibility per spin (signed m), (n_temps,)
    chi_abs: np.ndarray        # |m|-based susceptibility (FSS-appropriate), (n_temps,)
    energy: np.ndarray         # mean energy per spin, (n_temps,)
    specific_heat: np.ndarray  # C per spin = (⟨E²⟩−⟨E⟩²)·N/T², (n_temps,)
    snapshots: dict            # {temperature_key: 2D int8 lattice, sampled at end}
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "abs_mag": self.abs_mag.tolist(),
            "abs_mag_err": self.abs_mag_err.tolist(),
            "chi": self.chi.tolist(),
            "chi_abs": self.chi_abs.tolist(),
            "energy": self.energy.tolist(),
            "specific_heat": self.specific_heat.tolist(),
            "snapshots": {k: v.astype(int).tolist() for k, v in self.snapshots.items()},
            "wall_seconds": self.wall_seconds,
        }


def _color_masks(L: int, n_temps: int, device: torch.device):
    """The three sublattice masks for ``color(i, j) = (i + 2·j) % 3``.

    Returns a list of three boolean tensors, each ``(n_temps, L, L)``, partitioning
    every site into one colour class. Flipping one class at a time is exact: a
    site's six neighbours all live in the *other* two classes (verified: each of
    the six neighbour offsets shifts the colour by a non-zero amount).
    """
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    color = (ix + 2 * iy) % 3
    return [
        (color == c).unsqueeze(0).expand(n_temps, L, L).contiguous()
        for c in range(3)
    ]


def _neighbor_sum(spins: torch.Tensor) -> torch.Tensor:
    """Sum of the six triangular-lattice neighbours on a periodic lattice.

    The four square neighbours plus the (i+1, j−1) / (i−1, j+1) diagonal — the
    diagonal the triangulation keeps. ``spins`` is ``(n_temps, L, L)``; rolls wrap.
    """
    return (
        torch.roll(spins, 1, dims=-2)
        + torch.roll(spins, -1, dims=-2)
        + torch.roll(spins, 1, dims=-1)
        + torch.roll(spins, -1, dims=-1)
        + torch.roll(spins, (1, -1), dims=(-2, -1))   # (i+1, j−1)
        + torch.roll(spins, (-1, 1), dims=(-2, -1))   # (i−1, j+1)
    )


def _color_sweep(spins: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor,
                 rng: torch.Generator) -> torch.Tensor:
    """Metropolis flip of one colour class with per-lattice inverse-T ``beta``.

    Identical in form to ``ising._half_sweep`` — only the neighbour stencil (6,
    not 4) and the sublattice partition (3 colours, not 2) differ.
    """
    nbr = _neighbor_sum(spins)                          # (n_temps, L, L)
    dE = 2.0 * spins.float() * nbr.float()              # ΔE for flipping each site (J=1)
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, -spins, spins)


def run(cfg: TriRunConfig) -> TriRunResult:
    """Run a batched triangular-lattice Ising sweep: one lattice per temperature.

    Mirrors ``ising.run`` — a burn-in then a measurement phase sampling ⟨|m|⟩ and
    the energy — but sweeps the three colour classes per step (not two), using the
    6-neighbour sum. The χ_abs peak locates the (finite-size) critical temperature,
    M05's headline observable, compared against the exact triangular T_c = 4/ln 3.
    """
    if cfg.L % 3 != 0:
        raise ValueError(
            f"L must be a multiple of 3 for the triangular 3-colour update "
            f"(got {cfg.L}); the (i+2j)%3 colouring only wraps cleanly across the "
            f"periodic seam when 3 | L."
        )
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T

    spins = (torch.randint(0, 2, (cfg.n_temps, cfg.L, cfg.L), generator=g_init, device=device, dtype=torch.int8) * 2 - 1)
    masks = _color_masks(cfg.L, cfg.n_temps, device)

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        for mask in masks:
            spins = _color_sweep(spins, beta, mask, g_step)

    # Measurement phase
    mag_samples = []
    energy_samples = []
    for s in range(cfg.n_sweeps):
        for mask in masks:
            spins = _color_sweep(spins, beta, mask, g_step)
        if s % cfg.sample_every == 0:
            sf = spins.float()
            mag_samples.append(sf.mean(dim=(-1, -2)).cpu())
            # Energy per spin: -J/2 · Σ_i s_i · Σ_neighbours(s_i); the 1/2 stops
            # each of the 3N bonds being counted from both ends (6 neighbours / 2).
            e = -0.5 * (sf * _neighbor_sum(spins).float()).mean(dim=(-1, -2)).cpu()
            energy_samples.append(e)
    wall = time.time() - t0

    mag = torch.stack(mag_samples)              # (n_samples, n_temps)
    energy = torch.stack(energy_samples)        # (n_samples, n_temps)
    abs_mag_per_sample = mag.abs()
    abs_mag = abs_mag_per_sample.mean(dim=0).numpy()
    abs_mag_err = (abs_mag_per_sample.std(dim=0) / np.sqrt(len(mag_samples))).numpy()
    T_np = T.cpu().numpy()
    chi = (cfg.L * cfg.L) * (mag.pow(2).mean(dim=0) - mag.mean(dim=0).pow(2)).numpy() / T_np
    # |m|-based susceptibility — the finite-size-scaling–appropriate observable
    # (the same sign-flip reasoning ``ising.chi_abs`` documents in the square case:
    # ⟨|m|⟩ removes the spurious variance from magnetization sign-flips near T_c on
    # a finite lattice that can't tunnel between ±M in a finite run). χ' = L²(⟨m²⟩−⟨|m|⟩²)/T.
    chi_abs = (cfg.L * cfg.L) * (
        mag.pow(2).mean(dim=0) - abs_mag_per_sample.mean(dim=0).pow(2)
    ).numpy() / T_np
    energy_mean = energy.mean(dim=0).numpy()
    # Specific heat per spin C(T) = (⟨E²⟩−⟨E⟩²)·N/T² (population variance, matching
    # the square + 3D engines). It peaks at T_c — M05's thermal cross-check.
    specific_heat = (cfg.L * cfg.L) * energy.var(dim=0, unbiased=False).numpy() / (T_np ** 2)

    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": spins[i].cpu().numpy() for i in pick_idx}

    return TriRunResult(
        config=cfg,
        T=T_np,
        abs_mag=abs_mag,
        abs_mag_err=abs_mag_err,
        chi=chi,
        chi_abs=chi_abs,
        energy=energy_mean,
        specific_heat=specific_heat,
        snapshots=snapshots,
        wall_seconds=wall,
    )
