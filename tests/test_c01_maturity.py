"""C01's public receipt must prove one fixed, non-trivial calibration."""

from __future__ import annotations

import copy
import hashlib

import pytest

from lab import c01, checks


def _valid_report(monkeypatch) -> dict:
    prefix = c01.fibonacci_bfile_segment(c01.CALIBRATION_TERMS)
    monkeypatch.setattr(
        c01,
        "_download",
        lambda *_args, **_kwargs: prefix + b"40 102334155\n",
    )
    return c01.to_report(c01.run_c01())


def test_c01_checker_rederives_valid_fixed_receipt(monkeypatch):
    report = _valid_report(monkeypatch)

    # These are report-owned conclusions, not checker inputs.
    report["bfile_exact_match"] = False
    report["mersenne_prime_verified"] = False
    report["calibration_passed"] = False
    report["status"] = "null"

    ok, detail = checks.check_c01(report)
    assert ok, detail
    assert "40 terms match byte-for-byte" in detail


def test_c01_nonstandard_short_run_is_diagnostic_not_a_calibration(monkeypatch):
    prefix = c01.fibonacci_bfile_segment(12)
    monkeypatch.setattr(c01, "_download", lambda *_args, **_kwargs: prefix)

    result = c01.run_c01(n_terms=12)

    assert result.bfile_exact_match is True
    assert result.calibration_passed is False
    ok, detail = checks.check_c01(c01.to_report(result))
    assert ok is False
    assert "identity changed" in detail


def test_c01_report_records_actual_noncanonical_source(monkeypatch):
    prefix = c01.fibonacci_bfile_segment(c01.CALIBRATION_TERMS)
    monkeypatch.setattr(c01, "_download", lambda *_args, **_kwargs: prefix)

    result = c01.run_c01(source_url="https://mirror.example/A000045.txt")
    report = c01.to_report(result)

    assert result.calibration_passed is False
    assert report["oeis_bfile_url"] == "https://mirror.example/A000045.txt"
    ok, detail = checks.check_c01(report)
    assert ok is False
    assert "identity changed" in detail


def test_c01_rejects_previous_empty_small_exponent_bypass(monkeypatch):
    report = _valid_report(monkeypatch)
    empty_hash = hashlib.sha256(b"").hexdigest()
    report.update(
        n_terms=0,
        source_bytes=0,
        source_prefix_text="",
        source_prefix_sha256=empty_hash,
        generated_prefix_sha256=empty_hash,
        mersenne_exponent=3,
        mersenne_candidate=7,
        lucas_lehmer_residue=0,
        bfile_exact_match=True,
        mersenne_prime_verified=True,
        calibration_passed=True,
    )

    ok, detail = checks.check_c01(report)
    assert ok is False
    assert "identity changed" in detail


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"oeis_sequence": "A000040"}, "identity changed"),
        ({"oeis_bfile_url": "https://example.test/b000045.txt"}, "identity changed"),
        ({"mersenne_exponent": 3, "mersenne_candidate": 7}, "identity changed"),
        ({"mersenne_exponent": 10**9}, "identity changed"),
        ({"mersenne_candidate": 2**31 - 2}, "calibration failed"),
        ({"lucas_lehmer_residue": 1}, "calibration failed"),
        ({"source_sha256": "g" * 64}, "malformed SHA-256"),
        ({"source_prefix_sha256": "0" * 64}, "does not match"),
        ({"generated_prefix_sha256": "0" * 64}, "does not match"),
        ({"source_bytes": 1}, "shorter than"),
    ],
)
def test_c01_rejects_tampered_identity_and_evidence(
    monkeypatch,
    changes,
    reason,
):
    report = _valid_report(monkeypatch)
    report.update(changes)
    # Forged honor-system claims must not rescue bad evidence.
    report["bfile_exact_match"] = True
    report["mersenne_prime_verified"] = True
    report["calibration_passed"] = True

    ok, detail = checks.check_c01(report)
    assert ok is False
    assert reason in detail


def test_c01_rejects_changed_prefix_even_when_attacker_rehashes_it(monkeypatch):
    report = copy.deepcopy(_valid_report(monkeypatch))
    forged = report["source_prefix_text"].replace("39 63245986", "39 63245987")
    forged_hash = hashlib.sha256(forged.encode("utf-8")).hexdigest()
    report["source_prefix_text"] = forged
    report["source_prefix_sha256"] = forged_hash
    report["generated_prefix_sha256"] = forged_hash
    report["bfile_exact_match"] = True

    ok, detail = checks.check_c01(report)
    assert ok is False
    assert "do not match" in detail
