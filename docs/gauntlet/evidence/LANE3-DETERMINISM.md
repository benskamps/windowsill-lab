# Lane 3 — Determinism

Branch `gauntlet/determinism`, based at `15f0cf6`.
Findings DET-1, DET-2, DET-3 from the 2026-08-21 gauntlet dossier.

**The theme:** the committed feed was not regenerable from repo content. Two
boxes regenerated different ledgers from the same commit. This lane makes the
artifacts a pure function of the repo.

| finding | verdict | commit |
|---|---|---|
| DET-1 non-atomic canonical writes | **CLOSED** | `00945c8` |
| DET-2 pot ordering derives from mtimes | **CLOSED** | `b5a2768` |
| DET-3 "NEVER sort_keys" enforced by comment only | **CLOSED** | `de536ad` |

---

## Before anything else: `PYTHONPATH=src` is mandatory

The editable install on this box resolves `lab` to the **live clone**, not to a
worktree:

```
$ python -c "import lab; print(lab.__file__)"
C:\Users\beschipp\projects\windowsill-lab\src\lab\__init__.py
```

There is no `conftest.py` and no `pythonpath` in `pyproject.toml`, so
`python -m pytest` from a worktree silently tests the live clone's source. Every
command below therefore starts with `PYTHONPATH=src`, and every re-verification
must too — without it a green run on this branch proves nothing about it.

```
$ PYTHONPATH=src python -c "import lab; print(lab.__file__)"
C:\Users\beschipp\projects\_workspaces\windowsill-lab-det\src\lab\__init__.py
```

The pre-fix runs quoted below were taken from an isolated export of the base
commit (`git archive 15f0cf6 | tar -x -C <tmp>`, with the three new test files
copied in), so nothing about them depends on this worktree's state.

---

## DET-1 (P1) — non-atomic canonical writes, frozen forever by receipt immutability

**Commit `00945c8`** · `src/lab/atomic.py`, `tests/test_atomic_writes.py`, and
59 call sites across `publish.py`, `physics_feed.py`, `receipt.py`,
`archive.py`, `render.py`.

### What was wrong

Every canonical writer went `dest.write_text(...)`, which truncates the
destination and then fills it. An interrupted write left a truncated file where
the evidence had been. For receipts that is permanent:
`publish.py:1476-1478` keeps whatever receipt is already on disk — correctly,
because evidence is immutable and the selector cannot tell a correction from a
corruption — so a torn receipt is frozen forever.

The dossier said "~15 writers in `render.py`". The real count is **51 in
`render.py`** and **59 in total**; all 59 are fixed.

### The fault injection

Deliberately symmetric. It patches `io.open`, the single call that BOTH
`Path.write_text` and an explicit `path.open("w")` bottom out in, and tears any
write whose file name mentions the destination. The old in-place writer and the
new tmp writer face the identical fault; only the destination differs, which is
the entire point of the fix. (A first attempt patched
`io.TextIOWrapper.write` — that type is immutable in CPython and the patch
raises `TypeError`, so it never ran.)

### Command

```
PYTHONPATH=src python -m pytest tests/test_atomic_writes.py -p no:cacheprovider --no-header -q
```

### FAIL-BEFORE (verbatim, at `15f0cf6`)

