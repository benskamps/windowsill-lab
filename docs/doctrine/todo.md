# The list — 2026-08-26

Ordered by **cheapest decisive gate first**, per the rule that has now paid four
times. Every item names what would kill it.

---

## A · PENTIMENTO — the boldest thing on this list

*In painting, pentimento is the ghost of what the artist painted over. arXiv
keeps every version of every paper, publicly, forever — and between v1 and the
published version, claims get softened, error bars grow, and results disappear.
**Nobody diffs them systematically.***

Why it survives every rule learned this week: it needs **no domain fluency**
(it's a text diff), it makes only **positive checkable claims** ("this sentence
is in v1 and absent from v3"), and the corpus is enormous and untouched.

| # | task | gate that kills it | cost |
|---|---|---|---|
| A1 | Sample papers **2–3 years old** (not this week's — my first test got 1% multi-version because recent submissions haven't been revised) and measure the true multi-version rate | if <20% have v2+, there is no corpus | 1 hr |
| A2 | Diff v1 → vN for 100 papers; measure what fraction have **numerical changes** (a value or error bar that moved) | if changes are only typos/formatting, dead | 2 hr |
| A3 | Classify the deltas: softened claim · widened error bar · **removed result** · added caveat | if "removed result" is ~0%, the interesting half is empty | 3 hr |
| A4 | Does the *direction* of change correlate with anything? (venue, citation count, time-to-revision) | no signal ⇒ it's noise, report and stop | 4 hr |

**A1 is the whole project's gate. One hour.**

## B · TRANSFERABLE METHODS — the actual thesis

*AI tooling's edge is carrying a method across a domain boundary it has never
crossed. Ranked by how little domain knowledge they need.*

| # | method | from | to | why nobody's done it |
|---|---|---|---|---|
| B1 | **Transitivity violations** — if paper 1 says A beats B, paper 2 says B beats C, paper 3 says C beats A, that's a *logical* inconsistency | logic | ML benchmarks, materials | needs a corpus held all at once; no one holds it |
| B2 | **Tolerance stack-up** — errors compound along a citation chain; if A±5% feeds B±10%, what is C's *real* bar? | engineering | any cited-value chain | the field treats a cited number as exact |
| B3 | **Funnel-plot asymmetry** — the canonical publication-bias test | medicine | physics, materials | physics doesn't meta-analyse itself |
| B4 | **Benford / terminal-digit** on reported values | forensic accounting | fringe vs mainstream corpora | needs a clean corpus (see C1 — my first attempt died there) |
| B5 | **Control charts (SPC)** on one lab's published values over time | manufacturing | any prolific group | nobody asks if a lab's output is "in control" |
| B6 | **Negative space** — what a field systematically *never* measures | art/composition | any | absence is invisible without the whole set |

**B1 is the sharpest**: pure logic, zero domain knowledge, and benchmark papers
state their comparisons explicitly.

## C · CORPUS INFRASTRUCTURE — currently the binding constraint

| # | task | note |
|---|---|---|
| C1 | **A corpus builder that produces a clean corpus.** Crossref `query=` returned 3,000 records at **0% on-topic and 0% abstracts** — dermatology and heparin under a cold-fusion query. It does not preserve relevance under cursor paging. | *Nothing in A or B works without this.* |
| C2 | **The OpenAlex S3 snapshot** — 649M records, 330 GB gzipped, free, no account. We have 694 GB. Kills the rate-limit problem permanently. | the real answer to "what happens at 10⁶" |
| C3 | Abstract-vs-full-text gate: what fraction of the signal is in abstracts alone? | decides whether this is a weekend or a quarter |
| C4 | Local models as the **extraction** layer, never the reasoning layer | free, parallel, and extraction is checkable |

## D · OUTSTANDING

| # | item |
|---|---|
| D1 | PR #139 — the no-JS fallback fix, open |
| D2 | Scramble campaign — ~300k/325k draws, finishing today |
| D3 | Deep queue is **empty**; the lane reported idle at 23:30, correctly |
| D4 | Objections **O002, O003, O005, O006** open in the ledger — only an artifact can close them |
| D5 | P-DISCREPANCY untested — the last unrun pot, and the best of them |

## E · BEN ONLY

| # | item |
|---|---|
| E1 | *"every one with a live explainer"* — 28 runs, 27 rooms. Live copy in your voice. |
| E2 | **U-K02's 3.1 GPU-hours** — still unspent, and shouldn't be until the susceptibility question is settled (we may be comparing linear response against published *fluctuation* exponents) |
| E3 | U-C01 — what Borwein 2004 actually excluded |
| E4 | Telegram token, if the reports should go anywhere |
| E5 | Whether to post the M14 release. Traffic is 4 uniques/14 days, ~2 of them you. |

---

## If I could only do one thing

**A1.** One hour, and it decides whether the boldest idea we have is a project
or a daydream. Everything in B is blocked behind C1 anyway.
