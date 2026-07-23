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
import statistics
from pathlib import Path

from .publish import LAB_HOME, MILESTONES_MD, REPORTS_DIR, parse_milestones

# Onsager's exact 2D Ising critical temperature, 1944.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.2692
# Exact 2D Ising susceptibility exponent ratio (M02 finite-size scaling).
GAMMA_OVER_NU = 7.0 / 4.0   # = 1.75
# Exact 2D Ising magnetization scaling dimension (M03 data collapse): β=1/8, ν=1.
BETA_OVER_NU = 1.0 / 8.0    # = 0.125
INV_NU = 1.0                # 1/ν
# 3D simple-cubic Ising critical temperature — the MC/series benchmark (M06).
TC_3D = 4.5115
# 3D ±J Edwards–Anderson spin-glass transition temperature (M12) — the modern
# Monte-Carlo benchmark (no closed form; the literature clusters near ≈0.95).
# Located by the disorder-averaged Binder-cumulant crossing across lattice sizes.
TC_SG_3D = 0.95
# Crossing tolerance for M12: finite-size Binder crossings drift with the size pair
# and carry corrections-to-scaling, so — like M08's ±0.07 BKT window — a physically
# justified band is allowed. Owned by the check (not read from the report) so a run
# can't widen its own tolerance to pass. A broken run still misses by a wide margin.
TC_SG_3D_TOL = 0.15
# Exact triangular-lattice 2D Ising critical temperature (M05): T_c = 4/ln 3.
TC_TRI = 4.0 / math.log(3.0)   # ≈ 3.6410
# 2D XY BKT transition temperature (M08) — the square-lattice MC/RG benchmark
# (0.89290(5)); no closed form. Located via the helicity-modulus jump crossing.
T_BKT = 0.8929
# The universal-jump slope: at the crossing Υ/T = 2/π, i.e. Υ(T_BKT) = (2/π)·T_BKT.
TWO_OVER_PI = 2.0 / math.pi
# Wannier's exact residual (ground-state) entropy per spin of the triangular Ising
# antiferromagnet (M13): S0/N = 0.3383 k_B, the macroscopic degeneracy the frustrated
# ground state leaves at T=0. Measured by integrating C(T)/T down from S(∞)=ln2.
WANNIER_S0 = 0.3383
# Residual-entropy tolerance for M13. A physically-justified band, NOT a fudge: the
# integrated residual carries a few-percent systematic from the finite temperature
# window and the trapezoidal integration of a Monte-Carlo C(T). Empirically it lands
# slightly BELOW 0.3383 and converges to ≈0.32 as the lattice grows (L=24→0.334,
# L=96→0.322), so ±0.03 comfortably passes the trustworthy large-L runs while a broken
# run — wrong geometry, wrong J sign, or a non-degenerate ground state (residual near 0
# or ln2) — misses by 10× more. Owned by the check, not read from the report, so a run
# can't widen its own tolerance.
WANNIER_S0_TOL = 0.03
# The exact triangular-AFM ground-state energy per spin (|J| units): each frustrated
# triangle keeps two of three bonds → Σ_bonds s_i s_j = −N → e = −1. An independent
# anchor: a wrong-sign (accidental FM, e→−3) or wrong-geometry run fails this outright.
TRI_AFM_GROUND_ENERGY = -1.0
TRI_AFM_GROUND_ENERGY_TOL = 0.06
# 2D ±J random-bond Ising, the multicritical Nishimori point (M14): the square-lattice
# literature benchmark (p_c ≈ 0.109–0.110, T_c ≈ 0.953). M14 does NOT gate on pinning
# this — it is genuinely hard at reachable scale — it gates on the EXACT Nishimori-line
# internal energy, an identity that needs no critical precision.
MNP_P_C = 0.1094
MNP_T_C = 0.9528
# Nishimori-line energy tolerance for M14, OWNED BY THE CHECK. On the line the disorder-
# averaged energy per spin is the exact identity E/N = −2·tanh(1/T) = −2(1−2p) (square,
# J=1); at modest L the measured value sits within a few ×0.01 of it, so ±0.05 passes the
# trustworthy runs while a broken engine (wrong bond draw, wrong estimator, off the line)
# misses by far more. A hard identity, not a fitted T_c — the tolerance is slack, not a fudge.
MNP_ENERGY_TOL = 0.05
# How tightly a reported (p, T) point must sit on the Nishimori line to be graded: the
# check re-derives tanh(1/T) and requires it to equal 1 − 2p. A point off the line has no
# exact-energy identity to test against, so it is rejected rather than mis-graded.
NISHIMORI_LINE_TOL = 1e-2
# Allen–Cahn coarsening exponent (M15): curvature-driven growth of a non-conserved order
# parameter gives L_domain(t) ∼ t^(1/2). The verified claim is this GROWTH EXPONENT.
ALLEN_CAHN_EXPONENT = 0.5
# Exponent tolerance for M15, OWNED BY THE CHECK. A physically-justified band, NOT a fudge:
# Allen–Cahn is asymptotic and the finite-time effective exponent is documented to sit a few
# percent BELOW ½ (the preasymptotic correction — coarsening approaches t^(1/2) from below),
# so ±0.06 admits the honest ~0.46–0.49 measured at reachable scale while still rejecting a
# broken run: diffusive ¼, ballistic 1, or a frozen/saturated ~0 all miss by far more.
ALLEN_CAHN_TOL = 0.06
# The log-log coarsening line is essentially perfect, so a genuine power-law fit clears a
# high R²; a noisy/curved L(t) (un-quenched, or fit across the finite-size saturation knee)
# would not. Guards against grading a slope off a bad line.
M15_MIN_R2 = 0.99
# M15 scaling-window rule — re-derived here (a receipt), matching ``m15`` defaults. The check
# prefers the window params the report stored (so producer and grader can't silently drift),
# falling back to these if absent.
M15_T_FIT_MIN = 20
M15_L_MIN_FIT = 4.0
M15_SAT_FRAC = 0.20
# ── M17: 1+1d kinetic roughening. Three growth classes, three EXACT exponents. ────────────
# Kardar–Parisi–Zhang (1986): w(t) ∼ t^β with β = 1/3, w_sat ∼ L^α with α = 1/2, so the
# dynamic exponent z = α/β = 3/2 and the correlation length ξ(t) ∼ t^{1/z} = t^{2/3}.
KPZ_BETA = 1.0 / 3.0
KPZ_ALPHA = 0.5
KPZ_Z = 1.5
# Edwards–Wilkinson (the linear theory — KPZ minus the (∇h)² term): β = 1/4 exactly.
EW_BETA = 0.25
# Random deposition (independent columns, no relaxation): β = 1/2 exactly, and stronger — a
# CLOSED FORM w²(t) = p(1−p)·t at every t, with nothing fitted.
RD_BETA = 0.5
# Tolerances, OWNED BY THE CHECK (never read from the report, so a run can't widen its own
# band). Physically justified, not fudges: like M15's Allen–Cahn band, the finite fit window
# makes the effective exponent land a few percent BELOW its asymptotic value — measured at
# ≈0.316 for KPZ and ≈0.239 for EW, both low by the same ~5%, which is the tell that the
# deficit is the window and not the physics. The bands still separate the three classes by a
# wide margin: KPZ's ±0.04 admits [0.293, 0.373], which excludes EW's ¼ and RD's ½ outright.
KPZ_BETA_TOL = 0.04
EW_BETA_TOL = 0.03
RD_BETA_TOL = 0.02
KPZ_ALPHA_TOL = 0.05
# Random deposition is graded against its exact CURVE, point by point — max relative
# deviation of the measured w² from p(1−p)t. A pipeline with a broken width estimator or a
# mis-scaled time axis fails here before any exponent is fitted.
RD_EXACT_TOL = 0.05
# The log-log roughening line is essentially perfect over ≥2 decades; a genuine power law
# clears a high R². Guards against grading a slope off a curved or noisy line.
M17_MIN_R2 = 0.99
# M17 scaling-window rule — re-derived here (a receipt). Preferred from the report when it
# stored them (so producer and grader can't silently drift), else these.
M17_T_FIT_MIN = 20
M17_W_FIT_MIN = 1.5
# λ < 0 for the single-step model (v(u) = (p/2)(1−u²) ⇒ λ = ∂²v/∂u² = −p), so KPZ predicts
# the MIRRORED Tracy–Widom law. These signed skewness targets are what a correct run matches;
# a positive skewness would mean the growth direction or the map was inverted.
TW_GUE_SKEW = -0.2241   # curved / droplet geometry
TW_GOE_SKEW = -0.2935   # flat geometry
# Skewness band. Third moments converge slowly (O(t^{-1/3}) corrections ≈ 0.15 at reachable
# t) and carry a sampling error ≈ sqrt(6/N); ±0.06 admits that without admitting a Gaussian
# (skew 0) or the wrong Tracy–Widom class.
TW_SKEW_TOL = 0.06


