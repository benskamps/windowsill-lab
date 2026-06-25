"""M08 — 2D XY model: the Berezinskii–Kosterlitz–Thouless transition.

M01–M07 located ordinary critical points by a peak (χ, C). M08 is different in
kind: the 2D XY model has **no long-range order at any T > 0** and so **no
order-parameter peak to find** — its transition is the *topological* BKT
vortex-unbinding at

    T_BKT ≈ 0.8929          (square-lattice MC/RG benchmark; no closed form)

The falsifiable signature is the **helicity modulus** Υ(T) and its **universal
jump**: in the L→∞ limit Υ drops discontinuously from (2/π)·T_BKT to 0 at T_BKT
(Nelson–Kosterlitz). On a finite lattice the jump is rounded, but the operational
estimate is clean and parameter-free: plot Υ(T) against the straight line
y = (2/π)·T and read **their crossing** as T_BKT(L). That crossing is the headline
number ``check_m08`` re-derives.

``run_m08`` drives the continuous-angle engine ``xy.run`` over a window straddling
0.8929, then finds the crossing of the measured Υ(T) with (2/π)·T by linear
interpolation between the two bracketing temperatures (a 1-D root of
g(T) = Υ(T) − (2/π)·T). Because BKT log-corrections are notoriously strong, a
single-L crossing is honestly a coarse estimate that typically sits a little
**above** 0.8929 — the same finite-size honesty M05/M06 carry — so the check uses
a BKT-appropriate, log-correction-tolerant window (±0.07), wider than a
sharp-peak check.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

# Square-lattice 2D XY BKT transition temperature — the high-precision MC/RG
# benchmark (0.89290(5)); MILESTONES.md's ≈ 0.893 is correct. No closed form.
T_BKT = 0.8929
# The universal-jump slope: at the crossing Υ/T = 2/π, i.e. Υ = (2/π)·T.
TWO_OVER_PI = 2.0 / math.pi


def helicity_crossing(T, helicity) -> float | None:
    """Locate the crossing of Υ(T) with the line (2/π)·T — the BKT estimate of T_BKT.

    Solves g(T) = Υ(T) − (2/π)·T = 0 by walking the sweep and linearly
    interpolating across the first sign change of ``g`` (from g > 0 below the
    transition, where Υ exceeds the jump line, to g < 0 above it). Returns the
    interpolated crossing temperature, or ``None`` if ``g`` never changes sign on
    the swept window (the crossing isn't bracketed — the window is mis-placed or
    the run is broken). NumPy-only so the check can re-derive it without torch.

    The Υ(T) curve must be reasonably smooth for this to be meaningful — a jagged
    curve (under-equilibrated, or a bad helicity estimator) can cross the line
    several times. We take the FIRST high→low crossing, the physical one: Υ starts
    above the line at low T and drops through it once near T_BKT.
    """
    T = np.asarray(T, dtype=float)
    Y = np.asarray(helicity, dtype=float)
    g = Y - TWO_OVER_PI * T
    for i in range(len(T) - 1):
        # First downward crossing: g goes from ≥0 to <0 between i and i+1.
        if g[i] >= 0.0 and g[i + 1] < 0.0:
            # Linear interpolation of the root of g between T[i] and T[i+1].
            frac = g[i] / (g[i] - g[i + 1])
            return float(T[i] + frac * (T[i + 1] - T[i]))
    return None


@dataclass
class M08Result:
    T: list
    helicity_modulus: list
    helicity_err: list
    energy: list
    abs_mag: list
    acceptance: list
    L: int
    tc_crossing: float | None    # the Υ(T)=(2/π)T crossing — the headline T_BKT(L)
    tc_benchmark: float          # T_BKT (0.8929)
    rel_error: float | None      # |tc_crossing − T_BKT| / T_BKT
    updater: str
    wall_seconds: float
    config: dict


def run_m08(
    L: int = 64,
    T_min: float = 0.6,
    T_max: float = 1.1,
    n_temps: int = 26,
    n_sweeps: int = 40000,
    n_burnin: int = 8000,
    over_relax: int = 1,
    seed: int = 42,
    device: str = "cuda",
    updater: str = "metropolis",
    progress=None,
) -> M08Result:
    """Run the 2D XY sweep over a window straddling T_BKT and locate the Υ-jump crossing.

    Mirrors ``run_m05``/``run_m07``: a single batched sweep over [T_min, T_max]
    straddling the BKT benchmark 0.8929, wall-clock timing, a ``progress``
    callback, and a ``to_report``-ready result. The crossing of the measured
    Υ(T) with the universal-jump line (2/π)·T is the headline finite-L estimate of
    T_BKT; ``check_m08`` re-derives it from the report's (T, helicity) arrays. The
    default Metropolis-plus-over-relaxation updater gives a smooth Υ(T) (the
    over-relaxation cures the XY critical slowing that would otherwise jag the
    curve and fool the crossing finder).
    """
    from .xy import XYRunConfig, run

    t0 = time.time()
    cfg = XYRunConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_sweeps=n_sweeps, n_burnin=n_burnin, over_relax=over_relax,
        seed=seed, device=device, updater=updater,
    )
    r = run(cfg)

    tc_crossing = helicity_crossing(r.T, r.helicity_modulus)
    rel_err = (abs(tc_crossing - T_BKT) / T_BKT) if tc_crossing is not None else None

    result = M08Result(
        T=r.T.tolist(),
        helicity_modulus=r.helicity_modulus.tolist(),
        helicity_err=r.helicity_err.tolist(),
        energy=r.energy.tolist(),
        abs_mag=r.abs_mag.tolist(),
        acceptance=r.acceptance.tolist(),
        L=L,
        tc_crossing=tc_crossing,
        tc_benchmark=T_BKT,
        rel_error=rel_err,
        updater=updater,
        wall_seconds=time.time() - t0,
        config={
            "L": L, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "over_relax": over_relax,
            "seed": seed, "updater": updater, "model": "xy",
        },
    )
    if progress is not None:
        progress(result)
    return result


def to_report(result: M08Result) -> dict:
    """A JSON report shaped for the page + the M08 check.

    Distinct ``experiment`` tag (``M08-xy-bkt``) so the single-peak χ/C checks all
    skip it (M08 carries NO χ-peak — its observable is the helicity-jump crossing)
    and ``check_m08`` claims it, with the per-T (T, helicity) arrays the page needs
    and the headline crossing ``check_m08`` re-derives.
    """
    tc_str = f"{result.tc_crossing:.4f}" if result.tc_crossing is not None else "—"
    err_str = f"{result.rel_error*100:.1f}%" if result.rel_error is not None else "—"
    headline = (
        f"2D XY BKT (L={result.L}): helicity Υ(T) crosses the (2/π)T jump line at "
        f"T_BKT={tc_str} vs benchmark {result.tc_benchmark:.4f} (rel. err {err_str}) "
        f"· {result.wall_seconds:.0f}s on GPU"
    )
    return {
        "experiment": "M08-xy-bkt",
        "headline": headline,
        "L": result.L,
        "T": result.T,
        "helicity_modulus": result.helicity_modulus,
        "helicity_err": result.helicity_err,
        "energy": result.energy,
        "abs_mag": result.abs_mag,
        "acceptance": result.acceptance,
        "tc_crossing": result.tc_crossing,
        "tc_benchmark": result.tc_benchmark,
        "rel_error": result.rel_error,
        "two_over_pi": TWO_OVER_PI,
        "updater": result.updater,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
