"""`lab setup` — the generated artifacts and pre-flight are pure + testable."""
from pathlib import Path

from lab import setup
from lab.publish import REPO_ROOT


def test_nightly_script_is_runnable_and_self_contained():
    sh = setup.nightly_script()
    assert sh.startswith("#!/usr/bin/env bash")
    assert str(REPO_ROOT) in sh                    # cd's into the repo
    # The nightly advances the frontier via the milestone-aware scheduler `lab next`
    # (swapped from `lab run` 2026-07-05), falling back to `lab publish` on failure.
    assert "lab.cli next" in sh and "lab.cli publish" in sh
    assert "git push" in sh                        # it pushes the feed
    assert "git diff --cached --quiet" in sh       # commits only on change
    # The whole reports/ tree is staged so every permanent per-run report lands.
    assert "reports/" in sh
    # Guard: nightly publishes ONLY from main. If the clone is left on a feature
    # branch, it must refuse — otherwise the public feed gets stranded.
    assert 'abbrev-ref HEAD' in sh
    assert '!= "main"' in sh
    assert "REFUSING" in sh
    # Sync before pushing: a bare push from a stale main is rejected the moment
    # remote advances (a merged PR, the mirror bot), which stranded the feed for
    # days in June 2026. The nightly must rebase onto remote, not just push.
    assert "git pull --rebase" in sh


def test_units_reference_the_nightly_script_and_schedule():
    assert "ExecStart=" in setup.service_unit()
    assert str(setup.NIGHTLY_SH) in setup.service_unit()
    assert "OnCalendar=*-*-* 04:30:00" in setup.timer_unit(at="04:30:00")
    assert "WantedBy=timers.target" in setup.timer_unit()


def test_cron_line_points_at_the_nightly_script():
    line = setup.cron_line(at_hour=5)
    assert line.startswith("0 5 * * *")
    assert str(setup.NIGHTLY_SH) in line


def test_health_checks_report_python_and_remote():
    names = {c["name"] for c in setup.health_checks()}
    assert {"python", "git remote", "compute", "feed writable"} <= names
    for c in setup.health_checks():
        assert set(c) == {"name", "ok", "detail"}


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    sentinel = tmp_path / "scripts" / "nightly.sh"
    monkeypatch.setattr(setup, "NIGHTLY_SH", sentinel)
    plan = setup.install(dry_run=True)
    assert not sentinel.exists()
    assert plan["method"] in ("systemd", "cron", "schtasks")


# ── Windows nightly (Task Scheduler) — pure generators are platform-neutral ──
def test_nightly_ps1_is_runnable_and_self_contained():
    ps = setup.nightly_ps1()
    assert str(REPO_ROOT) in ps                        # cd's into the repo
    # The nightly advances the frontier via `lab next` (swapped from `lab run`
    # 2026-07-05), falling back to `lab publish` on failure.
    assert "lab.cli next" in ps and "lab.cli publish" in ps
    assert "git push" in ps                            # it pushes the feed
    assert "git diff --cached --quiet" in ps           # commits only on change
    assert "reports/" in ps                            # stages the whole reports/ tree
    # Guard: nightly publishes ONLY from main (same as the bash analog).
    assert "abbrev-ref HEAD" in ps
    assert "-ne 'main'" in ps
    assert "REFUSING" in ps
    # Same sync-before-push guard as the bash analog (the June 2026 stranding fix).
    assert "git pull --rebase" in ps


def test_task_xml_is_wellformed_and_runs_the_nightly():
    import xml.etree.ElementTree as ET
    xml = setup.task_xml(at="04:30:00")
    ET.fromstring(xml.encode("utf-16"))                # well-formed (declared UTF-16)
    assert "2026-01-01T04:30:00" in xml                # the chosen schedule time
    assert str(setup.NIGHTLY_PS1) in xml               # the action runs nightly.ps1
    assert "powershell.exe" in xml
    # Resilience: catch a missed start, and wake a sleeping box so the
    # windowsill grows even when nobody's at the machine at 3am.
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "<WakeToRun>true</WakeToRun>" in xml


def test_windows_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "NIGHTLY_PS1", tmp_path / "scripts" / "nightly.ps1")
    monkeypatch.setattr(setup, "TASK_XML", tmp_path / "scripts" / "task.xml")
    plan = setup._install_windows(dry_run=True)
    assert not (tmp_path / "scripts" / "nightly.ps1").exists()
    assert plan["method"] == "schtasks"
