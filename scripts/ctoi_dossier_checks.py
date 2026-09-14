#!/usr/bin/env python3
"""Three physics checks a CTOI reader asks first, from the joint ephemeris.

Reads ``docs/submissions/TIC<tic>-ephemeris.json`` (scripts/ctoi_ephemeris.py)
and the same pinned light curves, and answers, with numbers:

1. **Stacked odd/even and secondary** at the JOINT ephemeris across every
   sector — the receipts grade these per sector; stacking three sectors is
   the stronger test of "is this an eclipsing binary at twice the period".
2. **Stellar density from the transit shape** (Seager & Mallén-Ornelas 2003):
   for a circular orbit, a/R* follows from P, T14 and depth, and ρ* from
   a/R* and P. A transiting planet on a dwarf gives ρ* near the catalogue
   value; a blended or grazing EB, or a giant host, gives a density far off.
   TIC v8 says ρ* = 2.57 g/cm³ for this host.
3. **A phase-folded figure**, all sectors, binned, with the trapezoid model —
   the one picture every reviewer wants before anything else.

numpy + matplotlib only. Writes ``docs/submissions/TIC<tic>-checks.json`` and
``docs/submissions/TIC<tic>-fold.png``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lab import a01, a05                       # noqa: E402
from ctoi_ephemeris import trapezoid, BTJD_OFFSET  # noqa: E402

G_CGS = 6.674e-8
R_SUN_CM = 6.957e10
DAY_S = 86400.0


def stacked(t, f, period, t0, t14):
    ph = np.mod(t - t0 + 0.5 * period, period) - 0.5 * period       # days from mid-transit
    epoch = np.round((t - t0) / period)
    win = np.abs(ph) < 0.35 * t14                                    # inner flat part
    oot = (np.abs(ph) > 0.75 * t14) & (np.abs(ph) < 3.0 * t14)
    base = np.median(f[oot]); noise = 1.4826 * np.median(np.abs(f[oot] - base))
    def med_se(n): return np.sqrt(np.pi / 2) * noise / np.sqrt(max(n, 1))
    odd = win & (epoch % 2 == 1); even = win & (epoch % 2 == 0)
    d_odd = base - np.median(f[odd]); d_even = base - np.median(f[even])
    oe_sigma = abs(d_odd - d_even) / np.hypot(med_se(odd.sum()), med_se(even.sum()))
    # secondary at phase 0.5, same window width
    ph2 = np.mod(t - t0, period) - 0.5 * period
    sec = np.abs(ph2) < 0.35 * t14
    d_sec = base - np.median(f[sec]); sec_sigma = d_sec / med_se(sec.sum())
    return {"depth_odd": float(d_odd), "depth_even": float(d_even), "odd_even_sigma": float(oe_sigma),
            "n_odd": int(odd.sum()), "n_even": int(even.sum()),
            "secondary_depth": float(d_sec), "secondary_sigma": float(sec_sigma), "n_secondary": int(sec.sum()),
            "secondary_depth_3sigma_upper_ppm": float(max(d_sec, 0) + 3 * med_se(sec.sum())) * 1e6,
            "baseline": float(base), "oot_noise": float(noise)}


def density_from_shape(period_days, t14_days, depth, ingress_frac=0.15):
    """Seager & Mallén-Ornelas (2003), circular orbit, b from the ingress ratio."""
    k = np.sqrt(depth)
    t23 = t14_days * (1 - 2 * ingress_frac)         # flat-bottom duration, from the fixed trapezoid shape
    P = period_days
    s14 = np.sin(np.pi * t14_days / P); s23 = np.sin(np.pi * t23 / P)
    b2 = ((1 - k) ** 2 - (s23 / s14) ** 2 * (1 + k) ** 2) / (1 - (s23 / s14) ** 2)
    b = np.sqrt(max(b2, 0.0))
    a_rs = np.sqrt(((1 + k) ** 2 - b2 * (1 - s14 ** 2)) / (s14 ** 2))
    rho = 3 * np.pi / (G_CGS * (P * DAY_S) ** 2) * a_rs ** 3           # g/cm^3
    return {"k_rp_rs": float(k), "impact_b": float(b), "a_over_rs": float(a_rs), "rho_star_gcc": float(rho),
            "t23_hours_assumed": float(t23 * 24)}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--tic", required=True)
    ap.add_argument("--rho-catalog", type=float, default=None, help="TIC v8 rho (g/cc)")
    args = ap.parse_args()
    eph = json.loads((REPO_ROOT / "docs/submissions" / f"TIC{args.tic}-ephemeris.json").read_text())
    P, t0 = eph["period_days"], eph["epoch_btjd"]; t14 = eph["duration_hours"] / 24; depth = eph["depth_ppm"] / 1e6

    ts, fs, tags = [], [], []
    for s in eph["per_sector"]:
        blob = (a01.CACHE_DIR / s["cache_file"]).read_bytes()
        c = a05.curve_from_blob(blob); ts.append(c["t"]); fs.append(c["f"]); tags.append(np.full(c["t"].size, s["sector"]))
    t = np.concatenate(ts); f = np.concatenate(fs); sec_tag = np.concatenate(tags)

    stack = stacked(t, f, P, t0, t14)
    dens = density_from_shape(P, t14, depth, eph.get("ingress_fraction_fixed", 0.15))
    out = {"tic": args.tic, "joint": {k: eph[k] for k in ("period_days", "epoch_bjd", "depth_ppm", "duration_hours", "n_transits_total", "sectors")},
           "stacked_odd_even_secondary": stack, "shape_density": dens}
    if args.rho_catalog:
        out["shape_density"]["rho_catalog_gcc"] = args.rho_catalog
        out["shape_density"]["rho_ratio_shape_over_catalog"] = dens["rho_star_gcc"] / args.rho_catalog
    print(json.dumps(out, indent=1))

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    ph = (np.mod(t - t0 + 0.5 * P, P) - 0.5 * P) * 24     # hours
    m = np.abs(ph) < 6
    fig, ax = plt.subplots(2, 1, figsize=(8, 7), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    for s, col in zip(sorted(set(sec_tag.tolist())), ("#c9a86a", "#8aa86b", "#8fa3ad")):
        k = m & (sec_tag == s); ax[0].plot(ph[k], f[k], ".", ms=2, alpha=.35, color=col, label=f"sector {s}")
    bins = np.linspace(-6, 6, 97); idx = np.digitize(ph[m], bins)
    bx = 0.5 * (bins[1:] + bins[:-1]); by = np.array([np.median(f[m][idx == i]) if (idx == i).sum() > 3 else np.nan for i in range(1, len(bins))])
    ax[0].plot(bx, by, "o", ms=4, color="#e8833a", label="binned, 7.5 min")
    xx = np.linspace(-6, 6, 800); ax[0].plot(xx, trapezoid(t0 + xx / 24, t0, P, depth, t14), "-", color="#ece1cc", lw=1.2, label="trapezoid model")
    ax[0].set_ylabel("detrended flux"); ax[0].legend(loc="lower right", fontsize=8)
    ax[0].set_title(f"TIC {args.tic} — P = {P:.6f} d, depth {depth*100:.2f} %, T14 {t14*24:.2f} h — sectors {eph['sectors']}, {eph['n_transits_total']} transits")
    ph2 = (np.mod(t - t0, P) - 0.5 * P) * 24; m2 = np.abs(ph2) < 6
    idx2 = np.digitize(ph2[m2], bins); by2 = np.array([np.median(f[m2][idx2 == i]) if (idx2 == i).sum() > 3 else np.nan for i in range(1, len(bins))])
    ax[1].plot(ph2[m2], f[m2], ".", ms=2, alpha=.25, color="#847660"); ax[1].plot(bx, by2, "o", ms=4, color="#e8833a")
    ax[1].axhline(stack["baseline"], color="#ece1cc", lw=.8); ax[1].set_ylim(stack["baseline"] - 0.02, stack["baseline"] + 0.01)
    ax[1].set_ylabel("phase 0.5 (secondary)"); ax[1].set_xlabel("hours from mid-transit")
    for a in ax: a.set_facecolor("#1c1510"); a.tick_params(colors="#b8a98c"); [sp.set_color("#4a3b28") for sp in a.spines.values()]
    fig.patch.set_facecolor("#1c1510")
    for a in ax: a.yaxis.label.set_color("#b8a98c"); a.xaxis.label.set_color("#b8a98c"); a.title.set_color("#ece1cc")
    png = REPO_ROOT / "docs/submissions" / f"TIC{args.tic}-fold.png"; fig.tight_layout(); fig.savefig(png, dpi=150)
    (REPO_ROOT / "docs/submissions" / f"TIC{args.tic}-checks.json").write_text(json.dumps(out, indent=1))
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
