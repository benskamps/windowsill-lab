"""Batched 2D *XY* model on GPU — continuous angle spins, helicity modulus.

M08 is the first model to leave the discrete-Ising world entirely. Each site
carries a **continuous angle** θ_i ∈ [0, 2π) — an O(2) planar unit vector, not a
±1 Ising spin — and a bond's energy is the cosine of the angle difference:

    E = -J · Σ_⟨ij⟩ cos(θ_i − θ_j)            (J = 1, k_B = 1)

The 2D XY model has **no long-range order at any T > 0** (Mermin–Wagner: a
continuous symmetry can't break in 2D), yet it still has a transition — the
**Berezinskii–Kosterlitz–Thouless (BKT)** transition at T_BKT ≈ 0.8929, a
*topological* unbinding of vortex–antivortex pairs. Below T_BKT the spin
correlations decay as a **power law** (quasi-long-range order); above, they decay
exponentially. So ⟨|m|⟩ is **useless** as an order parameter here — on a large
lattice it → 0 at *all* T > 0, and is NOT the BKT signature. (M01–M07's "find
where ⟨|m|⟩'s χ peaks" recipe is exactly the wrong tool for M08.)

### The right observable — the helicity modulus Υ(T) and its universal jump

The clean, falsifiable BKT signature is the **helicity modulus** Υ(T) (a.k.a.
spin stiffness / superfluid density): the free-energy curvature response to an
infinitesimal twist of the boundary condition. It is finite below T_BKT and
drops to 0 above, with a **universal jump** (Nelson–Kosterlitz): in the L→∞
limit Υ(T_BKT⁻) = (2/π)·T_BKT. Operationally we plot Υ(T) and the straight line
y = (2/π)·T and read **their crossing** as the finite-L estimate of T_BKT (see
``m08``); at that crossing Υ/T = 2/π ≈ 0.6366.

The Teitel–Jayaprakash / Weber–Minnhagen estimator, for one bond direction
(here x̂), with bond current I_x = Σ_{x-bonds} sin(θ_i − θ_{i+x̂}):

    Υ_x = (1/N)⟨ Σ_{x-bonds} cos(θ_i − θ_{i+x̂}) ⟩          (energy-like term)
          − (β/N)·[ ⟨I_x²⟩ − ⟨I_x⟩² ]                       (fluctuation term)

and Υ = ½(Υ_x + Υ_y). **The fluctuation term is the load-bearing subtlety** — the
single place the number most often comes out wrong:

* it carries a factor **β = 1/T** (dropping it, or using 1/N with the wrong
  power of T, shifts the crossing badly), and
* it is a **connected** variance ⟨I²⟩−⟨I⟩². On a torus ⟨I_x⟩ = 0 by the
  reflection symmetry θ → −θ, so the two forms agree in expectation, but the
  connected form is the rigorous one and removes finite-sample drift, so we use
  it. The current is summed over the *whole* lattice each sample, then its
  variance is taken across samples.

Sanity rails the tests pin: as T → 0 the lattice is nearly aligned, every cosine
≈ 1 and the current ≈ 0, so Υ → J = 1; as T → ∞ the angles randomize, the cosine
term averages to 0 and Υ → 0.

### The update — Metropolis with a per-T proposal width

The square lattice is bipartite, so the red/black checkerboard parallel update
``ising.py`` uses is exact for the XY model too (a site's four neighbours all
live on the other colour, held fixed). For each site in a colour we propose

    θ_i' = θ_i + δ·u,        u ~ Uniform(−1, 1)

and accept with min(1, exp(−ΔE/T)). The proposal width **δ must be tuned per
temperature** to hold the acceptance ≈ 30–50%: a fixed δ that is fine at high T
collapses the acceptance near/below T_BKT (the lattice freezes, Υ looks
spuriously high and the crossing lands too warm). We size δ(T) ∝ √T, clamped to a
sane band, which holds acceptance in the target range across the whole sweep, and
we *measure and report* the realized acceptance so a mis-tune is visible rather
than silent. Over-relaxation microcanonical sweeps are interleaved to cut the
critical slowing the helicity term suffers near T_BKT (they rotate each spin to
the local-field reflection — energy-conserving, ergodicity-restoring, and they
decorrelate the long-wavelength spin-wave modes Metropolis crawls through). A
single-cluster XY Wolff is also provided (``updater='wolff'``) for the hardest
points; Metropolis + over-relaxation already gives a smooth Υ(T), so it is the
default. ``int8`` has no place here — angles are float32 throughout.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict

import numpy as np
import torch

TWO_PI = 2.0 * math.pi


@dataclass
class XYRunConfig:
    L: int = 64
    T_min: float = 0.6
    T_max: float = 1.1
    n_temps: int = 25
    n_burnin: int = 8000
    n_sweeps: int = 40000        # measurement sweeps (XY equilibrates slowly — be generous)
    sample_every: int = 20
    over_relax: int = 1          # microcanonical over-relaxation sweeps per Metropolis sweep
    seed: int = 42
    device: str = "cuda"
    updater: str = "metropolis"  # 'metropolis' (+ over-relaxation; default) or 'wolff'

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class XYRunResult:
    config: XYRunConfig
    T: np.ndarray                  # (n_temps,)
    helicity_modulus: np.ndarray   # Υ(T), the BKT observable, (n_temps,)
    helicity_err: np.ndarray       # standard error of Υ, (n_temps,)
    energy: np.ndarray             # mean energy per spin, (n_temps,)
    abs_mag: np.ndarray            # ⟨|m|⟩ per spin — carried for context, NOT the order param
    acceptance: np.ndarray         # realized Metropolis acceptance per T (tune diagnostic)
    snapshots: dict                # {temperature_key: 2D float angle lattice, sampled at end}
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "T": self.T.tolist(),
            "helicity_modulus": self.helicity_modulus.tolist(),
            "helicity_err": self.helicity_err.tolist(),
            "energy": self.energy.tolist(),
            "abs_mag": self.abs_mag.tolist(),
            "acceptance": self.acceptance.tolist(),
            "snapshots": {k: v.tolist() for k, v in self.snapshots.items()},
            "wall_seconds": self.wall_seconds,
        }


def _checkerboard_masks(L: int, n_temps: int, device: torch.device):
    """The two bipartite sublattice masks — identical to ``ising._checkerboard_masks``.

    The square lattice is bipartite, so a site on colour ``a`` has all four
    neighbours on colour ``b`` and vice-versa; updating one colour while the other
    is held fixed is exact for the XY model too.
    """
    ix = torch.arange(L, device=device).view(L, 1).expand(L, L)
    iy = torch.arange(L, device=device).view(1, L).expand(L, L)
    a = ((ix + iy) % 2 == 0).unsqueeze(0).expand(n_temps, L, L).contiguous()
    return a, ~a


def _neighbor_angle_sums(theta: torch.Tensor):
    """The four rolled-neighbour angle tensors (up, down, left, right), periodic.

    Returns them as a tuple so callers can build whichever combination they need
    (the local effective field for the update, or the directional bond sums for
    the helicity estimator). ``theta`` is ``(n_temps, L, L)``; rolls wrap.
    """
    up = torch.roll(theta, 1, dims=-2)
    down = torch.roll(theta, -1, dims=-2)
    left = torch.roll(theta, 1, dims=-1)
    right = torch.roll(theta, -1, dims=-1)
    return up, down, left, right


def _energy_per_spin(theta: torch.Tensor) -> torch.Tensor:
    """Energy per spin e = -0.5·mean_i Σ_{4 nbrs} cos(θ_i − θ_nbr), per lattice.

    The 0.5 de-double-counts the 2N bonds (each bond is seen from both ends), so
    e ∈ [-2, 0]: -2 fully aligned (cos = 1 on every bond), 0 fully disordered.
    Returns one scalar per lattice — shape ``(n_temps,)``.
    """
    up, down, left, right = _neighbor_angle_sums(theta)
    cos_sum = (
        torch.cos(theta - up) + torch.cos(theta - down)
        + torch.cos(theta - left) + torch.cos(theta - right)
    )
    return -0.5 * cos_sum.mean(dim=(-1, -2))


def _abs_mag(theta: torch.Tensor) -> torch.Tensor:
    """⟨|m|⟩ per lattice, m = (1/N)|Σ_i (cosθ_i, sinθ_i)| — the vector magnetization.

    Carried for *context* only: M08's transition has NO order parameter (⟨|m|⟩ → 0
    at all T>0 as L grows), so this is a diagnostic, never the BKT signature.
    """
    mx = torch.cos(theta).mean(dim=(-1, -2))
    my = torch.sin(theta).mean(dim=(-1, -2))
    return torch.sqrt(mx * mx + my * my)


def _helicity_terms(theta: torch.Tensor):
    """The two per-lattice helicity ingredients for THIS configuration.

    Returns ``(cos_term, current_x, current_y)`` each shape ``(n_temps,)``:

    * ``cos_term`` = (1/N)·Σ_{x and y bonds} cos(θ_i − θ_j), averaged over the two
      directions — the energy-like stiffness piece (per spin);
    * ``current_x`` = Σ_{x-bonds} sin(θ_i − θ_{i+x̂}) — the bond current along x
      (summed over the whole lattice, NOT divided by N: its *variance across
      samples* becomes the fluctuation term);
    * ``current_y`` likewise along ŷ.

    Each bond is taken once, oriented from a site to its +x (resp. +y) neighbour,
    so the sign convention is consistent across the lattice. The β/N weighting and
    the connected variance of the currents are applied in ``run`` over the sample
    ensemble — see the module docstring's estimator.
    """
    n_temps = theta.shape[0]
    N = theta.shape[-1] * theta.shape[-2]
    # +x neighbour of (i,j) is (i, j+1): roll columns by -1 brings it to (i,j).
    nbr_x = torch.roll(theta, -1, dims=-1)
    # +y neighbour of (i,j) is (i+1, j): roll rows by -1.
    nbr_y = torch.roll(theta, -1, dims=-2)
    dx = theta - nbr_x
    dy = theta - nbr_y
    cos_term = (torch.cos(dx).sum(dim=(-1, -2)) + torch.cos(dy).sum(dim=(-1, -2))) / (2.0 * N)
    current_x = torch.sin(dx).sum(dim=(-1, -2))
    current_y = torch.sin(dy).sum(dim=(-1, -2))
    return cos_term, current_x, current_y


def _metropolis_half_sweep(theta: torch.Tensor, beta: torch.Tensor, mask: torch.Tensor,
                           delta: torch.Tensor, g: torch.Generator):
    """One Metropolis update of the sites on ``mask`` (a checkerboard colour).

    Proposes θ_i' = θ_i + δ(T)·u, u ~ Uniform(−1, 1), computes ΔE from the four
    neighbour bonds, and accepts with min(1, exp(−β·ΔE)). The neighbours of every
    masked site sit on the *other* colour (held fixed), so the whole colour class
    updates in parallel exactly. ``delta`` and ``beta`` are ``(n_temps,)``.

    Returns ``(theta, n_accepted)`` where ``n_accepted`` is a per-lattice count of
    proposals accepted on this colour — summed by the caller into the realized
    acceptance diagnostic.
    """
    up, down, left, right = _neighbor_angle_sums(theta)
    # Current bond energy (the part that depends on θ_i): Σ_nbr cos(θ_i − θ_nbr).
    e_old = (
        torch.cos(theta - up) + torch.cos(theta - down)
        + torch.cos(theta - left) + torch.cos(theta - right)
    )
    u = (torch.rand(theta.shape, generator=g, device=theta.device) * 2.0 - 1.0)
    proposed = theta + delta.view(-1, 1, 1) * u
    e_new = (
        torch.cos(proposed - up) + torch.cos(proposed - down)
        + torch.cos(proposed - left) + torch.cos(proposed - right)
    )
    # E = -J Σ cos(...), so ΔE = -(e_new − e_old) (energy drops when cosines grow).
    dE = -(e_new - e_old)
    prob = torch.exp(-beta.view(-1, 1, 1) * dE).clamp(max=1.0)
    rand = torch.rand(theta.shape, generator=g, device=theta.device)
    flip = mask & (rand < prob)
    n_accepted = flip.sum(dim=(-1, -2))
    return torch.where(flip, proposed, theta), n_accepted


def _over_relax_half_sweep(theta: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """One microcanonical over-relaxation update of the sites on ``mask``.

    Reflects each masked spin about its local effective field
    H_i = Σ_nbr (cosθ_nbr, sinθ_nbr): the move θ_i → 2·φ_i − θ_i (with φ_i =
    atan2(H_y, H_x)) leaves every bond energy of site i unchanged (it is a
    reflection of θ_i across the field direction, and cos(2φ−θ−θ_nbr) summed over
    neighbours equals the original). Energy-conserving and deterministic, so it
    needs no Metropolis test, yet it rotates the long-wavelength spin-wave modes
    that single-site Metropolis decorrelates only slowly — the standard cure for
    XY critical slowing near T_BKT. Exact in parallel on a checkerboard colour
    (neighbours held fixed).
    """
    up, down, left, right = _neighbor_angle_sums(theta)
    hx = torch.cos(up) + torch.cos(down) + torch.cos(left) + torch.cos(right)
    hy = torch.sin(up) + torch.sin(down) + torch.sin(left) + torch.sin(right)
    phi = torch.atan2(hy, hx)
    reflected = 2.0 * phi - theta
    return torch.where(mask, reflected, theta)


def _wolff_update(theta: torch.Tensor, beta: torch.Tensor, g: torch.Generator) -> torch.Tensor:
    """One single-cluster Wolff move per batched lattice (the embedded-Ising trick).

    The embedded-Ising (Wolff–Kosterlitz) construction. Pick a random axis r̂ at
    angle α; each spin's Ising variable is ε_i = sign(p_i), p_i = cos(θ_i − α) =
    s_i·r̂. Two **same-ε** neighbours are bonded with the FK-style probability
    1 − exp(−2·β·J·p_i·p_j) (only when p_i·p_j > 0, i.e. ε_i = ε_j; opposite-sign
    pairs never bond), the seed's component is grown to a fixpoint over the *frozen*
    bond field (the same load-bearing facts as ``wolff.py``: each undirected bond
    drawn once, the field frozen before the flood), and the whole (monochromatic-ε)
    cluster has its Ising spin **flipped** ε_i → −ε_i.

    Flipping ε is **reflection across the line PERPENDICULAR to r̂** — it negates
    the component of s_i along r̂ and keeps the perpendicular component — which in
    angles is θ_i → 2α + π − θ_i (this sends p_i → −p_i; reflecting across r̂
    itself, the naive ``2α − θ``, *preserves* p_i and does NOT flip ε, so it is
    NOT the Wolff move and fails to order a cold lattice). This is the O(2)
    analogue of the Ising single-cluster flip and is rejection-free. Pure: returns
    new angles, does not mutate ``theta``.
    """
    from .wolff import _grow_cluster, _seed_mask

    n_temps, L, _ = theta.shape
    device = theta.device
    alpha = torch.rand((n_temps, 1, 1), generator=g, device=device) * TWO_PI
    proj = torch.cos(theta - alpha)                       # p_i = s_i·r̂, (n_temps, L, L)

    # Bond activation along the two torus orientations (down, right) — each
    # undirected bond exactly once (mirrors wolff._bond_field). p_i·p_j > 0 ⇔ the
    # two sites share an ε sign; the clamp(max=0) zeroes the activation prob for
    # opposite-sign pairs, so the draw can never bond across an ε domain wall.
    down_proj = torch.roll(proj, shifts=-1, dims=-2)
    right_proj = torch.roll(proj, shifts=-1, dims=-1)
    p_down = 1.0 - torch.exp((-2.0 * beta.view(n_temps, 1, 1) * (proj * down_proj)).clamp(max=0.0))
    p_right = 1.0 - torch.exp((-2.0 * beta.view(n_temps, 1, 1) * (proj * right_proj)).clamp(max=0.0))
    u_down = torch.rand(theta.shape, generator=g, device=device)
    u_right = torch.rand(theta.shape, generator=g, device=device)
    bond_down = u_down < p_down
    bond_right = u_right < p_right

    seed = _seed_mask(n_temps, L, device, g)
    in_cluster = _grow_cluster(seed, bond_down, bond_right)
    # Flip the embedded Ising spin: reflect across the line ⊥ r̂ → θ → 2α + π − θ.
    reflected = 2.0 * alpha + math.pi - theta
    return torch.where(in_cluster, reflected, theta)


def _delta_for(T: torch.Tensor) -> torch.Tensor:
    """Per-temperature Metropolis proposal width δ(T), tuned for ~30–50% acceptance.

    A planar spin in a local field of magnitude h sees an energy scale ~h·δ² for a
    small kick δ, so the acceptance is governed by β·h·δ² ~ O(1) → δ ∝ √(T/h).
    With h = O(1) near the transition, δ ∝ √T holds the acceptance in band across
    the whole sweep; we clamp it to [0.6, π] so it never collapses (too small,
    frozen) nor wraps absurdly (too large, ~0 acceptance). Realized acceptance is
    measured and reported, so a mistune is visible, not silent.
    """
    return torch.sqrt(T).clamp(min=0.6, max=math.pi)


def run(cfg: XYRunConfig) -> XYRunResult:
    """Run a batched 2D XY sweep on the square lattice: one lattice per temperature.

    Mirrors ``ising.run`` — a burn-in then a measurement phase — but the spins are
    continuous angles and the headline observable is the **helicity modulus** Υ(T)
    (the BKT signature), assembled from the per-sample helicity ingredients via the
    Teitel–Jayaprakash / Weber–Minnhagen estimator (see the module docstring):

        Υ = ⟨cos_term⟩ − (β/N)·[ Var(I_x) + Var(I_y) ] / 2

    where the cosine term is already the per-spin average over the two bond
    directions and Var is the *connected* variance of each direction's whole-lattice
    bond current across the measurement samples. ⟨|m|⟩ and the realized acceptance
    are carried as diagnostics (⟨|m|⟩ is NOT the order parameter here).

    Two updaters share this driver (``cfg.updater``):

    * ``'metropolis'`` (default) — per-T-tuned-δ checkerboard Metropolis with
      ``cfg.over_relax`` interleaved microcanonical over-relaxation sweeps (the
      cure for XY critical slowing); ``n_burnin``/``n_sweeps`` count Metropolis
      sweeps.
    * ``'wolff'`` — the embedded-Ising single-cluster reflection move, for the
      hardest near-T_BKT points; ``n_burnin``/``n_sweeps`` count cluster updates.
    """
    if cfg.updater not in ("metropolis", "wolff"):
        raise ValueError(f"unknown updater {cfg.updater!r} (use 'metropolis' or 'wolff')")
    device = torch.device(cfg.device)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 1)

    T = torch.linspace(cfg.T_min, cfg.T_max, cfg.n_temps, device=device, dtype=torch.float32)
    beta = 1.0 / T
    N = cfg.L * cfg.L

    # Random initial angles θ ∈ [0, 2π).
    theta = torch.rand((cfg.n_temps, cfg.L, cfg.L), generator=g_init, device=device,
                       dtype=torch.float32) * TWO_PI

    use_wolff = cfg.updater == "wolff"
    if not use_wolff:
        mask_a, mask_b = _checkerboard_masks(cfg.L, cfg.n_temps, device)
        delta = _delta_for(T)

    # accept_num / accept_den accumulate the realized Metropolis acceptance; one
    # full sweep proposes a move at every one of the N sites (both colours).
    accept_num = torch.zeros(cfg.n_temps, device=device)
    accept_den = 0

    def _metropolis_sweep(th):
        nonlocal accept_num, accept_den
        th, na = _metropolis_half_sweep(th, beta, mask_a, delta, g_step)
        th, nb = _metropolis_half_sweep(th, beta, mask_b, delta, g_step)
        accept_num += (na + nb).float()
        accept_den += N
        for _ in range(cfg.over_relax):
            th = _over_relax_half_sweep(th, mask_a)
            th = _over_relax_half_sweep(th, mask_b)
        return th

    def _wolff_sweep(th):
        return _wolff_update(th, beta, g_step)

    step = _wolff_sweep if use_wolff else _metropolis_sweep

    t0 = time.time()
    # Burn-in (acceptance during burn-in is not counted toward the diagnostic).
    if not use_wolff:
        for _ in range(cfg.n_burnin):
            theta = _metropolis_half_sweep(theta, beta, mask_a, delta, g_step)[0]
            theta = _metropolis_half_sweep(theta, beta, mask_b, delta, g_step)[0]
            for _ in range(cfg.over_relax):
                theta = _over_relax_half_sweep(theta, mask_a)
                theta = _over_relax_half_sweep(theta, mask_b)
    else:
        for _ in range(cfg.n_burnin):
            theta = step(theta)

    # Measurement phase
    cos_samples = []
    ix_samples = []
    iy_samples = []
    energy_samples = []
    absmag_samples = []
    for s in range(cfg.n_sweeps):
        theta = step(theta)
        if s % cfg.sample_every == 0:
            cos_term, cur_x, cur_y = _helicity_terms(theta)
            cos_samples.append(cos_term.cpu())
            ix_samples.append(cur_x.cpu())
            iy_samples.append(cur_y.cpu())
            energy_samples.append(_energy_per_spin(theta).cpu())
            absmag_samples.append(_abs_mag(theta).cpu())
    wall = time.time() - t0

    cos_term = torch.stack(cos_samples)          # (n_samples, n_temps)
    cur_x = torch.stack(ix_samples)
    cur_y = torch.stack(iy_samples)
    energy = torch.stack(energy_samples)
    absmag = torch.stack(absmag_samples)
    T_np = T.cpu().numpy()
    beta_np = (1.0 / T).cpu().numpy()
    n_samples = len(cos_samples)

    # Helicity modulus Υ(T) — the BKT observable.
    # First term: ⟨cos_term⟩ (already the per-spin average over x and y bonds).
    # Second term: (β/N)·½·[Var(I_x) + Var(I_y)] — the connected variance of each
    # direction's whole-lattice bond current, averaged over the two directions, with
    # the β/N weighting. (Both directions are equivalent on the square lattice; the
    # ½·(x+y) average just halves the statistical noise.)
    cos_mean = cos_term.mean(dim=0).numpy()
    var_ix = cur_x.var(dim=0, unbiased=False).numpy()   # ⟨I_x²⟩ − ⟨I_x⟩², connected
    var_iy = cur_y.var(dim=0, unbiased=False).numpy()
    fluct = (beta_np / N) * 0.5 * (var_ix + var_iy)
    helicity = cos_mean - fluct

    # Standard error of Υ: the cosine term dominates the easily-estimable error
    # (the fluctuation term's error is higher-order); report the cosine-term SEM as
    # an honest, slightly-conservative Υ error bar for the plot.
    helicity_err = (cos_term.std(dim=0) / np.sqrt(max(1, n_samples))).numpy()

    energy_mean = energy.mean(dim=0).numpy()
    abs_mag_mean = absmag.mean(dim=0).numpy()
    acceptance = (
        (accept_num / accept_den).cpu().numpy() if (not use_wolff and accept_den > 0)
        else np.full(cfg.n_temps, np.nan)
    )

    pick_idx = [0, cfg.n_temps // 2, cfg.n_temps - 1]
    snapshots = {f"T={T_np[i]:.3f}": theta[i].cpu().numpy() for i in pick_idx}

    return XYRunResult(
        config=cfg,
        T=T_np,
        helicity_modulus=helicity,
        helicity_err=helicity_err,
        energy=energy_mean,
        abs_mag=abs_mag_mean,
        acceptance=acceptance,
        snapshots=snapshots,
        wall_seconds=wall,
    )