```
============================= test session starts =============================
collected 5 items

tests\test_atomic_writes.py FFFFF                                        [100%]

================================== FAILURES ===================================
tests\test_atomic_writes.py:81: in _survives_json
E           json.decoder.JSONDecodeError: Unterminated string starting at: line 3 column 15 (char 44)
tests\test_atomic_writes.py:81: in _survives_json
E           json.decoder.JSONDecodeError: Unterminated string starting at: line 4 column 10 (char 48)
E       AssertionError: assert '<html>zzzzzz...zzzzzzzzzzzzz' == '<html><body>.../body></html>'
tests\test_atomic_writes.py:136: AssertionError
tests\test_atomic_writes.py:81: in _survives_json
E           json.decoder.JSONDecodeError: Unterminated string starting at: line 3 column 11 (char 45)
E       AssertionError: in-place canonical writes (use lab.atomic.atomic_write_text):
E       assert not ['publish.py:1481: destination.write_text(content, encoding="utf-8")', 'publish.py:1526: json_dest.write_text(src.read...oding="utf-8")', 'physics_feed.py:428: out_path.write_text(json.dumps(feed, indent=2) + "\\n", encoding="utf-8")', ...]
tests\test_atomic_writes.py:181: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_atomic_writes.py::test_torn_receipt_write_leaves_the_committed_receipt_intact
FAILED tests/test_atomic_writes.py::test_torn_physics_feed_write_leaves_the_previous_feed_intact
FAILED tests/test_atomic_writes.py::test_torn_archive_index_write_leaves_the_committed_index_intact
FAILED tests/test_atomic_writes.py::test_torn_pot_write_leaves_the_committed_feed_intact
FAILED tests/test_atomic_writes.py::test_no_canonical_writer_writes_in_place
============================== 5 failed in 0.50s ==============================
```

Read the failures, not just the count: `Unterminated string` means the receipt,
the physics feed and `pot.json` that were already on disk came back **truncated
and unparseable**. The archive index came back as the letter `z` repeated. In
every case the pre-existing evidence was destroyed by an interrupted write.

### The fix

`src/lab/atomic.py` — the pattern lifted from `scripts/a05_hunt.py:284-288`
and `:318-322` (tmp file → `flush` → `os.fsync` → `Path.replace`), unchanged in
substance, with two documented additions: the tmp name is dot-prefixed and
pid-stamped so it cannot be caught by any discovery glob or collide between the
parallel lanes, and a failed write unlinks the tmp and re-raises rather than
reporting success. No second pattern was invented.

**No bytes changed.** `open(mode="w")` with the default `newline=None`
translates `\n` to `os.linesep`, which is exactly what `Path.write_text` did, so
every committed artifact still serializes identically:

```
$ PYTHONPATH=src python -c "...write the same text both ways, compare bytes..."
write_text bytes : b'line1\r\nline2\r\nunicode \xe2\x80\x94 dash\r\n'
atomic bytes     : b'line1\r\nline2\r\nunicode \xe2\x80\x94 dash\r\n'
IDENTICAL: True
tmp residue: ['a.txt', 'b.txt']
```

Confirmed at scale by the full suite: 1589 passed / 16 skipped / **0 failed**
with DET-1 alone applied — not one golden, contract or sync test moved.

A `.gitignore` rule for `.*.tmp` / `*.tmp` rides along: a crashed write leaves a
scratch file behind, and the nightly stages `reports/` with `git add -A`, which
picks up dotfiles. Nothing tracked in this repo ends in `.tmp`.

The receipt-immutability rule at `publish.py:1476-1478` is left as it is. It was
never the bug; it was the amplifier. With atomic writes a torn receipt never
exists, so "keep what is on disk" can no longer freeze a corruption.

### PASS-AFTER (verbatim)

```
============================= test session starts =============================
collected 5 items

tests\test_atomic_writes.py .....                                        [100%]

============================== 5 passed in 0.16s ==============================
```

---

## DET-2 (P1) — pot.json ordering derives from filesystem mtimes

**Commit `b5a2768`** · `src/lab/archive.py`,
`tests/test_ledger_determinism.py`, `tests/test_archive.py`.

### What was wrong

`archive.py:495-500` sorted the ledger newest-first with the file's **mtime as
the primary key**. Nothing in git preserves mtimes: a clone stamps every file
with the checkout time and `git pull` re-stamps whatever it touched. So win and
loam regenerated different `pot.json` files from byte-identical repo content,
each saw the other's feed as changed, and each committed its own.

The sort was not the only mtime term. Where two files in one directory resolved
to a single `(date, slug, turn)` key — the legacy bare `<date>.json` dump and
the per-run `<date>-<slug>.json` — the newest mtime won, so the row's **content**
moved between boxes as well. Both are fixed.

