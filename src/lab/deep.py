"""The deep lane — the hours the scheduler cannot spend.

This box does science about 2 % of the day (`docs/design/2026-08-24-deployment-note.md`).
Not because the GPU is busy: because every scheduled turn is a slot, slots are
sized for the cheapest job on the ladder, and the results that actually moved
the frontier this weekend took hours and were typed by a human. The run that
resolved M12 after two nulls was 4.4 GPU-hours — nine times the lab's entire
daily output — and no lane existed that could have started it.

So: a lane whose unit of work is a NIGHT rather than a slot.

    pulse  · every 6h · minutes · re-verify, keep the page honest
    deep   · nightly  · hours   · one job that could not fit anywhere else

**The queue is explicit and it is a file.** One job per line, run oldest-first.
A human fills it today; the planner may fill it later. It is deliberately not
clever — a lane that chooses its own long-running work, on a box with no
supervision between 23:30 and morning, should earn that privilege after it has
been watched, not before.

**An empty queue is a REPORT, never a fallback.** This is the rule the current
deployment cannot express and the reason §4.2 of the note happened: asked for
frontier work when none was available, the planner quietly did maintenance
forever and every component behaved to spec while the frontier sat still. When
there is nothing worth running, the correct output is a sentence saying so.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from .labhome import LAB_HOME

QUEUE = LAB_HOME / "deep-queue.txt"
DONE = LAB_HOME / "deep-done.log"
LOG = LAB_HOME / "deep.log"

#: The point of the lane. A job that finishes inside a normal slot did not need
#: this lane and should go back to the pulse — reported, not enforced, because
#: a fast night is good news and refusing it would be theatre.
SLOT_MINUTES = 45


def read_queue(path: Path = None) -> list[str]:
    """Runnable jobs, oldest first. ``#`` comments and blanks are skipped."""
    path = path or QUEUE
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _drop_first(path: Path, job: str) -> None:
    """Remove exactly the line we ran — never rewrite the rest of the queue.

    Anything else risks eating a job a human added while the run was in flight,
    and a lane that silently loses work is worse than one that repeats it.
    """
    if not path.exists():
        return
    kept, dropped = [], False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not dropped and raw.strip() == job:
            dropped = True
            continue
        kept.append(raw)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def _log(message: str) -> None:
    LAB_HOME.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {message}\n")


def run_next(queue: Path = None, done: Path = None, runner=None) -> dict:
    """Take the oldest job and run it to completion. No budget, no timeout.

    Returns a verdict dict in every case — including the empty one, which is a
    result and not an absence.
    """
    queue = queue or QUEUE
    done = done or DONE
    jobs = read_queue(queue)
    if not jobs:
        _log("deep: queue empty — nothing worth a night; NOT inventing work")
        return {"outcome": "idle", "job": None,
                "detail": "the queue is empty. An idle lane reports the vacuum; "
                          "it does not manufacture work to look busy."}

    job = jobs[0]
    argv = job.split()
    _log(f"deep: start · {job}")
    t0 = time.time()
    if runner is None:
        proc = subprocess.run([sys.executable, "-m", "lab.cli", *argv],
                              capture_output=False)
        code = proc.returncode
    else:
        code = runner(argv)
    minutes = (time.time() - t0) / 60.0

    verdict = "ok" if code == 0 else f"exit:{code}"
    _log(f"deep: {verdict} · {minutes:.1f} min · {job}")
    # Only a finished job leaves the queue. A crash keeps its place, because the
    # usual cause is a transient (a cold cache, a network blip) and silently
    # discarding the night's work would hide it.
    if code == 0:
        _drop_first(queue, job)
        LAB_HOME.mkdir(parents=True, exist_ok=True)
        with (done).open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                     f"{minutes:.1f}min {job}\n")
    return {"outcome": verdict, "job": job, "minutes": minutes,
            "fit_in_a_slot": minutes < SLOT_MINUTES,
            "detail": (f"ran {job} in {minutes:.1f} min"
                       + (" — that fits in a normal slot and probably belongs in "
                          "the pulse lane" if minutes < SLOT_MINUTES else ""))}
