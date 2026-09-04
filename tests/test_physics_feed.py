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


# ── Turn-stamped receipts: the attestation that silently never ran ──────────
#
# Every test above this line uses a BARE ``run-<date>-<slug>.json`` receipt — the
# only shape that existed before turn-stamping landed on 2026-08-02. All 19 of
# them passed against a raw-name derivation that kept the turn stamp, because a
# bare name has no stamp to keep. That is how 33 days of 2026-08-01 lattices
# shipped under a 2026-08-30 provenance line with a green suite.
#
# TWO traps make the obvious regression test pass on the unfixed code, and both
# have to be closed or this proves nothing:
#
# 1. Writing a stamped receipt AND its raw report side by side lets
#    ``_newest_m01_report`` simply select the RAW report — also a valid M01 sweep
#    in the same tree — and the feed comes out fresh without the attestation path
#    ever running. Closed by forcing the receipt strictly newer with ``os.utime``
#    and asserting on ``generated_from``.
# 2. Handing in a ``previous_feed`` built from that same report lets the OTHER
#    attestation path (``_attested_packed_snapshots``, which re-hashes the
#    already-packed lattices) succeed on the broken code, unlabeled — a green
#    test for the wrong reason. Closed by passing ``previous_feed=None``, so the
#    only route to a lattice is recovering the raw report BY NAME.


def _stamped_receipt_over_raw_report(tmp_path, receipt_name):
    """A turn-stamped receipt that outranks the raw report it omitted snapshots from.

    Returns ``(reports_dir, raw_report)``. ``os.utime`` forces the receipt
    strictly newer — the production ordering, where the receipt is written just
    after the run that produced the report — so selection cannot fall back to the
    raw report and mask the seam under test.
    """
    import os

    reports = tmp_path / "reports"
    reports.mkdir()
    raw = _tiny_report()
    raw_path = reports / "2026-08-30-m01.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")

    receipt = _tiny_report()
    snapshots = receipt.pop("snapshots")
    receipt["chi"] = [0.04, 8.8, 0.35]     # this turn's OWN numbers, not the raw's
    receipt["public_receipt"] = {
        "omitted": [{
            "path": "snapshots",
            "sha256": physics_feed._snapshot_digest(snapshots),
        }]
    }
    receipts = reports / "receipts"
    receipts.mkdir()
    receipt_path = receipts / receipt_name
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    stamp = raw_path.stat().st_mtime
    os.utime(raw_path, (stamp, stamp))
    os.utime(receipt_path, (stamp + 60, stamp + 60))
    return reports, raw


def test_turn_stamped_receipt_recovers_the_raw_report_it_was_distilled_from(tmp_path):
    # The regression itself. ``run-2026-08-30-2100-m01.json`` is distilled from
    # ``2026-08-30-m01.json``: the turn stamp lives ONLY in the receipt name,
    # because one report is written per (date, slug) while every turn gets its own
    # receipt. A blind ``name[4:]`` looks for ``2026-08-30-2100-m01.json``, a
    # filename no code in this repo has ever written, so the lookup misses, the
    # attestation is skipped, and — with no previous feed to carry — the triptych
    # goes dark. Fixed, the raw report is found by name and its lattices are
    # attested against the receipt's own digest.
    reports, raw = _stamped_receipt_over_raw_report(
        tmp_path, "run-2026-08-30-2100-m01.json"
    )

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=None,
    )
    m01 = feed["m01"]
    # The receipt won selection — without this the lattices could be fresh for
    # the wrong reason (the raw report having been chosen directly).
    assert feed["generated_from"] == "reports/receipts/run-2026-08-30-2100-m01.json"
    assert m01["chi"] == [0.04, 8.8, 0.35]
    # On the unfixed derivation there is no ``snapshots`` key at all.
    assert set(m01["snapshots"]) == {"1.5", "2.5", "3.5"}
    assert m01["snapshot_L"] == 4
    # Attested from this run's own raw report → this run's evidence, unlabeled.
    assert "snapshots_source_report" not in m01
    assert "snapshots_date" not in m01


