"""Behavioural fixtures for the hunt slot's git side — real clones, real pushes.

``scripts/a05-hunt-slot.sh`` is the wrapper the timer fires four times a day. Its
two jobs are small and both failed SILENTLY in production on 2026-08-17/18, under a
systemd unit that stayed green the whole time:

* it staged with a glob that predated the runner's ``-HHMM`` receipt suffix, so only
  the day's FIRST slot ever matched — slots 2-4 wrote graded receipts that nothing
  staged, and ``git commit`` said "nothing to commit" and exited 0;
* it left the runner's in-place refresh of ``pot.json`` sitting dirty, and
  ``campaign.sh`` refuses to run against a dirty tracked file — so the survey lane
  quietly halted the physics lane for ~33h (campaign passes 119-124, never run).

The pot has two rules, not one, and they pull in opposite directions: a receipt
published WITHOUT its refreshed aggregate ships a red main (CI enforces
``pot == hunt_block()``), while a pot left dirty by a run that publishes NOTHING
halts the campaign. So a pushed receipt takes pot.json with it and every other exit
restores it — and an ungraded receipt leaves ``reports/hunts/`` entirely, because the
aggregator globs that directory and would otherwise count a run whose control failed.

Neither is visible to a static text pin, so these drive the real script against
throwaway clones with a stub runner standing in for ``scripts/a05_hunt.py``.

The rig lives in ``tests/slot_harness.py``, shared with ``test_hunt_slot_gates.py``.
These eight used to skip wholesale on Windows for want of ``flock``, which meant the
box that edits the script never ran its regressions; the harness supplies a no-op
flock shim where the real binary is missing, so the rest of the script runs for real.
"""
import pytest

from tests.slot_harness import git as _git, make_slot


@pytest.fixture
def slot(tmp_path):
    return make_slot(tmp_path)


def test_a_suffixed_receipt_is_staged_and_pushed(slot):
    """Slot 2-4 of a day. The old glob matched only the bare name and lost these."""
    slot.run("hunt-2026-08-18-s3-1302.json")
    assert "reports/hunts/hunt-2026-08-18-s3-1302.json" in slot.pushed_files()


def test_the_days_first_receipt_still_pushes(slot):
    """The bare name the old glob DID match must keep working."""
    slot.run("hunt-2026-08-18-s3.json")
    assert "reports/hunts/hunt-2026-08-18-s3.json" in slot.pushed_files()


def test_a_lead_dossier_travels_with_its_receipt(slot):
    """A receipt cites its dossier; publishing one without the other strands the lead."""
    slot.run(
        "hunt-2026-08-18-s3-1302.json",
        dossier="hunt-2026-08-18-s3-1302-tic287328866.html",
    )
    pushed = slot.pushed_files()
    assert "reports/hunts/hunt-2026-08-18-s3-1302.json" in pushed
    assert "reports/hunts/dossiers/hunt-2026-08-18-s3-1302-tic287328866.html" in pushed


def test_an_ungraded_run_pushes_nothing(slot):
    """check_a05 None/False stays local with the log — win's contract."""
    before = slot.pushed_files()
    slot.run("hunt-2026-08-18-s3-1902.json", grade="None")
    assert slot.pushed_files() == before


def test_an_ungraded_receipt_is_kept_but_moved_out_of_the_ledger(slot):
    """The evidence survives; it just stops being counted. The aggregator globs
    reports/hunts/ rather than git, so a receipt left there is published by the
    next run that pushes, while CI recomputes from the committed set and goes red."""
    slot.run("hunt-2026-08-18-s3-1902.json", grade="None")
    assert not (slot.repo / "reports" / "hunts" / "hunt-2026-08-18-s3-1902.json").exists()
    assert (slot.lab / "ungraded" / "hunt-2026-08-18-s3-1902.json").exists()


def test_an_ungraded_run_leaves_the_clone_runnable(slot):
    """THE regression: an ungraded run used to leave pot.json dirty, and a dirty
    tracked file makes campaign.sh refuse every pass until a human clears it."""
    slot.run("hunt-2026-08-18-s3-1902.json", grade="None")
    assert slot.is_clean(), "campaign.sh would refuse to run against this clone"


def test_a_graded_run_leaves_the_clone_runnable(slot):
    """Same invariant on the push path."""
    slot.run("hunt-2026-08-18-s3-1302.json")
    assert slot.is_clean(), "campaign.sh would refuse to run against this clone"


def test_a_receipt_is_published_with_its_refreshed_aggregate(slot):
    """CI enforces pot == hunt_block(), so a receipt whose commit leaves the pot
    behind ships a red main in the producer's own commit."""
    slot.run("hunt-2026-08-18-s3-1302.json")
    committed = _git(slot.repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert "pot.json" in committed
    assert "reports/hunts/hunt-2026-08-18-s3-1302.json" in committed
    assert "4686" in _git(slot.repo, "show", "origin/main:pot.json")
