"""STR-1 — the hunt driver's pot read-modify-write, and who may clobber what.

Two defects, one blast radius (the 2026-08-15 lead-destruction class):

* **The unlocked RMW.** ``scripts/a05_hunt.py`` ends by reading ``pot.json``,
  replacing its ``hunt`` key and writing the whole document back. The WRITE is
  atomic (tmp + fsync + replace) and always was. The READ-MODIFY-WRITE is not
  serialized against anything. The campaign lane reaches its own publish through
  ``lab next``, which holds ``next_run_lock`` (src/lab/cli.py:107, taken at
  cli.py:2456) for the whole turn — so campaign's writes are mutually exclusive
  with each other, and with nothing else. Interleave them: hunt reads pot →
  campaign publishes a new pot → hunt writes back the copy it read, and
  campaign's pass is silently gone. Nothing is corrupt, nothing alarms, and the
  only thing standing between this and production is that the two lanes happen
  to be scheduled in different hours. Configuration is not a lock.

* **The unowned receipt write.** The receipt lands at
  ``reports/hunts/<hunt_id>.json`` unconditionally. ``find_checkpoint`` works
  hard to avoid colliding ids, and ``--hunt-id`` walks straight past all of it —
  as does a receipt for our id that the OTHER box committed while our 100-minute
  slice was burning. On 2026-08-15 exactly that happened: loam's bare survey
  slot defaulted to sector 2 and overwrote win's committed s2 receipt, taking a
  lead-awaiting-human-review row with it. Writing must never destroy a receipt
  this run did not write.

Both tests drive ``main()`` — the real driver, with the search stubbed — so they
fail on the base commit by doing the wrong THING, not by missing a symbol.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "a05_hunt_pot_lock", ROOT / "scripts" / "a05_hunt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StubResult:
    """What ``a05.run_a05`` hands back: a complete slice with no dossiers."""
    complete = True
    rows: list = []
    dossiers: dict = {}


class _StubPool:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    map = staticmethod(map)


REPORT = {
    "experiment": "a05-survey-hunt",
    "schema": 1,
    "counts": {"searched": 3, "attempted": 3, "stage2": 1,
               "above_threshold": 0, "leads_awaiting_human_review": 0},
}


def _driver(tmp_path, monkeypatch, *, grade=True):
    """A runnable ``a05_hunt`` whose search, grading and pot all live in tmp.

    Everything stubbed here is a REAL name on the base commit, so the code path
    under test is the shipped one end to end: find_checkpoint -> run_a05 ->
    to_report -> check_a05 -> settle_receipt -> the pot refresh.
    """
    from lab import a05, checks, cli, publish

    mod = _load_script()
    lab_home = tmp_path / "labhome"
    (lab_home / "cache").mkdir(parents=True)
    (tmp_path / "reports" / "hunts").mkdir(parents=True)
    monkeypatch.setattr(mod, "LAB_HOME", lab_home)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "Pool", lambda _n: _StubPool())
    monkeypatch.setattr(mod, "prior_targets", lambda: set())
    monkeypatch.setattr(mod, "floor_history", lambda: ())
    monkeypatch.setattr(mod, "provenance",
                        lambda: {"machine": "test", "code_sha": "",
                                 "python": "3.11"})
    monkeypatch.setattr(a05, "run_a05", lambda **kw: _StubResult())
    monkeypatch.setattr(a05, "to_report", lambda *a, **kw: dict(REPORT))
    monkeypatch.setattr(checks, "check_a05", lambda report: (grade, "stub"))

    # The lock the campaign lane holds — same lock, relocated into tmp so the
    # test never touches the real ~/.lab.
    monkeypatch.setattr(cli, "LAB_HOME", tmp_path / "lock-home")

    pot = tmp_path / "pot.json"
    pot.write_text(json.dumps({"hunt": None, "campaign": "pass-1"},
                              indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(publish, "POT_JSON", pot)
    return mod, pot


#: The OTHER lane, as a genuinely separate process. It has to be a real one:
#: the campaign publish and the hunt slot are different process trees on the
#: box (systemd runs `a05-hunt-slot.sh`; the campaign loop runs `lab next`), and
#: a same-process stand-in would re-enter the lock rather than contend for it.
#: It does what `lab next` does — take the lock, write pot.json, release — and
#: SKIPS when the lock is busy, exactly as cli.py's `next` dispatch skips its
#: slot. Exit 0 = it published; exit 7 = it found the box busy and stood down.
CAMPAIGN_PUBLISH = '''\
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from lab.cli import LockBusy, next_run_lock

lock, pot = Path(sys.argv[2]), Path(sys.argv[3])
try:
    with next_run_lock(lock):
        doc = json.loads(pot.read_text(encoding="utf-8"))
        doc["campaign"] = "pass-2"
        pot.write_text(json.dumps(doc, indent=2) + "\\n", encoding="utf-8")
except LockBusy:
    sys.exit(7)
'''


class _CampaignPublish:
    """Runs :data:`CAMPAIGN_PUBLISH` at the moment the hunt asks for its hunt
    block — i.e. in the middle of the hunt's read-modify-write."""

    def __init__(self, tmp_path: Path, pot: Path):
        self.script = tmp_path / "campaign_publish.py"
        self.script.write_text(CAMPAIGN_PUBLISH, encoding="utf-8")
        self.lock = tmp_path / "lock-home" / "next.lock"
        self.pot = pot
        self.wrote = False

    def __call__(self, *a, **kw):
        # A different process TREE: strip the ancestry variable the run lock
        # exports, or this would inherit "your own turn holds it" from pytest.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("LAB_NEXT_LOCK")}
        proc = subprocess.run(
            [sys.executable, str(self.script), str(ROOT / "src"),
             str(self.lock), str(self.pot)],
            env=env, capture_output=True, text=True, timeout=120)
        assert proc.returncode in (0, 7), proc.stderr
        self.wrote = proc.returncode == 0
        return {"targets_searched": 42}


