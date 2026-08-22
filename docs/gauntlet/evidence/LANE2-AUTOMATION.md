# Lane 2 — Automation Gates

Gauntlet P1 burn-down, branch `gauntlet/automation-gates`, base `15f0cf6`.
Findings AUTO-F1, F6, F2, F10, F4 from `docs/gauntlet/GAUNTLET-LEDGER.md`.

**The theme.** The publish gate was weaker than the science: exit codes captured and
discarded, success inferred from the *absence* of a failure string, failed runs
committing under messages indistinguishable from successes. Every fix here replaces
an inference with a proof.

| Finding | Verdict | Commit | Proof |
|---|---|---|---|
| **AUTO-F1** push gate is a log grep, exit code discarded | **CLOSED** | `eca3d44` | crash injection, 4 tests |
| **AUTO-F6** `git commit … \|\| exit 0` conflates every failure | **CLOSED** | `a558b36` | real failing pre-commit hook, 4 tests |
| **AUTO-F2** `git pull --rebase` exit unchecked | **CLOSED** | `616ff20` | real git conflict + real detached clone, 2 tests |
| **AUTO-F10** MAST outage rows count as DONE | **CLOSED** | `06f72ff` | 4 regression tests, written first |
| **AUTO-F4** quarantine-resume livelock | **CLOSED** | `b0ecf36` | livelock driven over 6 slots, 2 tests |

All five were **confirmed at the base** — none refuted. The failing harness was
committed first, at `f5435ab`, so the pre-fix state is re-runnable from git rather
than only quoted here.

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

**Commit:** `eca3d44`

---

## AUTO-F6 — `git commit … || exit 0` conflates every failure with "nothing to commit" — **CLOSED**

**Confirmed at the base.** `scripts/a05-hunt-slot.sh:103-105`:

```bash
git commit -q -m "a05: hunt receipt sector ${sector} $(date +%F) (loam slot)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" || exit 0  # nothing new to commit
```

One branch for two failures, only one of which is benign. `campaign.sh` runs in
this same clone in these same hours; lose the `.git/index.lock` race to it and the
commit fails with the receipt **staged** — and a staged index is one of the three
conditions `campaign.sh` itself refuses to run against. One lost race silently halts
the *other* lane, under a green unit, until a human notices.

### BEFORE — the gate passes wrongly

```
$ python -m pytest tests/test_hunt_slot_gates.py -q --no-header -k commit

E   assert 0 != 0
     +  where 0 = CompletedProcess(args=[…'a05-hunt-slot.sh'],
          …stderr="…Unable to create '…/loam/.git/index.lock': File exists.\n").returncode
tests\test_hunt_slot_gates.py:88

E   AssertionError: campaign.sh would refuse to run against this clone
    assert False
     +  where False = is_clean()
tests\test_hunt_slot_gates.py:96

E   AssertionError: assert not True
     +  where True = (…/'loam'/'reports'/'hunts'/'hunt-2026-08-21-s3.json').exists
tests\test_hunt_slot_gates.py:104

FAILED test_a_failed_commit_does_not_exit_green
FAILED test_a_failed_commit_does_not_leave_the_receipt_staged
FAILED test_a_failed_commit_does_not_strand_its_receipt_in_the_ledger
```

Note the first: **exit code 0**, with the commit having failed. That is what the
systemd unit sees — green — while the receipt sits staged and the physics lane is
blocked.

### The fix

* **Discriminate by asking the index.** `git diff --cached --quiet --` after a failed
  commit: nothing staged → the receipt was already published, quiet `exit 0` (the
  case the old `|| exit 0` was actually written for). Anything staged → the commit
  really failed: log it, `git reset` the pathspec so the campaign lane is not
  blocked, quarantine the receipt out of the aggregator's glob, `exit 1`.
* **Bounded retry on the named root cause.** Contention with `campaign.sh` is
  transient by construction, so the commit is retried while the failure output names
  `index.lock`, `LAB_HUNT_COMMIT_TRIES` (4) times with `LAB_HUNT_COMMIT_SLEEP` (5s)
  between. Deadlock-free: it acquires nothing and waits on nothing.
