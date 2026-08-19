"""Is the thing that made this eclipse small enough to be a planet?

Every gate before this one asks a question about the *light curve*: does the
depth alternate, is there a secondary, did the centroid move, is the star
pulsating. None of them asks the simplest question a human asks first — **how
big is the occulting body?** TIC 287328866 walked the whole ladder as a
`planet-candidate` while implying a companion of ≥ 3.1 R_Jup around an F
subgiant. Nothing in the pipeline was looking.

The arithmetic is one line. A body of radius ``R_c`` transiting a star of radius
``R_*`` blocks ``(R_c / R_*)²`` of its light, so

    R_c = R_* · √(depth)

and the only inputs are a depth this pipeline already measures and a stellar
radius SPOC already copied from the TESS Input Catalog into the light curve's
own PRIMARY header (``lab.a01.PRIMARY_KEYWORDS``). No second catalog, no network,
nothing that can be down.

### The crowding correction is load-bearing here, and it cuts both ways

The observed depth is diluted by every other star in the aperture. CROWDSAP is
the fraction of aperture flux belonging to the target, so ``depth / CROWDSAP`` is
the depth the eclipse would have had on the target alone — the number to use
IF the target is the eclipsing star. That "if" is exactly what the centroid gate
exists to test, which is why :func:`companion_radius` reports the corrected and
uncorrected radii separately and grades on the **uncorrected** one by default.

Grading on the uncorrected radius is the conservative choice, and conservative
here means *reluctant to refute*: correcting always makes the companion look
bigger, so a gate that graded the corrected number would refute more candidates
on the strength of a catalog model rather than a measurement. On a heavily
blended target the corrected number is reported loudly and left to the human.

### What "too big" means

``MAX_PLANET_R_SUN`` is set at 2.5 Jupiter radii. Degenerate-body physics puts
the radius of anything from Saturn to the hydrogen-burning limit within roughly
0.8–1.3 R_Jup — mass buys almost no radius once electron degeneracy sets in —
and the largest inflated hot Jupiters known reach about 2 R_Jup. So 2.5 R_Jup is
not a knife edge: it is well above anything the planet population reaches, and
a body measured past it is stellar or the depth is wrong. Both of those are
reasons to take a candidate off the shelf.

### Calibration against a known planet, and the systematic it exposes

WASP-18 b is in the cache and its radius is published: 1.19 R_Jup. Run this gate
on the blind detection's depth for TIC 100100827 and it returns **1.27 R_Jup** —
about 7 % high. That is not noise, it is the estimator: the depth this pipeline
measures is a *box-fit mean depth* on a limb-darkened transit, and a limb-darkened
star is brightest at the centre of the disc, so a body crossing it blocks more
than its geometric share of the light. The measured depth therefore exceeds
``(R_c/R_*)²`` and every radius here runs high by roughly the same margin.

The consequence is stated rather than corrected: the effective bar is nearer
2.3 R_Jup in true radius than the 2.5 written in the constant, and the error
runs in the direction of refuting *more*, not fewer, candidates. That is the
wrong direction for a conservative gate, which is why the margin above the
planet population (2 R_Jup) matters and why the constant is not set tighter.
Correcting it properly means fitting a limb-darkened transit model instead of a
box — a real upgrade, not a coefficient, and not done here.

### What this gate cannot do

It cannot fire without a radius. Faint or unclassified targets carry no RADIUS
keyword (TIC 77044472, T = 15.8, is a live example), and an unknown radius is
not a small one: the gate returns ``None`` with a reason, exactly like the
centroid gate on a file with no centroid columns. It also cannot promote
anything — a companion small enough to be a planet is not evidence that it *is*
one, and this module never emits a positive verdict.
"""
from __future__ import annotations

import math

#: Jupiter's radius in solar radii (IAU 2015 nominal: 7.1492e7 m / 6.957e8 m).
R_JUP_IN_R_SUN = 7.1492e7 / 6.957e8

#: Largest companion radius still admissible as a planet. See module docstring:
#: 2.5 R_Jup sits well clear of the inflated-hot-Jupiter population near 2.
MAX_PLANET_R_SUN = 2.5 * R_JUP_IN_R_SUN

#: Below this CROWDSAP the corrected radius is reported with a flag: more than
#: half the aperture flux belongs to something else, so the correction is large
#: and model-dependent enough that a reader must see it. Matches the spirit of
#: ``a05_vetting.CROWDSAP_MIN`` but at a harsher level, because this is where a
#: correction changes a physical conclusion rather than a reported number.
CROWDSAP_SEVERE = 0.5


def companion_radius(depth: float, r_star_sun, crowdsap=None) -> dict:
    """Radius of the occulting body, from the depth and the host's radius.

    Returns both the uncorrected radius (graded) and the crowding-corrected one
    (reported), each in solar radii and Jupiter radii, plus the verdict
    `companion-too-large` when the graded radius exceeds MAX_PLANET_R_SUN.

    A missing or non-positive stellar radius disables the gate: verdict ``None``
    with a reason. A missing radius is not a small radius.
    """
    out: dict = {"verdict": None, "r_star_sun": None,
                 "r_companion_sun": None, "r_companion_jup": None,
                 "r_companion_corrected_sun": None,
                 "r_companion_corrected_jup": None,
                 "crowdsap": None, "severely_blended": False, "reason": None}
    try:
        depth = float(depth)
    except (TypeError, ValueError):
        out["reason"] = "no-depth"
        return out
    if not (depth > 0) or depth >= 1.0:
        out["reason"] = "depth-out-of-range"
        return out
    if r_star_sun is None:
        out["reason"] = "no-stellar-radius"
        return out
    try:
        r_star = float(r_star_sun)
    except (TypeError, ValueError):
        out["reason"] = "no-stellar-radius"
        return out
    if not (r_star > 0) or not math.isfinite(r_star):
        out["reason"] = "no-stellar-radius"
        return out

    out["r_star_sun"] = r_star
    r_c = r_star * math.sqrt(depth)
    out["r_companion_sun"] = r_c
    out["r_companion_jup"] = r_c / R_JUP_IN_R_SUN

    if crowdsap is not None:
        try:
            c = float(crowdsap)
        except (TypeError, ValueError):
            c = 0.0
        if 0.0 < c <= 1.0:
            corrected = depth / c
            out["crowdsap"] = c
            out["severely_blended"] = bool(c < CROWDSAP_SEVERE)
            if corrected < 1.0:
                r_cc = r_star * math.sqrt(corrected)
                out["r_companion_corrected_sun"] = r_cc
                out["r_companion_corrected_jup"] = r_cc / R_JUP_IN_R_SUN
            else:
                # A corrected depth at or above unity is not a body at all —
                # the target cannot lose more light than it has. Reported as
                # such rather than as a radius, because it means the eclipse
                # belongs to a neighbour and the crowding model is being asked
                # a question it cannot answer.
                out["corrected_depth_exceeds_unity"] = float(corrected)

    if r_c > MAX_PLANET_R_SUN:
        out["verdict"] = "companion-too-large"
    return out


def admissibility(depth: float, curve_keywords: dict) -> dict:
    """:func:`companion_radius` fed straight from a light curve's own keywords.

    ``curve_keywords`` is the dict :func:`lab.a01.read_tess_light_curve` returns
    with ``ancillary=True`` — RADIUS and CROWDSAP live there. Separated from the
    arithmetic so the physics is testable without a FITS file anywhere near it.
    """
    return companion_radius(depth,
                            (curve_keywords or {}).get("RADIUS"),
                            (curve_keywords or {}).get("CROWDSAP"))
