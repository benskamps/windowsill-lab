# Investigation: the win/loam publish divergence — 52 vs 58 reports, temp_c None vs 53.0

**Status:** diagnosis only, 2026-08-12. No code changed, no commits, no pushes.
**Raised by:** Ben's 2026-08-12 directive ("re win and loam, we restart the
investigation — surely. It's all data.") after the 2026-08-11 night lane routed
three merged PRs (#96/#97/#98) *around* this divergence via milestones-key-only
regeneration rather than through it.
**Readers:** whoever next touches `archive.scan_runs`, `archive._collapse_streaks`,
`publish.cpu_temp_c`, or decides the single-producer-vs-two-producer question.
**Method:** `/investigate` (root cause before fix). Everything below is either
**[reproduced]** with a negative control, **[receipt-backed]** from a live read of
the two boxes, or **[hypothesis]** and labelled as such.

---

## TL;DR

Two independent defects, neither of which is what the divergence looked like.

1. **The report count is not a count of reports.** No run is dropped on win.
   Every one of the 114 committed runs appears in both boxes' ledgers. The
   difference is that `_collapse_streaks` merges *consecutive* rows, and
   `scan_runs` orders rows by **file mtime as the primary sort key** — filesystem
   metadata, not content. mtime is a property of *when git happened to write the
   file in that clone*, so the two boxes order the same runs differently, so
   different runs land adjacent, so a different number of rows survive the
   collapse. **[reproduced]**

2. **Neither box publishes a CPU temperature.** win returns `None` because the
   LibreHardwareMonitor web server is not running. loam's `53.0` is **the Intel
   WiFi adapter** (`iwlwifi_1`) — the only entry in loam's
   `/sys/class/thermal`. loam's real CPU sensor exists (`k10temp`, Tctl 47.5 °C)
   but lives under `/sys/class/hwmon/`, which `cpu_temp_c()` never reads. So win
   fails closed and honest; loam fails **open and wrong**, publishing a WiFi
   reading to the public feed under the label "CPU heat". **[receipt-backed]**

The "six dropped reports" framing does not survive contact with the evidence.
There is no set of six names. See §2.4.

---

## 1. Axis one — the report count

### 1.1 The mechanism

`archive.run_ledger()` → `archive.scan_runs()` → `archive._collapse_streaks()`.

`scan_runs` (src/lab/archive.py:342) ends with:

```python
ordered = sorted(
    by_key.items(),
    key=lambda kv: (kv[1][0], kv[0][0], kv[0][2] or ""),   # (mtime, date_stem, turn)
    reverse=True,
)
```

`kv[1][0]` is `p.stat().st_mtime`. It is **primary**. The code's own comment
explains the `date_stem` tiebreak as protection for "a fresh git clone (which
loses mtimes)" — the author correctly foresaw the *flat*-mtime case and
correctly handled it. What was not foreseen is the opposite case: a **live
working tree has non-flat mtimes**, and there the primary key dominates and the
date tiebreak never fires. Ordering then follows the history of git writes on
that machine, not the history of the experiment.

`_collapse_streaks` (src/lab/archive.py:482) merges a row into its predecessor
only when the two are **adjacent** and share `(milestone, verdict)` within a
day. Adjacency is decided entirely by the sort above. So the number of rows in
`pot.json.reports` is a function of the filesystem, not of the repository.

### 1.2 The negative control [reproduced]

To isolate ordering from every other variable I built a loam-shaped tree
(`git archive HEAD | tar -x` into the scratchpad — exactly the tracked files a
clone has, with flat archive mtimes) and pointed both trees at the **same empty
`LAB_HOME`**, so the `~/.lab` corpus could not contribute:

| tree | underlying runs | `reports` rows |
|---|---|---|
| win live working tree, `LAB_HOME` empty | **114** | **53** |
| clone-shaped tree, `LAB_HOME` empty | **114** | **57** |

Corpus verified identical, not merely equal in size — the full
`{(date, turn, slug)}` sets compare equal:

```
corpus identical: True | win-only: set() | clone-only: set()
```

Same 114 runs in, 53 rows out on one and 57 on the other. **The only variable
that differs between those two runs is file mtime.** That is the root cause,
demonstrated rather than argued.

Confirming the same thing from the other direction, re-sorting win's own rows by
content instead of mtime and re-collapsing:

