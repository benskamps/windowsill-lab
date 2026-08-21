"""The shape of the dip, and what the duration alone forbids.

A05 detects with a box: BLS finds a period, a phase and a mean depth. A box is
the right detector and the wrong model, and everything it throws away is
diagnostic:

* **Duration.** ``T14/P`` bounds the host's mean density with no catalogue at
  all (:func:`density_ceiling`). That matters because ``a05_physical``'s radius
  gate DISABLES itself when the TIC has no ``RADIUS`` — and a star with no
  catalogue radius is exactly the faint, blended, poorly-characterised object
  most likely to be hiding a false positive. TIC 77044472 had no radius, no
  Teff and no logg; the gate that should have sized its companion simply never
  ran. The density ceiling gives a floor on ``R*`` that needs nothing but the
  fold.
* **Ingress shape.** A planet crossing a limb-darkened disc makes a flat-
  bottomed U; a grazing stellar companion makes a V. The oldest EB
  discriminator there is, and a box cannot express it
  (:func:`fit_transit` returns ``v_ness``).
* **Impact parameter.** ``b`` is degenerate with depth in a box fit and is the
  difference between a 1.2 R_Jup planet and a grazing M dwarf.

### The density ceiling, and why it is a ceiling

For a companion of radius ratio ``k`` on a circular orbit::

    T14 = (P / pi) * sqrt((1 + k)^2 - b^2) / (a/R*)

Solving at ``b = 0`` gives the MAXIMUM ``a/R*`` consistent with the observed
duration, since any ``b > 0`` needs a smaller ``a/R*`` to last as long. With
Kepler's third law::

    rho* = 3 pi / (G P^2) * (a/R*)^3

``rho*`` inherits that maximum: **any real impact parameter makes the host less
dense than this number, never more.**

The ``(1 + k)`` is load-bearing and was missing from the first version of this
module. Validated against WASP-18 (k = 0.10, published host density
0.873 g/cm3): with the term the ceiling is 1.08 g/cm3 and holds; without it,
0.80 — and the true host violates its own bound. For a DEEP eclipse the error
is much worse, because ``k`` is large and the term enters cubed.

Applied to TIC 77044472 (``T14/P = 0.0375``, k = 0.24) the ceiling is
~3.1 g/cm3. That excludes M dwarfs but leaves K dwarfs standing, so the
implied companion is ~1.7 R_Jup and **this gate does not refute that target**.
An earlier pass here claimed the opposite — that the ceiling forced a G-type
host and a stellar companion — on the strength of the missing ``(1+k)``. It
did not. The catalogue crosscheck carried that verdict (see :mod:`lab.a05_sky`,
and the 2026-08-20 investigation); a gate should not be credited with a kill it
did not make.
"""
from __future__ import annotations

import math

import numpy as np

#: G in SI, and solar reference values.
G_SI = 6.67430e-11
R_SUN_M = 6.957e8
M_SUN_KG = 1.98892e30
#: Solar mean density in g/cm^3.
RHO_SUN_CGS = 1.408

#: A coarse main-sequence radius/mass grid, densest first. Used ONLY to turn a
#: density ceiling into a radius floor. Values are textbook dwarf sequence and
#: are not claimed to better than ~10 %; the gate that consumes them is
#: conservative in the direction of refusing to refute.
MAIN_SEQUENCE = (
    # (R/Rsun, M/Msun)
    (0.15, 0.12), (0.27, 0.25), (0.50, 0.47), (0.62, 0.60), (0.72, 0.70),
    (0.85, 0.88), (0.95, 0.93), (1.00, 1.00), (1.10, 1.05), (1.40, 1.35),
    (1.70, 1.60), (2.40, 2.90),
)

#: Fraction of the eclipse depth used to define first/fourth contact when
#: measuring T14 off a binned fold. 5 % of depth is shallow enough to catch
#: ingress and deep enough to stay out of the noise on a faint target.
CONTACT_FRACTION = 0.05

#: Bins across the fold for the duration measurement.
FOLD_BINS = 400

