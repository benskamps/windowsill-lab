# K03 at h→0 — the correction worked, and it cost more than it bought

**2026-08-24 · 3.93 GPU-hours · both branches, N = 200,000, 9-rung ladders**

## What was fixed

The h-scan established that K03's single-ladder χ carries a saturation bias
that *shrinks with ε* — so it does not cancel in a power-law fit, it tilts it.
This run replaced the estimator: fit the response itself, take the linear
coefficient, check sufficiency by adding a term.

It worked, and the bias was as large as advertised:

| branch | columns converged | bias removed |
|---|---|---|
| supercritical | **7 of 8** | +9.1% → **+44.0%**, monotone toward K_c |
| subcritical | 4 of 8 | mixed sign — see below |

The supercritical branch is measured across the full range for the first time:
**γ = 1.044 ± 0.020**, R² = 0.998. Both Daido and Hong predict **0.25**. That is
**39σ from a value the two papers agree on**, with the systematic that could
have explained it now removed.

## What broke

**The drift test still refuses both branches.**

```
above:  local γ = 1.089, 0.927, 1.026, 1.135, 1.102, 1.204    span 25.7%
below:  local γ = 1.141, 1.173, 0.975                          span 18.1%
```

And the character of the supercritical drift changed: it was a clean monotone
0.96 → 1.19 before the correction, and it is now **scatter around ~1.08**. The
correction removed a systematic tilt and put noise in its place.

**The subcritical branch got worse, and that is the finding worth keeping.**
Only four of eight columns converged, and the rejected ones carry *negative*
bias — the h→0 value came out **smaller** than the single-ladder slope. That is
not saturation, which can only push the other way. It is a cubic fit chasing
noise on low-χ outer columns, where the response is small enough that the
curvature terms have nothing to fit but scatter.

## The lesson: the estimator costs statistics

The h→0 estimator is strictly better where saturation is large — inner columns,
big χ — and strictly worse where saturation is negligible — outer columns, small
χ. Which is exactly where the previous run's clean plateau came from:
γ′ = 0.9829 ± 0.0053, constant to 5.4% across ε ∈ [0.03, 0.32].

So one bias was traded for another, and the only reason that is visible is that
the estimator carries its own convergence check and refused four columns instead
of returning confident numbers for them.

**The fix is a hybrid decided per column**, and the instrument to decide it was
built the same day: `convergence.py` asks precisely *is the bias larger than the
tolerance this result is graded at*. Use h→0 where saturation matters; use the
single ladder where it does not. Neither estimator is right everywhere, and
nothing forced a choice between them except not having asked.

## What survived three independent analyses

Across a window artifact, critical slowing down, and now a corrected saturation
bias, one observation has not moved:

> **This engine measures γ ≈ γ′ ≈ 1 everywhere it can reach — generic
> mean-field — and matches neither paper.**

If the anomalous 1/4 exponent exists on this frequency class, it lives closer to
K_c than ε = 0.005, which is a statement about **both** papers' windows rather
than about either of their answers.

## U-K02 is not settled

It is far better instrumented than it was this morning and it is still open.
39σ dressed up as a discovery would be the worst possible use of a day that
found three real instrument defects.
