#!/usr/bin/env python3
"""Count the class §8 of the survey paper proposes to test.

§8 of ``docs/papers/2026-09-18-survey-methods-draft.md`` proposes that the
secondary-eclipse surface-brightness bound of §6.3 be run over a class of
signals: high MES, high impact parameter, inferred R_p > 2 R_Jup, faint
late-type host. §7 recorded the size of that class as the paper's one open
blocker. This script counts it, by the rule fixed in advance in
``docs/preregistrations/2026-10-08-paper-s8-class-census.md``; every cut and
threshold below is that file's, and a change here that is not a change there
is a defect.

It is a READER of public catalogues. It fits nothing and downloads nothing:
the MAST TCE statistics files, the ExoFOP TOI and CTOI tables and a TIC Tmag
table are fetched elsewhere (the environment this lab mostly runs in cannot
reach MAST) and handed in as a directory. The SHA-256 of every file read is
written into the output so the census can be re-run against the same bytes.

Two passes, because the TCE files carry no magnitude::

    # 1. list the TICs that need a Tmag (every TCE that could enter any grid cell)
    python scripts/paper_s8_class_census.py DATA_DIR --candidates > tics.txt
    # ... fetch TIC v8.2 Tmag for those into DATA_DIR/tic_tmag.csv (ticid,tmag)
    # 2. the census
    python scripts/paper_s8_class_census.py DATA_DIR --json OUT.json

Where the inputs came from (all public, fetched 2026-10-08):

* every ``*_dvr-tcestats.csv`` linked from
  https://archive.stsci.edu/tess/bulk_downloads/bulk_downloads_tce.html
* https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv
  saved as ``exofop_toi.csv``, and ``download_ctoi.php?sort=ctoi&output=csv``
  saved as ``exofop_ctoi.csv``
* Tmag from the MAST ``Mast.Catalogs.Filtered.Tic`` service (columns
  ``ID,Tmag``, filtered on the candidate list), saved as ``tic_tmag.csv`` --
  committed as ``docs/survey/2026-10-08-s8-tic-tmag.csv``

``--selftest`` checks the parts that do not need the data.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tic374861595_secondary_limit import RESPONSES, band_ratio  # noqa: E402

R_JUP_IN_R_EARTH = 11.21
TCE_MES_THRESHOLD = 7.1
H_BURNING_K = 2300.0
RHO_JUP = 1.326            # g/cm^3
DEUTERIUM_MJUP = 13.0
EXHIBIT_TIC = 374861595
PRIMARY_GLOB = "*-s0001-s0096_dvr-tcestats.csv"

# The primary cell and the definition grid, exactly as pre-registered.
PRIMARY = {"mes": 50.0, "b": 0.7, "rp_rj": 2.0, "teff": 4000.0, "tmag": 12.0}
GRID = {
    "mes": [20.0, 50.0, 100.0],
    "b": [0.6, 0.7, 0.8],
    "rp_rj": [1.5, 2.0, 2.5],
    "teff": [3900.0, 4000.0, 4500.0],
    "tmag": [11.0, 12.0, 13.0],
}
MC_DRAWS = 2000
MC_SEED = 2026


# ── reading ──────────────────────────────────────────────────────────────────

def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _num(v: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return math.nan
    return x if math.isfinite(x) else math.nan


TCE_FIELDS = {
    "mes": "tce_max_mult_ev", "b": "tce_impact", "b_err": "tce_impact_err",
    "rp": "tce_prad", "rp_err": "tce_prad_err", "teff": "tce_steff",
    "teff_err": "tce_steff_err", "depth": "tce_depth", "period": "tce_period",
    "ws_mes": "tce_ws_maxmes", "ws_depth": "wst_depth", "ror": "tce_ror",
    "oe_stat": "tce_bin_oedp_stat",
}


def read_tce(path: str) -> list[dict]:
    """One TCE statistics file -> list of row dicts with the fields used here."""
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        lines = (ln for ln in fh if not ln.startswith("#"))
        rows = []
        for r in csv.DictReader(lines):
            try:
                tic = int(float(r["ticid"]))
            except (KeyError, ValueError):
                continue
            row = {"tic": tic, "tceid": r.get("tceid", ""),
                   "sectors": r.get("sectors", "")}
            for k, col in TCE_FIELDS.items():
                row[k] = _num(r.get(col))
            rows.append(row)
    return rows


def read_tic_column(path: str, candidates: tuple[str, ...]) -> set[int]:
    """TIC ids from a CSV whose TIC column may be named any of ``candidates``.
    ExoFOP's CSVs have carried leading comment lines in the past; skip them."""
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    reader = csv.DictReader(lines)
    col = next((c for c in reader.fieldnames or [] if c.strip() in candidates), None)
    if col is None:
        raise SystemExit(f"{path}: no TIC column among {reader.fieldnames}")
    out = set()
    for r in reader:
        m = re.match(r"\s*(\d+)", r.get(col) or "")
        if m:
            out.add(int(m.group(1)))
    return out


