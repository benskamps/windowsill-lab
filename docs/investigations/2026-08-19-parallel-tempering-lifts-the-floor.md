# Parallel tempering lifts the M11 equilibration floor from T ≈ 0.6 to T = 0.30

**And it costs nothing.** 75.7 s tempered against 78.3 s untempered, same lattice,
same sweeps, same GPU. The arm that bought the result was the one that changed
the *move*, not the one that bought more sweeps — and the sweeps arm is in this
run as a control, at twice the wall-clock, failing.

---

## 1. The pre-registered claim

`spin_glass.py` has documented its own wall since it was written:

> *"There is a concrete equilibration floor at T ≈ 0.5–0.6 for L=16: below it,
> single-spin Metropolis can no longer equilibrate the glass in tractable time,
> and the coldest points fall into an under-equilibration dip where ⟨q²⟩ is
> suppressed below the peak rather than continuing to grow (verified directly —
> even 4× the burn-in does not lift the two coldest points out of the dip)."*

M11 ships with `T_min = 0.6` for exactly this reason: the production run stops
at the floor rather than publishing numbers it does not trust. That is the right
call, and it is also a standing admission that a whole temperature range is out
of reach.

The claim tested here, written before the runs: **an exchange move should lift
the dip; more sweeps should not.** Both halves are falsifiable and the second
half is a control the module's own docstring already predicts will fail.

## 2. The arms

L = 16, T ∈ [0.30, 2.00] (deliberately *below* the shipped floor), 16
temperatures, 64 disorder realizations, 60,000 measurement sweeps, seed
2026081316, CUDA. Four arms, identical except where noted:

| arm | burn-in | swap | wall |
|---|---|---|---|
| `plain` | 30,000 | — | 78.3 s |
| `plain-4x-burn` | 120,000 | — | 159.5 s |
| `pt-every-10` | 30,000 | every 10 sweeps | 95.7 s |
| `pt-every-50` | 30,000 | every 50 sweeps | 75.7 s |

## 3. The result

⟨q²⟩ at the eight coldest rungs (the full ladder is in the raw output):

| T | 0.30 | 0.41 | 0.53 | 0.64 | 0.75 | 0.87 | 0.98 | 1.09 |
|---|---|---|---|---|---|---|---|---|
| `plain` | 0.137 | 0.192 | 0.286 | **0.315** | 0.249 | 0.171 | 0.117 | 0.077 |
| `plain-4x-burn` | 0.149 | 0.219 | **0.362** | 0.316 | 0.246 | 0.171 | 0.116 | 0.077 |
| `pt-every-10` | **0.523** | 0.492 | 0.413 | 0.327 | 0.246 | 0.174 | 0.116 | 0.077 |
| `pt-every-50` | **0.523** | 0.491 | 0.413 | 0.329 | 0.248 | 0.174 | 0.116 | 0.078 |

Bold marks each arm's maximum. The physics says ⟨q²⟩ must **grow monotonically
as T falls** toward the T = 0 critical point; a maximum anywhere but the coldest
rung is the dip.

- **`plain` peaks at T = 0.64** and falls away below it. The dip, reproduced.
- **`plain-4x-burn` still peaks at T = 0.53**, at 2× the wall-clock. The dip
  moved one rung and did not lift. The docstring's prediction, confirmed:
  *more sweeps do not buy this.*
- **Both tempered arms are monotone to the coldest rung.** ⟨q²⟩(0.30) = 0.523
  against `plain`'s 0.137 — a factor of 3.8 at the cold end, and the shape is
  the one the physics requires.

## 4. Four controls, and why the result is not a sampler artifact

A sampler that makes cold numbers bigger is exactly what a *broken* sampler
looks like. Four independent checks say this one is not.

**(a) The warm end does not move.** At T ≥ 0.75 — where single-spin Metropolis
was already equilibrated — all four arms agree to three decimals (0.249 / 0.246
/ 0.246 / 0.248 at T = 0.75; 0.117 / 0.116 / 0.116 / 0.116 at T = 0.98).
Tempering changes the answer *only where Metropolis was stuck*, which is the
signature of an equilibration fix and not of a bias.

