# A05 survey — what is wrong, and the plan. Brief for outside review.

**Written for someone with no context on this repo.** Everything below is
verified against committed evidence unless marked otherwise. Where I am
uncertain I say so; the places I most want a second opinion are marked
**[REVIEW]**.

---

## 1 · What the system is

`windowsill-lab` is a single-box astronomy/physics lab. The component under
audit is **A05**, a blind transit search: it downloads TESS light curves, runs a
box-least-squares period search, and grades every threshold crossing through a
disposition ladder (eclipsing binary, harmonic alias, stellar pulsation, known
planet, …). Its terminal machine state is `lead-awaiting-human-review` — the
machine is forbidden by its own vocabulary from ever emitting `planet`.

Committed record: **76 receipts**, ~13,600 graded target rows, sectors 2/3/30,
**9 lead stars**. Public surface: `pot.json` → brokenbranch.dev.

**None of what follows is a fabricated number.** An independent re-derivation of
every count, FAP, Gumbel fit, control membership and dossier hash reproduced
from the receipts' own raw evidence. Two independent runs of the checker agree.
Every finding is a **logic error** — a correct computation over the wrong
inputs, or a gate nothing invokes.

---

## 2 · What is wrong

### FIXED

**F1 — The public page advertised leads a human had refuted three weeks earlier.**
`pot.json` published `leads_awaiting_human_review: 9`. The rulings ledger
(`docs/shelf-rulings.json`, human-written) had refuted six of them on 2026-08-19/20.
One refutation reads: *"The dip is HATS-16 b (TOI 228.01, TFOPWG KP) on neighbour
TIC 77044471, 0.71 px away."* We were publicly presenting a planet published in
2015, on the wrong star, as an unexplained candidate.
Cause: `publish.hunt_block()` read the receipts only; the ledger had exactly one
non-test consumer in the whole repo. The page then **recomputed** the count from
the dispositions histogram, so fixing the publisher alone would not have reached
a reader. Fixed at both layers in `5b89987`, with an agreement test.

### SEVERE — open

**S1 — The estimator that "closed" the discovery question cannot return a
positive, and named the weakest crossing as the strongest.**
`src/lab/u_a01_attempt.py:126-131`. For zero exceedances it returns the
rule-of-three bound `3/N`; for one exceedance the point estimate `1/N`. The
bound is **three times larger than the estimate it replaces**, so the statistic
is non-monotone in signal strength:

| SDE | exceedances | expected background | verdict |
|---|---|---|---|
| 8.60 | 1 | 0.0387 | **promotable** |
| 8.65 | 0 | 0.1162 | refused |
| 50.0 | 0 | 0.1162 | refused |

Consequences: with `PROMOTE_MAX_BACKGROUND = 0.1`, no crossing at any SDE could
pass until N > 377,580 draws; at the 84,500 available the ceiling was 0.338, i.e.
3.4x the gate. **The kill verdict was arithmetically guaranteed before any data
was examined.** It also reported TIC 382028425 at SDE 8.048 as "the strongest
uncatalogued crossing" while TIC 77044472 sat in the same receipts at SDE 10.14.
**[REVIEW]** — I want a statistician on the correct estimator here, not just the
bug. My instinct is a proper upper confidence bound (Clopper–Pearson or
Poisson) that is monotone by construction, but the choice affects every
promotion decision the survey will ever make.

**S2 — Two leads sit below their own sector's measured noise floor.**
Priced against 325,000 committed scramble draws, split by sector:

| TIC | sector | SDE | null draws ≥ SDE | expected false alarms in sector |
|---|---|---|---|---|
| 49558810 | 3 | 8.0241 | **11** | 0.254 |
| 287328866 | 3 | 8.0281 | **11** | 0.254 |

0.254 is **2.5x the survey's own declared `PROMOTE_MAX_BACKGROUND = 0.1`**. Both
are exceeded eleven times by pure noise. They were never leads by the survey's
own rule. The other seven leads are **unpriced, not refuted** — the bound in S1
cannot separate SDE 9 from SDE 50.

### HIGH — open

**H1 — A gate documented as machine-checkable is checked by nothing.**
`docs/a05-receipt-schema.md` states the `sky_gates` block makes "an unrun gate is
not a passed gate" a machine-checkable claim. `check_a05`
(`src/lab/checks.py:2942-3345`) never reads it; neither does the aggregator's
gate `publish._hunt_refusal`. The block is **absent entirely from 50 of 76
receipts**, and **6 of the 9 lead stars were minted while the neighbour/blend
gate was a documented no-op** — including TIC 77044472, the one that turned out
to be a planet on the neighbouring star. A receipt with `lookup_errors: 5` is
accepted and counted today.

**H2 — Two gates, and the weaker one runs where it matters.**
`check_a05` returns `None` when a receipt's uniformity control fails ("every
graded FAP is uninterpretable"), and `scripts/a05_hunt.py:378-395` states such a
receipt "may not be published". But aggregation runs `publish._hunt_refusal`,
which is laxer. **Three uniformity-failed receipts and two budget-failed
receipts are published and counted.** `hunt-2026-08-18-s2-1000.json` is one of
the three and is the **sole source** of lead TIC 77044472.

**H3 — A lead the repo's own source documents as an eclipsing binary.**
`src/lab/a04.py:180-186` records TIC 144122210 as an EB whose secondary "missed
being auto-disposed by 0.13 sigma" under a fixed ±0.03-phase window, and
re-measures it at ~8.9 sigma in a duration-matched window. The receipt still says
`lead-awaiting-human-review`. Systematic: the field recording which window was
used first appears 2026-08-29, so **7 of 9 lead stars** were graded with an
estimator `a04.py` itself calls biased toward zero and worst on short transits.

