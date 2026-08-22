"""a05_star — grade the star, not the sector (shelf-exit contract §3).

The hunt grades one sector at a time and never looks at a star twice. That is
how TIC 287328866 stayed shelved: six of its eight sectors read the doubled-
fold difference below 5σ in isolation while the combination reads 9.8σ
(2026-08-19 shelf sweep). This module is the general form of what that sweep
did by hand: assemble every committed observation of one TIC and grade the
star's evidence as one body.

Two design rules, both inherited rather than chosen here:

* **The combination is `combine_p2_folds` and nothing else.** It is the
  VET-F2-corrected statistic — inverse-variance over the PHASE-ANCHORED
  ``signed_difference``, never the folded magnitude whose |noise| bias grew
  a 5.89σ refutation of a real planet out of nothing at k=40. This module
  wraps it; it does not reimplement or extend it. A star-level statistic
  this module cannot express with the reviewed combiner is an open question
  for the contract, not a formula to invent here.
* **An ungraded sector is a statement, not an omission.** Receipts from
  before the 2026-08-19 fold gate carry no per-sector fold evidence, and a
  pre-VET-F2 fold dict carries no signed quantity; both are NAMED in the
  dossier with their reason. The 2026-08-19 sweep's numbers (28.3σ on
  TIC 234518605 over 6 sectors) are NOT reproducible from the committed
  receipts — they hold one pre-fold-gate sector per shelf star — and the
  honest output for those stars is ``insufficient-sectors`` plus the named
  gaps, never a manufactured combination.

Observations arrive in the shape :func:`lab.shelf.collect` produces, so the
register can hand its groups straight in.
"""
from __future__ import annotations

from .a05_fold import combine_p2_folds

LEAD = "lead-awaiting-human-review"


def _fold_evidence(row: dict):
    """The p2_fold gate summary a post-2026-08-19 receipt row carries."""
    ev = row.get("disposition_evidence") or {}
    fold = ev.get("fold") or {}
    return fold.get("p2_fold")


def star_dossier(tic: int, observations: list[dict]) -> dict:
    """One star, every committed look at it, graded as one body.

    Returns::

        {"tic", "sectors",            # every sector observed, any disposition
         "graded_sectors",            # sectors whose fold evidence combined
         "ungraded",                  # [{sector, receipt, reason}] — named gaps
         "sector_verdicts",           # {sector: disposition} for non-lead rows
         "combined_fold"}             # combine_p2_folds output, verbatim

    ``combined_fold`` is the reviewed combiner's dict unchanged — including
    its own refusals (``insufficient-sectors``, ``degenerate-sigma``), so a
    downstream reader sees the statistic's voice, not a paraphrase.
    """
    usable, graded, ungraded = [], [], []
    verdicts: dict = {}
    for o in sorted(observations, key=lambda o: (str(o["sector"]), o["day"])):
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
        if p2.get("signed_difference") is None:
            ungraded.append({
                "sector": o["sector"], "receipt": o["receipt"],
                "reason": "unsigned fold evidence (pre-VET-F2) — the folded "
                          "magnitude must not be combined"})
            continue
        usable.append(p2)
        graded.append(o["sector"])

    return {
        "tic": tic,
        "sectors": sorted({o["sector"] for o in observations},
                          key=lambda s: (str(s))),
        "graded_sectors": graded,
        "ungraded": ungraded,
        "sector_verdicts": verdicts,
        "combined_fold": combine_p2_folds(usable),
    }
