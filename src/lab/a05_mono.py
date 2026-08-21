"""Single transits — the planets a period search cannot see.

BLS folds. Folding needs at least two events, and :data:`lab.a04.MIN_TRANSITS`
makes that explicit by capping the period grid at ``baseline / MIN_TRANSITS``.
So every transiting body whose period exceeds roughly half a TESS sector shows
**one** dip in that sector and is invisible to the survey *by construction* —
not missed, not marginal: outside the detector's definition.

That is a large and specifically under-worked population. The 2-minute SPOC
targets in sectors 2, 3 and 30 have been searched for short-period planets by
teams with better data and more of it; HATS-16 b was published in 2015 and this
lab still rediscovered it (see the 2026-08-20 investigation). The long-period
regime is where an amateur instrument has room, because the thing that makes it
hard is not photometric precision — it is that one event carries no period, so
every candidate must be argued from a single dip's *shape* rather than from
repetition.

### The statistic

For a trial duration ``w`` and centre ``tau``, compare the flux inside the box
with a local baseline drawn from flanking windows out to
:data:`FLANK_FACTOR` * w::

    depth = median(out) - median(in)
    snr   = depth / (sigma * sqrt(1/n_in + 1/n_out))

scanned over a grid of centres and durations. Local flanks rather than a global
baseline: a single dip must be measured against the star as it was that day,
or every long-timescale wobble becomes a candidate.

### The null, without permuting anything

The same statistic computed for *brightenings* — the sign-flipped excursions of
the identical scan — is a null drawn from the same star, the same cadences and
the same systematics. Under symmetric noise, the largest upward excursion is
distributed like the largest downward one; astrophysical transits contribute
only to the downward tail. So :func:`search_single` reports
``snr_max_brightening`` beside ``snr`` and the ratio is the honest first
statement of significance, computed for free.

It is a *weaker* null than a permutation and is not a substitute for one where
the noise is skewed (flares make the upward tail heavier, which is
conservative here — it inflates the null and refutes more). Reported, never
silently graded: the caller decides.
"""
from __future__ import annotations

import math

import numpy as np

#: Trial durations in hours. A long-period transit across a dwarf lasts a few
#: hours to most of a day; below ~1 h a 2-minute cadence has too few points to
#: separate a transit from a cosmic-ray residual.
DURATIONS_HOURS = (1.5, 2.5, 4.0, 6.0, 9.0, 13.0)

#: Flanking baseline extends to this multiple of the trial half-width on each
#: side. 3x gives a baseline comparable in weight to the in-box sample without
#: reaching so far that stellar variability dominates it.
FLANK_FACTOR = 3.0

#: Scan step as a fraction of the trial duration.
STEP_FRACTION = 0.25

#: Minimum cadences inside the box and in the flanks for a trial to count.
MIN_IN = 8
MIN_OUT = 30

#: Report threshold. Deliberately high: a single-event detector has no
#: repetition to lean on, so the bar replaces the evidence that folding
#: normally supplies. Nothing is *graded* at this module's level — this is the
#: line above which an event is worth a human's attention.
SNR_REPORT = 9.0

#: An event whose centre falls within this fraction of the series' end is
#: refused: a dip truncated by the edge of a sector has no measurable egress
#: and its duration is unbounded.
EDGE_GUARD_FRACTION = 0.02

#: Events closer together than this (in units of the trial duration) are the
#: same event found at neighbouring scan positions.
DEDUPE_SPACING = 2.0


