#!/usr/bin/env python3
"""Independent re-check of an outside candidate, under a committed pre-registration.

Governed by ``docs/preregistrations/2026-10-20-recheck-tic100796276-tic4206066.md``
(and its Amendment 1). Every test name here (T1..T8) is that file's. The script
measures and writes a receipt; the pass/fail lines it applies are copied from
the pre-registration, not chosen here.

    python scripts/recheck_external.py tic100796276
    python scripts/recheck_external.py tic4206066

Receipts land in ``docs/investigations/2026-10-20-recheck/``. FITS bytes stay in
the box-local A01 cache and are pinned by SHA-256 in the receipt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lab import a04, a05_fold, a05_mono, a05_physical, a05_sky, a05_vetting, exofop  # noqa: E402
from lab import a05_multisector as ms  # noqa: E402

OUT_DIR = ROOT / "docs" / "investigations" / "2026-10-20-recheck"
PREREG = "docs/preregistrations/2026-10-20-recheck-tic100796276-tic4206066.md"
BJD0 = 2457000.0

# ----------------------------------------------------------------- helpers --


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating,)):
        v = float(x)
        return v if math.isfinite(v) else None
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, np.ndarray):
        return _jsonable(x.tolist())
    return x


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _band_ratio():
    """``band_ratio`` and ``RESPONSES`` from the §6.3 script, reused unchanged."""
    path = ROOT / "scripts" / "tic374861595_secondary_limit.py"
    spec = importlib.util.spec_from_file_location("secondary_limit", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.band_ratio, mod.RESPONSES


def sb_cutoff(bound: float, t_host: float) -> dict:
    """Companion temperature at which its band surface brightness reaches
    ``bound`` × the host's, by bisection, for each response stand-in."""
    band_ratio, responses = _band_ratio()
    out = {"bound": bound, "t_host_k": t_host, "cutoff_k": {}}
    if not (0 < bound < 1):
        out["applicable"] = False
        return out
    for name, resp in responses.items():
        lo, hi = 300.0, t_host
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if band_ratio(mid, t_host, resp) > bound:
                hi = mid
            else:
                lo = mid
        out["cutoff_k"][name] = round(0.5 * (lo + hi), 1)
    out["applicable"] = True
    out["adopted_cutoff_k"] = max(out["cutoff_k"].values())
    out["stellar_companion_excluded"] = bool(out["adopted_cutoff_k"] < 2300.0)
    return out


def fold_x(t, period, t0):
    """Time from the nearest predicted mid-transit, in days."""
    return ((np.asarray(t) - t0 + 0.5 * period) % period) - 0.5 * period


def epochs_in(curve, period, t0, half):
    """Epoch numbers whose ±half window contains data."""
    t = curve["t"]
    n0 = int(math.floor((t.min() - t0) / period)) - 1
    n1 = int(math.ceil((t.max() - t0) / period)) + 1
    out = []
    for n in range(n0, n1 + 1):
        tc = t0 + n * period
        if np.sum(np.abs(t - tc) <= half) >= 3:
            out.append(n)
    return out


def load_all(tic: str, wanted: list[tuple[str, int]]):
    prods = {(p["provenance"], p["sector"]): p for p in ms.discover_products(tic)}
    curves, rows = {}, []
    for key in wanted:
        p = prods.get(key)
        if p is None:
            rows.append({"provenance": key[0], "sector": key[1],
                         "status": "no-product"})
            continue
        c, r = ms.load_product(p)
        r["status"] = "loaded"
        curves[key] = c
        rows.append(r)
    return curves, rows, sorted(prods)


def stitch(curves: dict, keys) -> tuple:
    ts, fs, ws = [], [], []
    for k in keys:
        c = curves.get(k)
        if c is None:
            continue
        # bin to 10 minutes so 2-min and 200-s/600-s cadences weigh by cadence count
        t, f, n = ms.bin_series(c["t"], c["f"], 10.0 / 1440.0)
        ts.append(t)
        fs.append(f)
        ws.append(n)
    t, f, w = np.concatenate(ts), np.concatenate(fs), np.concatenate(ws)
    o = np.argsort(t)
    return t[o], f[o], w[o]


