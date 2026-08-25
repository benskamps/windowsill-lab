# Unknowns — the map of what this lab does not know

> `MILESTONES.md` is the ladder: what was measured. `TRACKS.md` is the summit:
> what each track is *for*. This is the third map and the last one to be drawn
> — **what is not known at all**, and whether this box can reach it.
>
> Drafted 2026-08-24, the day the lab decided to start charting unknowns rather
> than only climbing rungs. Read by `lab unknowns`.

## The rule that keeps this honest

Every entry declares **who does not know it**, and the honest answer is usually
the uncomfortable one:

| value | meaning | how often it's the true answer |
|---|---|---|
| `field` | nobody knows — a genuine open question | rare, high burden of proof |
| `us` | the field knows; we have not measured it | **most of them** |
| `reach` | whether *this instrument* can touch it is what's unknown | the useful middle |

Only a `field` unknown crosses the charter's **SETI gate**. A `us` unknown is
calibration — often the right thing to do, never the same thing. Blurring the
two is the easiest way for a calibration bench to convince itself it is doing
discovery, and this file exists to make that impossible to do by accident.

## Status is a claim, not a mood

An entry enters as **`claimed-open`**. It becomes **`charted`** only when
somebody has actually checked that the field does not know it — a literature
pass, or Ben's ruling. *A claim that something is unknown is itself a claim*,
and it gets the same treatment as every other claim here.

**Everything below is `claimed-open` unless marked otherwise.** These were
drafted by a machine that is confident but not authoritative about what the
literature contains, and confident-but-wrong is the exact failure mode this
lab was built to refuse.

## Reach is measured, never argued

Every entry carries a **feasibility test**: the cheapest thing that decides
whether this box can reach the question, run *before* any attempt on the
question itself. An `out-of-reach` verdict is a **result** — recorded with the
number that produced it and what would have to change. That is what separates a
catalogue of unknowns from a catalogue of wishes.

---

## U-K01 · track K

**question.** Is K03's fitted susceptibility exponent a measurement of γ, or an artifact of an ε window that sits outside the critical scaling regime?

**why open.** The 2026-08-23 run measured the supercritical branch cleanly — six columns, R² = 0.999 — and returned γ = 1.07 ± 0.02, roughly 46σ from the 0.25 that *both* Daido and Hong predict. Two readings fit: the engine contradicts two published papers, or ε ∈ [0.02, 0.32] never entered the asymptotic window and is reporting the generic mean-field χ ~ ε⁻¹. Nothing on the record distinguished them, and the fact was buried under a `status: fail` caused by the *other* branch.

**known to.** reach

**who would care.** Us, immediately and before anything else: every K03 result, and any larger-N run planned on top of one, is meaningless until this is settled.

**feasibility test.** Fit the local log-log slope between each adjacent pair of columns in the committed receipt. A true power law has a constant local slope; a drifting one is a crossover being averaged over. Costs milliseconds and no new simulation.

**if out of reach.** Push the ε floor below the current 0.0317 and fix the linearity-gate refusals that cost the four innermost subcritical columns. **Do not** buy a larger N inside the same window — that purchases a more precise artifact.

**importance.** 5

**status.** charted

**reach.** out-of-reach

**reach evidence.** Local exponent drifts 20.1% across the window, monotonically: 0.979 at the inner edge to 1.195 at the outer, falling as ε shrinks — the signature of a crossover approached from outside. Compounding it, the subcritical gate is thresholding a noisy statistic: ε = 0.127 was refused while ε = 0.08, *closer* to K_c, passed, so the three surviving columns passed partly on the draw and cannot carry γ′ either. Measured 2026-08-24 from `run-2026-08-23-2216-k03.json`.

## U-K02 · track K

**question.** On the regular (deterministic-quantile) frequency class, is the Kuramoto susceptibility exponent asymmetric across K_c — Daido's γ = 1/4, γ' = 1 — or symmetric at 1/4, as Hong, Chaté, Tang & Park report?

**why open.** Two published results directly contradict each other on the same class: Daido, Prog. Theor. Phys. 75, 1460 (1986) and J. Stat. Phys. 60, 753 (1990); Hong et al., PRE 92, 022122 (2015) §IV. The 2026-08-02 assay established this engine's frequency set is that class term for term, so the disagreement is measurable here rather than merely readable.

**known to.** field

**who would care.** Anyone who cites either paper for the critical behaviour of the regular-frequency Kuramoto model — the two are not reconcilable and the literature carries both.

