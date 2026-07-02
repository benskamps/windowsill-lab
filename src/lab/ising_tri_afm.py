"""Frustrated triangular-lattice *antiferromagnetic* Ising — the M13 engine.

M10 flipped J on the **square** lattice and found nothing new: the square lattice is
bipartite, so the antiferromagnet is the ferromagnet in disguise (same T_c, the Néel
state carries the order). M13 flips J on the **triangular** lattice, and everything
changes — because the triangular lattice is **non-bipartite**. Its elementary cell is
a triangle, an odd cycle: three mutually-adjacent spins that all want to disagree
*cannot* all disagree. One bond is always frustrated. There is no way to satisfy every
antiferromagnetic bond, no unique ground state, and — the headline — **no finite-T
ordering transition at all**. Instead the ground state is *macroscopically degenerate*:
an exponential number of equally-good arrangements, leaving a **residual entropy**

    S0 / N = 0.3383 k_B          (Wannier 1950, exact)

that survives to absolute zero. That number, not a T_c, is what M13 measures — by
integrating the specific heat (see ``entropy.py`` and ``m13.py``); this module only has
to produce a clean ``C(T)`` over a *wide* temperature window.

### What this engine reuses, and the one thing it flips

The correctness-critical machinery is the triangular **3-sublattice** update from
``ising_tri`` — the square red/black checkerboard is physically *wrong* on a
non-bipartite lattice (two same-colour sites end up neighbours across the kept
diagonal), so the update colours sites by ``color(i,j) = (i + 2j) % 3`` and flips one
independent colour class at a time, which requires ``3 | L``. We import
``ising_tri._neighbor_sum`` (the six-neighbour stencil) and ``ising_tri._color_masks``
(the three sublattice masks) verbatim, exactly as ``ising_afm`` reuses ``ising``'s
``_neighbor_sum`` + ``_checkerboard_masks`` — so the two triangular engines can never
drift on the geometry. The *only* change is the coupling sign carried into the flip:
ΔE for flipping site i is ``2·J·s_i·(neighbour sum)``, and with the antiferromagnet's
``J = −1`` this is ``dE = −2·s_i·nbr`` (the ferromagnetic M05 engine uses ``+2·s_i·nbr``).
Setting ``J = +1`` recovers the M05 ferromagnet on this engine — the cross-check test's
lever.

### What it measures, and why the grid is wide

Thermodynamic integration needs C from near ``T = 0`` (where ``C → 0`` and the residual
is exposed) up to high T (where ``C → 0`` again and ``S → ln 2``), so the config takes an
explicit ``T_values`` grid — ``m13`` hands it a **geometric** grid that packs points
into the low-T hump where ``C/T`` varies fastest. The observables are the energy per
spin and the specific heat ``C = (⟨E²⟩−⟨E⟩²)·N/T²`` (population variance, identical in
form to the square/triangular/3D engines); the *uniform* ``⟨|m|⟩`` is carried only as a
diagnostic (it stays small — the frustrated AFM has no net moment). The ground-state
energy per spin is a hard anchor: exactly ``−1`` in ``|J|`` units (each triangle keeps
two of its three bonds, ``Σ_bonds s_i s_j → −N``), which the cold end must approach.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch

from .ising_tri import _neighbor_sum, _color_masks


@dataclass
class TriAFMRunConfig:
    L: int = 96                       # must be a multiple of 3 (periodic 3-colour seam)
    T_min: float = 0.10               # cold edge — near T=0 to expose the residual
    T_max: float = 8.0                # hot edge — where C→0 and S→ln2
    n_temps: int = 64
    T_values: tuple | None = None     # explicit grid (overrides linspace); m13 hands a
    #                                   geometric grid, denser at low T where C/T peaks
    n_burnin: int = 8000
    n_sweeps: int = 40000
    sample_every: int = 20
    seed: int = 42
    device: str = "cuda"
    J: float = -1.0                   # antiferromagnetic; J=+1 recovers the M05 ferromagnet

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class TriAFMRunResult:
    config: TriAFMRunConfig
    T: np.ndarray               # (n_temps,), ascending as given
    energy: np.ndarray          # mean energy per spin, (n_temps,)
    energy_err: np.ndarray      # standard error of the mean energy, (n_temps,)
    specific_heat: np.ndarray   # C per spin = (⟨E²⟩−⟨E⟩²)·N/T², (n_temps,)
    abs_mag: np.ndarray         # UNIFORM ⟨|m|⟩ — the diagnostic (stays ≈0), (n_temps,)
    snapshots: dict             # {temperature_key: 2D int8 lattice, sampled at end}
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "energy": self.energy.tolist(),
            "energy_err": self.energy_err.tolist(),
            "specific_heat": self.specific_heat.tolist(),
            "abs_mag": self.abs_mag.tolist(),
            "snapshots": {k: v.astype(int).tolist() for k, v in self.snapshots.items()},
            "wall_seconds": self.wall_seconds,
        }


def _color_sweep(spins: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor,
                 J: float, rng: torch.Generator) -> torch.Tensor:
    """Metropolis flip of one triangular colour class, carrying the coupling sign ``J``.

    Identical in form to ``ising_tri._color_sweep`` except that ΔE carries ``J``: for
    flipping site i, ``dE = 2·J·s_i·(neighbour sum)``. With the antiferromagnet's
    ``J = −1`` this is ``dE = −2·s_i·nbr`` (the M05 ferromagnet uses ``+2·s_i·nbr``).
    The masked colour class's six neighbours all live in the *other two* colours, held
    fixed, so the whole class flips in parallel exactly — the guarantee the 3-colouring
    buys on the non-bipartite triangular lattice.
    """
    nbr = _neighbor_sum(spins)
    dE = 2.0 * J * spins.float() * nbr.float()
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, -spins, spins)


def _temperatures(cfg: TriAFMRunConfig, device: torch.device) -> torch.Tensor:
    """The temperature grid: the explicit ``T_values`` if given, else a linspace.

    ``m13`` supplies a geometric grid so the low-T region (where ``C/T`` has all its
    structure) is finely sampled; a bare ``lab`` run without a grid falls back to a
    uniform window, matching the other engines' ``linspace`` convention.
    """
    if cfg.T_values is not None:
        return torch.tensor(list(cfg.T_values), device=device, dtype=torch.float32)
    return torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)


def run(cfg: TriAFMRunConfig) -> TriAFMRunResult:
    """Run a batched triangular *antiferromagnetic* Ising sweep: one lattice per T.

    Mirrors ``ising_tri.run`` — a burn-in then a measurement phase sweeping the three
    colour classes per step with the six-neighbour stencil — but with ``J = −1`` and a
    *wide* temperature window, and it reads only the thermal observables (energy, C),
    since the frustrated AFM has no ordering transition to locate. C(T) is the input to
    the thermodynamic-integration residual-entropy measurement in ``m13``.
    """
    if cfg.L % 3 != 0:
        raise ValueError(
            f"L must be a multiple of 3 for the triangular 3-colour update (got {cfg.L}); "
            f"the (i+2j)%3 colouring only wraps cleanly across the periodic seam when 3 | L."
        )
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = _temperatures(cfg, device)
    n_temps = int(T.shape[0])
    beta = 1.0 / T

    spins = (torch.randint(0, 2, (n_temps, cfg.L, cfg.L), generator=g_init,
                           device=device, dtype=torch.int8) * 2 - 1)
    masks = _color_masks(cfg.L, n_temps, device)

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        for mask in masks:
            spins = _color_sweep(spins, beta, mask, cfg.J, g_step)

    # Measurement phase
    energy_samples = []
    unif_samples = []
    for s in range(cfg.n_sweeps):
        for mask in masks:
            spins = _color_sweep(spins, beta, mask, cfg.J, g_step)
        if s % cfg.sample_every == 0:
            sf = spins.float()
            # Energy per spin: −J/2 · Σ_i s_i · Σ_neighbours(s_i). The 1/2 stops each of
            # the 3N bonds being counted from both ends (6 neighbours / 2). At the
            # frustrated ground state Σ_bonds s_i s_j → −N, so e → −1 in |J| units.
            e = -0.5 * cfg.J * (sf * _neighbor_sum(spins).float()).mean(dim=(-1, -2)).cpu()
            energy_samples.append(e)
            # Uniform ⟨|m|⟩ — carried to SHOW it stays ≈0 (the AFM has no net moment).
            unif_samples.append(sf.mean(dim=(-1, -2)).cpu())
    wall = time.time() - t0

    energy = torch.stack(energy_samples)        # (n_samples, n_temps)
    unif = torch.stack(unif_samples)
    T_np = T.cpu().numpy()

    energy_mean = energy.mean(dim=0).numpy()
    energy_err = (energy.std(dim=0) / np.sqrt(len(energy_samples))).numpy()
    # Specific heat per spin C(T) = (⟨E²⟩−⟨E⟩²)·N/T² (population variance, matching the
    # square FM + triangular FM + 3D engines). A broad hump, NOT a divergence — the
    # frustrated AFM has no transition; the area under C/T is what carries the physics.
    specific_heat = (cfg.L * cfg.L) * energy.var(dim=0, unbiased=False).numpy() / (T_np ** 2)
    abs_mag = unif.abs().mean(dim=0).numpy()

    pick_idx = [0, n_temps // 2, n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": spins[i].cpu().numpy() for i in pick_idx}

    return TriAFMRunResult(
        config=cfg,
        T=T_np,
        energy=energy_mean,
        energy_err=energy_err,
        specific_heat=specific_heat,
        abs_mag=abs_mag,
        snapshots=snapshots,
        wall_seconds=wall,
    )
