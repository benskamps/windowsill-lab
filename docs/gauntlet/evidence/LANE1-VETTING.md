# Lane 1 — Vetting Spine: closure evidence

**Branch:** `gauntlet/vetting-spine`, based at `15f0cf6`.
**Consumer:** the gauntlet manager, re-verifying each finding by running the
named test at the pre-fix base and confirming it FAILS there.
**Findings:** VET-F1, VET-F2, VET-F3, VET-F4 (all P1, ledger LANE 1).

---

## READ THIS FIRST — how to reproduce any run below

`windowsill-lab` is pip-installed **editable, pointed at the live clone**
`C:\Users\beschipp\projects\windowsill-lab\src\lab`. A bare `python -m pytest`
inside a worktree therefore imports the **live clone's** source, not the
worktree's — it silently grades the wrong tree. Every command in this file
pins the worktree explicitly:

```
PYTHONPATH="$PWD/src" python -m pytest ...
```

Verify before trusting any result here:

```
$ PYTHONPATH="$PWD/src" python -c "import lab; print(lab.__file__)"
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\src\lab\__init__.py
```

The FAIL-BEFORE blocks were produced against a pristine export of the base
commit's source, with the new tests in place — the exact state the manager
will re-verify. Set the rig up once:

```
BASE=/tmp/base15f0cf6
rm -rf "$BASE" && mkdir -p "$BASE"
git archive 15f0cf6 src | tar -x -C "$BASE"
PYTHONPATH="$BASE/src" python -c "import lab; print(lab.__file__)"   # must print $BASE
```

Then every FAIL-BEFORE below reproduces as

```
PYTHONPATH="$BASE/src" python -m pytest <selector>
```

and its matching PASS-AFTER as

```
PYTHONPATH="$PWD/src" python -m pytest <selector>
```

(VET-F1's fail-before predates this rig and was captured with
`git stash push -u -- src/`, which is equivalent for that finding — it reverts
every file VET-F1 touches.)

---

## VET-F1 — checker vocabulary five verdicts behind the engine — **CLOSED**

**Defect (confirmed).** `src/lab/checks.py:184` restated the engine's
disposition vocabulary as a 13-entry literal; `src/lab/a05.py:112` defined 18.
Missing from the checker: `eclipsing-binary-p2-alias`, `companion-too-large`,
`blended-known-planet`, `blend-favours-neighbour`, `ctoi-known` — every word
the 2026-08-19/20 sky and blend gates added. The first honest refutation those
gates drew would hit `checks.py:2892` (gate 4), return `False`, and quarantine
the **whole** receipt: slice lost, targets silently re-eligible.

**Fix.** New stdlib-only `src/lab/a05_vocab.py` holds the one definition.
`a05.py` re-exports `MACHINE_DISPOSITIONS` / `TOI_REFUTED_DISPOSITIONS` from
it; `checks.py` derives `A05_MACHINE_VOCABULARY` / `A05_TOI_REFUTED` from it.
A separate module (rather than `checks.py` importing `a05.py`) is deliberate:
`checks.py` is documented stdlib-only and must stay importable without numpy
or any engine code, so the checker never imports the engine that produced the
receipt it grades. Verified still true after the fix:

```
$ PYTHONPATH="$PWD/src" python -c "import sys, lab.checks; print('numpy' in sys.modules)"
False
```

**Test command**

```
PYTHONPATH="$PWD/src" python -m pytest tests/test_a05_receipts.py \
  -k "vocabulary or gate_4 or new_verdict" -p no:randomly -q --tb=line
```

**FAIL-BEFORE** (src reverted to `15f0cf6`, new tests present)

```
      'machine vocabulary' is contained here:
      ?          -------
        tside the machine vocabulary ? the machine has no word for 'planet' and may not invent one
      ?                   +++++++++++++++++++++++++
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a05_receipts.py:752: AssertionError: A05 TIC 901 carries disposition 'ctoi-known', outside the machine vocabulary ? the machine has no word for 'planet' and may not invent one
=========================== short test summary info ===========================
FAILED tests/test_a05_receipts.py::test_checker_vocabulary_is_lockstep_with_the_engine
FAILED tests/test_a05_receipts.py::test_every_new_verdict_is_in_the_checker_vocabulary
FAILED tests/test_a05_receipts.py::test_new_engine_verdict_clears_gate_4[eclipsing-binary-p2-alias]
FAILED tests/test_a05_receipts.py::test_new_engine_verdict_clears_gate_4[companion-too-large]
FAILED tests/test_a05_receipts.py::test_new_engine_verdict_clears_gate_4[blended-known-planet]
FAILED tests/test_a05_receipts.py::test_new_engine_verdict_clears_gate_4[blend-favours-neighbour]
FAILED tests/test_a05_receipts.py::test_new_engine_verdict_clears_gate_4[ctoi-known]
============ 7 failed, 1 passed, 40 deselected in 79.86s (0:01:19) ============
```

