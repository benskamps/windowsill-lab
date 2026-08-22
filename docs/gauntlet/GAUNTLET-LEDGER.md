# Gauntlet Execution Ledger — 2026-08-21

**Consumer:** any agent burning down gauntlet findings. Read this, take the next
unclaimed row in its tier, work it, tick it. Re-read before every wave.
**Source:** architectural gauntlet 2026-08-21, 4 read-only audit lanes, repo @ `15f0cf6`.
**Supersedes** the Desktop dossier as the *execution* surface (the dossier stays the
narrative record; this file is the machine-checkable one).

**36 findings — 16 P1, 20 P2.** (35 from the gauntlet; AUTO-F11 found during remediation.) Every row has an ID, a tier, an anchor, and a
**done-when** line. Seven rows are **out-of-repo or repo-wide** and carry no single
`file:line` — they are marked as such rather than given a false anchor. A row is CLOSED only when its done-when
command has been shown FAILING at the pre-fix base and PASSING on the fix branch.

> **Package note:** the dossier says `src/windowsill/`; the real package is **`src/lab/`**.
> All paths below are corrected. Line numbers are anchored at `15f0cf6`.

## Status board

| Metric | Baseline (21:00) | Now |
|---|---|---|
| P1 closed (open PR + fail-before/pass-after shown) | 0 / 15 | **15 / 15 — the gauntlet is closed, and every closure is MERGED.** VET-F1/F2/F3/F4 (#114); AUTO-F1/F2/F3/F4/F6/F10 (#113); DET-1/DET-2 (#115); AUTO-F7 + STR-9-the-new-P1 (#116); STR-1 + AUTO-F5 (#117). +DET-3 (P2), +AUTO-F11 (bonus). Merge train run 2026-08-22 on Ben's nod: #113 → #115 (inside the quiet window before the 09:02 loam slot) → #114 (rebased, conflict resolved keep-both, CI re-fired) → #112 → #116/#117 (wave-2 salvage from the OOM-killed session, re-verified on the ruler post-mortem: lane-4 base 4 behavioral fails + bare-pytest 2 fails → green; hunt-lock base-vs-main 7 behavioral fails / 3 negative-space passes → 10 green). |
| **AUTO-F4 — refuted, then repaired** | — | First closure was **REFUTED**: the set-aside was bypassed by the fresh-id fallback for a **same-day** checkpoint, and the test passed only because its fixture was dated *yesterday*. Repaired at `6ea04ec` (the fresh-id branch now collides with set-aside checkpoints too) and the test is **parametrised over `same-day` / `prior-day`** so it can never go green for that reason again. Re-verified: base fails BOTH parametrisations behaviourally (`the sector lane never advanced: hunt-2026-08-22-s3 x6`), branch passes. **Closed.** |
| Bonus P1 closed (found during remediation, outside the 15) | — | AUTO-F11 (#113) |
| P2 closed | 0 / 20 | 0 / 20 |

## Tier definitions

- **P1** — armed defect: detonates on the pipeline doing its job, or silently
  destroys/loses science. Fix before the next slot where practical.
- **P2** — real defect, latent: needs a second condition (a refactor, a crash, an
  operator mistake) to fire. Continuation pool.

---

## LANE 1 — VETTING SPINE

| ID | Tier | Anchor | Defect | Done-when (machine-checkable) |
|---|---|---|---|---|
| **VET-F1** | P1 | `src/lab/checks.py:184` vs `src/lab/a05.py:112` | Checker vocabulary is 5 verdicts behind the engine (`eclipsing-binary-p2-alias`, `companion-too-large`, `blended-known-planet`, `blend-favours-neighbour`, `ctoi-known`). First honest refutation from the 8/19-20 gates quarantines the whole receipt. | A lockstep test asserts checker vocabulary equals engine vocabulary and FAILS on the pre-fix tree; one receipt fixture per new verdict passes `check_a05` gate 4. `pytest tests/` exits 0. |
| **VET-F2** | P1 | `src/lab/a05_fold.py:382`, `:541` | `combine_p2_folds` sign guard vacuous — producer sorts eclipse A deeper so `depth_difference >= 0` always; `sign_consistent` can never be False on real output. Combining folded-normal abs(noise) biases +0.8 sigma * sqrt(k); ~39 noise sectors cross the 5 sigma refutation bar. Tests pass only on hand-signed fixtures the producer cannot emit (`tests/test_a05_fold.py:383`). | A test driving `combine_p2_folds` from **producer-real** input (through the real fold path, not hand-built diffs) fails pre-fix; the guard records which eclipse was deeper so the sign is meaningful; a pure-noise k=40 combination no longer crosses 5 sigma. |
| **VET-F3** | P1 | `src/lab/a04.py:210` (and `:215`) | Median standard errors use the MEAN formula (`sigma = noise/sqrt(n)`, `:210`), omitting the sqrt(pi/2) median factor. TWO distinct factors, not one: `diff_sigma` (`:211`) is a difference of two medians and is understated **1.772x**; `sec_sigma`/`depth_sigma` (`:215`) is a single median and is understated **1.2533x**. The gate that mints `planet-candidate` is `:247` (the else-branch of `depth_sigma < ODD_EVEN_SIGMA` at `:244`), so a true **~4.0 sigma** dip clears the nominal 5 sigma bar. `a05_fold` already fixed this same math for its own gates; the old formula still mints every candidate first. | SPLIT: (a) a test pins `diff_sigma` against the analytic value and fails pre-fix by 1.772x; (b) a test pins the single-median sigma and fails pre-fix by 1.2533x; (c) the `:247` mint no longer admits the ~4.0 sigma case. Applying 1.772x to BOTH sites would over-correct the depth term. |
| **VET-F4** | P1 | `scripts/a05_hunt.py:264` to `src/lab/a05.py:492` | `run_a05` called without `neighbours` / `sky_catalog`, so `apply_sky_gates` (the 8/20 HATS-16 b fix) never runs in production. Violates shelf-exit contract section 2, "an unrun gate is not a passed gate". | Hunt driver passes both; the receipt carries positive evidence the gate RAN (not merely that it passed); a test asserting a production-shaped hunt invocation reaches `apply_sky_gates` fails pre-fix. |
| VET-F5 | P2 | `src/lab/a05.py:294-415`; `a05_stats.py:106,534,549` | `fap_graded` computed at real cost, compared to nothing; leads mint on SDE>=8 plus vetting alone. `ESCALATION_LADDER` / `saturated` / `next_rung` referenced only by tests. | A lead cannot mint with a failing graded-FAP rung; test fails pre-fix. |
| VET-F6 | P2 | `src/lab/checks.py:2671-2726`, `:3099` | Checker never re-derives observed SDE — replays only null maxima; row sde/period/depth trusted from the receipt in all 14 gates. A mis-carried or tampered sde passes everything. | Spot check re-derives SDE from the cached bytes it already holds and fails a deliberately-tampered fixture. |
| VET-F7 | P2 | `src/lab/checks.py:2803-2815`, `:3020` | Control-ensemble tampering one-sided: gate 2b checks sde>=line implies stage2 but not the promised converse for predeclared members; gate 10 compares uniformity only against control rows carrying fap. Ensemble can be selectively thinned to pass KS. | A selectively-thinned control ensemble fixture fails gate 10 post-fix and passes pre-fix. |
| VET-F8 | P2 | repo-wide | Shelf-exit contract is policy without code: no `first_seen` in src/, `combine_p2_folds` called by nothing outside tests, no promotion/parking code, no 60-day clock. Also unwired: `a05_sky.cluster_detections`, `aggregate_sensitivity`, `survey_trials`, a05_shape v-ness/density gates (only `duration_fraction` is called, `a05.py:346`). | `first_seen` persisted per lead; a promote/park decision function exists and is called on the production path; test covers both branches. |
| VET-F9 | P2 | `src/lab/a05.py:344-372`, `:362` | Opt-in injection-FAP grades masked series against an **unmasked** null — the null contains the host's own transit train. | Injection FAP builds its null from the masked series; test fails pre-fix. |

## LANE 2 — DETERMINISM / SCHEMA

| ID | Tier | Anchor | Defect | Done-when |
|---|---|---|---|---|
| **DET-1** | P1 | `src/lab/publish.py:1577`, `physics_feed.py:428`, `receipt.py:132`, `archive.py:1074`, **51** `write_text`/`write_bytes` call sites in `render.py` (counted, not estimated); `publish.py:1476` | Non-atomic canonical writes; receipt immutability then freezes torn writes forever. The correct tmp+fsync+replace pattern already exists at `scripts/a05_hunt.py:284,318` — for hunt receipts only. | One shared atomic-write helper used by all named writers **and by all 51 render.py call sites** (`grep -c 'write_text\|write_bytes' src/lab/render.py` == the number covered); a test simulating interruption mid-write leaves the old file intact and fails pre-fix. `pytest tests/` exits 0. |
| **DET-2** | P1 | `src/lab/archive.py:495-500` | `pot.json` run order sorts by **mtime PRIMARY**. `git pull` re-stamps mtimes, so win and loam regenerate different ledgers. Structural root of the 7/31 double-conflict, 8/05 stranding, 8/08-11 66h freeze — all the unwedge machinery treats the symptom. | Sort key is (date, turn, content-id) with **no** mtime term; two consecutive regenerations, with mtimes deliberately shuffled between, produce byte-identical `pot.json`. **LANDING is Ben's morning call** — it rewrites the committed feed and may need the timers quiet. |
| DET-3 | P2 | `scripts/a05_hunt.py:310-314` (comments only) | "NEVER sort_keys" enforced only by comments; all sync gates compare parsed objects; no byte-serialization pin. A `sort_keys` refactor ships green and recreates the wedge incidents. | A serialization-pin test fails if `sort_keys` or `indent` drift. **Pins the EXISTING layout — does not change it.** |
| DET-4 | P2 | `src/lab/checks.py:2694` | Receipts editable with no machine detection: no self-hash; `source_report_sha256` points at gitignored files; `_a05_spot` returns None (not fail) without the FITS cache, so only the producing box can physically self-audit. | Receipt carries a self-hash the checker verifies; the missing-cache path returns a distinguishable SKIP, not a silent pass. |
| DET-5 | P2 | `tests/test_schema.py:38-68` | Hand-rolled validator skips minItems / uniqueItems / additionalProperties; committed `pot.json` and `physics-latest.json` are never validated in CI (only synthesized snapshots). Both validate clean today; nothing keeps them so. | CI validates the **committed** feeds against the full schema. |
| DET-6 | P2 | `src/lab/archive.py:312-331`; `reports/.gitignore` | 19 dated report pairs git-tracked in defiance of `reports/.gitignore`, while `archive.py` hard-codes that dated deep-links never resolve. | Either untracked, or the deep-link hard-code removed — decided, not drifted. |
| DET-7 | P2 | `src/lab/determinism.py:82-83` | `GOLDEN_RTOL=0.12`; the golden was blessed on torch 2.6.0 / py3.13 / win while production runs unpinned nightlies (torch 2.10 dev/rocm, py3.14), so every real environment grades inside the 12% band, and `--bless` can re-anchor the rest. | RTOL tightened or the environment pinned so the band is meaningful. |
| DET-8 | P2 | `src/lab/receipt.py:62-65` vs `physics_feed.py:144-148` | Duplicated canonical-digest implementations with no lockstep test; drift silently freezes the physics panel permanently via the carry-stale path (`physics_feed.py:385-398`). | One implementation, or a lockstep test that fails on divergence. |

**Verified clean — DO NOT re-audit:** hunt receipt and pot writes atomic with fsync;
m14 zip sha256 matches and is git-blob pinned; per-target seeds content-derived
(`a05.py:159-181`); control membership pre-data by hash; JSONL checkpoint tolerates
torn tails; both committed feeds validate today.

## LANE 3 — AUTOMATION

| ID | Tier | Anchor | Defect | Done-when |
|---|---|---|---|---|
| **AUTO-F1** | P1 | `scripts/a05-hunt-slot.sh:69`, `:87` | Push gate is a log grep: `rc=$?` is captured and never consulted; success is inferred from the **absence** of a failure string in the last 5 log lines. A crash between receipt-write (`scripts/a05_hunt.py:296`) and grade-print pushes an ungraded receipt and desyncs the pot — red main from the producer's own commit (the realized 8/15 class, claimed closed). | Gate keys on `rc` **and** a POSITIVE grade token, never string-absence. Crash-injection proof in the transcript: simulate the failure, show the gate now refuses. `shellcheck` clean on touched scripts. |
| **AUTO-F2** | P1 | `scripts/a05-hunt-slot.sh:64`, `:106` | `git pull --rebase --autostash` exit unchecked: a conflict leaves the clone detached mid-rebase, the 100-minute hunt runs anyway, the commit lands on detached HEAD, the push silently fails and the receipt is stranded. `campaign.sh:160-188` fixed this exact class; the sibling script regressed it. | Pull rc checked; failure aborts the slot before the hunt starts. Crash-injection proof. `shellcheck` clean. |
| **AUTO-F3** | P1 | `scripts/campaign.sh:287-301`, `:305` | A failed pass still commits `campaign: pass N seed=S`: verify runs only when `lab next` SUCCEEDED, but the failed path still publishes, and `git add -A -- reports/` sweeps partial artifacts. The canonical failure-masquerade. | A failed `lab next` produces NO commit; harness proof in the transcript. |
| **AUTO-F4** | P1 | `scripts/a05_hunt.py:139-172`, `:187-218` | Quarantined-but-completed checkpoint livelock: resume picks the ungraded checkpoint forever, so a deterministic grade failure makes the sector lane rebuild / refail / requarantine under green units indefinitely. No new sky is searched. | Resume cannot select a checkpoint that has already failed grading; a test drives the livelock and fails pre-fix. |
| **AUTO-F5** | P1 | systemd 2h timeout vs `scripts/campaign.sh:281` | SIGKILL between receipt write and staging leaves a dirty pot plus an orphan receipt, producing either the passes-119-124-style 33h stall (dirty-worktree guard) or red main via the directory-globbed hunt block counting the orphan. | The orphan receipt is detected and reconciled (or refused) rather than stalling or reddening; proof by injected orphan. |
| **AUTO-F6** | P1 | `scripts/a05-hunt-slot.sh:103-105` | `git commit ... || exit 0` conflates every commit failure with "nothing to commit". index.lock contention with `campaign.sh` (same clone, same hours) leaves the receipt staged, and the staged-changes guard then refuses all passes. Root cause: two lanes, one clone, no shared git-level lock. | Commit failure is discriminated — nothing-to-commit and real failure take different branches. Crash-injection proof. `shellcheck` clean. |
| **AUTO-F7** | P1 | **OUT-OF-REPO** — fix the GENERATOR at `src/lab/setup.py:274` (`_NIGHTLY_PS1`, template-relative :68-76) / `:436` `nightly_ps1()`; `scripts/campaign.sh:291` is in-repo and correct | Windows and Linux are two different pipelines: nightly.ps1 has no verify re-grade, commits on `lab next` failure, and has no `campaign.published` heartbeat, so a win-side stall is invisible to the watcher. Seed spaces are disjoint and only loam's is ledger-recoverable. | A dry-run harness shows a failed `lab next` produces NO commit on win; the verify re-grade is present; a win-side published heartbeat exists. |
| AUTO-F8 | P2 | **OUT-OF-REPO** — fix the GENERATOR at `src/lab/setup.py:457` `task_xml()` | `InteractiveToken`: logged out means the Windows half silently stops. `StartWhenAvailable` catch-up can fire inside loam's slot hours, while loam's `Persistent=false` drops missed slots — opposite semantics per box. | Token type and catch-up semantics reconciled across boxes, or the divergence documented as intent. **Tier C: touching Task Scheduler is Ben's click.** |
| AUTO-F9 | P2 | `scripts/campaign.sh`; `~/.lab/campaign.iter` | No instance lock: a manual run beside the unit races the iter file and duplicate seeds get committed as independent samples. Ledger recovery scans only the last 4000 commits (~16 months). | An instance lock exists; a second concurrent invocation refuses. |
| **AUTO-F10** | P1 | `scripts/a05_hunt.py:76-82`; `src/lab/a05.py:723-739` | MAST outage rows count as DONE: a full-outage slot "completes" with 200 error rows, and `prior_targets()` then excludes those errored TICs from all future hunts as if they had been searched. Silent permanent coverage loss. | `error:` rows do not count toward done coverage; `prior_targets()` does not exclude transiently-errored TICs; test fails pre-fix. |
| **AUTO-F11** | P1 | `tests/test_hunt_slot_script.py` (skip guard) | **Found 2026-08-21 during remediation, not in the original gauntlet.** All 8 slot-script regression tests `skip` wholesale on Windows for want of `flock` (skip reason: "the slot itself only ever runs on loam"). The reasoning is backwards: the slot RUNS on loam but is EDITED on win, so the box that changes the script never runs its regressions. Same family as the gauntlet's central theme — a gate that cannot fail. | On Windows the file reports 8 passed, not 8 skipped; a no-op `flock` shim stands in where the binary is absent so the rest of the script runs for real. |

## LANE 4 — STRUCTURE / TESTS

| ID | Tier | Anchor | Defect | Done-when |
|---|---|---|---|---|
| **STR-1** | P1 | `scripts/a05_hunt.py:315-325`, `:283-291` | The hunt driver's unlocked read-modify-write of `pot.json` sits **outside** `next_run_lock` and races campaign publish; the receipt write has no ownership or existence check. The 8/15 lead-destruction class, closed only by config convention. | The RMW happens under the same lock as campaign publish; the receipt write refuses to clobber a receipt it does not own; test fails pre-fix. |
| STR-2 | P2 | `src/lab/curriculum.py:217-218` to `cli._hunt_status()` to `publish._hunt_receipt_counters` | Layering inversion: a `row["disposition"]` KeyError on a malformed hunt row kills BOTH the planner and the rotation fallback, so every physics turn collapses to the M01 heartbeat. One malformed exoplanet artifact stalls the physics ladder. | A malformed hunt row cannot take down the physics rotation; test fails pre-fix. |
| STR-3 | P2 | `_checkerboard_masks` in ising / glauber / potts / xy / heisenberg / spin_glass | Lattice kernels copy-pasted 6+ times while OTHER modules import the shared helpers, so a fix in ising reaches wolff and afm automatically and never reaches potts, xy or heisenberg. Wrong-science time bomb. | One implementation, imported by all six; physics regression tests still green. |
| STR-4 | P2 | `src/lab/cli.py:1130`, `:1137` | A new milestone is a ~7-surface shotgun edit, and the RUNNERS-to-cli dispatch is an unpinned string seam (dispatch by recursive `main([subcmd])`), so a typo'd runner ships green, the rotation slot is permanently dead, and it is visible only in task logs. | A test asserts every RUNNERS entry resolves to a real dispatch branch. |
| STR-5 | P2 | `src/lab/render.py:179-180` | The evidence ledger is written by the plotting module: `render.py` (3674 lines) owns git-provenance and receipt writing, and when `json_dump not in html` the **HTML** silently keeps its UNSTAMPED embedded JSON while the committed receipt IS stamped (`:181`, written at `:187`), so the human report and the committed receipt diverge in provenance with no error. The stale side is the human report, not the receipt. | A provenance mismatch raises instead of silently keeping the unstamped copy. |
| STR-6 | P2 | `pyproject.toml` | Deps are floors, not pins (`torch>=2.4`, no lockfile); psutil is deliberately undeclared, giving per-box behavioral drift and no pin to bisect against when the golden reds. | A lockfile or pinned set exists for the golden-grading environment. |
| STR-7 | P2 | `scripts/k03_pilot.py:21`; `scripts/a05-hunt-slot.sh:67` | Three script-invocation conventions, one cwd-fragile: a relative `sys.path.insert` and a relative `PYTHONPATH` inside systemd. | One convention; scripts run correctly from any cwd. |
| STR-8 | P2 | `tests/` | Split-brain tests: gold-standard invariant tests (a05_stats, kuramoto_field, determinism_golden) sit beside smoke-only engine tests (~half of `test_ising` is does-it-run), and ~6 of ~30 cli dispatch branches are route-tested. **Highest-risk untested surface: `src/lab/cli.py:1336-2450`** — the per-milestone dispatch blocks that turn flags into the physical parameters of ~24 scheduled experiments, exercised for untested branches only by the nightly scheduler in production. | The named branches are covered — the specific gap closed, not "more tests". |

---

## Execution order (fix-first)

1. **VET-F1** — the only P1 that detonates on the pipeline working *correctly*.
2. **AUTO-F1** — the other worst candidate, but it needs a crash to fire.
3. **VET-F4** — every future lead is minted without "whose light is this".
4. **VET-F3** — wrong sigma on the candidate-minting rung.
5. **DET-2** — structural root of the feed divergence.

Then the remaining P1s, then the P2 pool in the order listed above.

## Standing constraints

- **NEVER `sort_keys`** in pot or receipt serialization. DET-3 pins the existing layout.
- **Never full-publish from win.**
- Do not re-chase TIC 140940493. TIC 287328866 is **refuted** (EB P/2 alias).
- The "verified clean" list is settled.
- Nothing merges to `main` while the loam campaign and hunt timers are live.

---

## Found during remediation — 2026-08-22 (not in the original gauntlet)

> Two of these (STR-9, STR-10) are defects in the **measuring apparatus**, not the product.
> They are listed as P1 because a burn-down graded by a broken instrument grades nothing.

| ID | Tier | Anchor | Defect | Done-when |
|---|---|---|---|---|
| **STR-9** | **P1** | `pyproject.toml` (no `pythonpath`); no `conftest.py` anywhere | **A bare `pytest` in a git worktree tests the WRONG SOURCE.** The editable install resolves `lab` to the **live clone** (`~/projects/windowsill-lab/src/lab`) regardless of cwd. Verified: bare `import lab` from `_workspaces/windowsill-lab-verify` returns the live clone's path; `PYTHONPATH=src` returns the worktree's. So an agent running bare `pytest` in a worktree reads that worktree's TESTS against the live clone's CODE — a silent false-result generator, and precisely the "passes for the wrong reason" class this burn-down exists to kill. CI is unaffected (`ci.yml` sets `PYTHONPATH=src`). **Every verification in the 2026-08-21 burn-down used `PYTHONPATH=src`, so those results stand.** | A `conftest.py` or a `pythonpath` entry in `pyproject.toml` makes a bare `pytest` resolve `lab` to the tree it is run from; a test asserts `lab.__file__` is under the repo root of the running tree. |
| **STR-10** | **P1** | the test instrument itself (`pytest` invocation convention) | **A truncated pytest run reports success and exits 0.** Observed 2026-08-22 at 99.9% commit charge: pytest OOM'd *inside its own traceback formatter*, aborted partway, printed `520 passed, 1 warning in 368.19s`, and **exited 0** — against a real baseline of `1584 passed / 16 skipped`. Buried above it: `INTERNALERROR> MemoryError`. This is the AUTO-F1 / AUTO-F3 defect class — success inferred from a green exit code that means nothing — occurring **inside the instrument used to measure those findings**. Any suite number taken at face value on a loaded box may be a lie. Secondary: redirecting a buffered pytest to a file loses the whole buffer when the process is OOM-killed, yielding an empty file and no diagnosis. | Suite evidence is only accepted when (a) the output is `grep INTERNALERROR`-clean, (b) the pass count is sane against the ~1584/16 baseline, and (c) the skip count is non-zero — a materially low count with **zero skips** is the truncation signature. Invocations use `python -u -m pytest` so an OOM kill cannot swallow the buffer. A run that cannot meet this is recorded as **NOT OBTAINABLE**, never estimated. |
| DET-9 | P2 | no `.gitattributes`; local `core.autocrlf=true` | Canonical artifacts are written with **platform newline translation** — win emits CRLF, loam emits LF. This only stays out of the repo because `core.autocrlf=true` happens to be set on this box. A differently-configured box commits CRLF and hands the other one a whole-file diff. Same family as DET-2: an artifact that is not a pure function of repo content. | Newlines pinned explicitly at the writer (not left to the platform), or a `.gitattributes` that makes the committed form deterministic. **Note:** pinning rewrites how every artifact serializes — exactly the change class DET-3 exists to stop shipping quietly, so it wants its own deliberate landing. |
| DET-10 | P2 | `archive.write_index()`; `reports/index.html` | A test calls `archive.write_index()` **without patching `REPORTS_DIR`**, so a full-suite run dirties the tracked `reports/index.html` in whatever tree it runs in. Separately, regenerating it now yields **145 runs / 128 passing / 12 nulls** against a committed **146 / 128 / 13** — pre-existing drift between the committed index and the current receipts, present at the base. | The suite cannot write to a tracked path; and the committed index either matches a regeneration or the drift is explained. |

---

## Refutation record — 2026-08-21

This ledger was submitted to an independent fresh-context reviewer that had seen
none of the work behind it, prompted to **refute** rather than confirm, and pointed
at a pristine worktree pinned at `15f0cf6`.

**Verdict: REFUTED.** ~72 anchors checked, **5 wrong**; completeness held (all 35
findings present, no tier drift); **18 of 35 done-when lines** judged not actually
machine-checkable. Every one of the five anchor errors was then re-verified by hand
before being corrected here. Full report:
`~/projects/personal-infra/audit/ledger-refutation-2026-08-21/REFUTATION.md`

### Corrected in this file

| # | Was | Now |
|---|---|---|
| A1 | DET-3 anchored `src/lab/a05_hunt.py:310` | `scripts/a05_hunt.py:310` — the `src/windowsill/`→`src/lab/` sweep **over-applied** and rewrote a `scripts/` path. The package note's own correction introduced the error it was written to prevent. |
| A2 | AUTO-F7 anchored `scripts/nightly.ps1:93` | **OUT-OF-REPO.** No `.ps1` is tracked at `15f0cf6`. The file is *generated* by `lab setup` from `src/lab/setup.py:274`. Fixing the generated file is worse than useless — untracked, unreviewable, overwritten on next setup. |
| A3 | AUTO-F8 anchored `task.xml:38` | **OUT-OF-REPO.** Same: generated from `src/lab/setup.py:457`. |
| A4 | DET-1 said "~15 writers in `render.py`" | **51** call sites — a 3.4x undercount that turned an anchor error into a **scope error**: the row could have been closed with two-thirds of the writers untouched. |
| A5 | STR-5 anchored `render.py:181-182` | `:179-180`, and the mechanism was backwards — the **HTML** keeps the unstamped JSON; the committed receipt is stamped. |
| — | VET-F3 said "~1.77x" and "2.8 sigma at `:244`" | **Two** factors: `diff_sigma` 1.772x (`:211`), single-median 1.2533x (`:215`). The mint is at `:247`, and the real figure is **~4.0 sigma**. This error came from the dossier, not from transcription. |

### Known debt, not silently carried

18 done-when lines still lean on judgment words rather than a command. The highest-cost
ones (DET-1's scope, VET-F3's split, the two out-of-repo rows) are fixed above. The
remainder are mostly P2 rows in the continuation pool; each needs restating as a
**mutation** test so a fail-before can exist at all. Recorded here rather than quietly
left, because a burn-down surface whose done-whens cannot fail is the same defect class
the gauntlet is about.

**What the refutation did NOT find:** no missing findings, no tier drift, no invented
findings, no internal contradiction, and no instance of the ledger asking anyone to
violate the standing `sort_keys` constraint.
