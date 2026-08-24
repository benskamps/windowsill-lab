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
    """The seam agrees with a straight re-derivation of the committed
    receipts.

    Until 2026-08-15 this test pinned the exact remaining-target count and
    went red after every landed hunt (receipts now arrive 4-8x/day from two
    boxes). What the seam PROMISES is arithmetic, not a number: per sector,
    remaining = newest declared enumeration minus the sum of searched
    counters across accepted receipts, clamped at zero; sectors sorted;
    None once nothing remains. This test re-derives that inline from the
    same committed files and requires exact agreement — a parsing or
    aggregation regression still fails, but a new receipt no longer does."""
    from pathlib import Path

    from lab import cli
    from lab import publish as pm

    accepted, _refused, _superseded = pm._accepted_hunt_receipts(
        pm.REPO_ROOT / "reports" / "hunts")
    assert accepted, "committed receipts exist — the survey has run"
    enums: dict[int, tuple[tuple[str, str], int]] = {}
    searched: dict[int, int] = {}
    for date, path, receipt in accepted:
        sector = receipt.get("sector")
        if not isinstance(sector, int):
            continue
        searched[sector] = (searched.get(sector, 0)
                            + pm._hunt_receipt_counters(receipt)
                            ["targets_searched"])
        enum_total = receipt.get("n_enumerated")
        stamp = (date, path.name)
        if isinstance(enum_total, int) and stamp >= enums.get(
                sector, (("", ""), 0))[0]:
            enums[sector] = (stamp, enum_total)
    expected = sum(max(0, total - searched.get(s, 0))
                   for s, (_, total) in enums.items())

    status = cli._hunt_status()
    if expected <= 0:
        assert status is None                 # sky exhausted → slot vanishes
        return
    assert status is not None
    assert status["remaining_targets"] == expected
    assert status["sectors"] == sorted(enums)
    # The split is live: at least sector 2 (win) carries an enumeration.
    assert 2 in enums


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


