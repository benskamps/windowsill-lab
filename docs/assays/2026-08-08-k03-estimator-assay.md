# K03 estimator assay — four ways to measure the wrong thing

**Date:** 2026-08-08 · **Status:** K03 remains OPEN. No exponent is claimed.
**Question:** is the Kuramoto susceptibility exponent asymmetric across K_c?
Daido (1986–1990) says `(γ, γ') = (1/4, 1)`; Hong, Chaté, Tang & Park
(*Phys. Rev. E* **92**, 022122, 2015) say `γ = γ' = 1/4`, on the same
regular/deterministic-quantile Lorentzian this engine uses.

This assay records four estimators that each produced a **plausible, precise,
well-fitted, and wrong** answer, and the design the measurement actually needs.
It exists because the alternative was shipping one of those four numbers.

Every run below: N = 2000, γ_Lorentz = 0.5 so `K_c = 2γ = 1` exactly (K01
confirmed it to 0.07 %), ε = |K−K_c|/K_c on a log grid, RK4 at dt = 0.01.

---

## Attempt 1 — χ = N·Var(r), the K01/K02 estimator

**Result:** γ' = **−0.121**. A negative susceptibility exponent.

**Why it fails.** Below K_c the system is simply incoherent. Measured ⟨r⟩ sits at
**0.0225–0.0251** across a 25× range in ε, against the finite-size floor
1/√N = **0.0224**. It never leaves the floor. A Rayleigh-distributed r with
⟨r²⟩ = 1/N gives N·Var(r) → **1 − π/4 = 0.2146**; measured, χ ran 0.27–0.35 and
varied only **1.3×** across that entire range.

The estimator is flat below K_c by construction. There is no subcritical exponent
in it to find, and the fit was reading noise on a horizontal line.

**Generalisable lesson.** K01 locates the peak and K02 measures finite-size
scaling *at* K_c — both are questions about the critical point itself, where this
estimator is fine. K03 asks about the *approach* from below, which it cannot see.
An estimator inherited from a neighbouring milestone is not thereby validated for
a new question.

---

## Attempt 2 — χ = ∂⟨cos θ⟩/∂h, fitted through the origin

Switching to the linear response to a pinning field h along Θ = 0, with
m = ⟨cos θ⟩ as the conjugate variable. m has zero mean at h = 0 below K_c, which
fixes Attempt 1's floor problem — and the subcritical branch did come out
physical (χ falling 13.7 → 2.0, R² = 0.98).

**Result above K_c:** γ = **−0.306**, **R² = 0.9949**.

**Why it fails.** Above K_c the system is spontaneously ordered, so
m(h=0) = **0.175 ≠ 0**. Forcing the fit through the origin folds that spontaneous
order into the slope. Spontaneous order grows with K, so the fit *manufactured* a
χ that rises with ε — a negative exponent, with an R² of 0.995.

**Generalisable lesson.** R² is not evidence. It measures how well a curve fits,
not whether the quantity being fitted is the one you meant. A high R² on a
fabricated trend is the most dangerous output an estimator can produce, because
every downstream check is happier the wronger it gets.

---

## Attempt 3 — the field was outside linear response

With an intercept added, both branches were re-examined against their own
secants, `(m(h) − m(0))/h`, which must be **constant** if h is small enough.

| branch | h = 0.004 | 0.008 | 0.016 |
|---|---|---|---|
| below K_c | 21.3 | 17.1 | 12.4 |
| above K_c | 14.3 | 10.3 | 7.4 |

Strongly sublinear on both sides: even the smallest field was already saturating.
So **Attempt 2's subcritical γ' = 0.771 ± 0.044 (R² = 0.98) is also void** — it
was a slope fitted across a range where no single slope exists.

**Generalisable lesson.** A linear-response measurement needs a *gate*, not a
hope. The corrected runner refuses a column whose secants disagree by more than
15 % instead of fitting it. On the corrected run that gate passed **1 of 12
columns**, which is the honest verdict: the measurement did not happen.

---

## Attempt 4 — ⟨cos θ⟩ is the wrong observable above K_c

Even with a 4× smaller field ladder and an intercept, the supercritical secant
spread stayed at **2.4–3.0**. That is not a field-strength problem; it is the
wrong observable.

Above K_c the phase ψ of the ordered state is a **free Goldstone mode**. An
arbitrarily small field pins it to Θ = 0, so ⟨cos θ⟩ jumps from `r·⟨cos ψ⟩`
(averaged down by ψ's drift) to ≈ `r`, and then stops. It saturates rather than
responding linearly.

The receipt, at ε = 0.04:

| quantity | value |
|---|---|
| exact spontaneous `r(K) = √(1 − K_c/K)` | **0.1961** |
| measured m(h = 0) | 0.17505 |
| measured m(h = 0.002) | 0.21633 |

m straddles and saturates at r — the field is rotating the crowd, not stretching
it. ⟨cos θ⟩ therefore measures the **transverse** susceptibility, which diverges
trivially and carries no information about γ.

---

## What K03 actually needs

**Two observables, one per branch, because the symmetry differs across K_c.**

| branch | order | conjugate observable | why |
|---|---|---|---|
| below K_c | none; ψ undefined | `χ' = ∂⟨cos θ⟩/∂h` | no floor at h = 0, no Goldstone mode to swamp it |
| above K_c | ordered; ψ free | `χ = ∂⟨r⟩/∂h` (**longitudinal**) | must measure the change in the *magnitude* of order, not its direction |

Plus, on both branches:

1. **An intercept in the fit** — never through the origin.
2. **A linearity gate that refuses** — secants constant to a stated tolerance, per
   column, reported in the receipt.
3. **A per-column field ladder.** One global h cannot serve a χ that ranges over
   ~50× across the grid; h must be chosen so χ·h stays small *everywhere*, which
   needs a cheap pilot pass to estimate χ first.
4. **The finite-size floor respected.** ν̄ ≈ 5/4 for this class puts rounding at
   ε ~ N^(−4/5) = 0.0023 at N = 2000, so the grid must start a decade out
   (ε ≥ 0.02). That constraint held throughout and is not implicated in any of
   the four failures.

Cost estimate: a pilot pass plus a graded pass, both two-branch, ≈ 1 hour of CPU
at N = 2000 — the runs above took 1386 s and 1727 s for single passes.

---

## Why this is written down instead of a number

Four estimators, four confident answers: −0.121, −0.306, +0.771, +1.162. Every
one of them precise, three of them with R² above 0.97, and not one of them a
measurement of the thing K03 asks about.

What caught each was never a statistic. It was a physical sanity check the
estimator could not make on its own: a negative exponent is impossible; a nonzero
intercept means the fit is absorbing something; a drifting secant means no single
slope exists; a response that saturates at the spontaneous order is rotation, not
susceptibility.

That is bug-class 6 (`personal-infra/docs/bug-classes.md`) four times in one
milestone — *an estimator with no positive control returning a confident wrong
number* — and it is the same shape as A03's phantom chirp masses six days
earlier. The class does not stop generating instances because one was fixed.

The engine groundwork this required — an opt-in pinning field on `kuramoto.py`,
`h = 0` bit-identical so K01/K02 are untouched — is real and landed. The exponent
is not, and K03 stays open until the design above is built and gated.
