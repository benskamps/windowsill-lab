# Decision: portfolio rotation — retire the M01-every-pass fallback

**Status:** decided 2026-08-01, shipped in the `portfolio/scheduler-rotation` PR.
**Raised by:** Ben's 2026-08-01 directive ("why are we still reporting m01 and
running m01 every day? … 4 runs per device per day across the portfolio").
**Readers:** whoever arms the schedules (the checklist at the bottom), and any
future session touching `lab next`, `curriculum.ROTATION`, or the cadence
templates. Companion decision: `2026-06-26-heartbeat-vs-lab-next.md` (still the
record of why the frontier comes first).

## The finding — why every pass ran M01 (verified against the code)

Not a bug, and not a rotation that failed to rotate — **there was no rotation.**
`lab next` picks the single OPEN milestone (`publish.parse_milestones` promotes
the first `[ ]` pending line when nothing is `[>]`). Today that is **M18**,
which has no runner (`curriculum.RUNNERS` stops at M17/C01/A01/I01), so the
scheduler took its designed fallback: the M01 heartbeat — forever, because the
pointer is structurally stuck. Review `[?]` milestones aren't pending, every
runnable milestone is terminal (`[x]`/`[~]`/`[?]`), and every other `[ ]`
pending (C02–C04, A02–A04, I02–I03, B01–B02) has no runner and sits after M18
anyway. The 2026-06-26 decision even predicted the state ("`lab next` would run
the heartbeat until M12's code lands"); it never contemplated rotating over
already-verified runnable milestones. Receipts: campaign passes 42–48
(afc807e…8bdcc1e) each rewrote the same day's `run-…-m01.json`; 37 of 61
committed receipts are m01.

So this is a **new decision**, not a bug fix: when the frontier has no engine,
re-measure the whole runnable portfolio instead of re-measuring M01.

## The decision

Selection precedence in `lab next` (each branch prints a one-line reason,
dry-run included):

1. **Frontier first** — the open milestone, when it has a runner and passes its
   hardware gate. Unchanged from 2026-06-26: an M18 runner landing, or a hand-
   placed `[>]`, immediately reclaims the bench.
2. **Portfolio rotation** — otherwise, advance the curated committed
   `curriculum.ROTATION` past the receipts-ledger pointer, skipping ineligible
   slots with a disclosed one-line reason (a log line — never a receipt, never
   a report, never a science row).
3. **M01 heartbeat** — only when the rotation yields nothing (fail closed,
   named reason).

M01 stays in the rotation as **one slot**: the calibration pulse, demoted from
daily headline.

### Curated membership — a cost decision, not just a capability one

`ROTATION` is an explicit list, not blanket `RUNNERS`. Excluded at birth:

- **M12** — the full parallel-tempering run is the PT2H-class config (exceeds
  the Windows task `ExecutionTimeLimit`); the `--quick` variant ships a `[~]`
  null every pass. The three committed M12 receipts are all quick-run nulls
  (`wall_seconds` 7.8 / 6.9 / 229.2 — the last a Loam GPU quick run). Either
  membership choice is receipt spam.
- **M16** — same wall-clock class (3D spin-glass aging; its one committed
  receipt is a 0.7 s null probe).

Known cost accepted: **A01** hits the MAST network every rotation visit (600 s
deadline). A flaky pass exits nonzero and campaign.sh logs "experiment failed"
honestly. Acceptable; it will happen.

Membership changes are one-line PRs against `curriculum.ROTATION`.

### Hardware gates — skips are disclosed absences, not failure runs

`curriculum.HARDWARE_GATES` maps milestone → a deterministic, configuration-only
check (no device probing). Today's only entry: **I01** is eligible exactly when
`WINDOWSILL_I01_FRAMES` names an existing dark-frame stack; otherwise the
scheduler skips it with a named reason — one log line per pass, no receipt, no
public row. (Neither box currently has a webcam.)

**`LAB_I01_CAMERA` deliberately does NOT satisfy the gate** (review finding,
2026-08-01): the scheduler dispatches a bare `lab i01` with no capture flags,
and `run_i01` never reads `LAB_I01_CAMERA` — so a camera-only config would
fail `no_real_frames` rc 3 every pass with **no receipt**, freezing the
pointer and re-picking I01 forever (a rotation livelock). The gate names that
mismatch (`no-frames:` reason) instead of passing. Live capture stays an
attended `lab i01 --camera N`; if scheduled capture is ever wanted, the
dispatch itself must learn to pass capture flags first — re-widen the gate
only in the same PR.

Separately, `lab i01` invoked bare now **fails fast**: a run that measured
nothing (`no_real_frames`, capture errors — `analysis is None`) prints its
named error and exits **3** without rendering, publishing, or writing a
receipt. The old behavior laundered the absence into a completed run (rc 0 + a
published null science row). A **measured** null (real frames analyzed,
calibration failed) still publishes — that is data, not absence. The committed
2026-07-14 I01 null receipt predates this gate and stays: honest archive.
Out-of-repo callers that assumed `lab i01` rc 0: the change is named and
intended.

### The pointer — a committed ledger fact, not box-local state

The rotation pointer is derived from the receipts ledger both boxes already
commit and pull-rebase before every pass: **the milestone of the receipt with
the maximum `generated_at`** across `reports/receipts/` (unreadable/unstamped
receipts degrade to their filename date — the `run_cadence` discipline; ties
break by milestone id). No receipts → the rotation starts at its first slot.
A newest receipt from OUTSIDE the rotation (a manual `lab m12`, or the last
frontier run right after its milestone verifies) also restarts the walk at
slot 0 — bounded (one reset per such receipt, then normal advance) and named
in the printed reason (review amendment, 2026-08-01).

**Duplicate-pick window (do NOT "fix" this into a lock file):** if schedules
are mis-armed or a slept box fires catch-up runs, both boxes can read the same
pointer and run the same milestone. Bounded outcome: one redundant independent
sample, the same `(date, slug)` receipt, resolved by the existing
rebase-and-retry push loops. Disclosed in pass logs; it self-heals on the next
pass. The alternative (clock-derived slot) needs zero coordination but marches
on while a box is down, skipping milestones — the ledger pointer instead
degrades to "resume from whatever actually last ran", which is the behavior we
want.

## Cadence — 4 passes/device/day, interleaved

| Box | Mechanism | Local slots |
|-----|-----------|-------------|
| Win | Task Scheduler, four explicit daily `CalendarTrigger`s (`lab setup` template) | 00/06/12/18 |
| Loam | `campaign.sh` + `windowsill-campaign.service` (`LAB_CAMPAIGN_HOURS="3 9 15 21"`, `INTERVAL=21600` fallback) | 03/09/15/21 |

8 interleaved portfolio turns/day. `campaign.sh` now sleeps to the **next
listed local hour boundary** (`next_wake_seconds`, recomputed from the wall
clock each pass — drift-free, DST-proof) instead of accumulating
`sleep INTERVAL` drift. `ExecutionTimeLimit PT2H` < 6 h spacing, so Windows
passes never overlap; `MultipleInstancesPolicy IgnoreNew` backs that up.

**Windows seed semantics changed:** `yyyyMMdd` → `yyyyMMddHH`, so the four
daily passes are independent samples. This retires the documented "a same-day
rerun repeats deterministically" property (a retry within the same **hour**
still repeats; a `StartWhenAvailable` catch-up run lands in its own hour → its
own sample). The determinism gate (`lab verify --rerun-smoke`) is unaffected —
it pins its own seed.

