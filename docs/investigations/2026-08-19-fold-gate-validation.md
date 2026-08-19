# The fold gates, built and graded against TIC 287328866 (2026-08-19)

The 2026-08-18 note refuted TIC 287328866 by hand and listed three candidate
gates "not built here, Ben's call". This is the build, and the grading. Two of
the three landed as designed. The third — the odd/even depth estimator — turned
out to be a **different defect than the note diagnosed**, and the note's stated
mechanism is retired below. A fourth seam, larger than all three, surfaced while
measuring: the hunt never looks at a star twice.

Everything here is reproducible from public data: `lab.a01` pins each SPOC light
curve by URI and SHA-256, and every number below came from those files through
`lab.a04.detrend` → `lab.a05_vetting.prewhiten` → `lab.a04.blind_search`, the
same path the hunt runs.

---

## 1. What was built

| Gate | Where | Verdict it can emit |
|---|---|---|
| Doubled-period fold | `lab.a05_fold.p2_fold` | `eclipsing-binary-p2-alias` |
| Duration-matched odd/even | `lab.a05_fold.odd_even_fold` | `eclipsing-binary-odd-even` |
| Multi-sector combination | `lab.a05_fold.combine_p2_folds` | `eclipsing-binary-p2-alias` |
| CTOI catalog crosscheck | `lab.exofop` → `lab.a04.catalog_crosscheck` | `ctoi-known` |
| Companion-radius admissibility | `lab.a05_physical` | `companion-too-large` |

66 tests (`tests/test_a05_fold.py`, `tests/test_exofop.py`,
`tests/test_a05_physical.py`). Every gate emits
only REFUTATIONS: none of them can move a row toward "planet", and each one's
failure mode is a lead that stays on the shelf rather than one that leaves it
wrongly.

---

The fifth gate was not on the 08-18 list at all. It asks the question a human asks
first — **how big was the occulting body?** — from `R_c = R_★√depth`, with the
stellar radius read out of the light curve's own PRIMARY header, so it needs no
second catalog and nothing that can be down. TIC 287328866 implies 2.51 R_Jup on
its F subgiant and fires. Calibration against a known planet: WASP-18 b returns
1.27 R_Jup against a published 1.19, ~7 % high, because the depth is a box fit on
a limb-darkened transit — a systematic that runs toward refuting more candidates
than it should, stated rather than corrected.

## 2. Seam 2 — the vacuous secondary test. Confirmed, and it is the load-bearing one.

A04 looks for a secondary eclipse at phase 0.5 of the *detected* period. At a
P/2 alias both eclipses are already stacked inside the fold and there is no
phase left for a secondary to occupy, so `secondary_sigma = 0.48` on
TIC 287328866 sector 3 was not evidence of anything — it was arithmetic.

`p2_fold` folds at 2P and measures both minima through **one aperture**. The
verdict fires only when both are individually ≥ 5σ *and* their depths differ by
≥ 5σ. The 0.5 phase separation is guaranteed by construction (a detection at P
always puts its events half a fold apart at 2P) and is therefore reported as a
consistency check, never as a finding — a distinction the hand refutation did
not make.

## 3. Seam 1 — the note's dilution mechanism does not survive re-measurement

The 2026-08-18 note attributed the miss to a diluting estimator: A04 takes the
parity depth as a median over a fixed ±0.03 phase window, and a window wider
than the eclipse would drag that median toward baseline. It supported this by
comparing the vet's numbers (1.410 % / 1.496 %) against a hand fold
(2.102 % / 1.661 %) and reading the gap as a 5× dilution.

**Those two numbers came from different flux series.** The vet measures
detrended, prewhitened flux; the hand fold measured raw quality-masked PDCSAP.
Re-measured on matched (detrended) flux, sector 3 reads:

| estimator | odd | even | difference |
|---|---|---|---|
| A04 fixed window, median | 0.01410 | 0.01496 | −0.00086 |
| duration-matched support | 0.01512 | 0.01598 | −0.00086 |

The two estimators agree on the difference to the fifth decimal. **The window
was not eating the eclipse.** Most of the 2.10 % → 1.65 % gap is the 0.5 d
running-median detrend applied before the vet and not before the hand fold.

*Verdict: the dilution mechanism is retired.* It is also, separately, the answer
to the still-open "vet-depth 22× gap" question from 2026-08-16 — that comparison
should be re-run on matched flux before it is treated as an estimator defect.

