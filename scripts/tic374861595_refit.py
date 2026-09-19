#!/usr/bin/env python3
"""Limb-darkened refit + Gaia-anchored host radius for TIC 374861595.

The CTOI package (``docs/submissions/TIC374861595-CTOI.md``) names exactly two
upgrades that stand between it and something a referee would accept, and both
are named twice — once in §2 ("a paper wants ``batman``/``juliet`` with a
Gaia-anchored R★") and once in §5b, after SPOC's own multi-sector Data
Validation fit landed and disagreed with the lab's trapezoid by 25 % in depth
and 37 % in duration. This script is those two upgrades:

**(a) A physical transit model instead of a trapezoid.** The lab's numbers came
from a trapezoid fit in numpy (``scripts/ctoi_ephemeris.py``). A trapezoid has
no limb darkening, so it under-reads depth and over-reads duration on a
round-bottomed transit; §2 predicted the direction and §5b measured the size.
It also cannot fit an impact parameter, which is the whole argument here: SPOC
prefers ``b = 0.90``, i.e. grazing, and a grazing geometry is where Rp/R★ goes
soft. Fitting a real Mandel & Agol (2002) occultation with Claret (2000)
limb darkening gives ``(k, a/R★, b)`` with their real covariance instead of a
shape parameter the trapezoid never had.

**(b) A stellar radius derived here rather than copied.** §1 quotes TIC v8's
0.616 R☉; §5d notes Gaia GSP-Phot says 0.80 R☉ and that GSP-Phot is unreliable
for M dwarfs. Neither is a number this repo derived. The Mann et al. (2015)
M_K → R★ and Mann et al. (2019) M_K → M★ relations are two lines of algebra on
a 2MASS magnitude and a Gaia parallax, so there is no reason to cite a
catalogue for them. Deriving them here also makes the *density* comparison
honest, which is the one place the transit and the star can be checked against
each other without a radial velocity.

**Why the density comparison is the point.** The transit shape gives ρ★ on its
own, through ρ_circ = 3π/(G P²)·(a/R★)³ (Seager & Mallén-Ornelas 2003), with no
stellar model in it at all. The Mann relations give ρ★ from photometry and
parallax, with no light curve in it at all. If they disagree, something is
wrong: the orbit is eccentric, or the host radius is wrong, or the fit sat on
the wrong branch of the grazing degeneracy. §1 vs §5b already shows the lab's
trapezoid landing at ρ_circ = 6.2 g/cm³ and SPOC's fit at 2.3 g/cm³ — a factor
of 2.7 that nobody has reconciled. This script puts all three densities in one
table, in one unit, so the disagreement is at least legible.

A warning the reader should carry into §5b: the package's §1 quotes
"ρ★ = 2.57 g/cm³" for the catalogue and "1.64" for SPOC's fit, but M★/R★³ for
TIC's own (0.601 M☉, 0.616 R☉) is 2.57 *in solar units* — 3.62 g/cm³ — and
SPOC's a/R★ = 7.71 gives 2.31 g/cm³, which is 1.64 in solar units. Those two
numbers are solar units wearing a cgs label, while the same section's
"6.2 g/cm³" really is cgs. This script prints every density in both units for
that reason.

Running it
----------

    py -3.11 scripts/tic374861595_refit.py --selftest      # no network, no data
    py -3.11 scripts/tic374861595_refit.py                 # downloads via lightkurve
    py -3.11 scripts/tic374861595_refit.py --fits-dir C:\\lc\\374861595
    py -3.11 scripts/tic374861595_refit.py --errors mcmc --json refit.json

``--selftest`` is the gate: it injects a transit with known parameters into
synthetic noise, runs the complete fitting path on it, and fails loudly if the
recovered parameters miss the truth. It also checks the occultation model
against the closed-form uniform-source solution and the Mann relations against
hand-computed values. Nothing in it touches the network or the disk. Run it
before believing any number below it; a fitter nobody has fed a known answer
is indistinguishable from one wired to return the starting guess.

Dependencies
------------

numpy is required. Everything else is optional and the script says so at
startup: ``lightkurve`` (downloading), ``batman-package`` (faster and
independently-written transit model), ``emcee`` (MCMC errors), ``astropy``
(FITS reading, if ``lab.a01`` is not importable). With numpy alone and a
directory of FITS files, every path in here still runs.

Times
-----

SPOC's ``TIME`` column is BTJD = BJD_TDB − 2457000, and this script works in
BTJD throughout. Epochs are reported in both.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import warnings
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------- constants --

BTJD_OFFSET = 2457000.0

#: Newton's constant, cgs, and the solar mass/radius the density conversions
#: use. IAU 2015 nominal values; the choice matters at the 0.1 % level and the
#: numbers here are good to ~10 %, but a stated constant is a checkable one.
G_CGS = 6.67430e-8
MSUN_G = 1.98892e33
RSUN_CM = 6.957e10
#: ρ☉ = M☉ / (4/3 π R☉³) in g/cm³ — the factor that turns solar-unit densities
#: into cgs and back. 1.4097; the literature's "1.408" rounds a slightly
#: different R☉.
RHO_SUN_CGS = MSUN_G / (4.0 / 3.0 * math.pi * RSUN_CM**3)

#: SPOC multi-sector Data Validation, sectors 1–96, generated 2025-12-24,
#: pipeline spoc-5.0.125. Transcribed from
#: ``docs/submissions/TIC374861595-spoc-s1-s96-dvr.xml``, which is committed
#: beside the package. These are the STARTING GUESS for the fit below and the
#: comparison column in the summary — never an answer this script reports as
#: its own.
SPOC_DV = {
    "period_days": 1.9369484453819672,
    "period_err_days": 2.0902313e-07,
    "epoch_btjd": 2036.5479415409804,
    "epoch_err_days": 4.7113088e-05,
    "depth_ppm": 104602.85,
    "depth_err_ppm": 404.57,
    "duration_hours": 2.153350,
    "ingress_hours": 1.076675,
    "b": 0.9000290,
    "b_err": 0.1119763,
    "rp_rstar": 0.42987933,
    "rp_rstar_err": 0.07581938,
    "rstar_sun": 0.615867,
    "rstar_sun_err": 0.0186475,
    "teff_k": 3445.0,
    "teff_err_k": 157.0,
    "logg": 4.63786,
}

#: Claret (2000) four-parameter nonlinear limb-darkening coefficients for this
#: host in the TESS band, as SPOC's DV fit used them. Held FIXED by default:
#: five transit parameters already trade against each other on a grazing
#: geometry, and four more that only the limb's last few percent constrain will
#: wander wherever chi-squared is flattest. ``--free-ld`` frees them anyway.
CLARET_TESS = (0.6909416, 0.13755335, -0.028271813, -0.029731765)

#: The lab's own trapezoid result, from ``docs/submissions/
#: TIC374861595-ephemeris.json`` (3 sectors, 33 transits, numpy trapezoid).
#: The thing this script is replacing; kept for the comparison column.
LAB_TRAPEZOID = {
    "period_days": 1.9369092992603822,
    "period_err_days": 2.4707130374400595e-06,
    "epoch_btjd": 2172.136531197764,
    "epoch_err_days": 7.897620564147134e-05,
    "depth_ppm": 84140.02312581753,
    "depth_err_ppm": 372.27414243702094,
    "duration_hours": 1.5730945488435646,
    "duration_err_hours": 0.00444007006163089,
    "rp_rstar": 0.301,
    "b": 0.29,
    "a_rstar": 10.68,
    "n_transits": 33,
    "sectors": (30, 31, 35),
}

TIC = "374861595"

#: 2MASS J05542154-6407473 / Gaia DR3 4756470194913503104.
#:
#: HONESTY NOTE, because this default is the weakest number in the file: the
#: sandbox that wrote this script had no route to 2MASS or VizieR, so Ks here
#: is NOT read from the 2MASS point-source catalogue. It is back-derived from
#: the package's §5d, which states "Mann+2015 from M_K = 4.98 gives 0.616 R☉",
#: combined with the package's parallax — i.e. it reproduces the input TIC v8
#: used, not an independent measurement. It is right to about the precision the
#: package quotes M_K to (±0.01), which is ±0.3 % in R★ — small next to the
#: 2.89 % relation scatter, but it is still a derived default standing in for a
#: catalogue lookup. Pass --kmag with the real 2MASS Ks and its error before
#: putting any of this in a paper. The script prints a warning when it uses the
#: default.
DEFAULT_ABS_KMAG = 4.98      # package §5d; K is derived from this and the parallax
DEFAULT_KMAG_ERR = 0.025     # typical 2MASS Ks error at K~11.7; a placeholder
DEFAULT_PARALLAX_MAS = 4.47
DEFAULT_PARALLAX_ERR_MAS = 0.03

#: Mann et al. (2015), ApJ 804, 64 — Table 1 / Eq. 4, the metallicity-free
#: M_K → R★ relation:  R★/R☉ = a + b·M_K + c·M_K² .
#: Valid 4.6 < M_K < 9.8; quoted scatter 2.89 % in R★.
#:
#: **Cite the 2016 erratum, ApJ 819, 87, not the original article.** The journal
#: printed Tables 1-3 with press errors; the erratum reprinted them, and it is
#: the erratum's values that these constants match. Checked digit for digit by
#: ``scripts/mann_coefficients_check.py``. A paper that cites "Mann+2015 Table 1"
#: from the article as printed cites numbers that are not these.
MANN15_R_COEFFS = (1.9515, -0.3520, 0.01680)
MANN15_R_SCATTER = 0.0289
MANN15_MK_RANGE = (4.6, 9.8)

#: Mann et al. (2019), ApJ 871, 63 — Table 6, the n = 5, metallicity-free
#: M_K → M★ relation:  M★/M☉ = 10^( Σ_{i=0..5} a_i · (M_K − 7.5)^i ).
#: Valid 4.0 < M_K < 11.0; quoted scatter ~2–3 % in M★.
#: All six checked against the authors' own 400,000-sample posterior by
#: ``scripts/mann_coefficients_check.py`` (within 1.31 σ; −0.86 % in the mass at
#: this star's M_K). Prefer this relation over Mann+2015's mass row, which
#: disagrees by 6 % here and rests on model-derived rather than dynamical masses.
MANN19_M_COEFFS = (-0.642, -0.208, -8.43e-4, 7.87e-3, 1.42e-4, -2.13e-4)
MANN19_M_ZP = 7.5
MANN19_M_SCATTER = 0.030
MANN19_MK_RANGE = (4.0, 11.0)


class RefitError(RuntimeError):
    """Something the script refuses to paper over."""


# --------------------------------------------------- limb-darkening laws --


def claret_nonlinear_intensity(mu: np.ndarray, coeffs) -> np.ndarray:
    """I(μ)/I(1) for Claret (2000) four-parameter nonlinear limb darkening.

        I(μ)/I(1) = 1 − Σ_{j=1..4} c_j · (1 − μ^{j/2})

    μ = cos(angle between the line of sight and the surface normal) =
    sqrt(1 − r²) for a point at fractional stellar radius r.
    """
    c1, c2, c3, c4 = coeffs
    mu = np.asarray(mu, dtype=float)
    mu = np.clip(mu, 0.0, 1.0)
    return (1.0
            - c1 * (1.0 - mu**0.5)
            - c2 * (1.0 - mu)
            - c3 * (1.0 - mu**1.5)
            - c4 * (1.0 - mu**2))


def quadratic_intensity(mu: np.ndarray, coeffs) -> np.ndarray:
    """I(μ)/I(1) = 1 − u1(1−μ) − u2(1−μ)² — the usual quadratic law."""
    u1, u2 = coeffs
    mu = np.clip(np.asarray(mu, dtype=float), 0.0, 1.0)
    return 1.0 - u1 * (1.0 - mu) - u2 * (1.0 - mu) ** 2


def uniform_intensity(mu: np.ndarray, coeffs=()) -> np.ndarray:
    """I(μ)/I(1) = 1 — no limb darkening. Used as the exactness check."""
    return np.ones_like(np.asarray(mu, dtype=float))


LD_LAWS = {
    "nonlinear": (claret_nonlinear_intensity, 4),
    "quadratic": (quadratic_intensity, 2),
    "uniform": (uniform_intensity, 0),
}


def ld_norm_closed_form(law: str, coeffs) -> float:
    """∫ I dA over the disk, divided by π — in closed form where one exists.

    The disk-integrated flux is 2π ∫₀¹ I(μ) μ dμ = π·W, so W is what every
    occultation depth is divided by. Having it in closed form is not an
    optimisation: it is the thing :func:`_selftest_ld_norm` checks the
    quadrature against, and a quadrature nobody checked is a quadrature that
    can be silently wrong by a few percent at the limb.
    """
    if law == "uniform":
        return 1.0
    if law == "quadratic":
        u1, u2 = coeffs
        return 1.0 - u1 / 3.0 - u2 / 6.0
    if law == "nonlinear":
        # ∫₀¹ 2μ·μ^{j/2} dμ = 2/(j/2+2), so the j-th term contributes
        # −c_j·(1 − 2/(j/2+2)) = −c_j·(j/2)/(j/2+2).
        total = 1.0
        for j, c in enumerate(coeffs, start=1):
            h = j / 2.0
            total -= c * h / (h + 2.0)
        return float(total)
    raise RefitError(f"no closed-form normalisation for law {law!r}")


# ------------------------------------------------- the occultation model --


def _gauss_legendre(n: int):
    """Gauss–Legendre nodes/weights on [−1, 1]; cached by order."""
    key = int(n)
    cache = _gauss_legendre._cache
    if key not in cache:
        cache[key] = np.polynomial.legendre.leggauss(key)
    return cache[key]


_gauss_legendre._cache = {}


def uniform_occultation(z: np.ndarray, k: float) -> np.ndarray:
    """Mandel & Agol (2002) Eq. 1 — the uniform-source light curve, exactly.

    Closed form, no limb darkening. This exists so the general integrator
    below has something with a known answer to be compared against: set every
    limb-darkening coefficient to zero and the two must agree to quadrature
    precision. They are computed by completely different routes (analytic
    circle-circle overlap vs. a radial quadrature), so agreement is evidence.
    """
    z = np.abs(np.asarray(z, dtype=float))
    k = float(k)
    lam = np.zeros_like(z)
    if k <= 0:
        return 1.0 - lam

    total = z <= (k - 1.0)                         # star entirely covered
    full = (~total) & (z <= (1.0 - k))             # planet entirely on disk
    part = (~total) & (~full) & (z < (1.0 + k))    # partial overlap

    lam[total] = 1.0
    lam[full] = k * k
    if np.any(part):
        zp = z[part]
        k0 = np.arccos(np.clip((k * k + zp * zp - 1.0) / (2.0 * k * zp), -1.0, 1.0))
        k1 = np.arccos(np.clip((1.0 - k * k + zp * zp) / (2.0 * zp), -1.0, 1.0))
        inner = 4.0 * zp * zp - (1.0 + zp * zp - k * k) ** 2
        lam[part] = (k * k * k0 + k1 - 0.5 * np.sqrt(np.clip(inner, 0.0, None))) / math.pi
    return 1.0 - lam


def occultation_ld(z: np.ndarray, k: float, intensity, *, ng: int = 24) -> np.ndarray:
    """Relative flux for a dark disk of radius k over a limb-darkened star.

    Exact geometry, numerically-integrated intensity. The occulted flux is

        ΔF(z) = ∫ I(r) · 2 r · α(r, z, k) dr ,   α = half-angle of the arc of
                                                 the circle of radius r that
                                                 lies inside the planet disk

    with r running over [max(0, z−k), min(1, z+k)], and F = 1 − ΔF/(π·W).
    α is π where the whole circle is swallowed (r ≤ k − z), arccos((z²+r²−k²)
    /2zr) where it is partly swallowed, and 0 outside.

    HONESTY ABOUT WHAT THIS IS AND IS NOT. This is a *fallback* for machines
    without ``batman-package``, but it is not a cheap approximation: unlike the
    small-planet expansion, it makes no assumption about k, and unlike a
    pixel-grid integration its error is quadrature error, which is measurable.
    What it gives up is speed (a few hundred microseconds per z-grid rather
    than a few microseconds), analytic derivatives, and everything outside a
    circular orbit around a spherical, radially-symmetric star — no
    eccentricity, no oblateness, no gravity darkening, no spot crossings.
    Where batman is importable this script uses batman instead, and the
    selftest checks the two agree.

    The integration variable is s, with μ = s² and r = sqrt(1 − s⁴). That
    substitution is doing real work: the integrand in r has an infinite
    derivative at the limb (r → 1), which is exactly where a grazing transit
    like this one spends its whole time, and Gauss–Legendre in r converges
    slowly there. In s the Claret law's μ^{j/2} terms become plain powers of s
    and dr·2r absorbs the singularity: 2r dr = −4s³ ds. So

        ΔF(z) = ∫ 4 s³ I(s²) α(r(s)) ds ,

    smooth, with the integrand vanishing as s³ at the limb.
    """
    z = np.abs(np.asarray(z, dtype=float)).ravel()
    k = float(k)
    if k <= 0.0:
        return np.ones_like(z)

    r_lo = np.clip(z - k, 0.0, 1.0)
    r_hi = np.clip(z + k, 0.0, 1.0)
    # Breakpoint: below r = k − z the whole circle of radius r is inside the
    # planet disk (α = π). Above it, α is an arccos.
    r_mid = np.clip(k - z, r_lo, r_hi)

    def s_of_r(r):
        return np.power(np.clip(1.0 - r * r, 0.0, 1.0), 0.25)

    # s decreases as r increases, so the ordering flips.
    s_hi = s_of_r(r_lo)      # innermost radius  -> largest s (μ nearest 1)
    s_mid = s_of_r(r_mid)
    s_lo = s_of_r(r_hi)      # outermost radius  -> smallest s (μ nearest 0)

    nodes, weights = _gauss_legendre(ng)

    def segment(a, b, arc, sine=False):
        """∫_a^b 4 s³ I(s²) α ds, vectorised over z. `arc` gets (s, r).

        ``sine=True`` integrates over φ with s = mid + half·sin φ instead of
        over s directly. That is not a refinement, it is the difference
        between a converged integral and a wrong one: α(r) → 0 like
        sqrt(r − r_edge) at both ends of the partial-overlap segment (it is an
        arccos whose argument reaches ±1 there), and Gauss–Legendre on a
        square-root endpoint converges like ng^-3. Measured, the plain version
        was 1.4e-5 off the uniform-source closed form at ng = 24 — 14 ppm,
        which is a tenth of the depth precision this fit reports. The sine map
        turns sqrt(r − r_edge) into something linear in φ and the error drops
        below 1e-9.
        """
        a = np.asarray(a, dtype=float)[:, None]
        b = np.asarray(b, dtype=float)[:, None]
        half = 0.5 * (b - a)
        mid = 0.5 * (b + a)
        if sine:
            phi = 0.5 * math.pi * nodes[None, :]
            s = mid + half * np.sin(phi)
            jac = half * np.cos(phi) * (0.5 * math.pi)
        else:
            s = mid + half * nodes[None, :]
            jac = np.broadcast_to(half, s.shape)
        s = np.clip(s, 0.0, 1.0)
        r = np.sqrt(np.clip(1.0 - s**4, 0.0, 1.0))
        val = 4.0 * s**3 * intensity(s * s) * arc(s, r)
        return np.sum(val * jac * weights[None, :], axis=1)

    zc = z[:, None]

    def arc_full(s, r):
        return np.full_like(s, math.pi)

    def arc_partial(s, r):
        denom = 2.0 * zc * r
        with np.errstate(divide="ignore", invalid="ignore"):
            cosa = np.where(denom > 0.0,
                            (zc * zc + r * r - k * k) / np.where(denom > 0.0, denom, 1.0),
                            -1.0)
        # z == 0 is the exactly-central case: every circle with r < k is fully
        # inside, and the r_mid breakpoint has already routed those to arc_full,
        # so anything reaching here at z == 0 is outside the planet.
        cosa = np.where(zc > 0.0, cosa, 1.0)
        return np.arccos(np.clip(cosa, -1.0, 1.0))

    deficit = (segment(s_mid, s_hi, arc_full)
               + segment(s_lo, s_mid, arc_partial, sine=True))

    # ∫ I dA over the whole disk, by the same quadrature so that any residual
    # quadrature bias cancels in the ratio rather than showing up as a depth
    # error. (The closed form is used for the selftest cross-check.)
    a0 = np.zeros(1)
    b0 = np.ones(1)
    norm_nodes = 0.5 * (b0[:, None] + a0[:, None]) + 0.5 * (b0[:, None] - a0[:, None]) * nodes[None, :]
    norm = np.sum(4.0 * norm_nodes**3 * intensity(norm_nodes**2)
                  * math.pi * weights[None, :], axis=1) * 0.5
    flux = 1.0 - deficit / float(norm[0])
    return np.clip(flux, 0.0, None)


class OccultationTable:
    """F(z) on a z-grid, linearly interpolated — the reason this is fast enough.

    F(z) depends only on (k, limb darkening). It does NOT depend on period,
    epoch, a/R★ or b, which is what a fitter actually varies most. Building a
    grid once per k and interpolating onto tens of thousands of cadences turns
    a per-likelihood cost of ~10 ms into ~0.2 ms, which is the difference
    between a bootstrap that finishes and one that does not.

    The grid is densified around z = 1 − k and z = 1 + k, where F has corners
    (second contact and first contact). ``--exact`` skips this class entirely;
    the selftest asserts the two agree to better than 20 ppm, which is 0.02 %
    of this transit's 10 % depth.
    """

    def __init__(self, k: float, intensity, *, nz: int = 600, ng: int = 24):
        k = float(k)
        self.k = k
        edges = [0.0, 1.0 + k]
        grid = [np.linspace(0.0, 1.0 + k, nz)]
        for corner in (abs(1.0 - k), 1.0 + k):
            width = max(0.02 * k, 1e-4)
            grid.append(np.linspace(max(0.0, corner - width), corner + width, 201))
        z = np.unique(np.clip(np.concatenate(grid), edges[0], edges[1]))
        self.z = z
        self.f = occultation_ld(z, k, intensity, ng=ng)

    def __call__(self, z: np.ndarray) -> np.ndarray:
        z = np.abs(np.asarray(z, dtype=float))
        return np.interp(z, self.z, self.f, left=self.f[0], right=1.0)


def projected_separation(t, t0, period, a_rstar, b):
    """Sky-projected star–planet separation in stellar radii, circular orbit.

    Returns (z, in_front). With cos i = b/(a/R★),

        x = (a/R★)·sin θ ,  y = (a/R★)·cos θ·cos i ,  θ = 2π(t − t0)/P

    and z = sqrt(x² + y²). ``in_front`` is cos θ > 0 — without it the model
    puts a second, identical dip at phase 0.5, which is precisely the secondary
    eclipse the package spent §5c showing is absent.
    """
    a_rstar = float(a_rstar)
    cos_i = np.clip(float(b) / a_rstar, -1.0, 1.0)
    sin_i = math.sqrt(max(0.0, 1.0 - cos_i * cos_i))
    theta = 2.0 * math.pi * (np.asarray(t, dtype=float) - t0) / period
    st, ct = np.sin(theta), np.cos(theta)
    z = a_rstar * np.sqrt(st * st + (ct * cos_i) ** 2)
    return z, ct > 0.0, sin_i


class TransitModel:
    """Circular-orbit transit light curve. batman if present, numpy if not.

    ``backend`` is reported in the output on purpose: two people running this
    script on the same data with different packages installed are running
    different code, and the summary should say which.
    """

    def __init__(self, law: str, coeffs, *, backend: str = "auto",
                 exact: bool = False, nz: int = 600, ng: int = 24,
                 supersample: int = 1, exp_time_days: float = 120.0 / 86400.0):
        if law not in LD_LAWS:
            raise RefitError(f"unknown limb-darkening law {law!r}")
        self.law = law
        self.coeffs = tuple(float(c) for c in coeffs)
        self.exact = bool(exact)
        self.nz = int(nz)
        self.ng = int(ng)
        self.supersample = max(1, int(supersample))
        self.exp_time_days = float(exp_time_days)
        self._batman = None
        if backend in ("auto", "batman"):
            try:
                import batman  # noqa: F401
                self._batman = batman
            except Exception:
                if backend == "batman":
                    raise RefitError(
                        "--backend batman requested but `import batman` failed; "
                        "pip install batman-package")
        self.backend = "batman" if self._batman is not None else "numpy"

    # -- the intensity profile, as a closure the integrator can call ---------

    def intensity(self, mu):
        func, _ = LD_LAWS[self.law]
        return func(mu, self.coeffs)

    def with_coeffs(self, coeffs) -> "TransitModel":
        out = object.__new__(TransitModel)
        out.__dict__.update(self.__dict__)
        out.coeffs = tuple(float(c) for c in coeffs)
        return out

    # -- evaluation ---------------------------------------------------------

    def _flux_numpy(self, t, t0, period, k, a_rstar, b):
        z, in_front, _ = projected_separation(t, t0, period, a_rstar, b)
        out = np.ones_like(z)
        mask = in_front & (z < 1.0 + k)
        if not np.any(mask):
            return out
        if self.exact:
            out[mask] = occultation_ld(z[mask], k, self.intensity, ng=self.ng)
        else:
            table = OccultationTable(k, self.intensity, nz=self.nz, ng=self.ng)
            out[mask] = table(z[mask])
        return out

    def _flux_batman(self, t, t0, period, k, a_rstar, b):
        batman = self._batman
        a = float(a_rstar)
        inc = math.degrees(math.acos(np.clip(float(b) / a, -1.0, 1.0)))
        params = batman.TransitParams()
        params.t0 = float(t0)
        params.per = float(period)
        params.rp = float(k)
        params.a = a
        params.inc = inc
        params.ecc = 0.0
        params.w = 90.0
        params.limb_dark = {"nonlinear": "nonlinear",
                            "quadratic": "quadratic",
                            "uniform": "uniform"}[self.law]
        params.u = list(self.coeffs)
        kwargs = {}
        if self.supersample > 1:
            kwargs = {"supersample_factor": self.supersample,
                      "exp_time": self.exp_time_days}
        m = batman.TransitModel(params, np.asarray(t, dtype=float), **kwargs)
        return m.light_curve(params)

    def __call__(self, t, t0, period, k, a_rstar, b):
        t = np.asarray(t, dtype=float)
        if self.supersample > 1 and self._batman is None:
            # Finite-exposure smearing, done by hand for the numpy backend.
            # 120 s cadence over a 2.15 h transit does not need it; 1800 s FFI
            # data does, and quietly not doing it would round the ingress off
            # and pull b toward 0.
            offs = (np.arange(self.supersample) - 0.5 * (self.supersample - 1)) \
                / self.supersample * self.exp_time_days
            acc = np.zeros_like(t)
            for o in offs:
                acc += self._flux_numpy(t + o, t0, period, k, a_rstar, b)
            return acc / self.supersample
        if self._batman is not None:
            return self._flux_batman(t, t0, period, k, a_rstar, b)
        return self._flux_numpy(t, t0, period, k, a_rstar, b)


# ------------------------------------------------------ derived geometry --


def transit_durations(period, k, a_rstar, b):
    """(T14, T23, T_ingress) in hours for a circular orbit, or NaN if none.

    Seager & Mallén-Ornelas (2003) Eqs. 3 and 15 with e = 0:

        T14 = (P/π)·asin( sqrt((1+k)² − b²) / (a/R★ · sin i) )
        T23 = (P/π)·asin( sqrt((1−k)² − b²) / (a/R★ · sin i) )

    T23 is NaN for a grazing geometry (b > 1 − k), which is a result, not an
    error: a grazing transit has no flat bottom, and a pipeline that reports
    one has assumed the answer.
    """
    a = float(a_rstar)
    cos_i = np.clip(float(b) / a, -1.0, 1.0)
    sin_i = math.sqrt(max(1e-12, 1.0 - cos_i * cos_i))

    def _dur(kk):
        arg = (1.0 + kk) ** 2 - float(b) ** 2
        if arg <= 0:
            return float("nan")
        val = math.sqrt(arg) / (a * sin_i)
        if val >= 1.0:
            return float("nan")
        return period / math.pi * math.asin(val)

    t14 = _dur(k)
    t23 = _dur(-k)
    ingress = float("nan") if math.isnan(t23) else 0.5 * (t14 - t23)
    return (t14 * 24.0,
            t23 * 24.0 if not math.isnan(t23) else float("nan"),
            ingress * 24.0 if not math.isnan(ingress) else float("nan"))


def transit_depth_ppm(model: TransitModel, period, k, a_rstar, b, t0=0.0):
    """Maximum fractional depth of the fitted model, in ppm.

    Measured off the model rather than computed as k², because for a grazing
    transit k² is not the depth — the planet never fully covers its own area of
    stellar disk — and for a central transit limb darkening makes the depth
    deeper than k². Both effects are what the trapezoid got wrong.
    """
    t = t0 + np.linspace(-0.25, 0.25, 2001) * period
    f = model(t, t0, period, k, a_rstar, b)
    return float((1.0 - np.min(f)) * 1e6)


def density_from_ar(period_days: float, a_rstar: float) -> float:
    """ρ★ in g/cm³ from the transit shape alone (Seager & Mallén-Ornelas 2003).

        ρ★ = 3π/(G P²) · (a/R★)³

    Circular orbit, Mp ≪ M★. No stellar model enters. That independence is why
    it is worth comparing with the Mann-relation density: they share no inputs.
    """
    p_sec = float(period_days) * 86400.0
    return float(3.0 * math.pi / (G_CGS * p_sec**2) * float(a_rstar) ** 3)


def ar_from_density(period_days: float, rho_cgs: float) -> float:
    """The inverse of :func:`density_from_ar` — what a/R★ a given ρ★ implies."""
    p_sec = float(period_days) * 86400.0
    return float((rho_cgs * G_CGS * p_sec**2 / (3.0 * math.pi)) ** (1.0 / 3.0))


# ----------------------------------------------------- the Mann relations --


def mann15_radius(abs_kmag):
    """Mann et al. (2015), ApJ 804, 64 — M_K → R★/R☉, no metallicity term.

        R★/R☉ = 1.9515 − 0.3520·M_K + 0.01680·M_K²

    Calibrated on 183 nearby M dwarfs with interferometric or
    eclipsing-binary radii; quoted scatter 2.89 %, valid 4.6 < M_K < 9.8.

    Why this relation and not Gaia's GSP-Phot radius: GSP-Phot fits a model
    atmosphere grid whose M-dwarf corner is known to be poor, and the package's
    §5d records it returning 0.80 R☉ against TIC's 0.616 — a 30 % disagreement
    on a star whose absolute K magnitude is measured to a few percent. The
    M_K relation goes through one well-behaved, nearly reddening-free,
    metallicity-insensitive observable instead.
    """
    a, b, c = MANN15_R_COEFFS
    mk = np.asarray(abs_kmag, dtype=float)
    return a + b * mk + c * mk * mk


def mann19_mass(abs_kmag):
    """Mann et al. (2019), ApJ 871, 63 — M_K → M★/M☉, n = 5, no [Fe/H].

        M★/M☉ = 10^( Σ_{i=0..5} a_i · (M_K − 7.5)^i )

    with a = (−0.642, −0.208, −8.43e−4, 7.87e−3, 1.42e−4, −2.13e−4).
    Calibrated on 62 nearby M-dwarf binaries with dynamical masses; scatter
    ~2–3 %, valid 4.0 < M_K < 11.0.

    Note the zero point: the polynomial is in (M_K − 7.5), not M_K, and the
    result is a base-10 logarithm. Getting either wrong produces a mass that is
    wrong by a factor of several rather than by a few percent, which is why
    :func:`selftest` pins two hand-computed values.
    """
    mk = np.asarray(abs_kmag, dtype=float)
    x = mk - MANN19_M_ZP
    log_m = np.zeros_like(x)
    for i, a in enumerate(MANN19_M_COEFFS):
        log_m = log_m + a * x**i
    return 10.0**log_m


def absolute_magnitude(app_mag, parallax_mas, extinction=0.0):
    """M = m + 5·log10(ϖ[mas]/100) − A.

    Equivalent to m − 5·log10(d/10 pc) − A with d = 1000/ϖ. No Lutz–Kelker or
    zero-point correction is applied: at ϖ/σ_ϖ ≈ 150 both are far below the
    2.89 % relation scatter, and applying one silently would make the number
    depend on which parallax zero-point paper the author happened to read.
    """
    return (np.asarray(app_mag, dtype=float)
            + 5.0 * np.log10(np.asarray(parallax_mas, dtype=float) / 100.0)
            - float(extinction))


def stellar_parameters(kmag, kmag_err, parallax_mas, parallax_err_mas,
                       *, extinction=0.0, n_mc=20000, seed=20260918):
    """Gaia + 2MASS → (M_K, R★, M★, ρ★) with Monte-Carlo uncertainties.

    Errors are propagated by sampling rather than by a Jacobian because the
    relations are polynomial in M_K and M_K is logarithmic in parallax, so the
    output distributions are not Gaussian and a first-order propagation would
    quietly symmetrise them. The relations' OWN scatter (2.89 % in R★, 3 % in
    M★) is included as a multiplicative term and usually dominates — the
    measurement errors on a ϖ/σ = 150 parallax are not the limiting factor
    here, and a quoted error that omitted the calibration scatter would be
    three times too small.
    """
    rng = np.random.default_rng(seed)
    k_s = rng.normal(float(kmag), max(float(kmag_err), 0.0), n_mc)
    plx_s = rng.normal(float(parallax_mas), max(float(parallax_err_mas), 1e-9), n_mc)
    plx_s = np.clip(plx_s, 1e-6, None)
    mk_s = absolute_magnitude(k_s, plx_s, extinction)

    r_s = mann15_radius(mk_s) * rng.normal(1.0, MANN15_R_SCATTER, n_mc)
    m_s = mann19_mass(mk_s) * rng.normal(1.0, MANN19_M_SCATTER, n_mc)
    good = np.isfinite(r_s) & np.isfinite(m_s) & (r_s > 0) & (m_s > 0)
    r_s, m_s = r_s[good], m_s[good]
    rho_s = RHO_SUN_CGS * m_s / r_s**3

    mk = float(absolute_magnitude(kmag, parallax_mas, extinction))
    out = {
        "kmag": float(kmag),
        "kmag_err": float(kmag_err),
        "parallax_mas": float(parallax_mas),
        "parallax_err_mas": float(parallax_err_mas),
        "extinction_ak": float(extinction),
        "distance_pc": 1000.0 / float(parallax_mas),
        "abs_kmag": mk,
        "abs_kmag_err": float(np.std(mk_s, ddof=1)),
        "rstar_sun": float(mann15_radius(mk)),
        "rstar_sun_err": float(np.std(r_s, ddof=1)),
        "mstar_sun": float(mann19_mass(mk)),
        "mstar_sun_err": float(np.std(m_s, ddof=1)),
        "rho_star_cgs": float(RHO_SUN_CGS * mann19_mass(mk) / mann15_radius(mk) ** 3),
        "rho_star_cgs_err": float(np.std(rho_s, ddof=1)),
        "in_range_mann15": bool(MANN15_MK_RANGE[0] <= mk <= MANN15_MK_RANGE[1]),
        "in_range_mann19": bool(MANN19_MK_RANGE[0] <= mk <= MANN19_MK_RANGE[1]),
        "n_mc": int(r_s.size),
    }
    out["rho_star_sun"] = out["rho_star_cgs"] / RHO_SUN_CGS
    out["rho_star_sun_err"] = out["rho_star_cgs_err"] / RHO_SUN_CGS
    return out


# ------------------------------------------------------------ the fitter --


def nelder_mead(func, x0, step, *, maxiter=4000, ftol=1e-10, xtol=1e-10):
    """Downhill simplex, in numpy, because scipy is not a lab dependency.

    ``step`` is a per-parameter initial simplex edge; internally the problem is
    rescaled so every parameter has step 1, which is what makes a simplex work
    at all on a vector whose entries span 2036 (an epoch in days) and 0.3 (a
    radius ratio). Standard Nelder & Mead (1965) coefficients.
    """
    x0 = np.asarray(x0, dtype=float)
    step = np.asarray(step, dtype=float)
    n = x0.size

    def f(u):
        return float(func(x0 + u * step))

    sim = np.zeros((n + 1, n))
    for i in range(n):
        sim[i + 1, i] = 1.0
    val = np.array([f(s) for s in sim])

    alpha, gamma, rho, sigma = 1.0, 2.0, 0.5, 0.5
    for _ in range(int(maxiter)):
        order = np.argsort(val)
        sim, val = sim[order], val[order]
        if (abs(val[-1] - val[0]) <= ftol * (abs(val[0]) + ftol)
                and np.max(np.abs(sim[1:] - sim[0])) <= xtol):
            break
        centroid = np.mean(sim[:-1], axis=0)
        xr = centroid + alpha * (centroid - sim[-1])
        fr = f(xr)
        if fr < val[0]:
            xe = centroid + gamma * (xr - centroid)
            fe = f(xe)
            sim[-1], val[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < val[-2]:
            sim[-1], val[-1] = xr, fr
        else:
            xc = centroid + rho * (sim[-1] - centroid)
            fc = f(xc)
            if fc < val[-1]:
                sim[-1], val[-1] = xc, fc
            else:
                sim[1:] = sim[0] + sigma * (sim[1:] - sim[0])
                val[1:] = np.array([f(s) for s in sim[1:]])
    order = np.argsort(val)
    return x0 + sim[order][0] * step, float(val[order][0])


#: Parameter order used everywhere below. Kept as a module constant so the
#: fitter, the bootstrap and the MCMC cannot silently disagree about it.
PARAM_NAMES = ("period", "epoch", "k", "a_rstar", "b")
PARAM_STEPS = (2e-5, 2e-3, 0.02, 0.3, 0.06)


def _unpack(theta, model: TransitModel, n_ld: int):
    p, t0, k, a, b = theta[:5]
    if n_ld:
        return p, t0, k, a, b, model.with_coeffs(theta[5:5 + n_ld])
    return p, t0, k, a, b, model


def _penalty(theta, n_ld: int) -> float:
    """Hard bounds as an infinite penalty — the simplex has no bound support.

    ``b < 1 + k`` rather than ``b < 1``: a transit CAN be grazing past the
    stellar limb, and forcing b ≤ 1 on this target would be assuming away the
    exact geometry SPOC's fit prefers.
    """
    p, t0, k, a, b = theta[:5]
    if not (0.1 < p < 1000.0):
        return math.inf
    if not (1e-4 < k < 0.95):
        return math.inf
    if not (1.5 < a < 500.0):
        return math.inf
    if not (0.0 <= b < 1.0 + k):
        return math.inf
    if a * math.sqrt(max(0.0, 1.0 - (b / a) ** 2)) <= 1.0:
        return math.inf
    return 0.0


def chi2_of(theta, t, f, w, model: TransitModel, n_ld: int):
    """χ² with the out-of-transit level solved for analytically.

    The baseline scale f0 enters linearly, so it is a weighted least-squares
    solution given the shape rather than a sixth simplex dimension. One fewer
    parameter to wander, and no starting guess to get wrong.
    """
    pen = _penalty(theta, n_ld)
    if pen:
        return pen
    p, t0, k, a, b, m = _unpack(theta, model, n_ld)
    try:
        mod = m(t, t0, p, k, a, b)
    except Exception:
        return math.inf
    if not np.all(np.isfinite(mod)):
        return math.inf
    denom = float(np.sum(w * mod * mod))
    if denom <= 0:
        return math.inf
    f0 = float(np.sum(w * f * mod) / denom)
    r = f - f0 * mod
    return float(np.sum(w * r * r))


def fit_transit(t, f, w, model: TransitModel, guess, *, free_ld=False,
                maxiter=4000, restarts=2):
    """Fit (P, T0, k, a/R★, b) [+ limb darkening] by restarted simplex.

    Restarts are not decoration: the (k, a/R★, b) surface for a grazing transit
    has a long curved valley — deeper-and-more-grazing trades against
    shallower-and-more-central along it — and a single simplex parks partway
    down. Restarting from the previous best with a fresh simplex is the cheap
    way to walk the valley floor. It is NOT a guarantee of a global minimum,
    and on this target it will not be: see the a/R★–b degeneracy warning the
    summary prints.
    """
    n_ld = len(model.coeffs) if free_ld else 0
    theta = np.array(list(guess) + (list(model.coeffs) if n_ld else []), dtype=float)
    steps = np.array(list(PARAM_STEPS) + ([0.05] * n_ld), dtype=float)

    def obj(th):
        return chi2_of(th, t, f, w, model, n_ld)

    best, best_chi2 = theta, obj(theta)
    if not math.isfinite(best_chi2):
        raise RefitError(
            "the starting guess is outside the model's bounds — check the "
            "period/epoch/a-over-Rstar you passed in")
    for i in range(max(1, int(restarts))):
        cand, chi = nelder_mead(obj, best, steps * (0.5**i), maxiter=maxiter)
        if chi < best_chi2:
            best, best_chi2 = cand, chi
    return best, best_chi2, n_ld


# ------------------------------------------------------------- the errors --


def bootstrap_errors(t, f, w, model, best, n_ld, *, n_boot=200, seed=20260918,
                     method="residual", maxiter=800, progress=None):
    """Parameter scatter from refitting resampled residuals.

    ``residual`` resamples the residuals i.i.d.; ``prayerbead`` rolls them
    cyclically. The difference matters and is not cosmetic: TESS PDCSAP
    residuals on a 14th-magnitude M dwarf are correlated on the timescale of an
    ingress, i.i.d. resampling destroys that correlation, and the errors it
    returns are therefore LOWER LIMITS. Prayer-bead keeps the correlation
    structure and is the honest default for anything going in a paper; it is
    not the default here only because it gives exactly ``len(t)`` distinct
    realisations and is slower to cover them. Neither is a posterior — use
    ``--errors mcmc`` for that.
    """
    rng = np.random.default_rng(seed)
    p, t0, k, a, b, m = _unpack(best, model, n_ld)
    mod = m(t, t0, p, k, a, b)
    denom = float(np.sum(w * mod * mod))
    f0 = float(np.sum(w * f * mod) / denom)
    base = f0 * mod
    resid = f - base

    steps = np.array(list(PARAM_STEPS) + ([0.05] * n_ld), dtype=float) * 0.4
    draws = []
    for i in range(int(n_boot)):
        if method == "prayerbead":
            shift = rng.integers(1, resid.size)
            fb = base + np.roll(resid, int(shift))
        else:
            fb = base + rng.choice(resid, size=resid.size, replace=True)

        def obj(th, fb=fb):
            return chi2_of(th, t, fb, w, model, n_ld)

        cand, _ = nelder_mead(obj, best, steps, maxiter=maxiter)
        draws.append(cand)
        if progress and (i + 1) % max(1, int(n_boot) // 10) == 0:
            progress(f"  bootstrap {i + 1}/{n_boot}")
    draws = np.asarray(draws, dtype=float)
    return draws, np.std(draws, axis=0, ddof=1)


def mcmc_errors(t, f, w, model, best, n_ld, *, nwalkers=32, nsteps=3000,
                burn=1000, seed=20260918, progress=None):
    """emcee posterior with flat priors inside the bounds. Optional import.

    The likelihood is Gaussian with the weights already in ``w`` and a single
    baseline scale solved analytically, same as :func:`chi2_of`. No noise
    jitter term is fitted, so the posterior widths here are conditional on the
    quoted photometric errors being right; where they are not (correlated
    systematics), compare against ``--errors prayerbead`` before believing the
    narrower of the two.
    """
    try:
        import emcee
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise RefitError(
            "--errors mcmc needs emcee (pip install emcee); "
            f"import failed: {exc}") from exc

    ndim = best.size

    def log_prob(th):
        c = chi2_of(th, t, f, w, model, n_ld)
        if not math.isfinite(c):
            return -math.inf
        return -0.5 * c

    scatter = np.array(list(PARAM_STEPS) + ([0.02] * n_ld), dtype=float) * 0.05
    rng = np.random.default_rng(seed)
    p0 = best[None, :] + rng.normal(0.0, 1.0, (nwalkers, ndim)) * scatter[None, :]
    for i in range(nwalkers):
        tries = 0
        while not math.isfinite(log_prob(p0[i])) and tries < 200:
            p0[i] = best + rng.normal(0.0, 1.0, ndim) * scatter
            tries += 1
        if not math.isfinite(log_prob(p0[i])):
            p0[i] = best.copy()

    sampler = emcee.EnsembleSampler(nwalkers, ndim, log_prob)
    sampler.run_mcmc(p0, int(nsteps), progress=False)
    chain = sampler.get_chain(discard=int(burn), flat=True)
    if progress:
        try:
            acc = float(np.mean(sampler.acceptance_fraction))
            progress(f"  emcee acceptance fraction {acc:.3f}, "
                     f"{chain.shape[0]} samples after burn-in")
        except Exception:
            pass
    return chain, np.std(chain, axis=0, ddof=1)


# -------------------------------------------------------------- the data --


def read_fits_light_curve(path: Path) -> dict:
    """One TESS SPOC light-curve FITS file → {t, f, ferr, sector, source}.

    Prefers ``lab.a01.read_tess_light_curve`` — the repo's own pure-numpy FITS
    walker, already used by every receipt — so that a curve read here is the
    same bytes-to-array path the rest of the lab uses. Falls back to astropy.
    Quality flags are applied: any non-zero QUALITY cadence is dropped, which
    is SPOC's own "default" bitmask taken at its most conservative.
    """
    path = Path(path)
    blob = path.read_bytes()

    # The two readers are tried in a fixed order and the choice is NOT made by
    # catching exceptions from the first one: an exception from lab.a01 on a
    # file it *should* have read (a truncated download, a wrong product) is a
    # thing the operator needs to see, not a reason to quietly reach for a
    # different library. Only the ImportError routes to the fallback.
    a01 = None
    src = str(REPO_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        from lab import a01 as _a01  # noqa: WPS433
        a01 = _a01
    except Exception:
        a01 = None

    if a01 is not None:
        # Column names are the FITS ones, verbatim: lab.a01 returns the TESS
        # TTYPEs untouched ("TIME", "PDCSAP_FLUX", …), not lower-cased aliases.
        curve = a01.read_tess_light_curve(blob)
        t = np.asarray(curve["TIME"], dtype=float)
        f = np.asarray(curve["PDCSAP_FLUX"], dtype=float)
        ferr = np.asarray(curve["PDCSAP_FLUX_ERR"], dtype=float)
        qual = np.asarray(curve["QUALITY"], dtype=float)
    else:
        try:
            from astropy.io import fits
        except Exception as exc:
            raise RefitError(
                f"cannot read {path.name}: neither lab.a01 nor astropy is "
                f"importable ({exc}). Run this from the repo root so `src/lab` "
                "is on the path, or pip install astropy.") from exc
        with fits.open(str(path)) as hdul:
            data = hdul[1].data
            t = np.asarray(data["TIME"], dtype=float)
            col = "PDCSAP_FLUX" if "PDCSAP_FLUX" in data.columns.names else "SAP_FLUX"
            f = np.asarray(data[col], dtype=float)
            ecol = col + "_ERR"
            ferr = (np.asarray(data[ecol], dtype=float)
                    if ecol in data.columns.names else np.full_like(f, np.nan))
            qual = np.asarray(data["QUALITY"], dtype=float)

    good = np.isfinite(t) & np.isfinite(f) & (f > 0) & (qual == 0)
    t, f, ferr = t[good], f[good], ferr[good]
    med = float(np.median(f))
    order = np.argsort(t, kind="stable")
    return {"t": t[order], "f": f[order] / med,
            "ferr": ferr[order] / med, "source": Path(path).name}


def load_from_dir(fits_dir: Path) -> list[dict]:
    paths = sorted(p for p in Path(fits_dir).glob("*.fits")
                   if "_lc" in p.name or "lc.fits" in p.name) \
        or sorted(Path(fits_dir).glob("*.fits"))
    if not paths:
        raise RefitError(f"no *.fits files under {fits_dir}")
    return [read_fits_light_curve(p) for p in paths]


def load_from_lightkurve(tic: str, *, exptime=120, max_sectors=None,
                         progress=None) -> list[dict]:
    """Download SPOC 2-minute light curves. The only networked path here.

    Deliberately restricted to ``author="SPOC"`` and 2-minute cadence: the
    package's numbers, SPOC's DV fit and this refit should all be looking at
    the same product, and mixing in QLP or 30-minute FFI photometry would
    smear the ingress this fit is trying to measure while looking like more
    data.
    """
    try:
        import lightkurve as lk
    except Exception as exc:
        raise RefitError(
            "no --fits-dir was given and `import lightkurve` failed "
            f"({exc}).\n"
            "  Either:  pip install lightkurve\n"
            "  or:      download the SPOC 2-min light curves for TIC "
            f"{tic} from MAST by hand and pass --fits-dir <folder>.\n"
            "  This script will not invent a light curve.") from exc

    if progress:
        progress(f"searching MAST for TIC {tic} (SPOC, {exptime}s)…")
    search = lk.search_lightcurve(f"TIC {tic}", mission="TESS",
                                  author="SPOC", exptime=exptime)
    if len(search) == 0:
        raise RefitError(f"MAST returned no SPOC {exptime}s light curves for TIC {tic}")
    if max_sectors:
        search = search[:int(max_sectors)]
    if progress:
        progress(f"  {len(search)} products; downloading…")
    coll = search.download_all()
    out = []
    for lcf in coll:
        lc = lcf.remove_nans("flux")
        try:
            lc = lc[lc.quality == 0]
        except Exception:
            pass
        t = np.asarray(lc.time.value, dtype=float)
        f = np.asarray(lc.flux.value, dtype=float)
        try:
            ferr = np.asarray(lc.flux_err.value, dtype=float)
        except Exception:
            ferr = np.full_like(f, np.nan)
        good = np.isfinite(t) & np.isfinite(f) & (f > 0)
        t, f, ferr = t[good], f[good], ferr[good]
        if t.size < 100:
            continue
        med = float(np.median(f))
        sector = getattr(lcf.meta, "get", lambda *_: None)("SECTOR") \
            if hasattr(lcf, "meta") else None
        out.append({"t": t, "f": f / med, "ferr": ferr / med,
                    "source": f"sector {sector}" if sector else "lightkurve"})
    if not out:
        raise RefitError("lightkurve returned products but none had usable cadences")
    return out


def sector_coverage(curves) -> dict:
    """Which TESS sectors these light curves actually are.

    ``load_from_lightkurve`` already stamps each curve's ``source`` as
    ``"sector <n>"``; nothing read it back, so every coverage number this script
    produced was a range a human typed from the product count. Returns the sorted
    sector list, how many curves could not be identified, and the span -- so a
    reader can check the count against the list instead of trusting a label.
    """
    sectors, unknown = [], 0
    for c in curves:
        m = re.fullmatch(r"sector (\d+)", str(c.get("source", "")))
        if m:
            sectors.append(int(m.group(1)))
        else:
            unknown += 1
    sectors = sorted(set(sectors))
    return {"sectors": sectors, "unknown": unknown,
            "n_curves": len(curves),
            "lowest": sectors[0] if sectors else None,
            "highest": sectors[-1] if sectors else None}


def window_and_detrend(curves, period, epoch, duration_hours, *,
                       window_factor=3.0, poly_order=1):
    """Cut ±window_factor·T14 around each transit and flatten each window.

    Why per-window rather than a global filter: a global spline or Savitzky–
    Golay run over the whole sector has to be told to mask the transits, and if
    the mask is even slightly wrong it eats the transit and shrinks the depth —
    which is one of the ways a trapezoid fit ends up 25 % shallow. Fitting a
    low-order polynomial to the OUT-OF-TRANSIT points of each window and
    dividing is local, mask-explicit, and cannot pull flux out of the transit
    it is not fitted to.

    The package's §5d also notes a coherent 3.8-day out-of-transit modulation
    at ~1–2 % (probably rotation). Over a ±3-duration window that is 0.54 days
    wide, a straight line removes it to well under the photometric scatter;
    ``--poly-order 2`` is there for anyone who wants to check that claim.

    KNOWN LIMITATION, pinned by a test rather than left to be discovered: this
    function cannot tell a right epoch from a wrong one. Windows are laid down
    at epoch + n·P across the whole series, so an epoch off by half a period
    yields exactly as many well-formed windows, containing flat baseline. What
    fails then is the fit, by driving k to its lower bound — so a fitted k
    near 1e-4 means "you gave me the wrong ephemeris", not "there is no
    planet". It raises only when there is genuinely nothing to window.
    """
    dur = float(duration_hours) / 24.0
    half = float(window_factor) * dur
    tt, ff, ee = [], [], []
    n_windows = 0
    for c in curves:
        t, f = c["t"], c["f"]
        ferr = c.get("ferr")
        if t.size == 0:
            continue
        n_lo = math.floor((t.min() - epoch - half) / period)
        n_hi = math.ceil((t.max() - epoch + half) / period)
        for n in range(int(n_lo), int(n_hi) + 1):
            tc = epoch + n * period
            m = np.abs(t - tc) <= half
            if np.count_nonzero(m) < 20:
                continue
            tw, fw = t[m], f[m]
            ew = ferr[m] if ferr is not None and np.all(np.isfinite(ferr[m])) else None
            oot = np.abs(tw - tc) > 0.75 * dur
            if np.count_nonzero(oot) < max(6, poly_order + 2):
                continue
            coef = np.polyfit(tw[oot] - tc, fw[oot], int(poly_order))
            base = np.polyval(coef, tw - tc)
            if np.any(base <= 0):
                continue
            tt.append(tw)
            ff.append(fw / base)
            ee.append((ew / base) if ew is not None
                      else np.full_like(fw, np.nan))
            n_windows += 1
    if not tt:
        raise RefitError(
            "no usable transit windows — check --period/--epoch, and that the "
            "light curves actually cover the epoch you gave")
    t = np.concatenate(tt)
    f = np.concatenate(ff)
    e = np.concatenate(ee)
    order = np.argsort(t, kind="stable")
    return t[order], f[order], e[order], n_windows


def weights_from(f, ferr):
    """1/σ² weights: quoted errors where they exist, robust MAD where not.

    The MAD is computed on the OUT-OF-TRANSIT half of the flux distribution by
    construction (a 10 % transit at ~13 % duty cycle inside the window leaves
    the median firmly out of transit), so a deep transit does not inflate its
    own error bar.
    """
    if ferr is not None and np.all(np.isfinite(ferr)) and np.all(ferr > 0):
        return 1.0 / ferr**2, float(np.median(ferr))
    sigma = float(np.median(np.abs(f - np.median(f))) * 1.4826)
    sigma = max(sigma, 1e-8)
    return np.full_like(f, 1.0 / sigma**2), sigma


# -------------------------------------------------------------- reporting --


def summarise(best, errs, n_ld, model, rho_star, *, chi2=None, ndata=None,
              backend="numpy"):
    p, t0, k, a, b, m = _unpack(best, model, n_ld)
    t14, t23, ing = transit_durations(p, k, a, b)
    depth = transit_depth_ppm(m, p, k, a, b)
    rho_circ = density_from_ar(p, a)
    e = dict(zip(PARAM_NAMES, errs[:5])) if errs is not None else {}
    out = {
        "backend": backend,
        "limb_darkening": {"law": model.law,
                           "coeffs": list(m.coeffs),
                           "free": bool(n_ld)},
        "period_days": float(p),
        "period_err_days": float(e.get("period", float("nan"))),
        "epoch_btjd": float(t0),
        "epoch_bjd_tdb": float(t0) + BTJD_OFFSET,
        "epoch_err_days": float(e.get("epoch", float("nan"))),
        "rp_rstar": float(k),
        "rp_rstar_err": float(e.get("k", float("nan"))),
        "a_rstar": float(a),
        "a_rstar_err": float(e.get("a_rstar", float("nan"))),
        "b": float(b),
        "b_err": float(e.get("b", float("nan"))),
        "inclination_deg": float(math.degrees(math.acos(min(1.0, b / a)))),
        "depth_ppm": float(depth),
        "duration_t14_hours": float(t14),
        "duration_t23_hours": float(t23),
        "ingress_hours": float(ing),
        "grazing": bool(b > 1.0 - k),
        "rho_circ_cgs": float(rho_circ),
        "rho_circ_sun": float(rho_circ / RHO_SUN_CGS),
    }
    if chi2 is not None and ndata:
        nfree = 5 + n_ld + 1
        out["chi2"] = float(chi2)
        out["ndata"] = int(ndata)
        out["chi2_reduced"] = float(chi2 / max(1, ndata - nfree))
    if rho_star:
        out["rho_star_cgs"] = rho_star["rho_star_cgs"]
        out["rho_ratio_transit_over_star"] = float(rho_circ / rho_star["rho_star_cgs"])
        out["rp_rjup"] = float(k * rho_star["rstar_sun"] * 6.957e5 / 71492.0)
        out["rp_rearth"] = float(k * rho_star["rstar_sun"] * 6.957e5 / 6371.0)
        # Uncertainty on Rp from k and R★ only; the Monte Carlo above already
        # carries the relation scatter into rstar_sun_err.
        if np.isfinite(out["rp_rstar_err"]):
            frac = math.hypot(out["rp_rstar_err"] / max(k, 1e-9),
                              rho_star["rstar_sun_err"] / max(rho_star["rstar_sun"], 1e-9))
            out["rp_rjup_err"] = float(out["rp_rjup"] * frac)
            out["rp_rearth_err"] = float(out["rp_rearth"] * frac)
    return out


def _fmt(value, err=None, digits=6):
    """Value ± error, with the error always at two significant figures.

    Two, not one: an error printed as "0.02" cannot be told from 0.015 or
    0.024, and on a parameter like b those are different conclusions about
    whether the transit is grazing.
    """
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "—"
    s = f"{value:.{digits}g}"
    if err is not None and np.isfinite(err):
        s += f" ± {_fmt_err(err)}"
    return s


def _fmt_err(err: float) -> str:
    """Two significant figures, in fixed notation wherever that is readable.

    ``f"{372.27:.2g}"`` is ``3.7e+02``, which next to a depth written 84140 is
    just noise for the reader to decode. Anything between 1e-4 and 1e5 gets
    written out.
    """
    err = float(err)
    if not np.isfinite(err) or err == 0.0:
        return f"{err:.2g}"
    mag = math.floor(math.log10(abs(err)))
    if -4 <= mag <= 4:
        return f"{err:.{max(0, 1 - mag)}f}"
    return f"{err:.2g}"


def print_summary(fit, star, *, out=sys.stdout):
    w = out.write
    w("\n" + "=" * 78 + "\n")
    w(f"TIC {TIC} — limb-darkened refit + Gaia-anchored host\n")
    w("=" * 78 + "\n\n")

    w("HOST STAR (derived here, not copied from a catalogue)\n")
    w("-" * 78 + "\n")
    w(f"  K (2MASS)            {_fmt(star['kmag'], star['kmag_err'], 5)} mag\n")
    w(f"  parallax             {_fmt(star['parallax_mas'], star['parallax_err_mas'], 4)} mas"
      f"   -> {star['distance_pc']:.1f} pc\n")
    w(f"  A_K applied          {star['extinction_ak']:.3f} mag\n")
    w(f"  M_K                  {_fmt(star['abs_kmag'], star['abs_kmag_err'], 4)} mag\n")
    w(f"  R* (Mann+2015)       {_fmt(star['rstar_sun'], star['rstar_sun_err'], 4)} Rsun"
      f"      [TIC v8: {SPOC_DV['rstar_sun']:.4f} ± {SPOC_DV['rstar_sun_err']:.4f}]\n")
    w(f"  M* (Mann+2019)       {_fmt(star['mstar_sun'], star['mstar_sun_err'], 4)} Msun\n")
    w(f"  rho* (M*/R*^3)       {_fmt(star['rho_star_cgs'], star['rho_star_cgs_err'], 4)} g/cm^3"
      f"   = {_fmt(star['rho_star_sun'], star['rho_star_sun_err'], 4)} rho_sun\n")
    if not (star["in_range_mann15"] and star["in_range_mann19"]):
        w("  ** M_K is OUTSIDE at least one relation's calibrated range — the\n"
          "     numbers above are extrapolations and should not be quoted. **\n")
    w("\n")

    w("TRANSIT FIT (this script)\n")
    w("-" * 78 + "\n")
    ld = fit["limb_darkening"]
    w(f"  model backend        {fit['backend']}\n")
    w(f"  limb darkening       {ld['law']}, {'FREE' if ld['free'] else 'fixed'}: "
      + ", ".join(f"{c:.6g}" for c in ld["coeffs"]) + "\n")
    w(f"  period               {_fmt(fit['period_days'], fit['period_err_days'], 10)} d\n")
    w(f"  epoch                {_fmt(fit['epoch_btjd'], fit['epoch_err_days'], 10)} BTJD\n")
    w(f"                       {fit['epoch_bjd_tdb']:.6f} BJD_TDB\n")
    w(f"  Rp/R*                {_fmt(fit['rp_rstar'], fit['rp_rstar_err'], 4)}\n")
    w(f"  a/R*                 {_fmt(fit['a_rstar'], fit['a_rstar_err'], 4)}\n")
    w(f"  b                    {_fmt(fit['b'], fit['b_err'], 4)}"
      f"   ({'GRAZING' if fit['grazing'] else 'non-grazing'}, i = {fit['inclination_deg']:.3f} deg)\n")
    w(f"  depth (of the model) {fit['depth_ppm']:.1f} ppm\n")
    w(f"  T14 / T23 / ingress  {_fmt(fit['duration_t14_hours'], None, 5)} / "
      f"{_fmt(fit['duration_t23_hours'], None, 5)} / "
      f"{_fmt(fit['ingress_hours'], None, 5)} h\n")
    if "chi2_reduced" in fit:
        w(f"  chi2 / dof           {fit['chi2']:.1f} / {fit['ndata']} pts"
          f"   -> reduced {fit['chi2_reduced']:.4f}\n")
    if "rp_rjup" in fit:
        w(f"  Rp = k x R*          {_fmt(fit['rp_rjup'], fit.get('rp_rjup_err'), 4)} R_Jup"
          f"  = {_fmt(fit['rp_rearth'], fit.get('rp_rearth_err'), 4)} R_Earth\n")
    w("\n")

    w("DENSITY CROSS-CHECK  (the one place star and light curve meet)\n")
    w("-" * 78 + "\n")
    w("  Two routes with NO shared inputs: the transit shape (a/R*, P) knows no\n"
      "  stellar model; the Mann relations know no photometry of this transit.\n")
    w(f"  rho from transit shape   {fit['rho_circ_cgs']:.4f} g/cm^3"
      f"   = {fit['rho_circ_sun']:.4f} rho_sun\n")
    w(f"  rho from Mann relations  {star['rho_star_cgs']:.4f} g/cm^3"
      f"   = {star['rho_star_sun']:.4f} rho_sun\n")
    ratio = fit["rho_circ_cgs"] / star["rho_star_cgs"]
    w(f"  ratio (transit/star)     {ratio:.3f}\n")
    implied = ar_from_density(fit["period_days"], star["rho_star_cgs"])
    w(f"  a/R* the star implies    {implied:.3f}   (fit says {fit['a_rstar']:.3f})\n")
    if ratio > 1.3 or ratio < 0.77:
        w("  -> These do not agree. A circular orbit around this star cannot\n"
          "     produce this transit shape. The live explanations are (i) the\n"
          "     grazing degeneracy put the fit on the wrong branch, (ii) the\n"
          "     orbit is eccentric, (iii) the host is not the star the Mann\n"
          "     relations describe (unresolved blend). This is a result to\n"
          "     report, not a number to average away.\n")
    else:
        w("  -> Consistent within the usual factor-1.3 tolerance for a\n"
          "     circular-orbit shape density.\n")
    w("\n")

    w("COMPARISON  (lab trapezoid | SPOC DV s1-s96 | this refit)\n")
    w("-" * 78 + "\n")
    rows = [
        ("period (d)",
         _fmt(LAB_TRAPEZOID["period_days"], LAB_TRAPEZOID["period_err_days"], 10),
         _fmt(SPOC_DV["period_days"], SPOC_DV["period_err_days"], 10),
         _fmt(fit["period_days"], fit["period_err_days"], 10)),
        ("epoch (BTJD)",
         _fmt(LAB_TRAPEZOID["epoch_btjd"], LAB_TRAPEZOID["epoch_err_days"], 10),
         _fmt(SPOC_DV["epoch_btjd"], SPOC_DV["epoch_err_days"], 10),
         _fmt(fit["epoch_btjd"], fit["epoch_err_days"], 10)),
        ("depth (ppm)",
         _fmt(LAB_TRAPEZOID["depth_ppm"], LAB_TRAPEZOID["depth_err_ppm"], 6),
         _fmt(SPOC_DV["depth_ppm"], SPOC_DV["depth_err_ppm"], 6),
         _fmt(fit["depth_ppm"], None, 6)),
        ("T14 (h)",
         _fmt(LAB_TRAPEZOID["duration_hours"], LAB_TRAPEZOID["duration_err_hours"], 5),
         _fmt(SPOC_DV["duration_hours"], None, 5),
         _fmt(fit["duration_t14_hours"], None, 5)),
        ("ingress (h)", "— (fixed 0.15 T14)",
         _fmt(SPOC_DV["ingress_hours"], None, 5),
         _fmt(fit["ingress_hours"], None, 5)),
        ("Rp/R*", _fmt(LAB_TRAPEZOID["rp_rstar"], None, 4),
         _fmt(SPOC_DV["rp_rstar"], SPOC_DV["rp_rstar_err"], 4),
         _fmt(fit["rp_rstar"], fit["rp_rstar_err"], 4)),
        ("a/R*", _fmt(LAB_TRAPEZOID["a_rstar"], None, 4), "7.71 ± 0.05",
         _fmt(fit["a_rstar"], fit["a_rstar_err"], 4)),
        ("b", _fmt(LAB_TRAPEZOID["b"], None, 4),
         _fmt(SPOC_DV["b"], SPOC_DV["b_err"], 4),
         _fmt(fit["b"], fit["b_err"], 4)),
        ("R* (Rsun)", f"{SPOC_DV['rstar_sun']:.4f} (TIC)",
         f"{SPOC_DV['rstar_sun']:.4f} (TIC)",
         _fmt(star["rstar_sun"], star["rstar_sun_err"], 4) + " (Mann+15)"),
        ("rho* (g/cm^3)", f"{density_from_ar(LAB_TRAPEZOID['period_days'], LAB_TRAPEZOID['a_rstar']):.3f} (shape)",
         f"{density_from_ar(SPOC_DV['period_days'], 7.71):.3f} (shape)",
         f"{fit['rho_circ_cgs']:.3f} (shape) / {star['rho_star_cgs']:.3f} (star)"),
    ]
    w(f"  {'quantity':<15}{'lab trapezoid':<29}{'SPOC DV':<29}{'this refit'}\n")
    for name, a, b_, c in rows:
        w(f"  {name:<15}{a:<29}{b_:<29}{c}\n")
    w("\n")
    w("CAVEATS a reader must carry out of this table\n")
    w("-" * 78 + "\n")
    w("  * A grazing transit does not determine k. Along the b-vs-k valley, a\n"
      "    deeper planet further off-centre fits as well as a shallower one\n"
      "    nearer the middle; SPOC's own +/-0.076 on k = 0.430 is that valley,\n"
      "    not a measurement error. Quote k with b, or do not quote it.\n")
    w("  * These errors are photometric only. They contain no dilution error,\n"
      "    no limb-darkening-coefficient error (the Claret values are held\n"
      "    fixed unless --free-ld), and no stellar-model error beyond the Mann\n"
      "    relation scatter.\n")
    w("  * Nothing here measures a mass. The package's disposition is still\n"
      "    'planet candidate', and only a radial-velocity follow-up moves it.\n")
    w("  * PDCSAP flux is already crowding-corrected by SPOC, so no dilution\n"
      "    correction is applied here. If you feed this SAP flux instead, the\n"
      "    depth will be too shallow and nothing in this script will notice.\n")
    w("  * A dash in the T23 or ingress column is not a missing number. b > 1-k\n"
      "    means the transit has no flat bottom and no second contact, so both\n"
      "    are undefined. SPOC's DV nonetheless prints an ingress of 1.0767 h\n"
      "    for the same grazing geometry — exactly half its own T14. Read that\n"
      "    as its fitter's convention, not as a measured second contact.\n")
    w("=" * 78 + "\n")


# -------------------------------------------------------------- selftest --


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def _selftest_mann(log):
    """Hand-computed values, written out so a reader can redo them on paper."""
    # Mann+2015 at M_K = 4.98 (the value the CTOI package §5d quotes):
    #   1.9515 - 0.3520*4.98 + 0.01680*4.98^2
    # = 1.9515 - 1.752960 + 0.016800*24.8004
    # = 1.9515 - 1.752960 + 0.416647 = 0.615187
    r = float(mann15_radius(4.98))
    log(f"  Mann+2015 R*(M_K=4.98) = {r:.6f} Rsun (hand: 0.615187)")
    _check(abs(r - 0.615187) < 1e-5, f"Mann+2015 at M_K=4.98 gave {r}, want 0.615187")
    # Independent corroboration, not a second copy of the same arithmetic:
    # TIC v8 lists 0.615867 Rsun for this star from the same relation.
    _check(abs(r - SPOC_DV["rstar_sun"]) < 0.002,
           f"Mann+2015 gives {r}, TIC v8 lists {SPOC_DV['rstar_sun']} — "
           "the coefficients do not reproduce the catalogue")

    # Mann+2015 at M_K = 7.00:
    #   1.9515 - 0.3520*7 + 0.01680*49 = 1.9515 - 2.4640 + 0.8232 = 0.310700
    r2 = float(mann15_radius(7.0))
    log(f"  Mann+2015 R*(M_K=7.00) = {r2:.6f} Rsun (hand: 0.310700)")
    _check(abs(r2 - 0.310700) < 1e-6, f"Mann+2015 at M_K=7 gave {r2}, want 0.310700")

    # Mann+2019 at the relation's own zero point M_K = 7.5: (M_K − 7.5) = 0, so
    # every term but a0 vanishes and M* = 10^(-0.642) = 0.228034 Msun. This is
    # the check that catches a missing 10^ or a forgotten −7.5 offset — get
    # either wrong and the mass is out by a factor of several, not a percent.
    m = float(mann19_mass(7.5))
    log(f"  Mann+2019 M*(M_K=7.50) = {m:.6f} Msun (hand: 10^-0.642 = 0.228034)")
    _check(abs(m - 0.228034) < 1e-6,
           f"Mann+2019 at the zero point gave {m}, want 10^-0.642 = 0.228034")

    # Mann+2019 at M_K = 4.98, so x = M_K − 7.5 = −2.52:
    #   x^2 =    6.3504        x^3 =  −16.003008
    #   x^4 =   40.32758016    x^5 = −101.62550200
    #   a0      = −0.642
    #   a1·x    = (−0.208)(−2.52)          = +0.52416000
    #   a2·x^2  = (−8.43e−4)(6.3504)       = −0.00535339
    #   a3·x^3  = (7.87e−3)(−16.003008)    = −0.12594367
    #   a4·x^4  = (1.42e−4)(40.32758016)   = +0.00572652
    #   a5·x^5  = (−2.13e−4)(−101.625502)  = +0.02164623
    #   Σ = −0.22176431  ->  10^−0.22176431 = 0.6001167
    m2 = float(mann19_mass(4.98))
    log(f"  Mann+2019 M*(M_K=4.98) = {m2:.7f} Msun (hand: 0.6001167)")
    _check(abs(m2 - 0.6001167) < 1e-6,
           f"Mann+2019 at M_K=4.98 gave {m2}, want 0.6001167")
    # And the corroboration: TIC v8 lists 0.601 Msun for this star.
    _check(abs(m2 - 0.601) < 0.01,
           f"Mann+2019 gives {m2} Msun, TIC v8 lists 0.601 — coefficients suspect")

    # The density conversion, end to end: rho_sun * M/R^3.
    rho = RHO_SUN_CGS * m2 / r**3
    log(f"  rho*(M_K=4.98) = {rho:.4f} g/cm^3 = {rho / RHO_SUN_CGS:.4f} rho_sun")
    _check(3.4 < rho < 3.9, f"rho* {rho} g/cm^3 is not near the expected 3.6")
    # This is the number the CTOI package prints as '2.57 g/cm^3'; 2.57 is the
    # SOLAR-UNIT value. Pin the relationship so the mislabelling cannot creep
    # back in here.
    _check(abs(rho / RHO_SUN_CGS - 2.57) < 0.06,
           "solar-unit density drifted from the package's 2.57")

    # Absolute magnitude round trip.
    mk = float(absolute_magnitude(11.729, 4.47))
    log(f"  M_K(K=11.729, plx=4.47 mas) = {mk:.4f}")
    _check(abs(mk - 4.98) < 0.01, f"absolute_magnitude gave {mk}, want ~4.98")


def _selftest_ld_norm(log):
    """The quadrature's disk-integrated flux vs. the closed forms."""
    nodes, weights = _gauss_legendre(64)
    s = 0.5 + 0.5 * nodes

    def quad_norm(intensity):
        return float(np.sum(4.0 * s**3 * intensity(s * s) * weights) * 0.5)

    for law, coeffs in (("uniform", ()),
                        ("quadratic", (0.35, 0.22)),
                        ("nonlinear", CLARET_TESS)):
        func, _ = LD_LAWS[law]
        num = quad_norm(lambda mu, f=func, c=coeffs: f(mu, c))
        closed = ld_norm_closed_form(law, coeffs)
        log(f"  norm {law:<10} quadrature {num:.10f}  closed form {closed:.10f}")
        _check(abs(num - closed) < 1e-9,
               f"{law} normalisation: quadrature {num} vs closed form {closed}")