7 failures: 2 lockstep tripwires + one per new verdict (the ledger's "one
receipt fixture per new verdict passes gate 4"). Each gate-4 failure is the
real quarantine message from `checks.py`, drawn on an otherwise-honest
end-to-end receipt from the module's full-pipeline `hunt` fixture.

**PASS-AFTER**

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.5.0, asyncio-1.3.0, cov-7.0.0, mock-3.15.1, respx-0.22.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 48 items / 40 deselected / 8 selected

tests\test_a05_receipts.py ........                                      [100%]

================= 8 passed, 40 deselected in 83.64s (0:01:23) =================
```

**Commit:** `b692d1a` — fix(vet-f1): derive checker disposition vocabulary from the engine's


---

## VET-F3 — a mean's error bar on a median's number — **CLOSED**

**Defect (confirmed — and quantified more precisely than the ledger).**
`vet_candidate` reads every depth with `np.median` but divides by a **mean's**
standard error, `noise / sqrt(n)` (`a04.py:210`, `:215` at `15f0cf6`). The SE
of a median on Gaussian noise is `sqrt(pi/2)` times a mean's, and a
*difference* of two medians carries that factor on each term. Measured on the
pre-fix tree, the two affected statistics run hot by different amounts:

| statistic | site | true inflation | measured pre-fix |
|---|---|---|---|
| `odd_even_sigma` — difference of two medians | `:211` | `sqrt(pi)` = 1.7725 | **1.7697** (analytic pin); 1.81 (120-trial pure-noise MC) |
| `depth_sigma` — depth against the baseline median | `:220` | `sqrt(pi/2)` = 1.2533 | **1.253** (6.15 reported on a true 4.91-sigma dip) |

The ledger's headline is right: the candidate-minting rung at `:244` is
miscalibrated and mints below threshold. One number in it is not. The "true
~2.8 sigma clears the 5-sigma bar" figure applies `sqrt(pi)` to the *depth*
gate, but the depth gate carries `sqrt(pi/2)` — one median against a
large-`n` baseline, not two medians differenced. So `:244` actually admits
true **~3.99-sigma** dips (5 / 1.2533), not 2.8-sigma ones. The 1.77x figure
is exactly right for the odd-even statistic at `:211`. Both sites are wrong,
both are fixed; the magnitudes are recorded here as measured rather than
restated.

**Fix.** `MEDIAN_SIGMA_FACTOR` now has one definition, in `a04.py` — the lower
module, since `a05_fold` imports `a04` and the constant cannot live in
`a05_fold` without a cycle — and `a05_fold.MEDIAN_SIGMA_FACTOR` re-exports it,
giving the repo one convention as the brief required. A local
`_median_se(*counts)` builds the SE of a sum or difference of independent
medians, and each statistic asks for its own terms instead of sharing one
wrong bar:

- `odd_even_sigma` -> `_median_se(n_odd, n_even)`
- `sec_sigma` -> `_median_se(n_sec, n_out)`, sign preserved (the
  `phased-brightening` verdict tests `sec_sigma <= -5`)
- `depth_sigma` -> `_median_se(min(n_odd, n_even), n_out)`

`base` is itself a median over the out-of-transit sample, so it enters as a
term: negligible at large `n_out`, but not zero, and not the caller's job to
decide that.

**Test command**

```
python -m pytest tests/test_a04_maturity.py \
  -k "calibrated or analytic_difference or sub_five or genuinely_significant" \
  -p no:randomly -q --tb=line
```

**FAIL-BEFORE** (base source at `15f0cf6`)

```
     +  where 0.6446568637086126 = abs((1.442541424511478 - 0.7978845608028654))
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a04_maturity.py:350: AssertionError: odd-even sigma is not calibrated: mean|z| = 1.443, expected 0.798 (scale is off by 1.808x)
E   AssertionError: reported 0.5011 vs analytic 0.2832 - ratio 1.7697
    assert 0.5010991962750879 == 0.28315497039243254 +- 2.8e-10

      comparison failed
      Obtained: 0.5010991962750879
      Expected: 0.28315497039243254 +- 2.8e-10
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a04_maturity.py:371: AssertionError: reported 0.5011 vs analytic 0.2832 - ratio 1.7697
E   AssertionError: depth_sigma 6.15 still clears the 5-sigma bar on a true ~4.9-sigma dip
    assert 6.152078020953943 < 5.0
     +  where 5.0 = a04.ODD_EVEN_SIGMA
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a04_maturity.py:386: AssertionError: depth_sigma 6.15 still clears the 5-sigma bar on a true ~4.9-sigma dip
=========================== short test summary info ===========================
FAILED tests/test_a04_maturity.py::test_odd_even_sigma_is_calibrated_on_pure_noise
FAILED tests/test_a04_maturity.py::test_odd_even_sigma_matches_the_analytic_difference_of_medians
FAILED tests/test_a04_maturity.py::test_depth_gate_does_not_mint_a_sub_five_sigma_candidate
================= 3 failed, 1 passed, 25 deselected in 1.67s ==================
```

The fourth selected test (`test_a_genuinely_significant_dip_is_still_a_candidate`)
passes at the base by design — it is the guard that the fix tightens the bar
without closing it.

**PASS-AFTER**

```
collected 29 items / 25 deselected / 4 selected

tests\test_a04_maturity.py ....                                          [100%]

====================== 4 passed, 25 deselected in 1.47s =======================
```

**No collateral damage.** Every suite that consumes these statistics stays
green with the tightened bars:

```
$ PYTHONPATH="$PWD/src" python -m pytest tests/test_a04_maturity.py tests/test_a05_fold.py \
    tests/test_a05_vetting.py tests/test_a05_mono.py tests/test_a05_shape.py -p no:randomly -q
============================= 97 passed in 33.93s =============================
```

**Commit:** `c153034` — fix(vet-f3): give the A04 vetting rung a median error bar


---

## VET-F4 — sky gates dead in production — **CLOSED**

**Defect (confirmed, and worse than the anchor says).** `scripts/a05_hunt.py`
called `run_a05` without `neighbours` / `sky_catalog`, so `apply_sky_gates`
(`a05.py:492-536` — the 2026-08-20 HATS-16 b fix) was a no-op in the one place
production leads are minted. Investigating it surfaced a second fact the
ledger does not record: **no production neighbour resolver existed anywhere in
the repo.** `grep` for `neighbours` across `src/` and `scripts/` at `15f0cf6`
returns only `a05_sky`'s own consumers and `a05.py`'s parameter. The gate was
not merely unwired — there was nothing to wire it to. So this fix is bigger
than "pass two kwargs", and that is stated here rather than buried.

**Fix, in four parts.**

1. **The resolvers** (`src/lab/a05_sky.py`): `resolve_neighbours(tic)` does a
   MAST TIC cone search of `NEIGHBOUR_MAX_PX` (4 px) and returns the row shape
   `aperture_shares` / `neighbour_crosscheck` already consume — `tic`,
   `sep_px` (via the module's own `separation_px`), `flux_rel` from the Tmag
   difference, `r_star_sun`. `sky_catalog_lookup(tic)` routes a NEIGHBOUR's
   TIC through `a04.catalog_crosscheck` and then `exofop.ctoi_crosscheck`.
   Both use `a01._mast` — the same query path `scripts/survey_census.py`
   already uses for `Mast.Catalogs.Filtered.Tic`.

2. **The wiring** (`scripts/a05_hunt.py`): both seams passed as
   `functools.partial`s with their own `sky_deadline` (the hunt's soft wall
   plus a 300 s grace), because the sky lookups run in the wrap, *after* the
   search budget is spent, and would otherwise inherit an already-expired
   deadline.

3. **Positive evidence** (`a05.py`): a `sky_gates` block on every receipt —
   `status` (`"ran"` / `"not-wired"`), `neighbours_wired`, `catalog_wired`,
   `rows_examined`, `rows_refuted`, `lookup_errors`, `verdicts`. This is the
   part the brief insisted on: absence of a sky verdict is ambiguous between
   "ran and cleared every lead" and "never wired", and for a day in August it
   silently meant the second. The block is emitted whether or not the gate
   ran, so a receipt can say *"this gate did not run"* out loud. It is the
   only shape change to committed receipts, and it is additive.

4. **The outage guard widened** (`a05.py`, `apply_sky_gates`). The existing
   `try` covered only `neighbours(...)`. `neighbour_crosscheck` *skips* a
   neighbour whose `catalog_lookup` returns nothing, so a TOI/CTOI outage
   returning `None` was indistinguishable from "this neighbour carries no
   planet" — the same unasked-question-reads-as-cleared-gate failure the
   finding is about, one level down. `sky_catalog_lookup` now raises
   `a05_sky.SkyLookupError` instead of returning `None` on a failed lookup,
   and the guard covers the cross-check, so an outage strips the disposition,
   marks the row `pending_catalog`, and `run_a05` refuses to call the slice
   complete.

**Honest limit.** `resolve_neighbours` and `sky_catalog_lookup` make live MAST
and ExoFOP calls, and **their live behaviour is not verified from this box** —
no test here hits the network. What is tested is the wiring (the driver
reaches the real entry points), the execution record, the per-row evidence,
and the outage path. A first production hunt should have its receipt's
`sky_gates` block read before its leads are trusted.

**Test command**

```
python -m pytest tests/test_a05_hunt_script.py tests/test_a05_receipts.py \
  -k "sky_gate_seams or wired_resolvers or declares_the_sky_gate or wired_run \
      or examined_row or sky_lookup_outage or neighbour_catalog_outage" \
  -p no:randomly -q
```

**FAIL-BEFORE** (base source at `15f0cf6`)

```
E   KeyError: 'sky_gates'
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a05_receipts.py:767: KeyError: 'sky_gates'
E   KeyError: 'sky_gates'
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a05_receipts.py:806: KeyError: 'sky_gates'
E   KeyError: 'sky_gates'
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a05_receipts.py:816: KeyError: 'sky_gates'
E   AssertionError: assert 'AttributeError' == 'SkyLookupError'

      - SkyLookupError
      + AttributeError
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a05_receipts.py:841: AssertionError: assert 'AttributeError' == 'SkyLookupError'
E   AttributeError: module 'lab.a05_sky' has no attribute 'SkyLookupError'
C:\Users\beschipp\projects\_workspaces\windowsill-lab-vet\tests\test_a05_receipts.py:853: AttributeError: module 'lab.a05_sky' has no attribute 'SkyLookupError'
=========================== short test summary info ===========================
FAILED tests/test_a05_hunt_script.py::test_production_hunt_wires_the_sky_gate_seams
FAILED tests/test_a05_hunt_script.py::test_the_wired_resolvers_are_the_real_ones
FAILED tests/test_a05_receipts.py::test_receipt_declares_the_sky_gate_did_not_run
FAILED tests/test_a05_receipts.py::test_a_wired_run_actually_reaches_apply_sky_gates
FAILED tests/test_a05_receipts.py::test_the_examined_row_carries_its_sky_evidence
FAILED tests/test_a05_receipts.py::test_a_sky_lookup_outage_does_not_mint_a_lead
FAILED tests/test_a05_receipts.py::test_a_neighbour_catalog_outage_does_not_read_as_a_clean_neighbour
=========== 7 failed, 1 passed, 58 deselected in 200.54s (0:03:20) ============
```

The one pass at base is `test_a_wired_run_still_passes_check_a05` — the guard
that wiring the gate does not make the receipt unreadable. It is expected to
pass on both sides.

The headline failure is the first line of the summary:
`test_production_hunt_wires_the_sky_gate_seams`, whose message at base reads

```
AssertionError: a05_hunt calls run_a05 without `neighbours` - apply_sky_gates
is a no-op and every lead is minted without asking whose light it was
```

**PASS-AFTER**

```
collected 66 items / 58 deselected / 8 selected

tests\test_a05_hunt_script.py ..                                         [ 25%]
tests\test_a05_receipts.py ......                                        [100%]

================ 8 passed, 58 deselected in 197.55s (0:03:17) =================
```

**No collateral damage** — the whole receipt suite, including every
adversarial hand-edit test, is green with the additive block:

```
$ PYTHONPATH="$PWD/src" python -m pytest tests/test_a05_receipts.py -p no:randomly -q
======================= 54 passed in 201.43s (0:03:21) ========================
$ PYTHONPATH="$PWD/src" python -m pytest tests/test_a05_hunt_script.py -p no:randomly -q
============================= 12 passed in 0.26s ==============================
```

**Commit:** VETF4_SHA