### The fix

| | key |
|---|---|
| sort | `(date, turn, generated_at, slug)`, reverse. No mtime term. |
| same-key tiebreak (`_pick_rank`) | `(generated_at, per-run-file-over-bare-dump, filename)`. No mtime term. |

Content-id choice: `generated_at` is the run's own timestamp out of its own
document — content, present already, identical in every clone (the same field
`_receipts_by_run` already joins on). It orders two different milestones that
share one `(date, turn)`. The slug closes the key so two rows can never tie and
fall back on dict iteration order.

### Command

```
PYTHONPATH=src python -m pytest tests/test_ledger_determinism.py -p no:cacheprovider --no-header -q
```

### FAIL-BEFORE (verbatim, at `15f0cf6`)

```
tests\test_ledger_determinism.py FF.F                                    [100%]
=========================== short test summary info ===========================
FAILED tests/test_ledger_determinism.py::test_pot_regeneration_is_byte_identical_under_mtime_shuffle
FAILED tests/test_ledger_determinism.py::test_scan_runs_order_is_independent_of_mtimes
FAILED tests/test_ledger_determinism.py::test_same_key_file_choice_is_independent_of_mtimes
========================= 3 failed, 1 passed in 2.03s =========================
```

The headline assertion's own message, at the base:

```
E       AssertionError: pot.json is not a pure function of repo content — the two boxes regenerate different feeds:
E           run 1 sha256 698522b410d27401f8acd730d00b184f75773dcf46cee2276e380ddc016cdd0f
E           run 2 sha256 3980911f04ace1ff2ff4a0b28851f94f3fcac4b5caa69e8f9c04f8f812b818b8
E           run 1 order  ['same turn, different milestone (b)', 'same turn, different milestone (b)']
E           run 2 order  ['the oldest run', 'first turn of the 20th', 'same turn, different milestone (a)', 'same turn, different milestone (b)']
```

The same fixture published a 2-row feed on one mtime arrangement and a 4-row
feed on the other.

### PASS-AFTER (verbatim)

```
============================= test session starts =============================
collected 4 items

tests\test_ledger_determinism.py ....                                    [100%]

============================== 4 passed in 1.28s ==============================
```

### The byte-identical regeneration demonstration

`docs/gauntlet/evidence/det2_regen_demo.py` is a standalone, rerunnable version
of the headline proof — no pytest, exits 0 when the two runs agree, and runs
unmodified at the pre-fix base. It builds five runs in a temp dir, regenerates
the pot bytes, re-stamps every mtime in reverse order (what the other box's
`git pull` does to a working tree), and regenerates again. The wall clock and
the CPU thermometer — the feed's two honest non-repo inputs — are pinned, so the
only thing left that can move the bytes is the filesystem's timestamps.

```
PYTHONPATH=src python docs/gauntlet/evidence/det2_regen_demo.py
```

#### The mtime shuffle between the two runs

```
run 1 mtimes (ascending, as a sequential checkout leaves them):
    1700000000  2026-08-19-m01.json
    1700000060  2026-08-20-m01.json
    1700000120  2026-08-20-m03.json
    1700000180  2026-08-21-m01.json
    1700000240  2026-08-21-m03.json
    1700000300  run-2026-08-19-0700-m01.json
    1700000360  run-2026-08-20-0700-m01.json
    1700000420  run-2026-08-20-1900-m03.json
    1700000480  run-2026-08-21-0700-m01.json
    1700000540  run-2026-08-21-0700-m03.json

run 2 mtimes (reversed, as the other box's git pull leaves them):
    1700000600  2026-08-19-m01.json
    1700000540  2026-08-20-m01.json
    1700000480  2026-08-20-m03.json
    1700000420  2026-08-21-m01.json
    1700000360  2026-08-21-m03.json
    1700000300  run-2026-08-19-0700-m01.json
    1700000240  run-2026-08-20-0700-m01.json
    1700000180  run-2026-08-20-1900-m03.json
    1700000120  run-2026-08-21-0700-m01.json
    1700000060  run-2026-08-21-0700-m03.json
```

