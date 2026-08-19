# Assay — K02's susceptibility exponent γ/ν̄_c at K_c

**Measured:** `γ/ν̄_c = 0.185 ± 0.040` (r² = 0.955), from `χ_c(K_c) = N·Var_t(r)`
across the ladder N = 250 … 4000, 12 initial conditions per rung, t_burn =
t_measure = 2000. Same run, same windows, same rungs that give
`β/ν̄_c = 0.4011 ± 0.0173` (r² = 0.9999) — which reproduces K02's shipped
0.401(17) exactly, and is the control that says the second moment was added
without disturbing the first.

**Raw output:** `docs/investigations/2026-08-19-k02-chi-ladder.json` — per-rung
r, χ, per-seed values, equilibration drift, and both fits.

**Wall:** 2163 s, CPU. **Assayer:** Claude (Opus), 2026-08-19.
**Protocol:** `docs/assays/PROTOCOL.md`.

---

## 1. Why this fires

`BACKLOG.md` proposed this measurement as *"a live disagreement in the
literature, on data K02 already collects"* — Daido's asymmetric prediction
(γ = 1/4 above K_c, γ′ = 1 below) against Hong et al. 2015's symmetric
γ ≃ γ′ ≃ 1/4 with hyperscaling obeyed — and called it *"a one-line fit"*.

It is a one-line fit. **It is not a test of that disagreement**, and the backlog
entry was wrong about that. §4 below is the estimator audit that says why, and
it is the most important section here.

## 2. Configuration class

Matched to K02's existing, already-assayed class (see
`2026-08-02-k02-literature-crosscheck.md`, which established it):

- **Model**: Kuramoto, deterministic RK4, Lorentzian frequencies, γ = 0.5,
  so K_c = 2γ = 1.0 exactly.
- **Sampling rule**: *regular* / equally-spaced — the deterministic midpoint
  quantiles `(i+½)/N`, matched term for term to Hong et al.'s regular set. This
  is the distinction the K02 assay turned on: the *random* iid class has
  different published exponents, and grading against the wrong one manufactures
  a fake result in either direction.
- **Regime**: N ≤ 4000 = 2¹². Park & Park 2024 put the true asymptote beyond
  N ≳ 2¹⁵, so **every number here is a pre-asymptotic effective exponent**, the
  same way K02's β/ν̄_c = 0.401 is effective against an asymptotic 0.325. The
  applicable published comparison is therefore the pre-asymptotic one.
- **Deviation carried over**: the tail clip at |ω| ≤ 40γ, unchanged from K02 and
  already documented there as an uncontrolled difference.

## 3. Estimator

`χ_c = N · Var_t(r)` evaluated at exactly K_c, per initial condition, over the
long window `critical_coherence` already uses for ⟨r⟩. Combined across initial
conditions by **median**, matching the K-sweep's convention: the per-seed
distribution of `Var_t(r)` is heavy-tailed near criticality, which is why the
sweep does not average it either. The mean is reported alongside so the tail
stays visible (they agree to ~1–4 % here, so the tail is mild at these N).

Measured on the long window rather than the K-sweep's short one on purpose: the
sweep's window is badly insufficient at N = 4000 — the reason
`critical_coherence` exists — and a variance read off a transient is not a
susceptibility.

## 4. Estimator audit — what this number is NOT

**PROTOCOL §4: is our number measuring what their number measures? No.**

Daido and Hong et al. disagree about the exponents of the divergence
`χ ~ |K − K_c|^(−γ)` **on each side** of the transition: γ approaching from
above, γ′ from below. A measurement made *at* K_c has no side. Finite-size
scaling there returns a single number, `γ/ν̄_c`, which is a property of the
combination.

So this measurement **cannot separate an asymmetric exponent pair from a
symmetric one**, and any writeup that says it settles Daido vs Hong is wrong.
Testing the asymmetry needs `χ(K)` fitted separately above and below K_c at
fixed large N with the crossover window excluded — a different and much more
expensive measurement. The fit function says this in its own returned
`measures` field so the caveat cannot be separated from the number.

## 5. Error bars

`chi_sem` per rung is the standard error of a **median** (1.2533·σ/√n, not
σ/√n — reporting a mean's bar on a median's number would understate it). The fit
takes the larger of the regression standard error and the bar propagated from
those per-rung uncertainties, as `fit_critical_exponent` already does.

**The honest weakness is at the cold end of the ladder — the large-N end.**
Relative `chi_sem` runs 1.9 %, 3.9 %, 4.2 %, 11.1 %, 12.3 % across
N = 250…4000, so the fit is dominated by the small-N rungs, and r² = 0.955 (vs
0.9999 for ⟨r⟩) reflects that. The N = 2000 rung also carries the run's largest
equilibration drift at **1.52σ** — inside the tolerance the check uses, but the
least settled point in the ladder, and it sits where the lever arm is longest.

## 6. Verdict: **REDISCOVERED** — consistent with the published symmetric reading

Hong et al. 2015 report γ ≃ 1/4 for the regular set. With their published
β/ν̄_c = 0.39(2) and β = 1/2, that implies ν̄_c ≈ 1.28 and

    γ/ν̄_c ≈ 0.25 / 1.28 ≈ 0.195

against our **0.185 ± 0.040**. Agreement at **0.24σ**. The lab's number is
consistent with the published symmetric reading and is not sharper than it —
our bar (±0.040) is wider than the spread between the candidate published
values, so this is a calibration against the literature, not a discrimination
between literature positions.

**A suggestive observation, deliberately not promoted to a finding.** A γ′ = 1
governing the finite-size amplitude at criticality would imply γ′/ν̄_c ≈ 0.78,
which is nowhere near 0.185. That *looks* like evidence against the asymmetric
reading — but which exponent governs the rounding at K_c is exactly the question
§4 says this measurement cannot answer, and reasoning heuristically about it is
how a calibration becomes a fake discovery. Recorded as an observation with its
own caveat attached; it is a reason to build the two-sided measurement, not a
substitute for it.

## 7. Routing

- The number is **calibration against a published value**, cited to Hong et al.
  2015 for the regular-frequency class. Per PROTOCOL §8 that is a good outcome:
  "we reproduced a real result on a windowsill" is the lab's thesis, and citing
  it is strictly stronger than an unsourced near-miss.
- **No novelty claim.** Nothing here goes public as new.
- Any public phrasing quotes the published γ ≃ 1/4 and reports ours as
  consistent with it, with the pre-asymptotic caveat from §2 attached.
- The backlog entry that proposed this as a test of the Daido/Hong disagreement
  is corrected rather than deleted: the framing was wrong, the measurement was
  worth making anyway, and the correction is the more useful artifact.

## 8. Free wins

1. **The two-sided measurement is now a well-posed next experiment**, and §4
   specifies it: `χ(K)` above and below K_c at fixed large N, crossover window
   excluded. That *would* test the asymmetry. It is expensive and it is real.
2. **The large-N error bars are the binding constraint, not the physics.** More
   initial conditions per rung buys this measurement more than another rung on
   the ladder does — a cheap, specific instruction for the next run.
3. **β/ν̄_c reproduced at 0.4011 ± 0.0173** on an independent run, against the
   shipped 0.401(17). That is a free reproducibility receipt for K02's headline
   number, obtained for nothing because the same run carries both moments.