def _reports_newest_first() -> list[Path]:
    """Report and public-receipt JSONs newest-first.

    Full reports remain the preferred local evidence.  A clean git checkout may
    intentionally contain only compact ``reports/receipts/run-<date>-<slug>.json``
    artifacts for older runs, so include those as a verification fallback.  The
    receipts omit only visual snapshots and retain every checker input.
    """
    paths: list[Path] = []
    for d in (REPORTS_DIR, LAB_HOME):
        if d.exists():
            paths += d.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*.json")
    receipts = REPORTS_DIR / "receipts"
    if receipts.exists():
        paths += receipts.glob("run-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.json")

    def sort_key(path: Path) -> tuple[str, bool]:
        is_receipt = path.parent == receipts
        date = path.stem[4:14] if is_receipt else path.stem[:10]
        # For the same run date, try the full report before its compact receipt.
        return date, not is_receipt

    return sorted(paths, key=sort_key, reverse=True)


def check_m01(report: dict) -> tuple[bool | None, str]:
    """2D Ising: the susceptibility χ peaks at the (finite-size) critical point.

    Returns ``None`` if this report isn't an Ising χ-sweep (not applicable).
    Otherwise recovers T at max(χ) and asserts it sits near Onsager's exact T_c
    — a generous tolerance, since this catches a broken simulation, not a
    high-precision exponent claim.
    """
    # M06 (3D Ising) also carries top-level T+chi but a different experiment tag
    # and a different T_c — it has its own check; don't grade it against Onsager.
    # Legacy M01 dumps carry no experiment field; the rendered ones tag
    # "M01-ising-verification". Anything else with a tag belongs to another check.
    exp = report.get("experiment")
    if exp and not exp.startswith("M01"):
        return None, "not the 2D Ising χ-sweep"
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi):
        return None, "not an Ising χ-sweep"
    peak_T = T[max(range(len(chi)), key=lambda i: chi[i])]
    # The default sweep's 0.1-spaced grid can resolve the peak to roughly one
    # bin.  ±0.1 remains a regression/calibration gate, not a precision claim,
    # but no longer passes a result two whole bins away from Onsager.
    tol = 0.1
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


def check_m06(report: dict) -> tuple[bool | None, str]:
    """3D simple-cubic Ising: the χ peak locates T_c near the MC benchmark 4.5115.

    Returns ``None`` unless this is an M06 report. Otherwise re-derives the
    critical temperature *independently* from the per-T (T, χ) arrays — a coarse
    argmax refined by a 3-point parabola through the peak — and asserts it sits
    near the Monte-Carlo benchmark T_c ≈ 4.5115. The tolerance is deliberately
    generous (±0.15): on a small finite lattice the χ peak sits at a
    pseudo-critical T_c(L) shifted *above* the infinite-volume value, so this
    catches a broken 3D simulation, not a precision-T_c claim. A receipt that
    re-computes the number rather than echoing the reported one.
    """
    if report.get("experiment") != "M06-3d-ising":
        return None, "not a 3D-Ising report"
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi) or len(T) < 3:
        return None, "3D-Ising report missing (T, χ) arrays"
    i = max(range(len(chi)), key=lambda k: chi[k])
    # 3-point parabola refinement of the peak (stdlib port of m06.refine_peak).
    if 0 < i < len(T) - 1:
        y0, y1, y2 = chi[i - 1], chi[i], chi[i + 1]
        denom = y0 - 2.0 * y1 + y2
        peak_T = T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    else:
        peak_T = T[i]
    tol = 0.15
    ok = abs(peak_T - TC_3D) <= tol
    return ok, f"3D χ peak at T={peak_T:.3f} vs MC benchmark {TC_3D:.4f} (tol ±{tol})"


def check_m04(report: dict) -> tuple[bool | None, str]:
    """2D Ising specific heat: the C(T) peak locates T_c near Onsager's exact 2.2692.

    Returns ``None`` unless this is an M04 report. Otherwise re-derives the
    critical temperature *independently* from the per-T (T, specific_heat) arrays
    — a coarse argmax refined by a 3-point parabola through the peak — and asserts
    the specific-heat peak sits near the exact 2D T_c. The tolerance (±0.1)
    absorbs the finite-L shift: on a finite lattice the C peak sits a little above
    the infinite-volume value, so this catches a broken thermal measurement, not a
    precision-T_c claim. A receipt that re-computes the number, not an echo.
    """
    if report.get("experiment") != "M04-specific-heat":
        return None, "not an M04 specific-heat report"
    T, cv = report.get("T"), report.get("specific_heat")
    if not T or not cv or len(T) != len(cv) or len(T) < 3:
        return None, "M04 report missing (T, specific_heat) arrays"
    i = max(range(len(cv)), key=lambda k: cv[k])
    # 3-point parabola refinement of the peak (stdlib port of m06.refine_peak).
    if 0 < i < len(T) - 1:
        y0, y1, y2 = cv[i - 1], cv[i], cv[i + 1]
        denom = y0 - 2.0 * y1 + y2
        peak_T = T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    else:
        peak_T = T[i]
    tol = 0.1
    ok = abs(peak_T - ONSAGER_TC) <= tol
    return ok, f"2D C peak at T={peak_T:.3f} vs Onsager exact {ONSAGER_TC:.4f} (tol ±{tol})"


def check_m05(report: dict) -> tuple[bool | None, str]:
    """Triangular-lattice 2D Ising: the χ peak locates T_c near the exact 4/ln 3.

    Returns ``None`` unless this is an M05 report. Otherwise re-derives the
    critical temperature *independently* from the per-T (T, χ) arrays — a coarse
    argmax refined by a 3-point parabola through the peak — and asserts it sits
    near the exact triangular T_c = 4/ln 3 ≈ 3.6410. The tolerance is deliberately
    generous (±0.15, like M06): on a finite lattice the χ peak sits at a
    pseudo-critical T_c(L) shifted *above* the infinite-volume value, so this
    catches a broken triangular simulation (wrong geometry, wrong neighbour count,
    or a non-bipartite update done with the square checkerboard), not a
    precision-T_c claim. A receipt that re-computes the number, not an echo.
    """
    if report.get("experiment") != "M05-triangular":
        return None, "not an M05 triangular-Ising report"
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi) or len(T) < 3:
        return None, "M05 report missing (T, χ) arrays"
    i = max(range(len(chi)), key=lambda k: chi[k])
    # 3-point parabola refinement of the peak (stdlib port of m06.refine_peak).
    if 0 < i < len(T) - 1:
        y0, y1, y2 = chi[i - 1], chi[i], chi[i + 1]
        denom = y0 - 2.0 * y1 + y2
        peak_T = T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    else:
        peak_T = T[i]
    tol = 0.15
    ok = abs(peak_T - TC_TRI) <= tol
    return ok, f"triangular χ peak at T={peak_T:.3f} vs exact 4/ln3 = {TC_TRI:.4f} (tol ±{tol})"


def _refine_peak_stdlib(T, y) -> float:
    """Sub-grid peak location via a 3-point parabola (stdlib port of m06.refine_peak).

    The discrete argmax is only accurate to the grid spacing ΔT; fitting a
    quadratic through the peak sample and its two neighbours recovers the vertex.
    Falls back to the discrete argmax T when the peak is on an endpoint. Shared by
    the per-q M07 check below so every q is graded the same way M04/M05/M06 grade
    their single peak.
    """
    i = max(range(len(y)), key=lambda k: y[k])
    if 0 < i < len(T) - 1:
        y0, y1, y2 = y[i - 1], y[i], y[i + 1]
        denom = y0 - 2.0 * y1 + y2
        return T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    return T[i]