def stitch_raw(curves: dict, keys):
    t = np.concatenate([curves[k]["t"] for k in keys if k in curves])
    f = np.concatenate([curves[k]["f"] for k in keys if k in curves])
    o = np.argsort(t)
    return t[o], f[o]


def secondary_block(t, f, period, t0, dur, primary_depth):
    """T6: phase-0.5 depth, any-phase ceiling, coverage, and the SB bound."""
    x = (np.asarray(t) - t0) % period                       # 0..P from primary
    ph05 = ms.box_depth(x, f, 0.5 * period, dur)
    excl = 2.0 * dur
    step = 0.25 * dur
    best = None
    covered = 0
    n_trials = 0
    for c in np.arange(excl, period - excl, step):
        r = ms.box_depth(x, f, c, dur)
        n_trials += 1
        if r["depth"] is None:
            continue
        covered += 1
        if best is None or r["snr"] > best["snr"]:
            best = r
    cov_frac = covered / n_trials if n_trials else 0.0

    def ceil(r):
        return None if r is None or r["depth"] is None else max(r["depth"], 0.0) + 3.0 * r["sigma"]

    c05, cany = ceil(ph05), ceil(best)
    ceiling = max([c for c in (c05, cany) if c is not None], default=None)
    out = {"phase_0p5": ph05, "deepest_any_phase": best,
           "phase_coverage_frac": cov_frac, "ceiling_phase_0p5": c05,
           "ceiling_any_phase": cany, "ceiling": ceiling,
           "primary_depth": primary_depth}
    if ceiling is not None and primary_depth and primary_depth > 0:
        out["sb_ratio_bound"] = ceiling / primary_depth
    return out


def sky_block(tic, period, depth, crowdsap, r_star):
    out = {}
    try:
        neigh = a05_sky.resolve_neighbours(tic)
        out["neighbours"] = neigh
        out["flux_budget"] = a05_sky.flux_budget(depth, crowdsap, neigh, r_star)
        out["neighbour_crosscheck"] = a05_sky.neighbour_crosscheck(
            period, neigh, a05_sky.sky_catalog_lookup)
    except Exception as exc:  # noqa: BLE001 - an unrun gate is pending, never passed
        out["error"] = f"pending_catalog: {exc!r}"
    try:
        out["target_catalog"] = a04.catalog_crosscheck(tic, detected_period_days=period)
    except Exception as exc:  # noqa: BLE001
        out["target_catalog"] = {"lookup_error": repr(exc)}
    try:
        out["target_ctoi"] = exofop.ctoi_crosscheck(tic, detected_period_days=period)
    except Exception as exc:  # noqa: BLE001
        out["target_ctoi"] = {"lookup_error": repr(exc)}
    return out


def _date(btjd: float) -> str:
    return (dt.datetime(2014, 12, 8, 12) + dt.timedelta(days=btjd)).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------- TIC 100796276 --

L279 = {
    "tic": "100796276",
    "period": 18.15219, "period_err": 0.00003,
    "t0_btjd": 2459036.9763 - BJD0, "t0_err": 0.0022,
    "duration_days": 2.4 / 24.0, "depth": 0.0032, "t_host_k": 3490.0,
    # his six transits, by epoch number from T0; 118 is the partial he excluded
    "claimed_epochs": {0: "2020-07-06 S27", 1: "2020-07-24 S27",
                       61: "2023-07-18 S67", 101: "2025-07-13 S94 (predicted)",
                       119: "2026-06-05 S104 (predicted)",
                       120: "2026-06-23 S105"},
    "excluded_epochs": {118: "2026-05-18 S104 partial, excluded by him"},
    "spoc_period": 11.47,
}
PRIMARY_L279 = [("SPOC", 27), ("TESS-SPOC", 67)]
XCHECK_L279 = [("TESS-SPOC", 27)]
QLP_L279 = [("QLP", 94), ("QLP", 104)]


