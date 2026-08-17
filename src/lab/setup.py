"""``lab setup`` — make the windowsill breathe on its own.

One command: check the machine is wired (Python, git remote, device), then
install a nightly job that runs the patient experiment, refreshes ``pot.json``,
and pushes it. After that the seed grows without anyone touching it.

Prefers a systemd **user** timer; falls back to a copy-paste cron line. Stdlib
only, and every install step is idempotent.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from .publish import POT_JSON, REPO_ROOT, _git

PY = sys.executable                      # the interpreter that ran setup (venv-safe)
NIGHTLY_SH = REPO_ROOT / "scripts" / "nightly.sh"
UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE = "windowsill-lab.service"
TIMER = "windowsill-lab.timer"

# Windows nightly — a Task Scheduler job is the analog of the systemd timer.
NIGHTLY_PS1 = REPO_ROOT / "scripts" / "nightly.ps1"
TASK_XML = REPO_ROOT / "scripts" / "windowsill-lab.task.xml"
TASK_NAME = "windowsill-lab"


# ── health checks ───────────────────────────────────────────────────────────
def health_checks() -> list[dict]:
    """Return [{name, ok, detail}] — the pre-flight `lab setup --check`."""
    out: list[dict] = []

    v = sys.version_info
    out.append({
        "name": "python",
        "ok": v >= (3, 11),
        "detail": f"{v.major}.{v.minor}.{v.micro}" + ("" if v >= (3, 11) else " (need ≥ 3.11)"),
    })

    remote = _git("remote", "get-url", "origin")
    out.append({
        "name": "git remote",
        "ok": bool(remote),
        "detail": remote or "no 'origin' remote — nightly can't push",
    })

    out.append(_device_check())

    out.append({
        "name": "feed writable",
        "ok": os.access(REPO_ROOT, os.W_OK),
        "detail": str(POT_JSON),
    })
    return out


def _device_check() -> dict:
    try:
        import torch  # noqa: PLC0415 — optional, checked lazily
    except ImportError:
        return {"name": "compute", "ok": True,
                "detail": "torch not installed — runs will be skipped, feed still updates"}
    if torch.cuda.is_available():
        return {"name": "compute", "ok": True, "detail": f"GPU via torch {torch.__version__}"}
    return {"name": "compute", "ok": True, "detail": f"CPU only (torch {torch.__version__})"}


# ── conflicted-pull recovery (shared by both nightly templates) ─────────────
# THE DEFECT: `git pull --rebase --autostash` was called with no failure path.
# When it conflicts — routinely, because the nightly commits DERIVED files
# (pot.json, physics-latest.json, reports/) that both boxes regenerate — git
# stops mid-rebase and leaves the clone detached with unmerged files. Every
# later git command in the script then dies on "Pulling is not possible because
# you have unmerged files", so push attempts 2-4 could only ever fail, and the
# run exited on "push failed after 4 attempts" leaving the clone WEDGED. The
# 2026-08-05 STRANDED guard then fired on every subsequent nightly (correctly:
# loud, exit 1) but nothing repaired the clone, so the feed stayed frozen until
# a human noticed — 66h on 2026-08-08..11, the third such stranding in a
# fortnight.
#
# THE FIX: never leave a conflicted rebase/merge behind. Abort it before the
# next attempt touches git. When the same pull conflicts twice we still give up
# loudly with exit 1 (the 08-05 contract — an outage must not report success),
# but now from a CLEAN clone on main, so the NEXT nightly starts from a good
# state instead of inheriting the wedge. Recovering the un-pushed receipt is a
# human's call; not stranding the lab is not.
#
# These are separate constants so the tests can execute them against a real
# conflicted repo rather than grep the template for hopeful substrings.
UNWEDGE_SH = """\
unwedge() {
  # 0 = a conflict existed and was cleaned up; 1 = nothing to clean.
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    echo "   conflicted rebase — 'git rebase --abort' to leave the clone clean"
    git rebase --abort || true
    return 0
  fi
  if [ -n "$(git ls-files --unmerged)" ]; then
    echo "   conflicted merge — 'git merge --abort' to leave the clone clean"
    git merge --abort || true
    return 0
  fi
  return 1
}
sync_main() {
  # 0 = pulled; 2 = conflicted (aborted, clone clean); 1 = failed some other way.
  if git pull --rebase --autostash; then return 0; fi
  if unwedge; then return 2; fi
  return 1
}
"""

UNWEDGE_PS1 = """\
function Repair-WedgedClone {
    # $true when a conflicted rebase/merge existed and was aborted.
    if ((Test-Path '.git\\rebase-merge') -or (Test-Path '.git\\rebase-apply')) {
        Log "   conflicted rebase -- 'git rebase --abort' to leave the clone clean"
        git rebase --abort 2>&1 | LogCmd
        return $true
    }
    $unmerged = @(git ls-files --unmerged)
    if ($unmerged.Count -gt 0) {
        Log "   conflicted merge -- 'git merge --abort' to leave the clone clean"
        git merge --abort 2>&1 | LogCmd
        return $true
    }
    return $false
}
function Sync-Main {
    # 0 = pulled; 2 = conflicted (aborted, clone clean); 1 = failed otherwise.
    # Callers take the LAST pipeline item: a stray line from a native command
    # would otherwise turn the return value into an array and read as truthy.
    git pull --rebase --autostash 2>&1 | LogCmd
    if ($LASTEXITCODE -eq 0) { return 0 }
    if (@(Repair-WedgedClone)[-1]) { return 2 }
    return 1
}
"""


# ── generated artifacts (pure → unit-tested) ────────────────────────────────
def nightly_script() -> str:
    return f"""#!/usr/bin/env bash