### What the re-measurement did find

A04 labels epochs `floor((t - t[0]) / P)`, which places the epoch boundary at
whatever phase the first cadence happens to occupy. On sector 3 (transit phase
0.895) A04's convention and the transit-centred convention already used by
`a05_vetting.centroid_shift` **disagree about the sign** of the odd-even
difference: −0.00086 one way, +0.00104 the other. The photons cannot care where
the counting started, so a gate reading that sign is grading its own
bookkeeping. `odd_even_fold` uses the centred form.

Even centred, the parity split reads 2.70σ where the doubled fold reads higher.
Splitting by counted epoch is simply weaker than splitting by phase, so this
gate is a supporting measurement and Seam 2 carries the verdict.

## 4. Seam 3 — the CTOI table. Confirmed, and it closes the case outright.

`lab.exofop` caches ExoFOP's community-candidate table (~1.4 MB, ~3,800 stars)
and looks up by TIC with **alias-aware** period matching. On the live table:

```
TIC 287328866 → CTOI 287328866.01  P = 2.063194 d  (alias n = 2)
                CTOI 287328866.02  P = 2.079861 d  (alias n = 2)
```

Both 2019 filings match the 1.038 d detection at n = 2. A direct period match
would have missed both, which is why the matcher tests n = 1…4 in both
directions. Control: WASP-18 (TIC 100100827), a confirmed planet host, returns
zero CTOIs.

The new disposition is `ctoi-known`, and its meaning is deliberately narrow:
somebody already filed this signal, so it is not a fresh lead. It is not a
planet, not a TOI, and not a refutation.

## 5. The seam nobody listed: one sector at a time

Running `p2_fold` on all eight available sectors of TIC 287328866:

| sector | detected P (d) | SDE | depth-difference σ | fires alone? |
|---|---|---|---|---|
| 1 | 1.03815 | 7.52 | 6.63 | ✅ |
| 2 | 1.03841 | 9.00 | 6.25 | ✅ |
| 3 | 1.03824 | 8.03 | 3.51 | ❌ |
| 4 | 1.03868 | 8.83 | 3.03 | ❌ |
| 5 | 1.03880 | 8.92 | 2.87 | ❌ |
| 6 | 1.03840 | 8.16 | 0.38 | ❌ |
| 7 | 1.03869 | 8.76 | 2.20 | ❌ |
| 8 | 1.03861 | 8.62 | 2.35 | ❌ |
| **combined** | | | **9.43** | ✅ |

All eight differences carry the **same sign**; the inverse-variance combination
is 9.43σ. Six of the eight sectors, graded in isolation, would have shelved this
star as a lead — and the hunt grades exactly one sector at a time.

