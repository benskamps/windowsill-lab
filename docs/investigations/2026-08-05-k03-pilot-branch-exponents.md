# K03 pilot — is the susceptibility exponent asymmetric across K_c?

**Date:** 2026-08-05 · **Status:** pilot, not a milestone. No claim promoted.
**Artifact:** `scripts/k03_pilot.py` (this run's exact script), receipt inline below.

## The question

χ ~ |K − K_c|^(−γ) above the transition, ^(−γ') below.

| | γ (above) | γ' (below) |
|---|---|---|
| **Daido** (1986–90) | 1/4 | **1** |
| **Hong, Chaté, Tang & Park 2015** | ≈1/4 | **≈1/4** |

Both statements are about the *regular* (deterministic-quantile) Lorentzian. The
2026-08-02 assay (§2.2) established that this engine's frequency set is Hong's
Eq. (4.1) term for term, so the configuration class matches and the comparison is
legitimate — the gate PROTOCOL.md §3 turns on.

**This is a reproduction, not a novelty claim.** Hong et al. already published
γ = γ'. No assay is owed.

## Why K02's data could not answer it

The seal of 2026-08-02 expected γ' to fall out of "a one-line fit on K02's data."
It does not:

- K02's coupling grid carries **12 dense points above K_c and 4 below**. The
  branches are not comparably resolved.
- Those 4 are non-monotonic (χ = 1.539 at ε = 0.01 but 1.934 at ε = 0.02, N=4000)
  — single-seed noise there is comparable to signal.

K03 needs its own two-sided run. That is what this pilot is.

## Feasibility check, done first

Finite N rounds the transition over ε ~ N^(−1/ν̄). Hong §IV A gives **ν̄ ≈ 5/4**
for this exact class, so rounding sits at ε ≈ 0.0023 at N = 2000 and a grid
starting at ε = 0.02 is a decade clear of it. A scaling window exists.

(Had ν̄ been 5/2 — the *random*-sampling value a casual search surfaces first —
rounding would be ε ≈ 0.048 and the entire grid would sit inside it. The
measurement would be impossible and this pilot should not have been run. Matching
the configuration class decided whether the experiment was worth doing at all.)

## Setup

Symmetric log-spaced ε ∈ {0.02, 0.03, 0.045, 0.065, 0.10, 0.15, 0.22, 0.32} on
both branches (16 couplings), γ_Lorentz = 0.5 so K_c = 1 exactly, RK4 at dt = 0.02,
t_burn = 500, t_measure = 1000, 4 initial conditions, N ∈ {1000, 2000}.
χ = N·Var_t(r), the same estimator K01/K02 use.

Each point's measurement window is run in halves and the half-to-half change is
reported as **drift**, so a point still equilibrating is visible rather than
silently fitted.

## Result

| N | γ (above) | R² | max drift | γ' (below) | R² | max drift |
|---|---|---|---|---|---|---|
| 1000 | +0.189 | 0.989 | 15% | +0.167 | 0.798 | **70%** |
| 2000 | +0.182 | 0.957 | 15% | −0.067 | 0.721 | **39%** |

The fitted exponents below K_c are unstable — they change sign between the two
population sizes, and the fit quality is poor. **The branch exponents are not
measured to any useful precision by this pilot.**

But the discrimination does not need precision, because the two theories differ by
a factor of eight. Over this grid's 16× range in ε:

| | predicted χ rise | measured, N=1000 | measured, N=2000 |
|---|---|---|---|
| above K_c (γ = 1/4, **both** theories) | **2.00×** | 1.76× | 1.68× |
| below K_c, **Daido** (γ' = 1) | **16.0×** | — | — |
| below K_c, **Hong** (γ' ≈ 1/4) | **2.00×** | — | — |
| below K_c, **measured** | — | **1.59×** | **0.86×** |

**The above-branch is the positive control.** Both theories agree there, it
predicts 2.00×, and the instrument returns 1.76× and 1.68×. So the method does
detect a divergence of this size — it is not flattening everything it sees.

Applying that same method below K_c, where Daido predicts **16×**, returns
**1.59× and 0.86×**.

## What can be said

1. **Daido's γ' = 1 is not what this instrument sees.** It is an order-of-magnitude
   miss, not a marginal one.
2. **The direction of the known systematic cannot rescue it.** A finite window
   under-samples the slowest fluctuations, which are nearest K_c — so the bias
   *flattens* the measured divergence, and it is strongest exactly at small ε.
   That bias could turn a true 16× into something smaller. But turning 16× into
   0.86× requires an ~18× underestimate at ε = 0.02, where the measured drift is
   33%. Not plausible.
3. **Qualitatively consistent with Hong**: both branches small and comparable, no
   strong asymmetry.

## What cannot be said

- **Not the exponents.** Both branches read low — γ ≈ 0.18 against an expected
  0.25 — and γ' is unstable in N. This does not measure γ or γ' and does not
  reproduce Hong's 1/4 quantitatively.
- **Not a resolution of the disagreement.** Disfavouring γ' = 1 with a 4-seed
  pilot at N ≤ 2000 is not the same as adjudicating a published dispute.

## What a real measurement needs

The blocker is equilibration below K_c: **21–39% half-to-half drift at
t_measure = 1000**, versus ≤15% above. Relaxation below the transition is slower
than this window resolves, and the K02 revision found the same thing at K_c.

To reach ≤5% drift, t_measure needs roughly 10–50× (drift falls between 1/√t and
1/t). Cost is linear in t and in N. This pilot was 42 min for two rungs; a
run with adequate windows is **~10–40 GPU-hours**, i.e. a campaign job on loam,
not an interactive one.

Second requirement: more initial conditions. Four is enough to see a factor of
ten, nowhere near enough to separate 0.25 from 0.18.

## Reproduce

```
python scripts/k03_pilot.py out.json
```

Deterministic given the seeds {42, 7, 1234, 99}; frequencies are the engine's
inverse-CDF quantile draw, not a generator, so the frequency set carries no
sampling noise.

## Receipt

| N | wall | above: χ(0.02) → χ(0.32) | below: χ(0.02) → χ(0.32) |
|---|---|---|---|
| 1000 | 864 s | 0.472 → 0.269 | 0.349 → 0.219 |
| 2000 | 1651 s | 0.549 → 0.327 | 0.287 → 0.334 |

Full per-point χ and drift in the run JSON.
