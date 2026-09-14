#!/usr/bin/env python3
"""Transit ephemeris for a CTOI submission, from the receipts' own cached bytes.

The hunt receipts carry period, BLS depth and a fold phase — never an epoch in
BJD or a duration in hours, which a CTOI needs. This measures both from the
SHA-256-pinned light curves the receipts name, with the same decode + detrend
path every receipt used (``a05.curve_from_blob``), so the numbers here are
derivable from the committed record and nothing else.

Per sector: a trapezoid transit model (depth, mid-time T0, total duration T14,
ingress fraction fixed at 0.15) is fit by grid + coordinate refinement at the
receipt's BLS period, on the detrended flux. Uncertainties are from 200
bootstrap resamples of the in-window residuals. Then a joint linear ephemeris
T0(n) = T0_ref + n·P is fit across all sectors by weighted least squares —
the ~140-day baseline between sectors 30 and 35 constrains P far better than
any single 27-day sector can.

numpy only, by design: the lab's venv carries no scipy/astropy, and a number
that needs a library nobody here installed is a number nobody here can
re-derive.

    python3 scripts/ctoi_ephemeris.py --tic 374861595 \
        --receipt hunt-2026-08-31-s30-0102.json --receipt followup-374861595-s31.json \
        --receipt followup-374861595-s35.json

Times: SPOC TIME is BTJD = BJD_TDB − 2457000. Output epochs are BJD_TDB.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lab import a01, a05  # noqa: E402

BTJD_OFFSET = 2457000.0
INGRESS_FRAC = 0.15
N_BOOT = 200


def trapezoid(t: np.ndarray, t0: float, period: float, depth: float,
              t14: float, ingress_frac: float = INGRESS_FRAC) -> np.ndarray:
    """Unit baseline minus a trapezoid dip of total width t14 (days)."""
    ph = np.mod(t - t0 + 0.5 * period, period) - 0.5 * period
    x = np.abs(ph)
    half = 0.5 * t14
    flat = half * (1.0 - 2.0 * ingress_frac)
    m = np.ones_like(t)
    inside = x <= flat
    m[inside] = 1.0 - depth
    ramp = (x > flat) & (x < half)
    m[ramp] = 1.0 - depth * (half - x[ramp]) / (half - flat)
    return m


def chi2(t, f, w, t0, period, depth, t14):
    r = f - trapezoid(t, t0, period, depth, t14)
    return float(np.sum(w * r * r))


def fit_sector(t: np.ndarray, f: np.ndarray, period: float, phase_hint: float,
               depth_hint: float) -> dict:
    """Grid over (T0, T14, depth) then coordinate-refine; bootstrap the errors."""
    # per-point weights from out-of-transit scatter (robust)
    mad = np.median(np.abs(f - np.median(f))) * 1.4826
    w = np.full_like(f, 1.0 / max(mad, 1e-6) ** 2)

    # T0 candidates: scan the WHOLE period. The receipt's `phase` is a BLS
    # bin index convention, not a phase relative to t[0] — trusting it placed
    # two of three sectors on flat baseline and fit 0.1% dips into noise.
    # An 8% signal does not need a hint; it needs a complete scan.
    t0_grid = t[0] + np.linspace(0.0, 1.0, 400, endpoint=False) * period
    t14_grid = np.linspace(0.5 / 24, 4.0 / 24, 22)
    depth_grid = np.linspace(0.3, 1.6, 27) * depth_hint

    best = (np.inf, None)
    for t0 in t0_grid:
        for t14 in t14_grid:
            # depth is linear given the shape: solve in closed form
            shape = 1.0 - trapezoid(t, t0, period, 1.0, t14)   # 0..1 dip profile
            num = np.sum(w * (1.0 - f) * shape)
            den = np.sum(w * shape * shape)
            d = float(num / den) if den > 0 else 0.0
            if not (0 < d < 0.5):
                continue
            c = chi2(t, f, w, t0, period, d, t14)
            if c < best[0]:
                best = (c, (t0, d, t14))
    if best[1] is None:
        raise RuntimeError("no transit fit converged")
    t0, d, t14 = best[1]

    # coordinate refinement, three passes, finer each time
    for scale in (0.02, 0.005, 0.001):
        for _ in range(2):
            cands = t0 + np.linspace(-1, 1, 41) * scale * period
            cs = [chi2(t, f, w, c, period, d, t14) for c in cands]
            t0 = float(cands[int(np.argmin(cs))])
            cands = t14 * np.linspace(0.85, 1.15, 31)
            cs = [chi2(t, f, w, t0, period, d, c) for c in cands]
            t14 = float(cands[int(np.argmin(cs))])
            shape = 1.0 - trapezoid(t, t0, period, 1.0, t14)
            d = float(np.sum(w * (1.0 - f) * shape) / np.sum(w * shape * shape))

    # bootstrap: resample residuals, refit T0/depth (T14 held) — cheap and honest
    model = trapezoid(t, t0, period, d, t14)
    resid = f - model
    rng = np.random.default_rng(20260914)
    boots = []
    for _ in range(N_BOOT):
        fb = model + rng.choice(resid, size=resid.size, replace=True)
        cands = t0 + np.linspace(-1, 1, 41) * 0.004 * period
        cs = [chi2(t, fb, w, c, period, d, t14) for c in cands]
        tb = float(cands[int(np.argmin(cs))])
        shape = 1.0 - trapezoid(t, tb, period, 1.0, t14)
        db = float(np.sum(w * (1.0 - fb) * shape) / np.sum(w * shape * shape))
        cands = t14 * np.linspace(0.9, 1.1, 21)
        cs = [chi2(t, fb, w, tb, period, db, c) for c in cands]
        t14b = float(cands[int(np.argmin(cs))])
        boots.append((tb, db, t14b))
    boots = np.asarray(boots)

    # number of transits actually covered
    n_tr = int(np.unique(np.round((t[np.abs(np.mod(t - t0 + 0.5 * period, period) - 0.5 * period) < 0.5 * t14] - t0) / period)).size)
    in_win = np.abs(np.mod(t - t0 + 0.5 * period, period) - 0.5 * period) < 0.5 * t14
    return {
        "t0_btjd": t0, "t0_err": float(np.std(boots[:, 0])),
        "depth": d, "depth_err": float(np.std(boots[:, 1])),
        "t14_days": t14, "t14_err": float(np.std(boots[:, 2])),
        "n_transits": n_tr, "n_in_transit_points": int(in_win.sum()),
        "oot_scatter": float(mad), "chi2": float(best[0]), "n_points": int(t.size),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tic", required=True)
    ap.add_argument("--receipt", action="append", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    per_sector = []
    for name in args.receipt:
        rec = json.loads((REPO_ROOT / "reports/hunts" / name).read_text())
        row = next(r for r in rec["targets"] if r.get("tic") == args.tic)
        blob = (a01.CACHE_DIR / row["cache_file"]).read_bytes()
        import hashlib
        assert hashlib.sha256(blob).hexdigest() == row["cache_sha256"], f"{name}: cache bytes do not match the receipt's SHA-256"
        curve = a05.curve_from_blob(blob)
        t, f = curve["t"], curve["f"]
        fit = fit_sector(t, f, float(row["period_days"]), float(row["phase"]), float(row["depth"]))
        fit.update(sector=rec["sector"], receipt=name, cache_file=row["cache_file"],
                   bls_period=float(row["period_days"]), bls_depth=float(row["depth"]),
                   sde=float(row["sde"]), r_star_sun=curve.get("r_star_sun"), teff_k=curve.get("teff_k"),
                   crowdsap=curve.get("crowdsap"))
        per_sector.append(fit)
        print(f"sector {rec['sector']}: T0 = {fit['t0_btjd']:.5f} ± {fit['t0_err']:.5f} BTJD · depth {fit['depth']*100:.3f} ± {fit['depth_err']*100:.3f} % · "
              f"T14 {fit['t14_days']*24:.2f} ± {fit['t14_err']*24:.2f} h · {fit['n_transits']} transits · {fit['n_in_transit_points']} in-transit pts", flush=True)

    # joint ephemeris: assign integer epoch n to each sector's T0 relative to the first
    p0 = float(np.mean([s["bls_period"] for s in per_sector]))
    t0s = np.array([s["t0_btjd"] for s in per_sector]); e = np.array([s["t0_err"] for s in per_sector])
    n = np.round((t0s - t0s[0]) / p0)
    # weighted linear fit T0 = a + b n
    W = 1.0 / e**2
    A = np.vstack([np.ones_like(n), n]).T
    cov = np.linalg.inv(A.T @ (W[:, None] * A))
    beta = cov @ (A.T @ (W * t0s))
    a, b = beta; a_err, b_err = np.sqrt(np.diag(cov))
    resid = t0s - (a + b * n)
    # reference epoch at the middle of the baseline to decorrelate
    n_mid = float(np.round(np.mean(n)))
    t0_ref = a + b * n_mid
    t0_ref_err = float(np.sqrt(cov[0, 0] + n_mid**2 * cov[1, 1] + 2 * n_mid * cov[0, 1]))

    depths = np.array([s["depth"] for s in per_sector]); derr = np.array([s["depth_err"] for s in per_sector])
    t14s = np.array([s["t14_days"] for s in per_sector]); terr = np.array([s["t14_err"] for s in per_sector])
    wd = 1 / derr**2; wt = 1 / terr**2
    joint = {
        "tic": args.tic, "sectors": [s["sector"] for s in per_sector],
        "period_days": float(b), "period_err_days": float(b_err),
        "epoch_bjd": float(t0_ref + BTJD_OFFSET), "epoch_err_days": t0_ref_err,
        "epoch_btjd": float(t0_ref), "epoch_n_from_first": n_mid,
        "epoch_integer_offsets": n.tolist(), "ephemeris_residuals_min": (resid * 1440).tolist(),
        "depth_ppm": float(np.sum(wd * depths) / np.sum(wd) * 1e6), "depth_err_ppm": float(1 / np.sqrt(np.sum(wd)) * 1e6),
        "duration_hours": float(np.sum(wt * t14s) / np.sum(wt) * 24), "duration_err_hours": float(1 / np.sqrt(np.sum(wt)) * 24),
        "n_transits_total": int(sum(s["n_transits"] for s in per_sector)),
        "btjd_offset": BTJD_OFFSET, "ingress_fraction_fixed": INGRESS_FRAC, "bootstrap_n": N_BOOT,
        "per_sector": per_sector,
    }
    r_star = per_sector[0]["r_star_sun"]
    if r_star:
        rp_rsun = np.sqrt(joint["depth_ppm"] / 1e6) * float(r_star)
        joint["r_star_sun"] = float(r_star)
        joint["rp_rjup_uncorrected"] = float(rp_rsun / (7.1492e7 / 6.957e8))
        joint["rp_rearth_uncorrected"] = float(rp_rsun * 6.957e8 / 6.371e6)
    print(f"\nJOINT: P = {joint['period_days']:.7f} ± {joint['period_err_days']:.7f} d · T0 = {joint['epoch_bjd']:.5f} ± {joint['epoch_err_days']:.5f} BJD_TDB "
          f"· depth {joint['depth_ppm']:.0f} ± {joint['depth_err_ppm']:.0f} ppm · T14 {joint['duration_hours']:.2f} ± {joint['duration_err_hours']:.2f} h · "
          f"{joint['n_transits_total']} transits · residuals {['%.1f' % x for x in joint['ephemeris_residuals_min']]} min")
    if r_star:
        print(f"       Rp (uncorrected, box-free) = {joint['rp_rjup_uncorrected']:.2f} R_Jup = {joint['rp_rearth_uncorrected']:.1f} R_Earth on R* = {r_star:.3f} R_sun")
    out = Path(args.out) if args.out else REPO_ROOT / "docs/submissions" / f"TIC{args.tic}-ephemeris.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(joint, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
