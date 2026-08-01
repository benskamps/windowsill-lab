"""Shared quality assessment for the M01 Ising temperature sweep.

The M01 checker has long known how to spot a metastable, non-equilibrated
sample.  This small stdlib-only module makes that same decision available to
the renderer, public feed, archive, and browser so they cannot disagree about
which susceptibility peak is scientifically usable.
"""
from __future__ import annotations

import math
import statistics

EQUIL_SIGMA = 5.0
EQUIL_MAX_EXCLUDED = 2

# χ-scale consistency guard.  Deep in the ordered phase (|M| well above the
# critical region) equilibrium χ sits near the smooth disordered-tail
# background; a sample whose χ exceeds that background by orders of magnitude
# is a metastable domain artifact even when |M|(T) never rises (the 2026-07-29
# campaign pass-43 shape: a monotone-decreasing metastable shelf).
CHI_SCALE_RATIO = 100.0
# The background scale is the median χ of samples at T ≥ this — comfortably
# above Onsager T_c ≈ 2.2692 for any lattice size.  Sweeps that stop near T_c
# carry no background to compare against, so the guard stays inert there.
CHI_TAIL_T_MIN = 2.8
CHI_TAIL_MIN_SAMPLES = 3
# |M| above this is the ordered phase proper; the finite-size critical region
# (where a large χ is physical) sits well below it on the production grids.
MAG_ORDERED_MIN = 0.5


def _guard_scan(report: dict) -> tuple[list[int] | None, str | None]:
    """Run the rising-|M| scan; second element names an unreadable guard field.

    Returns ``(indices, None)`` when the scan ran, ``([], None)`` for legacy
    reports that carry no magnetization arrays at all, and ``(None, field)``
    when a guard array is present but unusable — the caller must fail closed,
    never treat that as a clean scan.
    """
    T = report.get("T")
    mag = report.get("abs_mag")
    err = report.get("abs_mag_err")
    if mag is None and err is None:
        return [], None  # legacy report: deliberately no exclusions
    if not isinstance(mag, (list, tuple)):
        return None, "abs_mag"
    if not isinstance(err, (list, tuple)):
        return None, "abs_mag_err"
    if not isinstance(T, (list, tuple)) or not T:
        return None, "T"
    if len(mag) != len(T):
        return None, "abs_mag"
    if len(err) != len(T):
        return None, "abs_mag_err"

    bad: set[int] = set()
    for i in range(len(T) - 1):
        try:
            left_err = float(err[i] or 0.0)
            right_err = float(err[i + 1] or 0.0)
        except (TypeError, ValueError, OverflowError):
            return None, "abs_mag_err"
        try:
            rise = float(mag[i + 1]) - float(mag[i])
        except (TypeError, ValueError, OverflowError):
            return None, "abs_mag"
        sigma = math.hypot(left_err, right_err)
        if not all(math.isfinite(v) for v in (left_err, right_err, rise, sigma)):
            continue
        if sigma > 0 and rise / sigma > EQUIL_SIGMA:
            bad.add(i if left_err >= right_err else i + 1)
    return sorted(bad), None


def nonequilibrated_indices(report: dict) -> list[int] | None:
    """Return samples whose rising |M|(T) proves they did not equilibrate.

    Equilibrium |M| is non-increasing with temperature.  When an adjacent rise
    exceeds ``EQUIL_SIGMA`` combined standard errors, the noisier endpoint is
    treated as the wandering/metastable sample.  Missing legacy uncertainty
    arrays deliberately produce no exclusions; a *present but unreadable*
    guard array returns ``None`` so callers cannot mistake a scan that never
    ran for a clean one.
    """
    indices, _malformed = _guard_scan(report)
    return indices


def _chi_scale_suspects(
    T: list[float], chi: list[float], mag: list[float], excluded: list[int]
) -> set[int]:
    """Samples whose χ is orders of magnitude out of scale for their phase.

    A suspect χ exceeds ``CHI_SCALE_RATIO`` × the disordered-tail median while
    the sample sits in the ordered phase (``|M| > MAG_ORDERED_MIN``) or right
    beside a sample the rising-|M| guard already excluded.  The critical
    region itself (large χ, small |M|) is never flagged.
    """
    tail = [chi[i] for i in range(len(T)) if T[i] >= CHI_TAIL_T_MIN]
    if len(tail) < CHI_TAIL_MIN_SAMPLES:
        return set()
    tail_median = statistics.median(tail)
    if tail_median <= 0:
        return set()
    threshold = CHI_SCALE_RATIO * tail_median
    excluded_set = set(excluded)
    suspects: set[int] = set()
    for i, value in enumerate(chi):
        if value <= threshold:
            continue
        ordered = mag[i] > MAG_ORDERED_MIN
        beside_excluded = (i - 1) in excluded_set or (i + 1) in excluded_set
        if ordered or beside_excluded:
            suspects.add(i)
    return suspects


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

    rise_excluded, malformed = _guard_scan(report)
    if malformed is not None:
        return {
            **invalid,
            "note": (
                f"equilibration guard could not run: malformed {malformed} — "
                "no T_c claimed"
            ),
        }

    chi_suspects: set[int] = set()
    mag = report.get("abs_mag")
    if isinstance(mag, (list, tuple)):
        # _guard_scan already coerced every element, so this cannot raise.
        mag_values = [float(value) for value in mag]
        chi_suspects = _chi_scale_suspects(
            T_values, chi_values, mag_values, rise_excluded
        )

    excluded = sorted(set(rise_excluded) | chi_suspects)
    chi_only = sorted(chi_suspects - set(rise_excluded))
    valid = [i for i in range(len(T_values)) if i not in set(excluded)]
    if len(excluded) > EQUIL_MAX_EXCLUDED:
        if chi_only:
            rise_where = ", ".join(f"T={T_values[i]:.3f}" for i in rise_excluded)
            chi_where = ", ".join(f"T={T_values[i]:.3f}" for i in chi_only)
            note = (
                f"sweep not equilibrated: {len(excluded)} of {len(T_values)} "
                f"samples failed equilibration guards "
                f"({EQUIL_SIGMA:g}σ monotonic-|M|: {rise_where}; "
                f"χ-scale: {chi_where}) — no T_c claimed"
            )
        else:
            note = (
                f"sweep not equilibrated: {len(excluded)} of {len(T_values)} "
                f"samples failed the {EQUIL_SIGMA:g}σ monotonic-|M| guard — "
                "no T_c claimed"
            )
        return {
            **invalid,
            "excluded_indices": excluded,
            "valid_indices": valid,
            "note": note,
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
        if chi_only and rise_excluded:
            guard = f"{EQUIL_SIGMA:g}σ monotonic-|M| and χ-scale guards"
        elif chi_only:
            guard = "χ-scale guard"
        else:
            guard = f"{EQUIL_SIGMA:g}σ monotonic-|M| guard"
        note = (
            f"{len(excluded)} non-equilibrated sample(s) excluded by the "
            f"{guard} ({where})"
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