def read_tmag(path: str) -> dict[int, float]:
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out[int(float(r["ticid"]))] = _num(r["tmag"])
    return out


# ── the class ────────────────────────────────────────────────────────────────

def in_class(row: dict, cell: dict, tmag: dict[int, float] | None,
             rp=None, b=None, teff=None) -> bool:
    rp = row["rp"] if rp is None else rp
    b = row["b"] if b is None else b
    teff = row["teff"] if teff is None else teff
    if not (row["mes"] >= cell["mes"] and b >= cell["b"]
            and rp >= cell["rp_rj"] * R_JUP_IN_R_EARTH and teff <= cell["teff"]):
        return False
    if tmag is None:          # candidate pass: brightness not yet known
        return True
    t = tmag.get(row["tic"], math.nan)
    return t >= cell["tmag"]


def loosest_cell() -> dict:
    return {"mes": min(GRID["mes"]), "b": min(GRID["b"]),
            "rp_rj": min(GRID["rp_rj"]), "teff": max(GRID["teff"]),
            "tmag": min(GRID["tmag"])}


def mc_could_enter(row: dict) -> bool:
    """Could 3 sigma of catalogue error carry this TCE into the primary cell?"""
    def lo(v, e):
        return v - 3 * (e if e == e else 0.0)
    def hi(v, e):
        return v + 3 * (e if e == e else 0.0)
    c = PRIMARY
    return (row["mes"] >= c["mes"]
            and hi(row["b"], row["b_err"]) >= c["b"]
            and hi(row["rp"], row["rp_err"]) >= c["rp_rj"] * R_JUP_IN_R_EARTH
            and lo(row["teff"], row["teff_err"]) <= c["teff"])


def class_tics(rows, cell, tmag) -> set[int]:
    return {r["tic"] for r in rows if in_class(r, cell, tmag)}


# ── the §6.3 pass ────────────────────────────────────────────────────────────

def cutoff_temperature(ratio_limit: float, t_star: float) -> float:
    """Warmest companion the ceiling allows, warmer of the two band stand-ins."""
    worst = 0.0
    for resp in RESPONSES.values():
        lo, hi = 100.0, t_star
        if band_ratio(hi, t_star, resp) <= ratio_limit:
            return t_star        # even a host twin is allowed: nothing excluded
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if band_ratio(mid, t_star, resp) > ratio_limit:
                hi = mid
            else:
                lo = mid
        worst = max(worst, 0.5 * (lo + hi))
    return worst


def roche_period_days(rp_rearth: float, m_mjup: float = DEUTERIUM_MJUP) -> float:
    """Shortest period a companion of this mass and the catalogue radius survives
    at, from Rappaport et al. 2013: P_min ~ 12.6 h (rho / 1 g cm^-3)^-1/2.
    REPORTED, never used: not part of the pre-registered rule. At the
    deuterium-burning mass it asks whether the catalogue radius is survivable
    for anything of planetary mass at the observed period."""
    if not (rp_rearth == rp_rearth and rp_rearth > 0):
        return math.nan
    rho = RHO_JUP * m_mjup / (rp_rearth / R_JUP_IN_R_EARTH) ** 3
    return 12.6 / 24.0 / math.sqrt(rho)


