"""A04 discovery pilot — point the calibrated blind search at stars nobody designated.

A04 (promoted 2026-08-14) earned a narrow claim: the blind BLS search + vetting
stack recovers confirmed planets it was never told about, and its SDE >= 8
threshold sits in a measured gap between injected transits and the noise floor.
This pilot is the rung that claim was FOR: run the same instrument over the
next slice of the sector sample — stars the graded run never touched — and see
whether anything survives vetting that the catalog does NOT already know.

Honesty first: every 2-minute SPOC target has been worked by the official SPOC
pipeline and years of community searches, so the expected outcome is recoveries
of already-known planets and a stack of vetted rejections. That is still the
right experiment — the discovery loop has to exist and run clean before it can
ever get lucky — and a candidate with an EMPTY catalog row is precisely the
artifact Ben's review gate exists for.

Protocol (identical to lab a04, aperture widened):
  * same consistent-hash ranking, same seed — the hunt slice is the SAME
    deterministic ordering the graded run used, minus everything it searched,
    so the sample stays predeclared rather than cherry-picked;
  * same grid, detrend, SDE ranking, odd-even / secondary / rail vetting;
  * injection control re-run on this slice's own host star (sensitivity is
    re-proven per run, never inherited);
  * catalog cross-check at report time only, never during the search.

Results checkpoint to ~/.lab/a04-hunt-<date>.jsonl per target (crash lesson:
commit code before long runs, checkpoint results during them).

Usage:  python scripts/a04_hunt.py [--n 150] [--sector 2] [--minutes 50]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from lab import a01, a04

LAB_HOME = Path(a01.CACHE_DIR).parent if hasattr(a01, "CACHE_DIR") else Path.home() / ".lab"


def hunt_slice(sector: int, n: int, already: set[str]) -> list[str]:
    """The next `n` targets in A04's own deterministic ranking, skipping
    everything the graded run searched (and the designated recovery targets —
    they are calibration, not hunt territory)."""
    tics = a04.sector_targets(sector, max_pages=8)
    pool = [t for t in tics
            if t not in already and t not in a04.RECOVERY_TARGETS]

    def rank(tic: str) -> bytes:
        return hashlib.sha256(f"2026|{tic}".encode()).digest()

    return sorted(pool, key=rank)[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--sector", type=int, default=a04.DEFAULT_SECTOR)
    ap.add_argument("--minutes", type=float, default=50.0,
                    help="soft wall-clock budget; stops cleanly, resume by rerun")
    args = ap.parse_args()

    t0 = time.time()
    deadline = t0 + args.minutes * 60
    stamp = date.today().isoformat()
    ckpt = LAB_HOME / f"a04-hunt-{stamp}-s{args.sector}.jsonl"
    ckpt.parent.mkdir(parents=True, exist_ok=True)

    # What the graded run already searched — from its committed receipt.
    receipt = json.loads(
        (Path(__file__).resolve().parents[1]
         / "reports/receipts/run-2026-08-08-2338-a04.json").read_text(encoding="utf-8"))
    rep = receipt.get("report", receipt)
    already = {row["tic"] for row in rep.get("searched", [])}
    print(f"graded run searched {len(already)} targets; excluding them")

    done: set[str] = set()
    rows: list[dict] = []
    if ckpt.exists():
        for line in ckpt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows.append(row)
                done.add(row["tic"])
        print(f"resuming: {len(done)} targets already checkpointed")

    targets = hunt_slice(args.sector, args.n, already)
    print(f"hunt slice: {len(targets)} targets, sector {args.sector}")

    curves_host = None       # first clean curve, for the injection control
    with ckpt.open("a", encoding="utf-8") as out:
        for i, tic in enumerate(targets):
            if tic in done:
                continue
            if time.time() > deadline:
                print(f"[budget] soft wall reached after {i} targets; rerun to resume")
                break
            try:
                tf = a04.light_curve(tic, args.sector)
            except Exception as e:  # noqa: BLE001 — one bad target must not sink the hunt
                row = {"tic": tic, "error": type(e).__name__}
                out.write(json.dumps(row) + "\n"); out.flush()
                rows.append(row)
                continue
            if tf is None:
                row = {"tic": tic, "skipped": "no product in sector"}
                out.write(json.dumps(row) + "\n"); out.flush()
                rows.append(row)
                continue
            det = a04.blind_search(*tf)
            row = {"tic": tic, "period_days": det.period_days, "depth": det.depth,
                   "phase": det.phase, "sde": det.sde}
            if det.sde >= a04.SDE_THRESHOLD:
                row["vetting"] = a04.vet_candidate(*tf, det)
                row["catalog"] = a04.catalog_crosscheck(tic)
                v = row["vetting"].get("verdict")
                known = row["catalog"].get("known_planet") or row["catalog"].get("known_toi")
                tag = "KNOWN" if known else ("*** UNCATALOGUED ***" if v == "planet-candidate" else "")
                print(f"  [{i+1}/{len(targets)}] TIC {tic}: SDE {det.sde:.1f} "
                      f"P={det.period_days:.4f} d -> {v} {tag}")
            else:
                print(f"  [{i+1}/{len(targets)}] TIC {tic}: SDE {det.sde:.1f} (floor)")
            if curves_host is None and det.sde < a04.SDE_THRESHOLD:
                curves_host = (tic, tf)
            out.write(json.dumps(row) + "\n"); out.flush()
            rows.append(row)

    # Injection control on this slice's own quietest usable host.
    injections = []
    if curves_host is not None:
        host, (t, f) = curves_host
        for depth, period in a04.INJECTIONS:
            det = a04.blind_search(t, a04.inject_box(t, f, period, depth))
            err = abs(det.period_days / period - 1.0)
            injections.append({
                "host_tic": host, "injected_depth": depth,
                "injected_period_days": period,
                "recovered_period_days": det.period_days, "sde": det.sde,
                "recovered": bool(err <= a04.PERIOD_TOL_FRAC
                                  and det.sde >= a04.SDE_THRESHOLD),
            })
        print("injection control:",
              f"{sum(i['recovered'] for i in injections)}/{len(injections)} recovered")

    searched = [r for r in rows if "sde" in r]
    floor = [r["sde"] for r in searched if r["sde"] < a04.SDE_THRESHOLD]
    hits = [r for r in searched if r["sde"] >= a04.SDE_THRESHOLD]
    uncatalogued = [
        r for r in hits
        if r.get("vetting", {}).get("verdict") == "planet-candidate"
        and not r.get("catalog", {}).get("lookup_error")
        and not (r.get("catalog", {}).get("known_planet")
                 or r.get("catalog", {}).get("known_toi"))]

    summary = {
        "experiment": "a04-discovery-pilot",
        "date": stamp,
        "sector": args.sector,
        "slice_rule": "next targets in A04's consistent-hash ranking, graded-run "
                      "targets and designated recovery targets excluded",
        "targets_attempted": len(rows),
        "targets_searched": len(searched),
        "above_threshold": len(hits),
        "floor_max_sde": max(floor) if floor else None,
        "floor_n": len(floor),
        "injections": injections,
        "control_passed": bool(injections and all(i["recovered"] for i in injections)),
        "hits": hits,
        "uncatalogued_planet_candidates": uncatalogued,
        "wall_seconds": time.time() - t0,
        "claim_boundary": (
            "A pilot over a deterministic slice of one sector's 2-minute SPOC "
            "targets — territory the official pipeline has already searched. "
            "An uncatalogued planet-candidate here is a lead for human review "
            "and independent follow-up, not a discovery; nothing is submitted "
            "anywhere on the strength of this script."),
    }
    out_path = LAB_HOME / f"a04-hunt-{stamp}-s{args.sector}-summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nsummary -> {out_path}")
    print(f"searched {len(searched)}, {len(hits)} above threshold, "
          f"{len(uncatalogued)} uncatalogued planet-candidate(s), "
          f"floor max {summary['floor_max_sde']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