#: Quadratic limb-darkening coefficients used when no better estimate exists.
#: Solar-ish values in the TESS band; the fit is not sensitive to them at the
#: precision this pipeline works to, and they are reported with the result so a
#: reader can see what was assumed.
DEFAULT_LIMB_DARKENING = (0.35, 0.23)

#: Grid resolution for the transit fit. Coarse-to-fine, numpy only.
FIT_K_GRID = 24
FIT_B_GRID = 18
FIT_AR_GRID = 16

#: The fit runs against the BINNED fold, not raw cadences. Two reasons: a
#: 4608-point grid over ~20k cadences is minutes of numpy for a shape question,
#: and the per-bin median is the estimator the rest of A05 already trusts. The
#: bins inside the transit window are what constrain the shape, so the count is
#: set by how many land there rather than by the fold.
FIT_BINS = 600

#: Above this the trough is called V-shaped — grazing/stellar rather than a
#: flat-bottomed planetary transit. ``v_ness`` is the ingress+egress share of
#: T14, which for a planet is ~2k/(1+k) and for a grazing body approaches 1.
V_NESS_GRAZING = 0.75

#: A running-median detrend whose window is not long compared with the period
#: does not flatten the star — it eats the transit. Measured on WASP-18 b
#: (P = 0.941 d) with the pipeline's 0.5 d window: k inflates 0.101 -> 0.161,
#: b rails 0.45 -> 0.98, v_ness 0.22 -> 1.00, and a confirmed planet is
#: reported ``grazing-or-v-shaped``. Undetrended, the same fit returns k within
#: 3.3 % of the published value. Shape work must therefore declare its detrend,
#: and any window below this multiple of the period is flagged, not trusted.
DETREND_MIN_WINDOW_PERIODS = 3.0


def detrend_safe(period_days: float, window_days: float | None) -> dict:
    """Is a running-median window long enough to leave this transit alone?

    ``None`` window means undetrended, which is always safe for shape.
    """
    if window_days is None:
        return {"safe": True, "ratio": None, "reason": "undetrended"}
    try:
        P, w = float(period_days), float(window_days)
    except (TypeError, ValueError):
        return {"safe": False, "ratio": None, "reason": "no-inputs"}
    if not (P > 0 and w > 0):
        return {"safe": False, "ratio": None, "reason": "inputs-out-of-range"}
    ratio = w / P
    ok = ratio >= DETREND_MIN_WINDOW_PERIODS or ratio <= 0.05
    return {"safe": bool(ok), "ratio": float(ratio),
            "reason": None if ok else "detrend-window-comparable-to-period"}