# Windowsill Lab — nightly: run the patient experiment, refresh the feed, push.
# Installed by `lab setup`. Safe to edit; commits only when something changed.
set -uo pipefail
cd "{REPO_ROOT}" || exit 1
LOG="${{LAB_NIGHTLY_LOG:-$HOME/.lab/nightly.log}}"
mkdir -p "$(dirname "$LOG")"
# A conflicted pull must never survive into the next git command — see
# setup.UNWEDGE_SH for the outage this closes.
{UNWEDGE_SH}{{
  echo "── $(date -u +%FT%TZ) nightly start"
  # Guard: only the published trunk feeds brokenbranch.dev. If the clone was
  # left on a feature branch, a nightly commit/push would strand the feed (and
  # the mirror never updates). Refuse rather than publish to the wrong branch.
  branch="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$branch" != "main" ]; then
    # A deliberate feature branch is benign (skip quietly). A clone stranded
    # detached mid-rebase is an OUTAGE — and until 2026-08-05 both exited 0. The
    # 08-04 win nightly conflicted on the derived feeds, left the clone detached,
    # and every run after it logged "on branch 'HEAD'" and exited 0: six times over
    # 37h, green to the scheduler each time, while the feed froze. Nothing watches
    # a job that keeps reporting success.
    if [ "$branch" = "HEAD" ] || [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
      echo "STRANDED: detached/mid-rebase (branch '$branch') — the clone needs repair, NOT a benign skip."
      echo "   repair: git status; resolve or 'git rebase --abort'; 'git checkout main' before the next run."
      echo "── done (FAILED: clone stranded)"
      exit 1
    fi
    echo "REFUSING: on branch '$branch', not main — nightly publishes only from main. Skipping."
    echo "── done (skipped: not on main)"
    exit 0
  fi
  # Refuse a pre-loaded index: agents work in this clone, and anything staged
  # at 02:50 must never ship to main under a "nightly:" message. First belt;
  # the --only commit below is the second. (campaign.sh grew the same guard.)
  if ! git diff --cached --quiet; then
    echo "REFUSING: pre-existing staged changes — nightly will not sweep the index. Skipping."
    echo "── done (skipped: staged changes present)"
    exit 0
  fi
  # Sync with remote BEFORE working: PRs and the page-mirror bot push to main on
  # their own schedule, and a bare push from a stale main is rejected ("fetch
  # first") — exactly how the feed stranded for days in June 2026. Rebase on top.
  # A conflict here (the derived feeds diverge routinely) used to leave the
  # clone mid-rebase for the REST of the run; sync_main aborts it so the run
  # continues from clean local state instead of poisoning every later git call.
  sync_main || echo "   pull did not land — continuing from local state (clone left clean)"
  # Advance the portfolio: `lab next` runs the open milestone's experiment when it
  # has a runner, otherwise the committed portfolio rotation past the receipts-ledger
  # pointer (M01 heartbeat only when the rotation is empty). Best-effort; always
  # leave the feed fresh. (Frontier scheduler 2026-07-05 PR #49; rotation 2026-08-01.)
  # The UTC date+HOUR --seed makes each nightly run an independent sample; a retry
  # within the same hour repeats deterministically. This retires the documented
  # "same-day rerun repeats" property of the old date-only seed.
  "{PY}" -m lab.cli next --seed "$(date -u +%Y%m%d%H)" || "{PY}" -m lab.cli publish
  # Stage the feed + the WHOLE reports/ tree (recursive) so every permanent
  # per-run report (reports/<date>-<slug>.html/.json) lands, not just latest.html.
  git add pot.json physics-latest.json 2>/dev/null || true
  git add -A reports/ 2>/dev/null || true
  if git diff --cached --quiet -- pot.json physics-latest.json reports/; then
    echo "nothing changed"
  else
    git commit --only -m "nightly: $(date -u +%F)" -- pot.json physics-latest.json reports/
    # On rejection, remote advanced under us: rebase and retry, don't hammer a
    # push that can only be rejected again.
    pushed=0
    conflicts=0
    for i in 1 2 3 4; do
      if git push; then pushed=1; break; fi
      sync_main; rc=$?
      if [ "$rc" -eq 2 ]; then
        conflicts=$((conflicts + 1))
        # Twice means this is not a race we can rebase past — the derived feeds
        # genuinely diverged. Stop rather than loop; the clone is already clean.
        if [ "$conflicts" -ge 2 ]; then
          echo "ERROR: the same pull conflicted twice — the derived feeds diverged."
          echo "   giving up with the clone CLEAN on main; this run's commit is unpushed."
          echo "   next nightly starts from a good state; recover the receipt by hand."
          break
        fi
      fi
      sleep $((2 ** i))
    done
    if [ "$pushed" -ne 1 ]; then
      echo "ERROR: push failed after 4 attempts (clone left clean on main)"
      exit 1
    fi
  fi
  echo "── done"
}} >>"$LOG" 2>&1
"""


def service_unit() -> str:
    return f"""[Unit]
