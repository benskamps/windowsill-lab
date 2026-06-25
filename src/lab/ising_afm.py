"""Batched 2D *antiferromagnetic* Ising Metropolis simulation on GPU.

M10 flips one sign. The ferromagnetic Ising model (``ising.py``) favours *aligned*
neighbours; the antiferromagnet (AFM) sets the coupling **J = −1**, so
*anti-aligned* neighbours are favoured and the ground state is the checkerboard
**Néel** state (every spin opposite to all four neighbours), not the aligned
ferromagnet.

    E = −J · Σ_⟨ij⟩ s_i s_j      with J = −1   ⇒   E = +Σ_⟨ij⟩ s_i s_j

### Why this lands on Onsager's *same* T_c (the point of the milestone)

The square lattice is **bipartite** — two interleaved sublattices A, B (the
checkerboard). The sublattice gauge transformation ``s_i → −s_i for i ∈ B`` flips
the sign of *every* bond (each bond joins an A site to a B site), turning H_AFM
exactly into H_FM. So the AFM is the FM in disguise: it has the **same critical
temperature**, Onsager's exact

    T_N (Néel) = 2 / ln(1 + √2) ≈ 2.26919          (k_B = 1)

the same number M01/M04 verified. M10 is therefore a **framework sanity check**:
does the engine handle negative J cleanly and land on a known answer? — not new
physics.

### The right order parameter — the STAGGERED magnetization

The catch: the *uniform* magnetization ⟨|m|⟩ = |⟨s⟩| stays ≈ 0 at all T for the
AFM (the Néel ground state has equal up/down spins, so it carries no net moment).
Reading uniform m would show *nothing* through the transition and look like a
broken simulation — that is the milestone's headline trap. The order parameter is
the **staggered** magnetization, which weights each spin by its sublattice sign
ε_i = (−1)^(x+y) (+1 on A, −1 on B):

    m_s = (1/N) Σ_i ε_i s_i

In the Néel ground state every ε_i s_i = +1 (A-sites up, B-sites down — or the
global flip), so m_s → ±1 (ordered); in the disordered phase m_s → 0. Its
fluctuation is the **staggered susceptibility**

    χ_s = N·(⟨m_s²⟩ − ⟨|m_s|⟩²) / T

(the |m_s|-based form, exactly as ``ising.chi_abs`` uses ⟨|m|⟩ to kill the
spurious ±M-sign-flip variance a finite lattice can't tunnel through). χ_s peaks
at T_N — located exactly as M01 located its χ peak, just on the staggered quantity.

### Why the square checkerboard is still EXACT here (no 3-colouring)

The square lattice is **bipartite and unfrustrated**: a site's four neighbours all
live on the *other* colour, held fixed while we update one colour, so the parallel
Metropolis flip of a colour class is exact for *any* nearest-neighbour coupling,
the AFM included. This is the **easy** lattice — the M05 triangular-AFM
3-sublattice problem comes from *frustration* on a *non-bipartite* lattice (odd
cycles), which the square lattice does not have. The frustrated triangular AFM is
the later, harder M13; do not conflate them.

### The only code change from ``ising.py``

ΔE for flipping a site: ``dE = 2·J·s_i·(neighbour sum)`` with J = −1 →
**``dE = −2·s_i·nbr``** (the opposite sign of the FM engine's ``+2·s_i·nbr``).
Everything else — the batched one-temperature-per-lattice design, the red/black
checkerboard, the |m|-based susceptibility form, the specific heat — mirrors
``ising.py`` verbatim. We deliberately keep ``ising.py`` untouched and reuse its
``_neighbor_sum`` so the two engines can never drift on the neighbour stencil. A
``staggered=False`` cross-check path measures the *uniform* observables instead,
which (by the gauge duality) must equal an FM run's staggered-free observables at
the same |J| — the strongest guard against a silent sign error that secretly
reverts the model to the FM.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch

from .ising import _neighbor_sum, _checkerboard_masks


@dataclass
class AFMRunConfig:
    L: int = 128
    T_min: float = 2.0
    T_max: float = 2.6
    n_temps: int = 25
    n_burnin: int = 8000
    n_sweeps: int = 40000
    sample_every: int = 20
    seed: int = 42
    device: str = "cuda"
    J: float = -1.0              # antiferromagnetic; J=+1 recovers the FM (cross-check)

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class AFMRunResult:
    config: AFMRunConfig
    T: np.ndarray                  # (n_temps,)
    stag_mag: np.ndarray           # ⟨|m_s|⟩ per spin — the AFM order parameter, (n_temps,)
    stag_mag_err: np.ndarray       # standard error of ⟨|m_s|⟩, (n_temps,)
    chi_staggered: np.ndarray      # staggered susceptibility N·(⟨m_s²⟩−⟨|m_s|⟩²)/T, (n_temps,)
    abs_mag: np.ndarray            # UNIFORM ⟨|m|⟩ — the diagnostic that stays ≈0 (the trap), (n_temps,)
    energy: np.ndarray             # mean energy per spin, (n_temps,)
    specific_heat: np.ndarray      # C per spin = (⟨E²⟩−⟨E⟩²)·N/T², (n_temps,)
    snapshots: dict                # {temperature_key: 2D int8 lattice, sampled at end}
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "stag_mag": self.stag_mag.tolist(),
            "stag_mag_err": self.stag_mag_err.tolist(),
            "chi_staggered": self.chi_staggered.tolist(),
            "abs_mag": self.abs_mag.tolist(),
            "energy": self.energy.tolist(),
            "specific_heat": self.specific_heat.tolist(),
            "snapshots": {k: v.astype(int).tolist() for k, v in self.snapshots.items()},
            "wall_seconds": self.wall_seconds,
        }


def _stagger_sign(L: int, n_temps: int, device: torch.device) -> torch.Tensor:
    """The sublattice sign ε_i = (−1)^(x+y) as a ±1 float tensor ``(n_temps, L, L)``.

    +1 on sublattice A (x+y even), −1 on B (x+y odd) — the checkerboard parity.
    Staggered magnetization m_s = (1/N)Σ_i ε_i s_i then measures Néel order: in the
    AFM ground state ε_i s_i = +1 everywhere (each sublattice uniformly polarised
    opposite the other), so m_s → ±1, while the uniform Σ s_i → 0. This is the same
    parity the red/black checkerboard masks use, built once and broadcast.
    """
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    eps = torch.where(((ix + iy) % 2 == 0), 1.0, -1.0)
    return eps.unsqueeze(0).expand(n_temps, L, L).contiguous()


def _half_sweep(spins: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor,
                J: float, rng: torch.Generator) -> torch.Tensor:
    """Flip spins on ``mask`` using Metropolis with per-lattice inverse-T ``beta``.

    Identical in form to ``ising._half_sweep`` except the coupling sign carried in
    ΔE. For flipping site i, ΔE = 2·J·s_i·(neighbour sum); with the AFM J = −1 this
    is ``dE = −2·s_i·nbr`` (the FM engine uses J = +1 → ``+2·s_i·nbr``). The masked
    sites' neighbours all sit on the other checkerboard colour (held fixed), so the
    whole colour class flips in parallel exactly — the square lattice is bipartite,
    so this is correct for either coupling sign (no 3-colouring needed).
    """
    nbr = _neighbor_sum(spins)                          # (n_temps, L, L)
    dE = 2.0 * J * spins.float() * nbr.float()          # ΔE for flipping each site
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, -spins, spins)


def run(cfg: AFMRunConfig) -> AFMRunResult:
    """Run a batched antiferromagnetic Ising sweep: one lattice per temperature.

    Mirrors ``ising.run`` — a burn-in then a measurement phase — but with J = −1
    (antiferromagnetic) and the **staggered** order parameter m_s = (1/N)Σ ε_i s_i
    (ε = (−1)^(x+y)) as the headline observable. The staggered-χ peak locates the
    Néel temperature T_N, which by the bipartite gauge duality equals Onsager's
    exact FM T_c ≈ 2.2692. The *uniform* ⟨|m|⟩ is also measured and reported — it
    stays ≈ 0 through the transition (the Néel state carries no net moment), the
    deliberate "reading uniform m looks broken" contrast.

    Setting ``cfg.J = +1`` recovers the ferromagnet on this same engine: then the
    *uniform* ⟨|m|⟩ is the order parameter and the staggered m_s stays ≈ 0 — the
    mirror image, used by the duality cross-check test.
    """
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T

    spins = (torch.randint(0, 2, (cfg.n_temps, cfg.L, cfg.L), generator=g_init,
                           device=device, dtype=torch.int8) * 2 - 1)
    mask_a, mask_b = _checkerboard_masks(cfg.L, cfg.n_temps, device)
    eps = _stagger_sign(cfg.L, cfg.n_temps, device)

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        spins = _half_sweep(spins, beta, mask_a, cfg.J, g_step)
        spins = _half_sweep(spins, beta, mask_b, cfg.J, g_step)

    # Measurement phase
    stag_samples = []
    unif_samples = []
    energy_samples = []
    for s in range(cfg.n_sweeps):
        spins = _half_sweep(spins, beta, mask_a, cfg.J, g_step)
        spins = _half_sweep(spins, beta, mask_b, cfg.J, g_step)
        if s % cfg.sample_every == 0:
            sf = spins.float()
            # Staggered magnetization m_s = (1/N) Σ ε_i s_i (the AFM order parameter).
            stag_samples.append((eps * sf).mean(dim=(-1, -2)).cpu())
            # Uniform magnetization m = (1/N) Σ s_i (the diagnostic — stays ≈0).
            unif_samples.append(sf.mean(dim=(-1, -2)).cpu())
            # Energy per spin: -J/2 · Σ_i s_i · Σ_neighbours(s_i). The 1/2 stops each
            # bond being double-counted; with J=-1 the Néel ground state gives -2.
            e = -0.5 * cfg.J * (sf * _neighbor_sum(spins).float()).mean(dim=(-1, -2)).cpu()
            energy_samples.append(e)
    wall = time.time() - t0

    stag = torch.stack(stag_samples)            # (n_samples, n_temps)
    unif = torch.stack(unif_samples)
    energy = torch.stack(energy_samples)
    T_np = T.cpu().numpy()

    abs_stag_per_sample = stag.abs()
    stag_mag = abs_stag_per_sample.mean(dim=0).numpy()
    stag_mag_err = (abs_stag_per_sample.std(dim=0) / np.sqrt(len(stag_samples))).numpy()
    # Staggered susceptibility χ_s = N·(⟨m_s²⟩−⟨|m_s|⟩²)/T — the |m_s|-based form
    # (same sign-flip reasoning as ising.chi_abs: a finite lattice can't tunnel
    # between ±m_s in a finite run, so ⟨|m_s|⟩² removes that spurious variance). Its
    # peak locates T_N.
    chi_staggered = (cfg.L * cfg.L) * (
        stag.pow(2).mean(dim=0) - abs_stag_per_sample.mean(dim=0).pow(2)
    ).numpy() / T_np
    # The UNIFORM ⟨|m|⟩ — carried to SHOW it stays ≈0 (the AFM has no net moment).
    abs_mag = unif.abs().mean(dim=0).numpy()
    energy_mean = energy.mean(dim=0).numpy()
    # Specific heat per spin C(T) = (⟨E²⟩−⟨E⟩²)·N/T² (population variance, matching
    # the square FM + triangular + 3D engines). Peaks at T_N — the thermal cross-check.
    specific_heat = (cfg.L * cfg.L) * energy.var(dim=0, unbiased=False).numpy() / (T_np ** 2)

    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": spins[i].cpu().numpy() for i in pick_idx}

    return AFMRunResult(
        config=cfg,
        T=T_np,
        stag_mag=stag_mag,
        stag_mag_err=stag_mag_err,
        chi_staggered=chi_staggered,
        abs_mag=abs_mag,
        energy=energy_mean,
        specific_heat=specific_heat,
        snapshots=snapshots,
        wall_seconds=wall,
    )
