"""AUTO-F5 — what the NEXT slot does about a hunt that was killed outright.

``windowsill-hunt.service`` sets ``TimeoutStartSec=2h``. When it expires systemd
kills the unit's whole cgroup, and a SIGKILL runs no exit path at all: not
``quarantine_receipt``, not ``restore_pot``, and not a trap — ``a05-hunt-slot.sh``
has none (``campaign.sh:209`` does; its sibling never grew one). The graceful
refusals are all covered, ``276c7b6`` included — that one added the quarantine to
the ``git add`` failure branch, which is a branch the shell actually *executes*.
Process death executes nothing.

Two shapes of debris survive that death, and each breaks a different lane:

* **An untracked receipt in ``reports/hunts/``.** The pot aggregator globs that
  DIRECTORY (``src/lab/publish.py``) while CI recomputes ``pot == hunt_block()``
  from the COMMITTED set. The next run that publishes therefore ships a pot
  counting a receipt CI cannot see, and main goes red in that run's own commit.
  This is the 2026-08-15 class arriving by a different road.

* **A dirty ``pot.json``.** ``campaign.sh:281`` refuses to run a pass against
  pre-existing tracked worktree changes, so every later campaign pass is
  declined until a human looks. That is passes 119-124 — ~33h — with both units
  green.

The state these tests inject IS the aftermath of the kill; there is nothing else
to reproduce, because the kill leaves no code running to observe. What is under
test is the only thing that can still be fixed: whether the NEXT run notices.
"""
from __future__ import annotations

import json

import pytest

from tests.slot_harness import git, make_slot


@pytest.fixture
def slot(tmp_path):
    return make_slot(tmp_path)


def _kill_debris(slot, *, receipt="hunt-2026-08-21-s3.json", dirty_pot=True):
    """The disk as a SIGKILLed slot leaves it: an untracked receipt the dead run
    wrote, its dossier beside it, and (if it got that far) a pot.json refreshed
    but never committed."""
    orphan = slot.repo / "reports" / "hunts" / receipt
    orphan.write_text(json.dumps({"experiment": "a05-survey-hunt", "schema": 1,
                                  "counts": {"targets_searched": 200}}),
                      encoding="utf-8")
    dossiers = slot.repo / "reports" / "hunts" / "dossiers"
    dossiers.mkdir(parents=True, exist_ok=True)
    stem = receipt[: -len(".json")]
    (dossiers / f"{stem}-tic999.html").write_text("<html>orphan</html>",
                                                  encoding="utf-8")
    if dirty_pot:
        (slot.repo / "pot.json").write_text(
            json.dumps({"hunt": {"targets_searched": 9999}}), encoding="utf-8")
    return orphan


def _receipts_on_disk(slot) -> set[str]:
    return {p.name for p in (slot.repo / "reports" / "hunts").glob("*.json")}


def _receipts_in_git(slot) -> set[str]:
    return {name.rsplit("/", 1)[-1] for name in slot.pushed_files()
            if name.startswith("reports/hunts/") and name.endswith(".json")}


def test_an_orphan_receipt_from_a_killed_run_is_not_left_to_redden_main(slot):
    """The invariant CI's ``pot == hunt_block()`` actually rests on: every
    receipt the aggregator can SEE is a receipt git has.

    A killed run leaves one that git does not have, and the very next successful
    slot publishes a pot computed over both. Nothing in the slot script looked
    for it, so the orphan sat there being counted."""
    _kill_debris(slot, dirty_pot=False)

    proc = slot.run("hunt-2026-08-22-s3.json", grade="True")

    assert proc.returncode == 0, proc.stderr
    assert _receipts_on_disk(slot) == _receipts_in_git(slot), (
        "a receipt the pot aggregator globs is not in the committed set — the "
        "next publish ships a pot CI cannot reproduce")
    quarantined = {p.name for p in (slot.lab / "ungraded").glob("*.json")}
    assert "hunt-2026-08-21-s3.json" in quarantined, (
        "the orphan was neither published nor filed — its evidence is gone")


def test_a_killed_runs_dossier_travels_into_quarantine_with_its_receipt(slot):
    """Same rule as every other refusal: a lead's dossier is cited by the
    receipt that ships it, so it goes wherever the receipt goes."""
    _kill_debris(slot, dirty_pot=False)

    slot.run("hunt-2026-08-22-s3.json", grade="True")

    filed = {p.name for p in slot.lab.glob("ungraded/*")}
    assert "hunt-2026-08-21-s3-tic999.html" in filed, filed


def test_the_dirty_pot_a_killed_run_left_stops_stalling_the_campaign_lane(slot):
    """Passes 119-124, reproduced from the other end.

    The kill left pot.json modified and never committed. The next slot cannot
    hunt either — here because the clone cannot reach origin — and on the base
    it exits without ever looking at the mess, so the tracked worktree stays
    dirty and campaign.sh declines every pass behind it. Reconciliation has to
    happen BEFORE the pull, or the one thing that unblocks the other lane is
    gated on the thing that just failed."""
    _kill_debris(slot)
    git(slot.repo, "remote", "set-url", "origin",
        str(slot.tmp_path / "no-such-origin.git"))

    proc = slot.run("hunt-2026-08-22-s3.json", grade="True")

    assert proc.returncode != 0
    assert not slot.hunt_ran(), "the slot hunted against an unsynced clone"
    assert slot.is_clean(), (
        "pot.json is still dirty after a slot that refused to run — campaign.sh "
        "declines every pass behind it (the 33h stall)")
    assert (slot.lab / "ungraded" / "hunt-2026-08-21-s3.json").exists()


def test_reconciliation_leaves_a_healthy_clone_alone(slot):
    """The guard on the guard. With no debris, a normal slot must behave
    exactly as it did: hunt, stage, commit, push, and touch nothing else."""
    proc = slot.run("hunt-2026-08-22-s3.json", grade="True")

    assert proc.returncode == 0, proc.stderr
    assert slot.hunt_ran()
    assert "reports/hunts/hunt-2026-08-22-s3.json" in slot.pushed_files()
    assert slot.is_clean()
    assert not list(slot.lab.glob("ungraded/*"))


def test_a_dirty_pot_with_no_orphan_receipt_is_left_alone(slot):
    """Deliberately NOT reconciled, and the restraint is the point.

    campaign.sh writes pot.json too, in this same clone, with no git-level lock
    between the lanes (LANE2-AUTOMATION.md). A dirty pot on its own is as likely
    to be a campaign pass mid-flight as a dead hunt, and reverting it would be
    this lane destroying the other lane's work — the exact class STR-1 is about.
    A dirty pot PLUS an untracked hunt receipt is unambiguous; a dirty pot alone
    is not, so it is left for the slot's own restore_pot to handle on the paths
    that know they own it."""
    (slot.repo / "pot.json").write_text(
        json.dumps({"hunt": {"targets_searched": 4242}}), encoding="utf-8")
    git(slot.repo, "remote", "set-url", "origin",
        str(slot.tmp_path / "no-such-origin.git"))

    slot.run("hunt-2026-08-22-s3.json", grade="True")

    assert json.loads((slot.repo / "pot.json").read_text(encoding="utf-8")) == {
        "hunt": {"targets_searched": 4242}}
