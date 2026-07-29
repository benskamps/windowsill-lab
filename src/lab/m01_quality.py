"""Shared quality assessment for the M01 Ising temperature sweep.

The M01 checker has long known how to spot a metastable, non-equilibrated
sample.  This small stdlib-only module makes that same decision available to
the renderer, public feed, archive, and browser so they cannot disagree about
which susceptibility peak is scientifically usable.
"""
from __future__ import annotations

import math

EQUIL_SIGMA = 5.0
EQUIL_MAX_EXCLUDED = 2


def nonequilibrated_indices(report: dict) -> list[int]:
    """Return samples whose rising |M|(T) proves they did not equilibrate.

    Equilibrium |M| is non-increasing with temperature.  When an adjacent rise
    exceeds ``EQUIL_SIGMA`` combined standard errors, the noisier endpoint is
    treated as the wandering/metastable sample.  Missing legacy uncertainty
    arrays deliberately produce no exclusions.
    """
    T = report.get("T")
    mag = report.get("abs_mag")
    err = report.get("abs_mag_err")
    if not all(isinstance(values, (list, tuple)) for values in (T, mag, err)):
        return []
    if not T or not (len(T) == len(mag) == len(err)):
        return []

    bad: set[int] = set()
    try:
        for i in range(len(T) - 1):
            left_err = float(err[i] or 0.0)
            right_err = float(err[i + 1] or 0.0)
            rise = float(mag[i + 1]) - float(mag[i])
            sigma = math.hypot(left_err, right_err)
            if not all(math.isfinite(v) for v in (left_err, right_err, rise, sigma)):
                continue
            if sigma > 0 and rise / sigma > EQUIL_SIGMA:
                bad.add(i if left_err >= right_err else i + 1)
    except (TypeError, ValueError, OverflowError):
        return []
    return sorted(bad)


def assess_m01_quality(report: dict) -> dict:
    """Return the canonical quality state and usable susceptibility peak.

    ``status`` is ``ok`` for a clean sweep, ``degraded`` when one or two
    disclosed samples were excluded, and ``invalid`` when a peak must not be
    claimed.  The returned indices are JSON-ready lists so this dict can ride
    directly in ``physics-latest.json``.
    """
    T = report.get("T")
    chi = report.get("chi")
    invalid = {
        "status": "invalid",
        "excluded_indices": [],
        "valid_indices": [],
        "peak_index": None,
        "peak_t": None,
        "note": "invalid χ sweep — no T_c claimed",
    }
    if not isinstance(T, (list, tuple)) or not isinstance(chi, (list, tuple)):
        return invalid
    if not T or len(T) != len(chi):
        return invalid

    try:
        T_values = [float(value) for value in T]
        chi_values = [float(value) for value in chi]
    except (TypeError, ValueError, OverflowError):
        return invalid
    if not all(math.isfinite(value) for value in (*T_values, *chi_values)):
        return invalid

    excluded = nonequilibrated_indices(report)
    valid = [i for i in range(len(T_values)) if i not in set(excluded)]
    if len(excluded) > EQUIL_MAX_EXCLUDED:
        return {
            **invalid,
            "excluded_indices": excluded,
            "valid_indices": valid,
            "note": (
                f"sweep not equilibrated: {len(excluded)} of {len(T_values)} "
                f"samples failed the {EQUIL_SIGMA:g}σ monotonic-|M| guard — "
                "no T_c claimed"
            ),
        }
    if not valid:
        return {
            **invalid,
            "excluded_indices": excluded,
            "note": "sweep not equilibrated: no usable samples — no T_c claimed",
        }

    peak_index = max(valid, key=lambda i: chi_values[i])
    status = "degraded" if excluded else "ok"
    if excluded:
        where = ", ".join(f"T={T_values[i]:.3f}" for i in excluded)
        note = (
            f"{len(excluded)} non-equilibrated sample(s) excluded by the "
            f"{EQUIL_SIGMA:g}σ monotonic-|M| guard ({where})"
        )
    else:
        note = "all susceptibility samples passed the equilibrium guard"
    return {
        "status": status,
        "excluded_indices": excluded,
        "valid_indices": valid,
        "peak_index": peak_index,
        "peak_t": T_values[peak_index],
        "note": note,
    }