def _selftest_occultation(log):
    """The integrator against the closed-form uniform source, and sanity."""
    k = 0.30
    z = np.concatenate([np.linspace(0.0, 1.0 + k, 401),
                        np.array([1.0 - k, 1.0 + k, 1e-9])])
    exact = uniform_occultation(z, k)
    mine = occultation_ld(z, k, lambda mu: uniform_intensity(mu), ng=40)
    worst = float(np.max(np.abs(exact - mine)))
    log(f"  uniform source: max |numeric - Mandel&Agol closed form| = {worst:.3e}")
    # 1e-6 = 1 ppm, against a transit depth of ~100,000 ppm. The tolerance is
    # set by what the fit reports, not by what the integrator happens to
    # achieve; if a future change makes this 10 ppm, the depth column is wrong
    # in its fifth digit and someone should know.
    _check(worst < 1e-6,
           f"numeric occultation disagrees with the uniform closed form by {worst}")

    # Out of transit is exactly 1, everywhere past first contact.
    oot = occultation_ld(np.array([1.0 + k + 1e-9, 2.0, 10.0]), k,
                         lambda mu: claret_nonlinear_intensity(mu, CLARET_TESS))
    _check(np.allclose(oot, 1.0, atol=1e-12), f"out-of-transit flux is not 1: {oot}")

    # Uniform source, central: depth is EXACTLY k^2. Limb darkening: deeper.
    cen_u = float(occultation_ld(np.array([0.0]), k, uniform_intensity, ng=40)[0])
    _check(abs((1.0 - cen_u) - k * k) < 1e-9,
           f"uniform central depth {1 - cen_u} != k^2 = {k * k}")
    cen_ld = float(occultation_ld(np.array([0.0]), k,
                                  lambda mu: claret_nonlinear_intensity(mu, CLARET_TESS),
                                  ng=40)[0])
    log(f"  central depth: uniform {1 - cen_u:.6f} (= k^2), Claret {1 - cen_ld:.6f}")
    _check((1.0 - cen_ld) > k * k,
           "limb-darkened central depth is not deeper than k^2 — LD has the wrong sign")

    # Monotonic in k, and flux never exceeds 1.
    depths = []
    for kk in (0.05, 0.10, 0.20, 0.30, 0.40, 0.50):
        f = occultation_ld(np.array([0.0]), kk,
                           lambda mu: claret_nonlinear_intensity(mu, CLARET_TESS))
        _check(f[0] <= 1.0 + 1e-12, f"flux > 1 at k={kk}: {f[0]}")
        depths.append(1.0 - float(f[0]))
    _check(all(b > a for a, b in zip(depths, depths[1:])),
           f"central depth is not monotonic in k: {depths}")
    log(f"  central depths for k=0.05..0.50: "
        + ", ".join(f"{d:.4f}" for d in depths))

    # Grid interpolation vs direct evaluation — the speed shortcut must not
    # cost accuracy at the level the depth is quoted to.
    intensity = lambda mu: claret_nonlinear_intensity(mu, CLARET_TESS)
    table = OccultationTable(k, intensity)
    zt = np.linspace(0.0, 1.0 + k, 3000)
    err = float(np.max(np.abs(table(zt) - occultation_ld(zt, k, intensity))))
    log(f"  interpolated table vs direct: max error {err * 1e6:.2f} ppm")
    _check(err < 2e-5, f"OccultationTable interpolation error {err} is too large")

    # Quadrature convergence: ng=24 (the default) against ng=64.
    zg = np.linspace(0.0, 1.0 + k, 500)
    e2 = float(np.max(np.abs(occultation_ld(zg, k, intensity, ng=24)
                             - occultation_ld(zg, k, intensity, ng=64))))
    log(f"  quadrature ng=24 vs ng=64: max error {e2 * 1e6:.3f} ppm")
    _check(e2 < 1e-6, f"quadrature has not converged at ng=24: {e2}")


