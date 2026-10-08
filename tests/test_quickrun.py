"""BACKLOG #6: a ``--quick`` run never writes the live surfaces.

On 2026-08-19 ``lab m11 --quick`` overwrote ``pot.json`` so a 6-second L=8 toy
run became the public headline, and wrote into the tracked ``reports/`` and
``reports/receipts/``. These tests drive a real milestone command end to end
(runner stubbed, real ``_commit_report``, real ``publish``) with every live
surface repointed into ``tmp_path``, and assert none of them is touched.
"""
import inspect
import json
import re

import pytest

import lab.cli as cli
from lab import labhome, quickrun


@pytest.fixture
def surfaces(tmp_path, monkeypatch):
    from lab import publish as publish_mod
    from lab import render as render_mod

    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    pot = tmp_path / "pot.json"
    monkeypatch.setattr(render_mod, "REPO_REPORTS", reports)
    monkeypatch.setattr(render_mod, "LAB_HOME", lab_home)
    monkeypatch.setattr(labhome, "LAB_HOME", lab_home)
    monkeypatch.setattr(publish_mod, "POT_JSON", pot)
    monkeypatch.setattr(publish_mod, "LAB_HOME", lab_home)
    monkeypatch.setattr(publish_mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish_mod, "RECEIPTS_DIR", reports / "receipts")
    # If publish() ever got past its quick-run refusal, this is the first thing
    # it does; make that loud rather than letting it reach the real repo.
    def _must_not_run():
        raise AssertionError("publish() went past the --quick refusal")
    monkeypatch.setattr(publish_mod, "ensure_public_receipts", _must_not_run)
    return {"reports": reports, "lab_home": lab_home, "pot": pot}


def _stub_m11(monkeypatch):
    """Stub the M11 engine; keep the real renderer seam (_commit_report)."""
    from lab import m11 as m11_mod
    from lab import render as render_mod

    class _Result:
        monotone_broadening = True
        q2_hot, q2_cold, broadening_fraction = 0.1, 0.6, 1.0
        max_abs_q_mean = 0.01
        swap_health = None
        comparison = None
        wall_seconds = 6.0

    monkeypatch.setattr(m11_mod, "run_m11", lambda **kw: _Result())
    monkeypatch.setattr(m11_mod, "to_report",
                        lambda r: {"experiment": "M11-spin-glass", "headline": "toy"})

    def fake_render_m11(report, date=None):
        dump = json.dumps(report)
        return render_mod._commit_report(
            date or "2026-08-19", "m11", f"<html><pre>{dump}</pre></html>", dump)

    monkeypatch.setattr(render_mod, "render_m11", fake_render_m11)


@pytest.mark.parametrize("flag", ["--quick", "--qui"])
def test_quick_run_leaves_feed_reports_and_receipts_untouched(
        surfaces, monkeypatch, capsys, flag):
    _stub_m11(monkeypatch)

    assert cli.main(["m11", flag, "--device", "cpu"]) == 0

    out = capsys.readouterr().out
    assert not surfaces["pot"].exists(), "--quick wrote the live pot.json"
    assert not surfaces["reports"].exists(), (
        "--quick wrote into the tracked reports/ (report, receipt, or latest.html)")
    assert "snapshot skipped" in out and "live feed left untouched" in out
    # The run still leaves its report for the person who ran it, out of the repo.
    quick = list((surfaces["lab_home"] / "quick").glob("2026-08-19-m11.*"))
    assert sorted(p.suffix for p in quick) == [".html", ".json"]
    # And the switch does not outlive the command.
    assert not quickrun.active()


def test_full_run_still_commits_its_report_and_publishes(surfaces, monkeypatch, capsys):
    """Control: without --quick the same command reaches every surface."""
    from lab import publish as publish_mod

    _stub_m11(monkeypatch)
    published = []
    monkeypatch.setattr(publish_mod, "publish",
                        lambda *a, **k: published.append(1) or surfaces["pot"])

    assert cli.main(["m11", "--device", "cpu"]) == 0

    assert published == [1]
    assert (surfaces["reports"] / "2026-08-19-m11.html").exists()
    assert (surfaces["reports"] / "latest.html").exists()
    assert list((surfaces["reports"] / "receipts").glob("run-2026-08-19-*-m11.json"))


def test_publish_refuses_while_a_quick_run_is_active(surfaces):
    from lab import publish as publish_mod

    quickrun.enter()
    try:
        with pytest.raises(quickrun.QuickRunNotPublished):
            publish_mod.publish(quiet=True)
    finally:
        quickrun.reset()
    assert not surfaces["pot"].exists()


def test_every_quick_parser_arms_the_guard():
    """A new milestone that adds --quick must route its parse through
    _quick_guard, or it silently re-opens BACKLOG #6."""
    unguarded = []
    for name, fn in inspect.getmembers(cli, inspect.isfunction):
        if not name.startswith("_parse_"):
            continue
        src = inspect.getsource(fn)
        if re.search(r'["\']--quick["\']', src) and "_quick_guard(" not in src:
            unguarded.append(name)
    assert not unguarded, f"parsers with --quick but no _quick_guard: {unguarded}"
