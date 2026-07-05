"""M02 — finite-size scaling of the 2D Ising susceptibility.

M01 located the critical point from a single lattice. M02 asks a sharper,
parameter-free question: how does the *peak* susceptibility grow as the lattice
grows? Finite-size scaling theory says that near criticality

    χ(T, L) = L^(γ/ν) · f( (T - T_c) · L^(1/ν) )

so the peak height obeys  χ_max(L) ∝ L^(γ/ν).  For the 2D Ising universality
class the exponents are *exact*: γ/ν = 7/4 and ν = 1. The slope of
log χ_max vs log L is therefore a number the simulation must reproduce with no
free parameters — and the rescaled curves χ·L^(-γ/ν) vs (T-T_c)·L^(1/ν) must
all collapse onto one master curve.

The pure analysis functions here (`chi_peak`, `fit_gamma_over_nu`,
`collapse_coords`) are NumPy-only and unit-tested without a GPU; `run_fss`
drives the GPU sweep across lattice sizes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .ising import RunConfig, run
from .onsager import T_C

GAMMA_OVER_NU = 7.0 / 4.0   # 2D Ising, exact (Onsager / Kaufman)
NU = 1.0                    # correlation-length exponent, exact

# Lattice sizes spanning an 8× linear range — enough leverage for a clean slope.
# Historically capped at 256 because single-spin Metropolis suffers critical
# slowing down (z ≈ 2.17) near T_c and can't equilibrate larger lattices in a
# tractable sweep budget. With the Wolff cluster updater (``updater='wolff'``,
# the default, z ≈ 0.25) this cap lifts: the nightly can extend the tuple to
# L = 512/1024 to tighten the measured γ/ν — see BACKLOG's cluster-algorithm
# section and the PR that wired Wolff into ``run_fss``.
DEFAULT_L = (32, 64, 128, 256)


@dataclass
class FSSCurve:
    L: int
    T: list           # temperatures swept
    chi: list         # susceptibility per spin at each T
    chi_max: float    # peak susceptibility
    T_peak: float     # (pseudo-critical) temperature at the peak
    wall_seconds: float


@dataclass
class FSSResult:
    curves: list          # list[FSSCurve], one per L
    slope: float          # measured γ/ν (log χ_max vs log L)
    intercept: float
    r2: float             # goodness of the log-log fit
    tc: float             # T_c used for the collapse (Onsager exact)
    gamma_over_nu_theory: float
    nu: float
    wall_seconds: float
    config: dict          # the shared sweep parameters


def chi_peak(T, chi) -> tuple[float, float]:
    """``(chi_max, T at the peak)`` from one χ(T) sweep."""
    T = np.asarray(T, dtype=float)
    chi = np.asarray(chi, dtype=float)
    i = int(np.argmax(chi))
    return float(chi[i]), float(T[i])


def fit_gamma_over_nu(L_values, chi_max_values) -> tuple[float, float, float]:
    """Least-squares slope of ``log χ_max`` vs ``log L`` → ``(slope, intercept, R²)``.

    The slope estimates γ/ν; for 2D Ising it should land near 7/4.
    """
    x = np.log(np.asarray(L_values, dtype=float))
    y = np.log(np.asarray(chi_max_values, dtype=float))
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(intercept), r2


def collapse_coords(L, T, chi, tc=T_C, gamma_over_nu=GAMMA_OVER_NU, nu=NU):
    """Finite-size-scaling collapse coordinates for one lattice size.

    ``x = (T - tc) · L^(1/ν)``  and  ``y = χ · L^(-γ/ν)``. Plotting ``y`` vs ``x``
    for every L should overlay the curves onto a single master curve.
    """
    T = np.asarray(T, dtype=float)
    chi = np.asarray(chi, dtype=float)
    x = (T - tc) * L ** (1.0 / nu)
    y = chi * L ** (-gamma_over_nu)
    return x, y


def run_fss(
    L_values=DEFAULT_L,
    T_min: float = 2.27,
    T_max: float = 2.40,
    n_temps: int = 24,
    n_sweeps: int = 80000,
    n_burnin: int = 30000,
    seed: int = 42,
    device: str = "cuda",
    updater: str = "wolff",
    progress=None,
) -> FSSResult:
    """Run the Ising sweep at each lattice size and fit the peak scaling.

    Uses the **|m|-based susceptibility** (``chi_abs``), the
    finite-size-scaling–appropriate observable: the signed χ is contaminated by
    magnetization sign-flips on large lattices near T_c and does NOT scale
    cleanly. The temperature window sits tight around T_c (default [2.27, 2.40])
    so the increasingly narrow peak is well-resolved and never dips into the
    sub-T_c region where the sign artifact lives. ``progress(L, curve)`` is
    called after each lattice if provided, so a CLI can report as it goes.

    M02 measures χ_max IN the critical region, where single-spin Metropolis
    suffers critical slowing down (z ≈ 2.17) and caps the reachable lattice at
    L ≈ 256. The default ``updater='wolff'`` samples with the cluster algorithm
    (z ≈ 0.25, ``wolff.py``) — the correct instrument for criticality — so the
    nightly can push ``L_values`` to 512/1024 and sharpen γ/ν. Pass
    ``updater='metropolis'`` to fall back to ``ising.run`` (an algorithm
    cross-check, or off-critical work). Both engines expose ``chi_abs`` and
    ``T`` with identical shapes, so the peak-fit path is updater-agnostic. NOTE
    the units difference: in the Wolff branch ``n_sweeps``/``n_burnin`` are
    counted in *cluster updates*, not Metropolis sweeps (far fewer needed).

    GPU-SAFETY CONTRACT: this production driver is for the actual milestone
    night — it is NOT invoked by the test suite (the tests exercise only the
    numpy analysis layer and a tiny CPU Wolff/Metropolis agreement smoke). Any
    manual smoke MUST be ``device='cpu'`` with small ``L``/``n_sweeps`` so it
    finishes in seconds; the L≥512 sweep is the nightly's job, never CI.
    """
    t0 = time.time()
    curves: list[FSSCurve] = []
    for L in L_values:
        if updater == "wolff":
            from .wolff import WolffConfig, wolff_run
            cfg = WolffConfig(
                L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
                n_updates=n_sweeps, n_burnin=n_burnin, seed=seed, device=device,
            )
            r = wolff_run(cfg)
        elif updater == "metropolis":
            cfg = RunConfig(
                L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
                n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed, device=device,
            )
            r = run(cfg)
        else:
            raise ValueError(f"unknown updater {updater!r} (use 'wolff' or 'metropolis')")

        cmax, tpk = chi_peak(r.T, r.chi_abs)   # |m|-susceptibility peak
        curve = FSSCurve(
            L=L, T=r.T.tolist(), chi=r.chi_abs.tolist(),
            chi_max=cmax, T_peak=tpk, wall_seconds=r.wall_seconds,
        )
        curves.append(curve)
        if progress is not None:
            progress(L, curve)

    slope, intercept, r2 = fit_gamma_over_nu(
        [c.L for c in curves], [c.chi_max for c in curves]
    )
    return FSSResult(
        curves=curves, slope=slope, intercept=intercept, r2=r2,
        tc=float(T_C), gamma_over_nu_theory=GAMMA_OVER_NU, nu=NU,
        wall_seconds=time.time() - t0,
        config={
            "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed,
            "updater": updater,
        },
    )


def to_report(fss: FSSResult) -> dict:
    """A JSON report shaped for the page + the M02 check.

    Distinct ``experiment`` tag and per-L ``curves`` so the M01 check skips it
    and the M02 check can re-derive the slope independently.
    """
    return {
        "experiment": "M02-finite-size-scaling",
        "headline": (
            f"finite-size scaling: χ_max ∝ L^{fss.slope:.3f} "
            f"(2D Ising γ/ν = 7/4 = {GAMMA_OVER_NU:.2f}) · {fss.wall_seconds:.0f}s on GPU"
        ),
        "L_values": [c.L for c in fss.curves],
        "curves": [
            {
                "L": c.L, "T": c.T, "chi": c.chi,
                "chi_max": c.chi_max, "T_peak": c.T_peak,
                "wall_seconds": c.wall_seconds,
            }
            for c in fss.curves
        ],
        "gamma_over_nu_fit": fss.slope,
        "gamma_over_nu_theory": fss.gamma_over_nu_theory,
        "fit_r2": fss.r2,
        "nu": fss.nu,
        "tc": fss.tc,
        "wall_seconds": fss.wall_seconds,
        "config": fss.config,
    }
