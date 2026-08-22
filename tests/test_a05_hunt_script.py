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


# -- AUTO-F10: an outage is not a search -------------------------------------
#
# A target that MAST refused to serve produces an ``error:<Exc>`` row, and that row
# is written to the checkpoint and counted into ``result.rows`` exactly like a real
# search (src/lab/a05.py:723-732). A full-outage slot therefore "completes" with 200
# error rows — and ``prior_targets()`` then excluded every one of those TICs from
# every FUTURE hunt, because it read the ``tic`` key and never the ``outcome``.
# Nothing alarms and nothing retries: the sky those targets cover is silently and
# PERMANENTLY dropped from the survey. The partial case is worse, because it grades
# and publishes: 40 errored TICs out of 200 vanish under a green receipt.
#
# The vocabulary is closed (checks.py:2750): searched / skipped-no-product / error:*.
# ``skipped-no-product`` is permanent — there is genuinely no 2-minute product to
# search — so it stays excluded. ``error:*`` is transient by construction, so it must
# stay eligible. Anything without a readable outcome keeps the old behaviour: A04's
# graded receipt lists bare ``searched`` rows with no outcome key at all, and the
# conservative reading of an unlabelled row is that it was searched.

def _checkpoint(lab_home: Path, name: str, rows: list[dict]) -> Path:
    path = lab_home / name
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_an_errored_target_stays_eligible_for_a_later_hunt(tmp_path, monkeypatch):
    """The MAST outage case. These TICs were never searched — only attempted."""
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    _checkpoint(lab_home, "a05-hunt-2026-08-20-s3.jsonl", [
        {"tic": "111", "outcome": "searched"},
        {"tic": "222", "outcome": "error:HTTPError"},
        {"tic": "333", "outcome": "error:TimeoutError"},
        {"tic": "444", "outcome": "skipped-no-product"},
    ])
    already = mod.prior_targets()
    assert "222" not in already and "333" not in already, (
        "an outage was recorded as coverage — that sky is now permanently unsearched")


def test_searched_and_no_product_targets_stay_excluded(tmp_path, monkeypatch):
    """The other half. A search that ran, and a target with genuinely no product,
    are both DONE — re-searching them would burn the budget for nothing."""
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    _checkpoint(lab_home, "a05-hunt-2026-08-20-s3.jsonl", [
        {"tic": "111", "outcome": "searched"},
        {"tic": "444", "outcome": "skipped-no-product"},
        {"tic": "555"},  # A04-era row with no outcome key: read as searched
    ])
    already = mod.prior_targets()
    assert {"111", "444", "555"} <= already


def test_an_errored_row_in_a_published_receipt_stays_eligible(tmp_path, monkeypatch):
    """The partial-outage case, which GRADES and PUBLISHES: the receipt is real,
    its errored rows are not coverage, and the receipt glob has to say so too."""
    mod = _load_script()
    _isolated(mod, tmp_path, monkeypatch)
    hunts = tmp_path / "reports" / "hunts"
    hunts.mkdir(parents=True, exist_ok=True)
    (hunts / "hunt-2026-08-19-s3.json").write_text(json.dumps({
        "experiment": "a05-survey-hunt", "schema": 1,
        "targets": [{"tic": "777", "outcome": "searched"},
                    {"tic": "888", "outcome": "error:ConnectionError"}],
    }), encoding="utf-8")
    already = mod.prior_targets()
    assert "777" in already
    assert "888" not in already


def test_a_resume_reattempts_the_targets_that_errored(tmp_path, monkeypatch):
    """The same rule one slice inward. Inheriting an errored row as done freezes
    the outage into this slice's receipt; the outage has had 100 minutes to clear."""
    mod = _load_script()
    inherit, retry = mod.split_resumable([
        {"tic": "111", "outcome": "searched"},
        {"tic": "222", "outcome": "error:HTTPError"},
        {"tic": "444", "outcome": "skipped-no-product"},
    ])
    assert [r["tic"] for r in inherit] == ["111", "444"]
    assert [r["tic"] for r in retry] == ["222"]


# -- AUTO-F4: a checkpoint that cannot be graded must not be resumed forever ---
#
# ``find_checkpoint`` resumes the newest checkpoint that has no COMMITTED receipt,
# and ``settle_receipt`` files an ungraded receipt in LAB_HOME/ungraded — so a
# checkpoint whose grade fails deterministically never acquires the thing that would
# retire it. The sector lane then rebuilds the same rows, writes the same receipt,
# fails the same grade and requarantines it, every slot, forever: no new sky is
# searched and both units stay green. Bound the retries, then set it aside.

def test_a_deterministically_ungradeable_checkpoint_stops_being_resumed(
        tmp_path, monkeypatch):
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    stuck = "hunt-2026-08-20-s3"
    _checkpoint(lab_home, f"a05-{stuck}.jsonl",
                [{"tic": "111", "outcome": "searched"}])

    seen = []
    for _ in range(6):  # six slots — a day and a half of the sector lane
        hunt_id, _ckpt = mod.find_checkpoint(3)
        seen.append(hunt_id)
        if hunt_id != stuck:
            break
        # The slot reruns, rebuilds identical rows, and grading fails identically.
        mod.settle_receipt(_receipt(tmp_path, f"{hunt_id}.json"), None)

    assert seen[-1] != stuck, f"the sector lane never advanced: {seen}"
    assert seen.count(stuck) <= mod.GRADE_RETRY_LIMIT
    assert (lab_home / "ungraded" / f"{stuck}.json").exists(), (
        "the evidence must survive being set aside")


def test_a_single_grade_failure_is_still_retried(tmp_path, monkeypatch):
    """Bounded, not zero. A grade can fail for a reason that clears — the fix must
    not throw away a 100-minute slice on its first bad run."""
    mod = _load_script()
    lab_home = _isolated(mod, tmp_path, monkeypatch)
    stuck = "hunt-2026-08-20-s3"
    _checkpoint(lab_home, f"a05-{stuck}.jsonl",
                [{"tic": "111", "outcome": "searched"}])
    mod.settle_receipt(_receipt(tmp_path, f"{stuck}.json"), None)
    hunt_id, ckpt = mod.find_checkpoint(3)
    assert hunt_id == stuck
    assert ckpt == lab_home / f"a05-{stuck}.jsonl"
