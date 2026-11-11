#!/usr/bin/env python3
"""TIC 374861595: the doubled-period fold on every sector, and the light between the dips.

Consumer: docs/investigations/2026-11-10-tic374861595-eb-at-2p-refutation.md. Run once per
change to the light-curve set; it reads local FITS files and touches no network.

Why this exists. The shelf graded this star on three sectors (30, 31, 35). The shelf-exit
contract (section 3) says a star is graded on every archival sector, combined. An outside
vetter (issue 189) read the signal as a near-equal eclipsing binary at twice the detected
period. This script asks the questions that reading raises, on every light curve it is given:

1. THE LAB'S OWN GATE. ``lab.a05_fold.p2_fold`` and ``odd_even_fold`` per sector, then
   ``lab.a05_fold.combine_p2_folds``. The curve is prepared exactly as the hunt prepares it
   (``lab.a05.curve_from_blob`` then ``lab.a05_vetting.prewhiten``). One thing differs from
   a hunt, on purpose: every sector is folded on ONE ephemeris (SPOC's multi-sector DV fit),
   so the two eclipse slots at 2P are the same two physical events in every sector. A hunt
   uses each sector's own detection, and a slipped parity there makes the combiner refuse.

2. THE SAME QUESTION, ASKED WITHOUT THE GATE'S MACHINERY. The fold gate's error bars are
   white-noise bars, and this star varies. So the depth difference is also measured one dip
   at a time on raw flux (no detrend, no prewhitening, no shared aperture), with the error
   taken from the scatter between events.

3. A MEASUREMENT NO GATE MAKES. The fold gate compares eclipse depths, and a near-equal pair
   has near-equal depths. So this also fits the light BETWEEN the dips with a sinusoid at 2P,
   per sector, on flux that has NOT been detrended, and asks whether its phase holds from
   sector to sector. It then scans nearby periods for the one at which the per-sector phases
   line up best. A star whose brightness keeps step with twice the dip period for years is
   rotating in step with a 2P orbit. This is a measurement, not a verdict: nothing here can
   move a disposition.

What this cannot show. A phase that wanders does not rule out a binary (spots move). The
ephemeris is SPOC's, not re-derived here. A per-sector gate firing on white-noise bars is
soft where the star varies on the eclipse timescale; block 2 is there to say how soft.

    python scripts/tic374861595_p2_fold_all_sectors.py --fits-dir DIR --json OUT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from lab import a01, a04, a05, a05_fold, a05_vetting  # noqa: E402

TIC = 374861595
#: SPOC multi-sector DV fit, sectors 1-96, read from the committed
#: docs/submissions/TIC374861595-spoc-s1-s96-dvr.xml (allTransitsFit).
P_DAYS = 1.9369484453819672
T0_BTJD = 2036.5479415409804
#: Half-width, in phase of P, masked around every dip before the between-dips fit.
#: The eclipse lasts 2.15 h = 0.046 of P end to end; 0.06 each side clears it with margin.
ECLIPSE_MASK_PHASE = 0.06
#: A gap longer than this splits a sector into separately-trended segments (TESS orbits).
SEGMENT_GAP_DAYS = 0.5
#: A segment shorter than this many cadences is dropped rather than trended.
MIN_SEGMENT_CADENCES = 200
#: Period scan around 2P for the phase-coherence peak: fractional offsets from 2P.
SCAN_STEP = 0.0002
SCAN_HALF_RANGE = 0.02
SCAN_EPS = [round(k * SCAN_STEP, 6) for k in range(-int(round(SCAN_HALF_RANGE / SCAN_STEP)),
                                                   int(round(SCAN_HALF_RANGE / SCAN_STEP)) + 1)]
CONTROL_EPS = (-0.01, -0.003, 0.003, 0.01)
#: A sector's between-dips phase is used only if its amplitude clears this many sigma.
MIN_AMP_SIGMA = 3.0
#: Event-level cross-check: half-width of the dip core, and the side bands that set its
#: baseline, in hours from mid-eclipse. The eclipse is 2.15 h end to end.
CORE_HALF_HOURS = 0.5
SIDE_BAND_HOURS = (1.5, 3.5)
#: Fewest events of each parity for a sector's event-level difference to be reported.
MIN_EVENTS_PER_PARITY = 3


def sector_of(path: Path) -> int | None:
    m = re.search(r"-s(\d{4})-0*%d-" % TIC, path.name)
    return int(m.group(1)) if m else None


def fold_one(blob: bytes) -> dict:
    """The hunt's own preparation, then the lab's fold gates on the fixed ephemeris."""
    curve = a05.curve_from_blob(blob)
    t = np.asarray(curve["t"], dtype=float)
    fw, components = a05_vetting.prewhiten(t, np.asarray(curve["f"], dtype=float))
    phase0 = (T0_BTJD % P_DAYS) / P_DAYS
    det = a04.Detection(period_days=P_DAYS, depth=0.0, phase=float(phase0), sde=0.0)
    p2 = a05_fold.p2_fold(t, fw, det)
    oe = a05_fold.odd_even_fold(t, fw, det)
    return {"p2_fold": p2, "odd_even_fold": oe, "n_cadences": int(len(t)),
            "t_mid_btjd": float(0.5 * (t.min() + t.max())),
            "prewhitened_components": [[float(nu), float(amp)] for nu, amp in components]}


def raw_light(blob: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Quality-masked, time-sorted, median-normalised PDCSAP. NOT detrended."""
    curve = a01.read_tess_light_curve(blob, ancillary=True)
    t, f, _aux = a05_vetting.normalise_with_ancillary(curve)
    order = np.argsort(t, kind="stable")
    t, f = np.asarray(t, dtype=float)[order], np.asarray(f, dtype=float)[order]
    return t, f / np.median(f)


