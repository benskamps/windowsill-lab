# Lane 4 — win/loam symmetry

Branch `gauntlet/win-loam-symmetry`, based at `15f0cf6`.
Findings: **AUTO-F7** (P1) and **STR-9** (P1). Both CLOSED.

Environment note for anyone re-running this: there is no `.venv` in the
worktrees and no `pytest` on PATH — the bare invocation form on this box is
`python -m pytest`. Every command below is verbatim and rerunnable.

---

## AUTO-F7 — win and loam were two different pipelines — **CLOSED** (`a0696c3`)

### What was actually wrong

The dossier anchors this at `scripts/nightly.ps1:93`. That file is **generated
and gitignored** (`.gitignore:14`), produced by `lab setup` from a template in
tracked source. Editing it would produce an untracked change no PR can carry and
that the next `lab setup` silently overwrites. **The fix is in the generator**:
`src/lab/setup.py` — the `_NIGHTLY_PS1` template rendered by `nightly_ps1()`.

Three defects, each present in win and absent in loam's `scripts/campaign.sh`:

| # | win (before) | loam (`campaign.sh`) |
|---|---|---|
| 1 | no `lab verify` re-grade at all | `:291` — verify fails, publish withheld |
| 2 | `lab next` fails, `lab publish` runs, then **commit + push + exit 0** | `:283-301` — a guarded, logged pass |
| 3 | no published heartbeat | `:330` — `campaign.published`, touched ONLY on a real push |

Defect 3 is not theoretical. Loam ran ~26h with no publish, both units green,
exit 0, and it was caught *only* because `campaign.published` went stale.
Everything else either script writes (the log, the counter, `pot.json` under the
mirror bot) moves on a REFUSED or FAILED run too, so an mtime watcher reading
any of them scores a halted lane as healthy. Consumer of the loam row:
`personal-infra/groundskeeper/checks/freshness.py:74`.

### The harness

`tests/test_nightly_drive.py` — it **executes** the generated PowerShell (pwsh
7.6.5) against a throwaway `origin.git` + clone, with a stubbed `lab` package on
`PYTHONPATH` whose exit codes the test controls and which dirties all three
nightly-owned paths *before* exiting (so a missing commit can never be explained
away as "nothing changed"). It then reads the git ledger and the heartbeat.

This is deliberate: unit-testing the generated string is necessary but **not
sufficient** — loam's own first cut of a comparable fix passed its string
assertions and failed its dry run. `LAB_STATE_DIR` and `LAB_NIGHTLY_LOG` point
the run at throwaway directories. **Task Scheduler is never touched** — the
scheduler's only job is to invoke this script, and the script is what is tested.

### FAIL-BEFORE — verbatim, at `15f0cf6`

```
$ git stash push -- src/lab/setup.py tests/test_setup.py     # revert the generator
$ python -m pytest tests/test_nightly_drive.py -p no:cacheprovider

tests/test_nightly_drive.py::test_win_nightly_writes_no_receipt_when_the_experiment_fails FAILED [ 25%]
tests/test_nightly_drive.py::test_win_nightly_withholds_the_publish_when_verify_fails FAILED [ 50%]
tests/test_nightly_drive.py::test_win_nightly_publishes_and_beats_when_the_run_grades_clean FAILED [ 75%]
tests/test_nightly_drive.py::test_both_nightly_templates_regrade_before_publishing FAILED [100%]

________ test_win_nightly_writes_no_receipt_when_the_experiment_fails _________
E       AssertionError: a failed run wrote a receipt:
E         -- 2026-08-22T11:59:00Z nightly start
E         Already up to date.
E         [main 3668ed7] nightly: 2026-08-22
E          3 files changed, 3 insertions(+), 3 deletions(-)
E         To C:\...\test_win_nightly_writes_no_rec0\origin.git
E            f2e8774..3668ed7  main -> main
E         -- done (success)
E
E       assert '3668ed77b2b9...6b0554bd37939' == 'f2e87742c929...8e357b04a66a0'
tests\test_nightly_drive.py:116: AssertionError

__________ test_win_nightly_withholds_the_publish_when_verify_fails ___________
E       AssertionError: an ungraded run was published:
E         [main 22bb6fa] nightly: 2026-08-22
E            9d828ae..22bb6fa  main -> main
E         -- done (success)
tests\test_nightly_drive.py:132: AssertionError

_______ test_win_nightly_publishes_and_beats_when_the_run_grades_clean ________
E       AssertionError: no heartbeat after a real publish:
E         [main 41160d4] nightly: 2026-08-22
E            9928d7e..41160d4  main -> main
E         -- done (success)
E       assert False
E        +  where False = exists()
E        +    where exists = (WindowsPath('...\state') / 'nightly.published').exists
tests\test_nightly_drive.py:153: AssertionError
```

**Read the first block carefully: `lab next` returned 1, and the win nightly
committed `nightly: 2026-08-22`, pushed it to main, and logged
`-- done (success)`.** That is the dossier's claim, executed rather than argued.

