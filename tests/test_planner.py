"""The value-function planner (`curriculum.plan_turn`) — the concept-level fix
for the M01-x40 / M02-x44 waste: 84 of the first 136 committed receipts were
two slugs, because two independent scheduler defects (a stuck open-pointer, a
stem-slice parse livelock) could each buy unlimited consecutive re-runs of a
verified rung while CI stayed green. The planner turns selection into a
value/cost score derived from the receipts ledger itself, so ANY future defect
of that class hits the repeat law instead of the archive.

Torch-free: `plan_turn` is pure (ledger tuples + a status mapping in, a
decision record out), and the cli tests stub the dispatch boundary exactly as
tests/test_next.py does, so no engine ever runs.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import lab.cli as cli
import lab.receipt as receipt_mod
from lab import curriculum
from lab.curriculum import (
    CANARY_HALF_LIFE_DAYS,
    HUNT_CANDIDATE,
    NEVER_RUN_VALUE,
    NULL_RETRY_VALUE,
    OPEN_FRONTIER_VALUE,
    REPEAT_HARD_CAP,
    STALENESS_CAP,
    VERIFIED_CANARY_VALUE,
    plan_turn,
)

#: A fixed "now" so every score in this file re-derives identically forever.
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)

#: An open frontier id with a real runner that is NOT a ROTATION member —
#: exactly the shape the frontier seam exists for. Guarded like test_next's
#: NO_RUNNER_ID so a curriculum edit fails loudly instead of silently
#: rewriting what these tests mean. M12 holds this shape PERMANENTLY: it is
#: excluded from the rotation by wall-clock class (2026-08-01 doc), not by
#: review status, so planner-era rotation growth can never absorb it the way
#: it absorbed M18 on 2026-08-14.
FRONTIER_ID = "M12"
assert FRONTIER_ID in curriculum.RUNNERS, f"{FRONTIER_ID} lost its runner"
assert FRONTIER_ID not in curriculum.ROTATION, f"{FRONTIER_ID} joined ROTATION"


@pytest.fixture(autouse=True)
def _no_camera(monkeypatch):
    """Pin the I01 hardware gate CLOSED so scores never depend on the host env."""
    monkeypatch.delenv("WINDOWSILL_I01_FRAMES", raising=False)
    monkeypatch.delenv("LAB_I01_CAMERA", raising=False)


def _verified_estate():
    """Every rotation member verified — the lab's real steady state."""
    return {mid: "verified" for mid in curriculum.ROTATION}


def _stamp(dt):
    return dt.isoformat()


def _iterate(records, statuses, n, *, step_hours=6.0, hunt_status=None):
    """Run the planner n times, appending its own choice to the ledger — the
    self-feeding loop a real scheduled estate is. Returns the pick sequence."""
    records = list(records)
    picks = []
    now = NOW
    for _ in range(n):
        now = now + timedelta(hours=step_hours)
        pick, _decision = plan_turn(
            records, statuses, now=now, hunt_status=hunt_status)
        assert pick is not None
        picks.append(pick)
        records.append((_stamp(now), pick))
    return picks


def _max_run(picks):
    longest = run = 0
    prev = None
    for p in picks:
        run = run + 1 if p == prev else 1
        prev = p
        longest = max(longest, run)
    return longest


# ── class ordering ───────────────────────────────────────────────────────────

def test_class_constants_keep_their_strict_order():
    """The invariant, not a tendency: OPEN > NEVER_RUN > NULL > CANARY, and the
    staleness cap sits BELOW the never-run value so no amount of waiting lets a
    verified canary outrank a rung that has never been measured at all."""
    assert OPEN_FRONTIER_VALUE > NEVER_RUN_VALUE > NULL_RETRY_VALUE \
        > VERIFIED_CANARY_VALUE
    assert STALENESS_CAP * VERIFIED_CANARY_VALUE < NEVER_RUN_VALUE


