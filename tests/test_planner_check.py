"""The planner decision check (`checks.check_planned_decision`) — can a
scheduled receipt's compact `planned` block be audited after the fact?

The planner ships its decision inside the receipt it produces (chosen + reason
+ top-3 scoreboard). This check re-derives what history still permits: the
argmax of the block's own scoreboard, the ledger-refutable class claims
(never-run vs a receipt that exists), the staleness/repeat arithmetic as a
ceiling, and the repeat hard cap — against the receipts ledger AS IT WAS,
records strictly older than the receipt's generated_at. It deliberately does
NOT re-derive the status classification (historical MILESTONES.md state is
gone) and the docstring says so.

Verdict discipline under test: no block → vacuous pass; malformed block →
None (unreadable, never conflated with fabrication); arithmetic that does not
reconcile → False (the fabrication verdict).

Torch-free: plan_turn is pure and the receipts here are dict fixtures.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import lab.checks as checks
import lab.receipt as receipt_mod
from lab import curriculum
from lab.checks import audit_planned_decisions, check_planned_decision
from lab.curriculum import plan_turn

#: A fixed plan-time "now" so every score re-derives identically forever.
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)

#: The open-frontier id with a real runner outside ROTATION — same guarded
#: fixture shape as tests/test_planner.py.
FRONTIER_ID = "M12"
assert FRONTIER_ID in curriculum.RUNNERS, f"{FRONTIER_ID} lost its runner"
assert FRONTIER_ID not in curriculum.ROTATION, f"{FRONTIER_ID} joined ROTATION"


@pytest.fixture(autouse=True)
def _no_camera(monkeypatch):
    """Pin the I01 hardware gate CLOSED so scores never depend on the host."""
    monkeypatch.delenv("WINDOWSILL_I01_FRAMES", raising=False)
    monkeypatch.delenv("LAB_I01_CAMERA", raising=False)


def _stamp(dt):
    return dt.isoformat()


def _scheduled_receipt(decision, generated_at):
    """A receipt produced the way the scheduler really produces one: the
    planned-block seam armed around build_public_receipt."""
    receipt_mod.set_planned_decision(decision)
    try:
        receipt = receipt_mod.build_public_receipt(
            {"experiment": "x", "generated_at": _stamp(generated_at)})
    finally:
        receipt_mod.clear_planned_decision()
    # Round-trip through JSON: the check reads committed files, not live dicts.
    return json.loads(json.dumps(receipt))


def _four_class_fixture(monkeypatch):
    """One candidate of each class on the board (the test_planner shape):
    frontier 8.0, never-run 5.0, null-retry 3.0, canary off the top-3."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04", "M05"))
    old = _stamp(NOW - timedelta(days=30))
    records = [(old, "M04"), (old, "M05")]
    statuses = {FRONTIER_ID: "open", "M03": "verified",
                "M04": "null", "M05": "verified"}
    _pick, decision = plan_turn(records, statuses, now=NOW)
    generated_at = NOW + timedelta(minutes=5)          # the run took 5 minutes
    receipt = _scheduled_receipt(decision, generated_at)
    return receipt, records, generated_at


# ── the honest path, and the strictly-older boundary ─────────────────────────

def test_honest_planned_block_reconciles(monkeypatch):
    """A block written by the real pipeline passes against the same ledger —
    including the receipt's OWN record (stamp == generated_at), a record from
    the future, and an unparseable stamp, all of which the strictly-older
    boundary must exclude."""
    receipt, records, generated_at = _four_class_fixture(monkeypatch)
    ledger = records + [
        (_stamp(generated_at), FRONTIER_ID),           # this very receipt
        (_stamp(generated_at + timedelta(hours=6)), "M09"),   # the future
        ("not-a-stamp", "M02"),                        # unplaceable
    ]
    ok, detail = check_planned_decision(receipt, ledger)
    assert ok is True
    assert "argmax" in detail and "strictly-older" in detail


def test_boundary_is_load_bearing_one_second_earlier_flips_the_verdict(
        monkeypatch):
    """The SAME extra record graded on the other side of the boundary changes
    the answer: an M12 receipt one second BEFORE generated_at makes M12 the
    re-derived ledger head (repeats=1), halving its ceiling to 4.0 — the
    block's honest 8.0 then reads as irreconcilable. At exactly generated_at
    (the previous test) it is excluded and the block passes. That is the
    boundary doing its job, documented in the docstring."""
    receipt, records, generated_at = _four_class_fixture(monkeypatch)
    ledger = records + [
        (_stamp(generated_at - timedelta(seconds=1)), FRONTIER_ID)]
    ok, detail = check_planned_decision(receipt, ledger)
    assert ok is False
    assert "ceiling" in detail


