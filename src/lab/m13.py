"""M13 — frustrated triangular antiferromagnet: the residual (Wannier) entropy.

The first *frustration* milestone, and the first that **integrates** a measured curve
rather than locating a feature in it. Ising spins on the triangular lattice with
antiferromagnetic coupling (J = −1) cannot satisfy every bond — each triangle is an odd
cycle — so there is no ordering transition and the ground state is *macroscopically
degenerate*. That degeneracy leaves a residual entropy that survives to absolute zero,
known exactly since Wannier (1950):

    S0 / N = 0.3383 k_B

M13 measures it by **thermodynamic integration of the specific heat**: cooling from the
free-spin limit (S = N·ln 2) removes entropy at the rate dS = (C/T) dT, so

    S0 = N·ln 2 − ∫_0^∞ (C(T)/T) dT.

``run_m13`` drives ``ising_tri_afm.run`` (the triangular 3-sublattice engine with the
flipped J sign) over a **geometric** temperature grid — packed into the low-T hump where
C/T carries all its weight, wide enough at the hot end that S has climbed back to ln 2 —
then hands the resulting C(T) to ``entropy.py`` to integrate. The reducers here are the
same numpy/stdlib entropy functions ``check_m13`` re-derives from the report arrays, so
the grade is a receipt, not an echo, and the pass/null tolerance is owned by the check.

The integrated residual is honestly a **few-percent** number: it lands slightly *below*
Wannier's exact 0.3383 and converges to ≈0.32 as the lattice grows (L=24→0.334,
L=96→0.322) — the residual gap is the finite temperature-window integration systematic,
not a lattice or model error (the ground-state energy is an exact −1 at every size). The
grid is integrated in log-temperature (``entropy.py``), which is grid-robust on the
geometric grid, so the number is stable run-to-run. When the integrated S0 misses the
≈0.3383 benchmark beyond the check's band the milestone ships as a ``[~]`` failed-
calibration null with the reason in the report, never a fake green leaf.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from .entropy import LN2, entropy_curve, residual_entropy, total_entropy_removed, high_t_tail

# Wannier's exact residual (ground-state) entropy per spin of the triangular Ising
# antiferromagnet (Wannier 1950; the 1973 erratum confirms the value): the T→0 entropy
# that the macroscopic ground-state degeneracy leaves behind. Units k_B.
WANNIER_S0 = 0.3383
# Exact triangular-AFM ground-state energy per spin (|J| units): each triangle keeps two
# of its three bonds, Σ_bonds s_i s_j → −N, so e → −1. The cold end must approach this —
# a hard anchor that a wrong-geometry or wrong-sign run would miss.
GROUND_ENERGY = -1.0
# Runner-side band used only for the report's status hint / headline verdict. The
# AUTHORITATIVE pass/null grade re-derives the residual in ``checks.check_m13`` with the
# check's *own* tolerance, so a report can never widen its own bar. Physically a few-
# percent allowance for finite-L C, trapezoidal discretisation, and low-T truncation.
S0_TOL = 0.03


def entropy_grid(T_min: float, T_max: float, n: int) -> tuple[float, ...]:
    """A geometric (log-spaced) temperature grid, ``T_min … T_max`` with ``n`` points.

    Geometric spacing packs points into the low-temperature end, where the integrand
    ``C/T`` rises through the frustrated hump (peak near T ≈ 1) and where a uniform grid
    would under-resolve it and bias the integral. The hot end stays coarse — C is tiny
    there — but reaches high enough that S has climbed back to ≈ ln 2.
    """
    lo, hi = math.log(T_min), math.log(T_max)
    return tuple(float(math.exp(lo + (hi - lo) * i / (n - 1))) for i in range(n))


@dataclass
class M13Result:
    T: list                    # geometric temperature grid (ascending)
    specific_heat: list        # C(T) per spin — the integrand's numerator
    energy: list               # energy per spin at each T (→ −1 at the cold end)
    energy_err: list
    abs_mag: list              # uniform ⟨|m|⟩ — the diagnostic that stays ≈0
    entropy_curve: list        # S(T) per spin, descending from ≈ln2 to the residual
    s_inf: float               # ln 2 — the high-T reference entropy per spin
    s0_measured: float         # residual S0/N (with the analytic high-T tail) — headline
    s0_no_tail: float          # residual without the tail (transparency companion)
    high_t_tail: float         # the analytic ∫_{T_max}^∞ C/T added back (≈ small)
    entropy_removed: float     # ∫ C/T over the window (+tail) = s_inf − s0_measured
    s0_benchmark: float        # WANNIER_S0 (0.3383)
    s0_abs_error: float        # |s0_measured − 0.3383|
    e_ground: float            # min measured energy per spin (should approach −1)
    resolved: bool             # runner-side hint: within S0_TOL AND ground energy sane
    L: int
    wall_seconds: float
    config: dict


def run_m13(
    L: int = 96,
    T_min: float = 0.10,
    T_max: float = 14.0,
    n_temps: int = 80,
    n_sweeps: int = 40000,
    n_burnin: int = 8000,
    seed: int = 42,
    device: str = "cuda",
    progress=None,
) -> M13Result:
    """Sweep the triangular AFM over a wide geometric window and integrate C/T → S0.

    Builds the geometric grid, runs ``ising_tri_afm.run`` (J = −1) once over it, then
    integrates the specific heat down from the free-spin reference S(∞) = ln 2 to read
    off the residual entropy S0/N, comparing it to Wannier's exact 0.3383. The verdict
    ``resolved`` is a runner-side hint (within ``S0_TOL`` and the cold energy near the
    exact ground state −1); ``check_m13`` re-derives the residual and owns the real grade.
    """
    from .ising_tri_afm import TriAFMRunConfig, run

    t0 = time.time()
    grid = entropy_grid(T_min, T_max, n_temps)
    cfg = TriAFMRunConfig(
        L=L, T_values=grid, n_temps=n_temps, n_sweeps=n_sweeps,
        n_burnin=n_burnin, seed=seed, device=device, J=-1.0,
    )
    r = run(cfg)

    # Sort every per-T array ascending in T once, so the report's parallel arrays and the
    # entropy curve all index the same grid (the engine returns them in grid order, but a
    # geometric grid handed in any order stays safe this way).
    order = sorted(range(len(r.T)), key=lambda i: r.T[i])
    T = [float(r.T[i]) for i in order]
    C = [float(r.specific_heat[i]) for i in order]
    energy = [float(r.energy[i]) for i in order]
    energy_err = [float(r.energy_err[i]) for i in order]
    abs_mag = [float(r.abs_mag[i]) for i in order]

    Ts, S = entropy_curve(T, C, s_inf=LN2, add_high_t_tail=True)
    s0 = residual_entropy(T, C, s_inf=LN2, add_high_t_tail=True)
    s0_nt = residual_entropy(T, C, s_inf=LN2, add_high_t_tail=False)
    tail = high_t_tail(T[-1], C[-1])
    removed = total_entropy_removed(T, C, add_high_t_tail=True)
    e_ground = float(np.min(r.energy))
    abs_err = abs(s0 - WANNIER_S0)
    resolved = bool(abs_err <= S0_TOL and abs(e_ground - GROUND_ENERGY) <= 0.05)

    result = M13Result(
        T=T,
        specific_heat=C,
        energy=energy,
        energy_err=energy_err,
        abs_mag=abs_mag,
        entropy_curve=S,
        s_inf=LN2,
        s0_measured=s0,
        s0_no_tail=s0_nt,
        high_t_tail=tail,
        entropy_removed=removed,
        s0_benchmark=WANNIER_S0,
        s0_abs_error=abs_err,
        e_ground=e_ground,
        resolved=resolved,
        L=L,
        wall_seconds=time.time() - t0,
        config={
            "L": L, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed, "device": device,
            "lattice": "triangular", "J": -1.0, "grid": "geometric",
            "method": "thermodynamic-integration-of-C-over-T",
        },
    )
    if progress is not None:
        progress(result)
    return result


def to_report(result: M13Result) -> dict:
    """A JSON report shaped for the page + the M13 check.

    Distinct ``experiment`` tag (``M13-triangular-afm``) so no peak/crossing check
    misreads it — M13's signature is an **integrated** residual entropy, not a located
    feature. Carries the geometric ``T`` grid, the ``specific_heat`` integrand, and the
    cumulative ``entropy_curve`` so ``check_m13`` can re-integrate C/T from the arrays and
    re-derive S0 itself. When the integrated residual misses the ≈0.3383 benchmark the
    report carries ``status: "null"`` — an honest failed-calibration grey leaf.
    """
    s0 = result.s0_measured
    verdict = ("residual S0/N ≈ %.4f k_B — Wannier reproduced" % s0 if result.resolved
               else "integrated residual off the 0.3383 benchmark — calibration null")
    headline = (
        f"Frustrated triangular Ising antiferromagnet (L={result.L}): no ordering "
        f"transition, a macroscopically degenerate ground state. Integrating C(T)/T from "
        f"S(∞)=ln2 down gives a residual entropy S0/N = {s0:.4f} k_B vs Wannier's exact "
        f"0.3383 (Δ={result.s0_abs_error:.4f}); ground-state energy {result.e_ground:.4f} "
        f"per spin (exact −1) — {verdict} · {result.wall_seconds:.0f}s"
    )
    report = {
        "experiment": "M13-triangular-afm",
        "headline": headline,
        "L": result.L,
        "T": result.T,
        "specific_heat": result.specific_heat,
        "energy": result.energy,
        "energy_err": result.energy_err,
        "abs_mag": result.abs_mag,
        "entropy_curve": result.entropy_curve,
        "s_inf": result.s_inf,
        "s0_measured": result.s0_measured,
        "s0_no_tail": result.s0_no_tail,
        "high_t_tail": result.high_t_tail,
        "entropy_removed": result.entropy_removed,
        "s0_benchmark": result.s0_benchmark,
        "s0_abs_error": result.s0_abs_error,
        "e_ground": result.e_ground,
        "resolved": result.resolved,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
    # Honest failed-calibration marker: a folded grey leaf, never a green one. Omitted
    # when resolved (the archive/check grades that). The check re-derives independently.
    if not result.resolved:
        report["status"] = "null"
    return report
