# Lane 2 — Automation Gates

Gauntlet P1 burn-down, branch `gauntlet/automation-gates`, base `15f0cf6`.
Findings AUTO-F1, F6, F2, F10, F4 from `docs/gauntlet/GAUNTLET-LEDGER.md`.

**The theme.** The publish gate was weaker than the science: exit codes captured and
discarded, success inferred from the *absence* of a failure string, failed runs
committing under messages indistinguishable from successes. Every fix here replaces
an inference with a proof.

---

## Method, and what the harness does and does not simulate

The shell findings are proved by **crash injection** against throwaway clones —
`tests/slot_harness.py` builds a bare origin, a clone, a stub runner standing in for
`scripts/a05_hunt.py`, and drives the real `scripts/a05-hunt-slot.sh`. **No test
touches the real remote, the real MAST API, or any systemd unit.** Faults are
injected as the production incidents actually happened, not stubbed around:

| Fault | How it is produced | Honest about |
|---|---|---|
| Runner crashes after the receipt write | stub runner writes the receipt, prints `receipt -> …`, exits 1 without printing a grade and without refreshing pot.json | exact shape of `a05_hunt.py:296` → crash |
| Grade line scrolls out of the tail window | stub prints `check_a05: False` then 8 more lines | exact shape; the real runner prints after grading |
| `git commit` fails, index left staged | a real failing `pre-commit` hook — **no git stubbing** | same *shape* as losing the index.lock race; it is not a real lock race |
| `git pull --rebase --autostash` conflicts | a second clone pushes a conflicting `pot.json` commit to origin, this clone commits its own | a **real** git conflict and a **real** mid-rebase detached clone |
| `flock` missing | no-op `flock` shim on PATH where the binary is absent | Git Bash on Windows ships no flock; **without the shim `flock -n 9 \|\| exit 0` exits 0 having done nothing and every "nothing was pushed" assertion passes vacuously.** The shim does not simulate contention and no test asserts anything about the lock. |

### shellcheck

`shellcheck` **is installed** (`C:\Users\beschipp\scoop\shims\shellcheck`).

This clone has `core.autocrlf=true`, so the worktree copy of every script is CRLF
and shellcheck reports `SC1017 Literal carriage return` on any of them — an artifact
of the Windows checkout, not of the file git stores. The gate is therefore run
against the bytes git actually ships to loam:

```
$ tr -d '\r' < scripts/a05-hunt-slot.sh | shellcheck -f gcc -s bash -
```

Baseline for reference — the **pre-fix** script was not clean:

```
$ git show 15f0cf6:scripts/a05-hunt-slot.sh | shellcheck -f gcc -s bash -
-:64:1: note: Consider using { cmd1; cmd2; } >> file instead of individual redirects. [SC2129]
rc=1
```

Result after this lane's changes: **clean, rc=0** (see each finding below).

### A note on the pre-existing suite

`tests/test_hunt_slot_script.py` (8 regressions for this same script) **skipped
wholesale on Windows** for want of `flock` — so the box that edits the script never
ran them. They now run on the shared harness. Verified to pass on the **base**
script and on the **fixed** script, so nothing in this lane changed their meaning:

```
$ git checkout 15f0cf6 -- scripts/a05-hunt-slot.sh
$ python -m pytest tests/test_hunt_slot_script.py -q --no-header
tests\test_hunt_slot_script.py ........                                  [100%]
============================= 8 passed in 12.27s ==============================
```

---

## The whole-lane BEFORE block

Nine gate tests, all failing against the unmodified tree at `15f0cf6`:

```
$ python -m pytest tests/test_hunt_slot_gates.py -q --no-header
FAILED tests/test_hunt_slot_gates.py::test_a_crashed_runner_publishes_nothing
FAILED tests/test_hunt_slot_gates.py::test_a_crashed_runner_leaves_the_clone_runnable
FAILED tests/test_hunt_slot_gates.py::test_a_failing_grade_that_scrolled_out_of_the_tail_window_publishes_nothing
FAILED tests/test_hunt_slot_gates.py::test_the_gate_reads_this_runs_log_not_the_days
FAILED tests/test_hunt_slot_gates.py::test_a_failed_commit_does_not_exit_green
FAILED tests/test_hunt_slot_gates.py::test_a_failed_commit_does_not_leave_the_receipt_staged
FAILED tests/test_hunt_slot_gates.py::test_a_failed_commit_does_not_strand_its_receipt_in_the_ledger
FAILED tests/test_hunt_slot_gates.py::test_a_conflicted_pull_aborts_the_slot_before_the_hunt
FAILED tests/test_hunt_slot_gates.py::test_a_conflicted_pull_leaves_the_clone_on_main
======================== 9 failed, 2 passed in 17.71s =========================
```