**H4 — Our own pre-registration inherits a stale threshold.** (Ours, not the
audit's.) `docs/preregistrations/2026-09-10-u-a01-sector-96.md` justifies
SDE ≥ 8.0 with "84,500 draws, maximum 8.049", taken from `UNKNOWNS.md`. The live
null is 325,000 draws with a **sector-3 maximum of 8.6499**. A hunt running now
inherits a threshold below its own measured null maximum.

### MEDIUM — open

**M1** — One measurement filed twice. The 2026-08-15 sector-2 pair shares **29
byte-identical rows including `cache_sha256`** (two boxes hunted overlapping
slices). Neither declares `supersedes`, which the schema requires. Star-level
counts dedupe correctly; `targets_searched` is a row sum by design (194
duplicate rows).

**M2** — The page renders `targets_searched` (rows) as "stars searched blind".
13,350 published against at most 13,156 distinct stars: **≥194 overstatement**.

**M3** — TIC 212950885 passes physical admissibility only because the gate grades
the **uncorrected** depth (1.735 R_Jup graded, 2.893 reported, limit 2.5).
`crowdsap` 0.36; its own flux budget names a neighbour holding 64% of the
aperture at 0.887 px. The grading choice is defensible; the receipt does not
disclose that the lead's survival depends on it.

**M4** — CTOI cross-check fields first appear 2026-08-28; only **3 of 9** leads
carry them, while **four of the six refutations cite a CTOI match** as the
killing evidence.

### LOW — open

**L1** — TIC 234518605's BLS box depth and folded vetting depth disagree by
**22x** (survey median ratio 0.93). Window dilution explains ~2x. **Cause
undetermined.** Star is independently refuted on other grounds.

---

## 3 · Why these happened

Every item is one of two shapes, and they are the same shape:

1. **A correct computation over half the record** — F1, S1, H3, H4, M1, M2, M4.
2. **A check that exists and is never invoked** — H1, H2, and F1 again.

The system had the right answer *somewhere* in every single case. The failure was
always in the join. Not one arithmetic error was found.

Measured: of **52 gate-shaped functions** in `src/lab`, exactly **one** is
invoked only by tests (`rivals.discriminates_on`, whose own docstring says *"a
function a caller may invoke, not a gate a run must pass"*). So the dead-gate
population is small and enumerable — this is an **unswept floor, not an endemic
condition**.

---

## 4 · The plan

Sequenced so that public correctness lands first and prevention lands last.

### Phase 0 — stop publishing claims we know are wrong (hours)
- **F1** — done.
- **H4** — declare the true null maximum in the running hunt's receipt. Do **not**
  silently re-baseline the threshold mid-flight; the pre-registration is a
  commitment and its error is part of the record.
- **M2** — relabel the page: rows are "searches", stars are "stars".

### Phase 1 — retract what the evidence does not support (1–2 days)
- **S2** — re-grade TIC 49558810 and 287328866 against their own sector's null.
  On the survey's own rule they are not leads. **[REVIEW]**: retract outright,
  or re-disposition to `low-significance`? Retraction is cleaner; re-disposition
  preserves the audit trail. I lean re-disposition with a ruling in the ledger.
- **H3** — re-grade the 7 pre-2026-08-29 leads in a duration-matched secondary
  window. TIC 144122210 is already documented as an EB and should carry that
  disposition.
- **M4** — run the CTOI cross-check over all 9 leads retrospectively.
- **M3** — disclose the diluted-depth dependence in TIC 212950885's receipt.

### Phase 2 — make the gates actually gate (2–3 days)
- **H2** — `_hunt_refusal` must refuse everything `check_a05` refuses. One gate,
  or the stricter one wins. Backfill: the 5 bad receipts leave the counters.
- **H1** — give `sky_gates` a checker, or delete the schema's claim that it has
  one. A documented gate with no reader is worse than no gate, because it is
  cited as assurance.
- **M1** — add `supersedes`/`overlaps` to the 2026-08-15 pair.
- **S1** — replace `empirical_fap` with a monotone bound, re-run the U-A01
  reanalysis, and correct `UNKNOWNS.md:168`. **[REVIEW]** — the estimator choice.

### Phase 3 — make the class non-recurring (1 week)
Three linters in CI, each of which **must fail a planted positive control before
its silence is trusted**. That last clause is the whole design: the first two
versions of the dead-gate detector I wrote reported a clean floor because they
could not see the floor, and only a control caught it.

1. **Uncalled gates** — built and working. Parses the AST (a docstring mention is
   not a call), counts registry-table membership as wiring, refuses to report
   unless it rediscovers `rivals.discriminates_on`. Current finding: 1 of 52.
2. **Two producers** — for each published field, enumerate every code path that
   writes or derives it. More than one is a drift waiting to happen. This is F1,
   M1 and M2 in a single query.
3. **Consumers must not compute** — a render layer doing arithmetic over feed
   fields is a second producer in a costume. F1's second half was exactly this.

`quietfail` (this estate's own external linter, already public) encodes the
governing rule — *withhold counts from checks that fail their own positive
control* — and has never been pointed at this repo. It should be.

---

## 5 · Where I most want the second opinion

1. **The estimator in S1.** The bug is certain; the right replacement is a
   statistics judgement that will govern every future promotion.
2. **Retract vs re-disposition in S2.**
3. **Whether H1's blend-gate absence retroactively invalidates the six
   refutations** that were themselves made with the gate a no-op. I believe not —
   they were refuted on multi-sector folds and CTOI matches, not on blend — but I
   have not proved it and it is the kind of thing that should not rest on my
   belief.
4. **L1's 22x depth disagreement.** I could not determine the cause without the
   light curve. It may be nothing; it may be a defect in how one of the two
   depths is computed, which would touch every row.
