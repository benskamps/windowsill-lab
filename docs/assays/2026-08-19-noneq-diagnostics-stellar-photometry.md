# Assay — non-equilibrium diagnostics on stellar photometry

**Assayed claim:** *"Applying the non-equilibrium statistical-mechanics toolkit —
aging protocols, multi-time correlation functions, KPZ-style roughness exponents,
absorbing-state (directed-percolation) diagnostics, mutual-information memory
measures — to stellar variability and post-detrend residuals is essentially open
territory, because the field treats them almost exclusively with stationary
Gaussian processes, Fourier methods and autoregressive models."*

**Provenance of the claim:** an outside read of the lab by Grok (xAI) on
2026-08-19, which nominated this as the lab's *"biggest impact possibility"* on
the grounds that it uniquely exploits both wings of the lab under one roof and
needs no hardware. Digest:
`docs/investigations/2026-08-19-external-review-grok.md` §3.5. The idea was
routed here rather than into the backlog as a build, precisely because "nobody
has done this" was an assertion, not a result.

**Assayer:** Claude (Opus). **Date:** 2026-08-19. **Protocol:**
`docs/assays/PROTOCOL.md`.

> **Completeness caveat, stated up front.** PROTOCOL §7 requires citations pinned
> to the specific equation, figure or section carrying each claim. This assay
> pins to **title, authors, venue, year and arXiv id** — abstract-level, not
> equation-level. Every verdict below is therefore provisional at the strength
> the protocol demands, and the two verdicts that turn on *how* a published
> quantity is defined (C2, C4) are the ones most exposed by that gap. Closing it
> means reading four papers, and that is the first item in §9.

---

## 1. Stance

Default hypothesis: rediscovery. The job here is to find the strongest published
statement of each element, not to protect an attractive idea. The claim under
assay is an *absence* claim about a whole literature, which is the easiest kind
of claim to make and the hardest to earn: one paper kills it.

## 2. The claim splits into six, and they do not share a fate

The umbrella claim is not gradable as one thing. Split by the diagnostic:

| | Sub-claim | Verdict |
|---|---|---|
| **C1** | The umbrella: non-equilibrium statistical mechanics is essentially unapplied to stellar photometry | **REFUTED** |
| **C2** | Long-memory / multifractal / Hurst analysis of stellar light curves | **REDISCOVERED** |
| **C3** | Aging protocols and two-time correlation functions on photometric residuals | **UNPUBLISHED (a)**, premise unestablished |
| **C4** | KPZ-style roughness exponents on light curves | **UNPUBLISHED (b)** — one line from C2 |
| **C5** | Absorbing-state / directed-percolation diagnostics for active-region onset and decay | **UNPUBLISHED (a)**, premise unestablished |
| **C6** | A non-equilibrium-informed discriminator beats a GP at separating transits from activity | **UNTESTED** — not a novelty question |

## 3. Configuration-class matching

PROTOCOL §3 is the gate the whole thing turns on, and here the "configuration
class" is not a lattice — it is **what object the exponent is measured on**. Two
distinctions decide C2 and C4:

- **A time series is not a growing interface.** KPZ describes an interface
  *w(t) ~ t^β* roughening in time with a spatial roughness exponent α and
  dynamic exponent z. A single-star light curve is a 1-D signal with one
  independent variable. There is no spatial direction for α to live in.
- **For a 1-D self-affine signal, the roughness exponent IS the Hurst
  exponent.** They are the same quantity under two names — the self-affinity
  exponent of the trace. This is the identity that collapses C4 into C2, and it
  is why "measure KPZ roughness on a light curve" is not a new measurement: it
  is the published measurement with a different word in front of it.

The correctly matched configuration for a genuine KPZ measurement would be a
*spatially resolved, growing* stellar structure (a resolved active-region
boundary evolving in time), which TESS photometry does not deliver: TESS gives
one number per cadence per star.

