"""Tests for the compact plottable physics feed (physics-latest.json)."""
from __future__ import annotations

import base64
import json

from lab import physics_feed


def _tiny_report(L=4):
    """A minimal M01-shape report: a 3-temp χ-sweep + a 4×4 lattice snapshot."""
    ordered = [[1, 1, 1, 1]] * L        # all +1
    disordered = [[1, -1, 1, -1]] * L   # checkerboard-ish
    return {
        "config": {"L": L, "seed": 42, "device": "cpu", "n_sweeps": 100, "n_temps": 3},
        "T": [1.5, 2.5, 3.5],
        "abs_mag": [0.98, 0.42, 0.10],
        "abs_mag_err": [1e-4, 5e-3, 8e-3],
        "chi": [0.03, 8.2, 0.4],
        "energy": [-1.95, -1.40, -1.05],
        "specific_heat": [0.19, 1.1, 0.6],
        "snapshots": {"T=1.500": ordered, "T=2.500": disordered, "T=3.500": disordered},
        "wall_seconds": 3.2,
        "experiment": "M01-ising-verification",
    }


def test_pack_lattice_roundtrips_msb_first():
    # A single row [+1,-1,-1,+1, -1,-1,-1,-1] → bits 1001 0000 → 0x90.
    packed = physics_feed.pack_lattice([[1, -1, -1, 1, -1, -1, -1, -1]])
    assert base64.b64decode(packed) == bytes([0x90])


def test_pack_lattice_pads_to_byte_boundary():
    # 4 sites all +1 → 1111 padded → 1111 0000 = 0xF0.
    assert base64.b64decode(physics_feed.pack_lattice([[1, 1, 1, 1]])) == bytes([0xF0])


def test_build_feed_lifts_curves_and_peak(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-07-14-m01.json").write_text(json.dumps(_tiny_report()), encoding="utf-8")

    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    assert feed is not None
    m01 = feed["m01"]
    assert m01["T"] == [1.5, 2.5, 3.5]
    assert m01["chi"] == [0.03, 8.2, 0.4]
    assert m01["abs_mag_err"] == [1e-4, 5e-3, 8e-3]
    # χ peaks at the middle temperature.
    assert m01["chi_peak_t"] == 2.5
    assert m01["raw_chi_peak_t"] == 2.5
    assert m01["quality_status"] == "ok"
    assert m01["excluded_indices"] == []
    # The run date is derived from the report filename, not a bad string slice.
    assert m01["date"] == "2026-07-14"
    # Onsager's exact T_c rides along for the calibration line.
    assert abs(feed["onsager_tc"] - 2.269185) < 1e-5


def test_build_feed_publishes_qualified_peak_and_disclosed_raw_outlier(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = _tiny_report()
    report.update({
        "T": [1.5, 1.6, 2.3],
        "abs_mag": [0.62, 0.98, 0.65],
        "abs_mag_err": [0.02, 0.001, 0.005],
        "chi": [1900.0, 2.0, 81.0],
        "energy": [-1.7, -1.9, -1.4],
        "specific_heat": [0.2, 0.3, 1.1],
    })
    (reports / "2026-07-25-m01.json").write_text(json.dumps(report), encoding="utf-8")

    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    m01 = feed["m01"]
    assert feed["schema"] == 2
    assert m01["raw_chi_peak_t"] == 1.5
    assert m01["chi_peak_t"] == 2.3
    assert m01["quality_status"] == "degraded"
    assert m01["excluded_indices"] == [0]
    assert "excluded" in m01["quality_note"]


def test_build_feed_packs_three_snapshots(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-07-14-m01.json").write_text(json.dumps(_tiny_report()), encoding="utf-8")

    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    snaps = feed["m01"]["snapshots"]
    assert set(snaps) == {"1.5", "2.5", "3.5"}
    assert feed["m01"]["snapshot_L"] == 4
    # The ordered snapshot is all +1 → every bit set (0xFF bytes).
    assert set(base64.b64decode(snaps["1.5"])) == {0xFF}


def test_build_feed_returns_none_without_snapshot_report(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    # A report with no snapshots (e.g. an M02 FSS run) must not be chosen.
    (reports / "2026-07-05-m02.json").write_text(
        json.dumps({"experiment": "M02", "L_values": [8, 12]}), encoding="utf-8"
    )
    assert physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab") is None


def test_build_feed_accepts_legacy_m01_but_rejects_other_snapshot_experiments(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()

    legacy_m01 = _tiny_report()
    legacy_m01.pop("experiment")
    (reports / "2026-07-14-m01.json").write_text(
        json.dumps(legacy_m01), encoding="utf-8"
    )

    impostor = _tiny_report()
    impostor["experiment"] = "M02-finite-size-scaling"
    (reports / "2026-07-15-m02.json").write_text(
        json.dumps(impostor), encoding="utf-8"
    )

    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    assert feed is not None
    assert feed["generated_from"] == "reports/2026-07-14-m01.json"


def test_latest_m01_receipt_wins_and_retains_only_attested_snapshots(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    raw_report = _tiny_report()
    raw_path = reports / "2026-07-14-m01.json"
    raw_path.write_text(json.dumps(raw_report), encoding="utf-8")
    previous_feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab"
    )

    receipts = reports / "receipts"
    receipts.mkdir()
    receipt = _tiny_report()
    snapshots = receipt.pop("snapshots")
    receipt["chi"] = [0.02, 9.1, 0.3]
    receipt["provenance"] = {"source_commit": "receipt-source"}
    receipt["public_receipt"] = {
        "omitted": [{
            "path": "snapshots",
            "sha256": physics_feed._snapshot_digest(snapshots),
        }]
    }
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )

    other = dict(receipt, experiment="M02-finite-size-scaling")
    (receipts / "run-2026-07-16-m02.json").write_text(
        json.dumps(other), encoding="utf-8"
    )

    feed = physics_feed.build_feed(
        reports_dir=reports,
        lab_home=tmp_path / "nolab",
        previous_feed=previous_feed,
    )
    assert feed is not None
    assert feed["generated_from"] == "reports/receipts/run-2026-07-15-m01.json"
    assert feed["m01"]["source_report"] == feed["generated_from"]
    assert feed["m01"]["date"] == "2026-07-15"
    assert feed["m01"]["chi"] == receipt["chi"]
    assert feed["provenance"] == receipt["provenance"]
    assert feed["m01"]["snapshots"] == previous_feed["m01"]["snapshots"]

    oversized = json.loads(json.dumps(previous_feed))
    encoded = oversized["m01"]["snapshots"]["1.5"]
    oversized["m01"]["snapshots"]["1.5"] = base64.b64encode(
        base64.b64decode(encoded) + b"\0"
    ).decode("ascii")
    rejected = physics_feed.build_feed(
        reports_dir=reports,
        lab_home=tmp_path / "nolab",
        previous_feed=oversized,
    )
    assert "snapshots" not in rejected["m01"]


def test_build_physics_feed_writes_file(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-07-14-m01.json").write_text(json.dumps(_tiny_report()), encoding="utf-8")
    out = tmp_path / "physics-latest.json"

    written = physics_feed.build_physics_feed(
        out_path=out, reports_dir=reports, lab_home=tmp_path / "nolab",
        provenance={"code_sha": "abc123"},
    )
    assert written == out
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == physics_feed.PHYSICS_SCHEMA
    assert data["provenance"]["code_sha"] == "abc123"
    assert data["m01"]["config"]["seed"] == 42
