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
    assert "git add pot.json physics-latest.json" in sh
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
    assert "git add pot.json physics-latest.json" in ps
    # Guard: nightly publishes ONLY from main (same as the bash analog).
    assert "abbrev-ref HEAD" in ps
    assert "-ne 'main'" in ps
    assert "REFUSING" in ps
    # Same sync-before-push guard as the bash analog (the June 2026 stranding fix).
    assert "git pull --rebase" in ps
    assert "push failed after 4 attempts" in ps


# ── nightly hardening: index safety + independent nightly seeds ─────────────
# The defect being fixed: the nightly committed with a bare `git commit`, so
# anything pre-staged in the clone at 03:00 (agents work in it — IN-USE.md is a
# live convention) shipped to main under a "nightly:" message. campaign.sh got
# the pre-staged refusal + --only pathspec in PR #66; the nightly templates
# did not. NOTE: the installed scripts/nightly.ps1 is gitignored — these
# templates only take effect after `lab setup` is re-run on the box.

def test_nightly_sh_refuses_prestaged_index_before_running():
    sh = setup.nightly_script()
    guard = sh.index("git diff --cached --quiet")
    assert "staged" in sh and "REFUSING" in sh[:sh.index("lab.cli next")]
    # The refusal gate sits BEFORE the experiment/publish — a dirty index means
    # no run, no sweep, exit 0 (skip, logged), same semantics as campaign.sh.
    assert guard < sh.index("lab.cli next")


def test_nightly_ps1_refuses_prestaged_index_before_running():
    ps = setup.nightly_ps1()
    guard = ps.index("git diff --cached --quiet")
    assert guard < ps.index("lab.cli next")
    assert "staged" in ps


def test_nightly_templates_commit_only_campaign_paths():
    """`--only` + explicit pathspec: even if something slips into the index
    mid-run, the nightly commit can only ever carry the feed + reports tree."""
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        assert "git commit" in script
        assert "--only" in script
        assert "-- pot.json physics-latest.json reports/" in script


def test_nightly_templates_derive_seed_from_utc_date():
    """The bash nightly keeps its UTC-date seed (one pass/night). The Windows
    nightly fires 4×/day, so its seed carries the HOUR — each of the four daily
    passes is an independent sample instead of the same-day deterministic
    repeat. (A retry within the same hour still repeats — documented in the
    template.)"""
    sh = setup.nightly_script()
    assert "--seed" in sh and 'date -u +%Y%m%d' in sh
    ps = setup.nightly_ps1()
    assert "--seed" in ps and "yyyyMMddHH" in ps


def test_task_xml_is_wellformed_and_runs_the_nightly():
    import xml.etree.ElementTree as ET
    xml = setup.task_xml()
    root = ET.fromstring(xml.encode("utf-16"))         # well-formed (declared UTF-16)
    # 4 passes/device/day: four explicit daily CalendarTriggers (legible in the
    # Task Scheduler UI), interleaved with Loam's 03/09/15/21 local turns.
    triggers = [el for el in root.iter()
                if el.tag.endswith("}CalendarTrigger")]
    assert len(triggers) == 4
    for hh in ("00:00:00", "06:00:00", "12:00:00", "18:00:00"):
        assert f"2026-01-01T{hh}" in xml
    # ExecutionTimeLimit is an anti-wedge watchdog, NOT overlap prevention: on
    # 2026-08-02 the old PT2H limit killed the wrapper mid-M02 while the python
    # child survived and finished, orphaning its logging. Overlap is the run
    # lock's job (cli.next_run_lock); the watchdog sits past the longest honest
    # milestone so it only fires on a genuinely wedged wrapper.
    assert "<ExecutionTimeLimit>PT12H</ExecutionTimeLimit>" in xml
    assert str(setup.NIGHTLY_PS1) in xml               # the action runs nightly.ps1
    assert "powershell.exe" in xml
    # Resilience: catch a missed start, and wake a sleeping box so the
    # windowsill grows even when nobody's at the machine.
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "<WakeToRun>true</WakeToRun>" in xml
    assert "<RestartOnFailure>" in xml
    assert "-NonInteractive -WindowStyle Hidden" in xml


def test_task_xml_accepts_custom_times():
    xml = setup.task_xml(times=("04:30:00",))
    assert "2026-01-01T04:30:00" in xml
    assert xml.count("<CalendarTrigger>") == 1


def test_windows_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "NIGHTLY_PS1", tmp_path / "scripts" / "nightly.ps1")
    monkeypatch.setattr(setup, "TASK_XML", tmp_path / "scripts" / "task.xml")
    plan = setup._install_windows(dry_run=True)
    assert not (tmp_path / "scripts" / "nightly.ps1").exists()
    assert plan["method"] == "schtasks"
