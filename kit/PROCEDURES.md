# Field procedures: light curve to candidate to validated to confirmed

How the professional field runs the path, where the windowsill lab (and so this kit) stands against it, and an honest answer to "is any of this new?". Researched for the kit on 2026-10-09. The lab claims no planet, and disposition words are used the way the field uses them.

Lab state read: `benskamps/windowsill-lab` at `2436d02` (src/lab/a01, a04, a05*, exofop, shelf; docs/papers/2026-09-18-survey-methods-draft.md).

---

## 0 · The short version

| question | answer |
|---|---|
| Does the lab follow the field's path? | Through **detection and flux-level vetting, yes**, and in places more strictly than amateur work usually does. It **stops before statistical validation** (no TRICERATOPS/vespa), has **no pixel-level difference imaging of its own**, and searches **2-min SPOC targets one sector at a time** rather than FFIs or stitched multi-sector light curves. |
| Is the method novel? | **The techniques mostly are not.** Per-target noise nulls, scrambled-light-curve placebos, injection/recovery, machine disposition flags, and secondary-depth physical checks all exist in the Kepler/TESS pipelines (sources in §6). **What is unusual is the governance:** a closed vocabulary with no "planet" word, receipts refused when their own controls fail, a published denominator and refutation record at hobby scale. **The most plausibly new result** is the paper's §8 census (high-MES grazing faint-M-dwarf TCEs, mostly never promoted, and the finding that the secondary-eclipse bound needs odd/even pairing). I found no equivalent in the sources read; that is not proof none exists. |
| One correction the paper needs | §6.3/§8 say the secondary-eclipse bound "is not part of the standard promotion path." SPOC/Kepler DV already turns the weak-secondary depth into **planet effective-temperature and geometric-albedo comparison statistics** (Twicken et al. 2018). The lab's version is a sharper use of the same number, not a new one. Say that. |
| How would the field's own automated tests read TIC 374861595? | LEO-Vetter (Kunimoto et al. 2025) fails a signal with R_p > 22 R⊕ (**SPOC: 28.9 R⊕**) and with V = R_p/R★ + b ≥ 1.5 (**lab refit: 0.544 + 1.053 ≈ 1.60**). TRICERATOPS FPP is described as not robust above 8 R⊕. So the object sits exactly where the field's automation says "astrophysical false positive" and where statistical validation does not apply. That matches the lab's own conclusion: only RVs separate the options. |

---

## 1 · The words, and the papers that define them

| word | what it means in the field | defined / used by |
|---|---|---|
| **TCE** (threshold crossing event) | A periodic signal a pipeline flagged above its detection threshold. Not a candidate yet. | SPOC: MES > 7.1 plus consistency checks; QLP: BLS significance > 9 (Guerrero et al. 2021) |
| **TOI** | A TCE that survived TESS team triage and vetting and was released publicly. | Guerrero et al. 2021 |
| **CTOI** | An object of interest from a community pipeline, posted on ExoFOP. Some were later promoted to TOIs after being wrongly rejected in triage. | Guerrero et al. 2021 |
| **PC** (planet candidate) | Vetting disposition: transit-like, no reason found to reject. A candidate is a claim about *absence of refutation*, not about planethood. | Guerrero et al. 2021 Table 1; Robovetter "PC" (Thompson et al. 2018) |
| **EB / V / IS** | Vetting dispositions: eclipsing binary (V-shaped), stellar variability, instrumental systematic. Excluded from the TOI catalog. | Guerrero et al. 2021 |
| **FP / FA** | TFOPWG: false positive (astrophysical, e.g. EB or blend) / false alarm (noise or systematic). | Guerrero et al. 2021 |
| **KP** | Known planet from an earlier survey. | Guerrero et al. 2021 |
| **Validated** | Statistically shown to be far more likely a planet than any false-positive scenario, without a mass. Thresholds the literature actually uses: **FPP < 1%** (Morton et al. 2016, 1,935 KOIs), **99% confidence** via multiplicity (Rowe et al. 2014, 851 planets), **FPP < 0.015 and NFPP < 10⁻³** (Giacalone et al. 2021). | Morton 2012, 2016; Lissauer et al. 2012; Rowe et al. 2014; Giacalone et al. 2021 |
| **Likely planet** | TRICERATOPS: **FPP < 0.5 and NFPP < 10⁻³**. Not validated. | Giacalone et al. 2021 |
| **Likely nearby false positive** | TRICERATOPS: **NFPP > 10⁻¹**. | Giacalone et al. 2021 |
| **Confirmed** | Mass (or minimum mass) measured, usually RVs or TTVs. The NASA Exoplanet Archive also requires mass ≤ 30 M_Jup, enough follow-up that a false positive is unlikely, and **peer-reviewed publication**. Note: TFOPWG's "CP" bin also holds validated planets without masses. | NASA Exoplanet Archive criteria page; Guerrero et al. 2021 |

