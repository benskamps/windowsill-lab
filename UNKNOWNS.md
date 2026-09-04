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

**question.** On a regular (deterministic-quantile) frequency class, is the *subcritical* Kuramoto **fluctuation** exponent γ′ — the one on χ = N·Var_t(r), not on the field response ∂⟨r⟩/∂h — Daido's 1, or the 1/4 that Hong, Chaté, Tang & Park measure? **Narrowed 2026-09-03**, and the narrowing is most of what this entry now says: both parties agree on the supercritical γ = 1/4, so the contested cell is exactly one — (regular, subcritical, fluctuation).

**why open.** Two published results disagree about the subcritical fluctuation exponent on a deterministic-quantile frequency set, nobody has settled it, and this box can build that frequency set. Everything else this entry used to say was wrong or overstated, corrected 2026-09-03 by a six-agent primary-source pass (assay: `docs/assays/2026-09-03-u-k02-prior-art-pinned.md`; quotes, locators and hashes: `evidence/literature/`). **(1) The citation was wrong, and it was public.** Daido's asymmetric pair is *not* in Prog. Theor. Phys. 75, 1460 (1986). All four pages of that paper were read this round; its only fluctuation-exponent statement is Eq. (7), σ̂ ≃ Q_±|ε − ε_c|^(−1/2) for ε ≷ ε_c — the **same** exponent on both sides, with only the amplitudes differing by √2. The asymmetry first appears in Prog. Theor. Phys. 81, 727 (1989) — γ′ = 1/2 below (Eq. 12), γ′ = 1/8 above (Eq. 17) — and is developed in J. Stat. Phys. 60, 753 (1990), which nobody in this pass reached. `src/lab/k03.py` carried the same wrong source string; the rivals lane corrected it in this same pass — its docstring and `DAIDO["source"]` now cite 1989, and `tests/test_rivals.py` asserts `"75, 1460"` stays out of that field. `BACKLOG.md` and the 2026-08-02 assay still carry the 1986 attribution and are not this file's to fix. **(2) The two papers do not contradict each other wholesale.** Hong et al.'s much-quoted "definitely excludes Daido's value γ = 1/4" is in §III B, the **random** class. In the regular class they *endorse* Daido supercritically — "This value is consistent with Daido's theoretical result of γ = 1/4" (§IV B) — and disagree only below K_c, where his perturbation theory says 1 and they measure γ′ = 0.25(1). One cell is contested, not a literature. **(3) Both sides are fluctuation exponents.** Daido's σ and Hong et al.'s χ (Eq. 3.6, N[⟨Δ²⟩ − ⟨Δ⟩²]) are the same observable family. The *field* response ∂⟨r⟩/∂h that K03's instrument measures is a different object, and Hong et al. give it a different symbol and a different value in the same paragraph — "It is almost trivial to derive the susceptibility exponents in the Kuramoto model, which turn out to be γ_sus = γ′_sus = 1" — while warning FDT is probably violated, so the two need not agree. **(4) The class match is narrower than this entry claimed.** The 2026-08-02 assay's "term for term" holds against *Daido's* construction: `kuramoto.py` builds regular-quantile **Lorentzian** frequencies, which is what Daido used. Hong et al.'s regular-class γ and γ′ are **Gaussian**; their entire regular-Lorentzian content is two sentences reporting ν̄ ≈ 5/4 for the *order parameter*, with no χ, no γ and no γ′ anywhere. **That same axis bears on a green leaf, and the 2026-09-03 pass did not say so** (flagged by the hostile review, same day): milestone K02's promoted headline calibrates this engine's Lorentzian r(K_c, N) against “the published β/ν̄_c = 0.39(2) **for exactly this configuration** (Hong et al. Eq. 4.3)” — but Eq. (4.3) is a §IV equation, so by the pinned record's own reading (`evidence/literature/hong-chate-tang-park-2015-pre92-022122.json`, field `frequency_class`) that β is **Gaussian** as well. The single Hong number this lab already grades a leaf against is the one number the literature pass left unpinned: it appears in no quote and no `numbers` entry in that record. **And it is not prose — it is executable.** A second hostile review (2026-09-04) traced it: `src/lab/checks.py:393` states in a comment that Eq. (4.3) is “for the REGULAR (deterministic-quantile) **Lorentzian** — this engine's exact published configuration, their §IV A”, and on that authority line 395 hard-codes the graded constant `K02_CRITICAL_EXPONENT = 0.39`, which `check_k02` compares against at line 2147 with a ±0.08 band. The same attribution is doctrine as well: `docs/assays/PROTOCOL.md` §3 teaches future assays that the regular class's “published collapse exponent is 0.39(2)”. So the unmatched distribution axis reaches one comment, one graded constant and one protocol — three sites, not one, and the middle one decides whether a leaf is green. **Not corrected anywhere:** `checks.py` and `PROTOCOL.md` are outside every lane this pass ran, and moving a graded constant is Ben's call, not a review's. It may well transfer — Hong's two-sentence Lorentzian spot-check reports the same ν̄ ≈ 5/4, and β = 1/2 is mean-field — but “may well transfer” is exactly the standard this paragraph refuses for the clip. Not corrected here: K02 is a `[x]` line whose parenthetical `publish.parse_milestones` lifts verbatim into `pot.json`, so rewording it is a publish-path change and not this file's to make. On top of that the tail clip at |ω| ≤ 40γ parks 2·arctan(1/40)/π = 1.591 % of the population exactly on the boundary, N-independently, so this engine's g(ω) is strictly neither paper's. Effect on γ: **undetermined** — it has never been measured and is not assumed harmless. Checked directly on 2026-09-03 at N = 2000: Daido's own quantile rule as quoted from p. 1461, Δ_j = γ·tan{jπ/N − (N+1)π/2N}, reproduces `lorentzian_frequencies()` *unclipped* to 2 × 10⁻¹¹, so the clip is the whole of the difference — and it is not a small one where it bites: 32 of 2000 oscillators are moved, the largest by **616.6** in ω (a frequency of ≈636.6 parked at 20, a 31× displacement of the bound itself). That is the argument for running the clip control before anything expensive, not after. **(5) Units, and a factor of two.** Daido never writes 1/4 or 1. He writes γ′ = 1/8 and γ′ = 1/2 on σ = √(N·Var), labelling **both** sides γ′ (in his papers γ is the Lorentzian half-width, not an exponent). The modern literature silently squares these into χ units. Any future fit here must state whether it fitted σ or χ, or it inherits the same class of error as the fluctuation/response mismatch. **Retiring or settling this entry is Ben's call, not a pass's.**

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