Identical file contents in both runs; only the timestamps move.

#### BEFORE — at `15f0cf6` (exit 1)

```
run 1  sha256 ff11bd286834607be098b5b7f62cc1bb3bba2b4a86a8ee7057b1aad1255bd1db  74057 bytes
run 2  sha256 7da2979262103532879a525c5987d4635854d15990ced310f39de9070dab72b6  74444 bytes

run 1 scan order (every run, newest first):
    2026-08-21 0700 m03
    2026-08-21 0700 m01
    2026-08-20 1900 m03
    2026-08-20 0700 m01
    2026-08-19 0700 m01
run 2 scan order (every run, newest first):
    2026-08-19 0700 m01
    2026-08-20 0700 m01
    2026-08-20 1900 m03
    2026-08-21 0700 m01
    2026-08-21 0700 m03

run 1 published rows: ['2026-08-21 x1', '2026-08-21 x1', '2026-08-20 x1', '2026-08-20 x2']
run 2 published rows: ['2026-08-19 x1', '2026-08-20 x1', '2026-08-20 x1', '2026-08-21 x1', '2026-08-21 x1']

RESULT: DIVERGED — the same commit publishes two different feeds.
```

The order does not drift — it **fully reverses**, and the published feed differs
in row count and in 387 bytes.

#### AFTER — on this branch (exit 0)

```
run 1  sha256 ff11bd286834607be098b5b7f62cc1bb3bba2b4a86a8ee7057b1aad1255bd1db  74057 bytes
run 2  sha256 ff11bd286834607be098b5b7f62cc1bb3bba2b4a86a8ee7057b1aad1255bd1db  74057 bytes

run 1 scan order (every run, newest first):
    2026-08-21 0700 m03
    2026-08-21 0700 m01
    2026-08-20 1900 m03
    2026-08-20 0700 m01
    2026-08-19 0700 m01
run 2 scan order (every run, newest first):
    2026-08-21 0700 m03
    2026-08-21 0700 m01
    2026-08-20 1900 m03
    2026-08-20 0700 m01
    2026-08-19 0700 m01

run 1 published rows: ['2026-08-21 x1', '2026-08-21 x1', '2026-08-20 x1', '2026-08-20 x2']
run 2 published rows: ['2026-08-21 x1', '2026-08-21 x1', '2026-08-20 x1', '2026-08-20 x2']

RESULT: BYTE-IDENTICAL — the feed is a pure function of repo content.
```

`ff11bd28…` on both runs. Note that run 1 is byte-identical *across the two
trees* as well: the fix does not invent a new order, it stops the old one from
moving.

### What landing this does to the live feed — read before merging

Measured on this box against the real `reports/` tree, before vs after:

```
### PRE-FIX ordering
scan_runs: 163  public_runs: 145
verdicts: {'verified': 128, 'null': 12, 'unscored': 5}
ledger rows: 82
membership sha: 66a3446358ff8335
first 5: [('2026-08-21','1500','m06'), ('2026-08-21','1139','m05'), ('2026-08-19','2111','m11'), ('2026-08-15','2156','m12'), ('2026-08-15','2129','k03')]

### WITH the DET-2 fix
scan_runs: 163  public_runs: 145
verdicts: {'verified': 128, 'null': 12, 'unscored': 5}
ledger rows: 84
membership sha: 66a3446358ff8335
first 5: [('2026-08-21','1500','m06'), ('2026-08-21','1139','m05'), ('2026-08-19','2111','m11'), ('2026-08-19','----','m11'), ('2026-08-15','2156','m12')]
```

**Membership is identical** — same 163 scanned, same 145 public, same verdict
counts, same membership hash. Not one run appears or disappears. What changes is
the **order**, and with it the feed's presentation grouping: 82 collapsed ledger
rows become 84, because `_collapse_streaks` merges consecutive same-verdict runs
and a different order breaks different streaks. Same record, different
arrangement.

