"""Batched 3D simple-cubic Ising Wolff single-cluster updater.

This is the three-dimensional cousin of ``wolff.py``. The 2D Wolff updater
sidesteps critical slowing down by flipping whole *clusters* instead of single
spins; the same trick is exactly what M06 (3D Ising, T_c ≈ 4.5115) and the
M06 L-extrapolation in ``BACKLOG.md`` need to reach larger lattices without the
single-spin Metropolis updater's z ≈ 2 autocorrelation blow-up near criticality.

The 3D generalisation is mechanical — only the *bond bookkeeping* changes:

### The load-bearing correctness facts (3D edition)

1. **Each undirected bond is activated exactly once.** On a periodic simple-cubic
   torus every site owns exactly *three* bonds — its "+x" bond to
   ``((x+1)%L, y, z)``, its "+y" bond to ``(x, (y+1)%L, z)`` and its "+z" bond to
   ``(x, y, (z+1)%L)``. Iterating all sites in those three orientations enumerates
   every one of the 3·L³ bonds once with no double counting. We therefore draw
   exactly *three* uniform fields per update (one per orientation), never six.
   Activating in all six directions would give each bond two independent chances
   and corrupt the cluster-size distribution.

2. **The bond field is frozen before the flood.** Activation randomness is sampled
   once into ``bond_x``/``bond_y``/``bond_z`` and the parallel BFS grows the seed's
   component to a fixpoint over those *frozen* tensors. Re-sampling inside the BFS
   frontier (the classic GPU-Wolff bug) breaks detailed balance and lets clusters
   grow without bound.

The bond-activation probability is the same as in 2D, ``p = 1 - exp(-2·β·J)`` —
it depends only on the single-bond Boltzmann weight, not on the dimension.

The pure mechanics (``_neighbor_sum``, ``_bond_field``, ``_seed_mask``,
``_grow_cluster``, ``wolff_update``) are torch but device-agnostic and unit-tested
on CPU. ``wolff_run`` is the temperature-sweep driver; its equilibrium observables
(``abs_mag``, ``energy``) are directly comparable to the verified ``ising3d.run``
Metropolis engine — which is exactly how the test suite proves this updater samples
the correct Boltzmann distribution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch


@dataclass
class Wolff3DConfig:
    L: int = 16
    T_min: float = 4.0
    T_max: float = 5.0
    n_temps: int = 21
    n_burnin: int = 1000        # Wolff UPDATES (not sweeps); z≈0.3 → far fewer needed
    n_updates: int = 8000       # measurement-phase Wolff updates
    sample_every: int = 10
    seed: int = 42
    device: str = "cpu"

    def n_samples(self) -> int:
        return self.n_updates // self.sample_every


@dataclass
class Wolff3DResult:
    config: Wolff3DConfig
    T: np.ndarray                      # (n_temps,)
    abs_mag: np.ndarray                # mean |m| per spin, (n_temps,)
    abs_mag_err: np.ndarray            # standard error of mean |m|, (n_temps,)
    chi: np.ndarray                    # signed-m susceptibility per spin, (n_temps,)
    chi_abs: np.ndarray                # |m|-based susceptibility (FSS observable), (n_temps,)
    energy: np.ndarray                 # mean energy per spin, (n_temps,)
    mean_cluster_fraction: np.ndarray  # ⟨cluster size⟩/L³ per T, (n_temps,) diagnostic
    snapshots: dict                    # {temperature_key: 2D int8 mid-plane slice}
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


def _neighbor_sum(spins: torch.Tensor) -> torch.Tensor:
    """Sum of the six nearest neighbours on a periodic simple-cubic lattice.

    ``spins`` has shape ``(n_temps, L, L, L)``; rolls wrap (periodic BC). Mirrors
    ``ising3d._neighbor_sum`` but in torch so the energy estimator and the cluster
    machinery share one tensor backend.
    """
    return (
        torch.roll(spins, 1, dims=-3) + torch.roll(spins, -1, dims=-3)
        + torch.roll(spins, 1, dims=-2) + torch.roll(spins, -1, dims=-2)
        + torch.roll(spins, 1, dims=-1) + torch.roll(spins, -1, dims=-1)
    )


def _bond_field(
    spins: torch.Tensor, p: torch.Tensor, rng: torch.Generator
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Activate each aligned bond EXACTLY ONCE.

    Returns ``(bond_x, bond_y, bond_z)``, all bool ``(n_temps, L, L, L)``.
    ``bond_x[..., x, y, z]`` couples ``(x,y,z) ↔ ((x+1)%L, y, z)`` and similarly
    for y (axis −2) and z (axis −1). Together these enumerate every undirected
    bond on the torus once. ``p`` has shape ``(n_temps, 1, 1, 1)``.

    A bond activates iff its two endpoints are aligned AND a fresh uniform draw
    falls below ``p``. Exactly three uniform fields are drawn (one per
    orientation) so the activation randomness is consumed once and never re-rolled
    during the flood.
    """
    # +x neighbour of (x,y,z) is ((x+1)%L,y,z) → roll the lattice by −1 on that
    # axis so position (x,y,z) sees the spin originally at (x+1,y,z).
    x_nbr = torch.roll(spins, shifts=-1, dims=-3)
    y_nbr = torch.roll(spins, shifts=-1, dims=-2)
    z_nbr = torch.roll(spins, shifts=-1, dims=-1)
    aligned_x = spins == x_nbr
    aligned_y = spins == y_nbr
    aligned_z = spins == z_nbr

    u_x = torch.rand(spins.shape, generator=rng, device=spins.device)
    u_y = torch.rand(spins.shape, generator=rng, device=spins.device)
    u_z = torch.rand(spins.shape, generator=rng, device=spins.device)

    bond_x = aligned_x & (u_x < p)
    bond_y = aligned_y & (u_y < p)
    bond_z = aligned_z & (u_z < p)
    return bond_x, bond_y, bond_z


