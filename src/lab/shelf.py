"""shelf — the exit condition for ``lead-awaiting-human-review``.

The contract this enforces is ``docs/shelf-exit-contract.md``, RULED by Ben on
2026-08-19: **>= 2 sectors to promote, and a promoted lead goes to ExoFOP as a
CTOI.** Before this module, the shelf had an entry condition and no exit
condition — seven lead rows by 2026-08-19, the oldest from 08-15, none ruled
on. "A queue with an entry condition and no exit condition is not a standard;
it is a slow stop."

Three principles, from the contract, load-bearing throughout:

* **The machine may refute. Only a human may promote.** The best state this
  module can assign is ``promotable-awaiting-ben`` — a recommendation, never a
  promotion. Promotions come only from the rulings file, written by a person.
* **An ungraded criterion is not a passed criterion.** A star whose physical
  admissibility could not be graded (no TIC radius — TIC 77044472), or whose
  depth consistency cannot be computed because receipts carry no depth
  uncertainty, is PARKED with the gap named, never waved through.
* **Parking is not refutation and must never be reported as one.** A parked
  lead is the lab admitting a limit — of data, of bandwidth — which is an
  honest thing to publish and a dishonest thing to disguise.

The register is a **pure derivation** of the committed hunt receipts plus the
day: same receipts, same day, same register, on any clone — the DET-2 lesson
applied to a new surface before it grew its own mtime dependence. Nothing
here writes; rendering and committing stay with their existing owners.

Grading is per-star, not per-sector (§3): every committed row for a TIC is in
evidence, so a gate that fired in sector 3 stands against a clean look in
sector 2. The §4 significance criterion is currently graded per sector (alpha
in both schemes, in every sector independently) — the contract *proposes*
combining evidence across sectors, but the general carry-evidence-forward
machinery (§3, "the largest open build in the sky track") is not built, and a
combination rule invented here would be exactly the kind of statistic the
2026-08-19 fold-gate audit existed to catch. Per-sector-independent is the
conservative reading; it can only under-promote, never over-promote.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

from . import a04
from .a05_sensitivity import FAP_ALPHA

#: §5 — the two deadlines. 14 days: the lead surfaces with its question.
#: 60 days: auto-parked ``stale-unruled``, recorded as a bandwidth admission.
SURFACE_AFTER_DAYS = 14
STALE_AFTER_DAYS = 60

#: §4 depth consistency: pairwise depths must agree within this many sigma.
DEPTH_SIGMA_TOL = 3.0

LEAD = "lead-awaiting-human-review"

#: Physics refutations — a named astrophysical or instrumental explanation.
#: Any of these on ANY sector of a star parks the star (§4: "every gate
#: silent, on every sector — not silent on the sector it was found in").
GATE_VERDICTS = frozenset({
    "stellar-pulsation", "harmonic-alias", "eclipsing-binary-odd-even",
    "eclipsing-binary-secondary", "eclipsing-binary-p2-alias",
    "phased-brightening", "low-significance", "insufficient-coverage",
    "period-railed", "centroid-shift", "companion-too-large",
    "blended-known-planet", "blend-favours-neighbour",
})

#: Catalog identities — somebody already filed this signal. Not a claim about
#: what it is; only "not a fresh lead".
IDENTITY_VERDICTS = frozenset({
    "recovery-or-known", "known-planet", "toi-known-fp", "ctoi-known",
})

#: The rulings a human may enter (§1's three exits; ``parked`` is machine-side
#: and never appears here). Anything else in the rulings file is refused
#: loudly — a vocabulary that can drift from its checker is the VET-F1 defect.
HUMAN_RULINGS = frozenset({"promoted", "refuted", "not-novel"})


# ------------------------------------------------------------- collection --

def _receipt_day(payload: dict, path: Path) -> str:
    """``YYYY-MM-DD`` a receipt was generated — its content's word first,
    the filename's date stem only as a fallback for receipts predating
    ``generated_at``."""
    stamp = str(payload.get("generated_at") or "")
    if len(stamp) >= 10:
        return stamp[:10]
    name = path.stem  # hunt-2026-08-14-s2[-hhmm]
    parts = name.split("-")
    if len(parts) >= 4:
        return "-".join(parts[1:4])
    raise ValueError(f"receipt carries no date: {path}")


def collect(hunts_dir: Path) -> dict[int, list[dict]]:
    """Every committed row, grouped by TIC, for every star with >= 1 lead row.

    Non-lead rows ride along on purpose: the star is graded on everything the
    pipeline ever said about it, not on its best sector.
    """
    observations: dict[int, list[dict]] = {}
    leads: set[int] = set()
    for path in sorted(Path(hunts_dir).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("targets") or []
        day = _receipt_day(payload, path)
        sector = payload.get("sector")
        for row in rows:
            tic = row.get("tic")
            disposition = row.get("disposition")
            if tic is None or disposition is None:
                continue
            obs = {"tic": int(tic), "sector": sector, "day": day,
                   "receipt": path.name, "disposition": disposition,
                   "row": row,
                   # Receipt-level: the FAPs in `row` are graded against this
                   # receipt's own permutation null, so its control travels
                   # with every row it minted.
                   "uniformity": payload.get("uniformity")}
            observations.setdefault(int(tic), []).append(obs)
            if disposition == LEAD:
                leads.add(int(tic))
    return {tic: observations[tic] for tic in sorted(leads)}


# ---------------------------------------------------------- §4: criteria --

def _fap(row: dict, scheme: str):
    try:
        return float(row["fap"]["schemes"][scheme]["fap_empirical"])
    except (KeyError, TypeError, ValueError):
        return None


def _persistence(lead_obs: list[dict]) -> list[str]:
    reasons = []
    sectors = sorted({o["sector"] for o in lead_obs})
    if len(sectors) < 2:
        reasons.append(
            f"persistence: detected in 1 sector — §4 requires >= 2 "
            f"(structurally blind to single-sector planets, by ruling)")
        return reasons
    periods = [float(o["row"]["period_days"]) for o in lead_obs]
    ref = periods[0]
    if any(abs(p / ref - 1.0) > a04.PERIOD_TOL_FRAC for p in periods[1:]):
        reasons.append(
            f"persistence: period disagrees across sectors beyond "
            f"PERIOD_TOL_FRAC={a04.PERIOD_TOL_FRAC}")
    errs = [o["row"].get("depth_err") for o in lead_obs]
    if any(e is None or not (float(e) > 0) for e in errs):
        reasons.append(
            "persistence: depth consistency ungradeable — receipts carry no "
            "depth uncertainty (§4 needs a measured sigma_depth; an ungraded "
            "criterion is not a passed criterion)")
    else:
        depths = [float(o["row"]["depth"]) for o in lead_obs]
        for i in range(len(depths)):
            for j in range(i + 1, len(depths)):
                sigma = math.hypot(float(errs[i]), float(errs[j]))
                if abs(depths[i] - depths[j]) > DEPTH_SIGMA_TOL * sigma:
                    reasons.append(
                        f"persistence: depths differ beyond "
                        f"{DEPTH_SIGMA_TOL:g} sigma between sectors "
                        f"{lead_obs[i]['sector']} and {lead_obs[j]['sector']}")
                    return reasons
    return reasons


def _significance(lead_obs: list[dict]) -> list[str]:
    """Both shuffling schemes under alpha, in every lead sector — but a FAP is
    a statement made AGAINST a null, and the receipt's own uniformity control
    is what certifies that null. check_a05 gate 10 (src/lab/checks.py:3042)
    rules that a failed control makes every graded FAP in the receipt
    *uninterpretable, not negative*; this mirrors that verdict rather than
    re-deriving the KS statistic (check_a05 already polices the recorded
    block against a re-run, so `pass` here is a checked claim, not a trusted
    one). Three of the committed receipts carry exactly this failure — one of
    them (hunt-2026-08-18-s2-1000) is the receipt that minted TIC 77044472's
    lead — so this is a live case, not an edge case."""
    for o in lead_obs:
        uni = o.get("uniformity")
        if not isinstance(uni, dict) or not isinstance(uni.get("pass"), bool):
            return [f"significance: uniformity control ungraded in "
                    f"{o['receipt']} — an ungraded control is not a passed "
                    "control, and a FAP without its null is not a number"]
        if uni["pass"] is False:
            return [f"significance: FAP uninterpretable — the receipt's own "
                    f"uniformity control failed (D={uni.get('ks_stat', 0):.3f}"
                    f" over n={uni.get('n_control')}) in {o['receipt']}; "
                    "uninterpretable is not passed (check_a05 gate 10)"]
        for scheme in ("iid", "block"):
            fap = _fap(o["row"], scheme)
            if fap is None:
                return [f"significance: no {scheme} FAP in sector "
                        f"{o['sector']} — ungraded is not passed"]
            if fap > FAP_ALPHA:
                return [f"significance: {scheme} FAP {fap:.4g} > "
                        f"alpha={FAP_ALPHA} in sector {o['sector']} "
                        f"(both shuffling schemes must clear, everywhere)"]
    return []


def _star_gate(tic: int, all_obs: list[dict]) -> list[str]:
    """§3's gate: the star's per-sector fold evidence combined as one body.

    A star observed eight times must not get eight weak looks — TIC 287328866
    read the doubled-fold difference under 5σ in six of eight sectors while
    the combination reads 9.8σ. The combination is `combine_p2_folds` via
    `lab.a05_star` (the VET-F2-corrected signed statistic), so this fires only
    a verdict the reviewed combiner itself emits; with fewer than two graded
    sectors it stays silent and the per-sector criteria stand alone."""
    from . import a05_star
    d = a05_star.star_dossier(tic, all_obs)
    combined = d["combined_fold"]
    if combined.get("verdict"):
        sectors = ",".join(str(s) for s in d["graded_sectors"])
        per = ", ".join(f"{s:.1f}σ" for s in combined["per_sector_sigma"])
        return [f"gate fired (combined): {combined['verdict']} at "
                f"{combined['difference_sigma']:.1f}σ across sectors "
                f"[{sectors}] (per-sector: {per} — no single sector cleared "
                "the bar alone)"]
    return []


def _gates_silent(all_obs: list[dict]) -> list[str]:
    reasons = []
    for o in all_obs:
        if o["disposition"] in GATE_VERDICTS:
            reasons.append(f"gate fired: {o['disposition']} in sector "
                           f"{o['sector']} ({o['receipt']})")
        elif o["disposition"] in IDENTITY_VERDICTS:
            reasons.append(f"catalogued: {o['disposition']} in sector "
                           f"{o['sector']} — not novel")
    return reasons


def _admissible(lead_obs: list[dict]) -> list[str]:
    for o in lead_obs:
        phys = (o["row"].get("disposition_evidence") or {}).get("physical")
        if phys is None:
            return ["physical admissibility ungraded — receipt "
                    f"{o['receipt']} predates the 2026-08-19 gate; "
                    "an unrun gate is not a passed gate"]
        if phys.get("reason"):
            return [f"physical admissibility ungraded — {phys['reason']} "
                    f"(a missing radius is not a small radius)"]
        if phys.get("verdict"):
            return [f"physically inadmissible: {phys['verdict']}"]
    return []


# ------------------------------------------------------------- the grade --

def grade(tic: int, all_obs: list[dict], today: date,
          ruling: dict | None = None) -> dict:
    lead_obs = [o for o in all_obs if o["disposition"] == LEAD]
    first = min(o["day"] for o in lead_obs)
    days = (today - datetime.strptime(first, "%Y-%m-%d").date()).days

    entry = {
        "tic": tic,
        "first_seen": first,
        "days_on_shelf": days,
        "sectors": sorted({o["sector"] for o in lead_obs}),
        "receipts": sorted({o["receipt"] for o in all_obs}),
    }

    if ruling is not None:
        entry.update(state=ruling["ruling"], clock="ruled",
                     ruled_by=ruling.get("by"), ruled_on=ruling.get("date"),
                     why=ruling.get("why"), promotable=False, parked_on=[],
                     question="")
        return entry

    parked_on = (_persistence(lead_obs) + _significance(lead_obs)
                 + _gates_silent(all_obs) + _star_gate(tic, all_obs)
                 + _admissible(lead_obs))
    promotable = not parked_on

    if days >= STALE_AFTER_DAYS:
        clock = "stale-unruled"
        entry["stale_reason"] = ("no human ruling within the contract window "
                                 f"({STALE_AFTER_DAYS} days) — parked as a "
                                 "bandwidth admission, not a refutation")
    elif days >= SURFACE_AFTER_DAYS:
        clock = "surfaced"
    else:
        clock = "fresh"

    entry.update(
        state="promotable-awaiting-ben" if promotable else "parked",
        promotable=promotable,
        parked_on=parked_on,
        clock=clock,
        question=("promote or refute — every machine criterion is clear"
                  if promotable else parked_on[0]),
    )
    return entry


# ---------------------------------------------------------- the register --

def load_rulings(path: Path | None) -> dict[int, dict]:
    if path is None or not Path(path).exists():
        return {}
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    for r in entries:
        verdict = r.get("ruling")
        if verdict not in HUMAN_RULINGS:
            raise ValueError(
                f"ruling {verdict!r} for TIC {r.get('tic')} is not in the "
                f"contract's vocabulary {sorted(HUMAN_RULINGS)} — "
                "refusing the whole file rather than skipping a row")
        out[int(r["tic"])] = r
    return out


def register(hunts_dir: Path, rulings: Path | None,
             today: date) -> list[dict]:
    """The whole shelf, graded, oldest first. Pure: reads receipts and the
    rulings file, writes nothing."""
    ruled = load_rulings(rulings)
    grouped = collect(hunts_dir)
    entries = [grade(tic, obs, today, ruled.get(tic))
               for tic, obs in grouped.items()]
    entries.sort(key=lambda e: (e["first_seen"], e["tic"]))
    return entries


def render_text(entries: list[dict]) -> str:
    """The CLI surface: one line per star, the question in full below it."""
    if not entries:
        return "shelf: empty — no lead-awaiting-human-review rows on record."
    lines = []
    for e in entries:
        sectors = ",".join(str(s) for s in e["sectors"])
        head = (f"TIC {e['tic']:<12} {e['state']:<24} "
                f"clock={e['clock']:<13} first_seen={e['first_seen']} "
                f"({e['days_on_shelf']}d) sectors=[{sectors}]")
        lines.append(head)
        if e.get("why"):
            lines.append(f"    ruling: {e['why']}")
        elif e.get("question"):
            lines.append(f"    q: {e['question']}")
        for r in e.get("parked_on", [])[1:]:
            lines.append(f"       also: {r}")
    return "\n".join(lines)
