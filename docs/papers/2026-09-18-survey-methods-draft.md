# A blind transit search with a closed disposition vocabulary: 116 threshold crossings, nine recoveries, seven leads, five refutations, no discovery

**Draft, 2026-09-18. Not submitted. Nothing in this paper has been sent anywhere.**

Target venue: *PASP* or *AJ* — a peer-reviewed journal, chosen for that property
and not for speed. The venue reasoning is in `docs/submissions/TIC374861595-CTOI.md`
§3; the short form is that Research Notes of the AAS is described by the AAS
itself as non-peer-reviewed, which disqualifies it both as a referee and as the
credential ExoFOP's community-candidate policy now requires.

This draft supersedes `docs/submissions/TIC374861595-paper-outline.md`, which
planned the same paper and is the source of §6's structure and §7's blocker
list. It is not a replacement for the CTOI package: `TIC374861595-CTOI.md`
remains the package of record for the object, and this document cites it rather
than restating it. Both, and the two scripts §6–7 name, land with PR #163;
this draft is written on top of that branch and its file references resolve
there.

Every census number below is re-derived from the committed receipts in
`reports/hunts/` by `scripts/survey_paper_numbers.py`, which reads and computes
nothing else, and which asserts its agreement with the aggregator that writes
`pot.json`. `tests/test_survey_paper_numbers.py` checks this document's census
table against that reader, cell by cell.

---

## Abstract

*(draft; the bracketed clause resolves when the refit in §7 runs)*

We describe a small archival transit search built to be checkable rather than
productive, and report the full disposition record of its first 12,898
target-searches over seven TESS sectors. Every one of the 116 detections above
the SDE = 8.0 threshold carries a machine disposition drawn from a closed
18-term vocabulary that contains no word for "planet"; the terminal machine
state is `lead-awaiting-human-review`. The search recovers nine known
transiting planets that were not designated in advance, returns zero candidates
from 1,850 phase-scrambled placebo light curves, measures a per-host injection
depth limit for 1,565 hosts and bars 384 of them from aggregate sensitivity
statements on their own measured blindness, and refuses five of its own hunt
receipts outright when their controls fail. Of seven leads the pipeline minted,
five were subsequently killed by the survey's own gates, one is parked on a
named gap, and one — TIC 374861595, an uncatalogued 10.5 % signal on a mid-M
dwarf that the SPOC pipeline has detected 259 times without promotion to TOI —
remains open. We present that object as a worked example rather than as a
result: the survey's contribution to it is an independent blind recovery inside
a sample with a denominator, and one measurement the standard promotion path
does not make, namely a surface-brightness bound from the absent secondary
eclipse that is independent of the grazing degeneracy [and a limb-darkened
reanalysis of the transit shape]. **We claim no planet.** We argue that the
useful publishable content of a small survey is its disposition record and its
refusals, and that both are cheap to produce and almost never reported.

---

## 1 · Introduction

Small archival transit searches are easy to run and hard to believe. The search
itself is a solved problem — box least squares over detrended photometry is
thirty years old and a few hundred lines — and the archive is open, so the
barrier to producing a list of candidates from TESS data is close to zero. The
barrier to producing a list anyone should act on is not.

The gap between those two is almost entirely bookkeeping, and bookkeeping is
what small surveys do not publish. A search that reports its survivors and not
its denominator cannot be distinguished from a search that reports whatever
survived a threshold chosen after looking. A search that reports "candidates"
without saying what the other detections were, and why, has published the tail
of a distribution whose body it is asking the reader to imagine. A search with
no negative control has not shown that its pipeline would decline to produce
candidates from data containing none.

This paper reports a survey built the other way round. The instrument was
designed so that its record — not its results — would be the thing worth
publishing, on the grounds that a small survey's realistic yield is zero
discoveries and that a zero-discovery survey is publishable exactly to the
extent that its zero is a measurement rather than an absence of effort.

Three design decisions carry that:

1. **A closed disposition vocabulary.** Every detection above threshold gets a
   machine verdict drawn from a fixed 18-term list (§2.4). The list contains no
   word for "planet" and no word for "discovery". A detection cannot leave the
   pipeline undispositioned, and the most a machine path can say about the best
   thing it ever found is `lead-awaiting-human-review`.
2. **A per-target null, and controls on the controls.** Each graded detection
   carries an empirical false-alarm probability from permutations of its own
   light curve (§2.2), each run carries a pre-data uniformity control on those
   FAPs, and each run carries a whole-pipeline placebo (§4).
3. **Refusal rather than repair.** A receipt whose own controls fail is refused
   at aggregation time and named in the published record, not fixed and not
   silently dropped (§3.3). Five of eighty committed receipts are in that state.

The survey has found no planets, and §5 reports in detail the five leads it
minted and then killed. We take the refutation record to be the paper's
substance. A pipeline whose gates never take anything away is
indistinguishable, from outside, from a pipeline whose gates are not wired —
and §4.4 describes the three weeks in 2026 when ours was exactly that, and how
we found out.

§6 works one object end to end. TIC 374861595 is not a discovery: SPOC found
the signal first, in 2020, and has redetected it in every 2-minute sector the
target has been observed in since. What the survey adds is a blind recovery inside a sample whose size is
known, and one measurement — a companion bound from the absent secondary
eclipse that survives the grazing degeneracy — that the promotion path does not
make and that was available in the same archive the whole time. We present it
as the survey's worked example because a methods paper whose method never meets
a hard case has not been tested.