def test_turn_stamped_attestation_beats_an_unrelated_stale_carry(tmp_path):
    # The same seam with a previous feed present, and the previous feed holding
    # ANOTHER run's lattices so the packed-retention path cannot rescue the broken
    # derivation. Unfixed, this falls through to the disclosed-stale carry and the
    # page keeps serving the older run under the newer provenance line — the exact
    # 33-day shape. Fixed, the fresh attestation wins and no staleness is claimed.
    reports, raw = _stamped_receipt_over_raw_report(
        tmp_path, "run-2026-08-30-2100-m01.json"
    )
    older = tmp_path / "older"
    older.mkdir()
    unrelated = _tiny_report()
    unrelated["snapshots"] = {"T=1.500": [[-1, -1, -1, -1]] * 4}
    (older / "2026-08-01-m01.json").write_text(json.dumps(unrelated), encoding="utf-8")
    stale_feed = physics_feed.build_feed(reports_dir=older, lab_home=tmp_path / "nolab")
    assert stale_feed["m01"]["snapshots"]

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=stale_feed,
    )
    m01 = feed["m01"]
    assert feed["generated_from"] == "reports/receipts/run-2026-08-30-2100-m01.json"
    assert m01["snapshots"] != stale_feed["m01"]["snapshots"]
    assert "snapshots_source_report" not in m01
    assert "snapshots_date" not in m01


def test_legacy_unstamped_receipt_still_attests_from_its_raw_report(tmp_path):
    # The compatibility half: a receipt written before 2026-08-02 carries no turn
    # stamp, so the parse must return exactly the string the old slice returned.
    reports, raw = _stamped_receipt_over_raw_report(
        tmp_path, "run-2026-08-30-m01.json"
    )

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=None,
    )
    assert feed["generated_from"] == "reports/receipts/run-2026-08-30-m01.json"
    assert set(feed["m01"]["snapshots"]) == {"1.5", "2.5", "3.5"}
    assert "snapshots_source_report" not in feed["m01"]


def test_raw_report_names_parses_the_turn_stamp_off_but_keeps_the_date():
    # The date is also four digits followed by a hyphen, so a turn-stamp matcher
    # run against the whole name eats the YEAR instead. Pinned directly.
    assert physics_feed._raw_report_names("run-2026-08-30-2100-m01.json")[0] == (
        "2026-08-30-m01.json"
    )
    assert physics_feed._raw_report_names("run-2026-08-30-m01.json") == [
        "2026-08-30-m01.json"
    ]


# ── snapshot_peak_t: the frame's temperature travels with the frame ─────────


