#!/usr/bin/env python3
"""Bulk epoch-scramble campaign — turn U-A01's extrapolation into a measurement.

U-A01 established that the transit shelf's promotion threshold can be *priced*,
but only through a tail model: 1,400 pooled null draws never reached SDE 8.0
(largest ever 7.00), so the per-curve false-alarm probability is an
extrapolation one full SDE beyond the data. That extrapolation is the
difference between **0.61 expected false alarms across the survey** — under
which a crossing matters — and the model-free bound of **21**, under which a
crossing proves nothing.

The fix needs no cleverness, only draws. A scrambled light curve is by
construction a sample from the null, the curves are already on disk, and the
work is embarrassingly parallel CPU that does not compete with the GPU lane.
Enough of them and the tail model stops being load-bearing, because the
threshold region is inside the sample.

Resumable by design: a campaign that must complete in one sitting will be
killed by a reboot and start from nothing. Every (curve, seed) already recorded
is skipped, so this can be stopped and restarted freely.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np                                              # noqa: E402
from lab import a01, a04, a05, a05_sensitivity as sens          # noqa: E402

OUT = Path(os.environ.get("SCRAMBLE_OUT",
                          Path.home() / ".lab" / "scramble-null.jsonl"))
TARGET = int(os.environ.get("SCRAMBLE_TARGET", 325_000))
WORKERS = int(os.environ.get("SCRAMBLE_WORKERS", 12))
MIN_POINTS = 500


def one(job):
    """One null draw: scramble a real curve, run the real search, keep the SDE."""
    path, seed = job
    try:
        c = a05.curve_from_blob(Path(path).read_bytes())
        t = np.asarray(c["t"], float)
        f = np.asarray(c["f"], float)
        m = np.isfinite(t) & np.isfinite(f)
        t, f = t[m], f[m]
        if t.size < MIN_POINTS:
            return None
        ts, fs = sens.epoch_scramble(t, f, seed=seed)
        det = a04.blind_search(ts, fs)
        return {"curve": Path(path).name, "seed": seed,
                "sde": float(det.sde), "period_days": float(det.period_days),
                "n": int(t.size)}
    except Exception as e:                                       # noqa: BLE001
        # A single unreadable product must not kill a 17-hour campaign, but it
        # must not vanish either — a silently shrinking sample biases the null.
        return {"curve": Path(path).name, "seed": seed, "error": type(e).__name__}


def done_pairs() -> set:
    if not OUT.exists():
        return set()
    seen = set()
    with OUT.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
                seen.add((r["curve"], r["seed"]))
            except Exception:                                    # noqa: BLE001
                continue
    return seen


def main() -> int:
    curves = sorted(glob.glob(str(a01.CACHE_DIR) + "/**/*.fits", recursive=True))
    if not curves:
        print("no cached light curves — nothing to scramble", file=sys.stderr)
        return 1
    seen = done_pairs()
    print(f"{len(curves):,} cached curves · {len(seen):,} draws already recorded "
          f"· target {TARGET:,} · {WORKERS} workers", flush=True)

    # Seeds cycle OUTSIDE the curve loop so that stopping early still leaves a
    # sample spread across every curve rather than exhausting the first few —
    # a null built from 40 seeds of 30 stars is not the same null.
    jobs = []
    seed = 0
    while len(seen) + len(jobs) < TARGET:
        seed += 1
        for p in curves:
            key = (Path(p).name, seed)
            if key in seen:
                continue
            jobs.append((p, seed))
            if len(seen) + len(jobs) >= TARGET:
                break
    if not jobs:
        print("target already reached", flush=True)
        return 0

    t0 = time.time()
    written = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh, Pool(WORKERS) as pool:
        for rec in pool.imap_unordered(one, jobs, chunksize=8):
            if rec is None:
                continue
            fh.write(json.dumps(rec) + "\n")
            written += 1
            if written % 500 == 0:
                fh.flush()
                rate = written / max(time.time() - t0, 1e-9)
                total = len(seen) + written
                eta = (TARGET - total) / rate / 3600 if rate else float("inf")
                print(f"[{time.time()-t0:7.0f}s] {total:,}/{TARGET:,} "
                      f"({rate:.1f}/s, ETA {eta:.1f} h)", flush=True)
    print(f"done: {written:,} new draws in {(time.time()-t0)/3600:.2f} h", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