## 4. Estimator audit

Is our proposed number measuring what their number measures?

- **C2/C4.** MFDMA and MFDFA return a spectrum of generalised Hurst exponents
  h(q), with h(2) the classical Hurst exponent. A "KPZ roughness exponent"
  extracted from a light curve by a structure-function or width-scaling fit
  returns the same self-affinity exponent, estimated by a different (and
  generally *worse*, because non-detrending) estimator. Same quantity,
  different name, weaker method. That is the textbook §4 failure mode — *same
  name, different quantity* — running in reverse.
- **C3.** Aging is defined by the breakdown of time-translation invariance
  *after a quench*: C(t, t_w) fails to depend only on t − t_w, and the waiting
  time t_w is set by a controlled preparation. A stellar light curve has no
  quench and no t_w. One could *define* an analogue (t_w = time since flare
  onset; t_w = time since spot emergence), but that is a new construction whose
  physical content has to be argued, not a transplant of an existing estimator.
- **C5.** Directed percolation's order parameter is an activity density with a
  control parameter tuned through p_c. For active regions the analogous
  quantities (fraction of the disc active; a spreading probability) are not
  observable in single-band disc-integrated photometry at all — they are
  inferred through a spot model. An absorbing-state exponent measured on an
  inferred quantity inherits the spot model's assumptions.

## 5. Error bars

Not applicable at this stage: no number has been measured. Recorded because
PROTOCOL §5 makes the *absence* of a bar a reportable fact rather than a silence
— when this idea produces its first exponent, it enters this assay with an
uncertainty or it does not enter.

## 6. Verdicts, with their evidence

### C1 — the umbrella claim: **REFUTED**

The strongest published counter-statement is C2's corpus. The claim as phrased
("essentially open", "the non-equilibrium perspective is essentially open") is
false: the memory / fractal / complexity wing of non-equilibrium time-series
analysis has been applied to Kepler photometry systematically, on samples in the
hundreds of stars, with explicit stellar-magnetism conclusions.

### C2 — long-memory and multifractal analysis: **REDISCOVERED**

Strongest published statements found:

