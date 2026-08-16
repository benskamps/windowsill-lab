"""Lane census — characterize every enumerated survey target BEFORE searching it.

CONSUMERS: Ben (the survey-strategy call) and the future hunt prioritizer.
Produced 2026-08-16 on Ben's directive ("go wide on that") after two
lead-awaiting-human-review rows died in two minutes of external catalog work
(both were SIMBAD-catalogued spectroscopic binaries; one sat on a 2.3 R_Sun
subgiant). The lesson: the sky has public answers, and hash-order search
treats a solved star and a virgin M dwarf as equal value. This script builds
the map that fixes that.

For every 2-minute SPOC target in the lane sectors (win 2+29, loam 3+30):

  * TIC stellar parameters (bulk MAST):  Teff, radius, mass, Tmag,
    luminosity class, contamination ratio, distance.
  * SIMBAD object type by TIC identifier (bulk TAP): known SB*/EB*/variable
    classes — the killers the TOI cross-check cannot see.
  * TOI membership (one ExoFOP CSV): already-community-flagged targets.

Classification (v1, deliberately simple — every threshold is printed into the
output so the map can be re-argued without re-fetching):

  KILL   known-binary-or-variable   SIMBAD otype in the binary/variable set
  KILL   evolved-host               radius > 1.5 R_Sun or lumclass GIANT
  INFO   has-toi                    community already watching it
  PEAK   quiet-m-dwarf              Teff < 4000 K, radius < 0.6 R_Sun
  PEAK   k-dwarf                    4000-5300 K, radius < 0.9 R_Sun
  ...    g-dwarf / other            the remainder

Outputs (committed):
  docs/survey/lane-census-<date>.json   full per-target table + provenance
  docs/survey/<date>-lane-census.md     the human map: histograms, counts,
                                        and the top yield-ranked targets/lane

Pure catalog I/O — touches no light curves, changes no search behavior. The
enumeration comes from the SAME ``a04.sector_targets`` the hunts use, so this
census and the survey can never disagree about what a sector contains.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lab import a01, a04  # noqa: E402

LANES = {"win": (2, 29), "loam": (3, 30)}
OUT_DIR = REPO_ROOT / "docs" / "survey"
SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"
TOI_CSV = "https://exofop.ipac.caltech.edu/tess/download_toi.php?output=csv"
# SIMBAD otypes that kill a target for planet-search purposes. Broad on
# purpose: anything the literature already calls a binary or a periodic
# variable is a rediscovery machine, not a discovery target. (SB* killed both
# 2026-08-15 leads.)
KILL_OTYPES = {
    "SB*", "EB*", "Al*", "bL*", "WU*", "EP*", "El*",      # binaries
    "RR*", "dS*", "gD*", "Ce*", "cC*", "Pu*", "RV*",      # pulsators
    "Ro*", "BY*", "RS*", "Er*", "Fl*",                    # rotational/eruptive
    "Mi*", "LP*", "sr*",                                  # long-period var
}
EVOLVED_RADIUS = 1.5      # R_Sun — above this, transits shrink & EBs abound
M_DWARF_TEFF, M_DWARF_RADIUS = 4000.0, 0.6
K_DWARF_TEFF, K_DWARF_RADIUS = 5300.0, 0.9


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def enumerate_sector(sector: int) -> list[str]:
    """The survey's own enumeration — a04.sector_targets, paged to exhaustion."""
    tics = a04.sector_targets(sector, max_pages=12, pagesize=500)
    print(f"  sector {sector}: {len(tics)} SPOC 2-min targets")
    return tics


def fetch_tic_params(tics: list[str]) -> dict[str, dict]:
    """Bulk TIC catalog rows keyed by TIC id (chunked MAST filtered query)."""
    out: dict[str, dict] = {}
    chunks = list(_chunks(sorted(tics), 400))
    for i, chunk in enumerate(chunks):
        rows = a01._mast("Mast.Catalogs.Filtered.Tic", {
            "columns": "ID,ra,dec,Tmag,Teff,rad,mass,logg,lumclass,d,contratio,objType",
            "filters": [{"paramName": "ID",
                         "values": [str(t) for t in chunk]}],
        }, pagesize=500, page=1)
        for r in rows:
            out[str(r.get("ID"))] = r
        print(f"  TIC params: chunk {i + 1}/{len(chunks)} → {len(out)} rows")
        time.sleep(0.4)
    return out