def run_l279() -> dict:
    E = L279
    P, T0, D = E["period"], E["t0_btjd"], E["duration_days"]
    curves, inputs, listed = load_all(E["tic"], PRIMARY_L279 + XCHECK_L279 + QLP_L279)
    R: dict = {"tic": E["tic"], "claim": E, "inputs": inputs,
               "products_listed": [list(k) for k in listed], "tests": {}}
    tier = {k: ("primary" if k in PRIMARY_L279 else "xcheck" if k in XCHECK_L279
                else "QLP (amendment 1)") for k in curves}

    # T1 — the survey's own per-sector BLS
    t1 = []
    for k, c in curves.items():
        try:
            det = a04.blind_search(c["t"], c["f"])
            t1.append({"source": list(k), "tier": tier[k], "period_days": det.period_days,
                       "sde": det.sde, "depth": det.depth,
                       "p_hi_effective": min(a04.P_HI, (c["t"].max() - c["t"].min()) / a04.MIN_TRANSITS)})
        except a04.A04Error as exc:
            t1.append({"source": list(k), "tier": tier[k], "error": str(exc)})
    R["tests"]["T1_survey_bls"] = {"rows": t1, "expected": "cannot report 18.15 d by construction"}

    # T2 — single events, no period
    t2 = {"per_sector": [], "claimed": {}}
    for k, c in curves.items():
        ss = a05_mono.search_single(c["t"], c["f"])
        hits = a05_mono.scan(c["t"], c["f"])
        dips = [h for h in hits if h["snr"] > 0]
        row = {"source": list(k), "tier": tier[k],
               "snr_max_brightening": ss["snr_max_brightening"],
               "events_snr_ge_9": [dict(h, date=_date(h["t_centre"])) for h in ss["candidates"]]}
        t2["per_sector"].append(row)
        for n, label in {**E["claimed_epochs"], **E["excluded_epochs"]}.items():
            tc = T0 + n * P
            if not (c["t"].min() - 0.5 <= tc <= c["t"].max() + 0.5):
                continue
            near = [h for h in dips if abs(h["t_centre"] - tc) <= 0.5 and h["snr"] >= 7.0]
            near.sort(key=lambda h: -h["snr"])
            cov = int(np.sum(np.abs(c["t"] - tc) <= D))
            best = near[0] if near else None
            agrees = bool(best is not None and abs(best["t_centre"] - tc) <= 1.0 / 24)
            t2["claimed"].setdefault(str(n), []).append({
                "label": label, "source": list(k), "tier": tier[k],
                "cadences_within_1T14": cov,
                "best_dip_snr_ge_7": best,
                "offset_min": None if best is None else (best["t_centre"] - tc) * 1440,
                "verdict": ("agrees" if agrees else
                            "not-tested" if cov < 5 else "disagrees")})
    R["tests"]["T2_single_events"] = t2

    # T3 — period with no prior, primary tier only
    t, f, w = stitch(curves, PRIMARY_L279)
    bls = ms.bls_stitched(t, f, w, p_lo=1.0, p_hi=40.0)
    peaks = ms.top_peaks(bls, 5)
    near = ms.peak_near(bls, P, 0.0005)
    spoc = ms.peak_near(bls, E["spoc_period"], 0.003)
    top = peaks[0]["period_days"]
    ratios = [r for r in (1, 2, 3, 0.5, 1 / 3) if abs(top * r - P) <= 0.01]
    R["tests"]["T3_bls_no_prior"] = {
        "tier": "primary (SPOC S27 + TESS-SPOC S67), 10-min bins",
        "n_trials": bls["n_trials"], "baseline_days": bls["baseline_days"],
        "top_peaks": peaks, "at_18p152": near, "at_spoc_11p47": spoc,
        "top_within_0p01d": bool(abs(top - P) <= 0.01),
        "top_integer_ratio": ratios,
    }

    # T4 — event times at his period
    t4 = {"events": [], "pair_prediction": None, "spoc_11p47": None}
    measured = {}
    for k, c in curves.items():
        for n in epochs_in(c, P, T0, D):
            tc = T0 + n * P
            et = ms.event_time(c["t"], c["f"], tc, D)
            bd = ms.box_depth(c["t"], c["f"], tc, D)
            row = {"epoch": n, "source": list(k), "tier": tier[k],
                   "label": E["claimed_epochs"].get(n) or E["excluded_epochs"].get(n),
                   "predicted_btjd": tc, "predicted_utc": _date(tc),
                   "fit": et, "depth_at_prediction": bd}
            if et.get("t_mid") is not None:
                row["o_minus_c_min"] = (et["t_mid"] - tc) * 1440.0
                row["sigma_min"] = et["sigma_days"] * 1440.0
            t4["events"].append(row)
            if k != ("TESS-SPOC", 27) and et.get("t_mid") is not None and bd["snr"] and bd["snr"] >= 5:
                measured.setdefault(n, row)
    in_claim = [r for r in t4["events"] if r["epoch"] in E["claimed_epochs"]
                and r["tier"] != "xcheck" and "o_minus_c_min" in r]
    t4["max_abs_o_minus_c_min"] = max((abs(r["o_minus_c_min"]) for r in in_claim), default=None)
    t4["all_within_15_min"] = bool(in_claim) and all(abs(r["o_minus_c_min"]) <= 15 for r in in_claim)
    if 0 in measured and 61 in measured:
        a, b = measured[0]["fit"]["t_mid"], measured[61]["fit"]["t_mid"]
        p_pair = (b - a) / 61.0
        preds = []
        for n in (101, 119):
            if n in measured:
                tp = a + n * p_pair
                preds.append({"epoch": n, "predicted_btjd": tp,
                              "observed_btjd": measured[n]["fit"]["t_mid"],
                              "o_minus_c_min": (measured[n]["fit"]["t_mid"] - tp) * 1440})
        t4["pair_prediction"] = {"period_from_pair": p_pair, "predictions": preds}
    if 0 in measured:
        a = measured[0]["fit"]["t_mid"]
        c = curves[("SPOC", 27)]
        rows = []
        for m in (1, 2):
            tc = a + m * E["spoc_period"]
            bd = ms.box_depth(c["t"], c["f"], tc, D)
            hits = [h for h in a05_mono.scan(c["t"], c["f"])
                    if h["snr"] > 0 and abs(h["t_centre"] - tc) <= 0.25]
            hits.sort(key=lambda h: -h["snr"])
            rows.append({"n": m, "t_btjd": tc, "utc": _date(tc), "in_data": bd["n_in"] >= 3,
                         "box_at_exact_time": bd, "strongest_dip_within_6h": hits[0] if hits else None})
        t4["spoc_11p47"] = rows
    R["tests"]["T4_at_his_period"] = t4

    # primary fold depth (used by T5-T8)
    tp, fp = stitch_raw(curves, PRIMARY_L279)
    xp = fold_x(tp, P, T0)
    prim = ms.box_depth(xp, fp, 0.0, D)
    R["primary_fold_depth"] = prim
    depth = prim["depth"]

    # T5 — odd/even and 2P
    det = a04.Detection(P, depth, (T0 % P) / P, 0.0)
    hw = D / P
    R["tests"]["T5_odd_even"] = {
        "odd_even_fold": a05_fold.odd_even_fold(tp, fp, det, half_window=hw),
        "p2_fold": a05_fold.p2_fold(tp, fp, det, half_window=hw),
        "epoch_parity": {str(n): ("odd" if n % 2 else "even") for n in E["claimed_epochs"]}}

    # T6 — secondary + SB bound
    sec = secondary_block(tp, fp, P, T0, D, depth)
    if "sb_ratio_bound" in sec:
        sec["sb"] = sb_cutoff(sec["sb_ratio_bound"], E["t_host_k"])
    R["tests"]["T6_secondary"] = sec

    # T7 — depth across sectors
    rows = []
    for k, c in curves.items():
        x = fold_x(c["t"], P, T0)
        r = ms.box_depth(x, c["f"], 0.0, D)
        r.update({"source": list(k), "tier": tier[k], "crowdsap": c["crowdsap"]})
        rows.append(r)
    prim_rows = [r for r in rows if r["tier"] == "primary" and r["depth"] is not None]
    wts = np.array([1 / r["sigma"] ** 2 for r in prim_rows])
    ds = np.array([r["depth"] for r in prim_rows])
    wmean = float(np.sum(wts * ds) / np.sum(wts)) if len(ds) else None
    chi2 = float(np.sum(wts * (ds - wmean) ** 2)) if len(ds) else None
    dof = max(len(ds) - 1, 0)
    # survival function of chi2 for small integer dof, no scipy
    p = None
    if dof == 1:
        p = math.erfc(math.sqrt(chi2 / 2))
    elif dof == 2:
        p = math.exp(-chi2 / 2)
    R["tests"]["T7_depth_by_sector"] = {
        "rows": rows, "weighted_mean_primary": wmean, "chi2": chi2, "dof": dof,
        "p_value": p,
        "max_dev_sigma": max((abs(r["depth"] - wmean) / r["sigma"] for r in prim_rows), default=None),
        "his_depth": E["depth"]}

    # T8 — whose light is it
    spoc = curves[("SPOC", 27)]
    sky = sky_block(E["tic"], P, depth, spoc["crowdsap"], spoc["r_star_sun"])
    cen_lab, cen_match = {}, {}
    cen_t = np.concatenate([curves[k]["t"] for k in PRIMARY_L279])
    def _cat(name):
        parts = [curves[k][name] for k in PRIMARY_L279]
        if any(p is None for p in parts):
            return None
        return np.concatenate(parts)
    cx, cy = _cat("cx"), _cat("cy")
    o = np.argsort(cen_t)
    if cx is not None:
        cen_lab = a05_vetting.centroid_shift(cen_t[o], cx[o], cy[o], det)
        centres = [T0 + n * P for n in E["claimed_epochs"]]
        cen_match = ms.centroid_shift_matched(cen_t[o], cx[o], cy[o], centres, D, depth)
    else:
        cen_lab = cen_match = {"reason": "no-centroid-data",
                               "have": {str(k): curves[k]["cx"] is not None for k in PRIMARY_L279}}
    sky["centroid_lab_window"] = cen_lab
    sky["centroid_duration_matched"] = cen_match
    sky["companion_radius"] = a05_physical.companion_radius(depth, spoc["r_star_sun"],
                                                             spoc["crowdsap"])
    sky["header"] = {k: spoc[k] for k in ("r_star_sun", "teff_k", "tessmag", "crowdsap", "flfrcsap")}
    R["tests"]["T8_sky"] = sky
    R["disposition"] = disposition_l279(R)
    return R


