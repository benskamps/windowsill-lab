#!/usr/bin/env python3
"""Re-derive the CTOI package's transit table from the DV XML and diff it.

Four numbers in `docs/submissions/TIC374861595-CTOI.md` have now been wrong at
different times -- the upload line's ephemeris, the stellar density's units, the
odd/even statistic, and the baseline-and-sector-count pair. Every one was typed
rather than derived, and every one was caught by a human reading carefully
rather than by anything that would fail.

So this file fails. It reads the numbers out of the committed DV XML, reads the
numbers out of the markdown, and exits nonzero when they disagree. It is
deliberately dumb: no fitting, no physics, just "does the document say what the
source says".

    python3 scripts/ctoi_table_check.py
    python3 scripts/ctoi_table_check.py --selftest   # prove it can fail

Exit 0 agree, 1 disagree, 2 a file is missing.
"""
from __future__ import annotations

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent.parent
XML = HERE / "docs/submissions/TIC374861595-spoc-s1-s96-dvr.xml"
DOC = HERE / "docs/submissions/TIC374861595-CTOI.md"

#: Cadence length of the 2-minute target pixel data the DV run consumed.
CADENCE_MINUTES = 2.0


def dv_facts() -> dict:
    root = ET.parse(XML).getroot()
    strip = lambda e: e.tag.split("}")[-1]                      # noqa: E731
    p1 = [c for c in root if strip(c) == "planetResults"][0]
    fit = [c for c in p1 if strip(c) == "allTransitsFit"][0]
    par = {m.attrib["name"]: (float(m.attrib["value"]),
                              float(m.attrib["uncertainty"]))
           for m in fit.iter() if strip(m) == "modelParameter"}
    cand = [c for c in p1.iter() if strip(c) == "planetCandidate"][0]

    bitmap = root.attrib["sectorsObserved"]
    sectors = [i for i, ch in enumerate(bitmap) if ch == "1"]
    cadences = int(root.attrib["endCadence"]) - int(root.attrib["startCadence"])
    baseline_d = cadences * CADENCE_MINUTES / 60.0 / 24.0

    return {
        "period": par["orbitalPeriodDays"][0],
        "depth_ppm": par["transitDepthPpm"][0],
        "duration_h": par["transitDurationHours"][0],
        "b": par["minImpactParameter"][0],
        "a_over_rs": par["ratioSemiMajorAxisToStarRadius"][0],
        "observed_transits": int(cand.attrib["observedTransitCount"]),
        "expected_transits": int(cand.attrib["expectedTransitCount"]),
        "sectors": sectors,
        "baseline_d": baseline_d,
    }


#: Values this package has already retracted. Each one may appear in the §0
#: correction record -- that is what the record is for -- and nowhere else. The
#: existence checks below only ask whether the *right* number is stated
#: somewhere; this asks whether a *wrong* one survived somewhere, which is the
#: defect that actually happened (the baseline was wrong in three places while a
#: correct copy sat in the same file).
RETRACTED = [
    ("baseline", "2,300"),
    ("sector count", "25+ sectors"),
    ("odd/even", "1.13"),
    ("sector ranges", "35–39"),
    ("sector ranges", "61–69"),
    ("sector ranges", "87–97"),
    ("density label", "2.57 g/cm"),
]

#: The §0 correction record quotes the retracted values on purpose. Everything
#: from §0.1 on is live text a reader takes at face value.
LIVE_FROM = "## 0.1"


def live_text(doc: str) -> str:
    """The part of the document that is asserting, not recording a retraction."""
    i = doc.find(LIVE_FROM)
    return doc if i < 0 else doc[i:]


