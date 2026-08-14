"""Small, durable public receipts derived from full numerical reports.

Full Windowsill reports intentionally contain heavy lattice snapshots and plot
payloads.  They are valuable locally and in ``reports/latest.html``, but adding
roughly a megabyte of repeated imagery to git every night is not a sustainable
public record.  A measurement receipt keeps every scalar/curve used by the
milestone checker, plus provenance and reproduction commands, while replacing
only snapshot-like fields with explicit SHA-256 records.

The result is deterministic, stdlib-only, and honest about its boundary: it is
evidence for regrading saved measurements, not a simulation rerun.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA = "windowsill.measurement-receipt.v1"

#: Scheduler decision for the CURRENT process's turn, or ``None`` for manual
#: runs. A module-level seam on purpose: the planner decides in ``cli._run_next``
#: and the receipt is written many frames deeper (render → write_public_receipt)
#: without a parameter path that survives the dispatch boundary. The scheduler
#: sets it around exactly one dispatch and clears it in a ``finally``, so a
#: manual ``lab m03`` can never inherit a stale decision.
_PLANNED_DECISION: dict | None = None


def set_planned_decision(decision: dict | None) -> None:
    """Arm the compact ``planned`` block for receipts written by this turn."""
    global _PLANNED_DECISION
    _PLANNED_DECISION = decision


def clear_planned_decision() -> None:
    """Disarm the seam — the scheduler's ``finally`` companion to ``set``."""
    set_planned_decision(None)


def planned_block(decision: dict) -> dict:
    """The compact, receipt-ready view of a planner decision.

    Chosen + one-line reason + the top-3 scoreboard mids with scores: enough
    for a future check to re-derive the pick from the same ledger (the
    re-derivation test in tests/test_planner.py is the pattern), small enough
    to commit nightly forever.
    """
    return {
        "planner": decision.get("planner"),
        "chosen": decision.get("chosen"),
        "reason": decision.get("reason"),
        "scoreboard": [
            {"mid": e.get("mid"), "cls": e.get("cls"), "score": e.get("score")}
            for e in (decision.get("scoreboard") or [])[:3]
        ],
    }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _is_snapshot_field(key: str) -> bool:
    lowered = key.lower()
    return lowered == "snapshots" or lowered.endswith("_snapshots")


def build_public_receipt(report: dict, source_bytes: bytes | None = None) -> dict:
    """Return a compact copy of *report* with large visual snapshots omitted.

    Every omitted value receives its own digest and JSON path.  The exact source
    report bytes are also hashed when available, tying the compact receipt to the
    fuller local artifact without pretending the omitted bytes are downloadable.
    """
    omitted: list[dict] = []

    def scrub(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            clean = {}
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if _is_snapshot_field(str(key)):
                    omitted.append({
                        "path": child_path,
                        "sha256": hashlib.sha256(_canonical_bytes(child)).hexdigest(),
                        "reason": "large visual lattice snapshots",
                    })
                    continue
                clean[key] = scrub(child, child_path)
            return clean
        if isinstance(value, list):
            return [scrub(child, f"{path}[{i}]") for i, child in enumerate(value)]
        return value

    clean = scrub(report, "")
    metadata = {
        "schema": RECEIPT_SCHEMA,
        "claim_boundary": (
            "Saved measurements can be regraded; this receipt is not a simulation rerun."
        ),
        "omitted": omitted,
    }
    if source_bytes is not None:
        metadata["source_report_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    # Present exactly when a scheduler turn armed the seam above — a scheduled
    # receipt carries its own selection rationale; a manual run carries none.
    if _PLANNED_DECISION is not None:
        metadata["planned"] = planned_block(_PLANNED_DECISION)
    clean["public_receipt"] = metadata
    return clean


def receipt_text(report: dict, source_bytes: bytes | None = None) -> str:
    """Serialize a public receipt deterministically with a trailing newline."""
    return json.dumps(
        build_public_receipt(report, source_bytes),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"


def write_public_receipt(report: dict, destination: Path,
                         source_bytes: bytes | None = None) -> Path:
    """Write one compact receipt and return its path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(receipt_text(report, source_bytes), encoding="utf-8")
    return destination