def _selftest_batman(log):
    """If batman is installed, the two backends must agree. If not, say so."""
    try:
        import batman  # noqa: F401
    except Exception:
        log("  batman not installed — numpy backend only (this is supported, "
            "not a failure)")
        return
    t = np.linspace(-0.12, 0.12, 900)
    a, b, k, p = 7.7, 0.45, 0.30, 1.9369484
    mn = TransitModel("nonlinear", CLARET_TESS, backend="numpy")
    mb = TransitModel("nonlinear", CLARET_TESS, backend="batman")
    fn = mn(t, 0.0, p, k, a, b)
    fb = mb(t, 0.0, p, k, a, b)
    worst = float(np.max(np.abs(fn - fb)))
    log(f"  batman vs numpy backend: max |diff| = {worst * 1e6:.2f} ppm")
    _check(worst < 5e-5,
           f"numpy and batman backends disagree by {worst}; do not trust either")


def _selftest_geometry(log):
    """Durations and the density inversion, against closed forms."""
    p, k, a, b = 1.9369484, 0.30, 7.71, 0.45
    t14, t23, ing = transit_durations(p, k, a, b)
    # Independent check: measure T14 off the model itself (first/last contact).
    m = TransitModel("uniform", (), backend="numpy")
    t = np.linspace(-0.2, 0.2, 400001)
    f = m(t, 0.0, p, k, a, b)
    inside = t[f < 1.0 - 1e-12]
    measured = (inside.max() - inside.min()) * 24.0
    log(f"  T14 analytic {t14:.6f} h vs measured off the model {measured:.6f} h")
    _check(abs(t14 - measured) < 0.01,
           f"analytic T14 {t14} disagrees with the model's own {measured}")
    _check(t23 < t14 and ing > 0, "T23/ingress geometry is inconsistent")

    rho = density_from_ar(p, a)
    back = ar_from_density(p, rho)
    log(f"  rho(a/R*=7.71, P=1.93695 d) = {rho:.4f} g/cm^3; inverse -> a/R* {back:.6f}")
    _check(abs(back - a) < 1e-9, "density_from_ar and ar_from_density disagree")
    # SPOC's a/R* = 7.71 is quoted in the package as rho = 1.64 (solar units).
    _check(abs(rho / RHO_SUN_CGS - 1.64) < 0.05,
           f"shape density {rho / RHO_SUN_CGS:.3f} rho_sun does not match the "
           "package's 1.64 for SPOC's a/R*")