* `quarantine_receipt` now takes a lead's dossier with it, matching what
  `a05_hunt.py:settle_receipt` does — a receipt cites its dossier, so they move
  together or not at all.

**The root cause is NOT closed.** Two lanes, one clone, no git-level lock between
them. A real shared lock needs `campaign.sh` to take the same one, and `campaign.sh`
belongs to another lane of this gauntlet (AUTO-F3/F5) — touching it here would
collide. **Recommended follow-up:** one `flock` on `$LAB/clone.lock` held across the
stage-commit-push window in *both* scripts. Until then the retry converts a silent
lane-halt into, at worst, a loud skipped slot.

### AFTER — the gate refuses

```
$ python -m pytest tests/test_hunt_slot_gates.py -q --no-header -k commit
tests\test_hunt_slot_gates.py ....                                       [100%]
======================= 4 passed, 8 deselected in 9.59s =======================
```

Four, not three: the fourth is
`test_genuinely_nothing_to_commit_is_still_a_quiet_success`, which pins the benign
branch so the fix did not turn a re-run into an alarm.

A fifth test covers the retry and does not match that `-k` filter:

```
$ python -m pytest tests/test_hunt_slot_gates.py -q --no-header \
      -k transient_index_lock
tests\test_hunt_slot_gates.py .                                          [100%]
====================== 1 passed, 11 deselected in 2.35s =======================
```

`test_transient_index_lock_contention_is_retried_not_abandoned` asserts the slot
publishes on the third attempt (`commit_attempts() == 3`) rather than giving up.

```
$ tr -d '\r' < scripts/a05-hunt-slot.sh | shellcheck -f gcc -s bash -
shellcheck rc=0
```

**Commit:** `a558b36`

## AUTO-F2 — `git pull --rebase --autostash` exit unchecked — **CLOSED**

**Confirmed at the base.** Both call sites discarded the status:

```bash
:64   git pull --rebase --autostash -q 2>>"$log"
:106  git pull --rebase --autostash -q >>"$log" 2>&1
```

A conflict leaves the clone **detached and mid-rebase**. The 100-minute hunt then
burns against an unsynced clone, its commit lands on detached HEAD, the push fails,
the receipt is stranded — and every later `campaign.sh` pass trips its on-main guard
and logs `on 'HEAD' not main`, a symptom four days downstream of its cause.

The injected conflict is **real**, not stubbed: a second clone pushes a conflicting
`pot.json` commit to origin while this clone commits its own, so the slot's own
`git pull --rebase --autostash` genuinely conflicts and genuinely detaches
(`Slot.diverge_with_conflict`). `pot.json` is regenerated by *both* boxes, so this is
the conflict that recurs by construction.

### BEFORE — the gate passes wrongly

```
$ python -m pytest tests/test_hunt_slot_gates.py -q --no-header -k conflicted

E   AssertionError: the hunt burned against an unsynced clone
    assert not True
     +  where True = hunt_ran()
tests\test_hunt_slot_gates.py:124

E   AssertionError: assert 'HEAD' == 'main'
      - main
      + HEAD
tests\test_hunt_slot_gates.py:133

FAILED test_a_conflicted_pull_aborts_the_slot_before_the_hunt
FAILED test_a_conflicted_pull_leaves_the_clone_on_main
```

`hunt_ran()` is a marker the stub runner writes on entry, so the first failure is
literal: **100 minutes of hunting started after the sync had already failed.** The
second is `campaign.sh`'s third precondition, broken by this script.

### The fix

`safe_pull_rebase()`, ported from `scripts/campaign.sh:169` — the sibling that already
fixed this class for the physics lane. Capture output and rc, log the tail of git's
own message, abort the rebase if one is in progress, report whether the abort
restored the clone or left it **STRANDED**, return nonzero. Both call sites now check:

* **Pre-hunt (`:64`)** — failure exits **before the runner starts**. No telescope
  archive time is spent against a clone that did not sync.