def _seed_mask(n_temps: int, L: int, device, rng: torch.Generator) -> torch.Tensor:
    """One random True site per lattice; bool ``(n_temps, L, L, L)``."""
    flat = torch.zeros(n_temps, L * L * L, dtype=torch.bool, device=device)
    idx = torch.randint(0, L * L * L, (n_temps,), generator=rng, device=device)
    flat[torch.arange(n_temps, device=device), idx] = True
    return flat.view(n_temps, L, L, L)


def _grow_cluster(
    seed: torch.Tensor,
    bond_x: torch.Tensor,
    bond_y: torch.Tensor,
    bond_z: torch.Tensor,
    max_iters: int | None = None,
) -> torch.Tensor:
    """Parallel BFS to a fixpoint over the FROZEN bond field.

    Returns the ``in_cluster`` bool mask ``(n_temps, L, L, L)`` of each lattice's
    seed-connected component. Each pass propagates membership across every
    activated bond in BOTH directions (a bond joins its two endpoints, so an
    in-cluster endpoint pulls in the other). The cluster grows by at most one ring
    per pass and is bounded by ``L³`` sites, so the fixpoint is reached in at most
    ``L³`` passes (``max_iters`` default). A lattice that converges early simply
    stops changing while others continue — its component is unaffected because the
    bond field is frozen.
    """
    L = seed.shape[-1]
    if max_iters is None:
        max_iters = L * L * L

    in_cluster = seed.clone()
    # For each orientation, a bond located at site s couples s with its +axis
    # neighbour s'. Membership can flow either way across that bond:
    #   - s  joins because s' is in cluster  → guard is bond at s,  pull from +axis
    #   - s' joins because s  is in cluster  → guard is bond rolled to s', pull from −axis
    bx_a = bond_x                                    # at (x,y,z): partner (x+1,y,z)
    bx_b = torch.roll(bond_x, shifts=1, dims=-3)     # at (x+1,y,z): partner (x,y,z)
    by_a = bond_y
    by_b = torch.roll(bond_y, shifts=1, dims=-2)
    bz_a = bond_z
    bz_b = torch.roll(bond_z, shifts=1, dims=-1)

    for _ in range(max_iters):
        prev = in_cluster
        grown = in_cluster.clone()
        grown |= bx_a & torch.roll(in_cluster, shifts=-1, dims=-3)
        grown |= bx_b & torch.roll(in_cluster, shifts=1, dims=-3)
        grown |= by_a & torch.roll(in_cluster, shifts=-1, dims=-2)
        grown |= by_b & torch.roll(in_cluster, shifts=1, dims=-2)
        grown |= bz_a & torch.roll(in_cluster, shifts=-1, dims=-1)
        grown |= bz_b & torch.roll(in_cluster, shifts=1, dims=-1)
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
    """One independent single-cluster Wolff move per batched 3D lattice.

    Pure (returns new spins; does not mutate ``spins``). ``p = 1 - exp(-2·β·J)``;
    ``beta`` has shape ``(n_temps,)``. The bond field is built once and frozen, a
    single random seed site is chosen per lattice, the seed's connected component
    is grown to a fixpoint, and exactly that component is flipped via
    ``torch.where(in_cluster, -spins, spins)``.

    With ``return_size=True`` also returns per-lattice cluster sizes
    ``(n_temps,)``; with ``return_cluster=True`` also returns the boolean
    ``in_cluster`` mask (used by tests). If both are requested the order is
    ``(spins, sizes, cluster)``.
    """
    n_temps, L, _, _ = spins.shape
    device = spins.device
    p = (1.0 - torch.exp(-2.0 * beta.to(torch.float32) * J)).view(n_temps, 1, 1, 1).to(device)

    bond_x, bond_y, bond_z = _bond_field(spins, p, rng)
    seed = _seed_mask(n_temps, L, device, rng)
    in_cluster = _grow_cluster(seed, bond_x, bond_y, bond_z)

    new_spins = torch.where(in_cluster, (-spins).to(spins.dtype), spins)

    extras = []
    if return_size:
        extras.append(in_cluster.sum(dim=(-1, -2, -3)))
    if return_cluster:
        extras.append(in_cluster)
    if extras:
        return (new_spins, *extras)
    return new_spins


