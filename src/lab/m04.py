"""M04 — 2D Ising specific heat: the logarithmic divergence at T_c.

M01–M03 read the *magnetic* response (susceptibility, finite-size scaling, the
β exponent). M04 reads the *thermal* response — the specific heat
``C(T) = (⟨E²⟩−⟨E⟩²)·N/T²``. In the 2D Ising model this is the Onsager
observable with the famous **logarithmic divergence** at the exact critical
temperature

    T_c = 2 / ln(1 + √2) ≈ 2.26919          (Onsager 1944 — the same T_c as M01)

so M04 is a *second, independent* calibration of the same critical point: M01's
magnetization said T_c from the order parameter; now the energy fluctuations
have to agree. On a finite L×L lattice the true divergence is rounded into a
finite peak sitting just above T_c (an O(L^−1/ν) finite-size shift), so the
headline is honestly a finite-L estimate — cross-checked against the χ-peak
from the same run.

Onsager's exact leading amplitude of the divergence
(``C ≈ −A·ln|1−T/T_c| + B``, units k_B = J = 1) is

    A = (2/π)·(2/T_c)² ≈ 0.4945

carried for context; a finite-L peak can't resolve it precisely, and the report
says so. The peak *location* is the calibrated claim.

The analysis reuses m06's NumPy-only peak finders; ``run_m04`` drives the same
2D sweep ``ising.run`` that M01 uses, just read through the C(T) lens.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .m06 import refine_peak, specific_heat_peak

# Onsager's exact 2D Ising critical temperature (k_B = J = 1).
TC_2D = 2.0 / math.log(1.0 + math.sqrt(2.0))           # ≈ 2.269185
# Leading amplitude of the logarithmic specific-heat divergence (context only).
LOG_AMPLITUDE = (2.0 / math.pi) * (2.0 / TC_2D) ** 2    # ≈ 0.4945


@dataclass
class M04Result:
    T: list
    specific_heat: list
    energy: list
    chi: list
    abs_mag: list
    abs_mag_err: list
    L: int
    tc_cv: float            # C-peak T_c estimate (coarse-grid argmax)
    tc_cv_refined: float    # parabola-refined C-peak (headline)
    tc_chi_refined: float   # χ-peak from the SAME run (independent cross-check)
    tc_benchmark: float     # TC_2D (Onsager exact)
    rel_error: float        # |tc_cv_refined − TC_2D| / TC_2D
    log_amplitude: float    # the analytical A, for context
    wall_seconds: float
    config: dict


def run_m04(
    L: int = 128,
    T_min: float = 2.0,
    T_max: float = 2.6,
    n_temps: int = 25,
    n_sweeps: int = 40000,
    n_burnin: int = 8000,
    seed: int = 42,
    device: str = "cuda",
    progress=None,
) -> M04Result:
    """Run the 2D Ising sweep over a window straddling T_c and locate the C peak.

    Mirrors ``run_m06``: a single batched sweep over a tight window around the
    exact 2D T_c ≈ 2.2692, wall-clock timing, a ``progress`` callback, and a
    ``to_report``-ready result. The specific-heat peak gives the headline
    finite-L T_c; the susceptibility peak from the same run is the cross-check.
    """
    from .ising import RunConfig, run

    t0 = time.time()
    cfg = RunConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed, device=device,
    )
    r = run(cfg)

    _, tc_cv = specific_heat_peak(r.T, r.specific_heat)
    tc_cv_refined = refine_peak(r.T, r.specific_heat)
    tc_chi_refined = refine_peak(r.T, r.chi_abs)
    rel_err = abs(tc_cv_refined - TC_2D) / TC_2D

    result = M04Result(
        T=r.T.tolist(),
        specific_heat=r.specific_heat.tolist(),
        energy=r.energy.tolist(),
        chi=r.chi_abs.tolist(),
        abs_mag=r.abs_mag.tolist(),
        abs_mag_err=r.abs_mag_err.tolist(),
        L=L,
        tc_cv=tc_cv,
        tc_cv_refined=tc_cv_refined,
        tc_chi_refined=tc_chi_refined,
        tc_benchmark=TC_2D,
        rel_error=rel_err,
        log_amplitude=LOG_AMPLITUDE,
        wall_seconds=time.time() - t0,
        config={
            "L": L, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed,
        },
    )
    if progress is not None:
        progress(result)
    return result


def to_report(result: M04Result) -> dict:
    """A JSON report shaped for the page + the M04 check.

    Distinct ``experiment`` tag (``M04-specific-heat``) so check_m01's χ-peak
    check skips it and ``check_m04`` claims it, with the per-T arrays the page
    needs and the headline numbers ``check_m04`` re-derives.
    """
    return {
        "experiment": "M04-specific-heat",
        "headline": (
            f"2D Ising specific heat (L={result.L}): C(T) peaks at "
            f"T_c={result.tc_cv_refined:.3f} vs Onsager exact {result.tc_benchmark:.4f} "
            f"(rel. err {result.rel_error*100:.1f}%); χ-peak cross-check "
            f"{result.tc_chi_refined:.3f} · {result.wall_seconds:.0f}s"
        ),
        "L": result.L,
        "T": result.T,
        "specific_heat": result.specific_heat,
        "energy": result.energy,
        "chi": result.chi,
        "abs_mag": result.abs_mag,
        "abs_mag_err": result.abs_mag_err,
        "tc_cv": result.tc_cv,
        "tc_cv_refined": result.tc_cv_refined,
        "tc_chi_refined": result.tc_chi_refined,
        "tc_benchmark": result.tc_benchmark,
        "rel_error": result.rel_error,
        "log_amplitude": result.log_amplitude,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