def disposition_l279(R) -> dict:
    T = R["tests"]
    fired = []
    oe = T["T5_odd_even"]["odd_even_fold"].get("verdict")
    p2 = T["T5_odd_even"]["p2_fold"].get("verdict")
    for v in (oe, p2):
        if v:
            fired.append(v)
    sb = T["T6_secondary"].get("sb") or {}
    ph = T["T6_secondary"].get("phase_0p5") or {}
    if ph.get("snr") is not None and ph["snr"] >= a04.ODD_EVEN_SIGMA:
        fired.append("eclipsing-binary-secondary")
    sky = T["T8_sky"]
    for key in ("flux_budget", "neighbour_crosscheck"):
        v = (sky.get(key) or {}).get("verdict")
        if v:
            fired.append(v)
    if (sky.get("centroid_duration_matched") or {}).get("verdict"):
        fired.append("centroid-shift")
    if (sky.get("companion_radius") or {}).get("verdict"):
        fired.append(sky["companion_radius"]["verdict"])
    claimed = T["T2_single_events"]["claimed"]
    verdicts = [r["verdict"] for n, rows in claimed.items() if int(n) in L279["claimed_epochs"]
                for r in rows if r["tier"] != "xcheck"]
    covered = sum(1 for v in verdicts if v != "not-tested")
    if fired:
        word = fired[0]
    elif covered < 2:
        word = "insufficient-coverage"
    elif any(v == "disagrees" for v in verdicts):
        word = "low-significance"
    else:
        word = "lead-awaiting-human-review"
    pending = bool(sky.get("error"))
    return {"machine_disposition": word, "gates_fired": fired,
            "sky_gates_pending": pending, "complete": not pending,
            "claimed_event_verdicts": verdicts, "sb_note": sb.get("stellar_companion_excluded")}