def event_depths(t: np.ndarray, f: np.ndarray) -> dict:
    """Odd minus even dip depth, one event at a time, with the error taken from the events.

    Independent of the fold gate on purpose: raw flux, no detrend, no prewhitening, no shared
    aperture. Each dip's depth is one minus the median flux within CORE_HALF_HOURS of
    mid-eclipse over the mean of the medians of its two side bands. Events are split by their
    count from the SPOC epoch; an odd count is slot 1 of ``p2_fold`` on this ephemeris. The
    error is the scatter between events, not a white-noise model.
    """
    n_lo = int(math.floor((t.min() - T0_BTJD) / P_DAYS))
    n_hi = int(math.ceil((t.max() - T0_BTJD) / P_DAYS))
    depths: dict[int, list[float]] = {0: [], 1: []}
    for n in range(n_lo, n_hi + 1):
        dt_h = (t - (T0_BTJD + n * P_DAYS)) * 24.0
        core = np.abs(dt_h) < CORE_HALF_HOURS
        side = (np.abs(dt_h) > SIDE_BAND_HOURS[0]) & (np.abs(dt_h) < SIDE_BAND_HOURS[1])
        left, right = side & (dt_h < 0), side & (dt_h > 0)
        if core.sum() < 20 or left.sum() < 30 or right.sum() < 30:
            continue
        base = 0.5 * (float(np.median(f[left])) + float(np.median(f[right])))
        depths[n % 2].append(1.0 - float(np.median(f[core])) / base)
    even, odd = np.array(depths[0]), np.array(depths[1])
    out = {"n_even": int(len(even)), "n_odd": int(len(odd)), "difference_odd_minus_even": None}
    if len(even) < MIN_EVENTS_PER_PARITY or len(odd) < MIN_EVENTS_PER_PARITY:
        out["reason"] = "too-few-events"
        return out
    sigma = math.hypot(float(odd.std(ddof=1)) / math.sqrt(len(odd)),
                       float(even.std(ddof=1)) / math.sqrt(len(even)))
    out.update({"depth_even": float(even.mean()), "depth_odd": float(odd.mean()),
                "difference_odd_minus_even": float(odd.mean() - even.mean()),
                "sigma": float(sigma)})
    return out


