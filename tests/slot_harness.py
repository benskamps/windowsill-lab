"""Shared rig for driving ``scripts/a05-hunt-slot.sh`` against throwaway clones.

``tests/test_hunt_slot_script.py`` grew its own copy of this while proving the
staging and pot rules; the gate tests (``test_hunt_slot_gates.py``) need the same
rig plus fault injection, so the pieces live here rather than in two places.

Two seams matter and both are honest about what they simulate:

* **flock.** The slot opens fd 9 on ``$LAB/hunt.lock`` and ``flock -n 9 || exit 0``.
  Git Bash on Windows ships no ``flock``, so the line exits 0 having done NOTHING
  and every "nothing was pushed" assertion passes vacuously. Where the real binary
  is missing we put an always-succeeds shim on PATH: it makes the REST of the
  script run for real on this box. It does not simulate contention, so no test
  here asserts anything about the lock itself.
* **hooks.** A failing ``pre-commit`` hook is a real ``git commit`` failure with the
  index left staged — the same shape as losing the index.lock race to
  ``campaign.sh``, without stubbing git.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SLOT_SH = ROOT / "scripts" / "a05-hunt-slot.sh"

#: Stands in for ``scripts/a05_hunt.py``. Writes the receipt (and optionally a
#: lead dossier), refreshes pot.json in place the way the real runner does, and
#: prints the two lines the wrapper reads back. The fault knobs reproduce the
#: production shapes: a crash after the receipt is on disk but before it is
#: graded, and extra chatter that scrolls the grade line out of a tail window.
STUB_RUNNER = '''\
import json
import os
import sys
from pathlib import Path

root = Path.cwd()
Path(os.environ["STUB_RAN_MARKER"]).write_text("ran", encoding="utf-8")

receipt = root / "reports" / "hunts" / os.environ["STUB_RECEIPT"]
receipt.parent.mkdir(parents=True, exist_ok=True)
receipt.write_text(json.dumps({"experiment": "a05-survey-hunt", "schema": 1}),
                   encoding="utf-8")

dossier = os.environ.get("STUB_DOSSIER")
if dossier:
    path = root / "reports" / "hunts" / "dossiers" / dossier
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<html>lead</html>", encoding="utf-8")

print(f"receipt -> {receipt}")

pot = root / "pot.json"
if os.environ.get("STUB_CRASH_AFTER_RECEIPT"):
    # The 100-minute hunt died between writing its receipt and grading it: no
    # grade line was ever printed and pot.json was never refreshed.
    print("Traceback (most recent call last):", file=sys.stderr)
    print("MemoryError", file=sys.stderr)
    sys.exit(1)

pot.write_text(json.dumps({"hunt": {"targets_searched": 4686}}), encoding="utf-8")
print(f"check_a05: {os.environ['STUB_GRADE']} - stub detail")
for line in range(int(os.environ.get("STUB_TRAILING_LINES", "0"))):
    print(f"pot hunt block refreshed step {line}")
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
'''


def git(repo, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, timeout=120)
    if check:
        assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


def bash_path() -> str | None:
    """A POSIX bash that can actually run the slot script.

    On Windows ``shutil.which("bash")`` resolves to System32's WSL stub, which
    answers with an RPC error unless a distro is installed - prefer Git's bash.
    """
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        for candidate in (program_files / "Git" / "bin" / "bash.exe",
                          program_files / "Git" / "usr" / "bin" / "bash.exe"):
            if candidate.exists():
                return str(candidate)
        return None
    return shutil.which("bash")


def shim_path(bash: str, tmp_path: Path) -> str:
    """PATH with a no-op ``flock`` prepended where the real one is missing."""
    path = os.environ["PATH"]
    have_flock = subprocess.run([bash, "-c", "command -v flock"],
                                capture_output=True).returncode == 0
    if have_flock:
        return path
    shims = tmp_path / "shims"
    shims.mkdir(exist_ok=True)
    (shims / "flock").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (shims / "flock").chmod(0o755)
    return f"{shims}{os.pathsep}{path}"


class Slot:
    """One clone, one origin, one runnable slot script."""

    def __init__(self, bash, tmp_path, repo, origin, lab):
        self.bash, self.tmp_path = bash, tmp_path
        self.repo, self.origin, self.lab = repo, origin, lab
        self.ran_marker = tmp_path / "runner-ran"

    def run(self, receipt, grade="True", dossier=None, crash_after_receipt=False,
            trailing_lines=0, exit_code=0):
        self.ran_marker.unlink(missing_ok=True)
        env = {
            "PATH": shim_path(self.bash, self.tmp_path),
            "HOME": str(self.tmp_path),
            "LAB_HUNT_LAB": str(self.lab),
            "LAB_HUNT_REPO": str(self.repo),
            "LAB_HUNT_PY": sys.executable,
            "STUB_RECEIPT": receipt,
            "STUB_GRADE": grade,
            "STUB_RAN_MARKER": str(self.ran_marker),
            "STUB_TRAILING_LINES": str(trailing_lines),
            "STUB_EXIT": str(exit_code),
            # The slot backs off between index.lock retries; tests do not wait.
            "LAB_HUNT_COMMIT_SLEEP": "0",
        }
        if dossier:
            env["STUB_DOSSIER"] = dossier
        if crash_after_receipt:
            env["STUB_CRASH_AFTER_RECEIPT"] = "1"
        return subprocess.run([self.bash, str(SLOT_SH)], env=env,
                              capture_output=True, text=True, timeout=300)

    # -- observations the production incidents were graded on -----------------
    def hunt_ran(self) -> bool:
        """Did the 100-minute hunt actually burn, or was the slot refused first?"""
        return self.ran_marker.exists()

    def pushed_files(self) -> set[str]:
        return set(git(self.repo, "ls-tree", "-r", "--name-only",
                       "origin/main").splitlines())

    def branch(self) -> str:
        return git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")

    def is_clean(self) -> bool:
        """The three conditions campaign.sh checks before it will run a pass."""
        staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--"],
                                cwd=self.repo)
        worktree = subprocess.run(["git", "diff", "--quiet", "--"], cwd=self.repo)
        return (staged.returncode == 0 and worktree.returncode == 0
                and self.branch() == "main")

    def log_text(self) -> str:
        return "\n".join(p.read_text(encoding="utf-8")
                         for p in sorted(self.lab.glob("hunt-s*.log")))

    def break_commit(self, fail_times=None):
        """A real ``git commit`` failure that leaves the index staged - the shape
        of losing the index.lock race to campaign.sh, with no git stubbing.

        ``fail_times`` makes the contention TRANSIENT: the hook refuses that many
        commits and then lets one through, which is what losing the race to a
        campaign pass actually looks like. Omit it for permanent failure.
        """
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "pre-commit"
        limit = "" if fail_times is None else str(fail_times)
        hook.write_text(
            "#!/usr/bin/env bash\n"
            f'limit="{limit}"\n'
            'n=$(cat .git/pre-commit-calls 2>/dev/null || echo 0); n=$((n + 1))\n'
            'echo "$n" > .git/pre-commit-calls\n'
            '[ -n "$limit" ] && [ "$n" -gt "$limit" ] && exit 0\n'
            "echo \"fatal: Unable to create '$PWD/.git/index.lock': File exists.\" >&2\n"
            "exit 1\n", encoding="utf-8")
        hook.chmod(0o755)

    def commit_attempts(self) -> int:
        path = self.repo / ".git" / "pre-commit-calls"
        return int(path.read_text(encoding="utf-8").strip()) if path.exists() else 0

    def diverge_with_conflict(self):
        """Give origin and this clone conflicting committed pot.json edits, so
        the slot's own ``git pull --rebase --autostash`` really conflicts."""
        other = self.tmp_path / "other"
        git(self.tmp_path, "clone", str(self.origin), "other")
        git(other, "config", "user.email", "win@windowsill.test")
        git(other, "config", "user.name", "win-box")
        (other / "pot.json").write_text('{"hunt": {"targets_searched": 9001}}',
                                        encoding="utf-8")
        git(other, "commit", "-aqm", "win: pot from the other box")
        git(other, "push", "-q", "origin", "main")
        (self.repo / "pot.json").write_text('{"hunt": {"targets_searched": 7777}}',
                                            encoding="utf-8")
        git(self.repo, "commit", "-aqm", "loam: pot from this box")


def make_slot(tmp_path) -> Slot:
    bash = bash_path()
    if bash is None or shutil.which("git") is None:
        pytest.skip("needs bash and git on PATH")

    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "--initial-branch=main")

    repo = tmp_path / "loam"
    git(tmp_path, "clone", str(origin), "loam")
    git(repo, "config", "user.email", "loam@windowsill.test")
    git(repo, "config", "user.name", "loam-box")
    (repo / "pot.json").write_text('{"hunt": {"targets_searched": 3882}}',
                                   encoding="utf-8")
    (repo / "reports" / "hunts").mkdir(parents=True)
    (repo / "reports" / "hunts" / ".keep").write_text("", encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "a05_hunt.py").write_text(STUB_RUNNER, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "seed")
    git(repo, "push", "-q", "origin", "main")

    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "hunt.sector").write_text("3\n", encoding="utf-8")
    return Slot(bash, tmp_path, repo, origin, lab)
