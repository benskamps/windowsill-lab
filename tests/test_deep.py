"""The deep lane — hours instead of slots, and a vacuum it is allowed to report.

The rule under test that matters most is the negative one: asked to work when
there is nothing worth doing, this lane must say so. The current scheduler
cannot express that, which is how §4.2 of the deployment note happened — a
planner with no frontier available did maintenance forever, faithfully, at
exit 0, while every component behaved to spec.
"""
from __future__ import annotations

from lab import deep


def _queue(tmp_path, *lines):
    q = tmp_path / "deep-queue.txt"
    q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return q


def test_comments_and_blanks_are_not_jobs(tmp_path):
    q = _queue(tmp_path, "# a note", "", "m14 --L-values 32", "   ", "# trailing")
    assert deep.read_queue(q) == ["m14 --L-values 32"]


def test_an_empty_queue_is_a_result_not_a_fallback(tmp_path):
    """The load-bearing test. An idle lane reports the vacuum; it does not
    manufacture work to look busy."""
    verdict = deep.run_next(queue=tmp_path / "nothing.txt", done=tmp_path / "d.log")
    assert verdict["outcome"] == "idle"
    assert verdict["job"] is None
    assert "does not manufacture work" in verdict["detail"]


def test_a_queue_of_only_comments_is_also_idle(tmp_path):
    q = _queue(tmp_path, "# just thinking out loud")
    assert deep.run_next(queue=q, done=tmp_path / "d.log")["outcome"] == "idle"


def test_the_oldest_job_runs_first(tmp_path):
    seen = []
    q = _queue(tmp_path, "m14 --first", "p01 --second")
    deep.run_next(queue=q, done=tmp_path / "d.log",
                  runner=lambda argv: seen.append(argv) or 0)
    assert seen == [["m14", "--first"]]


def test_a_finished_job_leaves_the_queue_and_lands_in_the_ledger(tmp_path):
    q = _queue(tmp_path, "m14 --run", "p01 --later")
    done = tmp_path / "done.log"
    deep.run_next(queue=q, done=done, runner=lambda argv: 0)
    assert deep.read_queue(q) == ["p01 --later"]
    assert "m14 --run" in done.read_text(encoding="utf-8")


def test_a_crashed_job_keeps_its_place(tmp_path):
    """The usual cause is a transient — a cold cache, a network blip — and a
    lane that silently discards a failed night hides it."""
    q = _queue(tmp_path, "m14 --run")
    verdict = deep.run_next(queue=q, done=tmp_path / "d.log",
                            runner=lambda argv: 3)
    assert verdict["outcome"] == "exit:3"
    assert deep.read_queue(q) == ["m14 --run"], "a failure must not eat the job"


def test_only_the_line_we_ran_is_removed(tmp_path):
    """Never rewrite the rest of the queue: a human may have appended a job
    while the night was in flight, and losing it silently is unforgivable."""
    q = _queue(tmp_path, "m14 --run", "# keep me", "p01 --later")
    deep.run_next(queue=q, done=tmp_path / "d.log", runner=lambda argv: 0)
    body = q.read_text(encoding="utf-8")
    assert "# keep me" in body and "p01 --later" in body
    assert "m14 --run" not in body


def test_a_job_that_fits_in_a_slot_is_reported_as_misfiled(tmp_path):
    """Not enforced — a fast night is good news — but a job that never needed
    hours belongs in the pulse lane, and the lane should say so rather than
    quietly justify its own existence."""
    q = _queue(tmp_path, "p01")
    verdict = deep.run_next(queue=q, done=tmp_path / "d.log", runner=lambda argv: 0)
    assert verdict["fit_in_a_slot"] is True
    assert "belongs in the pulse lane" in verdict["detail"]


def test_the_shipped_queue_is_readable_and_its_first_job_is_a_real_command(tmp_path):
    """The one non-hermetic check: whatever is queued on this box must at least
    name a subcommand the CLI has, or the night is wasted on a typo."""
    from lab import curriculum
    jobs = deep.read_queue()
    if not jobs:
        return                      # an empty queue is legitimate
    head = jobs[0].split()[0]
    assert head in set(curriculum.RUNNERS.values()) | {"frontier", "publish", "verify"}, head