def _robust_sigma(x: np.ndarray) -> float:
    if x.size < 4:
        return float("nan")
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def scan(t: np.ndarray, f: np.ndarray,
         durations_hours: tuple = DURATIONS_HOURS) -> list[dict]:
    """Matched-box scan over centres and durations. Returns every trial above
    :data:`SNR_REPORT`, deduplicated, strongest first.

    Both signs are scanned: ``sign = -1`` is a dip, ``sign = +1`` a
    brightening, and the brightening trials are the null described in the
    module docstring.
    """
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    ok = np.isfinite(t) & np.isfinite(f)
    t, f = t[ok], f[ok]
    if t.size < MIN_IN + MIN_OUT:
        return []
    order = np.argsort(t)
    t, f = t[order], f[order]
    span = float(t[-1] - t[0])
    guard = EDGE_GUARD_FRACTION * span
    sigma = _robust_sigma(f)
    if not (sigma > 0):
        return []
    hits: list[dict] = []
    for dur_h in durations_hours:
        w = 0.5 * float(dur_h) / 24.0
        if w <= 0 or 2.0 * w >= 0.5 * span:
            continue
        step = max(STEP_FRACTION * 2.0 * w, 1e-6)
        centres = np.arange(t[0] + guard + w, t[-1] - guard - w, step)
        for tau in centres:
            d = np.abs(t - tau)
            inb = d <= w
            out = (d > w) & (d <= FLANK_FACTOR * w)
            n_in, n_out = int(inb.sum()), int(out.sum())
            if n_in < MIN_IN or n_out < MIN_OUT:
                continue
            base = float(np.median(f[out]))
            delta = base - float(np.median(f[inb]))
            err = sigma * math.sqrt(1.0 / n_in + 1.0 / n_out)
            if err <= 0:
                continue
            snr = delta / err
            hits.append({"t_centre": float(tau), "duration_hours": float(dur_h),
                         "depth": float(delta / base) if base else None,
                         "snr": float(snr), "n_in": n_in, "n_out": n_out,
                         "sign": -1 if snr >= 0 else 1})
    return _dedupe(hits)


def _dedupe(hits: list[dict]) -> list[dict]:
    """Collapse neighbouring scan positions of the same event; strongest wins."""
    kept: list[dict] = []
    for h in sorted(hits, key=lambda r: -abs(r["snr"])):
        w = h["duration_hours"] / 24.0
        if any(abs(h["t_centre"] - k["t_centre"]) < DEDUPE_SPACING * w
               for k in kept):
            continue
        kept.append(h)
    return kept


def search_single(t: np.ndarray, f: np.ndarray,
                  durations_hours: tuple = DURATIONS_HOURS,
                  known_period_days: float | None = None,
                  known_phase: float | None = None) -> dict:
    """Single-transit search with the brightening null attached.

    ``known_period_days`` / ``known_phase`` — when the target already carries a
    periodic detection, an event at that ephemeris's phase is not a
    monotransit; it is one of the events the fold already found. Marked
    ``periodic: True``. Phase follows :class:`lab.a04.Detection`'s convention
    (``np.mod(t, period) / period``), so the two agree without a conversion.
    """
    hits = scan(t, f, durations_hours)
    dips = [h for h in hits if h["snr"] > 0]
    bright = [h for h in hits if h["snr"] < 0]
    snr_null = max((abs(h["snr"]) for h in bright), default=0.0)
    out = {"candidates": [], "n_trials": len(hits),
           "snr_max_brightening": float(snr_null),
           "snr_threshold": SNR_REPORT, "reason": None}
    if not dips:
        out["reason"] = "no-dips"
        return out
    t_arr = np.asarray(t, dtype=float)
    for h in sorted(dips, key=lambda r: -r["snr"]):
        if h["snr"] < SNR_REPORT:
            continue
        rec = dict(h)
        rec["snr_over_null"] = (float(h["snr"] / snr_null)
                                if snr_null > 0 else None)
        rec["periodic"] = False
        if known_period_days and known_phase is not None:
            P = float(known_period_days)
            if P > 0:
                ph = (h["t_centre"] % P) / P
                sep = abs(((ph - float(known_phase) + 0.5) % 1.0) - 0.5)
                # within half the trial duration of the known ephemeris
                rec["periodic"] = bool(
                    sep * P <= 0.5 * h["duration_hours"] / 24.0)
        if rec["periodic"]:
            out.setdefault("periodic_events", []).append(rec)
            continue
        out["candidates"].append(rec)
    if not out["candidates"]:
        out["reason"] = "nothing-above-threshold"
    return out
