"""Batched 2D q-state Potts Metropolis simulation on GPU.

M07 generalises the Ising spin (s = ±1, two states) to the **q-state Potts**
spin: each site holds one of ``q`` flavours s ∈ {0, …, q−1}, and a bond
contributes energy only when its two endpoints carry the *same* flavour:

    E = -J · Σ_<ij> δ(s_i, s_j)          (δ = 1 if s_i = s_j, else 0;  J = 1)

q = 2 is the Ising model in disguise (two flavours, agree/disagree), so this
engine reduces to ``ising.py``'s physics there; the interesting cases are q ≥ 3.
The ferromagnetic Potts model on the square lattice has an **exact** critical
temperature (Baxter / the self-dual point):

    T_c(q) = 1 / ln(1 + √q)              (k_B = J = 1)
        q=3 → 0.99497   q=4 → 0.91024   q=5 → 0.85153   q=6 → 0.80760

and the transition changes *character* with q: it is **continuous (2nd order)**
for q ≤ 4 and **first-order (discontinuous)** for q ≥ 5 — the qualitative
change M07 is meant to surface in the susceptibility curves.

### Why the square checkerboard is valid here (unlike the triangular M05)

The square lattice is **bipartite**, so the red/black (2-colour) checkerboard
update ``ising.py`` uses is exact for *any* nearest-neighbour model on it,
Potts included: every site's four neighbours live on the *other* colour, held
fixed while we update one colour, so the parallel Metropolis flips of a colour
class are independent. (M05's triangular lattice is non-bipartite and needed a
3-colour update; the square Potts model does **not** — we deliberately don't
over-engineer it.)

### The q-state Metropolis move

For each site in the colour we propose a *new distinct* flavour
``s' = (s + k) % q`` with ``k`` uniform in ``{1, …, q−1}`` (so s' ≠ s — a real
move every time, the standard Potts proposal). The energy change is read from
the change in the count of agreeing neighbours:

    n_old = #{neighbours equal to the current flavour s}
    n_new = #{neighbours equal to the proposed flavour s'}
    ΔE = -J·(n_new − n_old) = (n_old − n_new)      (J = 1)

accepted with probability min(1, exp(−β·ΔE)). Lowering energy (n_new > n_old,
landing on a more-agreeing flavour) is always accepted; the Boltzmann factor
gates the rest.

### Order parameter (the Potts magnetisation)

A signed ±M doesn't generalise to q flavours; the standard scalar order
parameter is built from the most-populated flavour fraction
``ρ_max = max_a (n_a / N)``:

    m = (q·ρ_max − 1) / (q − 1)

m → 1 in the ordered phase (one flavour dominates, ρ_max → 1) and m → 0 in the
disordered phase (flavours equipartitioned, ρ_max → 1/q). The susceptibility is
the fluctuation of this order parameter, χ = N·(⟨m²⟩ − ⟨m⟩²)/T — its peak
locates the (finite-size) critical temperature, exactly as ⟨|m|⟩'s χ did for
Ising. Everything else mirrors ``ising.py``: a batch of ``n_temps`` independent
lattices, one temperature each, run in parallel; energy per spin carries the
0.5 that stops each bond being counted from both ends.

### Why M07 needs a cluster updater (not single-spin Metropolis)

Single-spin Metropolis is *correct* for the Potts model, but near the Potts
transition it is badly **non-ergodic on a finite run**: the q ≥ 5 transition is
first-order with a real free-energy barrier, and even the continuous q ≤ 4 cases
(q = 4 especially, with huge logarithmic corrections) suffer severe critical
slowing down. A Metropolis lattice gets trapped in one metastable basin for the
whole run; independent lattices at neighbouring temperatures fall into different
basins, which fills the susceptibility curve with spurious spikes and makes the
χ-peak a measurement of *noise*, not the transition. (We verified this directly —
the Metropolis M07 sweep produced a jagged, multi-peaked χ that located the
transition by luck, not signal.)

The fix is the standard one, already used by M03 (``wolff.py``): a **Wolff
single-cluster updater**, generalised from Ising to Potts. The
Fortuin–Kasteleyn bond probability between two *same-flavour* neighbours is

    p = 1 − exp(−β·J)        (J = 1; note the Potts factor is βJ, not the
                              Ising spin-flip 2βJ)

a seed cluster of one flavour is grown to a fixpoint over a frozen bond field,
and the whole (necessarily monochromatic) cluster is **recoloured to a uniformly
random new flavour**. The cluster size self-tunes to the correlation length, so
this decorrelates the lattice through the transition that Metropolis cannot. The
cluster mechanics (``_bond_field``/``_seed_mask``/``_grow_cluster``) are reused
verbatim from ``wolff.py`` — they only test ``spins == neighbour``, which is
flavour-agnostic. ``updater='wolff'`` (the default) drives M07; the correct-but-
slow ``updater='metropolis'`` checkerboard path is kept for off-critical work and
as an independent cross-check of the same physics.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
import torch


@dataclass
class PottsRunConfig:
    q: int = 3                # number of Potts flavours (q ≥ 2; q=2 is Ising)
    L: int = 128
    T_min: float = 0.88
    T_max: float = 1.12
    n_temps: int = 25
    # With the default Wolff updater these are counted in *cluster updates*, not
    # Metropolis sweeps — one cluster move decorrelates far more than one sweep,
    # so far fewer are needed (z ≈ 0.25 vs ≈ 2). The metropolis path reads them as
    # sweeps. n_samples() is the shared measurement-sample count either way.
    n_burnin: int = 3000
    n_sweeps: int = 8000
    sample_every: int = 10
    seed: int = 42
    device: str = "cuda"
    updater: str = "wolff"    # 'wolff' (cluster, the M07 default) or 'metropolis'

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class PottsRunResult:
    config: PottsRunConfig
    T: np.ndarray              # (n_temps,)
    order: np.ndarray          # mean Potts order parameter m, (n_temps,)
    order_err: np.ndarray      # standard error of m, (n_temps,)
    chi: np.ndarray            # order-parameter susceptibility N·var(m)/T, (n_temps,)
    energy: np.ndarray         # mean energy per spin, (n_temps,)
    specific_heat: np.ndarray  # C per spin = (⟨E²⟩−⟨E⟩²)·N/T², (n_temps,)
    snapshots: dict            # {temperature_key: 2D int8 lattice, sampled at end}
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "order": self.order.tolist(),
            "order_err": self.order_err.tolist(),
            "chi": self.chi.tolist(),
            "energy": self.energy.tolist(),
            "specific_heat": self.specific_heat.tolist(),
            "snapshots": {k: v.astype(int).tolist() for k, v in self.snapshots.items()},
            "wall_seconds": self.wall_seconds,
        }


def _checkerboard_masks(L: int, n_temps: int, device: torch.device):
    """The two bipartite sublattice masks — identical to ``ising._checkerboard_masks``.

    The square lattice is bipartite, so a site on colour ``a`` has all four
    neighbours on colour ``b`` and vice-versa; updating one colour while the
    other is held fixed is exact for any nearest-neighbour model, Potts included.
    """
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    a = ((ix + iy) % 2 == 0).unsqueeze(0).expand(n_temps, L, L).contiguous()
    return a, ~a


def _agree_count(spins: torch.Tensor, value: torch.Tensor) -> torch.Tensor:
    """Per-site count of the four neighbours whose flavour equals ``value``.

    ``spins`` and ``value`` are both ``(n_temps, L, L)`` int tensors (``value``
    is either the current flavour at each site or a proposed one). Each rolled
    copy is the neighbour in one of the four directions; the per-direction
    equality is cast to int8 *before* summing — adding the bool tensors directly
    is logical-OR (True+True == True), which would collapse the count to {0,1}
    instead of {0,…,4}. Periodic boundaries (rolls wrap).
    """
    return (
        (torch.roll(spins, 1, dims=-2) == value).to(torch.int8)
        + (torch.roll(spins, -1, dims=-2) == value).to(torch.int8)
        + (torch.roll(spins, 1, dims=-1) == value).to(torch.int8)
        + (torch.roll(spins, -1, dims=-1) == value).to(torch.int8)
    )


def _energy_per_spin(spins: torch.Tensor) -> torch.Tensor:
    """Energy per spin e = -0.5·mean_i Σ_{4 nbrs} δ(s_i, s_nbr), per lattice.

    The 0.5 stops each bond being counted from both endpoints (there are 2N
    bonds on the periodic square lattice, so e ∈ [-2, 0]: -2 fully ordered, 0
    fully disordered). Returns one scalar per lattice — shape ``(n_temps,)``.
    """
    agree = _agree_count(spins, spins).float()          # (n_temps, L, L), each in {0..4}
    return -0.5 * agree.mean(dim=(-1, -2))


def _half_sweep(spins: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor,
                q: int, g: torch.Generator) -> torch.Tensor:
    """One q-state Metropolis update of the sites on ``mask`` (a checkerboard colour).

    Proposes s' = (s + k) % q with k ∈ {1,…,q−1} uniform (always a *distinct*
    flavour), computes ΔE = (n_old − n_new) from the change in the agreeing-
    neighbour count, and accepts with prob min(1, exp(−β·ΔE)). The neighbours of
    every masked site sit on the *other* colour (held fixed), so the whole colour
    class flips in parallel exactly.
    """
    n_old = _agree_count(spins, spins)                  # agreement with current flavour
    # Propose a distinct new flavour: shift by k ∈ {1,…,q−1} (never 0).
    k = torch.randint(1, q, spins.shape, generator=g, device=spins.device, dtype=torch.int64)
    proposed = ((spins.to(torch.int64) + k) % q).to(spins.dtype)
    n_new = _agree_count(spins, proposed)               # agreement with proposed flavour
    dE = (n_old - n_new).float()                        # ΔE = -J·(n_new − n_old), J=1
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(spins.shape, generator=g, device=spins.device)
    flip = mask & (rand < prob)
    return torch.where(flip, proposed, spins)


def _order_parameter(spins: torch.Tensor, q: int) -> torch.Tensor:
    """The Potts order parameter m = (q·ρ_max − 1)/(q − 1) per lattice.

    ``ρ_max`` is the fraction of sites in the most-populated flavour. Counts are
    formed with a one-hot over the q flavours summed across the lattice, so this
    is a single vectorised op per sample. Returns shape ``(n_temps,)``; m → 1
    ordered (one flavour dominates), m → 0 disordered (ρ_max → 1/q).
    """
    n_temps = spins.shape[0]
    N = spins.shape[-1] * spins.shape[-2]
    # Per-flavour counts: (n_temps, q). one_hot over the last axis, summed over sites.
    onehot = torch.nn.functional.one_hot(spins.to(torch.int64).reshape(n_temps, -1), q)
    counts = onehot.sum(dim=1).float()                  # (n_temps, q)
    rho_max = counts.max(dim=1).values / N              # (n_temps,)
    return (q * rho_max - 1.0) / (q - 1.0)


def _wolff_update(spins: torch.Tensor, beta: torch.Tensor, q: int,
                  g: torch.Generator) -> torch.Tensor:
    """One q-state-Potts single-cluster Wolff move per batched lattice.

    Reuses ``wolff.py``'s frozen-bond-field cluster mechanics (the only
    correctness-critical part — see that module's two load-bearing facts), which
    are flavour-agnostic because they test ``spins == neighbour``. The only Potts
    specialisations are:

    * the bond probability ``p = 1 − exp(−β·J)`` (J = 1) between two *same-flavour*
      neighbours — the Fortuin–Kasteleyn value; note it is ``βJ``, not the Ising
      single-cluster ``2βJ`` (that factor 2 is the Ising spin-flip energy, absent
      in the Potts δ-bond convention);
    * the move *recolours* the (monochromatic) seed cluster to a uniformly random
      *new* flavour ``(s + k) % q`` with ``k ∈ {1,…,q−1}``, instead of negating it.

    Pure: returns new spins, does not mutate ``spins``.
    """
    from .wolff import _bond_field, _grow_cluster, _seed_mask

    n_temps, L, _ = spins.shape
    device = spins.device
    # Potts FK activation prob between aligned (same-flavour) neighbours.
    p = (1.0 - torch.exp(-beta.to(torch.float32))).view(n_temps, 1, 1).to(device)
    bond_down, bond_right = _bond_field(spins, p, g)
    seed = _seed_mask(n_temps, L, device, g)
    in_cluster = _grow_cluster(seed, bond_down, bond_right)
    # Recolour the whole (single-flavour) cluster to a random distinct flavour.
    k = torch.randint(1, q, (n_temps, 1, 1), generator=g, device=device, dtype=torch.int64)
    recolored = ((spins.to(torch.int64) + k) % q).to(spins.dtype)
    return torch.where(in_cluster, recolored, spins)


def run(cfg: PottsRunConfig) -> PottsRunResult:
    """Run a batched q-state Potts sweep on the square lattice: one lattice per T.

    Mirrors ``ising.run`` — a burn-in then a measurement phase that samples the
    Potts order parameter m and the energy per spin — and locates T_c from the
    χ(m) peak (M07's headline observable, vs the exact T_c(q) = 1/ln(1+√q)).

    Two updaters share this driver (``cfg.updater``):

    * ``'wolff'`` (default) — the single-cluster Wolff move, the right tool through
      the Potts transition (first-order for q ≥ 5, strong critical slowing for
      q ≤ 4); ``n_burnin``/``n_sweeps`` count *cluster updates*.
    * ``'metropolis'`` — the bipartite-checkerboard single-spin move, correct but
      non-ergodic on a finite run near the transition (kept for off-critical work
      and as an independent cross-check); ``n_burnin``/``n_sweeps`` count *sweeps*
      (two half-sweeps, one per checkerboard colour, each step).
    """
    if cfg.q < 2:
        raise ValueError(f"q must be ≥ 2 (got {cfg.q}); q=2 is the Ising model.")
    if cfg.updater not in ("wolff", "metropolis"):
        raise ValueError(f"unknown updater {cfg.updater!r} (use 'wolff' or 'metropolis')")
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T

    # Random initial flavours s ∈ {0,…,q−1}.
    spins = torch.randint(0, cfg.q, (cfg.n_temps, cfg.L, cfg.L),
                          generator=g_init, device=device, dtype=torch.int8)

    if cfg.updater == "wolff":
        def _step(s):
            return _wolff_update(s, beta, cfg.q, g_step)
    else:
        mask_a, mask_b = _checkerboard_masks(cfg.L, cfg.n_temps, device)

        def _step(s):
            s = _half_sweep(s, beta, mask_a, cfg.q, g_step)
            return _half_sweep(s, beta, mask_b, cfg.q, g_step)

    t0 = time.time()
    # Burn-in
    for _ in range(cfg.n_burnin):
        spins = _step(spins)

    # Measurement phase
    order_samples = []
    energy_samples = []
    for s in range(cfg.n_sweeps):
        spins = _step(spins)
        if s % cfg.sample_every == 0:
            order_samples.append(_order_parameter(spins, cfg.q).cpu())
            energy_samples.append(_energy_per_spin(spins).cpu())
    wall = time.time() - t0

    order = torch.stack(order_samples)          # (n_samples, n_temps)
    energy = torch.stack(energy_samples)        # (n_samples, n_temps)
    T_np = T.cpu().numpy()

    order_mean = order.mean(dim=0).numpy()
    order_err = (order.std(dim=0) / np.sqrt(len(order_samples))).numpy()
    # Order-parameter susceptibility χ = N·(⟨m²⟩−⟨m⟩²)/T — its peak locates T_c.
    chi = (cfg.L * cfg.L) * (
        order.pow(2).mean(dim=0) - order.mean(dim=0).pow(2)
    ).numpy() / T_np
    energy_mean = energy.mean(dim=0).numpy()
    # Specific heat per spin C(T) = (⟨E²⟩−⟨E⟩²)·N/T² (population variance, matching
    # the square + triangular + 3D engines). It peaks at T_c — the thermal cross-check.
    specific_heat = (cfg.L * cfg.L) * energy.var(dim=0, unbiased=False).numpy() / (T_np ** 2)

    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": spins[i].cpu().numpy() for i in pick_idx}

    return PottsRunResult(
        config=cfg,
        T=T_np,
        order=order_mean,
        order_err=order_err,
        chi=chi,
        energy=energy_mean,
        specific_heat=specific_heat,
        snapshots=snapshots,
        wall_seconds=wall,
    )
