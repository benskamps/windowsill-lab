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

The FAIL-BEFORE blocks were produced by reverting only the source (leaving the
new tests in place), which is the exact state the manager will re-verify:

```
git stash push -u -- src/     # tests stay, fix goes away
PYTHONPATH="$PWD/src" python -m pytest <selector>
git stash pop
```

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

**Commit:** ``d2546b3``
