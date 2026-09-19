# Paper outline — the survey, the triage gap, and TIC 374861595

> **SUPERSEDED 2026-09-18.** A full draft written against this outline now lives
> on `claude/project-thread-alqen7` (commit `1c8a7f1`), together with
> `scripts/survey_paper_numbers.py`, which re-derives every census figure from
> `reports/hunts/*.json` and asserts agreement with `lab.publish.hunt_block`.
> **Write from the draft, not from this file.** Kept for the section plan and the
> blocker list; its §2 numbers were corrected here after the re-derivation
> contradicted three of them.

**Status: outline, not a draft.** Two of the numbers the paper turns on (the
limb-darkened radius and the Gaia-anchored R★) do not exist yet, and drafting
prose around numbers that will move is how a paper acquires sentences nobody
re-checks. Everything below is either a number already in this repo, with its
source named, or an explicit hole marked **[BLOCKED]**.

Venue decision and its reasoning: `TIC374861595-CTOI.md` §3. Short version: AJ or
PASP, because RNAAS is non-peer-reviewed and therefore cannot satisfy ExoFOP's
upload rule, and because a single-candidate note has too little new content to
survive a referee.

---

## The one-sentence claim

An automated blind search with a closed disposition vocabulary, run over 12,898
archival TESS targets, surfaced a high-significance transit signal that the SPOC
pipeline has detected 259 times across 23 sectors and that was never promoted to
TOI — and the measurement that discriminates it from the eclipsing binary it
resembles was available in the same archive the whole time.

**The paper is about the gap, not about the object.** The object is the existence
proof.

---

## Section plan

### 1 · Introduction — the triage funnel and where it leaks
The TESS promotion path runs detection → DV vetting → human triage → TOI. The
pipeline half is documented and reproducible; the human half is a judgment call
made at volume. Signals that are *high-significance but awkward* — grazing, large
inferred radius, faint late-type host — are cheap to set aside and expensive to
resolve, so they accumulate. Name the class, state that the paper exhibits one and
proposes the test that resolves the class.

*Do not write this section as a criticism of the TESS Science Office.* The claim
is about the cost structure of triage at survey volume, which is a real and
uncontroversial constraint.

### 2 · The survey
`pot.json` is the aggregator's own summary; the figures below come from
re-deriving it out of the receipts.

Re-derived 2026-09-18 with `scripts/survey_paper_numbers.py`. **Three of the
figures this outline first carried did not survive that pass** — they are struck
through below, because a referee checks the census first and the imprecise forms
had already reached two documents.

