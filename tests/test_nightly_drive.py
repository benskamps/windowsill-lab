"""AUTO-F7 — the generated win nightly, actually executed.

Unit-testing the generated string is necessary but not sufficient: loam's own
first cut of a comparable fix passed its string assertions and failed its dry
run. So these drive the REAL generated PowerShell against a throwaway clone with
a stubbed `lab`, then read the git ledger and the heartbeat.

Nothing here touches Task Scheduler — the scheduler's only job is to invoke this
script, and the script is what is under test.

Fail-before at 15f0cf6, all three cases (verbatim, docs/gauntlet/evidence/LANE4-SYMMETRY.md):
a FAILING `lab next` still committed "nightly: <date>", pushed it, and exited 0.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from lab import setup

PWSH = shutil.which("pwsh")

#: Stand-in for `lab.cli`. Dirties every nightly-owned path, THEN exits with the
#: code the harness asked for. Dirtying first is the point: it means a missing
#: commit can never be explained away as "nothing changed".
_STUB_CLI = r'''import os
import pathlib
import sys
import time

cmd = next((a for a in sys.argv[1:] if not a.startswith("-")), "")
stamp = f"{cmd} {time.time_ns()}\n"
for rel in ("pot.json", "physics-latest.json", "reports/latest.html"):
    p = pathlib.Path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(stamp, encoding="utf-8")
sys.exit(int(os.environ.get("STUB_RC_" + cmd.upper(), "0")))
'''


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(cwd), capture_output=True, text=True)


def _nightly_clone(tmp_path):
    """A clone on main carrying the three nightly-owned paths, with an origin it
    can actually push to — the shape the scheduled job wakes up to."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    subprocess.run(["git", "clone", str(origin), str(repo)],
                   capture_output=True, check=True)
    # Cloning an EMPTY repo leaves the local branch at the client's
    # init.defaultBranch, so name it here rather than assume.
    _git(repo, "checkout", "-B", "main")
    for key, val in (("user.email", "t@t"), ("user.name", "t"),
                     ("commit.gpgsign", "false")):
        _git(repo, "config", key, val)
    (repo / "reports").mkdir(exist_ok=True)
    for rel in ("pot.json", "physics-latest.json", "reports/latest.html"):
        (repo / rel).write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "push", "-u", "origin", "main")
    return repo


def _drive(tmp_path, repo, monkeypatch, **rcs):
    """Render the real generator against the throwaway clone and RUN it."""
    monkeypatch.setattr(setup, "REPO_ROOT", repo)
    monkeypatch.setattr(setup, "PY", sys.executable)
    script = tmp_path / "nightly.ps1"
    script.write_text(setup.nightly_ps1(), encoding="utf-8")

    stub = tmp_path / "stub" / "lab"
    stub.mkdir(parents=True, exist_ok=True)
    (stub / "__init__.py").write_text("", encoding="utf-8")
    (stub / "cli.py").write_text(_STUB_CLI, encoding="utf-8")

    log, state = tmp_path / "nightly.log", tmp_path / "state"
    env = {**os.environ,
           "PYTHONPATH": str(stub.parent),
           "LAB_NIGHTLY_LOG": str(log),
           "LAB_STATE_DIR": str(state),
           **{f"STUB_RC_{k.upper()}": str(v) for k, v in rcs.items()}}
    out = subprocess.run(
        [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)],
        cwd=str(repo), capture_output=True, text=True, env=env)
    return out, (log.read_text(encoding="utf-8") if log.exists() else ""), state


def _head(repo):
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _tracked_dirt(repo):
    return _git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip()


@pytest.mark.skipif(PWSH is None, reason="pwsh unavailable")
def test_win_nightly_writes_no_receipt_when_the_experiment_fails(tmp_path, monkeypatch):
    """A failed `lab next` must leave the ledger alone. Until 2026-08-22 the win
    template fell through to `lab publish` and the block below committed
    "nightly: <date>" regardless — a receipt, on main, for an experiment that
    never ran, pushed, exit 0. Loam has never done this (campaign.sh:283-301)."""
    repo = _nightly_clone(tmp_path)
    before = _head(repo)
    out, log, state = _drive(tmp_path, repo, monkeypatch, next=1)

    assert _head(repo) == before, "a failed run wrote a receipt:\n" + log
    assert out.returncode != 0, \
        "a failed run exited 0 — nothing watches a job that reports success"
    assert "FAILED" in log, log
    assert _tracked_dirt(repo) == "", "clone left dirty — the next run inherits it"
    assert not (state / "nightly.published").exists(), "heartbeat beat on a failed run"


@pytest.mark.skipif(PWSH is None, reason="pwsh unavailable")
def test_win_nightly_withholds_the_publish_when_verify_fails(tmp_path, monkeypatch):
    """The re-grade loam has had since campaign.sh:291 and win had not at all: a
    run whose result does not survive `lab verify` publishes nothing."""
    repo = _nightly_clone(tmp_path)
    before = _head(repo)
    out, log, state = _drive(tmp_path, repo, monkeypatch, next=0, verify=1)

    assert _head(repo) == before, "an ungraded run was published:\n" + log
    assert out.returncode != 0, log
    assert "WITHHELD" in log, log
    assert _tracked_dirt(repo) == "", "clone left dirty — the next run inherits it"
    assert not (state / "nightly.published").exists()


@pytest.mark.skipif(PWSH is None, reason="pwsh unavailable")
def test_win_nightly_publishes_and_beats_when_the_run_grades_clean(tmp_path, monkeypatch):
    """The happy path still works, and now leaves a heartbeat the estate watcher
    can go stale on. Loam's 26h no-publish stall — both units green, exit 0 —
    was caught ONLY because campaign.published stopped moving; win had no
    equivalent, so the same stall on this box would have been invisible."""
    repo = _nightly_clone(tmp_path)
    before = _head(repo)
    out, log, state = _drive(tmp_path, repo, monkeypatch, next=0, verify=0, publish=0)

    assert out.returncode == 0, log + out.stdout + out.stderr
    assert _head(repo) != before, "a clean run published nothing:\n" + log
    assert _git(repo, "log", "-1", "--pretty=%s").stdout.strip().startswith("nightly: ")
    assert _git(repo, "rev-parse", "origin/main").stdout.strip() == _head(repo)
    assert (state / "nightly.published").exists(), \
        "no heartbeat after a real publish:\n" + log


def test_both_nightly_templates_regrade_before_publishing():
    """Both generated jobs — not just the one whose box happened to be audited."""
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        assert "lab.cli verify" in script
        assert "WITHHELD" in script
        assert "nightly.published" in script