---

## 2 · The instrument

### 2.1 Sample selection and the search

Targets are drawn from the 2-minute SPOC light curves of a single sector at a
time, ranked by a consistent hash of the TIC identifier under a fixed seed
(2026), with graded-run and prior-hunt targets excluded. The ranking is
declared in each receipt's `slice_rule` field and is a pure function of the
identifier, so a slice is reproducible from the seed alone and cannot be
reordered after seeing an outcome.

Detrending and the periodogram follow `lab.a04.blind_search`: a
frequency-uniform grid of 3,000 trial periods, box least squares at each, and a
detection statistic SDE = (max − median)/std computed over that periodogram.
The threshold is SDE ≥ 8.0, fixed across every receipt in this sample (§2.3
states what that threshold is and is not calibrated against).

### 2.2 The per-target null

The statistic being calibrated is not box power at the detected period. It is
the *maximum over the whole period grid*, because that maximum is what a blind
search reports, and a null that re-tests only the detected period would ignore
the look-elsewhere effect across 3,000 trials and understate the false-alarm
probability substantially.

Each Stage-2 target therefore gets B = 256 permutations of its own detrended
flux, each of which is re-searched over the same grid and reduced to its own
SDE by the same convention. Two permutation schemes are run:

* an **iid** shuffle, which destroys all time structure including the
  correlated residuals that survive detrending, and
* a **block** shuffle in contiguous 0.75-day blocks, which preserves
  short-range autocorrelation and returns the larger — more honest — FAP on red
  targets.

Both are stored in the receipt. **The graded FAP is the more conservative of
the two**, as the empirical bound *p* = (1 + k)/(B + 1) where *k* counts null
maxima at or above the observed SDE. A Gumbel tail fit is also recorded and is
explicitly *reported-never-graded*; a failed bulk calibration nulls that block
rather than downgrading it.

Two limits of this construction are declared rather than discovered by a
referee:

* **The null is built after detrending.** The detrending was fit to the data
  and has absorbed some genuinely random low-frequency variance, so the
  permuted copies are slightly quieter than a fresh realisation of the same
  star. Every FAP in this survey is therefore anti-conservative by construction
  at some level. The block scheme and the conservative-of-two rule are partial
  compensation, not a fix. The receipt schema carries this sentence verbatim so
  that it travels with the numbers.
* **B = 256 floors the statistic.** The smallest attainable graded FAP is
  (1 + 0)/257 = 3.9 × 10⁻³, and all seven leads in this sample sit exactly
  there. The graded FAP therefore discriminates between "worse than 1-in-257"
  and "at the floor", and no lead in this survey is distinguished from any
  other by it. This is a resolution limit, and the leads are separated by the
  vetting ladder rather than by the statistic.

### 2.3 What the threshold is priced against

Five receipts in this sample consulted a pooled scramble null of 325,000 draws
whose **maximum SDE is 8.65 — above the 8.0 threshold**. The receipts record
that fact in a field named for it (`threshold_below_null_max: true`) rather
than leaving it to be noticed. Thirteen of those 325,000 draws exceeded the
threshold, giving a per-target false-alarm probability at threshold of
≤ 6.4 × 10⁻⁵ at 95 % confidence, and therefore an expectation of roughly **0.8
false crossings across the 12,898 searches in this sample**, if that null
describes the whole sample — which it was not measured over.

So the threshold does not sit above the noise. It sits where a per-target
graded FAP and a disposition are required to interpret anything that crosses
it, which is the design. A reader should expect of order one of the 116
crossings in §3 to be noise, and should not expect the survey to be able to say
which.

The remaining 70 accepted receipts predate the pooled null and record `null`
in that field. They are not retrofitted.

### 2.4 The disposition vocabulary

The vocabulary is a single module (`lab.a05_vocab`) read by both the engine
that writes dispositions and the checker that grades receipts, deliberately
stdlib-only so the checker can import it without importing the engine whose
output it is checking. It defines 18 terms, walked in ladder order: series
gates (pulsation, harmonic alias, odd/even depth, secondary eclipse, P/2 alias,
phased brightening, low significance, insufficient coverage, period rail,
centroid shift, companion too large), then sky gates (blended known planet,
blend favours neighbour), then catalogue identification (recovery-or-known,
known-planet, TOI-known-FP, CTOI-known), then the terminal human-review state.

It contains no term `planet`. A receipt whose machine emitted one is refused
outright at aggregation, and `planets_discovered` in the published ledger is a
pinned literal zero that no code path can raise: promotion is a human act
recorded in `MILESTONES.md`, not a value computed from JSON.

That the vocabulary is one object with two readers is not a stylistic
preference. For two days in August 2026 it was two literals, the engine learned
five new honest words from the sky gates, and the checker kept the old
thirteen — so the first genuine refutation those gates produced would have
failed the checker's vocabulary gate and quarantined the entire receipt,
losing the slice and silently returning its targets to the eligible pool. The
merge was a bug fix, and the bug was that a restated contract is not a
contract.

### 2.5 The receipt

