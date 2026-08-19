# Assay — prior art for the 2026-08-19 gates and the tempering move

**Why this exists:** four gates and one sampler move landed today, each of which
solved a real problem for this lab. PROTOCOL §1 fires on *any measurement a
milestone wants to claim beyond calibration*, and the risk here is not a wrong
number — it is a **framing** that lets "we built a thing that works" drift into
"we built a thing nobody had". Every item below is graded against the literature
before any of it appears on a page.

**Assayer:** Claude (Opus). **Date:** 2026-08-19. **Protocol:** `docs/assays/PROTOCOL.md`.

**Same completeness caveat as the sibling assay:** citations are pinned to title,
authors where retrieved, venue and arXiv id — not to equation or section. For the
verdicts below that is enough, because every one of them is REDISCOVERED and the
question was only ever *whether the corpus exists*, not what its exponents say.

---

## The short version

| Item | Verdict |
|---|---|
| Doubled-period fold / P-2 alias gate | **REDISCOVERED** |
| Duration-matched depth estimator | **REDISCOVERED** |
| CTOI catalog crosscheck | **REDISCOVERED** (it is a table lookup) |
| Companion-radius admissibility gate | **REDISCOVERED** |
| Multi-sector evidence combination | **REDISCOVERED** |
| Parallel tempering for spin glasses | **REDISCOVERED**, emphatically |
| Mutation-testing a verification suite | **REDISCOVERED** (from software engineering) |

**Nothing built today is novel, and none of it was supposed to be.** The value is
that a home instrument now does what the professional pipelines do; the assay's
job is to make sure nobody says otherwise.

---

## 1. The transit-vetting gates

### Strongest published statement

