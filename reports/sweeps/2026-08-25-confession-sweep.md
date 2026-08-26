# Confession sweep — eight literatures, 327 papers

**2026-08-25 · Loam + Ember.** Written to disk because Telegram is not wired:
`~/.openclaw/.env` carries only a placeholder comment, no bot token, no chat id.
This sends the moment that exists.

---

## What was tested

`P-CONFESSION` is the one surviving pot from the day's hunting: papers state
their own constraints — *"prohibitive"*, *"we were limited to"*, *"CPU hours"* —
and a stated constraint is a **positive, checkable claim** we can reprice against
2026 hardware, never a negative claim about literature. It measured 59% raw and
~10% actionable on a Monte Carlo lattice corpus. The question was whether that
travels.

**Actionable** means the admission sentence also carries an extractable number.
Without one there is nothing to reprice.

## Results

| literature | papers | any admission | **actionable** |
|---|---|---|---|
| **machine learning** | 50 | **70.0%** | **6.0%** |
| Monte Carlo lattice *(baseline)* | 50 | 59.0% | **10.0%** |
| astronomy survey pipelines | 24 | 54.2% | 0.0% |
| free-energy calculation | 50 | 48.0% | **4.0%** |
| quantum teleportation | 50 | 36.0% | 0.0% |
| CO2 capture | 50 | 30.0% | 0.0% |
| perovskite solar cells | 50 | 12.0% | 0.0% |
| *free energy — fringe* **(control)** | **3** | 66.7% | 0.0% |
| *Kozyrev mirrors* **(control)** | **2** | 0.0% | 0.0% |

## Finding 1 — the tell tracks the CONSTRAINT, not the discipline

My conclusion after six literatures was *"it only works in simulation-heavy
fields, because only there is the binding constraint literally CPU time."*

**Ember killed it.** Given the six-row table cold and asked for objections, its
first was that the method might be *"biased towards fields where computational
limitations are more explicit in language, rather than a reflection of the
actual need for CPU time"* — and it named the check: **run machine learning**,
which is compute-bound and is not a simulation field.

Machine learning came back at **70% / 6%** — the highest admission rate of
anything tested.

So the conclusion is wrong and the corrected one is more useful:

> **The tell fires wherever COMPUTE is the binding constraint, in any
> discipline.** Teleportation is apparatus-bound, CO2 capture is chemistry-bound,
> solar cells are fabrication-bound — all three have admissions in prose and
> never a number, because the thing that stopped them was not a machine.

That widens the pot from "computational physics" to include **the largest
compute-bound literature in the world**, which was not on the list.

## Finding 2 — the controls measured something I did not design them to

Both fringe controls returned an **absence of literature**, not a low
confession rate. Filtered to open-access, 2010+, with a fetchable PDF, from an
index of 250M+ works:

* *overunity / zero-point energy extraction* — **3 papers**
* *Kozyrev mirrors / torsion field detectors* — **2 papers**

Against 50 available in every mainstream topic, capped only because we stopped
asking. That is a quantitative statement about those fields rather than a
rhetorical one, and it arrived free.

It also means the control **could not do its job**: the question was whether the
tell fires on prose style regardless of substance, and n=3 cannot answer it. A
proper style control needs a field with real literature and no compute
constraint — astronomy survey pipelines at **54.2% / 0.0%** turns out to be
exactly that, and it says the admission LANGUAGE is common while the extractable
NUMBER is not. **The prose is not the signal. The number is.**

## Finding 3 — the actionable rate is the whole ballgame

Raw admission rates span 12–70% and predict almost nothing. The actionable rate
separates cleanly: **10 / 6 / 4 / 0 / 0 / 0 / 0**. Every field where compute
binds carries numbers; no other field does, at any admission rate.

---

## Ember's section

Ember is a local model on this box — different weights, different corpus, no
access to my reasoning. It gets the claim and is asked to attack it. It does not
have to be right, and on the day's record it usually isn't; it has to be
**elsewhere**, and it is.

Its three objections to the six-row conclusion, verbatim in substance:

1. *"The method may be biased towards fields where computational limitations are
   more explicit and frequent in language, rather than being a reflection of the
   actual need for CPU time."* — **Check: run machine learning.**
2. *"The absence of actionable sentences in experimental or materials fields may
   be due to different linguistic patterns, rather than a genuine difference in
   the nature of computational limitations."*
3. *"The conclusion relies on an overly simplistic assumption that the presence
   or absence of extractable numbers is a reliable indicator of whether
   computational limitations are binding."*

**Objection 1 was run and it overturned the conclusion.** Objections 2 and 3 are
open and are logged in the objection ledger against this sweep. Neither has been
answered, and by the ledger's rule only an artifact can answer them — not me
agreeing that they are probably fine.

Ember is now **2-for-5** on finding things my own audits missed: the dt-
convergence gap earlier today (which was wrong, and worth having, because the
answer became a measurement instead of an assumption), and this, which was
right and changed the result.

## What this does not claim

* **327 papers is one sample, one index, one day.** OpenAlex search ranking
  chooses which 50 we see, and that is not a random draw.
* **The number-extractor is crude.** A constraint stated in a table or a figure
  caption is invisible to it, which biases every rate downward by an unknown
  amount — most plausibly in the experimental fields, where numbers live in
  tables.
* **Nothing here has been repriced.** Finding that 6% of ML papers state a
  numbered compute constraint is not the same as finding one that has expired.
  That is the next gate, and it is the expensive one.

---

*Loam, for Ben. 2026-08-25.*
