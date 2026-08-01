"""Tests for the compact plottable physics feed (physics-latest.json)."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

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
    # valid_indices is exactly the complement of excluded_indices.
    assert m01["valid_indices"] == [1, 2]
    assert sorted(m01["excluded_indices"] + m01["valid_indices"]) == list(range(len(m01["T"])))


def test_build_feed_invalid_sweep_claims_no_qualified_peak_but_keeps_raw(tmp_path):
    # Three separate 5σ |M|(T) rises → 3 exclusions > EQUIL_MAX_EXCLUDED → the
    # sweep grades invalid: no qualified peak, raw argmax still disclosed.
    reports = tmp_path / "reports"
    reports.mkdir()
    report = _tiny_report()
    report.update({
        "T": [1.0, 1.2, 1.4, 1.6, 1.8, 2.0],
        "abs_mag": [0.1, 0.9, 0.1, 0.9, 0.1, 0.9],
        "abs_mag_err": [1e-4] * 6,
        "chi": [0.5, 3.0, 9.0, 2.0, 1.0, 0.5],
        "energy": [-1.9] * 6,
        "specific_heat": [0.2] * 6,
        "snapshots": {"T=1.000": [[1, -1], [-1, 1]]},
    })
    (reports / "2026-07-26-m01.json").write_text(json.dumps(report), encoding="utf-8")

    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    m01 = feed["m01"]
    assert m01["quality_status"] == "invalid"
    assert m01["chi_peak_t"] is None
    assert m01["raw_chi_peak_t"] == 1.4
    assert m01["excluded_indices"] == [0, 2, 4]
    assert m01["valid_indices"] == [1, 3, 5]
    assert sorted(m01["excluded_indices"] + m01["valid_indices"]) == list(range(len(m01["T"])))


@pytest.mark.parametrize("field, bad", [("T", "corrupt"), ("chi", None)])
def test_build_feed_degrades_to_none_on_non_numeric_curve_element(tmp_path, field, bad):
    # A report can pass the list-shape gate with a non-numeric element; that is
    # "no usable M01 sweep", not a crash of the publish path.
    reports = tmp_path / "reports"
    reports.mkdir()
    report = _tiny_report()
    values = list(report[field])
    values[1] = bad
    report[field] = values
    (reports / "2026-07-27-m01.json").write_text(json.dumps(report), encoding="utf-8")

    assert physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab") is None


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
    # Attested retention is this run's own evidence — no staleness label.
    assert "snapshots_source_report" not in feed["m01"]
    assert "snapshots_date" not in feed["m01"]

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
    assert "snapshots_source_report" not in rejected["m01"]
    assert "snapshots_date" not in rejected["m01"]


# ── Disclosed-stale carry-forward: attestation failed, lattices ride labeled ─


def _snapshotless_receipt(attested_sha256=None):
    """An M01 receipt whose run omitted its snapshots from the public record."""
    receipt = _tiny_report()
    receipt.pop("snapshots")
    receipt["chi"] = [0.05, 7.7, 0.5]
    if attested_sha256 is not None:
        receipt["public_receipt"] = {
            "omitted": [{"path": "snapshots", "sha256": attested_sha256}]
        }
    return receipt


def _previous_feed_from_raw(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-07-14-m01.json").write_text(
        json.dumps(_tiny_report()), encoding="utf-8"
    )
    previous = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    return reports, previous


def test_failed_attestation_carries_previous_snapshots_with_disclosure(tmp_path):
    # The PR #66 regression shape: a receipt-based rebuild whose attested digest
    # does not match the previous feed's lattices went dark. Now the previous
    # lattices ride forward labeled with the run they actually came from.
    reports, previous_feed = _previous_feed_from_raw(tmp_path)
    receipts = reports / "receipts"
    receipts.mkdir()
    receipt = _snapshotless_receipt("0" * 64)  # attests some OTHER run's lattices
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=previous_feed,
    )
    m01 = feed["m01"]
    assert feed["generated_from"] == "reports/receipts/run-2026-07-15-m01.json"
    assert m01["snapshots"] == previous_feed["m01"]["snapshots"]
    assert m01["snapshot_L"] == previous_feed["m01"]["snapshot_L"]
    assert m01["snapshots_source_report"] == previous_feed["m01"]["source_report"]
    assert m01["snapshots_date"] == previous_feed["m01"]["date"]


def test_receipt_without_any_attestation_also_carries_disclosed_snapshots(tmp_path):
    reports, previous_feed = _previous_feed_from_raw(tmp_path)
    receipts = reports / "receipts"
    receipts.mkdir()
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(_snapshotless_receipt(None)), encoding="utf-8"
    )

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=previous_feed,
    )
    m01 = feed["m01"]
    assert m01["snapshots"] == previous_feed["m01"]["snapshots"]
    assert m01["snapshots_source_report"] == "reports/2026-07-14-m01.json"
    assert m01["snapshots_date"] == "2026-07-14"


def test_stale_carry_names_the_original_run_across_consecutive_passes(tmp_path):
    # Two failed attestations in a row must still name the run the lattices
    # came from, not the intermediate carrier.
    reports, previous_feed = _previous_feed_from_raw(tmp_path)
    receipts = reports / "receipts"
    receipts.mkdir()
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(_snapshotless_receipt("0" * 64)), encoding="utf-8"
    )
    first_stale = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=previous_feed,
    )
    (receipts / "run-2026-07-16-m01.json").write_text(
        json.dumps(_snapshotless_receipt("f" * 64)), encoding="utf-8"
    )

    second_stale = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=first_stale,
    )
    m01 = second_stale["m01"]
    assert second_stale["generated_from"] == "reports/receipts/run-2026-07-16-m01.json"
    assert m01["snapshots"] == previous_feed["m01"]["snapshots"]
    assert m01["snapshots_source_report"] == "reports/2026-07-14-m01.json"
    assert m01["snapshots_date"] == "2026-07-14"


def test_stale_carry_refuses_undecodable_previous_snapshots(tmp_path):
    # A previous feed whose packed lattice no longer unpacks cleanly is not
    # carried: no snapshots and no staleness label (never a mislabeled panel).
    reports, previous_feed = _previous_feed_from_raw(tmp_path)
    receipts = reports / "receipts"
    receipts.mkdir()
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(_snapshotless_receipt(None)), encoding="utf-8"
    )
    corrupted = json.loads(json.dumps(previous_feed))
    encoded = corrupted["m01"]["snapshots"]["1.5"]
    corrupted["m01"]["snapshots"]["1.5"] = base64.b64encode(
        base64.b64decode(encoded) + b"\0"
    ).decode("ascii")

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=corrupted,
    )
    assert "snapshots" not in feed["m01"]
    assert "snapshots_source_report" not in feed["m01"]
    assert "snapshots_date" not in feed["m01"]


def test_stale_carry_refuses_when_origin_is_unknown(tmp_path):
    # Lattices whose source run cannot be named cannot be labeled stale, so
    # they do not ride forward at all.
    reports, previous_feed = _previous_feed_from_raw(tmp_path)
    receipts = reports / "receipts"
    receipts.mkdir()
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(_snapshotless_receipt(None)), encoding="utf-8"
    )
    anonymous = json.loads(json.dumps(previous_feed))
    del anonymous["m01"]["source_report"]
    anonymous["m01"].pop("snapshots_source_report", None)

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=anonymous,
    )
    assert "snapshots" not in feed["m01"]
    assert "snapshots_source_report" not in feed["m01"]


def test_fresh_snapshots_carry_no_staleness_fields(tmp_path):
    reports, _ = _previous_feed_from_raw(tmp_path)
    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    assert "snapshots" in feed["m01"]
    assert "snapshots_source_report" not in feed["m01"]
    assert "snapshots_date" not in feed["m01"]


# ── The committed artifact itself: the canary PR #66 lacked ─────────────────


def test_committed_feed_is_not_dark_while_its_receipt_attests_lattices():
    # PR #66 committed a rebuilt physics-latest.json with no snapshots while
    # its own receipt attested them — three blank canvases under a "straight
    # from the run" caption. Re-derive the attestation from the committed
    # artifact: snapshots must be present and either match the receipt's
    # digest exactly (this run's evidence) or carry both staleness labels.
    repo_root = Path(__file__).resolve().parents[1]
    feed = json.loads((repo_root / "physics-latest.json").read_text(encoding="utf-8"))
    m01 = feed["m01"]
    receipt = json.loads(
        (repo_root / feed["generated_from"]).read_text(encoding="utf-8")
    )
    expected = physics_feed._attested_snapshot_digest(receipt)
    if expected is None and "snapshots" not in m01:
        pytest.skip("newest receipt attests no lattices and the feed carries none")

    packed = m01.get("snapshots")
    assert isinstance(packed, dict) and packed, (
        "committed feed dropped its lattice snapshots while its receipt attests them"
    )
    lattice_L = m01.get("snapshot_L")
    assert isinstance(lattice_L, int) and not isinstance(lattice_L, bool)
    reconstructed = physics_feed._unpack_snapshots(packed, lattice_L)
    assert reconstructed is not None, "committed packed lattices do not unpack"
    fresh = (
        expected is not None
        and physics_feed._snapshot_digest(reconstructed) == expected
    )
    if fresh or "/receipts/run-" not in feed["generated_from"]:
        assert "snapshots_source_report" not in m01
        assert "snapshots_date" not in m01
    else:
        assert isinstance(m01.get("snapshots_source_report"), str)
        assert isinstance(m01.get("snapshots_date"), str)


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
