"""`lab next` — the milestone-aware scheduler: frontier first (the LOWEST OPEN
milestone with a runner), then the committed portfolio ROTATION over already-
runnable milestones, and only then the M01 heartbeat.

Torch-free: selection is pure (reads parsed milestone dicts / receipt tuples),
and the routing tests stub the target runner + renderer + publish so no
Monte-Carlo sweep or GPU is touched. These lock in the fix for the bug where
the scheduler re-ran M01 every pass because the open frontier (M18) has no
runner and the fallback was a single hardcoded heartbeat instead of a rotation
(docs/investigations/2026-08-01-portfolio-rotation.md).
"""
import json

import lab.cli as cli
from lab import curriculum
from lab.publish import parse_milestones


def _rotation_receipts(tmp_path, *entries):
    """Write a fixture receipts dir: entries are (filename_date, slug, stamp|None)."""
    receipts = tmp_path / "receipts"
    receipts.mkdir(exist_ok=True)
    for date, slug, stamp in entries:
        body = json.dumps({"generated_at": stamp}) if stamp else "{corrupt"
        (receipts / f"run-{date}-{slug}.json").write_text(body, encoding="utf-8")
    return receipts


def _no_camera(monkeypatch):
    monkeypatch.delenv("WINDOWSILL_I01_FRAMES", raising=False)
    monkeypatch.delenv("LAB_I01_CAMERA", raising=False)


# ── pure selection ────────────────────────────────────────────────────────────

def test_select_next_picks_the_lowest_open_milestone():
    """Given a milestone state, `_select_next` returns the one flagged open — the
    lowest still-pending — not the first (already-verified) one."""
    milestones = [
        {"id": "M01", "status": "verified"},
        {"id": "M11", "status": "verified"},
        {"id": "M12", "status": "open"},      # the lowest not-done
        {"id": "M13", "status": "pending"},
        {"id": "M14", "status": "pending"},
    ]
    mid, has_runner = cli._select_next(milestones)
    assert mid == "M12"
    assert has_runner is True          # M12 has a registered runner


def test_select_next_flags_missing_runner_for_frontier_without_engine():
    """When the open milestone has no runner registered (e.g. M18, past the runner
    frontier), selection still names it but reports has_runner=False so the caller
    can heartbeat."""
    milestones = [
        {"id": "M17", "status": "verified"},
        {"id": "M18", "status": "open"},
    ]
    mid, has_runner = cli._select_next(milestones)
    assert mid == "M18"
    assert has_runner is False


def test_select_next_dispatches_m15_now_that_it_has_a_runner():
    """M15 landed a runner (the Glauber-dynamics domain-growth engine), so when it is the
    open bench selection reports has_runner=True — the nightly climbs to it rather than
    heartbeating. The regression this locks: M15 used to be the runner frontier."""
    milestones = [
        {"id": "M14", "status": "verified"},
        {"id": "M15", "status": "open"},
        {"id": "M16", "status": "pending"},
    ]
    mid, has_runner = cli._select_next(milestones)
    assert mid == "M15"
    assert has_runner is True


def test_select_next_returns_none_when_nothing_open():
    milestones = [
        {"id": "M01", "status": "verified"},
        {"id": "M02", "status": "null"},
    ]
    mid, has_runner = cli._select_next(milestones)
    assert mid is None
    assert has_runner is False


def test_select_next_over_real_parse_promotes_first_pending():
    """End-to-end with the real MILESTONES parser: the first `[ ]` line is the
    open bench, and it's what selection returns — even though earlier lines are
    `[x]` done."""
    text = (
        "- [x] **M01** — done one. (done 2026-06-08 — ok)\n"
        "- [x] **M11** — done eleven. (done 2026-06-25 — ok)\n"
        "- [ ] **M12** — open twelve.\n"
        "- [ ] **M13** — pending thirteen.\n"
    )
    milestones = parse_milestones(text)
    mid, has_runner = cli._select_next(milestones)
    assert mid == "M12"
    assert has_runner is True


# ── the `lab next` command surface ────────────────────────────────────────────

