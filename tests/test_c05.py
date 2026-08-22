"""C05 — two independent algorithms must agree byte-for-byte, and the checker
must catch a receipt that lies about it.

The BBP digit-extraction identity teleports to a hex position of π; Machin's
1706 arctan formula walks there from digit zero on exact integers. The tests
pin the agreement on small, fast configurations, and pin the checker's teeth
on a full-shape fixture with one poisoned digit — a fabricated receipt must
fail on ARITHMETIC, not on a mood.
"""
from __future__ import annotations

import copy

from lab import c05
from lab.checks import check_c05


# The first 32 fractional hex digits of π, a public constant since long
# before this repo: 3.243F6A8885A308D313198A2E03707344…
KNOWN_32 = "243F6A8885A308D313198A2E03707344"


def test_machin_reproduces_the_known_prefix_exactly():
    assert c05.machin_pi_hex(32) == KNOWN_32
    # and it is stable under longer requests (no end-effect corruption)
    assert c05.machin_pi_hex(200)[:32] == KNOWN_32


def test_bbp_at_position_zero_reads_the_known_digits():
    assert c05.bbp_window(0) == KNOWN_32[:8]


def test_bbp_agrees_with_machin_across_a_small_expansion():
    ref = c05.machin_pi_hex(256)
    for d in (0, 1, 7, 63, 100, 200, 248):
        assert c05.bbp_window(d) == ref[d:d + 8], f"disagreement at {d}"


def test_adjacent_windows_agree_on_their_shared_digits():
    a, b = c05.bbp_window(120), c05.bbp_window(124)
    assert a[4:] == b[:4]


def test_the_seeded_sample_is_deterministic_and_edge_inclusive():
    p1 = c05.sampled_positions()
    p2 = c05.sampled_positions()
    assert p1 == p2
    assert p1[0] == 0 and p1[-1] == c05.CALIBRATION_HEX_DIGITS - c05.WINDOW
    assert len(p1) == c05.N_SAMPLED_POSITIONS


def test_a_diagnostic_run_reports_but_never_passes_the_public_gate():
    # C01's rule: smaller work is a diagnostic, not the calibration.
    result = c05.run_c05(n_digits=256, deep_position=512)
    assert result.all_windows_match, "the arithmetic itself must agree"
    assert result.calibration_passed is False
    report = c05.to_report(result)
    assert report["status"] == "null"
    assert "claim_boundary" in report


def _full_shape_receipt() -> dict:
    """A receipt in the FULL calibration identity, digits taken from the real
    arithmetic where cheap and from internally-consistent construction where
    the full run would be too slow for a unit test.

    Windows inside the checker's re-derived prefix carry REAL digits (the
    checker re-extracts them); windows beyond it and the deep block are
    internally consistent by construction, which is exactly the level the
    checker grades them at.
    """
    ref = c05.machin_pi_hex(2048)
    positions = c05.sampled_positions()
    windows = []
    for d in positions:
        if d <= 2048 - c05.WINDOW:
            digits = ref[d:d + c05.WINDOW]
        else:
            digits = format(d % (16 ** 8), "08X")   # consistent placeholder
        windows.append({"position": d, "bbp": digits, "reference": digits,
                        "match": True, "wall_seconds": 0.01})
    overlaps = []
    for d in positions[:6]:
        a = ref[d:d + 8]
        b = ref[d + 4:d + 12]
        overlaps.append({"position": d, "shared_from_d": a[4:],
                         "shared_from_d4": b[:4], "agree": a[4:] == b[:4]})
    import hashlib
    return {
        "experiment": "C05-bbp-digit-extraction",
        "status": "pass",
        "n_hex_digits": c05.CALIBRATION_HEX_DIGITS,
        "window": c05.WINDOW,
        "sample_seed": c05.SAMPLE_SEED,
        "reference_sha256": "0" * 64,
        "reference_prefix_text": ref,
        "reference_prefix_sha256": hashlib.sha256(ref.encode()).hexdigest(),
        "known_prefix_match": True,
        "windows": windows,
        "all_windows_match": True,
        "overlap_pairs": overlaps,
        "all_overlaps_agree": True,
        "deep": {"position": c05.DEEP_POSITION, "digits": "7AF5863E",
                 "adjacent_digits": "863E0000"[:8],
                 "adjacent_overlap_agree": True, "wall_seconds": 70.0},
        "calibration_passed": True,
        "wall_seconds": 200.0,
    }


def test_check_c05_passes_an_honest_full_shape_receipt():
    ok, why = check_c05(_full_shape_receipt())
    assert ok is True, why


def test_a_poisoned_receipt_fails_on_arithmetic_not_on_a_flag():
    receipt = _full_shape_receipt()
    # Alter ONE digit in one prefix-range window — and keep the receipt's own
    # flags proclaiming success, exactly what a fabrication would do.
    w = receipt["windows"][1]
    w["bbp"] = w["reference"] = ("0" if w["bbp"][0] != "0" else "1") + w["bbp"][1:]
    w["match"] = True
    ok, why = check_c05(receipt)
    assert ok is False
    assert "DISAGREE" in why or "DOES NOT match" in why


def test_a_receipt_with_a_lying_deep_flag_fails():
    receipt = _full_shape_receipt()
    receipt["deep"]["adjacent_digits"] = "00000000"   # overlap now false…
    receipt["deep"]["adjacent_overlap_agree"] = True  # …but the flag lies
    ok, _ = check_c05(receipt)
    assert ok is False


def test_identity_drift_is_refused_before_any_arithmetic():
    receipt = _full_shape_receipt()
    receipt["n_hex_digits"] = 64
    ok, why = check_c05(receipt)
    assert ok is False and "identity changed" in why


def test_check_c05_is_none_on_foreign_reports():
    ok, _ = check_c05({"experiment": "C01-arithmetic-calibration"})
    assert ok is None