def secondary_verdict(row: dict) -> dict:
    ws_mes, ws_depth, depth = row["ws_mes"], row["ws_depth"], row["depth"]
    # The odd/even statistic is REPORTED, never used: the pre-registration does
    # not cut on it. It matters because an equal-eclipse binary folded at half
    # its true period puts its secondary on top of its primary, where a
    # weak-secondary search cannot see it -- the one configuration the §6.3
    # argument is blind to, and the one odd/even exists to catch.
    out = {"ws_mes": ws_mes, "ws_depth_ppm": ws_depth, "primary_depth_ppm": depth,
           "odd_even_stat": row.get("oe_stat", math.nan),
           "p_roche_13mj_d": roche_period_days(row.get("rp", math.nan))}
    if not (ws_mes == ws_mes and ws_depth == ws_depth and depth == depth) \
            or depth <= 0:
        return {**out, "verdict": "not-testable", "why": "missing field"}
    if ws_mes >= TCE_MES_THRESHOLD:
        return {**out, "verdict": "secondary-detected"}
    if ws_mes <= 0 or ws_depth <= 0:
        # depth/MES gives no usable sigma when the strongest event is not positive
        return {**out, "verdict": "not-testable", "why": "ws_maxmes or wst_depth <= 0"}
    sigma = ws_depth / ws_mes
    ceiling = max(ws_depth, 0.0) + 3.0 * sigma
    limit = ceiling / depth
    t_cut = cutoff_temperature(limit, row["teff"])
    verdict = "stellar-excluded" if t_cut < H_BURNING_K else "not-excluded"
    return {**out, "sigma_ppm": sigma, "ceiling_ppm": ceiling,
            "ratio_limit": limit, "t_cutoff_k": t_cut, "verdict": verdict}


# ── the census ───────────────────────────────────────────────────────────────