* **Post-commit (`:106`)** — failure leaves the receipt committed locally and
  unpushed, and exits 1. Nothing is red: this clone's `pot.json` and its receipt set
  still agree; the work is simply unpublished, and the next slot's pre-hunt pull is
  the retry. The bare `git push` that followed is also checked now.

Deliberately the **strict half** of campaign.sh's version: it does not attempt
`resolve_by_regeneration`, because that helper is campaign.sh's own and rebuilding
the feeds needs the `lab` CLI. **Residual risk, eyes open:** a `pot.json` conflict
that nothing resolves stalls the sector lane — every later slot refuses at the
pre-hunt pull — rather than corrupting it. That is the right trade (a stall is
recoverable, a stranded receipt on a detached HEAD is not), but it is a stall.
**Recommended follow-up:** lift `resolve_by_regeneration` out of `campaign.sh` into a
shared helper both scripts source. That edit lands in `campaign.sh`, which another
lane of this gauntlet owns, so it is not done here.

### AFTER — the gate refuses

```
$ python -m pytest tests/test_hunt_slot_gates.py tests/test_hunt_slot_script.py -q --no-header
tests\test_hunt_slot_gates.py ............                               [ 60%]
tests\test_hunt_slot_script.py ........                                  [100%]
============================= 20 passed in 35.25s =============================
```

```
$ tr -d '\r' < scripts/a05-hunt-slot.sh > /tmp/slot-norm.sh && shellcheck -f json /tmp/slot-norm.sh
(no findings)
```

**Commit:** `616ff20`

## AUTO-F10 — MAST outage rows count as DONE — **CLOSED**

**Confirmed at the base.** The row vocabulary is closed (`src/lab/checks.py:2750`):
`searched` / `skipped-no-product` / `error:<Exc>`. `src/lab/a05.py:723-732` writes an
`error:` row when the loader raises, appends it to the checkpoint, and counts it into
`result.rows` exactly like a real search — so `result.complete` is satisfied by an
outage. `scripts/a05_hunt.py:76-83` and `:91-92` then read the `tic` key and **never
the outcome**, so every errored TIC was excluded from every future hunt.

This is the one finding in the lane that destroys science rather than uptime: the sky
those targets cover leaves the survey **permanently**, with nothing alarming and
nothing retrying. The partial-outage case is worse than the full one, because it
grades and publishes: 40 errored TICs out of 200 vanish under a green receipt.

### BEFORE — the regression tests fail (written first, unmodified tree)

```
$ python -m pytest tests/test_a05_hunt_script.py -q --no-header -k errored

>       assert "222" not in already and "333" not in already, (
E       AssertionError: an outage was recorded as coverage — that sky is now permanently unsearched
E       assert ('222' not in {'111', '222', '333', '444'})

>       assert "888" not in already
E       AssertionError: assert '888' not in {'777', '888'}

FAILED test_an_errored_target_stays_eligible_for_a_later_hunt
FAILED test_an_errored_row_in_a_published_receipt_stays_eligible
====================== 2 failed, 13 deselected in 0.42s =======================
```

### The fix

`was_attempted_but_never_searched(row)` names the distinction once, and both globs in
`prior_targets()` consult it:

* **`error:*` is transient** — attempted, MAST refused, no sky covered. Stays
  eligible for a later hunt.
* **`skipped-no-product` is permanent** — there is genuinely no 2-minute product to
  search. Stays excluded, so the budget is not burned re-attempting it.
* **No readable outcome keeps the old behaviour.** A04's graded receipt lists bare
  `searched` rows with no `outcome` key at all; the conservative reading of an
  unlabelled row is that it ran. The change is strictly narrower than "retry
  everything unfamiliar".

`split_resumable()` applies the same rule one slice inward: a resume re-attempts the
targets that errored on the earlier pass instead of inheriting them as done. The
outage has had the whole slot to clear, and inheriting would freeze it into *this*
slice's receipt. Re-erroring costs one extra checkpoint row; `run_a05` keys rows by
TIC, so the last one per target wins.