def test_a_campaign_publish_is_not_lost_under_the_hunts_pot_refresh(
        tmp_path, monkeypatch):
    """No lost update. The campaign lane publishes in the middle of the hunt's
    read-modify-write; whatever it managed to commit must still be there when
    the hunt is done.

    On the base commit the hunt holds no lock, so the campaign write LANDS and
    is then overwritten by the stale copy the hunt read before it — pot says
    ``pass-1`` while the campaign lane believes it published ``pass-2``. Under
    the fix the hunt holds ``next_run_lock`` across the whole RMW, the campaign
    publish finds it busy and skips, and nothing anyone wrote is destroyed.
    """
    from lab import publish

    mod, pot = _driver(tmp_path, monkeypatch)
    campaign = _CampaignPublish(tmp_path, pot)
    monkeypatch.setattr(publish, "hunt_block", campaign)
    monkeypatch.setattr("sys.argv", ["a05_hunt.py", "--sector", "2",
                                     "--hunt-id", "hunt-2026-08-22-s2"])

    assert mod.main() == 0

    doc = json.loads(pot.read_text(encoding="utf-8"))
    expected = "pass-2" if campaign.wrote else "pass-1"
    assert doc["campaign"] == expected, (
        "the hunt's read-modify-write ran unlocked and clobbered a campaign "
        f"publish that had already committed (campaign.wrote={campaign.wrote})")
    assert doc["hunt"] == {"targets_searched": 42}


def test_the_pot_is_still_refreshed_when_nothing_is_contending(
        tmp_path, monkeypatch):
    """The happy path the lock must not break: an uncontended hunt still lands
    its hunt block, in the publisher's serialization and insertion order."""
    from lab import publish

    mod, pot = _driver(tmp_path, monkeypatch)
    monkeypatch.setattr(publish, "hunt_block",
                        lambda *a, **kw: {"targets_searched": 4686})
    monkeypatch.setattr("sys.argv", ["a05_hunt.py", "--sector", "2",
                                     "--hunt-id", "hunt-2026-08-22-s2"])

    assert mod.main() == 0
    text = pot.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["hunt"] == {"targets_searched": 4686}
    assert doc["campaign"] == "pass-1"
    # insertion order preserved — `hunt` still precedes `campaign`, never sorted
    assert text.index('"hunt"') < text.index('"campaign"')