**This is the largest of the four findings.** No estimator improvement fixes it:
a star observed in eight sectors is currently getting eight independent weak
looks instead of one strong one, across every gate in the ladder, not just this
one. `combine_p2_folds` is the first instance; the general version (carry a
star's per-sector evidence forward and grade the star, not the sector) is a
pipeline change and is now the top item in the sky track's backlog.

Honest note on sector 3 specifically: with the corrected estimator it reads
3.51σ and does **not** fire on its own. An earlier version of this gate reported
5.0σ on that sector, and that number was wrong — see §6.

## 6. Two false-positive mechanisms found while building, and what killed them

Both were caught by negative controls on synthetic planets, not by inspection.
Both would have refuted real candidates.

**(a) Each eclipse choosing its own aperture.** The first implementation located
a support independently for each of the two minima. On a planet whose fitted
period is slightly off the true one the fold smears, the two halves of the
doubled fold smear differently, and the supports genuinely diverge — one
measured 27 cadences over 0.020 in phase, the other 83 over 0.058. The
difference between two depths measured through two different apertures is not a
depth difference. It fired `eclipsing-binary-p2-alias` on a **planted synthetic
transit** in the receipt end-to-end fixture. Fix: locate the support once on the
stacked fold at the detected period, then measure both eclipses through it.

**(b) Reading that aperture with a mean.** A cadence is either inside an eclipse
or outside it, and the two halves of the fold do not catch the ingress cadences
identically — one may hold 57 in-eclipse cadences per event where the other
holds 58. Through a mean that one-cadence asymmetry is a depth difference of
order depth/57, which on a 2 % planted transit measured **5.4σ** and fired the
gate on a planet. The same curve through a median: 1.9σ, with the injected depth
recovered to 0.1 %.

Note what (b) does *not* say. A04's estimator was never wrong for being a
median — it was wrong for taking that median over a window sized for searching.
The aperture is the fix; the median is how it is read.

## 6.5 The number §7 said was unmeasured: what happens to the shelf

Every lead standing on the shelf as of 2026-08-19 — six distinct TICs across the
committed receipts, the oldest from 08-15 — run through the new gates on every
archival sector, with the CTOI table consulted:

| TIC | detected P (d) | sectors | combined σ | CTOI | outcome |
|---|---|---|---|---|---|
| 234518605 | 5.6725 | 6 | **28.3** | .01 direct match | refuted twice over |
| 272357134 | 4.1959 | 8 | **16.4** | .01 direct match (2 CTOIs) | refuted twice over |
| 287328866 | 1.0382 | 8 | **9.8** | .01 at alias n = 2 (2 CTOIs) | refuted twice over |
| 369603748 | 3.0298 | 2 | **8.2** | none | refuted |
| 49558810 | 3.3546 | 2 | **8.6** | none | refuted |
| 77044472 | 2.6857 | 2 | 1.4 | none | **survives** |

**Five of six leave the shelf.** Three of them were already filed on ExoFOP by
somebody else — including two at a *direct* period match, which the pipeline
would have caught the moment it read the CTOI table at all, no fold gate needed.

Note what the per-sector column does not show here but does in §5: several of
these clear the bar comfortably in combination while individual sectors do not.
TIC 49558810 reads 2.6σ in sector 3 and 9.0σ in sector 30; TIC 369603748 reads
5.1σ and 6.5σ. Grading the star rather than the sector is doing real work in this
table, not just on the one object it was found on.

Raw output: `docs/investigations/2026-08-19-shelf-sweep.json` — every sector of
every lead, with the per-sector verdicts and the combination.

**Robustness:** this sweep ran on detrended-only flux with the phase re-fitted
per sector by `a04.bls_power`, while §5 ran on prewhitened flux with a full blind
search. TIC 287328866 comes out at 9.8σ here and 9.4σ there — the verdict is
stable across two different preprocessing paths, which is worth more than either
number alone.

**The survivor, and why it is not a promotion.** TIC 77044472 is not refuted by
these gates, and it is also not a candidate. Its detected depth is 6.1 % in
sector 2 and 7.6 % in sector 69 — inconsistent between sectors, and enormous. Its
CROWDSAP is **0.139**: 86 % of the aperture flux belongs to something other than
the target, so the crowding-corrected depth is ~44 %, which is not a planet on
any main-sequence host. The admissibility gate cannot say so, because the star
carries no RADIUS keyword (T = 15.8, unclassified) and an unknown radius is not a
small one. So the machine correctly declines to rule, and the row correctly stays
on the shelf carrying a loud `crowded` flag — which is the gate behaving as
designed and the shelf-exit contract's §4 "physically admissible" criterion
having nothing to work with.

That is one genuinely open lead, down from six, with the reason for the one
recorded.

## 7. What is still not measured

- **Error bars are white.** Every σ here is `σ_point / √n` from a local MAD.
  Correlated stellar variability on the eclipse timescale would widen the true
  bar, so a fire close to the 5σ line is soft. Sector 3 at 3.51σ and sector 1 at
  6.63σ are both inside the band where that matters.
- **Eight sectors, one star.** The combination in §5 is demonstrated on one
  object. It has unit tests including a pure-noise control, but no population
  study says what its false-alarm rate is across a survey slice.
- **The gate has never been run over a full hunt slice.** §6.5 runs it over the
  six leads the ladder actually minted, which is the question that mattered; what
  is still unmeasured is the *false-refutation* rate across the 5,375 stars
  searched to date — how many rows the new gates would have taken away from a
  disposition they deserved. The synthetic negative controls bound it, real
  photometry does not.
- **Prior art.** None of these gates is new; the professional pipelines have
  carried this family since Kepler. See
  `docs/assays/2026-08-19-fold-gates-and-tempering-prior-art.md` for the pinned
  citations and for the 7 % radius systematic the box-depth estimator carries.
