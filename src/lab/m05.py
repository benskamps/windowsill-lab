"""M05 — triangular-lattice 2D Ising: verify the exact T_c = 4 / ln 3.

M01–M04 calibrated the lab on the **square** lattice (Onsager's exact
T_c ≈ 2.2692). M05 changes the *geometry*, not the physics: the triangular
lattice is the square grid plus one diagonal, so each site has six neighbours
instead of four. It is still the J=1 ferromagnetic Ising model, still in the 2D
Ising universality class — the critical *exponents* are unchanged — but the
critical *temperature* is different, and it is known exactly:

    T_c = 4 / ln(3) ≈ 3.64096          (k_B = J = 1)

So M05 is a clean geometry check: a known-answer reproduction at a *new* number,
on an engine that had to abandon the square lattice's red/black checkerboard
(the triangular lattice is non-bipartite) for a **3-sublattice** update — see
``ising_tri``. We locate T_c the way M01 did: run a batch of independent lattices,
one temperature each across a window straddling 3.641, and find where the
|m|-susceptibility χ peaks; the specific-heat peak from the same run is the
independent thermal cross-check. On a finite L the peak sits at a pseudo-critical
``T_c(L)`` shifted *above* the infinite-volume value by an O(L^−1/ν) amount, so
the headline is honestly a finite-L estimate (the check's ±0.15 tolerance, like
M06's, absorbs that shift).

The analysis reuses m06's NumPy-only peak finders; ``run_m05`` drives the
triangular sweep ``ising_tri.run``.
"""
from __future__ import annotations
from .hw import hw

import math
import time
from dataclasses import dataclass

from .m06 import refine_peak, specific_heat_peak, susceptibility_peak

# Exact triangular-lattice 2D Ising critical temperature (k_B = J = 1).
TC_TRI = 4.0 / math.log(3.0)           # ≈ 3.640957


@dataclass
class M05Result:
    T: list
    chi: list                # |m|-susceptibility at each T (headline observable)
    abs_mag: list
    abs_mag_err: list
    energy: list
    specific_heat: list
    L: int
    tc_chi: float            # χ-peak T_c estimate (coarse-grid argmax)
    tc_chi_refined: float    # parabola-refined χ-peak (headline)
    tc_cv_refined: float     # specific-heat-peak T_c from the SAME run (cross-check)
    tc_benchmark: float      # TC_TRI (exact)
    rel_error: float         # |tc_chi_refined − TC_TRI| / TC_TRI
    wall_seconds: float
    config: dict


def run_m05(
    L: int = 129,
    T_min: float = 3.3,
    T_max: float = 4.0,
    n_temps: int = 25,
    n_sweeps: int = 40000,
    n_burnin: int = 8000,
    seed: int = 42,
    device: str = "cuda",
    progress=None,
) -> M05Result:
    """Run the triangular Ising sweep over a window straddling T_c and locate the χ peak.

    Mirrors ``run_m04``: a single batched sweep over a tight window around the
    exact triangular T_c ≈ 3.641, wall-clock timing, a ``progress`` callback, and a
    ``to_report``-ready result. The χ-peak gives the headline finite-L T_c; the
    specific-heat peak from the same run is the independent thermal cross-check.

    ``L`` defaults to 129 — the multiple of 3 nearest the square engine's 128 —
    because the triangular 3-colour update only wraps cleanly when 3 | L (see
    ``ising_tri``; it raises otherwise).
    """
    from .ising_tri import TriRunConfig, run

    t0 = time.time()
    cfg = TriRunConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed, device=device,
    )
    r = run(cfg)

    _, tc_chi = susceptibility_peak(r.T, r.chi_abs)
    tc_chi_refined = refine_peak(r.T, r.chi_abs)
    tc_cv_refined = refine_peak(r.T, r.specific_heat)
    rel_err = abs(tc_chi_refined - TC_TRI) / TC_TRI

    result = M05Result(
        T=r.T.tolist(),
        chi=r.chi_abs.tolist(),
        abs_mag=r.abs_mag.tolist(),
        abs_mag_err=r.abs_mag_err.tolist(),
        energy=r.energy.tolist(),
        specific_heat=r.specific_heat.tolist(),
        L=L,
        tc_chi=tc_chi,
        tc_chi_refined=tc_chi_refined,
        tc_cv_refined=tc_cv_refined,
        tc_benchmark=TC_TRI,
        rel_error=rel_err,
        wall_seconds=time.time() - t0,
        config={
            "L": L, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed,
            "lattice": "triangular",
        },
    )
    if progress is not None:
        progress(result)
    return result


def to_report(result: M05Result) -> dict:
    """A JSON report shaped for the page + the M05 check.

    Distinct ``experiment`` tag (``M05-triangular``) so check_m01's χ-peak check
    skips it (it carries top-level ``T``/``chi`` but a different ``experiment``
    field and a different T_c — ``check_m05`` claims it), with the per-T arrays the
    page needs and the headline T_c numbers ``check_m05`` re-derives.
    """
    return {
        "experiment": "M05-triangular",
        "headline": (
            f"Triangular-lattice 2D Ising (L={result.L}): χ peaks at "
            f"T_c={result.tc_chi_refined:.3f} vs exact 4/ln3 = {result.tc_benchmark:.4f} "
            f"(rel. err {result.rel_error*100:.1f}%); C-peak cross-check "
            f"{result.tc_cv_refined:.3f} · {result.wall_seconds:.0f}s on {hw(result.config)}"
        ),
        "L": result.L,
        "T": result.T,
        "chi": result.chi,
        "abs_mag": result.abs_mag,
        "abs_mag_err": result.abs_mag_err,
        "energy": result.energy,
        "specific_heat": result.specific_heat,
        "tc_chi": result.tc_chi,
        "tc_chi_refined": result.tc_chi_refined,
        "tc_cv_refined": result.tc_cv_refined,
        "tc_benchmark": result.tc_benchmark,
        "rel_error": result.rel_error,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