**FAIL-BEFORE KIND: behavioural.** Every failure is an `AssertionError` about an
observed git SHA or an observed missing file — no `AttributeError`, `KeyError`
or `ImportError`, and no reference to an API that does not exist at `15f0cf6`.
(`test_both_nightly_templates_regrade_before_publishing` is the one string-level
assertion of the four; it is a companion, not the evidence.)

### PASS-AFTER — verbatim

```
$ python -m pytest tests/test_nightly_drive.py tests/test_setup.py -p no:cacheprovider
...
tests/test_setup.py::test_generated_nightly_sh_parses PASSED             [ 95%]
tests/test_setup.py::test_generated_nightly_ps1_parses PASSED            [100%]
============================= 24 passed in 8.68s ==============================
```

### DRY-RUN PROOF — the three cases side by side

Same harness driven as a script against the base generator and then the fixed
one (the direct ancestor of `tests/test_nightly_drive.py`):

```
############ BASE (15f0cf6 generator) ############
### A  lab next FAILS  rcs={'next': 1}
  exit code        : 0
  HEAD moved       : True  (COMMIT WRITTEN)
  commit subject   : nightly: 2026-08-22
  heartbeat exists : False
  log> -- done (success)
### B  verify FAILS  rcs={'next': 0, 'verify': 1}
  exit code        : 0
  HEAD moved       : True  (COMMIT WRITTEN)
  heartbeat exists : False
### C  clean run
  exit code        : 0
  HEAD moved       : True  (COMMIT WRITTEN)
  heartbeat exists : False

############ PATCHED generator ############
### A  lab next FAILS  rcs={'next': 1}
  exit code        : 1
  HEAD moved       : False  (no commit)
  tracked dirt     : ''
  heartbeat exists : False
  log> FAILED: 'lab next' failed -- no receipt is written for a run that did not happen.
  log> -- done (FAILED: experiment failed)
### B  verify FAILS  rcs={'next': 0, 'verify': 1}
  exit code        : 1
  HEAD moved       : False  (no commit)
  tracked dirt     : ''
  heartbeat exists : False
  log> WITHHELD: 'lab verify' failed -- publishing withheld (the grades are in the log above).
  log> -- done (FAILED: verify failed)
### C  clean run
  exit code        : 0
  HEAD moved       : True  (COMMIT WRITTEN)
  commit subject   : nightly: 2026-08-22
  heartbeat exists : True
  log>    4da7cde..cc0a70b  main -> main
  log> -- published
  log> -- done (success)
```

**Failed `lab next` produces no commit: yes.** It also no longer exits 0, and it
leaves the clone clean (`tracked dirt: ''`) so the next run starts from a good
state — the `Restore-CampaignPaths` helper, mirroring `campaign.sh:294-300`.

### Judgement calls, stated rather than buried

- **Both templates changed, not just the PS1.** `nightly_script()` (bash, for
  cron/systemd installs) carried the identical two defects. Fixing only the win
  side would have closed a win/loam asymmetry by opening a ps1/sh one, and the
  existing tests already assert the two templates as a pair.
- **Deliberate divergence from loam on the `next`-failure path.** `campaign.sh`
  logs "experiment failed; refreshing existing feed only", runs `lab publish`,
  and *may still commit* that refresh. The win path now publishes nothing and
  commits nothing. A freshened feed committed under a `nightly:` message right
  after a failed experiment is the failure-masquerade itself; the invariant
  being mirrored is "publish only what verify graded", not the literal control
  flow. This is win being **stricter** than loam, and it is the shape the
  done-when asked for.
- **Failure now exits 1.** `RestartOnFailure` in the task XML (`PT5M`, count 2)
  will retry a failed experiment twice. That is the established convention in
  this template — the STRANDED guard already exits 1 while the benign
  not-on-main skip exits 0 — and a green exit 0 on a withheld publish is exactly
  the "outage that reports success" class this lane exists to close.
- **Heartbeat only beats on a real push.** If a graded run produces
  byte-identical output there is no commit, no push, and no heartbeat. That is
  loam's accepted behaviour too (`campaign.sh:336` sits inside the pushed
  branch), so the two lanes stay symmetric.

### Remaining asymmetry, NOT closed here

`campaign.sh:281` refuses a pass when the worktree has pre-existing **tracked
changes**; the win template only refuses a pre-loaded **index**. Adding the
worktree guard to win was considered and rejected: agents work in the win clone
(`IN-USE.md` is a live convention there), so a stray edit would freeze the public
feed for as long as it sat. Recorded rather than silently fixed — it is a
scope-and-risk call, not an oversight.

### Follow-up owed OUTSIDE this repo (not done here, deliberately)

The artifact now exists at `$HOME/.lab/nightly.published`, matching the
`~/.lab/<lane>.published` convention. Making the watcher *read* it needs one row
in `personal-infra/groundskeeper/checks/freshness.py` (beside the
`campaign.published` row at `:74`), scoped to the win box — that table is
currently loam-local. Different repo, so it is named here rather than smuggled
into this branch.

---

## STR-9 — a bare `pytest` in a worktree tested the WRONG SOURCE — **CLOSED** (`635b9fb`)

### Reproduced at `15f0cf6`

