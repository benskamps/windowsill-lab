"""Behavioural fixtures for the hunt slot's git side — real clones, real pushes.

``scripts/a05-hunt-slot.sh`` is the wrapper the timer fires four times a day. Its
two jobs are small and both failed SILENTLY in production on 2026-08-17/18, under a
systemd unit that stayed green the whole time:

* it staged with a glob that predated the runner's ``-HHMM`` receipt suffix, so only
  the day's FIRST slot ever matched — slots 2-4 wrote graded receipts that nothing
  staged, and ``git commit`` said "nothing to commit" and exited 0;
* it left the runner's in-place refresh of ``pot.json`` sitting dirty, and
  ``campaign.sh`` refuses to run against a dirty tracked file — so the survey lane
  quietly halted the physics lane for ~33h (campaign passes 119-124, never run).

The pot has two rules, not one, and they pull in opposite directions: a receipt
published WITHOUT its refreshed aggregate ships a red main (CI enforces
``pot == hunt_block()``), while a pot left dirty by a run that publishes NOTHING
halts the campaign. So a pushed receipt takes pot.json with it and every other exit
restores it — and an ungraded receipt leaves ``reports/hunts/`` entirely, because the
aggregator globs that directory and would otherwise count a run whose control failed.

Neither is visible to a static text pin, so these drive the real script against
throwaway clones with a stub runner standing in for ``scripts/a05_hunt.py``.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SLOT_SH = ROOT / "scripts" / "a05-hunt-slot.sh"

#: Stands in for the hunt driver: writes the receipt (and optionally a lead's
#: dossier), refreshes pot.json in place the way the real runner does, and prints
#: the two lines the wrapper reads back — the receipt path and the grade.
STUB_RUNNER = '''\
import json
import os
import sys
from pathlib import Path

root = Path.cwd()
receipt = root / "reports" / "hunts" / os.environ["STUB_RECEIPT"]
receipt.parent.mkdir(parents=True, exist_ok=True)
receipt.write_text(json.dumps({"experiment": "a05-survey-hunt", "schema": 1}), encoding="utf-8")

dossier = os.environ.get("STUB_DOSSIER")
if dossier:
    path = root / "reports" / "hunts" / "dossiers" / dossier
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<html>lead</html>", encoding="utf-8")

# The real runner rewrites pot.json's hunt block on every run, graded or not.
pot = root / "pot.json"
pot.write_text(json.dumps({"hunt": {"targets_searched": 4686}}), encoding="utf-8")

print(f"receipt -> {receipt}")
print(f"check_a05: {os.environ['STUB_GRADE']} — stub detail")
'''


def _git(repo, *args):
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


def _bash() -> str | None:
    """A POSIX bash that can actually run the slot script.

    On Windows, ``shutil.which("bash")`` resolves to System32's WSL stub, which
    answers with an RPC error unless a WSL distro is installed — prefer the bash
    that ships with Git, and skip rather than run the stub.
    """
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        for candidate in (program_files / "Git" / "bin" / "bash.exe",
                          program_files / "Git" / "usr" / "bin" / "bash.exe"):
            if candidate.exists():
                return str(candidate)
        return None
    return shutil.which("bash")


@pytest.fixture
def slot(tmp_path):
    """A bare origin, a clone wired to the stub runner, and a runnable slot script."""
    bash = _bash()
    if bash is None or shutil.which("git") is None:
        pytest.skip("needs bash and git on PATH")
    # Without flock the script's own lock line (`flock -n 9 || exit 0`) exits 0
    # having done NOTHING — every "nothing was pushed" assertion then passes
    # vacuously. Git Bash on Windows ships no flock; the slot only runs on loam.
    if subprocess.run([bash, "-c", "command -v flock"],
                      capture_output=True).returncode != 0:
        pytest.skip("the slot script needs flock (absent on Windows Git Bash; "
                    "the slot itself only ever runs on loam)")

    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main")

    repo = tmp_path / "loam"
    _git(tmp_path, "clone", str(origin), "loam")
    _git(repo, "config", "user.email", "loam@windowsill.test")
    _git(repo, "config", "user.name", "loam-box")
    (repo / "pot.json").write_text('{"hunt": {"targets_searched": 3882}}', encoding="utf-8")
    (repo / "reports" / "hunts").mkdir(parents=True)
    (repo / "reports" / "hunts" / ".keep").write_text("", encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "a05_hunt.py").write_text(STUB_RUNNER, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "push", "-q", "origin", "main")

    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "hunt.sector").write_text("3\n", encoding="utf-8")

    class Slot:
        def __init__(self):
            self.repo = repo
            self.origin = origin
            self.lab = lab

        def run(self, receipt, grade="True", dossier=None):
            env = {
                "PATH": os.environ["PATH"],
                "HOME": str(tmp_path),
                "LAB_HUNT_LAB": str(lab),
                "LAB_HUNT_REPO": str(repo),
                "LAB_HUNT_PY": sys.executable,
                "STUB_RECEIPT": receipt,
                "STUB_GRADE": grade,
            }
            if dossier:
                env["STUB_DOSSIER"] = dossier
            return subprocess.run(
                [bash, str(SLOT_SH)], env=env, capture_output=True, text=True, timeout=300
            )

        def pushed_files(self):
            return set(_git(repo, "ls-tree", "-r", "--name-only", "origin/main").splitlines())

        def is_clean(self):
            """The three conditions campaign.sh checks before it will run a pass."""
            staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--"], cwd=repo)
            worktree = subprocess.run(["git", "diff", "--quiet", "--"], cwd=repo)
            branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
            return staged.returncode == 0 and worktree.returncode == 0 and branch == "main"

    return Slot()


def test_a_suffixed_receipt_is_staged_and_pushed(slot):
    """Slot 2-4 of a day. The old glob matched only the bare name and lost these."""
    slot.run("hunt-2026-08-18-s3-1302.json")
    assert "reports/hunts/hunt-2026-08-18-s3-1302.json" in slot.pushed_files()


def test_the_days_first_receipt_still_pushes(slot):
    """The bare name the old glob DID match must keep working."""
    slot.run("hunt-2026-08-18-s3.json")
    assert "reports/hunts/hunt-2026-08-18-s3.json" in slot.pushed_files()


def test_a_lead_dossier_travels_with_its_receipt(slot):
    """A receipt cites its dossier; publishing one without the other strands the lead."""
    slot.run(
        "hunt-2026-08-18-s3-1302.json",
        dossier="hunt-2026-08-18-s3-1302-tic287328866.html",
    )
    pushed = slot.pushed_files()
    assert "reports/hunts/hunt-2026-08-18-s3-1302.json" in pushed
    assert "reports/hunts/dossiers/hunt-2026-08-18-s3-1302-tic287328866.html" in pushed


def test_an_ungraded_run_pushes_nothing(slot):
    """check_a05 None/False stays local with the log — win's contract."""
    before = slot.pushed_files()
    slot.run("hunt-2026-08-18-s3-1902.json", grade="None")
    assert slot.pushed_files() == before


