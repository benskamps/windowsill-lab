"""Behavioural fixtures for the campaign's conflict path — real clones, real rebases.

Every other campaign test is a static text pin. These drive the actual functions in
``scripts/campaign.sh`` against throwaway git clones, because the 2026-07-31 outage was
a *behaviour* nobody had exercised: two boxes publishing the same derived feeds, a
conflicted ``pull --rebase``, and a clone left stranded mid-rebase for four days.

The shape that actually occurred — per Loam's manual recovery — is BOTH ``pot.json``
and ``physics-latest.json`` conflicting on the same replay, so that is the fixture.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_SH = ROOT / "scripts" / "campaign.sh"

# Stands in for `lab.cli publish`: rebuilds both derived feeds as a pure function of
# the receipts on disk. That is the property the real generator has had since #66 and
# the only one resolve-by-regeneration depends on.
STUB_CLI = '''\
import json
import sys
from pathlib import Path


def main():
    if "publish" not in sys.argv:
        return 0
    root = Path.cwd()
    receipts = sorted(p.name for p in (root / "reports" / "receipts").glob("*.json"))
    for name, schema in (("pot.json", "pot/v5"), ("physics-latest.json", "physics/v2")):
        (root / name).write_text(
            json.dumps({"schema": schema, "receipts": receipts}, indent=1) + "\\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _working_bash():
    exe = shutil.which("bash")
    if exe is None:
        return None
    try:
        probe = subprocess.run([exe, "--version"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if probe.returncode != 0 or b"bash" not in probe.stdout.lower():
        return None
    return exe


def _git(repo, *args):
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=120
    )
    return proc


def _git_ok(repo, *args):
    proc = _git(repo, *args)
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


@pytest.fixture
def lab(tmp_path):
    """An origin plus two clones ('win' and 'loam'), wired to the stub generator."""
    if _working_bash() is None:
        pytest.skip("no working bash on PATH")
    if shutil.which("git") is None:
        pytest.skip("no git on PATH")

    stub = tmp_path / "stubpkg" / "lab"
    stub.mkdir(parents=True)
    (stub / "__init__.py").write_text("", encoding="utf-8")
    (stub / "cli.py").write_text(STUB_CLI, encoding="utf-8")

    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git_ok(origin, "init", "--bare", "--initial-branch=main")

    class Lab:
        def __init__(self):
            self.tmp = tmp_path
            self.origin = origin
            self.stubpath = str(tmp_path / "stubpkg")

        def clone(self, name):
            path = tmp_path / name
            _git_ok(tmp_path, "clone", str(origin), name)
            _git_ok(path, "config", "user.email", f"{name}@windowsill.test")
            _git_ok(path, "config", "user.name", f"{name}-box")
            _git_ok(path, "config", "pull.rebase", "true")
            return path

        def regenerate(self, repo):
            """Run the stub generator the way campaign.sh runs the real one."""
            env = dict(os.environ, PYTHONPATH=self.stubpath, PYTHONIOENCODING="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "lab.cli", "publish"],
                cwd=str(repo), env=env, capture_output=True, text=True, timeout=120,
            )
            assert proc.returncode == 0, proc.stderr
            return proc

        def publish(self, repo, receipt, push=True):
            """Add a receipt, rebuild both feeds from it, commit — the campaign's pass."""
            receipts = repo / "reports" / "receipts"
            receipts.mkdir(parents=True, exist_ok=True)
            (receipts / receipt).write_text(
                json.dumps({"run": receipt}), encoding="utf-8"
            )
            self.regenerate(repo)
            _git_ok(repo, "add", "-A")
            _git_ok(repo, "commit", "-m", f"campaign: pass 1 2026-08-01 seed=1001 ({receipt})")
            if push:
                _git_ok(repo, "push", "-q", "origin", "main")

        def source_and_run(self, repo, snippet):
            """Source campaign.sh in library mode and run `snippet` against `repo`."""
            home = self.tmp / f"home-{repo.name}"
            (home / ".lab").mkdir(parents=True, exist_ok=True)
            script = (
                'set -u\n'
                f'export HOME="{home.as_posix()}"\n'
                'export LAB_CAMPAIGN_LIB=1\n'
                f'export LAB_CAMPAIGN_REPO="{repo.as_posix()}"\n'
                f'export LAB_CAMPAIGN_PY="{Path(sys.executable).as_posix()}"\n'
                f'export PYTHONPATH="{self.stubpath}"\n'
                f'export LAB_CAMPAIGN_LOG="{(home / "campaign.log").as_posix()}"\n'
                f'export LAB_CAMPAIGN_STATE="{(home / "campaign.iter").as_posix()}"\n'
                f'. "{CAMPAIGN_SH.as_posix()}"\n'
                f'{snippet}\n'
            )
            proc = subprocess.run(
                [_working_bash(), "-c", script],
                capture_output=True, text=True, timeout=300,
            )
            log = home / "campaign.log"
            proc.campaign_log = log.read_text(encoding="utf-8") if log.exists() else ""
            return proc

    return Lab()


