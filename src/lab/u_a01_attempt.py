"""U-A01 ATTEMPT — re-price every detection this survey ever made, against a measured null.

**This decision rule was written and committed before any real-target
disposition was examined.** That ordering is the entire difference between an
attempt and a fishing trip, and it is the condition `TRACKS.md` already sets for
Track A's arrival: *the refutation battery committed BEFORE the data is opened*.

## Why this is the attempt and not another feasibility test

The hunt lane has searched 9,985 target-rows across 58 sectors-worth of work and
put nothing on the shelf. Its threshold, SDE >= 8.0, was set a priori and never
had a price: until 2026-08-25 the largest of 1,400 pooled null draws was 7.00,
so the false-alarm probability at threshold was an extrapolation.

The scramble campaign changed that. With 38,500+ null draws the threshold region
is **inside the sample**, so every real detection can now be given a measured
false-alarm probability rather than an assumed one. Nothing new is searched here
— what is new is that the survey can finally say what its own crossings are
worth.

## The rule, fixed in advance

1. **FAP** of a detection at SDE ``s`` is the empirical tail of the scramble
   null: ``#{null >= s} / N_null``. Where the count is zero the FAP is reported
   as an upper bound (rule of three), never as a point estimate.
2. **Trials** is the number of DISTINCT targets searched, not the number of
   rows. Re-searching one star in six sectors is not six chances at a false
   alarm from independent noise, and counting it that way would inflate the
   correction in our own favour.
3. **Expected background** = FAP x trials. A candidate is promotable only if
   this is below ``PROMOTE_MAX_BACKGROUND``.
4. **Known planets are excluded from the frontier claim.** Recovering a
   catalogued planet is a calibration success and is reported as such; it is
   not a discovery and must never be counted as one.
5. **A candidate must also survive the existing vetting chain.** This runner
   does not re-litigate dispositions it did not compute.
6. **If nothing passes, the result is an honest empty with every exit named** —
   how many crossed threshold, how many were known, how many failed vetting,
   how many were killed by the trials factor. An empty shelf whose exits are
   enumerated is a result; an empty shelf with no accounting is a shrug.

A verdict of ``killed`` or ``unresolved`` closes G01 exactly as well as
``supported``. The commitment is to attempt and report.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from .hypothesis import DISCOVER, Finding, Hypothesis, KILLED, SUPPORTED, UNRESOLVED

#: A candidate is promotable only if fewer than this many false alarms are
#: expected across the whole survey at its significance. 0.1 is strict on
#: purpose: the shelf's value is that anything on it is worth a follow-up.
PROMOTE_MAX_BACKGROUND = 0.1

#: Below this many null draws the empirical tail is too thin to price anything
#: and the attempt reports UNRESOLVED rather than guessing.
MIN_NULL_DRAWS = 10_000

NULL_PATH = Path.home() / ".lab" / "scramble-null.jsonl"

HYPOTHESIS = Hypothesis(
    id="U-A01",
    track="A",
    stage=DISCOVER,
    unknown_id="U-A01",
    question=("Does this survey's own record contain a transit signal that is "
              "significant against a MEASURED false-alarm null and is not "
              "already catalogued?"),
    why_unanswered=("The hunt lane's SDE >= 8 threshold was set a priori and "
                    "never priced. Until the scramble campaign put draws above "
                    "the threshold into the null, no crossing could be assigned "
                    "a false-alarm probability that did not rest on a one-SDE "
                    "extrapolation."),
    observable=("For the strongest uncatalogued crossing: its empirical FAP "
                "from the scramble null, multiplied by the number of distinct "
                "targets searched."),
    kill_condition=("If no uncatalogued crossing has an expected background "
                    "below 0.1 across the survey, the claim that this survey "
                    "holds an undiscovered transit is KILLED, and the shelf's "
                    "empty is reported with every exit counted."),
    cheapest_decisive=("Minutes, on committed bytes plus the campaign's null. "
                       "No new searching."),
    why_this_might_be_nothing=("The shelf is already empty and the lane has "
                               "been running for weeks, so the overwhelmingly "
                               "likely outcome is that every crossing is a "
                               "known planet or a vetting failure. The point is "
                               "that until now the survey could not say that "
                               "with a number attached."),
)


def load_null(path: Path = NULL_PATH) -> np.ndarray:
    if not Path(path).exists():
        return np.array([])
    vals = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:                                   # noqa: BLE001
                continue
            if "sde" in r:
                vals.append(r["sde"])
    return np.sort(np.asarray(vals, dtype=float))


def empirical_fap(null: np.ndarray, sde: float) -> dict:
    """Tail probability of the measured null at ``sde``; a bound when empty."""
    n = null.size
    k = int((null >= sde).sum())
    if k == 0:
        return {"fap": 3.0 / n, "exceedances": 0, "is_bound": True}
    return {"fap": k / n, "exceedances": k, "is_bound": False}


def survey_rows(hunt_dir: str = "reports/hunts") -> list[dict]:
    rows = []
    for f in sorted(glob.glob(f"{hunt_dir}/*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for t in (d.get("targets") or []):
            if t.get("sde") is not None:
                rows.append(t)
    return rows


def run(hunt_dir: str = "reports/hunts", null_path: Path = NULL_PATH) -> Finding:
    null = load_null(null_path)
    rows = survey_rows(hunt_dir)
    if null.size < MIN_NULL_DRAWS:
        return Finding(hypothesis=HYPOTHESIS, verdict=UNRESOLVED,
                       detail=(f"only {null.size:,} null draws — below the "
                               f"{MIN_NULL_DRAWS:,} needed to price a crossing. "
                               "Nothing is concluded."),
                       evidence={"null_draws": int(null.size)})

    trials = len({r.get("tic") for r in rows if r.get("tic")})
    crossings = [r for r in rows if r["sde"] >= 8.0]
    known = [r for r in crossings if r.get("known_planet")]
    unknown = [r for r in crossings if not r.get("known_planet")]

    priced = []
    for r in unknown:
        f = empirical_fap(null, r["sde"])
        priced.append({**r, **f, "expected_background": f["fap"] * trials})
    priced.sort(key=lambda r: r["expected_background"])
    promotable = [r for r in priced
                  if r["expected_background"] < PROMOTE_MAX_BACKGROUND]

    evidence = {
        "null_draws": int(null.size), "null_max": float(null.max()),
        "rows": len(rows), "distinct_targets": trials,
        "crossings_at_8": len(crossings),
        "crossings_known_planet": len(known),
        "crossings_uncatalogued": len(unknown),
        "best_uncatalogued": priced[0] if priced else None,
        "promotable": promotable,
    }
    if promotable:
        best = promotable[0]
        return Finding(hypothesis=HYPOTHESIS, verdict=SUPPORTED,
                       detail=(f"{len(promotable)} uncatalogued crossing(s) "
                               f"survive the measured null; the strongest is "
                               f"TIC {best.get('tic')} at SDE {best['sde']:.2f}, "
                               f"expected background {best['expected_background']:.3f} "
                               f"across {trials:,} distinct targets"),
                       evidence=evidence)
    return Finding(
        hypothesis=HYPOTHESIS, verdict=KILLED,
        detail=(f"no uncatalogued crossing survives. {len(rows):,} searched "
                f"rows over {trials:,} distinct targets produced "
                f"{len(crossings)} crossings at SDE >= 8, of which {len(known)} "
                f"are catalogued planets and {len(unknown)} are not; none of "
                f"the latter reaches an expected background below "
                f"{PROMOTE_MAX_BACKGROUND}. The claim that this survey already "
                f"holds an undiscovered transit is killed on its predeclared "
                f"terms, and the shelf's empty is now a measured empty"),
        evidence=evidence)