def _selftest_injection(log, *, seed=20260918, noise_ppm=600.0, n_boot=12):
    """Inject a known transit, fit it blind, and insist on getting it back.

    The tolerances below are stated, not tuned to whatever came out: they are
    what the package needs the fit to be good to. Period to 1e-5 d is 0.9 s,
    a hundred times finer than the O-C drift §5b flags. Rp/R* to 3 % is inside
    SPOC's own 18 % uncertainty. b to 0.08 is what separates 'grazing' from
    'not grazing' on a k = 0.30 transit (the boundary is b = 0.70).

    The injected geometry is deliberately NOT the grazing one. A grazing
    transit is degenerate on purpose — that is the package's own finding — so
    a recovery test there would be testing the degeneracy, not the fitter. The
    grazing case gets its own looser test below.
    """
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model = TransitModel("nonlinear", CLARET_TESS, backend="numpy")

    # Three 27-day sectors with a gap, 10-minute sampling: enough transits to
    # constrain the period over a realistic baseline without a slow selftest.
    rng = np.random.default_rng(seed)
    chunks = []
    for start in (2036.0, 2065.0, 2150.0):
        chunks.append(np.arange(start, start + 24.0, 10.0 / 1440.0))
    t = np.concatenate(chunks)
    clean = model(t, truth["epoch"], truth["period"], truth["k"],
                  truth["a_rstar"], truth["b"])
    sigma = noise_ppm * 1e-6
    f = clean + rng.normal(0.0, sigma, t.size)
    curves = [{"t": t, "f": f, "ferr": np.full_like(f, sigma), "source": "synthetic"}]

    # Start from values deliberately OFF the truth, in the direction and by the
    # amount SPOC's published numbers differ from the lab's, so the test
    # exercises the search rather than the starting point.
    guess = (truth["period"] + 3e-5, truth["epoch"] + 4e-3, 0.38, 6.4, 0.75)
    t14_guess = transit_durations(guess[0], guess[2], guess[3], guess[4])[0]
    tw, fw, ew, nwin = window_and_detrend(curves, guess[0], guess[1],
                                          t14_guess, window_factor=3.0)
    w, sig = weights_from(fw, ew)
    log(f"  injected {nwin} windows, {tw.size} cadences, sigma {sig * 1e6:.0f} ppm")

    best, chi2, n_ld = fit_transit(tw, fw, w, model, guess, restarts=3)
    got = dict(zip(PARAM_NAMES, best[:5]))
    for name in PARAM_NAMES:
        log(f"  {name:<9} injected {truth[name]:.8g}  recovered {got[name]:.8g}"
            f"  delta {got[name] - truth[name]:+.3e}")

    tol = {"period": 1e-5, "epoch": 1e-3, "k": 0.03 * truth["k"],
           "a_rstar": 0.10 * truth["a_rstar"], "b": 0.08}
    for name, lim in tol.items():
        d = abs(got[name] - truth[name])
        _check(d <= lim,
               f"injection-recovery FAILED on {name}: recovered {got[name]:.8g} "
               f"vs injected {truth[name]:.8g} (|delta| {d:.3e} > tol {lim:.3e})")

    red = chi2 / (tw.size - 6)
    log(f"  reduced chi2 {red:.4f} (want ~1 — the noise is exactly Gaussian here)")
    _check(0.85 < red < 1.15, f"reduced chi2 {red} says the fit is not consistent "
                              "with the noise it was given")

    # The error path has to run too, and has to return something sane: a
    # bootstrap error of zero would mean the refits never moved, which is what
    # a silently-broken optimiser looks like.
    draws, errs = bootstrap_errors(tw, fw, w, model, best, n_ld,
                                   n_boot=n_boot, seed=seed + 1, maxiter=400)
    log("  bootstrap sigma: " + ", ".join(
        f"{n}={e:.3e}" for n, e in zip(PARAM_NAMES, errs[:5])))
    _check(np.all(errs[:5] > 0), f"bootstrap returned a zero error: {errs}")
    _check(errs[0] < 1e-4, f"bootstrap period error {errs[0]} is implausibly large")
    # And the truth should sit inside a few sigma of the recovery.
    for i, name in enumerate(PARAM_NAMES):
        pull = abs(got[name] - truth[name]) / max(errs[i], 1e-12)
        log(f"  pull {name:<9} {pull:.2f} sigma")
        _check(pull < 6.0,
               f"{name} is {pull:.1f} bootstrap-sigma from truth — either the "
               "fit is biased or the errors are too small")
    return got