One run produces one JSON receipt in `reports/hunts/`, carrying every row it
attempted with its outcome, the SHA-256 of the cached FITS bytes it read, the
full permutation maxima for both schemes, the injection ladder and measured
depth limit of every Stage-2 host, the run's controls, and a `claim_boundary`
string that the publication path ships verbatim. The aggregator re-derives
every counter from those rows and never reads a receipt's own `counts` block
(rule 2 of the schema): a receipt that misreports its own totals is caught
rather than repeated.

---

## 3 · The census

**Table 1 — the survey record.** Every row is re-derived from the committed
receipts by `scripts/survey_paper_numbers.py`. As of the newest accepted
receipt, 2026-09-13.

| quantity | value | note |
|---|---|---|
| target-searches | 12,898 | sum over receipts of work done; **not** a count of stars |
| distinct identities | 12,151 | distinct TICs appearing in searched rows |
| pilot stars counted by a floor | 551 | schema-0 pilot; identities not individually recorded |
| rows attempted | 13,524 | |
| rows with no usable product | 1,094 | |
| rows that errored | 83 | |
| receipts accepted | 75 | |
| receipts refused | 5 | refused by their own controls; §3.3 |
| receipts superseded | 1 | extended by a later run; excluded to avoid double-counting |
| above threshold | 116 | distinct stars, SDE ≥ 8.0, newest verdict |
| dispositioned | 116 / 116 | from the closed 18-term vocabulary; 14 terms used |
| Stage-2 rows | 1,758 | targets that paid for a per-target null |
| injections run | 31,644 | |
| injections recovered | 20,538 | 64.9 % |
| ladder hosts | 1,565 | hosts with a measured per-period depth limit |
| hosts barred as insensitive | 384 | could not recover a 1 % transit at any ladder period |
| placebo scrambles | 1,850 | |
| placebo candidates | 0 | |
| known planets recovered | 9 | none designated in advance |
| leads minted | 7 | |
| leads refuted | 5 | by the survey's own gates; §5 |
| leads parked | 1 | on a named gap |
| leads awaiting review | 1 | TIC 374861595; §6 |
| planets claimed | 0 | pinned literal |

### 3.1 The denominator, stated precisely

`12,898` is a count of **target-searches**, not of stars. The aggregator sums
it per receipt on purpose — re-searching a star in a later slice really is more
work — but a survey's denominator is stars, and the two differ here. Of the
12,347 searched rows carrying identities, 12,151 are distinct; the remaining
551 belong to a pre-A05 pilot receipt that recorded a noise floor over its
sample rather than a row per star, so those identities are not individually
recoverable and may overlap the 12,151.

The honest statement is therefore: **12,898 target-searches over at least
12,151 and at most 12,702 distinct stars**, across TESS sectors 2, 3, 30, 31,
35, 42 and 96. We use the search count where the quantity is work and the
identity count where the quantity is sky, and we do not average the two.

### 3.2 The dispositions

**Table 2 — every threshold crossing, by verdict.** 116 of 116; the four
vocabulary terms not appearing here (`eclipsing-binary-p2-alias`,
`period-railed`, `blended-known-planet`, `blend-favours-neighbour`) are defined
and were not the newest verdict on any star in this sample.

| disposition | n |
|---|---|
| eclipsing-binary-odd-even | 20 |
| low-significance | 17 |
| eclipsing-binary-secondary | 16 |
| harmonic-alias | 16 |
| stellar-pulsation | 14 |
| recovery-or-known | 10 |
| lead-awaiting-human-review | 7 |
| toi-known-fp | 3 |
| known-planet | 3 |
| insufficient-coverage | 3 |
| centroid-shift | 3 |
| phased-brightening | 2 |
| ctoi-known | 1 |
| companion-too-large | 1 |

Eclipsing binaries in their two obvious presentations account for 36 of 116.
Harmonic aliases account for another 16 — the classical failure mode of a box
search, and the one that produced this survey's most instructive refutation
(§5.2).

Three crossings are `toi-known-fp`: the community had already refuted the
signal as a false positive or false alarm, so the row is neither a recovery nor
a lead. Counting them as recoveries would inflate the recovery statistic with
things nobody recovered.

### 3.3 The refused receipts

Five receipts are excluded from every counter in Table 1 and named in the
published record with their reason:

| receipt | refused because |
|---|---|
| `hunt-2026-08-14-s3.json` | uniformity control failed |
| `hunt-2026-08-16-s2.json` | over its declared compute budget share |
| `hunt-2026-08-17-s2-0026.json` | uniformity control failed |
| `hunt-2026-08-17-s2.json` | over its declared compute budget share |
| `hunt-2026-08-18-s2-1000.json` | uniformity control failed |

Refusal is at aggregation, by the same checker that grades receipts, and it is
not discretionary: a receipt the checker will not grade is not a receipt the
ledger may count. One of the five was the sole source of a lead, which left the
ledger with it (§5.4).

This gate was added in September 2026 after an audit found the aggregator
counting receipts whose own uniformity control had failed — the checker
returned "every graded FAP here is uninterpretable" and the aggregator counted
the run anyway. The five refusals above are that audit's finding, published
rather than repaired.

---

## 4 · Calibration

### 4.1 What the search recovers

Nine known transiting planets were recovered blind. None was designated in
advance; each was identified at grading time by catalogue cross-match after the
search had already reported its period.

