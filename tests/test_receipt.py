"""Compact public receipts preserve evidence while bounding large artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lab.archive import classify_run
from lab.receipt import RECEIPT_SCHEMA, build_public_receipt, receipt_text


def test_receipt_keeps_checker_inputs_and_hashes_snapshots():
    report = {
        "experiment": "M01-ising-verification",
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 9.0, 1.0],
        "snapshots": {"low": [[1, -1], [-1, 1]]},
        "provenance": {"source_commit": "abc123"},
    }
    raw = json.dumps(report).encode("utf-8")
    receipt = build_public_receipt(report, raw)

    assert receipt["T"] == report["T"]
    assert receipt["chi"] == report["chi"]
    assert receipt["provenance"] == report["provenance"]
    assert "snapshots" not in receipt
    meta = receipt["public_receipt"]
    assert meta["schema"] == RECEIPT_SCHEMA
    assert meta["source_report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert meta["omitted"][0]["path"] == "snapshots"
    assert len(meta["omitted"][0]["sha256"]) == 64
    assert "not a simulation rerun" in meta["claim_boundary"]


def test_receipt_is_deterministic_and_nested_snapshot_fields_are_explicit():
    report = {
        "experiment": "M15-glauber-domain-growth",
        "curves": [{"t": [1, 2], "G_snapshots": {"1": [0.9, 0.4]}}],
        "fit": {"slope": 0.486},
    }
    first = receipt_text(report)
    second = receipt_text(report)
    assert first == second
    decoded = json.loads(first)
    assert "G_snapshots" not in decoded["curves"][0]
    assert decoded["fit"]["slope"] == 0.486
    assert decoded["public_receipt"]["omitted"][0]["path"] == "curves[0].G_snapshots"


def test_receipts_preserve_verdict_for_shipped_reports():
    reports = Path(__file__).resolve().parents[1] / "reports"
    checked = 0
    for path in sorted(reports.glob("20??-??-??-*.json")):
        full = json.loads(path.read_text(encoding="utf-8"))
        compact = build_public_receipt(full, path.read_bytes())
        original = classify_run(full)
        receipt = classify_run(compact)
        assert receipt["milestone"] == original["milestone"], path.name
        assert receipt["verdict"] == original["verdict"], path.name
        checked += 1
    assert checked, "repository should ship at least one checkable report"