def _selftest_injection_grazing(log, *, seed=20260919, noise_ppm=600.0):
    """The grazing case, with tolerances that admit the degeneracy.

    b = 0.90 with k = 0.43 is SPOC's geometry. Here the fit is NOT expected to
    recover k to 3 %: the package's §5c is an argument about exactly that. What
    the fit must still get right is the ephemeris, and the transit DEPTH, which
    is an observable rather than a parameter. If depth came back wrong, nothing
    downstream would be trustworthy.
    """
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.430, "a_rstar": 7.710, "b": 0.900}
    model = TransitModel("nonlinear", CLARET_TESS, backend="numpy")
    rng = np.random.default_rng(seed)
    t = np.concatenate([np.arange(s, s + 24.0, 10.0 / 1440.0)
                        for s in (2036.0, 2065.0, 2150.0)])
    clean = model(t, truth["epoch"], truth["period"], truth["k"],
                  truth["a_rstar"], truth["b"])
    sigma = noise_ppm * 1e-6
    f = clean + rng.normal(0.0, sigma, t.size)
    curves = [{"t": t, "f": f, "ferr": np.full_like(f, sigma), "source": "synthetic"}]

    truth_depth = transit_depth_ppm(model, truth["period"], truth["k"],
                                    truth["a_rstar"], truth["b"])
    guess = (truth["period"] + 3e-5, truth["epoch"] + 4e-3, 0.33, 9.0, 0.55)
    t14_guess = transit_durations(guess[0], guess[2], guess[3], guess[4])[0]
    tw, fw, ew, _ = window_and_detrend(curves, guess[0], guess[1], t14_guess)
    w, _ = weights_from(fw, ew)
    best, chi2, n_ld = fit_transit(tw, fw, w, model, guess, restarts=3)
    got = dict(zip(PARAM_NAMES, best[:5]))
    depth = transit_depth_ppm(model, got["period"], got["k"],
                              got["a_rstar"], got["b"])
    log(f"  grazing: injected k={truth['k']:.3f} b={truth['b']:.3f} -> "
        f"recovered k={got['k']:.3f} b={got['b']:.3f}")
    log(f"  grazing: injected depth {truth_depth:.1f} ppm -> "
        f"recovered {depth:.1f} ppm")
    _check(abs(got["period"] - truth["period"]) < 2e-5,
           f"grazing case lost the period: {got['period']}")
    _check(abs(got["epoch"] - truth["epoch"]) < 2e-3,
           f"grazing case lost the epoch: {got['epoch']}")
    _check(abs(depth - truth_depth) < 0.03 * truth_depth,
           f"grazing case recovered depth {depth:.1f} ppm vs injected "
           f"{truth_depth:.1f} ppm — more than 3 % off")
    _check(got["b"] > 1.0 - got["k"] - 0.10,
           f"grazing case returned a non-grazing geometry (b={got['b']:.3f}, "
           f"k={got['k']:.3f}) — the shape information was lost")
    log("  (k itself is NOT asserted here: the grazing degeneracy is the "
        "package's own finding, not a bug to tune away)")


