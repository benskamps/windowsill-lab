"""A07 — Galilean clockwork: Kepler's third law and the Laplace resonance,
re-derived from JPL Horizons ephemerides.

Galileo found the moons in 1610; Kepler's third law bound their periods to
their orbits; Laplace showed in 1805 that Io, Europa and Ganymede are locked
in a three-body resonance so exact that ``n_Io - 3 n_Europa + 2 n_Ganymede``
librates about zero. This runner pulls jovicentric state vectors for the four
moons from the Horizons API (free, keyless), recovers each sidereal period
from the slope of the unwrapped orbital longitude, and grades three claims:

1. each recovered period matches the published sidereal period;
2. ``T^2 / a^3`` is the same number for all four moons — Kepler III — and the
   implied ``GM_Jupiter`` matches the JPL value;
3. the Laplace relation closes: ``|n1 - 3 n2 + 2 n3| / n1`` is consistent
   with zero at this pipeline's precision — with Callisto, deliberately, NOT
   in the resonance, riding along as the outsider that proves the relation
   is special and not an artifact of the method.

Claim boundary (the A03 discipline): this measures the CONSISTENCY of the
Horizons ephemeris with Kepler's law and the Laplace relation as recovered by
this pipeline. Horizons serves the world's best fitted solar-system model, so
this is a calibration against that model — not an independent observation of
Jupiter. What is genuinely measured here is that THIS pipeline's fetching,
parsing, plane-finding and frequency recovery reproduce celestial mechanics
end to end, at stated tolerances, from bytes it can re-derive offline.

Network doctrine is A01's, reused rather than re-implemented: bounded
retries, deadlines, and "an outage answers nothing" — a fetch that fails
raises ``A01NetworkError`` and no report is written. Every raw response is
cached and pinned by SHA-256 so ``check_a07`` can re-derive the physics with
the network unplugged.

The observation window is FIXED (2026-01-01 → 2026-05-01, 1 h cadence) so a
rerun asks Horizons the identical question and the receipt is comparable
across runs; 120 days spans ~68 Io orbits, which is what makes a phase-slope
period good to ~1e-5 while a bare FFT of the same window would stop at ~1%.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import a01
from .labhome import CACHE as LAB_CACHE

CACHE_DIR = LAB_CACHE / "a07"

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

#: The fixed window (TDB dates handed to Horizons verbatim).
START, STOP, STEP = "2026-01-01", "2026-05-01", "1h"

#: Jovicentric: Jupiter body center, ecliptic reference plane, km-s units.
CENTER, REF_PLANE, OUT_UNITS = "500@599", "ECLIPTIC", "KM-S"

MOONS = {"501": "Io", "502": "Europa", "503": "Ganymede", "504": "Callisto"}
RESONANT = ("501", "502", "503")   # the Laplace trio; Callisto is the outsider

#: Published sidereal orbital periods, days. Hand-cited (the Horizons object
#: header quotes Io's period only as "~1.77 d", too coarse to grade against):
#: JPL SSD Planetary Satellite Mean Orbital Parameters,
#: https://ssd.jpl.nasa.gov/sats/elem/ (mean elements w.r.t. local Laplace
#: planes), retrieved 2026-08-22. The receipt carries this citation.
PUBLISHED_PERIOD_DAYS = {
    "501": 1.769137786,
    "502": 3.551181041,
    "503": 7.154552960,
    "504": 16.689018400,
}
PUBLISHED_SOURCE = ("JPL SSD Planetary Satellite Mean Orbital Parameters, "
                    "https://ssd.jpl.nasa.gov/sats/elem/ (retrieved 2026-08-22)")

#: GM of Jupiter (the planet alone, excluding the satellite system),
#: km^3 s^-2 — JPL/IAU current best estimate as served with the Horizons
#: object data (Jupiter GM 126,686,531.9). A moon's jovicentric orbit is
#: governed by GM_Jupiter + GM_moon; the moon terms are <= 0.008% (Ganymede)
#: and are absorbed by the tolerance rather than modeled.
GM_JUPITER_KM3_S2 = 126686531.9
GM_SOURCE = ("Jupiter GM 126686531.9 km^3 s^-2 — JPL Horizons Jupiter "
             "object data / JUP365 solution (planet alone, satellites "
             "excluded)")

#: Tolerances, each with its argument:
#: * period: the phase-slope over >= 7 orbits of the slowest moon recovers a
#:   mean motion to ~1e-5 relative; the published MEAN elements differ from a
#:   120-day osculating fit by resonant librations and precession at up to a
#:   few 1e-5 — 5e-4 relative is an order of magnitude of headroom while
#:   still refusing any wrong-moon / wrong-frame / aliasing failure outright.
PERIOD_RTOL = 5e-4
#: * Kepler spread and GM: ``a`` is taken as the mean jovicentric distance,
#:   which differs from the mean-element semi-major axis at O(e^2) ~ 1e-4,
#:   and Jupiter's J2 shifts the effective a^3/T^2 by ~4e-4 at Io — 1%
#:   swallows both while a wrong orbit misses by far more.
KEPLER_SPREAD_TOL = 0.01
GM_RTOL = 0.01
#: * Laplace closure: with each n good to ~1e-5 relative, the combination is
#:   good to a few 1e-5 of n_Io; 1e-3 is conservative and still ~250x smaller
#:   than the same combination evaluated with Callisto substituted in.
LAPLACE_TOL = 1e-3


class A07ParseError(RuntimeError):
    """The Horizons response did not carry the table it always carries."""


# ------------------------------------------------------------------ fetch --

def _query(moon: str) -> dict:
    return {
        "format": "text", "COMMAND": f"'{moon}'", "OBJ_DATA": "'YES'",
        "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'VECTORS'",
        "CENTER": f"'{CENTER}'", "START_TIME": f"'{START}'",
        "STOP_TIME": f"'{STOP}'", "STEP_SIZE": f"'{STEP}'",
        "VEC_TABLE": "'2'", "REF_PLANE": f"'{REF_PLANE}'",
        "OUT_UNITS": f"'{OUT_UNITS}'", "CSV_FORMAT": "'YES'",
    }


def cache_basename(moon: str) -> str:
    return f"horizons-{moon}-{START}-{STOP}-{STEP}.txt"


def fetch_vectors(moon: str, cache_dir: Path = CACHE_DIR,
                  deadline: float | None = None) -> tuple[bytes, dict]:
    """Raw Horizons response for one moon, cached and pinned by SHA-256.

    A cache hit never touches the network (the fixed window makes the
    request identity a pure function of the moon id). A miss goes through
    ``a01._request`` — A01's bounded-retry, deadline-aware transport — so an
    outage raises ``A01NetworkError`` and no result is fabricated.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / cache_basename(moon)
    if path.exists():
        blob = path.read_bytes()
    else:
        url = HORIZONS_URL + "?" + urllib.parse.urlencode(_query(moon))
        blob = a01._request(url, deadline=deadline)
        path.write_bytes(blob)
    return blob, {"file": path.name,
                  "sha256": hashlib.sha256(blob).hexdigest()}


