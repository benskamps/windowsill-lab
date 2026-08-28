"""The slot's publish gate, proved by injecting the failures it is supposed to stop.

``tests/test_hunt_slot_script.py`` proves the slot does the right thing when
everything works. These prove it REFUSES when something breaks — the half that
was missing, and the half the 2026-08-15 red main came from.

Three gates, three injected faults, all against throwaway clones:

* **AUTO-F1** — the runner crashes between writing its receipt and grading it.
  The wrapper captured ``rc=$?`` and never read it, then inferred success from the
  ABSENCE of ``check_a05: None|False`` in the last five log lines. An ungraded
  receipt therefore published, with a pot.json the crashed run never refreshed:
  CI recomputes ``pot == hunt_block()`` from the committed set and goes red, in the
  producer's own commit.
* **AUTO-F6** — ``git commit`` fails for a reason that is not "nothing to commit"
  (losing the index.lock race to ``campaign.sh``, which shares this clone and these
  hours). ``|| exit 0`` conflated the two, leaving the receipt STAGED — and a staged
  index is one of the three conditions campaign.sh refuses to run against, so one
  lost race silently halted the other lane until a human noticed.
* **AUTO-F2** — ``git pull --rebase --autostash`` conflicts. Its status was
  discarded, so the 100-minute hunt burned against a clone that was mid-rebase and
  detached, and its receipt was stranded. ``campaign.sh:169`` (``safe_pull_rebase``)
  already fixed this class; the sibling script regressed it.

Nothing here touches the real remote, the real MAST API, or any systemd unit.
"""
from __future__ import annotations

import pytest

from tests.slot_harness import make_slot


@pytest.fixture
def slot(tmp_path):
    return make_slot(tmp_path)


# --- AUTO-F1: the exit code is the gate, and the grade must be POSITIVE -------

def test_a_crashed_runner_publishes_nothing(slot):
    """The realized 8/15 class. The receipt is on disk and no failure string was
    ever printed, so an absence-gate reads the crash as a success."""
    proc = slot.run("hunt-2026-08-21-s3.json", crash_after_receipt=True)
    assert "reports/hunts/hunt-2026-08-21-s3.json" not in slot.pushed_files()
    assert proc.returncode != 0, "a crashed hunt must not exit green"


def test_a_crashed_runner_leaves_the_clone_runnable(slot):
    """...and must not strand its receipt in the directory the pot aggregator
    globs, or the next publishing run counts a hunt that never graded."""
    slot.run("hunt-2026-08-21-s3.json", crash_after_receipt=True)
    assert slot.is_clean(), "campaign.sh would refuse to run against this clone"
    assert not (slot.repo / "reports" / "hunts" / "hunt-2026-08-21-s3.json").exists()


def test_a_failing_grade_that_scrolled_out_of_the_tail_window_publishes_nothing(slot):
    """``tail -5 | grep -q 'check_a05: (None|False)'`` is a five-line window onto a
    log the runner keeps writing to. Push the grade line out of it and the gate
    stops seeing the failure at all — string-ABSENCE is not evidence of success."""
    slot.run("hunt-2026-08-21-s3-1302.json", grade="False", trailing_lines=8)
    assert "reports/hunts/hunt-2026-08-21-s3-1302.json" not in slot.pushed_files()


def test_the_gate_reads_this_runs_log_not_the_days(slot):
    """One log file per sector per DAY, appended by all four slots. A crashed run
    that printed no receipt line must not inherit the previous slot's."""
    slot.run("hunt-2026-08-21-s3.json")               # slot 1: graded, published
    slot.run("hunt-2026-08-21-s3-1302.json", crash_after_receipt=True)  # slot 2
    pushed = slot.pushed_files()
    assert "reports/hunts/hunt-2026-08-21-s3.json" in pushed
    assert "reports/hunts/hunt-2026-08-21-s3-1302.json" not in pushed


def test_a_run_that_graded_and_then_died_publishes_nothing(slot):
    """The other side of the crash window. ``a05_hunt.py`` refreshes pot.json AFTER
    grading, so a run can print ``check_a05: True`` and still die before the pot and
    the receipt agree. A positive grade is necessary, not sufficient — rc is the
    other half, which is why the gate needs both."""
    proc = slot.run("hunt-2026-08-21-s3.json", exit_code=3)
    assert "reports/hunts/hunt-2026-08-21-s3.json" not in slot.pushed_files()
    assert proc.returncode == 3, "the runner's own exit code should survive"
    assert slot.is_clean()


def test_a_graded_run_still_publishes(slot):
    """The gate tightened, not the lane closed."""
    slot.run("hunt-2026-08-21-s3.json")
    assert "reports/hunts/hunt-2026-08-21-s3.json" in slot.pushed_files()
    assert "4686" in slot.log_text() or slot.is_clean()


# --- AUTO-F6: nothing-to-commit is not the same as commit failed --------------

def test_a_failed_commit_does_not_exit_green(slot):
    """A green exit under a green unit is how the lane loses days."""
    slot.break_commit()
    proc = slot.run("hunt-2026-08-21-s3.json")
    assert proc.returncode != 0


