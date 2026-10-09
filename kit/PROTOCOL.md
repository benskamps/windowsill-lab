# The windowsill protocol for an agent-run transit search

Version 1, 2026-10-09. These are the rules the windowsill lab's A05 survey
already follows, numbered so others can cite and follow them. Each rule says
what to do, why, how `lab.planetkit` enforces it, and where it came from in
this repo.

The short form:

> **The machine may refute. Only a human may promote. The record is the
> product.**

---

## The rules

### 1. Write the question down first, and date it publicly

Fix the star, the sectors, the seed, the size of the null and the period grid
before opening a light curve. Commit the file.

- **Why.** A threshold or sector set chosen after looking can make almost any
  dip look significant. A commit timestamp is the cheapest proof of order
  anyone can check.
- **Kit.** `run` refuses data or sectors the preregistration did not declare.
  It also refuses a custom detection threshold, and it records the file's
  SHA-256 and first commit. An uncommitted preregistration is flagged in the
  verdict.
- **Lab.** `docs/preregistrations/`, and the §8 census preregistered on
  2026-10-08.

### 2. One threshold for every star

Report anything at SDE ≥ 8.0 over 3,000 trial periods. Report it for every
star, without tuning.

- **Why.** The lab's pooled scramble null (325,000 draws) has a maximum SDE of
  8.65, which is above the threshold. So about one crossing in the whole
  survey is expected to be noise, and the threshold is only where
  interpretation starts. Saying so is better than pretending the threshold
  clears the noise.
- **Kit.** The threshold is fixed. Preregistrations that try to change it are
  refused.
- **Lab.** Paper §2.3.

### 3. Give every signal its own null, in two schemes, and take the worse one

Permute the star's own detrended flux B = 256 times. Re-run the whole search
on each permutation. Do it twice: an iid shuffle, and a 0.75-day block
shuffle that keeps red noise. Grade on the larger false-alarm probability.

- **Why.** A blind search reports the maximum over 3,000 periods, so the null
  has to include that look-elsewhere effect. Red noise makes the iid null too
  kind.
- **Kit.** Every sector pays for the full two-scheme null (`row.fap`).
- **Lab.** `lab.a05_stats`, paper §2.2. The paper states both known limits of
  this null: it is built after detrending, and B floors the FAP at 1/257.

### 4. Measure what this star could have shown you

Inject synthetic transits into the star's own light curve (with its own
signal masked), and record the shallowest depth the search recovers.

- **Why.** "I found nothing" means nothing until you know what the search
  could have found. 384 of the lab's 1,565 measured hosts could not recover a
  1% transit at any period, so they are barred from any statement about
  absence.
- **Kit.** `row.d_min` and `row.insensitive`. The "nothing found" verdict
  quotes the floor, or says the star is too noisy to mean anything.
- **Lab.** `lab.a05_sensitivity`, paper §4.3.

### 5. Run a placebo through the whole ladder

Scramble the light curve against its own timestamps: same values, same gaps,
no phase coherence. Send the scrambles through the same search and every
vetting gate.

- **Why.** The null in rule 3 calibrates a number. The placebo tests the
  pipeline: will the gates behind that number manufacture a candidate from a
  curve that contains none? One is too many. The lab's 1,850 scrambles
  produced zero.
- **Kit.** Ten scrambles per sector by default. If any one comes back a
  candidate, the star's status is `control-failed` and the run says nothing.
- **Lab.** Paper §4.2.

### 6. Walk a fixed ladder of refutations, and record every rung

In order:

1. Pulsation spectrum and prewhitening.
2. Harmonic alias.
3. Odd/even depths.
4. Secondary eclipse.
5. Doubled-period fold.
6. Phased brightening.
7. Coverage.
8. Period rail.
9. Centroid shift.
10. Size of the occulter.
11. Catalogs: TOI, confirmed planets, and community candidates, alias-aware.

A gate that could not run says so. It is never counted as passed.

- **Why.** Eclipsing binaries alone were 36 of the lab's 116 crossings.
  "Unrun is not passed" exists because a catalog outage once nearly minted a
  lead.
- **Kit.** The same `lab.a05.process_target` and `resolve_catalog` the survey
  uses. Offline runs end `incomplete`, never `lead`.
- **Lab.** Shelf-exit contract §2. The real refutations that built each gate
  are in paper §5.

### 7. Speak only in a closed vocabulary, with no word for "planet"

Each signal gets exactly one of 18 machine words. Each star gets one of six
statuses. Neither list contains "planet". The best a machine can say is
`lead-awaiting-human-review`.

- **Why.** Words are where overclaiming happens. If the pipeline can't emit
  the word, no receipt, page or post generated from it can carry the word by
  accident.