**Kunimoto, M. et al. (2025/2026),** *"LEO-Vetter: Fully Automated Flux- and
Pixel-level Vetting of TESS Planet Candidates to Support Occurrence Rates"*,
Astronomical Journal, [10.3847/1538-3881/ae070a](https://doi.org/10.3847/1538-3881/ae070a),
arXiv:[2509.10619](https://arxiv.org/abs/2509.10619). Code:
[github.com/mkunimoto/LEO-vetter](https://github.com/mkunimoto/LEO-vetter).

LEO-Vetter is a Robovetter-lineage tool that computes vetting metrics and checks
them against pass/fail thresholds, implementing *"flux- and pixel-level tests
against noise/systematic false positives and astrophysical false positives"*,
reporting 91 % completeness and 97 % reliability against noise/systematic false
alarms on simulated data. Its stated failure taxonomy — *"eclipsing binary,
nearby eclipsing signal"* versus *"systematic, stellar variability"* — is the
same taxonomy this lab's `MACHINE_DISPOSITIONS` enumerates.

Its ancestor, the **Kepler Robovetter**, has carried odd/even depth comparison,
secondary-eclipse search, ephemeris-match and centroid tests as standard since
the Kepler DR24–DR25 catalogs. The half-period / double-period alias check is
part of that standard toolkit; it is not an invention of 2026-08-18.

Also found and relevant: **COUNTESS I**, *"A Uniformly Vetted Catalog of Known
and New Transiting Exoplanets in the TESS Northern Continuous Viewing Zone"*,
arXiv:[2606.13789](https://arxiv.org/abs/2606.13789) — a uniformly vetted catalog
built on the same public data this lab searches, and **RAVEN**, *"RAnking and
Validation of ExoplaNets"*, arXiv:[2509.17645](https://arxiv.org/abs/2509.17645).

### Verdict on each gate

- **Doubled-period fold (`p2_fold`): REDISCOVERED.** Half-period aliasing is the
  canonical EB false-positive mode and folding at 2P to compare alternate minima
  is the canonical response.
- **Duration-matched depth estimator (`measure_dip`): REDISCOVERED.** Fitting or
  measuring a transit over its own measured duration rather than a fixed window
  is standard; the published pipelines fit trapezoidal or limb-darkened models,
  which is *stronger* than what landed here.
- **CTOI crosscheck (`lab.exofop`): REDISCOVERED**, and calling it anything else
  would be silly — it is a lookup against a public table that exists to be looked
  up against. The finding was that this pipeline was not doing it.
- **Companion-radius admissibility (`a05_physical`): REDISCOVERED.**
  R_c = R_★√depth is textbook, and every professional pipeline applies a
  planetary-radius cut. Published vetting additionally fits limb-darkened models
  rather than box depths — see §1.1.
- **Multi-sector combination (`combine_p2_folds`): REDISCOVERED.** Multi-sector
  analysis is routine; LEO-Vetter's occurrence-rate purpose requires it.

### 1.1 The estimator audit finds us *behind*, not ahead

PROTOCOL §4 asks whether our number measures what theirs measures. It does not,
quite, and the difference runs against us: this pipeline measures a **box-fit
mean depth**, while published vetting fits limb-darkened transit models.
Measured against WASP-18 b, whose radius is published at 1.19 R_Jup, the
admissibility gate returns **1.27 R_Jup — about 7 % high**, and the box estimator
is why. That is a documented systematic in a gate that landed today, running in
the direction of refuting more candidates than it should. Stated in the module,
stated here.

### 1.2 What is genuinely ours, and it is not a method

The specific finding that **six of eight sectors of TIC 287328866 individually
read below the 5σ bar while their combination reads 9.4σ** is a measurement on a
specific star, made here. It is not a new method — it is what the standard method
says when applied to a star this lab had shelved. It goes in the record as a
measurement, cited to nobody, claimed as nothing more.

## 2. Parallel tempering

### Strongest published statement

Parallel tempering (replica exchange) for Ising spin glasses is ~35 years old and
is *the* standard answer to exactly the failure `spin_glass.py` documents.
Pinned:

- **Wang, W.; Machta, J.; Katzgraber, H. G. (2015),** *"Comparing Monte Carlo
  methods for finding ground states of Ising spin glasses: population annealing,
  simulated annealing, and parallel tempering"*, Phys. Rev. E **92**, 013303,
  arXiv:[1412.2104](https://arxiv.org/abs/1412.2104). The head-to-head comparison
  of the three samplers the lab's backlog names as candidates.
- **"Correlations between the dynamics of parallel tempering and the free-energy
  landscape in spin glasses"**, arXiv:[1210.6290](https://arxiv.org/abs/1210.6290).
- **peapods** — *"peapods: A Rust-Accelerated Monte Carlo Package for Ising Spin
  Systems"*, arXiv:[2602.19045](https://arxiv.org/abs/2602.19045), code at
  [github.com/PeaBrane/peapods](https://github.com/PeaBrane/peapods). Ships
  *"Metropolis, Gibbs, Swendsen–Wang, Wolff, and parallel tempering"* plus
  **three replica cluster moves for spin glasses (Houdayer ICM, Jörg, and CMR)**,
  overlap histograms, integrated autocorrelation times and equilibration
  diagnostics.
- **tamc** — [github.com/hmunozb/tamc](https://github.com/hmunozb/tamc),
  "Parallel Tempering Markov Chain Monte Carlo for Ising Spin Glasses".

### Verdict: **REDISCOVERED**, and the literature is well ahead

Not only is the move published, an open-source package exists that implements it
alongside **replica cluster moves this lab does not have** (Houdayer isoenergetic
cluster moves are the next rung past plain tempering for ±J glasses, and peapods
has them). PROTOCOL §8: *"If the literature is sharper than us, say so and give
their number."* It is, and that is the number.

The lab's own framing must therefore be: *the windowsill adopted a standard
sampler and measured what it bought on this hardware.* The measurement
(`docs/investigations/2026-08-19-parallel-tempering-lifts-the-floor.md`) is real
and local — 75.7 s tempered vs 78.3 s untempered, floor from 0.6 down past 0.30,
with a failing 4×-sweeps control. The *method* is 1990s standard practice.

### Free win

Wang–Machta–Katzgraber compare PT against **population annealing** directly. The
backlog names population annealing as a candidate; the comparison it would need
is published, so the lab can read the answer instead of measuring it, and should
read it before spending a sprint. And **Houdayer ICM** is the concrete next
sampler rung, named by a package that already implements it.

## 3. Mutation-testing the checks

**Verdict: REDISCOVERED**, from a different field. Mutation testing — perturb the
system under test, assert the test suite goes red, treat surviving mutants as
gaps in the suite — is a standard software-engineering technique with decades of
literature and mature tooling (`mutmut`, `cosmic-ray` in Python alone).

What is unusual is only the *target*: the mutants here are corrupted **reports**
rather than corrupted source, because the thing being audited is a suite of
physics checks whose inputs are data files. That is a variation on a known
technique, not a new one, and the correct label for the 31 "graded but not
required" fields it found across M03/M07/M14 is **a bug found by a standard
technique**, not a discovery.

## 4. Outcome routing

Per PROTOCOL §8, every REDISCOVERED item is relabelled as **standard practice
adopted**, with the citation attached, and this is a good outcome rather than a
demotion: "a windowsill runs Robovetter-class vetting and replica-exchange Monte
Carlo, and here is what each bought on two home machines" is a stronger and more
honest sentence than any novelty claim available here.

Concretely, and these are constraints on future public copy:

1. No page, post or `MILESTONES.md` entry may describe the fold gates, the CTOI
   lookup, the radius gate, the sector combination, the tempering move or the
   mutation harness as new. Each cites its prior art.
2. The **7 % radius systematic** (§1.1) travels with the admissibility gate
   anywhere it is described.
3. Where the literature is ahead — limb-darkened fits, Houdayer cluster moves,
   pixel-level vetting — the lab says so rather than omitting it.
4. The measurements *are* the lab's: the eight-sector 9.4σ combination, the
   tempering floor at 0.30 with its 4×-sweeps control, the 31 unrequired fields.
   Those are claimed, with receipts, and none of them is a claim about method.

## 5. The searches, as receipt

Run 2026-08-19. Exact query strings:

1. `LEO-Vetter TESS false positive vetting pipeline open source` — returned
   LEO-Vetter (AJ + arXiv 2509.10619 + GitHub), COUNTESS I (arXiv 2606.13789),
   RAVEN (arXiv 2509.17645), Nigraha (arXiv 2101.09227), ExoNet (arXiv 2604.15560).
2. `"peapods" Rust Monte Carlo Ising spin glass parallel tempering open source` —
   returned peapods (arXiv 2602.19045 + GitHub), tamc, Wang–Machta–Katzgraber
   (arXiv 1412.2104), and the PT/free-energy-landscape correlation study
   (arXiv 1210.6290).

**No empty searches to report.** Every item assayed here returned prior art on
the first query, which is itself the finding.

**Retrieved and rejected:** ExoNet and Nigraha (machine-learning vetting — same
problem, different method, not prior art for these specific geometric gates);
RAVEN (ranking/validation rather than the flux-level tests built here).

**Names from the 2026-08-19 external review, now graded.** The review offered a
peer list marked unverified. Verified real from these searches: **peapods**
(arXiv 2602.19045), **LEO-Vetter** (arXiv 2509.10619), **COUNTESS**
(arXiv 2606.13789), **AgenticSciML** (arXiv 2511.07262, npj Artificial
Intelligence), **SciExplorer** (Phys. Rev. X, *"Agentic Exploration of Physics
Models"*), **PhyNex** (arXiv 2606.14266, LLM-based agent for automated discovery
in computational physics). Still unverified after searching: **QUASAR**, **QISG**,
**BatchTNMC**.

Those three are named *here* on purpose and nowhere else on purpose, and the
distinction is PROTOCOL §7: an assay is a **receipt**, and a negative result is
only checkable if the thing that failed to check out is named — "three names I
will not tell you" is unfalsifiable, and a reader must be able to search them
again and either confirm the hole or fill it. What they may not do is appear in
any copy that *presents* them — as peers, as citations, as evidence the field is
crowded. The 2026-08-19 external-review digest originally listed them in exactly
that way and has been corrected.

---

**Headline:** *Everything built on 2026-08-19 is standard practice, and one
open-source package already ships a strictly better version of the sampler. What
the lab owns is the measurements: what the standard methods say about six shelved
leads, and what replica exchange buys on 76 seconds of consumer GPU.*