| ordering applied to win's 120-run live corpus | rows |
|---|---|
| as shipped — `(mtime, date, turn)` | 53 |
| content order — `(date, turn)` | 59 |
| by the run's own `generated_at` stamp | 61 |

### 1.3 Why win's mtimes are scrambled and loam's are not [receipt-backed]

win, `reports/receipts/` (114 files): **25 distinct mtimes, 14 inversions**
where mtime runs *backward* as the run date advances. The oldest receipts
(June runs) all carry `2026-08-02T13:15` — a bulk rewrite — while runs from
2026-08-10 and 2026-08-11 share `2026-08-11T22:38`, and last night's PR work
touched others again. Each of those 14 inversions is a place where the public
feed's "newest-first" order is simply wrong.

loam, same directory (115 files): every receipt older than the clone carries
`2026-07-20T03:00` — one flat block — and each receipt written since carries its
own run time, which is naturally chronological. A flat block means mtime *ties*,
which means the `date_stem` tiebreak fires and loam gets true content order for
free. **loam is not correct by design; it is correct by accident of never
having had its old files rewritten.** The next bulk operation on loam (a
re-clone, a filter-branch, a checkout that touches receipts) moves loam onto
win's behaviour with no code change.

### 1.4 There are no six dropped reports [reproduced]

Row-level diff, identical 114-run corpus, clone-shaped vs win:

```
clone rows absent from win          win rows absent from clone
2026-08-08 A04 verified ×1          2026-08-08 A04 verified ×3
2026-08-08 A04 verified ×2
2026-08-08 M02 verified ×1          2026-08-08 M02 verified ×7
2026-08-08 M02 verified ×6
2026-08-07 M02 verified ×1          2026-08-07 M02 verified ×20
2026-08-07 M02 verified ×19
2026-07-28 M01 verified ×6          2026-07-28 M01 verified ×7
2026-07-22 M01 verified ×1          2026-07-21 M01 verified ×2
2026-07-21 M01 verified ×5          2026-07-19 M01 verified ×3
2026-06-26 M01 verified ×1          2026-06-26 M01 verified ×2
2026-06-25 M01 verified ×1          2026-06-24 M01 verified ×8
2026-06-24 M01 verified ×1          2026-06-16 M01 verified ×1
2026-06-23 M01 verified ×8
```

Read the `group_count` column: the run totals balance on every line. The
deficit is **4 rows** at **three merge sites**, all of them regroupings:

| site | clone | win | net |
|---|---|---|---|
| A04, 2026-08-08 | 2 rows (1 + 2 runs) | 1 row (3 runs) | −1 |
| M02, 2026-08-07/08 | 4 rows (1+6+1+19 = 27 runs) | 2 rows (7+20 = 27 runs) | −2 |
| M01, 2026-06-23…26 | 4 rows (1+1+1+8 = 11 runs) | 3 rows (2+8+1 = 11 runs) | −1 |
| M01, 2026-07-21…28 | 3 rows (12 runs) | 3 rows (12 runs) | 0 (reshaped) |

**Nothing is dropped. Nothing is hidden.** Runs that should have been separated
by an intervening run of a different milestone were made adjacent by the mtime
scramble, and the collapse — working exactly as designed — merged them.

### 1.5 Reconciling the nominal 52-vs-58

The headline "6" conflates three effects. Accounting against origin/main's
`pot.json` (58 rows / 125 underlying runs, published by loam 2026-08-11T17:31):

- **−4 rows: ordering.** The defect above. This is the whole finding.
- **−1 row: per-box `~/.lab` corpus.** `scan_runs` walks `LAB_HOME` as well as
  the repo, and each box holds dated report JSONs the other never had. loam's
  `~/.lab` contributes ~11 local-only runs (125 vs the clone's 114), worth +1
  row; win's contributes 6, worth +0. Legitimate per-box history, but it means
  the feed's run total has never been a repository fact.
- **−1 row / −2 turns: snapshot age.** origin's `pot.json` was taken at
  `turns.count = 112`; win now reads 114.

The 33 gitignored dated report JSONs sitting in win's `reports/` (18 tracked,
51 on disk) were a live suspect for masking committed receipts. **Ruled out**
— §1.2's corpus-identity check shows they contribute zero net runs.

