# U-K01 — K03 was measuring its window, not its exponent

**2026-08-24 · the first reach test in the catalogue of unknowns**

## What was found

The 2026-08-23 K03 run carries `status: fail`, because the subcritical branch
lost four of seven columns to the linearity gate and could not be fitted. Under
that failure, unread, sat a clean supercritical measurement:

> **γ = 1.071 ± 0.018**, six columns, R² = 0.9989

Both Daido and Hong predict **γ = 0.25** supercritical. The measurement is ~46σ
from the value *both* published claims share, and nothing on any surface said
so — the receipt was filed as a failure and the number went unlooked-at.

Two readings fit. The exciting one is that the engine contradicts two papers.
The likely one is that ε ∈ [0.02, 0.32] never entered the critical scaling
window, and χ ~ ε⁻¹ is simply the generic mean-field response.

The reach test decides between them for free.

## The test

A genuine asymptotic power law has a **constant local slope**. Fit the slope
between each adjacent pair of committed columns and look:

| ε window | local γ |
|---|---|
| 0.0317 → 0.0504 | **0.979** |
| 0.0504 → 0.0800 | 1.034 |
| 0.0800 → 0.1270 | 1.060 |
| 0.1270 → 0.2016 | 1.100 |
| 0.2016 → 0.3200 | **1.195** |

Monotone drift of **20.1%** across the window, **falling as ε shrinks** — the
signature of a crossover being watched from outside it.

**Verdict: out-of-reach.** The 1.071 on the record is not γ. It is an average
over a crossover, and where it lands is a fact about where the grid was placed.
It cannot be compared to Daido's 0.25, to Hong's 0.25, or to anything else.

Cost: milliseconds, on bytes already committed. No new simulation.

## Two things this changes

**1. The supercritical branch was never going to settle anything.** Daido and
Hong predict the *same* γ = 0.25 above K_c. Every bit of discriminating power
lives in γ′ below, where the gap is Δγ′ = 0.75. K03 has been measuring its
cleanest numbers on the one branch that carries no information about the
question — and `_verdict` reports a combined σ-distance over both, which inflates
the apparent separation with a term identical in both claims. The *ranking* is
safe (adding an equal term under `hypot` is monotone), but the σ values overstate
how much was learned.

**2. The blocker is the window, not the precision.** The instrument achieved
stderr 0.0177 on a branch it could measure. Against Δγ′ = 0.75 that is a **42σ
separation** — enormous. This box has ample resolving power to settle a
thirty-year disagreement in the literature; what it does not have is a grid
close enough to K_c, and four subcritical columns that survive the gate.

So the next spend is **not** a larger-N hero run. A larger N inside the same
window buys a more precise artifact. The next spend is a lower ε floor and a
diagnosis of why the innermost columns fail their secant test.

## Why this is filed as a success

An `out-of-reach` verdict is the catalogue working. It cost milliseconds and it
cancelled a GPU-hours run that would have produced a confident wrong number —
which is precisely the failure mode M14 nearly shipped in July, and the reason
the feasibility test now runs *before* the attempt rather than after it.

The unknown is recorded as `charted`, `reach: out-of-reach`, with the drift
measurement as its evidence and a named next step. It is not closed. It is
*mapped* — which is the difference this catalogue exists to make.

## The honest limits

- **The drift tolerance (10%) is a judgement, not a derivation.** It is loose
  enough that a real power law with normal scatter passes and tight enough that
  this window fails at 20%. A borderline case would need a better criterion.
- **Pairwise slopes on six columns are noisy.** The monotonicity across all five
  gaps is what makes the drift believable, not any single pair.
- **This says nothing about whether Daido or Hong is right.** It says K03 has not
  yet been in a position to have an opinion, and that the version of the question
  worth asking is U-K02.
