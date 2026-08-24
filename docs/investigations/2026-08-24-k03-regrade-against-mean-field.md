# K03 regrade — what was the susceptibility actually measuring?

**2026-08-24 · a regrade of `reports/receipts/run-2026-08-23-2216-k03.json`, which nobody had read**

## Why this exists

The receipt is filed `status: fail`, and the label is accurate but incurious: the
subcritical branch got 3 of 4 columns through the linearity gate, one short, so
no exponent was claimed. What nobody looked at is that the **supercritical branch
passed 6 of 7 and returned γ = 1.071 ± 0.018 at R² = 0.9989** — a clean number
agreeing with neither Daido's 1/4 nor Hong's 1/4.

A clean number that matches nobody is either a result or an artifact, and there
is a cheap way to tell: compare it to the response the model has with **no
critical physics in it at all**. N=2000 Kuramoto on a regular Lorentzian has an
exact mean-field linear response below threshold, χ_MF = 1/(K_c − K), with no
free parameter and nothing to fit.

## The measurement

Below K_c, against the exact form:

| ε | K | measured χ | mean-field 1/(K_c−K) | ratio |
|---|---|---|---|---|
| 0.0800 | 0.9200 | 12.082 | 12.500 | **0.967** |
| 0.2016 | 0.7984 | 4.894 | 4.961 | **0.987** |
| 0.3200 | 0.6800 | 3.195 | 3.125 | **1.022** |

**Every surviving subcritical column reproduces the exact mean-field response to
1–3 %, across a 4× range in ε.** The four refused columns were all refused for
`nonlinear-secants` — the gate working.

## What that means, stated narrowly

Below the transition this instrument is measuring **the deterministic N→∞ linear
response**, not a fluctuation susceptibility. χ ~ ε⁻¹ is what 1/(K_c−K) *is*;
recovering it is a calibration, not an exponent. Daido and Hong disagree about
the *fluctuation* susceptibility's exponent, and a quantity that lands on the
mean-field curve to 1 % is not carrying that disagreement.

So the honest subcritical verdict is not γ' = 1. It is: **this observable cannot
resolve Daido vs Hong on the subcritical branch, and the reason is measurable
rather than suspected.** `TRACKS.md` names exactly that as a legitimate arrival
for Track K — "including the verdict *this instrument cannot resolve it*".

## What this pass does NOT settle

The supercritical branch. Above K_c the right comparison is the longitudinal
response ∂r/∂h at fixed K, and the number computed here was ∂r/∂K — the **wrong
observable**. Its ratios (4.88 → 1.88, drifting with ε) are therefore not
evidence of anything and are recorded only so nobody re-derives them believing
otherwise. Settling γ = 1.071 needs the self-consistent response *with a field*,
which is a few hours of work and the obvious next step.

## Cost

Zero new simulation. The run was already on disk; this is arithmetic over a
receipt that had been sitting unread for a day.