def _selftest_stellar_pipeline(log):
    """The star block end to end, on this target's own inputs."""
    kmag = float(DEFAULT_ABS_KMAG) - 5.0 * math.log10(DEFAULT_PARALLAX_MAS / 100.0)
    star = stellar_parameters(kmag, DEFAULT_KMAG_ERR, DEFAULT_PARALLAX_MAS,
                              DEFAULT_PARALLAX_ERR_MAS, n_mc=4000)
    log(f"  K={kmag:.4f} -> M_K={star['abs_kmag']:.4f}, "
        f"R*={star['rstar_sun']:.4f}+/-{star['rstar_sun_err']:.4f}, "
        f"M*={star['mstar_sun']:.4f}+/-{star['mstar_sun_err']:.4f}")
    _check(abs(star["abs_kmag"] - DEFAULT_ABS_KMAG) < 1e-6,
           "the default K magnitude does not round-trip to M_K = 4.98")
    _check(abs(star["rstar_sun"] - SPOC_DV["rstar_sun"]) < 0.002,
           "the derived R* does not reproduce TIC v8's value on TIC v8's input")
    _check(star["rstar_sun_err"] / star["rstar_sun"] > 0.02,
           "the R* error is smaller than the relation's own 2.89 % scatter — "
           "the calibration scatter has gone missing")
    _check(star["in_range_mann15"] and star["in_range_mann19"],
           "M_K fell outside a relation's calibrated range")


