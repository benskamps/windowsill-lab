"""Batched 2D Ising Metropolis simulation on GPU.

A batch of `n_temps` independent lattices runs in parallel — one temperature
per lattice. Updates use the checkerboard (red/black) scheme so every
site in a half-lattice can be flipped independently in one tensor op.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict, field
from typing import Optional

import numpy as np
import torch


@dataclass
class RunConfig:
    L: int = 128
    T_min: float = 1.5
    T_max: float = 3.5
    n_temps: int = 21
    n_burnin: int = 8000
    n_sweeps: int = 40000
    sample_every: int = 20
    seed: int = 42
    device: str = "cuda"

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class RunResult:
    config: RunConfig
    T: np.ndarray              # (n_temps,)
    abs_mag: np.ndarray        # mean |M| per spin, (n_temps,)
    abs_mag_err: np.ndarray    # standard error of mean |M|, (n_temps,)
    chi: np.ndarray            # susceptibility per spin (signed m), (n_temps,)
    chi_abs: np.ndarray        # |m|-based susceptibility (FSS-appropriate), (n_temps,)
    energy: np.ndarray         # mean energy per spin, (n_temps,)
    specific_heat: np.ndarray  # C per spin = (⟨E²⟩−⟨E⟩²)·N/T², (n_temps,) — M04
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


def _checkerboard_masks(L: int, n_temps: int, device: torch.device):
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    a = ((ix + iy) % 2 == 0).unsqueeze(0).expand(n_temps, L, L).contiguous()
    return a, ~a


def _neighbor_sum(spins: torch.Tensor) -> torch.Tensor:
    return (
        torch.roll(spins, 1, dims=-2)
        + torch.roll(spins, -1, dims=-2)
        + torch.roll(spins, 1, dims=-1)
        + torch.roll(spins, -1, dims=-1)
    )


def _half_sweep(spins: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor, rng: torch.Generator) -> torch.Tensor:
    """Flip spins on `mask` using Metropolis with per-lattice inverse-T `beta`."""
    nbr = _neighbor_sum(spins)                          # (n_temps, L, L)
    dE = 2.0 * spins.float() * nbr.float()              # ΔE for flipping each site (J=1)
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, -spins, spins)


def run(cfg: RunConfig) -> RunResult:
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T

    spins = (torch.randint(0, 2, (cfg.n_temps, cfg.L, cfg.L), generator=g_init, device=device, dtype=torch.int8) * 2 - 1)
    mask_a, mask_b = _checkerboard_masks(cfg.L, cfg.n_temps, device)

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        spins = _half_sweep(spins, beta, mask_a, g_step)
        spins = _half_sweep(spins, beta, mask_b, g_step)

    # Measurement phase
    mag_samples = []
    energy_samples = []
    for s in range(cfg.n_sweeps):
        spins = _half_sweep(spins, beta, mask_a, g_step)
        spins = _half_sweep(spins, beta, mask_b, g_step)
        if s % cfg.sample_every == 0:
            sf = spins.float()
            mag_samples.append(sf.mean(dim=(-1, -2)).cpu())
            # Energy per spin: -J/2 * sum_i s_i * sum_neighbors(s_i)
            # Factor 1/2 avoids double-counting each bond.
            e = -0.5 * (sf * _neighbor_sum(spins).float()).mean(dim=(-1, -2)).cpu()
            energy_samples.append(e)
    wall = time.time() - t0

    mag = torch.stack(mag_samples)              # (n_samples, n_temps)
    energy = torch.stack(energy_samples)        # (n_samples, n_temps)
    abs_mag_per_sample = mag.abs()
    abs_mag = abs_mag_per_sample.mean(dim=0).numpy()
    abs_mag_err = (abs_mag_per_sample.std(dim=0) / np.sqrt(len(mag_samples))).numpy()
    chi = (cfg.L * cfg.L) * (mag.pow(2).mean(dim=0) - mag.mean(dim=0).pow(2)).numpy() / T.cpu().numpy()
    # |m|-based susceptibility — the finite-size-scaling–appropriate observable.
    # Using ⟨|m|⟩ instead of ⟨m⟩ removes the spurious variance from magnetization
    # sign-flips that contaminates the signed χ on large lattices near T_c, where
    # the system can't tunnel between ±M in a finite run.  χ' = L²(⟨m²⟩−⟨|m|⟩²)/T.
    chi_abs = (cfg.L * cfg.L) * (
        mag.pow(2).mean(dim=0) - abs_mag_per_sample.mean(dim=0).pow(2)
    ).numpy() / T.cpu().numpy()
    energy_mean = energy.mean(dim=0).numpy()

    # Save a few snapshot lattices for the gallery
    T_np = T.cpu().numpy()
    # Specific heat per spin C(T) = (⟨E²⟩−⟨E⟩²)·N/T², from the same energy samples
    # (population variance, matching the 3D engine). It diverges logarithmically
    # at T_c — the observable M04 reads.
    specific_heat = (cfg.L * cfg.L) * energy.var(dim=0, unbiased=False).numpy() / (T_np ** 2)
    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": spins[i].cpu().numpy() for i in pick_idx}

    return RunResult(
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
