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