def test_frontier_sends_the_scheduler_hunting_when_lane_armed(monkeypatch,
                                                              capsys):
    """End to end on real committed state: A05 is the open frontier WITH a
    registered runner (2026-08-15), so a box with an armed sector lane
    dispatches `lab hunt` from the frontier branch — every slot goes to new
    sky, not to re-measuring finished work."""
    from lab import cli, curriculum
    monkeypatch.setattr(curriculum, "hunt_lane", lambda: (2, 29))
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab hunt`" in out
    assert "open milestone A05" in out


def test_frontier_without_lane_skips_a05_and_runs_the_portfolio(monkeypatch,
                                                                capsys):
    """A box with NO assigned lane must not hunt — the 2026-08-15 clobber
    lesson. The gate refuses with a named reason, the planner sees no survey
    candidate (dispatch status is lane-filtered), and the pass goes to the
    portfolio instead of refusal-spamming the survey slot."""
    from lab import cli, curriculum
    monkeypatch.setattr(curriculum, "hunt_lane", lambda: None)
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "skipped A05 — no-lane" in out
    assert "would run `lab hunt`" not in out
    assert "would run" in out                      # the portfolio still turns


# ── the sector lane: box-local config → gate → dispatch ──────────────────────

def test_hunt_lane_env_wins_and_malformed_reads_unassigned(monkeypatch,
                                                           tmp_path):
    from lab import curriculum
    from lab import labhome
    monkeypatch.setattr(labhome, "LAB_HOME", tmp_path)
    monkeypatch.setenv("WINDOWSILL_HUNT_SECTORS", "2,29")
    assert curriculum.hunt_lane() == (2, 29)
    monkeypatch.setenv("WINDOWSILL_HUNT_SECTORS", "two,three")
    assert curriculum.hunt_lane() is None          # malformed → unassigned
    monkeypatch.delenv("WINDOWSILL_HUNT_SECTORS")
    assert curriculum.hunt_lane() is None          # nothing configured
    (tmp_path / "hunt-sectors").write_text("3, 30\n", encoding="utf-8")
    assert curriculum.hunt_lane() == (3, 30)       # file fallback


def test_a05_gate_reasons(monkeypatch):
    from lab import cli, curriculum
    monkeypatch.setattr(curriculum, "hunt_lane", lambda: None)
    assert "no-lane" in curriculum.hardware_gate_reason("A05")
    monkeypatch.setattr(curriculum, "hunt_lane", lambda: (2, 29))
    monkeypatch.setattr(cli, "_hunt_status", lambda: None)
    assert "no-sky" in curriculum.hardware_gate_reason("A05")
    monkeypatch.setattr(cli, "_hunt_status", lambda: {
        "remaining_targets": 100, "sectors": [3], "per_sector": {3: 100}})
    assert "lane-exhausted" in curriculum.hardware_gate_reason("A05")
    monkeypatch.setattr(cli, "_hunt_status", lambda: {
        "remaining_targets": 100, "sectors": [2, 3],
        "per_sector": {2: 40, 3: 60}})
    assert curriculum.hardware_gate_reason("A05") is None


def test_dispatch_status_filters_to_the_lane(monkeypatch):
    from lab import cli, curriculum
    monkeypatch.setattr(cli, "_hunt_status", lambda: {
        "remaining_targets": 100, "sectors": [2, 3, 30],
        "per_sector": {2: 40, 3: 50, 30: 10}})
    monkeypatch.setattr(curriculum, "hunt_lane", lambda: (2, 29))
    status = cli._hunt_status_for_dispatch()
    assert status == {"remaining_targets": 40, "sectors": [2],
                      "per_sector": {2: 40}}
    monkeypatch.setattr(curriculum, "hunt_lane", lambda: None)
    assert cli._hunt_status_for_dispatch() is None


def test_bare_hunt_injects_the_lane_sector_and_refuses_without_one(
        monkeypatch, capsys):
    """A bare `lab hunt` hunts the lane sector with the most remaining
    committed coverage; with no eligible lane it refuses (exit 3) instead of
    falling into the driver's hardcoded default sector — the exact path that
    clobbered win's receipt on 2026-08-15."""
    import subprocess
    from lab import cli
    calls = []
    monkeypatch.setattr(subprocess, "call",
                        lambda argv, **kw: calls.append(argv) or 0)
    monkeypatch.setattr(cli, "_hunt_status_for_dispatch", lambda: {
        "remaining_targets": 70, "sectors": [2, 29],
        "per_sector": {2: 30, 29: 40}})
    assert cli.main(["hunt"]) == 0
    assert calls and "--sector" in calls[0]
    assert calls[0][calls[0].index("--sector") + 1] == "29"   # most remaining
    calls.clear()
    monkeypatch.setattr(cli, "_hunt_status_for_dispatch", lambda: None)
    rc = cli.main(["hunt"])
    assert rc == 3 and not calls
    assert "refusing bare dispatch" in capsys.readouterr().err
    # An explicit sector is an attended run — never second-guessed.
    monkeypatch.setattr(cli, "_hunt_status_for_dispatch",
                        lambda: (_ for _ in ()).throw(AssertionError(
                            "explicit --sector must not consult the lane")))
    assert cli.main(["hunt", "--sector", "3"]) == 0
    assert calls and calls[0][calls[0].index("--sector") + 1] == "3"


# ── Lane ownership: when another scheduler on this box owns a milestone ──────
#
# loam ran A05 twice over: the dedicated windowsill-hunt.timer landed a receipt
# every slot on a 100-minute budget, while the campaign ALSO picked A05 four
# times a day and ran it on the scheduler's 45-minute default. After the
# 2026-08-20 search level-ups made each target dearer, that budget stopped
# finishing a slice — so passes 134-137 each burnt ~45 minutes, wrote no
# receipt, published nothing, and starved the physics ladder, all at exit 0.

def test_lane_ownership_is_off_unless_declared(monkeypatch):
    monkeypatch.delenv("LAB_NEXT_SKIP", raising=False)
    assert curriculum.lane_owner_reason("A05") is None


def test_lane_ownership_names_the_reason(monkeypatch):
    monkeypatch.setenv("LAB_NEXT_SKIP", "A05")
    reason = curriculum.lane_owner_reason("A05")
    assert reason and "owned-elsewhere" in reason
    assert curriculum.lane_owner_reason("M05") is None, "only the named ids"


def test_lane_ownership_tolerates_spacing_and_case(monkeypatch):
    monkeypatch.setenv("LAB_NEXT_SKIP", " a05 , i01 ")
    assert curriculum.lane_owner_reason("A05")
    assert curriculum.lane_owner_reason("I01")


def test_ownership_is_asked_before_the_hardware_gate(monkeypatch):
    """If we are not the lane that runs it, whether our hardware could is not
    the question — and the ownership answer must not depend on lane config."""
    monkeypatch.setenv("LAB_NEXT_SKIP", "A05")
    monkeypatch.delenv("WINDOWSILL_HUNT_SECTORS", raising=False)
    assert "owned-elsewhere" in curriculum.hardware_gate_reason("A05")


def test_the_planner_does_not_re_pick_an_owned_hunt(monkeypatch):
    """THE regression this fix first shipped with: the frontier branch skipped
    A05 as owned-elsewhere and the planner immediately re-picked it one layer
    down, because the hunt rides in as its own candidate and never consulted
    A05's gate."""
    monkeypatch.setenv("LAB_NEXT_SKIP", "A05")
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04", "M05"))
    statuses = {"M03": "verified", "M04": "verified", "M05": "verified"}
    pick, decision = plan_turn([], statuses, now=NOW,
                               hunt_status={"remaining_targets": 500})
    assert pick != HUNT_CANDIDATE
    assert HUNT_CANDIDATE not in [e["mid"] for e in decision["scoreboard"]]
    skipped = dict(decision.get("skips") or [])
    assert "owned-elsewhere" in skipped.get(HUNT_CANDIDATE, ""), \
        "the refusal must be disclosed by name, not silent"


def test_an_undeclared_box_still_hunts(monkeypatch):
    """The default has to stay exactly what it was — win's campaign keeps
    picking the hunt until win declares its own lane."""
    monkeypatch.delenv("LAB_NEXT_SKIP", raising=False)
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04", "M05"))
    statuses = {"M03": "verified", "M04": "verified", "M05": "verified"}
    pick, _decision = plan_turn([], statuses, now=NOW,
                                hunt_status={"remaining_targets": 500})
    assert pick == HUNT_CANDIDATE


# ── the planner must be able to say "nothing is worth running" ───────────────

def test_an_all_canary_board_is_named_as_an_idle_frontier(monkeypatch):
    """Twelve consecutive passes on 2026-08-24 re-ran already-green milestones
    and every surface reported health. In 160 passes of history a canary has
    changed zero verdicts, so a board with nothing but canaries is a fact the
    operator needs — not a state to hide behind a pick."""
    monkeypatch.delenv("LAB_NEXT_SKIP", raising=False)
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04", "M05"))
    old = _stamp(NOW - timedelta(days=30))
    records = [(old, "M03"), (old, "M04"), (old, "M05")]
    statuses = {"M03": "verified", "M04": "verified", "M05": "verified"}
    _pick, decision = plan_turn(records, statuses, now=NOW)
    assert decision["frontier_idle"] is True
    assert "frontier has nothing runnable" in decision["frontier_idle_reason"]


def test_a_board_with_real_work_is_not_flagged_idle(monkeypatch):
    """The narrowness matters: a frontier that IS moving must not carry the
    flag, or it becomes noise and gets ignored like every other permanent
    warning."""
    monkeypatch.delenv("LAB_NEXT_SKIP", raising=False)
    monkeypatch.setattr(curriculum, "ROTATION", ("M03", "M04", "M05"))
    statuses = {FRONTIER_ID: "open", "M03": "verified", "M04": "verified",
                "M05": "verified"}
    _pick, decision = plan_turn([], statuses, now=NOW)
    assert decision["frontier_idle"] is False
    assert decision["frontier_idle_reason"] is None
