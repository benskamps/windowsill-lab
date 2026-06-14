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


def install(prefer_cron: bool = False, dry_run: bool = False) -> dict:
    """Install the nightly job. Returns a small report dict for the CLI to print."""
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