Calibration point for the viral object: The viral post's TIC 4206066 FPP of 0.03–0.04 is above Giacalone's 0.015 validation line and well inside "likely planet." It is a candidate.

Two cautions the literature itself raises about validation:
- **Single-method validation is fragile.** Armstrong et al. 2021 found many disagreements between their ML classifier and vespa and urged caution about relying on any one method.
- **vespa is retired.** Its author's README now says "Current recommendation is to retire VESPA in favor of TRICERATOPS."
- **FPP is weak at low SNR and big radii.** Giacalone et al. 2021: FPP alone is not a reliable predictor of disposition when SNR < 15. LEO-Vetter paper: FPP not robust for R_p > 8 R⊕.

---

## 2 · The end-to-end path as the professional field runs it

```
pixels ─► photometry ─► detrend ─► periodic search ─► TCE
   │                                               │
   │                      triage (TEC tiers / Astronet-Triage / Robovetter / LEO-Vetter)
   │                                               │
   │                      DV report + human vetting (≥3 vetters, group vetting)
   │                                               │
   └──────── pixel checks (difference images) ─────┤
                                                   ▼
                                     TOI / CTOI  (PC)
                                                   │
                TFOP follow-up: ground photometry (on/off-target), high-res imaging,
                reconnaissance spectroscopy
                                                   │
                         ┌─────────────────────────┴───────────────┐
                 statistical validation                     mass measurement
                 (TRICERATOPS FPP/NFPP)                     (RV / TTV)
                         │                                         │
                     VALIDATED                                 CONFIRMED
                                (both need peer review to enter the archive)
```

### 2.1 Photometry and detrending

| practice | what the field does | failure mode | source |
|---|---|---|---|
| Light curves | 2-min targets: SPOC PDCSAP (systematics-corrected, crowding-corrected). FFIs: QLP for ~10M stars; TESS-SPOC FFI too. | PDCSAP can still carry residual systematics near momentum dumps and orbit gaps; crowding correction assumes the TIC is right. | Jenkins et al. 2016; Huang et al. 2020 |
| Detrender | **Time-windowed Tukey biweight** slider is the benchmarked best default. Robust Huber spline for young, very variable stars. | **Savitzky–Golay** removes 10–20% of Kepler transits, "should be avoided." **GPs** do worse than robust sliders ("no way of knowing the in-transit dip is not part of the trend"). Sliding **mean** is outlier-dragged. Sliding **median** works but is less efficient (missed 7/100 K2 planets in the benchmark). | Hippke et al. 2019 (wōtan) |
| Window length | **≈ 3 × T14.** Below ~2.2 × T14 the detrender eats transit flux; a transit is removed outright when T14 ≳ 2w. Too long and stellar variability wins the periodogram. A single fixed window for all stars recovered 87% vs. an adaptive per-star window. | Fixed windows trade short-duration sensitivity against long-duration loss. | Hippke et al. 2019 |