def fold_profile(t: np.ndarray, f: np.ndarray, period: float,
                 bins: int = FOLD_BINS) -> tuple[np.ndarray, float, float]:
    """Median-binned phase fold, rolled so the deepest bin sits at the centre.

    Returns ``(profile, baseline, depth)``. ``profile`` has ``bins`` entries
    covering one period; NaN where a bin caught too few cadences.
    """
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    ph = ((t - t[0]) / float(period)) % 1.0
    idx = np.clip((ph * bins).astype(int), 0, bins - 1)
    prof = np.array([np.median(f[idx == b]) if int((idx == b).sum()) > 2
                     else np.nan for b in range(bins)])
    if not np.any(np.isfinite(prof)):
        return prof, float("nan"), float("nan")
    prof = np.roll(prof, bins // 2 - int(np.nanargmin(prof)))
    edge = max(1, bins // 6)
    baseline = float(np.nanmedian(np.concatenate([prof[:edge], prof[-edge:]])))
    depth = float(baseline - np.nanmin(prof))
    return prof, baseline, depth


def duration_fraction(t: np.ndarray, f: np.ndarray, period: float,
                      bins: int = FOLD_BINS) -> dict:
    """``T14/P`` from the fold, by first/fourth contact at :data:`CONTACT_FRACTION`."""
    prof, baseline, depth = fold_profile(t, f, period, bins)
    out = {"t14_frac": None, "t14_hours": None, "depth": None,
            "baseline": None, "reason": None}
    if not np.isfinite(depth) or depth <= 0:
        out["reason"] = "no-eclipse-in-fold"
        return out
    thr = baseline - CONTACT_FRACTION * depth
    c = bins // 2
    lo = c
    while lo > 0 and np.isfinite(prof[lo - 1]) and prof[lo - 1] < thr:
        lo -= 1
    hi = c
    while hi < bins - 1 and np.isfinite(prof[hi + 1]) and prof[hi + 1] < thr:
        hi += 1
    frac = (hi - lo + 1) / float(bins)
    out.update({"t14_frac": float(frac), "t14_hours": float(frac * period * 24.0),
                "depth": float(depth), "baseline": float(baseline)})
    if frac >= 0.5:
        out["reason"] = "duration-fills-fold"
    return out


def density_ceiling(period_days: float, t14_frac: float,
                    k: float = 0.0) -> dict:
    """Maximum mean stellar density consistent with this duration (``b = 0``).

    ``T14 = (P/pi) * sqrt((1+k)^2 - b^2) / (a/R*)``, so at ``b = 0``

        (a/R*)_max = (1 + k) / (pi * T14/P)

    **The ``(1+k)`` matters and dropping it breaks the ceiling.** For a deep
    eclipse ``k`` is not small: at k = 0.24 it inflates ``rho_max`` by
    ``1.24^3`` — a factor of 1.9 — and a ceiling that is too low excludes hosts
    that are in fact allowed. Validated on WASP-18 (k = 0.10, published host
    density 0.873 g/cm3): with the term, the ceiling lands at 1.08 and holds;
    without it, 0.80 and the true host violates its own bound.

    Pass ``k`` from the fit where available, or ``sqrt(depth)`` as the
    first-order estimate. ``k = 0`` reproduces the (unsafe) small-planet limit
    and is kept only as the explicit default for callers that have no depth.

    Returns ``{"rho_max_cgs", "a_over_r_max", "r_star_min_sun", "excluded"}``
    where ``excluded`` names the main-sequence rungs the ceiling forbids.
    """
    out = {"rho_max_cgs": None, "a_over_r_max": None, "r_star_min_sun": None,
           "excluded": [], "reason": None}
    try:
        P = float(period_days)
        frac = float(t14_frac)
    except (TypeError, ValueError):
        out["reason"] = "no-inputs"
        return out
    if not (P > 0) or not (0 < frac < 0.5):
        out["reason"] = "inputs-out-of-range"
        return out
    try:
        kk = max(0.0, float(k))
    except (TypeError, ValueError):
        kk = 0.0
    a_over_r = (1.0 + kk) / (math.pi * frac)
    rho_si = 3.0 * math.pi / (G_SI * (P * 86400.0) ** 2) * a_over_r ** 3
    rho_cgs = rho_si / 1000.0
    out["a_over_r_max"] = float(a_over_r)
    out["rho_max_cgs"] = float(rho_cgs)
    allowed = [(r, m) for (r, m) in MAIN_SEQUENCE
               if RHO_SUN_CGS * m / r ** 3 <= rho_cgs]
    out["excluded"] = [f"R={r:.2f}" for (r, m) in MAIN_SEQUENCE
                       if RHO_SUN_CGS * m / r ** 3 > rho_cgs]
    out["r_star_min_sun"] = float(min(r for r, _ in allowed)) if allowed else None
    if not allowed:
        out["reason"] = "no-main-sequence-host-allowed"
    return out


def _occultquad(z: np.ndarray, k: float, u1: float, u2: float) -> np.ndarray:
    """Quadratic limb-darkened transit, by direct numerical disc integration.

    Not Mandel & Agol's closed form — this integrates the limb-darkened
    intensity over the stellar disc on a fixed radial grid, which is a few
    hundred microseconds per call in numpy and free of the elliptic-integral
    branch bookkeeping that makes the analytic version easy to get subtly
    wrong. Accuracy is set by :data:`_DISC_RINGS` and is well past what a
    box-detected TESS signal can distinguish.
    """
    z = np.asarray(z, dtype=float)
    n = _DISC_RINGS
    # radial midpoints and their annulus areas on the unit disc
    r = (np.arange(n) + 0.5) / n
    dr = 1.0 / n
    mu = np.sqrt(np.clip(1.0 - r * r, 0.0, 1.0))
    inten = 1.0 - u1 * (1.0 - mu) - u2 * (1.0 - mu) ** 2
    area = 2.0 * math.pi * r * dr
    total = float((inten * area).sum())
    # overlap fraction of each annulus with the occulting disc of radius k
    # centred at separation z: analytic circle-annulus overlap per ring.
    zz = z[:, None]
    rr = r[None, :]
    d = np.abs(zz)
    # fraction of the ring's circumference covered by the occulter
    with np.errstate(invalid="ignore", divide="ignore"):
        cosarg = (d * d + rr * rr - k * k) / (2.0 * d * rr)
    cosarg = np.clip(cosarg, -1.0, 1.0)
    frac = np.arccos(cosarg) / math.pi
    frac = np.where(d <= 1e-12, np.where(rr <= k, 1.0, 0.0), frac)
    frac = np.where(d + rr <= k, 1.0, frac)          # ring fully inside
    frac = np.where(d >= rr + k, 0.0, frac)          # ring entirely outside
    frac = np.where(rr >= d + k, 0.0, frac)          # occulter inside ring hole
    blocked = (frac * inten[None, :] * area[None, :]).sum(axis=1)
    return 1.0 - blocked / total


#: Radial rings for the disc integration above.
_DISC_RINGS = 128


def transit_model(phase: np.ndarray, k: float, b: float, a_over_r: float,
                  u1: float, u2: float) -> np.ndarray:
    """Normalised flux vs orbital phase (0 at mid-transit, in units of period)."""
    ph = np.asarray(phase, dtype=float)
    theta = 2.0 * math.pi * ph
    # sky-projected separation in stellar radii
    z = np.sqrt((a_over_r * np.sin(theta)) ** 2 + (b * np.cos(theta)) ** 2)
    z = np.where(np.cos(theta) < 0, 1e9, z)          # secondary side: no transit
    return _occultquad(z, k, u1, u2)


def fit_transit(t: np.ndarray, f: np.ndarray, period: float,
                limb_darkening: tuple[float, float] = DEFAULT_LIMB_DARKENING,
                a_over_r_max: float | None = None) -> dict:
    """Coarse grid fit of a limb-darkened transit; returns shape discriminants.

    Reports ``k`` (Rp/R*), ``b``, ``a_over_r``, the reduced chi-square of the
    transit model and of the best box, and ``v_ness`` — the ingress+egress
    share of T14. A planet gives ``v_ness ~ 2k/(1+k)``; a grazing stellar
    companion pushes it toward 1 (:data:`V_NESS_GRAZING`).

    This is a SHAPE measurement for the dossier, not a gate. It grades nothing
    on its own: a box-detected, faint, blended signal rarely constrains ``b``,
    and a fit that reports ``b = 0.9 +- anything`` is decoration. What it is
    for is the V-vs-U question, which survives low signal-to-noise.
    """
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    prof, baseline, depth = fold_profile(t, f, period)
    out = {"k": None, "b": None, "a_over_r": None, "v_ness": None,
           "chi2_transit": None, "chi2_box": None, "verdict": None,
           "limb_darkening": [float(limb_darkening[0]), float(limb_darkening[1])],
           "reason": None}
    if not np.isfinite(depth) or depth <= 0:
        out["reason"] = "no-eclipse-in-fold"
        return out
    ph = ((t - t[0]) / float(period)) % 1.0
    # centre the fold on the eclipse using the binned minimum
    prof_raw = np.array([np.median(f[np.clip((ph * FOLD_BINS).astype(int), 0,
                                             FOLD_BINS - 1) == b_])
                         if int((np.clip((ph * FOLD_BINS).astype(int), 0,
                                         FOLD_BINS - 1) == b_).sum()) > 2
                         else np.nan for b_ in range(FOLD_BINS)])
    centre = (float(np.nanargmin(prof_raw)) + 0.5) / FOLD_BINS
    x = ((ph - centre + 0.5) % 1.0) - 0.5             # signed phase from mid
    y = f / baseline
    near = np.abs(x) < 0.12
    if int(near.sum()) < 40:
        out["reason"] = "too-few-in-window"
        return out
    # Bin the in-window fold: the shape lives in the bin medians, and a grid
    # search over raw cadences is minutes of numpy for a question the bins
    # already answer.
    edges = np.linspace(-0.12, 0.12, FIT_BINS + 1)
    which = np.digitize(x[near], edges) - 1
    xs_l, ys_l, ws_l = [], [], []
    yn = y[near]
    for bi in range(FIT_BINS):
        m = which == bi
        n_in = int(m.sum())
        if n_in < 2:
            continue
        xs_l.append(0.5 * (edges[bi] + edges[bi + 1]))
        ys_l.append(float(np.median(yn[m])))
        ws_l.append(n_in)
    if len(xs_l) < 20:
        out["reason"] = "too-few-bins"
        return out
    xs = np.asarray(xs_l)
    ys = np.asarray(ys_l)
    ws = np.asarray(ws_l, dtype=float)
    off = np.abs(xs) > 0.06
    sigma = float(1.4826 * np.median(np.abs(ys[off] - np.median(ys[off])))) if off.sum() > 3 else 0.0
    if not (sigma > 0):
        sigma = float(np.std(ys)) or 1e-6
    dur = duration_fraction(t, f, period)
    frac = dur["t14_frac"]
    if not frac or not (0 < frac < 0.5):
        out["reason"] = "no-duration"
        return out
    # a/R* is not a free parameter: the duration measures it, given (k, b).
    #     T14/P = sqrt((1+k)^2 - b^2) / (pi * a/R*)
    # Fitting it free made the search rail at the grid edge and report
    # b = 0.89 / v_ness = 1.0 for WASP-18 b — a "grazing" verdict on a
    # confirmed planet. Constraining it removes the k-b-a/R* degeneracy that
    # a box-detected signal cannot break on its own.
    # k is NOT bounded by sqrt(depth). That identity holds for a central
    # transit; a grazing body hides most of its disc off the limb, so its
    # depth is far below k^2 and a grid anchored to sqrt(depth) cannot reach
    # it. Anchoring it there made the fit unable to express the grazing case
    # `v_ness` exists to catch.
    ks = np.linspace(max(1e-3, 0.5 * math.sqrt(depth)),
                     min(0.85, max(3.0 * math.sqrt(depth), 0.35)), FIT_K_GRID)
    best = None
    for k in ks:
        # b runs to just short of 1+k, not to a fixed 0.98: a GRAZING body has
        # b > 1-k and can sit past 1. A grid capped below that cannot express
        # the very configuration `v_ness` exists to detect, and quietly
        # returns a shallow-looking best fit instead.
        bs = np.linspace(0.0, (1.0 + k) * (1.0 - 1e-6), FIT_B_GRID)
        for b in bs:
            ar = math.sqrt((1.0 + k) ** 2 - b * b) / (math.pi * frac)
            if ar <= 1.5:
                continue
            m = transit_model(xs, float(k), float(b), float(ar),
                              limb_darkening[0], limb_darkening[1])
            chi2 = float(np.sum(ws * (ys - m) ** 2)) / (sigma * sigma)
            if best is None or chi2 < best[0]:
                best = (chi2, float(k), float(b), float(ar))
    if best is None:
        out["reason"] = "no-admissible-model"
        return out
    chi2, k, b, ar = best
    dof = max(1, int(ws.sum()) - 3)
    # best box, same window: depth d over the fitted duration
    half = 0.5 * (dur["t14_frac"] or 0.05)
    box = np.where(np.abs(xs) <= half, 1.0 - depth / baseline, 1.0)
    chi2_box = float(np.sum(ws * (ys - box) ** 2)) / (sigma * sigma)
    # ingress share of the total duration, from the fitted geometry
    denom = math.sqrt(max(1e-9, (1.0 + k) ** 2 - b * b))
    t_full = math.sqrt(max(0.0, (1.0 - k) ** 2 - b * b))
    v_ness = float(1.0 - t_full / denom) if denom > 0 else 1.0
    out.update({"k": k, "b": b, "a_over_r": ar, "v_ness": v_ness,
                "chi2_transit": chi2 / dof, "chi2_box": chi2_box / dof,
                "r_p_over_r_star": k})
    if v_ness >= V_NESS_GRAZING:
        out["verdict"] = "grazing-or-v-shaped"
    return out
