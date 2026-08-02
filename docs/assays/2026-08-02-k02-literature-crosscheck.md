# K02 — literature cross-check assay

**Date:** 2026-08-02
**Subject:** windowsill-lab PR #85, branch `track/k02-chi-shape`
**Assay type:** novelty certification (Erdős Check discipline) — frontier goal #1
**Stance:** adversarial. Default hypothesis is *rediscovery*. The job is to find the strongest published statement of each K02 element, not to protect the result.

---

## 0. Headline

**K02's physics is right. K02's novelty is nil, and its headline number is off.**

Every substantive element of K02 is published, in the same model, with the same
frequency distribution, the same deterministic sampling rule, and the same
estimator — over a *wider* N range, with *longer* runs and *more* samples than
K02 used. The single most load-bearing citation is:

> H. Hong, H. Chaté, L.-H. Tang, H. Park, *"Finite-size scaling, dynamic
> fluctuations, and hyperscaling relation in the Kuramoto model,"* Phys. Rev. E
> **92**, 022122 (2015), arXiv:1503.06393.

That paper's §IV is K02's experiment. Its Eq. (4.1) is K02's sampling rule. Its
χ is K02's χ. And its §IV A explicitly reports the **regular Lorentzian** case —
K02's exact frequency set — as a confirmation run.

The worse news is quantitative: the literature value of K02's exponent, measured
in K02's own N-window on K02's own system, is **0.39(2)**. K02 reports **0.28**
with no error bar. The gap is not noise; §3.4 identifies the estimator defect
that produces it.

---

## 1. What K02 claims

From the PR #85 body, three sub-claims:

1. **χ = N·Var_t(r) peaks at a fixed CONTROL coupling K_c at every N** (250→4000),
   and the peak is interior in r (partial coherence), standing 2.2×–8.9× above
   both ends of the swept range.
2. **Read in COHERENCE-space, the peak location r\* collapses with N**:
   0.201 → 0.180 → 0.135 → 0.117 → 0.094 across N = 250/500/1000/2000/4000,
   fitted **r\* ∝ N^−0.28**, R² = 0.985.
3. **Therefore Run 01's χ(r) = a·r²(1−r)³ with r\* = 2/5 (N=24) is a finite-size
   artifact, not a law.**

---

## 2. K02's engine is, bit-for-bit, a published configuration

This is the pivot of the whole assay, so it is established first.

### 2.1 The sampling rule is the literature's "regular sampling"

`src/lab/kuramoto.py::lorentzian_frequencies` builds frequencies as

```python
u = (np.arange(n) + 0.5) / n
omega = gamma * np.tan(np.pi * (u - 0.5))
```

i.e. the inverse CDF of the Lorentzian evaluated at the midpoint quantiles
`(i+½)/N`. That is *exactly*:

- **Hong et al. 2015, Eq. (4.1):** `(j − 0.5)/N = ∫_{−∞}^{ω_j} g(ω) dω`,
  described there as *"the 'regular' frequency set {ω_j} with minimal disorder
  among frequencies… generated following a deterministic procedure… The generated
  frequencies are quasi-uniformly spaced."*
- **Park & Park 2024, Eq. (9):** the identical relation, which they call the
  **ES (equally spaced)** case, the `s = ½` member of a one-parameter family
  `x_k = (k − s)/N` (their Eqs. 11–12).

The prompt's framing — that K02 uses "deterministic quantiles (no frequency
disorder!)" and that this is load-bearing — is correct, and the literature not
only knows about it, it is *the* axis along which the modern Kuramoto FSS
literature is organized. The regular/random distinction is the subject of both
papers.

### 2.2 The Lorentzian variant is explicitly published

Hong et al. 2015 §IV A, after presenting the Gaussian regular results:

> *"[We] also considered the regular Lorentzian distribution given by
> g(ω) = γ_ω/[π(ω² + γ_ω²)] with the half-width γ_ω, where the oscillator
> frequency is chosen as ω_j = γ_ω tan[jπ/N − (N+1)π/(2N)] for j = 1,…,N.
> **We find a similar behavior again with ν̄ ≈ 5/4.**"*

