# LANE 5 — hunt lock & orphan reconciliation (STR-1, AUTO-F5)

**Branch:** `gauntlet/hunt-lock`
**Base: `94c3ffa`** — NOT the original dossier commit `15f0cf6`.

Why: both findings live in `scripts/a05_hunt.py` and the hunt/campaign shell
lanes, which PR #113 (`gauntlet/automation-gates`) rewrote substantially. Basing
at `15f0cf6` would produce an unmergeable conflict, and — more to the point — it
would prove the wrong thing: the question is whether these defects survive on the
code that is actually going to main, not on the code the dossier was written
against. Every FAIL-BEFORE below was captured with the FINAL test file, at
`94c3ffa`, by stashing only `src/` and `scripts/` (the tests are untracked at
that point, so the base source runs against the shipped tests).

Run command, everywhere in this file:

```
PYTHONPATH=src python -m pytest tests/test_hunt_pot_lock.py -p no:randomly -q
```

`PYTHONPATH=src` is not cosmetic — a bare `pytest` in a worktree resolves `lab`
to the live clone (STR-9), so it would test a different source tree entirely.

---

## STR-1 (P1) — CLOSED

Two defects in the same few lines at the end of `main()`.

### 1. The read-modify-write of `pot.json` held no lock

The write is atomic (tmp + fsync + replace) and is on the dossier's
verified-clean list; it is untouched. The defect is the **read-modify-write**
around it. `pot.json` has a second writer: the campaign lane publishes through
`lab next`, which holds `next_run_lock` (`src/lab/cli.py:107`, taken at
`cli.py:2456`) for its whole turn. The hunt driver held nothing. Interleave
them — hunt reads pot, campaign publishes a pass, hunt writes back the copy it
read — and the campaign pass is gone with nothing dirty, nothing red and nothing
to alarm on. The only thing keeping that off production was that the two lanes
are *scheduled* in different hours.

### 2. The receipt write had no ownership or existence check

`receipt_path = hunts_dir / f"{hunt_id}.json"` was opened and written
unconditionally — the last unguarded step in a pipeline that guards everything
else. A receipt already at that path was written by somebody else. On 2026-08-15
that somebody was win: loam's bare survey slot defaulted into sector 2 and
overwrote win's committed s2 receipt, taking a lead-awaiting-human-review row
with it. `find_checkpoint` avoids colliding ids at the *start* of a run; two
things walk past it — `--hunt-id`, and the 100 minutes in between, during which
the other box can commit a receipt for the id we picked.

### FAIL-BEFORE at `94c3ffa` (verbatim)

```
collected 3 items

tests\test_hunt_pot_lock.py F.F                                          [100%]

E       AssertionError: the hunt's read-modify-write ran unlocked and clobbered a campaign publish that had already committed (campaign.wrote=True)
E       assert 'pass-1' == 'pass-2'

E       AssertionError: the hunt overwrote a receipt written by another producer - the 2026-08-15 lead-destruction incident, byte for byte
E       assert {'counts': {'..., 'schema': 1} == {'experiment'...'287328866'}]}
E         Omitting 2 identical items, use -vv to show
E         Left contains 1 more item:
E         {'counts': {'above_threshold': 0,
E                     'attempted': 3,
E                     'leads_awaiting_human_review': 0,
E                     'searched': 3,...
---------------------------- Captured stdout call -----------------------------
receipt -> ...\reports\hunts\hunt-2026-08-22-s2.json
searched 3/3, stage2 1, above threshold 0, leads 0
check_a05: True - stub
pot hunt block refreshed -> ...\pot.json
=========================== short test summary info ===========================
FAILED tests/test_hunt_pot_lock.py::test_a_campaign_publish_is_not_lost_under_the_hunts_pot_refresh
FAILED tests/test_hunt_pot_lock.py::test_the_receipt_write_refuses_to_clobber_a_receipt_it_does_not_own
========================= 2 failed, 1 passed in 0.56s =========================
```

**FAIL-BEFORE KIND: behavioural, both.** Neither test calls a symbol that does
not exist at the base. Both drive the shipped `main()` end to end
(`find_checkpoint` → `run_a05` → `to_report` → `check_a05` → `settle_receipt` →
the pot refresh) with only the search and the grade stubbed, and both fail
because the base does the wrong *thing*: it destroys a write that had already
landed, and it destroys a receipt it did not write. The one test that passes at
the base (`..._when_nothing_is_contending`) is deliberate — it is the happy-path
guard the lock must not break, not a proof of anything.

The concurrent writer in the lost-update test is a **real separate process**
(`CAMPAIGN_PUBLISH`, run via `subprocess`), not a same-process stand-in, because
after the fix a same-process stand-in would *re-enter* the lock rather than
contend for it and the test would prove nothing.

### The fix

