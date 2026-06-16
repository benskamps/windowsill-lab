"""Make ``verified`` mean something a machine confirmed.

A green leaf on the windowsill should be a *receipt*, not an honor-system
checkbox. This module re-derives a milestone's headline number from a run report
and asserts it against the known answer. ``lab verify`` runs the registered
checks; CI runs ``lab verify`` so a milestone can't be marked ``[x]`` unless its
number actually reproduces.

Each check is *applicable* only to reports it understands (it returns ``None``
for ones it can't read), so a milestone is graded against the newest report it
can actually evaluate — not whatever ran most recently. Stdlib only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .publish import LAB_HOME, MILESTONES_MD, REPORTS_DIR, parse_milestones

# Onsager's exact 2D Ising critical temperature, 1944.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.2692
# Exact 2D Ising susceptibility exponent ratio (M02 finite-size scaling).
GAMMA_OVER_NU = 7.0 / 4.0   # = 1.75
# Exact 2D Ising magnetization scaling dimension (M03 data collapse): β=1/8, ν=1.
BETA_OVER_NU = 1.0 / 8.0    # = 0.125
INV_NU = 1.0                # 1/ν


def _reports_newest_first() -> list[Path]:
    paths: list[Path] = []
    for d in (REPORTS_DIR, LAB_HOME):
        if d.exists():
            paths += d.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")
    return sorted(paths, key=lambda p: p.stem, reverse=True)


def check_m01(report: dict) -> tuple[bool | None, str]:
    """2D Ising: the susceptibility χ peaks at the (finite-size) critical point.

    Returns ``None`` if this report isn't an Ising χ-sweep (not applicable).
    Otherwise recovers T at max(χ) and asserts it sits near Onsager's exact T_c
    — a generous tolerance, since this catches a broken simulation, not a
    high-precision exponent claim.
    """
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi):
        return None, "not an Ising χ-sweep"
    peak_T = T[max(range(len(chi)), key=lambda i: chi[i])]
    tol = 0.2
    ok = abs(peak_T - ONSAGER_TC) <= tol
    return ok, f"χ peak at T={peak_T:.3f} vs Onsager {ONSAGER_TC:.3f} (tol ±{tol})"


def _loglog_slope(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least-squares slope + R² of ``log y`` vs ``log x`` (stdlib only).

    The check re-derives the scaling exponent itself rather than trusting the
    number the experiment reported — a receipt, not an honour-system echo.
    """
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    n = len(lx)
    mx, my = sum(lx) / n, sum(ly) / n
    sxx = sum((a - mx) ** 2 for a in lx)
    sxy = sum((a - mx) * (b - my) for a, b in zip(lx, ly))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((b - (slope * a + intercept)) ** 2 for a, b in zip(lx, ly))
    ss_tot = sum((b - my) ** 2 for b in ly)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, r2


def check_m02(report: dict) -> tuple[bool | None, str]:
    """Finite-size scaling: the peak susceptibility grows as χ_max ∝ L^(γ/ν).

    Returns ``None`` unless this is an M02 report. Otherwise re-fits the slope
    of log χ_max vs log L from the per-L peaks and asserts it sits near the
    exact 2D Ising exponent γ/ν = 7/4, with a tight log-log fit. A generous
    tolerance — this catches a simulation that scales wrong (or not at all),
    not a high-precision exponent measurement.
    """
    if report.get("experiment") != "M02-finite-size-scaling":
        return None, "not a finite-size-scaling report"
    curves = report.get("curves") or []
    Ls = [c.get("L") for c in curves]
    chimax = [c.get("chi_max") for c in curves]
    if len(Ls) < 3 or any(v is None or v <= 0 for v in Ls + chimax):
        return None, "finite-size-scaling report missing per-L peaks"
    slope, r2 = _loglog_slope(Ls, chimax)
    tol = 0.15
    ok = abs(slope - GAMMA_OVER_NU) <= tol and r2 >= 0.97
    return ok, (
        f"χ_max ∝ L^{slope:.3f} vs γ/ν={GAMMA_OVER_NU:.2f} "
        f"(tol ±{tol}, R²={r2:.3f}, {len(Ls)} sizes)"
    )


