# Re-check: TIC 4206066, Pavel Rabtsevich's 3.18 d and 11.13 d signals

**Whose:** Pavel Rabtsevich's, doi:10.5281/zenodo.22967456. This is an
independent re-check, not our discovery.
**Consumer:** Ben and the project thread, once. One-off investigation. **Retires:** nothing (no prior surface for this star).
**Pre-registration:** the same file as TIC 100796276 (b7d3b02 + amendment 1,
8af09e0). **Receipt:** `tic4206066-receipt.json`.
**Data:** SPOC S32 (2-min) and TESS-SPOC S6 (30-min) are primary; TESS-SPOC S32
is a cross-check. His discovery sector, S98, is QLP-only and was **not
admitted** for this star, so the sector where he found both signals is outside
this re-check. His pre-registered S110 test cannot be run until S110 is
public.

## Signal A (3.182785 d, his ≈ 500 ppm, T14 1.87 h)

| test | result |
|---|---|
| T4: depth at his ephemeris | SPOC S32 341 ± 55 ppm (6.3σ, 8 epochs); TESS-SPOC S6 385 ± 72 ppm (5.3σ, 6 epochs); primary fold **336 ± 49 ppm (6.9σ)** |
| T7: depth across sectors | S32 and S6 agree within 0.5σ. The cross-check copy of S32 gives 308 ± 55 ppm |
| T1: the survey's per-sector BLS | SPOC S32: top peak 7.47 d, SDE 5.0, so **not recovered**. TESS-SPOC S6 and S32: top peak 3.181 and 3.184 d, SDE 7.2 and 6.9, which is **below the survey's 8.0 threshold**. The lab's survey would not have flagged it in any one of these sectors |
| T5: odd/even | 0.27σ difference; neither parity alone reaches 5σ, so the gate cannot fire either way |
| T6: secondary | phase 0.5: −74 ± 56 ppm; 3σ ceiling 263 ppm over the full orbit. The surface-brightness bound is 0.78, a companion cooler than about 3,810 K, which **does not exclude** a stellar companion (host 4,010 K). Too shallow a primary for this bound to bite |
| T8: centroid (duration-matched, graded) | **3.7σ shift, implied offset 0.28 px ≈ 5.8″**. That is under the 0.5-px bar, so it does not fire, but it is a significant shift. His difference-image fit gives (+5 ± 3, 0 ± 3)″, so the two measurements are consistent with each other. The lab-window variant gives 1.4σ |
| T8: neighbours and catalogue | not a TOI or CTOI; CROWDSAP 0.997. Every TIC neighbour within 4 px is ≤ 0.04 % of the target's flux. The nearest, TIC 712986249 (0.58 px, 12″), would need an ~84 % eclipse to make this dip. Not refuted by the lab's flux budget (the gate asks only below CROWDSAP 0.8) |
| T8: size | 0.116 R_Jup = **1.30 R⊕** from our depth and the header R★ = 0.648 R☉ (his 1.4 ± 0.1 R⊕ with R★ 0.623) |

No lab gate fires. Signal A is **present at 6.9σ** in the two archival sectors
this lab admits, at about two-thirds of his depth. The detrend and box bias run
in that direction, and his depth comes from a transit model. That is
"reproduced, faintly". The centroid shift is significant at 3.7σ and points
about 6″ off the target, in agreement with his own localisation. It is worth
naming because it is the same unresolved-companion question he raises, now seen
by a second instrument.

## Signal B (11.13274 d, his ≈ 1,000 ppm)

| sector | depth at his ephemeris | epochs |
|---|---|---|
| TESS-SPOC S6 | 450 ± 48 ppm (9.5σ) | 2 |
| SPOC S32 | 387 ± 94 ppm (4.1σ) | 2 |
| TESS-SPOC S32 (cross-check) | 312 ± 95 ppm (3.3σ) | 2 |

There is a dip at his B ephemeris in both admitted sectors, at **less than half
his depth**. He notes that the S32 B events abut A transits, so the S32 numbers
are partly A's light. S6 at 9.5σ from two 30-min events is the strongest
number here, but only two events go into it. No duration for B was published,
so the 2.0 h used here is our assumption. Reported, not graded: the
pre-registration fixed no pass line for B beyond the per-sector SNR.

## Not tested

S98 (his discovery data, QLP only, not admitted), S110 (not yet public), his
TRICERATOPS runs, his Gaia RUWE/RV arguments, and the 0.2–2″ companion channel.

— Claude on Portal1, 2026-10-20
