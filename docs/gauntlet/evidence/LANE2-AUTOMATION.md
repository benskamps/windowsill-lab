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
| **AUTO-F4** quarantine-resume livelock | **CLOSED** (refuted once, repaired) | `b0ecf36` + `6ea04ec` | livelock driven over 6 slots, parametrised same-day/prior-day |

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

## AUTO-F4 — quarantine-resume livelock — **CLOSED (repaired after refutation)**

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

**First commit (INCOMPLETE):** `b0ecf36`

### The first fix was REFUTED — and the refutation was right

An independent reviewer broke `b0ecf36` and the manager confirmed it. The set-aside
was applied in the resume loop only; the code then fell through to a fresh id built
from `date.today()`:

```python
hid = f"hunt-{date.today().isoformat()}-s{sector}"
if (hunts_dir / f"{hid}.json").exists():   # COMMITTED receipts only
```

A set-aside checkpoint's receipt lives in `LAB_HOME/ungraded/`, not in
`reports/hunts/`, so that test cannot see it. When the stuck checkpoint carries
**today's** date — which every checkpoint any of today's four slots creates does —
the "fresh" id came back byte-identical to the one just refused, the existing
checkpoint file was handed straight back, and **the livelock survived for the only
case that occurs in production.**

My test went green because its fixture was dated `2026-08-20` — yesterday. That, and
only that, is why it passed. A prior-day checkpoint takes a genuinely different fresh
id; a same-day one does not. The test proved the branch that does not matter.

**Recorded as a lesson, not just a bug:** a fix guarded by one predicate evaluated in
two places will drift, and a fixture whose date is incidental to the author is load-
bearing to the test. Both are now closed by construction — one predicate, and a
parametrised fixture that cannot go green for the wrong reason.

### The repair

`is_retired(hunt_id, hunts_dir)` names the question once — *is this hunt id finished,
by EITHER route?* — and **both** branches of `find_checkpoint` call it: the resume
loop and the fresh-id collision check (including its `-HHMM` and `-HHMMSS`
escalations). The two can no longer disagree.

The regression test is parametrised over `same-day` and `prior-day`, with the fixture
date derived from `date.today()` rather than hardcoded.

### The three-way proof

```
$ PYTHONPATH=src python -m pytest tests/test_a05_hunt_script.py -q --no-header -k ungradeable

# base 15f0cf6 — no set-aside at all
FAILED ...test_a_deterministically_ungradeable_checkpoint_stops_being_resumed[same-day]
FAILED ...test_a_deterministically_ungradeable_checkpoint_stops_being_resumed[prior-day]
====================== 2 failed, 15 deselected in 0.44s =======================

# b0ecf36 — the incomplete fix: prior-day green, same-day still livelocked
FAILED ...test_a_deterministically_ungradeable_checkpoint_stops_being_resumed[same-day]
================= 1 failed, 1 passed, 15 deselected in 0.50s ==================

# repaired
tests	est_a05_hunt_script.py ..                                         [100%]
====================== 2 passed, 15 deselected in 0.19s =======================
```

The captured stdout from the `b0ecf36` run is the clearest statement of the defect —
the lane announcing four times that it is moving on while it does not:

```
grade failure 1/2 for hunt-2026-08-22-s3
grade failure 2/2 for hunt-2026-08-22-s3
setting aside hunt-2026-08-22-s3: failed grading 2 times — the sector lane moves on
grade failure 3/2 for hunt-2026-08-22-s3
setting aside hunt-2026-08-22-s3: failed grading 3 times — the sector lane moves on
...
AssertionError: the sector lane never advanced:
  ['hunt-2026-08-22-s3', 'hunt-2026-08-22-s3', 'hunt-2026-08-22-s3',
   'hunt-2026-08-22-s3', 'hunt-2026-08-22-s3', 'hunt-2026-08-22-s3']
```

`test_a_single_grade_failure_is_still_retried` is unchanged and still green: the
bound is 2, not 0. This was under-correction, and the over-correction fence held.

