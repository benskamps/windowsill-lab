"""Fail-closed, standard-library verifier for the M14 receipt bundle.

Usage from this directory or an extracted archive:

    python verify_release.py receipt.json --strict

Strict mode verifies complete manifest coverage, byte counts and SHA-256s, pins
the evidence to the first-committed report blob, enforces the receipt's bounded
non-claims, and independently regrades the saved aggregate measurements. It
does not import Windowsill Lab or rerun the Monte Carlo simulation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any


RELEASE_ID = "m14-nishimori-v1"
RECEIPT_SCHEMA = "windowsill.verification-receipt.v1"
MANIFEST_SCHEMA = "windowsill.release-manifest.v1"
VERIFY_COMMAND = "python verify_release.py receipt.json --strict"
ARCHIVE_NAME = f"{RELEASE_ID}.zip"
EVIDENCE_PATH = "evidence/2026-07-05-m14.json"
EVIDENCE_PACKAGED_BYTES = 5351
EVIDENCE_PACKAGED_SHA256 = "a6ed8abaccf25dfd3d1bacd0f519df17c9de19944e171557818e4f57dfc33677"
SOURCE_GIT_BLOB_BYTES = 5350
SOURCE_GIT_BLOB_SHA1 = "960284db926ed3ed1f74e47b866c4943d0492384"
SOURCE_GIT_BLOB_SHA256 = "b3c605d86af074fe66b6c846c763c01004f1660da30f4d971bfadbe7d907c7be"
FIRST_COMMIT = "d64c4c88cc92e960c522c86e6f3db7fbd63a508e"
ENERGY_ABS_TOLERANCE = 0.05
LINE_ABS_TOLERANCE = 0.01
EXPECTED_P = (0.04, 0.06, 0.08, 0.10, 0.1094, 0.12, 0.14, 0.16)
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class ReleaseVerificationError(ValueError):
    """The bundle cannot support its declared narrow claim."""


def _reject_constant(value: str) -> None:
    raise ReleaseVerificationError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseVerificationError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseVerificationError(f"cannot read valid UTF-8 JSON from {path.name}: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runtime_noise(relative: Path) -> bool:
    return "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}


def _manifest_path(root: Path, raw_name: Any) -> tuple[str, Path]:
    if not isinstance(raw_name, str) or not raw_name:
        raise ReleaseVerificationError("manifest path must be a non-empty string")
    if "\\" in raw_name:
        raise ReleaseVerificationError(f"manifest path must use POSIX separators: {raw_name!r}")
    relative = PurePosixPath(raw_name)
    if relative.is_absolute() or relative.as_posix() != raw_name:
        raise ReleaseVerificationError(f"manifest path is not canonical and relative: {raw_name!r}")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseVerificationError(f"manifest path traversal is forbidden: {raw_name!r}")
    path = root.joinpath(*relative.parts)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReleaseVerificationError(f"manifest symlink is forbidden: {raw_name}")
    return raw_name, path


def verify_manifest(root: Path) -> dict:
    manifest = load_json(root / "manifest.json")
    if not isinstance(manifest, dict):
        raise ReleaseVerificationError("manifest root must be an object")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ReleaseVerificationError("unsupported or missing manifest schema_version")
    if manifest.get("release_id") != RELEASE_ID:
        raise ReleaseVerificationError("manifest release_id mismatch")
    if manifest.get("verify_command") != VERIFY_COMMAND:
        raise ReleaseVerificationError("manifest verify command mismatch")
    excluded = manifest.get("excluded_from_file_table")
    if not isinstance(excluded, dict) or set(excluded) != {"manifest.json", ARCHIVE_NAME}:
        raise ReleaseVerificationError("manifest exclusions must name only itself and the archive")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ReleaseVerificationError("manifest files must be a non-empty array")
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    listed_order: list[str] = []
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise ReleaseVerificationError("each manifest file needs exactly path, bytes, and sha256")
        name, path = _manifest_path(root, item["path"])
        folded = name.casefold()
        if name in seen or folded in seen_casefold:
            raise ReleaseVerificationError(f"duplicate or case-colliding manifest path: {name}")
        seen.add(name)
        seen_casefold.add(folded)
        listed_order.append(name)
        byte_count = item["bytes"]
        digest = item["sha256"]
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
            raise ReleaseVerificationError(f"manifest byte count is invalid: {name}")
        if not isinstance(digest, str) or not HEX_64.fullmatch(digest):
            raise ReleaseVerificationError(f"manifest SHA-256 is invalid: {name}")
        if not path.is_file():
            raise ReleaseVerificationError(f"manifest file missing: {name}")
        data = path.read_bytes()
        if len(data) != byte_count:
            raise ReleaseVerificationError(f"manifest byte count mismatch: {name}")
        if sha256_bytes(data) != digest:
            raise ReleaseVerificationError(f"manifest digest mismatch: {name}")

    if listed_order != sorted(listed_order):
        raise ReleaseVerificationError("manifest paths must be lexicographically sorted")
    actual = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        name = relative.as_posix()
        if name in {"manifest.json", ARCHIVE_NAME} or _runtime_noise(relative):
            continue
        actual.add(name)
    if seen != actual:
        missing = sorted(actual - seen)
        absent = sorted(seen - actual)
        raise ReleaseVerificationError(
            f"manifest coverage mismatch (unlisted={missing}, missing={absent})"
        )
    return manifest


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReleaseVerificationError(f"{label} must be a number, not {type(value).__name__}")
    value = float(value)
    if not math.isfinite(value):
        raise ReleaseVerificationError(f"{label} must be finite")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReleaseVerificationError(f"{label} must be an integer")
    return value


def _list(value: Any, label: str, length: int) -> list:
    if not isinstance(value, list) or len(value) != length:
        raise ReleaseVerificationError(f"{label} must be an array of length {length}")
    return value


def _close(actual: float, expected: float, label: str, tolerance: float = 1e-12) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise ReleaseVerificationError(f"{label} mismatch: {actual!r} != {expected!r}")


def _numeric_row(mapping: Any, key: str, label: str, length: int, *, nonnegative: bool = False) -> list[float]:
    if not isinstance(mapping, dict) or key not in mapping:
        raise ReleaseVerificationError(f"{label} is missing row {key}")
    row = [_number(value, f"{label}[{key}][{index}]") for index, value in enumerate(_list(mapping[key], f"{label}[{key}]", length))]
    if nonnegative and any(value < 0.0 for value in row):
        raise ReleaseVerificationError(f"{label}[{key}] must be nonnegative")
    return row


def regrade_report(report: Any) -> dict:
    """Recompute the narrow energy gate from a decoded report object."""
    if not isinstance(report, dict):
        raise ReleaseVerificationError("evidence root must be an object")
    if report.get("experiment") != "M14-random-bond-nishimori":
        raise ReleaseVerificationError("evidence experiment tag is not M14")
    if _integer(report.get("gate_L"), "gate_L") != 24:
        raise ReleaseVerificationError("this release supports only gate_L=24")
    if report.get("L_values") != [12, 24]:
        raise ReleaseVerificationError("this release expects the persisted L_values [12, 24]")

    point_count = len(EXPECTED_P)
    ps = [_number(value, f"p_values[{index}]") for index, value in enumerate(_list(report.get("p_values"), "p_values", point_count))]
    for index, (actual, expected) in enumerate(zip(ps, EXPECTED_P)):
        _close(actual, expected, f"p_values[{index}]", 1e-15)
    if any(not 0.0 < p < 0.5 for p in ps) or any(a >= b for a, b in zip(ps, ps[1:])):
        raise ReleaseVerificationError("p_values must be finite, distinct, strictly increasing, and inside (0, 0.5)")

    temperatures = [_number(value, f"T_values[{index}]") for index, value in enumerate(_list(report.get("T_values"), "T_values", point_count))]
    if any(value <= 0.0 for value in temperatures):
        raise ReleaseVerificationError("all temperatures must be positive")
    energies = _numeric_row(report.get("energy_by_L"), "24", "energy_by_L", point_count)
    errors = _numeric_row(report.get("energy_err_by_L"), "24", "energy_err_by_L", point_count, nonnegative=True)
    _numeric_row(report.get("energy_by_L"), "12", "energy_by_L", point_count)
    _numeric_row(report.get("energy_err_by_L"), "12", "energy_err_by_L", point_count, nonnegative=True)
    for key in ("12", "24"):
        magnitudes = _numeric_row(report.get("abs_mag_by_L"), key, "abs_mag_by_L", point_count)
        if any(not 0.0 <= value <= 1.0 for value in magnitudes):
            raise ReleaseVerificationError(f"abs_mag_by_L[{key}] must stay inside [0, 1]")
        _numeric_row(report.get("binder_by_L"), key, "binder_by_L", point_count)

    stored_targets = [_number(value, f"energy_exact[{index}]") for index, value in enumerate(_list(report.get("energy_exact"), "energy_exact", point_count))]
    points = _list(report.get("calibration_points"), "calibration_points", point_count)
    deviations: list[float] = []
    line_residuals: list[float] = []
    for index, (p, temperature, energy, error, stored_target, point) in enumerate(
        zip(ps, temperatures, energies, errors, stored_targets, points)
    ):
        if not isinstance(point, dict):
            raise ReleaseVerificationError(f"calibration_points[{index}] must be an object")
        point_p = _number(point.get("p"), f"calibration_points[{index}].p")
        point_t = _number(point.get("T"), f"calibration_points[{index}].T")
        point_energy = _number(point.get("energy"), f"calibration_points[{index}].energy")
        point_error = _number(point.get("energy_err"), f"calibration_points[{index}].energy_err")
        point_target = _number(point.get("energy_exact"), f"calibration_points[{index}].energy_exact")
        point_deviation = _number(point.get("abs_dev"), f"calibration_points[{index}].abs_dev")
        if point_error < 0.0:
            raise ReleaseVerificationError(f"calibration_points[{index}].energy_err must be nonnegative")
        for actual, expected, label in (
            (point_p, p, "p"), (point_t, temperature, "T"),
            (point_energy, energy, "energy"), (point_error, error, "energy_err"),
        ):
            _close(actual, expected, f"calibration_points[{index}].{label}")

        expected_temperature = 2.0 / math.log((1.0 - p) / p)
        _close(temperature, expected_temperature, f"T_values[{index}]", LINE_ABS_TOLERANCE)
        line_residual = abs(math.tanh(1.0 / temperature) - (1.0 - 2.0 * p))
        if line_residual > LINE_ABS_TOLERANCE:
            raise ReleaseVerificationError(f"point {index} is off the Nishimori line")
        target_from_t = -2.0 * math.tanh(1.0 / temperature)
        target_from_p = -2.0 * (1.0 - 2.0 * p)
        _close(target_from_t, target_from_p, f"point {index} equivalent exact targets", 2.0 * LINE_ABS_TOLERANCE)
        _close(stored_target, target_from_t, f"energy_exact[{index}]")
        _close(point_target, target_from_t, f"calibration_points[{index}].energy_exact")
        deviation = abs(energy - target_from_t)
        _close(point_deviation, deviation, f"calibration_points[{index}].abs_dev")
        if deviation > ENERGY_ABS_TOLERANCE:
            raise ReleaseVerificationError(
                f"point {index} energy deviation {deviation:.17g} exceeds {ENERGY_ABS_TOLERANCE}"
            )
        deviations.append(deviation)
        line_residuals.append(line_residual)

    measured_max = max(deviations)
    recorded_max = _number(report.get("max_energy_dev"), "max_energy_dev")
    _close(recorded_max, measured_max, "max_energy_dev")
    if report.get("on_nishimori_line") is not True:
        raise ReleaseVerificationError("cached on_nishimori_line field disagrees with recomputation")
    if report.get("energy_resolved") is not True:
        raise ReleaseVerificationError("cached energy_resolved field disagrees with recomputation")
    if report.get("binder_crossing_p") is not None:
        raise ReleaseVerificationError("the persisted two-size Binder crossing must remain unresolved")

    config = report.get("config")
    if not isinstance(config, dict):
        raise ReleaseVerificationError("config must be an object")
    expected_config = {
        "p_values": list(EXPECTED_P), "L_values": [12, 24], "gate_L": 24,
        "n_realizations": 64, "n_sweeps": 10000, "n_burnin": 4000,
        "seed": 42, "device": "cpu", "model": "random-bond-ising-2d",
        "disorder": "bimodal-pm-J", "line": "nishimori",
        "updater": "checkerboard-metropolis",
    }
    if config != expected_config:
        raise ReleaseVerificationError("recorded run config differs from the bounded receipt")
    if _integer(report.get("n_realizations"), "n_realizations") != 64:
        raise ReleaseVerificationError("n_realizations differs from the bounded receipt")

    return {
        "status": "pass",
        "points_graded": point_count,
        "gate_l": 24,
        "max_abs_deviation": measured_max,
        "max_line_residual": max(line_residuals),
        "energy_abs_tolerance": ENERGY_ABS_TOLERANCE,
        "line_abs_tolerance": LINE_ABS_TOLERANCE,
    }


def verify_receipt_contract(receipt: Any) -> None:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ReleaseVerificationError("unsupported or missing receipt schema_version")
    if receipt.get("release_id") != RELEASE_ID:
        raise ReleaseVerificationError("receipt release_id mismatch")
    classification = receipt.get("classification")
    expected_false = (
        "novelty_claimed", "formal_proof_claimed", "precise_mnp_location_claimed",
        "independent_simulation_rerun", "raw_per_realization_samples_included",
        "peer_review_claimed",
    )
    if not isinstance(classification, dict) or classification.get("mode") != "saved_aggregate_regrade":
        raise ReleaseVerificationError("receipt must be classified as a saved aggregate regrade")
    if classification.get("evidence_grade") != "computed_statistical_agreement":
        raise ReleaseVerificationError("receipt evidence grade must distinguish statistical measurements")
    if any(classification.get(field) is not False for field in expected_false):
        raise ReleaseVerificationError("receipt must not claim novelty, proof, precise MNP, rerun, raw samples, or peer review")

    claim = receipt.get("claim")
    if not isinstance(claim, dict) or claim.get("scope") != "eight_saved_gate_l_energy_points":
        raise ReleaseVerificationError("receipt claim scope is not the supported eight-point gate")
    expected_claim = {
        "gate_l": 24, "point_count": 8, "p_min": 0.04, "p_max": 0.16,
        "target": "-2*tanh(1/T)", "energy_abs_tolerance": ENERGY_ABS_TOLERANCE,
        "nishimori_line_abs_tolerance": LINE_ABS_TOLERANCE,
    }
    for field, expected in expected_claim.items():
        if claim.get(field) != expected:
            raise ReleaseVerificationError(f"receipt claim field {field} changed")

    evidence = receipt.get("evidence")
    expected_evidence = {
        "artifact": EVIDENCE_PATH,
        "packaged_bytes": EVIDENCE_PACKAGED_BYTES,
        "packaged_sha256": EVIDENCE_PACKAGED_SHA256,
        "source_git_blob_bytes": SOURCE_GIT_BLOB_BYTES,
        "source_git_blob_sha1": SOURCE_GIT_BLOB_SHA1,
        "source_git_blob_sha256": SOURCE_GIT_BLOB_SHA256,
    }
    if not isinstance(evidence, dict):
        raise ReleaseVerificationError("receipt evidence must be an object")
    for field, expected in expected_evidence.items():
        if evidence.get(field) != expected:
            raise ReleaseVerificationError(f"receipt evidence field {field} changed")

    history = receipt.get("source_history")
    if not isinstance(history, dict) or history.get("first_commit_containing_report") != FIRST_COMMIT:
        raise ReleaseVerificationError("receipt lost its first-commit archival anchor")
    if history.get("first_commit_is_run_start_commit") is not False:
        raise ReleaseVerificationError("first report commit must not be presented as run-start provenance")
    unknown = receipt.get("unrecorded_run_provenance")
    if not isinstance(unknown, dict) or not unknown:
        raise ReleaseVerificationError("receipt must enumerate absent run provenance")
    if any(value is not None for value in unknown.values()):
        raise ReleaseVerificationError("unrecorded run provenance must remain explicitly null")
    reproduce = receipt.get("reproduce")
    if not isinstance(reproduce, dict) or reproduce.get("verify_bundle") != VERIFY_COMMAND:
        raise ReleaseVerificationError("receipt strict verification command mismatch")


def verify_bundle(receipt_path: str | Path = "receipt.json", *, strict: bool = True) -> dict:
    receipt_path = Path(receipt_path).resolve()
    root = receipt_path.parent
    if receipt_path.name != "receipt.json" or not receipt_path.is_file():
        raise ReleaseVerificationError("receipt path must name an existing receipt.json")
    if not strict:
        raise ReleaseVerificationError("public bundle verification is fail-closed and requires strict=True")
    manifest = verify_manifest(root)
    receipt = load_json(receipt_path)
    verify_receipt_contract(receipt)

    evidence_path = root / EVIDENCE_PATH
    evidence_bytes = evidence_path.read_bytes()
    if len(evidence_bytes) != EVIDENCE_PACKAGED_BYTES or sha256_bytes(evidence_bytes) != EVIDENCE_PACKAGED_SHA256:
        raise ReleaseVerificationError("bundled evidence does not match the pinned packaged report")
    if not evidence_bytes.endswith(b"\n") or evidence_bytes.endswith(b"\n\n"):
        raise ReleaseVerificationError("packaged evidence must add exactly one terminal LF")
    source_blob = evidence_bytes[:-1]
    if len(source_blob) != SOURCE_GIT_BLOB_BYTES or sha256_bytes(source_blob) != SOURCE_GIT_BLOB_SHA256:
        raise ReleaseVerificationError("packaged evidence does not reconstruct the pinned committed Git blob")

    measured = regrade_report(load_json(evidence_path))
    decision = receipt.get("decision", {})
    if decision.get("status") != measured["status"] or decision.get("points_graded") != measured["points_graded"]:
        raise ReleaseVerificationError("receipt decision disagrees with independently measured evidence")
    _close(
        _number(decision.get("measured_max_abs_deviation"), "decision.measured_max_abs_deviation"),
        measured["max_abs_deviation"],
        "decision.measured_max_abs_deviation",
    )
    return {
        **measured,
        "release_id": RELEASE_ID,
        "manifest_files": len(manifest["files"]),
        "evidence_grade": "computed_statistical_agreement",
        "precise_mnp_location_claimed": False,
        "simulation_rerun": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the bounded Windowsill M14 receipt")
    parser.add_argument("receipt", nargs="?", default="receipt.json")
    parser.add_argument("--strict", action="store_true", help="required: verify all bytes, provenance boundaries, and measurements")
    args = parser.parse_args()
    if not args.strict:
        print("FAIL - strict verification is required; rerun with --strict")
        return 1
    try:
        result = verify_bundle(args.receipt, strict=True)
    except Exception as exc:
        print(f"FAIL - {exc}")
        return 1

    print("PASS - saved M14 aggregate measurements regraded")
    print(f"Points: {result['points_graded']} at gate L={result['gate_l']}")
    print(f"Max |E measured - E exact|: {result['max_abs_deviation']:.17g} <= {result['energy_abs_tolerance']}")
    print("Exact target: -2*tanh(1/T); measurement grade: statistical agreement")
    print("Simulation rerun: false")
    print("Precise multicritical-point claim: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