def census(data_dir: str) -> dict:
    prim = sorted(glob.glob(os.path.join(data_dir, PRIMARY_GLOB)))
    if len(prim) != 1:
        raise SystemExit(f"expected one primary file matching {PRIMARY_GLOB}, got {prim}")
    all_tce = sorted(glob.glob(os.path.join(data_dir, "*_dvr-tcestats.csv")))
    toi_path = os.path.join(data_dir, "exofop_toi.csv")
    ctoi_path = os.path.join(data_dir, "exofop_ctoi.csv")
    tmag_path = os.path.join(data_dir, "tic_tmag.csv")

    rows = read_tce(prim[0])
    tmag = read_tmag(tmag_path)
    toi = read_tic_column(toi_path, ("TIC ID", "TIC"))
    ctoi = read_tic_column(ctoi_path, ("TIC ID", "TIC"))

    # Positive control: the exhibit must be in the primary cell.
    ex = [r for r in rows if r["tic"] == EXHIBIT_TIC]
    ex_in = any(in_class(r, PRIMARY, tmag) for r in ex)

    # Primary cell, TCE- and star-level.
    members = [r for r in rows if in_class(r, PRIMARY, tmag)]
    m_tics = sorted({r["tic"] for r in members})
    unprom = [r for r in members if r["tic"] not in toi]
    u_tics = sorted({r["tic"] for r in unprom})

    # Secondary pass on unpromoted members, one row per TCE, best (highest MES)
    # TCE per star decides the star's verdict.
    per_star = {}
    for r in sorted(unprom, key=lambda r: -r["mes"]):
        if r["tic"] in per_star:
            continue
        v = secondary_verdict(r)
        per_star[r["tic"]] = {
            "tic": r["tic"], "tceid": r["tceid"], "period_d": r["period"],
            "mes": r["mes"], "impact": r["b"], "prad_rearth": r["rp"],
            "teff_k": r["teff"], "tmag": tmag.get(r["tic"]),
            "ctoi": r["tic"] in ctoi, **v}
    verdicts = {}
    for s in per_star.values():
        verdicts[s["verdict"]] = verdicts.get(s["verdict"], 0) + 1

    # Measurement uncertainty: Monte Carlo over catalogue errors.
    rng = np.random.default_rng(MC_SEED)
    pool = [r for r in rows if mc_could_enter(r)]
    def draw(v, e):
        return v + (e if e == e and e > 0 else 0.0) * rng.standard_normal(MC_DRAWS)
    draws = [(r, draw(r["rp"], r["rp_err"]), draw(r["b"], r["b_err"]),
              draw(r["teff"], r["teff_err"])) for r in pool]
    mc_all, mc_un = [], []
    for i in range(MC_DRAWS):
        s_all = {r["tic"] for r, rp, b, te in draws
                 if in_class(r, PRIMARY, tmag, rp=rp[i], b=b[i], teff=te[i])}
        mc_all.append(len(s_all))
        mc_un.append(len(s_all - toi))

    def pct(a):
        q = np.percentile(a, [16, 50, 84])
        return {"p16": float(q[0]), "median": float(q[1]), "p84": float(q[2])}

    # Definition uncertainty: every grid cell.
    import itertools
    cells = []
    for vals in itertools.product(*GRID.values()):
        cell = dict(zip(GRID.keys(), vals))
        t = class_tics(rows, cell, tmag)
        cells.append({**cell, "n_class": len(t), "n_unpromoted": len(t - toi)})
    n_cls = [c["n_class"] for c in cells]
    n_un = [c["n_unpromoted"] for c in cells]

    # Breadth: every product, unioned by TIC, primary cell.
    union = set()
    per_file = {}
    best = {}          # tic -> highest-MES class TCE across every product
    for p in all_tce:
        hits = [r for r in read_tce(p) if in_class(r, PRIMARY, tmag)]
        per_file[os.path.basename(p)] = len({r["tic"] for r in hits})
        for r in hits:
            union.add(r["tic"])
            if r["tic"] not in best or r["mes"] > best[r["tic"]]["mes"]:
                best[r["tic"]] = {**r, "product": os.path.basename(p)}

    # NOT PRE-REGISTERED. The pre-registration runs the §6.3 pass on the
    # primary file only. This applies the identical rule to the breadth union's
    # unpromoted stars, each on its highest-MES class TCE, and is reported as
    # exploratory and labelled so wherever it is quoted.
    explore = {}
    explore_rows = []
    for tic in sorted(union - toi):
        r = best[tic]
        v = secondary_verdict(r)
        explore[v["verdict"]] = explore.get(v["verdict"], 0) + 1
        explore_rows.append({"tic": tic, "product": r["product"], "tceid": r["tceid"],
                             "period_d": r["period"], "mes": r["mes"],
                             "impact": r["b"], "prad_rearth": r["rp"],
                             "teff_k": r["teff"], "tmag": tmag.get(tic),
                             "ctoi": tic in ctoi, **v})

    missing_tmag = sorted({r["tic"] for r in rows
                           if in_class(r, loosest_cell(), None)} - set(tmag))

    return {
        "preregistration": "docs/preregistrations/2026-10-08-paper-s8-class-census.md",
        "inputs": {os.path.basename(p): sha256(p)
                   for p in [prim[0], toi_path, ctoi_path, tmag_path]},
        "inputs_breadth": {os.path.basename(p): sha256(p) for p in all_tce},
        "n_tce_files_breadth": len(all_tce),
        "primary_file_tces": len(rows),
        "primary_file_stars": len({r["tic"] for r in rows}),
        "toi_tics": len(toi), "ctoi_tics": len(ctoi),
        "positive_control": {"tic": EXHIBIT_TIC, "in_primary_file": bool(ex),
                             "in_class": ex_in},
        "primary_cell": PRIMARY,
        "class_tces": len(members), "class_stars": len(m_tics),
        "class_stars_promoted": len(set(m_tics) & toi),
        "unpromoted_tces": len(unprom), "unpromoted_stars": len(u_tics),
        "unpromoted_ctoi": sum(1 for t in u_tics if t in ctoi),
        "secondary_pass": verdicts,
        "unpromoted": sorted(per_star.values(), key=lambda s: -s["mes"]),
        "monte_carlo": {"draws": MC_DRAWS, "seed": MC_SEED, "pool_tces": len(pool),
                        "class_stars": pct(mc_all), "unpromoted_stars": pct(mc_un)},
        "grid": {"cells": len(cells), "class_min": min(n_cls), "class_max": max(n_cls),
                 "unpromoted_min": min(n_un), "unpromoted_max": max(n_un),
                 "table": cells},
        "breadth_union": {"class_stars": len(union),
                          "unpromoted_stars": len(union - toi),
                          "not_in_primary": len(union - set(m_tics)),
                          "unpromoted_ctoi": sum(1 for t in union - toi if t in ctoi),
                          "per_file": per_file},
        "exploratory_breadth_secondary_pass": {
            "preregistered": False,
            "rule": "identical to the primary pass; highest-MES class TCE per star",
            "verdicts": explore,
            "stars": sorted(explore_rows, key=lambda s: -s["mes"])},
        "missing_tmag": missing_tmag,
    }