Committed failing at `f5435ab` before any fix landed.

---

## AUTO-F1 — push gate is a log grep, exit code discarded — **CLOSED**

**Confirmed at the base.** `scripts/a05-hunt-slot.sh:69` captured `rc=$?` and never
read it again; `:87` inferred success from `tail -5 "$log"` **not** matching
`check_a05: \(None\|False\)`. Two independent ways to publish an ungraded receipt.

A third, found while building the proof and not in the dossier: the receipt path was
read as `sed -n 's|^receipt -> ||p' "$log" | tail -1` over the **whole day's log**.
There is one log per sector per day and all four slots append to it, so a crashed
slot 2 that printed no receipt line inherits **slot 1's** path and republishes an
already-committed receipt.

### BEFORE — the gate passes wrongly

```
$ python -m pytest tests/test_hunt_slot_gates.py -q --no-header -k "crashed or scrolled or reads_this_runs_log"

E   AssertionError: assert 'reports/hunts/hunt-2026-08-21-s3.json' not in
      {'pot.json', 'reports/hunts/.keep', 'reports/hunts/hunt-2026-08-21-s3.json',
       'scripts/a05_hunt.py'}
     +  where {...} = pushed_files()
tests\test_hunt_slot_gates.py:52

E   AssertionError: assert 'reports/hunts/hunt-2026-08-21-s3-1302.json' not in
      {'pot.json', 'reports/hunts/.keep',
       'reports/hunts/hunt-2026-08-21-s3-1302.json', 'scripts/a05_hunt.py'}
tests\test_hunt_slot_gates.py:62

FAILED test_a_crashed_runner_publishes_nothing
FAILED test_a_crashed_runner_leaves_the_clone_runnable
FAILED test_a_failing_grade_that_scrolled_out_of_the_tail_window_publishes_nothing
FAILED test_the_gate_reads_this_runs_log_not_the_days
```

The crashed run's receipt is **in `origin/main`**, published beside a `pot.json`
the dead run never refreshed — `pot == hunt_block()` no longer holds and CI reddens
on the producer's own commit. That is the realized 2026-08-15 class, claimed closed.

### The fix

Three changes, all replacing inference with proof:

1. **Window the log.** `log_mark=$(wc -l <"$log")` before the runner; everything read
   back comes from `run_log="$(tail -n +$((log_mark + 1)) "$log")"`. No fixed-size
   tail window, no cross-slot bleed.
2. **Proof 1 — the exit code.** `[ "$rc" -ne 0 ]` quarantines the receipt, restores
   `pot.json`, and exits `$rc`.
3. **Proof 2 — a positive grade token.** `grep -q '^check_a05: True'` over this run's
   log. Publishing now requires the runner to have *said* it graded, rather than to
   have failed to say it did not. **No gate in this script keys on string-absence
   any more.**

`quarantine_receipt` also gained a guard: the real runner quarantines its own
ungraded receipts and prints the *settled* path, so the wrapper must never `mv` a
file onto itself.

### AFTER — the gate refuses

```
$ python -m pytest tests/test_hunt_slot_gates.py -q --no-header -k "crashed or scrolled or reads_this_runs_log or graded_run_still"
tests\test_hunt_slot_gates.py .....                                      [100%]
5 passed
```

```
$ tr -d '\r' < scripts/a05-hunt-slot.sh | shellcheck -f gcc -s bash -
rc=0
```

**Commit:** `<F1-SHA>`

---

## AUTO-F6 — `git commit … || exit 0` conflates every failure with "nothing to commit"

_pending_

## AUTO-F2 — `git pull --rebase --autostash` exit unchecked

_pending_

## AUTO-F10 — MAST outage rows count as DONE

_pending_

## AUTO-F4 — quarantine-resume livelock

_pending_