def test_a_failed_commit_does_not_leave_the_receipt_staged(slot):
    """THE regression: campaign.sh refuses to run a pass against a staged index,
    so losing one index.lock race silently halted the physics lane."""
    slot.break_commit()
    slot.run("hunt-2026-08-21-s3.json")
    assert slot.is_clean(), "campaign.sh would refuse to run against this clone"


def test_a_failed_commit_does_not_strand_its_receipt_in_the_ledger(slot):
    """An uncommitted receipt left in reports/hunts/ is counted by the pot
    aggregator (which globs the directory) but not by CI (which reads git)."""
    slot.break_commit()
    slot.run("hunt-2026-08-21-s3.json")
    assert not (slot.repo / "reports" / "hunts" / "hunt-2026-08-21-s3.json").exists()
    assert (slot.lab / "ungraded" / "hunt-2026-08-21-s3.json").exists()


def test_transient_index_lock_contention_is_retried_not_abandoned(slot):
    """Losing the race to a campaign pass is transient by construction — the other
    lane finishes its own commit in seconds. Bounded retry, then publish."""
    slot.break_commit(fail_times=2)
    proc = slot.run("hunt-2026-08-21-s3.json")
    assert proc.returncode == 0
    assert slot.commit_attempts() == 3, "the slot gave up on transient contention"
    assert "reports/hunts/hunt-2026-08-21-s3.json" in slot.pushed_files()


def test_genuinely_nothing_to_commit_is_still_a_quiet_success(slot):
    """The branch ``|| exit 0`` was actually there for. Re-running a slot whose
    receipt is already published stages nothing and must exit 0, not alarm."""
    slot.run("hunt-2026-08-21-s3.json")
    proc = slot.run("hunt-2026-08-21-s3.json")
    assert proc.returncode == 0
    assert slot.is_clean()


# --- AUTO-F2: a failed sync aborts the slot BEFORE the hunt starts ------------

def test_a_conflicted_pull_aborts_the_slot_before_the_hunt(slot):
    """100 minutes of telescope archive time against a clone that is mid-rebase
    and detached, ending in a push that silently fails. Check the pull first."""
    slot.diverge_with_conflict()
    proc = slot.run("hunt-2026-08-21-s3.json")
    assert not slot.hunt_ran(), "the hunt burned against an unsynced clone"
    assert proc.returncode != 0


def test_a_conflicted_pull_leaves_the_clone_on_main(slot):
    """campaign.sh's third condition. A clone left detached logs 'on HEAD not
    main' on every later pass — a symptom four days downstream of its cause."""
    slot.diverge_with_conflict()
    slot.run("hunt-2026-08-21-s3.json")
    assert slot.branch() == "main"
    assert not (slot.repo / ".git" / "rebase-merge").exists()
    assert not (slot.repo / ".git" / "rebase-apply").exists()


# --- AUTO-F7: an intended empty slice is not a failure, and silence still is --
#
# 2026-08-28. The 09:02 slot did exactly what it is designed to do: the runner's
# soft minutes budget stopped the search cleanly at 192 rows, checkpointed, and
# wrote NO receipt because a receipt for an incomplete slice would be a lie. It
# exited 0. The wrapper then exited 1 — "no receipt path in this run's log" —
# and systemd logged `Failed to start` on a slot that worked.
#
# The guard itself is right and stays: a missing receipt is what a crash, a
# truncated log and a renamed print ALL look like, so absence may never be read
# as success. What was missing is the third state. This is the same two-way
# collapse `honesty_eval.py` was opened up for in warden on 2026-08-16 —
# ABSENT, MALFORMED and PRESENT are three outcomes, not two — and the rule is
# the same here: only the producer's OWN positive declaration, scoped to this
# run's log window, may distinguish an intended empty slice from a silent one.

def test_a_declared_budget_wall_is_a_quiet_success(slot):
    """The runner said it stopped on budget. That is a slot doing its job."""
    proc = slot.run("hunt-2026-08-28-s30.json", no_receipt=True, budget_wall=True)
    assert proc.returncode == 0, "an intended empty slice must not alarm"
    assert slot.hunt_ran()


def test_a_declared_budget_wall_publishes_nothing(slot):
    """Exiting green may not become a licence to publish an absent receipt."""
    slot.run("hunt-2026-08-28-s30.json", no_receipt=True, budget_wall=True)
    assert not any(f.startswith("reports/hunts/hunt-") for f in slot.pushed_files())
    assert slot.is_clean(), "the next campaign pass has to find this clone clean"


def test_a_silent_missing_receipt_is_still_a_failure(slot):
    """THE NEGATIVE CONTROL. Same absent receipt, no declaration from the runner
    — a crash between the search and the receipt write looks exactly like this.
    If this ever goes green the fix has blanket-greened the gate instead of
    opening a third state in it."""
    proc = slot.run("hunt-2026-08-28-s30.json", no_receipt=True, budget_wall=False)
    assert proc.returncode != 0, "absence without a declaration is still absence"