### AFTER — the regression tests pass

```
$ python -m pytest tests/test_a05_hunt_script.py -q --no-header
tests\test_a05_hunt_script.py ...............F                           [100%]
======================== 1 failed, 15 passed in 0.51s =========================
```

The one remaining failure is AUTO-F4's livelock test, fixed next. All four F10 tests
pass: `test_an_errored_target_stays_eligible_for_a_later_hunt`,
`test_searched_and_no_product_targets_stay_excluded`,
`test_an_errored_row_in_a_published_receipt_stays_eligible`,
`test_a_resume_reattempts_the_targets_that_errored`.

**Commit:** `06f72ff`

## AUTO-F4 — quarantine-resume livelock — **CLOSED**

**Confirmed at the base.** Two correct-looking rules that compose into a trap:

* `find_checkpoint` (`scripts/a05_hunt.py:139-172`) resumes the newest checkpoint
  that has **no committed receipt**;
* `settle_receipt` (`:187-218`) files an ungraded receipt in `LAB_HOME/ungraded`
  rather than committing it.

So a checkpoint whose grade fails *deterministically* never acquires the one thing
that would retire it. The sector lane rebuilds the same rows, writes the same
receipt, fails the same grade, requarantines it — every slot, forever, under two
green units. No new sky is searched and nothing alarms.

### BEFORE — the regression test drives the livelock (written first)

```
$ python -m pytest tests/test_a05_hunt_script.py -q --no-header \
      -k ungradeable

        seen = []
        for _ in range(6):  # six slots — a day and a half of the sector lane
            hunt_id, _ckpt = mod.find_checkpoint(3)
            seen.append(hunt_id)
            if hunt_id != stuck:
                break
            # The slot reruns, rebuilds identical rows, and grading fails identically.
            mod.settle_receipt(_receipt(tmp_path, f"{hunt_id}.json"), None)

>       assert seen[-1] != stuck, f"the sector lane never advanced: {seen}"
E       AssertionError: the sector lane never advanced: ['hunt-2026-08-20-s3',
        'hunt-2026-08-20-s3', 'hunt-2026-08-20-s3', 'hunt-2026-08-20-s3',
        'hunt-2026-08-20-s3', 'hunt-2026-08-20-s3']

FAILED test_a_deterministically_ungradeable_checkpoint_stops_being_resumed
```

Six consecutive slots — a day and a half of the sector lane — all resuming the same
dead checkpoint. That is the livelock, literally.

### The fix

`settle_receipt` now tallies each failed grade in
`LAB_HOME/ungraded/<hunt-id>.grade-failures`, and `find_checkpoint` skips a candidate
once the tally reaches `GRADE_RETRY_LIMIT` (**2**), printing why. When every
candidate is receipted *or set aside*, a fresh dated id starts and the lane advances.

Three properties worth naming:

* **Bounded, not zero.** A grade can fail for a reason that clears, and a
  100-minute slice is worth a second attempt.
  `test_a_single_grade_failure_is_still_retried` pins that.
* **The evidence survives.** The checkpoint rows and the quarantined receipt stay on
  disk; only the *resume* stops selecting them. The test asserts the quarantined
  receipt still exists after set-aside.
* **No sky is re-covered.** A set-aside checkpoint keeps its filename, so
  `prior_targets()` still globs it and its `searched` rows stay excluded. Setting
  aside costs the lane the ungradeable *receipt*, not the coverage.

The tally lives at `LAB_HOME/ungraded/<hunt-id>.grade-failures`, beside the receipt
it filed. Deleting it makes the checkpoint resumable again — the manual escape hatch
for a human who has fixed whatever the grade was catching.

### AFTER — the lane advances

```
$ python -m pytest tests/test_a05_hunt_script.py -q --no-header
tests\test_a05_hunt_script.py ................                           [100%]
============================= 16 passed in 0.34s ==============================
```

**Commit:** `b0ecf36`

---

## Re-verification note for the manager — read before re-running