# ------------------------------------------------------------------ parse --

def parse_vectors(text: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(t_days, r_km[n,3], v_kms[n,3]) from a CSV VECTORS response.

    Only the ``$$SOE``..``$$EOE`` table is trusted for numbers; a response
    without both markers is a structural failure, raised not guessed.
    """
    lines = text.splitlines()
    try:
        lo = next(i for i, s in enumerate(lines) if s.strip() == "$$SOE")
        hi = next(i for i, s in enumerate(lines) if s.strip() == "$$EOE")
    except StopIteration as exc:
        raise A07ParseError("Horizons response carries no $$SOE/$$EOE table "
                            "(API error text instead of an ephemeris?)") from exc
    t, r, v = [], [], []
    for row in lines[lo + 1:hi]:
        parts = [p.strip() for p in row.split(",")]
        if len(parts) < 8:
            raise A07ParseError(f"vector row with {len(parts)} fields: {row[:80]}")
        t.append(float(parts[0]))                       # JD TDB
        r.append([float(parts[2]), float(parts[3]), float(parts[4])])
        v.append([float(parts[5]), float(parts[6]), float(parts[7])])
    if len(t) < 100:
        raise A07ParseError(f"only {len(t)} ephemeris rows — window truncated")
    return (np.asarray(t, dtype=float),
            np.asarray(r, dtype=float), np.asarray(v, dtype=float))


# ---------------------------------------------------------------- analysis --

def mean_motion(t_jd: np.ndarray, r: np.ndarray,
                v: np.ndarray) -> dict:
    """Sidereal mean motion from the slope of the unwrapped orbital longitude.

    The orbit plane is taken from the mean specific angular momentum
    ``h = <r x v>`` — per moon, so the recovery is frame-agnostic (ecliptic
    in, orbit plane out). The longitude of ``r`` projected onto that plane,
    unwrapped, is a near-perfect straight line over 120 days; its
    least-squares slope is the mean motion. The quoted uncertainty is the
    fit's own slope error — honest about the ephemeris's smoothness, which
    is what makes it tiny.
    """
    h = np.cross(r, v).mean(axis=0)
    zhat = h / np.linalg.norm(h)
    # In-plane basis: x-axis from the first radius vector's in-plane part.
    x0 = r[0] - np.dot(r[0], zhat) * zhat
    xhat = x0 / np.linalg.norm(x0)
    yhat = np.cross(zhat, xhat)
    theta = np.unwrap(np.arctan2(r @ yhat, r @ xhat))
    tt = t_jd - t_jd[0]
    A = np.vstack([tt, np.ones_like(tt)]).T
    (slope, intercept), residuals, *_ = np.linalg.lstsq(A, theta, rcond=None)
    n_dof = len(tt) - 2
    rms = float(np.sqrt(residuals[0] / n_dof)) if residuals.size else 0.0
    # Standard slope error of an unweighted linear fit.
    sxx = float(np.sum((tt - tt.mean()) ** 2))
    slope_err = rms / np.sqrt(sxx) if sxx > 0 else float("nan")
    period = 2.0 * np.pi / slope
    return {
        "n_rad_per_day": float(slope),
        "n_err_rad_per_day": float(slope_err),
        "period_days": float(period),
        "period_err_days": float(period * slope_err / slope),
        "a_km": float(np.linalg.norm(r, axis=1).mean()),
        "fit_rms_rad": rms,
        "n_samples": int(len(tt)),
        "span_days": float(tt[-1]),
    }


def grade(per_moon: dict[str, dict]) -> dict:
    """The three graded claims, each carrying its numbers and its verdict."""
    periods = {}
    for moon, m in per_moon.items():
        ref = PUBLISHED_PERIOD_DAYS[moon]
        rel = abs(m["period_days"] / ref - 1.0)
        periods[moon] = {
            "name": MOONS[moon],
            "recovered_days": m["period_days"],
            "published_days": ref,
            "rel_error": rel,
            "pass": bool(rel <= PERIOD_RTOL),
        }
    gm = {moon: 4.0 * np.pi ** 2 * (m["a_km"] ** 3)
          / ((m["period_days"] * 86400.0) ** 2)
          for moon, m in per_moon.items()}
    gm_mean = float(np.mean(list(gm.values())))
    spread = max(abs(x / gm_mean - 1.0) for x in gm.values())
    gm_rel = abs(gm_mean / GM_JUPITER_KM3_S2 - 1.0)
    n = {moon: per_moon[moon]["n_rad_per_day"] for moon in per_moon}
    laplace = abs(n["501"] - 3.0 * n["502"] + 2.0 * n["503"]) / n["501"]
    # The outsider control: the same combination with Callisto in Ganymede's
    # seat must NOT close — the resonance is a property of the trio, not of
    # the arithmetic.
    laplace_callisto = abs(n["501"] - 3.0 * n["502"] + 2.0 * n["504"]) / n["501"]
    return {
        "periods": periods,
        "kepler": {
            "gm_per_moon_km3_s2": {MOONS[k]: float(v) for k, v in gm.items()},
            "gm_mean_km3_s2": gm_mean,
            "max_fractional_spread": float(spread),
            "spread_tol": KEPLER_SPREAD_TOL,
            "gm_published_km3_s2": GM_JUPITER_KM3_S2,
            "gm_rel_error": float(gm_rel),
            "gm_rtol": GM_RTOL,
            "gm_source": GM_SOURCE,
            "pass": bool(spread <= KEPLER_SPREAD_TOL and gm_rel <= GM_RTOL),
        },
        "laplace": {
            "residual_rel": float(laplace),
            "tol": LAPLACE_TOL,
            "callisto_substituted_rel": float(laplace_callisto),
            "pass": bool(laplace <= LAPLACE_TOL
                         and laplace_callisto > 10.0 * LAPLACE_TOL),
        },
    }


# -------------------------------------------------------------------- run --

@dataclass
class A07Result:
    per_moon: dict = field(default_factory=dict)
    grades: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)
    wall_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return (all(p["pass"] for p in self.grades["periods"].values())
                and self.grades["kepler"]["pass"]
                and self.grades["laplace"]["pass"])


def run_a07(cache_dir: Path = CACHE_DIR, deadline: float | None = None,
            phase=None) -> A07Result:
    t0 = time.time()
    result = A07Result()
    for moon, name in MOONS.items():
        blob, pin = fetch_vectors(moon, cache_dir=cache_dir, deadline=deadline)
        t, r, v = parse_vectors(blob.decode("utf-8", errors="replace"))
        m = mean_motion(t, r, v)
        result.per_moon[moon] = m
        result.cache[moon] = pin
        if phase:
            phase("moon", {"name": name, **m})
    result.grades = grade(result.per_moon)
    result.wall_seconds = time.time() - t0
    return result


def to_report(result: A07Result) -> dict:
    g = result.grades
    lap = g["laplace"]
    headline = (
        f"four moons, one law: T^2/a^3 spread "
        f"{g['kepler']['max_fractional_spread']:.2e}, GM_Jupiter "
        f"{g['kepler']['gm_mean_km3_s2']:.4g} vs {GM_JUPITER_KM3_S2:.4g} "
        f"km^3/s^2; Laplace residual {lap['residual_rel']:.1e} "
        f"(Callisto substituted: {lap['callisto_substituted_rel']:.2f})")
    return {
        "experiment": "A07-galilean-clockwork",
        "schema": 1,
        "status": "pass" if result.passed else "null",
        "headline": headline,
        "window": {"start": START, "stop": STOP, "step": STEP,
                   "center": CENTER, "ref_plane": REF_PLANE,
                   "units": OUT_UNITS},
        "per_moon": {MOONS[k]: v for k, v in result.per_moon.items()},
        "grades": g,
        "published_period_source": PUBLISHED_SOURCE,
        "cache": {MOONS[k]: v for k, v in result.cache.items()},
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "Horizons serves a fitted solar-system model, so every number "
            "here is a consistency check of THIS pipeline (fetch, parse, "
            "plane recovery, phase-slope frequency estimation) against the "
            "world's best ephemeris — a calibration, not an independent "
            "observation of Jupiter. The moon's own GM (<= 0.008% of "
            "Jupiter's) is absorbed by the stated tolerance, 'a' is the "
            "mean jovicentric distance (exact only for e = 0), and the "
            "published periods are MEAN elements while the fit is a "
            "120-day osculating slope — all three approximations are "
            "inside the graded tolerances, and the tolerances say so."),
    }