Description=Windowsill Lab — nightly run + publish
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={REPO_ROOT}
ExecStart={NIGHTLY_SH}
"""


def timer_unit(at: str = "03:00:00") -> str:
    return f"""[Unit]
Description=Windowsill Lab — nightly timer

[Timer]
OnCalendar=*-*-* {at}
Persistent=true

[Install]
WantedBy=timers.target
"""


def cron_line(at_hour: int = 3) -> str:
    return f"{0} {at_hour} * * * {NIGHTLY_SH} >> $HOME/.lab/nightly.log 2>&1"


# ── Windows generated artifacts (pure → unit-tested) ────────────────────────
# PowerShell + Task-Scheduler-XML are brace-heavy, so these are token templates
# rather than f-strings — keeps the generators readable and escape-bug-free.
_NIGHTLY_PS1 = r"""# Windowsill Lab — nightly: run the patient experiment, refresh the feed, push.
# Installed by `lab setup` on Windows. The PowerShell analog of nightly.sh.
# Safe to edit; commits only when something actually changed.
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Set-Location '__REPO_ROOT__'
$log = if ($env:LAB_NIGHTLY_LOG) { $env:LAB_NIGHTLY_LOG } else { Join-Path $HOME '.lab\nightly.log' }
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
# Append UTF-8 log lines. LogCmd coerces a native command's merged stdout+stderr
# to plain strings, so git's normal stderr (e.g. "main -> main") isn't logged as a
# scary NativeCommandError and the whole log stays one consistent encoding. The
# control flow keys off $LASTEXITCODE, which the pipe preserves.
function Log($m) { Add-Content -LiteralPath $log -Value $m -Encoding utf8 }
filter LogCmd { Log "$_" }
trap { Log "-- failed: $($_.Exception.Message)"; exit 1 }
# A conflicted pull must never survive into the next git command -- see
# setup.UNWEDGE_PS1 for the outage this closes.
__UNWEDGE__
Log "-- $((Get-Date).ToUniversalTime().ToString('s'))Z nightly start"
# Guard: only the published trunk feeds brokenbranch.dev. If the clone was left
# on a feature branch, a nightly commit/push would strand the feed (and the
# mirror never updates). Refuse rather than publish to the wrong branch.
$branch = (git rev-parse --abbrev-ref HEAD 2>&1 | Select-Object -First 1).Trim()
if ($branch -ne 'main') {
    # See the bash twin above: a deliberate feature branch is benign, a clone
    # stranded detached mid-rebase is an outage, and until 2026-08-05 both exited 0.
    $stranded = (Test-Path '.git\rebase-merge') -or (Test-Path '.git\rebase-apply') -or ($branch -eq 'HEAD')
    if ($stranded) {
        Log "STRANDED: detached/mid-rebase (branch '$branch') -- the clone needs repair, NOT a benign skip."
        Log "   repair: git status; resolve or 'git rebase --abort'; 'git checkout main' before the next run."
        Log "-- done (FAILED: clone stranded)"
        exit 1
    }
    Log "REFUSING: on branch '$branch', not main -- nightly publishes only from main. Skipping."
    Log "-- done (skipped: not on main)"
    exit 0
}
# Refuse a pre-loaded index: agents work in this clone, and anything staged at
# 02:50 must never ship to main under a "nightly:" message. First belt; the
# --only commit below is the second. (Same guard campaign.sh carries.)
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    Log "REFUSING: pre-existing staged changes -- nightly will not sweep the index. Skipping."
    Log "-- done (skipped: staged changes present)"
    exit 0
}
# Sync with remote BEFORE working. PRs and the page-mirror bot push to main on
# their own schedule; without this our nightly commit is based on a stale main and
# the push below is rejected ("fetch first") -- exactly how the feed stranded for
# days in June 2026. Rebase whatever we do on top of whatever has already landed.
# The pull also fetches the other box's receipts, so the portfolio-rotation
# pointer below is read from the SHARED committed ledger, not box-local state.
# A conflict here (the derived feeds diverge routinely) used to leave the clone
# mid-rebase for the REST of the run; Sync-Main aborts it so the run continues
# from clean local state instead of poisoning every later git call.
if (@(Sync-Main)[-1] -ne 0) { Log "   pull did not land -- continuing from local state (clone left clean)" }
# Advance the portfolio: `lab next` runs the open milestone's experiment when it has
# a runner, otherwise the committed portfolio rotation (curriculum.ROTATION) past the
# receipts-ledger pointer -- so 4 passes/day re-measure the whole runnable portfolio
# instead of re-running M01 every pass. Best-effort; always leave the feed fresh.
# (Frontier scheduler 2026-07-05 PR #49; rotation 2026-08-01, see
# docs/investigations/2026-08-01-portfolio-rotation.md.) The UTC date+HOUR --seed
# makes each of the four daily passes an independent sample; a retry within the
# same hour repeats deterministically (StartWhenAvailable catch-up runs land in
# their own hour, so they get their own sample). This retires the documented
# "same-day rerun repeats" property of the old date-only seed.
$seed = (Get-Date).ToUniversalTime().ToString('yyyyMMddHH')
& '__PY__' -m lab.cli next --seed $seed 2>&1 | LogCmd
if ($LASTEXITCODE -ne 0) { & '__PY__' -m lab.cli publish 2>&1 | LogCmd }
# Stage the feed + the WHOLE reports/ tree (recursive) so every permanent
# per-run report (reports/<date>-<slug>.html/.json) lands, not just latest.html.
git add pot.json physics-latest.json 2>&1 | LogCmd
git add -A reports/ 2>&1 | LogCmd
git diff --cached --quiet -- pot.json physics-latest.json reports/
if ($LASTEXITCODE -ne 0) {
    git commit --only -m "nightly: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd'))" -- pot.json physics-latest.json reports/ 2>&1 | LogCmd
    $pushSucceeded = $false
    $conflicts = 0
    for ($i = 1; $i -le 4; $i++) {
        git push 2>&1 | LogCmd
        if ($LASTEXITCODE -eq 0) { $pushSucceeded = $true; break }
        # Remote advanced between the sync above and now. Rebase onto it and retry,
        # rather than hammering a push that can only be rejected again.
        Log "push rejected; rebasing onto origin/main and retrying"
        if (@(Sync-Main)[-1] -eq 2) {
            $conflicts++
            # Twice means this is not a race we can rebase past -- the derived
            # feeds genuinely diverged. Stop rather than loop; clone is clean.
            if ($conflicts -ge 2) {
                Log "ERROR: the same pull conflicted twice -- the derived feeds diverged."
                Log "   giving up with the clone CLEAN on main; this run's commit is unpushed."
                Log "   next nightly starts from a good state; recover the receipt by hand."
                break
            }
        }
        Start-Sleep -Seconds ([math]::Pow(2, $i))
    }
    if (-not $pushSucceeded) {
        Log "ERROR: push failed after 4 attempts (clone left clean on main)"
        exit 1
    }
}
Log "-- done (success)"
"""

# Task Scheduler XML. schtasks /Create /XML wants UTF-16, so the file is written
# as utf-16 and the declaration says so. InteractiveToken = no stored password
# (runs while logged in); StartWhenAvailable catches a missed slot if the box
# slept, and WakeToRun wakes a sleeping machine so the windowsill grows even
# unattended. Cadence: FOUR explicit daily triggers (legible in the Task
# Scheduler UI, unlike a Repetition block) at 00/06/12/18 local — interleaved
# with Loam's campaign turns at 03/09/15/21 local: 8 turns/day across the
# portfolio.
#
# ExecutionTimeLimit is an ANTI-WEDGE WATCHDOG ONLY — it is NOT overlap
# prevention, and it does NOT reliably stop work. 2026-08-02 falsified the old
# PT2H-prevents-overlap theory: the 12:00 slot dispatched M02 (a legitimate
# ~4.5h GPU milestone), at 14:00 Task Scheduler terminated the powershell
# wrapper (0x41306), and the `python -m lab.cli next` CHILD survived the kill
# and ran to completion with its logging orphaned. So the limit stopped nothing
# except the log. Overlap prevention is the run lock's job (~/.lab/next.lock,
# see cli.next_run_lock): a slot that arrives while a turn is live skips itself
# and exits 0. PT12H is set so the watchdog sits well past the longest honest
# milestone rather than amputating it — it should only ever fire on a genuinely
# wedged wrapper.
_TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Windowsill Lab — 4×/day run + publish</Description>
  </RegistrationInfo>
  <Triggers>
__TRIGGERS__  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <RestartOnFailure>
      <Interval>PT5M</Interval>
      <Count>2</Count>
    </RestartOnFailure>
    <ExecutionTimeLimit>PT12H</ExecutionTimeLimit>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "__NIGHTLY_PS1__"</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def nightly_ps1() -> str:
    return (_NIGHTLY_PS1
            .replace("__REPO_ROOT__", str(REPO_ROOT))
            .replace("__PY__", PY)
            .replace("__UNWEDGE__", UNWEDGE_PS1))


# Win slots 00/06/12/18 local ↔ Loam slots 03/09/15/21 local (campaign.sh) —
# the two boxes take interleaved turns, 8 portfolio passes/day total.
TASK_TIMES: tuple[str, ...] = ("00:00:00", "06:00:00", "12:00:00", "18:00:00")

_TRIGGER_TEMPLATE = """    <CalendarTrigger>
      <StartBoundary>2026-01-01T__AT__</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