def check_m07(report: dict) -> tuple[bool | None, str]:
    """2D q-state Potts: each q's χ peak locates its exact T_c = 1/ln(1+√q).

    Returns ``None`` unless this is an M07 report. Otherwise re-derives the
    critical temperature *independently* for every q from its per-q (T, χ) arrays
    — a coarse argmax refined by a 3-point parabola — and asserts each lands near
    the exact Potts T_c. The transition is continuous for q ≤ 4 and **first-order**
    for q ≥ 5; first-order transitions have stronger finite-size effects and
    metastability, so the q ≥ 5 tolerance is widened (±0.15) relative to the
    continuous q ≤ 4 tolerance (±0.1) — a physical allowance for the larger
    pseudo-critical shift, not a fudge: a broken simulation (wrong T_c, wrong
    order parameter, a non-ordering lattice) still fails by a wide margin. A
    receipt that re-computes each number, not an echo.
    """
    if report.get("experiment") != "M07-potts":
        return None, "not an M07 Potts report"
    per_q = report.get("per_q")
    if not per_q:
        return None, "M07 report missing per-q arrays"

    parts: list[str] = []
    all_ok = True
    graded = 0
    for entry in per_q:
        q = entry.get("q")
        T, chi = entry.get("T"), entry.get("chi")
        if not q or not T or not chi or len(T) != len(chi) or len(T) < 3:
            continue
        graded += 1
        peak_T = _refine_peak_stdlib(T, chi)
        tc_exact = 1.0 / math.log(1.0 + math.sqrt(q))
        # Continuous (q≤4): ±0.1. First-order (q≥5): ±0.15 — stronger finite-size
        # / metastability shift on a finite lattice (a documented physical effect,
        # not a tolerance fudge; a broken run still misses by far more).
        tol = 0.1 if q <= 4 else 0.15
        ok = abs(peak_T - tc_exact) <= tol
        all_ok = all_ok and ok
        parts.append(f"q={q}: T={peak_T:.3f} vs {tc_exact:.3f} (±{tol}){'' if ok else ' ✗'}")

    if graded == 0:
        return None, "M07 report has no gradable (T, χ) per-q arrays"
    return all_ok, "Potts χ peaks — " + "; ".join(parts)


def check_m08(report: dict) -> tuple[bool | None, str]:
    """2D XY BKT: the helicity-modulus jump crossing locates T_BKT near 0.8929.

    Returns ``None`` unless this is an M08 report. Otherwise re-derives the
    transition temperature *independently* from the per-T (T, helicity) arrays —
    the crossing of Υ(T) with the universal-jump line (2/π)·T, found by linear
    interpolation across the first downward sign change of g(T) = Υ(T) − (2/π)·T —
    and asserts it sits near the MC/RG benchmark T_BKT ≈ 0.8929.

    The tolerance is deliberately generous (**±0.07**), wider than the sharp-peak
    checks (M04's ±0.1 is on a *much* larger T_c, so 0.07 here is the looser
    *relative* window). BKT has **no order-parameter peak** and notoriously strong
    **logarithmic finite-size corrections**, so a single-L crossing is honestly a
    coarse estimate that typically sits a little *above* 0.8929 (the same finite-L
    honesty M05/M06 carry). ±0.07 absorbs that log-correction drift while still
    catching a broken simulation — a wrong helicity estimator (e.g. the dropped
    1/T fluctuation term, the #1 XY failure mode) or an un-equilibrated run misses
    by far more, or fails to cross at all. A receipt that re-computes the number,
    not an echo.
    """
    if report.get("experiment") != "M08-xy-bkt":
        return None, "not an M08 XY-BKT report"
    T, Y = report.get("T"), report.get("helicity_modulus")
    if not T or not Y or len(T) != len(Y) or len(T) < 3:
        return None, "M08 report missing (T, helicity_modulus) arrays"

    # Re-derive the crossing of Υ(T) with (2/π)·T (a receipt, not an echo of the
    # reported tc_crossing): the first downward root of g = Υ − (2/π)·T.
    g = [Y[i] - TWO_OVER_PI * T[i] for i in range(len(T))]
    crossing = None
    for i in range(len(T) - 1):
        if g[i] >= 0.0 and g[i + 1] < 0.0:
            frac = g[i] / (g[i] - g[i + 1])
            crossing = T[i] + frac * (T[i + 1] - T[i])
            break
    if crossing is None:
        return False, (
            f"Υ(T) never crosses the (2/π)T jump line on [{T[0]:.3f}, {T[-1]:.3f}] "
            f"— no BKT crossing bracketed (window mis-placed or run un-equilibrated)"
        )
    tol = 0.07
    ok = abs(crossing - T_BKT) <= tol
    return ok, (
        f"XY helicity-jump crossing at T_BKT={crossing:.3f} vs benchmark "
        f"{T_BKT:.4f} (tol ±{tol})"
    )


def check_m09(report: dict) -> tuple[bool | None, str]:
    """2D Heisenberg / Mermin–Wagner: ⟨|m|⟩ drifts DOWN with L — the absence of order.

    Returns ``None`` unless this is an M09 report. This milestone has **no
    transition to locate** — its falsifiable signature is a *null done honestly*:
    under Mermin–Wagner the 2D Heisenberg model cannot spontaneously order at any
    T > 0 (and, unlike XY, has no BKT escape — π₁(S²)=0, no vortices), so at a
    fixed temperature the per-spin vector magnetization ⟨|m|⟩ **decreases
    monotonically as L grows**, drifting toward 0. PASS = that expected *absence*
    is reproduced; a non-decreasing ⟨|m|⟩(L) (a fake finite-T transition, or a
    broken simulation that orders spuriously) FAILS.

    The check re-derives the verdict from the report's (L, ⟨|m|⟩) arrays — a
    receipt, not an echo of the reported ``monotone_decreasing``: it confirms each
    successive L has a strictly smaller ⟨|m|⟩ (beyond a small Monte-Carlo noise
    floor built from the reported standard errors) AND that the slope of ⟨|m|⟩ vs
    1/L is positive (|m| washes out as L→∞, the infinite-volume value is ~0). The
    #1 way M09 ships wrong — reading a single small L where ⟨|m|⟩ looks finite and
    "finding" a transition — is exactly what a flat/rising sequence would show, so
    that failure is caught, not relabelled a discovery.
    """
    if report.get("experiment") != "M09-heisenberg":
        return None, "not an M09 Heisenberg report"
    Ls, m = report.get("L_values"), report.get("abs_mag")
    if not Ls or not m or len(Ls) != len(m) or len(Ls) < 3:
        return None, "M09 report missing (L_values, abs_mag) arrays (need ≥3 sizes)"
    err = report.get("abs_mag_err") or [0.0] * len(m)

    # Strictly decreasing beyond a 1.5·SEM noise floor (so Monte-Carlo jitter on a
    # statistically-flat pair can't masquerade as a drift — or break a real one).
    decreasing = all(
        m[i + 1] < m[i] - 1.5 * max(err[i], err[i + 1]) for i in range(len(m) - 1)
    )
    # Independent corroboration: ⟨|m|⟩ falls toward its 1/L→0 (infinite-volume)
    # intercept, so the least-squares slope of ⟨|m|⟩ against 1/L is positive.
    x = [1.0 / L for L in Ls]
    mx, my = sum(x) / len(x), sum(m) / len(m)
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, m))
    slope = sxy / sxx if sxx > 0 else 0.0

    ok = decreasing and slope > 0.0
    drift = " > ".join(f"{v:.3f}" for v in m)
    ratios = ", ".join(f"{m[i+1]/m[i]:.2f}" for i in range(len(m) - 1) if m[i] > 0)
    return ok, (
        f"⟨|m|⟩(L={','.join(map(str, Ls))}) = {drift} "
        f"(ratios {ratios}, slope vs 1/L = {slope:+.3f}) — "
        + ("drifts toward 0 with L: Mermin–Wagner absence of order reproduced"
           if ok else
           "does NOT monotonically decrease — a fake finite-T transition, not the "
           "expected absence")
    )