**Repair commit:** `6ea04ec`

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

### As the return contract asks it

```
$ python -m pytest tests/ -q --no-header
=========== 1610 passed, 8 skipped, 1 warning in 692.14s (0:11:32) ============
[exited with code 0]
```

Exit code **0**, **1610 passed / 0 failed**, 8 skipped.

That run carries the caveat above: it paired this worktree's `tests/` with the
**live clone's** `src/lab`. This lane changes nothing under `src/lab` (its diff is
`scripts/a05-hunt-slot.sh`, `scripts/a05_hunt.py`, `tests/`, `docs/`), so the verdict
does not move — but the honest invocation from a worktree pins the package.

### Pinned to this worktree's `src/lab` — 4 failures, NOT this lane's

```
$ PYTHONPATH=src python -m pytest tests/ -q --no-header
FAILED tests/test_i01_maturity.py::test_progress_callback_failure_cannot_strand_camera_child
FAILED tests/test_i01_maturity.py::test_capture_never_overwrites_or_deletes_racing_output
FAILED tests/test_i01_maturity.py::test_capture_never_overwrites_racing_metadata_and_removes_only_owned_output
FAILED tests/test_i01_maturity.py::test_worker_error_preserves_specific_machine_readable_code
====== 4 failed, 1606 passed, 8 skipped, 1 warning in 1040.59s (0:17:20) ======
```

All four are `test_i01_maturity.py` — the camera experiment. This lane touches no
i01 code, no `src/lab` file, and nothing either imports.