def _seed(lab):
    """A published origin with one receipt, and a second clone that has it."""
    win = lab.clone("win")
    lab.publish(win, "run-2026-07-30-m01.json")
    loam = lab.clone("loam")
    return win, loam


def _mid_rebase(repo):
    return (repo / ".git" / "rebase-merge").exists() or (
        repo / ".git" / "rebase-apply"
    ).exists()


def test_both_derived_feeds_conflicting_at_once_is_resolved_by_regeneration(lab):
    """The 2026-07-31 shape: pot.json AND physics-latest.json collide on one replay."""
    win, loam = _seed(lab)

    # Loam publishes and wins the race to origin.
    lab.publish(loam, "run-2026-08-01-loam-m01.json")
    # Win publishes the same pass locally; its push would be rejected, so it pulls.
    lab.publish(win, "run-2026-08-01-win-m01.json", push=False)

    # Precondition: this really is the both-files case, not a hypothetical.
    conflicted = _git(win, "pull", "--rebase")
    assert conflicted.returncode != 0
    unmerged = set(
        _git_ok(win, "diff", "--name-only", "--diff-filter=U").splitlines()
    )
    assert unmerged == {"pot.json", "physics-latest.json"}, unmerged
    _git_ok(win, "rebase", "--abort")

    proc = lab.source_and_run(win, 'safe_pull_rebase; echo "RC=$?"')

    assert "RC=0" in proc.stdout, f"{proc.stdout}\n{proc.stderr}\n{proc.campaign_log}"
    assert not _mid_rebase(win), "clone left mid-rebase"
    assert _git_ok(win, "rev-parse", "--abbrev-ref", "HEAD") == "main"

    # Neither side's copy was chosen: the feeds were rebuilt from the merged receipts.
    receipts = sorted(p.name for p in (win / "reports" / "receipts").glob("*.json"))
    assert receipts == [
        "run-2026-07-30-m01.json",
        "run-2026-08-01-loam-m01.json",
        "run-2026-08-01-win-m01.json",
    ], receipts
    for name in ("pot.json", "physics-latest.json"):
        feed = json.loads((win / name).read_text(encoding="utf-8"))
        assert feed["receipts"] == receipts, (name, feed)
        assert "<<<<<<<" not in (win / name).read_text(encoding="utf-8")

    assert _git_ok(win, "status", "--porcelain") == "", "worktree left dirty"
    assert "resolved by regeneration" in proc.campaign_log


def test_regenerated_result_is_committed_and_pushes_cleanly(lab):
    """Resolution ends in a commit, so nothing is left dangling for the next pass."""
    win, loam = _seed(lab)
    lab.publish(loam, "run-2026-08-01-loam-m01.json")
    lab.publish(win, "run-2026-08-01-win-m01.json", push=False)

    proc = lab.source_and_run(win, 'safe_pull_rebase; echo "RC=$?"')
    assert "RC=0" in proc.stdout, proc.campaign_log

    assert _git_ok(win, "push", "-q", "origin", "main") == ""
    # Loam pulls and lands on exactly the same tree — no divergence survives.
    _git_ok(loam, "pull", "--rebase")
    assert _git_ok(loam, "rev-parse", "HEAD") == _git_ok(win, "rev-parse", "HEAD")
    assert json.loads((loam / "pot.json").read_text(encoding="utf-8"))["receipts"] == [
        "run-2026-07-30-m01.json",
        "run-2026-08-01-loam-m01.json",
        "run-2026-08-01-win-m01.json",
    ]