- **de Freitas, D. B.; Nepomuceno, M. M. F.; Cordeiro, J. G.; Das Chagas, M. L.;
  De Medeiros, J. R. (2019),** *"Multifractal detrended moving average analysis
  of Kepler stars with surface differential rotation traces"*, MNRAS **488**,
  3274. arXiv:[1906.11911](https://arxiv.org/abs/1906.11911).
  **662 Kepler stars** with solar-like parameters, 141 with differential-rotation
  traces. Measures the global Hurst exponent H *"used as a measure of long-term
  memory of time series"* plus an asymmetry index A, and reports differential
  rotation *"distributed in two H regimes segregated by the degree of asymmetry
  A"*. This single paper is sufficient to refute C1.
- **"New Suns in the Cosmos V: Stellar rotation and multifractality in active
  Kepler stars"**, arXiv:[1906.07331](https://arxiv.org/abs/1906.07331).
- **"On the multiscale behaviour of stellar activity and rotation of the planet
  host Kepler-30"**, A&A (2021), arXiv:[2103.15921](https://arxiv.org/abs/2103.15921).
  Note the target class: *a planet host*. The multiscale toolkit has already been
  pointed at exactly the stars C6 proposes to point it at.
- **"Multifractal characterization as a function of timescale in the light curves
  with planetary signal observed by the Kepler mission"**,
  arXiv:[2209.04408](https://arxiv.org/abs/2209.04408).
- **"Multiscale entropy analysis of astronomical time series"**,
  arXiv:[2206.13529](https://arxiv.org/abs/2206.13529) — the
  information-theoretic complexity measures, also already applied.

The literature is also **sharper than the claim** on future missions: the MFDMA
work explicitly proposes itself for *"current TESS and future PLATO data"*, which
is the exact forward-looking pitch C6 rests on.

### C4 — KPZ roughness on light curves: **UNPUBLISHED (b)**

Searches for KPZ applied to astronomical light curves returned nothing
astronomical (see §7). But PROTOCOL §6's category-(b) rule applies with unusual
force: for a 1-D self-affine signal the roughness exponent *is* the Hurst
exponent, so this is not one line from published work — it is **zero lines**, a
renaming. The correct reading of the empty searches is that specialists do not
call H a "KPZ exponent" when there is no interface, not that a hole exists.

This is the assay's most useful output, and it is the one Grok's framing got
exactly backwards: the diagnostic advertised as novel is the diagnostic most
thoroughly published.

### C3 — aging / two-time correlations: **UNPUBLISHED (a)**, with a caveat that outweighs it

No paper found applying aging protocols or two-time correlation functions
C(t, t_w) to stellar photometry. The technique's own literature is large and
squarely non-astronomical (see §7 rejected list).

**But an empty search is only a finding when the question is well posed.** Aging
requires a quench and a waiting time. Stars are not quenched, and no
observational proxy for t_w has been established. So this is genuinely absent
*and* the absence has an obvious candidate explanation that is not "nobody
thought of it". Promoting this to a frontier candidate requires first arguing —
in writing, before any measurement — what plays the role of t_w and why. Until
then it is an idea, not a hole.

### C5 — absorbing-state diagnostics for active regions: **UNPUBLISHED (a)**, same caveat

No paper found. Same structure as C3: the observable required (an activity
density with a tunable control parameter) is not what disc-integrated photometry
measures, so the absence is at least partly an absence of *applicability*.

### C6 — beating a GP at transit/activity separation: **UNTESTED**

This is a performance claim, not a novelty claim, and the protocol has nothing to
say about it. Recorded so it is not mistaken for a verdict. Note that the
relevant comparison target is active: **"Quantifying the Effect of Short-timescale
Stellar Activity Upon Transit Detection in M Dwarfs"**, AJ,
[10.3847/1538-3881/ada898](https://doi.org/10.3847/1538-3881/ada898) — the
question is being worked with conventional tools by people with more data.

## 7. The searches, as receipt

Run 2026-08-19 via web search. Exact query strings, verbatim:

**Returned strong prior art (killed the claim):**

1. `multifractal detrended fluctuation analysis stellar light curves Kepler TESS`
2. `Hurst exponent DFA structure function stellar variability distinguish transit from stellar activity exoplanet detrending`

**Returned nothing astronomical (the empty searches):**

3. `aging two-time correlation function non-equilibrium statistical mechanics applied to stellar photometry light curve residuals` — returned only condensed-matter and XPCS work: Ragulskaya et al., *"On the analysis of two-time correlation functions: equilibrium vs non-equilibrium systems"*, J. Appl. Cryst. (2024), arXiv:[2406.12520](https://arxiv.org/abs/2406.12520); aging in long-range spin models; glass-forming liquids; blinking nanocrystals. **Zero astronomy.**
4. `"directed percolation" OR "absorbing state" transition solar active region emergence decay statistical` — returned only statistical-physics DP work (exactly solvable models, turbulent liquid crystals, patterned turbulence). **Zero solar physics.**
5. `"KPZ" OR "Kardar-Parisi-Zhang" roughness exponent astronomical time series light curve analysis` — returned KPZ theory and, separately, conventional astronomical time-series methods (ARMA/ARIMA/ARFIMA — Feigelson et al., *"Autoregressive Time Series Methods for Time Domain Astronomy"*, Frontiers in Physics **6**:80, 2018; PSD analysis of Fermi-LAT blazar light curves, arXiv:[2006.03991](https://arxiv.org/abs/2006.03991)). **No intersection.**

**Retrieved and rejected, one line each:**

- *Ragulskaya et al. 2024 (two-time correlations)* — methodology paper for X-ray photon correlation spectroscopy; no photometry, no astronomy.
- *Feigelson et al. 2018 (ARMA/ARIMA/ARFIMA for time-domain astronomy)* — rejected as prior art for C3–C5 but **relevant context**: ARFIMA is a long-memory model, so the "field uses only stationary GPs and Fourier" half of C1's premise is itself inaccurate.
- *Fermi-LAT blazar PSD analysis* — AGN, not stellar photometry; establishes that stochastic-process modelling of light curves is standard, not novel.
- *Hurst exponents applied to blazar optical light curves and pulsar spin-down* — same direction as C2, different objects; strengthens the rediscovery.
- *KPZ theory papers (polariton condensates, reaction-diffusion fronts, crystal growth)* — all genuine interfaces; none is a time series.

**Numerical coincidence flagged:** the KPZ growth exponent β = 1/3 and the Hurst
exponent of a light curve are both dimensionless numbers near a third for some
stars. They are **not** the same quantity (β is a growth exponent in time, H a
self-affinity exponent of the trace), and a future writeup that finds "H ≈ 1/3"
on a star must not read that as KPZ.

## 8. Outcome routing

- **C1 → the claim does not go public in any form.** No page, no post, and no
  backlog item may describe this direction as "open territory".
- **C2/C4 → relabelled.** If the lab measures a Hurst or multifractal spectrum on
  a light curve, it is **calibration against a published method**, cited to de
  Freitas et al. 2019, and that is a good outcome — reproducing a real result on
  a windowsill is the lab's actual thesis.
- **C3/C5 → parked as *ideas*, not as frontier candidates.** PROTOCOL §8 requires
  a second independent assay before "frontier" appears anywhere public for an
  UNPUBLISHED (a); these two do not even reach that queue until the premise
  argument in §6 is written. Also note: this assayer and Grok are both large
  language models, so if a second pass is run by another one, PROTOCOL §8's
  correlated-evidence clause applies and the assay must say so.
- **C6 → an experiment, gradable by a check, with no novelty claim attached.**

The `BACKLOG.md` entry added on 2026-08-19 ("non-equilibrium diagnostics on
stellar residuals", routed through this protocol) should be rewritten to carry
these verdicts rather than the open question it currently poses.

## 9. Free wins

PROTOCOL §9: an assay reads the literature in the lab's exact regime, which is
the best chance it gets to find its *next* experiment. Four came out of this one:

1. **Close the pinning gap.** Read de Freitas et al. 2019 §§ and the Kepler-30
   paper to equation level and confirm the H-index definition matches what a
   windowsill measurement would compute. This is the caveat at the top of this
   document, and it is cheap.
2. **A calibration target the lab did not have.** de Freitas et al. published H
   on 662 named Kepler stars. That is a **reproducible external benchmark for a
   sky-track instrument** — pull the same stars, compute H, compare. It grades
   the lab's photometry pipeline against a published number on real data, which
   is exactly the kind of rung A01 is made of, and nothing about it needs an
   unpublished idea to be interesting.
3. **ARFIMA is the honest baseline.** If the lab ever does test C6, the
   comparison target is not "a stationary GP" — it is a long-memory model, and
   Feigelson et al. 2018 names the family. Setting the baseline too low is how a
   method paper manufactures its own improvement.
4. **The C4 collapse is a reusable lesson.** "Diagnostic X from field A has never
   been applied to field B" deserves the question *is X a renaming of something B
   already does?* before it deserves a backlog slot. That is a general rule and
   belongs in PROTOCOL §3.

---

**Headline:** *The greenfield is mostly not green. The one diagnostic advertised
as most novel (KPZ roughness) is a renaming of the one most thoroughly published
(Hurst / multifractal), the umbrella claim is refuted outright by a 662-star
Kepler study, and the two genuinely unpublished diagnostics are unpublished at
least partly because the observable they need is not what photometry measures.
What survives is a free calibration target the lab did not know it had.*
