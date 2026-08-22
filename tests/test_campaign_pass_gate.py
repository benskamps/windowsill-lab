"""The campaign pass gate: what a FAILED pass is allowed to publish.

``tests/test_campaign_conflict.py`` drives ``campaign.sh``'s functions in library
mode (``LAB_CAMPAIGN_LIB=1``). This drives the LOOP itself — one real pass, against a
throwaway clone and a stub ``lab.cli`` — because the failure-masquerade lives in the
loop body, not in any function.

The shape (AUTO-F3): when ``lab next`` fails, the pass logged
"experiment failed; refreshing existing feed only", left ``publishable=1``, staged
``pot.json``, ``physics-latest.json`` and ``git add -A -- reports/``, and committed
under ``campaign: pass N <date> seed=S`` — a message **indistinguishable from a
successful pass**. The ``verify`` re-grade ran only on the SUCCEEDED path, so nothing
re-checked what was published, and ``add -A`` swept whatever partial artifacts the
failed run had already written into that commit.

The ledger is read back out of these commit messages (the counter recovers from it),
and the public feed is regenerated from what lands here. A failed pass that commits
under a success message corrupts both.

No real remote, no real ``lab`` package, no systemd unit is touched.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_SH = ROOT / "scripts" / "campaign.sh"

#: Stands in for ``lab.cli``. ``next`` runs the experiment (and can fail the way the
#: real one does — after writing something); ``publish`` rebuilds the derived feeds as
#: a pure function of the receipts; ``verify`` re-grades. Both failure modes are env
#: knobs so one fixture covers the whole matrix.
STUB_CLI = '''\
import json
import os
import sys
from pathlib import Path


def main():
    argv = sys.argv[1:]
    root = Path.cwd()

    if "next" in argv:
        rc = int(os.environ.get("STUB_NEXT_RC", "0"))
        reports = root / "reports"
        (reports / "receipts").mkdir(parents=True, exist_ok=True)
        if rc != 0:
            # A real `lab next` does not fail atomically: it fails PART WAY THROUGH,
            # with artifacts already on disk. `git add -A -- reports/` sweeps them.
            (reports / "receipts" / "run-partial.json").write_text(
                '{"run": "half-writ', encoding="utf-8")
            (reports / "scratch-from-the-failed-run.txt").write_text(
                "torn output", encoding="utf-8")
            print("stub: next FAILED after writing partial artifacts",
                  file=sys.stderr)
            return rc
        seed = argv[argv.index("--seed") + 1] if "--seed" in argv else "0"
        (reports / "receipts" / f"run-seed{seed}.json").write_text(
            json.dumps({"run": f"seed{seed}"}), encoding="utf-8")
        return 0

    if "publish" in argv:
        receipts = sorted(p.name for p in (root / "reports" / "receipts").glob("*.json"))
        for name, schema in (("pot.json", "pot/v5"),
                             ("physics-latest.json", "physics/v2")):
            (root / name).write_text(
                json.dumps({"schema": schema, "receipts": receipts}, indent=1) + "\\n",
                encoding="utf-8")
        return 0

    if "verify" in argv:
        return int(os.environ.get("STUB_VERIFY_RC", "0"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _bash():
    """A POSIX bash that can run campaign.sh (System32's WSL stub cannot)."""
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        for candidate in (program_files / "Git" / "bin" / "bash.exe",
                          program_files / "Git" / "usr" / "bin" / "bash.exe"):
            if candidate.exists():
                return str(candidate)
        return None
    return shutil.which("bash")


def _git(repo, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, timeout=120)
    if check:
        assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


class Campaign:
    def __init__(self, tmp_path, repo, origin, home, stubpath, bash):
        self.tmp_path, self.repo, self.origin = tmp_path, repo, origin
        self.home, self.stubpath, self.bash = home, stubpath, bash

    def run_pass(self, next_rc=0, verify_rc=0, seed_base=1000):
        """One real pass of the loop. MAX_ITERS=1 exits before any sleep."""
        env = dict(os.environ,
                   HOME=str(self.home),
                   PYTHONPATH=self.stubpath,
                   PYTHONIOENCODING="utf-8",
                   LAB_CAMPAIGN_REPO=str(self.repo),
                   LAB_CAMPAIGN_PY=sys.executable,
                   LAB_CAMPAIGN_LOG=str(self.home / "campaign.log"),
                   LAB_CAMPAIGN_STATE=str(self.home / "campaign.iter"),
                   LAB_CAMPAIGN_DEVICE="cpu",
                   LAB_CAMPAIGN_SEED=str(seed_base),
                   LAB_CAMPAIGN_MAX_ITERS="1",
                   LAB_CAMPAIGN_INTERVAL="1",
                   STUB_NEXT_RC=str(next_rc),
                   STUB_VERIFY_RC=str(verify_rc))
        env.pop("LAB_CAMPAIGN_HOURS", None)
        env.pop("LAB_CAMPAIGN_DRY", None)
        proc = subprocess.run([self.bash, str(CAMPAIGN_SH)], env=env,
                              capture_output=True, text=True, timeout=300)
        log = self.home / "campaign.log"
        proc.campaign_log = log.read_text(encoding="utf-8") if log.exists() else ""
        return proc

    # -- what the ledger and the next pass actually see -----------------------
    def head_subject(self):
        return _git(self.repo, "log", "-1", "--format=%s")

    def commit_count(self):
        return int(_git(self.repo, "rev-list", "--count", "HEAD"))

    def files_at_head(self):
        return set(_git(self.repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines())

    def pushed_files(self):
        return set(_git(self.repo, "ls-tree", "-r", "--name-only",
                        "origin/main").splitlines())

    def is_runnable(self):
        """The guards campaign.sh itself checks at the top of every pass."""
        staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--"],
                                cwd=self.repo)
        worktree = subprocess.run(["git", "diff", "--quiet", "--"], cwd=self.repo)
        branch = _git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        return (staged.returncode == 0 and worktree.returncode == 0
                and branch == "main")

    def heartbeat(self):
        return (self.home / "campaign.published").exists()


@pytest.fixture
def campaign(tmp_path):
    bash = _bash()
    if bash is None or shutil.which("git") is None:
        pytest.skip("needs bash and git on PATH")

    stub = tmp_path / "stubpkg" / "lab"
    stub.mkdir(parents=True)
    (stub / "__init__.py").write_text("", encoding="utf-8")
    (stub / "cli.py").write_text(STUB_CLI, encoding="utf-8")

    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main")

    repo = tmp_path / "loam"
    _git(tmp_path, "clone", str(origin), "loam")
    _git(repo, "config", "user.email", "loam@windowsill.test")
    _git(repo, "config", "user.name", "loam-box")
    _git(repo, "config", "pull.rebase", "true")
    (repo / "pot.json").write_text(
        json.dumps({"schema": "pot/v5", "receipts": []}, indent=1) + "\n",
        encoding="utf-8")
    (repo / "physics-latest.json").write_text(
        json.dumps({"schema": "physics/v2", "receipts": []}, indent=1) + "\n",
        encoding="utf-8")
    (repo / "reports" / "receipts").mkdir(parents=True)
    (repo / "reports" / "receipts" / ".keep").write_text("", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "push", "-q", "origin", "main")

    home = tmp_path / "home"
    (home / ".lab").mkdir(parents=True)
    return Campaign(tmp_path, repo, origin, home, str(tmp_path / "stubpkg"), bash)


# --- AUTO-F3: a failed experiment publishes nothing ---------------------------

def test_a_failed_experiment_produces_no_commit(campaign):
    """THE finding. A failed `lab next` used to commit under
    `campaign: pass N <date> seed=S` — the same message a successful pass writes."""
    before = campaign.commit_count()
    campaign.run_pass(next_rc=1)
    assert campaign.commit_count() == before, (
        f"a failed pass committed: {campaign.head_subject()!r}")


def test_a_failed_experiment_never_writes_a_success_shaped_message(campaign):
    """The ledger is read back out of these subjects — the pass counter recovers
    from them. A failure wearing a success's message corrupts the ledger, not just
    the feed."""
    campaign.run_pass(next_rc=1)
    assert not campaign.head_subject().startswith("campaign: pass 1 ")


def test_a_failed_experiment_does_not_sweep_its_partial_artifacts(campaign):
    """`git add -A -- reports/` is indiscriminate, and a real `lab next` fails part
    way through with artifacts already on disk."""
    campaign.run_pass(next_rc=1)
    committed = campaign.files_at_head()
    assert "reports/receipts/run-partial.json" not in committed
    assert "reports/scratch-from-the-failed-run.txt" not in committed


def test_a_failed_experiment_leaves_the_clone_runnable(campaign):
    """Same lesson as the hunt slot: campaign.sh refuses to run a pass against a
    staged index or a dirty tracked file, so a failed pass that leaves either one
    halts the lane until a human clears it."""
    campaign.run_pass(next_rc=1)
    assert campaign.is_runnable()


def test_a_failed_experiment_does_not_touch_the_published_heartbeat(campaign):
    """`campaign.published` is what the estate watcher reads for freshness."""
    campaign.run_pass(next_rc=1)
    assert not campaign.heartbeat()


# --- the over-correction fence: success and verify-failure are unchanged -------

def test_a_successful_pass_still_commits_and_publishes(campaign):
    before = campaign.commit_count()
    campaign.run_pass()
    assert campaign.commit_count() == before + 1
    assert campaign.head_subject().startswith("campaign: pass 1 ")
    assert "reports/receipts/run-seed1001.json" in campaign.pushed_files()
    assert campaign.heartbeat()


def test_a_failed_verify_still_withholds_the_commit(campaign):
    """Pre-existing behaviour this change must not disturb: a red re-grade
    withholds the publish and restores the campaign-owned paths."""
    before = campaign.commit_count()
    campaign.run_pass(verify_rc=1)
    assert campaign.commit_count() == before
    assert campaign.is_runnable()
    assert not campaign.heartbeat()
