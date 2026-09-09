#!/usr/bin/env python3
"""Build the OEIS submission package for a C03 extension.

Generates every field an editor will see, straight from the run log — no term is
ever retyped by hand between the computation and the submission, because that is
the one step in this pipeline with no checker on it.

Usage:  python3 scripts/c03_submission.py <extend.log> [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys

A_NUMBER = "A329398"
NAME = ("Number of compositions of n with uniform Lyndon factorization and "
        "uniform co-Lyndon factorization.")
OFFSET = 1
AUTHOR = "Gus Wiseman, Nov 13 2019"

#: The 25 terms the entry carried before this work, pinned so the generator can
#: prove it is EXTENDING the published sequence rather than replacing it.
PUBLISHED = [1, 2, 4, 7, 12, 18, 28, 40, 57, 80, 110, 148, 200, 266, 348, 457,
             592, 764, 978, 1248, 1580, 2000, 2508, 3142, 3913]

ROW = re.compile(
    r"n=\s*(\d+)\s+brute=\s*(\d+)\s+conj=\s*(\d+)\s+oeis=\s*(\S+)\s+(.*?)\s+[\d.]+s")


def parse_log(path: pathlib.Path):
    rows = {}
    for line in path.read_text().splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        n, brute, conj, oeis, verdict = m.groups()
        rows[int(n)] = {
            "brute": int(brute), "conj": int(conj),
            "oeis": None if oeis == "None" else int(oeis),
            "verdict": verdict.strip(),
        }
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=None)
    ns = ap.parse_args()

    rows = parse_log(ns.log)
    if not rows:
        print("no parseable rows in the log", file=sys.stderr)
        return 2

    # ── refuse rather than submit, on any of four grounds ────────────────────
    problems = []
    lo, hi = min(rows), max(rows)
    missing = [n for n in range(lo, hi + 1) if n not in rows]
    if missing:
        problems.append(f"log has gaps at n={missing} — a DATA line cannot skip terms")
    for n, r in sorted(rows.items()):
        if r["brute"] != r["conj"]:
            problems.append(f"n={n}: the two methods DISAGREE "
                            f"({r['brute']} vs {r['conj']}) — nothing is submittable")
        if r["oeis"] is not None and r["oeis"] != r["brute"]:
            problems.append(f"n={n}: our value {r['brute']} contradicts the "
                            f"published {r['oeis']}")
    # Every published term must have been reproduced, or this is not an extension.
    for i, want in enumerate(PUBLISHED, start=OFFSET):
        got = rows.get(i, {}).get("brute")
        if got is None:
            problems.append(f"n={i} of the published 25 was never recomputed")
        elif got != want:
            problems.append(f"n={i}: recomputed {got} but the entry publishes {want}")
    if problems:
        print("REFUSING to build a submission:", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 1

    terms = [rows[n]["brute"] for n in range(OFFSET, hi + 1)]
    new_n = [n for n in sorted(rows) if rows[n]["oeis"] is None]
    data_line = ", ".join(str(t) for t in terms)
    digest = hashlib.sha256(data_line.encode()).hexdigest()[:16]

    first_new, last_new = min(new_n), max(new_n)
    out = []
    out.append(f"# OEIS submission package — {A_NUMBER}")
    out.append("")
    out.append(f"**{NAME}**")
    out.append("")
    out.append(f"Offset {OFFSET}. Entry by {AUTHOR}. Generated from `{ns.log.name}`; "
               f"DATA digest `{digest}`.")
    out.append("")
    out.append(f"- Published terms reproduced: **{len(PUBLISHED)}** "
               f"(n={OFFSET}..{OFFSET + len(PUBLISHED) - 1}), all exact.")
    out.append(f"- New terms: **{len(new_n)}** (n={first_new}..{last_new}).")
    out.append(f"- Every term produced by two independent methods that agree.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 1 · DATA — paste this whole line, replacing what is there")
    out.append("")
    out.append("OEIS wants the FULL sequence, not only the new terms.")
    out.append("")
    out.append("```")
    out.append(data_line)
    out.append("```")
    out.append("")
    out.append("## 2 · Extensions field")
    out.append("")
    out.append("```")
    out.append(f"a({first_new})-a({last_new}) from <YOUR NAME>, "
               f"<Mon DD YYYY>")
    out.append("```")
    out.append("")
    out.append("## 3 · New comment — the conjecture check")
    out.append("")
    out.append("This is the part an editor is most likely to care about, and it is")
    out.append("stated as a VERIFICATION, never as a proof.")
    out.append("")
    out.append("```")
    out.append(f"Gus Wiseman's conjecture a(n) = 2*A000041(n) - A000005(n) holds for "
               f"all n <= {last_new}: each term above was computed independently by "
               f"brute-force enumeration of the compositions of n and by that formula, "
               f"and the two agree throughout. This is a verification, not a proof.")
    out.append("```")
    out.append("")
    out.append("## 4 · PROG — the program that produced the terms")
    out.append("")
    out.append("```")
    out.append("(Python)")
    out.append("def duval_lengths(s):")
    out.append("    # standard Lyndon factorization, O(len)")
    out.append("    n, i, out = len(s), 0, []")
    out.append("    while i < n:")
    out.append("        j, k = i + 1, i")
    out.append("        while j < n and s[k] <= s[j]:")
    out.append("            k = i if s[k] < s[j] else k + 1")
    out.append("            j += 1")
    out.append("        step = j - k")
    out.append("        while i <= k:")
    out.append("            out.append(step); i += step")
    out.append("    return out")
    out.append("def uniform(t): return len(set(t)) <= 1")
    out.append("def A329398(n):")
    out.append("    c, stack = 0, [((), n)]")
    out.append("    while stack:")
    out.append("        p, rem = stack.pop()")
    out.append("        if rem == 0:")
    out.append("            if uniform(duval_lengths(p)) and \\")
    out.append("               uniform(duval_lengths(tuple(-x for x in p))): c += 1")
    out.append("            continue")
    out.append("        for q in range(1, rem + 1): stack.append((p + (q,), rem - q))")
    out.append("    return c")
    out.append(f"print([A329398(n) for n in range(1, {last_new + 1})])")
    out.append("```")
    out.append("")
    out.append("A note for the PROG comment, if you want one: the longest Lyndon prefix")
    out.append("of a word is the first factor of its standard Lyndon factorization, so")
    out.append("iterating Duval's algorithm gives the same factorization the entry's")
    out.append("Mathematica computes by testing every prefix — and does it in O(len)")
    out.append("rather than O(len^3).")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 5 · Evidence behind the terms")
    out.append("")
    out.append("Three independent lines, all reproducible from this repo:")
    out.append("")
    out.append(f"1. **Reproduction.** The Duval implementation returns all "
               f"{len(PUBLISHED)} published terms exactly. A generator that could not "
               f"reproduce the entry would not be allowed to extend it.")
    out.append("2. **A second algorithm.** A literal transcription of the entry's own "
               "Mathematica (test every prefix, take the longest Lyndon one) agrees "
               "with the Duval implementation on every n it reaches.")
    out.append("3. **A second characterisation.** Wiseman's conjectured closed form "
               "agrees on every term, published and new. It shares no machinery with "
               "the enumeration.")
    out.append("")
    out.append("## 6 · What is NOT claimed")
    out.append("")
    out.append("- The conjecture is **not proved**; it is verified over a finite range.")
    out.append("- Computing a term is not the same act as OEIS accepting one. These "
                "terms are submitted for editorial review and may be rejected.")
    out.append("- No claim of priority: the terms are absent from the OEIS entry, "
               "which is not the same as absent from the world.")
    out.append("")
    out.append("## 7 · The submission itself (a human does this)")
    out.append("")
    out.append("1. Register / log in at https://oeis.org (upper right).")
    out.append(f"2. Go to https://oeis.org/{A_NUMBER} and click **edit**.")
    out.append("3. Replace the DATA section with the line in §1.")
    out.append("4. Add the comment in §3, the Extensions line in §2 (with your name "
               "and today's date), and the PROG in §4.")
    out.append("5. **Save changes**, then **\"These changes are ready for review by an "
               "OEIS editor\"**.")
    out.append("")
    out.append("No b-file: b-files are for 100/1000/10000/20000-term runs, and this "
               "sequence is far shorter than that. The DATA line is the right home.")

    text = "\n".join(out) + "\n"
    if ns.out:
        ns.out.mkdir(parents=True, exist_ok=True)
        path = ns.out / f"{A_NUMBER}-submission.md"
        path.write_text(text)
        print(f"wrote {path}")
        print(f"  {len(PUBLISHED)} reproduced · {len(new_n)} new "
              f"(n={first_new}..{last_new}) · digest {digest}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