Their ω_j simplifies to `γ_ω · tan(π·(2j − N − 1)/(2N))`. K02's simplifies to
`γ · tan(π·(2i + 1 − N)/(2N))`. Substituting `i = j − 1` makes them **identical
term for term**. K02's natural-frequency set is the one in that sentence.

### 2.3 The estimator is the literature's estimator

K02's χ = N·Var_t(r) is, verbatim:

- **Park & Park 2024, Eq. (6):** `χ_N := N lim_{t→∞} [ r̄²_N(t) − (r̄_N(t))² ]`
- **Hong et al. 2015:** `χ(K,N) ≡ N⟨(Δ − ⟨Δ⟩)²⟩ = N(⟨Δ²⟩ − ⟨Δ⟩²)`

Same symbol, same definition, same name ("dynamic fluctuations of the order
parameter"). K02 did not invent this estimator and does not claim to, but the
PR body's care about "estimator definitions and honest-floor discipline"
should be read against the fact that the definition is standard.

### 2.4 The literature's runs strictly dominate K02's

| | Hong et al. 2015 (regular) | Park & Park 2024 (ES) | **K02** |
|---|---|---|---|
| N range | 200 → 12 800 | 32 → 262 144 | **250 → 4 000** |
| time steps | 10⁷ | t_max ≈ 10⁹ | ~10⁵ (1245 s total, 26 K-points × 5 IC × 5 N) |
| samples | 20–100 initial conditions | effective-exponent + CTS analysis | **5 initial conditions** |
| dt | 0.01 (Heun) | 0.05 (RK4, rescaled τ) | 0.01 (RK4) |

K02's 16× lever arm in N is a *subset* of Hong's 64× and Park & Park's 8192×.

---

## 3. Verdict per sub-claim

### 3.1 Sub-claim 1 — "χ peaks at a fixed point in K_c; the peak is interior in r"

**Verdict: REDISCOVERED — and the literature is strictly sharper.**

That χ = N·Var_t(r) peaks at the synchronization transition is the definition of
the susceptibility of this transition and is the organizing object of both cited
papers (Hong 2015 Figs. 1 and 8; Park & Park 2024 Eq. 6). That the coherence at
that peak is interior (0 < r < 1) is immediate: `r(K_c, N)` is small but nonzero
at finite N and rises to the ordered branch above. There is no unpublished
content here.

**More importantly, K02's version of this claim is a weaker statement than the
published one, in a way that matters for sub-claim 2.** Hong et al. 2015 §III
report:

> *"the peak position at K = K_max is **always on the subcritical side** (ε < 0)
> and **approaches** the bulk critical point (ε = 0) as N increases."*

and they treat that drift as a *measurable*, extracting an exponent from it —
their Eq. (3.10):

```
χ_max ~ N^(γ'/ν̄'),     δK_max = |K_max − K_c| ~ N^(−1/ν̄')
```

with a fitted `δK_max ~ N^−0.33` in the random case (their Fig. 2b).

So the literature says the χ peak is **not** at a fixed point in K — it sits
below K_c and converges to it as a power law. K02's "fixed at K_c at every N" is
true only to within K02's resolution (its measured peak couplings 1.011, 1.041,
0.999, 1.007, 0.973 scatter on both sides with std ≈ 0.024, which is larger than
the drift it would need to resolve). This is not an error in K02 — its honest
floor is wide enough to cover it — but the claim should be stated as
*"unresolved at this resolution"* rather than *"fixed."* The mechanism argument
in the PR body leans on the peak being exactly at K_c; it survives the drift
(the drift vanishes as N→∞), but the wording overstates what was measured.

**Assay note on the honest floor.** K02's σ = 3 × local r half-spacing, with the
3 taken from the measured wander of the K-peak, is a defensible construction and
the PR is right that the raw argmax is badly conditioned near a square-root
singularity. That discipline is sound and is *not* the problem. The problem is
downstream, in §3.4.

---

### 3.2 Sub-claim 2 — "r\* collapses as N^−0.28"

**Verdict: REDISCOVERED, and the published value disagrees with K02's number.**

