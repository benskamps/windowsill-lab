"""Portable public contract for the narrow M14 Nishimori-line release."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = "m14-nishimori-v1"
RELEASE_ROOT = ROOT / "release" / RELEASE_ID
ARCHIVE = RELEASE_ROOT / f"{RELEASE_ID}.zip"
ARCHIVE_CHECKSUM = ROOT / "release" / f"{RELEASE_ID}.sha256"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("m14_release_verifier", RELEASE_ROOT / "verify_release.py")
builder = _load_module("m14_release_builder", RELEASE_ROOT / "build_archive.py")


def _json(name: str):
    return json.loads((RELEASE_ROOT / name).read_text(encoding="utf-8"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_bundle(destination: Path) -> Path:
    def ignore(_directory, names):
        ignored = {ARCHIVE.name} if ARCHIVE.name in names else set()
        ignored.update(name for name in names if name == "__pycache__")
        return ignored

    return Path(shutil.copytree(RELEASE_ROOT, destination, ignore=ignore))


def test_strict_offline_verifier_regrades_the_checked_in_bundle():
    result = verifier.verify_bundle(RELEASE_ROOT / "receipt.json", strict=True)
    assert result["status"] == "pass"
    assert result["points_graded"] == 8
    assert result["gate_l"] == 24
    assert result["max_abs_deviation"] == pytest.approx(0.015110101699829181)
    assert result["energy_abs_tolerance"] == 0.05
    assert result["evidence_grade"] == "computed_statistical_agreement"
    assert result["simulation_rerun"] is False
    assert result["precise_mnp_location_claimed"] is False

    completed = subprocess.run(
        [sys.executable, "verify_release.py", "receipt.json", "--strict"],
        cwd=RELEASE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout
    assert "Simulation rerun: false" in completed.stdout
    assert "Precise multicritical-point claim: false" in completed.stdout

    no_strict = subprocess.run(
        [sys.executable, "verify_release.py", "receipt.json"],
        cwd=RELEASE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert no_strict.returncode != 0
    assert "strict verification is required" in no_strict.stdout


def test_receipt_is_bounded_and_does_not_invent_missing_run_provenance():
    receipt = _json("receipt.json")
    assert receipt["schema_version"] == "windowsill.verification-receipt.v1"
    assert receipt["release_id"] == RELEASE_ID
    assert receipt["classification"] == {
        "mode": "saved_aggregate_regrade",
        "evidence_grade": "computed_statistical_agreement",
        "novelty_claimed": False,
        "formal_proof_claimed": False,
        "precise_mnp_location_claimed": False,
        "independent_simulation_rerun": False,
        "raw_per_realization_samples_included": False,
        "peer_review_claimed": False,
    }
    assert receipt["claim"]["scope"] == "eight_saved_gate_l_energy_points"
    assert receipt["claim"]["gate_l"] == 24
    assert receipt["claim"]["point_count"] == 8
    assert receipt["claim"]["energy_abs_tolerance"] == 0.05
    assert receipt["decision"]["grade"] == "saved_aggregate_data_recalculation"
    assert receipt["source_history"]["first_commit_containing_report"] == (
        "d64c4c88cc92e960c522c86e6f3db7fbd63a508e"
    )
    assert receipt["source_history"]["first_commit_is_run_start_commit"] is False
    assert receipt["unrecorded_run_provenance"]
    assert set(receipt["unrecorded_run_provenance"].values()) == {None}

    limits = " ".join(receipt["limits"]).lower()
    for boundary in (
        "not a monte carlo rerun",
        "does not prove the identity",
        "precise multicritical nishimori point",
        "no raw per-realization samples",
        "not asserted to be the code checkout",
        "does not claim novelty",
    ):
        assert boundary in limits


def test_manifest_has_exact_complete_byte_and_digest_coverage():
    manifest = _json("manifest.json")
    assert manifest["schema_version"] == "windowsill.release-manifest.v1"
    assert manifest["release_id"] == RELEASE_ID
    assert manifest["verify_command"] == "python verify_release.py receipt.json --strict"
    paths = [item["path"] for item in manifest["files"]]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert {
        ".gitattributes",
        "LICENSE",
        "README.md",
        "build_archive.py",
        "evidence/2026-07-05-m14.json",
        "receipt.json",
        "verify_release.py",
    } == set(paths)

    for item in manifest["files"]:
        data = (RELEASE_ROOT / item["path"]).read_bytes()
        assert len(data) == item["bytes"], item["path"]
        assert _sha256(data) == item["sha256"], item["path"]

    receipt = _json("receipt.json")
    evidence = (RELEASE_ROOT / receipt["evidence"]["artifact"]).read_bytes()
    assert len(evidence) == receipt["evidence"]["packaged_bytes"] == 5351
    assert _sha256(evidence) == receipt["evidence"]["packaged_sha256"]
    assert _sha256(evidence[:-1]) == receipt["evidence"]["source_git_blob_sha256"]
    assert evidence.endswith(b"\n") and not evidence.endswith(b"\n\n")


def test_archive_is_byte_deterministic_complete_and_verifies_after_extraction(tmp_path):
    expected = builder.archive_bytes(RELEASE_ROOT, builder.manifest_bytes(RELEASE_ROOT))
    assert builder.archive_bytes(RELEASE_ROOT, builder.manifest_bytes(RELEASE_ROOT)) == expected
    assert ARCHIVE.read_bytes() == expected
    digest, name = ARCHIVE_CHECKSUM.read_text(encoding="ascii").strip().split("  ", 1)
    assert name == ARCHIVE.name
    assert digest == _sha256(expected)

    manifest = _json("manifest.json")
    expected_names = sorted(
        [f"{RELEASE_ID}/{item['path']}" for item in manifest["files"]]
        + [f"{RELEASE_ID}/manifest.json"]
    )
    with zipfile.ZipFile(ARCHIVE) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == expected_names
        assert archive.comment == b""
        for info in infos:
            assert not info.is_dir()
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED
            assert stat.S_IMODE(info.external_attr >> 16) == 0o644
            relative = info.filename.removeprefix(f"{RELEASE_ID}/")
            loose = RELEASE_ROOT / relative
            assert archive.read(info) == loose.read_bytes()
        archive.extractall(tmp_path)

    extracted = tmp_path / RELEASE_ID
    completed = subprocess.run(
        [sys.executable, "verify_release.py", "receipt.json", "--strict"],
        cwd=extracted,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout


def test_strict_verification_rejects_tampering_and_unlisted_payload(tmp_path):
    tampered = _copy_bundle(tmp_path / "tampered")
    evidence_path = tampered / "evidence" / "2026-07-05-m14.json"
    evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
    with pytest.raises(verifier.ReleaseVerificationError, match="manifest (byte count|digest) mismatch"):
        verifier.verify_bundle(tampered / "receipt.json", strict=True)

    extra = _copy_bundle(tmp_path / "extra")
    (extra / "undeclared.txt").write_text("not in the receipt\n", encoding="utf-8")
    with pytest.raises(verifier.ReleaseVerificationError, match="manifest coverage mismatch"):
        verifier.verify_bundle(extra / "receipt.json", strict=True)


def test_regrader_derives_the_target_instead_of_trusting_cached_pass_fields():
    report = _json("evidence/2026-07-05-m14.json")
    honest = verifier.regrade_report(report)
    assert honest["status"] == "pass"

    # The approximate MNP marker is context, not part of the energy gate.
    nongated_change = copy.deepcopy(report)
    nongated_change["mnp_order_p_half"] = 0.40
    assert verifier.regrade_report(nongated_change)["status"] == "pass"

    # Make the measured point fail, then falsify every cached target/pass summary
    # that a trusting verifier might echo. The independent derivation must reject it.
    fabricated = copy.deepcopy(report)
    fabricated["energy_by_L"]["24"][0] += 0.5
    point = fabricated["calibration_points"][0]
    point["energy"] += 0.5
    point["energy_exact"] = point["energy"]
    point["abs_dev"] = 0.0
    fabricated["energy_exact"][0] = point["energy"]
    fabricated["max_energy_dev"] = 0.0
    fabricated["energy_resolved"] = True
    with pytest.raises(verifier.ReleaseVerificationError):
        verifier.regrade_report(fabricated)

    wrong_type = copy.deepcopy(report)
    wrong_type["p_values"][0] = True
    with pytest.raises(verifier.ReleaseVerificationError, match="must be a number"):
        verifier.regrade_report(wrong_type)

    duplicate_p = copy.deepcopy(report)
    duplicate_p["p_values"][1] = duplicate_p["p_values"][0]
    with pytest.raises(verifier.ReleaseVerificationError):
        verifier.regrade_report(duplicate_p)
