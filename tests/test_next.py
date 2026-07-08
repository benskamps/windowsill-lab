"""`lab next` — the milestone-aware scheduler that selects and runs the LOWEST
OPEN milestone (falling back to the M01 heartbeat when the open milestone has no
runner yet, or nothing is open).

Torch-free: selection is pure (reads parsed milestone dicts), and the one
routing test stubs the target runner + renderer + publish so no Monte-Carlo
sweep or GPU is touched. These lock in the fix for the bug where the nightly
re-ran M01 forever instead of advancing to the open milestone.
"""
import lab.cli as cli
from lab.publish import parse_milestones


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
    """When the open milestone has no runner registered (e.g. M16, past the runner
    frontier), selection still names it but reports has_runner=False so the caller
    can heartbeat."""
    milestones = [
        {"id": "M15", "status": "verified"},
        {"id": "M16", "status": "open"},
    ]
    mid, has_runner = cli._select_next(milestones)
    assert mid == "M16"
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


def test_next_dry_run_falls_back_to_heartbeat_when_no_runner(monkeypatch, capsys):
    """Open milestone past the runner frontier (M16) → dry-run reports the M01
    heartbeat as the fallback, naming the milestone it's standing in for."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M15", "status": "verified"},
        {"id": "M16", "status": "open"},
    ])
    rc = cli.main(["next", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run `lab run`" in out
    assert "no runner for M16" in out


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