def check_m10(report: dict) -> tuple[bool | None, str]:
    """AFM Ising: the STAGGERED-χ peak locates T_N near Onsager's exact 2.2692.

    Returns ``None`` unless this is an M10 report. Otherwise re-derives the Néel
    temperature *independently* from the per-T (T, chi_staggered) arrays — a coarse
    argmax refined by a 3-point parabola through the peak — and asserts it sits near
    the exact 2D T_c (= T_N, by the bipartite gauge duality). The tolerance (±0.1)
    absorbs the finite-L shift, exactly as ``check_m04`` does on the same number; on
    a finite lattice the peak sits a little above the infinite-volume value, so this
    catches a broken AFM simulation, not a precision-T_N claim.

    A SECOND guard makes this milestone meaningful: it confirms the UNIFORM ⟨|m|⟩
    stayed small (≤ 0.3 across the sweep). The headline AFM bug is a silent sign
    error that reverts the model to the *ferromagnet* — which would still peak at
    2.2692, but on the *uniform* magnetization, with χ_staggered ≈ 0 and a large
    uniform ⟨|m|⟩ at low T. Requiring the staggered peak to be the real signal AND
    the uniform moment to stay ≈ 0 catches that masquerade. A receipt that
    re-computes the number, not an echo.
    """
    if report.get("experiment") != "M10-afm-ising":
        return None, "not an M10 AFM-Ising report"
    T, chi = report.get("T"), report.get("chi_staggered")
    if not T or not chi or len(T) != len(chi) or len(T) < 3:
        return None, "M10 report missing (T, chi_staggered) arrays"
    peak_T = _refine_peak_stdlib(T, chi)
    tol = 0.1
    near_tn = abs(peak_T - ONSAGER_TC) <= tol
    # The AFM signature: the uniform magnetization never orders (≈0 throughout). A
    # silent sign-flip to the FM would make this large — so it must stay small for
    # a PASS, not just the staggered peak landing on T_N.
    abs_mag = report.get("abs_mag") or []
    max_unif = max((abs(v) for v in abs_mag), default=0.0)
    unif_small = max_unif <= 0.3
    ok = near_tn and unif_small
    detail = (
        f"staggered χ_s peak at T={peak_T:.3f} vs Onsager exact {ONSAGER_TC:.4f} "
        f"(tol ±{tol}); uniform ⟨|m|⟩ ≤ {max_unif:.3f}"
    )
    if not unif_small:
        detail += " ✗ (uniform moment too large — looks like the FM, not the AFM)"
    return ok, detail


def check_m11(report: dict) -> tuple[bool | None, str]:
    """2D Edwards–Anderson spin glass: P(q) BROADENS as T → 0 — the T=0-critical signature.

    Returns ``None`` unless this is an M11 report. Like M09 (Mermin–Wagner) this
    milestone has **no finite-T transition to locate** — the 2D EA glass sits at the
    lower critical dimension (T_c = 0), so the verification is the *expected approach
    to the T = 0 critical point*: the disorder-averaged overlap distribution P(q)
    **broadens monotonically as T falls** (its second moment ⟨q²⟩ grows toward T = 0).
    A finite-T transition claim, or a P(q) that does **not** broaden, is the failure.

    The check re-derives the verdict from the report's (T, ⟨q²⟩) arrays — a receipt,
    not an echo of the reported ``monotone_broadening`` — and adds two physical
    guards so a broken/un-equilibrated run can't pass by accident:

    * **Broadening**: sorted by T ascending, ⟨q²⟩ is (weakly) decreasing — i.e. it
      grows as T → 0. A small fraction of non-monotone steps is tolerated at the noisy
      low-T end (≥ 80% of steps must broaden, AND ⟨q²⟩_cold must exceed ⟨q²⟩_hot by a
      clear margin), since spin glasses are hard to equilibrate; a flat or shrinking
      ⟨q²⟩ fails.
    * **Symmetry**: P(q) = P(−q) by the ±J / spin-inversion symmetry, so the
      disorder-averaged ⟨q⟩ must stay ≈ 0 (the equilibration diagnostic). A large
      |⟨q⟩| means a single broken-symmetry replica leaked through (un-equilibrated or
      buggy), so it fails even if ⟨q²⟩ happened to rise.
    """
    if report.get("experiment") != "M11-spin-glass-2d":
        return None, "not an M11 spin-glass report"
    T, q2 = report.get("T"), report.get("q2_mean")
    if not T or not q2 or len(T) != len(q2) or len(T) < 3:
        return None, "M11 report missing (T, q2_mean) arrays (need ≥3 temperatures)"

    # Re-derive the broadening trend: sort by T, ⟨q²⟩ should fall as T rises.
    order = sorted(range(len(T)), key=lambda i: T[i])
    Ts = [T[i] for i in order]
    q2s = [q2[i] for i in order]
    steps = [q2s[i + 1] - q2s[i] for i in range(len(q2s) - 1)]
    n_down = sum(1 for d in steps if d <= 1e-9)
    frac = n_down / len(steps) if steps else 0.0
    q2_cold, q2_hot = q2s[0], q2s[-1]
    # Cold ⟨q²⟩ must clearly exceed hot (a real broadening, not noise), and ≥80% of
    # the adjacent steps must broaden (tolerating a little low-T Monte-Carlo jitter).
    broadens = frac >= 0.8 and q2_cold > q2_hot + 0.05

    # Symmetry / equilibration guard: |⟨q⟩| ≈ 0 by the ±J symmetry. Prefer the
    # re-derivable per-T ⟨q⟩ if present; else fall back to the reported diagnostic.
    qm = report.get("q_mean")
    max_abs_qmean = (max(abs(v) for v in qm) if qm else
                     report.get("max_abs_q_mean", 0.0))
    symmetric = max_abs_qmean <= 0.15

    ok = broadens and symmetric
    detail = (
        f"⟨q²⟩ grows {q2_hot:.3f}→{q2_cold:.3f} as T falls {Ts[-1]:.2f}→{Ts[0]:.2f} "
        f"({n_down}/{len(steps)} steps broaden); max|⟨q⟩|={max_abs_qmean:.3f} — "
        + ("P(q) broadens toward the T=0 critical point (2D EA orders only at T=0; "
           "no finite-T glass phase) — reproduced"
           if ok else
           ("⟨q²⟩ does NOT broaden monotonically toward T=0 — not the expected "
            "T=0-critical behaviour" if not broadens else
            "P(q) is not symmetric (|⟨q⟩| too large) — un-equilibrated or broken, "
            "not a clean overlap"))
    )
    return ok, detail