### 2.2 Period search and significance

| practice | what the field does | source |
|---|---|---|
| **BLS** | Box-fitting search; the standard since 2002. | Kovács, Zucker & Mazeh 2002 |
| **TLS** | Limb-darkened template instead of a box. At equal false-positive rate (SDE ≈ 7 for 1%), injection tests recovered **~93% vs ~76%** of Earth-size planets around Sun-like stars, about as fast as BLS. | Hippke & Heller 2019 |
| **SDE → FAP** | TLS white-noise table: SDE 7.0 ≈ 1% FAP, 8.3 ≈ 0.1%, 9.1 ≈ 0.01%. **Red noise makes these optimistic.** | TLS docs (FAQ) |
| **SPOC threshold** | MES > 7.1σ, at least two transits, consistency tests. | Guerrero et al. 2021; Thompson et al. 2018 (DR25 Robovetter recomputes MES on good transits, fails < 7.1) |
| **QLP threshold** | BLS significance > 9 and signal-to-pink-noise > 9; searches T < 13.5; manual vetting historically only T < 10.5, which left 1,617 faint-star TOIs to a later automated pass. | Guerrero et al. 2021; Kunimoto et al. 2022 |
| **Per-target noise null** | DV's **statistical bootstrap** computes each TCE's false-alarm probability from that target's own null single-event statistics after its transits are removed. | Twicken et al. 2018 |
| **Survey-level false alarm rate** | Kepler DR25 ran the full pipeline on **inverted** light curves and on light curves **scrambled in one-year chunks** to manufacture realistic false alarms, and measured catalog reliability from them. | Thompson et al. 2018 |
| **Completeness** | Injected transits (injTCE) through the whole pipeline. | Thompson et al. 2018 |

### 2.3 The vetting battery

| test | what it catches | field implementation | source |
|---|---|---|---|
| Odd/even depth | EB at half its true period | DV χ² on separate odd/even fits; LEO-Vetter fails at > 3σ (box, trapezoid, transit model) plus timing offsets | Twicken et al. 2018; Kunimoto et al. 2025 |
| Secondary eclipse | EB, or a self-luminous companion | DV weak-secondary test (max MES at any phase); converted to **geometric albedo** and **planet effective temperature** comparison statistics; LEO-Vetter "Significant Secondary" with exceptions for planet-like occultations | Twicken et al. 2018; Kunimoto et al. 2025 |
| Shape (U vs V) | Grazing EB | LEO-Vetter V = R_p/R★ + b ≥ 1.5 fails; TOI vetters' EB disposition is "V-shaped" | Kunimoto et al. 2025; Guerrero et al. 2021 |
| Size | Stellar companion | LEO-Vetter fails R_p > 22 R⊕; DAVE flags depths implying a stellar companion | Kunimoto et al. 2025; Kostov et al. 2019 |
| Duration vs stellar density | Wrong host, blend, eccentric orbit | Transit shape alone fixes ρ★ for circular orbits; mismatch with the star's ρ★ flags a blend or eccentricity (photoeccentric effect) | Seager & Mallén-Ornelas 2003; Dawson & Johnson 2012; LEO-Vetter unphysical-duration tests |
| Centroid / difference imaging | Light from a neighbour | DV builds in-transit, out-of-transit and **difference images** and fits a PRF centroid; "the out-of-transit image centroid is subject to crowding … the difference image centroid is not." LEO-Vetter fails Δθ > 15″. | Twicken et al. 2018; Bryson et al. 2013; Kunimoto et al. 2025 |
| Ephemeris match | Contamination from another known variable | Robovetter flag **EC**: same period and epoch as another object that is the real source | Thompson et al. 2018 |
| Nearby-star flux budget | Neighbour EB diluted into the aperture | TRICERATOPS NTP/NEB scenarios for every nearby star that could make the depth | Giacalone et al. 2021 |
| Noise / systematics tests | False alarms | LEO-Vetter: SNR ≥ 6.2, model-vs-line ΔAIC, SWEET sinusoid test, asymmetry, depth mean-to-median, per-transit SNR consistency, Chases, model-shift uniqueness, single-event domination, data-gap test, per-transit flags | Kunimoto et al. 2025 |
| Single vs multi-sector | Sector-specific systematics; long periods | SPOC multi-sector DV (e.g. s1–s96); COUNTESS stitches multi-sector light curves of uneven cadence before BLS | Guerrero et al. 2021; Hotnisky et al. 2026 |
| Machine dispositions | Throughput | Robovetter flags **NT** (not transit-like), **SS** (stellar eclipse), **CO** (centroid offset), **EC** (ephemeris match); ExoMiner deep classifier; Astronet-Triage for QLP | Thompson et al. 2018; Valizadegan et al. 2022; Guerrero et al. 2021 |
| Human vetting | Everything automation misses | TESS: each target seen by 3–5 individual vetters; any PC or undecided vote goes to group vetting by ≥ 3 vetters checking centroids, aperture-dependent depths, odd/even and secondaries | Guerrero et al. 2021 |