---

## 2. Axis two — temp_c

### 2.1 win: `None` is a real breakage, fail-closed [receipt-backed]

```
curl http://localhost:8085/data.json  →  HTTP 000 (no listener)
Get-Process *LibreHardware*           →  (no process)
Startup\LibreHardwareMonitor.lnk      →  present
```

The Startup shortcut survives; the process is not running (no reboot-time
launch, or it was closed). `_cpu_temp_windows()` catches the connection error
and returns `None`, and `build_snapshot` publishes `temp_c: null`. The page
falls back to spring. Honest, and honestly broken.

### 2.2 loam: `53.0` is the WiFi card, not the CPU [receipt-backed]

loam exposes exactly **one** thermal zone:

```
/sys/class/thermal/thermal_zone0  type=iwlwifi_1  temp=42000
```

`cpu_temp_c()` (src/lab/publish.py:283) globs `/sys/class/thermal/thermal_zone*`,
looks for a zone whose `type` contains `cpu`/`x86_pkg`/`k10temp`/`tctl`/`coretemp`,
finds none, and then takes its documented fallback: *"Fall back to the first
readable zone."* That zone is the Intel WiFi adapter. Confirmed by running the
function on the box:

```
$ PYTHONPATH=src python3 -c 'from lab.publish import cpu_temp_c; print(cpu_temp_c())'
42.0                      # and /sys/class/thermal/thermal_zone0/temp == 42000
```

The committed `53.0` is that same WiFi sensor, read while an M02 campaign pass
had the machine warm. It has never been a CPU reading.

### 2.3 loam's real CPU sensor exists and is not being read [receipt-backed]

```
/sys/class/hwmon/hwmon1  name=k10temp
   temp1_input  label=Tctl   47500
   temp3_input  label=Tccd1  54500
```

`k10temp` is loaded and bound (AMD Ryzen 7 5800X). The CPU temperature is right
there. `cpu_temp_c()` simply never looks at `/sys/class/hwmon/` — it only knows
`/sys/class/thermal/`, and on this box the CPU is not registered as a thermal
zone. `lm-sensors` is not installed, which is why this was never spotted by hand.

### 2.4 Verdict on axis two

**Both boxes are broken, differently, and the field is also unattributed.**

- It is *not* "win breakage vs loam truth." loam's number is wrong at the sensor.
- It is *not* clean "per-box truth recorded by whoever published last" either —
  though that is separately true of the schema: `temp_c` is a bare scalar with
  no producer label, so even once both sensors are fixed the feed would silently
  alternate between two machines' CPUs with no way for a reader to tell which.
- The fail-open fallback is the deeper defect. `_cpu_temp_windows()` fails
  closed (returns `None` when it cannot find a CPU sensor). The Linux path fails
  open (returns *whatever thermal zone it can read*). One of those two
  behaviours is publishing a false claim to a public feed whose entire pitch is
  honest instrumentation.

---

## 3. Axis three — every other divergent key

Full key-by-key diff, win `publish.collect()` vs origin/main `pot.json`:

| key | win | origin | assessment |
|---|---|---|---|
| `schema_version`, `source`, `total`, `archive_url` | — | — | identical |
| `milestones` | 34 | 34 | **byte-identical** (compared as objects, not lengths) |
| `runs` | 51 | 51 | identical |
| `reports` | 53 | 58 | axis one |
| `temp_c` | `None` | `53.0` | axis two |
| `provenance` | `77bf50c` · python 3.11.9 · windows · torch 2.9.1 | `5a41c61` · python 3.14.4 · linux · torch 2.10.0.dev | **per-box, unattributed — same shape of defect as `temp_c`** |
| `turns.count` | 114 | 112 | snapshot age |
| `turns.last_by_machine` | `{windows-cuda: …, linux-rocm: …}` | same shape | **already correctly keyed by machine** |
| `last_run`, `updated` | — | — | timestamps, expected |
| `divergence` | absent | absent | `detect_divergence` currently returns empty on both |

Two things worth pulling out:

- **`provenance` is a third unlabelled per-box scalar.** It records the *publishing*
  box's interpreter and torch build, not the box that ran the experiment in
  `latest_report`. Lower stakes than `temp_c` (nobody reads it as a measurement)
  but the same design hole.
