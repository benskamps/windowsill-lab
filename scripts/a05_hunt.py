"""A05 survey hunt — the receipts-grade driver for the survey pipeline.

Promotes ``scripts/a04_hunt.py``'s driver shape to the A05 contract:

* **Resumable**: every completed target appends one JSONL row to
  ``$LAB_HOME/a05-hunt-<date>-s<sector>.jsonl`` the moment it finishes. A
  crash or a soft budget stop loses at most the in-flight chunk; rerunning
  the same command resumes from the checkpoint and — because stage-2
  decisions, control membership, and per-target seeds are all content-hashed,
  never order-dependent — produces the same rows it would have produced in
  one sitting.
* **Soft minutes budget**: the deadline stops the run CLEANLY between
  targets; an early-stopped run writes no receipt (an incomplete slice must
  never masquerade as a survey — ``to_report`` refuses it).
* **Bounded parallelism**: the permutation stage is the only expensive pure
  compute, so it fans out over a stdlib ``multiprocessing`` pool capped at
  ``MAX_WORKERS`` = 12 processes, each running single-target numpy. Network
  (MAST) stays serial in the main process — parallel downloads would only
  move the bottleneck onto someone else's server.
* **Receipt at wrap**: the completed run becomes
  ``reports/hunts/hunt-<date>-s<sector>.json`` (the schema of
  ``docs/a05-receipt-schema.md``), lead dossiers land next to it under
  ``reports/hunts/dossiers/``, and ``checks.check_a05`` is run on the fresh
  receipt immediately so a malformed receipt is caught at birth, not at CI.

Prior-target exclusion pulls from every earlier artifact on disk: the A04
graded receipt, the A04 pilot checkpoints, prior A05 checkpoints, and prior
hunt receipts. Floor history likewise folds in every hunt summary found in
``LAB_HOME`` (so the 2026-08-14 wide hunt's floor joins the receipt as soon
as its summary exists) on top of the schema doc's two prior points.

Usage:  python scripts/a05_hunt.py [--n 500] [--sector 2] [--minutes 50]
                                   [--workers 12] [--B 256]
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import date
from multiprocessing import Pool, cpu_count
from pathlib import Path

from lab import a05, checks
from lab.labhome import LAB_HOME

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Hard cap on worker processes for the permutation stage. Each worker is
#: single-target numpy; 12 saturates the 16-core box while leaving headroom
#: for the main process's downloads and the OS.
MAX_WORKERS = 12


def prior_targets() -> set[str]:
    """Every TIC any earlier graded run, pilot, or hunt already touched."""
    already: set[str] = set()
    graded = REPO_ROOT / "reports/receipts/run-2026-08-08-2338-a04.json"
    if graded.exists():
        receipt = json.loads(graded.read_text(encoding="utf-8"))
        rep = receipt.get("report", receipt)
        already |= {row["tic"] for row in rep.get("searched", [])}
    for pattern in ("a04-hunt-*.jsonl", "a05-hunt-*.jsonl"):
        for path in LAB_HOME.glob(pattern):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        already.add(json.loads(line)["tic"])
                    except (ValueError, KeyError):
                        continue
    hunts_dir = REPO_ROOT / "reports/hunts"
    if hunts_dir.exists():
        for path in hunts_dir.glob("hunt-*.json"):
            try:
                rep = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            already |= {row.get("tic") for row in rep.get("targets", [])
                        if row.get("tic")}
    return already


def floor_history() -> list[dict]:
    """The schema doc's prior floor points plus every hunt summary on disk."""
    points = [dict(p) for p in a05.PRIOR_FLOOR_HISTORY]
    seen = {p["source"] for p in points}
    for path in sorted(LAB_HOME.glob("a04-hunt-*-summary.json")):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        source = path.stem.replace("-summary", "")
        n, floor_max = s.get("floor_n"), s.get("floor_max_sde")
        if source not in seen and n and floor_max is not None:
            points.append({"n": int(n), "floor_max": float(floor_max),
                           "source": source})
            seen.add(source)
    return points


def provenance() -> dict:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001 — provenance is reported, never graded
        sha = ""
    return {"machine": platform.node(),
            "code_sha": sha,
            "python": platform.python_version()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--sector", type=int, default=2)
    ap.add_argument("--minutes", type=float, default=50.0,
                    help="soft wall-clock budget; stops cleanly, resume by rerun")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--B", type=int, default=256)
    args = ap.parse_args()

    t0 = time.time()
    stamp = date.today().isoformat()
    hunt_id = f"hunt-{stamp}-s{args.sector}"
    ckpt = LAB_HOME / f"a05-{hunt_id}.jsonl"
    ckpt.parent.mkdir(parents=True, exist_ok=True)

    done_rows: list[dict] = []
    if ckpt.exists():
        for line in ckpt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done_rows.append(json.loads(line))
        print(f"resuming: {len(done_rows)} targets already checkpointed")

    already = prior_targets() - {r["tic"] for r in done_rows}
    print(f"excluding {len(already)} previously searched targets")

    out = ckpt.open("a", encoding="utf-8")

    def on_row(row: dict) -> None:
        out.write(json.dumps(row) + "\n")
        out.flush()
        sde = row.get("sde")
        note = f"SDE {sde:.1f}" if isinstance(sde, float) else row.get("outcome")
        extra = f" -> {row['disposition']}" if row.get("disposition") else ""
        print(f"  TIC {row['tic']}: {note}{extra}")

    n_workers = max(1, min(args.workers, MAX_WORKERS, cpu_count()))
    with Pool(n_workers) as pool:
        result = a05.run_a05(
            sector=args.sector, n_targets=args.n,
            already=already, done_rows=done_rows,
            B=args.B, deadline=t0 + args.minutes * 60.0,
            soft_budget_seconds=args.minutes * 60.0,
            on_row=on_row, pool_map=pool.map, hunt_id=hunt_id)
    out.close()

    if not result.complete:
        print(f"[budget] soft wall reached with {len(result.rows)} rows "
              "checkpointed; rerun the same command to resume — no receipt "
              "is written for an incomplete slice")
        return 0

    report = a05.to_report(result, prior_floor_history=tuple(floor_history()),
                           provenance=provenance())
    hunts_dir = REPO_ROOT / "reports/hunts"
    hunts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = hunts_dir / f"{hunt_id}.json"
    receipt_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for tic, html in result.dossiers.items():
        dossier_dir = hunts_dir / "dossiers"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        (dossier_dir / f"{hunt_id}-tic{tic}.html").write_text(
            html, encoding="utf-8")

    counts = report["counts"]
    print(f"\nreceipt -> {receipt_path}")
    print(f"searched {counts['searched']}/{counts['attempted']}, "
          f"stage2 {counts['stage2']}, above threshold "
          f"{counts['above_threshold']}, leads "
          f"{counts['leads_awaiting_human_review']}")
    ok, detail = checks.check_a05(report)
    print(f"check_a05: {ok} — {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