`src/lab/cli.py`
* `next_run_lock(path=None, wait_seconds=0.0)` — `wait_seconds` polls a busy
  lock instead of giving up on the first look. **Default 0, so `lab next` keeps
  its behaviour exactly**: a scheduled turn that finds the box busy still skips
  its slot rather than queueing behind one. Only a caller that is *finishing*
  work passes a budget.
* `_held_by_this_process_tree()` + `NEXT_LOCK_ENV` — re-entrancy across a process
  tree. This is load-bearing, not a nicety: `lab next` takes the lock and then
  dispatches `lab hunt`, which runs `scripts/a05_hunt.py` in a **subprocess**
  (`cli.py`, `cmd == "hunt"`). Locking the pot refresh without this would make
  the campaign lane block on *itself* for the whole wait budget and then withhold
  a graded receipt — a deadlock introduced by the fix for a race. The environment
  variable is the ancestry channel; the lock *file* is the proof (both must
  agree, and the named pid must still be a live python), so a leaked variable
  from a dead turn falls through to real acquisition.

`scripts/a05_hunt.py`
* The pot RMW now runs inside `next_run_lock(wait_seconds=POT_LOCK_WAIT_SECONDS)`
  — the **same** lock, not a second scheme. Two locking schemes over one file is
  the same bug wearing a hat.
* On `LockBusy` after the budget: the receipt is **withheld**, not published.
  Publishing a receipt without its refreshed aggregate is the 2026-08-15 red-main
  class, so both are withheld together. It is filed with the logs and `main()`
  returns 1, which is `a05-hunt-slot.sh`'s first proof and stops it staging
  anything.
* That withholding is **not tallied** as a grade failure (`settle_receipt(...,
  tally=False)`). Nothing is wrong with the slice — someone else was holding the
  lock — and counting it toward `GRADE_RETRY_LIMIT` would retire a healthy
  checkpoint over someone else's scheduling. Untallied, the lane self-heals: the
  next slot resumes the same checkpoint, rebuilds these rows off disk without
  re-searching a single star, and publishes then.
* `unowned_receipt_path()` — refuses to open a path that already holds a receipt
  this run did not write, and files beside it under a stamped id (the same
  collision-avoidance shape `find_checkpoint` already uses, and the same #79
  turn-stamp lesson). **Refusing is not discarding**: the slice really was
  searched and really did grade, so its work is preserved next to the incumbent
  rather than thrown away.

`POT_LOCK_WAIT_SECONDS` defaults to 300s (`LAB_HUNT_POT_LOCK_WAIT` overrides).
Sized against the two clocks it sits between: a campaign turn holds the lock for
minutes, and `windowsill-hunt.service`'s `TimeoutStartSec=2h` still has to cover
a 100-minute slice plus this wait.

### PASS-AFTER (verbatim)

```
collected 5 items

tests\test_hunt_pot_lock.py .....                                        [100%]

============================== 5 passed in 2.62s ==============================
```

Two of the five are guards on the fix itself, not closures:
`..._re_enters_instead_of_deadlocking` pins the deadlock described above (and
that an unrelated process is still refused, and that a re-entering child does not
release a lock it never took), and `..._gives_up_and_raises_rather_than_hanging`
pins that the wait is a budget rather than a hang.

**Commit:** see `fix(str-1)` below.

---

## AUTO-F5 (P1) — CLOSED (still open at the base; `276c7b6` does not cover it)

### Is it already fixed?

**No.** The brief asked this first, so it is answered with file:line rather than
opinion.

`276c7b6` ("quarantine the receipt when staging itself fails") adds
`quarantine_receipt` to the `git add` failure branch —
`scripts/a05-hunt-slot.sh:173-181` on the base. That is a branch the shell
**executes**: `git add` returns non-zero, the `if` is taken, the function runs.

AUTO-F5 is process death. `scripts/windowsill-hunt.service:7` sets
`TimeoutStartSec=2h`; when it expires systemd kills the unit's whole cgroup, and
no exit path runs at all. Proof that nothing catches it:

```
$ grep -n "trap" scripts/a05-hunt-slot.sh
(none)
$ grep -n "trap" scripts/campaign.sh
209:trap 'log "campaign: signal - stopping after pass $iter"; exit 0' INT TERM
$ grep -n "ls-files|untracked|orphan" scripts/a05-hunt-slot.sh
172:# (TIC 287328866) pushed its receipt and left its dossier sitting untracked.   <- a comment
```

The sibling script has the trap; this one never grew one — and a trap would not
cover SIGKILL regardless. Nothing anywhere in the slot looks for debris at
start. **AUTO-F5 was open at `94c3ffa`.**

### The two shapes of debris