### 2.4 Statistical validation

| step | detail | source |
|---|---|---|
| Inputs | Light curve fold, stellar parameters, nearby stars from TIC/Gaia, and **follow-up**: high-resolution imaging contrast curves (without them, unresolved companions are allowed out to 2″), ground photometry ruling individual neighbours out | Giacalone et al. 2021 |
| Scenarios | TP, EB, EBx2P; bound companion (PTP, PEB, PEBx2P, STP, SEB, SEBx2P); unresolved fore/background (DTP, DEB, DEBx2P, BTP, BEB, BEBx2P); each resolved nearby star (NTP, NEB, NEBx2P) | Giacalone et al. 2021 |
| Effect of follow-up | TOI 465.01: AO imaging moved FPP 0.33 → 0.19 | Giacalone et al. 2021 |
| Thresholds | See §1 | — |
| Convergence | Large-N sampling (10⁶) chosen so consecutive runs agree; FPP has run-to-run scatter, report it | Giacalone et al. 2021 |
| Priors | Occurrence-rate prior dropped because it underestimated FPP | Giacalone et al. 2021 |
| Base rates to keep in mind | Kepler overall FP rate ~9.4%, **highest for giants (17.7%)** | Fressin et al. 2013 |

### 2.5 How a SPOC TCE becomes a TOI (TESS)

1. SPOC searches 2-min (and later FFI) light curves; TCE at MES > 7.1 → DV report and DV summary.
2. TESS-ExoClass sorts SPOC TCEs into tiers; tiers 1–2 go to vetting. QLP TCEs pass Astronet-Triage (T < 13.5), then cuts on brightness, radius, depth.
3. Individual vetting (3–5 vetters), then group vetting; dispositions PC / EB / V / IS / U.
4. Survivors released as TOIs on the TOI page, ExoFOP-TESS and MAST, with TFOP priorities.
5. TFOP follow-up; TFOPWG dispositions move to CP / KP / FP / FA as evidence arrives.

(Guerrero et al. 2021, full text.)

---

## 3 · Gap table: windowsill-lab against the field

Legend: ✅ does it · 🟡 partial or different · ❌ skips · ⭐ beyond the usual field practice