# ── the fabrication verdicts ─────────────────────────────────────────────────

def test_hand_edited_chosen_is_false(monkeypatch):
    """A chosen that is not the argmax of its own scoreboard is the primal
    fabrication: the receipt claims a decision its own numbers refuse."""
    receipt, records, _gen = _four_class_fixture(monkeypatch)
    planned = receipt["public_receipt"]["planned"]
    assert planned["chosen"] == FRONTIER_ID
    planned["chosen"] = planned["scoreboard"][1]["mid"]
    ok, detail = check_planned_decision(receipt, records)
    assert ok is False
    assert "not the argmax" in detail


def test_corrupted_canary_arithmetic_is_false(monkeypatch):
    """A verified-canary score inflated past its re-derived staleness ceiling
    (base 1.0 × log2(1 + days/7) × repeat decay, cost only divides) is
    arithmetic that cannot reconcile."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04", "M05"))
    records = [
        (_stamp(NOW - timedelta(days=30)), "M04"),
        (_stamp(NOW - timedelta(days=1)), "M05"),
    ]
    statuses = {"M03": "verified", "M04": "verified", "M05": "verified"}
    _pick, decision = plan_turn(records, statuses, now=NOW)
    receipt = _scheduled_receipt(decision, NOW + timedelta(minutes=5))
    planned = receipt["public_receipt"]["planned"]
    entry = next(e for e in planned["scoreboard"] if e["mid"] == "M05")
    assert entry["cls"] == "verified-canary"
    assert entry["score"] < 0.2                    # ~1 day stale, head-decayed
    entry["score"] = 2.0                           # keeps descending order
    ok, detail = check_planned_decision(receipt, records)
    assert ok is False
    assert "M05" in detail and "ceiling" in detail


def test_never_run_claim_refuted_by_the_ledger_is_false(monkeypatch):
    """`never-run` is a ledger-refutable claim: an older receipt for the same
    mid proves the class was fabricated."""
    receipt, records, _gen = _four_class_fixture(monkeypatch)
    board = receipt["public_receipt"]["planned"]["scoreboard"]
    assert any(e["mid"] == "M03" and e["cls"] == "never-run" for e in board)
    ledger = records + [(_stamp(NOW - timedelta(days=60)), "M03")]
    ok, detail = check_planned_decision(receipt, ledger)
    assert ok is False
    assert "claims never-run" in detail


def test_canary_claim_without_any_older_receipt_is_false(monkeypatch):
    """The mirror refutation: verified-canary / null-retry both require a
    prior receipt under v1 law; a ledger holding none proves the class wrong."""
    receipt, records, _gen = _four_class_fixture(monkeypatch)
    ok, detail = check_planned_decision(receipt, [])   # empty older ledger
    assert ok is False
    assert "null-retry" in detail and "no" in detail


# ── the repeat law survives its own audit ────────────────────────────────────

def _capped_fixture(monkeypatch):
    """The hard-cap shape from test_planner: three consecutive frontier
    receipts at the head, one barely-stale canary — the cap fires and the
    board carries a `(repeat-capped)` zero-score entry."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03",))
    records = [
        (_stamp(NOW - timedelta(days=3)), "M03"),
        (_stamp(NOW - timedelta(hours=18)), FRONTIER_ID),
        (_stamp(NOW - timedelta(hours=12)), FRONTIER_ID),
        (_stamp(NOW - timedelta(hours=6)), FRONTIER_ID),
    ]
    statuses = {FRONTIER_ID: "open", "M03": "verified"}
    pick, decision = plan_turn(records, statuses, now=NOW)
    assert pick == "M03"
    receipt = _scheduled_receipt(decision, NOW + timedelta(minutes=5))
    return receipt, records


def test_honest_repeat_capped_block_reconciles(monkeypatch):
    receipt, records = _capped_fixture(monkeypatch)
    board = receipt["public_receipt"]["planned"]["scoreboard"]
    capped = next(e for e in board if e["mid"] == FRONTIER_ID)
    assert "repeat-capped" in capped["cls"] and capped["score"] == 0.0
    ok, _detail = check_planned_decision(receipt, records)
    assert ok is True


def test_erasing_the_repeat_cap_is_false(monkeypatch):
    """The fabrication the cap exists to make impossible: rewrite the capped
    frontier entry as an uncapped winner. Every other number is made
    self-consistent (sorted board, chosen = argmax, score exactly at the
    decayed ceiling 8 × 2^-3 = 1.0) so ONLY the re-derived repeat law can
    catch it — and must."""
    receipt, records = _capped_fixture(monkeypatch)
    planned = receipt["public_receipt"]["planned"]
    canary = next(e for e in planned["scoreboard"] if e["mid"] == "M03")
    planned["scoreboard"] = [
        {"mid": FRONTIER_ID, "cls": "open-frontier", "score": 1.0},
        canary,
    ]
    planned["chosen"] = FRONTIER_ID
    ok, detail = check_planned_decision(receipt, records)
    assert ok is False
    assert "repeat law erased" in detail