def compare(dv: dict, doc: str) -> list[str]:
    """Return one string per disagreement between the DV facts and the doc."""
    bad: list[str] = []
    live = live_text(doc)

    def want(label: str, pattern: str, note: str = "") -> None:
        if not re.search(pattern, doc):
            bad.append(f"{label}: the document does not state {note or pattern}")

    # The transit row, as the package prints it.
    want("period", r"1\.9369484", "SPOC's period 1.9369484")
    want("depth", r"104603", "SPOC's depth 104603 ppm")
    want("duration", r"2\.1533", "SPOC's duration 2.1533 h")
    want("impact parameter", r"0\.9000", "b = 0.9000")
    want("a/R*", r"7\.71473", "a/R* = 7.71473")
    want("observed transits", rf"\*\*{dv['observed_transits']}\*\*",
         f"{dv['observed_transits']} observed transits")

    # The two that were wrong, stated as the XML implies them.
    n_sectors = len(dv["sectors"])
    if not re.search(rf"\*\*{n_sectors} sectors\*\*", doc):
        bad.append(f"sector count: XML bitmap has {n_sectors} bits set "
                   f"(first S{dv['sectors'][0]}); the document does not say "
                   f"'**{n_sectors} sectors**'")
    baseline = round(dv["baseline_d"])
    if not re.search(rf"{baseline:,}".replace(",", "[,]?") + r"\s*d", doc):
        bad.append(f"baseline: XML spans {dv['baseline_d']:,.1f} d; the "
                   f"document does not state ~{baseline:,} d")

    # No retracted value may survive outside the correction record.
    for label, text in RETRACTED:
        if text in live:
            bad.append(f"{label}: the retracted value '{text}' appears in live "
                       f"text (it belongs only in the §0 correction record)")

    # The arithmetic that makes the baseline self-checking, rather than a
    # number the reader has to take on faith.
    cycles = dv["baseline_d"] / dv["period"]
    drift = abs(cycles - dv["expected_transits"]) / dv["expected_transits"]
    if drift > 0.01:
        bad.append(f"baseline vs expectedTransitCount: {cycles:,.1f} cycles "
                   f"against {dv['expected_transits']} expected "
                   f"({100 * drift:.1f} % apart) — one of them is wrong")

    # Sector numbers the document must not invent. Any S<n> it names in the
    # coverage list has to be a bit that is actually set.
    # Bound the match to the bold run the list lives in (it closes at "96**"),
    # not to a character window -- a window overruns into the surrounding prose
    # and reads unrelated digits as sector numbers.
    listed = re.search(r"read off the DV bitmap:(.*?)\*\*", doc, re.S)
    if listed:
        named = {int(x) for x in re.findall(r"\b(\d{1,2})\b", listed.group(1))}
        invented = sorted(named - set(dv["sectors"]))
        if invented:
            bad.append(f"coverage list names sectors not in the bitmap: {invented}")

    return bad


#: Each edit rewrites one true number in the document into a wrong one, in
#: *every* place it appears -- a mutation of only the first copy is satisfied by
#: a correct copy further down, which is the bug it is meant to model.
MUTATIONS = [
    ("baseline", "1,897 d", "1,900 d"),
    ("sector count", "**23 sectors**", "**25 sectors**"),
    ("transit count", "**259**", "**261**"),
    ("period", "1.9369484", "1.9369999"),
    ("depth", "104603", "104999"),
    ("coverage list", "27, 28, 30", "27, 28, 39"),
    # And the defect the existence checks are blind to: a retracted value
    # left standing in live text while a correct copy sits elsewhere.
    ("stale baseline in live text", "## 0.1", "## 0.1 over ~2,300 d\n"),
    ("stale sector count in live text", "## 0.1", "## 0.1 over 25+ sectors\n"),
]


def selftest(dv: dict, doc: str) -> int:
    """Prove the checker fails on a wrong document, not just passes on a right one."""
    ok = not compare(dv, doc)
    print(f"  {'PASS' if ok else 'FAIL'}  unmutated document is accepted")
    failures = 0 if ok else 1
    for label, was, now in MUTATIONS:
        if was not in doc:
            print(f"  FAIL  {label}: '{was}' is not in the document to mutate")
            failures += 1
            continue
        caught = bool(compare(dv, doc.replace(was, now)))
        print(f"  {'PASS' if caught else 'FAIL'}  {label}: "
              f"'{was}' -> '{now}' is {'rejected' if caught else 'ACCEPTED'}")
        failures += not caught
    print(f"\nselftest: {len(MUTATIONS) + 1 - failures}/{len(MUTATIONS) + 1}")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    for f in (XML, DOC):
        if not f.exists():
            print(f"MISSING: {f}", file=sys.stderr)
            return 2

    dv = dv_facts()
    doc = DOC.read_text()
    n_sectors = len(dv["sectors"])
    cycles = dv["baseline_d"] / dv["period"]

    print(f"DV XML : {dv['observed_transits']} transits, "
          f"{dv['expected_transits']} expected, {n_sectors} sectors "
          f"(S{dv['sectors'][0]}–S{dv['sectors'][-1]}), "
          f"{dv['baseline_d']:,.1f} d = {cycles:,.1f} cycles")

    if "--selftest" in argv:
        print("\nselftest — each row corrupts one number and must be caught:")
        return selftest(dv, doc)

    bad = compare(dv, doc)
    if bad:
        print(f"\nDISAGREES — {len(bad)} item(s):")
        for b in bad:
            print(f"  - {b}")
        return 1
    print("\nThe package's transit table agrees with the DV XML.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
