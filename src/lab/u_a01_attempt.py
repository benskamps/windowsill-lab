"""U-A01 RE-ANALYSIS — re-price every detection this survey ever made, against a measured null.

**This is not an attempt on U-A01 and was wrongly labelled one on 2026-08-25.**
It consumes only committed bytes: `survey_rows` reads `reports/hunts/`, and not a
single new observation is acquired. U-A01 asks whether the SECTOR contains an
uncatalogued transit; this answers whether the RECORD does — a question the
empty shelf had already answered, to which this adds error bars. Narrowing a
question until it fits a runner you can finish in minutes, then grading against
a kill condition you also wrote, is not crossing a gate.

What it legitimately produces is a MEASURED empty rather than an absent one,
which is worth having. It returns `REANALYSED` and cannot close a discovery
goal.

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
import math
from pathlib import Path

import numpy as np

from .a04 import SDE_THRESHOLD
from .hypothesis import (DISCOVER, Finding, Hypothesis, REANALYSED,
                         UNRESOLVED)

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


#: One-sided confidence of the upper bound every crossing is graded on.
FAP_BOUND_CONFIDENCE = 0.95


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b) — Lentz continued fraction
    (Numerical Recipes 6.4). Stdlib only; converges in tens of iterations
    for the binomial tails this module prices."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _betainc(b, a, 1.0 - x)
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((a + m2 - 1.0) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / (c if abs(c) > tiny else tiny)
        h *= d * c
        aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1.0))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / (c if abs(c) > tiny else tiny)
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return front * h / a


def _binom_upper(k: int, n: int, conf: float = FAP_BOUND_CONFIDENCE) -> float:
    """Clopper–Pearson upper bound on a rate from ``k`` of ``n`` exceedances.

    The smallest ``p`` at which observing ``<= k`` successes has probability
    ``1 - conf``. For ``k == 0`` this is ``1 - (1-conf)**(1/n)`` — the rule
    of three, exactly. ``P[X <= k] = I_{1-p}(n-k, k+1)``; bisection on it.
    """
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    alpha = 1.0 - conf
    if k == 0:
        return 1.0 - alpha ** (1.0 / n)

    def cdf(p: float) -> float:
        return _betainc(n - k, k + 1, 1.0 - p)

    lo, hi = k / n, 1.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def empirical_fap(null: np.ndarray, sde: float) -> dict:
    """The measured null's tail at ``sde``, graded on its conservative bound.

    ``fap`` — the value every promotion decision uses — is the one-sided
    Clopper–Pearson upper bound on the tail rate at ``FAP_BOUND_CONFIDENCE``,
    and it is MONOTONE NON-INCREASING in ``sde``: a stronger crossing can
    never be priced worse than a weaker one. ``fap_point`` is the plain
    ``k/n`` (0 when the tail is empty), kept for the record.

    Audit item 2 (2026-09-11): the first estimator returned ``3/n`` for an
    empty tail and ``k/n`` otherwise, so a crossing with ONE exceedance
    (``1/n``) was priced three times better than one with NONE (``3/n``).
    SDE 8.60 was promotable while SDE 50 was refused; the survey's
    "strongest uncatalogued crossing" was chosen by that ordering, and it
    named SDE 8.048 while SDE 10.14 sat in the same receipts. The rule of
    three was right as a bound; using it beside a point estimate was the
    error. Every tail is now graded on the same bound.
    """
    n = null.size
    k = int((null >= sde).sum())
    return {"fap": _binom_upper(k, n), "fap_point": (k / n if n else 0.0),
            "exceedances": k, "is_bound": True,
            "bound_confidence": FAP_BOUND_CONFIDENCE}


def survey_rows(hunt_dir: str = "reports/hunts") -> list[dict]:
    """Every searched row of every ACCEPTED receipt — the ledger's own set.

    Until 2026-09-11 this globbed the directory, so rows from receipts the
    publish gate refuses (a failed uniformity control, a busted budget
    share) were priced here as if they were survey. One producer decides
    what a receipt is; this reader asks it rather than re-deciding.
    """
    from .publish import _accepted_hunt_receipts   # noqa: PLC0415 — publish imports nothing from here
    accepted, _refused, _superseded = _accepted_hunt_receipts(Path(hunt_dir))
    rows = []
    for _date, _path, d in accepted:
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
    threshold = float(SDE_THRESHOLD)
    crossings = [r for r in rows if r["sde"] >= threshold]
    known = [r for r in crossings if r.get("known_planet")]
    unknown = [r for r in crossings if not r.get("known_planet")]

    priced = []
    for r in unknown:
        f = empirical_fap(null, r["sde"])
        priced.append({**r, **f, "expected_background": f["fap"] * trials})
    # The bound is monotone in SDE, so this order is the SDE order; ties
    # (equal exceedance counts) break toward the stronger crossing.
    priced.sort(key=lambda r: (r["expected_background"], -r["sde"]))
    promotable = [r for r in priced
                  if r["expected_background"] < PROMOTE_MAX_BACKGROUND]

    evidence = {
        "null_draws": int(null.size), "null_max": float(null.max()),
        "threshold": threshold,
        "null_exceedances_at_threshold": int((null >= threshold).sum()),
        "fap_bound_confidence": FAP_BOUND_CONFIDENCE,
        "rows": len(rows), "distinct_targets": trials,
        "crossings_at_threshold": len(crossings),
        "crossings_known_planet": len(known),
        "crossings_uncatalogued": len(unknown),
        "best_uncatalogued": priced[0] if priced else None,
        "promotable": promotable,
    }
    if promotable:
        best = promotable[0]
        return Finding(hypothesis=HYPOTHESIS, verdict=REANALYSED,
                       detail=(f"{len(promotable)} uncatalogued crossing(s) "
                               f"survive the measured null; the strongest is "
                               f"TIC {best.get('tic')} at SDE {best['sde']:.2f}, "
                               f"expected background {best['expected_background']:.3f} "
                               f"across {trials:,} distinct targets"),
                       evidence=evidence)
    return Finding(
        hypothesis=HYPOTHESIS, verdict=REANALYSED,
        detail=(f"no uncatalogued crossing survives. {len(rows):,} searched "
                f"rows over {trials:,} distinct targets produced "
                f"{len(crossings)} crossings at SDE >= {threshold:g}, of which {len(known)} "
                f"are catalogued planets and {len(unknown)} are not; none of "
                f"the latter reaches an expected background below "
                f"{PROMOTE_MAX_BACKGROUND}. The claim that this survey already "
                f"holds an undiscovered transit is killed on its predeclared "
                f"terms, and the shelf's empty is now a measured empty"),
        evidence=evidence)
