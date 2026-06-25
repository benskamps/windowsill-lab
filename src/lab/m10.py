"""M10 — antiferromagnetic Ising on the bipartite square lattice.

A framework sanity check, not new physics. M01–M09 explored new geometries,
dimensions, spin types, and the absence of order; M10 asks a plumbing question:
**does the engine handle a negative coupling cleanly and still land on a known
answer?** Set J = −1 (antiferromagnetic) on the square lattice and the model is —
by the bipartite sublattice gauge transformation ``s_i → −s_i for i ∈ B`` —
*exactly* the ferromagnet in disguise. So its Néel temperature is Onsager's same
exact value:

    T_N = 2 / ln(1 + √2) ≈ 2.26919          (k_B = 1)

the number M01 (magnetization) and M04 (specific heat) already verified.

The twist is the **order parameter**. The uniform ⟨|m|⟩ stays ≈ 0 for the AFM (the
Néel ground state carries no net moment), so reading it would show nothing and
look broken — that is the milestone's whole point. The order parameter is the
**staggered** magnetization m_s = (1/N)Σ ε_i s_i with ε_i = (−1)^(x+y), and its
susceptibility χ_s = N·(⟨m_s²⟩−⟨|m_s|⟩²)/T peaks at T_N. ``run_m10`` locates that
peak the way ``run_m04`` located the FM χ/C peak — coarse argmax refined by a
3-point parabola — and the specific-heat peak from the same run is the independent
thermal cross-check. On a finite L the peak sits a little above the
infinite-volume value (the same O(L^−1/ν) finite-size shift M04/M05/M06 carry), so
the headline is honestly a finite-L estimate.

The analysis reuses m06's NumPy-only peak finders; ``run_m10`` drives the
antiferromagnetic sweep ``ising_afm.run``.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .m06 import refine_peak, specific_heat_peak, susceptibility_peak

# Onsager's exact 2D Ising critical temperature — the Néel temperature of the
# bipartite-square AFM is identical to it by the sublattice gauge duality.
TC_AFM = 2.0 / math.log(1.0 + math.sqrt(2.0))           # ≈ 2.269185


@dataclass
class M10Result:
    T: list
    chi_staggered: list      # staggered susceptibility χ_s at each T (headline observable)
    stag_mag: list           # ⟨|m_s|⟩ staggered order parameter
    stag_mag_err: list
    abs_mag: list            # UNIFORM ⟨|m|⟩ — stays ≈0 (the trap, carried for the page)
    energy: list
    specific_heat: list
    L: int
    tc_chi: float            # χ_s-peak T_N estimate (coarse-grid argmax)
    tc_chi_refined: float    # parabola-refined χ_s-peak (headline)
    tc_cv_refined: float     # specific-heat-peak T_N from the SAME run (cross-check)
    tc_benchmark: float      # TC_AFM (Onsager exact)
    rel_error: float         # |tc_chi_refined − TC_AFM| / TC_AFM
    max_abs_mag: float       # the largest UNIFORM ⟨|m|⟩ over the sweep — must stay ≈0
    wall_seconds: float
    config: dict


def run_m10(
    L: int = 128,
    T_min: float = 2.0,
    T_max: float = 2.6,
    n_temps: int = 25,
    n_sweeps: int = 40000,
    n_burnin: int = 8000,
    seed: int = 42,
    device: str = "cuda",
    progress=None,
) -> M10Result:
    """Run the antiferromagnetic Ising sweep over a window straddling T_N and locate the χ_s peak.

    Mirrors ``run_m04``: a single batched sweep over a tight window around the
    exact T_N ≈ 2.2692, wall-clock timing, a ``progress`` callback, and a
    ``to_report``-ready result. The **staggered** susceptibility χ_s peak gives the
    headline finite-L T_N; the specific-heat peak from the same run is the
    independent thermal cross-check. The largest uniform ⟨|m|⟩ over the sweep is
    captured too — it must stay ≈ 0 (the AFM has no net moment), the deliberate
    "uniform m looks broken" contrast the milestone is built around.
    """
    from .ising_afm import AFMRunConfig, run

    t0 = time.time()
    cfg = AFMRunConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed, device=device, J=-1.0,
    )
    r = run(cfg)

    _, tc_chi = susceptibility_peak(r.T, r.chi_staggered)
    tc_chi_refined = refine_peak(r.T, r.chi_staggered)
    tc_cv_refined = refine_peak(r.T, r.specific_heat)
    rel_err = abs(tc_chi_refined - TC_AFM) / TC_AFM

    result = M10Result(
        T=r.T.tolist(),
        chi_staggered=r.chi_staggered.tolist(),
        stag_mag=r.stag_mag.tolist(),
        stag_mag_err=r.stag_mag_err.tolist(),
        abs_mag=r.abs_mag.tolist(),
        energy=r.energy.tolist(),
        specific_heat=r.specific_heat.tolist(),
        L=L,
        tc_chi=tc_chi,
        tc_chi_refined=tc_chi_refined,
        tc_cv_refined=tc_cv_refined,
        tc_benchmark=TC_AFM,
        rel_error=rel_err,
        max_abs_mag=float(max(r.abs_mag)),
        wall_seconds=time.time() - t0,
        config={
            "L": L, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed,
            "J": -1.0, "lattice": "square-afm",
        },
    )
    if progress is not None:
        progress(result)
    return result


def to_report(result: M10Result) -> dict:
    """A JSON report shaped for the page + the M10 check.

    Distinct ``experiment`` tag (``M10-afm-ising``) so the single-peak χ-checks all
    skip it — note it carries the staggered susceptibility under ``chi_staggered``,
    NOT a top-level ``chi``, so ``check_m01`` (which reads ``chi``) is not-applicable
    by structure as well as by tag, and ``check_m10`` claims it. Carries the per-T
    arrays the page needs and the headline T_N numbers ``check_m10`` re-derives,
    plus ``max_abs_mag`` (the uniform ⟨|m|⟩ ceiling — the AFM signature: it stays
    ≈0 while the staggered order parameter does all the work).
    """
    return {
        "experiment": "M10-afm-ising",
        "headline": (
            f"Antiferromagnetic Ising (L={result.L}): staggered χ_s peaks at "
            f"T_N={result.tc_chi_refined:.3f} vs Onsager exact {result.tc_benchmark:.4f} "
            f"(rel. err {result.rel_error*100:.1f}%); C-peak cross-check "
            f"{result.tc_cv_refined:.3f}; uniform ⟨|m|⟩ stays ≤{result.max_abs_mag:.3f} "
            f"· {result.wall_seconds:.0f}s on GPU"
        ),
        "L": result.L,
        "T": result.T,
        "chi_staggered": result.chi_staggered,
        "stag_mag": result.stag_mag,
        "stag_mag_err": result.stag_mag_err,
        "abs_mag": result.abs_mag,
        "energy": result.energy,
        "specific_heat": result.specific_heat,
        "tc_chi": result.tc_chi,
        "tc_chi_refined": result.tc_chi_refined,
        "tc_cv_refined": result.tc_cv_refined,
        "tc_benchmark": result.tc_benchmark,
        "rel_error": result.rel_error,
        "max_abs_mag": result.max_abs_mag,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