**importance.** 3

**status.** charted

**reach.** out-of-reach

**reach evidence.** Measured 2026-08-25 from `run-2026-08-24-0324-m12.json`. Two blockers, in order. **(1) The discriminating observable is not recorded**: M12 stores P(q) at one reference size (L=12) and the question is entirely about how P(0) scales with L, so the number has been generated on all four passes over L=[6,8,10,12] and discarded. That is a serialisation fix, not a compute one, and until it lands no GPU time can help. **(2) Even then the statistics are far short**: P(0) = 0.2185 ± 0.0739 at T/T_c = 0.71 — a **34% relative error** from 800 disorder realizations, against a droplet-vs-RSB effect of only **13%** across L = 6→12. That is **0.3σ**. P(0) does not self-average, so realizations are the only lever: 3σ needs ~62× more, about **11 GPU-days**. Real, priced, and not a frontier this box is close to.

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

**importance.** 1

**status.** retired

**reach evidence.** RETIRED 2026-08-25. Believed closed by Borwein, Borwein & Galway (2004). Kept in the file as a record that the lab put a wrong entry on its own map and took it off — a catalogue that only ever grows is a wish list.

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

**reach evidence.** Priced 2026-08-24 from 1,400 pooled null draws, then **RE-ANALYSED 2026-08-25 · verdict REANALYSED — NOT an attempt**.

> ⚠ **Corrected 2026-08-25.** This was first recorded as an ATTEMPT and it is not one. It consumed only committed bytes; no new observation was acquired. U-A01 asks whether the *sector* holds an uncatalogued transit — this answered whether the *record* does, which the empty shelf had already said. The pipeline permitted the swap because no stage in it required going outside, which is the estate architecture audit's defect at a third radius: *the care went into the asking, and it stopped at the looking.*

The scramble campaign put the threshold region inside the sample — 84,500 null draws, max SDE 8.049 — so every crossing this survey ever made could be given a *measured* false-alarm probability instead of an extrapolated one. The decision rule was committed at 12:10Z **before any real-target disposition was examined** (`4832d91`).

Result: 9,714 searched rows over **9,514 distinct targets** produced **173 crossings at SDE ≥ 8** — of which **79 are catalogued planets**, which is the pipeline recovering real signal and is reported as calibration, not discovery. Of the 94 uncatalogued crossings the strongest is **TIC 382028425, SDE 8.048**, empirical FAP 1.18e-05 from a single null exceedance, giving an expected background of **0.113** across the trials — just over the pre-registered ceiling of 0.1. It is independently dispositioned `harmonic-alias`, so it dies twice.

**The claim that this survey already holds an undiscovered transit is killed.** The shelf's empty is no longer an absence of evidence; it is a measured empty with every exit counted.

## U-I01 · track I

**question.** What is the minimum ionising-particle detection threshold of this box's own capped CMOS sensor, and can it separate a genuine track from a hot pixel by a stated rule?

**why open.** Not open to the field — citizen-science projects have been doing smartphone-CMOS cosmic-ray detection for years. It is entirely unmeasured *here*, and Track I's whole goal is to characterise this instrument's noise well enough that a signal would be believable.

**known to.** us

**who would care.** Only this lab — and that is stated plainly rather than dressed up. It does not cross the gate and must not be counted as if it did.

**feasibility test.** Confirm an instrument exists before designing an experiment for it.

**if out of reach.** Close Track I at "no instrument present", which is a legitimate arrival by the track's own stated terms.

**importance.** 2

**status.** retired

**reach.** out-of-reach

**reach evidence.** `ls /dev/video*` returns nothing — there is no camera on this box (2026-08-24). RETIRED 2026-08-25: there is no instrument and no plan to buy one, so this is not a frontier, it is a shopping list. Track I closes at "no instrument present", a legitimate arrival by its own stated terms.

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