def test_frontier_beats_never_run_beats_null_beats_canary(monkeypatch):
    """One candidate of each class on the board: the scoreboard must rank them
    in class order whatever the walk order says."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04", "M05"))
    old = _stamp(NOW - timedelta(days=30))
    records = [
        (old, "M04"),                 # null with a receipt → null-retry
        (old, "M05"),                 # verified, 30 days stale → canary
    ]                                 # M03 has no receipt → never-run
    statuses = {FRONTIER_ID: "open", "M03": "verified",
                "M04": "null", "M05": "verified"}
    pick, decision = plan_turn(records, statuses, now=NOW)
    assert pick == FRONTIER_ID
    order = [e["mid"] for e in decision["scoreboard"]]
    assert order == [FRONTIER_ID, "M03", "M04", "M05"]
    classes = {e["mid"]: e["cls"] for e in decision["scoreboard"]}
    assert classes == {FRONTIER_ID: "open-frontier", "M03": "never-run",
                       "M04": "null-retry", "M05": "verified-canary"}


# ── staleness ────────────────────────────────────────────────────────────────

def test_canary_staleness_worthless_next_day_due_in_a_week(monkeypatch):
    """A verified canary is worth ~0 the day after it ran, exactly its base
    value at one half-life, and never more than the cap however long it sits.
    A fresher M04 receipt holds the ledger head so M03's score is staleness
    alone — repeat decay applies only to the mid at the head of the ledger."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04"))

    def value_at(days):
        records = [
            (_stamp(NOW - timedelta(days=days)), "M03"),
            (_stamp(NOW - timedelta(minutes=1)), "M04"),
        ]
        _pick, decision = plan_turn(
            records, {"M03": "verified", "M04": "verified"}, now=NOW)
        return next(
            e for e in decision["scoreboard"] if e["mid"] == "M03")["score"]

    assert value_at(0) == 0.0
    assert 0 < value_at(1) < 0.2                       # came due? barely
    assert value_at(CANARY_HALF_LIFE_DAYS) == pytest.approx(
        VERIFIED_CANARY_VALUE, abs=1e-4)               # log2(2) == 1
    assert value_at(1) < value_at(7) < value_at(30)    # monotone growth …
    assert value_at(100_000) == STALENESS_CAP * VERIFIED_CANARY_VALUE  # … capped


# ── the repeat law ───────────────────────────────────────────────────────────

def test_repeat_decay_law_property_diverse_and_never_a_run_past_the_cap():
    """THE LAW, as a property: iterate the planner 50 turns over the real
    rotation with every rung verified, feeding each pick back into the ledger.
    The pick set must be diverse and no mid may run more than REPEAT_HARD_CAP
    consecutive turns — the property whose absence produced 40 consecutive
    M01 receipts."""
    picks = _iterate([], _verified_estate(), 50)
    assert _max_run(picks) <= REPEAT_HARD_CAP
    assert len(set(picks)) >= 5


def test_open_frontier_cannot_monopolize_the_schedule_either():
    """The nastier property case: a permanently-open frontier whose base value
    dwarfs every alternative. Decay + the hard cap must still break its runs —
    the frontier gets MOST turns (it is the most valuable work) but never more
    than REPEAT_HARD_CAP in a row."""
    statuses = {**_verified_estate(), FRONTIER_ID: "open"}
    picks = _iterate([], statuses, 50)
    assert _max_run(picks) <= REPEAT_HARD_CAP
    assert picks.count(FRONTIER_ID) >= 15      # still the dominant workload
    assert len(set(picks)) >= 3


