"""The planner-v3 rerun gate: no scheduled rerun when nothing changed.

Every "unchanged" verdict here has a positive control beside it — the same
receipt with ONE thing changed must come back eligible — because a gate that
says "unchanged" to everything would pass a test that only checks the skip.
"""
import json

import pytest

import lab.cli as cli
from lab import curriculum, rerun_gate


def _head() -> str:
    run = rerun_gate._git("rev-parse", "HEAD")
    assert run is not None and run.returncode == 0
    return run.stdout.strip()


def _receipt(**over) -> dict:
    env = rerun_gate.current_environment()
    prov = {"source_commit": _head(), "source_clean": True, **env}
    prov.update(over.pop("provenance", {}))
    return {"generated_at": "2026-11-04T09:00:00+00:00", "provenance": prov, **over}


def _write(receipts, stem, body):
    receipts.mkdir(exist_ok=True)
    (receipts / f"run-{stem}.json").write_text(json.dumps(body), encoding="utf-8")


# ── what counts as the experiment's code ─────────────────────────────────────

def test_closure_follows_the_science_not_the_plumbing():
    assert rerun_gate.code_closure("c03") == ["src/lab/c03.py"]
    a03 = rerun_gate.code_closure("a03")
    assert "src/lab/a03.py" in a03 and "src/lab/pn.py" in a03
    assert "src/lab/fss.py" in rerun_gate.code_closure("m02")
    for sub in ("c03", "a03", "m02", "run"):
        for plumbing in rerun_gate.PLUMBING:
            assert f"src/lab/{plumbing}.py" not in rerun_gate.code_closure(sub)


def test_unknown_subcommand_compares_the_whole_tree():
    assert rerun_gate.code_closure("no-such-subcommand") is None


# ── why_changed: one control per field ───────────────────────────────────────

def test_identical_run_is_unchanged():
    env = rerun_gate.current_environment()
    files = rerun_gate.code_closure("c03")
    assert rerun_gate.why_changed(_receipt(), files, env) is None


@pytest.mark.parametrize("receipt, fragment", [
    ({"generated_at": "2026-11-04T09:00:00+00:00"}, "no provenance"),
    (_receipt(provenance={"source_commit": None}), "no source commit"),
    (_receipt(provenance={"source_clean": False}), "uncommitted source"),
    (_receipt(provenance={"python": "3.13.14"}), "python differs"),
    (_receipt(provenance={"dependencies": {"numpy": "1.0"}}), "dependencies differs"),
    (_receipt(provenance={"platform": "windows-amd64"}), "platform differs"),
    (_receipt(provenance={"source_commit": "0" * 40}), "git cannot compare"),
])
def test_any_difference_or_blind_spot_makes_it_eligible(receipt, fragment):
    env = rerun_gate.current_environment()
    why = rerun_gate.why_changed(receipt, rerun_gate.code_closure("c03"), env)
    assert why is not None and fragment in why


def test_a_code_change_or_an_uncommitted_edit_makes_it_eligible(monkeypatch):
    env = rerun_gate.current_environment()
    real_git = rerun_gate._git

    class _Done:
        def __init__(self, returncode, stdout=""):
            self.returncode, self.stdout = returncode, stdout

    monkeypatch.setattr(rerun_gate, "_git",
                        lambda *a: _Done(1) if a[0] == "diff" else real_git(*a))
    assert "code changed" in rerun_gate.why_changed(_receipt(), ["src/lab/c03.py"], env)
    monkeypatch.setattr(rerun_gate, "_git",
                        lambda *a: _Done(0, " M src/lab/c03.py") if a[0] == "status"
                        else real_git(*a))
    assert "uncommitted" in rerun_gate.why_changed(_receipt(), ["src/lab/c03.py"], env)


# ── the ledger-level verdicts ────────────────────────────────────────────────

def test_a_repeat_is_skipped_and_a_changed_one_is_not(tmp_path):
    receipts = tmp_path / "receipts"
    _write(receipts, "2026-11-03-0907-a03", _receipt())
    _write(receipts, "2026-11-03-0300-a01", _receipt(provenance={"python": "3.13.14"}))
    env = rerun_gate.current_environment()
    out = rerun_gate.unchanged_since_last_run(
        ["A03", "A01"], curriculum.RUNNERS, receipts, env)
    assert set(out) == {"A03"}
    assert "nothing changed since its last run" in out["A03"]


def test_newest_receipt_decides(tmp_path):
    """An old identical receipt does not gate a mid whose NEWEST run differs."""
    receipts = tmp_path / "receipts"
    _write(receipts, "2026-11-02-1136-a03", _receipt(generated_at="2026-11-02T11:36:00+00:00"))
    _write(receipts, "2026-11-03-0907-a03",
           _receipt(generated_at="2026-11-03T09:07:00+00:00", provenance={"python": "3.13.14"}))
    out = rerun_gate.unchanged_since_last_run(
        ["A03"], curriculum.RUNNERS, receipts, rerun_gate.current_environment())
    assert out == {}