def test_a_conflict_on_authored_content_is_refused_not_regenerated(lab):
    """Negative control: only the two derived feeds are auto-resolvable.

    A conflict in authored content must fail loudly and leave the clone usable and
    the local work intact — regeneration would silently destroy someone's edit.
    """
    win, loam = _seed(lab)

    for repo, text in ((loam, "loam edit\n"), (win, "win edit\n")):
        (repo / "README.md").write_text(text, encoding="utf-8")
        _git_ok(repo, "add", "-A")
        _git_ok(repo, "commit", "-m", f"docs: {repo.name} edit")
    _git_ok(loam, "push", "-q", "origin", "main")

    head_before = _git_ok(win, "rev-parse", "HEAD")
    proc = lab.source_and_run(win, 'safe_pull_rebase; echo "RC=$?"')

    assert "RC=1" in proc.stdout, f"{proc.stdout}\n{proc.campaign_log}"
    assert not _mid_rebase(win), "clone left mid-rebase after a refused conflict"
    assert _git_ok(win, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert _git_ok(win, "rev-parse", "HEAD") == head_before, "local work was discarded"
    assert (win / "README.md").read_text(encoding="utf-8") == "win edit\n"
    assert "not auto-resolving" in proc.campaign_log


def test_unpushed_commits_outside_the_owned_paths_block_the_hard_sync(lab):
    """Second control: the derived-feed conflict is resolvable, our own commit is not.

    Regeneration discards unpushed commits, so it must refuse when they carry work
    the campaign did not author — even though the conflict itself looks resolvable.
    """
    win, loam = _seed(lab)
    lab.publish(loam, "run-2026-08-01-loam-m01.json")
    lab.publish(win, "run-2026-08-01-win-m01.json", push=False)

    (win / "NOTES.md").write_text("hand-written, unpushed\n", encoding="utf-8")
    _git_ok(win, "add", "-A")
    _git_ok(win, "commit", "-m", "notes: something a human wrote")
    head_before = _git_ok(win, "rev-parse", "HEAD")

    proc = lab.source_and_run(win, 'safe_pull_rebase; echo "RC=$?"')

    assert "RC=1" in proc.stdout, f"{proc.stdout}\n{proc.campaign_log}"
    assert not _mid_rebase(win)
    assert _git_ok(win, "rev-parse", "HEAD") == head_before
    assert (win / "NOTES.md").exists(), "unpushed human work was destroyed"
    assert "outside the campaign's own" in proc.campaign_log


def test_counter_recovers_from_the_ledger_when_the_state_file_is_lost(lab):
    """The seed-reuse bug: a wiped ~/.lab must not restart the campaign at pass 1."""
    win = lab.clone("win")
    lab.publish(win, "run-2026-07-30-m01.json")
    for n in (47, 48, 49):
        (win / "pot.json").write_text(
            json.dumps({"schema": "pot/v5", "pass": n}), encoding="utf-8"
        )
        _git_ok(win, "commit", "-qam", f"campaign: pass {n} 2026-08-01 seed={1000 + n}")

    # No state file at all — the fresh-clone / restored-box case.
    proc = lab.source_and_run(win, 'echo "ITER=$iter"')
    assert "ITER=49" in proc.stdout, f"{proc.stdout}\n{proc.stderr}"
    assert "recovered from ledger" in proc.campaign_log


def test_counter_never_walks_backwards_from_a_stale_ledger(lab):
    """A state file ahead of the ledger still wins — the counter is monotonic."""
    win = lab.clone("win")
    lab.publish(win, "run-2026-07-30-m01.json")
    (win / "pot.json").write_text(
        json.dumps({"schema": "pot/v5", "pass": 12}), encoding="utf-8"
    )
    _git_ok(win, "commit", "-qam", "campaign: pass 12 2026-08-01 seed=1012")

    home = lab.tmp / "home-win"
    (home / ".lab").mkdir(parents=True, exist_ok=True)
    # newline="" so Windows does not write CRLF into a file the shell reads raw.
    (home / "campaign.iter").write_text("77\n", encoding="utf-8", newline="")

    proc = lab.source_and_run(win, 'echo "ITER=$iter"')
    assert "ITER=77" in proc.stdout, f"{proc.stdout}\n{proc.stderr}"
