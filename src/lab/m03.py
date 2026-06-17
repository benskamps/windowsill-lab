"""M03 — critical-exponent β via magnetization data-collapse.

M01 found the critical point; M02 measured how the susceptibility *peak* grows
with lattice size (γ/ν = 7/4). M03 turns the finite-size-scaling idea into its
most demanding visual: the **data collapse** of the order parameter itself.

Near criticality the per-spin magnetization obeys the scaling form

    M(T, L) = L^(-β/ν) · F( (T - T_c) · L^(1/ν) )

equivalently  M · L^(β/ν) = F( (T - T_c) · L^(1/ν) ).  So if you plot

    y = M · L^(β/ν)   against   x = (T - T_c) · L^(1/ν)

for *every* lattice size, all the curves must fall on top of one another — onto
a single master curve F. For the 2D square-lattice Ising universality class the
exponents are *exact*: β = 1/8 and ν = 1, so β/ν = 1/8 is a number the
simulation must reproduce with no free parameters. That same 1/8 is literally
the exponent in Onsager's spontaneous magnetization
``M(T) = (1 - sinh(2J/T)^-4)^(1/8)`` below T_c (see ``onsager.py``) — M03 ties
directly back to that exact result.

Note the SIGN, relative to M02's χ collapse: M *shrinks* with L at criticality,
so the y-rescale exponent is **+β/ν** (χ *grows*, so its exponent was −γ/ν).

The pure analysis functions here (``collapse_coords``, ``master_curve``,
``collapse_quality``, ``fit_beta_over_nu``, ``fit_collapse``) are NumPy-only and
unit-tested without a GPU. ``run_m03`` drives the sweep, sampling with the Wolff
cluster updater (``wolff.py``) because M03 lives IN the critical region where
single-spin Metropolis suffers critical slowing down.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .onsager import T_C            # single source of truth for the critical T
from .fss import NU                 # exact correlation-length exponent (= 1.0)

# 2D Ising critical exponents, all EXACT for the square-lattice universality
# class (Onsager 1944 / Yang 1952).
BETA = 1.0 / 8.0                    # magnetization exponent: M ∝ (T_c - T)^β below T_c
BETA_OVER_NU = BETA / NU            # = 1/8 — the magnetization scaling dimension (y-rescale)
INV_NU = 1.0 / NU                   # = 1.0 — the reduced-temperature exponent (x-rescale)

# Moderate sizes for the production run: wide enough leverage for a clean
# collapse while staying inside what Wolff equilibrates near T_c in reasonable
# time. NOT to be invoked during spec/test work (see the GPU-safety note on
# run_m03).
DEFAULT_L = (16, 24, 32, 48)


@dataclass
class M03Curve:
    L: int
    T: list          # temperatures swept
    M: list          # per-spin ⟨|m|⟩ at each T (the order parameter)
    M_err: list      # standard error of ⟨|m|⟩ at each T
    wall_seconds: float


@dataclass
class M03Result:
    curves: list                # list[M03Curve], one per L
    beta_over_nu_fit: float     # headline number: β/ν recovered from the collapse
    inv_nu_fit: float | None    # 1/ν from the joint no-assumptions fit (or None)
    collapse_quality: float     # residual loss at the exact exponents (smaller = better)
    tc: float                   # T_c used for the collapse (Onsager exact)
    beta_over_nu_theory: float
    nu: float
    wall_seconds: float
    config: dict                # the shared sweep parameters


def collapse_coords(L, T, M, tc=T_C, beta_over_nu=BETA_OVER_NU, inv_nu=INV_NU):
    """Data-collapse coordinates for one lattice size.

    ``x = (T - tc) · L^(1/ν)``  and  ``y = M · L^(β/ν)``. Plotting ``y`` vs ``x``
    for every L should overlay the magnetization curves onto a single master
    curve F. Mirror of ``fss.collapse_coords`` but for the order parameter — note
    the y-rescale exponent is **+β/ν** (M shrinks with L), not −γ/ν.
    """
    T = np.asarray(T, dtype=float)
    M = np.asarray(M, dtype=float)
    x = (T - tc) * L ** inv_nu
    y = M * L ** beta_over_nu
    return x, y


def _overlap_window(xs_list) -> tuple[float, float]:
    """``[lo, hi]`` = the x-region every curve covers (the scorable overlap)."""
    lo = max(float(x.min()) for x in xs_list)
    hi = min(float(x.max()) for x in xs_list)
    return lo, hi


def _interp_grid(curves, tc, beta_over_nu, inv_nu, n_bins):
    """Rescale + interpolate every curve onto a shared x-grid over the overlap.

    Returns ``(centers, Y)`` where ``centers`` is ``(n_bins,)`` and ``Y`` is
    ``(n_curves, n_bins)`` — one interpolated y per curve per bin. Returns
    ``(None, None)`` if fewer than two curves overlap. Each curve contributes
    exactly one sample per bin, so the per-bin variance across rows of ``Y`` is
    *literally* how far from collapsed the curves are at that reduced temperature.
    """
    if len(curves) < 2:
        return None, None
    rescaled = [collapse_coords(L, T, M, tc, beta_over_nu, inv_nu) for (L, T, M) in curves]
    lo, hi = _overlap_window([x for x, _ in rescaled])
    if not (hi > lo):
        return None, None
    centers = np.linspace(lo, hi, n_bins)
    rows = []
    for x, y in rescaled:
        order = np.argsort(x)
        rows.append(np.interp(centers, x[order], y[order]))
    return centers, np.asarray(rows)


def master_curve(curves, tc=T_C, beta_over_nu=BETA_OVER_NU, inv_nu=INV_NU, n_bins=24):
    """Pooled master curve from a list of ``(L, T, M)`` tuples.

    Rescales each curve via ``collapse_coords``, restricts to the x-overlap
    window, bins x into ``n_bins`` uniform centers, and returns
    ``(centers, mean_y_per_bin, std_y_per_bin)``. The per-bin std *across curves*
    is the raw collapse residual — the band the page can draw around F. Returns
    three empty arrays if the curves don't overlap.
    """
    centers, Y = _interp_grid(curves, tc, beta_over_nu, inv_nu, n_bins)
    if centers is None:
        empty = np.array([])
        return empty, empty, empty
    return centers, Y.mean(axis=0), Y.std(axis=0)


def collapse_quality(curves, tc=T_C, beta_over_nu=BETA_OVER_NU, inv_nu=INV_NU, n_bins=24) -> float:
    """Scalar collapse loss — SMALLER is BETTER, 0 = perfect collapse.

    Rescale every curve, interpolate each onto a common grid spanning the
    x-overlap window, take the variance of the interpolated y values ACROSS
    curves per bin, and return the mean bin variance normalized by the overall
    pooled y-variance (dimensionless, ~O(1) for a bad collapse, run-to-run
    comparable). Returns ``np.inf`` if fewer than two curves overlap.

    Interpolation (not raw binning of pooled points) is the key choice: one y per
    curve per bin means the cross-curve variance *is* the overlap residual. When
    the data obey the scaling form every curve is the same F, so all interpolated
    values per bin are identical and the loss is 0.
    """
    centers, Y = _interp_grid(curves, tc, beta_over_nu, inv_nu, n_bins)
    if centers is None:
        return np.inf
    per_bin_var = Y.var(axis=0)            # variance across curves, per bin
    pooled_var = float(Y.var())            # overall y spread → dimensionless loss
    if pooled_var <= 0.0:
        return 0.0
    return float(per_bin_var.mean() / pooled_var)


def _golden_min(f, a, b, tol=1e-7, max_iter=200):
    """Golden-section minimization of a 1-D function on ``[a, b]`` (numpy only)."""
    gr = (np.sqrt(5.0) - 1.0) / 2.0       # 0.618...
    c = b - gr * (b - a)
    d = a + gr * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(max_iter):
        if abs(b - a) < tol:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = f(d)
    xm = 0.5 * (a + b)
    return xm, f(xm)


def fit_beta_over_nu(curves, tc=T_C, inv_nu=INV_NU, bracket=(0.0, 0.5), n_bins=24) -> tuple[float, float]:
    """Recover β/ν by minimizing ``collapse_quality`` over β/ν alone.

    ``inv_nu`` and ``tc`` are held at their exact values — the cleanest
    one-parameter fit, and M03's headline number. Uses a dependency-free
    golden-section minimizer over ``bracket`` (matching the house "numpy for pure
    analysis" rule — ``fss.py`` uses only ``np.polyfit``). Returns
    ``(beta_over_nu_fit, loss_at_min)``; on exact synthetic data it lands on
    0.125 to within the minimizer tolerance with loss ~0.
    """
    loss = lambda bon: collapse_quality(curves, tc=tc, beta_over_nu=bon, inv_nu=inv_nu, n_bins=n_bins)
    bon, val = _golden_min(loss, bracket[0], bracket[1])
    return float(bon), float(val)


def fit_collapse(curves, tc=T_C, bon_bracket=(0.0, 0.5), invnu_bracket=(0.5, 2.0), n_bins=24) -> tuple[float, float, float]:
    """Joint no-assumptions fit: minimize ``collapse_quality`` over (β/ν, 1/ν).

    The stronger no-free-lunch check — recovers BOTH exponents when neither is
    assumed, proving the collapse isn't an artifact of fixing 1/ν. Nested
    golden-section (outer over 1/ν, inner over β/ν) iterated to convergence,
    numpy only. Returns ``(beta_over_nu_fit, inv_nu_fit, loss)``.
    """
    def inner(invnu):
        loss = lambda bon: collapse_quality(curves, tc=tc, beta_over_nu=bon, inv_nu=invnu, n_bins=n_bins)
        return _golden_min(loss, bon_bracket[0], bon_bracket[1])

    def outer(invnu):
        _, val = inner(invnu)
        return val

    invnu, _ = _golden_min(outer, invnu_bracket[0], invnu_bracket[1])
    bon, val = inner(invnu)
    return float(bon), float(invnu), float(val)


def to_report(result: M03Result) -> dict:
    """A JSON report shaped for the page + the M03 check, mirroring ``fss.to_report``.

    Distinct ``experiment`` tag and per-L ``curves`` (each ``{L, T, M}``), plus
    the master-curve arrays so the page can draw the collapsed band. NO top-level
    ``T``/``chi`` keys, so ``check_m01`` treats it as not-applicable.
    """
    raw = [(c.L, np.asarray(c.T, float), np.asarray(c.M, float)) for c in result.curves]
    centers, mean_y, std_y = master_curve(
        raw, tc=result.tc, beta_over_nu=result.beta_over_nu_theory
    )
    return {
        "experiment": "M03-data-collapse",
        "headline": (
            f"data collapse: M·L^(β/ν) onto one master curve at β/ν={result.beta_over_nu_fit:.3f} "
            f"(2D Ising β=1/8 → β/ν={BETA_OVER_NU:.3f}, loss={result.collapse_quality:.1e}) "
            f"· {result.wall_seconds:.0f}s"
        ),
        "L_values": [c.L for c in result.curves],
        "curves": [
            {"L": c.L, "T": c.T, "M": c.M, "M_err": c.M_err, "wall_seconds": c.wall_seconds}
            for c in result.curves
        ],
        "beta_over_nu_fit": result.beta_over_nu_fit,
        "beta_over_nu_theory": result.beta_over_nu_theory,
        "inv_nu_fit": result.inv_nu_fit,
        "inv_nu": INV_NU,
        "nu": result.nu,
        "tc": result.tc,
        "collapse_quality": result.collapse_quality,
        "master_curve": {
            "centers": centers.tolist(),
            "mean_y": mean_y.tolist(),
            "std_y": std_y.tolist(),
        },
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }


def run_m03(
    L_values=DEFAULT_L,
    T_min: float = 2.24,
    T_max: float = 2.30,
    n_temps: int = 24,
    n_sweeps: int = 20000,
    n_burnin: int = 4000,
    seed: int = 42,
    device: str = "cuda",
    updater: str = "wolff",
    progress=None,
) -> M03Result:
    """Sweep each lattice size across a tight window straddling T_c and fit the collapse.

    Mirrors ``run_fss``: per-L sweep loop, ``progress(L, curve)`` callback,
    wall-clock timing, ``to_report`` at the end. Uses ``RunResult.abs_mag``
    (⟨|m|⟩) as the order parameter M — the |m| convention matches the sign-flip
    reasoning ``fss.py`` documents for ``chi_abs``.

    M03 measures M(T) IN the critical region, where single-spin Metropolis
    suffers critical slowing down (z ≈ 2.17). The default ``updater='wolff'``
    samples with the cluster algorithm (z ≈ 0.25, ``wolff.py``); pass
    ``updater='metropolis'`` to fall back to ``ising.run`` for off-critical work.

    GPU-SAFETY CONTRACT: a long CUDA sweep crashed this machine's GPU. This
    production driver is for the actual milestone night — it is NOT invoked by the
    test suite (the tests exercise only the numpy analysis layer on synthetic
    data). Any manual smoke MUST be ``device='cpu'``, ``L<=24``, ``n_sweeps<=300``,
    small ``n_temps`` — finishing in seconds — and is never the default, never CI.
    """
    t0 = time.time()
    curves: list[M03Curve] = []
    for L in L_values:
        if updater == "wolff":
            from .wolff import WolffConfig, wolff_run
            cfg = WolffConfig(
                L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
                n_updates=n_sweeps, n_burnin=n_burnin, seed=seed, device=device,
            )
            r = wolff_run(cfg)
            T, M, M_err, wall = r.T, r.abs_mag, r.abs_mag_err, r.wall_seconds
        elif updater == "metropolis":
            from .ising import RunConfig, run
            cfg = RunConfig(
                L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
                n_sweeps=n_sweeps, n_burnin=n_burnin, seed=seed, device=device,
            )
            r = run(cfg)
            T, M, M_err, wall = r.T, r.abs_mag, r.abs_mag_err, r.wall_seconds
        else:
            raise ValueError(f"unknown updater {updater!r} (use 'wolff' or 'metropolis')")

        curve = M03Curve(
            L=L, T=T.tolist(), M=M.tolist(), M_err=M_err.tolist(), wall_seconds=wall,
        )
        curves.append(curve)
        if progress is not None:
            progress(L, curve)

    raw = [(c.L, np.asarray(c.T, float), np.asarray(c.M, float)) for c in curves]
    beta_over_nu_fit, _ = fit_beta_over_nu(raw)
    bon_joint, invnu_joint, _ = fit_collapse(raw)
    quality = collapse_quality(raw)   # at the EXACT exponents — the headline residual

    return M03Result(
        curves=curves,
        beta_over_nu_fit=beta_over_nu_fit,
        inv_nu_fit=invnu_joint,
        collapse_quality=quality,
        tc=float(T_C),
        beta_over_nu_theory=BETA_OVER_NU,
        nu=NU,
        wall_seconds=time.time() - t0,
        config={
            "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed,
            "updater": updater,
        },
    )