def test_next_dry_run_names_open_milestone_not_m01(monkeypatch, capsys):
    """`lab next --dry-run` prints the open milestone it WOULD run and runs
    nothing. The regression: it must NOT silently pick M01 when M12 is open."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M01", "status": "verified"},
        {"id": "M12", "status": "open"},
    ])
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "M12" in out
    assert "would run `lab m12`" in out


def test_next_dry_run_rotates_when_frontier_has_no_runner(monkeypatch, capsys, tmp_path):
    """Open milestone past the runner frontier (M18) → the portfolio rotation
    advances past the ledger pointer instead of heartbeating M01 forever. This
    rewrites the old 'falls back to heartbeat' expectation: the M01-every-pass
    behavior WAS this branch (M18 open, no runner, hardcoded fallback)."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M17", "status": "verified"},
        {"id": "M18", "status": "open"},
    ])
    receipts = _rotation_receipts(
        tmp_path, ("2026-07-30", "m01", "2026-07-30T09:00:00+00:00"),
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab m02`" in out          # pointer M01 → next slot M02
    assert "no runner for M18" in out            # the branch still names its cause


def test_next_dry_run_selects_m17_kpz_runner(monkeypatch, capsys):
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M16", "status": "verified"},
        {"id": "M17", "status": "open"},
    ])
    rc = cli.main(["next", "--dry-run", "--seed", "1004", "--device", "cuda"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab m17`" in out
    assert "ignored unsupported scheduler option(s): --device" in out


def test_scheduler_options_are_filtered_per_runner():
    from lab.curriculum import filter_scheduler_options

    args = ["--quick", "--seed", "17", "--device=cuda"]
    assert filter_scheduler_options("M12", args) == (args, [])
    assert filter_scheduler_options("M17", args) == (
        ["--quick", "--seed", "17"], ["--device"],
    )
    assert filter_scheduler_options("I01", args) == (
        ["--quick"], ["--seed", "--device"],
    )


def test_unsupported_malformed_scheduler_option_does_not_swallow_next_option():
    from lab.curriculum import filter_scheduler_options

    args = [
        "--seed", "--quick",
        "--device", "--capture-timeout", "3",
    ]
    assert filter_scheduler_options("I01", args) == (
        ["--quick", "--capture-timeout", "3"],
        ["--seed", "--device"],
    )
    assert filter_scheduler_options("I01", ["--seed", "-q"]) == (
        ["-q"],
        ["--seed"],
    )
    assert filter_scheduler_options("I01", ["--seed", "-1", "--quick"]) == (
        ["--quick"],
        ["--seed"],
    )


def test_next_dry_run_selects_m16_aging_runner(monkeypatch, capsys):
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M15", "status": "review"},
        {"id": "M16", "status": "open"},
    ])
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab m16`" in out


def test_next_dry_run_selects_m14_runner_when_m14_open(monkeypatch, capsys):
    """With M14 the open bench, `lab next --dry-run` now names the M14 runner it
    would dispatch — the proof that landing the random-bond engine makes the nightly
    climb to the frontier instead of heartbeating (M14 was the runner frontier before)."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M13", "status": "verified"},
        {"id": "M14", "status": "open"},
    ])
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "M14" in out
    assert "would run `lab m14`" in out


def test_next_routes_to_the_open_milestones_runner(monkeypatch, capsys):
    """Non-dry `lab next` dispatches the open milestone's real command. We stub
    the M12 runner/renderer/publish so the dispatch is exercised without a sweep.
    Proves `next` actually advances to M12 rather than re-running M01."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M11", "status": "verified"},
        {"id": "M12", "status": "open"},
    ])

    calls = {}

    class _FakeResult:
        crossing_T = None
        crossing_resolved = False
        t_sg_benchmark = 0.95
        tolerance = 0.10
        max_abs_q_mean = 0.03
        wall_seconds = 1.0

        class _Swap:
            def mean(self):
                return 0.5
        swap_rate = _Swap()
        T = [0.4, 0.95, 1.6]

    def fake_run_m12(**kwargs):
        calls["run"] = kwargs
        # M12's CLI progress callback is invoked per-L with (L, result).
        if kwargs.get("progress"):
            kwargs["progress"](4, _FakeResult())
        return _FakeResult()

    from lab import m12 as m12_mod
    from lab import render as render_mod
    monkeypatch.setattr(m12_mod, "run_m12", fake_run_m12)
    monkeypatch.setattr(m12_mod, "to_report", lambda result: {"experiment": "M12"})
    monkeypatch.setattr(render_mod, "render_m12", lambda report, date=None: "/tmp/m12.html")
    monkeypatch.setattr(publish_mod, "publish", lambda *a, **k: "/tmp/pot.json")

    rc = cli.main(["next", "--quick"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "run" in calls                    # the M12 runner was invoked
    assert "running `lab m12`" in out
    assert "M12 3D Edwards" in out           # M12's own banner printed


# ── the portfolio rotation registry (curriculum.ROTATION) ─────────────────────

def test_rotation_is_curated_and_every_slot_is_dispatchable():
    """ROTATION is a curated committed list, not blanket RUNNERS: M12/M16 are
    excluded by name (wall-clock class exceeds the Windows PT2H slot; --quick
    variants ship a null every pass), M18+ has no runner. M01 stays as one slot
    — the calibration pulse, demoted from daily headline."""
    assert curriculum.ROTATION[0] == "M01"
    assert "M12" not in curriculum.ROTATION
    assert "M16" not in curriculum.ROTATION
    assert "M18" not in curriculum.ROTATION
    assert "I01" in curriculum.ROTATION           # in rotation, hardware-gated
    assert len(set(curriculum.ROTATION)) == len(curriculum.ROTATION)
    for mid in curriculum.ROTATION:
        assert mid in curriculum.RUNNERS


def test_i01_hardware_gate_names_the_absence(monkeypatch, tmp_path):
    """No camera env + no frames env (or frames pointing at nothing) → a named
    'no-camera' reason. ONLY a real stack on disk satisfies the gate — that is
    the one input the scheduled bare dispatch can measure from. Deterministic —
    the scheduler never probes a device. (Amended in review 2026-08-01: the
    original expectation that LAB_I01_CAMERA satisfies the gate was the
    livelock bug — see test_i01_gate_rejects_camera_only_config below.)"""
    _no_camera(monkeypatch)
    reason = curriculum.HARDWARE_GATES["I01"]()
    assert reason is not None and "no-camera" in reason

    monkeypatch.setenv("WINDOWSILL_I01_FRAMES", str(tmp_path / "missing.npy"))
    assert curriculum.HARDWARE_GATES["I01"]() is not None   # set but absent

    stack = tmp_path / "dark.npy"
    stack.write_bytes(b"\x93NUMPY")
    monkeypatch.setenv("WINDOWSILL_I01_FRAMES", str(stack))
    assert curriculum.HARDWARE_GATES["I01"]() is None

    _no_camera(monkeypatch)
    monkeypatch.setenv("LAB_I01_CAMERA", "0")
    assert curriculum.HARDWARE_GATES["I01"]() is not None   # camera-only ≠ dispatchable


# ── pure rotation selection (select_rotation) ────────────────────────────────

def _all_verified():
    return [{"id": mid, "status": "verified"} for mid in curriculum.ROTATION]


def test_select_rotation_walks_to_the_next_slot():
    pick, skips = curriculum.select_rotation(_all_verified(), "M01")
    assert (pick, skips) == ("M02", [])
    pick, _ = curriculum.select_rotation(_all_verified(), "M17")
    assert pick == "C01"
    # Unknown or absent pointer starts the rotation at its first slot.
    pick, _ = curriculum.select_rotation(_all_verified(), "ZZ99")
    assert pick == "M01"
    pick, _ = curriculum.select_rotation(_all_verified(), None)
    assert pick == "M01"


def test_select_rotation_skips_gated_i01_and_wraps(monkeypatch):
    """N2: pointer at A01 → next slot is I01 → gated (no camera) → disclosed
    skip with a named reason, then wrap to M01. The skip is a returned tuple,
    not a receipt, not a report, not a science row."""
    _no_camera(monkeypatch)
    pick, skips = curriculum.select_rotation(_all_verified(), "A01")
    assert pick == "M01"
    assert len(skips) == 1
    mid, reason = skips[0]
    assert mid == "I01" and "no-camera" in reason


def test_select_rotation_leaves_the_open_bench_to_the_frontier():
    """A rotation entry currently OPEN belongs to the frontier branch; rotation
    skips it with a named reason rather than double-dispatching it."""
    milestones = [{"id": mid, "status": "verified"} for mid in curriculum.ROTATION]
    for m in milestones:
        if m["id"] == "M03":
            m["status"] = "open"
    pick, skips = curriculum.select_rotation(milestones, "M02")
    assert pick == "M04"
    assert skips and skips[0][0] == "M03" and "open" in skips[0][1]


def test_select_rotation_empty_returns_none_with_the_skip_ledger(monkeypatch):
    monkeypatch.setattr(curriculum, "ROTATION", ())
    pick, skips = curriculum.select_rotation(_all_verified(), None)
    assert pick is None and skips == []


# ── the committed rotation pointer (rotation_pointer + receipt reader) ───────

def test_rotation_pointer_max_stamp_wins():
    records = [
        ("2026-07-30T01:00:00+00:00", "M01"),
        ("2026-07-31T05:00:00+00:00", "M13"),
        ("2026-07-30", "M07"),                     # date-degraded record
    ]
    assert curriculum.rotation_pointer(records) == "M13"
    assert curriculum.rotation_pointer([]) is None


def test_receipt_records_stamp_beats_newer_filename_date(tmp_path, monkeypatch):
    """N3: the newest generated_at wins even when a different receipt has a
    newer FILENAME date; a corrupt receipt degrades to its filename date (the
    run_cadence discipline) instead of failing the read."""
    from lab import publish as publish_mod
    receipts = _rotation_receipts(
        tmp_path,
        ("2026-07-29", "m13", "2026-07-31T04:00:00+00:00"),  # older name, newest stamp
        ("2026-07-30", "m01", None),                         # corrupt → filename date
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)
    records = cli._receipt_records()
    assert ("2026-07-30", "M01") in records
    assert curriculum.rotation_pointer(records) == "M13"


def test_next_dry_run_with_no_receipts_starts_rotation_at_the_pulse(
        monkeypatch, capsys, tmp_path):
    """Empty ledger → pointer None → the rotation opens at M01 (the calibration
    pulse) with the empty ledger named in the printed reason — fail-closed and
    disclosed, never silent."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M18", "status": "open"},
    ])
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", tmp_path / "empty-receipts")
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab run`" in out and "M01" in out
    assert "no receipts" in out