# ----------------------------------------------------------- TIC 4206066 --

K4206 = {
    "tic": "4206066",
    "A": {"period": 3.182785, "t0_btjd": 2460998.736 - BJD0, "duration_days": 1.87 / 24, "depth": 500e-6},
    "B": {"period": 11.13274, "t0_btjd": 2461000.865 - BJD0, "duration_days": 2.0 / 24, "depth": 1000e-6},
    "t_host_k": None,
}
PRIMARY_K = [("SPOC", 32), ("TESS-SPOC", 6)]
XCHECK_K = [("TESS-SPOC", 32)]


def run_k4206() -> dict:
    E = K4206
    curves, inputs, listed = load_all(E["tic"], PRIMARY_K + XCHECK_K)
    tier = {k: ("primary" if k in PRIMARY_K else "xcheck") for k in curves}
    R = {"tic": E["tic"], "claim": E, "inputs": inputs,
         "products_listed": [list(k) for k in listed], "tests": {},
         "not_admitted": "QLP S98 (his discovery sector) is not admitted (prereg amendment 1)"}
    A = E["A"]
    t1 = []
    for k, c in curves.items():
        det = a04.blind_search(c["t"], c["f"])
        PA = A["period"]
        alias = [m for m in (1, 2, 3, 0.5, 1 / 3) if abs(det.period_days - PA * m) / (PA * m) < 0.01]
        t1.append({"source": list(k), "tier": tier[k], "period_days": det.period_days,
                   "sde": det.sde, "depth": det.depth, "matches_A_alias": alias,
                   "sde_threshold": a04.SDE_THRESHOLD})
    R["tests"]["T1_survey_bls"] = t1
    t4 = []
    for name in ("A", "B"):
        S = E[name]
        for k, c in curves.items():
            x = fold_x(c["t"], S["period"], S["t0_btjd"])
            r = ms.box_depth(x, c["f"], 0.0, S["duration_days"])
            n_ev = len(epochs_in(c, S["period"], S["t0_btjd"], S["duration_days"]))
            r.update({"signal": name, "source": list(k), "tier": tier[k], "n_epochs_covered": n_ev,
                      "his_depth": S["depth"]})
            t4.append(r)
    R["tests"]["T4_depth_at_ephemeris"] = t4
    tp, fp = stitch_raw(curves, PRIMARY_K)
    xp = fold_x(tp, A["period"], A["t0_btjd"])
    prim = ms.box_depth(xp, fp, 0.0, A["duration_days"])
    R["primary_fold_depth_A"] = prim
    depth = prim["depth"] if prim["depth"] and prim["depth"] > 0 else A["depth"]
    det = a04.Detection(A["period"], depth, (A["t0_btjd"] % A["period"]) / A["period"], 0.0)
    hw = A["duration_days"] / A["period"]
    R["tests"]["T5_odd_even_A"] = a05_fold.odd_even_fold(tp, fp, det, half_window=hw)
    sec = secondary_block(tp, fp, A["period"], A["t0_btjd"], A["duration_days"], depth)
    teff = curves[("SPOC", 32)]["teff_k"]
    if "sb_ratio_bound" in sec and teff:
        sec["sb"] = sb_cutoff(sec["sb_ratio_bound"], teff)
    R["tests"]["T6_secondary_A"] = sec
    rows = [r for r in t4 if r["signal"] == "A"]
    R["tests"]["T7_depth_by_sector_A"] = rows
    spoc = curves[("SPOC", 32)]
    sky = sky_block(E["tic"], A["period"], depth, spoc["crowdsap"], spoc["r_star_sun"])
    sky["centroid_lab_window"] = a05_vetting.centroid_shift(spoc["t"], spoc["cx"], spoc["cy"], det)
    centres = [A["t0_btjd"] + n * A["period"] for n in epochs_in(spoc, A["period"], A["t0_btjd"], A["duration_days"])]
    sky["centroid_duration_matched"] = ms.centroid_shift_matched(
        spoc["t"], spoc["cx"], spoc["cy"], centres, A["duration_days"], depth)
    sky["companion_radius"] = a05_physical.companion_radius(depth, spoc["r_star_sun"], spoc["crowdsap"])
    sky["header"] = {k: spoc[k] for k in ("r_star_sun", "teff_k", "tessmag", "crowdsap", "flfrcsap")}
    R["tests"]["T8_sky_A"] = sky
    return R


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=["tic100796276", "tic4206066"])
    a = ap.parse_args(argv)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    R = run_l279() if a.target == "tic100796276" else run_k4206()
    R.update({"preregistration": PREREG, "code_commit": _git_head(),
              "generated_at": started, "script": "scripts/recheck_external.py",
              "vocabulary": "lab.a05_vocab"})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{a.target}-receipt.json"
    path.write_text(json.dumps(_jsonable(R), indent=1, sort_keys=False) + "\n",
                    encoding="utf-8", newline="\n")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