def fetch_simbad_otypes(tics: list[str]) -> dict[str, str]:
    """otype per TIC via SIMBAD TAP, matching on the 'TIC nnn' identifier.

    A TIC absent from SIMBAD returns nothing — that is fine and expected
    (uncatalogued = no external kill information, not a problem).
    """
    out: dict[str, str] = {}
    chunks = list(_chunks(sorted(tics), 200))
    for i, chunk in enumerate(chunks):
        idlist = ",".join(f"'TIC {t}'" for t in chunk)
        adql = ("SELECT ident.id, basic.otype FROM ident "
                "JOIN basic ON ident.oidref = basic.oid "
                f"WHERE ident.id IN ({idlist})")
        data = urllib.parse.urlencode({
            "request": "doQuery", "lang": "adql", "format": "json",
            "query": adql,
        }).encode("ascii")
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(SIMBAD_TAP, data=data),
                    timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            for ident, otype in payload.get("data", []):
                out[str(ident).replace("TIC", "").strip()] = str(otype)
        except Exception as exc:  # noqa: BLE001 — a failed chunk is a gap, not an abort
            print(f"  SIMBAD chunk {i + 1}/{len(chunks)} FAILED: {exc}")
        if (i + 1) % 5 == 0 or i + 1 == len(chunks):
            print(f"  SIMBAD: chunk {i + 1}/{len(chunks)} → {len(out)} matches")
        time.sleep(0.6)
    return out


def fetch_toi_tics() -> set[str]:
    with urllib.request.urlopen(TOI_CSV, timeout=120) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    lines = text.splitlines()
    header = lines[0].split(",")
    tic_col = next(i for i, h in enumerate(header) if h.strip().lower() == "tic id")
    tics = {line.split(",")[tic_col].strip() for line in lines[1:] if line.strip()}
    print(f"  TOI table: {len(tics)} distinct TICs")
    return tics


def classify(tic: str, params: dict | None, otype: str | None,
             has_toi: bool) -> dict:
    teff = params.get("Teff") if params else None
    rad = params.get("rad") if params else None
    lum = str(params.get("lumclass") or "") if params else ""
    row = {
        "tic": tic,
        "teff": teff, "radius": rad, "tmag": params.get("Tmag") if params else None,
        "mass": params.get("mass") if params else None,
        "lumclass": lum or None, "distance_pc": params.get("d") if params else None,
        "contratio": params.get("contratio") if params else None,
        "simbad_otype": otype, "has_toi": has_toi,
        "flags": [],
    }
    if otype in KILL_OTYPES:
        row["flags"].append("known-binary-or-variable")
    if (isinstance(rad, (int, float)) and rad > EVOLVED_RADIUS) or lum.upper() == "GIANT":
        row["flags"].append("evolved-host")
    if has_toi:
        row["flags"].append("has-toi")
    killed = any(f in ("known-binary-or-variable", "evolved-host")
                 for f in row["flags"])
    if not killed and isinstance(teff, (int, float)) and isinstance(rad, (int, float)):
        if teff < M_DWARF_TEFF and rad < M_DWARF_RADIUS:
            row["flags"].append("quiet-m-dwarf-peak")
        elif teff < K_DWARF_TEFF and rad < K_DWARF_RADIUS:
            row["flags"].append("k-dwarf")
    if params is None:
        row["flags"].append("no-tic-params")
    # v1 yield score — occurrence-weighted, detectability-weighted, kills to 0.
    # Printed thresholds; re-arguable without re-fetching. Occurrence weights
    # are coarse class priors (M dwarfs host the most small transiting
    # planets), detectability rewards deep transits (small R) and bright
    # hosts (low noise): score = occ * (1/rad^2) * 10^(-0.2*(Tmag-10)).
    score = 0.0
    if not killed and isinstance(rad, (int, float)) and rad > 0 \
            and isinstance(row["tmag"], (int, float)):
        occ = (2.5 if "quiet-m-dwarf-peak" in row["flags"]
               else 1.2 if "k-dwarf" in row["flags"] else 0.7)
        score = occ * (1.0 / rad ** 2) * 10 ** (-0.2 * (row["tmag"] - 10.0))
    row["yield_score"] = round(score, 4)
    return row


