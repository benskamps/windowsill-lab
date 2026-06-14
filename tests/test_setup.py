"""`lab setup` — the generated artifacts and pre-flight are pure + testable."""
from pathlib import Path

from lab import setup
from lab.publish import REPO_ROOT


def test_nightly_script_is_runnable_and_self_contained():
    sh = setup.nightly_script()
    assert sh.startswith("#!/usr/bin/env bash")
    assert str(REPO_ROOT) in sh                    # cd's into the repo
    assert "lab.cli run" in sh and "lab.cli publish" in sh
    assert "git push" in sh                        # it pushes the feed
    assert "git diff --cached --quiet" in sh       # commits only on change


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
    assert plan["method"] in ("systemd", "cron")