def selftest(verbose=True) -> int:
    """Everything that can be checked without a network or a photon.

    Returns a process exit code: 0 for pass, 1 for any failure.
    """
    def log(msg):
        if verbose:
            print(msg)

    blocks = [
        ("Mann relations vs hand-computed values", _selftest_mann),
        ("limb-darkening normalisation vs closed forms", _selftest_ld_norm),
        ("occultation model vs Mandel & Agol closed form", _selftest_occultation),
        ("batman backend cross-check", _selftest_batman),
        ("transit geometry and density inversion", _selftest_geometry),
        ("stellar pipeline on this target's inputs", _selftest_stellar_pipeline),
        ("injection-recovery, non-grazing", _selftest_injection),
        ("injection-recovery, grazing (SPOC geometry)", _selftest_injection_grazing),
    ]
    failures = []
    for i, (name, func) in enumerate(blocks, start=1):
        log(f"\n[{i}/{len(blocks)}] {name}")
        try:
            func(log)
            log("  PASS")
        except AssertionError as exc:
            log(f"  FAIL: {exc}")
            failures.append((name, str(exc)))
        except Exception as exc:  # an error is a failure, not a skip
            log(f"  ERROR: {type(exc).__name__}: {exc}")
            failures.append((name, f"{type(exc).__name__}: {exc}"))

    log("\n" + "=" * 78)
    if failures:
        log(f"SELFTEST FAILED — {len(failures)} of {len(blocks)} blocks")
        for name, msg in failures:
            log(f"  - {name}: {msg}")
        log("=" * 78)
        return 1
    log(f"SELFTEST PASSED — {len(blocks)}/{len(blocks)} blocks")
    log("Nothing above touched the network or any real data. A pass means the")
    log("machinery recovers what it is given; it says nothing about TIC "
        f"{TIC}.")
    log("=" * 78)
    return 0


