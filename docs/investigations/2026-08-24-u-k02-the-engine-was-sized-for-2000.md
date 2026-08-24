# U-K02 — a thirty-year disagreement, blocked by an engine sized for N = 2,000

**2026-08-24 · the second reach test, and the first one that came back yes**

## The question

Daido (1986, 1990) and Hong, Chaté, Tang & Park (2015) contradict each other on
the susceptibility exponents of the Kuramoto model on the regular
frequency class: **γ = 1/4, γ′ = 1** against **γ = γ′ = 1/4**. The 2026-08-02
assay established this engine's frequency set is that class term for term, so
the disagreement is measurable here rather than merely readable.

U-K01 had just established that K03 could not touch it. This asks what it would
take — and asks *before* spending anything.

## Four measured facts, in order

**1. The supercritical branch was never going to settle it.** Both papers
predict the same γ = 1/4 above K_c. Every bit of discriminating power lives in
γ′ below, where the gap is Δγ′ = 0.75. K03 has been getting its cleanest
numbers on the one branch that carries no information about the question.

**2. Precision was never the blocker.** The instrument achieved stderr 0.0177 on
a branch it could measure. Against a 0.75 gap that is a **42σ separation** —
enormous.

**3. The refusals are noise, not saturation.** A saturating response has secants
that *fall monotonically*; the refused subcritical columns rise and scatter:

| ε | secants | verdict |
|---|---|---|
| 0.0200 | 36.3, **65.9**, 39.0 | refused |
| 0.0317 | 15.3, **46.7**, 34.0 | refused |
| 0.0504 | 8.3, 19.2, 22.2 | refused |
| 0.0800 | 12.8, 12.8, 10.4 | **passed** |
| 0.1270 | 9.7, 6.1, 6.4 | refused |

Note the fourth and fifth rows: **ε = 0.127 was refused while ε = 0.08, closer
to K_c, passed.** That non-monotonicity is the signature of a threshold applied
to a noisy statistic — so the three columns that survived did so partly on the
draw, and cannot carry γ′ either. The subcritical branch was not merely
under-measured; it was un-measured, including where it appeared to succeed.

**4. The noise has a scaling law, and it names the cause.** Converting each
column's secant spread into an implied noise on ⟨cos θ⟩ and fitting against ε:

> **noise ~ ε^(−0.76)**

That is critical slowing down. The correlation time diverges approaching K_c
while `T_MEASURE` stayed pinned at 2000 for every column, so the same wall-clock
buys steadily fewer independent samples exactly where the measurement matters
most. Holding noise constant requires `T_MEASURE ~ ε^(−1.53)`, and nothing in
the design budgeted for it.

## The lever

The error on a subcritical observable falls as `1/sqrt(N · T/τ)`. N and T trade
evenly in total *work* — and not at all evenly in *wall-clock*, because time is
strictly serial while N is embarrassingly parallel.

`kuramoto.py` collapses the pair sum to a mean field, making each step O(N), and
its docstring concluded that this "makes a 2000-oscillator sweep a NumPy job
rather than a GPU one." Benchmarked on this box today (RK4, float64, per step):

| N | NumPy CPU | torch GPU | |
|---|---|---|---|
| 2,000 | 203 µs | 306 µs | GPU **slower** |
| 20,000 | 1,737 µs | 310 µs | 5.6× |
| 200,000 | 17,680 µs | 527 µs | **33.6×** |
| 2,000,000 | — | 3,245 µs | |

The old verdict was right at N = 2,000 and stops being right somewhere below
20,000. At N = 200,000 the GPU delivers **100× the oscillators for 2.6× the
wall-clock** — a 10× noise reduction that would otherwise cost 100× the
measurement time.

## Verdict — IN REACH, 3.1 GPU-hours

Projected grid: N = 200,000, ε floor 0.005 (4× closer to K_c than before), eight
columns, `T_MEASURE` scaled by the measured noise law, every column aimed at
**half** the gate tolerance rather than at it:

| ε | T_MEASURE | predicted spread (tol 0.15) |
|---|---|---|
| 0.0050 | 4,675 | 0.075 |
| 0.0091 | 2,000 | 0.073 |
| 0.0164 | 2,000 | 0.046 |
| 0.0297 | 2,000 | 0.030 |
| 0.0538 | 2,000 | 0.019 |
| 0.0975 | 2,000 | 0.012 |
| 0.1767 | 2,000 | 0.008 |
| 0.3200 | 2,000 | 0.005 |

**3.1 GPU-hours. The same statistics on the CPU engine: 103 hours.**

So a thirty-year disagreement in the literature is settleable on this box in one
night, and the reason it wasn't is not physics, funding, or cleverness. It is
that the engine was sized for N = 2,000 on a machine whose GPU sits idle.

## The rule the new engine ships under

**A new engine must reproduce the old engine before it is allowed to produce new
science.** `kuramoto_gpu.py` mirrors `kuramoto._drift` in the same algebraic
form and order — `⟨sin θ⟩·cos θ − ⟨cos θ⟩·sin θ`, not a complex-exponential
centroid — so trajectories can be compared bit-near rather than merely
approximately. Over 400 steps at N = 2,048, on both branches, with and without a
pinning field, the two agree to **~1e-15**: float64 round-off. A faster
instrument that quietly disagrees with the calibrated one is not an upgrade; it
is an unlabelled second lab.

## What is NOT claimed

- **Nothing about who is right.** This says the question is affordable and names
  the price. Daido and Hong are untouched until the run happens.
- **The 3.1 hours is a projection**, built by extrapolating a seven-point noise
  fit about one decade in ε. It could be wrong by a factor of a few. It cannot
  plausibly be wrong by the 33× that separates this from the CPU path.
- **ε = 0.005 may still not be inside the scaling window.** U-K01's drift test
  must be re-run on the new data; if the local exponent is still drifting there,
  the answer is another decade down, not a claim.
- **The ε^-0.76 exponent is an engine property, not a critical exponent.** It
  describes this integrator at this N and T. It is used to budget, nothing else.