def candidates(data_dir: str) -> list[int]:
    """Every TIC in any product that passes the loosest grid cell bar Tmag, or
    that Monte Carlo could carry into the primary cell."""
    out = set()
    for p in sorted(glob.glob(os.path.join(data_dir, "*_dvr-tcestats.csv"))):
        for r in read_tce(p):
            if in_class(r, loosest_cell(), None) or mc_could_enter(r):
                out.add(r["tic"])
    return sorted(out)


def selftest() -> int:
    ok = True
    def chk(name, cond):
        nonlocal ok
        print(("  PASS  " if cond else "  FAIL  ") + name)
        ok = ok and bool(cond)
    # The exhibit, from its committed DV numbers, must pass the primary cell.
    ex = {"tic": EXHIBIT_TIC, "mes": 508.6, "b": 0.90, "rp": 28.9, "teff": 3445.0}
    chk("exhibit in primary cell", in_class(ex, PRIMARY, {EXHIBIT_TIC: 14.08}))
    chk("exhibit out if faint cut were 14.5",
        not in_class(ex, {**PRIMARY, "tmag": 14.5}, {EXHIBIT_TIC: 14.08}))
    chk("missing Tmag excludes", not in_class(ex, PRIMARY, {}))
    # §6.3 reproduced: SPOC ceiling alone (602 + 3*168) on 104,603 ppm at 3445 K.
    lim = (601.95 + 3 * 167.83) / 104602.85
    t = cutoff_temperature(lim, 3445.0)
    chk(f"§6.3 cut-off reproduced ({t:.0f} K, paper ≲ 1,800 K)", 1500 < t < 2000)
    v = secondary_verdict({"ws_mes": 3.32, "ws_depth": 601.95,
                           "depth": 104602.85, "teff": 3445.0})
    chk(f"exhibit verdict stellar-excluded (σ≈{v.get('sigma_ppm', 0):.0f} ppm)",
        v["verdict"] == "stellar-excluded")
    chk("significant secondary -> secondary-detected",
        secondary_verdict({"ws_mes": 9.0, "ws_depth": 5000.0, "depth": 1e5,
                           "teff": 3400.0})["verdict"] == "secondary-detected")
    chk("non-positive ws -> not-testable",
        secondary_verdict({"ws_mes": -1.0, "ws_depth": -50.0, "depth": 1e5,
                           "teff": 3400.0})["verdict"] == "not-testable")
    chk("shallow primary -> not-excluded",
        secondary_verdict({"ws_mes": 2.0, "ws_depth": 400.0, "depth": 3000.0,
                           "teff": 3400.0})["verdict"] == "not-excluded")
    print("SELFTEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", nargs="?")
    ap.add_argument("--candidates", action="store_true")
    ap.add_argument("--json", metavar="OUT")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.data_dir:
        ap.error("data_dir required")
    if a.candidates:
        print("\n".join(str(t) for t in candidates(a.data_dir)))
        return 0
    res = census(a.data_dir)
    text = json.dumps(res, indent=1, sort_keys=False)
    if a.json:
        Path(a.json).write_text(text + "\n")
    s = res
    print(f"primary file: {s['primary_file_tces']:,} TCEs on {s['primary_file_stars']:,} stars")
    print(f"positive control TIC {EXHIBIT_TIC}: in class = {s['positive_control']['in_class']}")
    print(f"class: {s['class_stars']} stars ({s['class_tces']} TCEs); "
          f"promoted {s['class_stars_promoted']}; unpromoted {s['unpromoted_stars']} "
          f"({s['unpromoted_ctoi']} are CTOIs)")
    print(f"secondary pass on unpromoted: {s['secondary_pass']}")
    mc = s["monte_carlo"]
    print(f"MC class stars {mc['class_stars']}; unpromoted {mc['unpromoted_stars']}")
    g = s["grid"]
    print(f"grid {g['cells']} cells: class {g['class_min']}–{g['class_max']}, "
          f"unpromoted {g['unpromoted_min']}–{g['unpromoted_max']}")
    b = s["breadth_union"]
    print(f"breadth (all {s['n_tce_files_breadth']} products): class {b['class_stars']}, "
          f"unpromoted {b['unpromoted_stars']}, not in primary {b['not_in_primary']}")
    print("EXPLORATORY (not pre-registered) secondary pass on breadth unpromoted: "
          f"{s['exploratory_breadth_secondary_pass']['verdicts']}")
    if s["missing_tmag"]:
        print(f"WARNING: {len(s['missing_tmag'])} candidate TICs have no Tmag")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
