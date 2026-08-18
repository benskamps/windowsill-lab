"""a05_hunt driver regressions — the wide hunt's own operational bugs.

The 2026-08-14 wide run exposed three: summaries/checkpoints written under
``LAB_HOME/cache`` were invisible to the root-only globs (re-searching
already-searched stars and dropping measured floors), a run that crossed
midnight could not resume its own checkpoint (the id was re-derived from
``date.today()``), and committed schema-0 receipts' floors never joined the
history. These tests pin the driver's file-discovery contract; the pipeline
itself is tested in test_a05_receipts.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "a05_hunt_under_test", ROOT / "scripts" / "a05_hunt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _isolated(mod, tmp_path, monkeypatch):
    lab_home = tmp_path / "labhome"
    (lab_home / "cache").mkdir(parents=True)
    monkeypatch.setattr(mod, "LAB_HOME", lab_home)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    return lab_home


def test_prior_targets_globs_lab_home_and_its_cache(tmp_path, monkeypatch):
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    (lab_home / "a05-hunt-2026-08-12-s2.jsonl").write_text(
        json.dumps({"tic": "444"}) + "\n", encoding="utf-8")
    (lab_home / "cache" / "a05-hunt-2026-08-13-s2.jsonl").write_text(
        json.dumps({"tic": "555"}) + "\n", encoding="utf-8")
    (lab_home / "cache" / "a04-hunt-2026-08-13-s2.jsonl").write_text(
        json.dumps({"tic": "666"}) + "\n", encoding="utf-8")
    assert {"444", "555", "666"} <= mod.prior_targets()


def test_floor_history_folds_cache_summaries_and_schema0_receipts(
        tmp_path, monkeypatch):
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    (lab_home / "cache" / "a04-hunt-2026-08-20-s3-summary.json").write_text(
        json.dumps({"floor_n": 200, "floor_max_sde": 7.7}), encoding="utf-8")
    hunts = tmp_path / "reports" / "hunts"
    hunts.mkdir(parents=True)
    (hunts / "hunt-2026-09-01-s3.json").write_text(
        json.dumps({"experiment": "a05-survey-hunt", "schema": 0,
                    "floor": {"n": 300, "max_sde": 7.71}, "targets": []}),
        encoding="utf-8")
    points = {p["source"]: p for p in mod.floor_history()}
    assert points["a04-hunt-2026-08-20-s3"]["n"] == 200
    assert points["hunt-2026-09-01-s3"]["n"] == 300
    # Priors survive untouched at the front.
    from lab import a05
    assert [p["source"] for p in mod.floor_history()][:len(
        a05.PRIOR_FLOOR_HISTORY)] == [p["source"]
                                      for p in a05.PRIOR_FLOOR_HISTORY]


def test_floor_history_dedupes_the_same_sample_under_two_names(
        tmp_path, monkeypatch):
    """The wide pilot's floor exists as a LAB_HOME summary AND as the
    committed pilot-570 prior — same n=551 sample, one point."""
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    (lab_home / "a04-hunt-2026-08-14-s2-summary.json").write_text(
        json.dumps({"floor_n": 551, "floor_max_sde": 7.8752631815526755}),
        encoding="utf-8")
    points = mod.floor_history()
    assert sum(1 for p in points if p["n"] == 551) == 1


def test_midnight_resume_picks_newest_receiptless_checkpoint(
        tmp_path, monkeypatch):
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    hunts = tmp_path / "reports" / "hunts"
    hunts.mkdir(parents=True)
    old = lab_home / "a05-hunt-2026-08-10-s2.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    receipted = lab_home / "a05-hunt-2026-08-11-s2.jsonl"
    receipted.write_text("{}\n", encoding="utf-8")
    (hunts / "hunt-2026-08-11-s2.json").write_text("{}", encoding="utf-8")
    os.utime(old, (1_000_000_000, 1_000_000_000))
    os.utime(receipted, (2_000_000_000, 2_000_000_000))
    # The newest checkpoint is receipted, so the OLDER open one resumes —
    # regardless of today's date.
    hid, ckpt = mod.find_checkpoint(2)
    assert hid == "hunt-2026-08-10-s2"
    assert ckpt == old
    # A different sector never picks this sector's checkpoint.
    hid3, _ = mod.find_checkpoint(3)
    assert hid3 == f"hunt-{date.today().isoformat()}-s3"


def test_hunt_id_override_and_fresh_id(tmp_path, monkeypatch):
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    hid, ckpt = mod.find_checkpoint(2, "hunt-custom-s2")
    assert hid == "hunt-custom-s2"
    assert ckpt == lab_home / "a05-hunt-custom-s2.jsonl"
    hid2, _ = mod.find_checkpoint(2)
    assert hid2 == f"hunt-{date.today().isoformat()}-s2"


# ── The grade gate belongs to the runner, not to one scheduler ───────────────

def _receipt(tmp_path: Path, name: str = "hunt-2026-08-18-s3-1902.json") -> Path:
    hunts = tmp_path / "reports" / "hunts"
    hunts.mkdir(parents=True, exist_ok=True)
    p = hunts / name
    p.write_text(json.dumps({"experiment": "a05-survey-hunt", "schema": 1}),
                 encoding="utf-8")
    return p


def test_a_graded_receipt_stays_in_the_ledger(tmp_path, monkeypatch):
    mod = _load_script()
    _isolated(mod, tmp_path, monkeypatch)
    r = _receipt(tmp_path)
    assert mod.settle_receipt(r, True) == r
    assert r.exists()


def test_an_ungraded_receipt_is_filed_with_the_logs(tmp_path, monkeypatch):
    """check_a05 None means a control failed, so the run is uninterpretable —
    not a negative. It may not sit in reports/hunts/, which the pot aggregator
    globs: the next run that publishes would count it, and CI, recomputing from
    the committed set alone, would go red."""
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    r = _receipt(tmp_path)
    dest = mod.settle_receipt(r, None)
    assert not r.exists()
    assert dest == lab_home / "ungraded" / r.name and dest.exists()


def test_a_failed_receipt_is_filed_too(tmp_path, monkeypatch):
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    r = _receipt(tmp_path)
    assert mod.settle_receipt(r, False) == lab_home / "ungraded" / r.name


def test_an_ungraded_runs_dossiers_travel_with_it(tmp_path, monkeypatch):
    """A dossier left behind is the same leak in HTML: the campaign lane stages
    all of reports/, so it would publish a lead's render for a run whose numbers
    were never publishable."""
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    r = _receipt(tmp_path)
    dossiers = r.parent / "dossiers"
    dossiers.mkdir()
    rendered = dossiers / f"{r.stem}-tic287328866.html"
    rendered.write_text("<html>lead</html>", encoding="utf-8")
    mod.settle_receipt(r, None, dossiers={"287328866": "<html>lead</html>"})
    assert not rendered.exists()
    assert (lab_home / "ungraded" / rendered.name).exists()


def test_the_gate_runs_before_the_pot_is_refreshed():
    """Order matters and is invisible to the unit tests above: refreshing the
    pot first would write the ungraded run's counters into the feed before the
    receipt was pulled out from under it."""
    src = (ROOT / "scripts" / "a05_hunt.py").read_text(encoding="utf-8")
    assert src.index("settle_receipt(receipt_path") < src.index("pot[\"hunt\"] = hunt_block()")