- **`turns.last_by_machine` is the fix, already shipped.** Schema v5 solved this
  exact problem once, correctly, for the turn cadence. The pattern to copy for
  `temp_c` and `provenance` is sitting in the same file.

---

## 4. The design question — recommendation

### The options

**(a) Single-producer rule** — only loam publishes derived feeds; win commits
receipts only. *Cost:* zero engineering; it is already the de-facto night
pattern. *Benefit:* the divergence stops appearing. *Why I do not recommend it:*
it does not fix anything. The mtime defect stays live and fires the moment
loam's old files are ever rewritten (§1.3 — loam is correct by accident, not by
design), and the resulting wrong ordering would then ship unnoticed with no
second box to contradict it. It also discards a layer the instrument
deliberately built: `turns.last_by_machine`, `group_machines`, and
`detect_divergence` all exist to make a two-box rotation legible. Retiring win
as a producer throws that away to hide a bug.

**(b) Make publish deterministic; key the per-box fields.** *Cost:* small and
well-bounded — one sort key, one sensor function, one schema field. *Benefit:*
the feed becomes a function of the repository, which is what a reproducible
instrument requires.

**(c) "It's all data" — surface both producers' views as a two-machines story.**
*Cost:* a page/feed change. *Benefit:* genuinely in the spirit of the project,
and Ben's framing points here. *Why not yet:* right now the divergence is **not
data**. It is filesystem noise. Publishing §1's 4-row delta as an honest
two-machines finding would be publishing a false claim — the two boxes do not
disagree about the science, they disagree about `stat()`. (c) becomes available,
and good, only *after* (b).

### Recommendation: **(b), in this order**

1. **Demote mtime out of the sort key.** `scan_runs` should order by the run's
   own identity — `(date, turn, generated_at)` — with mtime kept only as a
   last-resort tiebreak, or dropped. This is the root-cause fix and it is a
   prerequisite for (a) and (c) both: until the ordering is content-derived, no
   producer arrangement makes the row count meaningful. A regression test is
   cheap and obvious: build a fixture, shuffle the mtimes, assert the ledger is
   unchanged. That test fails today.
2. **Make the Linux temp path fail closed and read the right sensor.** Add
   `/sys/class/hwmon/` (`k10temp`/`coretemp`, preferring a `Tctl`/`Tdie`/
   `Package` label) ahead of the thermal-zone walk, and **delete the
   "first readable zone" fallback** — a zone that does not identify as a CPU
   must return `None`, exactly as the Windows path already does. This one change
   stops the feed publishing a WiFi temperature as CPU heat.
3. **Key `temp_c` by producer**, following the `turns.last_by_machine` precedent
   already in schema v5: `{"windows-cuda": …, "linux-rocm": …}` with the reading's
   timestamp. Same treatment for `provenance` if it is worth the schema bump.
4. **Restart LibreHardwareMonitor on win** (Startup shortcut is intact; it just
   is not running) — an ops action, not a code change.

Then (c) is unlocked and worth doing: once the two boxes' numbers are real, a
visible two-machines panel is the honest instrument telling its own story, and
`detect_divergence` finally has something true to detect.

---

## 5. What I could not verify

- **Whether the 2026-08-07 `d63c749` regression (58 → 47 rows, temp nulled) had
  this same root cause.** [hypothesis] The signature matches exactly — a
  recovery commit rewrites files, mtimes jump, ordering scrambles, rows collapse
  — and "loam's next campaign pass healed it ~6h later" is precisely what §1.3
  predicts (loam republished from its own flat-mtime tree). I did not reconstruct
  the tree at that commit to prove it.
- **The exact `53.0` reading.** I proved the *sensor* (`iwlwifi_1`) and read it
  live at 42.0. I did not capture the WiFi card at 53.0 under campaign load; that
  it was 53.0 at 2026-08-11T17:31 is inference from the code path, which admits
  no other source.
- **Whether loam's ~11 `~/.lab` local-only runs are ones win should have.** Out
  of scope for this lane; flagged because they are why the run totals differ
  (125 vs 120) independent of the ordering bug.
- **Ops note, not my lane:** loam's clone is `## main...origin/main [ahead 2]` —
  two unpushed commits, plus a receipt for `run-2026-08-12-0729-m02.json` that
  origin does not have.