```
$ cd /c/Users/beschipp/projects/_workspaces/windowsill-lab-gen
$ python -c "import lab; print(lab.__file__)"
C:\Users\beschipp\projects\windowsill-lab\src\lab\__init__.py          # THE LIVE CLONE
$ PYTHONPATH=src python -c "import lab; print(lab.__file__)"
C:\Users\beschipp\projects\_workspaces\windowsill-lab-gen\src\lab\__init__.py
```

`lab` is installed editable, and an editable install points at exactly one tree.
There was no `conftest.py` anywhere and no `pythonpath` entry in
`pyproject.toml`, so a bare `pytest` in a worktree collected the worktree's
**tests** and ran them against the primary clone's **code**. CI is unaffected —
`.github/workflows/ci.yml` sets `PYTHONPATH=src` explicitly — which is precisely
why it survived: green CI could not see it.

### FAIL-BEFORE — verbatim, at `15f0cf6`

```
$ python -m pytest tests/test_import_hygiene.py -p no:cacheprovider

E       AssertionError: tests in C:\Users\beschipp\projects\_workspaces\windowsill-lab-gen
        are exercising C:\Users\beschipp\projects\windowsill-lab\src\lab\__init__.py
        - a different tree.
E         A bare `pytest` in a worktree resolved `lab` through the editable install
        instead of ./src; see conftest.py.
E       assert False
E        +  where False = is_relative_to(WindowsPath('C:/Users/beschipp/projects/_workspaces/windowsill-lab-gen'))
tests\test_import_hygiene.py:23: AssertionError

FAILED tests/test_import_hygiene.py::test_lab_resolves_to_the_tree_the_tests_live_in
FAILED tests/test_import_hygiene.py::test_lab_resolves_under_src
============================== 2 failed in 0.23s ==============================
```

Behavioural: it asserts on the value of `lab.__file__`, which exists at
`15f0cf6` and holds the wrong value.

### The fix, and why this one

A root `conftest.py` that prepends `./src` to `sys.path` — **not**
`[tool.pytest.ini_options] pythonpath = ["src"]`. Both work; the conftest was
picked because it anchors the resolution to **the location of the file itself**
(`Path(__file__).resolve().parent / "src"`) rather than to pytest's *rootdir
inference*, which is the thing that varies between `pytest`, `pytest tests/`,
and `python -m pytest` run from a subdirectory. It also carries the explanation
of why it exists, which an ini key cannot. The `if not in sys.path` guard makes
it a no-op when `PYTHONPATH=src` is already set, so CI behaviour is unchanged.

### PASS-AFTER — verbatim

```
$ python -m pytest tests/test_import_hygiene.py -p no:cacheprovider   # no PYTHONPATH
collected 2 items
tests/test_import_hygiene.py::test_lab_resolves_to_the_tree_the_tests_live_in PASSED [ 50%]
tests/test_import_hygiene.py::test_lab_resolves_under_src PASSED         [100%]
============================== 2 passed in 0.04s ==============================
```

The full branch suite below was run **bare** (no `PYTHONPATH`) for exactly this
reason: `test_import_hygiene` is inside it, so the run proves its own source.

### The blast radius is wider than pytest — say so plainly

`conftest.py` only governs **pytest**. Any bare `python -c "from lab import ..."`
run from a worktree still resolves to the live clone. This bit me while writing
this file: I read back the generated `nightly.ps1` with a bare `python -c` and
got the **old, unfixed** template, because `import lab` had gone to
`~/projects/windowsill-lab`. The correct form inside a worktree remains
`PYTHONPATH=src python -c ...`, exactly as the lane brief says. Closing that
surface properly means a per-worktree venv (or `pip install -e .` per tree),
which is an estate decision, not a one-file fix — named here rather than
pretended away by a conftest that cannot reach it.

---

## FULL SUITE — base vs branch

```
base   (15f0cf6, PYTHONPATH=src, new files excluded)
  1584 passed, 16 skipped, 1 warning in 538.30s (0:08:58)

branch (bare `python -m pytest`, no PYTHONPATH)
  BRANCH-SUITE: see the line appended below
```

Status changes: none expected — the only deltas are the new tests
(`test_import_hygiene.py` +2, `test_nightly_drive.py` +4). Final numbers are
recorded in the BRANCH-SUITE line at the end of this file.

### A discarded run, recorded because it is this lane's own subject matter

The first branch-suite attempt reported:

```
================= 520 passed, 1 warning in 368.19s (0:06:08) ==================
[exited with code 0]
```

That is **not** a result and was thrown away. Above it in the same output:

```
INTERNALERROR> ...
INTERNALERROR> MemoryError
```

Four gauntlet lanes were running suites concurrently on a 32 GB box; pytest hit
`MemoryError` inside its own traceback formatter, aborted collection partway
(hence 520 and *zero* skips against a base of 1584 passed / 16 skipped) — **and
exited 0**. A truncated run that reports success is exactly the class AUTO-F7
closes, arriving unprompted in the harness measuring it. The number below is
from a clean re-run with the machine quiet. Anyone re-running the suite under
lane contention should `grep INTERNALERROR` before believing the summary line.
