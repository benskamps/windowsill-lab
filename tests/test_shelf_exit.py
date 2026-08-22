"""The shelf-exit contract (docs/shelf-exit-contract.md), enforced in code.

RULED 2026-08-19: >=2 sectors to promote; a promoted lead goes to ExoFOP as a
CTOI. These tests hold the register to the contract's three load-bearing
principles:

* the machine may refute, only a human may promote;
* an ungraded criterion is not a passed criterion;
* parking is not refutation and must never be reported as one.

The register is a PURE DERIVATION of the committed receipts plus the day —
it writes nothing, so the shelf's contents are a known quantity on any clone
(the DET-2 lesson applied to a new surface before it exists).
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from lab import shelf


# ---------------------------------------------------------------- fixtures --

#: A receipt whose permutation null certified itself — the default, because
#: real receipts carry this block and _significance refuses to read a FAP
#: without it (an uncontrolled null is not a null).
UNIFORMITY_OK = {"n_control": 25, "p_values": [0.5] * 25,
                 "ks_stat": 0.11, "pass": True}


def receipt(tmp_path, name, sector, generated_at, rows, uniformity="ok"):
    d = tmp_path / "hunts"
    d.mkdir(exist_ok=True)
    payload = {"experiment": "a05", "generated_at": generated_at,
               "sector": sector, "targets": rows}
    if uniformity == "ok":
        payload["uniformity"] = UNIFORMITY_OK
    elif uniformity is not None:
        payload["uniformity"] = uniformity
    (d / name).write_text(json.dumps(payload), encoding="utf-8")
    return d


def lead_row(tic=234518605, period=5.6724, depth=0.0489, depth_err=None,
             fap_iid=0.0039, fap_block=0.0039, physical="graded", **extra):
    """A row in the shape scripts/a05_hunt.py commits (subset the shelf reads)."""
    row = {
        "tic": tic, "disposition": "lead-awaiting-human-review",
        "period_days": period, "depth": depth, "sde": 8.4,
        "fap": {"B": 256, "schemes": {
            "iid": {"fap_empirical": fap_iid},
            "block": {"fap_empirical": fap_block, "block_days": 0.75},
        }},
        "disposition_evidence": {},
    }
    if depth_err is not None:
        row["depth_err"] = depth_err
    if physical == "graded":
        row["disposition_evidence"]["physical"] = {
            "verdict": None, "reason": None, "r_companion_jup": 1.1}
    elif physical == "no-radius":
        row["disposition_evidence"]["physical"] = {
            "verdict": None, "reason": "no-stellar-radius"}
    # physical == "absent": receipt predates the 2026-08-19 gate.
    row.update(extra)
    return row


def refuted_row(tic, disposition, period=5.6724):
    return {"tic": tic, "disposition": disposition, "period_days": period,
            "depth": 0.05, "sde": 7.0, "fap": {"schemes": {}},
            "disposition_evidence": {}}


TODAY = date(2026, 8, 22)


# --------------------------------------------------------------- collection --

def test_the_register_finds_every_lead_row_across_receipts(tmp_path):
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(tic=111)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00", [lead_row(tic=222)])
    entries = shelf.register(hunts, rulings=None, today=TODAY)
    assert [e["tic"] for e in entries] == [111, 222], \
        "ordered by first_seen then tic — the queue's age is its order"


def test_the_register_is_a_pure_function_of_receipts_and_the_day(tmp_path):
    hunts = receipt(tmp_path, "hunt-2026-08-14-s2.json", 2,
                    "2026-08-14T10:00:00", [lead_row()])
    a = shelf.register(hunts, rulings=None, today=TODAY)
    b = shelf.register(hunts, rulings=None, today=TODAY)
    assert a == b


# ------------------------------------------------- §4: the parking criteria --

def test_a_single_sector_lead_is_parked_on_persistence_not_refuted(tmp_path):
    hunts = receipt(tmp_path, "hunt-2026-08-14-s2.json", 2,
                    "2026-08-14T10:00:00", [lead_row()])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert e["state"] == "parked"
    assert e["state"] != "refuted", "parking is not refutation"
    assert any("persistence" in r and "1 sector" in r for r in e["parked_on"])
    assert e["promotable"] is False


def test_two_sectors_at_inconsistent_period_park_on_period_agreement(tmp_path):
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(period=5.6724, depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00",
                    [lead_row(period=6.9, depth_err=0.002)])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("period" in r for r in e["parked_on"])


def test_depth_consistency_ungradeable_is_not_passed(tmp_path):
    # Production receipts carry no depth uncertainty. Two clean sectors at a
    # consistent period must still PARK, naming the missing measurement —
    # an ungraded criterion is not a passed criterion (§2's rule, applied
    # to §4). This is the honest state of the real shelf until the pipeline
    # measures sigma_depth.
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row()])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00", [lead_row()])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("depth" in r and "ungrade" in r for r in e["parked_on"])


def test_depths_apart_beyond_three_sigma_park_the_star(tmp_path):
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth=0.0489, depth_err=0.0005)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00",
                    [lead_row(depth=0.0700, depth_err=0.0005)])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("depth" in r and "3" in r for r in e["parked_on"])


def test_significance_must_clear_alpha_in_both_schemes_everywhere(tmp_path):
    # One sector's block-shuffle FAP above alpha parks the star even though
    # the iid scheme is clean — "both shuffling schemes" means both.
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00",
                    [lead_row(depth_err=0.002, fap_block=0.04)])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("significance" in r or "FAP" in r for r in e["parked_on"])


def test_a_gate_that_fired_in_any_sector_parks_the_star(tmp_path):
    # A lead is a property of a star, not of a sector (§3): sector 3's
    # odd/even verdict stands against sector 2's clean look.
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(tic=333, depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00",
                    [refuted_row(333, "eclipsing-binary-odd-even")])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("eclipsing-binary-odd-even" in r and "sector 3" in r
               for r in e["parked_on"])


def test_a_star_catalogued_in_another_sector_is_not_novel(tmp_path):
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(tic=444, depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00", [refuted_row(444, "ctoi-known")])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("catalogued" in r and "ctoi-known" in r for r in e["parked_on"])


def test_physical_admissibility_ungraded_is_not_passed(tmp_path):
    # TIC 77044472, the one lead standing on 2026-08-19, has no TIC RADIUS —
    # the gate returns reason "no-stellar-radius" and the star cannot be
    # graded. Ungraded is parked, never promoted past.
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002, physical="no-radius")])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00",
                    [lead_row(depth_err=0.002, physical="no-radius")])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("admissib" in r and "no-stellar-radius" in r
               for r in e["parked_on"])


def test_a_receipt_predating_the_physical_gate_is_ungraded_not_passed(tmp_path):
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002, physical="absent")])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00",
                    [lead_row(depth_err=0.002, physical="absent")])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("admissib" in r for r in e["parked_on"])


def test_a_failed_uniformity_control_makes_the_faps_uninterpretable(tmp_path):
    """check_a05 gate 10's verdict, mirrored: a receipt whose own uniformity
    control failed cannot certify any FAP it graded. hunt-2026-08-18-s2-1000
    (D=0.265, the receipt that minted TIC 77044472's lead) is the live case —
    the shelf was reading FAPs a control had already disowned."""
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-18-s3.json", 3,
                    "2026-08-18T10:00:00", [lead_row(depth_err=0.002)],
                    uniformity={"n_control": 25, "p_values": [0.9] * 25,
                                "ks_stat": 0.265, "pass": False})
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("uninterpretable" in r and "uniformity control failed" in r
               and "0.265" in r for r in e["parked_on"]), e["parked_on"]
    assert e["state"] == "parked"
    assert e["state"] != "refuted", "uninterpretable is not negative"


def test_a_small_uniformity_ensemble_is_ungradeable_not_passed(tmp_path):
    """check_a05 refuses to grade the calibrator below A05_UNIFORMITY_MIN_N
    control points; a `pass: true` over three p-values is a claim the KS
    test cannot back, and the register must not accept it."""
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00", [lead_row(depth_err=0.002)],
                    uniformity={"n_control": 3, "p_values": [0.4, 0.5, 0.6],
                                "ks_stat": 0.1, "pass": True})
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("ungradeable" in r and "3 control p-value" in r
               for r in e["parked_on"]), e["parked_on"]


def test_a_receipt_without_a_uniformity_block_is_ungraded_not_passed(tmp_path):
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00", [lead_row(depth_err=0.002)],
                    uniformity=None)
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert any("uniformity control ungraded" in r for r in e["parked_on"])


# ------------------------------------------------- the machine never promotes --

def test_every_criterion_clear_is_promotable_awaiting_ben_never_promoted(tmp_path):
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002)])
    hunts = receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                    "2026-08-15T10:00:00", [lead_row(depth_err=0.002)])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert e["parked_on"] == []
    assert e["promotable"] is True
    assert e["state"] == "promotable-awaiting-ben"
    assert "promoted" not in e["state"].split("-"), \
        "only a human may promote; the machine's ceiling is a recommendation"


# ----------------------------------------------------------- §5: the clock --

def test_first_seen_is_the_earliest_receipt_and_the_clock_runs_from_it(tmp_path):
    receipt(tmp_path, "hunt-2026-08-15-s3.json", 3, "2026-08-15T10:00:00",
            [lead_row()])
    hunts = receipt(tmp_path, "hunt-2026-08-14-s2.json", 2,
                    "2026-08-14T10:00:00", [lead_row()])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert e["first_seen"] == "2026-08-14"
    assert e["days_on_shelf"] == 8
    assert e["clock"] == "fresh"


def test_a_lead_past_fourteen_days_is_surfaced_with_its_question(tmp_path):
    hunts = receipt(tmp_path, "hunt-2026-08-01-s2.json", 2,
                    "2026-08-01T10:00:00", [lead_row()])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert e["clock"] == "surfaced"
    assert e["question"], "a surfaced lead carries the one question it needs"


def test_a_lead_past_sixty_days_auto_parks_as_stale_unruled(tmp_path):
    hunts = receipt(tmp_path, "hunt-2026-06-01-s2.json", 2,
                    "2026-06-01T10:00:00", [lead_row()])
    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert e["clock"] == "stale-unruled"
    assert "no human ruling within the contract window" in e["stale_reason"]
    assert e["state"] != "refuted", \
        "auto-parking is a bandwidth admission, never a refutation"


# ------------------------------------------------------- rulings are human --

def test_a_human_ruling_is_terminal_and_the_machine_never_overrides_it(tmp_path):
    hunts = receipt(tmp_path, "hunt-2026-06-01-s2.json", 2,
                    "2026-06-01T10:00:00", [lead_row(tic=555)])
    rulings = tmp_path / "shelf-rulings.json"
    rulings.write_text(json.dumps([{
        "tic": 555, "ruling": "promoted", "date": "2026-08-20", "by": "ben",
        "why": "dossier reviewed; filed as CTOI"}]), encoding="utf-8")
    (e,) = shelf.register(hunts, rulings=rulings, today=TODAY)
    assert e["state"] == "promoted"
    assert e["ruled_by"] == "ben"
    # Terminal: the 60-day clock does not restyle a ruled lead as stale.
    assert e["clock"] == "ruled"


def test_a_ruling_the_contract_does_not_name_is_refused(tmp_path):
    hunts = receipt(tmp_path, "hunt-2026-08-14-s2.json", 2,
                    "2026-08-14T10:00:00", [lead_row(tic=666)])
    rulings = tmp_path / "shelf-rulings.json"
    rulings.write_text(json.dumps([{
        "tic": 666, "ruling": "confirmed-planet", "date": "2026-08-20",
        "by": "ben", "why": "..."}]), encoding="utf-8")
    with pytest.raises(ValueError, match="confirmed-planet"):
        shelf.register(hunts, rulings=rulings, today=TODAY)