**Table 3 — blind recoveries.**

| planet | TIC | sector | SDE | recovered P (d) | published P (d) | ΔP/P |
|---|---|---|---|---|---|---|
| HIP 65 A b | 201248411 | 2 | 14.22 | 0.9812412 | 0.980972 | +2.7 × 10⁻⁴ |
| WASP-45 b | 120610833 | 2 | 11.15 | 3.1248448 | 3.1260751 | −3.9 × 10⁻⁴ |
| WASP-96 b | 160148385 | 2 | 10.02 | 3.4287693 | 3.4252563 | +1.0 × 10⁻³ |
| HATS-34 b | 355703913 | 2 | 11.29 | 2.1048482 | — | — |
| TOI-125 b | 52368076 | 2 | 8.31 | 4.6567334 | — | — |
| WASP-119 b | 388104525 | 3 | 8.14 | 2.5000709 | 2.4997996 | +1.1 × 10⁻⁴ |
| WASP-18 b | 100100827 | 30 | 10.21 | 0.9416280 | 0.9414525 | +1.9 × 10⁻⁴ |
| WASP-53 b | 268766053 | 30 | 9.70 | 3.3085095 | 3.3098458 | −4.0 × 10⁻⁴ |
| WASP-190 b | 116156517 | 96 | 8.15 | 5.3748547 | 5.36777 | +1.3 × 10⁻³ |

Periods agree with the published values to between 1.1 × 10⁻⁴ and 1.3 × 10⁻³
fractionally, consistent with a single-sector baseline of ~27 days. Three rows
carry no published period in the receipt; their identification rests on the
catalogue match alone and the comparison is not made here rather than made
against a number the receipt does not hold.

Nine recoveries is a weak statement about completeness and we do not
strengthen it. The survey does not report an occurrence rate, a detection
efficiency curve, or a completeness fraction, because the sample was selected
by a hash rather than by any astrophysical criterion and because 384 of its
1,565 measured hosts are barred as insensitive (§4.3). What the recoveries
establish is that the pipeline end to end — detrend, search, grade, disposition
— returns real transiting planets from real archival data without being told
where to look.

One recovery is a boundary case worth stating. WASP-18 b has a genuine 399 ppm
secondary eclipse, so the series gate that kills eclipsing binaries on their
secondaries fires on it correctly. The schema resolves this by letting
catalogue identity outrank a bare secondary verdict **only for confirmed
planets** (TFOPWG KP/CP), preserving the physics verdict in
`disposition_evidence.initial_verdict` rather than erasing it. For anything not
already confirmed, the physics verdict stands. This is the one place the
pipeline consults an oracle, it is bounded to confirmed objects, and it is
recorded on the row.

### 4.2 What the search refuses to find

1,850 phase-scrambled light curves — same flux values, same cadence times, same
gaps, same noise distribution, zero phase coherence — were run through the
**full** search and vetting ladder, not merely the ranker. They produced **zero**
candidates.

This is the negative control the survey leans on hardest, because it is the one
that tests the part a periodogram null does not: a permutation FAP calibrates
the statistic, while the placebo asks whether the ladder behind the statistic
will manufacture a candidate from a curve that contains none. One would be too
many.

### 4.3 Per-host sensitivity, and hosts that are allowed to say nothing

A survey-wide positive control answers the wrong question. The predecessor
pipeline injected three boxes into one host and demanded all three back, so a
single host with unlucky photometry missing one injection declared a healthy
run failed.

This survey asks instead **how deep can this host see**. Every Stage-2 host gets
a predeclared ladder — depths 0.2 %, 0.4 %, 1.0 % × periods 2.3, 3.7, 5.1 d ×
two epochs, chosen before any hunt ran and never retuned — and a missed 0.2 %
injection is not a failure but the measurement: it degrades that host's depth
limit *d*_min and weakens the null statement the survey may make about it.

31,644 injections were run and 20,538 recovered. 1,565 hosts carry a measured
depth limit; the median limit is 0.2 % at all three ladder periods, which is
the ladder's own floor rung, so the true limit for a typical host is somewhere
below 0.2 % and this ladder cannot say where.

**384 of the 1,565 hosts — 24.5 % — cannot recover a 1 % injection at any
ladder period** and are barred from aggregate sensitivity statements entirely.
A survey that averaged those hosts in would be reporting a sensitivity its
photometry never had on a quarter of its sample.

### 4.4 The calibration of the calibrator, and the gate that was not wired

Each run routes a fixed fraction of its targets to a uniformity control, chosen
by a deterministic hash of (seed, TIC) **with no SDE filter**, so a control
member may legitimately host a real astrophysical signal and drag the KS
statistic. Filtering controls by outcome would bias the very calibration the
control exists to test; a KS statistic degraded by a real signal is
investigated, not excluded. Across 74 accepted receipts, 1,287 control members
were graded, with a maximum KS statistic of 0.343.

Absence of a verdict is not a passed gate, and the survey learned this the
expensive way. From 2026-08-20 the production hunt script called the engine
without a neighbour resolver, so the sky gates — the ones that ask whose light
this is, rather than what shape it has — were a silent no-op in the one place
production leads are minted. A receipt with no sky verdict on any row was
ambiguous between "ran and cleared everything" and "never ran", and for that
period it meant the second. The repair is a `sky_gates` block that states the
answer either way, including whether a resolver was supplied at all, so that
"an unrun gate is not a passed gate" became a machine-checkable claim instead
of a hope. A nonzero `lookup_errors` count means some lead could not be asked
the question, and a run in that state is not permitted to become a receipt.

