"""Batched 3D simple-cubic Ising Metropolis simulation (NumPy, CPU).

Phase 2 leaves the exactly-solved 2D plane and steps into three dimensions —
where there is *no* closed-form solution. The simple-cubic Ising critical
temperature is known only numerically, to high precision, from decades of Monte
Carlo and series work:

    T_c / J ≈ 4.5115  (≈ 4.51152, the modern MC/series benchmark)

That number is M06's calibration target. We locate it the same way M01 located
the 2D T_c: run a batch of independent L×L×L lattices, one temperature each, and
find where the magnetic susceptibility peaks.

### Why NumPy here instead of the torch engine

``ising.py``/``wolff.py`` are 2D-specific (their ``_neighbor_sum`` rolls over two
axes). Rather than special-case them, M06 ships a small self-contained 3D engine.
It is **CPU NumPy** on purpose: the lab's GPU is a 2D-tuned ROCm card and a long
CUDA sweep once crashed this machine (see the GPU-safety note in ``m03.py``); a
modest 3D sweep (L = 8–12, a few thousand sweeps) finishes on the CPU in a few
minutes, which keeps the milestone *verifiable in one sitting* with no device
risk. The design still mirrors ``ising.run``: ``n_temps`` independent lattices
updated in parallel via a vectorised checkerboard (red/black) sweep.

The 3D checkerboard works exactly as in 2D: colour each site by the parity of
``(x+y+z)``. On a simple cubic lattice with periodic boundaries every site's six
nearest neighbours have the opposite parity, so all same-colour sites can be
proposed for a flip simultaneously — their ΔE depends only on the *other*
colour, which is held fixed during that half-sweep. (This requires even L so the
checkerboard wraps consistently across the periodic seam.)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class Run3DConfig:
    L: int = 10
    T_min: float = 4.0
    T_max: float = 5.0
    n_temps: int = 21
    n_burnin: int = 3000
    n_sweeps: int = 8000
    sample_every: int = 10
    seed: int = 42

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class Run3DResult:
    config: Run3DConfig
    T: np.ndarray              # (n_temps,)
    abs_mag: np.ndarray        # mean |m| per spin, (n_temps,)
    abs_mag_err: np.ndarray    # standard error of mean |m|, (n_temps,)
    chi: np.ndarray            # |m|-based susceptibility per spin, (n_temps,)
    energy: np.ndarray         # mean energy per spin, (n_temps,)
    specific_heat: np.ndarray  # C per spin = (⟨E²⟩−⟨E⟩²)·N/T², (n_temps,)
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "abs_mag": self.abs_mag.tolist(),
            "abs_mag_err": self.abs_mag_err.tolist(),
            "chi": self.chi.tolist(),
            "energy": self.energy.tolist(),
            "specific_heat": self.specific_heat.tolist(),
            "wall_seconds": self.wall_seconds,
        }


def _checkerboard_masks(L: int) -> tuple[np.ndarray, np.ndarray]:
    """Parity masks for a single L³ lattice: ``(even, odd)`` over ``(x+y+z)%2``."""
    ix, iy, iz = np.indices((L, L, L))
    even = ((ix + iy + iz) % 2 == 0)
    return even, ~even


def _neighbor_sum(spins: np.ndarray) -> np.ndarray:
    """Sum of the six nearest neighbours on a periodic simple-cubic lattice.

    ``spins`` has shape ``(n_temps, L, L, L)``; rolls wrap (periodic BC).
    """
    return (
        np.roll(spins, 1, axis=-3) + np.roll(spins, -1, axis=-3)
        + np.roll(spins, 1, axis=-2) + np.roll(spins, -1, axis=-2)
        + np.roll(spins, 1, axis=-1) + np.roll(spins, -1, axis=-1)
    )


def _half_sweep(spins, beta, mask, rng):
    """Metropolis flip of the ``mask`` sublattice (one colour), all temps at once.

    ``spins`` is int8 ±1, shape ``(n_temps, L, L, L)``; ``beta`` is ``(n_temps,)``;
    ``mask`` is ``(L, L, L)`` boolean broadcast across the batch.
    """
    nbr = _neighbor_sum(spins)                       # (n_temps, L, L, L)
    dE = 2.0 * spins * nbr                            # ΔE for flipping each site (J=1)
    prob = np.exp(-beta[:, None, None, None] * dE)    # accept prob (clipped below)
    rand = rng.random(spins.shape, dtype=np.float64)
    flip = mask[None] & (rand < prob)
    spins[flip] *= -1
    return spins


def run(cfg: Run3DConfig) -> Run3DResult:
    """Run a batched 3D Ising sweep: one L³ lattice per temperature, in parallel.

    Returns per-temperature ⟨|m|⟩, the |m|-susceptibility χ = N(⟨m²⟩−⟨|m|⟩²)/T,
    energy per spin, and the specific heat C = N(⟨e²⟩−⟨e⟩²)/T². The χ peak
    locates the (finite-size) critical temperature — M06's headline observable,
    compared against the MC benchmark T_c ≈ 4.5115.
    """
    if cfg.L % 2 != 0:
        raise ValueError(f"L must be even for the 3D checkerboard (got {cfg.L})")
    rng = np.random.default_rng(cfg.seed)
    N = cfg.L ** 3

    T = np.linspace(cfg.T_min, cfg.T_max, cfg.n_temps).astype(np.float64)
    beta = 1.0 / T

    spins = (rng.integers(0, 2, size=(cfg.n_temps, cfg.L, cfg.L, cfg.L), dtype=np.int8) * 2 - 1)
    mask_a, mask_b = _checkerboard_masks(cfg.L)

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        spins = _half_sweep(spins, beta, mask_a, rng)
        spins = _half_sweep(spins, beta, mask_b, rng)

    # Measurement phase: accumulate per-sample magnetization and energy.
    mag_samples = []
    e_samples = []
    for s in range(cfg.n_sweeps):
        spins = _half_sweep(spins, beta, mask_a, rng)
        spins = _half_sweep(spins, beta, mask_b, rng)
        if s % cfg.sample_every == 0:
            sf = spins.astype(np.float64)
            mag_samples.append(sf.mean(axis=(-1, -2, -3)))                   # (n_temps,)
            # Energy per spin: -J/2 · Σ_i s_i · Σ_neighbors(s_i); the 1/2 stops
            # each of the 3N bonds being counted from both ends.
            e = -0.5 * (sf * _neighbor_sum(spins)).mean(axis=(-1, -2, -3))
            e_samples.append(e)
    wall = time.time() - t0

    mag = np.asarray(mag_samples)        # (n_samples, n_temps)
    energy = np.asarray(e_samples)       # (n_samples, n_temps)
    n_s = mag.shape[0]

    abs_mag_per = np.abs(mag)
    abs_mag = abs_mag_per.mean(axis=0)
    abs_mag_err = abs_mag_per.std(axis=0) / np.sqrt(n_s)
    # |m|-based susceptibility — the finite-size-scaling–appropriate observable,
    # for the same sign-flip reason ``ising.chi_abs`` documents in 2D.
    chi = N * (np.square(mag).mean(axis=0) - np.square(abs_mag_per.mean(axis=0))) / T
    energy_mean = energy.mean(axis=0)
    specific_heat = N * energy.var(axis=0) / (T ** 2)

    return Run3DResult(
        config=cfg,
        T=T,
        abs_mag=abs_mag,
        abs_mag_err=abs_mag_err,
        chi=chi,
        energy=energy_mean,
        specific_heat=specific_heat,
        wall_seconds=wall,
    )