| | |
|---|---|
| target-**searches** (sum of work) | **12,898** — ~~"targets"~~ |
| distinct stars | **12,151** recorded + 551 pilot counted by a floor → **sample is 12,151–12,702 stars** |
| rows attempted / no usable product / errored | 13,524 / 1,094 / 83 |
| above threshold (SDE 8.0) | **116** |
| dispositioned | **116 / 116**, vocabulary **18 defined, 14 used** — ~~"closed 14-term vocabulary"~~ |
| known planets recovered | **9** (named in the reader's output) |
| leads minted | **7** |
| refuted by the survey's own gates | **5 counted**, of **7 refutation rulings** — ~~"5 refutations"~~ full stop. A ruling counts only while its star is a currently-minted lead; the two uncounted include TIC 77044472, where the dip was HATS-16 b on a neighbour 0.71 px away |
| leads parked / awaiting human review | 1 / 1 |
| planets claimed | **0** |
| hunt files refused by their own controls | **5** (`uniformity-failed` ×3, `budget-over-share` ×2) |

Three more things the paper must state, all from the same reader, none of them
flattering and all of them checkable:

- **The SDE 8.0 threshold sits *below* the pooled scramble null's maximum of
  8.650** (325,000 draws) — about **0.82 expected false crossings** over the
  sample. Say this before a referee finds it.
- **The graded FAP floors at (1+0)/257 = 3.891e-3** with B = 256, and **all seven
  leads sit exactly at that floor.** No lead can grade below it; the number is a
  property of the bootstrap budget, not of the leads.
- **384 of 1,565 hosts with a measured depth limit cannot see a 1 % transit** at
  any ladder period, and are barred from aggregate sensitivity claims.

*Caveat for anyone re-running the reader:* `lab.publish._shelf_states` swallows
`ImportError`, so without numpy installed it silently returns `{}` and the
refutation count degrades to 0. Install numpy before trusting a local pass.

State the claim boundary verbatim from `pot.json` — completeness of *disposition*
over the sample, **not** completeness of detection, **not** an occurrence rate,
**no** discovery. A survey that names what it does not claim is the credibility of
the rest of the paper.

The unusual, publishable methods content is the **refusal machinery**: gates that
kill the pipeline's own leads, and hunt files rejected outright by their controls
and logged as rejected rather than quietly dropped. Five refused files is a
feature to report, not an embarrassment to omit.

### 3 · TIC 374861595 — recovery and independent analysis
Host table and blind-recovery details from `TIC374861595-CTOI.md` §1–2. Be explicit
early: **SPOC found this first and published the DV reports.** What is new is (a)
the blind recovery inside a survey with a denominator and (b) §5 below.

**[BLOCKED]** The transit parameter table cannot be finalised until
`scripts/tic374861595_refit.py` has been run on real light curves. SPOC's values
stand in the meantime and are correctly attributed.

### 4 · What SPOC saw, and what happened next
The DV record: TCE 1, MES 508.6, model SNR 507.4, bootstrap FAP 0, 259 observed
transits, `suspectedEclipsingBinary: false`, odd/even statistic 1.288, centroid
0.60″ ± 2.50″ on target across 23 difference images with 23/23 good quality
metrics, ghost diagnostic core 260.5 / halo 65.2. Then: no TOI, in any sector,
since sector 27 (July 2020) — the first sector in which TESS observed this
target at all. **Not "since 2018":** the DV `sectorsObserved` bitmap has no bit
set below 27, and the 1,897-day baseline it spans is what reproduces the DV's
own expectedTransitCount of 980.

The obvious reading, stated as the likeliest and not as fact: the DV summary prints
Rp = 28.9 ± 5.2 R⊕ in red, and a 10 % V-shaped transit on a Tmag 14 M dwarf giving
a radius no planet has is precisely the shape of a grazing eclipsing binary.
Setting it aside is a defensible call on the information on the summary sheet.

### 5 · The discriminating measurement
This is the paper's result and should be its longest technical section.

The absent secondary eclipse, two independent routes: SPOC's weak-secondary search
(max MES 3.3, 602 ± 168 ppm, at phase 0.328 d rather than 0.5 P) and this lab's
undetrended per-event measurement (−159 ± 628 ppm over 34 events). Adopted 3σ
ceiling 1,105 ppm.

**Lead with the cancellation argument**, because it is the thing a referee will
test first: at b = 0.90 the eclipse is grazing, but the same overlap area enters
the primary and the secondary, so the depth ratio is the surface-brightness ratio
with no geometry left in it. The bound is therefore *independent of b and k* —
which matters exactly because b and k are the two things this fit cannot pin down.

Then the exclusion table from `scripts/tic374861595_secondary_limit.py`: stars
excluded by 10–48×, early-L marginal, cut-off T ≲ 1,800 K. Carry both bandpass
stand-ins and both stated caveats (reflected light ignored → conservative;
blackbody overestimates cool-dwarf flux → the true cut-off is looser). Do not
recover the earlier "two orders of magnitude"; it was wrong.

Conclusion of the section, and of the paper's object half: **a stellar companion is
excluded. A giant planet and a cool brown dwarf are not distinguished, and no
photometry can distinguish them.**

### 6 · What is not measured
The honest limits, at length, because the paper's credibility rests on them:
- **Radius is degenerate, not measured.** k and b trade off at b = 0.90. **[BLOCKED
  on the refit]** — the deliverable is a k–b posterior, not a point estimate.
- **R★ is catalogue.** TIC adopts Mann+2015 from M_K, so quoting TIC is not an
  independent check. **[BLOCKED on the Gaia-anchored R★.]**
- **Mass is unknown.** K ≈ 300 m/s (1 M_Jup) vs ≈ 15 km/s (50 M_Jup) at this
  period. Tmag 14.1 is reachable on a 4-m-class spectrograph. This is the paper's
  explicit ask.
- **The 3.80–3.87 d out-of-transit modulation** (0.6–1.6 % in three sectors, ≈ 2
  P_orb). Probably host rotation near a 2:1 commensurability. Report it; do not
  explain it.
- **The O−C drift** of +5.2, +3.2, +0.8 min over 73 cycles against SPOC's
  ephemeris. Almost certainly trapezoid mid-time bias rather than TTVs, and the
  refit settles it. **[BLOCKED on the refit.]** If it survives the refit it is a
  separate and more interesting paper.

### 7 · The generalisable part
The proposal, which is what makes this a methods paper rather than an anecdote:
the secondary-eclipse surface-brightness bound is cheap, needs no new observations,
is independent of the grazing degeneracy that makes these signals awkward, and is
not part of the standard promotion path. Estimate how many archival TCEs fall in
the same class — high MES, high b, inferred Rp > 2 R_Jup, faint late-type host —
and note that the test is one pass over data already on disk.

**[BLOCKED]** That population count is not in this repo and needs its own query
against the DV catalogue. Without it, §7 is a suggestion rather than a result;
with it, §7 is the reason the paper gets cited.

### 8 · Data and code availability
Every number re-derives from SHA-256-pinned receipts in `reports/hunts/`. State
where the repository will live and whether it will be public **before** writing
"reproduce this" anywhere in the paper.

---

## Ordered blockers

1. Run `scripts/tic374861595_refit.py` on real light curves → §3, §6, and the
   O−C question. *Needs a machine with MAST access.*
2. Gaia-anchored R★ with its own error budget (same script) → §6.
3. The population count for §7. Not started; the paper is publishable without it
   and much better with it.
4. Decide public-vs-private on the repository → §8.

Nothing in the survey half (§2, §4, §5) is blocked. Those three sections could be
written today.