def test_claiming_the_cap_without_cap_worthy_repeats_is_false(monkeypatch):
    """The other direction: a block that claims `(repeat-capped)` must sit at
    ≥ REPEAT_HARD_CAP re-derived consecutive repeats. Handing the check a
    ledger with only one head receipt exposes the claim."""
    receipt, records = _capped_fixture(monkeypatch)
    thin = [records[0], records[-1]]                   # one M12 at the head
    ok, detail = check_planned_decision(receipt, thin)
    assert ok is False
    assert "claims the repeat cap at 1" in detail


# ── vacuity, unreadability, and the version boundary ─────────────────────────

def test_missing_planned_block_passes_vacuously():
    """Manual runs and historical receipts carry no planned block and owe
    nothing — with or without public_receipt metadata."""
    bare = {"experiment": "M01-ising-verification", "T": [1.0], "chi": [1.0]}
    ok, detail = check_planned_decision(bare, [])
    assert ok is True and "vacuous" in detail
    receipt = receipt_mod.build_public_receipt(bare)   # seam unarmed
    ok, detail = check_planned_decision(receipt, [])
    assert ok is True and "vacuous" in detail


@pytest.mark.parametrize("mangle", [
    lambda p: "not-an-object",                          # block not a dict
    lambda p: {k: v for k, v in p.items() if k != "planner"},
    lambda p: {k: v for k, v in p.items() if k != "chosen"},
    lambda p: {**p, "scoreboard": []},
    lambda p: {**p, "scoreboard": [{"mid": "M03", "cls": "never-run",
                                    "score": "5.0"}]},  # score not a number
])
def test_malformed_planned_block_is_none_not_false(monkeypatch, mangle):
    """Unreadable evidence is named None — never converted into the
    fabrication verdict."""
    receipt, records, _gen = _four_class_fixture(monkeypatch)
    receipt["public_receipt"]["planned"] = mangle(
        receipt["public_receipt"]["planned"])
    ok, detail = check_planned_decision(receipt, records)
    assert ok is None
    assert "unreadable" in detail


def test_planned_block_without_generated_at_is_none(monkeypatch):
    """No parseable generated_at → no strictly-older boundary → not graded."""
    receipt, records, _gen = _four_class_fixture(monkeypatch)
    del receipt["generated_at"]
    ok, detail = check_planned_decision(receipt, records)
    assert ok is None
    assert "generated_at" in detail


def test_foreign_planner_version_is_a_vacuous_boundary_not_a_verdict(
        monkeypatch):
    """PLANNER_VERSION exists so old decisions are never re-derived against
    new law: a block stamped with a different version passes vacuously with
    the boundary named — neither False nor None."""
    receipt, records, _gen = _four_class_fixture(monkeypatch)
    receipt["public_receipt"]["planned"]["planner"] = "v0"
    ok, detail = check_planned_decision(receipt, records)
    assert ok is True
    assert "PLANNER_VERSION boundary" in detail


def test_vocabulary_covers_everything_plan_turn_emits(monkeypatch):
    """The audit's class vocabulary must cover the planner's: every cls the
    real plan_turn can stamp into a block is gradable (base map + the
    staleness-derived verified-canary + the cap suffix), and the hunt class
    binds to the hunt candidate alone."""
    emitted = {"open-frontier", "never-run", "null-retry", "verified-canary",
               "hunt"}
    assert set(checks._PLANNED_BASE_VALUE) | {"verified-canary"} == emitted
    # A hunt entry is graded at its ceiling and never repeat-decayed…
    monkeypatch.setattr(curriculum, "ROTATION", ("M03",))
    records = [(_stamp(NOW - timedelta(hours=6)), "M03")]
    _pick, decision = plan_turn(
        records, {"M03": "verified"}, now=NOW,
        hunt_status={"remaining_targets": 500})
    receipt = _scheduled_receipt(decision, NOW + timedelta(minutes=5))
    ok, _detail = check_planned_decision(receipt, records)
    assert ok is True
    # …and 'hunt' on any other mid is a vocabulary violation.
    planned = receipt["public_receipt"]["planned"]
    hunt = next(e for e in planned["scoreboard"]
                if e["mid"] == curriculum.HUNT_CANDIDATE)
    hunt["mid"] = "M03"
    planned["chosen"] = "M03"
    ok, detail = check_planned_decision(receipt, records)
    assert ok is False
    assert "hunt" in detail