We report this because a reader has no way to distinguish a survey whose gates
are wired from one whose gates are not, and because the class of defect — a
control that is absent rather than failing — is the one least likely to be
caught by any test that only checks outputs.

---

## 5 · The refutation record

Seven leads were minted. Five were refuted by the survey's own gates, one is
parked, one is open. Seven refutation rulings are on the record; two of them
belong to stars that are no longer minted leads, for reasons §5.4 gives, and
are therefore not among the five.

All seven leads sit at the graded-FAP floor of 3.9 × 10⁻³ (§2.2), so none of
what follows was decided by the statistic.

One point of attribution, because "the survey's own gates" could be read too
generously. These refutations were not produced by the in-line vetting ladder
that dispositions a row at hunt time — had they been, the stars would never have
reached `lead-awaiting-human-review` at all. They come from a post-hoc sweep
(2026-08-19/20) that re-ran the fold, catalogue and sky gates over every
standing lead across every sector the star was observed in, and from a second
look in a later sector. The verdicts are machine verdicts; the decision to run
the sweep, and the transcription of each ruling into the rulings file, is
human. The machine dispositions on those rows remain
`lead-awaiting-human-review`, which is why the refutation count lives in a
separate ledger rather than in the disposition table, and why §5.4's arithmetic
exists at all.

### 5.1 Refuted on the fold, across sectors rather than within one

Four leads died on the same gate: fold the candidate at 2 P and compare odd
with even eclipse depths, combined across every sector the star was observed
in rather than within the sector that produced the detection.

| TIC | combined significance | sectors | also |
|---|---|---|---|
| 234518605 | 28.3 σ | 6 | direct-period CTOI match |
| 272357134 | 16.4 σ | 8 | two CTOIs at a direct period match |
| 369603748 | 8.2 σ | 2 | — |
| 49558810 | 8.6 σ | 2 | — |

TIC 369603748 is the instructive one: its per-sector significances are 5.1 σ
and 6.5 σ, and neither would have closed it. 8.2 σ combined did. **Grading the
star rather than the sector is what refuted it**, and a survey that grades
sectors independently would still be carrying this lead.

### 5.2 Refuted on physical admissibility

TIC 287328866 reached 9.8 σ combined over eight sectors as an eclipsing binary
at a P/2 alias, and independently matched two CTOIs at alias *n* = 2. It is
also the survey's physical-admissibility exemplar: the implied companion radius
at the detected period is 2.5 R_Jup on an F subgiant, which is not a planet,
not a brown dwarf and not a small star. A signal that implies an object no one
has ever observed is evidence about the model, not about the object — and the
vocabulary has a term for it (`companion-too-large`, carried by one other
crossing in Table 2) so that the judgement is recorded as a verdict rather than
made in prose.

### 5.3 Refuted as a real planet on a different star

TIC 77044472 is the best case in the record and it is not one of the five.

The light curve was never wrong; the pipeline never asked whose light it was.
The dip is HATS-16 b — TOI 228.01, TFOPWG-dispositioned a known planet — on
neighbour TIC 77044471, 0.71 pixels away, at a direct period match. This is a
refutation of the *target*, not of the signal: a real transiting planet,
correctly detected, attributed to the wrong star.

It is the case that produced the sky gates described in §4.4, and therefore the
case that produced the discovery that those gates had not been running. A
survey that reported this lead as a candidate would have been reporting a
fifteen-year-old published planet as new, which is the specific failure that
`blended-known-planet` and `blend-favours-neighbour` now exist to catch.

### 5.4 Two rulings that do not count, and why

Two refutation rulings do not reduce the lead count, because a ruling counts
only while its star is a currently-minted lead:

* **TIC 77044472** was minted by `hunt-2026-08-18-s2-1000.json`, which was
  later refused when its uniformity control failed (§3.3). The receipt left the
  ledger and its lead left with it. The refutation above stands as science; it
  is simply not a subtraction from a lead the ledger no longer carries.
* **TIC 144122210** was dispositioned `eclipsing-binary-secondary` by a second
  look in sector 31 after a sector-30 pass had it as a lead by a margin of
  0.13 σ. The newest verdict wins, so the star is no longer a lead and the
  human ruling that had already reached the same conclusion has nothing left to
  subtract from.

We report the arithmetic because the alternative — publishing "seven leads,
seven refutations" — would be adding two numbers that describe different
things. The record carries both, and the aggregator's rule (a ruling counts
against a minted lead, and the count never goes negative) is in
`lab.publish.hunt_block`.

Until September 2026 this arithmetic was wrong in the other direction: the
published ledger read the receipts alone and reported nine leads awaiting human
review for three weeks after six of the nine had been ruled refuted, because
refutations are written by a person into a rulings file and nothing ever wrote
them back into the receipts. The arithmetic was correct throughout; the inputs
were half the record.

### 5.5 The parked lead

