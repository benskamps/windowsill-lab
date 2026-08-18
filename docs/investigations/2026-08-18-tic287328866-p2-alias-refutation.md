# TIC 287328866 — the 1.038 d "lead" is an eclipsing binary at 2.0765 d (P/2 alias)

**Status: REFUTED (pending Ben's ruling — the machine cannot move a lead, per the
dossier contract).** Detected 2026-08-18, sector 3 (loam lane): P = 1.03824 d,
depth 1.44%, SDE 8.03, disposition `lead-awaiting-human-review`
(`reports/hunts/hunt-2026-08-18-s3.json`, dossier
`reports/hunts/dossiers/hunt-2026-08-18-s3-tic287328866.html`).

## The refutation, in evidence order

**1. ExoFOP already carries this star as two community candidates that are one
binary.** CTOI 287328866.01: P = 2.063194 d, depth 11,876 ppm. CTOI
287328866.02: P = 2.079861 d, depth 17,498 ppm. Both submitted by `lipponen`
on 2019-06-22 from sector 1. Two "candidates" on one star at near-identical
~2.07 d periods with *different* depths is the classic shape of an eclipsing
binary's primary and secondary eclipses filed separately. Our detection sits
exactly on the alias: 2 × 1.03824 = **2.07647 d**, between the two CTOI periods.

**2. The photons agree, in both sectors independently.** Folding the pinned
SPOC PDCSAP light curves at 2P = 2.07647 d (200 median bins, quality-masked,
via `lab.a01.read_tess_light_curve`) on loam's cached FITS:

| sector | eclipse A | eclipse B | phase sep | depth ratio |
|---|---|---|---|---|
| s3 (`tess2018263035959-s0003-...-0123-s_lc.fits`) | 2.102% | 1.661% | **0.500** | 1.27 |
| s2 (`tess2018234235059-s0002-...-0121-s_lc.fits`) | 2.120% | 1.692% | **0.500** | 1.25 |

Two minima exactly half a period apart with unequal depths, consistent across
sectors — primary and secondary eclipses. Point scatter (MAD) is 0.45–0.49%,
so the 0.44% depth *difference* is decisively resolved in the binned profiles.

**3. The host physically forbids the planet reading.** TIC v8.2: Teff 6210 K,
R★ = 2.146 R☉, log g 3.85 — an F-type **subgiant**. The true primary depth
(2.1%; 2.6% crowding-corrected at CROWDSAP 0.809) implies a companion radius
≥ 0.31 R☉ ≈ 3.1 R_Jup — stellar, not planetary. It is a subgiant + small
star binary at P = 2.0765 d.

## Why every gate missed — three seams, all actionable

- **odd/even read 3.86σ, gate fires at 5.** At the detected P/2, odd epochs are
  eclipse A and even epochs eclipse B, so the alternation IS present — but the
  vet measured depth_odd = 1.410% vs depth_even = 1.496% (diff 0.086%), while
  the 2P fold shows the true alternation is 0.44%. The vet's windowed median
  under-measures the difference ~5× — the same family as the open 8/16
  "vet-depth 22× gap" question. The signal was there; the measurement diluted
  it under the threshold.
- **The secondary test is vacuous at a P/2 alias.** secondary_sigma = 0.48 —
  necessarily: both eclipses are already inside the fold; there is no phase
  left for a secondary to appear at. A near-zero secondary at the detected
  period is *not* evidence against an EB when the detection may be P/2. The
  discriminating test is the one run here: fold at 2P and look for two minima.
- **The catalog crosscheck returned all nulls — it does not read CTOIs.**
  `catalog: {known_toi: null, known_planet: null}` on a star with two 2019
  CTOIs. The crosscheck covers TOIs and confirmed planets; community TOIs are
  invisible to it. Third lead in a week (after the two 8/16 CTOI recoveries)
  where ExoFOP's community table already had the answer.

**Candidate gates for a follow-up (not built here, Ben's call):** (a) a
double-period fold check — two minima at 0.5 separation in the 2P fold ⇒
`eclipsing-binary-p2-alias`; (b) CTOI table in the catalog crosscheck;
(c) revisit the odd/even depth estimator against fold-measured depths (the
22× / 5× dilution family).

Note the centroid block also logged a 7.1σ shift (0.073 px, verdict null) —
consistent with blend/EB, not load-bearing here.

*Method note: analysis run on loam against the receipt-pinned FITS
(sha256-verified cache files under `~/.lab/cache/a01/`); ExoFOP queried
2026-08-18. No receipt was modified; dispositions move only by human review.*