- **Kit.** `check_receipt` refuses any word outside the lists, any
  `planets_claimed` other than the literal 0, and any plain verdict that makes
  a claim ("found a planet", "new world").
- **Lab.** `lab.a05_vocab` is one module read by both the engine and the
  checker, so the two cannot drift. Paper §2.4.

### 8. Refuse, don't repair

When a run's own controls fail, refuse the whole run and keep it in the
record with the reason. Do not fix it quietly and do not drop it.

- **Why.** A pipeline whose failures disappear can't be told apart from one
  that never fails. Five of the lab's 80 receipts are refused, and they are
  listed.
- **Kit.** `control-failed` is a published status, not an exception.
- **Lab.** Paper §3.3.

### 9. A lead is a property of a star, not of one sector

A lead needs the same period, independently, in at least two sectors. A
single-sector lead is provisional, and the receipt must say so.

- **Why.** One sector can't confirm itself. This rule can reject a real planet
  seen only once, and the lab records that as a cost. It does not hide it.
- **Kit.** `star.provisional_single_sector`, `star.persistent`.
- **Lab.** Shelf-exit contract §3 to §4, ruled 2026-08-19.

### 10. Every number in the write-up comes from the receipts

The paper, page or post is generated from the receipts or checked against
them. It is never typed by hand.

- **Why.** Agents and people both round, misremember and improve numbers. A
  test that compares the document's table cell by cell to the receipts makes
  that impossible to do quietly.
- **Kit.** The receipt carries `may_say` and `claim_boundary`, ready to quote
  verbatim.
- **Lab.** `scripts/survey_paper_numbers.py` and
  `tests/test_survey_paper_numbers.py`.

---

## Is any of this new?

This is my honest read, as of 2026-10-09. It comes from what I know of the
literature plus a web search today, not from an exhaustive review. An
astronomer should check it before anyone quotes it.

**The individual tools are standard, and you should say so.**

| Piece | Prior art |
|---|---|
| Box least-squares search | Kovács, Zucker & Mazeh 2002 |
| Injection–recovery for completeness | Kepler DR25 (Christiansen et al.) |
| Inverted and scrambled light curves as a false-alarm population | Kepler DR25 (Thompson et al. 2018; Coughlin 2017) |
| Rule-based vetting with named failure flags | the DR25 Robovetter; LEO-Vetter; TESS DV reports |
| Odd/even, secondary and centroid tests | every vetting pipeline |
| Blind analysis and preregistration | standard in particle physics, increasingly in cosmology, routine in psychology |

The lab's own paper says it outright: "No part of this required new
observations, new instruments or new statistics."

**What looks uncommon, maybe new, in a small archival search:**

1. **Governance built for an agent-written pipeline.** The closed vocabulary
   with no "planet" word, enforced by a checker that refuses receipts. The
   rule that a machine may refute but only a human may promote, with a clock
   on the promotion queue. Paper numbers machine-checked against receipts.
   Each idea has cousins: Robovetter dispositions, blinding, reproducible
   papers. I haven't seen them combined as a contract for AI-run science.
2. **Publishing the denominator and the refusals as the product.** Every
   crossing gets a disposition (116 of 116), every refused receipt is
   listed, and hosts are barred from absence claims by their own measured
   blindness. Large surveys publish denominators. Small and hobby searches
   almost never do.
3. **One astrophysical finding, the strongest candidate for something
   genuinely new** (paper §8). The secondary-eclipse surface-brightness bound
   on grazing, oversized signals around faint M dwarfs. A preregistered
   census found the class on 130 stars in SPOC's public catalog, 125 of them
   never promoted to TOI. Unpaired, the bound "excludes" a stellar companion
   on 63 of them. Paired with odd/even, it does so on only 20. A cheap test
   that is only safe in combination is a concrete, checkable result.

**Others are converging on the same idea right now.**
[klucilla/refute](https://github.com/klucilla/refute) (v0.1 locked
2026-10-07) is a falsification-first framework for exoplanet claims built
with Claude Code. [vibe-science](https://github.com/th3vib3coder/vibe-science)
is a falsification-first Claude Code plugin. Rabtsevich preregistered his
Sector 110 predictions. The lab's edge is not the idea. It is the dated
record: these rules were enforced in code, with refusals on file, from August
2026, before the crowd arrived.

## Sources inside this repo

- `docs/papers/2026-09-18-survey-methods-draft.md`: the survey, its numbers,
  its refutations.
- `docs/shelf-exit-contract.md`: how a lead enters, exits, and who decides.
- `docs/doctrine/research-doctrine.md`: why the lab works this way.
- `docs/submissions/TIC374861595-CTOI.md`: one lead worked end to end,
  including the ExoFOP rule.
- `src/lab/a05*.py`: the pipeline. `src/lab/planetkit.py`: this kit.