def test_next_falls_back_to_heartbeat_when_rotation_is_empty(
        monkeypatch, capsys, tmp_path):
    """The explicit heartbeat fallback survives (fail closed, named reason):
    an empty ROTATION must still produce a run, and say why."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M18", "status": "open"},
    ])
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", tmp_path / "empty-receipts")
    monkeypatch.setattr(curriculum, "ROTATION", ())
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab run`" in out
    assert "heartbeat" in out


def test_next_dry_run_frontier_beats_rotation(monkeypatch, capsys, tmp_path):
    """An OPEN milestone with a runner (M15 marked [>]) preserves the 6/26
    decision: frontier first — rotation is only the fallback."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M14", "status": "verified"},
        {"id": "M15", "status": "open"},
    ])
    receipts = _rotation_receipts(
        tmp_path, ("2026-07-30", "m01", "2026-07-30T09:00:00+00:00"),
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab m15`" in out
    assert "open milestone M15" in out


def test_two_boxes_advance_the_rotation_not_repeat_it(monkeypatch, capsys, tmp_path):
    """Two-box determinism: the pointer is a committed ledger fact, so after one
    box lands its receipt the other box picks the NEXT slot, not the same one."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M18", "status": "open"},
    ])
    receipts = _rotation_receipts(
        tmp_path, ("2026-08-01", "m02", "2026-08-01T00:10:00+00:00"),  # Win's pass
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)
    cli.main(["next", "--dry-run"])
    assert "would run `lab m03`" in capsys.readouterr().out   # Loam reads → next slot

    _rotation_receipts(
        tmp_path, ("2026-08-01", "m03", "2026-08-01T03:10:00+00:00"),  # Loam lands
    )
    cli.main(["next", "--dry-run"])
    assert "would run `lab m04`" in capsys.readouterr().out


def test_rotation_pass_never_dispatches_gated_i01(monkeypatch, capsys, tmp_path):
    """N2 end-to-end: a non-dry pass with the pointer at A01 (next slot I01, no
    camera) prints ONE disclosed skip line, dispatches the wrapped pick (M01),
    and produces zero I01 artifacts — the I01 runner is never invoked."""
    _no_camera(monkeypatch)
    from lab import i01 as i01_mod
    from lab import ising as ising_mod
    from lab import publish as publish_mod
    from lab import render as render_mod

    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M18", "status": "open"},
    ])
    receipts = _rotation_receipts(
        tmp_path, ("2026-07-31", "a01", "2026-07-31T15:10:00+00:00"),
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)

    def _never_run_i01(*a, **k):
        raise AssertionError("gated I01 must never be dispatched by the scheduler")
    monkeypatch.setattr(i01_mod, "run_i01", _never_run_i01)

    class _FakeIsing:
        wall_seconds = 1.0
    calls = {}
    monkeypatch.setattr(ising_mod, "run", lambda cfg: calls.setdefault("cfg", cfg) and _FakeIsing() or _FakeIsing())
    monkeypatch.setattr(render_mod, "render", lambda result: tmp_path / "m01.html")
    monkeypatch.setattr(publish_mod, "publish", lambda *a, **k: str(tmp_path / "pot.json"))

    rc = cli.main(["next", "--seed", "2026080100"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "skipped I01" in out and "no-camera" in out
    assert "running `lab run`" in out          # wrapped to the M01 slot
    assert "cfg" in calls                      # the M01 engine actually ran
    assert not list(tmp_path.glob("**/*i01*"))  # zero i01 artifacts anywhere


# ── adversarial review pass (2026-08-01): gate/runner contract, pointer
#    disclosure, tie-break determinism, dry-run purity ────────────────────────

def test_i01_gate_rejects_camera_only_config_the_dispatch_cannot_use(monkeypatch):
    """LAB_I01_CAMERA alone must NOT make I01 eligible. The scheduler dispatches
    a bare `lab i01`, which measures only from --frames / WINDOWSILL_I01_FRAMES
    — live capture requires an attended `lab i01 --camera N` (cli passes no
    capture flags on dispatch; i01.run_i01 never reads LAB_I01_CAMERA). If the
    gate passed on LAB_I01_CAMERA, the dispatch would exit 3 with NO receipt,
    the pointer would never advance past the previous slot, and every later
    pass would re-pick I01: a rotation livelock. The gate must skip with a
    reason naming the mismatch instead."""
    monkeypatch.delenv("WINDOWSILL_I01_FRAMES", raising=False)
    monkeypatch.setenv("LAB_I01_CAMERA", "0")
    reason = curriculum.hardware_gate_reason("I01")
    assert reason is not None
    assert "LAB_I01_CAMERA" in reason and "WINDOWSILL_I01_FRAMES" in reason
    pick, skips = curriculum.select_rotation(_all_verified(), "A01")
    assert pick == "M01"                       # wraps past the gated slot
    assert skips and skips[0][0] == "I01"


def test_next_dry_run_names_the_restart_when_pointer_is_outside_the_rotation(
        monkeypatch, capsys, tmp_path):
    """A newest receipt from an out-of-rotation experiment (a manual `lab m12`,
    or a frontier run right after its milestone verifies) restarts the walk at
    slot 0 — and the printed reason must SAY so, not claim the rotation
    'continues after M12' while actually resetting. Checkers re-derive claims;
    the reason line is the claim."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M18", "status": "open"},
    ])
    receipts = _rotation_receipts(
        tmp_path, ("2026-08-01", "m12", "2026-08-01T10:00:00+00:00"),
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab run`" in out                  # slot 0 is M01
    assert "outside the rotation" in out and "M12" in out
    assert "rotation continues after M12" not in out


def test_rotation_pointer_ignores_receipts_outside_the_rotation():
    """Review finding 1: an out-of-rotation receipt must not become the pointer.

    M12/M16 are excluded from ROTATION by name but are still hand-run (four
    such receipts are already committed), and the frontier lands one the moment
    its milestone gets a runner. An unknown pointer restarts the walk at slot 0
    — so letting the newest M12 win meant one manual `lab m12` re-seeded M01 as
    the next pick and rewound the whole lap, reintroducing the M01-every-pass
    bias the rotation exists to remove. The pointer is the newest receipt the
    ROTATION OWNS; the M12 receipt is skipped, not obeyed."""
    records = [
        ("2026-08-01T02:00:00+00:00", "M07"),
        ("2026-08-01T09:00:00+00:00", "M12"),   # hand-run, newest overall
    ]
    assert curriculum.rotation_pointer(records) == "M07"
    assert curriculum.select_rotation(_all_verified(), "M07")[0] == "M08"
    # M16 and a future frontier receipt (M18) are skipped on the same rule.
    for outsider in ("M16", "M18"):
        assert curriculum.rotation_pointer(
            [("2026-08-01T02:00:00+00:00", "M07"),
             ("2026-08-01T09:00:00+00:00", outsider)]
        ) == "M07"
    # Disclosure companion: the raw newest is still available to name it.
    assert curriculum.newest_receipt_milestone(records) == "M12"
    # A ledger with ONLY out-of-rotation receipts has no pointer to resume from.
    assert curriculum.rotation_pointer([("2026-08-01", "M12")]) is None


def test_next_dry_run_resumes_the_rotation_past_a_manual_out_of_rotation_run(
        monkeypatch, capsys, tmp_path):
    """Finding 1 end-to-end: a manual `lab m12` landing the newest receipt must
    NOT rewind the lap to M01. The pass resumes after the newest receipt the
    rotation owns (M07 → M08) and says so."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M18", "status": "open"},
    ])
    receipts = _rotation_receipts(
        tmp_path,
        ("2026-08-01", "m07", "2026-08-01T02:00:00+00:00"),
        ("2026-08-01", "m12", "2026-08-01T09:00:00+00:00"),  # manual, newest
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab m08`" in out                  # resumed, not rewound
    assert "rotation continues after M07" in out
    assert "would run `lab run`" not in out              # M01 was NOT re-seeded


def test_rotation_pointer_tie_breaks_by_milestone_id_order_independent():
    """Claim check for cross-box determinism: with IDENTICAL generated_at
    stamps the pointer must be the max milestone id whatever order the records
    arrive in — otherwise two boxes iterating the same committed ledger
    differently would derive different pointers and double-run a slot."""
    stamp = "2026-08-01T06:00:00+00:00"
    records = [(stamp, "M03"), (stamp, "M07"), (stamp, "M02")]
    assert curriculum.rotation_pointer(records) == "M07"
    assert curriculum.rotation_pointer(list(reversed(records))) == "M07"


def test_next_dry_run_runs_nothing_and_writes_nothing(monkeypatch, capsys, tmp_path):
    """Negative control for the dry-run promise: with every engine entry point
    booby-trapped, `lab next --dry-run` must still succeed and disclose its
    skips — proof the dry path selects and prints but never runs, renders,
    publishes, or writes."""
    from lab import i01 as i01_mod
    from lab import ising as ising_mod
    from lab import publish as publish_mod
    from lab import render as render_mod
    _no_camera(monkeypatch)
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M18", "status": "open"},
    ])
    receipts = _rotation_receipts(
        tmp_path, ("2026-07-31", "a01", "2026-07-31T15:10:00+00:00"),
    )
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", receipts)

    def _boom(*a, **k):
        raise AssertionError("--dry-run must not execute anything")
    monkeypatch.setattr(ising_mod, "run", _boom)
    monkeypatch.setattr(i01_mod, "run_i01", _boom)
    monkeypatch.setattr(render_mod, "render", _boom)
    monkeypatch.setattr(publish_mod, "publish", _boom)

    before = sorted(p.name for p in receipts.iterdir())
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "skipped I01" in out and "no-camera" in out   # disclosed in dry-run
    assert "would run `lab run`" in out                  # wrapped to M01
    assert sorted(p.name for p in receipts.iterdir()) == before
