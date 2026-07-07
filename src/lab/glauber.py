"""Batched 2D Ising **Glauber (heat-bath) dynamics** on GPU — the non-equilibrium engine.

Every prior milestone samples an *equilibrium* ensemble: the sampler only has to reach
the Boltzmann distribution, so cluster moves (Wolff) that decorrelate fast are welcome.
M15 is different in kind — it studies **how the system gets there**. After a quench from
``T = ∞`` (a random lattice) to ``T < T_c`` the system is *not* in equilibrium: it coarsens,
growing ordered domains whose typical size ``L_domain(t)`` grows as a power of the real
Monte-Carlo time. So the dynamics must be a **physical local rule** and MC time is the
observable's own axis — a cluster update would flip whole domains at once and destroy the
very coarsening we are trying to measure. Hence single-spin Glauber, never Wolff.

### The rule

Glauber / heat-bath dynamics for the Ising model: pick a site, and set its new value from
the local heat bath *independent of its current value* — with the local field
``h = Σ_neighbours s`` (square lattice, ``J = 1``),

    P(s → +1) = e^{βh} / (e^{βh} + e^{−βh}) = 1 / (1 + e^{−2βh}) = σ(2βh),

and ``s → −1`` otherwise. (This is the standard Glauber choice for Ising; its transition
rate ``w = ½[1 − s·tanh(βh)]`` is the ``e^{−x}/(1+e^{−x})`` form written for a spin flip.)
One **sweep** — the unit of MC time on the x-axis of every M15 plot — is one heat-bath
touch of every site, done as two checkerboard half-sweeps so a whole sublattice updates in
one tensor op (the red/black scheme reused from ``ising.py``; on a bipartite square lattice
each site's neighbours are all the other colour, so a synchronous half-lattice update is
exact detailed-balance Glauber, not an approximation).

A *batch* dimension runs many independent random initial conditions (seeds) at the **same**
temperature — the domain length and energy are averaged over that ensemble to tame the
run-to-run noise in a single coarsening lattice.

### The domain-length estimators (two, cross-checked)

* **Correlation length ``L_c(t)``** (preferred): the equal-time two-point function
  ``G(r,t) = ⟨s_i s_{i+r}⟩`` computed by Wiener–Khinchin (an FFT power spectrum, then an
  inverse FFT — the periodic autocorrelation), axis-averaged and normalised to ``G(0)=1``.
  The domain size is the first ``r`` where ``G`` falls through a fixed threshold
  ``G(L_c) = ½`` (linear-interpolated). A textbook coarsening estimator.
* **Energy length ``L_e(t)``** (cross-check): the excess energy over equilibrium is carried
  entirely by domain walls, whose density ``∝ 1/L``, so ``L_e(t) ∝ 1/(E(t) − E_eq)``. The
  equilibrium energy ``E_eq(T)`` is measured here from a reference run started in the ground
  state and equilibrated at the quench ``T`` — self-consistent with the same dynamics. Only
  the *exponent* is compared, so the unknown proportionality constant drops out.

Allen–Cahn (curvature-driven, non-conserved order parameter) predicts ``L_domain(t) ∼ t^{1/2}``.
``m15.py`` fits the exponent in a scaling window (past the early transient, below finite-size
saturation) and reports it honestly with its fit uncertainty — a clean ½ is *not* assumed.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
import torch

from .onsager import T_C


@dataclass
class QuenchConfig:
    L: int = 256                 # lattice side (periodic square)
    T: float = 1.5               # quench temperature (below T_c ≈ 2.269; default ≈0.66·T_c)
    n_seeds: int = 32            # independent random initial conditions, averaged
    t_max: int = 4000            # final Monte-Carlo time (sweeps) after the quench
    n_times: int = 44            # number of (log-spaced) measurement times
    t_first: int = 1             # first measurement sweep
    eq_burnin: int = 4000        # reference-equilibrium burn-in sweeps (for E_eq)
    eq_sample: int = 2000        # reference-equilibrium averaging sweeps (for E_eq)
    seed: int = 42
    device: str = "cuda"

    def temperature_ratio(self) -> float:
        return self.T / float(T_C)


@dataclass
class QuenchResult:
    config: QuenchConfig
    times: np.ndarray            # measurement sweeps t, ascending (n_times,)
    L_corr: np.ndarray           # correlation domain length L_c(t) (n_times,)
    L_energy: np.ndarray         # energy domain length L_e(t) ∝ 1/(E−E_eq) (n_times,)
    energy: np.ndarray           # mean energy per spin E(t) (n_times,)
    excess_energy: np.ndarray    # E(t) − E_eq (n_times,)
    e_eq: float                  # measured equilibrium energy per spin at the quench T
    G_snapshots: dict            # {t_key: [G(r) for r in 0..L//2]} at a few times (for the plot)
    snapshots: dict              # {t_key: 2D int8 lattice} for the coarsening gallery (seed 0)
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": {
                "L": self.config.L, "T": self.config.T, "n_seeds": self.config.n_seeds,
                "t_max": self.config.t_max, "n_times": self.config.n_times,
                "t_first": self.config.t_first, "eq_burnin": self.config.eq_burnin,
                "eq_sample": self.config.eq_sample, "seed": self.config.seed,
                "device": self.config.device,
            },
            "times": self.times.tolist(),
            "L_corr": self.L_corr.tolist(),
            "L_energy": self.L_energy.tolist(),
            "energy": self.energy.tolist(),
            "excess_energy": self.excess_energy.tolist(),
            "e_eq": self.e_eq,
            "G_snapshots": {k: list(map(float, v)) for k, v in self.G_snapshots.items()},
            "snapshots": {k: v.astype(int).tolist() for k, v in self.snapshots.items()},
            "wall_seconds": self.wall_seconds,
        }


def _checkerboard_masks(L: int, n_seeds: int, device: torch.device):
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    a = ((ix + iy) % 2 == 0).unsqueeze(0).expand(n_seeds, L, L).contiguous()
    return a, ~a


def _neighbor_sum(spins: torch.Tensor) -> torch.Tensor:
    """Σ of the four von-Neumann neighbours (periodic), reused verbatim from ``ising.py``."""
    return (
        torch.roll(spins, 1, dims=-2)
        + torch.roll(spins, -1, dims=-2)
        + torch.roll(spins, 1, dims=-1)
        + torch.roll(spins, -1, dims=-1)
    )


def heatbath_prob_up(neighbor_sum: torch.Tensor, beta: float) -> torch.Tensor:
    """Glauber/heat-bath probability that a site becomes ``+1``: σ(2β·h), h = neighbour sum.

    Independent of the site's current value — the defining property of heat-bath dynamics.
    Isolated as a named function so the test can brute-force it against the closed form
    ``1/(1+e^{−2βh})`` for every reachable integer field ``h ∈ {−4,−2,0,2,4}``.
    """
    return torch.sigmoid(2.0 * beta * neighbor_sum.float())


def _half_sweep_heatbath(spins: torch.Tensor, beta: float, mask: torch.Tensor,
                         rng: torch.Generator) -> torch.Tensor:
    """One heat-bath half-sweep on ``mask`` — set masked sites to +1 w.p. σ(2βh), else −1."""
    p_up = heatbath_prob_up(_neighbor_sum(spins), beta)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    new_up = rand < p_up                                   # True → +1, False → −1
    new_spins = torch.where(new_up, torch.ones_like(spins), -torch.ones_like(spins))
    return torch.where(mask, new_spins, spins)


def _energy_per_spin(spins: torch.Tensor) -> torch.Tensor:
    """Ising energy per spin, per lattice in the batch: −½·mean(s·Σ_neighbours s)."""
    sf = spins.float()
    return -0.5 * (sf * _neighbor_sum(spins).float()).mean(dim=(-1, -2))


def equal_time_correlation(spins: torch.Tensor) -> torch.Tensor:
    """Axis-averaged, normalised equal-time correlation ``G(r)`` for r = 0 … L//2.

    Wiener–Khinchin: the periodic autocorrelation is the inverse FFT of the power spectrum.
    ``G2[dx,dy] = (1/N) Σ_ij s_ij s_{i+dx,j+dy}`` (averaged over the seed batch); ``G2[0,0]=1``
    since ``s²=1``. We average the two lattice axes ``G2[r,0]`` and ``G2[0,r]`` and normalise
    to ``G(0)=1``. Returns a 1-D tensor of length ``L//2 + 1`` on the input device.
    """
    B, L, _ = spins.shape
    f = torch.fft.fft2(spins.float())
    power = (f * f.conj()).real
    g2 = torch.fft.ifft2(power).real / (L * L)            # (B, L, L)
    g2 = g2.mean(dim=0)                                   # (L, L)
    r_max = L // 2
    g_axis = 0.5 * (g2[: r_max + 1, 0] + g2[0, : r_max + 1])
    g0 = g_axis[0].clamp_min(1e-12)
    return g_axis / g0


def domain_length_from_G(G, threshold: float = 0.5) -> float:
    """First ``r`` where the normalised ``G(r)`` falls through ``threshold`` (linear-interp).

    The standard half-height correlation-length estimator of the domain size. ``G`` is a 1-D
    sequence with ``G[0]=1`` decreasing with ``r``. Returns a float ``r`` (lattice units). If
    ``G`` never drops below the threshold in range (domains as large as the measured window),
    returns the last ``r`` — a saturation flag the scaling-window fit then excludes. Stdlib
    math only, so ``check_m15`` re-derives it identically from the report's stored ``G``.
    """
    g = [float(x) for x in G]
    for r in range(1, len(g)):
        if g[r] < threshold:
            g0, g1 = g[r - 1], g[r]
            if g0 == g1:
                return float(r)
            return float((r - 1) + (g0 - threshold) / (g0 - g1))
    return float(len(g) - 1)


def _log_spaced_times(t_first: int, t_max: int, n: int) -> list[int]:
    """Unique, ascending, log-spaced integer sweep counts in ``[t_first, t_max]``."""
    lo, hi = math.log(t_first), math.log(t_max)
    raw = [int(round(math.exp(lo + (hi - lo) * i / (n - 1)))) for i in range(n)]
    out: list[int] = []
    for t in raw:
        t = max(t_first, min(t_max, t))
        if not out or t > out[-1]:
            out.append(t)
    return out


def _reference_equilibrium_energy(cfg: QuenchConfig, device: torch.device,
                                  beta: float, g: torch.Generator) -> float:
    """Equilibrium energy per spin ``E_eq(T)`` at the quench temperature.

    Started from the *ordered* ground state (all +1) and equilibrated with the SAME heat-bath
    dynamics, then averaged — a self-consistent reference for the excess-energy length, rather
    than an external analytic value. A handful of seeds is plenty: ``E`` is intensive and the
    lattice is large, so the ensemble/spatial average is already smooth.
    """
    n = min(cfg.n_seeds, 8)
    spins = torch.ones((n, cfg.L, cfg.L), device=device, dtype=torch.int8)
    mask_a, mask_b = _checkerboard_masks(cfg.L, n, device)
    for _ in range(cfg.eq_burnin):
        spins = _half_sweep_heatbath(spins, beta, mask_a, g)
        spins = _half_sweep_heatbath(spins, beta, mask_b, g)
    acc = 0.0
    for _ in range(cfg.eq_sample):
        spins = _half_sweep_heatbath(spins, beta, mask_a, g)
        spins = _half_sweep_heatbath(spins, beta, mask_b, g)
        acc += float(_energy_per_spin(spins).mean().cpu())
    return acc / cfg.eq_sample


def run(cfg: QuenchConfig) -> QuenchResult:
    """Quench a random lattice to ``T < T_c`` and track the domain length vs MC time.

    Measures ``E_eq(T)`` from an equilibrated reference first, then evolves ``n_seeds`` random
    lattices under Glauber dynamics, sampling ``G(r,t)`` (→ correlation length) and ``E(t)``
    (→ energy length) at log-spaced times. Returns the raw ``L(t)`` curves; the exponent fit
    lives in ``m15.py`` so the engine stays a pure measurement instrument.
    """
    device = torch.device(cfg.device)
    beta = 1.0 / cfg.T
    g_ref = torch.Generator(device=device).manual_seed(cfg.seed + 7)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    t0 = time.time()
    e_eq = _reference_equilibrium_energy(cfg, device, beta, g_ref)

    # Random T=∞ start: each site ±1 with equal probability, one lattice per seed.
    spins = (torch.randint(0, 2, (cfg.n_seeds, cfg.L, cfg.L), generator=g_init,
                           device=device, dtype=torch.int8) * 2 - 1)
    mask_a, mask_b = _checkerboard_masks(cfg.L, cfg.n_seeds, device)

    # Gallery snapshots are stride-downsampled to a viewable ≤128 px (matching the M01 gallery)
    # so the committed report JSON stays light — a full 512² lattice per snapshot would bloat it
    # ~20×. Striding keeps crisp ±1 domains, and the coarsening structure is far larger than the
    # stride, so the downsampled field reads identically.
    snap_stride = max(1, -(-cfg.L // 128))   # ceil(L/128)

    meas_times = _log_spaced_times(cfg.t_first, cfg.t_max, cfg.n_times)
    meas_set = set(meas_times)
    # A few times get a saved lattice snapshot + full G(r) curve for the report gallery.
    snap_targets = sorted({meas_times[i] for i in
                           (0, len(meas_times) // 3, 2 * len(meas_times) // 3, len(meas_times) - 1)})

    times: list[int] = []
    L_corr: list[float] = []
    L_energy: list[float] = []
    energy: list[float] = []
    excess: list[float] = []
    G_snapshots: dict = {}
    snapshots: dict = {}

    for t in range(1, cfg.t_max + 1):
        spins = _half_sweep_heatbath(spins, beta, mask_a, g_step)
        spins = _half_sweep_heatbath(spins, beta, mask_b, g_step)
        if t in meas_set:
            G = equal_time_correlation(spins).cpu().numpy()
            Lc = domain_length_from_G(G, threshold=0.5)
            e = float(_energy_per_spin(spins).mean().cpu())
            dE = e - e_eq
            # L_e ∝ 1/ΔE; guard the (rare) non-positive ΔE at late times / noise with NaN so
            # the fit window — which excludes saturated late times anyway — simply drops it.
            Le = (1.0 / dE) if dE > 1e-9 else float("nan")
            times.append(t)
            L_corr.append(Lc)
            L_energy.append(Le)
            energy.append(e)
            excess.append(dE)
            if t in snap_targets:
                G_snapshots[f"t={t}"] = [float(x) for x in G]
                snapshots[f"t={t}"] = spins[0, ::snap_stride, ::snap_stride].cpu().numpy()

    return QuenchResult(
        config=cfg,
        times=np.array(times, dtype=float),
        L_corr=np.array(L_corr, dtype=float),
        L_energy=np.array(L_energy, dtype=float),
        energy=np.array(energy, dtype=float),
        excess_energy=np.array(excess, dtype=float),
        e_eq=e_eq,
        G_snapshots=G_snapshots,
        snapshots=snapshots,
        wall_seconds=time.time() - t0,
    )