def wolff_run(cfg: Wolff3DConfig) -> Wolff3DResult:
    """Batched single-cluster Wolff sweep across temperatures (3D simple cubic).

    Mirrors ``ising3d.run``: one temperature per batched L³ lattice, the same core
    observables (``abs_mag``, ``abs_mag_err``, ``chi``, ``energy``) with identical
    shapes for direct comparison, plus ``chi_abs`` and the
    ``mean_cluster_fraction`` diagnostic. NOTE the units difference: one Wolff
    *update* is not one Metropolis *sweep*, so ``n_burnin``/``n_updates`` are
    counted in Wolff updates. Equilibrated observables are still directly
    comparable across the two algorithms — which is the suite's detailed-balance
    check.
    """
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T

    spins = (
        torch.randint(
            0, 2, (cfg.n_temps, cfg.L, cfg.L, cfg.L),
            generator=g_init, device=device, dtype=torch.int8,
        )
        * 2
        - 1
    )

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        spins = wolff_update(spins, beta, g_step)

    # Measurement phase
    mag_samples = []
    energy_samples = []
    cluster_frac_samples = []
    N = cfg.L ** 3
    for s in range(cfg.n_updates):
        spins, size = wolff_update(spins, beta, g_step, return_size=True)
        if s % cfg.sample_every == 0:
            sf = spins.float()
            mag_samples.append(sf.mean(dim=(-1, -2, -3)).cpu())
            e = -0.5 * (sf * _neighbor_sum(spins).float()).mean(dim=(-1, -2, -3)).cpu()
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
    # (same definition as ising3d.run.chi).
    chi_abs = (N) * (
        mag.pow(2).mean(dim=0) - abs_mag_per_sample.mean(dim=0).pow(2)
    ).numpy() / T_np
    energy_mean = energy.mean(dim=0).numpy()
    mean_cluster_fraction = cluster_frac.mean(dim=0).numpy()

    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    # 3D lattices are large; store a single mid-plane (z=L//2) slice per picked
    # temperature so the snapshot stays JSON-light while remaining a real view.
    mid = cfg.L // 2
    snapshots = {
        f"T={T_np[i]:.3f}": spins[i, :, :, mid].cpu().numpy() for i in pick_idx
    }

    return Wolff3DResult(
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
