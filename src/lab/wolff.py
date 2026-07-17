"""Batched 2D Ising Wolff single-cluster updater on GPU.

The Metropolis updater (``ising.py``) flips one site at a time. Near T_c it
suffers *critical slowing down*: the autocorrelation time blows up like
τ ∝ L^z with z ≈ 2.17, so equilibrating a large lattice costs O(L²) sweeps and
L≥512 becomes impractical. The **Wolff algorithm** (Swendsen–Wang's
single-cluster cousin, Wolff 1989) sidesteps this. Instead of flipping a site,
it grows a *cluster* of aligned spins by activating each bond between aligned
neighbours with probability

    p = 1 - exp(-2·β·J)      (J = 1)

and flips the whole connected component containing a random seed. Because the
cluster size self-tunes to the correlation length, the dynamic exponent drops to
z ≈ 0.25 — a single cluster move near criticality decorrelates the lattice that
many Metropolis sweeps could not.

This module mirrors ``ising.run``'s batched design: ``n_temps`` independent
lattices run in parallel, one temperature per lattice, all updated in lockstep
with vectorised ``torch.roll`` operations.

### The two load-bearing correctness facts

1. **Each undirected bond is activated exactly once.** On a torus every site
   owns exactly two bonds — its "down" bond to ``((i+1)%L, j)`` and its "right"
   bond to ``(i, (j+1)%L)``. Iterating all sites in those two orientations
   enumerates every bond once with no double counting. We therefore draw exactly
   *two* uniform fields per update (one per orientation), never four. Activating
   in all four directions would give each bond two independent chances and
   corrupt the cluster-size distribution.

2. **The bond field is frozen before the flood.** Activation randomness is
   sampled once into ``bond_down``/``bond_right`` and the parallel BFS grows the
   seed's component to a fixpoint over those *frozen* tensors. Re-sampling inside
   the BFS frontier (the classic GPU-Wolff bug) breaks detailed balance and lets
   clusters grow without bound.

The pure mechanics (``_bond_field``, ``_seed_mask``, ``_grow_cluster``,
``wolff_update``) are torch but device-agnostic and unit-tested on CPU.
``wolff_run`` is the temperature-sweep driver, returning the same observables
and shapes as ``ising.run`` for direct comparison.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch

from .ising import _neighbor_sum


@dataclass
class WolffConfig:
    L: int = 128
    T_min: float = 2.0
    T_max: float = 2.5
    n_temps: int = 21
    n_burnin: int = 2000        # Wolff UPDATES (not sweeps); z≈0.25 → far fewer needed
    n_updates: int = 20000      # measurement-phase Wolff updates
    sample_every: int = 10
    seed: int = 42
    device: str = "cpu"
    init: str = "random"        # "random" (hot, T=∞) or "ordered" (cold, all-up)

    def n_samples(self) -> int:
        return self.n_updates // self.sample_every


@dataclass
class WolffResult:
    config: WolffConfig
    T: np.ndarray                      # (n_temps,)
    abs_mag: np.ndarray                # mean |m| per spin, (n_temps,)
    abs_mag_err: np.ndarray            # standard error of mean |m|, (n_temps,)
    chi: np.ndarray                    # signed-m susceptibility per spin, (n_temps,)
    chi_abs: np.ndarray                # |m|-based susceptibility (FSS observable), (n_temps,)
    energy: np.ndarray                 # mean energy per spin, (n_temps,)
    mean_cluster_fraction: np.ndarray  # ⟨cluster size⟩/L² per T, (n_temps,) diagnostic
    snapshots: dict                    # {temperature_key: 2D int8 lattice}
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
            "mean_cluster_fraction": self.mean_cluster_fraction.tolist(),
            "snapshots": {k: v.astype(int).tolist() for k, v in self.snapshots.items()},
            "wall_seconds": self.wall_seconds,
        }


def _bond_field(
    spins: torch.Tensor, p: torch.Tensor, rng: torch.Generator
) -> tuple[torch.Tensor, torch.Tensor]:
    """Activate each aligned bond EXACTLY ONCE.

    Returns ``(bond_down, bond_right)``, both bool ``(n_temps, L, L)``.
    ``bond_down[..., i, j]`` couples ``(i, j) ↔ ((i+1)%L, j)`` and
    ``bond_right[..., i, j]`` couples ``(i, j) ↔ (i, (j+1)%L)``. Together these
    enumerate every undirected bond on the torus once. ``p`` has shape
    ``(n_temps, 1, 1)``.

    A bond activates iff its two endpoints are aligned AND a fresh uniform draw
    falls below ``p``. Exactly two uniform fields are drawn (one per
    orientation) so the activation randomness is consumed once and never
    re-rolled during the flood.
    """
    # down-neighbour of (i,j) is ((i+1)%L, j) → roll the lattice UP by one row so
    # that position (i,j) sees the spin originally at (i+1,j).
    down_nbr = torch.roll(spins, shifts=-1, dims=-2)
    right_nbr = torch.roll(spins, shifts=-1, dims=-1)
    aligned_down = spins == down_nbr
    aligned_right = spins == right_nbr

    u_down = torch.rand(spins.shape, generator=rng, device=spins.device)
    u_right = torch.rand(spins.shape, generator=rng, device=spins.device)

    bond_down = aligned_down & (u_down < p)
    bond_right = aligned_right & (u_right < p)
    return bond_down, bond_right


def _seed_mask(n_temps: int, L: int, device, rng: torch.Generator) -> torch.Tensor:
    """One random True site per lattice; bool ``(n_temps, L, L)``."""
    flat = torch.zeros(n_temps, L * L, dtype=torch.bool, device=device)
    idx = torch.randint(0, L * L, (n_temps,), generator=rng, device=device)
    flat[torch.arange(n_temps, device=device), idx] = True
    return flat.view(n_temps, L, L)


def _grow_cluster(
    seed: torch.Tensor,
    bond_down: torch.Tensor,
    bond_right: torch.Tensor,
    max_iters: int | None = None,
) -> torch.Tensor:
    """Parallel BFS to a fixpoint over the FROZEN bond field.

    Returns the ``in_cluster`` bool mask ``(n_temps, L, L)`` of each lattice's
    seed-connected component. Each pass propagates membership across every
    activated bond in BOTH directions (a bond joins its two endpoints, so an
    in-cluster endpoint pulls in the other). The cluster grows by at most one
    ring per pass and is bounded by ``L*L`` sites, so the fixpoint is reached in
    at most ``L*L`` passes (``max_iters`` default). A lattice that converges
    early simply stops changing while others continue — its component is
    unaffected because the bond field is frozen.
    """
    L = seed.shape[-1]
    if max_iters is None:
        max_iters = L * L

    in_cluster = seed.clone()
    # Pre-roll the bond tensors to the four directions a site can be reached from.
    # bond_down[i,j] couples (i,j)<->(i+1,j):
    #   - site (i+1,j) joins if (i,j) is in cluster: in_cluster pulled from up
    #     across bond_down located at (i,j) → roll bond_down DOWN to align to (i+1,j)
    #   - site (i,j) joins if (i+1,j) is in cluster: pull in_cluster from below
    bond_down_to_up = bond_down  # at (i,j): neighbour (i+1,j)
    bond_down_to_down = torch.roll(bond_down, shifts=1, dims=-2)  # at (i+1,j): neighbour (i,j)
    bond_right_to_left = bond_right  # at (i,j): neighbour (i,j+1)
    bond_right_to_right = torch.roll(bond_right, shifts=1, dims=-1)  # at (i,j+1): neighbour (i,j)

    for _ in range(max_iters):
        prev = in_cluster
        grown = in_cluster.clone()
        # (i,j) joins because its down-neighbour (i+1,j) is in cluster, via bond_down[i,j]
        grown |= bond_down_to_up & torch.roll(in_cluster, shifts=-1, dims=-2)
        # (i+1,j) joins because (i,j) is in cluster, via the same bond
        grown |= bond_down_to_down & torch.roll(in_cluster, shifts=1, dims=-2)
        # (i,j) joins because its right-neighbour (i,j+1) is in cluster, via bond_right[i,j]
        grown |= bond_right_to_left & torch.roll(in_cluster, shifts=-1, dims=-1)
        # (i,j+1) joins because (i,j) is in cluster, via the same bond
        grown |= bond_right_to_right & torch.roll(in_cluster, shifts=1, dims=-1)
        in_cluster = grown
        if not torch.any(in_cluster.ne(prev)):
            break
    return in_cluster


def wolff_update(
    spins: torch.Tensor,
    beta: torch.Tensor,
    rng: torch.Generator,
    J: float = 1.0,
    return_size: bool = False,
    return_cluster: bool = False,
):
    """One independent single-cluster Wolff move per batched lattice.

    Pure (returns new spins; does not mutate ``spins``). ``p = 1 - exp(-2·β·J)``;
    ``beta`` has shape ``(n_temps,)``. The bond field is built once and frozen,
    a single random seed site is chosen per lattice, the seed's connected
    component is grown to a fixpoint, and exactly that component is flipped via
    ``torch.where(in_cluster, -spins, spins)``.

    With ``return_size=True`` also returns per-lattice cluster sizes
    ``(n_temps,)``; with ``return_cluster=True`` also returns the boolean
    ``in_cluster`` mask (used by tests). If both are requested the order is
    ``(spins, sizes, cluster)``.
    """
    n_temps, L, _ = spins.shape
    device = spins.device
    p = (1.0 - torch.exp(-2.0 * beta.to(torch.float32) * J)).view(n_temps, 1, 1).to(device)

    bond_down, bond_right = _bond_field(spins, p, rng)
    seed = _seed_mask(n_temps, L, device, rng)
    in_cluster = _grow_cluster(seed, bond_down, bond_right)

    new_spins = torch.where(in_cluster, (-spins).to(spins.dtype), spins)

    extras = []
    if return_size:
        extras.append(in_cluster.sum(dim=(-1, -2)))
    if return_cluster:
        extras.append(in_cluster)
    if extras:
        return (new_spins, *extras)
    return new_spins


def wolff_run(cfg: WolffConfig) -> WolffResult:
    """Batched single-cluster Wolff sweep across temperatures.

    Mirrors ``ising.run``: one temperature per batched lattice, the same
    observables (``abs_mag``, ``abs_mag_err``, ``chi``, ``chi_abs``, ``energy``,
    ``snapshots``) with identical shapes for direct comparison, plus the
    ``mean_cluster_fraction`` diagnostic. NOTE the units difference: one Wolff
    *update* is not one Metropolis *sweep*, so ``n_burnin``/``n_updates`` are
    counted in Wolff updates. Equilibrated observables are still directly
    comparable across the two algorithms.
    """
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T

    # Initial condition. "random" is the historical hot (T=∞) start. "ordered"
    # (all spins up) matters at scale: from a hot start the aligned-bond field
    # percolates only weakly (p_bond = ½·(1−e^(−2β)) ≈ 0.29 < ½ near T_c), so
    # single-cluster moves flip O(10)-site clusters and the lattice inches
    # toward equilibrium — measured on GPU, L=256/512 stay at cluster
    # fraction ~1e-4 even after 2000 updates. From the ordered side the
    # aligned-bond probability is 1−e^(−2β) ≈ 0.59 > ½, clusters span, and a
    # few hundred updates disorder the lattice into equilibrium. Both starts
    # sample the same equilibrium distribution once burned in (tested); the
    # ordered start is simply the practical one for large-L critical runs.
    if cfg.init == "ordered":
        spins = torch.ones((cfg.n_temps, cfg.L, cfg.L), device=device, dtype=torch.int8)
    elif cfg.init == "random":
        spins = (
            torch.randint(0, 2, (cfg.n_temps, cfg.L, cfg.L), generator=g_init, device=device, dtype=torch.int8)
            * 2
            - 1
        )
    else:
        raise ValueError(f"unknown init {cfg.init!r} (use 'random' or 'ordered')")

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        spins = wolff_update(spins, beta, g_step)

    # Measurement phase
    mag_samples = []
    energy_samples = []
    cluster_frac_samples = []
    N = cfg.L * cfg.L
    for s in range(cfg.n_updates):
        spins, size = wolff_update(spins, beta, g_step, return_size=True)
        if s % cfg.sample_every == 0:
            sf = spins.float()
            mag_samples.append(sf.mean(dim=(-1, -2)).cpu())
            e = -0.5 * (sf * _neighbor_sum(spins).float()).mean(dim=(-1, -2)).cpu()
            energy_samples.append(e)
            cluster_frac_samples.append((size.float() / N).cpu())
    wall = time.time() - t0

    mag = torch.stack(mag_samples)              # (n_samples, n_temps)
    energy = torch.stack(energy_samples)        # (n_samples, n_temps)
    cluster_frac = torch.stack(cluster_frac_samples)
    abs_mag_per_sample = mag.abs()
    abs_mag = abs_mag_per_sample.mean(dim=0).numpy()
    abs_mag_err = (abs_mag_per_sample.std(dim=0) / np.sqrt(len(mag_samples))).numpy()
    T_np = T.cpu().numpy()
    chi = (N) * (mag.pow(2).mean(dim=0) - mag.mean(dim=0).pow(2)).numpy() / T_np
    # |m|-based susceptibility — the finite-size-scaling–appropriate observable
    # (same definition as ising.run.chi_abs).
    chi_abs = (N) * (
        mag.pow(2).mean(dim=0) - abs_mag_per_sample.mean(dim=0).pow(2)
    ).numpy() / T_np
    energy_mean = energy.mean(dim=0).numpy()
    mean_cluster_fraction = cluster_frac.mean(dim=0).numpy()

    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": spins[i].cpu().numpy() for i in pick_idx}

    return WolffResult(
        config=cfg,
        T=T_np,
        abs_mag=abs_mag,
        abs_mag_err=abs_mag_err,
        chi=chi,
        chi_abs=chi_abs,
        energy=energy_mean,
        mean_cluster_fraction=mean_cluster_fraction,
        snapshots=snapshots,
        wall_seconds=wall,
    )