def _binder_crossing_stdlib(Ts, G_by_L) -> tuple[float | None, list[tuple]]:
    """Re-derive the multi-L Binder crossing from sorted arrays — stdlib, a receipt.

    ``Ts`` is the ascending temperature ladder; ``G_by_L`` maps each L (int) to its
    g_L(T) on that ladder. For each size pair the crossing is the first ``+ → −`` sign
    change of ``d(T) = g_large − g_small`` (larger L is more ordered below T_SG, less
    above), linear-interpolated to the zero of ``d``. Returns ``(primary_T, pairs)``
    where the primary estimate is the crossing of the two largest sizes (or the median
    of all pairwise crossings if that pair does not cross), and ``pairs`` is the list of
    ``(L_small, L_large, T)`` crossings. ``(None, [])`` when nothing crosses — an honest
    no-crossing, not an invented T_SG. Mirrors ``m12.locate_tsg`` deliberately: the
    check re-computes the number independently rather than echoing the reported one.
    """
    Ls = sorted(G_by_L)
    pairs: list[tuple] = []
    for a in range(len(Ls)):
        for b in range(a + 1, len(Ls)):
            gs, gl = G_by_L[Ls[a]], G_by_L[Ls[b]]
            d = [x - y for y, x in zip(gs, gl)]
            for i in range(len(d) - 1):
                if d[i] >= 0.0 and d[i + 1] < 0.0:
                    denom = d[i + 1] - d[i]
                    t = Ts[i] if denom == 0 else Ts[i] + (-d[i]) * (Ts[i + 1] - Ts[i]) / denom
                    pairs.append((Ls[a], Ls[b], float(t)))
                    break
    if not pairs:
        return None, []
    big = {Ls[-1], Ls[-2]} if len(Ls) >= 2 else {Ls[-1]}
    top = next((t for (a, b, t) in pairs if {a, b} == big), None)
    if top is None:
        ts = sorted(t for (_, _, t) in pairs)
        top = ts[len(ts) // 2]
    return float(top), pairs


def check_m12(report: dict) -> tuple[bool | None, str]:
    """3D Edwards–Anderson spin glass: a multi-L Binder crossing locates T_SG ≈ 0.95.

    Returns ``None`` unless this is an M12 report. Unlike M11 (2D, T_c = 0, no finite-T
    phase), the **3D** ±J glass has a genuine finite-temperature spin-glass transition;
    its fingerprint is the disorder-averaged Binder cumulant g_L(T) crossing at a single
    temperature across ≥3 lattice sizes on one shared ladder. The check **re-derives**
    that crossing from the report's per-L ``binder_by_L`` arrays (a receipt, not an echo
    of the reported ``crossing_T``) and asserts it lands near the ≈0.95 benchmark within
    the check-owned ±0.15 band, plus two guards so an under-equilibrated run can't pass:

    * **A crossing must exist**: ≥3 sizes must actually intersect. A smeared, crossing-
      free g_L(T) — the signature of parallel-tempering under-equilibration (M11's
      documented failure mode) — has no crossing and fails, rather than passing on a
      flat curve.
    * **Symmetry / equilibration**: P(q) = P(−q) by the ±J symmetry, so the disorder-
      averaged ⟨q⟩ must stay ≈ 0 across every size and temperature. A large |⟨q⟩| means
      a broken-symmetry replica leaked through, so it fails even if a crossing appeared.
    """
    if report.get("experiment") != "M12-spin-glass-3d":
        return None, "not an M12 spin-glass report"
    T = report.get("T")
    binder_by_L = report.get("binder_by_L")
    if (not T or not binder_by_L or len(binder_by_L) < 3 or len(T) < 3
            or any(len(v) != len(T) for v in binder_by_L.values())):
        return None, "M12 report missing a shared T ladder or ≥3 per-L Binder arrays"

    order = sorted(range(len(T)), key=lambda i: T[i])
    Ts = [float(T[i]) for i in order]
    G_by_L = {int(k): [float(v[i]) for i in order] for k, v in binder_by_L.items()}
    crossing_T, pairs = _binder_crossing_stdlib(Ts, G_by_L)

    # Symmetry / equilibration guard: |⟨q⟩| ≈ 0 across all sizes and temperatures.
    qm = report.get("q_mean_by_L") or {}
    max_abs_qmean = max((abs(x) for v in qm.values() for x in v), default=None)
    if max_abs_qmean is None:
        max_abs_qmean = report.get("max_abs_q_mean", 0.0)

    has_crossing = crossing_T is not None
    near = has_crossing and abs(crossing_T - TC_SG_3D) <= TC_SG_3D_TOL
    symmetric = max_abs_qmean <= 0.15
    ok = near and symmetric

    ct_str = f"{crossing_T:.3f}" if has_crossing else "none"
    pair_str = ", ".join(f"{a}/{b}→{t:.3f}" for (a, b, t) in pairs) or "no pair crosses"
    detail = (
        f"Binder crossing T_SG = {ct_str} vs benchmark {TC_SG_3D:.2f} "
        f"(tol ±{TC_SG_3D_TOL}); pairwise [{pair_str}]; max|⟨q⟩|={max_abs_qmean:.3f} — "
        + ("g_L(T) cross near T_SG≈0.95 — the finite-T 3D spin-glass transition, "
           "reproduced" if ok else
           ("no multi-L Binder crossing resolved (smeared g_L(T) — likely "
            "under-equilibrated; needs more disorder realizations / longer parallel "
            "tempering)" if not has_crossing else
            ("crossing far from the 0.95 benchmark" if not near else
             "P(q) not symmetric (|⟨q⟩| too large) — un-equilibrated or broken")))
    )
    return ok, detail


def check_m13(report: dict) -> tuple[bool | None, str]:
    """Frustrated triangular antiferromagnet: the integrated residual entropy ≈ 0.3383 k_B.

    Returns ``None`` unless this is an M13 report. Otherwise **re-derives** the residual
    entropy from the report's own ``(T, specific_heat)`` arrays — re-integrating C(T)/T
    down from the free-spin reference S(∞) = ln 2 with the shared ``entropy`` primitive
    (a receipt, not an echo of the reported ``s0_measured``) — and asserts it lands near
    Wannier's exact ``S0/N = 0.3383`` within the check-owned ±0.03 band. Two things make
    the pass honest rather than lucky:

    * **The integration is redone here**, from the raw C(T), so a report cannot ship a
      hand-set residual; the number is recomputed from the curve every grade.
    * **A ground-state anchor**: the frustrated triangular AFM has an exact ground energy
      of −1 per spin (two of every triangle's three bonds satisfied). The coldest measured
      energy must sit near −1, so an accidental ferromagnet (e → −3) or a wrong-geometry
      run fails outright even if its integral happened to land near 0.3383.

    A miss (coarse grid / small lattice / broken model) fails, and the milestone ships as
    an honest ``[~]`` failed-calibration null — never a fake green.
    """
    if report.get("experiment") != "M13-triangular-afm":
        return None, "not an M13 triangular-AFM report"
    T, C = report.get("T"), report.get("specific_heat")
    if not T or not C or len(T) != len(C) or len(T) < 3:
        return None, "M13 report missing parallel (T, specific_heat) arrays"

    from .entropy import LN2, residual_entropy
    s0 = residual_entropy(T, C, s_inf=LN2, add_high_t_tail=True)
    near = abs(s0 - WANNIER_S0) <= WANNIER_S0_TOL

    # Ground-state energy anchor: the coldest measured energy per spin ≈ −1.
    energy = report.get("energy") or []
    e_ground = min(energy) if energy else None
    ground_ok = e_ground is not None and abs(e_ground - TRI_AFM_GROUND_ENERGY) <= TRI_AFM_GROUND_ENERGY_TOL

    ok = bool(near and ground_ok)
    e_str = f"{e_ground:.3f}" if e_ground is not None else "—"
    detail = (
        f"integrated residual S0/N = {s0:.4f} vs Wannier exact {WANNIER_S0:.4f} "
        f"(tol ±{WANNIER_S0_TOL}); ground-state energy {e_str}/spin (exact −1) — "
        + ("frustrated residual entropy reproduced by C/T integration" if ok else
           ("residual near 0.3383 but the ground energy is off (wrong sign/geometry?)"
            if near and not ground_ok else
            ("ground energy sane but the integrated residual misses 0.3383 — coarse "
             "grid / small lattice / under-converged C" if ground_ok and not near else
             "both the residual and the ground energy are off — broken run")))
    )
    return ok, detail


def check_m14(report: dict) -> tuple[bool | None, str]:
    """Random-bond Ising: the disorder-averaged energy ON the Nishimori line is exact.

    Returns ``None`` unless this is an M14 report. M14's verified claim is NOT the
    (genuinely hard) multicritical-point location — it is the **exact Nishimori-line
    internal energy**. On the line ``tanh(J/T) = 1 − 2p``, and Nishimori's gauge symmetry
    fixes the disorder-averaged energy per spin to the identity

        E/N = −2 J tanh(J/T) = −2 J (1 − 2p)      (square lattice, exact, any L),

    so the check **re-derives** the exact target from each calibration point's own ``T``
    (a receipt, not an echo of the reported ``energy_exact``) and asserts the measured
    disorder-averaged energy lands within the check-owned ±0.05 band, at every point. Two
    guards keep the pass honest:

    * **On the line**: each point must actually sit on the Nishimori line — the check
      re-checks ``tanh(1/T) ≈ 1 − 2p`` — else there is no exact identity to grade against
      and the point is rejected (a run can't smuggle in an off-line point that happens to
      match some other energy).
    * **A spread of points**: ≥3 distinct ``p`` must be graded, so a single lucky point
      can't carry the leaf.

    The precise MNP (p_c ≈ 0.109, T_c ≈ 0.953) is mapped only approximately at reachable
    scale and is deliberately **not** gated — a documented open edge, not a fake green.
    """
    if report.get("experiment") != "M14-random-bond-nishimori":
        return None, "not an M14 random-bond report"
    pts = report.get("calibration_points")
    if not pts or len(pts) < 3:
        return None, "M14 report missing ≥3 Nishimori-line calibration points"

    parts: list[str] = []
    all_ok = True
    graded = 0
    for pt in pts:
        p, T, e = pt.get("p"), pt.get("T"), pt.get("energy")
        if p is None or T is None or e is None or T <= 0:
            continue
        # Guard 1 — the point must be on the Nishimori line, else the identity doesn't apply.
        on_line = abs(math.tanh(1.0 / T) - (1.0 - 2.0 * p)) <= NISHIMORI_LINE_TOL
        if not on_line:
            all_ok = False
            parts.append(f"p={p:.3f}: OFF the Nishimori line ✗")
            continue
        graded += 1
        # Re-derive the exact target from T alone (a receipt): E/N = −2·tanh(1/T).
        e_exact = -2.0 * math.tanh(1.0 / T)
        dev = abs(e - e_exact)
        ok = dev <= MNP_ENERGY_TOL
        all_ok = all_ok and ok
        parts.append(f"p={p:.3f}: E={e:.3f} vs {e_exact:.3f} (Δ={dev:.3f}){'' if ok else ' ✗'}")

    if graded < 3:
        return None, "M14 report has <3 gradable on-line calibration points"
    detail = (
        f"Nishimori-line energy E/N vs exact −2·tanh(1/T) — " + "; ".join(parts) + " — "
        + ("the exact disorder-averaged Nishimori-line energy is reproduced across the "
           "line (the MNP p_c≈0.109 itself is mapped only approximately at this scale)"
           if all_ok else
           "measured energy departs from the exact Nishimori-line identity — a broken "
           "random-bond run, not the expected exact energy")
    )
    return all_ok, detail


def _loglog_slope_r2(xs: list[float], ys: list[float]) -> tuple[float, float, int]:
    """Least-squares slope + R² of ``log y`` vs ``log x`` (stdlib), plus the point count.

    Distinct from ``_loglog_slope`` (which takes raw x,y and logs them): here ``xs``/``ys``
    are ALREADY the window-selected raw ``t``/``L`` and this logs them once. Returns
    ``(slope, r2, n)``. The check re-fits the M15 growth exponent itself — a receipt, not an
    echo of the reported number.
    """
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    n = len(lx)
    mx, my = sum(lx) / n, sum(ly) / n
    sxx = sum((a - mx) ** 2 for a in lx)
    sxy = sum((a - mx) * (b - my) for a, b in zip(lx, ly))
    slope = sxy / sxx if sxx > 0 else 0.0
    intercept = my - slope * mx
    ss_res = sum((b - (slope * a + intercept)) ** 2 for a, b in zip(lx, ly))
    ss_tot = sum((b - my) ** 2 for b in ly)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, r2, n


def check_m15(report: dict) -> tuple[bool | None, str]:
    """Glauber domain growth: the coarsening exponent n in L(t) ∼ t^n is Allen–Cahn's ½.

    Returns ``None`` unless this is an M15 report. Otherwise **re-derives** the growth
    exponent from the report's own ``(times, L_corr)`` arrays — re-selecting the scaling
    window (t ≥ t_fit_min, L ∈ [L_min_fit, sat_frac·L]) with the *stored* window rule and
    re-fitting ``log L`` vs ``log t`` (a receipt, not an echo of the reported ``exponent``) —
    and asserts it lands near the Allen–Cahn ½ within the check-owned ±0.06 band. Two guards
    keep the pass honest:

    * **A clean power law**: the re-fit R² must clear ``M15_MIN_R2`` (0.99). A noisy or curved
      L(t) — an un-quenched run, or a fit dragged across the finite-size saturation knee —
      fails rather than passing on a slope through bad points.
    * **Real growth over range**: ≥5 window points spanning at least a decade in ``t`` and a
      clearly growing L (L_hi ≥ 2·L_lo), so a nearly-flat/frozen curve can't score a fit.

    The graded estimator is the **correlation length** (the energy length rides along in the
    report as a documented cross-check). The finite-time effective exponent honestly sits a
    few percent below ½; the band absorbs that documented preasymptotic bias without admitting
    a broken exponent (diffusive ¼, ballistic 1, frozen ~0).
    """
    if report.get("experiment") != "M15-glauber-domain-growth":
        return None, "not an M15 Glauber domain-growth report"
    t, L = report.get("times"), report.get("L_corr")
    if not t or not L or len(t) != len(L) or len(t) < 5:
        return None, "M15 report missing parallel (times, L_corr) arrays"

    L_box = report.get("L")
    if not L_box:
        return None, "M15 report missing the lattice size L"
    t_fit_min = report.get("t_fit_min", M15_T_FIT_MIN)
    l_min_fit = report.get("l_min_fit", M15_L_MIN_FIT)
    sat_frac = report.get("sat_frac", M15_SAT_FRAC)

    # Re-select the scaling window from the stored rule and re-fit the exponent.
    xs, ys = [], []
    for ti, Li in zip(t, L):
        if (Li is None or ti is None or Li <= 0 or not math.isfinite(Li)):
            continue
        if ti >= t_fit_min and l_min_fit <= Li <= sat_frac * L_box:
            xs.append(float(ti)); ys.append(float(Li))
    if len(xs) < 5:
        return None, "M15 report has <5 points inside the scaling window"

    slope, r2, n = _loglog_slope_r2(xs, ys)
    t_lo, t_hi = min(xs), max(xs)
    L_lo, L_hi = min(ys), max(ys)
    decade = t_hi / t_lo >= 10.0
    grew = L_hi >= 2.0 * L_lo
    clean = r2 >= M15_MIN_R2
    near = abs(slope - ALLEN_CAHN_EXPONENT) <= ALLEN_CAHN_TOL
    ok = bool(near and clean and decade and grew)

    detail = (
        f"coarsening exponent n = {slope:.3f} vs Allen–Cahn {ALLEN_CAHN_EXPONENT:.2f} "
        f"(tol ±{ALLEN_CAHN_TOL}, R²={r2:.4f}, {n} pts, t∈[{t_lo:.0f},{t_hi:.0f}], "
        f"L∈[{L_lo:.1f},{L_hi:.1f}]) — "
        + ("L(t)∼t^n grows as Allen–Cahn t^(1/2) predicts (effective exponent a few percent "
           "below ½ is the documented preasymptotic correction)" if ok else
           ("R² too low — L(t) is not a clean power law (un-quenched or fit across the "
            "saturation knee)" if not clean else
            ("window too short — needs ≥1 decade in t and a clearly growing L" if not (decade and grew) else
             "exponent off the Allen–Cahn ½ prediction — a broken coarsening run")))
    )
    return ok, detail


def _group_rms(xs, ys) -> tuple[float, int]:
    groups: dict[float, list[float]] = {}
    for x, y in zip(xs, ys):
        groups.setdefault(round(float(x), 8), []).append(float(y))
    residuals = []
    for values in groups.values():
        if len(values) < 3:
            continue
        mean = sum(values) / len(values)
        residuals.append(math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)))
    return ((sum(residuals) / len(residuals), len(residuals))
            if residuals else (float("inf"), 0))