def mask_dips(t: np.ndarray, f: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Drop every dip and every segment too short to trend. Returns ``(t, f, segment_id)``."""
    ph = ((t - T0_BTJD) / P_DAYS + 0.5) % 1.0 - 0.5
    keep = np.abs(ph) > ECLIPSE_MASK_PHASE
    t, f = t[keep], f[keep]
    seg = (np.concatenate([[0], np.cumsum(np.diff(t) > SEGMENT_GAP_DAYS)])
           if len(t) else np.array([], dtype=int))
    ok = np.zeros(len(t), dtype=bool)
    for s in np.unique(seg):
        if (seg == s).sum() >= MIN_SEGMENT_CADENCES:
            ok |= seg == s
    return t[ok], f[ok], seg[ok]


def _design(t: np.ndarray, seg: np.ndarray, period: float) -> tuple[np.ndarray, int]:
    """Per-segment quadratic trend, then sin/cos at ``period`` and at ``period``/2."""
    cols = []
    for s in np.unique(seg):
        m = seg == s
        mid, span = 0.5 * (t[m].min() + t[m].max()), max(t[m].max() - t[m].min(), 1e-6)
        x = np.where(m, (t - mid) / span, 0.0)
        cols += [m.astype(float), x, x * x]
    theta = 2.0 * math.pi * (t - T0_BTJD) / period
    n_trend = len(cols)
    cols += [np.sin(theta), np.cos(theta), np.sin(2.0 * theta), np.cos(2.0 * theta)]
    return np.column_stack(cols), n_trend


def clip_mask(t: np.ndarray, f: np.ndarray, seg: np.ndarray, period: float) -> np.ndarray:
    """Cadences that survive 4-sigma clipping against the fit at ``period`` (flares, dropouts)."""
    good = np.ones(len(t), dtype=bool)
    for _ in range(5):
        X, _n = _design(t[good], seg[good], period)
        coef, *_ = np.linalg.lstsq(X, f[good], rcond=None)
        resid = f[good] - X @ coef
        bad = np.abs(resid) > 4.0 * float(np.sqrt(np.mean(resid ** 2)))
        if not bad.any():
            break
        good[np.flatnonzero(good)[bad]] = False
    return good


def sinusoid_fit(t: np.ndarray, f: np.ndarray, seg: np.ndarray, period: float) -> dict:
    """Amplitude and phase of the sinusoid at ``period`` in the between-dips light.

    Phase convention: theta = 2*pi*(t - T0)/period, so at period = 2P theta = 0 is an
    even-numbered dip of the SPOC ephemeris and theta = pi the next one.
    ``phase_of_max_cycles`` is the theta, in cycles, at which the fitted sinusoid is brightest.
    """
    X, n_trend = _design(t, seg, period)
    coef, *_ = np.linalg.lstsq(X, f, rcond=None)
    resid = f - X @ coef
    dof = max(len(resid) - X.shape[1], 1)
    rms = float(np.sqrt(np.sum(resid ** 2) / dof))
    cov = rms ** 2 * np.linalg.inv(X.T @ X)
    a_s, a_c = float(coef[n_trend]), float(coef[n_trend + 1])
    var_s, var_c = float(cov[n_trend, n_trend]), float(cov[n_trend + 1, n_trend + 1])
    amp = math.hypot(a_s, a_c)
    amp_sigma = (math.sqrt(a_s ** 2 * var_s + a_c ** 2 * var_c) / amp) if amp > 0 else float("inf")
    return {
        "amplitude": float(amp),
        "amplitude_sigma": float(amp_sigma),
        "amplitude_snr": float(amp / amp_sigma) if amp_sigma > 0 else None,
        "phase_of_max_cycles": float((math.atan2(a_s, a_c) / (2.0 * math.pi)) % 1.0),
        "harmonic_amplitude": float(math.hypot(coef[n_trend + 2], coef[n_trend + 3])),
        "residual_rms": rms,
    }


def rayleigh(phases_cycles: list[float]) -> dict:
    """Resultant length of unit phasors, and the Rayleigh p-value (Zar's approximation)."""
    n = len(phases_cycles)
    if n < 3:
        return {"n": n, "R": None, "p": None, "mean_phase_cycles": None}
    ang = 2.0 * math.pi * np.asarray(phases_cycles, dtype=float)
    c, s = float(np.cos(ang).sum()), float(np.sin(ang).sum())
    r = math.hypot(c, s) / n
    rn = r * n
    p = math.exp(math.sqrt(1.0 + 4.0 * n + 4.0 * (n * n - rn * rn)) - (1.0 + 2.0 * n))
    return {"n": n, "R": float(r), "p": float(min(p, 1.0)),
            "mean_phase_cycles": float((math.atan2(s, c) / (2.0 * math.pi)) % 1.0)}


def weighted(diffs: list[float], sigmas: list[float]) -> dict:
    """Inverse-variance mean, its formal bar, and what the scatter between sectors says."""
    d, s = np.asarray(diffs, dtype=float), np.asarray(sigmas, dtype=float)
    n = len(d)
    w = 1.0 / s ** 2
    mean, sig = float(np.sum(w * d) / np.sum(w)), float(1.0 / math.sqrt(np.sum(w)))
    chi2 = float(np.sum(((d - mean) / s) ** 2))
    inflate = max(1.0, math.sqrt(chi2 / max(n - 1, 1)))
    unweighted = float(d.mean())
    sem = float(d.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    k = int(max((d > 0).sum(), (d < 0).sum()))
    tail = sum(math.comb(n, j) for j in range(k, n + 1)) / 2 ** n
    return {"n_sectors": n, "mean": mean, "sigma_formal": sig,
            "sigmas_formal": mean / sig,
            "chi2": chi2, "dof": n - 1, "bar_inflation": inflate,
            "sigmas_after_inflation": mean / (sig * inflate),
            "unweighted_mean": unweighted, "standard_error_from_scatter": sem,
            "sigmas_from_scatter": unweighted / sem if sem and sem > 0 else None,
            "n_positive": int((d > 0).sum()), "n_negative": int((d < 0).sum()),
            "sign_binomial_p_two_sided": float(min(1.0, 2.0 * tail))}


def linear_drift(cycles: list[float], phases: list[float]) -> dict:
    """Straight-line fit of phase against cycle count: a period offset shows up as a slope.

    A modulation slower than 2P reaches maximum later each cycle, so its phase on the 2P clock
    climbs: a positive slope means a period LONGER than 2P.
    """
    x, y = np.asarray(cycles, dtype=float), np.asarray(phases, dtype=float)
    n = len(x)
    mx, my = float(x.mean()), float(y.mean())
    sxx = float(np.sum((x - mx) ** 2))
    slope = float(np.sum((x - mx) * (y - my)) / sxx)
    resid = y - (my + slope * (x - mx))
    s_res = float(np.sqrt(np.sum(resid ** 2) / max(n - 2, 1)))
    return {"n_sectors": n, "cycles_spanned": float(x.max() - x.min()),
            "phase_min": float(y.min()), "phase_max": float(y.max()), "phase_mean": my,
            "slope_cycles_per_cycle": slope, "slope_sigma": s_res / math.sqrt(sxx),
            "rms_about_line_cycles": s_res,
            "implied_period_days": 2.0 * P_DAYS * (1.0 + slope),
            "implied_period_sigma_days": 2.0 * P_DAYS * s_res / math.sqrt(sxx)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fits-dir", required=True, help="folder holding the star's *_lc.fits files")
    ap.add_argument("--json", help="write the full result here")
    args = ap.parse_args()

    by_sector: dict[int, Path] = {}
    for p in sorted(Path(args.fits_dir).rglob("*%d*s_lc.fits" % TIC)):
        s = sector_of(p)
        if s is not None and s not in by_sector:
            by_sector[s] = p
    if not by_sector:
        print("no light curves found for TIC %d under %s" % (TIC, args.fits_dir))
        return 2

    two_p = 2.0 * P_DAYS
    sectors = []
    for s in sorted(by_sector):
        blob = by_sector[s].read_bytes()
        row = {"sector": s, "file": by_sector[s].name,
               "sha256": hashlib.sha256(blob).hexdigest()}
        row.update(fold_one(blob))
        t_raw, f_raw = raw_light(blob)
        row["event_depths"] = event_depths(t_raw, f_raw)
        t, f, seg = mask_dips(t_raw, f_raw)
        if len(t) < 500:
            row["between_dips"] = {"amplitude": None, "reason": "too-few-cadences"}
            row["scan_phases"] = [None] * len(SCAN_EPS)
        else:
            good = clip_mask(t, f, seg, two_p)
            t, f, seg = t[good], f[good], seg[good]
            bd = sinusoid_fit(t, f, seg, two_p)
            bd.update({"n_used": int(good.sum()), "n_clipped": int((~good).sum())})
            row["between_dips"] = bd
            row["scan_phases"] = [sinusoid_fit(t, f, seg, two_p * (1.0 + eps))["phase_of_max_cycles"]
                                  for eps in SCAN_EPS]
        sectors.append(row)
        p2, bd, ev = row["p2_fold"], row["between_dips"], row["event_depths"]
        fold_txt = ("slot1-slot2 %+.3f pp (%.2f sigma)%s" % (
            100 * p2["signed_difference"], p2["difference_sigma"],
            "  GATE: " + p2["verdict"] if p2.get("verdict") else "")
            if p2.get("difference_sigma") is not None else "not measured (%s)" % p2.get("reason"))
        ev_txt = ("%+.3f +- %.3f pp" % (100 * ev["difference_odd_minus_even"], 100 * ev["sigma"])
                  if ev.get("difference_odd_minus_even") is not None else "n/a")
        bd_txt = ("amp %.3f%% (%.0f sigma) phase %.3f" % (
            100 * bd["amplitude"], bd["amplitude_snr"], bd["phase_of_max_cycles"])
            if bd.get("amplitude") else "not measured")
        oe_v = row["odd_even_fold"].get("verdict")
        print("s%02d  fold gate: %s%s | by event: %s | between dips: %s" % (
            s, fold_txt, "  GATE: " + oe_v if oe_v else "", ev_txt, bd_txt), flush=True)

    combined = a05_fold.combine_p2_folds([r["p2_fold"] for r in sectors])
    measured = [r for r in sectors if r["p2_fold"].get("signed_difference") is not None]
    fold_scatter = weighted(
        [r["p2_fold"]["signed_difference"] for r in measured],
        [math.hypot(r["p2_fold"]["eclipse_a"]["sigma"], r["p2_fold"]["eclipse_b"]["sigma"])
         for r in measured])
    ev_rows = [r for r in sectors if r["event_depths"].get("difference_odd_minus_even") is not None]
    by_event = weighted([r["event_depths"]["difference_odd_minus_even"] for r in ev_rows],
                        [r["event_depths"]["sigma"] for r in ev_rows])
    gates_fired = [{"sector": r["sector"], "gate": g, "verdict": r[g]["verdict"],
                    "difference_sigma": r[g].get("difference_sigma")}
                   for r in sectors for g in ("p2_fold", "odd_even_fold") if r[g].get("verdict")]

    usable = [r for r in sectors
              if (r["between_dips"].get("amplitude_snr") or 0.0) >= MIN_AMP_SIGMA]
    idx = {eps: i for i, eps in enumerate(SCAN_EPS)}
    scan = [{"eps": eps, **rayleigh([r["scan_phases"][i] for r in usable])}
            for eps, i in idx.items()]
    best = max(scan, key=lambda x: x["R"] if x["R"] is not None else -1.0)
    late = [r for r in usable if r["sector"] >= 61]
    coherence = {
        "n_sectors_used": len(usable),
        "sectors_used": [r["sector"] for r in usable],
        "at_2P": scan[idx[0.0]],
        "controls": {str(eps): scan[idx[round(eps, 6)]] for eps in CONTROL_EPS},
        "scan_best": {"eps": best["eps"], "period_days": two_p * (1.0 + best["eps"]),
                      "R": best["R"], "two_p_days": two_p,
                      "scan_step_eps": SCAN_STEP, "scan_half_range_eps": SCAN_HALF_RANGE},
        "sectors_61_onward": {
            **linear_drift([(r["t_mid_btjd"] - T0_BTJD) / two_p for r in late],
                           [r["between_dips"]["phase_of_max_cycles"] for r in late]),
            "R": rayleigh([r["between_dips"]["phase_of_max_cycles"] for r in late])["R"],
        } if len(late) >= 3 else None,
        "scan": [{"eps": s["eps"], "R": s["R"]} for s in scan],
    }

    result = {
        "tic": TIC,
        "ephemeris": {"period_days": P_DAYS, "t0_btjd": T0_BTJD,
                      "source": "docs/submissions/TIC374861595-spoc-s1-s96-dvr.xml allTransitsFit"},
        "thresholds": {"P2_ALIAS_SIGMA": a05_fold.P2_ALIAS_SIGMA,
                       "MIN_ECLIPSE_SIGMA": a05_fold.MIN_ECLIPSE_SIGMA,
                       "ODD_EVEN_SIGMA": a04.ODD_EVEN_SIGMA,
                       "MIN_AMP_SIGMA": MIN_AMP_SIGMA},
        "n_sectors": len(sectors),
        "sectors": [{k: v for k, v in r.items() if k != "scan_phases"} for r in sectors],
        "gates_fired": gates_fired,
        "combined_p2_fold": combined,
        "p2_fold_slot1_minus_slot2": fold_scatter,
        "event_level_odd_minus_even": by_event,
        "between_dips_coherence": coherence,
        "claim_boundary": [
            "The fold gates are the lab's own code on a fixed SPOC ephemeris; they grade a depth "
            "difference and are blind to a near-equal pair by construction.",
            "A per-sector gate firing rests on white-noise bars; the event-level block says how "
            "much the scatter between events widens them.",
            "The between-dips fit is a measurement, not a gate.",
            "A wandering phase would not rule out a binary; a held phase is evidence of rotation "
            "locked to 2P.",
        ],
    }
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")

    print()
    print("gates fired: %s" % (", ".join("s%d %s (%.2f sigma)" % (
        g["sector"], g["verdict"], g["difference_sigma"]) for g in gates_fired) or "none"))
    if combined.get("difference") is not None:
        print("lab combiner over %d sectors: slot1-slot2 %+.4f pp, %.2f sigma, sign consistent: %s, verdict: %s" % (
            combined["n_sectors"], 100 * combined["difference"], combined["difference_sigma"],
            combined.get("sign_consistent"), combined.get("verdict")))
    for name, w in (("fold gate, slot1-slot2", fold_scatter), ("by event, odd-even", by_event)):
        print("%s: %+.4f pp; %.1f sigma formal, %.1f after the sector scatter (chi2 %.1f/%d), "
              "%.1f from the scatter alone; sign %d to %d (p %.2g)" % (
                  name, 100 * w["mean"], w["sigmas_formal"], w["sigmas_after_inflation"],
                  w["chi2"], w["dof"], w["sigmas_from_scatter"], w["n_positive"], w["n_negative"],
                  w["sign_binomial_p_two_sided"]))
    a = coherence["at_2P"]
    if a["R"] is not None:
        print("between-dips phase at 2P over %d sectors: R = %.3f, Rayleigh p = %.2g" % (a["n"], a["R"], a["p"]))
        for eps, r in coherence["controls"].items():
            print("  control at 2P x (1 %+g): R = %.3f, p = %.2g" % (float(eps), r["R"], r["p"]))
        b = coherence["scan_best"]
        print("  all sectors line up best at %.5f d (R = %.3f); 2P is %.5f d" % (
            b["period_days"], b["R"], b["two_p_days"]))
        late_c = coherence["sectors_61_onward"]
        if late_c:
            print("  sectors 61 onward (%d sectors, %.0f cycles): phase %.3f to %.3f, R = %.3f; "
                  "modulation period %.5f +- %.5f d" % (
                      late_c["n_sectors"], late_c["cycles_spanned"], late_c["phase_min"],
                      late_c["phase_max"], late_c["R"], late_c["implied_period_days"],
                      late_c["implied_period_sigma_days"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
