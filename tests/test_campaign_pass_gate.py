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

    if "selftest" in argv:
        # The real one runs pytest, writes a SCRATCH record under LAB_HOME, and
        # — on the ONE pass per UTC day it is due — files its verdict as a
        # committed receipt under reports/receipts/, because ~/.lab is box-local
        # and a verdict that never leaves the box is one the shared feed cannot
        # carry. Not-due is the common case (a box takes ~4 passes a day), so
        # the default here writes nothing; STUB_SELFTEST_RECEIPT stands in for
        # the due pass.
        rc = int(os.environ.get("STUB_SELFTEST_RC", "0"))
        if os.environ.get("STUB_SELFTEST_RECEIPT"):
            receipts = root / "reports" / "receipts"
            receipts.mkdir(parents=True, exist_ok=True)
            (receipts / "selftest-2026-09-04-0312-linux-rocm.json").write_text(
                json.dumps({"schema": "windowsill.selftest-receipt.v1",
                            "selftest": {"status": "fail" if rc else "pass"}}),
                encoding="utf-8")
        return rc

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

    def run_pass(self, next_rc=0, verify_rc=0, selftest_rc=0, seed_base=1000,
                 selftest_receipt=False, dry=False):
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
                   STUB_VERIFY_RC=str(verify_rc),
                   STUB_SELFTEST_RC=str(selftest_rc),
                   STUB_SELFTEST_RECEIPT="1" if selftest_receipt else "")
        env.pop("LAB_CAMPAIGN_HOURS", None)
        env.pop("LAB_CAMPAIGN_DRY", None)
        if dry:
            env["LAB_CAMPAIGN_DRY"] = "1"
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


def test_a_red_test_suite_never_costs_the_pass_its_publish(campaign):
    """The loam twin of the win drive test — the pytest turn cannot withhold.

    ``lab next`` and ``lab verify`` are the science gates and they withhold; the
    suite runs AFTER the commit and push and answers a different question. The
    string pins in test_campaign_maturity.py say ``withhold_pass`` is not
    reachable from the tail; this proves it by failing the step for real and
    reading the ledger, the heartbeat and the loop's own exit status back out.
    """
    before = campaign.commit_count()
    proc = campaign.run_pass(selftest_rc=1)

    assert proc.returncode == 0, proc.campaign_log
    assert campaign.commit_count() == before + 1, \
        "a red suite unpublished a run that graded clean:\n" + proc.campaign_log
    assert campaign.head_subject().startswith("campaign: pass 1 ")
    assert "reports/receipts/run-seed1001.json" in campaign.pushed_files()
    assert campaign.heartbeat(), "a red suite swallowed the freshness heartbeat"
    assert campaign.is_runnable(), "a red suite left the clone unrunnable — lane frozen"
    assert "selftest reported a FAILURE" in proc.campaign_log
    assert "publish above stands" in proc.campaign_log


def test_the_test_verdict_reaches_the_committed_ledger(campaign):
    """The verdict has to LEAVE THE BOX, and only a commit does that.

    pot.json's `tests` block is a per-machine map derived from the committed
    selftest receipts — the same shape and the same source as
    turns.last_by_machine — precisely because the box-local file it used to be
    derived from is ONE mutable slot two machines both write, where one box's
    red suite is erased by the other's green within hours.

    Nothing else in the pass stages this receipt: `git add -A -- reports/` ran
    before the selftest step, so without its own commit it sits untracked until
    a later pass sweeps it — or until `withhold_pass` runs
    `git clean -qfd -- reports/` and deletes it.
    """
    proc = campaign.run_pass(selftest_receipt=True)
    receipt = "reports/receipts/selftest-2026-09-04-0312-linux-rocm.json"
    assert receipt in campaign.files_at_head(), \
        "the test verdict never reached the ledger:\n" + proc.campaign_log
    assert receipt in campaign.pushed_files(), \
        "the test verdict was committed but never pushed:\n" + proc.campaign_log
    assert campaign.is_runnable(), "the receipt commit left the clone dirty"


def test_the_receipt_commit_touches_nothing_but_the_receipts_directory(campaign):
    """It runs after the science commit and must not be able to move the feed.

    A commit that could reach pot.json here would be a second, ungraded
    publisher of the science feed sitting in the pass's tail.
    """
    campaign.run_pass(selftest_receipt=True)
    subject = campaign.head_subject()
    assert subject.startswith("selftest: "), subject
    touched = _git(campaign.repo, "show", "--name-only", "--format=", "HEAD").split()
    assert touched == ["reports/receipts/selftest-2026-09-04-0312-linux-rocm.json"], touched


