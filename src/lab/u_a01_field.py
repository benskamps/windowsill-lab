"""U-A01 FIELD ATTEMPT — the terminus, built.

``hypothesis.Finding.new_observations`` carries a docstring that says the
pipeline instrumented every stage from proposal to publication and never
built the final hop: *actually going and looking*. On 2026-09-11 the hunt
lane went and looked — sector 96, preregistered before the first light curve
opened, 149 stars searched, a receipt filed and graded — and ``pot.json``
still read ``a_field_unknown_attempted: false``, because nothing turned a hunt
receipt into the finding ``archive.attempt_ledger`` reads. The looking was
built. The telling was not. This module is the telling.

What it does, and refuses to do:

* It reads ONE committed hunt receipt and nothing else. The receipt must be
  one the publish gate accepts (``_hunt_refusal`` returns ``None``) — a
  receipt whose own controls failed is not a receipt, and this runner will not
  launder one into an attempt by re-labelling it.
* The verdict is the preregistration's outcome table, mechanically: any
  ``lead-awaiting-human-review`` row → UNRESOLVED (a lead is not a planet; a
  human owes an answer); every crossing dispositioned to a refutation or a
  catalogue match → KILLED; a refused receipt → UNRESOLVED **with no
  observations**, which ``attempted_the_question`` correctly reads as "did not
  count", exactly as the prereg says a withheld run does not.
* ``new_observations`` names the bytes: the receipt file, its sector, its
  ``generated_at``, how many targets were searched and how many rows carry a
  SHA-256-pinned product. Empty is impossible here by construction; a
  discovery verdict without it is refused by ``Finding.__post_init__``.
* It never writes UNKNOWNS.md. The goal computes its own progress from the
  receipts; a runner that edited the catalogue would be the substring search
  again with extra steps.
"""
from __future__ import annotations

import json
from pathlib import Path

from .hypothesis import DISCOVER, Finding, Hypothesis, KILLED, UNRESOLVED

LEAD_STATE = "lead-awaiting-human-review"

HYPOTHESIS = Hypothesis(
    id="U-A01",
    track="A",
    stage=DISCOVER,
    unknown_id="U-A01",
    question=("Does a TESS sector this survey has never searched contain a "
              "transiting planet signal that is not already catalogued?"),
    why_unanswered=("Until 2026-09-11 every U-A01 run consumed only committed "
                    "bytes: the re-analysis priced the survey's own record "
                    "against a measured null and was correctly labelled NOT an "
                    "attempt. The question asks about the sky, and the sky had "
                    "not been looked at."),
    observable=("For one preregistered sector sample: every crossing above the "
                "committed SDE threshold, its machine disposition, and whether "
                "any row reaches lead-awaiting-human-review after the sky gates."),
    kill_condition=("If every above-threshold crossing in the sample is "
                    "dispositioned to a refutation or a catalogue match and no "
                    "row is a lead, the claim that this sample holds an "
                    "uncatalogued transit this instrument can see is KILLED at "
                    "this sample and threshold. A lead is UNRESOLVED, never "
                    "supported: promotion to planet is a human act."),
    cheapest_decisive=("One sector, n=500 two-minute targets, about seven "
                       "GPU-hours on this box, under a preregistration committed "
                       "before the first light curve opens."),
    why_this_might_be_nothing=("The community has had months on any recent "
                               "sector and the pipeline's threshold sits below "
                               "the pooled null's maximum, so the overwhelmingly "
                               "likely result is a handful of eclipsing binaries "
                               "and pulsators and a known planet recovered blind "
                               "— a measured empty, not a discovery."),
)


def _crossings(receipt: dict) -> list[dict]:
    threshold = float(receipt.get("sde_threshold", 8.0))
    return [r for r in receipt.get("targets", [])
            if isinstance(r, dict) and r.get("outcome") == "searched"
            and isinstance(r.get("sde"), (int, float)) and r["sde"] >= threshold]


def run(receipt_path: str | Path, preregistration: str | None = None) -> Finding:
    """The finding the goal reads, from one accepted hunt receipt."""
    from .publish import _hunt_refusal   # noqa: PLC0415 — publish imports nothing from here

    path = Path(receipt_path)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("experiment") != "a05-survey-hunt":
        raise ValueError(f"{path.name} is not an A05 survey-hunt receipt")

    refusal = _hunt_refusal(receipt, path)
    if refusal is not None:
        # The prereg's fourth row: controls fail → no verdict, the run is
        # withheld and does not count. No observations, so the ledger agrees.
        return Finding(hypothesis=HYPOTHESIS, verdict=UNRESOLVED,
                       detail=(f"{path.name} is refused by the publish gate "
                               f"({refusal}); the attempt is withheld and does "
                               "not count"),
                       evidence={"receipt": path.name, "refusal": refusal})

    crossings = _crossings(receipt)
    leads = [r for r in crossings if r.get("disposition") == LEAD_STATE]
    counts = receipt.get("counts") or {}
    rows = [r for r in receipt.get("targets", []) if isinstance(r, dict)]
    searched = [r for r in rows if r.get("outcome") == "searched"]
    pinned = sum(1 for r in rows if r.get("cache_sha256"))

    new_observations = {
        "receipt": path.name,
        "sector": receipt.get("sector"),
        "generated_at": receipt.get("generated_at"),
        "targets_attempted": len(rows),
        "targets_searched": len(searched),
        "rows_with_pinned_product": pinned,
        "preregistration": preregistration,
    }
    controls = {
        "uniformity_pass": (receipt.get("uniformity") or {}).get("pass"),
        "placebo_pass": (receipt.get("placebo") or {}).get("pass"),
        "budget_share_used": (receipt.get("budget") or {}).get("survey_sum_reported"),
        "publish_gate": "accepted",
    }
    evidence = {
        "sector": receipt.get("sector"),
        "sde_threshold": receipt.get("sde_threshold", 8.0),
        "pooled_null": receipt.get("pooled_null"),
        "counts": counts,
        "crossings": [{"tic": r.get("tic"), "sde": r.get("sde"),
                       "disposition": r.get("disposition")} for r in crossings],
        "leads": [r.get("tic") for r in leads],
    }
    dispositions = sorted({str(r.get("disposition")) for r in crossings})

    if leads:
        return Finding(
            hypothesis=HYPOTHESIS, verdict=UNRESOLVED, detail=(
                f"sector {receipt.get('sector')}: {len(searched)} searched, "
                f"{len(crossings)} crossing(s) above threshold, "
                f"{len(leads)} lead(s) awaiting human review — a lead is not a "
                "planet; the sample produced a candidate the catalogue does not "
                "carry and a human owes the answer"),
            evidence=evidence, controls=controls,
            wall_seconds=float(receipt.get("wall_seconds") or 0.0),
            new_observations=new_observations)

    return Finding(
        hypothesis=HYPOTHESIS, verdict=KILLED, detail=(
            f"sector {receipt.get('sector')}: {len(searched)} of {len(rows)} "
            f"targets searched, {len(crossings)} crossing(s) above SDE "
            f"{receipt.get('sde_threshold', 8.0):g}, every one dispositioned "
            f"({', '.join(dispositions) or 'none'}), zero leads. The sample holds "
            "no uncatalogued transit this instrument can see, at this sample and "
            "this threshold — an empty shelf with every exit counted"),
        evidence=evidence, controls=controls,
        wall_seconds=float(receipt.get("wall_seconds") or 0.0),
        new_observations=new_observations)
