#!/usr/bin/env python3
"""Point `weird` at everything this box owns, then compare the corpora.

Five corpora that share no schema, no domain and no producer:

  survey    13,621 graded transit searches      astronomy pipeline
  physics      242 Ising/Kuramoto/spin-glass    numerical physics
  git        commits across every repo          human + machine authorship
  ember      58,713 chunks of a RAG store       text, read-only, sacred
  samehand   12,598 length-matched messages     authorship statistics

The families are unchanged. That is the claim being tested: a tool that learns
each corpus's own normal needs to know nothing about any of them.

Then the part no single-corpus run can do — a FINGERPRINT per corpus (what
share of its columns are constant, censored, multimodal, digit-law-violating)
and a comparison across them. A shape that is ordinary in one corpus and rare
in another is a fact about the producer, not about the column.

Ember's brain is opened `mode=ro` at the driver level. It is not modified, and
it is not modifiable through this handle.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from lab import weird  # noqa: E402

HOME = pathlib.Path.home()
REPO = pathlib.Path(__file__).resolve().parent.parent


# ── adapters: each returns [{_id, _src, <numeric fields>}] ──────────────────

def corpus_survey() -> list[dict]:
    return weird.load_rows((REPO / "reports" / "hunts").glob("hunt-*.json"),
                           "targets")


def corpus_physics() -> list[dict]:
    rows = []
    for f in sorted((REPO / "reports" / "receipts").glob("run-*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:                                    # noqa: BLE001
            continue
        r = weird.flatten(d)
        r["_id"], r["_src"] = f.stem, f.name
        rows.append(r)
    return rows


def corpus_git(max_repos: int = 40, per_repo: int = 600) -> list[dict]:
    rows = []
    repos = sorted(p for p in (HOME / "projects").iterdir()
                   if (p / ".git").exists())[:max_repos]
    for idx, p in enumerate(repos):
        try:
            out = subprocess.run(
                ["git", "-C", str(p), "log", "--no-merges", "--date=unix",
                 "--pretty=format:%H|%ad|%an|%s", "--numstat",
                 f"-n{per_repo}"],
                capture_output=True, text=True, timeout=60).stdout
        except Exception:                                    # noqa: BLE001
            continue
        cur = None
        for line in out.splitlines():
            if line.count("|") >= 3:
                h, ts, an, subj = line.split("|", 3)
                dt = datetime.datetime.fromtimestamp(int(ts))
                s = subj.lower()
                cur = {"_id": h[:9], "_src": p.name, "repo": float(idx),
                       "hour": float(dt.hour), "weekday": float(dt.weekday()),
                       "subject_len": float(len(subj)),
                       "is_fix": float(bool(re.search(r"\bfix|\bbug|revert", s))),
                       "is_bot": float(an.lower().startswith(("github", "claude"))),
                       "files": 0.0, "insert": 0.0, "delete": 0.0}
                rows.append(cur)
            elif cur is not None and line.count("\t") == 2:
                a, b, _ = line.split("\t")
                cur["files"] += 1
                if a.isdigit():
                    cur["insert"] += float(a)
                if b.isdigit():
                    cur["delete"] += float(b)
    for r in rows:
        r["churn"] = r["insert"] + r["delete"]
        r["del_frac"] = r["delete"] / max(1.0, r["churn"])
    return rows


def corpus_ember() -> list[dict]:
    """Ember's RAG store. READ-ONLY at the driver, not by discipline."""
    db = HOME / ".openclaw/workspace/ember-home/brain/chroma_db/chroma.sqlite3"
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    per: dict[str, dict] = {}
    q = ("select id, key, coalesce(int_value, float_value) v, string_value "
         "from embedding_metadata where key in "
         "('chunk_index','word_count','mtime','category','filename','trust_level')")
    for rid, key, v, sv in con.execute(q):
        r = per.setdefault(str(rid), {"_id": str(rid), "_src": "ember"})
        if key == "category" and sv:
            r["_cat"] = sv
        elif key == "filename" and sv:
            r["_file"] = sv
        elif v is not None:
            r[key] = float(v)
    con.close()
    # categories become a numeric label so the grouping families can use them
    cats = sorted({r["_cat"] for r in per.values() if "_cat" in r})
    code = {c: float(i) for i, c in enumerate(cats)}
    rows = []
    for r in per.values():
        if "_cat" in r:
            r["shelf"] = code[r.pop("_cat")]
        r.pop("_file", None)
        rows.append(r)
    return rows