TIC 212950885 (sector 42, SDE 9.82) is parked on a named gap rather than
refuted or promoted. Parking is a distinct state precisely so that "we have not
finished asking" cannot be silently recorded as either "refuted" or "awaiting
review".

---

## 6 · Worked example: TIC 374861595

**This section is an exhibit, not a result. No planet is claimed.**

### 6.1 What the survey found

A blind search recovered a 1.937-day, ~8.4 % (trapezoid) signal on TIC
374861595 independently in sectors 30, 31 and 35, with depths consistent
sector to sector (8.39 / 8.35 / 8.51 % ± 0.07) and odd/even eclipse depths
equal at 0.26 σ, 0.59 σ and 1.66 σ per sector, stacking to 2.4 σ over 1,088
in-transit points. The host is a mid-M dwarf at 222 pc: T_eff 3445 ± 157 K,
R★ 0.616 ± 0.019 R☉, Tmag 14.08 (TIC v8). The disposition is
`lead-awaiting-human-review`, the terminal machine state, and it is where the
object has stayed.

### 6.2 What SPOC saw first

SPOC detected this signal as TCE 1 and has redetected it in every 2-minute
sector the target has been observed in. Its multi-sector Data Validation fit
(product label `s1-s96`, `spoc-5.0.125`) reports 259 observed transits against
980 expected, MES 508.6, model SNR 507.4, bootstrap false-alarm probability 0,
`suspectedEclipsingBinary: false`, an odd/even statistic of 1.288, and a
difference-image centroid 0.60″ ± 2.50″ from the catalogue position across 23
sectors with all 23 quality metrics good.

**The coverage is 2020 onward, not 2018.** The DV product's own
`sectorsObserved` bitmap marks 23 sectors and none of them early: the first
falls in the high 20s and the last in the mid 90s, and the run described in §7
found light curves for this target beginning at sector 27 — mid-2020, two years
after TESS began. The span between the first and last cadence of the
multi-sector fit is 1,365,963 two-minute cadences, **1,897 days ≈ 5.2 years**.
An earlier revision of this section said "every 2-minute sector since 2018" and
"seven years"; both were wrong, and both are retracted in Appendix B.

*One detail is deliberately left imprecise here.* Read one-indexed, the bitmap
names sectors 28–97; read zero-indexed it names 27–96, which is the reading
that agrees with the product's own `s1-s96` label and with the sector-27 start
the §7 run observed. The two readings differ by one sector number and agree on
everything the argument uses — 23 sectors, first in 2020, a 5.2-year baseline.
The exact list is settled by the light-curve files the §7 run already holds and
should be stated from those, not from this bitmap.

It was never promoted to TOI, in any sector, across that whole baseline.

The likeliest reading — stated as a reading and not as fact — is on the DV
summary sheet itself, which prints R_p = 28.9 ± 5.2 R⊕ in red. A 10 % V-shaped
transit on a Tmag 14 M dwarf implying a radius no planet has is the exact
signature of a grazing eclipsing binary, and setting it aside is a defensible
call on the information that sheet presents. We are not describing an error. We
are describing the cost structure of triage at survey volume, in which
high-significance but awkward signals — grazing, implausibly large, faint
late-type host — are cheap to defer and expensive to resolve, and therefore
accumulate.

### 6.3 The measurement the promotion path does not make

The discriminating test is the absent secondary eclipse, and the reason it
works here is geometric.

At b = 0.90 the eclipse is grazing, and a grazing geometry is normally where
photometric inference goes to die: the radius ratio *k* and the impact
parameter *b* trade off so hard that neither is measured. But the same overlap
area enters the primary and the secondary, so **in the depth ratio the geometry
cancels exactly** and what remains is the surface-brightness ratio. The bound
is therefore independent of *b* and *k* — independent, that is, of precisely
the two quantities this fit cannot pin down.

Two independent routes give the same null: SPOC's weak-secondary search (max
MES 3.3, 602 ± 168 ppm, at phase 0.328 d rather than 0.5 P) and this lab's
undetrended per-event measurement (−159 ± 628 ppm over 34 events). The adopted
3 σ ceiling is 1,105 ppm.

Integrating Planck spectra over the TESS band against that ceiling
(`scripts/tic374861595_secondary_limit.py`) excludes stellar companions by
factors of 10–48, leaves early-L marginal, and puts the cut-off at
T ≲ 1,800 K. Both stated caveats travel with the number: reflected light is
ignored, which makes the bound conservative, and a blackbody overestimates
cool-dwarf flux, which makes the true cut-off looser than quoted.

An earlier revision of the package claimed exclusion "by two orders of
magnitude". That was wrong, is retracted in the package, and is not recovered
here.

**Conclusion: a stellar companion is excluded. A giant planet and a cool brown
dwarf are not distinguished, and no photometry can distinguish them.** Only
radial velocities separate them — K ≈ 300 m/s for 1 M_Jup against ≈ 15 km/s for
50 M_Jup at this period — and at Tmag 14.1 that is a 4-m-class spectrograph.
This is the paper's one observational ask.

### 6.4 What is not measured