def test_a_withheld_science_pass_still_files_its_test_verdict(campaign):
    """The two signals are independent, and this is the erasure hole it closes.

    A refused pass runs `withhold_pass`, which ends in
    `git clean -qfd -- reports/`. An untracked selftest receipt sitting there is
    collateral — the verdict deleted before anything could read it. The selftest
    step runs after the withhold and commits its own receipt, so a refused
    science run and a green suite stay two facts rather than collapsing into one.
    """
    before = campaign.commit_count()
    proc = campaign.run_pass(verify_rc=1, selftest_receipt=True)
    assert "verify failed; publishing withheld" in proc.campaign_log
    assert campaign.commit_count() == before + 1, \
        "the withheld pass swallowed the test verdict too:\n" + proc.campaign_log
    assert campaign.head_subject().startswith("selftest: ")
    assert "reports/receipts/selftest-2026-09-04-0312-linux-rocm.json" in \
        campaign.files_at_head()
    # ...and the science feed is still exactly where the withhold left it.
    assert "reports/receipts/run-seed1001.json" not in campaign.files_at_head()


def test_a_not_due_pass_commits_nothing_extra(campaign):
    """The common case: ~3 of every 4 passes are not this box's test turn.

    The receipt commit must be silent then — no empty commit, no ledger noise,
    nothing for the next pass's "pre-existing staged changes" guard to trip on.
    """
    before = campaign.commit_count()
    campaign.run_pass()                       # not due ⇒ no receipt written
    assert campaign.commit_count() == before + 1     # the science pass only
    assert campaign.head_subject().startswith("campaign: pass 1 ")
    assert campaign.is_runnable()


def test_a_failed_verify_still_withholds_the_commit(campaign):
    """Pre-existing behaviour this change must not disturb: a red re-grade
    withholds the publish and restores the campaign-owned paths."""
    before = campaign.commit_count()
    campaign.run_pass(verify_rc=1)
    assert campaign.commit_count() == before
    assert campaign.is_runnable()
    assert not campaign.heartbeat()


# --- the review's two: DRY stays local, and a failed receipt commit unwedges ---

def test_a_dry_pass_never_pushes_the_test_verdict(campaign):
    """`LAB_CAMPAIGN_DRY` is documented at the top of campaign.sh as
    "run+render locally, leave unstaged, skip commit/push".

    The science path honours it by resetting what it staged. The selftest step
    was added AFTER that branch, outside it — so a dry pass would git add,
    commit and PUSH a receipt to origin/main out of a run whose entire contract
    is that it publishes nothing.
    """
    before = campaign.commit_count()
    proc = campaign.run_pass(selftest_receipt=True, dry=True)
    assert campaign.commit_count() == before, (
        "a DRY pass committed:\n" + proc.campaign_log)
    assert not any(f.startswith("reports/receipts/selftest-")
                   for f in campaign.pushed_files()), campaign.pushed_files()
    assert campaign.is_runnable(), "a DRY pass left the clone unrunnable"


def test_a_receipt_commit_that_fails_leaves_the_lane_runnable(campaign):
    """The wedge. `git add` stages the receipt; if the commit then fails, the
    index stays loaded — and this loop's own top-of-pass guard treats a loaded
    index as a reason to skip the ENTIRE pass ("refusing to run or alter the
    index"), every pass, forever. One failed commit would silently halt the
    science lane; the science commit's own failure path resets for exactly this
    reason, and this step must too.

    Driven with a pre-commit hook that rejects only the receipt-only commit —
    the most likely real cause (a hook, a signing key, a locked index).
    """
    hooks = campaign.repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-commit").write_text(
        "#!/bin/sh\n"
        "git diff --cached --name-only | grep -q 'receipts/selftest-' && exit 1\n"
        "exit 0\n",
        encoding="utf-8", newline="\n")
    (hooks / "pre-commit").chmod(0o755)

    proc = campaign.run_pass(selftest_receipt=True)
    assert "could not be committed" in proc.campaign_log, proc.campaign_log
    assert campaign.is_runnable(), (
        "a failed receipt commit left the index loaded — the next pass will "
        "refuse to run at all:\n" + proc.campaign_log)
    staged = _git(campaign.repo, "diff", "--cached", "--name-only")
    assert staged == "", f"still staged: {staged!r}"
