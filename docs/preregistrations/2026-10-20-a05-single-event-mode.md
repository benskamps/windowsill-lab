# Pre-registration and design note: cross-sector single-event search (first rung)

**Committed before the prototype was run on any real light curve.** The positive
control was chosen from the NASA Exoplanet Archive's planet table and MAST
*observation metadata* (sector start and stop times). No flux from the control
star had been opened when this file was committed. The selection rule is below
so that it can be re-run.

## Why

The survey-methods draft (`docs/papers/2026-09-18-survey-methods-draft.md`)
states the limit: the blind search runs one sector at a time over 0.5–15 d with
`a04.MIN_TRANSITS = 3`. Any transiting body whose period is longer than about
nine days shows at most two dips per sector, and usually one. The survey cannot
see it *by construction*. TIC 100796276 (18.15 d, re-checked on this branch) is
a live example: the lab's own per-sector BLS cannot report its period.
`lab.a05_mono` already finds single dips inside one sector. Nothing yet
connects dips *across* sectors into a period. This rung builds that and nothing
more.

## Scope of this rung, fixed now

In scope: a prototype (`lab.a05_events`), its placebo, its injection ladder,
one positive control, and tests. **Out of scope: any survey run.** No sample of
stars is drawn and no target outside the control (and the re-check stars on
this branch) is searched. The machine still cannot say *planet*. Its output is
a list of candidate periods per star with their evidence, and the only terminal
word available downstream stays `lead-awaiting-human-review`.

## The method

1. **Stitch.** For one TIC, take every SPOC 2-min sector
   (`a05_multisector.discover_products`, provenance SPOC). Per sector: quality
   mask, normalise, `a04.detrend` (0.5 d). The detrend biases long events low.
   That bias is stated and left uncorrected in this rung.
2. **Events.** Per sector, `a05_mono.scan` (the lab's matched-box single-event
   scan, durations 1.5–13 h, local flanks, edge guard). An *event* is a dip with
   SNR ≥ **7.0**. That is lower than `a05_mono.SNR_REPORT = 9`, because pairing
   supplies the repetition a single event lacks. The per-sector brightening
   maximum (the same scan's sign-flipped trials) is kept beside each event.
3. **Pairs into periods.** For every pair of events (i, j) in *different
   orbit segments* (segments split on gaps > 1 d), with durations within a
   factor of 2 and depths consistent at 3σ, the separation Δ yields trial
   periods P_n = Δ/n for n = 1, 2, … while P_n ≥ **P_MIN = 10 d** (below that
   the per-sector BLS already sees it). Each trial is an **alias family
   member**, kept and reported as such.
4. **Ephemeris check, per trial.** Every predicted epoch t_i + k·P_n that falls
   inside the stitched data gets a box depth (`a05_multisector.box_depth`,
   the pair's mean duration).
   - **Veto**: any covered epoch whose box excludes the pair's mean depth at
     3σ (depth + 3σ < mean depth). Data where the dip should be and is not
     kills that alias.
   - **Score**: the combined SNR √(Σ SNR_k²) over all covered epochs (vetoed
     trials score nothing), with n_events = covered epochs whose box SNR ≥ 3.
5. **Star statistic.** S_max = the highest score over all surviving trials
   with n_events ≥ 2. Each surviving trial is reported with its period, epoch,
   alias index n, the events that support it, and the covered epochs that
   constrain it.

## The placebo, fixed now (mirrors A05's epoch-scramble)

**Segment roll.** Each orbit segment's flux array is rolled by an independent
uniform random offset against its own timestamps. This keeps each segment's
noise, systematics, gaps and individual dips. It destroys the timing coherence
*between* segments, which is the only thing the pairing step measures. The full
pipeline is re-run on B = **200** rolled copies per star, seed 2026. Output:
the null distribution of S_max, and the per-star empirical FAP
(1 + k)/(B + 1), the A05 convention, where k counts rolls with S_max ≥ the
observed value.

A second, astrophysics-free null is also reported: the same pipeline on the
**inverted** series (2 − f), which pairs brightenings. Reported, not graded.

**Placebo pass line, fixed now:** on the positive control, the observed S_max
must exceed every one of the 200 rolls (FAP ≤ 1/201). On the control with its
known transits *masked*, the rolled and unrolled S_max distributions must not
differ: the unmasked-and-masked observed S_max must sit inside the central
95 % of its own rolls. If a masked, signal-free star "detects" at FAP < 0.05,
the placebo has failed and the rung stops there.

## The injection ladder, fixed now (mirrors A04/A05's injection controls)

Into the positive control's own light curves, **with its known transits masked
out** (cadences within 1.5 × T14 of every published mid-time removed):

- periods {17.3, 31.7, 58.9} d (off-grid, not near TOI-1231 b's 24.2 d or its
  aliases), each at 5 random phases (seed 2026);
- depths {4000, 2000, 1000, 500} ppm, box shape, 3.0 h;
- 3 × 5 × 4 = 60 injections.

**Recovered** = a surviving trial within 0.5 % of P_inj (*exact*), or within
0.5 % of P_inj/n or n·P_inj for n ≤ 3 (*alias*), counted separately.
**Detectable** = at least two injected events fall in data. The ladder reports
the recovery fraction per depth among the detectable injections. No pass line
is set on the ladder: it measures the instrument, it does not grade it.

## The positive control, named now

**TOI-1231 b** (TIC 447061717): P = 24.245586 d, T0 = BJD 2458685.1163,
T14 = 3.24 h, depth 0.49 %, Tmag 10.26, R★ 0.48 R☉ (NASA Exoplanet Archive
`pscomppars`, queried 2026-10-20).

Selection rule, run on metadata only: query `pscomppars` for `tran_flag = 1`,
16 < P < 60 d, Tmag < 11, depth > 0.3 %, R★ < 0.8 R☉. That returned exactly one
planet, this one. Its SPOC 2-min single-sector spans (MAST `t_min`/`t_max`)
cover one predicted epoch each in sectors 9, 10, 36, 37, 63, 90 and 99. That is
seven sectors with one event each, which is the single-event regime this rung
exists for. Whether each of those epochs lands in quality-0 data is not known
in advance. The predicted epoch can sit in a downlink gap.

**Positive-control pass line, fixed now.** The search is blind: no period
prior, no use of the published ephemeris except afterwards, for grading. It
passes if

1. the top-scoring surviving trial is within 0.5 % of 24.2456 d (*exact*), or
   the top trial is an integer alias n ≤ 3 *and* the exact period also survives
   with a score ≥ 90 % of the top one (*alias-resolved*); and
2. the observed S_max beats all 200 segment rolls.

Anything else is a **failure, reported as a failure**. The rung does not
advance to a survey pre-registration until the failure is understood.

## What this rung cannot say

- A single star's FAP is per star. No survey trial factor is priced here
  because no survey is run.
- Period aliases are *reported, not resolved*, unless coverage vetoes them.
  A star with two events and no veto data has the whole alias family alive.
  That is the honest state, and the output says so.
- Long-duration events (> 13 h) are outside the duration grid. Events deeper
  than ~10 % are not excluded by this rung. That is the job of the existing
  companion-size gate downstream.

— Claude on Portal1, 2026-10-20, for the thread session