So landing DET-2 will produce a whole-`reports`-array diff on `pot.json` the
next time anything publishes. **`pot.json` is deliberately NOT regenerated or
committed on this branch**, per the lane brief: that is Ben's morning call with
the timers quiet.

### One existing test encoded the defect

`tests/test_archive.py::test_scan_runs_newest_first_by_mtime_not_date_string`
asserted that the more recently *written* file leads — the bug, written down as
a requirement. Its original intent (a stale future-dated report must not
masquerade as the latest) bought one narrow case at the cost of the ledger's
determinism. It is rewritten as
`test_scan_runs_newest_first_by_date_not_mtime`, keeps the same fixture, and now
additionally asserts the order survives an mtime swap. This was the **only**
test in the suite that had to change.

---

## DET-3 (P2) — "NEVER sort_keys" enforced only by comments

**Commit `de536ad`** · `tests/test_serialization_pin.py`. No source change —
the pin **is** the fix, and pinning is all it does.

### What was wrong

The rule lives in a comment (`scripts/a05_hunt.py:310-314`; the dossier cites
this as `src/lab/a05_hunt.py`, which does not exist — the file is under
`scripts/`). Every sync gate in the repo compares **parsed objects**, and a
parsed object is blind to key order, indent width, `ensure_ascii` and the
trailing newline. So a `sort_keys` refactor ships green and then rewrites every
committed artifact on its next run.

### Measured, not asserted

Mutation: `sort_keys=True` added to the pot's `json.dumps` in `publish.publish`,
and `sort_keys=True` → `False` in `receipt.receipt_text`. Run at the base tree:

```
### existing sync gates, sort_keys flipped
tests/test_publish.py tests/test_schema.py tests/test_web_pots.py
tests/test_hunt_block.py tests/test_receipt.py tests/test_determinism_golden.py
-> 150 passed          (in this worktree)
-> 1 failed, 149 passed (in the isolated base export; that one failure,
   test_run_record_shape_for_m01, fails there WITHOUT the mutation too — the
   export is not a git repo, so the run's URL resolves to None. Environmental,
   not a catch.)

### the DET-3 pins, same mutation, same tree
=========================== short test summary info ===========================
FAILED tests/test_serialization_pin.py::test_publish_writes_the_pinned_pot_layout
FAILED tests/test_serialization_pin.py::test_receipt_serialization_layout_is_pinned
FAILED tests/test_serialization_pin.py::test_committed_pot_matches_the_publishers_serialization
========================= 3 failed, 7 passed in 3.03s =========================
```

150 existing gates green on a change that would rewrite the entire public
record; the new pins red. That is the finding, measured.

### What is pinned — the current bytes are the spec

Four different layouts are in force and **each is pinned exactly as it already
is**. Nothing was reserialized, and `sort_keys` stays OFF where it is off:

| artifact | layout |
|---|---|
| `pot.json` | `indent=2`, INSERTION order, `ensure_ascii`, trailing newline |
| `physics-latest.json` | `indent=2`, INSERTION order, `ensure_ascii`, trailing newline |
| public receipts | `indent=2`, **SORTED** keys, `ensure_ascii=False`, trailing newline |
| hunt receipts | `indent=1`, INSERTION order, `ensure_ascii`, **no** trailing newline |

Worth stating plainly because it is a trap for the next reader: **receipts are
`sort_keys=True` today, on purpose** (`receipt.py:125`). The pin locks them
sorted. Only the pot and the feeds are insertion-ordered, and those are the ones
a blanket `sort_keys` refactor would wreck.

Two kinds of pin, because either alone has a hole:

* **golden bytes** catch a change to the *writer* before any artifact has been
  regenerated;
* **re-serializing the artifacts already on the books** catches a writer that
  disagrees with what a reader downloads. The committed `pot.json` is put back
  through `publish.publish` itself, not through a mirror of its `json.dumps`
  line.

