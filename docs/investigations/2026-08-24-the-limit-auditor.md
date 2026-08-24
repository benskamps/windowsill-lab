# The limit auditor — an instrument that audits instruments

**2026-08-24 · built after the same defect was found twice in one day**

## The defect has a shape

Half of what this lab reports is defined as a **limit**: a susceptibility at
h → 0, a peak frequency at grid spacing → 0, an exponent at L → ∞, an
equilibrium average at t → ∞. Every one is computed at a single convenient
finite value of that control. Until today, not one had been checked against the
limit it claims to be.

Found the hard way, hours apart:

- **K03** estimated χ from one field ladder at a fixed target response. Bias:
  **11–33%** — and, fatally, it *shrank with ε*, so it did not cancel in the
  power-law fit, it tilted it. The reported γ = 1.064 was never a measurement.
- **A02** refines a periodogram peak by parabolic interpolation on a grid fixed
  at `OVERSAMPLE = 10`, with a docstring saying this "only has to be fine
  [enough]" — an assumption, never tested.

Two milestones, two subsystems, one bug class. That is what made it worth
building an instrument instead of applying a second patch.

## The question it insists on

*Is it converged?* is the wrong question. Nothing is exactly converged, and a
machine that asks it generates nitpicks forever. The right question is:

> **Is the residual bias smaller than the tolerance this result is graded at?**

By that standard the two findings above are **opposite verdicts from identical
defects**, and any judgement that cannot separate them is worthless.

## A02, audited

Six committed light curves, swept across oversample 5 → 80:

| TIC | bias (ppm) | Rayleigh tolerance (ppm) | swept range (ppm) | verdict |
|---|---|---|---|---|
| 224285325 | 0.0 | 2,006 | 0.6 | harmless |
| **159717514** | **42.2** | **21,124** | **149.0** | harmless |
| 233310793 | 0.1 | 5,023 | 4.5 | harmless |
| 321818578 | 0.6 | 8,619 | 5.4 | harmless |
| 357132618 | 0.4 | 3,147 | 1.6 | harmless |
| 81709032 | 0.1 | 4,448 | 3.4 | harmless |

The defect is **real and measurable** — TIC 159717514 moves 149 ppm across the
sweep, monotonically, converging to 0.5663302 d while the shipped default
reports 0.5663541 d. And it is **harmless**: the worst residual is **0.20% of
its own grading tolerance**. A02's promoted results stand, and now they stand on
a number instead of an assumption.

## What it took to make the auditor trustworthy

Three separate defects *in the auditor itself*, each caught by a synthetic with
a known limit and by nothing else:

1. **Extrapolating by swapping h^p for h^(p+1) instead of nesting.** Reported
   perfectly linear data as undetermined. The sufficiency check has to *add* a
   term to the same model, never trade one power for another.
2. **Judging disagreement against the value's magnitude rather than its swept
   range.** A value of 42 drifting by 6 is being extrapolated over 6; calling a
   0.6 disagreement "1.4% of 42" hides that it is 10% of everything the
   extrapolation exists to remove. This passed an order-8 bias as converged.
3. **Demanding a determined extrapolation from data already flat to 0.1 ppm.**
   Reported the estate's *most* converged results as "undetermined" — exactly
   backwards. Fixed by the rule that if an estimator moves less than the
   tolerance across the entire sweep, the limit cannot matter.

There is also a check that adding a term cannot provide on its own: **drop the
control furthest from the limit and refit.** A bias of order 8 fitted by degrees
3 and 4 is fitted badly by *both, in the same way*, so they agree and the sweep
reports false confidence. A sound extrapolation barely moves when the point
least entitled to carry it is removed; a fictional one lurches.

## Why this is the useful artifact and not the K03 result

A finding is one number. This is the thing that finds them, and it can be
pointed at any estimator in the estate that takes a step size, a probe
amplitude, a system size, or a burn-in length.

Its most valuable output today was a **negative**: a promoted milestone checked
against a newly-discovered defect class and cleared, with the margin stated. A
lab that can only confirm its own results is not auditing them — and one that
cannot clear them is just generating doubt.

## Honest limits

- The auditor judges **one control at a time**. An estimator biased in two
  controls jointly (grid spacing *and* burn-in) will pass each sweep and still
  be wrong.
- `ORDER_TOL = 0.05` is a judgement, not a derivation.
- It can only ever be validated on synthetics, because real data has no true
  value. Every claim it makes about a real estimator inherits that.