Expected commit volume: every pass that changes anything commits (~8.6k-line
`latest.html` churn per pass today) → ≈8 report-churn commits/day on main.
Accepted per the existing campaign precedent; if repo growth bites, the fix is
trimming `latest.html` churn — separate, named work, not a reason to skip
cadence.

## Arming checklist (Ben's clicks — this PR registers/enables NOTHING)

Windows box:
1. Merge, then on main: `git pull`.
2. Re-run `lab setup` (regenerates `scripts/nightly.ps1` + task XML and
   re-registers the `windowsill-lab` task with the four triggers — the
   installed copies are gitignored and do not update on merge).
3. Watch one slot first: `python -m lab.cli next --dry-run` should print the
   rotation pick and any skip lines.

Loam:
1. On main: `git pull`.
2. `cp scripts/windowsill-campaign.service ~/.config/systemd/user/` then
   `systemctl --user daemon-reload && systemctl --user restart
   windowsill-campaign.service` (the running unit keeps the old 14400 interval
   until restarted).
3. Confirm the log line `campaign: START interval=21600s hours='3 9 15 21' …`
   and that the first sleep targets the next 03/09/15/21 boundary.

Until both are armed, Loam keeps its old 4 h cadence and the public rail keeps
its M01 wall (the display collapse is the lane-B change plus a mirror
propagation).