* **An untracked receipt in `reports/hunts/`.** The pot aggregator globs that
  DIRECTORY (`src/lab/publish.py`, `hunt_block`) while CI recomputes
  `pot == hunt_block()` from the COMMITTED set. The next successful publish
  therefore ships a pot counting a receipt CI cannot see, and main goes red in
  that run's own commit — the 2026-08-15 class by a different road.
* **A `pot.json` refreshed but never committed.** `scripts/campaign.sh:281`
  refuses a pass against pre-existing tracked worktree changes, so every later
  campaign pass is declined: passes 119-124, ~33h, under two green units.

The tests inject that aftermath, which is the only thing there is to reproduce —
the kill leaves no code running to observe. What is under test is the one thing
still fixable: whether the NEXT run notices.

### FAIL-BEFORE at `94c3ffa` (verbatim)

```
PYTHONPATH=src python -m pytest tests/test_hunt_slot_orphan.py -p no:randomly -q

E       AssertionError: a receipt the pot aggregator globs is not in the committed set - the next publish ships a pot CI cannot reproduce
E       assert {'hunt-2026-0...8-22-s3.json'} == {'hunt-2026-08-22-s3.json'}
E         Extra items in the left set:
E         'hunt-2026-08-21-s3.json'

E       AssertionError: set()
E       assert 'hunt-2026-08-21-s3-tic999.html' in set()

E       AssertionError: pot.json is still dirty after a slot that refused to run - campaign.sh declines every pass behind it (the 33h stall)
E       assert False
E        +  where False = is_clean()

=========================== short test summary info ===========================
FAILED tests/test_hunt_slot_orphan.py::test_an_orphan_receipt_from_a_killed_run_is_not_left_to_redden_main
FAILED tests/test_hunt_slot_orphan.py::test_a_killed_runs_dossier_travels_into_quarantine_with_its_receipt
FAILED tests/test_hunt_slot_orphan.py::test_the_dirty_pot_a_killed_run_left_stops_stalling_the_campaign_lane
========================= 3 failed, 2 passed in 7.53s =========================
```

**FAIL-BEFORE KIND: behavioural.** No new symbol is called; the tests drive the
shipped `scripts/a05-hunt-slot.sh` through the existing `slot_harness` rig, and
it fails because it leaves the orphan on disk, leaves its dossier, and leaves the
pot dirty. The two that pass at the base are the restraint guards described
below.

### The fix

`reconcile_dead_run()` in `scripts/a05-hunt-slot.sh`, called **before**
`safe_pull_rebase`. Any `reports/hunts/*.json` that `git ls-files` does not know
is debris from a process that never lived to stage it: it is filed into
`$LAB/ungraded/` with its dossier, on the same rule as every other refusal.

Three deliberate constraints, each with a test:

1. **Before the pull, not after.** The pull is one of the things that can fail,
   and the fix for a stalled lane must not be gated on the step that just
   failed. `..._stops_stalling_the_campaign_lane` breaks the remote so the slot
   refuses to hunt, and still requires a clean worktree afterwards.
2. **`pot.json` is reverted only when an orphan receipt is ALSO present.**
   `campaign.sh` writes `pot.json` too, in this clone, with no git-level lock
   between the lanes (LANE2-AUTOMATION.md). A dirty pot alone is as likely to be
   a campaign pass mid-flight, and reverting it would be this lane destroying the
   other lane's work — the exact class STR-1 is about. A dirty pot *plus* an
   untracked hunt receipt is unambiguous.
   `..._a_dirty_pot_with_no_orphan_receipt_is_left_alone` pins the restraint.
3. **The index is never touched.** A `git reset` here, even path-restricted,
   could break a `campaign.sh` pass caught between its `git add` and its
   `git commit`. The staged-at-death case stays with LANE 2, where the shared
   lock belongs — see "not closed here" below.

Safe against the other lane by construction: `campaign.sh` never writes
`reports/hunts/`, and the `flock` at the top of the slot means no second hunt on
this box.

### PASS-AFTER (verbatim)

```
collected 5 items

tests\test_hunt_slot_orphan.py .....                                     [100%]

============================== 5 passed in 6.37s ==============================
```

Neighbouring suites, unchanged by the edit:

```
PYTHONPATH=src python -m pytest tests/test_hunt_slot_script.py tests/test_hunt_slot_gates.py \
    tests/test_hunt_block.py tests/test_campaign_conflict.py tests/test_campaign_pass_gate.py -p no:randomly -q
============================= 65 passed in 48.91s =============================
```

### Not closed here, named

A run killed between `git add` and `git commit` leaves the index staged, which
campaign.sh also refuses. Reconciling that means resetting an index the other
lane may be using in the same instant — the real root cause is still "two lanes,
one clone, no shared lock", already recorded as open in LANE2-AUTOMATION.md. It
is not papered over here.

No systemd unit, timer, or Task Scheduler entry was modified. The unit file was
read only.

**Commit:** the `fix(auto-f5)` commit on this branch.