def check_m16(report: dict) -> tuple[bool | None, str]:
    """Re-derive whether a quenched 3D glass ages on the ``dt/t_w`` clock."""
    if report.get("experiment") != "M16-spin-glass-aging":
        return None, "not an M16 spin-glass aging report"
    tws, dts = report.get("waiting_times"), report.get("delta_times")
    rows = report.get("correlations")
    if not isinstance(tws, list) or not isinstance(dts, list) or not isinstance(rows, dict):
        return None, "M16 report missing waiting-time correlation table"
    if len(tws) < 3 or len(dts) < 4:
        return False, "M16 needs >=3 waiting times and >=4 lag times"
    ratios, differences, values = [], [], []
    for tw in tws:
        row = rows.get(str(int(tw)))
        if not isinstance(row, list) or len(row) != len(dts):
            return False, f"M16 incomplete row for t_w={tw}"
        for dt, value in zip(dts, row):
            if not isinstance(value, (int, float)) or not -1.0 <= float(value) <= 1.0:
                return False, "M16 correlation outside [-1,1]"
            ratios.append(float(dt) / float(tw))
            differences.append(float(dt))
            values.append(float(value))
    ratio_resid, ratio_groups = _group_rms(ratios, values)
    diff_resid, diff_groups = _group_rms(differences, values)
    collapse_ratio = ratio_resid / diff_resid if diff_resid > 0 else float("inf")
    fixed_lag = dts[len(dts) // 2]
    j = dts.index(fixed_lag)
    fixed = [float(rows[str(int(tw))][j]) for tw in tws]
    separation = fixed[-1] - fixed[0]
    ok = bool(collapse_ratio <= 0.80 and separation >= 0.03
              and ratio_groups >= 2 and diff_groups >= 4)
    return ok, (
        f"3D EA two-time correlation: t/t_w collapse residual is {collapse_ratio:.2f}× "
        f"the t−t_w residual ({ratio_groups} ratio groups, {diff_groups} lag groups); "
        f"at fixed Δt={fixed_lag}, C rises {fixed[0]:.3f}→{fixed[-1]:.3f} "
        f"(Δ={separation:+.3f}) — " +
        ("aging/time-translation breaking resolved" if ok else "aging gate not resolved")
    )


def _refit_growth_exponent(times, width, t_fit_min: float, w_fit_min: float):
    """Re-select M17's scaling window from the stored rule and re-fit ``log w`` vs ``log t``.

    Stdlib-only twin of ``m17.fit_exponent`` — the check must arrive at the exponent from the
    raw curve, never by reading the reported one. Returns ``(slope, r2, n, t_lo, t_hi)`` or
    ``None`` when fewer than four points survive the window.
    """
    xs, ys = [], []
    for t, w in zip(times or [], width or []):
        if t is None or w is None:
            continue
        t, w = float(t), float(w)
        if not (math.isfinite(t) and math.isfinite(w)) or w <= 0:
            continue
        if t >= t_fit_min and w >= w_fit_min:
            xs.append(t); ys.append(w)
    if len(xs) < 4:
        return None
    slope, r2, n = _loglog_slope_r2(xs, ys)
    return slope, r2, n, min(xs), max(xs)


def check_m17(report: dict) -> tuple[bool | None, str]:
    """KPZ growth on a ring: β = 1/3, α = 1/2, z = 3/2 — and the controls must NOT agree.

    Returns ``None`` unless this is an M17 report. Otherwise **re-derives** every graded
    number from the report's own raw arrays and grades five things, all of which must hold:

    1. **β = 1/3 for the KPZ model**, re-fit from ``growth.kpz.{times,width}`` with the stored
       window rule, inside the check-owned ±0.04 band, on a clean power law (R² ≥ 0.99).
    2. **The controls separate.** The *same* re-fit applied to the Edwards–Wilkinson and
       random-deposition curves must land on *their* exact exponents (1/4 and 1/2) — this is
       the negative control in the strict sense. A pipeline that manufactured 1/3 from any
       curve would report 1/3 three times and fail here; three exponents landing on three
       different exact values is what makes the KPZ number a measurement.
    3. **Random deposition matches its closed form** ``w²(t) = p(1−p)t`` point by point, to
       within ``RD_EXACT_TOL``. Re-computed here from the stored ``width_sq``, so it grades an
       exact curve with nothing fitted — the strongest single anchor in the milestone.
    4. **α = 1/2 from saturation**, re-fit from the stored ``(L, w_sat)`` table, giving
       ``z = α/β`` near 3/2.
    5. **Tracy–Widom class assignment.** The droplet sample's skewness must sit nearer the
       (λ<0-mirrored) GUE value and the flat sample's nearer GOE, each within ``TW_SKEW_TOL``.
       Grading the *assignment* — not merely "non-Gaussian" — is what makes the geometry
       dependence falsifiable. The fourth moment is deliberately NOT graded: it does not
       resolve at reachable ``t`` and the report says so.
    """
    if report.get("experiment") != "M17-kpz-growth":
        return None, "not an M17 KPZ growth report"
    growth = report.get("growth")
    if not isinstance(growth, dict) or "kpz" not in growth:
        return None, "M17 report missing the per-model growth curves"

    t_fit_min = float(report.get("t_fit_min", M17_T_FIT_MIN))
    w_fit_min = float(report.get("w_fit_min", M17_W_FIT_MIN))

    fits = {}
    for name in ("kpz", "ew", "rd"):
        block = growth.get(name)
        if not isinstance(block, dict):
            return None, f"M17 report missing the {name} growth curve"
        got = _refit_growth_exponent(block.get("times"), block.get("width"),
                                     t_fit_min, w_fit_min)
        if got is None:
            return None, f"M17 {name} curve has <4 points inside the scaling window"
        fits[name] = got

    beta, beta_r2, beta_n, t_lo, t_hi = fits["kpz"]
    ew_beta = fits["ew"][0]
    rd_beta = fits["rd"][0]

    # (1) the KPZ exponent, on a clean line spanning at least a decade
    beta_near = abs(beta - KPZ_BETA) <= KPZ_BETA_TOL
    clean = beta_r2 >= M17_MIN_R2
    decade = t_hi / t_lo >= 10.0

    # (2) the controls land on *their* exact exponents — the negative control
    ew_ok = abs(ew_beta - EW_BETA) <= EW_BETA_TOL
    rd_ok = abs(rd_beta - RD_BETA) <= RD_BETA_TOL
    # …and the three are genuinely distinct, not three noisy copies of one slope.
    separated = (abs(beta - ew_beta) > 0.04 and abs(rd_beta - beta) > 0.10)

    # (3) random deposition against its closed form w² = p(1−p)t, recomputed here
    rd_block = growth["rd"]
    p = float(report.get("config", {}).get("p_flip", 0.5))
    rd_dev, rd_pts = 0.0, 0
    for t, w2 in zip(rd_block.get("times") or [], rd_block.get("width_sq") or []):
        exact = p * (1.0 - p) * float(t)
        if exact > 0:
            rd_dev = max(rd_dev, abs(float(w2) - exact) / exact)
            rd_pts += 1
    rd_exact_ok = rd_pts >= 5 and rd_dev <= RD_EXACT_TOL

    # (4) α from the saturation table, and z = α/β
    sat = report.get("saturation")
    alpha = None
    if isinstance(sat, list) and len(sat) >= 3:
        Ls = [float(s["L"]) for s in sat]
        ws = [float(s["w_sat"]) for s in sat]
        alpha = _loglog_slope_r2(Ls, ws)[0]
    alpha_ok = alpha is not None and abs(alpha - KPZ_ALPHA) <= KPZ_ALPHA_TOL
    z = (alpha / beta) if (alpha is not None and beta > 0) else None

    # (5) Tracy–Widom class assignment from the skewness of each geometry
    dists = report.get("distributions") or {}
    targets = {"droplet": TW_GUE_SKEW, "flat": TW_GOE_SKEW}
    tw_ok, tw_bits = True, []
    for ic, target in targets.items():
        s = (dists.get(ic) or {}).get("skewness")
        if s is None:
            tw_ok = False
            tw_bits.append(f"{ic}: missing")
            continue
        s = float(s)
        other = targets["flat"] if ic == "droplet" else targets["droplet"]
        nearer_own = abs(s - target) < abs(s - other)
        within = abs(s - target) <= TW_SKEW_TOL
        tw_ok = tw_ok and nearer_own and within
        tw_bits.append(
            f"{ic} skew {s:+.4f} vs {'GUE' if ic == 'droplet' else 'GOE'} {target:+.4f}"
            f" (Δ={abs(s - target):.4f}{'' if nearer_own else ', WRONG CLASS'})"
        )

    ok = bool(beta_near and clean and decade and ew_ok and rd_ok and separated
              and rd_exact_ok and alpha_ok and tw_ok)

    if ok:
        why = ("three growth classes separate on one pipeline and the KPZ exponents, "
               "saturation and Tracy–Widom class assignment all reproduce")
    elif not (beta_near and clean and decade):
        why = ("the KPZ growth exponent is off 1/3, the log-log line is not clean, or the "
               "fit window spans under a decade")
    elif not (ew_ok and rd_ok and separated and rd_exact_ok):
        why = ("a CONTROL failed: the EW/RD exponents did not land on their own exact values, "
               "the three classes did not separate, or random deposition drifted off its "
               "exact w²=p(1−p)t curve — the exponent pipeline is not trustworthy")
    elif not alpha_ok:
        why = "the roughness exponent α from saturation is off the exact 1/2"
    else:
        why = ("the height-fluctuation skewness did not land on the λ<0-mirrored Tracy–Widom "
               "law its geometry predicts")

    detail = (
        f"β = {beta:.4f} vs KPZ 1/3 (tol ±{KPZ_BETA_TOL}, R²={beta_r2:.4f}, {beta_n} pts, "
        f"t∈[{t_lo:.0f},{t_hi:.0f}]); controls on the same pipeline: EW β={ew_beta:.4f} vs 1/4, "
        f"RD β={rd_beta:.4f} vs 1/2 and w² within {100 * rd_dev:.1f}% of the exact p(1−p)t; "
        f"α={alpha:.4f} vs 1/2" + (f", z=α/β={z:.3f} vs 3/2" if z else "") + "; "
        + "; ".join(tw_bits) + " — " + why
    )
    return ok, detail


def _fib_segment(n_terms: int) -> str:
    a, b = 0, 1
    lines = []
    for i in range(n_terms):
        lines.append(f"{i} {a}\n")
        a, b = b, a + b
    return "".join(lines)


def _lucas_lehmer_residue(exponent: int) -> int:
    modulus = (1 << exponent) - 1
    residue = 4
    for _ in range(exponent - 2):
        residue = (residue * residue - 2) % modulus
    return residue


def check_c01(report: dict) -> tuple[bool | None, str]:
    if report.get("experiment") != "C01-arithmetic-calibration":
        return None, "not a C01 arithmetic calibration"
    n = report.get("n_terms")
    prefix = report.get("source_prefix_text")
    p = report.get("mersenne_exponent")
    candidate = report.get("mersenne_candidate")
    if not isinstance(n, int) or not isinstance(prefix, str) or not isinstance(p, int):
        return None, "C01 report missing b-file bytes or Mersenne exponent"
    exact = prefix == _fib_segment(n)
    residue = _lucas_lehmer_residue(p)
    candidate_ok = candidate == (1 << p) - 1
    ok = bool(exact and candidate_ok and residue == 0)
    return ok, (
        f"OEIS A000045 first {n} terms " + ("match byte-for-byte" if exact else "do not match") +
        f"; Lucas–Lehmer final residue for 2^{p}−1 is {residue} — " +
        ("arithmetic calibration reproduced" if ok else "arithmetic calibration failed")
    )


def _linear_slope(xs, ys) -> float:
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom <= 0:
        raise ValueError("degenerate ephemeris epochs")
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom


def check_a01(report: dict) -> tuple[bool | None, str]:
    if report.get("experiment") != "A01-tess-hot-jupiter-calibration":
        return None, "not an A01 TESS calibration"
    times, epochs = report.get("transit_times"), report.get("transit_epochs")
    depths, kept = report.get("transit_depths"), report.get("kept_transits")
    benchmark = report.get("benchmark")
    products = report.get("products")
    if not all(isinstance(x, list) for x in (times, epochs, depths, kept)) or not isinstance(benchmark, dict):
        return None, "A01 report missing timed transits or benchmark"
    if not (len(times) == len(epochs) == len(depths) == len(kept)):
        return False, "A01 transit arrays are not parallel"
    selected = [i for i, use in enumerate(kept) if use]
    if len(selected) < 8:
        return False, "A01 has fewer than eight accepted transit timings"
    xs = [float(epochs[i]) for i in selected]
    ys = [float(times[i]) for i in selected]
    period = _linear_slope(xs, ys)
    depth = statistics.median(float(depths[i]) for i in selected)
    p_ref, p_tol = float(benchmark["period_days"]), float(benchmark["period_err_days"])
    d_ref, d_tol = float(benchmark["depth_fraction"]), float(benchmark["depth_err_fraction"])
    p_err, d_err = abs(period - p_ref), abs(depth - d_ref)
    hashes_ok = bool(products) and all(
        isinstance(p.get("sha256"), str) and len(p["sha256"]) == 64 for p in products
    )
    ok = bool(p_err <= p_tol and d_err <= d_tol and hashes_ok)
    return ok, (
        f"WASP-18 b from {len(products or [])} TESS SPOC products / {len(selected)} transits: "
        f"P={period:.8f} d vs {p_ref:.8f} (Δ={p_err:.2g}, tol {p_tol:.2g}); "
        f"depth={100*depth:.3f}% vs {100*d_ref:.3f}% "
        f"(Δ={100*d_err:.3f}%, tol {100*d_tol:.3f}%) — " +
        ("archive photometry calibration reproduced" if ok else "published error bars not both recovered")
    )


def check_i01(report: dict) -> tuple[bool | None, str]:
    if report.get("experiment") != "I01-cmos-particle-detector-calibration":
        return None, "not an I01 CMOS calibration"
    if not report.get("hardware_available"):
        return False, "no real capped-sensor dark frames were available; hardware-null recorded"
    analysis = report.get("analysis") or {}
    evidence = report.get("input_evidence") or []
    shape = analysis.get("shape") or []
    enough = len(shape) == 3 and int(shape[0]) >= 16
    noise = float(analysis.get("temporal_noise_sigma", 0)) > 0
    hashes = bool(evidence) and all(len(str(x.get("sha256", ""))) == 64 for x in evidence)
    ok = bool(enough and noise and hashes)
    return ok, (
        f"CMOS dark stack: {shape[0] if shape else 0} frames, "
        f"noise σ={analysis.get('temporal_noise_sigma', 0):.3g}, "
        f"{analysis.get('hot_pixel_count', 0)} persistent hot pixels, "
        f"{analysis.get('track_candidate_count', 0)} transient track-like components — " +
        ("instrument calibration operational" if ok else "instrument calibration incomplete")
    )


def check_controls(report: dict) -> tuple[bool | None, str]:
    """Grade a published-controls report: cross-updater agreement + a null that must fail.

    Returns ``None`` unless this is a controls report. Otherwise grades two
    independent probes (a receipt, not prose):

    * **Cross-updater agreement** (positive control): every ``controls`` entry
      compares an observable measured by two independent correct algorithms
      (single-spin Metropolis vs single-cluster Wolff). Each must agree within the
      entry's own ``tol`` — two updaters, one number. A silently broken updater
      makes ``delta`` blow past ``tol`` and this fails.
    * **Null-coupling baseline** (negative control): with ``J=0`` there is no
      transition, so χ(T) must be flat — its peak/median prominence stays below
      ``ratio_max`` (a real critical peak is many times its baseline; a flat noisy
      1/T curve is ≈1×). The control's job is to **fail** the "there is a T_c peak"
      gate; PASS here means that failure was reproduced — proving M01's peak is
      physics, not an artifact the analysis manufactures from noise. (Prominence,
      not the noisy argmax *location*, is the discriminator: a flat curve's argmax
      wanders, but its peak never towers over its baseline.)
    """
    if report.get("experiment") != "CTRL-published-controls":
        return None, "not a published-controls report"
    entries = report.get("controls") or []
    null = report.get("null_control") or {}
    if len(entries) < 2 or not null:
        return None, "controls report missing cross-updater entries or the null control"

    parts: list[str] = []
    all_ok = True
    for e in entries:
        delta, tol = e.get("delta"), e.get("tol")
        if delta is None or tol is None:
            continue
        ok = delta <= tol
        all_ok = all_ok and ok
        parts.append(
            f"{e.get('observable')}@T={e.get('T'):.1f}: |Δ|={delta:.3f}≤{tol}"
            + ("" if ok else " ✗")
        )

    # The negative control must NOT show a prominent peak: a flat χ has a peak/median
    # ratio near 1, while a genuine critical peak towers many× over its baseline. If
    # the null grew a prominent peak, the pipeline is manufacturing one.
    ratio = null.get("peak_to_median_ratio")
    ratio_max = null.get("ratio_max")
    null_flat = ratio is not None and ratio_max is not None and ratio <= ratio_max
    all_ok = all_ok and null_flat
    null_str = (f"J=0 null χ flat (peak/median={ratio:.2f}≤{ratio_max})"
                if ratio is not None else "J=0 null missing χ")

    detail = (
        "cross-updater [" + "; ".join(parts) + "] · " + null_str + " — "
        + ("two independent updaters agree and the J=0 null shows no peak — the M01 "
           "transition is physics, not an analysis artifact"
           if all_ok else
           "a control failed: the updaters disagree or the J=0 null grew a spurious peak")
    )
    return all_ok, detail


# milestone id → check. Add entries as milestones land; the rest report
# "unchecked" so the gap is visible rather than silently assumed.
CHECKS = {"M01": check_m01, "M02": check_m02, "M03": check_m03,
          "M04": check_m04, "M05": check_m05, "M06": check_m06,
          "M07": check_m07, "M08": check_m08, "M09": check_m09,
          "M10": check_m10, "M11": check_m11, "M12": check_m12,
          "M13": check_m13, "M14": check_m14, "M15": check_m15,
          "M16": check_m16, "M17": check_m17, "C01": check_c01, "A01": check_a01,
          "I01": check_i01, "CTRL": check_controls}


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
