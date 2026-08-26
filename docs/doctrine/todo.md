# The list — 2026-08-26, after A3

**Kill count today: 7 tested, 6 killed.** Every item below states what would
kill it. Items already killed are kept with their reason — a dead item is worth
more than an untested one.

---

## A · PENTIMENTO — hypothesis dead, tail alive

| # | task | gate | status |
|---|---|---|---|
| A1 | multi-version rate on aged papers | <20% ⇒ no corpus | **✅ 49.5%** (n=1200, cond-mat 62–66%, up to v8) |
| A2 | versions retrievable & diffable | if not, dead | **✅** — but **abstracts are useless**, half are byte-identical across 3 versions. Body only. |
| A3 | do papers shed numbers in revision? | additions ≈ removals ⇒ no signal | **❌ KILLED** — they net **GAIN** (485 added / 391 removed) |
| **A4** | **characterise the 29% that DO net-lose** | if the losses are references/appendices, boring | **← NEXT** |
| A5 | read the 4,880-word passage cut from 2306.16582 | if it's a duplicated derivation, boring | 30 min |
| A6 | scale n=45 → 500 to firm the 29% rate | if the rate collapses, the tail was noise | 3 hr |
| A7 | correlate loss with venue / citations / time-to-revision | no correlation ⇒ report and stop | 4 hr |

**Reframe forced by A3:** not *"science hides results"* — that's false and I can
now show it's false. It's **"a minority of papers are radically restructured
between submission and publication, and nobody has looked at what comes out."**
Smaller, weirder, more defensible.

## B · TRANSFERABLE METHODS — all blocked on C1

| # | method | from → to |
|---|---|---|
| **B1** | **transitivity violations** (A>B, B>C, C>A across papers) | logic → ML benchmarks |
| B2 | tolerance stack-up along a citation chain | engineering → cited values |
| B3 | funnel-plot asymmetry | medicine → physics |
| B4 | Benford / terminal digits | forensic accounting → fringe vs mainstream |
| B5 | control charts on one lab's output over time | manufacturing → prolific groups |
| B6 | negative space — what a field never measures | art → any |

**B1 is sharpest.** Pure logic, zero domain knowledge, and benchmark papers state
their comparisons explicitly. Nobody has done it because it needs the whole
corpus held at once.

## C · CORPUS — still the binding constraint

| # | task | status |
|---|---|---|
| C1 | a builder that yields a **clean** corpus | **❌ FAILED** — Crossref `query=` gave 0% on-topic, 0% abstracts |
| **C2** | **OpenAlex S3 snapshot** — 649M records, 330 GB gz, free, no account | **← THE UNLOCK.** 694 GB free. Ends the 429s permanently and unblocks all of B. |
| C3 | abstracts vs full text | **answered by A2: abstracts insufficient** |
| C4 | local models as extraction layer only | not started |

## D · RUNNING / OUTSTANDING

| | |
|---|---|
| scramble campaign | **312,000 / 325,000** draws — finishing today |
| PR #139 | open — the no-JS fallback fix |
| objections | **4 open** in the ledger; only an artifact closes them |
| deep queue | empty; lane correctly reported idle at 23:30 |
| P-DISCREPANCY | **still unrun** — the last untested pot, and the best of them |

## E · BEN ONLY

| | |
|---|---|
| E1 | *"every one with a live explainer"* — 28 runs, 27 rooms |
| E2 | **U-K02's 3.1 GPU-hours** — unspent, and shouldn't be spent until the susceptibility question is settled |
| E3 | U-C01 — what Borwein 2004 actually excluded |
| E4 | Telegram token |
| E5 | whether to post M14 (4 uniques/14 days, ~2 of them you) |

---

## Next two, by cheapest decisive gate

1. **A5** — read what was actually cut from 2306.16582. Thirty minutes, and it
   tells us whether the tail contains *results* or *housekeeping*. If it's
   housekeeping, A4/A6/A7 all die at once and we've saved a day.
2. **C2** — start the snapshot download. It runs unattended and unblocks all of
   Track B while we work on A.

**These two are independent and can run at the same time.**
