"""Batched 2D random-bond Ising on GPU — quenched ±J disorder at a tunable AF fraction p.

M14 is the random-bond Ising model: the M11/M12 ±J Edwards–Anderson machinery, but
with the disorder *biased*. Each bond is drawn once and frozen —

    J_ij = +J  with probability (1 − p),   −J  with probability p,

the ``p`` fraction of *antiferromagnetic* bonds tuning the model continuously from the
clean ferromagnet (p = 0) to the symmetric ±J spin glass (p = 1/2). The Hamiltonian is
the same quenched-disorder form M11 already runs,

    E = −Σ_⟨ij⟩ J_ij s_i s_j            (s_i = ±1, k_B = 1),

so this engine reuses ``spin_glass``'s three load-bearing primitives verbatim — the
checkerboard sublattice masks, the J-weighted neighbour sum, and the Metropolis
half-sweep — and changes exactly one thing: the bond draw is ``p``-biased instead of
50/50. Reusing those keeps the frustration bookkeeping (left/up bonds from the *rolled*
coupling tensors, verified against a brute-force bond sum in M11) from ever drifting.

### The Nishimori line — an exact, cheap calibration

The random-bond phase diagram lives in the ``(p, T)`` plane. Running through it is a
special curve, the **Nishimori line**,

    e^{−2J/T} = p / (1 − p)      ⇔      tanh(J/T) = 1 − 2p,

on which a hidden gauge symmetry makes several quantities **exactly known** — the reason
M14 can calibrate cheaply instead of chasing a hard critical point. The cleanest is the
internal energy: Nishimori proved the disorder-averaged bond energy on the line is

    [⟨ −J_ij s_i s_j ⟩] = −J tanh(J/T)      (exact, any lattice),

so the energy **per spin** on the square lattice (2 bonds/spin) is

    E/N = −2 J tanh(J/T) = −2 J (1 − 2p)    on the Nishimori line.

This engine measures ``E/N`` exactly as ``spin_glass`` does (−½⟨s·field⟩), disorder-
averaged over many realizations, so ``m14`` can point it at a handful of ``(p, T_NL(p))``
points and check the measured energy against ``−2 tanh(1/T)`` — a rigorous receipt that
holds at modest ``L`` because it is an *identity on the line*, not a finite-size-shifted
critical temperature.

### The multicritical (Nishimori) point — the ferromagnet's endpoint on the line

The ferromagnetic order that survives at small ``p`` dies as ``p`` grows; where the
ferro–paramagnet boundary crosses the Nishimori line is the **multicritical Nishimori
point (MNP)**, the square-lattice benchmark ``p_c ≈ 0.1094, T_c ≈ 0.9528``. So the same
sweep that calibrates the energy also **maps** the MNP: walking ``p`` up the Nishimori
line, the disorder-averaged order parameter ⟨|m|⟩ collapses toward zero near ``p_c``.
Pinning ``p_c`` *precisely* needs large ``L`` and many realizations (a hero run); at the
windowsill's reachable scale the collapse locates it only approximately — reported
honestly as such, while the energy identity carries the verified claim.

### Batch layout

One pass sweeps ``(n_realizations × n_temps)`` single lattices in parallel (no replicas —
M14's observables are the energy and the ferromagnetic magnetization, both single-copy).
Bonds are per-(realization); ``m14`` calls the engine once per ``(p, T)`` point, so a
whole point is one batched pass over its disorder realizations.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict

import numpy as np
import torch

# Reuse M11's three load-bearing primitives verbatim — same checkerboard, same
# J-weighted neighbour sum (left/up bonds from the rolled coupling tensors), same
# Metropolis half-sweep — so the random-bond engine can never drift from the EA one.
from .spin_glass import _checkerboard_masks, _weighted_neighbor_sum, _half_sweep


def nishimori_temperature(p: float, J: float = 1.0) -> float:
    """The Nishimori-line temperature for an AF-bond fraction ``p``.

    Inverts ``e^{−2J/T} = p/(1−p)`` → ``T_NL = 2J / ln((1−p)/p)``. Only defined for
    ``0 < p < 1/2`` (the ferromagnetic side, where the MNP lives); at ``p = 1/2`` the
    line runs to infinite temperature. Equivalent to ``tanh(J/T_NL) = 1 − 2p``.
    """
    if not (0.0 < p < 0.5):
        raise ValueError(f"Nishimori temperature is defined for 0 < p < 1/2 (got p={p})")
    return 2.0 * J / math.log((1.0 - p) / p)


def nishimori_energy_per_spin(T: float, J: float = 1.0, bonds_per_spin: int = 2) -> float:
    """Exact disorder-averaged internal energy per spin ON the Nishimori line.

    ``E/N = −(bonds/spin)·J·tanh(J/T)`` (= ``−2 J tanh(J/T)`` on the square lattice).
    On the line ``tanh(J/T) = 1 − 2p``, so this equals ``−2 J (1 − 2p)`` — an identity,
    not a fit, which is why it calibrates the engine at modest ``L``.
    """
    return -bonds_per_spin * J * math.tanh(J / T)


@dataclass
class RandomBondConfig:
    L: int = 24
    p: float = 0.1094              # AF-bond fraction; MNP benchmark p_c ≈ 0.1094
    T: float = 0.9528              # temperature (K); default sits at the MNP
    n_realizations: int = 64       # quenched ±J disorder samples to average over
    n_burnin: int = 6000
    n_sweeps: int = 12000
    sample_every: int = 20
    seed: int = 42
    device: str = "cuda"
    J: float = 1.0

    def n_samples(self) -> int:
        return self.n_sweeps // self.sample_every


@dataclass
class RandomBondResult:
    config: RandomBondConfig
    p: float
    T: float
    energy: float          # disorder-averaged energy per spin
    energy_err: float      # SEM across realizations
    abs_mag: float         # disorder-averaged ⟨|m|⟩ — the ferromagnetic order parameter
    m2: float              # disorder-averaged ⟨m²⟩
    m4: float              # disorder-averaged ⟨m⁴⟩
    binder: float          # magnetic Binder cumulant U = 1 − ⟨m⁴⟩/(3⟨m²⟩²)
    energy_exact_nl: float  # exact Nishimori-line energy per spin at this T
    on_nishimori_line: bool  # whether (p, T) sits on the line (within a tight tol)
    wall_seconds: float

    def to_json(self) -> dict:
        return {
            "config": asdict(self.config),
            "p": self.p,
            "T": self.T,
            "energy": self.energy,
            "energy_err": self.energy_err,
            "abs_mag": self.abs_mag,
            "m2": self.m2,
            "m4": self.m4,
            "binder": self.binder,
            "energy_exact_nl": self.energy_exact_nl,
            "on_nishimori_line": self.on_nishimori_line,
            "wall_seconds": self.wall_seconds,
        }


def _draw_bonds(R: int, L: int, p: float, J: float, gen: torch.Generator,
                device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    """Per-realization ±J bonds with an AF fraction ``p`` — the ONE change from M11.

    ``Jx[r,i,j]`` couples site (i,j) to its right neighbour, ``Jy`` to its down
    neighbour (the convention ``_weighted_neighbor_sum`` expects). Each bond is ``−J``
    (antiferromagnetic) with probability ``p``, else ``+J``. M11 draws the symmetric
    50/50 case; here the fraction is tunable, which is the whole random-bond model.
    """
    def one() -> torch.Tensor:
        u = torch.rand((R, L, L), generator=gen, device=device)
        # −J where u < p (antiferromagnetic bond), else +J.
        return torch.where(u < p, torch.full_like(u, -J), torch.full_like(u, J))
    return one(), one()


def run(cfg: RandomBondConfig) -> RandomBondResult:
    """Run a batched random-bond Ising point ``(p, T)`` over its disorder realizations.

    Sweeps ``n_realizations`` independent ±J lattices (bond fraction ``p``) at the single
    temperature ``T`` in one pass, then reduces to the disorder-averaged energy per spin
    (the Nishimori-line calibration observable), the ferromagnetic ⟨|m|⟩ / ⟨m²⟩ / ⟨m⁴⟩ and
    magnetic Binder cumulant (the MNP-location observables). ``m14`` calls this once per
    ``(p, T_NL(p))`` point along the Nishimori line.
    """
    device = torch.device(cfg.device)
    R, L = cfg.n_realizations, cfg.L
    N = L * L

    g_bond = torch.Generator(device=device).manual_seed(cfg.seed)
    g_init = torch.Generator(device=device).manual_seed(cfg.seed + 1)
    g_step = torch.Generator(device=device).manual_seed(cfg.seed + 2)

    beta = torch.full((R, 1, 1), 1.0 / cfg.T, device=device)
    Jx, Jy = _draw_bonds(R, L, cfg.p, cfg.J, g_bond, device)
    spins = (torch.randint(0, 2, (R, L, L), generator=g_init, device=device,
                           dtype=torch.int8) * 2 - 1)
    mask_a, mask_b = _checkerboard_masks(L, R, device)

    t0 = time.time()
    for _ in range(cfg.n_burnin):
        spins = _half_sweep(spins, beta, Jx, Jy, mask_a, g_step)
        spins = _half_sweep(spins, beta, Jx, Jy, mask_b, g_step)

    e_acc = torch.zeros(R, device=device)      # per-realization energy/spin sum
    m2_acc = torch.zeros(R, device=device)
    m4_acc = torch.zeros(R, device=device)
    mabs_acc = torch.zeros(R, device=device)
    n_samp = 0
    for s in range(cfg.n_sweeps):
        spins = _half_sweep(spins, beta, Jx, Jy, mask_a, g_step)
        spins = _half_sweep(spins, beta, Jx, Jy, mask_b, g_step)
        if s % cfg.sample_every == 0:
            sv = spins.float()
            field = _weighted_neighbor_sum(spins, Jx, Jy).float()
            # Energy per spin, same estimator as spin_glass: −½⟨s·field⟩ counts each
            # bond once (field sums all four neighbours → every bond twice).
            e_acc += (-0.5 * (sv * field).mean(dim=(-1, -2)))
            m = sv.mean(dim=(-1, -2))                # signed magnetization per realization
            m2_acc += m * m
            m4_acc += m ** 4
            mabs_acc += m.abs()
            n_samp += 1
    wall = time.time() - t0

    e_per = (e_acc / n_samp).cpu().numpy()          # (R,)
    m2_per = (m2_acc / n_samp).cpu().numpy()
    m4_per = (m4_acc / n_samp).cpu().numpy()
    mabs_per = (mabs_acc / n_samp).cpu().numpy()

    energy = float(np.mean(e_per))
    energy_err = float(np.std(e_per) / math.sqrt(R))
    m2 = float(np.mean(m2_per))
    m4 = float(np.mean(m4_per))
    abs_mag = float(np.mean(mabs_per))
    # Magnetic Binder cumulant from the disorder-averaged moments. U → 2/3 in the
    # ordered (ferro) phase, → 0 in the disordered phase; the L-crossing marks the MNP.
    binder = float(1.0 - m4 / (3.0 * m2 ** 2)) if m2 > 0 else 0.0

    e_exact = nishimori_energy_per_spin(cfg.T, cfg.J)
    # Is (p, T) on the Nishimori line? tanh(J/T) should equal 1 − 2p.
    on_nl = abs(math.tanh(cfg.J / cfg.T) - (1.0 - 2.0 * cfg.p)) <= 1e-3

    return RandomBondResult(
        config=cfg, p=cfg.p, T=cfg.T,
        energy=energy, energy_err=energy_err,
        abs_mag=abs_mag, m2=m2, m4=m4, binder=binder,
        energy_exact_nl=e_exact, on_nishimori_line=on_nl,
        wall_seconds=wall,
    )