# ------------------------------------------------------------------ main --


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=("Limb-darkened transit refit + Gaia-anchored stellar "
                     f"radius for TIC {TIC}."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run --selftest first. It needs no network and no data.")
    p.add_argument("--selftest", action="store_true",
                   help="inject a known transit, fit it, and check the Mann "
                        "relations; exits nonzero on failure")
    p.add_argument("--tic", default=TIC)
    p.add_argument("--fits-dir", type=Path, default=None,
                   help="directory of already-downloaded TESS SPOC *_lc.fits "
                        "files; skips all network access")
    p.add_argument("--max-sectors", type=int, default=None,
                   help="cap how many sectors lightkurve downloads")
    p.add_argument("--chain", type=Path, default=None,
                   help="write the joint MCMC samples to this .npz (the k-b "
                        "degeneracy needs the joint posterior, not marginals)")
    p.add_argument("--exptime", type=int, default=120,
                   help="cadence to request from MAST, seconds (default 120)")

    g = p.add_argument_group("transit model")
    g.add_argument("--ld-law", choices=sorted(LD_LAWS), default="nonlinear")
    g.add_argument("--ld-coeffs", default=None,
                   help="comma-separated limb-darkening coefficients; default "
                        "is the Claret TESS set SPOC's DV fit used")
    g.add_argument("--free-ld", action="store_true",
                   help="fit the limb-darkening coefficients too (degenerate "
                        "on a grazing transit — read the warning it prints)")
    g.add_argument("--backend", choices=("auto", "batman", "numpy"), default="auto")
    g.add_argument("--exact", action="store_true",
                   help="evaluate the occultation integral at every cadence "
                        "instead of interpolating a z-grid (slower, ~20 ppm "
                        "more accurate)")
    g.add_argument("--nz", type=int, default=600, help="z-grid size")
    g.add_argument("--ng", type=int, default=24, help="Gauss-Legendre order")
    g.add_argument("--supersample", type=int, default=1,
                   help="finite-exposure supersampling; leave at 1 for 2-min "
                        "data, use 7 or so for 30-min FFI cadence")

    g = p.add_argument_group("starting guess (defaults are SPOC's DV fit)")
    g.add_argument("--period", type=float, default=SPOC_DV["period_days"])
    g.add_argument("--epoch", type=float, default=SPOC_DV["epoch_btjd"],
                   help="BTJD")
    g.add_argument("--k", type=float, default=SPOC_DV["rp_rstar"])
    g.add_argument("--a-rstar", type=float, default=7.71)
    g.add_argument("--b", type=float, default=SPOC_DV["b"])
    g.add_argument("--window-factor", type=float, default=3.0)
    g.add_argument("--poly-order", type=int, default=1,
                   help="order of the per-window out-of-transit baseline")
    g.add_argument("--restarts", type=int, default=3)
    g.add_argument("--maxiter", type=int, default=6000)

    g = p.add_argument_group("uncertainties")
    g.add_argument("--errors", choices=("bootstrap", "prayerbead", "mcmc", "none"),
                   default="bootstrap")
    g.add_argument("--nboot", type=int, default=200)
    g.add_argument("--nwalkers", type=int, default=32)
    g.add_argument("--nsteps", type=int, default=4000)
    g.add_argument("--burn", type=int, default=1500)
    g.add_argument("--seed", type=int, default=20260918)

    g = p.add_argument_group("host star")
    g.add_argument("--kmag", type=float, default=None,
                   help="2MASS Ks. DEFAULT IS BACK-DERIVED, not a catalogue "
                        "lookup — see the module docstring")
    g.add_argument("--kmag-err", type=float, default=DEFAULT_KMAG_ERR)
    g.add_argument("--parallax", type=float, default=DEFAULT_PARALLAX_MAS,
                   help="mas")
    g.add_argument("--parallax-err", type=float, default=DEFAULT_PARALLAX_ERR_MAS)
    g.add_argument("--ak", type=float, default=0.0,
                   help="K-band extinction, mag. At 222 pc out of the plane "
                        "this is ~0.01-0.03; 0 is the honest default and its "
                        "effect on R* is +0.5 %% per 0.01 mag")

    p.add_argument("--json", type=Path, default=None,
                   help="write the full result as JSON")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest(verbose=not args.quiet)

    def log(msg=""):
        if not args.quiet:
            print(msg)

    # -- limb darkening -----------------------------------------------------
    if args.ld_coeffs:
        coeffs = tuple(float(x) for x in args.ld_coeffs.split(","))
    elif args.ld_law == "nonlinear":
        coeffs = CLARET_TESS
    elif args.ld_law == "quadratic":
        raise SystemExit("--ld-law quadratic needs --ld-coeffs u1,u2 (no "
                         "quadratic set is published for this host here)")
    else:
        coeffs = ()
    _, n_expected = LD_LAWS[args.ld_law]
    if len(coeffs) != n_expected:
        raise SystemExit(f"--ld-law {args.ld_law} wants {n_expected} "
                         f"coefficients, got {len(coeffs)}")
    if args.free_ld:
        log("WARNING: --free-ld frees the limb-darkening coefficients. On a\n"
            "  grazing transit the limb is the only part of the star the planet\n"
            "  ever crosses, so these trade directly against b and k and the\n"
            "  quoted errors will be optimistic. Compare against the fixed-LD\n"
            "  run before reporting either.")

    model = TransitModel(args.ld_law, coeffs, backend=args.backend,
                         exact=args.exact, nz=args.nz, ng=args.ng,
                         supersample=args.supersample,
                         exp_time_days=args.exptime / 86400.0)
    log(f"transit model backend: {model.backend}"
        + ("" if model.backend == "batman"
           else "  (pip install batman-package for the analytic model; the "
                "numpy integrator here is checked against it in --selftest)"))

    # -- host star ----------------------------------------------------------
    kmag = args.kmag
    if kmag is None:
        kmag = float(DEFAULT_ABS_KMAG) - 5.0 * math.log10(args.parallax / 100.0)
        log(f"\nWARNING: no --kmag given. Using K = {kmag:.4f}, which is BACK-\n"
            f"  DERIVED from the CTOI package's M_K = {DEFAULT_ABS_KMAG} and the\n"
            "  parallax, NOT read from 2MASS. It reproduces TIC v8's input; it is\n"
            "  not an independent measurement. Pass the real 2MASS Ks before\n"
            "  publishing anything that depends on R*.")
    star = stellar_parameters(kmag, args.kmag_err, args.parallax,
                              args.parallax_err, extinction=args.ak,
                              seed=args.seed)

    # -- data ---------------------------------------------------------------
    log("")
    if args.fits_dir:
        log(f"reading FITS from {args.fits_dir} (no network)")
        curves = load_from_dir(args.fits_dir)
    else:
        curves = load_from_lightkurve(args.tic, exptime=args.exptime,
                                      max_sectors=args.max_sectors,
                                      progress=log)
    n_pts = sum(c["t"].size for c in curves)
    log(f"  {len(curves)} light curves, {n_pts} good cadences, "
        f"BTJD {min(c['t'].min() for c in curves):.3f} to "
        f"{max(c['t'].max() for c in curves):.3f}")
    # The coverage the paper quotes has to be derived, not typed. The 2026-09-18
    # run reported "24 sectors (27-97)" and nothing recorded which 24 -- the
    # range label was a human summary, and its top end does not survive
    # arithmetic on the DV baseline. Print the list and ship it in the JSON.
    coverage = sector_coverage(curves)
    log(f"  sectors ({len(coverage['sectors'])}): "
        + (", ".join(str(x) for x in coverage["sectors"])
           if coverage["sectors"] else "UNKNOWN - no SECTOR keyword in these products"))
    if coverage["unknown"]:
        log(f"  WARNING: {coverage['unknown']} light curve(s) carry no SECTOR "
            f"keyword; the list above is incomplete, do not quote it")

    guess = (args.period, args.epoch, args.k, args.a_rstar, args.b)
    t14_guess = transit_durations(*[guess[0], guess[2], guess[3], guess[4]])[0]
    if not np.isfinite(t14_guess):
        t14_guess = SPOC_DV["duration_hours"]
    t, f, ferr, n_windows = window_and_detrend(
        curves, guess[0], guess[1], t14_guess,
        window_factor=args.window_factor, poly_order=args.poly_order)
    w, sigma = weights_from(f, ferr)
    log(f"  {n_windows} transit windows kept, {t.size} cadences in the fit, "
        f"per-point sigma {sigma * 1e6:.0f} ppm")

    # -- fit ----------------------------------------------------------------
    log("\nfitting…")
    best, chi2, n_ld = fit_transit(t, f, w, model, guess, free_ld=args.free_ld,
                                   maxiter=args.maxiter, restarts=args.restarts)
    log("  " + ", ".join(f"{n}={v:.8g}" for n, v in zip(PARAM_NAMES, best[:5])))

    # -- errors -------------------------------------------------------------
    errs = None
    chain = None
    if args.errors == "mcmc":
        log(f"\nsampling ({args.nwalkers} walkers x {args.nsteps} steps)…")
        chain, errs = mcmc_errors(t, f, w, model, best, n_ld,
                                  nwalkers=args.nwalkers, nsteps=args.nsteps,
                                  burn=args.burn, seed=args.seed, progress=log)
    elif args.errors in ("bootstrap", "prayerbead"):
        log(f"\n{args.errors} errors, {args.nboot} realisations…")
        chain, errs = bootstrap_errors(t, f, w, model, best, n_ld,
                                       n_boot=args.nboot, seed=args.seed,
                                       method=("prayerbead"
                                               if args.errors == "prayerbead"
                                               else "residual"),
                                       progress=log)
        if args.errors == "bootstrap":
            log("  NOTE: i.i.d. residual resampling. TESS residuals are\n"
                "  correlated on ingress timescales, so these are LOWER LIMITS.\n"
                "  Re-run with --errors prayerbead before quoting them.")

    fit = summarise(best, errs, n_ld, model, star, chi2=chi2, ndata=t.size,
                    backend=model.backend)
    fit["n_windows"] = int(n_windows)
    fit["n_cadences"] = int(t.size)
    fit["error_method"] = args.errors
    fit["sigma_ppm"] = float(sigma * 1e6)

    print_summary(fit, star)

    if args.json:
        payload = {
            "tic": args.tic,
            "generated_by": "scripts/tic374861595_refit.py",
            "fit": fit,
            "star": star,
            "comparison": {"lab_trapezoid": LAB_TRAPEZOID, "spoc_dv": SPOC_DV},
            "coverage": coverage,
            "inputs": {k_: (str(v) if isinstance(v, Path) else v)
                       for k_, v in vars(args).items()},
        }
        if chain is not None:
            payload["fit"]["posterior_percentiles"] = {
                name: [float(x) for x in np.percentile(chain[:, i], [16, 50, 84])]
                for i, name in enumerate(PARAM_NAMES)}
            # Marginals are not a joint posterior, and the joint is exactly what
            # the k-b degeneracy argument needs: at b ~ 1 the two trade off hard,
            # so "k = 0.54 +0.11/-0.10" read alone overstates how determined the
            # radius is. Ship the samples so the valley can be plotted.
            if args.chain:
                args.chain.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(args.chain, names=np.array(PARAM_NAMES),
                                    samples=chain.astype(np.float64))
                log(f"wrote {args.chain}  ({chain.shape[0]:,} x "
                    f"{chain.shape[1]} joint samples)")
            else:
                payload["fit"]["posterior_note"] = (
                    "16/50/84 marginals only; pass --chain to write the joint "
                    "samples the k-b degeneracy argument needs")
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        log(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    warnings.simplefilter("once")
    try:
        sys.exit(main())
    except RefitError as exc:
        # A RefitError is a refusal, not a crash: the script has decided it
        # cannot produce an honest number. Print it as the sentence it is and
        # exit 2, so a caller can tell "refused" from "blew up" (1) and from
        # "fine" (0).
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        sys.exit(2)
