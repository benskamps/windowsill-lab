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


# ── generated artifacts (pure → unit-tested) ────────────────────────────────
def nightly_script() -> str:
    return f"""#!/usr/bin/env bash
# Windowsill Lab — nightly: run the patient experiment, refresh the feed, push.
# Installed by `lab setup`. Safe to edit; commits only when something changed.
set -uo pipefail
cd "{REPO_ROOT}" || exit 1
LOG="${{LAB_NIGHTLY_LOG:-$HOME/.lab/nightly.log}}"
mkdir -p "$(dirname "$LOG")"
{{
  echo "── $(date -u +%FT%TZ) nightly start"
  # Run today's experiment (best-effort); always leave the feed fresh.
  "{PY}" -m lab.cli run || "{PY}" -m lab.cli publish
  git add pot.json reports/ 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "nothing changed"
  else
    git commit -m "nightly: $(date -u +%F)"
    for i in 1 2 3 4; do git push && break || sleep $((2 ** i)); done
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
Set-Location '__REPO_ROOT__'
$log = if ($env:LAB_NIGHTLY_LOG) { $env:LAB_NIGHTLY_LOG } else { Join-Path $HOME '.lab\nightly.log' }
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
"-- $((Get-Date).ToUniversalTime().ToString('s'))Z nightly start" | Out-File -Append -Encoding utf8 $log
# Run today's experiment (best-effort); always leave the feed fresh.
& '__PY__' -m lab.cli run *>> $log
if ($LASTEXITCODE -ne 0) { & '__PY__' -m lab.cli publish *>> $log }
git add pot.json reports/ 2>$null
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "nightly: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd'))" *>> $log
    for ($i = 1; $i -le 4; $i++) {
        git push *>> $log
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds ([math]::Pow(2, $i))
    }
}
"-- done" | Out-File -Append -Encoding utf8 $log
"""

# Task Scheduler XML. schtasks /Create /XML wants UTF-16, so the file is written
# as utf-16 and the declaration says so. InteractiveToken = no stored password
# (runs while logged in); StartWhenAvailable catches a missed 3am if the box slept.
_TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Windowsill Lab — nightly run + publish</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T__AT__</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "__NIGHTLY_PS1__"</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def nightly_ps1() -> str:
    return _NIGHTLY_PS1.replace("__REPO_ROOT__", str(REPO_ROOT)).replace("__PY__", PY)


def task_xml(at: str = "03:00:00") -> str:
    return (
        _TASK_XML
        .replace("__AT__", at)
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


def _install_windows(dry_run: bool = False, at: str = "03:00:00") -> dict:
    """Register a daily Scheduled Task — the Windows analog of the systemd timer."""
    plan = {"nightly": str(NIGHTLY_PS1), "method": "schtasks", "steps": [], "notes": []}
    hhmm = at[:5]

    if dry_run:
        plan["steps"].append("(dry run — nothing written)")
        plan["notes"].append(f"Would write {NIGHTLY_PS1} + {TASK_XML}, then register:")
        plan["notes"].append(f'  schtasks /Create /TN "{TASK_NAME}" /XML "{TASK_XML}" /F   (daily {hhmm})')
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
        f"registered task '{TASK_NAME}' (daily {hhmm})" if ok
        else f"schtasks failed: {(r.stderr or r.stdout).strip()}",
    ]
    plan["notes"].append(f"Inspect:  schtasks /Query /TN {TASK_NAME} /V /FO LIST")
    plan["notes"].append(f"Run now:  schtasks /Run /TN {TASK_NAME}")
    plan["notes"].append(
        "Fires at 03:00 while you're logged in (InteractiveToken — no stored "
        "password). To run while logged out, open Task Scheduler and tick "
        "'Run whether user is logged on or not'."
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