"""


def task_xml(times: tuple[str, ...] = TASK_TIMES) -> str:
    triggers = "".join(
        _TRIGGER_TEMPLATE.replace("__AT__", at) for at in times
    )
    return (
        _TASK_XML
        .replace("__TRIGGERS__", triggers)
        .replace("__NIGHTLY_PS1__", str(NIGHTLY_PS1))
    )


# ── install ─────────────────────────────────────────────────────────────────
def _write_nightly() -> None:
    NIGHTLY_SH.parent.mkdir(parents=True, exist_ok=True)
    NIGHTLY_SH.write_text(nightly_script())
    NIGHTLY_SH.chmod(NIGHTLY_SH.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _has_user_systemd() -> bool:
    if not shutil.which("systemctl"):
        return False
    r = subprocess.run(["systemctl", "--user", "show-environment"],
                       capture_output=True, text=True)
    return r.returncode == 0


def _write_windows() -> None:
    NIGHTLY_PS1.parent.mkdir(parents=True, exist_ok=True)
    NIGHTLY_PS1.write_text(nightly_ps1(), encoding="utf-8")
    TASK_XML.write_text(task_xml(), encoding="utf-16")   # schtasks /XML wants UTF-16


def _install_windows(dry_run: bool = False, times: tuple[str, ...] = TASK_TIMES) -> dict:
    """Register the Scheduled Task — the Windows analog of the systemd unit."""
    plan = {"nightly": str(NIGHTLY_PS1), "method": "schtasks", "steps": [], "notes": []}
    slots = "/".join(t[:5] for t in times)

    if dry_run:
        plan["steps"].append("(dry run — nothing written)")
        plan["notes"].append(f"Would write {NIGHTLY_PS1} + {TASK_XML}, then register:")
        plan["notes"].append(f'  schtasks /Create /TN "{TASK_NAME}" /XML "{TASK_XML}" /F   (daily at {slots})')
        return plan

    _write_windows()
    r = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(TASK_XML), "/F"],
        capture_output=True, text=True,
    )
    ok = r.returncode == 0
    plan["steps"] = [
        f"wrote {NIGHTLY_PS1}",
        f"wrote {TASK_XML}",
        f"registered task '{TASK_NAME}' (daily at {slots})" if ok
        else f"schtasks failed: {(r.stderr or r.stdout).strip()}",
    ]
    plan["notes"].append(f"Inspect:  schtasks /Query /TN {TASK_NAME} /V /FO LIST")
    plan["notes"].append(f"Run now:  schtasks /Run /TN {TASK_NAME}")
    plan["notes"].append(
        f"Fires at {slots} local while you're logged in (InteractiveToken — no "
        "stored password). Loam's campaign takes the 03/09/15/21 local slots — "
        "8 interleaved portfolio turns/day. To run while logged out, open Task "
        "Scheduler and tick 'Run whether user is logged on or not'."
    )
    return plan


def install(prefer_cron: bool = False, dry_run: bool = False) -> dict:
    """Install the nightly job. Returns a small report dict for the CLI to print."""
    if os.name == "nt":
        return _install_windows(dry_run=dry_run)

    plan = {"nightly": str(NIGHTLY_SH), "method": None, "steps": [], "notes": []}

    if dry_run:
        plan["method"] = "cron" if (prefer_cron or not _has_user_systemd()) else "systemd"
        plan["steps"].append("(dry run — nothing written)")
        return plan

    _write_nightly()

    if not prefer_cron and _has_user_systemd():
        plan["method"] = "systemd"
        UNIT_DIR.mkdir(parents=True, exist_ok=True)
        (UNIT_DIR / SERVICE).write_text(service_unit())
        (UNIT_DIR / TIMER).write_text(timer_unit())
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        r = subprocess.run(["systemctl", "--user", "enable", "--now", TIMER],
                           capture_output=True, text=True)
        plan["steps"] = [f"wrote {UNIT_DIR / SERVICE}", f"wrote {UNIT_DIR / TIMER}",
                         f"enabled {TIMER}" if r.returncode == 0 else f"enable failed: {r.stderr.strip()}"]
        plan["notes"].append(
            "Run `loginctl enable-linger $USER` so the timer fires while you're logged out."
        )
        plan["notes"].append(f"Check it: systemctl --user list-timers {TIMER}")
    else:
        plan["method"] = "cron"
        plan["steps"] = [f"wrote {NIGHTLY_SH}"]
        plan["notes"].append("Add this line to your crontab (`crontab -e`):")
        plan["notes"].append("  " + cron_line())
    return plan