**They are pre-existing, and here is the proof.** The base tree was extracted clean
from git (no working-copy state, none of this lane's commits) and run the same way:

```
$ git archive 15f0cf6 | tar -x -C <tmp>/base-15f0cf6
$ cd <tmp>/base-15f0cf6 && PYTHONPATH=src python -m pytest tests/test_i01_maturity.py -q --no-header
FAILED tests/test_i01_maturity.py::test_progress_callback_failure_cannot_strand_camera_child
FAILED tests/test_i01_maturity.py::test_capture_saves_grayscale_stack_metadata_hash_and_progress
FAILED tests/test_i01_maturity.py::test_capture_never_overwrites_or_deletes_racing_output
FAILED tests/test_i01_maturity.py::test_capture_never_overwrites_racing_metadata_and_removes_only_owned_output
FAILED tests/test_i01_maturity.py::test_worker_error_preserves_specific_machine_readable_code
======================== 5 failed, 25 passed in 3.01s =========================
```

Identical set at the base (plus one more that the loaded full run happened to pass).

**Likely cause: the box, not the code.** The captured stderr is
`OpenBLAS error: Memory allocation still failed after 10 retries, giving up.`, and
the typed failure the test asserts on degrades to a generic one when the camera
worker subprocess dies. At the time of these runs there were **10 orphaned python
workers** (~200 MB each, all started 00:00:07) left behind by a concurrent lane, and
free memory was 8.5 GB of 32 GB. Worth flagging to whoever owns them — they are
slowing and reddening every lane's suite, not just this one. Not killed here: they
are not this lane's processes.

### Lane tests, pinned

```
$ PYTHONPATH=src python -m pytest tests/test_hunt_slot_gates.py       tests/test_hunt_slot_script.py tests/test_a05_hunt_script.py -q --no-header
tests	est_hunt_slot_gates.py .............                              [ 35%]
tests	est_hunt_slot_script.py ........                                  [ 56%]
tests	est_a05_hunt_script.py ................                           [100%]
============================= 37 passed in 44.05s =============================
```

13 gate tests (crash injection), 8 pre-existing slot regressions (previously skipped
on Windows), 16 driver tests. All green.

---

## Reviewer notes folded in (not acted on)

Two live limits the reviewer named. Recorded here rather than fixed, because both are
scope calls rather than defects:

1. **AUTO-F2 has no retry.** Any pull failure costs a whole slot, and the DET lane's
   `pot.json` conflict recurs by construction — so the hunt lane can halt. It halts
   **loudly** (nonzero exit, a named reason in the log) rather than burning 100
   minutes against a detached clone, which is the trade this lane chose on purpose.
   The real close is the shared `resolve_by_regeneration`.
2. **AUTO-F10 has no permanent-error cap.** A TIC that is genuinely dead — as opposed
   to behind a transient outage — is now retried on every future hunt, forever.
   Bounded eligibility (an attempt counter per TIC, the way `GRADE_RETRY_LIMIT`
   bounds grades) is the follow-up. The current behaviour errs toward re-attempting,
   which is the safe direction for coverage and the wasteful one for budget.

---

# AUTO-F3 — campaign.sh failure-masquerade — **CLOSED**

Second assignment, same branch. `scripts/campaign.sh:287-301` and `:305`.

**Confirmed at the base, and worse than the dossier stated.** The dossier named three
faults; the harness found a fourth.

```bash
publishable=1
if ! "$PY" -m lab.cli next --seed "$seed" --device "$DEVICE" >> "$LOG" 2>&1; then
  log "campaign: pass $iter — experiment failed; refreshing existing feed only"
  "$PY" -m lab.cli publish >> "$LOG" 2>&1 \
    || log "campaign: pass $iter — feed refresh also failed"
elif ! "$PY" -m lab.cli verify >> "$LOG" 2>&1; then
```

A failed `lab next` leaves `publishable=1` and falls through to the staging block.

1. **It commits under a success's message.** `campaign: pass N <date> seed=S`.
2. **`verify` never runs on it** — the re-grade is on the `elif`, i.e. the SUCCEEDED
   path only. Nothing re-checks what ships.
3. **`git add -A -- reports/` sweeps the torn artifacts.** A real `lab next` does not
   fail atomically; it fails part way through with output already on disk.
4. **NOT in the dossier:** the commit is *pushed*, and `campaign.published` — the
   heartbeat `groundskeeper/checks/freshness.py` reads — **is touched**. The estate
   watcher therefore scores a failing lane as healthy. That heartbeat was added
   precisely because everything else moves on a refused pass; a failed pass reaching
   it defeats its whole purpose.

And because the pass counter is *recovered by reading these subjects back out of the
ledger*, the masquerade corrupts the ledger, not only the feed.

### The harness

`tests/test_campaign_pass_gate.py` drives the **loop** (`LAB_CAMPAIGN_MAX_ITERS=1`,
which exits before any sleep), not library mode — the masquerade lives in the loop
body, not in a function. `tests/test_campaign_conflict.py`'s stub-package approach is
reused: a throwaway origin + clone, a stub `lab.cli` on `PYTHONPATH` whose `next`,
`publish` and `verify` return codes are env knobs. Its `next` failure writes a torn
receipt and a scratch file *before* returning nonzero, because that is what the real
one does. **No real remote, no real `lab`, no systemd unit.**

### BEFORE — the gate passes wrongly

```
$ PYTHONPATH=src python -m pytest tests/test_campaign_pass_gate.py -q --no-header

>       assert campaign.commit_count() == before, (
E       AssertionError: a failed pass committed: 'campaign: pass 1 2026-08-22 seed=1001'
E       assert 2 == 1

E       AssertionError: assert 'reports/receipts/run-partial.json' not in
      {'physics-latest.json', 'pot.json', 'reports/receipts/.keep',
       'reports/receipts/run-partial.json', 'reports/scratch-from-the-failed-run.txt'}

>       assert not campaign.heartbeat()
E       assert not True

FAILED test_a_failed_experiment_produces_no_commit
FAILED test_a_failed_experiment_never_writes_a_success_shaped_message
FAILED test_a_failed_experiment_does_not_sweep_its_partial_artifacts
FAILED test_a_failed_experiment_does_not_touch_the_published_heartbeat
======================== 4 failed, 3 passed in 11.12s =========================
```

`'campaign: pass 1 2026-08-22 seed=1001'` is the whole finding in one string: that is
a *failed* pass, and nothing about the subject says so.

Committed failing at `0893ea2` before the fix landed.

### The fix

`withhold_pass()` is now the **single** way a pass declines to publish, and both
branches call it. Two inlined copies is precisely how the branches drifted apart — a
failed `verify` restored and withheld, a failed `lab next` did neither — so the repo
ends with one convention rather than two.

It restores the campaign-owned **tracked** paths (or the dirty-worktree guard refuses
every later pass) *and* `git clean -qfd -- reports/` clears **untracked** wreckage,
so the next pass's own `git add -A` cannot sweep what this one left behind.
`git checkout` alone would not have done that.

The "refresh the existing feed on the way past" publish is **removed**: its output was
restored by the very same pass, and the next successful pass rebuilds the feed from
the committed receipts anyway. Keeping it would have been work whose only effect was
to make a failure look like a pass.

### AFTER — the gate refuses

```
$ PYTHONPATH=src python -m pytest tests/test_campaign_pass_gate.py \
      tests/test_campaign_conflict.py tests/test_campaign_maturity.py -q --no-header
tests\test_campaign_pass_gate.py .......                                 [ 23%]
tests\test_campaign_conflict.py ......                                   [ 43%]
tests\test_campaign_maturity.py .................                        [100%]
============================= 30 passed in 18.65s =============================
```

Three of the seven pass at the base **by design** — they fence the over-correction
side: `test_a_successful_pass_still_commits_and_publishes` (a good pass still commits,
pushes and beats the heartbeat) and `test_a_failed_verify_still_withholds_the_commit`
(pre-existing behaviour undisturbed).

**Two static pins in `tests/test_campaign_maturity.py` were updated, not deleted.**
`test_campaign_withheld_pass_restores_owned_paths_for_the_next_pass` pinned the
restore's *position inside the loop body*, which the helper extraction moved; it now
asserts both branches reach `withhold_pass` before staging and that the restore has
exactly one home. A new pin,
`test_campaign_experiment_failure_never_reaches_the_publishing_path`, asserts
`"refreshing existing feed only"` is gone, so the masquerade cannot return by edit.
Both fail at `15f0cf6` and pass on the branch:

```
$ git checkout 15f0cf6 -- scripts/campaign.sh && PYTHONPATH=src python -m pytest \
      tests/test_campaign_maturity.py -q --no-header \
      -k "withheld_pass_restores or never_reaches_the_publishing"
FAILED tests/test_campaign_maturity.py::test_campaign_withheld_pass_restores_owned_paths_for_the_next_pass
FAILED tests/test_campaign_maturity.py::test_campaign_experiment_failure_never_reaches_the_publishing_path
====================== 2 failed, 15 deselected in 0.23s =======================
```

### shellcheck

`campaign.sh` was **not** clean at the base — two findings, both pre-existing:

```
$ git show 15f0cf6:scripts/campaign.sh | shellcheck -f gcc -s bash -
-:262:27: note: Command appears to be unreachable ... [SC2317]
-:325:9: warning: a appears unused ... [SC2034]
rc=1
```

Both are closed here (`for _ in 1 2 3 4` for the unused retry counter; a targeted,
commented `disable=SC2317` on the documented library-mode seam), so campaign.sh now
matches its sibling:

```
$ tr -d '\r' < scripts/campaign.sh > /tmp/camp.sh && shellcheck -f gcc -s bash /tmp/camp.sh
shellcheck rc=0
```

### Not closed by AUTO-F3

`git add -A -- reports/` still stages indiscriminately on the SUCCESS path. It is
safe there only because a successful `lab next` is assumed to leave no torn output —
an assumption nothing enforces. Narrowing it to the paths the run declares it wrote
is the real close, and it needs a producer-side change (`lab next` printing its
artifact list, the way `a05_hunt.py` prints `receipt -> PATH` for the slot). Out of
scope here; worth a finding of its own.

**Commit:** `32b2185` · **failing harness:** `0893ea2`
