#!/usr/bin/env python3
"""Second-sector follow-up for a PARKED lead — the look the shelf asks for.

`shelf.register` parks a lead on "persistence: detected in 1 sector — §4
requires >= 2". Nothing in the estate ever went and searched a second sector:
the hunt driver draws its sample by consistent hash and cannot be pointed at a
star. This can. It runs the full A05 ladder — same B, same controls, same
placebo, same sky gates — on ONE named star plus a hash-drawn sample from the
same sector large enough that the receipt's uniformity control can grade
(CONTROL_FRACTION × n >= checks.A05_UNIFORMITY_MIN_N), and files a receipt the
publish gate can accept or refuse on exactly the terms every other receipt is
held to. If the star crosses again, `shelf` sees two sectors and grades
period/depth consistency; if it does not, that non-detection rides along in
the receipt as the pipeline's own statement about the star.

    python3 scripts/a05_followup.py --tic 374861595 --sector 31

Writes `reports/hunts/followup-<tic>-s<sector>.json` (uncommitted — the
publish decision stays a human's) and prints the checker's verdict.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lab import a01, a04, a05, a05_sky, checks          # noqa: E402
from lab.labhome import LAB_HOME                         # noqa: E402
import a05_hunt as driver                                # noqa: E402


def load_curve_deep(tic: str, sector: int, cache_dir=None) -> dict | None:
    """`a05.load_curve` discovers at most 4 products, which reaches sector ~31
    for a star observed since sector 27 and never reaches sector 61. A
    follow-up has to be able to open ANY sector the star has a product in."""
    cache_dir = cache_dir or a01.CACHE_DIR
    products = a01.discover_spoc_light_curves(tic, max_sectors=80)
    product = next((p for p in products if p.get("sector") == sector), None)
    if product is None:
        return None
    blob, meta = a01._download_product(product, cache_dir)
    out = a05.curve_from_blob(blob)
    out["cache_file"] = str(meta.get("filename") or "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tic", required=True)
    ap.add_argument("--sector", type=int, required=True)
    ap.add_argument("--n", type=int, default=40, help="total targets incl. the star")
    ap.add_argument("--control-fraction", type=float, default=0.20)
    ap.add_argument("--minutes", type=float, default=120.0)
    ap.add_argument("--workers", type=int, default=driver.MAX_WORKERS)
    ap.add_argument("--B", type=int, default=256)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    need = checks.A05_UNIFORMITY_MIN_N
    if int(args.n * args.control_fraction) < need:
        print(f"refusing: {args.n} × {args.control_fraction} < {need} control rows — "
              "the receipt's uniformity control could not grade and it would be refused")
        return 2

    t0 = time.time()
    hunt_id = f"followup-{args.tic}-s{args.sector}"
    ckpt = LAB_HOME / f"a05-{hunt_id}.jsonl"
    ckpt.parent.mkdir(parents=True, exist_ok=True)

    pool_tics = [t for t in a04.sector_targets(args.sector) if t != args.tic]
    already = driver.prior_targets()
    pool_tics = [t for t in pool_tics if t not in already]
    sample = a04.sample_targets(pool_tics, args.n - 1, seed=args.seed)
    targets = [args.tic] + sample
    print(f"{hunt_id}: the star + {len(sample)} hash-drawn sector-{args.sector} targets "
          f"({len(pool_tics)} eligible), control fraction {args.control_fraction}")

    done_rows: list[dict] = []
    if ckpt.exists():
        done_rows = [json.loads(l) for l in ckpt.read_text().splitlines() if l.strip()]
        done_rows, _retry = driver.split_resumable(done_rows)
        print(f"resuming: {len(done_rows)} rows checkpointed")
    out = ckpt.open("a", encoding="utf-8")

    def on_row(row: dict) -> None:
        out.write(json.dumps(row) + "\n"); out.flush()
        sde = row.get("sde")
        note = f"SDE {sde:.1f}" if isinstance(sde, float) else row.get("outcome")
        star = "  <-- THE STAR" if row.get("tic") == args.tic else ""
        print(f"  TIC {row['tic']}: {note}"
              f"{(' -> ' + row['disposition']) if row.get('disposition') else ''}{star}",
              flush=True)

    sky_deadline = t0 + args.minutes * 60.0 + driver.SKY_LOOKUP_GRACE_SECONDS
    n_workers = max(1, min(args.workers, driver.MAX_WORKERS, cpu_count()))
    with Pool(n_workers) as pool:
        result = a05.run_a05(
            sector=args.sector, n_targets=len(targets), seed=args.seed,
            targets=targets, done_rows=done_rows,
            control_fraction=args.control_fraction,
            curve_loader=functools.partial(load_curve_deep, sector=args.sector),
            B=args.B, deadline=t0 + args.minutes * 60.0,
            soft_budget_seconds=args.minutes * 60.0,
            neighbours=functools.partial(a05_sky.resolve_neighbours, deadline=sky_deadline),
            sky_catalog=functools.partial(a05_sky.sky_catalog_lookup, deadline=sky_deadline),
            on_row=on_row, pool_map=pool.map, hunt_id=hunt_id)
    out.close()

    if not result.complete:
        print(f"[budget] soft wall reached with {len(result.rows)} rows checkpointed; "
              "rerun the same command to resume — no receipt for an incomplete slice")
        return 0

    report = a05.to_report(result, prior_floor_history=tuple(driver.floor_history()),
                           provenance=driver.provenance(),
                           pooled_null=driver.pooled_null_declaration())
    report["follow_up_for"] = {"tic": args.tic, "parked_on": "persistence: detected in 1 sector"}
    hunts_dir = REPO_ROOT / "reports/hunts"
    path = hunts_dir / f"{hunt_id}.json"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(report, indent=1)); os.fsync(f.fileno())
    tmp.replace(path)
    for tic, html in result.dossiers.items():
        d = hunts_dir / "dossiers"; d.mkdir(exist_ok=True)
        (d / f"{hunt_id}-tic{tic}.html").write_text(html, encoding="utf-8")

    ok, why = checks.check_a05(report)
    from lab.publish import _hunt_refusal
    star = next((r for r in report["targets"] if r.get("tic") == args.tic), None)
    print(f"\nreceipt -> {path}")
    print(f"check_a05: {ok} — {why[:200]}")
    print(f"_hunt_refusal: {_hunt_refusal(report, path)}")
    print(f"THE STAR: {json.dumps({k: star.get(k) for k in ('outcome','sde','period_days','depth','disposition')}) if star else 'not in receipt'}")
    print(f"wall {(time.time()-t0)/60:.0f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
