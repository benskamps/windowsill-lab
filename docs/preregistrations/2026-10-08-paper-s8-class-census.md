# Pre-registration — the §8 class census (survey-methods paper)

**Committed before any row of the TCE catalogues was read.** The column headers
of the SPOC multi-sector TCE file were read to learn what the catalogue carries;
no value in any row has been opened. That ordering is checkable: this file's
commit precedes the commit of `scripts/paper_s8_class_census.py` and of its
output.

## The question

§8 of `docs/papers/2026-09-18-survey-methods-draft.md` proposes that the
secondary-eclipse surface-brightness bound of §6.3 be applied to a class of
signals — high MES, high impact parameter, inferred R_p > 2 R_Jup, faint
late-type host — and says the size of that class is not in the repository
(§7 item 1). This file fixes, in advance, how that size is counted.

How many SPOC 2-minute TCEs are in that class, how many of them were never
promoted to TOI, and on how many of the unpromoted ones does SPOC's own
weak-secondary search already exclude a stellar companion by the §6.3
argument?

## The catalogue

- **Primary:** the SPOC multi-sector TCE statistics file for sectors 1–96
  (`tess2018206190142-s0001-s0096_dvr-tcestats.csv`, MAST TCE bulk downloads).
  It is the newest multi-sector product and the one that carries TIC
  374861595's DV fit, so the exhibit and the class are read off the same
  product with the same conventions.
- **Breadth check:** every single-sector and multi-sector TCE statistics file on
  the MAST bulk-download page at download time (sectors 1–107), unioned by TIC.
  A TIC is in the union class if *any* product puts one of its TCEs in the
  class. Reported, never substituted for the primary.
- **Promotion:** the ExoFOP TOI table (CSV, downloaded the same day). A TIC is
  "promoted" if it appears there under any TOI with any disposition, including
  FP and FA. The ExoFOP CTOI table is read and reported separately.
- **Brightness:** the TCE file carries no magnitude. Tmag is taken from TIC v8.2
  via the MAST catalog service, queried for class candidates only.

## The class, fixed now

A TCE is in class **C** if all five hold:

| cut | column | value | reading |
|---|---|---|---|
| high MES | `tce_max_mult_ev` | ≥ 50 | seven times the 7.1 TCE threshold |
| high b | `tce_impact` | ≥ 0.7 | grazing-leaning geometry |
| too large | `tce_prad` | ≥ 22.42 R⊕ | 2 R_Jup (1 R_Jup = 11.21 R⊕) |
| late-type host | `tce_steff` | ≤ 4,000 K | late K and M |
| faint | TIC v8.2 Tmag | ≥ 12.0 | |

TIC 374861595 (MES 508.6, b 0.90, R_p 28.9 R⊕, T_eff 3,445 K, Tmag 14.08) must
be a member. That is a positive control on the code, not a test of the cuts:
the cuts were written around the exhibit with margin on every axis, and they
are stated here so that nobody can move them after the count is seen.

## The secondary-eclipse pass, fixed now

For each unpromoted member of C:

1. **Applicable** only if SPOC's weak-secondary search found nothing
   significant: `tce_ws_maxmes` < 7.1. A member with a significant secondary is
   counted as *secondary detected* — the eclipsing-binary reading, and the test
   fires the other way.
2. **Ceiling.** σ_sec = `wst_depth` / `tce_ws_maxmes` (the file carries the
   depth and its MES, not the depth's error); 3 σ ceiling =
   max(`wst_depth`, 0) + 3 σ_sec. Where `tce_ws_maxmes` ≤ 0 or either field is
   missing, the member is *not testable* and is counted as such.
3. **Bound.** Surface-brightness ratio < ceiling / `tce_depth`; companion
   temperature cut-off by bisection on `band_ratio` from
   `scripts/tic374861595_secondary_limit.py`, reused unchanged, both response
   stand-ins, the warmer (more conservative) of the two reported.
4. **Verdict.** *Stellar companion excluded* if the cut-off is below
   **2,300 K** (the hydrogen-burning boundary for old field objects, M9/L0).
   Otherwise *not excluded*.

The weak-secondary search reports its strongest event at any phase, not at
phase 0.5, so this is a ceiling on a secondary anywhere in the orbit — the
same treatment §6.3 gives TIC 374861595.

## Uncertainty, fixed now

The count is a census of a finite catalogue, not a sample statistic, so there
is no sampling error to quote. Two sources of uncertainty are reported:

1. **Measurement.** 2,000 Monte Carlo draws perturbing `tce_prad`,
   `tce_impact` and `tce_steff` by their catalogue 1 σ errors (Gaussian,
   independent, which ignores the k–b correlation and is stated as such). MES
   and Tmag carry no error column used here and are held fixed. Class size and
   unpromoted count reported as median and 16/84 percentiles. Seed 2026.
2. **Definition.** A grid over every cut: MES {20, 50, 100}, b {0.6, 0.7, 0.8},
   R_p {1.5, 2.0, 2.5} R_Jup, T_eff {3,900, 4,000, 4,500} K, Tmag
   {11, 12, 13}. The full min–max range of the class size and of the
   unpromoted count is reported, with the primary cell named.

## What each outcome means, agreed in advance

| outcome | what §8 says |
|---|---|
| unpromoted class empty, or the exhibit alone | the class is a singleton; §8 withdraws the generalisation and says so |
| unpromoted class small (≲ 10) | §8 names the class as a short follow-up list, not a population |
| unpromoted class larger | §8 states the count as a result and the test as a cheap pass over it |

In every outcome: **no member is called a planet.** An excluded stellar
companion leaves a giant planet and a cool brown dwarf undistinguished (§6.3).
The census counts objects on which a photometric test is decisive about one
alternative; it does not count planets.

## Scope, stated now

SPOC 2-minute targets only. Full-frame-image pipelines (QLP, TESS-SPOC) are
not read, so the count is a floor on the class across TESS, not an estimate of
it.
