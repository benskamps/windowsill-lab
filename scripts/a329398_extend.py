#!/usr/bin/env python3
"""Extend A329398 — the long run, resumable, from the tested lab module.

Imports `lab.a329398` rather than carrying its own copy of the solver, so the
terms that reach an OEIS editor were produced by the code the test suite grades.
A scratchpad twin of the algorithm is how a fix lands in one place and a number
comes out of the other.

RESUMABLE, because this is a run measured in hours and a lost session should not
cost the whole thing: every term is written to a store under LAB_HOME as soon as
it is computed, and a restart recomputes nothing it already has. The store is
keyed by n and holds BOTH methods' answers, so a resumed run cannot quietly
inherit an unchecked term.

Every term, cached or fresh, is re-checked against the witness and against the
published values on the way out — resuming must not skip the controls.

Usage:
  python3 scripts/a329398_extend.py --to 46 [--log FILE] [--store FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from lab import a329398  # noqa: E402


def store_path(explicit: str | None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit)
    root = os.environ.get("LAB_HOME") or (pathlib.Path.home() / ".lab")
    d = pathlib.Path(root) / "c03"
    d.mkdir(parents=True, exist_ok=True)
    return d / "A329398.json"


def load_store(path: pathlib.Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {int(k): v for k, v in raw.items()}


def save_store(path: pathlib.Path, store: dict[int, dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({str(k): v for k, v in sorted(store.items())},
                              indent=0, sort_keys=True))
    tmp.replace(path)                      # atomic; a killed run cannot truncate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", type=int, required=True)
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--log", default=None)
    ap.add_argument("--store", default=None)
    ns = ap.parse_args()

    spath = store_path(ns.store)
    store = load_store(spath)
    log = open(ns.log, "a", buffering=1) if ns.log else sys.stdout

    published = a329398.PUBLISHED
    prev_dt = None
    for n in range(ns.start, ns.to + 1):
        cached = n in store
        t0 = time.time()
        if cached:
            brute = int(store[n]["brute"])
            dt = 0.0
        else:
            brute = a329398.count(n)
            dt = time.time() - t0
        conj = a329398.witness(n)

        # The controls run on EVERY term, cached or fresh. A resumed run that
        # trusted its own store would be a pipeline with a hole in the middle.
        ref = published[n - 1] if n <= len(published) else None
        if ref is not None and brute != ref:
            print(f"n={n} FATAL: solver returned {brute}, OEIS publishes {ref} "
                  "— stopping, nothing here is submittable", file=sys.stderr)
            return 1
        if brute != conj:
            print(f"n={n} *** METHODS DIVERGE *** brute={brute} conj={conj}\n"
                  "  This is either a bug or a counterexample to Wiseman's "
                  "conjecture. Stopping so a human looks at it.", file=sys.stderr)
            store[n] = {"brute": brute, "conj": conj, "diverged": True}
            save_store(spath, store)
            return 2

        store[n] = {"brute": brute, "conj": conj,
                    "published": ref, "seconds": round(dt, 3)}
        save_store(spath, store)

        verdict = "OK" if ref is not None else "NEW - methods agree"
        line = (f"n={n:>3} brute={brute:>12} conj={conj:>12} "
                f"oeis={str(ref):>12} {verdict:<22} {dt:9.2f}s"
                + ("  [cached]" if cached else "")
                + (f"  x{dt/prev_dt:.2f}" if prev_dt and prev_dt > 0.05 and dt else ""))
        print(line, file=log, flush=True)
        if dt:
            prev_dt = dt
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