def test_the_receipt_write_refuses_to_clobber_a_receipt_it_does_not_own(
        tmp_path, monkeypatch):
    """The 2026-08-15 overwrite, reproduced.

    A receipt for this hunt id is already on disk — the other box committed it
    while our slice was burning, or ``--hunt-id`` named an id that is already
    settled. The base commit opens the path and writes over it, and the lead row
    inside is gone. The run's own work must still be preserved: refusing is not
    the same as discarding, so a receipt lands BESIDE the foreign one.
    """
    from lab import publish

    mod, pot = _driver(tmp_path, monkeypatch)
    monkeypatch.setattr(publish, "hunt_block",
                        lambda *a, **kw: {"targets_searched": 1})
    monkeypatch.setattr("sys.argv", ["a05_hunt.py", "--sector", "2",
                                     "--hunt-id", "hunt-2026-08-22-s2"])

    hunts = tmp_path / "reports" / "hunts"
    foreign = hunts / "hunt-2026-08-22-s2.json"
    foreign_doc = {"experiment": "a05-survey-hunt", "schema": 1,
                   "machine": "win",
                   "targets": [{"tic": "287328866",
                                "disposition": "lead-awaiting-human-review"}]}
    foreign.write_text(json.dumps(foreign_doc, indent=1), encoding="utf-8")

    mod.main()

    assert json.loads(foreign.read_text(encoding="utf-8")) == foreign_doc, (
        "the hunt overwrote a receipt written by another producer — the "
        "2026-08-15 lead-destruction incident, byte for byte")
    written = sorted(p.name for p in hunts.glob("*.json"))
    assert len(written) == 2, (
        "the run's own receipt was discarded rather than filed beside the "
        f"foreign one: {written}")


def _run_campaign_publish(tmp_path, lock, pot, *, same_tree: bool):
    script = tmp_path / "campaign_publish.py"
    script.write_text(CAMPAIGN_PUBLISH, encoding="utf-8")
    env = dict(os.environ)
    if not same_tree:
        env = {k: v for k, v in env.items() if not k.startswith("LAB_NEXT_LOCK")}
    return subprocess.run(
        [sys.executable, str(script), str(ROOT / "src"), str(lock), str(pot)],
        env=env, capture_output=True, text=True, timeout=120)


def test_a_child_of_the_lock_holder_re_enters_instead_of_deadlocking(tmp_path):
    """The lock is one-turn-per-BOX, not one-acquire-per-process.

    ``lab next`` takes it and then dispatches ``lab hunt``, which runs the hunt
    driver in a SUBPROCESS (src/lab/cli.py, ``cmd == "hunt"``). Once that driver
    locks its own pot refresh, a lock that cannot tell a descendant from a rival
    makes the campaign lane block on itself for the whole wait budget and then
    withhold a graded receipt. A child of the holder must be let through; an
    unrelated process must not.
    """
    from lab.cli import next_run_lock

    lock = tmp_path / "next.lock"
    pot = tmp_path / "pot.json"
    pot.write_text(json.dumps({"campaign": "pass-1"}), encoding="utf-8")

    with next_run_lock(lock):
        inside = _run_campaign_publish(tmp_path, lock, pot, same_tree=True)
        # The holder still owns it: a re-entering child must not release on exit.
        still_held = lock.exists()
        outside = _run_campaign_publish(tmp_path, lock, pot, same_tree=False)

    assert inside.returncode == 0, (
        f"our own turn's child was refused its own lock: {inside.stderr}")
    assert still_held, "the re-entering child released a lock it never took"
    assert outside.returncode == 7, (
        f"an unrelated process took a held lock: rc={outside.returncode} "
        f"{outside.stderr}")
    assert not lock.exists(), "the holder failed to release on the way out"


def test_a_bounded_wait_gives_up_and_raises_rather_than_hanging(tmp_path):
    """``wait_seconds`` is a budget, not a promise. When it runs out the caller
    gets ``LockBusy`` — the hunt turns that into a withheld receipt, which is
    recoverable; a hang would burn the unit's whole ``TimeoutStartSec``."""
    import json as _json
    import time as _time

    from lab.cli import LockBusy, next_run_lock

    lock = tmp_path / "next.lock"
    lock.write_text(_json.dumps({"pid": os.getpid(), "started": "now",
                                 "milestone": None}), encoding="utf-8")

    env = {k: v for k, v in os.environ.items()
           if not k.startswith("LAB_NEXT_LOCK")}
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        started = _time.monotonic()
        with pytest.raises(LockBusy):
            with next_run_lock(lock, wait_seconds=0.5):
                pass
        assert _time.monotonic() - started < 30
    finally:
        os.environ.clear()
        os.environ.update(saved)
