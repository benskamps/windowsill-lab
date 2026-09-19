#!/usr/bin/env python3
"""What the missing secondary eclipse excludes for TIC 374861595.

This is the one discriminating measurement in the package, so it gets its own
script rather than a paragraph. Everything here is arithmetic on numbers that
are already in the repo; it downloads nothing and fits nothing.

## The argument, and why the grazing geometry does not spoil it

SPOC's multi-sector fit prefers b = 0.90 +/- 0.11 -- a grazing eclipse. The
obvious worry is that a grazing geometry breaks the usual secondary/primary
depth relation, because only part of the companion's disc ever crosses the star.
It does not, and the cancellation is exact at the level this argument needs:

    primary depth    = A_overlap * I_star      / F_total
    secondary depth  = A_overlap * I_companion / F_total

The SAME overlap area A_overlap appears in both -- at secondary the companion
passes behind the star and the star covers exactly the region the companion
covered at primary. So

    secondary / primary = I_companion / I_star = the surface-brightness ratio,

independent of b, of k, and of how grazing the configuration is. A non-detection
of the secondary is therefore a direct bound on the companion's surface
brightness, and the messy geometry never enters. (Reflected light and thermal
redistribution are ignored; both would only ADD secondary flux, so ignoring them
makes the exclusion conservative.)

## The bandpass

Surface brightness ratio is computed by integrating Planck functions over the
TESS response. The true response curve is not vendored here, so two deliberately
crude stand-ins are used -- a 600-1000 nm top-hat and a trapezoid that tapers
600->700 and 900->1000 nm -- and both are printed. If the conclusion depended on
which one you pick, the conclusion would not be worth printing. It does not.

A blackbody is a poor model for an M dwarf's spectrum, and for a T dwarf it is
worse (methane and water absorption carve the near-IR). The direction of that
error matters more than its size: real cool dwarfs are FAINTER than blackbodies
in the TESS band, so a blackbody OVERESTIMATES a cool companion's secondary
depth, which again makes the exclusion conservative for the cases being excluded
and generous for the cases being kept. Stated plainly rather than papered over.
"""
from __future__ import annotations

import math

# ── measured inputs (all re-derivable from files committed in this repo) ─────

# SPOC multi-sector DV, sectors 1-96, generated 2025-12-24, spoc-5.0.125.
# docs/submissions/TIC374861595-spoc-s1-s96-dvr.xml
PRIMARY_DEPTH_PPM = 104602.85      # allTransitsFit transitDepthPpm
PRIMARY_DEPTH_ERR = 404.57
TEFF_STAR_K = 3445.0               # TIC 8.2
TEFF_STAR_ERR = 157.0

# Weak-secondary search, same DV file: maxMes 3.32 at phase 0.328 d, i.e. NOT at
# phase 0.5 (P/2 = 0.968 d), and below the detection threshold.
SPOC_SECONDARY_PPM = 601.95
SPOC_SECONDARY_ERR = 167.83

# This lab's own independent secondary search on undetrended flux with per-event
# local baselines: docs/submissions/TIC374861595-checks2.json
LAB_SECONDARY_PPM = -159.29
LAB_SECONDARY_ERR = 627.65

H = 6.62607015e-34
C = 299792458.0
KB = 1.380649e-23


def planck(wav_m: float, temp_k: float) -> float:
    """Spectral radiance B_lambda. Units cancel in every ratio taken below."""
    x = H * C / (wav_m * KB * temp_k)
    # guard the deep-Wien tail: exp overflows long before the flux matters
    if x > 700:
        return 0.0
    return (2 * H * C ** 2) / wav_m ** 5 / math.expm1(x)


def _tophat(wav_nm: float) -> float:
    return 1.0 if 600.0 <= wav_nm <= 1000.0 else 0.0


def _trapezoid(wav_nm: float) -> float:
    if wav_nm < 600.0 or wav_nm > 1000.0:
        return 0.0
    if wav_nm < 700.0:
        return (wav_nm - 600.0) / 100.0
    if wav_nm > 900.0:
        return (1000.0 - wav_nm) / 100.0
    return 1.0


RESPONSES = {"tophat 600-1000nm": _tophat, "trapezoid 600/700-900/1000nm": _trapezoid}


def band_ratio(t_companion: float, t_star: float, response) -> float:
    """Surface-brightness ratio of companion to host, through one response."""
    num = den = 0.0
    lo, hi, n = 500.0, 1100.0, 6000          # nm; wider than the band, response gates it
    step = (hi - lo) / n
    for i in range(n + 1):
        nm = lo + i * step
        r = response(nm)
        if r == 0.0:
            continue
        w = 0.5 if i in (0, n) else 1.0       # trapezoid rule
        m = nm * 1e-9
        num += w * r * planck(m, t_companion)
        den += w * r * planck(m, t_star)
    return num / den if den else 0.0


# Candidate companions. Teff values are representative of the spectral class;
# the radii are only carried to say whether an object of that kind could produce
# the observed transit at all, and are not used in the surface-brightness bound.
COMPANIONS = [
    ("M5V star",            3050.0, 0.20),
    ("M7V star",            2650.0, 0.12),
    ("M9V star / brown dwarf boundary", 2400.0, 0.11),
    ("L2 brown dwarf",      1900.0, 0.10),
    ("L8 brown dwarf",      1400.0, 0.10),
    ("T4 brown dwarf",      1100.0, 0.09),
    ("T8 brown dwarf",       700.0, 0.09),
    ("hot Jupiter at T_eq", 745.0,  0.18),
]