def test_an_ungraded_receipt_is_kept_but_moved_out_of_the_ledger(slot):
    """The evidence survives; it just stops being counted. The aggregator globs
    reports/hunts/ rather than git, so a receipt left there is published by the
    next run that pushes, while CI recomputes from the committed set and goes red."""
    slot.run("hunt-2026-08-18-s3-1902.json", grade="None")
    assert not (slot.repo / "reports" / "hunts" / "hunt-2026-08-18-s3-1902.json").exists()
    assert (slot.lab / "ungraded" / "hunt-2026-08-18-s3-1902.json").exists()


def test_an_ungraded_run_leaves_the_clone_runnable(slot):
    """THE regression: an ungraded run used to leave pot.json dirty, and a dirty
    tracked file makes campaign.sh refuse every pass until a human clears it."""
    slot.run("hunt-2026-08-18-s3-1902.json", grade="None")
    assert slot.is_clean(), "campaign.sh would refuse to run against this clone"


def test_a_graded_run_leaves_the_clone_runnable(slot):
    """Same invariant on the push path."""
    slot.run("hunt-2026-08-18-s3-1302.json")
    assert slot.is_clean(), "campaign.sh would refuse to run against this clone"


def test_a_receipt_is_published_with_its_refreshed_aggregate(slot):
    """CI enforces pot == hunt_block(), so a receipt whose commit leaves the pot
    behind ships a red main in the producer's own commit."""
    slot.run("hunt-2026-08-18-s3-1302.json")
    committed = _git(slot.repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert "pot.json" in committed
    assert "reports/hunts/hunt-2026-08-18-s3-1302.json" in committed
    assert "4686" in _git(slot.repo, "show", "origin/main:pot.json")