def test_hard_cap_fires_where_decay_alone_would_not(monkeypatch):
    """Direct hard-cap unit: an open frontier at 8.0 versus one barely-stale
    canary at ~0.5. After three consecutive frontier receipts the decayed value
    (8 × 2^-3 = 1.0) STILL beats the canary — only the cap breaks the run, and
    the scoreboard says so."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03",))
    statuses = {FRONTIER_ID: "open", "M03": "verified"}
    head = [
        (_stamp(NOW - timedelta(days=3)), "M03"),
        (_stamp(NOW - timedelta(hours=18)), FRONTIER_ID),
        (_stamp(NOW - timedelta(hours=12)), FRONTIER_ID),
        (_stamp(NOW - timedelta(hours=6)), FRONTIER_ID),
    ]
    pick, decision = plan_turn(head, statuses, now=NOW)
    assert pick == "M03"
    capped = next(e for e in decision["scoreboard"] if e["mid"] == FRONTIER_ID)
    assert capped["score"] == 0.0
    assert "repeat-capped" in capped["cls"]
    assert capped["repeats"] == REPEAT_HARD_CAP


def test_m01_x40_history_would_have_broken_at_the_first_pick():
    """The fixture goldmine: the real archive's shape — 40 consecutive M01
    receipts (the stuck open-pointer era, 4 passes/day for 10 days). The task's
    bar is a broken streak by pick 4; the planner clears it at pick ONE, and
    holds the law for the next 8 picks."""
    records = [
        (_stamp(NOW - timedelta(days=10) + timedelta(hours=6 * i)), "M01")
        for i in range(40)
    ]
    pick, decision = plan_turn(records, _verified_estate(), now=NOW)
    assert pick != "M01"                       # streak broken immediately
    # M01's 40-repeat decay + hard cap zero it clean off the top-5 board.
    assert all(e["mid"] != "M01" for e in decision["scoreboard"])
    picks = _iterate(records, _verified_estate(), 8)
    assert _max_run(picks) <= REPEAT_HARD_CAP
    assert picks.count("M01") <= 1             # one lawful return at most


# ── the hunt seam ────────────────────────────────────────────────────────────

def test_hunt_candidate_scales_with_remaining_targets(monkeypatch):
    """A05-HUNT scores full OPEN_FRONTIER value at ≥500 remaining targets and
    scales down linearly below; zero remaining (or no status) fields no
    candidate at all."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03",))
    records = [(_stamp(NOW - timedelta(hours=6)), "M03")]  # fresh canary ~0

    def hunt_entry(status):
        _pick, decision = plan_turn(
            records, {"M03": "verified"}, now=NOW, hunt_status=status)
        return next(
            (e for e in decision["scoreboard"] if e["mid"] == HUNT_CANDIDATE),
            None)

    assert hunt_entry({"remaining_targets": 500})["score"] == OPEN_FRONTIER_VALUE
    assert hunt_entry({"remaining_targets": 100})["score"] == pytest.approx(
        OPEN_FRONTIER_VALUE / 5)
    assert hunt_entry({"remaining_targets": 0}) is None
    assert hunt_entry(None) is None


def test_hunt_never_repeat_decays(monkeypatch):
    """Each hunt turn searches a FRESH slice of the sector — cumulative by
    construction — so a repeated hunt is new coverage, not a re-measurement,
    and the repeat law deliberately exempts it: the planner may run it past
    the hard cap while targets remain."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03",))
    records = [(_stamp(NOW - timedelta(hours=6)), "M03")]
    picks = _iterate(
        records, {"M03": "verified"}, 6, step_hours=0.5,
        hunt_status={"remaining_targets": 500})
    assert picks == [HUNT_CANDIDATE] * 6       # > REPEAT_HARD_CAP, by design


# ── cost ─────────────────────────────────────────────────────────────────────

def test_cost_penalizes_expensive_runs_but_never_discounts_cheap_ones(
        monkeypatch):
    """Cost is a divisor clamped at 1.0: an expensive rung is demoted per
    second, but a cheap rung cannot buy a score above its class value — the
    class-ordering invariant survives the cost seam."""
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04"))
    durations = {"M03": [100.0, 110.0, 90.0], "M04": [10.0, 12.0, 9.0]}
    pick, decision = plan_turn(
        [], {"M03": "verified", "M04": "verified"}, now=NOW,
        durations=durations)
    assert pick == "M04"
    by_mid = {e["mid"]: e for e in decision["scoreboard"]}
    assert by_mid["M04"]["cost"] == 1.0                     # clamped, no boost
    assert by_mid["M04"]["score"] == NEVER_RUN_VALUE        # class value intact
    assert by_mid["M03"]["cost"] > 1.0
    assert by_mid["M03"]["score"] < NEVER_RUN_VALUE


# ── gates, skips, ties ───────────────────────────────────────────────────────

def test_gated_and_runnerless_slots_are_skipped_with_named_reasons():
    """The disclosure contract survives the planner: gated I01 lands in the
    decision's skips with its named reason, never on the scoreboard."""
    pick, decision = plan_turn([], _verified_estate(), now=NOW)
    assert pick is not None and pick != "I01"
    assert all(e["mid"] != "I01" for e in decision["scoreboard"])
    assert any(mid == "I01" and "no-camera" in reason
               for mid, reason in decision["skips"])