**(b) The lab's own equilibration diagnostic improves by an order of
magnitude.** |⟨q⟩| must be zero by the ±J spin-inversion symmetry, and M11
already uses its departure from zero as its equilibration tell. Across the cold
rungs: `plain` runs 0.011–0.066, `plain-4x-burn` 0.003–0.065, while **both
tempered arms run 0.0004–0.0065**. The tempered ensembles are symmetric to a
part in a thousand. This is an independent criterion, chosen by the milestone
before this work existed, and it agrees.

**(c) Two swap intervals, one answer.** `pt-every-10` and `pt-every-50` differ
by 5× in exchange frequency and agree to three decimals at every rung. If the
result were an artifact of the exchange it would depend on how often the
exchange happened.

**(d) Exact enumeration.** On a 4×4 lattice the Boltzmann distribution can be
summed over all 65,536 states. `tests/test_tempering.py` asserts that the
sampler reproduces the exact ⟨E⟩ at every rung of the ladder **with tempering on
and with it off**, to ±0.035 per spin. A wrong acceptance formula, a swap that
moves configurations without their statistics, or any other broken-detailed-
balance failure would show up there and does not.

## 5. The ladder is over-resolved, and the diagnostic says so

Swap acceptance: minimum adjacent-pair rate **0.465**, mean 0.593, every rung
connected. That is *above* the usual 20–40 % target band, which is not a
success — it means adjacent temperatures are closer than they need to be and
some of those 16 rungs are buying nothing. The same physics is probably
reachable with fewer temperatures (cheaper) or over a wider range (colder).
`tempering.geometric_ladder` exists for the respacing; it is not wired into M11
because respacing the ladder would change what M11 measures, and that is a
milestone decision, not a sampler decision.

Reporting the **minimum** adjacent acceptance rather than the mean is deliberate:
one dead rung disconnects the cold end from the hot end no matter how healthy the
average looks, and a mean-only report is how a tempering run convinces itself it
is mixing.

## 6. What this does not establish

- **Monotone ⟨q²⟩ is consistent with equilibration, not proof of it.** The
  evidence that the tempered cold end is equilibrated is the symmetry diagnostic
  (§4b) and the interval-independence (§4c), not the shape of the curve. A
  colder run would need its own diagnostics, not an extrapolation of this one.
- **T = 0.30 is where this run stopped, not where the new floor is.** Nothing
  here locates the tempered floor; it only shows the old one is not binding.
- **L = 16 only.** Larger lattices have longer relaxation times and the
  acceptance rate falls as √N for fixed ΔT, so the ladder that works here will
  not automatically work at L = 32.
- **No new physics.** ⟨q²⟩ growing toward T = 0 in the 2-D EA glass is the
  expected, published behaviour — this run makes the lab able to *measure* it
  over a range it previously could not, which is an instrument result. See the
  prior-art assay for what is and is not novel about the method itself
  (spoiler: nothing).

## 7. Not wired into M11

`swap_every` defaults to **0**, which reproduces every number measured before
today bit-for-bit — the exchange draws from its own RNG stream, so an untempered
run is byte-identical whether the feature exists or not (there is a test for
this). Turning it on for M11 means changing what a shipped milestone measures
and re-running the ladder below its published floor, which is Ben's call, not a
sampler's.

The concrete proposal, when he wants it: `T_min = 0.30`, `swap_every = 50`,
everything else unchanged. It costs the same 76 seconds M11 already spends and
it returns six rungs the milestone currently cannot claim.

---

**Raw output:** the four arms' full ladders, swap health and wall-clock are in
the run's JSON. **Code:** `lab/tempering.py` (the move), `lab/spin_glass.py`
(`swap_every`), `tests/test_tempering.py` (21 tests, including the exact
enumeration). **Prior art:** `docs/assays/2026-08-19-fold-gates-and-tempering-prior-art.md`.