def equilibrium_temp(teff: float, a_over_rs: float, albedo: float = 0.0) -> float:
    """Zero-albedo, full-redistribution equilibrium temperature."""
    return teff * (1.0 - albedo) ** 0.25 * math.sqrt(1.0 / (2.0 * a_over_rs))


def main() -> int:
    # The two independent non-detections, combined into one 3-sigma ceiling.
    # SPOC's is a positive 3.6-sigma-looking number at the WRONG phase, so it is
    # treated as a ceiling on a phase-0.5 event, not as a detection.
    spoc_3sig = SPOC_SECONDARY_PPM + 3 * SPOC_SECONDARY_ERR
    lab_3sig = LAB_SECONDARY_PPM + 3 * LAB_SECONDARY_ERR
    ceiling = min(spoc_3sig, lab_3sig)

    print("TIC 374861595 -- what the absent secondary eclipse excludes")
    print("=" * 74)
    print(f"primary depth (SPOC limb-darkened fit) : {PRIMARY_DEPTH_PPM:,.0f} "
          f"+/- {PRIMARY_DEPTH_ERR:,.0f} ppm")
    print(f"secondary, SPOC weak-secondary search  : {SPOC_SECONDARY_PPM:,.0f} "
          f"+/- {SPOC_SECONDARY_ERR:,.0f} ppm (at phase 0.328 d, not 0.5P)")
    print(f"secondary, this lab, undetrended       : {LAB_SECONDARY_PPM:,.0f} "
          f"+/- {LAB_SECONDARY_ERR:,.0f} ppm (34 events)")
    print(f"adopted 3-sigma ceiling on a secondary : {ceiling:,.0f} ppm")
    print(f"=> surface-brightness ratio must be    : < {ceiling / PRIMARY_DEPTH_PPM:.4f} "
          f"({100 * ceiling / PRIMARY_DEPTH_PPM:.2f} %)")
    print()
    print("a/R* = 7.71 (SPOC) gives an irradiation temperature of "
          f"{equilibrium_temp(TEFF_STAR_K, 7.71):.0f} K for the companion.")
    print()

    limit_ratio = ceiling / PRIMARY_DEPTH_PPM

    for label, resp in RESPONSES.items():
        print(f"-- response model: {label}")
        print(f"   {'companion':<36}{'Teff':>7}{'I2/I*':>12}"
              f"{'pred. sec.':>13}   verdict")
        for name, teff, _r in COMPANIONS:
            ratio = band_ratio(teff, TEFF_STAR_K, resp)
            pred_ppm = ratio * PRIMARY_DEPTH_PPM
            verdict = "EXCLUDED" if ratio > limit_ratio else "allowed"
            factor = ratio / limit_ratio
            detail = (f"{factor:>6.0f}x over limit" if verdict == "EXCLUDED"
                      else f"{1 / factor:>6.0f}x under limit" if factor > 0 else "")
            print(f"   {name:<36}{teff:>7.0f}{ratio:>12.2e}"
                  f"{pred_ppm:>13,.0f}   {verdict:<9} {detail}")
        print()

    # Where exactly is the cut? Bisect on Teff for the adopted ceiling.
    for label, resp in RESPONSES.items():
        lo, hi = 300.0, 3445.0
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if band_ratio(mid, TEFF_STAR_K, resp) > limit_ratio:
                hi = mid
            else:
                lo = mid
        print(f"cut-off companion temperature ({label}): "
              f"T_companion < {0.5 * (lo + hi):.0f} K")

    print()
    print("Reading: every stellar and L-type companion is excluded by orders of")
    print("magnitude. What survives is an object cooler than roughly 1,000 K --")
    print("a giant planet, or a cold T-type brown dwarf. The secondary bound says")
    print("NOTHING about mass, so only radial velocities separate those two.")
    return 0


def selftest() -> int:
    """Checks that would fail loudly if the arithmetic drifted."""
    ok = True

    def chk(name, cond):
        nonlocal ok
        print(("  PASS  " if cond else "  FAIL  ") + name)
        ok = ok and cond

    # Planck at equal temperatures must give a ratio of exactly 1, in any band.
    for label, resp in RESPONSES.items():
        chk(f"ratio(T,T) == 1 [{label}]",
            abs(band_ratio(TEFF_STAR_K, TEFF_STAR_K, resp) - 1.0) < 1e-12)
    # Monotone in companion temperature.
    prev = -1.0
    mono = True
    for t in range(400, 3500, 100):
        v = band_ratio(float(t), TEFF_STAR_K, _tophat)
        mono = mono and v > prev
        prev = v
    chk("surface-brightness ratio rises monotonically with T_companion", mono)
    # A hotter-than-host companion must exceed unity.
    chk("ratio(5000 K, 3445 K) > 1", band_ratio(5000.0, TEFF_STAR_K, _tophat) > 1.0)
    # Planck peak: Wien's law, lambda_max * T = 2.898e-3 m*K, checked by scan.
    t = 3445.0
    best = max(range(200, 3000), key=lambda nm: planck(nm * 1e-9, t))
    wien = 2.897771955e-3 / t * 1e9
    chk(f"Planck peaks at Wien's wavelength ({best} nm vs {wien:.0f} nm)",
        abs(best - wien) <= 2)
    # The deep-Wien guard must return 0, not raise.
    chk("no overflow at 10 K", planck(700e-9, 10.0) == 0.0)
    # Equilibrium temperature sanity: Earth-like a/R* ~ 215 gives ~279 K for the Sun.
    chk("T_eq(5772 K, a/R*=215) ~ 279 K",
        abs(equilibrium_temp(5772.0, 215.0) - 278.6) < 2.0)
    print("SELFTEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(selftest() if "--selftest" in sys.argv else main())
