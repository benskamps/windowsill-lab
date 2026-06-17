"""M06 — 3D simple-cubic Ising: verify the Monte-Carlo benchmark T_c ≈ 4.5115.

Phase 1 calibrated the lab against Onsager's *exact* 2D result. M06 is the first
Phase-2 step: the same machinery in three dimensions, where there is **no exact
solution** and the critical temperature is known only numerically. The
simple-cubic Ising model's critical temperature is a high-precision MC/series
benchmark:

    T_c / J ≈ 4.5115          (modern value ≈ 4.51152)

We locate it the way M01 located the 2D T_c — run a batch of independent L×L×L
lattices, one temperature each, and find where the magnetic susceptibility
χ(T) peaks. On a *finite* lattice that peak sits at a pseudo-critical
``T_c(L)`` shifted above the infinite-volume value by an O(L^(−1/ν)) amount, so
the headline number is honestly a finite-L estimate, not a precision Tc claim
(see the evidence-grade note in the report verdict).

The pure analysis functions here (``susceptibility_peak``,
``specific_heat_peak``, ``relative_error``) are NumPy-only and unit-tested
without running a single Monte-Carlo sweep. ``run_m06`` drives the actual
sweep via ``ising3d.run``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

# Simple-cubic Ising critical temperature — the Monte-Carlo / series benchmark.
# Modern high-precision value ≈ 4.51152; MILESTONES.md quotes the rounded 4.5115.
TC_3D = 4.5115

# 3D Ising critical exponents (NOT exact — best MC/conformal-bootstrap values),
# carried for context; M06 only *uses* T_c, but the report cites these as the
# reason the 2D exponents from M02/M03 must NOT be reused here.
BETA_3D = 0.3265     # magnetization exponent
GAMMA_3D = 1.2372    # susceptibility exponent
NU_3D = 0.6301       # correlation-length exponent


@dataclass
class M06Result:
    T: list                  # temperatures swept
    chi: list                # |m|-susceptibility at each T
    abs_mag: list            # ⟨|m|⟩ at each T (order parameter)
    abs_mag_err: list        # standard error of ⟨|m|⟩
    energy: list             # energy per spin at each T
    specific_heat: list      # C per spin at each T
    L: int
    tc_chi: float            # T_c estimate from the χ peak (headline)
    tc_chi_refined: float    # parabola-refined χ-peak T_c
    tc_cv: float             # T_c estimate from the specific-heat peak (cross-check)
    tc_benchmark: float      # 4.5115
    rel_error: float         # |tc_chi_refined − benchmark| / benchmark
    wall_seconds: float
    config: dict


def susceptibility_peak(T, chi) -> tuple[float, float]:
    """``(chi_max, T at the peak)`` from one χ(T) sweep (the coarse grid value)."""
    T = np.asarray(T, dtype=float)
    chi = np.asarray(chi, dtype=float)
    i = int(np.argmax(chi))
    return float(chi[i]), float(T[i])


def specific_heat_peak(T, cv) -> tuple[float, float]:
    """``(C_max, T at the peak)`` from one C(T) sweep — an independent T_c probe."""
    T = np.asarray(T, dtype=float)
    cv = np.asarray(cv, dtype=float)
    i = int(np.argmax(cv))
    return float(cv[i]), float(T[i])


def refine_peak(T, y) -> float:
    """Sub-grid peak location via a 3-point parabola through the max and its neighbours.

    The discrete argmax is only accurate to the grid spacing ΔT; fitting a
    quadratic to the peak sample and its two neighbours recovers the vertex,
    which removes most of the grid-quantization error in the T_c estimate. Falls
    back to the discrete argmax T when the max sits on an endpoint (no bracket).
    NumPy only — same spirit as ``fss.fit_gamma_over_nu`` doing the fit honestly
    rather than trusting a reported number.
    """
    T = np.asarray(T, dtype=float)
    y = np.asarray(y, dtype=float)
    i = int(np.argmax(y))
    if i == 0 or i == len(y) - 1:
        return float(T[i])
    x0, x1, x2 = T[i - 1], T[i], T[i + 1]
    y0, y1, y2 = y[i - 1], y[i], y[i + 1]
    # Vertex of the parabola through the three points.
    denom = (y0 - 2.0 * y1 + y2)
    if denom == 0.0:
        return float(x1)
    # Offset of the vertex from the centre sample, in units of the (uniform) step.
    delta = 0.5 * (y0 - y2) / denom
    step = x1 - x0
    return float(x1 + delta * step)


def relative_error(measured: float, benchmark: float = TC_3D) -> float:
    """``|measured − benchmark| / benchmark`` — the headline calibration error."""
    return abs(measured - benchmark) / benchmark


def run_m06(
    L: int = 10,
    T_min: float = 4.1,
    T_max: float = 4.9,
    n_temps: int = 21,
    n_sweeps: int = 8000,
    n_burnin: int = 3000,
    seed: int = 42,
    progress=None,
) -> M06Result:
    """Run the 3D Ising sweep at one lattice size and locate T_c from the χ peak.

    Mirrors ``run_fss``/``run_m03``: a single batched sweep (here over a window
    straddling the 3D benchmark T_c ≈ 4.5115), wall-clock timing, a ``progress``
    callback, and a ``to_report``-ready result. The χ-peak gives the headline
    T_c(L); the specific-heat peak is reported as an independent cross-check.

    Defaults are CPU-modest (L=10, 8k sweeps) so the milestone finishes in a few
    minutes with no GPU — see the device-safety reasoning in ``ising3d``.
    """
    from .ising3d import Run3DConfig, run

    t0 = time.time()
    cfg = Run3DConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed,
    )
    r = run(cfg)

    _, tc_chi = susceptibility_peak(r.T, r.chi)
    tc_chi_refined = refine_peak(r.T, r.chi)
    _, tc_cv = specific_heat_peak(r.T, r.specific_heat)
    rel_err = relative_error(tc_chi_refined)

    result = M06Result(
        T=r.T.tolist(),
        chi=r.chi.tolist(),
        abs_mag=r.abs_mag.tolist(),
        abs_mag_err=r.abs_mag_err.tolist(),
        energy=r.energy.tolist(),
        specific_heat=r.specific_heat.tolist(),
        L=L,
        tc_chi=tc_chi,
        tc_chi_refined=tc_chi_refined,
        tc_cv=tc_cv,
        tc_benchmark=TC_3D,
        rel_error=rel_err,
        wall_seconds=time.time() - t0,
        config={
            "L": L, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed,
        },
    )
    if progress is not None:
        progress(result)
    return result


def to_report(result: M06Result) -> dict:
    """A JSON report shaped for the page + the M06 check.

    Distinct ``experiment`` tag (``M06-3d-ising``) so the M01 χ-peak check skips
    it (it carries top-level ``T``/``chi`` but a different ``experiment`` field,
    and ``check_m06`` claims it first), with the per-T arrays the page needs and
    the headline T_c numbers ``check_m06`` re-derives.
    """
    return {
        "experiment": "M06-3d-ising",
        "headline": (
            f"3D simple-cubic Ising (L={result.L}): χ peaks at "
            f"T_c={result.tc_chi_refined:.3f} vs MC benchmark "
            f"{result.tc_benchmark:.4f} (rel. err {result.rel_error*100:.1f}%) "
            f"· {result.wall_seconds:.0f}s on CPU"
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
        "tc_cv": result.tc_cv,
        "tc_benchmark": result.tc_benchmark,
        "rel_error": result.rel_error,
        "beta_3d": BETA_3D,
        "gamma_3d": GAMMA_3D,
        "nu_3d": NU_3D,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
