"""Batched 2D *Heisenberg* model on GPU — O(3) unit-vector spins, Mermin–Wagner.

M08 was the first continuous-spin model: O(2) planar angles, with a topological
BKT transition. M09 goes one symmetry up — each site carries a **3-component
unit vector** S_i ∈ S² (a point on the sphere), and a bond's energy is the dot
product of neighbouring vectors:

    E = -J · Σ_⟨ij⟩ S_i · S_j            (J = 1, k_B = 1)

The point of M09 is a **null done honestly**. Mermin–Wagner: a 2D system with a
*continuous* symmetry (here O(3)) and short-range interactions cannot
spontaneously break that symmetry at any T > 0 — so the isotropic 2D Heisenberg
ferromagnet is **disordered at every finite temperature**, ordered only exactly
at T = 0. Crucially, unlike the XY model (M08), Heisenberg has **no BKT either**:
the order-parameter sphere S² is simply connected (π₁(S²) = 0), so there are no
stable point vortices to unbind. Correlations decay **exponentially** at all
T > 0; there is **no transition of any kind** at finite temperature.

### The right observable — show ⟨|m|⟩ drifts to 0 as L grows

There is no T_c to reproduce. The clean, falsifiable signature of the *absence*
of order is a **finite-size drift**: at a fixed moderate temperature, the
per-spin vector magnetization

    |m| = |(1/N) Σ_i S_i|                (the magnitude of the average vector)

**decreases toward 0 as L grows** — ⟨|m|⟩(16) > ⟨|m|⟩(32) > ⟨|m|⟩(64) > … — at
every T > 0. If there were spontaneous order, ⟨|m|⟩ would approach a finite
constant; under Mermin–Wagner it keeps shrinking, because the only thing holding
up a finite |m| on a small lattice is the finite correlation length ξ(T) being
comparable to L. Once L ≫ ξ the magnetization washes out. **The #1 failure mode
is reading a single small L**: at one fixed L, ⟨|m|⟩ is appreciable and *fakes* a
transition — the verification *requires* varying L and showing the monotone
drift toward 0. (``m09`` does the L-family sweep; this engine measures one (T, L)
point.)

### The update — uniform-on-sphere proposals, over-relaxation, embedded Wolff

The square lattice is bipartite, so the red/black checkerboard parallel update is
exact for O(3) too (a site's four neighbours all live on the other colour, held
fixed). Three moves share the driver:

* **Metropolis with a small-angle local proposal.** A fresh *uniform-on-sphere*
  vector r is sampled (z = cosθ ~ Uniform(−1, 1), φ ~ Uniform(0, 2π) — **never**
  θ uniform, which over-weights the poles and biases every measured energy and
  correlation), then mixed toward the current spin and renormalized:

      S_i' = normalize( S_i + δ·r ),     r ~ Uniform(S²)

  The mixing width δ tunes the typical rotation angle, holding acceptance in the
  ~30–50% band; δ → ∞ recovers a global uniform proposal, δ → 0 a tiny nudge. We
  size δ(T) ∝ √T (clamped to a sane band) and *measure and report* the realized
  acceptance so a mistune is visible, not silent.

* **Microcanonical over-relaxation** reflects each spin about its local field
  H_i = Σ_nbr S_j:  S_i → 2 (S_i·Ĥ_i) Ĥ_i − S_i. This leaves every bond energy of
  site i unchanged (it preserves S_i·H_i, hence the sum of the four dot products),
  so it needs no Metropolis test, yet it rotates the long-wavelength spin-wave
  modes single-site Metropolis decorrelates only slowly — the standard cure for
  the critical slowing the low-T (large-ξ) points suffer.

* **Embedded-Wolff** (``updater='wolff'``) — the O(3) analogue of M08's XY Wolff.
  Project every spin onto a random unit axis r̂; the embedded Ising variable is
  ε_i = sign(S_i·r̂). Two same-ε neighbours bond with the FK-style probability
  1 − exp(−2·β·J·(S_i·r̂)(S_j·r̂)) (only when the projections share a sign), the
  seed's component is grown over the *frozen* bond field, and the whole cluster is
  reflected **across the plane PERPENDICULAR to r̂**:

      S_i → S_i − 2 (S_i·r̂) r̂

  which negates the component along r̂ (flipping ε) and keeps the perpendicular
  part. This is the load-bearing subtlety M08 flagged as recurring for O(n)
  cluster moves: it is reflection across the *plane ⊥ r̂*, the move that flips the
  embedded Ising spin — reflecting *through* the axis instead would preserve the
  projection, not flip ε, and would heat a cold lattice rather than order it.

``int8`` has no place here — every component is float32 throughout.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict

import numpy as np
import torch


def _random_unit_vectors(shape: tuple[int, ...], g: torch.Generator,
                         device: torch.device) -> torch.Tensor:
    """Uniform points on S² — the Marsaglia / Archimedes construction.

    Returns a ``(*shape, 3)`` float32 tensor of unit vectors distributed
    **uniformly** over the sphere. The correct sampling draws the *z*-coordinate
    (= cos θ) uniformly in [−1, 1] and the azimuth φ uniformly in [0, 2π); then
    (√(1−z²)·cosφ, √(1−z²)·sinφ, z) is uniform on the sphere by Archimedes'
    hat-box theorem (equal-area projection onto the axis).

    Sampling θ uniformly instead — the tempting bug — clusters points at the
    poles and systematically biases every energy and correlation the engine
    measures. The engine never calls anything but this for a random vector, so
    that bias can't sneak in.
    """
    z = torch.rand(shape, generator=g, device=device, dtype=torch.float32) * 2.0 - 1.0
    phi = torch.rand(shape, generator=g, device=device, dtype=torch.float32) * (2.0 * math.pi)
    r = torch.sqrt(torch.clamp(1.0 - z * z, min=0.0))
    return torch.stack((r * torch.cos(phi), r * torch.sin(phi), z), dim=-1)


def _normalize(v: torch.Tensor) -> torch.Tensor:
    """Project vectors back onto the unit sphere along ``dim=-1`` (safe at 0)."""
    norm = torch.linalg.vector_norm(v, dim=-1, keepdim=True)
    return v / norm.clamp_min(1e-12)


@dataclass
class HeisenbergRunConfig:
    L: int = 32
    T_min: float = 0.7
    T_max: float = 0.7
    n_temps: int = 1
    n_burnin: int = 8000
    n_sweeps: int = 20000        # measurement sweeps
    sample_every: int = 20
    over_relax: int = 3          # microcanonical over-relaxation sweeps per Metropolis sweep
    seed: int = 42
    device: str = "cuda"
    updater: str = "metropolis"  # 'metropolis' (+ over-relaxation; default) or 'wolff'

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class HeisenbergRunResult:
    config: HeisenbergRunConfig
    T: np.ndarray                  # (n_temps,)
    abs_mag: np.ndarray            # ⟨|m|⟩ per spin — the Mermin–Wagner drift observable, (n_temps,)
    abs_mag_err: np.ndarray        # standard error of ⟨|m|⟩, (n_temps,)
    chi: np.ndarray                # |m|-based susceptibility χ = N(⟨m²⟩−⟨|m|⟩²)/T, (n_temps,)
    energy: np.ndarray             # mean energy per spin, (n_temps,)
    acceptance: np.ndarray         # realized Metropolis acceptance per T (tune diagnostic)
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "abs_mag": self.abs_mag.tolist(),
            "abs_mag_err": self.abs_mag_err.tolist(),
            "chi": self.chi.tolist(),
            "energy": self.energy.tolist(),
            "acceptance": self.acceptance.tolist(),
            "wall_seconds": self.wall_seconds,
        }


def _checkerboard_masks(L: int, n_temps: int, device: torch.device):
    """The two bipartite sublattice masks, broadcastable over the 3 vector comps.

    Same checkerboard ``ising``/``xy`` use, but shaped ``(n_temps, L, L, 1)`` so a
    boolean ``torch.where`` selects whole 3-vectors. A site on colour ``a`` has all
    four neighbours on colour ``b``; updating one colour with the other held fixed
    is exact for the Heisenberg model too (the lattice graph is bipartite).
    """
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    a = ((ix + iy) % 2 == 0).unsqueeze(0).expand(n_temps, L, L).contiguous()
    a = a.unsqueeze(-1)            # (n_temps, L, L, 1) — broadcasts over the 3 comps
    return a, ~a


def _neighbor_field(S: torch.Tensor) -> torch.Tensor:
    """The local field H_i = Σ_{4 nbrs} S_j at every site, periodic.

    ``S`` is ``(n_temps, L, L, 3)``; rolls wrap on the torus. Returns the same
    shape — the summed neighbour vector each update and the over-relaxation
    reflection use. (Rolls are over the two *lattice* axes −3, −2, never the
    component axis −1.)
    """
    up = torch.roll(S, 1, dims=-3)
    down = torch.roll(S, -1, dims=-3)
    left = torch.roll(S, 1, dims=-2)
    right = torch.roll(S, -1, dims=-2)
    return up + down + left + right


def _energy_per_spin(S: torch.Tensor) -> torch.Tensor:
    """Energy per spin e = -0.5·mean_i (S_i · Σ_{4 nbrs} S_j), per lattice.

    The 0.5 de-double-counts the 2N bonds (each bond is seen from both ends), so
    e ∈ [-2, 2]: -2 fully aligned (every dot product 1), 0 random. Returns one
    scalar per lattice — shape ``(n_temps,)``.
    """
    dot = (S * _neighbor_field(S)).sum(dim=-1)           # S_i · H_i, (n_temps, L, L)
    return -0.5 * dot.mean(dim=(-1, -2))


def _abs_mag(S: torch.Tensor) -> torch.Tensor:
    """⟨|m|⟩ per lattice, m = (1/N)·Σ_i S_i — the VECTOR magnetization magnitude.

    This is the Mermin–Wagner order parameter: |m| is the length of the average
    3-vector over the lattice. At fixed T > 0 it **drifts toward 0 as L grows**
    (no spontaneous order); on a single small lattice it looks deceptively finite
    and fakes a transition, which is why M09 varies L. Returns ``(n_temps,)``.
    """
    m = S.mean(dim=(-3, -2))                              # (n_temps, 3) — mean over the lattice
    return torch.linalg.vector_norm(m, dim=-1)


def _metropolis_half_sweep(S: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor,
                           delta: torch.Tensor, g: torch.Generator):
    """One Metropolis update of the sites on ``mask`` (a checkerboard colour).

    Proposes S_i' = normalize(S_i + δ·r), r a fresh uniform-on-sphere vector, then
    accepts with min(1, exp(−β·ΔE)). The energy that depends on S_i is
    −S_i·H_i (H_i the summed neighbour field), so ΔE = −(S_i'−S_i)·H_i. The
    neighbours of every masked site sit on the *other* colour (held fixed), so the
    whole colour class updates in parallel exactly. ``delta`` and ``beta`` are
    ``(n_temps,)``.

    Returns ``(S, n_accepted)`` where ``n_accepted`` is a per-lattice count of
    proposals accepted on this colour — summed by the caller into the realized
    acceptance diagnostic.
    """
    H = _neighbor_field(S)                                # (n_temps, L, L, 3), held fixed this half-sweep
    r = _random_unit_vectors(S.shape[:-1], g, S.device)  # (n_temps, L, L, 3)
    proposed = _normalize(S + delta.view(-1, 1, 1, 1) * r)
    # E_i depends on S_i only through −S_i·H_i, so ΔE = −(S' − S)·H.
    dE = -((proposed - S) * H).sum(dim=-1)               # (n_temps, L, L)
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(dE.shape, generator=g, device=S.device)
    accept = mask.squeeze(-1) & (rand < prob)            # (n_temps, L, L)
    n_accepted = accept.sum(dim=(-1, -2))
    new_S = torch.where(accept.unsqueeze(-1), proposed, S)
    return new_S, n_accepted


def _over_relax_half_sweep(S: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """One microcanonical over-relaxation update of the sites on ``mask``.

    Reflects each masked spin about its local field H_i = Σ_nbr S_j:

        S_i → 2 (S_i·Ĥ_i) Ĥ_i − S_i,    Ĥ_i = H_i / |H_i|

    This is the reflection of S_i across the H_i axis; it preserves S_i·H_i (hence
    every one of site i's four bond energies summed through H_i) and keeps |S_i|=1,
    so it is energy-conserving and needs no Metropolis test. Yet it rotates the
    long-wavelength spin-wave modes single-site Metropolis crawls through — the
    standard cure for critical slowing at the low-T, large-ξ points. Exact in
    parallel on a checkerboard colour (neighbours held fixed). Where H_i ≈ 0 the
    reflection is ill-defined; we leave those (vanishingly rare) sites unchanged.
    """
    H = _neighbor_field(S)
    norm = torch.linalg.vector_norm(H, dim=-1, keepdim=True)
    Hhat = H / norm.clamp_min(1e-12)
    proj = (S * Hhat).sum(dim=-1, keepdim=True)          # S_i·Ĥ_i
    reflected = 2.0 * proj * Hhat - S
    # Guard the degenerate H≈0 sites: keep the original spin there.
    reflected = torch.where(norm > 1e-9, reflected, S)
    return torch.where(mask, reflected, S)


def _wolff_update(S: torch.Tensor, beta: torch.Tensor, g: torch.Generator) -> torch.Tensor:
    """One embedded-Ising single-cluster Wolff move per batched lattice (O(3)).

    The Wolff–Kosterlitz embedded-Ising construction, the O(3) analogue of the XY
    Wolff in ``xy.py``. Pick a random unit axis r̂; each spin's Ising variable is
    ε_i = sign(p_i), p_i = S_i·r̂. Two **same-ε** neighbours are bonded with the
    FK-style probability 1 − exp(−2·β·J·p_i·p_j) (only when p_i·p_j > 0, i.e.
    ε_i = ε_j; opposite-sign pairs never bond), the seed's component is grown to a
    fixpoint over the *frozen* bond field (the same load-bearing facts as
    ``wolff.py``: each undirected bond drawn once, the field frozen before the
    flood), and the whole (monochromatic-ε) cluster is reflected.

    Reflecting flips the embedded ε — it must be reflection **across the plane
    PERPENDICULAR to r̂**:  S_i → S_i − 2 (S_i·r̂) r̂, which negates the component
    of S along r̂ (sending p_i → −p_i, flipping ε) and keeps the perpendicular
    part. Reflecting *through* the axis r̂ instead would PRESERVE p_i, NOT flip ε,
    and fail to order a cold lattice — the recurring O(n)-cluster subtlety M08
    flagged. Pure: returns new spins, does not mutate ``S``.
    """
    from .wolff import _grow_cluster, _seed_mask

    n_temps, L, _, _ = S.shape
    device = S.device
    rhat = _random_unit_vectors((n_temps, 1, 1), g, device)        # (n_temps,1,1,3)
    proj = (S * rhat).sum(dim=-1)                                  # p_i = S_i·r̂, (n_temps,L,L)

    # Bond activation along the two torus orientations (down, right) — each
    # undirected bond exactly once (mirrors wolff._bond_field / xy._wolff_update).
    # p_i·p_j > 0 ⇔ the two sites share an ε sign; clamp(max=0) zeroes the
    # activation prob for opposite-sign pairs, so a bond can never cross an ε wall.
    down_proj = torch.roll(proj, shifts=-1, dims=-2)
    right_proj = torch.roll(proj, shifts=-1, dims=-1)
    b = beta.view(n_temps, 1, 1)
    p_down = 1.0 - torch.exp((-2.0 * b * (proj * down_proj)).clamp(max=0.0))
    p_right = 1.0 - torch.exp((-2.0 * b * (proj * right_proj)).clamp(max=0.0))
    u_down = torch.rand(proj.shape, generator=g, device=device)
    u_right = torch.rand(proj.shape, generator=g, device=device)
    bond_down = u_down < p_down
    bond_right = u_right < p_right

    seed = _seed_mask(n_temps, L, device, g)
    in_cluster = _grow_cluster(seed, bond_down, bond_right)        # (n_temps,L,L) bool
    # Reflect the cluster across the plane ⊥ r̂: S → S − 2(S·r̂)r̂ (flips ε).
    reflected = S - 2.0 * proj.unsqueeze(-1) * rhat
    return torch.where(in_cluster.unsqueeze(-1), reflected, S)


def _delta_for(T: torch.Tensor) -> torch.Tensor:
    """Per-temperature Metropolis mixing width δ(T), tuned for ~30–50% acceptance.

    A unit vector in a local field of magnitude h sees an energy scale ~h·δ² for a
    small mixing δ, so acceptance is governed by β·h·δ² ~ O(1) → δ ∝ √(T/h). With
    h = O(1) over the moderate-T window M09 sweeps, δ ∝ √T holds acceptance in band;
    we clamp it to [0.5, 3.0] so it never collapses (too small, frozen) nor saturates
    to an effectively-global proposal (too large, low acceptance). Realized
    acceptance is measured and reported, so a mistune is visible, not silent.
    """
    return torch.sqrt(T).clamp(min=0.5, max=3.0)


def run(cfg: HeisenbergRunConfig) -> HeisenbergRunResult:
    """Run a batched 2D Heisenberg sweep on the square lattice: one lattice per T.

    Mirrors ``ising.run``/``xy.run`` — a burn-in then a measurement phase — but
    the spins are O(3) unit vectors and the headline observable is ⟨|m|⟩, the
    Mermin–Wagner drift order parameter (it shrinks toward 0 as L grows at every
    T > 0). χ is the |m|-based susceptibility N(⟨m²⟩−⟨|m|⟩²)/T (same FSS-appropriate
    form the Ising engines use), energy and the realized acceptance are carried as
    context. Two updaters share this driver (``cfg.updater``):

    * ``'metropolis'`` (default) — per-T-tuned-δ checkerboard Metropolis with
      ``cfg.over_relax`` interleaved microcanonical over-relaxation sweeps (the
      cure for spin-wave critical slowing at the low-T, large-ξ points);
      ``n_burnin``/``n_sweeps`` count Metropolis sweeps.
    * ``'wolff'`` — the embedded-Ising single-cluster reflection move;
      ``n_burnin``/``n_sweeps`` count cluster updates.
    """
    if cfg.updater not in ("metropolis", "wolff"):
        raise ValueError(f"unknown updater {cfg.updater!r} (use 'metropolis' or 'wolff')")
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T
    N = cfg.L * cfg.L

    # Random initial spins — uniform on the sphere (NOT pole-biased θ-uniform).
    S = _random_unit_vectors((cfg.n_temps, cfg.L, cfg.L), g_init, device)

    use_wolff = cfg.updater == "wolff"
    if not use_wolff:
        mask_a, mask_b = _checkerboard_masks(cfg.L, cfg.n_temps, device)
        delta = _delta_for(T)

    accept_num = torch.zeros(cfg.n_temps, device=device)
    accept_den = 0

    def _metropolis_sweep(s):
        nonlocal accept_num, accept_den
        s, na = _metropolis_half_sweep(s, beta, mask_a, delta, g_step)
        s, nb = _metropolis_half_sweep(s, beta, mask_b, delta, g_step)
        accept_num += (na + nb).float()
        accept_den += N
        for _ in range(cfg.over_relax):
            s = _over_relax_half_sweep(s, mask_a)
            s = _over_relax_half_sweep(s, mask_b)
        return s

    def _wolff_sweep(s):
        return _wolff_update(s, beta, g_step)

    step = _wolff_sweep if use_wolff else _metropolis_sweep

    t0 = time.time()
    # Burn-in (acceptance during burn-in is not counted toward the diagnostic).
    if not use_wolff:
        for _ in range(cfg.n_burnin):
            S = _metropolis_half_sweep(S, beta, mask_a, delta, g_step)[0]
            S = _metropolis_half_sweep(S, beta, mask_b, delta, g_step)[0]
            for _ in range(cfg.over_relax):
                S = _over_relax_half_sweep(S, mask_a)
                S = _over_relax_half_sweep(S, mask_b)
    else:
        for _ in range(cfg.n_burnin):
            S = step(S)

    # Measurement phase
    absmag_samples = []
    energy_samples = []
    for s in range(cfg.n_sweeps):
        S = step(S)
        if s % cfg.sample_every == 0:
            absmag_samples.append(_abs_mag(S).cpu())
            energy_samples.append(_energy_per_spin(S).cpu())
    wall = time.time() - t0

    absmag = torch.stack(absmag_samples)         # (n_samples, n_temps)
    energy = torch.stack(energy_samples)
    T_np = T.cpu().numpy()
    n_samples = len(absmag_samples)

    abs_mag_mean = absmag.mean(dim=0).numpy()
    abs_mag_err = (absmag.std(dim=0) / np.sqrt(max(1, n_samples))).numpy()
    # |m|-based susceptibility χ = N(⟨m²⟩ − ⟨|m|⟩²)/T — the FSS-appropriate form
    # (kills the spurious variance a finite lattice's drifting-direction |m| carries).
    chi = (N * (absmag.pow(2).mean(dim=0) - absmag.mean(dim=0).pow(2)) / T.cpu()).numpy()
    energy_mean = energy.mean(dim=0).numpy()
    acceptance = (
        (accept_num / accept_den).cpu().numpy() if (not use_wolff and accept_den > 0)
        else np.full(cfg.n_temps, np.nan)
    )

    return HeisenbergRunResult(
        config=cfg,
        T=T_np,
        abs_mag=abs_mag_mean,
        abs_mag_err=abs_mag_err,
        chi=chi,
        energy=energy_mean,
        acceptance=acceptance,
        wall_seconds=wall,
    )