def test_ties_degrade_to_the_rotation_walk_after_the_pointer():
    """Two boxes reading the same committed ledger must pick DIFFERENT slots.
    When scores tie (the all-never-run opening lap), the planner tie-breaks in
    rotation order after the ledger pointer — byte-identical behavior to
    `select_rotation`, and the reason line says so in the rotation's words."""
    records = [("2026-08-01T00:10:00+00:00", "M02")]
    pick, decision = plan_turn(records, _verified_estate(), now=NOW)
    assert pick == "M03"
    assert "rotation continues after M02" in decision["reason"]


# ── decision record + receipts ───────────────────────────────────────────────

def test_decision_record_shape():
    """The record a receipt will carry: planner version, chosen, one-line
    reason, top-5 scoreboard sorted by descending score, per-entry fields."""
    pick, decision = plan_turn([], _verified_estate(), now=NOW)
    assert decision["planner"] == "v1"
    assert decision["chosen"] == pick
    assert isinstance(decision["reason"], str) and decision["reason"]
    board = decision["scoreboard"]
    assert 1 <= len(board) <= 5
    scores = [e["score"] for e in board]
    assert scores == sorted(scores, reverse=True)
    for entry in board:
        assert set(entry) == {"mid", "cls", "value", "cost", "score", "repeats"}


def test_receipt_carries_planned_block_only_when_the_scheduler_armed_it():
    """Manual runs stay clean: the planned block appears exactly between
    set_planned_decision and clear_planned_decision, and holds the compact
    chosen + reason + top-3 view."""
    report = {"experiment": "x", "value": 1}
    assert "planned" not in receipt_mod.build_public_receipt(
        report)["public_receipt"]

    _pick, decision = plan_turn([], _verified_estate(), now=NOW)
    receipt_mod.set_planned_decision(decision)
    try:
        planned = receipt_mod.build_public_receipt(
            report)["public_receipt"]["planned"]
    finally:
        receipt_mod.clear_planned_decision()
    assert planned["chosen"] == decision["chosen"]
    assert planned["reason"] == decision["reason"]
    assert planned["planner"] == "v1"
    assert len(planned["scoreboard"]) == 3
    assert [e["mid"] for e in planned["scoreboard"]] == \
        [e["mid"] for e in decision["scoreboard"][:3]]

    assert "planned" not in receipt_mod.build_public_receipt(
        report)["public_receipt"]           # cleared — the next run is manual


def test_planned_block_re_derives_from_the_same_inputs():
    """Auditability: a receipt's planned block plus the same committed inputs
    must re-derive to the same chosen — the pattern a future `lab verify`
    check can adopt. plan_turn is deterministic in (records, statuses, now)."""
    records = [
        (_stamp(NOW - timedelta(days=10) + timedelta(hours=6 * i)), "M01")
        for i in range(40)
    ]
    statuses = _verified_estate()
    _pick, decision = plan_turn(records, statuses, now=NOW)
    receipt_mod.set_planned_decision(decision)
    try:
        receipt = receipt_mod.build_public_receipt({"experiment": "x"})
    finally:
        receipt_mod.clear_planned_decision()
    planned = json.loads(json.dumps(receipt))["public_receipt"]["planned"]

    re_pick, re_decision = plan_turn(records, statuses, now=NOW)
    assert re_pick == planned["chosen"]
    assert re_decision["reason"] == planned["reason"]
    assert [e["mid"] for e in re_decision["scoreboard"][:3]] == \
        [e["mid"] for e in planned["scoreboard"]]


# ── cli integration ──────────────────────────────────────────────────────────

@pytest.fixture()
def _isolated_lab_home(tmp_path, monkeypatch):
    home = tmp_path / "lab-home"
    home.mkdir()
    monkeypatch.setattr(cli, "LAB_HOME", home)
    return home


def _receipts_fixture(tmp_path, *entries):
    receipts = tmp_path / "receipts"
    receipts.mkdir(exist_ok=True)
    for date, slug, stamp in entries:
        (receipts / f"run-{date}-2336-{slug}.json").write_text(
            json.dumps({"generated_at": stamp}), encoding="utf-8")
    return receipts