K02's own mechanism argument closes the identification in one line: if χ peaks at
K_c, then the coherence at the peak *is* `r(K_c, N)`. And `r(K_c, N)` is the
single most-studied quantity in the Kuramoto FSS literature — the critical decay
of the order parameter, `R_N(K_c) ~ N^(−β/ν̄_c)` (Park & Park Eq. 7; Hong et al.
Eq. 3.1).

So K02's r\*(N) is the published FSS quantity under a different name, and its
exponent is β/ν̄_c.

#### The literature's exponents

| Sampling | ν̄ | β | **β/ν̄ = the collapse exponent** | Source |
|---|---|---|---|---|
| **Random** (iid draws) | 5/2 | 1/2 | **0.20** (= 1/5) | Hong et al. 2015 §III; established analytically + numerically |
| **Regular / deterministic** (K02's case) | ≈ 5/4 | 1/2 | **0.39(2)** (≈ 2/5) | **Hong et al. 2015, Eq. (4.3)** |
| **Regular / ES, asymptotic** | 1.54(7) ≈ 3/2 | 1/2 | **0.325(15)** (≈ 1/3) | **Park & Park 2024, Eq. (20)** |
| Deterministic, s > ½ | 3/2 | 1/2 | 1/3 | Park & Park 2024, Eq. (32) |
| Deterministic, s < ½ | 1.02(2) | 1/2 | 0.49(1) | Park & Park 2024 §VI B |

Hong et al. 2015 Eq. (4.2)–(4.3), measured directly at K_c over N = 200…12 800
for the regular case:

```
[⟨Δ⟩] ~ N^(−0.39(2)) ,   [⟨Δ²⟩] ~ N^(−0.78(3))     (Eq. 4.2)
⇒  β/ν̄ = 0.39(2)                                    (Eq. 4.3)
```

Park & Park 2024 Eq. (20), the modern revision, from N up to 2¹⁸ with
correction-to-scaling analysis:

```
β/ν̄_c = 0.325(15) ≈ 1/3 ,  thus  ν̄_c = 1.54(7) ≈ 3/2
```

#### Resolving the deterministic-frequency caveat (the prompt's load-bearing question)

The caveat is real and the papers resolve it cleanly. **K02's sampling is the
regular/ES case (s = ½)**, so the applicable published values are 0.39(2)
(Hong) and 0.325(15) (Park & Park) — *not* the random-sampling 0.20, and not the
"classic N^−1/4-ish" folklore the prompt flagged as unreliable (that recollection
does not correspond to any value in either paper; the value nearest 1/4 in this
literature is the *fluctuation* exponent γ ≈ 1/4 for the regular case, a
different quantity entirely — see §3.5).

Park & Park further show the exponents are **sensitive to the sampling detail**:
their family `x_k = (k−s)/N` gives β/ν̄_c ≈ 1/3 for s ≥ ½ but 0.49(1) for
s < ½. K02 sits at s = ½ exactly, so this sensitivity does not create ambiguity
for K02 — but it does mean any future K-track run must state its `s`.

#### Which literature value should K02 be graded against?

**0.39(2)**, not 0.325(15). Park & Park are explicit that the asymptotic value is
reached late:

> *"(β/ν̄_c)_eff for small N remains nearly constant around 0.37, which is
> comparable to the estimate β/ν̄ = 0.39(2) from Ref. [5]. However, it is evident
> that (β/ν̄_c)_eff eventually drifts toward a smaller value approximately 0.325,
> as N increases. This late crossover to the asymptotic scaling regime renders
> the estimation of the FSS exponent exceedingly challenging."*

Their crossover sets in around **N ≳ 2¹⁵ = 32 768**. K02's entire ladder
(250–4000 = 2⁸–2¹²) lies deep in the pre-asymptotic regime where the effective
exponent is ≈ 0.37–0.39.

#### The comparison

| | value | note |
|---|---|---|
| K02 | **−0.28** | no error bar published — **gap** |
| Literature, K02's N-window | **−0.39(2)** | Hong et al. Eq. (4.3) |
| Literature, asymptotic | −0.325(15) | Park & Park Eq. (20); K02 is far from this regime |
| Random sampling (wrong class for K02) | −0.20 | Hong et al. §III |

K02's −0.28 lies **between** the deterministic (−0.39) and random (−0.20)
values, matching neither. Against Hong's ±0.02 it is ~5σ low; K02 published no
error bar of its own, so a symmetric comparison is not possible. **That missing
error bar is the single most consequential reporting gap in K02** — with it, this
line would either be a clean "consistent with published" or a clean "in tension
with published," and it is currently neither.

---

### 3.3 Sub-claim 3 — "Run 01's r²(1−r)³ / r\* = 2/5 is a finite-size artifact"

**Verdict: the conclusion is CORRECT and is a one-line corollary of published
results (category b). The specific form being refuted is Ben's own, so its
refutation is not itself in the literature.**

No published paper tests `χ(r) = a·r²(1−r)³`, because no one plots χ against r
(see §3.5). So the *refutation* is genuinely new work in the trivial sense that
nobody had bothered. But the *content* of the refutation — that no N-independent
r\* can exist — follows immediately from Hong et al. Eq. (4.3): `r(K_c,N) →0` as
a power law, and the peak is at K_c, so the peak's r-coordinate cannot be a
constant. One line, from a 2015 equation.

K02's verdict is therefore correct and its supporting evidence is real, but it is
not a discovery; it is a local confirmation of a decade-old scaling law.

**⚠ A numerical coincidence that must not be allowed to propagate.** Run 01's
`r* = 2/5 = 0.4` is a *coherence value*. Hong et al.'s `β/ν̄ = 2/5 = 0.39(2)` is a
*scaling exponent*. These are different quantities with different dimensions that
happen to land on the same number in this model. Nothing connects them. Any
future writeup that puts both "2/5" figures near each other should say so
explicitly, because the collision is exactly the kind of thing that manufactures
a spurious "deep connection."

---

### 3.4 Why K02 got −0.28 instead of −0.39 — the estimator defect

This is an assay finding, not a literature finding, but it is the actionable one.

K02's −0.28 is **not** a measurement of `r(K_c,N)`. Per the PR body, the raw
argmax was declared unresolvable (bimodal at N=500, |Δ| = 0.069 inside a combined
±0.115), and the collapse was instead read off the **free Beta fit's interior
maximum `p/(p+q)`**. But the PR's own §3 table shows that fit is badly
misspecified:

- free-fit R² is only 0.732–0.817 — the Beta family does not describe χ(r);
- `p` and `q` do not converge, they **track N** (p: 0.50→0.91, q: 2.00→8.74).

`p/(p+q)` is a ratio of two parameters that are themselves drifting with N inside
a form that does not fit. Its N-dependence is therefore a compound of the real
physics *and* the family's misfit drift. The PR is admirably explicit that this
estimator "inherits the Beta family whose exponents are themselves under test" —
this assay's finding is that the inheritance is not a caveat on the number, it is
plausibly the dominant term in it.

**The fix is free and the data already exists.** K02 swept a dense grid around
K_c at every N. The literature-comparable measurement is:

> fit `log⟨r⟩` at `K = K_c` against `log N` — one number, one error bar, directly
> comparable to Hong Eq. (4.3) and Park & Park Eq. (20).

This bypasses the argmax conditioning problem entirely (no peak-finding, no
square-root singularity, no Beta family), because it evaluates at a *known exact*
coupling rather than a *searched* one. It is the single highest-value follow-up
in this assay, and it converts K02 from "a number that matches nothing" to "a
calibration check against a published value."

---

### 3.5 The "χ-peak read in r-space collapses; the fixed point is in K only" framing

**Verdict: UNPUBLISHED as an explicit statement (category c-by-absence), but
category (b) in substance — derivable in one line from published results.**

Searches run, all returning nothing that states this:

1. `Kuramoto susceptibility peak plotted against order parameter r instead of coupling K finite-size artifact "critical coherence"`
2. `"order parameter" susceptibility maximum "as a function of" coherence r Kuramoto "edge of synchronization" optimal partial coherence variance peak`
3. `"finite-size" Kuramoto "r*" peak location coherence axis reparametrization susceptibility "no N-independent" critical order parameter value`
4. `Hong Chaté Park Tang finite-size scaling Kuramoto model order parameter exponent` (returned the FSS corpus; none of it reparametrizes to r)

None of the retrieved papers — Hong et al. 2015, Park & Park 2024, Hong-Chaté-
Park-Tang 2016 (correlated disorder, *Chaos* 26, 103105), Coletta et al. 2017,
the higher-order-interaction FSS line (arXiv:2405.16049, 2506.23181) — plots χ
against r. Every one of them plots χ against K or ε = K − K_c.

**The honest reading of that negative is not "novelty."** It is that plotting the
susceptibility against the *response* variable rather than the *control* variable
is something specialists do not do, because it is a change of variables that
throws away the thing you control and introduces a singular Jacobian
(`dr/dK → ∞` at K_c⁺, which is precisely the conditioning problem K02 hit and
correctly diagnosed). The statement "the fixed point is in K, not in r" is, to a
practitioner, closer to a definition than a finding. It is unpublished the way
"3 is not an even number" is unpublished.

Where it *does* have value: as **pedagogy**, and as a correction to a specific
error (Run 01's) that a non-specialist can easily make. That is a real
contribution to the windowsill-lab's own project, and it is worth writing down.
It is not a contribution to the Kuramoto literature.

---

## 4. Methodological flags for the K-track (not literature findings)

Two engine-level notes surfaced by comparing K02's setup to the published ones.

**4.1 The tail clip is a deviation from the published configuration.**
`kuramoto.py` clips frequencies at `|ω| ≤ 40γ` (≈1.6% of the population). Hong et
al.'s regular Lorentzian is unclipped. The clip preserves `g(0)` and therefore
`K_c` exactly — that reasoning in the module docstring is correct — but it
collapses ~1.6% of the population onto **exactly two degenerate frequencies**
at ±40γ. Park & Park's analysis (their Appendix, Eq. 27) attributes the
finite-size correction partly to *"a few oscillators that break the equally
spaced feature"* and concludes that **running oscillators cannot be neglected**
and *"their contributions to R_N may dominate the finite-size effects."* K02's
clip manufactures a large degenerate block inside exactly that running
population. This is unlikely to move K_c, but it is not obviously neutral for
β/ν̄_c, and it is an uncontrolled difference from the papers K02 would be
compared against. Worth a negative control: rerun one rung at clip = 40γ vs 100γ
vs unclipped-with-smaller-dt and check r(K_c,N) is unchanged.

**4.2 Park & Park avoided the Lorentzian for precisely K02's reason.**
Their §II opens by noting that under regular sampling an unbounded-support g
gives extreme frequencies — at N = 2¹⁸ the largest is `> 10⁵` — *"which is hard
to be controlled in numerical integrations,"* and they switch to a compact-support
parabolic `g(ω) = (3/2)(1 − 4ω²)Θ(1 − 2|ω|)` to avoid it. K02 met the same wall
and answered it with clipping. Both are legitimate; they are different answers,
and K02's makes it *less* comparable to Park & Park and *more* comparable to Hong
et al. (who kept the Lorentzian). Worth stating explicitly in any future writeup.

**4.3 The fluctuation exponent γ is a free win K02 left on the table.**
K02 measured χ on a dense grid at five N. Hong et al. report `γ ≃ γ' ≃ 1/4` for
the regular case and `≃ 1` for the random case, with hyperscaling `γ = ν̄ − 2β`
**obeyed in the regular case and violated in the random case** (their Eq. 20/23).
Daido's perturbation theory (Prog. Theor. Phys. **75**, 1460 (1986); J. Phys. A
**20**, L629 (1987); Prog. Theor. Phys. **81**, 727 (1989); J. Stat. Phys. **60**,
753 (1990)) predicted the asymmetric `γ = 1/4` / `γ' = 1`, which Hong et al.
contradict with `γ = γ'`. **That is a live, checkable disagreement in the
literature, in exactly K02's regime, measurable with K02's existing data** —
`χ_c(K_c) ~ N^(γ/ν̄_c)` is a one-line fit on data already collected. This is a far
better K03 than another pass at the Beta form.

---

## 5. Summary table

| K02 sub-claim | Verdict | Citation |
|---|---|---|
| χ = N·Var_t(r) is the right susceptibility | **REDISCOVERED** (standard) | Hong 2015 χ def.; Park & Park 2024 Eq. (6) |
| χ peaks at/near K_c, interior in r | **REDISCOVERED**, literature sharper | Hong 2015 §III, Eq. (3.10) — peak is subcritical and drifts as N^(−1/ν̄') |
| r\* = r(K_c,N) collapses with N | **REDISCOVERED** | Hong 2015 Eq. (4.2)–(4.3); Park & Park 2024 Eq. (7), (20) |
| exponent −0.28 | **DISAGREES with published −0.39(2)**; no K02 error bar | Hong 2015 Eq. (4.3) |
| deterministic sampling matters | **REDISCOVERED** — it is the field's organizing axis | Hong 2015 §III vs §IV; Park & Park 2024 §VI |
| K02's exact engine (regular Lorentzian) | **PUBLISHED VERBATIM** | Hong 2015 §IV A |
| r²(1−r)³ / r\*=2/5 is a finite-size artifact | **CORRECT**; one-line corollary of Hong Eq. (4.3) | — |
| "peak collapses in r-space; fixed point is in K only" | **UNPUBLISHED as stated**, but derivable-in-one-line; absence reflects that nobody reparametrizes to r | 4 empty searches, §3.5 |

**Net novelty: none.** K02 is a competent, honestly-reported local reproduction of
Hong et al. 2015 §IV, at smaller N, with a worse estimator for the headline
exponent, refuting a form that only Ben's own earlier run proposed.

**That is not a bad outcome.** K02 was designed to be able to say no, and it said
no correctly. What it should not do is present the collapse as a finding.

---

## 6. Recommended reframe for `brokenbranch.dev/fireflies/`

The current line — *"χ = r²(1−r)³ peaks at r = 0.4"* — is wrong twice: the form
does not fit (K02 §3: negative R² against the pinned exponents), and 0.4 is a
property of a 24-oscillator population, not a constant.

**Recommended one-sentence replacement:**

> **Synchrony is jitteriest right at the tipping point — and the amount of
> togetherness at that tipping point isn't a magic number: it fades as the crowd
> grows (roughly as N^−1/3), so the "40%" we first measured was a fact about
> 24 fireflies, not about fireflies.**

Why this is faithful to both:

- *"jitteriest right at the tipping point"* — the susceptibility peak at the
  critical coupling, true in K02 and in Hong et al.; avoids claiming the peak is
  *exactly* at K_c, which the literature says it is not at finite N.
- *"isn't a magic number… fades as the crowd grows"* — K02's actual, correct
  finding, and Hong Eq. (4.3).
- *"roughly as N^−1/3"* — cites the literature's exponent range (0.325–0.39)
  rounded to a fraction a lay reader can hold, rather than K02's unreplicated
  −0.28. **Do not publish −0.28** until §3.4's direct `r(K_c,N)` fit is run.
- *"a fact about 24 fireflies"* — names the finite-size mechanism in plain
  language, which is the whole pedagogical point.

If a citation line is wanted beneath it: *"(the scaling of coherence at the
transition with population size is a known result — Hong, Chaté, Tang & Park,
Phys. Rev. E 92, 022122 (2015))."* Citing it is strictly better than not: it
turns a weak novelty claim into a strong "we reproduced a real result on a
windowsill," which is the lab's actual thesis.

---

## 7. Sources (pinned)

1. **H. Hong, H. Chaté, L.-H. Tang, H. Park**, *"Finite-size scaling, dynamic
   fluctuations, and hyperscaling relation in the Kuramoto model,"*
   **Phys. Rev. E 92, 022122 (2015)**, arXiv:**1503.06393**.
   - §IV, Eq. (4.1): regular sampling `(j−0.5)/N = ∫_{−∞}^{ω_j} g dω` — K02's rule.
   - §IV A: **regular Lorentzian**, `ω_j = γ_ω tan[jπ/N − (N+1)π/(2N)]` — K02's
     exact frequency set — *"we find a similar behavior again with ν̄ ≈ 5/4."*
   - Eq. (4.2)–(4.3), Fig. 6: `[⟨Δ⟩] ~ N^−0.39(2)` ⇒ **β/ν̄ = 0.39(2)**, ν̄ ≈ 5/4.
   - Eq. (3.10), Fig. 2: `χ_max ~ N^(γ'/ν̄')`, `δK_max ~ N^(−1/ν̄')`; peak is on
     the **subcritical** side and approaches K_c as N grows.
   - Fig. 8: χ vs ε for the regular distribution, N = 200…12 800.
   - Random case: ν̄ = 5/2, γ = γ' ≃ 1; regular: ν̄ ≃ 5/4, γ = γ' ≃ 1/4.
     Hyperscaling `γ = ν̄ − 2β` obeyed (regular) / violated (random).

2. **S.-C. Park, H. Park**, *"Finite-size scaling of the Kuramoto model at
   criticality,"* **Phys. Rev. E 110, 034216 (2024)**, arXiv:**2406.18904v2**.
   - Eq. (6): `χ_N := N lim_{t→∞}[ r̄²_N − (r̄_N)² ]` — K02's estimator.
   - Eq. (7): `R_N ~ N^(−β/ν̄_c)` at ε = 0.
   - Eq. (9): regular sampling; Eqs. (11)–(12): the `s`-family, `s = ½` = ES case.
   - **Eq. (20): β/ν̄_c = 0.325(15) ≈ 1/3, ν̄_c = 1.54(7) ≈ 3/2** (ES case).
   - §IV: effective exponent ≈ 0.37 at small N, crossing over to 0.325 only for
     N ≳ 2¹⁵; *"this late crossover… renders the estimation exceedingly challenging."*
   - Eq. (32): s > ½ ⇒ `R_N ≈ ((2s−1)/K_c²)^{1/3} N^{−1/3}`; §VI B: s < ½ ⇒
     β/ν̄_c = 0.49(1).
   - §II: Lorentzian avoided under regular sampling because extreme frequencies
     (`> 10⁵` at N = 2¹⁸) are *"hard to be controlled in numerical integrations."*
   - Eq. (27) + Appendix: finite-size correction traced to edge oscillators and
     *"a few oscillators that break the equally spaced feature"*; running
     oscillators *"may dominate the finite-size effects."*

3. **H. Daido**, Prog. Theor. Phys. **75**, 1460 (1986); J. Phys. A **20**, L629
   (1987); Prog. Theor. Phys. **81**, 727 (1989); **J. Stat. Phys. 60, 753
   (1990)** — *"Intrinsic fluctuations and a phase transition in a class of large
   populations of interacting oscillators."* Origin of the finite-size
   order-parameter-fluctuation problem; perturbative prediction `γ = 1/4`
   (supercritical) and `γ' = 1` (subcritical), on the **regular** frequency
   distribution. Contradicted by Hong et al. 2015, who find γ = γ'. Live
   disagreement — see §4.3.

4. **H. Hong, H. Chaté, H. Park, L.-H. Tang**, *"Correlated disorder in the
   Kuramoto model,"* **Chaos 26, 103105 (2016)**, arXiv:1605.07933. Extends the
   regular/random axis to correlated disorder; consulted, contains no r-space
   reparametrization.

5. Earlier FSS line establishing ν̄ = 5/2 for random sampling: H. Hong, H. Park,
   M. Y. Choi, Phys. Rev. E **72**, 036217 (2005); H. Hong, H. Chaté, H. Park,
   L.-H. Tang, Phys. Rev. Lett. **99**, 184101 (2007); H. Hong, H. Park, L.-H.
   Tang, Phys. Rev. E **76**, 066104 (2007); L.-H. Tang, J. Stat. Mech. P01034
   (2011); H. Hong, J. Um, H. Park, Phys. Rev. E **87**, 042105 (2013).

**Searches that returned nothing** (listed so the negative is checkable) — see §3.5
for the four query strings. No source found that plots or discusses the
susceptibility as a function of the order parameter r rather than the coupling K.
