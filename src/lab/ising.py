"""Batched 2D Ising Metropolis simulation on GPU.

A batch of `n_temps` independent lattices runs in parallel — one temperature
per lattice. Updates use the checkerboard (red/black) scheme so every
site in a half-lattice can be flipped independently in one tensor op.
"""
from __future__ import annotations

import math
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
    # Keep the library default random for backwards-compatible reproducibility.
    # The long-running M01 heartbeat opts into "ordered": local Metropolis
    # dynamics otherwise leaves cold, large random lattices in metastable
    # domains long after the nominal burn-in.
    initial_state: str = "random"

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
    # The temperature of the MIDDLE snapshot — the frame the gallery captions as
    # critical. Published because it is a choice this run made from its own χ'
    # curve (see ``snapshot_indices``), and a downstream reader that re-derives it
    # from a carried-forward lattice would name a temperature no lattice shows.
    snapshot_peak_t: float | None = None

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
            "snapshot_peak_t": self.snapshot_peak_t,
            "wall_seconds": self.wall_seconds,
        }


def snapshot_indices(n_temps: int, peak_observable=None) -> list[int]:
    """The three temperature indices the lattice gallery shows: cold, peak, hot.

    The gallery's whole claim is that the middle frame is what a critical point
    looks like from the inside. Since the first commit (2026-06-08) it was not:
    the index was the POSITIONAL midpoint of the sweep, ``n_temps // 2``, which is
    the critical frame only if T_c happens to sit at the centre of the temperature
    window. On the M01 heartbeat (T from 1.5 to 3.5, 21 points) it does not: that
    midpoint is T = 2.5, where the 2026-08-30 run measures ⟨|m|⟩ ≈ 0.047 — a
    nearly-disordered lattice — while the same run's χ' peak is index 8, T = 2.3,
    ⟨|m|⟩ ≈ 0.264, one grid step off Onsager's exact T_c = 2.269. The page showed
    thermal noise and captioned it "near the tipping point". The frame was wrong,
    not the caption.

    ``peak_observable`` is the run's OWN per-temperature response curve — χ' for
    the ferromagnetic spin engines — so each run picks the frame ITS measurement
    says is critical rather than a frame a config's endpoints happened to choose.
    Nothing is assumed about where T_c is.

    ``peak_observable=None`` reproduces the legacy positional midpoint EXACTLY.
    That is a compatibility guarantee, not a fallback of convenience: engines with
    no usable peak (``xy`` snapshots θ angles, not spins; the frustrated
    triangular antiferromagnet has no transition at all) keep the picture they
    have always had, provably unchanged, and the change is confined to the
    engines that can actually justify moving it.

    Two shapes fall back to that same legacy midpoint rather than guessing:

    * an observable that is the wrong length or carries a non-finite value — a
      degenerate curve must never be allowed to move the picture;
    * a peak that lands on the coldest or hottest index — the triptych needs
      three DISTINCT frames, and an endpoint peak means the sweep never bracketed
      the transition, so there is no interior critical frame to show.

    Ties resolve to the lowest index, deterministically, so a run's snapshot
    choice is reproducible from its own numbers.
    """
    legacy = [0, n_temps // 2, n_temps - 1]
    if peak_observable is None:
        return legacy
    try:
        values = [float(v) for v in peak_observable]
    except (TypeError, ValueError):
        return legacy
    if len(values) != n_temps or not all(math.isfinite(v) for v in values):
        return legacy
    peak = max(range(n_temps), key=lambda i: values[i])
    if peak in (0, n_temps - 1):
        return legacy
    return [0, peak, n_temps - 1]


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


def _initial_spins(cfg: RunConfig, device: torch.device,
                   rng: torch.Generator) -> torch.Tensor:
    shape = (cfg.n_temps, cfg.L, cfg.L)
    if cfg.initial_state == "ordered":
        return torch.ones(shape, device=device, dtype=torch.int8)
    if cfg.initial_state == "random":
        return (
            torch.randint(0, 2, shape, generator=rng, device=device, dtype=torch.int8)
            * 2 - 1
        )
    raise ValueError(
        f"initial_state must be 'ordered' or 'random', got {cfg.initial_state!r}"
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

    spins = _initial_spins(cfg, device, g_init)
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
    # The middle frame is the run's OWN χ' peak, not the sweep's midpoint — see
    # ``snapshot_indices``. Published as ``snapshot_peak_t`` so every reader down
    # the chain (receipt → physics-latest.json → the page's caption) names the
    # temperature this run actually rendered instead of re-deriving one.
    pick_idx = snapshot_indices(cfg.n_temps, chi_abs)
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
        # Rounded to the same 3 decimals the snapshot KEYS carry, so the declared
        # temperature and the frame it names are the same number and a reader can
        # look the lattice up by it. The raw float32 grid point would print as
        # 2.299999952316284 beside a key of "T=2.300" — two spellings of one
        # temperature is how a caption drifts off its picture.
        snapshot_peak_t=float(f"{T_np[pick_idx[1]]:.3f}"),
    )