def test_next_dry_run_prints_the_planner_reason(
        monkeypatch, capsys, tmp_path, _isolated_lab_home):
    """The scheduler path speaks planner: the one-line reason on a dry run
    names the decision, not just the branch."""
    from lab import publish as publish_mod
    monkeypatch.setattr(cli, "_hunt_status", lambda: None)   # non-hunt path
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M99", "status": "open"},
    ])
    receipts = _receipts_fixture(
        tmp_path, ("2026-08-01", "m02", "2026-08-01T00:10:00+00:00"))
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab m03`" in out
    assert "planner v1" in out


def test_planner_failure_falls_back_to_the_rotation_walk(
        monkeypatch, capsys, tmp_path, _isolated_lab_home):
    """The scheduler must never die of its own planner: plan_turn raising
    anything falls back to `select_rotation`, logs the failure by name, and
    still picks the walk's slot."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M99", "status": "open"},
    ])
    receipts = _receipts_fixture(
        tmp_path, ("2026-08-01", "m02", "2026-08-01T00:10:00+00:00"))
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)

    def _boom(*a, **k):
        raise RuntimeError("planner exploded")
    monkeypatch.setattr(curriculum, "plan_turn", _boom)

    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "planner failed (planner exploded)" in out
    assert "falling back to the rotation walk" in out
    assert "would run `lab m03`" in out
    assert "rotation continues after M02" in out


def test_scheduled_dispatch_arms_the_receipt_seam_and_clears_it(
        monkeypatch, capsys, tmp_path, _isolated_lab_home):
    """Non-dry scheduled pass: the planned decision is armed in lab.receipt for
    exactly the dispatch (so the receipt written inside carries it) and cleared
    after — a manual run following in the same process inherits nothing."""
    monkeypatch.setattr(cli, "_hunt_status", lambda: None)   # non-hunt path
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M99", "status": "open"},
    ])
    receipts = _receipts_fixture(
        tmp_path, ("2026-08-01", "m02", "2026-08-01T00:10:00+00:00"))
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)

    real_main = cli.main
    seen: list[dict | None] = []
    depth = {"n": 0}

    def _main(argv=None):
        depth["n"] += 1
        try:
            if depth["n"] > 1:      # the dispatch tail call — record the seam
                seen.append(receipt_mod._PLANNED_DECISION)
                return 0
            return real_main(argv)
        finally:
            depth["n"] -= 1

    monkeypatch.setattr(cli, "main", _main)
    rc = cli.main(["next"])
    assert rc == 0
    assert len(seen) == 1
    assert seen[0] is not None and seen[0]["chosen"] == "M03"
    assert seen[0]["planner"] == "v1"
    assert receipt_mod._PLANNED_DECISION is None       # cleared after dispatch

# ── the hunt seam: committed coverage state → the survey slot ─────────────────

def test_hunt_status_reads_the_committed_receipt():
    """Live committed state: the 570-target pilot receipt carries
    n_enumerated=1994, so the seam derives 1,424 remaining and the sector."""
    from lab import cli
    status = cli._hunt_status()
    assert status is not None
    assert status["remaining_targets"] == 1994 - 570
    assert status["sectors"] == [2]


def test_hunt_status_is_none_without_enumeration(tmp_path, monkeypatch):
    """A receipt without its enumeration total keeps the candidate OFF —
    honest over wishful (the pre-backfill state, pinned as a test)."""
    import json as _json
    from lab import cli, publish
    hunts = tmp_path / "reports" / "hunts"
    hunts.mkdir(parents=True)
    (hunts / "hunt-2026-01-01-s9.json").write_text(_json.dumps(
        {"date": "2026-01-01", "sector": 9, "targets_searched": 10}),
        encoding="utf-8")
    monkeypatch.setattr(publish, "REPO_ROOT", tmp_path)
    assert cli._hunt_status() is None


def test_planner_sends_the_scheduler_hunting(capsys):
    """End to end on real committed state: A05 is the open frontier with no
    RUNNERS entry, the hunt receipt proves 1,424 stars remain, so the dry-run
    scheduler must dispatch `lab hunt` — the survey slot outranks every
    canary and cannot repeat-decay."""
    from lab import cli
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab hunt`" in out
    assert "A05-HUNT" in out