| quantity | state |
|---|---|
| radius | **bounded, not measured.** *k* and *b* trade off at b = 0.90. **[BLOCKED on the refit]** — the deliverable is a *k*–*b* posterior, not a point estimate. |
| R★ | **catalogue.** TIC adopts Mann+2015 from M_K, so quoting TIC is not an independent check. Gaia GSP-Phot's 0.80 R☉ is model-based and unreliable for M dwarfs. **[BLOCKED on a Gaia-anchored R★.]** |
| M★ | **0.600 ± 0.013 M☉, settled 2026-09-18.** Mann+2019 at this star's M_K, from coefficients now checked against the authors' own 400,000-sample MCMC posterior by `scripts/mann_coefficients_check.py` — a better reference than Table 6, which reports that posterior's medians. Those medians give 0.605; the 0.9 % difference from this repo's implementation sits inside the relation's own 1.3 % spread. **The package's "Mann+2019 mass 0.72 M☉" is retracted**: the relation reaches 0.72 only at M_K = 4.19, 0.79 mag brighter than this star — a different object, not a different rounding — and Mann+2015's own M_Ks→M★ row gives 0.637, so it is not that older relation misattributed either. No derivation for the 0.72 exists. What survives is a smaller real systematic worth carrying: Mann+2015's and Mann+2019's mass relations **disagree by 6 % at this M_K, more than either one's quoted scatter**. Mann+2019 is the one to use — dynamical masses, against Mann+2015's semi-empirical model-derived ones. |
| mass of the companion | **unknown**, and no photometry can fix it. |
| ρ★ | **in tension.** The transit shape gives 1.644 ρ☉ (from SPOC's a/R★); the TIC catalogue gives 2.571 ρ☉. A factor of 1.56, like-for-like in solar units. A 2026-09-18 revision briefly claimed the two agree to 11 % by converting one side to cgs and not the other; that claim is retracted and **the tension is real**. At fixed period it means a non-circular orbit, an R★ smaller than TIC's, or a grazing fit sitting on a low-a/R★ branch — which is the radius problem seen from a second side. |
| out-of-transit modulation | 3.80–3.87 d at 0.6–1.6 % in three sectors, ≈ 2 P_orb. Probably host rotation near a 2:1 commensurability. **Reported, not explained.** |
| O−C drift | +5.2, +3.2, +0.8 min over 73 cycles against SPOC's ephemeris, monotone. Almost certainly trapezoid mid-time bias. **[BLOCKED on the refit.]** If it survives the refit it is a different and more interesting paper. |

### 6.5 What the survey contributed, stated narrowly

Not the detection: SPOC's was first and better. Not the object's nature: that
needs a spectrograph. What a blind search with a denominator adds is that this
signal was recovered without prior knowledge inside a sample of known size with
a full disposition record, so its survival means something quantifiable rather
than meaning that somebody found it interesting. And the surface-brightness
bound in §6.3 is a measurement that was available in the same public archive
for the whole 5.2-year baseline, costs one pass over data already on disk, and
is not part of the standard promotion path.

---

## 7 · What is blocked, and what it blocks

Two things in this draft are not finishable from the archive alone. A third was
listed here on 2026-09-18 and is recorded as resolved at the end of the section
rather than deleted, on the same principle as Appendix B: a blocker list that quietly
loses entries cannot be audited.

1. **The limb-darkened refit and the Gaia-anchored R★.**
   `scripts/tic374861595_refit.py` performs a Mandel–Agol fit with Claret limb
   darkening returning (P, T₀, k, a/R★, b) **with their covariance**, so the
   grazing degeneracy appears as a posterior rather than as a point estimate,
   and implements the Mann+2015/2019 relations from published coefficients so
   R★ is derived rather than copied. Its offline self-test passes 8/8 including
   injection-recovery at SPOC's grazing geometry. **A first run on real light
   curves is under way** as of 2026-09-18 on a machine with archive access — the
   environments the rest of this work was done in could not reach MAST. Its
   numbers are **not** in this draft: §6.4's radius, R★ and O−C rows stay
   blocked and the abstract's bracketed clause stays bracketed until the
   posterior is in hand and has been read.
   Two things about that run are already worth recording, because both change
   what the finished rows can say. First, **the archive holds 24 SPOC 2-minute
   sectors for this target, not the three the search used** — sectors 27 to 97,
   378,654 cadences, BTJD 2036.3 to 3988.3, a **5.3-year baseline** carrying 289
   transit windows. The O−C row was scoped against 73 cycles; it will be
   answerable against several thousand, which is the difference between
   "probably trapezoid mid-time bias" and a measurement. Second, the run must be
   given `--backend numpy`: the optional `batman` path rebuilds its model inside
   every likelihood call and is ~90× slower here (348 ms against 3.9 ms), which
   makes the MCMC impractical rather than merely slow. The two backends agree to
   1.54 ppm in the self-test, so this costs nothing but the flag.
   *A caveat travelled with that script from its author — the Mann coefficients
   were reproduced from memory and corroborated only by reproducing TIC's own
   R★ and M★ to four decimals, which is a weak check because TIC adopts the same
   relation. That caveat is discharged as of 2026-09-18; see the resolved item
   below. It does not unblock the refit itself, only the coefficients the refit
   will use.*
2. **The population estimate for the generalisation in §8.** Not in this
   repository and not attempted here.

**Resolved, and kept on the list.** A third entry stood here: *the Mann+2019
0.72 M☉ line*, which §6.4 had flagged suspect because nobody in the loop had
read Mann+2019 Table 6. That is now done, from a stronger source than the
printed table — the authors' own 400,000-sample MCMC posterior, of which Table 6
reports the medians. `scripts/mann_coefficients_check.py` performs the
comparison and exits nonzero if it ever stops holding. Findings: Mann+2015's
three radius coefficients match the published table digit for digit; all six
Mann+2019 mass coefficients sit within 1.31 σ of the authors' posterior median,
and the zero point of 7.5 is confirmed against the authors' own `mk_mass.py`.
The 0.72 is retracted (§6.4, Appendix B). One citation consequence: **Mann+2015
Table 1 must be cited as corrected by the 2016 erratum, ApJ 819, 87** — the
journal printed Tables 1–3 with press errors, and it is the erratum's values,
not the original article's, that the relation here matches.

Two further things gate publication rather than the draft: the repository's
public-or-private status (§9), and the standing project rule that papers are
the last phase and nothing may describe a send that has not happened. **No send
has happened.**

---

## 8 · The generalisable claim

The survey-methods claim is that the disposition record and the refusals are
the publishable content of a small archival search, and that both are nearly
free. The vocabulary is one module. The placebo is the existing pipeline run on
scrambled input. The per-host ladder is the existing search run on injected
input. The refusal gate is the checker already required to grade a receipt. No
part of this required new observations, new instruments or new statistics — it
required deciding that the record was the product.

The astrophysical claim is narrower and stated as a proposal: the
secondary-eclipse surface-brightness bound of §6.3 is cheap, needs no new
observations, and is *independent of the grazing degeneracy that makes this
class of signal awkward to triage in the first place*. It is not part of the
standard promotion path. The class it would act on — high MES, high b, inferred
R_p > 2 R_Jup, faint late-type host — is enumerable from the public DV
catalogue, and applying the test to that class is one pass over data already on
disk.

**We do not estimate the size of that class here.** That count is not in this
repository and is item 3 of §7. Without it, this section is a suggestion;
with it, it is a result. We would rather ship §8 as a suggestion, labelled,
than ship a number we did not compute.

---

## 9 · Data and code availability

Every number in §§3–5 re-derives from the SHA-256-pinned receipts in
`reports/hunts/` by `scripts/survey_paper_numbers.py`, and
`tests/test_survey_paper_numbers.py` checks this document's census table
against that reader on every test run. Cached FITS bytes are pinned by
SHA-256 in each receipt for spot reproduction within the checker's numerical
tolerance; the fits are seed-pinned, not bit-for-bit across platforms.

**[BLOCKED — do not write a "reproduce this" sentence until this is
resolved.]** The repository is private as of 2026-09-18. Rule 5 of the
project's publication contract requires that any invitation to reproduce
resolve to something a reader can reach, or carry a same-sentence statement
that it is not published yet. This section will name a public repository and a
Zenodo DOI, or it will say plainly that the code is not yet public. It will not
say "available on request".

---

## Appendix A · Where each number comes from

| paper number | derived by | from |
|---|---|---|
| census, Table 1 | `scripts/survey_paper_numbers.py::census` | `reports/hunts/*.json` rows |
| disposition counts, Table 2 | same, star-level ledger, newest verdict wins | same |
| recoveries, Table 3 | same, `known_planet` rows excluding TFOPWG FP/FA | same |
| refusals, §3.3 | `lab.publish._accepted_hunt_receipts` → `lab.checks.a05_control_verdict` | same |
| lead rulings, §5 | `lab.publish._shelf_states` → `docs/shelf-rulings.json` | ruling file + receipts |
| vocabulary size | `lab.a05_vocab.MACHINE_DISPOSITIONS` | source |
| threshold, pooled null, §2.3 | receipt `pooled_null` blocks | 5 receipts |
| candidate parameters, §6 | `docs/submissions/TIC374861595-CTOI.md` §1 | SPOC DV XML, committed |
| secondary-eclipse bound, §6.3 | `scripts/tic374861595_secondary_limit.py` | SPOC DV + lab per-event fit |

## Appendix B · Corrections carried forward

Five claims made during preparation were withdrawn and are recorded rather
than overwritten, because a package that hides its retractions is not one a
referee should trust:

| withdrawn claim | status |
|---|---|
| "stellar and L-type companions excluded by two orders of magnitude" | overstated; correct answer is 10–48× for stars, early-L marginal, cut-off T ≲ 1,800 K |
| "the fit and catalogue densities agree to 11 %" | wrong; caused by converting one side to cgs and not the other. The factor-1.56 tension is real |
| "12,898 targets searched" | a count of target-searches, not of stars; §3.1 |
| "SPOC has redetected it in every 2-minute sector since 2018" / "never promoted to TOI in seven years" | wrong on both counts. The DV product's own `sectorsObserved` bitmap marks 23 sectors, none early; the §7 run found light curves beginning at sector 27. Coverage starts in 2020 and spans 1,897 days ≈ 5.2 years. Retracted 2026-09-19 against the committed DV XML; §1, §6.2, §6.5 |
| "Mann+2019 mass 0.72 M☉" | wrong, and no derivation for it ever existed. Mann+2019 gives 0.605 M☉ at this star's M_K and reaches 0.72 only at M_K = 4.19, 0.79 mag brighter. Retracted 2026-09-18 against the authors' own posterior; §6.4, §7 |