Known exception, enumerated rather than discovered later: the two `schema: 0`
pilot hunt receipts from 2026-08-14 were written at `indent=2` with a trailing
newline by an older hand. They are committed evidence, so they are named in the
test, not rewritten.

### FAIL-BEFORE / PASS-AFTER

The pins pass at the base *and* on this branch (10 passed both times) — which is
correct and is the point: they change nothing. Their fail-before is the mutation
block above, where the rest of the suite stays green and these go red.

```
tests\test_serialization_pin.py ..........                               [100%]
============================= 10 passed in 3.10s ==============================
```

---

## Suite

```
PYTHONPATH=src python -m pytest tests/ -p no:cacheprovider --no-header -q
```

```
collected 1619 items
...
========== 1603 passed, 16 skipped, 1 warning in 1102.50s (0:18:22) ===========
EXIT=0
```

**Exit 0.** 1619 collected = the base suite's 1600 plus this lane's 19 new tests
(5 DET-1, 4 DET-2, 10 DET-3). The single warning is a pre-existing
`RankWarning` from `fss.py:81` in `test_fss_updater.py`, present at the base.
The run took 18 minutes rather than the usual 11 because the box was running its
own nightly at the time; the counts are unaffected.

Intermediate runs, for the record:

| tree | result |
|---|---|
| DET-1 alone | 1589 passed, 16 skipped, 0 failed |
| DET-1 + DET-2, before updating `test_archive.py` | 1592 passed, 16 skipped, **1 failed** — `test_scan_runs_newest_first_by_mtime_not_date_string`, the test that encoded the defect |
| all three, final | **1603 passed, 16 skipped, 0 failed** |

---

## Notes for the manager

1. **`PYTHONPATH=src` or the re-verification is meaningless.** See the top
   section. CI is unaffected — `.github/workflows/ci.yml` already runs
   `PYTHONPATH=src pytest`. The trap is local: any worktree-based verification
   run on this box without it has been testing the live clone's source.

   Related, and worth someone's attention: CI's pot gate only checks
   `pot.json["milestones"]` against `MILESTONES.md`. The `reports` ledger array
   is not gated, so landing DET-2 without regenerating `pot.json` will not red
   main — the feed simply stays as it is until the next publish rewrites it.

2. **`reports/index.html` drifts when the suite runs.** Some test calls
   `archive.write_index()` without patching `REPORTS_DIR`, so a full suite run
   rewrites the committed index in place. Regenerating it here yields
   `145 runs, 128 passing, 12 nulls` against a committed `146 / 128 / 13` —
   pre-existing drift between the committed index and the current receipts,
   present at the base and unrelated to this lane. Reverted, not committed.
   Someone should own it; it is not one of my three findings.

3. **Dossier corrections.** DET-1 says "~15 writers in `render.py`" — it is 51,
   59 across the five modules, and all are fixed. DET-3 cites
   `src/lab/a05_hunt.py:310-314`; the file is `scripts/a05_hunt.py`.

4. **Nothing on the verified-clean list was touched.** The hunt receipt and pot
   writes in `scripts/a05_hunt.py` are the model this lane copied, not a target;
   they are unchanged.

5. **Not committed on purpose:** a regenerated `pot.json`. DET-2 changes the
   code; landing it rewrites the committed feed (82 → 84 grouped rows, same
   membership), which is Ben's call.

6. **One determinism hole this lane did NOT close: line endings.** These
   artifacts are written with Python's default newline translation, so win
   writes CRLF and loam writes LF for the same content. It never reaches the
   repo *on this box* only because `core.autocrlf=true` normalizes on commit —
   a local git setting, not a repo one. There is no `.gitattributes`. A box
   configured differently would commit CRLF and hand the other box a
   whole-file diff. Pre-existing (`write_text` behaved identically), outside my
   three findings, and deliberately not changed here: pinning newlines rewrites
   how every artifact serializes, which is exactly the class of change DET-3
   exists to prevent shipping quietly. Worth a `.gitattributes` on someone's
   ledger.