def corpus_samehand() -> list[dict]:
    p = HOME / "projects/samehand/data/matched_corpus.jsonl"
    if not p.exists():
        return []
    rows = []
    for i, line in enumerate(p.read_text().splitlines()):
        try:
            d = json.loads(line)
        except Exception:                                    # noqa: BLE001
            continue
        r = weird.flatten(d)
        r["_id"], r["_src"] = f"r{i}", str(d.get("repo", "?"))
        rows.append(r)
    return rows


CORPORA = {
    "survey": corpus_survey,
    "physics": corpus_physics,
    "git": corpus_git,
    "ember": corpus_ember,
    "samehand": corpus_samehand,
}


# ── the cross-corpus question ───────────────────────────────────────────────

SHAPES = ("discrete", "pileup", "modal", "benford", "rounding", "order",
          "regime", "duplicate", "entity", "impossible", "conditional")


def fingerprint(reports: dict[str, weird.Report], n_cols: int) -> dict[str, float]:
    """Share of a corpus's columns exhibiting each shape.

    Normalised by column count so corpora of wildly different width compare.
    A shape ordinary in one corpus and absent in another is a property of
    whatever produced them.
    """
    out = {}
    for fam in SHAPES:
        rep = reports.get(fam)
        if rep is None or not rep.saw_control:
            out[fam] = float("nan")
            continue
        subjects = {f.subject for f in rep.findings}
        out[fam] = len(subjects) / max(1, n_cols)
    return out


def compare(prints: dict[str, dict[str, float]]) -> list[str]:
    """Shapes that separate the corpora, loudest first."""
    lines = []
    for fam in SHAPES:
        vals = {c: p[fam] for c, p in prints.items()
                if p.get(fam) == p.get(fam)}          # drop NaN
        if len(vals) < 2:
            continue
        hi = max(vals, key=vals.get)
        lo = min(vals, key=vals.get)
        if vals[hi] - vals[lo] > 0.10:
            lines.append(
                f"{fam:12} {vals[hi]:5.0%} of columns in {hi:9} vs "
                f"{vals[lo]:5.0%} in {lo}")
    return lines


def main() -> int:
    prints, sizes = {}, {}
    for name, load in CORPORA.items():
        t0 = time.time()
        try:
            rows = load()
        except Exception as exc:                             # noqa: BLE001
            print(f"\n[{name}] could not load: {type(exc).__name__}: {exc}",
                  flush=True)
            continue
        if len(rows) < 100:
            print(f"\n[{name}] only {len(rows)} rows — skipped", flush=True)
            continue
        cols = weird._fields(rows)
        sizes[name] = (len(rows), len(cols))
        print(f"\n{'='*72}\n{name}: {len(rows):,} rows · {len(cols)} numeric columns "
              f"({time.time()-t0:.0f}s to load)", flush=True)
        reps = weird.run_all(rows, {})
        trusted = sum(1 for r in reps.values() if r.saw_control)
        quiet = [n for n, r in reps.items() if r.saw_control and not r.findings]
        raw = sum(len(r.findings) for r in reps.values())
        kept, notes = weird.explain_away(reps)
        hyp = weird.hypothesise(kept)
        print(f"  {trusted}/{len(reps)} families trusted · {len(quiet)} quiet "
              f"({', '.join(quiet[:5])})", flush=True)
        print(f"  raw {raw} -> kept {len(kept)} -> {len(hyp)} mechanisms", flush=True)
        for h in hyp[:5]:
            print(f"    [{h.cost:9}] {h.claim[:118]}", flush=True)
        prints[name] = fingerprint(reps, len(cols))

    print(f"\n{'='*72}\nCROSS-CORPUS — shapes that separate the producers\n")
    hdr = f"  {'shape':12}" + "".join(f"{c:>11}" for c in prints)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for fam in SHAPES:
        row = f"  {fam:12}"
        for c in prints:
            v = prints[c].get(fam, float("nan"))
            row += f"{'   —' if v != v else f'{v:10.0%}'}" if v != v else f"{v:10.0%} "
        print(row)
    print()
    for line in compare(prints):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