# ── the verify() wiring: one cross-cutting row, only when blocks exist ───────

def _verify_fixture(tmp_path, monkeypatch):
    """An isolated estate for verify(): empty milestones (no per-milestone
    rows), a receipts ledger the planner audit reads through checks.REPORTS_DIR."""
    reports = tmp_path / "reports"
    receipts = reports / "receipts"
    lab_home = tmp_path / "lab-home"
    receipts.mkdir(parents=True)
    lab_home.mkdir()
    milestones = tmp_path / "MILESTONES.md"
    milestones.write_text("no milestones here\n", encoding="utf-8")
    monkeypatch.setattr(checks, "REPORTS_DIR", reports)
    monkeypatch.setattr(checks, "LAB_HOME", lab_home)
    monkeypatch.setattr(checks, "MILESTONES_MD", milestones)
    return receipts


def _planned_receipt_json(chosen="M03", score=5.0):
    return {
        "experiment": "M03-data-collapse",
        "generated_at": "2026-08-14T12:30:00+00:00",
        "public_receipt": {
            "schema": receipt_mod.RECEIPT_SCHEMA,
            "planned": {
                "planner": curriculum.PLANNER_VERSION,
                "chosen": chosen,
                "reason": "planner v1: test fixture",
                "scoreboard": [
                    {"mid": "M03", "cls": "never-run", "score": score},
                    {"mid": "M04", "cls": "never-run", "score": 5.0},
                ],
            },
        },
    }


def test_verify_emits_one_planned_row_when_blocks_exist(tmp_path, monkeypatch):
    """A ledger holding one older manual receipt and one scheduled receipt
    with an honest planned block → exactly one aggregate PLANNED pass row.
    The scheduled receipt's OWN ledger record (stamp == generated_at) sits on
    the boundary and must not refute its never-run claim."""
    receipts = _verify_fixture(tmp_path, monkeypatch)
    (receipts / "run-2026-06-15-m01.json").write_text(json.dumps({
        "experiment": "M01-ising-verification",
        "generated_at": "2026-06-15T00:00:00+00:00",
    }), encoding="utf-8")
    (receipts / "run-2026-08-14-1230-m03.json").write_text(
        json.dumps(_planned_receipt_json()), encoding="utf-8")
    results = checks.verify()
    assert results == [{
        "id": "PLANNED", "status": "pass",
        "detail": "1 planned block(s) re-derive against the strictly-older "
                  "receipts ledger",
    }]


def test_verify_planned_row_fails_on_a_fabricated_block(tmp_path, monkeypatch):
    receipts = _verify_fixture(tmp_path, monkeypatch)
    (receipts / "run-2026-08-14-1230-m03.json").write_text(
        json.dumps(_planned_receipt_json(chosen="M09")), encoding="utf-8")
    rows = {r["id"]: r for r in checks.verify()}
    assert rows["PLANNED"]["status"] == "fail"
    assert "not reconcile" in rows["PLANNED"]["detail"]


def test_verify_planned_row_names_unreadable_blocks(tmp_path, monkeypatch):
    """A structurally scrambled block blocks the gate under its own name —
    `unreadable`, distinct from the fabrication `fail`."""
    receipts = _verify_fixture(tmp_path, monkeypatch)
    rec = _planned_receipt_json()
    del rec["public_receipt"]["planned"]["chosen"]
    (receipts / "run-2026-08-14-1230-m03.json").write_text(
        json.dumps(rec), encoding="utf-8")
    rows = {r["id"]: r for r in checks.verify()}
    assert rows["PLANNED"]["status"] == "unreadable"


def test_verify_emits_no_planned_row_without_blocks(tmp_path, monkeypatch):
    """Historical receipts are never forced to carry planned blocks: a ledger
    with none produces NO row — vacuous by absence, not an all-clear badge."""
    receipts = _verify_fixture(tmp_path, monkeypatch)
    (receipts / "run-2026-06-15-m01.json").write_text(json.dumps({
        "experiment": "M01-ising-verification",
        "generated_at": "2026-06-15T00:00:00+00:00",
    }), encoding="utf-8")
    assert checks.verify() == []


def test_audit_skips_version_boundary_blocks(tmp_path, monkeypatch):
    """A foreign-version block neither passes nor fails the aggregate — it is
    not an audit, so alone it produces no row."""
    rec = _planned_receipt_json()
    rec["public_receipt"]["planned"]["planner"] = "v0"
    assert audit_planned_decisions([rec], records=[]) is None