def test_snapshot_peak_t_rides_with_this_runs_own_lattices(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = _tiny_report()
    report["snapshot_peak_t"] = 2.5
    (reports / "2026-08-30-m01.json").write_text(json.dumps(report), encoding="utf-8")

    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    assert feed["m01"]["snapshot_peak_t"] == 2.5


def test_attested_retention_publishes_this_runs_own_peak_temperature(tmp_path):
    """The third branch: lattices retained by digest are THIS run's, so is its T.

    ``build_feed`` reaches a lattice three ways, and each needs its own frame
    temperature answered separately. The fresh and disclosed-stale paths are
    pinned above; this is the one in between, and the one a rebuild actually
    walks — a receipt-only tree (the raw report is gitignored) whose omission
    digest matches the previous feed's ALREADY-PACKED lattices. Attestation
    proves those bytes are this run's own evidence, which is why the feed
    publishes them with no staleness label; the temperature that names their
    middle frame therefore has to come from this run's report too, not from the
    previous feed that merely stored them.

    Without this the branch was silent: deleting its ``_set_snapshot_peak_t``
    call left all 32 other tests in this file green (measured), so the field
    could go missing on the commonest rebuild path with a fully green suite —
    the same invisible-miss shape as the raw-name bug above.
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    raw = _tiny_report()                      # declares no peak temperature
    (reports / "2026-07-14-m01.json").write_text(json.dumps(raw), encoding="utf-8")
    previous_feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab"
    )
    assert "snapshot_peak_t" not in previous_feed["m01"]

    receipts = reports / "receipts"
    receipts.mkdir()
    receipt = _snapshotless_receipt(physics_feed._snapshot_digest(raw["snapshots"]))
    receipt["snapshot_peak_t"] = 2.5
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=previous_feed,
    )
    m01 = feed["m01"]
    assert feed["generated_from"] == "reports/receipts/run-2026-07-15-m01.json"
    # Retained by digest, not carried: this run's evidence, so no stale label...
    assert m01["snapshots"] == previous_feed["m01"]["snapshots"]
    assert "snapshots_source_report" not in m01
    # ...and the temperature naming the middle frame is this run's declaration,
    # which the previous feed could not have supplied.
    assert m01["snapshot_peak_t"] == 2.5


def test_snapshot_peak_t_is_omitted_when_the_report_declares_none(tmp_path):
    # Reports written before the engine declared the field must not gain an
    # invented temperature — the page keeps its own nearest-Tc fallback.
    reports, _ = _previous_feed_from_raw(tmp_path)
    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    assert "snapshot_peak_t" not in feed["m01"]


def test_stale_carry_brings_the_lattices_peak_temperature_not_this_runs(tmp_path):
    # The mislabel this field exists to close: when lattices carry forward, the
    # temperature that names them must come from the run that DREW them. This
    # run's own declaration describes frames nobody is looking at.
    reports = tmp_path / "reports"
    reports.mkdir()
    origin_report = _tiny_report()
    origin_report["snapshot_peak_t"] = 2.5
    (reports / "2026-07-14-m01.json").write_text(
        json.dumps(origin_report), encoding="utf-8"
    )
    previous_feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab"
    )
    assert previous_feed["m01"]["snapshot_peak_t"] == 2.5

    receipts = reports / "receipts"
    receipts.mkdir()
    receipt = _snapshotless_receipt("0" * 64)   # attests some OTHER run's lattices
    receipt["snapshot_peak_t"] = 3.5           # this run's frame, not the carried one
    (receipts / "run-2026-07-15-m01.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=tmp_path / "nolab", previous_feed=previous_feed,
    )
    m01 = feed["m01"]
    assert m01["snapshots_date"] == "2026-07-14"
    assert m01["snapshot_peak_t"] == 2.5


@pytest.mark.parametrize("bad", ["2.5", None, True, float("nan"), float("inf")])
def test_snapshot_peak_t_refuses_a_non_finite_or_non_numeric_declaration(tmp_path, bad):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = _tiny_report()
    report["snapshot_peak_t"] = bad
    (reports / "2026-08-30-m01.json").write_text(json.dumps(report), encoding="utf-8")

    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "nolab")
    assert "snapshot_peak_t" not in feed["m01"]


def test_turn_stamped_receipt_recovers_its_raw_report_from_lab_home(tmp_path):
    # The branch the production rebuild actually walks, and the one every test
    # above disables with ``lab_home=tmp_path / "nolab"``.
    #
    # ``render._write_report`` writes the full report to BOTH ``reports/`` and
    # ``~/.lab``, but ``reports/<date>-<slug>.json`` is gitignored — so on a fresh
    # clone, a `git clean`, or a worktree, ``~/.lab`` is the only copy left. The
    # turn-stamped name has to parse the same way down that path; a fix that only
    # worked against ``reports/`` would still leave a rebuilt feed serving stale
    # lattices under a fresh provenance line.
    import os

    reports = tmp_path / "reports"
    receipts = reports / "receipts"
    receipts.mkdir(parents=True)
    lab_home = tmp_path / "labhome"
    lab_home.mkdir()

    raw = _tiny_report()
    raw_path = lab_home / "2026-08-30-m01.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")

    receipt = _snapshotless_receipt(physics_feed._snapshot_digest(raw["snapshots"]))
    receipt_path = receipts / "run-2026-08-30-2100-m01.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    stamp = raw_path.stat().st_mtime
    os.utime(raw_path, (stamp, stamp))
    os.utime(receipt_path, (stamp + 60, stamp + 60))

    feed = physics_feed.build_feed(
        reports_dir=reports, lab_home=lab_home, previous_feed=None,
    )
    m01 = feed["m01"]
    assert feed["generated_from"] == "reports/receipts/run-2026-08-30-2100-m01.json"
    assert m01["chi"] == [0.05, 7.7, 0.5]        # the receipt's own numbers won
    assert set(m01["snapshots"]) == {"1.5", "2.5", "3.5"}
    assert m01["snapshot_L"] == 4
    # Attested from this run's own report → this run's evidence, unlabeled.
    assert "snapshots_source_report" not in m01
    assert "snapshots_date" not in m01