**feasibility test.** Priced before spending anything. The instrument's demonstrated stderr on a branch it can measure is 0.0177 against a Δγ' = 0.75 gap — a **42σ separation**, so precision was never the blocker. What blocks it is noise on the subcritical branch, and that noise was diagnosed: the refused columns' secants *rise and scatter* rather than falling monotonically, which is noise and not saturation, and the implied noise scales as **ε^-0.76** — critical slowing down against a `T_MEASURE` pinned at 2000 for every column.

**if out of reach.** Raise the ε floor or split the grid across nights. **Do not trim `T_MEASURE`**, the one axis that cannot be cut without reopening the noise problem the run exists to close.

**importance.** 5

**status.** charted

**reach.** in-reach

**reach evidence.** N is the lever, not T: error falls as 1/√(N·T) but time is serial while N is parallel. Benchmarked on this box 2026-08-24 (RK4, float64, per step): NumPy 203 µs at N=2,000 and 17,680 µs at N=200,000; torch on the RX 6900 XT 306 µs and 527 µs. The GPU is *slower* at N=2,000 and 33× faster at N=200,000 — 100× the oscillators for 2.6× the wall-clock. Projected grid reaching ε = 0.005 at N = 200,000 with ε-scaled `T_MEASURE`: every column predicted at or under half the gate tolerance, **3.1 GPU-hours** against 103 hours on the CPU engine.

## U-M01 · track M

**question.** Is the low-temperature phase of the 3D Edwards-Anderson spin glass described by replica symmetry breaking or by the droplet picture?

**why open.** One of the long-standing open problems in statistical mechanics: mean-field RSB is exact in infinite dimensions, droplet theory is a competing finite-dimensional scaling picture, and numerical work in 3D has been argued both ways for decades because the equilibrated sizes are small and the crossover is slow.

**known to.** field

**who would care.** The spin-glass community, and by extension everyone who borrows its language for optimisation landscapes and neural-network loss surfaces.

**feasibility test.** M12 proved this box does 4.4 GPU-hour parallel-tempering runs. The test is whether the overlap distribution P(q) at the largest L this box can equilibrate has enough weight between the peaks to distinguish a non-trivial plateau from a finite-size smear — measured against the equilibration criterion, not eyeballed.

**if out of reach.** Report what L this box *can* equilibrate and what that L can and cannot distinguish. A measured ceiling is a contribution; a claim from an unequilibrated run is not.

**importance.** 4

## U-C01 · track C

**question.** Does a BBP-type digit-extraction formula exist for π in base 10?

**why open.** BBP extracts hexadecimal digits of π without computing predecessors, and the same works in any base that is a power of 2. No analogous base-10 formula is known, and the question of whether one can exist is not settled the way a proved impossibility would be.

**known to.** field

> ⚠ **THIS ENTRY IS PROBABLY WRONG AND IS FLAGGED FOR RETIREMENT (2026-08-24).**
> Borwein, Borwein & Galway, *"Finding and excluding b-ary Machin-type BBP
> formulae"* (2004) is believed to have **excluded** base-10 Machin-type BBP
> formulae for π. If that holds, this question is *closed*, not open, and the
> entry must be retired — dropping the gate ratio from 57% to 50%. Recorded as a
> belief needing a human literature check, which is exactly the failure this
> file's own header warns about: drafted by a machine confident but not
> authoritative about what the literature contains. **A catalogue that only ever
> grows is a wish list.**

**who would care.** Number theorists and the normality-of-π programme; a base-10 analogue would be a genuinely notable result and its impossibility proof more so.

**feasibility test.** Not a simulation question — the cheap test is whether this lab can do anything beyond restating it. Search the space of known BBP-type formula families for base-10 candidates by the standard integer-relation approach and report the search bound reached. If the honest answer is "we can only restate the problem", this is a `us`-flavoured entry masquerading as a `field` one and should be demoted.

**if out of reach.** Demote to a reading note and retire it from the catalogue. An open problem the lab cannot approach is not this lab's unknown; it is the field's, and listing it here inflates the gate ratio without doing any work.

**importance.** 2

## U-A01 · track A

**question.** Does the sector currently on the hunt shelf contain a transiting planet signal that has not been catalogued?

**why open.** Nobody knows what is in un-vetted archival data until somebody searches it with a method that prices its own false alarms — which is the entire premise of the A05 blind hunt.

**known to.** field

