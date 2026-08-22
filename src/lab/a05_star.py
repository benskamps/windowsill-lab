"""a05_star — grade the star, not the sector (shelf-exit contract §3).

The hunt grades one sector at a time and never looks at a star twice. That is
how TIC 287328866 stayed shelved: six of its eight sectors read the doubled-
fold difference below 5σ in isolation while the combination reads 9.8σ
(2026-08-19 shelf sweep). This module is the general form of what that sweep
did by hand: assemble every committed observation of one TIC and grade the
star's evidence as one body.

Three design rules, all inherited rather than chosen here:

* **The combination is `combine_p2_folds` and nothing else.** It is the
  VET-F2-corrected statistic — inverse-variance over the PHASE-ANCHORED
  ``signed_difference``, never the folded magnitude whose |noise| bias grew
  a 5.89σ refutation of a real planet out of nothing at k=40. This module
  wraps it; it does not reimplement or extend it.
* **A sector is the unit of independence, not a receipt.** The same sector
  re-hunted lands the same photons in a new receipt (TIC 234518605's lead
  sits in two s2 receipts today), and feeding both to the combiner counts
  the light twice and inflates σ by √(#receipts). Identical same-sector
  folds are deduplicated to one representative with the extras NAMED as
  superseded; same-sector folds that DISAGREE refuse the whole sector
  loudly — a disagreement between two looks at the same photons means the
  pipeline changed under them, and picking one silently would bury that.
* **An ungraded sector is a statement, not an omission.** Receipts from
  before the 2026-08-19 fold gate carry no per-sector fold evidence; a
  pre-VET-F2 fold dict carries no signed quantity; a current-format fold
  that declined to grade says why; a fold the combiner's own filter would
  exclude (both eclipses not individually significant, degenerate σ) is
  named rather than silently dropped. The 2026-08-19 sweep's numbers are
  NOT reproducible from the committed receipts — one pre-fold-gate sector
  per shelf star — and the honest output there is ``insufficient-sectors``
  plus the named gaps, never a manufactured combination.

Observations arrive in the shape :func:`lab.shelf.collect` produces, so the
register can hand its groups straight in.
"""
from __future__ import annotations

import math

from .a05_fold import combine_p2_folds

LEAD = "lead-awaiting-human-review"

#: Two same-sector measurements of the same photons should be bit-identical;
#: this is a float-noise allowance, NOT a physics tolerance. Anything past it
#: means the pipeline changed between receipts, and the sector is refused
#: rather than silently represented by either number.
SAME_SECTOR_RTOL = 1e-9


def _fold_evidence(row: dict):
    """The p2_fold gate summary a post-2026-08-19 receipt row carries."""
    ev = row.get("disposition_evidence") or {}
    fold = ev.get("fold") or {}
    return fold.get("p2_fold")


def _uncombinable_reason(p2: dict) -> str | None:
    """Why `combine_p2_folds` would exclude this fold — the combiner's own
    filter, mirrored so the exclusion can be NAMED per sector. Guarded
    against drift: `star_dossier` asserts the combiner accepted exactly the
    folds this predicate passed."""
    if p2.get("reason"):
        return f"fold gate declined to grade (reason: {p2['reason']})"
    if p2.get("signed_difference") is None:
        return ("unsigned fold evidence (pre-VET-F2) — the folded magnitude "
                "must not be combined")
    if p2.get("difference_sigma") is None:
        return "fold evidence carries no difference_sigma"
    if not p2.get("both_eclipses_significant"):
        return ("fold evidence not combinable: both eclipses are not "
                "individually significant")
    if not (p2.get("eclipse_a") or {}).get("sigma"):
        return "fold evidence not combinable: no per-eclipse sigma"
    return None


def _same_fold(a: dict, b: dict) -> bool:
    return math.isclose(float(a["signed_difference"]),
                        float(b["signed_difference"]),
                        rel_tol=SAME_SECTOR_RTOL, abs_tol=1e-15)


def star_dossier(tic: int, observations: list[dict]) -> dict:
    """One star, every committed look at it, graded as one body.

    Returns::

        {"tic", "sectors",            # every sector observed, any disposition
         "graded_sectors",            # unique sectors whose fold evidence fed
                                      #   the combiner (== combined_sectors)
         "combined_sectors",          # the combiner's contributing set — the
                                      #   ONLY basis for any fired-gate claim
         "superseded",                # [{sector, receipt, reason}] same-sector
                                      #   duplicates represented by the newest
         "ungraded",                  # [{sector, receipt, reason}] named gaps
         "sector_verdicts",           # {sector: disposition} for non-lead rows
         "combined_fold"}             # combine_p2_folds output, verbatim

    ``combined_fold`` is the reviewed combiner's dict unchanged — including
    its own refusals (``insufficient-sectors``, ``degenerate-sigma``), so a
    downstream reader sees the statistic's voice, not a paraphrase.
    """
    ungraded, superseded = [], []
    verdicts: dict = {}
    by_sector: dict = {}   # sector -> list of (day, receipt, p2)
    for o in sorted(observations, key=lambda o: (str(o["sector"]), o["day"],
                                                 o["receipt"])):
        row = o["row"]
        if o["disposition"] != LEAD:
            verdicts[o["sector"]] = o["disposition"]
            continue
        p2 = _fold_evidence(row)
        if p2 is None:
            ungraded.append({
                "sector": o["sector"], "receipt": o["receipt"],
                "reason": "no fold evidence — receipt predates the "
                          "2026-08-19 fold gate"})
            continue
        reason = _uncombinable_reason(p2)
        if reason is not None:
            ungraded.append({"sector": o["sector"], "receipt": o["receipt"],
                             "reason": reason})
            continue
        by_sector.setdefault(o["sector"], []).append(
            (o["day"], o["receipt"], p2))

    # One fold per unique SECTOR — a receipt is not a unit of independence.
    usable, graded = [], []
    for sector, folds in by_sector.items():
        newest_day, newest_receipt, representative = folds[-1]
        disagreeing = [r for _, r, p in folds[:-1]
                       if not _same_fold(p, representative)]
        if disagreeing:
            for _, receipt, _p in folds:
                ungraded.append({
                    "sector": sector, "receipt": receipt,
                    "reason": ("same-sector fold evidence disagrees across "
                               "receipts — the pipeline changed between "
                               "looks at the same photons; refusing to pick "
                               "a representative")})
            continue
        for _, receipt, _p in folds[:-1]:
            superseded.append({
                "sector": sector, "receipt": receipt,
                "reason": (f"same-sector duplicate — represented by the "
                           f"newest receipt ({newest_receipt}); the same "
                           "photons must not be counted twice")})
        usable.append(representative)
        graded.append(sector)

    combined = combine_p2_folds(usable)
    # Drift guard: the combiner must have accepted exactly what the mirrored
    # predicate passed — if its filter changes shape, fail loudly here rather
    # than let a sector vanish from a claim silently.
    if combined["n_sectors"] != len(usable):
        raise RuntimeError(
            f"combine_p2_folds accepted {combined['n_sectors']} of "
            f"{len(usable)} pre-validated folds for TIC {tic} — "
            "_uncombinable_reason has drifted from the combiner's filter")

    return {
        "tic": tic,
        "sectors": sorted({o["sector"] for o in observations},
                          key=lambda s: (str(s))),
        "graded_sectors": graded,
        "combined_sectors": graded,
        "superseded": superseded,
        "ungraded": ungraded,
        "sector_verdicts": verdicts,
        "combined_fold": combined,
    }
