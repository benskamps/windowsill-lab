"""Batched 2D *honeycomb* (hexagonal)-lattice Ising Metropolis simulation on GPU.

M05's second half. ``ising_tri`` left the square lattice for the triangular one
(six neighbours, T_c = 4/ln 3). This module goes the other way, to the
triangular lattice's **dual** — the honeycomb, where every site has only

    z = 3 neighbours

and the exact critical temperature is again known in closed form:

    T_c = 2 / ln(2 + √3) ≈ 1.518651        (ferromagnetic, k_B = J = 1)

Three exact T_c on three geometries, one universality class: that is the whole
point of M05. The honeycomb number is the *smallest* of the three because each
spin has the fewest neighbours holding it in line, so thermal noise breaks the
order at a lower temperature (z = 3 → 1.5187, z = 4 → 2.2692, z = 6 → 3.6410).

### The brick-wall embedding

A honeycomb is not a subgraph of the square grid the way the triangular lattice
is a *supergraph* of it, so we lay it out as a **brick wall** on an L×L integer
array: keep both horizontal neighbours, and give each site exactly *one* vertical
partner, chosen by the parity of ``i + j``::

    (i, j−1),  (i, j+1),  and  (i+1, j) if (i+j) is even else (i−1, j)

That parity rule is what makes the third bond a *bond* rather than a broken
half-edge: a site at even parity reaches up to ``(i+1, j)``, whose own parity is
odd, so it reaches back down to ``(i, j)``. The relation is symmetric by
construction, every site has degree exactly 3, and the vertical bonds form the
staggered "mortar joints" of a brick wall — which is the honeycomb, redrawn.

### Why this is *simpler* than the triangular engine

``ising_tri`` needed a **3-sublattice** update because the triangular lattice is
non-bipartite (its triangles are odd cycles), so no 2-colouring can separate
neighbours. The honeycomb has **no odd cycles at all** — its girth is 6 — so it
*is* bipartite, and the plain square-lattice checkerboard

    color(i, j) = (i + j) % 2

is already a valid 2-colouring here: both horizontal neighbours and the single
vertical partner flip the parity of ``i + j``. So the exact parallel update is
``ising.py``'s red/black one, unchanged. This engine **removes** the hard part of
``ising_tri`` rather than adding to it; the only real physics delta is the
neighbour sum.

It also drops the awkward ``3 | L`` constraint. What it needs instead is **even
L** — otherwise the row-direction wrap glues the parity rule to itself
inconsistently at the seam (site ``(L−1, j)`` would reach ``(0, j)`` while
``(0, j)`` reached ``(1, j)``, leaving a dangling non-reciprocal half-bond) and
the column wrap would put two same-colour sites side by side. L = 128 — the
square engine's own default — is even, so unlike the triangular L = 129 there is
no seam compromise to explain.

Everything else mirrors ``ising.py`` / ``ising_tri``: a batch of ``n_temps``
independent lattices, one temperature each, run in parallel; the |m|-based
susceptibility ``chi_abs`` and the specific heat ``C = (⟨E²⟩−⟨E⟩²)·N/T²``
computed exactly as the other engines do, with the energy per spin still
carrying the 0.5 that stops each of the 3N/2 bonds being counted from both ends.
The all-aligned ground state therefore sits at **E = −1.5 per spin** (not the
square lattice's −2.0 or the triangular −3.0) — a cheap, exact, testable
signature that the coordination number really is 3.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch


# Exact honeycomb-lattice 2D Ising critical temperature (k_B = J = 1).
# T_c = 2 / ln(2 + √3) ≈ 1.518651 — the dual of the triangular 4/ln 3.
TC_HEX = 2.0 / np.log(2.0 + np.sqrt(3.0))


@dataclass
class HexRunConfig:
    L: int = 128              # must be even (brick-wall seam + checkerboard wrap)
    T_min: float = 1.35
    T_max: float = 1.70
    n_temps: int = 25
    n_burnin: int = 8000
    n_sweeps: int = 40000
    sample_every: int = 20
    seed: int = 42
    device: str = "cuda"
    # "ordered" (all +1) or "random" (infinite-temperature). Defaults to ORDERED
    # here, unlike ``ising.RunConfig`` which defaults to random and lets the CLI
    # opt in — because the honeycomb reproduced the 2026-07-23 M01 metastability
    # incident on its very first L=128 run. See ``_initial_spins``.
    initial_state: str = "ordered"

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class HexRunResult:
    config: HexRunConfig
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


def require_even_L(L: int) -> None:
    """The brick-wall honeycomb only closes on a torus when L is even.

    Two independent things break at odd L, and both are silent — the simulation
    would still *run* and produce a plausible-looking curve at the wrong T_c:

    1. **The vertical bond stops being reciprocal at the row seam.** ``(L−1, j)``
       picks its partner by the parity of ``L−1+j``; ``(0, j)`` picks by ``j``.
       For even L those parities are opposite, so exactly one of the two reaches
       across the seam to the other. For odd L they agree, and the pair either
       both reach away from the seam (a missing bond) or both reach into it (a
       doubled one) — degree 2 and degree 4 sites appear.
    2. **The ``(i+j)%2`` checkerboard stops wrapping in the column direction**:
       ``(i, L−1)`` and ``(i, 0)`` are horizontal neighbours and would share a
       colour, so the parallel red/black update would no longer be exact.

    Enforced rather than warned about, the way ``ising_tri`` enforces ``3 | L``.
    """
    if L % 2 != 0:
        raise ValueError(
            f"L must be even for the honeycomb brick-wall lattice (got {L}); "
            f"odd L breaks the parity rule's reciprocity at the periodic row "
            f"seam and puts two same-colour sites next to each other at the "
            f"column seam."
        )


def neighbor_coords(L: int) -> np.ndarray:
    """The three honeycomb neighbours of every site, as an ``(L, L, 3, 2)`` array.

    The explicit, loop-written ground truth for the geometry — deliberately
    *not* the vectorised form the engine uses, so the tests can pin the torch
    ``_neighbor_sum`` against an independent construction instead of against
    itself. Coordinates are already wrapped modulo L (periodic boundaries).

    Neighbour order is ``[(i, j−1), (i, j+1), vertical partner]``.
    """
    require_even_L(L)
    coords = np.zeros((L, L, 3, 2), dtype=np.int64)
    for i in range(L):
        for j in range(L):
            # The parity rule: even (i+j) reaches up, odd (i+j) reaches down.
            # Reciprocal because the partner's parity is always the opposite one.
            vert_i = (i + 1) % L if (i + j) % 2 == 0 else (i - 1) % L
            coords[i, j, 0] = (i, (j - 1) % L)
            coords[i, j, 1] = (i, (j + 1) % L)
            coords[i, j, 2] = (vert_i, j)
    return coords


def _vertical_parity_mask(L: int, device: torch.device) -> torch.Tensor:
    """``True`` where ``(i + j)`` is even — the sites whose partner is ``(i+1, j)``.

    Doubles as the red/black sublattice mask: the honeycomb is bipartite under
    exactly this colouring, so ``ising.py``'s checkerboard update is already exact
    here (no 3-colouring, unlike ``ising_tri``).
    """
    ix = torch.arange(L, device=device).view(L, 1)
    iy = torch.arange(L, device=device).view(1, L)
    return ((ix + iy) % 2 == 0)


def _neighbor_sum(spins: torch.Tensor, even: torch.Tensor) -> torch.Tensor:
    """Sum of the three honeycomb neighbours on a periodic brick-wall lattice.

    ``spins`` is ``(n_temps, L, L)``; ``even`` is the ``(L, L)`` parity mask from
    ``_vertical_parity_mask``. ``torch.roll(x, +1, dim)`` puts ``x[i−1]`` at
    position ``i`` and ``torch.roll(x, −1, dim)`` puts ``x[i+1]`` there, so the
    parity-selected vertical term is ``where(even, roll(−1), roll(+1))`` — reach
    *up* on even parity, *down* on odd. Two horizontal neighbours, one vertical:
    coordination 3, never 4.
    """
    horizontal = torch.roll(spins, 1, dims=-1) + torch.roll(spins, -1, dims=-1)
    up = torch.roll(spins, -1, dims=-2)     # value at (i+1, j)
    down = torch.roll(spins, 1, dims=-2)    # value at (i−1, j)
    vertical = torch.where(even, up, down)
    return horizontal + vertical


def _initial_spins(cfg: HexRunConfig, device: torch.device,
                   rng: torch.Generator) -> torch.Tensor:
    """The starting configuration — and on this lattice the default is ``ordered``.

    ``ising.RunConfig`` defaults to ``random`` and lets the long-running M01
    heartbeat opt into ``ordered``; this engine flips that default, and the reason
    is a measured failure rather than a preference.

    **The 2026-08-11 incident.** The first canonical honeycomb run (L=128, random
    start, 8 000 burn-in sweeps) came back with a χ peak at T = 1.379 — 9.2 % below
    the exact 1.5187 — and it was not a geometry bug. Twenty-four of the
    twenty-five lattices were textbook: ⟨|m|⟩ fell smoothly 0.921 → 0.044 and χ
    peaked cleanly near 1.54. The twenty-fifth, at T = 1.3792 deep in the *ordered*
    phase, sat at ⟨|m|⟩ = 0.573 between neighbours of 0.913 and 0.895, with an
    error bar 30× theirs and χ = 1164 against neighbours below 1.3. It was a single
    lattice frozen in a system-spanning stripe domain, flipping during the
    measurement window — the identical shape to M01's campaign pass 6 (see
    ``tests/test_m01_equilibration.py``), and the bare argmax crowned it.

    Why this lattice is more prone to it than the square or triangular engines:
    local Metropolis coarsens domains diffusively, so clearing a wrapping domain
    wall takes O(L²) sweeps, and with only **three** bonds per site — half the
    triangular coordination — a wall costs less energy and dissolves more slowly.
    An ordered start has no domains to remove, so the ordered phase equilibrates
    almost immediately, while above T_c it disorders within a few hundred sweeps
    (verified by ``test_ordered_start_still_disorders_above_tc``). Both starts
    sample the same equilibrium; only one of them gets there in the burn-in.
    """
    shape = (cfg.n_temps, cfg.L, cfg.L)
    if cfg.initial_state == "ordered":
        return torch.ones(shape, device=device, dtype=torch.int8)
    if cfg.initial_state == "random":
        return (torch.randint(0, 2, shape, generator=rng, device=device,
                              dtype=torch.int8) * 2 - 1)
    raise ValueError(
        f"initial_state must be 'ordered' or 'random', got {cfg.initial_state!r}"
    )


def _half_sweep(spins: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor,
                even: torch.Tensor, rng: torch.Generator) -> torch.Tensor:
    """Metropolis flip of one checkerboard colour with per-lattice inverse-T ``beta``.

    Identical in form to ``ising._half_sweep`` — the honeycomb is bipartite, so the
    2-colour update is exact with no modification. Only the neighbour stencil
    differs (3 parity-selected neighbours, not 4 fixed ones).
    """
    nbr = _neighbor_sum(spins, even)                    # (n_temps, L, L)
    dE = 2.0 * spins.float() * nbr.float()              # ΔE for flipping each site (J=1)
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=rng, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, -spins, spins)


def energy_per_spin(spins: torch.Tensor, even: torch.Tensor) -> torch.Tensor:
    """Mean energy per spin, ``E = −(J/2)·⟨s_i · Σ_neighbours s⟩`` with J = 1.

    The 0.5 stops each of the 3N/2 bonds being counted from both ends. The
    all-aligned ground state therefore sits at exactly **−1.5** per spin — the
    coordination number halved — against the square lattice's −2.0 and the
    triangular −3.0. That number is the cheapest possible exact check that the
    geometry is really the honeycomb and not something with an extra bond.
    """
    sf = spins.float()
    return -0.5 * (sf * _neighbor_sum(spins, even).float()).mean(dim=(-1, -2))


def run(cfg: HexRunConfig) -> HexRunResult:
    """Run a batched honeycomb Ising sweep: one lattice per temperature.

    Mirrors ``ising_tri.run`` — a burn-in then a measurement phase sampling ⟨|m|⟩
    and the energy — but sweeps the *two* checkerboard colours per step (not
    three), using the 3-neighbour parity-selected sum. The χ_abs peak locates the
    (finite-size) critical temperature, compared against the exact honeycomb
    T_c = 2/ln(2+√3).
    """
    require_even_L(cfg.L)
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T

    spins = _initial_spins(cfg, device, g_init)
    even = _vertical_parity_mask(cfg.L, device)
    masks = [even.unsqueeze(0).expand(cfg.n_temps, cfg.L, cfg.L).contiguous(),
             (~even).unsqueeze(0).expand(cfg.n_temps, cfg.L, cfg.L).contiguous()]

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        for mask in masks:
            spins = _half_sweep(spins, beta, mask, even, g_step)

    # Measurement phase
    mag_samples = []
    energy_samples = []
    for s in range(cfg.n_sweeps):
        for mask in masks:
            spins = _half_sweep(spins, beta, mask, even, g_step)
        if s % cfg.sample_every == 0:
            mag_samples.append(spins.float().mean(dim=(-1, -2)).cpu())
            energy_samples.append(energy_per_spin(spins, even).cpu())
    wall = time.time() - t0

    mag = torch.stack(mag_samples)              # (n_samples, n_temps)
    energy = torch.stack(energy_samples)        # (n_samples, n_temps)
    abs_mag_per_sample = mag.abs()
    abs_mag = abs_mag_per_sample.mean(dim=0).numpy()
    abs_mag_err = (abs_mag_per_sample.std(dim=0) / np.sqrt(len(mag_samples))).numpy()
    T_np = T.cpu().numpy()
    chi = (cfg.L * cfg.L) * (mag.pow(2).mean(dim=0) - mag.mean(dim=0).pow(2)).numpy() / T_np
    # |m|-based susceptibility — the finite-size-scaling–appropriate observable
    # (same reasoning ``ising.chi_abs`` and ``ising_tri`` document: ⟨|m|⟩ removes
    # the spurious variance from magnetization sign-flips near T_c on a finite
    # lattice). χ' = L²(⟨m²⟩ − ⟨|m|⟩²)/T.
    chi_abs = (cfg.L * cfg.L) * (
        mag.pow(2).mean(dim=0) - abs_mag_per_sample.mean(dim=0).pow(2)
    ).numpy() / T_np
    energy_mean = energy.mean(dim=0).numpy()
    # Specific heat per spin C(T) = (⟨E²⟩−⟨E⟩²)·N/T² (population variance, matching
    # the square, triangular and 3D engines). It peaks at T_c — the thermal cross-check.
    specific_heat = (cfg.L * cfg.L) * energy.var(dim=0, unbiased=False).numpy() / (T_np ** 2)

    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": spins[i].cpu().numpy() for i in pick_idx}

    return HexRunResult(
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
