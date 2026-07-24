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
    updater: str = "metropolis",
    device: str = "cpu",
    progress=None,
) -> M06Result:
    """Run the 3D Ising sweep at one lattice size and locate T_c from the χ peak.

    Mirrors ``run_fss``/``run_m03``: a single batched sweep (here over a window
    straddling the 3D benchmark T_c ≈ 4.5115), wall-clock timing, a ``progress``
    callback, and a ``to_report``-ready result. The χ-peak gives the headline
    T_c(L); the specific-heat peak is reported as an independent cross-check.

    ``updater`` picks the sampler, mirroring ``run_fss(updater=...)`` (M02):

    - ``'metropolis'`` (default) drives the verified ``ising3d.run`` checkerboard
      engine — the algorithm that landed M06's benchmark and the golden reports,
      kept as the default so single-L calibration reproduces exactly.
    - ``'wolff'`` drives the ``wolff3d.wolff_run`` single-cluster engine (z ≈ 0.3
      vs Metropolis' z ≈ 2 near criticality). This is the correct instrument for
      the L-extrapolation: it beats the critical slowing down that caps the
      Metropolis engine, so larger L become tractable. NOTE the units difference —
      in the Wolff branch ``n_sweeps``/``n_burnin`` are counted in *cluster
      updates*, not Metropolis sweeps (far fewer needed for the same decorrelation).

    Both engines expose the same observables with identical shapes, so the
    peak-fit path below is updater-agnostic. The one subtlety the branch handles:
    ``ising3d.run.chi`` is already the |m|-based (FSS-appropriate) susceptibility,
    whereas ``wolff3d`` exposes that as ``chi_abs`` (its ``chi`` is the signed one).
    We select the |m|-based observable from each so the χ peak means the same thing.

    ``device`` is passed to the Wolff (torch) engine; the Metropolis engine is
    NumPy-CPU and ignores it. Defaults are CPU-modest (L=10, 8k sweeps) so the
    milestone finishes in a few minutes with no GPU — see the device-safety
    reasoning in ``ising3d``.
    """
    t0 = time.time()
    if updater == "metropolis":
        from .ising3d import Run3DConfig, run
        cfg = Run3DConfig(
            L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
            n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed,
        )
        r = run(cfg)
        chi_obs = r.chi                      # ising3d.chi IS the |m|-based susceptibility
    elif updater == "wolff":
        from .wolff3d import Wolff3DConfig, wolff_run
        cfg = Wolff3DConfig(
            L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
            n_updates=n_sweeps, n_burnin=n_burnin, seed=seed, device=device,
        )
        r = wolff_run(cfg)
        chi_obs = r.chi_abs                  # the |m|-based observable in the Wolff result
    else:
        raise ValueError(f"unknown updater {updater!r} (use 'metropolis' or 'wolff')")

    _, tc_chi = susceptibility_peak(r.T, chi_obs)
    tc_chi_refined = refine_peak(r.T, chi_obs)
    _, tc_cv = specific_heat_peak(r.T, r.specific_heat)
    rel_err = relative_error(tc_chi_refined)

    result = M06Result(
        T=r.T.tolist(),
        chi=chi_obs.tolist(),
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
            "updater": updater, "device": device,
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


# --------------------------------------------------------------------------- #
# L-extrapolation — sharpen the finite-L pseudo-critical T_c toward T_c(∞).
#
# A single small lattice lands the χ-peak at a pseudo-critical T_c(L) shifted
# *above* the infinite-volume value by an O(L^(−1/ν)) finite-size correction
# (render_m06's own verdict flags this and points here / to the BACKLOG). Running
# several L and extrapolating T_c(L) → T_c(∞) turns a calibration pass into a
# precision number — the next instrument the lab already asked for.
# --------------------------------------------------------------------------- #


def extrapolate_tc(Ls, tc_of_L, nu: float = NU_3D) -> dict:
    """Extrapolate finite-size pseudo-critical ``T_c(L)`` to the thermodynamic limit.

    The peak of χ on a finite L³ lattice sits at

        T_c(L) = T_c(∞) + a · L^(−1/ν)

    so regressing ``T_c(L)`` on ``x = L^(−1/ν)`` and reading the intercept
    (``x → 0``, i.e. ``L → ∞``) recovers ``T_c(∞)``. NumPy-only, runs no Monte-Carlo
    sweep — same spirit as ``susceptibility_peak`` / ``refine_peak`` / ``fss``: the
    fit is unit-tested against synthetic data with a *known* intercept rather than
    trusting a reported number.

    Returns a dict: ``tc_inf`` (intercept), ``slope`` (``a``), ``tc_inf_stderr``
    (OLS standard error of the intercept; ``None`` with <3 points), ``r_squared``
    (``None`` with <3 points), ``nu``, ``n_points``, and the ``Ls`` / ``x`` /
    ``tc_of_L`` arrays sorted by ascending ``x`` (large-L first).
    """
    Ls = np.asarray(Ls, dtype=float)
    tc = np.asarray(tc_of_L, dtype=float)
    if Ls.shape != tc.shape:
        raise ValueError("Ls and tc_of_L must have the same length")
    if Ls.size < 2:
        raise ValueError("need at least two lattice sizes to extrapolate")
    if np.any(Ls <= 0.0):
        raise ValueError("lattice sizes must be positive")

    x = Ls ** (-1.0 / nu)
    order = np.argsort(x)            # ascending x ⇒ descending L (large lattice first)
    x_s, tc_s, Ls_s = x[order], tc[order], Ls[order]

    # Ordinary least squares: tc = intercept + slope · x.
    design = np.vstack([np.ones_like(x_s), x_s]).T
    coef, *_ = np.linalg.lstsq(design, tc_s, rcond=None)
    intercept, slope = float(coef[0]), float(coef[1])

    n = int(x_s.size)
    r_squared: float | None = None
    intercept_stderr: float | None = None
    if n >= 3:
        pred = intercept + slope * x_s
        ss_res = float(np.sum((tc_s - pred) ** 2))
        ss_tot = float(np.sum((tc_s - tc_s.mean()) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 1.0
        dof = n - 2
        if dof > 0:
            sigma2 = ss_res / dof
            xtx_inv = np.linalg.inv(design.T @ design)
            intercept_stderr = float(np.sqrt(sigma2 * xtx_inv[0, 0]))

    return {
        "tc_inf": intercept,
        "slope": slope,
        "tc_inf_stderr": intercept_stderr,
        "r_squared": r_squared,
        "nu": float(nu),
        "n_points": n,
        "Ls": Ls_s.tolist(),
        "x": x_s.tolist(),
        "tc_of_L": tc_s.tolist(),
    }


@dataclass
class M06ExtrapResult:
    Ls: list                 # lattice sizes swept
    tc_of_L: list            # χ-peak T_c(L) (parabola-refined) at each L
    tc_inf: float            # extrapolated T_c(∞) (the intercept)
    tc_inf_stderr: float     # OLS standard error of the intercept (None if <3 L)
    r_squared: float         # fit quality (None if <3 L)
    slope: float             # the finite-size amplitude a
    nu: float                # exponent used for the L^(−1/ν) axis
    tc_benchmark: float      # 4.5115
    rel_error: float         # |tc_inf − benchmark| / benchmark
    per_L: list              # trimmed per-L records (L, tc_chi_refined, tc_cv, wall)
    wall_seconds: float
    config: dict


def run_m06_l_extrapolation(
    Ls=(8, 10, 12, 16),
    T_min: float = 4.3,
    T_max: float = 4.75,
    n_temps: int = 17,
    n_sweeps: int = 6000,
    n_burnin: int = 2000,
    seed: int = 42,
    nu: float = NU_3D,
    updater: str = "metropolis",
    device: str = "cpu",
    progress=None,
) -> M06ExtrapResult:
    """Run M06 at several lattice sizes and extrapolate ``T_c(L) → T_c(∞)``.

    Each L gets an independent χ-peak ``T_c(L)`` from ``run_m06`` (same engine and
    parabola refinement as the single-L milestone), with the seed varied per L so
    the runs are statistically independent. The temperature window is tightened
    around the benchmark (the pseudo-critical peaks for these small L sit just
    above 4.5115) so a modest CPU sweep budget concentrates on resolving the peak.
    ``extrapolate_tc`` then reads the intercept.

    ``updater`` is forwarded to ``run_m06`` for every lattice: ``'metropolis'``
    (default) keeps the verified checkerboard engine, ``'wolff'`` swaps in the 3D
    single-cluster updater (``wolff3d``) whose z ≈ 0.3 beats the critical slowing
    that otherwise caps the reachable L — the whole reason BACKLOG points this
    extrapolation at the Wolff instrument. ``device`` is forwarded too (used only
    by the Wolff/torch branch).

    CPU-modest by default ({8,10,12,16}³, 6k sweeps) — finishes in a few minutes
    with no GPU, mirroring ``run_m06``'s device-safety reasoning.
    """
    t0 = time.time()
    Ls = tuple(int(L) for L in Ls)
    per_L: list = []
    tc_of_L: list = []
    for i, L in enumerate(Ls):
        r = run_m06(
            L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
            n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed + i,
            updater=updater, device=device,
        )
        per_L.append(r)
        tc_of_L.append(r.tc_chi_refined)
        if progress is not None:
            progress(L, r)

    fit = extrapolate_tc(Ls, tc_of_L, nu=nu)
    return M06ExtrapResult(
        Ls=list(Ls),
        tc_of_L=list(tc_of_L),
        tc_inf=fit["tc_inf"],
        tc_inf_stderr=fit["tc_inf_stderr"],
        r_squared=fit["r_squared"],
        slope=fit["slope"],
        nu=fit["nu"],
        tc_benchmark=TC_3D,
        rel_error=relative_error(fit["tc_inf"]),
        per_L=[
            {
                "L": r.L,
                "tc_chi_refined": r.tc_chi_refined,
                "tc_chi": r.tc_chi,
                "tc_cv": r.tc_cv,
                "wall_seconds": r.wall_seconds,
            }
            for r in per_L
        ],
        wall_seconds=time.time() - t0,
        config={
            "Ls": list(Ls), "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed, "nu": nu,
            "updater": updater, "device": device,
        },
    )


def extrapolation_to_report(result: M06ExtrapResult) -> dict:
    """A JSON report for the L-extrapolation, tagged ``M06-extrapolation``.

    Distinct ``experiment`` tag so the single-L χ-peak checks skip it. Carries the
    per-L ladder plus the extrapolated headline so a future render/feed wiring (a
    Ben-direction call on how to present it publicly) has everything it needs.
    """
    stderr = result.tc_inf_stderr
    stderr_str = f"±{stderr:.3f}" if stderr is not None else ""
    return {
        "experiment": "M06-extrapolation",
        "headline": (
            f"3D Ising T_c via L-extrapolation over L∈{result.Ls}: "
            f"T_c(∞) = {result.tc_inf:.4f}{stderr_str} vs MC benchmark "
            f"{result.tc_benchmark:.4f} (rel. err {result.rel_error*100:.2f}%) "
            f"· {result.wall_seconds:.0f}s on CPU"
        ),
        "Ls": result.Ls,
        "tc_of_L": result.tc_of_L,
        "tc_inf": result.tc_inf,
        "tc_inf_stderr": result.tc_inf_stderr,
        "r_squared": result.r_squared,
        "slope": result.slope,
        "nu": result.nu,
        "tc_benchmark": result.tc_benchmark,
        "rel_error": result.rel_error,
        "per_L": result.per_L,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
