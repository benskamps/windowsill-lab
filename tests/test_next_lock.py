"""`lab next` run lock — one turn per box, and a skipped slot is a healthy outcome.

The incident this locks in (2026-08-02): the scheduled task carried
``ExecutionTimeLimit PT2H`` on the theory that it prevented slot overlap. The
12:00 slot dispatched M02 (a legitimate ~4.5h GPU milestone); at 14:00 Task
Scheduler killed the powershell wrapper with 0x41306 and the ``python -m lab.cli
next`` CHILD survived — so the limit neither stopped the work nor prevented an
overlap, it only orphaned the logger. Overlap prevention belongs here, in the
process that actually knows whether a turn is running.

Torch-free: every test monkeypatches ``cli.LAB_HOME`` to ``tmp_path`` and stubs
the liveness probe, so nothing here ever touches the live ``~/.lab`` or reads a
real process table.
"""
import json

import pytest

import lab.cli as cli


@pytest.fixture
def lab_home(tmp_path, monkeypatch):
    home = tmp_path / "lab-home"
    home.mkdir()
    monkeypatch.setattr(cli, "LAB_HOME", home)
    return home


def _write_lock(lab_home, pid, started="2026-08-02T12:00:00+00:00", milestone=None):
    path = lab_home / "next.lock"
    path.write_text(
        json.dumps({"pid": pid, "started": started, "milestone": milestone}),
        encoding="utf-8",
    )
    return path


# ── acquire / release ─────────────────────────────────────────────────────────

def test_lock_is_held_during_the_turn_and_released_after(lab_home):
    """The lock exists while the body runs, carries this process's identity, and
    is gone once the turn finishes — no manual cleanup, no wedged next slot."""
    path = lab_home / "next.lock"
    assert not path.exists()
    with cli.next_run_lock() as held:
        assert held == path
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pid"] == cli.os.getpid()
        assert payload["started"].endswith("+00:00")
        assert payload["milestone"] is None
    assert not path.exists()


def test_lock_records_the_milestone_once_selection_knows_it(lab_home):
    """The milestone is only known after selection runs, so the lock is stamped
    with it mid-turn — a human reading next.lock should see WHAT is running."""
    path = lab_home / "next.lock"
    with cli.next_run_lock() as held:
        cli.note_lock_milestone(held, "M02")
        assert json.loads(path.read_text(encoding="utf-8"))["milestone"] == "M02"


def test_lock_is_released_when_the_turn_raises(lab_home):
    """A crashing runner must not leave a lock behind — otherwise one bad turn
    silently disables the scheduler until someone notices."""
    path = lab_home / "next.lock"
    with pytest.raises(RuntimeError):
        with cli.next_run_lock():
            assert path.exists()
            raise RuntimeError("runner blew up")
    assert not path.exists()


# ── contention ────────────────────────────────────────────────────────────────

def test_live_holder_makes_acquire_raise_lock_busy(lab_home, monkeypatch):
    """A lock owned by a LIVE python process is honored: the second turn refuses
    to start rather than racing the GPU and the repo."""
    _write_lock(lab_home, 4242, milestone="M02")
    monkeypatch.setattr(cli, "_process_is_live_python", lambda pid: pid == 4242)
    with pytest.raises(cli.LockBusy) as excinfo:
        with cli.next_run_lock():
            pytest.fail("acquired a lock held by a live process")
    assert excinfo.value.pid == 4242
    assert excinfo.value.started == "2026-08-02T12:00:00+00:00"
    # The holder's lock survives — the loser never clears someone else's turn.
    assert (lab_home / "next.lock").exists()