`lab` is installed **editable, pointed at the live clone**
(`C:\Users\beschipp\projects\windowsill-lab\src\lab`). Running `python -m pytest
tests/` from *any* worktree therefore silently pairs that worktree's `tests/` with
the **live clone's** `src/lab`. It is invisible in the output unless a warning
happens to print a source path.

```
$ python -c "import lab; print(lab.__file__)"
lab from: C:\Users\beschipp\projects\windowsill-lab\src\lab\__init__.py

$ PYTHONPATH=src python -c "import lab; print(lab.__file__)"
lab from: C:\Users\beschipp\projects\_workspaces\windowsill-lab-auto\src\lab\__init__.py
```

**PYTHONPATH wins**, so `PYTHONPATH=src python -m pytest tests/` is the honest
invocation from a worktree. This lane changes nothing under `src/lab`, so the
distinction does not move its verdict — but it will move any lane that does, and it
is worth every lane knowing.

(For the record, the worktree and the live clone differ only in `src/lab/a05_sky.py`
and `src/lab/kpz.py` — the live clone carries `bdc36d7 a05: the sky gates` and this
branch is based at `15f0cf6`.)

---

## What this lane did NOT close

Named plainly, because a gate that looks closed and is not is exactly the failure
mode this lane exists to end.

1. **AUTO-F6's root cause.** Two lanes (`campaign.sh` and `a05-hunt-slot.sh`), one
   clone, **no shared git-level lock**. The fix converts a silent lane-halt into a
   loud skipped slot and retries transient contention, but the race is still there. A
   real fix is one `flock` on `$LAB/clone.lock` held across the stage-commit-push
   window in *both* scripts — and `campaign.sh` belongs to another lane of this
   gauntlet (AUTO-F3/F5), so editing it here would collide.
2. **AUTO-F2's stall.** `safe_pull_rebase` here is the strict half of
   `campaign.sh`'s: it does not attempt `resolve_by_regeneration`, so an unresolved
   `pot.json` conflict stalls the sector lane rather than corrupting it. That is the
   right trade — a stall is recoverable, a stranded receipt on a detached HEAD is
   not — but it is a stall. Follow-up: lift `resolve_by_regeneration` into a helper
   both scripts source.
3. **The `flock` line itself is unproven on this box.** Git Bash ships no `flock`;
   the harness shims it so the rest of the script runs. Nothing here tests that two
   concurrent slots actually exclude each other. That needs loam.
4. **Not touched, by constraint:** no systemd unit, timer, or Task Scheduler job was
   started, stopped, modified, or reloaded (Tier C — Ben's click). Unit files were
   read only. `scripts/campaign.sh` and `scripts/nightly.ps1` were read for
   pattern-matching and not edited.

---

## Full suite

```
$ python -m pytest tests/ -q --no-header
=========== 1610 passed, 8 skipped, 1 warning in 692.14s (0:11:32) ============
[exited with code 0]
```

Exit code **0**, **1610 passed / 0 failed**, 8 skipped.

That is the literal command in the return contract, and it is the run that carries
the caveat above: it paired this worktree's `tests/` with the **live clone's**
`src/lab`. This lane changes nothing under `src/lab` (its diff is
`scripts/a05-hunt-slot.sh`, `scripts/a05_hunt.py`, `tests/`, `docs/`), so the verdict
does not move — but the honest invocation from a worktree is
`PYTHONPATH=src python -m pytest tests/`, and that re-run is recorded below.

### Lane tests, pinned to this worktree's `src/lab`

```
$ PYTHONPATH=src python -m pytest tests/test_hunt_slot_gates.py \
      tests/test_hunt_slot_script.py tests/test_a05_hunt_script.py -q --no-header
tests\test_hunt_slot_gates.py .............                              [ 35%]
tests\test_hunt_slot_script.py ........                                  [ 56%]
tests\test_a05_hunt_script.py ................                           [100%]
============================= 37 passed in 44.05s =============================
```

13 gate tests (crash injection), 8 pre-existing slot regressions (previously skipped
on Windows), 16 driver tests. All green.