| field step | lab | where in the lab | note |
|---|---|---|---|
| Quality-flag masking, PDCSAP | ✅ | `a01._normalise` (QUALITY == 0, PDCSAP) | standard |
| Crowding bookkeeping | ✅ | `a05_vetting.contamination` (CROWDSAP, FLFRCSAP) | reported, not graded, by design |
| Detrender | 🟡 | `a04.detrend`: running **median**, **fixed 0.5 d** window | wōtan says biweight and ≈ 3 × T14. 0.5 d is ≥ 2.2 × T14 only for T14 ≲ 5.5 h; longer transits (long periods, larger stars) get depth suppressed. The lab already documented the effect on TIC 287328866 (2.1% → 1.65%). |
| Search | 🟡 | `a04.blind_search`: BLS, 3,000 frequency-uniform trials, 0.5 d to baseline/3 | TLS would add sensitivity to small planets. Worth checking the grid: for a 27 d sector and a 2% duty cycle, phase-coherent sampling wants a frequency step ≲ q/(3·baseline), which over ~2 c/d of range is several thousand trials; 3,000 may undersample short durations at short periods. (Back-of-envelope, not a verified literature number.) |
| Threshold | ✅ | SDE ≥ 8.0, fixed across receipts, with `threshold_below_null_max` recorded honestly | comparable to TLS's 0.1–1% white-noise FAP band; the lab measured its own pooled null (max SDE 8.65) |
| Per-target noise null | ✅ ⭐ | `a05_stats`: 256 permutations, full-grid re-search (look-elsewhere), iid and block shuffles, conservative of two graded | Same idea as DV's statistical bootstrap. The **block shuffle + conservative-of-two** rule is a red-noise-aware variant; the B = 256 floor (FAP ≥ 3.9 × 10⁻³) means it cannot rank leads. |
| Whole-pipeline placebo | ✅ | `a05_sensitivity.scramble_placebo` (1,850 curves, 0 candidates) | Prior art: DR25 inverted and scrambled light curves. Lab scrambles at cadence/block level, DR25 in one-year chunks. |
| Injection / recovery | ✅ ⭐ | `a05_sensitivity.host_sensitivity`: per-host depth limit, 384 hosts barred as insensitive | Prior art: DR25 injTCE for survey completeness. Per-host bar on aggregate null statements is a clean reporting rule. |
| Odd/even | ✅ | `a04.vet_candidate`, `a05_fold.odd_even_fold`, `a05_star` combines across sectors (VET-F2-corrected) | at parity with DV/LEO |
| Secondary eclipse | ✅ | `a04`, `a05_fold`, TIC 374861595 per-event undetrended measurement | see §4 on the "not in the promotion path" claim |
| P/2 alias | ✅ | `eclipsing-binary-p2-alias`, `a05_fold.p2_fold` | TRICERATOPS models x2P scenarios too |
| Pulsation / variability | ✅ ⭐ | `a05_vetting.prewhiten`: least-squares prewhitening on true timestamps, shape-aware so it does not eat transit harmonics | stronger than LEO's SWEET test for δ Scuti-type aliasing; same purpose |
| Shape (U/V), impact parameter | ✅ | `a05_shape.fit_transit` (Mandel–Agol, `v_ness`) | |
| Density from duration | ✅ | `a05_shape.density_ceiling` (includes the (1 + k) term) | Seager & Mallén-Ornelas; works with no catalogue radius, which is where the lab needed it |
| Size admissibility | ✅ | `a05_physical` (`companion-too-large`), graded on uncorrected depth | LEO uses 22 R⊕ |
| Centroid | 🟡 | `a05_vetting.centroid_shift`: in- minus out-of-transit **flux-weighted MOM_CENTR**, per-event bootstrap | Not a difference image. Flux-weighted centroids are crowding-biased; DV and LEO use PRF-fit difference images. For its lead the lab *reads* SPOC's DV difference-image result (0.60″ ± 2.50″, 23/23 good). |
| Own difference imaging from TPFs/FFIs | ❌ | — | biggest pixel-level gap |
| Nearby-star flux budget | ✅ | `a05_sky.flux_budget` | closest field analogue is TRICERATOPS's NFPP; the lab's version is deterministic arithmetic, not a probability |
| Neighbour known-planet check | ✅ ⭐ | `a05_sky.neighbour_crosscheck` (HATS-16 b lesson) | |
| Ephemeris matching across apertures | ✅ | `a05_sky.cluster_detections` | Robovetter EC equivalent |
| Catalog identity (TOI, confirmed, CTOI, TFOPWG FP) | ✅ | `a04.catalog_crosscheck`, `exofop` | |
| Multi-sector consistency | 🟡 | search is per-sector; `a05_star` grades the star across sectors afterwards | SPOC and COUNTESS **search** stitched light curves; per-sector search caps periods at ~9 d and misses shallow signals that only stack |
| Single transits | 🟡 | `a05_mono` (brightening-sign null) | PHT II found 73 of its 90 new candidates as single transits; this is the right instinct |
| FFI targets | ❌ | 2-min SPOC targets only | QLP covers ~10M stars; the lab's ~13K target-searches are a small, well-trodden slice |
| Stellar parameters | ✅ ⭐ | TIC 374861595: R★ from 2MASS Ks + Gaia DR3 parallax via Mann relations, RUWE checked | above typical amateur practice |
| Eccentricity | ❌ | ρ★ tension (7.7σ) left unexplained | photoeccentric fit (Dawson & Johnson 2012) is the field tool for exactly this question |
| Human vetting | 🟡 | one human (the lab's owner) is the only promoter (`shelf`, rulings file) | the field uses 3–5 independent vetters |
| Statistical validation (TRICERATOPS) | ❌ | none anywhere in `src/` | needed for any small-planet lead; not applicable to TIC 374861595 (R_p > 8 R⊕) |
| High-res imaging, ground photometry | ❌ | — | TFOP territory; an archival lab can only request it |
| RV / mass | ❌ | — | the paper's one observational ask (K ≈ 300 m/s at 1 M_Jup vs ≈ 15 km/s at 50 M_Jup) |
| Closed vocabulary, refusals, receipts | ⭐ | `a05_vocab`, `checks`, receipt SHA-256 of FITS bytes, aggregator re-derives counts | Robovetter has fixed flags too, but includes PC; the lab's "no planet word" and pinned zero are a governance choice the field does not make |

---

## 4 · Is the method novel? Evidence, claim by claim

| lab claim or feature | verdict | evidence |
|---|---|---|
| Per-target FAP from the target's own data, full-grid look-elsewhere | **Prior art** | DV statistical bootstrap (Twicken et al. 2018) |
| Whole-pipeline placebo on scrambled light curves | **Prior art** | DR25 invTCE / scrTCE (Thompson et al. 2018) |
| Injection/recovery as the sensitivity statement | **Prior art**; per-host bar is a reporting refinement | DR25 injTCE (Thompson et al. 2018) |
| Machine disposition for every TCE | **Prior art** | Robovetter NT/SS/CO/EC (Thompson et al. 2018); TESS PC/EB/V/IS/U (Guerrero et al. 2021) |
| Vocabulary with no "planet" word, `planets_discovered` pinned to 0, human-only promotion | **Unusual governance, not a technique.** Defensible and rare. | No pipeline in the sources read forbids PC as a machine output |
| Refusing receipts whose own controls fail | **Unusual reporting practice** | Not seen in the sources read |
| Publishing the denominator and every refutation | **Standard for big catalogs** (DR25 publishes every TCE's disposition), **rare for small/amateur surveys.** The crowd around TIC 4206066 publishes survivors only. | Thompson et al. 2018 vs the viral-event map |
| Secondary-eclipse surface-brightness bound, independent of b and k | **Partly prior art.** DV already converts the weak secondary to planet T_eff and albedo statistics. The lab's sharper use (band-integrated Planck exclusion of stellar companions, noting geometry cancels in the depth ratio) is a good argument, but **conditional on the signal being on the target**: under a blend the eclipsing pair's primary is not this M dwarf and the temperature conversion no longer applies. The 7.7σ ρ★ tension points at exactly that case. | Twicken et al. 2018; lab paper §6.3–6.4 |
| §8 pre-registered census of high-MES, grazing, R_p > 2 R_Jup, faint late-M TCEs; 125/130 never promoted; secondary bound safe only when paired with odd/even (63 vs 20 "exclusions") | **Most plausibly new.** A falsifiable, pre-registered claim about a class the automation discards by construction (LEO's 22 R⊕ and V ≥ 1.5 cuts). I found no equivalent census in the sources read; that is the limit of this check, not a literature-wide proof. | lab paper §8; Kunimoto et al. 2025 thresholds |
| Prewhitening that refuses to shave transit harmonics | **Careful engineering of a standard idea** | asteroseismic prewhitening is standard; LEO's SWEET is the vetter analogue |
| Flux-budget gate | **Deterministic cousin of TRICERATOPS NFPP** | Giacalone et al. 2021 |

**Honest one-liner for the kit:** the lab's contribution is *Kepler DR25 discipline (nulls, placebos, injections, full disposition record) run at hobby scale with stricter claim governance*, plus one candidate astrophysical result (§8). Calling the vetting techniques new would not survive a referee.

---

## 5 · Gaps worth closing, ranked by what they buy

1. **Statistical validation step** (TRICERATOPS, plus a second method because single-method validation is fragile). Without it the lab cannot move any small-planet lead past "candidate" even in principle.
2. **Difference-image centroids** from TPFs (2-min) or FFI cutouts, PRF-fit, replacing or backing MOM_CENTR.
3. **Biweight detrending with a duration-scaled window** (≈ 3 × T14 per trial duration, or iterate on the best duration), and an A/B on the receipts' injection ladder.
4. **TLS as a second search** on the same light curves; report both SDEs.
5. **Multi-sector stitched search** for periods beyond ~9 d (COUNTESS shows the recipe on SPOC light curves).
6. **Photoeccentric fit** for TIC 374861595's ρ★ tension before calling a blend the leading reading.
7. **Cross-check with LEO-Vetter** on every lead: it is public, TESS-native, and gives a field-standard second opinion the paper can cite.
8. **FFIs** (QLP or TESS-SPOC FFI light curves) if the lab wants to search where the crowd is not already standing.

---

## 6 · Sources (each URL fetched 2026-10-09)

"Read" says what I actually read: abstract page, or full text.

| ref | URL | read |
|---|---|---|
| Kovács, Zucker & Mazeh 2002, A&A, BLS (doi:10.1051/0004-6361:20020802) | https://arxiv.org/abs/astro-ph/0206099 | abstract |
| Seager & Mallén-Ornelas 2003, ApJ (doi:10.1086/346105) | https://arxiv.org/abs/astro-ph/0206228 | abstract |
| Jenkins et al. 2016, SPIE, The TESS Science Processing Operations Center | https://ntrs.nasa.gov/citations/20160012677 | record |
| Twicken et al. 2018, PASP, Kepler Data Validation I (doi:10.1088/1538-3873/aab694) | https://arxiv.org/abs/1803.04526 | full text (first 100K chars) |
| Li et al. 2019, PASP, Kepler Data Validation II (doi:10.1088/1538-3873/aaf44d) | https://arxiv.org/abs/1812.00103 | abstract |
| Thompson et al. 2018, ApJS, DR25 Robovetter (doi:10.3847/1538-4365/aab4f9) | https://arxiv.org/abs/1710.06758 | full text |
| Coughlin et al. 2016, ApJS, DR24 Robovetter (doi:10.3847/0067-0049/224/1/12) | https://arxiv.org/abs/1512.06149 | abstract |
| Bryson et al. 2013, PASP, background false positives (doi:10.1086/671767) | https://arxiv.org/abs/1303.0052 | abstract |
| Guerrero et al. 2021, ApJS, TOI catalog (doi:10.3847/1538-4365/abefe1) | https://arxiv.org/abs/2103.12538 | full text (first 100K chars) |
| Huang et al. 2020, RNAAS, QLP photometry of 10M stars | https://arxiv.org/abs/2011.06459 | abstract |
| Kunimoto et al. 2022, ApJS, TESS Faint Star Search (doi:10.3847/1538-4365/ac5688) | https://arxiv.org/abs/2112.02176 | abstract |
| Kunimoto et al. 2025, LEO-Vetter | https://arxiv.org/abs/2509.10619 (full: https://arxiv.org/html/2509.10619v1) | full text |
| Hotnisky et al. 2026, COUNTESS I | https://arxiv.org/abs/2606.13789 | abstract |
| Hippke & Heller 2019, A&A, TLS (doi:10.1051/0004-6361/201834672) | https://arxiv.org/abs/1901.02015 | abstract |
| TLS FAQ (SDE → FAP table) | https://transitleastsquares.readthedocs.io/en/latest/FAQ.html | page |
| Hippke et al. 2019, AJ, wōtan (doi:10.3847/1538-3881/ab3984) | https://arxiv.org/abs/1906.00966 | full text |
| Morton 2012, ApJ, vespa method (doi:10.1088/0004-637X/761/1/6) | https://arxiv.org/abs/1206.1568 | abstract |
| Morton et al. 2016, ApJ, FPPs for all KOIs (doi:10.3847/0004-637X/822/2/86) | https://arxiv.org/abs/1605.02825 | abstract |
| vespa README (retirement note) | https://github.com/timothydmorton/VESPA | page |
| Giacalone et al. 2021, AJ 161, 24, TRICERATOPS (doi:10.3847/1538-3881/abc6af) | https://arxiv.org/abs/2002.00691 | full text |
| TRICERATOPS code | https://github.com/stevengiacalone/triceratops | page |
| Lissauer et al. 2012, ApJ, multis (doi:10.1088/0004-637X/750/2/112) | https://arxiv.org/abs/1201.5424 | abstract |
| Rowe et al. 2014, ApJ, multis validated (doi:10.1088/0004-637X/784/1/45) | https://arxiv.org/abs/1402.6534 | abstract |
| Fressin et al. 2013, ApJ, Kepler FP rate (doi:10.1088/0004-637X/766/2/81) | https://arxiv.org/abs/1301.0842 | abstract |
| Dawson & Johnson 2012, ApJ, photoeccentric effect (doi:10.1088/0004-637X/756/2/122) | https://arxiv.org/abs/1203.5537 | abstract |
| Kostov et al. 2019, AJ, DAVE (doi:10.3847/1538-3881/ab0110) | https://arxiv.org/abs/1901.07459 | abstract |
| Armstrong, Gamper & Damoulas 2021, MNRAS (doi:10.1093/mnras/staa2498) | https://arxiv.org/abs/2008.10516 | abstract |
| Valizadegan et al. 2022, ApJ, ExoMiner (doi:10.3847/1538-4357/ac4399) | https://arxiv.org/abs/2111.10009 | abstract |
| Eisner et al. 2021, MNRAS, Planet Hunters TESS II (doi:10.1093/mnras/staa3739) | https://arxiv.org/abs/2011.13944 | abstract |
| Eisner, Lintott & Aigrain 2020, JOSS, LATTE | https://joss.theoj.org/papers/10.21105/joss.02101 | page |
| NASA Exoplanet Archive inclusion criteria | https://exoplanetarchive.ipac.caltech.edu/docs/exoplanet_criteria.html | page |

**Could not verify from the research container:** ExoFOP pages (robots-blocked to the fetcher), so the APC disposition definition and the lab's note that CTOIs now need a peer-reviewed paper (ExoFOP rule change of 2026-08-19, per the lab's own transcription, `docs/submissions/TIC374861595-CTOI.md` §0.1) are carried from the lab's own records, not re-checked. The vespa retirement research note (doi:10.3847/2515-5172/acd9a6) is linked from the README but IOP blocked the fetch.