def test_next_skips_the_slot_when_another_turn_is_running(lab_home, monkeypatch, capsys):
    """End of the incident: the 18:00 slot arriving while M02 still runs prints one
    honest line and exits 0. A skipped slot is a healthy outcome, not an error —
    a nonzero exit would light up Task Scheduler's LastTaskResult for nothing."""
    _write_lock(lab_home, 4242)
    monkeypatch.setattr(cli, "_process_is_live_python", lambda pid: pid == 4242)
    ran = []
    monkeypatch.setattr(cli, "_run_next", lambda *a, **k: ran.append(a) or 0)

    rc = cli.main(["next"])

    out = capsys.readouterr().out
    assert rc == 0
    assert ran == []                                   # no work was dispatched
    assert "another turn is running (pid 4242" in out
    assert "skipping this slot" in out


def test_stale_lock_from_a_dead_pid_is_taken_over(lab_home, monkeypatch, capsys):
    """A lock left by a killed turn (or a reboot) must not wedge the scheduler
    forever: the dead pid is noted in the log and the new turn takes the lock."""
    _write_lock(lab_home, 999999, started="2026-08-01T00:00:00+00:00")
    monkeypatch.setattr(cli, "_process_is_live_python", lambda pid: False)

    with cli.next_run_lock() as held:
        assert json.loads(held.read_text(encoding="utf-8"))["pid"] == cli.os.getpid()

    out = capsys.readouterr().out
    assert "stale lock" in out and "999999" in out


def test_unreadable_lock_is_treated_as_stale(lab_home, monkeypatch, capsys):
    """A truncated/corrupt lock (power loss mid-write) names no live owner, so it
    is stale by definition — fail toward running, not toward a silent standstill."""
    (lab_home / "next.lock").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(cli, "_process_is_live_python", lambda pid: True)

    with cli.next_run_lock() as held:
        assert json.loads(held.read_text(encoding="utf-8"))["pid"] == cli.os.getpid()
    assert "stale lock" in capsys.readouterr().out


# ── the command surface ───────────────────────────────────────────────────────

def test_dry_run_takes_no_lock(lab_home, monkeypatch):
    """`lab next --dry-run` runs nothing, so it neither claims the lock nor is
    blocked by one — it stays a diagnostic you can run while a turn is live."""
    _write_lock(lab_home, 4242)
    monkeypatch.setattr(cli, "_process_is_live_python", lambda pid: pid == 4242)
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M01", "status": "verified"},
        {"id": "M12", "status": "open"},
    ])

    rc = cli.main(["next", "--dry-run"])

    assert rc == 0
    # The live holder's lock is untouched by a dry run.
    assert json.loads((lab_home / "next.lock").read_text(encoding="utf-8"))["pid"] == 4242


def test_next_holds_the_lock_across_the_dispatched_runner(lab_home, monkeypatch, capsys):
    """The lock must cover the RUN, not just selection — that is the whole point.
    We stub the dispatched subcommand and assert the lock is held from inside it."""
    from lab import publish as publish_mod
    monkeypatch.setattr(publish_mod, "parse_milestones", lambda _text: [
        {"id": "M11", "status": "verified"},
        {"id": "M12", "status": "open"},
    ])
    seen = {}
    real_main = cli.main

    def fake_main(argv):
        if argv and argv[0] == "m12":
            payload = json.loads((lab_home / "next.lock").read_text(encoding="utf-8"))
            seen.update(payload)
            return 0
        return real_main(argv)

    monkeypatch.setattr(cli, "main", fake_main)

    rc = real_main(["next"])

    assert rc == 0
    assert seen["pid"] == cli.os.getpid()
    assert seen["milestone"] == "M12"           # stamped before dispatch
    assert not (lab_home / "next.lock").exists()
    assert "running `lab m12`" in capsys.readouterr().out


def test_process_probe_says_this_process_is_a_live_python():
    """The real probe (no stubs): our own pid is alive and is a python process.
    Guards the ctypes/psutil branch from silently returning False on Windows,
    which would make every lock look stale and defeat the whole mechanism."""
    assert cli._process_is_live_python(cli.os.getpid()) is True


def test_process_probe_rejects_an_impossible_pid():
    assert cli._process_is_live_python(-1) is False