**who would care.** It is a small, real, checkable contribution — and it is the one place in this repo where the lab is already on the far side of the SETI gate rather than preparing to cross it.

**feasibility test.** Pool every epoch-scramble ever run — a scrambled curve is by construction a draw from the null — and ask whether the promotion threshold can be *priced* rather than merely set.

**if out of reach.** Quote only the model-free bound and treat the shelf as unpriceable until more scrambles exist. A shelf with an honest empty beats a lead priced by a null that does not hold.

**importance.** 5

**status.** charted

**reach.** in-reach

**reach evidence.** 1,400 null draws pooled from 58 hunts (2026-08-24); the largest ever reached SDE 7.00 against a promotion threshold of 8.0, so there are **zero exceedances**. An exponential tail fit extrapolates a per-curve FAP of 6.2e-5, stable to 6.1x across the fit cut, which over 9,985 real trials expects **0.61 false alarms across the entire survey** — a crossing would matter. The model-free bound (rule of three) is 2.1e-3, permitting up to 21, under which a crossing would prove nothing. **The price therefore rests entirely on a one-SDE extrapolation and is never quoted without that bound beside it.** ~325,000 pooled scrambles would replace the extrapolation with a measurement; scrambles reuse curves already on disk and are CPU work that does not compete with the GPU lane.

## U-I01 · track I

**question.** What is the minimum ionising-particle detection threshold of this box's own capped CMOS sensor, and can it separate a genuine track from a hot pixel by a stated rule?

**why open.** Not open to the field — citizen-science projects have been doing smartphone-CMOS cosmic-ray detection for years. It is entirely unmeasured *here*, and Track I's whole goal is to characterise this instrument's noise well enough that a signal would be believable.

**known to.** us

**who would care.** Only this lab — and that is stated plainly rather than dressed up. It does not cross the gate and must not be counted as if it did.

**feasibility test.** Confirm an instrument exists before designing an experiment for it.

**if out of reach.** Close Track I at "no instrument present", which is a legitimate arrival by the track's own stated terms.

**importance.** 2

**status.** charted

**reach.** out-of-reach

**reach evidence.** `ls /dev/video*` returns nothing — there is no camera on this box (2026-08-24). The unknown cannot be attempted at all, which was worth thirty seconds to establish rather than months to plan around.

## U-P01 · track P

**question.** At what chain length does the HP lattice model's ground state stop being provable by exhaustive enumeration on this box, and what fraction of sequences at that length have degenerate ground states?

**why open.** Ground-state degeneracy and designability in the HP model are studied but the specific boundary is an instrument property: it depends on what this box can enumerate. The physics question underneath — how designability scales with length — is genuinely active.

**known to.** reach

**who would care.** Us first, since P01's honesty rule is that a proven optimum is never pooled with an unproven one, and that rule needs a measured boundary to sit on.

**feasibility test.** Time the existing enumerator at increasing length until it exceeds one night, and record the length.

**if out of reach.** Report the measured ceiling as the deliverable. Track P's goal already says the arrival condition is knowing where proving becomes impossible and saying so.

**importance.** 3

**status.** charted

**reach.** in-reach

**reach evidence.** Measured 2026-08-24, three random sequences per length: L=20 at 0.28 s/seq, L=24 at 7.5 s, **L=25 at 33 s**, L=26 exceeding 80 s (timed out) — clean exponential growth, as a self-avoiding walk count demands. So a graded set of ~10 sequences fits one night up to **L ≈ 26**, and a single hero sequence to **L ≈ 30**. Beyond that, proving stops and Track P's honesty rule takes over.

---

## The goal these unknowns exist to serve

Charting is not crossing. Every entry above has been **priced** — reach
measured, cost stated, instrument checked — and not one has been **attempted**.
Pricing is the half this box is good at and the half that cannot produce a
result.

So `G01` is declared in `src/lab/goal.py`, published in `pot.json` where the
public page reads it, and dated **2026-09-24**:

> Stop pricing the frontier and cross it: attempt one field-unknown and report
> the result either way, with every track honest about where it stands.

Three properties make it a commitment rather than a preference. It is
**published**, so nobody has to be told the lab missed. Its progress is
**computed** from this file at every publish, never written, because a goal
whose progress is hand-edited measures the editor's mood. And it can read
**MISSED** — a deadline that slides is a wish with a calendar next to it.

A verdict of `killed` or `unresolved` meets it exactly as well as `supported`.
The commitment is to attempt and report; a goal that only counts successes buys
itself pressure to find them.