def main() -> int:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    sectors: dict[int, list[str]] = {}
    print("enumerating lane sectors (a04.sector_targets — the survey's own list):")
    for lane, secs in LANES.items():
        for s in secs:
            sectors[s] = enumerate_sector(s)
    all_tics = sorted({t for tics in sectors.values() for t in tics})
    print(f"  union: {len(all_tics)} distinct targets across {len(sectors)} sectors")

    print("fetching TIC stellar parameters (bulk MAST):")
    tic_params = fetch_tic_params(all_tics)
    print("fetching SIMBAD otypes (bulk TAP by identifier):")
    otypes = fetch_simbad_otypes(all_tics)
    print("fetching the TOI table (ExoFOP):")
    toi = fetch_toi_tics()

    rows = {t: classify(t, tic_params.get(t), otypes.get(t), t in toi)
            for t in all_tics}

    census = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "consumers": "Ben (survey strategy) + the future hunt prioritizer",
        "lanes": {lane: list(secs) for lane, secs in LANES.items()},
        "sectors": {str(s): tics for s, tics in sectors.items()},
        "thresholds": {
            "kill_otypes": sorted(KILL_OTYPES),
            "evolved_radius_rsun": EVOLVED_RADIUS,
            "m_dwarf": {"teff_max": M_DWARF_TEFF, "radius_max": M_DWARF_RADIUS},
            "k_dwarf": {"teff_max": K_DWARF_TEFF, "radius_max": K_DWARF_RADIUS},
        },
        "targets": rows,
        "wall_seconds": round(time.time() - t0, 1),
    }
    json_path = OUT_DIR / f"lane-census-{stamp}.json"
    json_path.write_text(json.dumps(census, indent=1), encoding="utf-8")
    print(f"census json -> {json_path}")

    # ── the human map ────────────────────────────────────────────────────────
    def count(flag, tics):
        return sum(1 for t in tics if flag in rows[t]["flags"])

    lines = [f"# Lane census — {stamp}",
             "",
             "**Consumers:** Ben (the survey-strategy call) + the future hunt",
             "prioritizer. Regenerate: `python scripts/survey_census.py` (pure",
             "catalog I/O; ~10 min). Data: `lane-census-" + stamp + ".json`.",
             "",
             "Born from the night both leads died in two minutes of external",
             "catalog checks (SIMBAD SB* + implied radii of 2.3/2.8 R_Jup).",
             ""]
    for lane, secs in LANES.items():
        for s in secs:
            tics = sectors[s]
            n = len(tics)
            if n == 0:
                lines += [f"## {lane} · sector {s} — ENUMERATION EMPTY", ""]
                continue
            killed = sum(1 for t in tics if any(
                f in ("known-binary-or-variable", "evolved-host")
                for f in rows[t]["flags"]))
            lines += [
                f"## {lane} · sector {s} — {n} targets",
                "",
                f"- known binary/variable (SIMBAD): **{count('known-binary-or-variable', tics)}**",
                f"- evolved host (R>1.5 R_Sun / giant): **{count('evolved-host', tics)}**",
                f"- has TOI already: {count('has-toi', tics)}",
                f"- no TIC params resolved: {count('no-tic-params', tics)}",
                f"- **KILLED before search: {killed} ({100 * killed / n:.0f}%)**",
                f"- 🏔 quiet M dwarfs (peak class): **{count('quiet-m-dwarf-peak', tics)}**",
                f"- K dwarfs: {count('k-dwarf', tics)}",
                "",
            ]
    ranked = sorted((r for r in rows.values() if r["yield_score"] > 0),
                    key=lambda r: -r["yield_score"])
    lines += ["## Top 40 by v1 yield score (union of lanes)", "",
              "| TIC | Teff | R★ | Tmag | flags | score |",
              "|---|---|---|---|---|---|"]
    for r in ranked[:40]:
        lines.append(f"| {r['tic']} | {r['teff']} | {r['radius']} | "
                     f"{r['tmag']} | {','.join(r['flags']) or '—'} | "
                     f"{r['yield_score']} |")
    lines += ["",
              f"_{census['wall_seconds']}s · thresholds in the JSON · score = "
              "occ(class) × R★⁻² × 10^(−0.2·(Tmag−10)), kills → 0_", ""]
    md_path = OUT_DIR / f"{stamp}-lane-census.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"census map  -> {md_path}")
    print(f"done in {census['wall_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