def _collapse_loss(curves, beta_over_nu, inv_nu=INV_NU, tc=ONSAGER_TC, n_bins=24) -> float:
    """Stdlib port of ``m03.collapse_quality`` — the data-collapse residual.

    Rescales every ``(L, T, M)`` curve to ``x=(T-tc)·L^(1/ν)``, ``y=M·L^(β/ν)``,
    interpolates each onto a shared grid over the x-overlap window, and returns
    the mean per-bin cross-curve variance normalized by the pooled y-variance.
    ``inf`` if fewer than two curves overlap. A receipt that re-derives the
    number rather than echoing it; mirrors how ``_loglog_slope`` ports M02.
    """
    rescaled = []
    for (L, T, M) in curves:
        x = [(t - tc) * L ** inv_nu for t in T]
        y = [m * L ** beta_over_nu for m in M]
        pairs = sorted(zip(x, y))
        rescaled.append(([p[0] for p in pairs], [p[1] for p in pairs]))
    if len(rescaled) < 2:
        return math.inf
    lo = max(xs[0] for xs, _ in rescaled)
    hi = min(xs[-1] for xs, _ in rescaled)
    if not (hi > lo):
        return math.inf

    centers = [lo + (hi - lo) * i / (n_bins - 1) for i in range(n_bins)]

    def _interp(xs, ys, c):
        if c <= xs[0]:
            return ys[0]
        if c >= xs[-1]:
            return ys[-1]
        for k in range(1, len(xs)):
            if xs[k] >= c:
                x0, x1, y0, y1 = xs[k - 1], xs[k], ys[k - 1], ys[k]
                if x1 == x0:
                    return y0
                return y0 + (y1 - y0) * (c - x0) / (x1 - x0)
        return ys[-1]

    cols = [[_interp(xs, ys, c) for xs, ys in rescaled] for c in centers]
    all_y = [v for col in cols for v in col]
    n_all = len(all_y)
    mean_all = sum(all_y) / n_all
    pooled_var = sum((v - mean_all) ** 2 for v in all_y) / n_all
    if pooled_var <= 0.0:
        return 0.0

    bin_vars = []
    for col in cols:
        m = sum(col) / len(col)
        bin_vars.append(sum((v - m) ** 2 for v in col) / len(col))
    return (sum(bin_vars) / len(bin_vars)) / pooled_var


def _fit_beta_over_nu(curves, lo=0.0, hi=0.5, tc=ONSAGER_TC, tol=1e-6) -> tuple[float, float]:
    """Stdlib golden-section minimization of ``_collapse_loss`` over β/ν."""
    gr = (math.sqrt(5.0) - 1.0) / 2.0
    f = lambda bon: _collapse_loss(curves, bon, tc=tc)
    a, b = lo, hi
    c, d = b - gr * (b - a), a + gr * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(200):
        if abs(b - a) < tol:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - gr * (b - a); fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + gr * (b - a); fd = f(d)
    xm = 0.5 * (a + b)
    return xm, f(xm)


def check_m03(report: dict) -> tuple[bool | None, str]:
    """Data collapse: M·L^(β/ν) vs (T-T_c)·L^(1/ν) overlays onto one master curve.

    Returns ``None`` unless this is an M03 report. Otherwise re-derives β/ν
    *independently* from the per-L (T, M) curves by minimizing the collapse loss
    (a stdlib port of ``m03.collapse_quality``/``fit_beta_over_nu``), and asserts
    the fit lands near the exact 2D Ising value β/ν = 1/8 AND the collapse
    residual at the exact exponents is below threshold. A receipt, not an
    honour-system echo of the reported number.
    """
    if report.get("experiment") != "M03-data-collapse":
        return None, "not a data-collapse report"
    raw = report.get("curves") or []
    curves = []
    for c in raw:
        L, T, M = c.get("L"), c.get("T"), c.get("M")
        if L and T and M and len(T) == len(M):
            curves.append((L, list(T), list(M)))
    if len(curves) < 3:
        return None, "data-collapse report missing per-L (T, M) curves"

    bon_fit, _ = _fit_beta_over_nu(curves)
    quality = _collapse_loss(curves, BETA_OVER_NU)   # loss at the EXACT exponents
    tol, q_thresh = 0.03, 0.02
    ok = abs(bon_fit - BETA_OVER_NU) <= tol and quality <= q_thresh
    return ok, (
        f"collapse β/ν={bon_fit:.3f} vs 1/8={BETA_OVER_NU:.3f} "
        f"(tol ±{tol}), residual={quality:.2e} (≤{q_thresh}), {len(curves)} sizes"
    )


# milestone id → check. Add entries as milestones land; the rest report
# "unchecked" so the gap is visible rather than silently assumed.
CHECKS = {"M01": check_m01, "M02": check_m02, "M03": check_m03}


def _grade(fn, reports: list[dict]) -> tuple[str, str]:
    """Grade a milestone against the newest report its check can evaluate."""
    for rep in reports:
        ok, detail = fn(rep)
        if ok is not None:
            return ("pass" if ok else "fail"), detail
    return "no-report", "no report this check can evaluate"


def verify(ids: list[str] | None = None) -> list[dict]:
    """Run registered checks against every verified milestone (or just ``ids``).

    Each result: ``pass`` / ``fail`` (check ran), ``unchecked`` (no check yet),
    or ``no-report`` (nothing the check can read).
    """
    ms = parse_milestones(MILESTONES_MD.read_text(encoding="utf-8") if MILESTONES_MD.exists() else "")
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in _reports_newest_first()]

    results: list[dict] = []
    for m in ms:
        if m["status"] != "verified" or (ids and m["id"] not in ids):
            continue
        fn = CHECKS.get(m["id"])
        if fn is None:
            results.append({"id": m["id"], "status": "unchecked", "detail": "no check registered"})
        else:
            status, detail = _grade(fn, reports)
            results.append({"id": m["id"], "status": status, "detail": detail})
    return results
