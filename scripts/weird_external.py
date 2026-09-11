#!/usr/bin/env python3
"""Point `weird` at public corpora nobody in this estate produced.

The estate sweep tested portability across five corpora we made. This tests it
against data made by other people, other instruments, other centuries of
convention — and in four different sciences:

  quakes   every seismic event on Earth for 30 days      USGS, geophysics
  sec      total assets of every US public company       SEC EDGAR, finance
  gaia     20,000 stars sampled from 1.8 billion         ESA Gaia DR3
  toi      8,148 TESS Objects of Interest                NASA, exoplanets
  ps       6,360 confirmed planets, 1992-2026            NASA, the gold record

Nothing in the families knows what a magnitude, a balance sheet, a parallax or
a transit depth is. That is the whole point: if the tool needs to be told, it
was never a tool.

A WARNING TO MYSELF, WRITTEN BEFORE THE RESULTS. These corpora are curated by
professionals who know their own conventions. Anything flagged here is far more
likely to be a documented convention than a defect, and the honest reading of
any finding is "what convention produces this shape?", never "NASA has a bug".
The one time today I skipped that step I had to retract a headline within hours.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from lab import weird  # noqa: E402

T = pathlib.Path("/tmp")


def _rows(objs, ident, src):
    out = []
    for i, o in enumerate(objs):
        flat = weird.flatten(o)
        if not flat:
            continue
        flat["_id"] = str(ident(o, i))
        flat["_src"] = str(src(o))
        out.append(flat)
    return out


def corpus_quakes():
    d = json.loads((T / "quakes.json").read_text())
    objs = []
    for f in d["features"]:
        p = dict(f.get("properties") or {})
        g = (f.get("geometry") or {}).get("coordinates") or [None, None, None]
        for k, v in zip(("lon", "lat", "depth_km"), g):
            if isinstance(v, (int, float)):
                p[k] = v
        p["_ident"] = f.get("id")
        p["_net"] = p.get("net")
        objs.append(p)
    return _rows(objs, lambda o, i: o.get("_ident") or i,
                 lambda o: o.get("_net") or "?")


def corpus_sec():
    d = json.loads((T / "sec.json").read_text())
    return _rows(d["data"], lambda o, i: o.get("cik", i),
                 lambda o: (o.get("entityName") or "?")[:1].upper())


def corpus_gaia():
    d = json.loads((T / "gaia.json").read_text())
    names = [c["name"] for c in d["metadata"]]
    objs = [dict(zip(names, row)) for row in d["data"]]
    return _rows(objs, lambda o, i: o.get("source_id", i),
                 lambda o: str(o.get("phot_variable_flag") or "?"))


def corpus_toi():
    d = json.loads((T / "toi.json").read_text())
    return _rows(d, lambda o, i: o.get("toi", i),
                 lambda o: str(o.get("tfopwg_disp") or "?"))


def corpus_ps():
    d = json.loads((T / "ps.json").read_text())
    return _rows(d, lambda o, i: o.get("pl_name", i),
                 lambda o: str(o.get("discoverymethod") or "?"))


CORPORA = {"quakes": corpus_quakes, "sec": corpus_sec, "gaia": corpus_gaia,
           "toi": corpus_toi, "ps": corpus_ps}

SHAPES = ("discrete", "pileup", "modal", "benford", "rounding", "order",
          "regime", "duplicate", "entity", "impossible", "conditional",
          "redundant", "hidden")


def main() -> int:
    prints = {}
    for name, load in CORPORA.items():
        try:
            rows = load()
        except Exception as exc:                              # noqa: BLE001
            print(f"\n[{name}] load failed: {type(exc).__name__}: {exc}", flush=True)
            continue
        if len(rows) < 200:
            print(f"\n[{name}] only {len(rows)} rows — skipped", flush=True)
            continue
        cols = weird._fields(rows)
        t0 = time.time()
        print(f"\n{'='*74}\n{name}: {len(rows):,} rows · {len(cols)} numeric columns",
              flush=True)
        reps = weird.run_all(rows, {})
        kept, notes = weird.explain_away(reps)
        hyp = weird.hypothesise(kept)
        q = [n for n, r in reps.items() if r.saw_control and not r.findings]
        print(f"  {sum(1 for r in reps.values() if r.saw_control)}/{len(reps)} trusted"
              f" · {len(q)} quiet · {time.time()-t0:.0f}s", flush=True)
        print(f"  raw {sum(len(r.findings) for r in reps.values())} "
              f"-> kept {len(kept)} -> {len(hyp)} mechanisms", flush=True)
        for h in hyp[:6]:
            print(f"    [{h.cost:9}] {h.claim[:118]}", flush=True)
        prints[name] = {f: (len({x.subject for x in reps[f].findings}) / max(1, len(cols))
                            if f in reps and reps[f].saw_control else float("nan"))
                        for f in SHAPES}

    if len(prints) >= 2:
        print(f"\n{'='*74}\nFINGERPRINTS — four sciences, one set of families\n")
        print(f"  {'shape':12}" + "".join(f"{c:>10}" for c in prints))
        for f in SHAPES:
            row = f"  {f:12}"
            for c in prints:
                v = prints[c][f]
                row += f"{'  —':>10}" if v != v else f"{v:9.0%} "
            print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