def test_fresh_input_runs_are_never_gated(tmp_path):
    receipts = tmp_path / "receipts"
    _write(receipts, "2026-11-03-0907-i01", _receipt())
    out = rerun_gate.unchanged_since_last_run(
        ["I01", "A05"], {"I01": "i01", "A05": "hunt"}, receipts,
        rerun_gate.current_environment())
    assert out == {}


def test_c03_moves_through_its_targets_then_stops(tmp_path):
    receipts = tmp_path / "receipts"
    env = rerun_gate.current_environment()
    _write(receipts, "2026-11-04-0900-c03", _receipt(target="A001006"))
    assert rerun_gate.next_input("C03", "c03", receipts, env) == "A000045"
    assert "C03" not in rerun_gate.unchanged_since_last_run(
        ["C03"], curriculum.RUNNERS, receipts, env)
    _write(receipts, "2026-11-04-1500-c03",
           _receipt(target="A000045", generated_at="2026-11-04T15:00:00+00:00"))
    assert rerun_gate.next_input("C03", "c03", receipts, env) is None
    out = rerun_gate.unchanged_since_last_run(["C03"], curriculum.RUNNERS, receipts, env)
    assert "every registered target" in out["C03"]


# ── the planner and the CLI seam ─────────────────────────────────────────────

def test_planner_drops_unchanged_candidates_as_named_skips():
    statuses = {"C03": "open", "A03": "null", "M01": "verified"}
    # M01 is the ledger head, so C03 carries no consecutive-repeat decay and the
    # ungated control below is a clean open-frontier win.
    records = [("2026-11-04T09:00:00+00:00", "C03"), ("2026-11-03T09:07:00+00:00", "A03"),
               ("2026-11-04T10:00:00+00:00", "M01")]
    pick, decision = curriculum.plan_turn(
        records, statuses, unchanged={"C03": "same", "A03": "same"})
    assert decision["planner"] == "v3"
    assert pick not in ("C03", "A03")
    board = {e["mid"] for e in decision["scoreboard"]}
    assert "C03" not in board and "A03" not in board
    assert ("C03", "same") in decision["skips"] and ("A03", "same") in decision["skips"]
    pick_open, _ = curriculum.plan_turn(records, statuses, unchanged={})
    assert pick_open == "C03"                     # control: ungated, the frontier wins


def test_next_runs_nothing_when_everything_is_unchanged(monkeypatch, capsys, tmp_path):
    from lab import publish as publish_mod
    monkeypatch.setattr(cli, "LAB_HOME", tmp_path)
    monkeypatch.setattr(cli, "_hunt_status", lambda: None)
    monkeypatch.setattr(publish_mod, "parse_milestones",
                        lambda _t: [{"id": "M01", "status": "verified"}])
    monkeypatch.setattr(cli, "_unchanged_runs",
                        lambda: {mid: "same" for mid in curriculum.RUNNERS})
    dispatched = []
    real_main = cli.main
    monkeypatch.setattr(cli, "main",
                        lambda argv=None: dispatched.append(argv) or 0
                        if argv and argv[0] != "next" else real_main(argv))
    assert real_main(["next"]) == 0
    out = capsys.readouterr().out
    assert "nothing to run" in out and dispatched == []


def test_next_dispatches_c03_with_its_next_target(monkeypatch, capsys):
    from lab import publish as publish_mod
    monkeypatch.setattr(cli, "_hunt_status", lambda: None)
    monkeypatch.setattr(publish_mod, "parse_milestones",
                        lambda _t: [{"id": "C03", "status": "open"}])
    monkeypatch.setattr(rerun_gate, "next_input", lambda *a, **k: "A000045")
    assert cli.main(["next", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would run `lab c03`" in out and "A000045" in out


def test_idle_turn_writes_the_campaign_marker_only_when_asked(monkeypatch, capsys, tmp_path):
    from lab import publish as publish_mod
    monkeypatch.setattr(cli, "LAB_HOME", tmp_path)
    monkeypatch.setattr(cli, "_hunt_status", lambda: None)
    monkeypatch.setattr(publish_mod, "parse_milestones",
                        lambda _t: [{"id": "M01", "status": "verified"}])
    monkeypatch.setattr(cli, "_unchanged_runs",
                        lambda: {mid: "same" for mid in curriculum.RUNNERS})
    marker = tmp_path / "next.idle"
    monkeypatch.setenv("LAB_NEXT_IDLE_FILE", str(marker))
    assert cli.main(["next", "--dry-run"]) == 0
    assert not marker.exists()                    # a dry run declares nothing
    assert cli.main(["next"]) == 0
    assert "nothing to run" in marker.read_text(encoding="utf-8")
