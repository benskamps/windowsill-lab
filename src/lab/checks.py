"""Make ``verified`` mean something a machine confirmed.

A green leaf on the windowsill should be a *receipt*, not an honor-system
checkbox. This module re-derives a milestone's headline number from a run report
and asserts it against the known answer. ``lab verify`` runs the registered
checks; CI runs ``lab verify`` so a milestone can't be marked ``[x]`` unless its
number actually reproduces.

Each check is *applicable* only to reports it understands (it returns ``None``
for ones it can't read), so a milestone is graded against the newest report it
can actually evaluate — not whatever ran most recently. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from pathlib import Path

from .m01_quality import (
    EQUIL_MAX_EXCLUDED as _EQUIL_MAX_EXCLUDED,
    EQUIL_SIGMA as _EQUIL_SIGMA,
    assess_m01_quality,
    nonequilibrated_indices,
)
from .curriculum import (
    CANARY_HALF_LIFE_DAYS,
    HUNT_CANDIDATE,
    NEVER_RUN_VALUE,
    NULL_RETRY_VALUE,
    OPEN_FRONTIER_VALUE,
    PLANNER_VERSION,
    REPEAT_HARD_CAP,
    STALENESS_CAP,
    VERIFIED_CANARY_VALUE,
    _head_run,
    _parse_stamp,
)
from .m16 import aging_gate as _m16_aging_gate
from .m16 import aging_metrics as _m16_aging_metrics
from .publish import LAB_HOME, MILESTONES_MD, REPORTS_DIR, parse_milestones

# Onsager's exact 2D Ising critical temperature, 1944.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.2692
# Exact 2D Ising susceptibility exponent ratio (M02 finite-size scaling).
GAMMA_OVER_NU = 7.0 / 4.0   # = 1.75
# Exact 2D Ising magnetization scaling dimension (M03 data collapse): β=1/8, ν=1.
BETA_OVER_NU = 1.0 / 8.0    # = 0.125
INV_NU = 1.0                # 1/ν
# 3D simple-cubic Ising critical temperature — the MC/series benchmark (M06).
TC_3D = 4.5115
# 3D Edwards–Anderson spin-glass transition temperature (M12) for the BIMODAL ±J
# couplings the engine actually draws (spin_glass3d._bonds: randint(0,2)*2−1).
# Katzgraber–Körner–Young, PRB 73, 224432 (2006) place the ±J transition at
# T_c = 1.120(4) — their 0.951(9) is the GAUSSIAN-disorder value — and
# Hasenbusch–Pelissetto–Vicari refine the ±J value to T_c = 1.1019(29). Mirrors
# m12.T_SG_BENCHMARK: the engine and this check must grade the same model
# (test_m12_benchmark_mirrors_the_engine_constant pins the pair together).
TC_SG_3D = 1.102
# Crossing tolerance for M12: finite-size Binder crossings drift with the size pair
# and carry corrections-to-scaling, so — like M08's ±0.07 BKT window — a physically
# justified band is allowed. Owned by the check (not read from the report) so a run
# can't widen its own tolerance to pass. A broken run still misses by a wide margin,
# and the Gaussian-disorder 0.95 sits outside the band. Mirrors m12.CROSSING_TOL.
TC_SG_3D_TOL = 0.10
# Exact triangular-lattice 2D Ising critical temperature (M05): T_c = 4/ln 3.
TC_TRI = 4.0 / math.log(3.0)   # ≈ 3.6410
# Exact honeycomb-lattice 2D Ising critical temperature (M05's second half):
# T_c = 2/ln(2+√3). The triangular lattice's dual, z = 3 instead of 6.
TC_HEX = 2.0 / math.log(2.0 + math.sqrt(3.0))   # ≈ 1.5187
# 2D XY BKT transition temperature (M08) — the square-lattice MC/RG benchmark
# (0.89290(5)); no closed form. Located via the helicity-modulus jump crossing.
T_BKT = 0.8929
# The universal-jump slope: at the crossing Υ/T = 2/π, i.e. Υ(T_BKT) = (2/π)·T_BKT.
TWO_OVER_PI = 2.0 / math.pi
# Wannier's exact residual (ground-state) entropy per spin of the triangular Ising
# antiferromagnet (M13): S0/N = 0.3383 k_B, the macroscopic degeneracy the frustrated
# ground state leaves at T=0. Measured by integrating C(T)/T down from S(∞)=ln2.
WANNIER_S0 = 0.3383

# M18 directed-percolation gate. These are owned by the verifier, not trusted
# from the report: a receipt must not be able to move its benchmark or widen its
# own tolerance. The fit-quality floor is intentionally loose enough for finite
# time corrections while still requiring the quoted power-law window to be one.
M18_DP_DELTA = 0.4505
M18_MEAN_FIELD_DELTA = 1.0
M18_MAX_BRACKET_WIDTH = 0.30
M18_MIN_HEADROOM = 2.0
M18_DYNAMIC_EXPONENT_Z = 1.766
M18_MIN_R2 = 0.98

# A04 blind-search gate. The recovery roster, catalog periods, injection ladder,
# and detection rule are part of the calibration design. Reading any of them
# back from the receipt would let the run grade itself.
A04_SDE_THRESHOLD = 8.0
A04_PERIOD_TOL_FRAC = 0.01
A04_MIN_FALSE_ALARM_SAMPLES = 20
A04_EXPECTED_RECOVERIES = {
    "WASP-18 b": 0.94145223,
    "HIP 65 A b": 0.98097340,
}
A04_EXPECTED_INJECTIONS = (
    (0.010, 3.7),
    (0.004, 2.3),
    (0.002, 5.1),
)
A04_SERENDIPITOUS_RECOVERY = ("WASP-20 b", 4.8996461)

# --- A05 survey-hunt gate. Every tolerance is OWNED HERE, never read from the
# receipt: a run that could carry its own thresholds could grade itself.
# Detection threshold and permutation-null contract (mirrors the engine's
# design constants; the check restates them so a drifted engine FAILS rather
# than silently re-defining the gate).
A05_SDE_THRESHOLD = 8.0
# Fewest permutations a graded FAP may rest on. 64 resolves the 0.05 band the
# uniformity test grades (grid 1/65) and doubles the Gumbel fitter's minimum
# sample; production runs at B=256 — the check floors the resolution, it does
# not pin the production choice.
A05_MIN_B = 64
# The block scheme's declared block length; a receipt claiming a different
# blocking is calibrated against a different null than the one audited.
A05_BLOCK_DAYS = 0.75
# The two measured floor points the triage line is drawn through, and the
# safety margin subtracted — the check re-derives the line and refuses a
# receipt whose triage block disagrees (a run must not move its own line).
A05_TRIAGE_FLOOR_POINTS = ((22, 6.6), (153, 7.65))
A05_TRIAGE_SAFETY_MARGIN = 1.0
# Prior floor-history points every receipt must carry forward (source, n,
# max SDE): dropping history is how an extrapolation stops being testable.
# Sources are the committed receipt basenames in reports/hunts/ — mirrors
# a05.PRIOR_FLOOR_HISTORY (lockstep test pins the pair).
A05_FLOOR_PRIOR = (("run-2026-08-08-2338-a04", 22, 6.6),
                   ("hunt-2026-08-14-s2-pilot-158", 153, 7.65),
                   ("hunt-2026-08-14-s2-pilot-570", 551, 7.875))
# One-sample KS 5% NUMERATOR for the uniformity re-run — Stephens' (1970)
# finite-n form: critical distance = CRIT / (sqrt(n) + 0.12 + 0.11/sqrt(n)).
# Lockstep with a05_stats.uniformity_stat (the two cross-check each other:
# gate 10 recomputes the engine's pass flag, so a one-sided change reads as
# contradiction). Below it, the smallest control ensemble worth grading
# (under 5 the KS test has no power and the calibration would be decorative).
A05_UNIFORMITY_CRIT = 1.358
A05_UNIFORMITY_MIN_N = 5
# Empirical FAPs are exact rationals (1+k)/(B+1); recomputation must agree to
# float round-off, nothing looser.
A05_FAP_ABS_TOL = 1e-9
# Gumbel refit agreement: the check's own MLE on the stored maxima must land
# within this relative band of the receipt's (mu, beta). Same data, same
# model — 5 % is generous for two correct fitters and far too tight for a
# fabricated block.
A05_GUMBEL_RTOL = 0.05
# The predeclared injection ladder every Stage-2 and recovery host must carry
# in full — echoed, not imported, so a lane that shrank its ladder fails.
A05_INJECTION_DEPTHS = (0.002, 0.004, 0.010)
A05_INJECTION_PERIODS = (2.3, 3.7, 5.1)
A05_INJECTION_EPOCHS = 2
A05_INJECTION_RULES = ("sde-threshold", "fap-injection-iid")
# Spot reproduction: recomputed null maxima from the SHA-256-pinned FITS must
# match the stored ones within this relative tolerance. Seed-pinned replay is
# bitwise on one platform; the band absorbs cross-platform libm/BLAS last-bit
# drift and nothing else — a wrong seed or tampered maxima miss by orders of
# magnitude. Caveat: the prewhiten stage takes DISCRETE branches (argmax peak
# picking, the component-count cutoff) that can flip on cross-platform last-
# bit differences, and a flipped branch produces a GROSS deviation even with
# a matching sha256. That still reads False — the receipt does not reproduce
# HERE — but _a05_spot names the ambiguity above A05_SPOT_GROSS so the reader
# knows to distinguish tampering from a platform branch flip.
A05_SPOT_RTOL = 1e-5
A05_SPOT_GROSS = 1e-2
# Budget bookkeeping: the reported survey share must re-derive from the rows'
# own wall clocks within this relative band, and no row may exceed its
# declared per-target share of the soft budget by more than the same slack.
A05_BUDGET_RTOL = 0.05
# Mirror of the engine's default per-target share (a05.PER_TARGET_SHARE) so a
# drifted default is caught by the lockstep test, not discovered when an
# honest ~180 s stage-2 row is refused against a 60 s cap. Row clocks are
# per-worker wall inside process_target; the soft budget is serial survey
# wall — the two are compared per ROW, never summed against each other.
A05_PER_TARGET_SHARE = 0.10
# The machine's ENTIRE disposition vocabulary, restated. "planet" is absent
# by design and its appearance anywhere is an affirmative contract violation,
# not a formatting problem.
A05_MACHINE_VOCABULARY = frozenset({
    "stellar-pulsation", "harmonic-alias", "eclipsing-binary-odd-even",
    "eclipsing-binary-secondary", "phased-brightening", "low-significance",
    "insufficient-coverage", "period-railed", "centroid-shift",
    "recovery-or-known", "known-planet", "toi-known-fp",
    "lead-awaiting-human-review",
})
# TFOPWG dispositions meaning "community already refuted this signal" — such
# a row must be machine-dispositioned toi-known-fp and can be neither a
# recovery nor a lead (the TIC 278866211 / TOI 189.01 lesson).
A05_TOI_REFUTED = ("FP", "FA")
# Panels a lead's dossier must carry (echo of the dossier contract).
A05_DOSSIER_PANELS = ("fold_p", "fold_half_p", "fold_2p",
                      "odd_even", "secondary", "self_injection")
# Residual-entropy tolerance for M13. A physically-justified band, NOT a fudge: the
# integrated residual carries a few-percent systematic from the finite temperature
# window and the trapezoidal integration of a Monte-Carlo C(T). Empirically it lands
# slightly BELOW 0.3383 and converges to ≈0.32 as the lattice grows (L=24→0.334,
# L=96→0.322), so ±0.03 comfortably passes the trustworthy large-L runs while a broken
# run — wrong geometry, wrong J sign, or a non-degenerate ground state (residual near 0
# or ln2) — misses by 10× more. Owned by the check, not read from the report, so a run
# can't widen its own tolerance.
WANNIER_S0_TOL = 0.03
# The exact triangular-AFM ground-state energy per spin (|J| units): each frustrated
# triangle keeps two of three bonds → Σ_bonds s_i s_j = −N → e = −1. An independent
# anchor: a wrong-sign (accidental FM, e→−3) or wrong-geometry run fails this outright.
TRI_AFM_GROUND_ENERGY = -1.0
TRI_AFM_GROUND_ENERGY_TOL = 0.06
# 2D ±J random-bond Ising, the multicritical Nishimori point (M14): the square-lattice
# literature benchmark (p_c ≈ 0.109–0.110, T_c ≈ 0.953). M14 does NOT gate on pinning
# this — it is genuinely hard at reachable scale — it gates on the EXACT Nishimori-line
# internal energy, an identity that needs no critical precision.
MNP_P_C = 0.1094
MNP_T_C = 0.9528
# Nishimori-line energy tolerance for M14, OWNED BY THE CHECK. On the line the disorder-
# averaged energy per spin is the exact identity E/N = −2·tanh(1/T) = −2(1−2p) (square,
# J=1); at modest L the measured value sits within a few ×0.01 of it, so ±0.05 passes the
# trustworthy runs while a broken engine (wrong bond draw, wrong estimator, off the line)
# misses by far more. A hard identity, not a fitted T_c — the tolerance is slack, not a fudge.
MNP_ENERGY_TOL = 0.05
# How tightly a reported (p, T) point must sit on the Nishimori line to be graded: the
# check re-derives tanh(1/T) and requires it to equal 1 − 2p. A point off the line has no
# exact-energy identity to test against, so it is rejected rather than mis-graded.
NISHIMORI_LINE_TOL = 1e-2
# Allen–Cahn coarsening exponent (M15): curvature-driven growth of a non-conserved order
# parameter gives L_domain(t) ∼ t^(1/2). The verified claim is this GROWTH EXPONENT.
ALLEN_CAHN_EXPONENT = 0.5
# Exponent tolerance for M15, OWNED BY THE CHECK. A physically-justified band, NOT a fudge:
# Allen–Cahn is asymptotic and the finite-time effective exponent is documented to sit a few
# percent BELOW ½ (the preasymptotic correction — coarsening approaches t^(1/2) from below),
# so ±0.06 admits the honest ~0.46–0.49 measured at reachable scale while still rejecting a
# broken run: diffusive ¼, ballistic 1, or a frozen/saturated ~0 all miss by far more.
ALLEN_CAHN_TOL = 0.06
# The log-log coarsening line is essentially perfect, so a genuine power-law fit clears a
# high R²; a noisy/curved L(t) (un-quenched, or fit across the finite-size saturation knee)
# would not. Guards against grading a slope off a bad line.
M15_MIN_R2 = 0.99
# M15 scaling-window rule — re-derived here (a receipt), matching ``m15`` defaults. The check
# prefers the window params the report stored (so producer and grader can't silently drift),
# falling back to these if absent — but honours stored values only inside the check-owned
# bounds defined below (a report can't tune its own window into the band).
M15_T_FIT_MIN = 20
M15_L_MIN_FIT = 4.0
M15_SAT_FRAC = 0.20
# ── M17: 1+1d kinetic roughening. Three growth classes, three EXACT exponents. ────────────
# Kardar–Parisi–Zhang (1986): w(t) ∼ t^β with β = 1/3, w_sat ∼ L^α with α = 1/2, so the
# dynamic exponent z = α/β = 3/2 and the correlation length ξ(t) ∼ t^{1/z} = t^{2/3}.
KPZ_BETA = 1.0 / 3.0
KPZ_ALPHA = 0.5
KPZ_Z = 1.5
# Edwards–Wilkinson (the linear theory — KPZ minus the (∇h)² term): β = 1/4 exactly.
EW_BETA = 0.25
# Random deposition (independent columns, no relaxation): β = 1/2 exactly, and stronger — a
# CLOSED FORM w²(t) = p(1−p)·t at every t, with nothing fitted.
RD_BETA = 0.5
# Tolerances, OWNED BY THE CHECK (never read from the report, so a run can't widen its own
# band). Physically justified, not fudges: like M15's Allen–Cahn band, the finite fit window
# makes the effective exponent land a few percent BELOW its asymptotic value — measured at
# ≈0.316 for KPZ and ≈0.239 for EW, both low by the same ~5%, which is the tell that the
# deficit is the window and not the physics. The bands still separate the three classes by a
# wide margin: KPZ's ±0.04 admits [0.293, 0.373], which excludes EW's ¼ and RD's ½ outright.
KPZ_BETA_TOL = 0.04
EW_BETA_TOL = 0.03
RD_BETA_TOL = 0.02
KPZ_ALPHA_TOL = 0.05
# Random deposition is graded against its exact CURVE, point by point — max relative
# deviation of the measured w² from p(1−p)t. A pipeline with a broken width estimator or a
# mis-scaled time axis fails here before any exponent is fitted.
RD_EXACT_TOL = 0.05
# The log-log roughening line is essentially perfect over ≥2 decades; a genuine power law
# clears a high R². Guards against grading a slope off a curved or noisy line.
M17_MIN_R2 = 0.99
# M17 scaling-window rule — re-derived here (a receipt). Preferred from the report when it
# stored them (so producer and grader can't silently drift), else these — honoured only
# inside the check-owned bounds defined below.
M17_T_FIT_MIN = 20
M17_W_FIT_MIN = 1.5
# λ < 0 for the single-step model (v(u) = (p/2)(1−u²) ⇒ λ = ∂²v/∂u² = −p), so KPZ predicts
# the MIRRORED Tracy–Widom law. These signed skewness targets are what a correct run matches;
# a positive skewness would mean the growth direction or the map was inverted.
TW_GUE_SKEW = -0.2241   # curved / droplet geometry
TW_GOE_SKEW = -0.2935   # flat geometry
# Skewness band. Third moments converge slowly (O(t^{-1/3}) corrections ≈ 0.15 at reachable
# t) and carry a sampling error ≈ sqrt(6/N); ±0.06 admits that without admitting a Gaussian
# (skew 0) or the wrong Tracy–Widom class.
TW_SKEW_TOL = 0.06

# ── K01: the Kuramoto synchronization transition. Track K (coherence). ────────────────────
# The fixed K01 calibration identity, mirrored from ``k01`` so the grader and the producer
# cannot drift (test_k01_identity_mirrors_the_runner pins the pair together). A run that
# changed any of these is a diagnostic, NOT this calibration — the same identity gate
# check_c01 puts on its 40-term OEIS prefix, and the reason a hostile receipt can't grade
# itself against a γ of its own choosing.
KURAMOTO_GAMMA = 0.5
KURAMOTO_N = 2000
KURAMOTO_POINTS = 25
KURAMOTO_K_MAX_OVER_GAMMA = 4.0
# Kuramoto's exact infinite-N mean-field critical coupling for a Lorentzian g(ω) of
# half-width γ: K_c = 2/(π·g(0)) = 2γ. At the fixed γ = 0.5 this is exactly 1.0.
KURAMOTO_KC = 2.0 * KURAMOTO_GAMMA
# Tolerance for K01, OWNED BY THE CHECK (never read from the report). Set by the SWEEP
# GRID, not by the shipped run's luck: the 25-point sweep of [0, 4γ] has ΔK = γ/6 = 0.0833,
# and no 3-point peak refinement recovers much better than a fraction of one grid step, so
# ±0.10 ≈ 1.2·ΔK is the honest floor. It comfortably admits every configuration measured
# before it was declared — N=2000 gave +0.0007 and −0.0090 on two initial conditions, and
# the finite-N shift is +0.008 at N=1000, +0.026 at N=500, +0.050 at N=250 (the estimate
# approaches 2γ from ABOVE as N grows) — while a broken run misses by ~10×: an uncoupled or
# sign-flipped sweep never orders and puts the fluctuation peak at a sweep endpoint (0 or
# 2γ·2, off by 1.0), and a mis-drawn frequency distribution moves K_c = 2γ by a whole factor.
KURAMOTO_KC_TOL = 0.10
# The STRONGER anchor: above the transition the mean-field solution is a closed form with
# nothing fitted, r(K) = √(1 − K_c/K). Graded only where it is genuinely asymptotic
# (K ≥ 1.5·K_c) — closer in, the finite-N curve is still rounding the transition's corner.
KURAMOTO_BRANCH_K_MIN_FACTOR = 1.5
# Branch tolerance, also check-owned. The shipped N=2000 run matches the closed form to
# 1.5e-4 and the cheapest N=250 run to 1.3e-3, so ±0.02 is slack by two orders of magnitude
# — deliberately, because its job is not precision but refusing a fabricated curve: a broken
# estimator misses these seven un-fitted values by 0.1–0.7, not by 0.02.
KURAMOTO_BRANCH_TOL = 0.02
# Negative control. With ZERO coupling there is no synchronization, so the measured
# coherence must be nothing but the random-walk centroid of N scattered phases, r ≈ 1/√N
# (measured 0.0203 against 0.0224 at N=2000). Allowing 3/√N catches the failure that
# matters — a collapsed frequency draw (all ω equal) orders at K=0 and would sail through a
# peak-only gate — without grading the noise floor to a precision it doesn't have.
KURAMOTO_INCOHERENT_MAX_SIGMA = 3.0

# ── K02: the susceptibility's SHAPE on the r-axis, and whether it survives N. ─────────────
# The fixed K02 identity, mirrored from ``k02`` (test_k02_identity_mirrors_the_runner pins
# the pair together). A run that shortened the ladder or dropped seeds is a diagnostic, not
# this measurement — the same rule check_k01 applies to its calibration.
K02_LADDER = (250, 500, 1000, 2000, 4000)
K02_SEEDS = (42, 7, 1234, 2718, 31415)
# Run 01's published form χ(r) = a·r²(1−r)³ has its interior maximum at p/(p+q) = 2/5.
# This is the number under test; it is NEVER read from the report.
K02_RUN01_R_STAR = 2.0 / 5.0
# Resolution floor on r*, OWNED BY THE CHECK.
#
# The naive floor — half the r-interval the peak's two neighbours span — is the error
# you would quote if the peak's INDEX were certain and only the spacing were not. That
# is not this measurement. What is actually uncertain is WHICH coupling carries the χ
# maximum, and r(K) = √(1−K_c/K) has infinite slope at K_c⁺, precisely where the peak
# sits, so an index that moves by a couple of grid steps drags r* a long way.
#
# So the honest floor is the K-peak's own uncertainty PROPAGATED through dr/dK, which
# on this grid is just the local r half-spacing multiplied by how many steps the
# K-peak wanders. That wander was MEASURED before this constant was declared: across
# the shipped ladder the refined χ peak lands at K/K_c = 1.011, 1.041, 0.999, 1.007,
# 0.973 — a standard deviation of 0.024, i.e. 2.4 steps of the dense arm's ΔK = 0.01.
# Three steps covers it. (Quoting the bare spacing instead would have claimed ±0.03 at
# N=500 on a rung whose five initial conditions came back BIMODAL at 0.05 and 0.20 —
# an error bar smaller than the scatter it was supposed to describe.)
K02_K_PEAK_STEPS = 3.0
# ...with an absolute minimum, so an unusually tight local spacing cannot manufacture
# precision the estimator does not have.
K02_R_STAR_SCATTER = 0.03
# The GATE: the ladder must be resolved RELATIVE TO THE CLAIM IT TESTS. r* has to sit
# more than its own floor away from Run 01's 2/5 — in EITHER direction. A rung that
# lands on 2/5 within error is genuinely inconclusive and must not be graded a pass in
# either story; a rung whose floor is so wide it cannot address the claim fails the
# same way. This is deliberately symmetric: it says "the instrument can speak to the
# question", never "the answer came out a particular way".
K02_R_STAR_EXCLUSION_SIGMA = 1.0
# The interior-peak gate needs a MARGIN, not just an argmax that isn't on an endpoint:
# a flat, noise-dominated χ curve would satisfy the bare index test. The peak must stand
# above the ends of the swept r-range by this factor (scout: 4–6× at every N).
K02_INTERIOR_PEAK_RATIO = 2.0
# The anchor: χ's peak in the CONTROL parameter is UNRESOLVED FROM K_c = 2γ at every
# rung. Note the wording — this gate does NOT certify that the peak sits exactly at K_c,
# and an earlier version of this file wrongly implied it did. Hong, Chaté, Tang & Park,
# Phys. Rev. E 92, 022122 (2015) §III report that the finite-N peak is always on the
# SUBCRITICAL side and only approaches K_c as N grows, drifting as δK_max ~ N^(−1/ν̄')
# (their Eq. 3.10). K02's measured peak couplings scatter on BOTH sides with a standard
# deviation of ≈0.024 — wider than that drift — so all this band can honestly assert is
# consistency. Same ±0.10 arithmetic K01 declared; its job is refusing a broken engine,
# not precision, since an uncoupled or sign-flipped sweep puts the peak at a sweep
# endpoint, off by ~1.0.
K02_KC_TOL = 0.10

# ── the calibration: r(K_c, N) ~ N^(−β/ν̄_c) against a PUBLISHED exponent ─────────────
# This is K02's headline after the 2026-08-02 literature assay
# (docs/assays/2026-08-02-k02-literature-crosscheck.md) retired the previous one. The
# benchmark is owned here and never read from the report:
#   Hong et al. 2015 Eq. (4.3), for the REGULAR (deterministic-quantile) Lorentzian —
#   this engine's exact published configuration, their §IV A — gives β/ν̄_c = 0.39(2)
#   over N = 200…12800.
K02_CRITICAL_EXPONENT = 0.39
K02_CRITICAL_EXPONENT_ERR = 0.02
# The tolerance is set to bracket the LITERATURE's own spread for this sampling class,
# not this run's luck. Park & Park 2024 Eq. (20) revise the asymptotic value to
# 0.325(15) while noting the effective exponent sits near 0.37 until N ≳ 2^15; K02's
# ladder stops at 2^12, so a correct run may legitimately land anywhere in ≈[0.325,
# 0.39]. ±0.08 admits that whole window (and both published error bars) while still
# excluding the two things this gate exists to catch: the RANDOM-sampling universality
# class at 0.20 (which is what a frequency draw that lost the deterministic quantile
# grid would give — 2.4 bands away), and the 0.28 artifact the demoted Beta-fit
# estimator produced before the assay caught it.
K02_CRITICAL_TOL = 0.08
# Equilibration. The defect that produced the retired headline: at N=4000 the sweep's
# window measured a TRANSIENT, ⟨r⟩ still falling 0.070 → 0.027 long after it stopped
# looking, inflating the coherence ~2.5×. The critical measurement therefore reports the
# change in ⟨r⟩ between the first and second halves of its own window, and a rung still
# drifting is refused rather than averaged.
#
# The gate is on the drift's SIGNIFICANCE, not on a bare percentage, and that is a
# correction made after measuring: at N=2000 the shipped protocol returned an 11.3%
# half-to-half change, which a flat 10% constant would have failed — but the drift
# estimator has its own noise floor (a difference of two half-window means across a
# finite set of initial conditions), and 11.3% there is well inside it. Grading a noisy
# number against a constant would have refused a perfectly equilibrated rung. So each
# rung reports |Δ| in units of its own standard error and must come in under this many
# sigma. Gross non-equilibration is still caught with room to spare: the old short
# window's ~60% drift at the top of the ladder is many sigma, not one.
K02_EQUILIBRATION_MAX_DRIFT_SIGMA = 3.0
# A belt-and-braces absolute cap for the case where the drift's error bar is itself
# unreliable (too few initial conditions, or a rung whose seeds all drifted together).
# Loose on purpose — the sigma gate above is the one that does the work.
K02_EQUILIBRATION_MAX_DRIFT = 0.25
# The tail-clip negative control. ``kuramoto`` clips the Lorentzian at |ω| ≤ 40γ; the
# published configuration this milestone is graded against is UNCLIPPED, and the clip
# piles ~1.6% of the population onto two degenerate frequencies inside exactly the
# running-oscillator population Park & Park 2024 argue dominates the finite-size
# correction. So the run re-measures r(K_c) at a 2.5× looser clip (with dt cut 4× to
# keep the fastest drifter resolved) and the two must agree to within this many sigma
# of their combined standard error. If the exponent were riding on the clip rather than
# on the physics, this is what would catch it.
K02_CLIP_CONTROL_MAX_SIGMA = 3.0

# A01 calibration anchor — owned by the checker, not accepted from the report.
# NASA Exoplanet Archive pscomppars values used by the A01 producer.  Freezing
# them here makes a receipt independently verifiable: changing a report's
# embedded benchmark cannot move its own goalposts.
WASP18_PERIOD_DAYS = 0.94145223
WASP18_PERIOD_TOL_DAYS = 2.4e-7
WASP18_DEPTH_FRACTION = 0.01041
WASP18_DEPTH_TOL_FRACTION = 0.00022

# CTRL tolerances OWNED BY THE CHECK — numerically mirrored from controls.py
# (its CROSS_UPDATER_TOL / NULL_PEAK_RATIO_MAX, the producer's own gates) so the
# grader and the producer can't drift apart silently, but never READ from the
# report: a receipt carrying tol=99 or ratio_max=50 is graded against these.
CROSS_UPDATER_TOL = 0.15
NULL_PEAK_RATIO_MAX = 2.5

# Check-owned bounds on the report-carried scaling-window parameters (M15/M17).
# The window is as powerful a dial as the tolerance on a slightly curved log-log
# line — an early window lowers the effective exponent, a late one raises it — so
# a report may pick its window only inside these bands; outside them it is graded
# FAIL, never honoured. The module defaults above sit comfortably inside.
M15_T_FIT_MIN_BOUNDS = (10.0, 100.0)
M15_L_MIN_FIT_BOUNDS = (2.0, 8.0)
M15_SAT_FRAC_BOUNDS = (0.10, 0.25)
M17_T_FIT_MIN_BOUNDS = (10.0, 100.0)
M17_W_FIT_MIN_BOUNDS = (1.0, 3.0)


def _window_param(report: dict, key: str, default: float, bounds: tuple) -> float | None:
    """A report-carried window parameter, honoured only inside the check-owned band.

    Returns the value to use, or ``None`` when the stored value is malformed or
    out of bounds — the caller grades that FAIL (a run can't tune its own window
    into the band, and unreadable guard data is a named failure, not a default).
    """
    raw = report.get(key, default)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    lo, hi = bounds
    if not (math.isfinite(v) and lo <= v <= hi):
        return None
    return v


def _reports_newest_first() -> list[Path]:
    """Report and public-receipt JSONs newest-first by run timestamp.

    Full reports remain the preferred local evidence.  A clean git checkout may
    intentionally contain only compact ``reports/receipts/run-<date>-<slug>.json``
    artifacts for older runs, so include those as a verification fallback.  The
    receipts omit only visual snapshots and retain every checker input.
    """
    paths: list[Path] = []
    for d in (REPORTS_DIR, LAB_HOME):
        if d.exists():
            paths += d.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*.json")
    receipts = REPORTS_DIR / "receipts"
    if receipts.exists():
        paths += receipts.glob("run-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.json")

    def sort_key(path: Path) -> tuple[str, bool, str]:
        is_receipt = path.parent == receipts
        date = path.stem[4:14] if is_receipt else path.stem[:10]
        # Several runs of one milestone can land on the same date. Sorting only
        # by YYYY-MM-DD made filesystem enumeration order choose the evidence —
        # on M18 that put the 10:08 quick null ahead of the 10:12 full pass. The
        # report's own UTC stamp is the canonical run order already used by the
        # publisher and rotation ledger. Unreadable files retain a deterministic
        # date/name fallback and are still surfaced later by verify().
        generated_at = ""
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict) and isinstance(parsed.get("generated_at"), str):
                generated_at = parsed["generated_at"]
        except (OSError, ValueError):
            pass
        stamp = generated_at or date
        # For twins with the same generated_at, try the full report before its
        # compact receipt; path name makes all remaining ties deterministic.
        return stamp, not is_receipt, path.name

    return sorted(paths, key=sort_key, reverse=True)


def check_m01(report: dict) -> tuple[bool | None, str]:
    """2D Ising: the susceptibility χ peaks at the (finite-size) critical point.

    Returns ``None`` if this report isn't an Ising χ-sweep (not applicable).
    Otherwise recovers T at max(χ) and asserts it sits near Onsager's exact T_c
    — a generous tolerance, since this catches a broken simulation, not a
    high-precision exponent claim.

    Samples that provably did not equilibrate are excluded from peak candidacy
    (see ``nonequilibrated_indices``) and named in the returned message, so the
    exclusion is disclosed rather than quietly applied.
    """
    # M06 (3D Ising) also carries top-level T+chi but a different experiment tag
    # and a different T_c — it has its own check; don't grade it against Onsager.
    # Legacy M01 dumps carry no experiment field; the rendered ones tag
    # "M01-ising-verification". Anything else with a tag belongs to another check.
    exp = report.get("experiment")
    if exp and not exp.startswith("M01"):
        return None, "not the 2D Ising χ-sweep"
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi):
        return None, "not an Ising χ-sweep"
    quality = assess_m01_quality(report)
    excluded = quality["excluded_indices"]
    if quality["status"] == "invalid":
        return False, quality["note"]

    peak_T = quality["peak_t"]
    # The default sweep's 0.1-spaced grid can resolve the peak to roughly one
    # bin.  ±0.1 remains a regression/calibration gate, not a precision claim,
    # but no longer passes a result two whole bins away from Onsager.
    tol = 0.1
    ok = abs(peak_T - ONSAGER_TC) <= tol
    msg = f"χ peak at T={peak_T:.3f} vs Onsager {ONSAGER_TC:.3f} (tol ±{tol})"
    if excluded:
        where = ", ".join(f"T={T[i]:.3f}" for i in excluded)
        msg += f" · {len(excluded)} non-equilibrated sample(s) excluded ({where})"
    return ok, msg


def _loglog_slope(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least-squares slope + R² of ``log y`` vs ``log x`` (stdlib only).

    The check re-derives the scaling exponent itself rather than trusting the
    number the experiment reported — a receipt, not an honour-system echo.
    """
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    n = len(lx)
    mx, my = sum(lx) / n, sum(ly) / n
    sxx = sum((a - mx) ** 2 for a in lx)
    sxy = sum((a - mx) * (b - my) for a, b in zip(lx, ly))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((b - (slope * a + intercept)) ** 2 for a, b in zip(lx, ly))
    ss_tot = sum((b - my) ** 2 for b in ly)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, r2


def check_m02(report: dict) -> tuple[bool | None, str]:
    """Finite-size scaling: the peak susceptibility grows as χ_max ∝ L^(γ/ν).

    Returns ``None`` unless this is an M02 report. Otherwise re-fits the slope
    of log χ_max vs log L from the per-L peaks and asserts it sits near the
    exact 2D Ising exponent γ/ν = 7/4, with a tight log-log fit. A generous
    tolerance — this catches a simulation that scales wrong (or not at all),
    not a high-precision exponent measurement.
    """
    if report.get("experiment") != "M02-finite-size-scaling":
        return None, "not a finite-size-scaling report"
    curves = report.get("curves") or []
    Ls = [c.get("L") for c in curves]
    chimax = [c.get("chi_max") for c in curves]
    if len(Ls) < 3 or any(v is None or v <= 0 for v in Ls + chimax):
        return None, "finite-size-scaling report missing per-L peaks"
    slope, r2 = _loglog_slope(Ls, chimax)
    tol = 0.15
    ok = abs(slope - GAMMA_OVER_NU) <= tol and r2 >= 0.97
    return ok, (
        f"χ_max ∝ L^{slope:.3f} vs γ/ν={GAMMA_OVER_NU:.2f} "
        f"(tol ±{tol}, R²={r2:.3f}, {len(Ls)} sizes)"
    )


def _collapse_loss(curves, beta_over_nu, inv_nu=INV_NU, tc=ONSAGER_TC, n_bins=24) -> float:
    """Stdlib port of ``m03.collapse_quality`` — the data-collapse residual.

    Rescales every ``(L, T, M)`` curve to ``x=(T-tc)·L^(1/ν)``, ``y=M·L^(β/ν)``,
    interpolates each onto a shared grid over the x-overlap window, and returns
    the mean per-bin cross-curve variance normalized by the pooled y-variance.
    ``inf`` if fewer than two curves overlap. A receipt that re-derives the
    number rather than echoing it; mirrors how ``_loglog_slope`` ports M02.
    """
    rescaled = []
    for (L, T, M) in curves:
        x = [(t - tc) * L ** inv_nu for t in T]
        y = [m * L ** beta_over_nu for m in M]
        pairs = sorted(zip(x, y))
        rescaled.append(([p[0] for p in pairs], [p[1] for p in pairs]))
    if len(rescaled) < 2:
        return math.inf
    lo = max(xs[0] for xs, _ in rescaled)
    hi = min(xs[-1] for xs, _ in rescaled)
    if not (hi > lo):
        return math.inf

    centers = [lo + (hi - lo) * i / (n_bins - 1) for i in range(n_bins)]

    def _interp(xs, ys, c):
        if c <= xs[0]:
            return ys[0]
        if c >= xs[-1]:
            return ys[-1]
        for k in range(1, len(xs)):
            if xs[k] >= c:
                x0, x1, y0, y1 = xs[k - 1], xs[k], ys[k - 1], ys[k]
                if x1 == x0:
                    return y0
                return y0 + (y1 - y0) * (c - x0) / (x1 - x0)
        return ys[-1]

    cols = [[_interp(xs, ys, c) for xs, ys in rescaled] for c in centers]
    all_y = [v for col in cols for v in col]
    n_all = len(all_y)
    mean_all = sum(all_y) / n_all
    pooled_var = sum((v - mean_all) ** 2 for v in all_y) / n_all
    if pooled_var <= 0.0:
        return 0.0

    bin_vars = []
    for col in cols:
        m = sum(col) / len(col)
        bin_vars.append(sum((v - m) ** 2 for v in col) / len(col))
    return (sum(bin_vars) / len(bin_vars)) / pooled_var


def _fit_beta_over_nu(curves, lo=0.0, hi=0.5, tc=ONSAGER_TC, tol=1e-6) -> tuple[float, float]:
    """Stdlib golden-section minimization of ``_collapse_loss`` over β/ν."""
    gr = (math.sqrt(5.0) - 1.0) / 2.0
    f = lambda bon: _collapse_loss(curves, bon, tc=tc)
    a, b = lo, hi
    c, d = b - gr * (b - a), a + gr * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(200):
        if abs(b - a) < tol:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - gr * (b - a); fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + gr * (b - a); fd = f(d)
    xm = 0.5 * (a + b)
    return xm, f(xm)


def check_m03(report: dict) -> tuple[bool | None, str]:
    """Data collapse: M·L^(β/ν) vs (T-T_c)·L^(1/ν) overlays onto one master curve.

    Returns ``None`` unless this is an M03 report. Otherwise re-derives β/ν
    *independently* from the per-L (T, M) curves by minimizing the collapse loss
    (a stdlib port of ``m03.collapse_quality``/``fit_beta_over_nu``), and asserts
    the fit lands near the exact 2D Ising value β/ν = 1/8 AND the collapse
    residual at the exact exponents is below threshold. A receipt, not an
    honour-system echo of the reported number.
    """
    if report.get("experiment") != "M03-data-collapse":
        return None, "not a data-collapse report"
    raw = report.get("curves") or []
    curves = []
    for c in raw:
        L, T, M = c.get("L"), c.get("T"), c.get("M")
        if L and T and M and len(T) == len(M):
            curves.append((L, list(T), list(M)))
    if len(curves) < 3:
        return None, "data-collapse report missing per-L (T, M) curves"

    bon_fit, _ = _fit_beta_over_nu(curves)
    quality = _collapse_loss(curves, BETA_OVER_NU)   # loss at the EXACT exponents
    tol, q_thresh = 0.03, 0.02
    ok = abs(bon_fit - BETA_OVER_NU) <= tol and quality <= q_thresh
    return ok, (
        f"collapse β/ν={bon_fit:.3f} vs 1/8={BETA_OVER_NU:.3f} "
        f"(tol ±{tol}), residual={quality:.2e} (≤{q_thresh}), {len(curves)} sizes"
    )


def check_m06(report: dict) -> tuple[bool | None, str]:
    """3D simple-cubic Ising: the χ peak locates T_c near the MC benchmark 4.5115.

    Returns ``None`` unless this is an M06 report. Otherwise re-derives the
    critical temperature *independently* from the per-T (T, χ) arrays — a coarse
    argmax refined by a 3-point parabola through the peak — and asserts it sits
    near the Monte-Carlo benchmark T_c ≈ 4.5115. The tolerance is deliberately
    generous (±0.15): on a small finite lattice the χ peak sits at a
    pseudo-critical T_c(L) shifted *above* the infinite-volume value, so this
    catches a broken 3D simulation, not a precision-T_c claim. A receipt that
    re-computes the number rather than echoing the reported one.
    """
    if report.get("experiment") != "M06-3d-ising":
        return None, "not a 3D-Ising report"
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi) or len(T) < 3:
        return None, "3D-Ising report missing (T, χ) arrays"
    i = max(range(len(chi)), key=lambda k: chi[k])
    # 3-point parabola refinement of the peak (stdlib port of m06.refine_peak).
    if 0 < i < len(T) - 1:
        y0, y1, y2 = chi[i - 1], chi[i], chi[i + 1]
        denom = y0 - 2.0 * y1 + y2
        peak_T = T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    else:
        peak_T = T[i]
    tol = 0.15
    ok = abs(peak_T - TC_3D) <= tol
    return ok, f"3D χ peak at T={peak_T:.3f} vs MC benchmark {TC_3D:.4f} (tol ±{tol})"


def check_m04(report: dict) -> tuple[bool | None, str]:
    """2D Ising specific heat: the C(T) peak locates T_c near Onsager's exact 2.2692.

    Returns ``None`` unless this is an M04 report. Otherwise re-derives the
    critical temperature *independently* from the per-T (T, specific_heat) arrays
    — a coarse argmax refined by a 3-point parabola through the peak — and asserts
    the specific-heat peak sits near the exact 2D T_c. The tolerance (±0.1)
    absorbs the finite-L shift: on a finite lattice the C peak sits a little above
    the infinite-volume value, so this catches a broken thermal measurement, not a
    precision-T_c claim. A receipt that re-computes the number, not an echo.
    """
    if report.get("experiment") != "M04-specific-heat":
        return None, "not an M04 specific-heat report"
    T, cv = report.get("T"), report.get("specific_heat")
    if not T or not cv or len(T) != len(cv) or len(T) < 3:
        return None, "M04 report missing (T, specific_heat) arrays"
    i = max(range(len(cv)), key=lambda k: cv[k])
    # 3-point parabola refinement of the peak (stdlib port of m06.refine_peak).
    if 0 < i < len(T) - 1:
        y0, y1, y2 = cv[i - 1], cv[i], cv[i + 1]
        denom = y0 - 2.0 * y1 + y2
        peak_T = T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    else:
        peak_T = T[i]
    tol = 0.1
    ok = abs(peak_T - ONSAGER_TC) <= tol
    return ok, f"2D C peak at T={peak_T:.3f} vs Onsager exact {ONSAGER_TC:.4f} (tol ±{tol})"


# M05's two non-square geometries, each with its own exact T_c and tolerance.
# experiment tag → (lattice name, exact T_c, its closed form, tolerance).
#
# The tolerances are the SAME FRACTION of each lattice's own T_c (≈4%), not the
# same absolute number: the triangular ±0.15 is 4.1% of 3.6410, so the honeycomb
# gets ±0.06 (4.0% of 1.5187) rather than inheriting a ±0.15 that would be a
# 10% band on a much smaller number and would pass almost anything. Owned by the
# check, never read from the report, so a run cannot widen its own gate.
_M05_LATTICES = {
    "M05-triangular": ("triangular", TC_TRI, "4/ln3", 0.15),
    "M05-hexagonal": ("honeycomb", TC_HEX, "2/ln(2+√3)", 0.06),
}


def check_m05(report: dict) -> tuple[bool | None, str]:
    """Non-square 2D Ising: the χ peak locates T_c near that lattice's exact value.

    Returns ``None`` unless this is an M05 report. Otherwise re-derives the
    critical temperature *independently* from the per-T (T, χ) arrays — a coarse
    argmax refined by a 3-point parabola through the peak — and asserts it sits
    near the exact T_c **for the geometry the report claims**: 4/ln 3 ≈ 3.6410 on
    the triangular lattice, 2/ln(2+√3) ≈ 1.5187 on the honeycomb.

    Dispatching on the experiment tag is the whole point. The two lattices differ
    by more than a factor of two in T_c, so a check that graded both against one
    constant would either fail a perfectly good run or — worse — pass a run that
    had silently used the wrong geometry. The tolerances are deliberately generous
    in the same way M06's is: on a finite lattice the χ peak sits at a
    pseudo-critical T_c(L) shifted *above* the infinite-volume value, so this
    catches a broken simulation (wrong neighbour count, a non-bipartite update
    done with a checkerboard, a parity rule inverted at the seam), not a
    precision-T_c claim. A receipt that re-computes the number, not an echo.

    Only one M05 report grades per run — ``_grade`` takes the newest report the
    check understands, so whichever geometry ran most recently is the one on the
    board. Both lattices stay permanently visible on the scoreboard, which keys
    its rows off the tag rather than off recency (``scoreboard._m05``).

    **Non-equilibration guard (added 2026-08-11).** ``check_m01`` has excluded
    provably non-equilibrated samples from peak candidacy since the 2026-07-23
    campaign incident; this check did not, and the honeycomb's first canonical run
    proved that was a real gap rather than a theoretical one. A single L=128
    lattice frozen in a stripe domain at T = 1.379 — ⟨|m|⟩ = 0.573 between
    neighbours of 0.913 and 0.895, a 46σ *rise* with temperature, χ = 1164 against
    neighbours below 1.3 — was crowned by the bare argmax and dragged the reported
    T_c 9.2 % low. Equilibrium ⟨|m|⟩(T) is non-increasing, so a rise that large is
    forbidden rather than merely unlikely; ``nonequilibrated_indices`` is pure
    relational physics with no lattice-specific constants, so it applies here
    unchanged. Excluded samples are **named in the returned message**, never
    quietly dropped.

    **The guard fails closed on both kinds of absent scan.** Guard arrays present
    but unreadable, *and* guard arrays missing altogether, both return ``False``
    naming the gap — no T_c is claimed either way. The missing case is the one a
    hand-written report can reach: ``nonequilibrated_indices`` answers ``[]`` (no
    exclusions) for a report carrying no magnetization arrays, which is the right
    tolerance for the M01-era dumps that predate uncertainty arrays but is not a
    scan. No M05 report is legacy in that sense — ``m05.to_report`` and
    ``to_report_hex`` have emitted ``abs_mag``/``abs_mag_err`` since the
    triangular run of 2026-06-24 — so inside this check their absence means the
    guard could not run, and a check that never ran must not read as a clean
    pass. The legacy tolerance stays where it belongs, in ``check_m01``.
    """
    lattice = _M05_LATTICES.get(report.get("experiment"))
    if lattice is None:
        return None, "not an M05 non-square-Ising report"
    name, exact, form, tol = lattice
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi) or len(T) < 3:
        return None, "M05 report missing (T, χ) arrays"

    if report.get("abs_mag") is None and report.get("abs_mag_err") is None:
        # No guard arrays at all — the scan had nothing to read, so it did not
        # run. Disclosed as a failure rather than inheriting check_m01's legacy
        # tolerance, which would let a hand-written M05 report grade clean on a
        # guard that never executed.
        return False, (f"{name} run carries no equilibration guard arrays "
                       f"(abs_mag / abs_mag_err) — the non-equilibration scan "
                       f"could not run, so no T_c is claimed")

    excluded = nonequilibrated_indices(report)
    if excluded is None:
        # A guard array is present but unusable — fail closed. A scan that never
        # ran must never be mistaken for a clean one.
        return False, (f"{name} run carries an unreadable equilibration guard "
                       f"array (abs_mag / abs_mag_err) — no T_c claimed")
    if len(excluded) > len(T) // 5:
        return False, (f"{name} run failed to equilibrate at {len(excluded)} of "
                       f"{len(T)} temperatures — no T_c claimed")

    candidates = [k for k in range(len(chi)) if k not in set(excluded)]
    i = max(candidates, key=lambda k: chi[k])
    # 3-point parabola refinement of the peak (stdlib port of m06.refine_peak).
    # Neighbours are only used when they are themselves usable samples.
    if 0 < i < len(T) - 1 and (i - 1) not in set(excluded) and (i + 1) not in set(excluded):
        y0, y1, y2 = chi[i - 1], chi[i], chi[i + 1]
        denom = y0 - 2.0 * y1 + y2
        peak_T = T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    else:
        peak_T = T[i]
    ok = abs(peak_T - exact) <= tol
    msg = (f"{name} χ peak at T={peak_T:.3f} vs exact {form} = {exact:.4f} "
           f"(tol ±{tol})")
    if excluded:
        msg += (f" · excluded {len(excluded)} non-equilibrated sample(s) at "
                f"T={', '.join(f'{T[k]:.4f}' for k in excluded)}")
    return ok, msg


def _refine_peak_stdlib(T, y) -> float:
    """Sub-grid peak location via a 3-point parabola (stdlib port of m06.refine_peak).

    The discrete argmax is only accurate to the grid spacing ΔT; fitting a
    quadratic through the peak sample and its two neighbours recovers the vertex.
    Falls back to the discrete argmax T when the peak is on an endpoint. Shared by
    the per-q M07 check below so every q is graded the same way M04/M05/M06 grade
    their single peak.
    """
    i = max(range(len(y)), key=lambda k: y[k])
    if 0 < i < len(T) - 1:
        y0, y1, y2 = y[i - 1], y[i], y[i + 1]
        denom = y0 - 2.0 * y1 + y2
        return T[i] if denom == 0 else T[i] + 0.5 * (y0 - y2) / denom * (T[i] - T[i - 1])
    return T[i]


def check_m07(report: dict) -> tuple[bool | None, str]:
    """2D q-state Potts: each q's χ peak locates its exact T_c = 1/ln(1+√q).

    Returns ``None`` unless this is an M07 report. Otherwise re-derives the
    critical temperature *independently* for every q from its per-q (T, χ) arrays
    — a coarse argmax refined by a 3-point parabola — and asserts each lands near
    the exact Potts T_c. The transition is continuous for q ≤ 4 and **first-order**
    for q ≥ 5; first-order transitions have stronger finite-size effects and
    metastability, so the q ≥ 5 tolerance is widened (±0.15) relative to the
    continuous q ≤ 4 tolerance (±0.1) — a physical allowance for the larger
    pseudo-critical shift, not a fudge: a broken simulation (wrong T_c, wrong
    order parameter, a non-ordering lattice) still fails by a wide margin. A
    receipt that re-computes each number, not an echo.
    """
    if report.get("experiment") != "M07-potts":
        return None, "not an M07 Potts report"
    per_q = report.get("per_q")
    if not per_q:
        return None, "M07 report missing per-q arrays"

    parts: list[str] = []
    all_ok = True
    graded = 0
    for entry in per_q:
        q = entry.get("q")
        T, chi = entry.get("T"), entry.get("chi")
        if not q or not T or not chi or len(T) != len(chi) or len(T) < 3:
            continue
        graded += 1
        peak_T = _refine_peak_stdlib(T, chi)
        tc_exact = 1.0 / math.log(1.0 + math.sqrt(q))
        # Continuous (q≤4): ±0.1. First-order (q≥5): ±0.15 — stronger finite-size
        # / metastability shift on a finite lattice (a documented physical effect,
        # not a tolerance fudge; a broken run still misses by far more).
        tol = 0.1 if q <= 4 else 0.15
        ok = abs(peak_T - tc_exact) <= tol
        all_ok = all_ok and ok
        parts.append(f"q={q}: T={peak_T:.3f} vs {tc_exact:.3f} (±{tol}){'' if ok else ' ✗'}")

    if graded == 0:
        return None, "M07 report has no gradable (T, χ) per-q arrays"
    return all_ok, "Potts χ peaks — " + "; ".join(parts)


def check_m08(report: dict) -> tuple[bool | None, str]:
    """2D XY BKT: the helicity-modulus jump crossing locates T_BKT near 0.8929.

    Returns ``None`` unless this is an M08 report. Otherwise re-derives the
    transition temperature *independently* from the per-T (T, helicity) arrays —
    the crossing of Υ(T) with the universal-jump line (2/π)·T, found by linear
    interpolation across the first downward sign change of g(T) = Υ(T) − (2/π)·T —
    and asserts it sits near the MC/RG benchmark T_BKT ≈ 0.8929.

    The tolerance is deliberately generous (**±0.07**), wider than the sharp-peak
    checks (M04's ±0.1 is on a *much* larger T_c, so 0.07 here is the looser
    *relative* window). BKT has **no order-parameter peak** and notoriously strong
    **logarithmic finite-size corrections**, so a single-L crossing is honestly a
    coarse estimate that typically sits a little *above* 0.8929 (the same finite-L
    honesty M05/M06 carry). ±0.07 absorbs that log-correction drift while still
    catching a broken simulation — a wrong helicity estimator (e.g. the dropped
    1/T fluctuation term, the #1 XY failure mode) or an un-equilibrated run misses
    by far more, or fails to cross at all. A receipt that re-computes the number,
    not an echo.
    """
    if report.get("experiment") != "M08-xy-bkt":
        return None, "not an M08 XY-BKT report"
    T, Y = report.get("T"), report.get("helicity_modulus")
    if not T or not Y or len(T) != len(Y) or len(T) < 3:
        return None, "M08 report missing (T, helicity_modulus) arrays"

    # Re-derive the crossing of Υ(T) with (2/π)·T (a receipt, not an echo of the
    # reported tc_crossing): the first downward root of g = Υ − (2/π)·T.
    g = [Y[i] - TWO_OVER_PI * T[i] for i in range(len(T))]
    crossing = None
    for i in range(len(T) - 1):
        if g[i] >= 0.0 and g[i + 1] < 0.0:
            frac = g[i] / (g[i] - g[i + 1])
            crossing = T[i] + frac * (T[i + 1] - T[i])
            break
    if crossing is None:
        return False, (
            f"Υ(T) never crosses the (2/π)T jump line on [{T[0]:.3f}, {T[-1]:.3f}] "
            f"— no BKT crossing bracketed (window mis-placed or run un-equilibrated)"
        )
    tol = 0.07
    ok = abs(crossing - T_BKT) <= tol
    return ok, (
        f"XY helicity-jump crossing at T_BKT={crossing:.3f} vs benchmark "
        f"{T_BKT:.4f} (tol ±{tol})"
    )


def check_m09(report: dict) -> tuple[bool | None, str]:
    """2D Heisenberg / Mermin–Wagner: ⟨|m|⟩ drifts DOWN with L — the absence of order.

    Returns ``None`` unless this is an M09 report. This milestone has **no
    transition to locate** — its falsifiable signature is a *null done honestly*:
    under Mermin–Wagner the 2D Heisenberg model cannot spontaneously order at any
    T > 0 (and, unlike XY, has no BKT escape — π₁(S²)=0, no vortices), so at a
    fixed temperature the per-spin vector magnetization ⟨|m|⟩ **decreases
    monotonically as L grows**, drifting toward 0. PASS = that expected *absence*
    is reproduced; a non-decreasing ⟨|m|⟩(L) (a fake finite-T transition, or a
    broken simulation that orders spuriously) FAILS.

    The check re-derives the verdict from the report's (L, ⟨|m|⟩) arrays — a
    receipt, not an echo of the reported ``monotone_decreasing``: it confirms each
    successive L has a strictly smaller ⟨|m|⟩ (beyond a small Monte-Carlo noise
    floor built from the reported standard errors) AND that the slope of ⟨|m|⟩ vs
    1/L is positive (|m| washes out as L→∞, the infinite-volume value is ~0). The
    #1 way M09 ships wrong — reading a single small L where ⟨|m|⟩ looks finite and
    "finding" a transition — is exactly what a flat/rising sequence would show, so
    that failure is caught, not relabelled a discovery.
    """
    if report.get("experiment") != "M09-heisenberg":
        return None, "not an M09 Heisenberg report"
    Ls, m = report.get("L_values"), report.get("abs_mag")
    if not Ls or not m or len(Ls) != len(m) or len(Ls) < 3:
        return None, "M09 report missing (L_values, abs_mag) arrays (need ≥3 sizes)"
    err = report.get("abs_mag_err") or [0.0] * len(m)

    # Strictly decreasing beyond a 1.5·SEM noise floor (so Monte-Carlo jitter on a
    # statistically-flat pair can't masquerade as a drift — or break a real one).
    decreasing = all(
        m[i + 1] < m[i] - 1.5 * max(err[i], err[i + 1]) for i in range(len(m) - 1)
    )
    # Independent corroboration: ⟨|m|⟩ falls toward its 1/L→0 (infinite-volume)
    # intercept, so the least-squares slope of ⟨|m|⟩ against 1/L is positive.
    x = [1.0 / L for L in Ls]
    mx, my = sum(x) / len(x), sum(m) / len(m)
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, m))
    slope = sxy / sxx if sxx > 0 else 0.0

    ok = decreasing and slope > 0.0
    drift = " > ".join(f"{v:.3f}" for v in m)
    ratios = ", ".join(f"{m[i+1]/m[i]:.2f}" for i in range(len(m) - 1) if m[i] > 0)
    return ok, (
        f"⟨|m|⟩(L={','.join(map(str, Ls))}) = {drift} "
        f"(ratios {ratios}, slope vs 1/L = {slope:+.3f}) — "
        + ("drifts toward 0 with L: Mermin–Wagner absence of order reproduced"
           if ok else
           "does NOT monotonically decrease — a fake finite-T transition, not the "
           "expected absence")
    )


def check_m10(report: dict) -> tuple[bool | None, str]:
    """AFM Ising: the STAGGERED-χ peak locates T_N near Onsager's exact 2.2692.

    Returns ``None`` unless this is an M10 report. Otherwise re-derives the Néel
    temperature *independently* from the per-T (T, chi_staggered) arrays — a coarse
    argmax refined by a 3-point parabola through the peak — and asserts it sits near
    the exact 2D T_c (= T_N, by the bipartite gauge duality). The tolerance (±0.1)
    absorbs the finite-L shift, exactly as ``check_m04`` does on the same number; on
    a finite lattice the peak sits a little above the infinite-volume value, so this
    catches a broken AFM simulation, not a precision-T_N claim.

    A SECOND guard makes this milestone meaningful: it confirms the UNIFORM ⟨|m|⟩
    stayed small (≤ 0.3 across the sweep). The headline AFM bug is a silent sign
    error that reverts the model to the *ferromagnet* — which would still peak at
    2.2692, but on the *uniform* magnetization, with χ_staggered ≈ 0 and a large
    uniform ⟨|m|⟩ at low T. Requiring the staggered peak to be the real signal AND
    the uniform moment to stay ≈ 0 catches that masquerade. A receipt that
    re-computes the number, not an echo.
    """
    if report.get("experiment") != "M10-afm-ising":
        return None, "not an M10 AFM-Ising report"
    T, chi = report.get("T"), report.get("chi_staggered")
    if not T or not chi or len(T) != len(chi) or len(T) < 3:
        return None, "M10 report missing (T, chi_staggered) arrays"
    peak_T = _refine_peak_stdlib(T, chi)
    tol = 0.1
    near_tn = abs(peak_T - ONSAGER_TC) <= tol
    # The AFM signature: the uniform magnetization never orders (≈0 throughout). A
    # silent sign-flip to the FM would make this large — so it must stay small for
    # a PASS, not just the staggered peak landing on T_N.
    abs_mag = report.get("abs_mag") or []
    max_unif = max((abs(v) for v in abs_mag), default=0.0)
    unif_small = max_unif <= 0.3
    ok = near_tn and unif_small
    detail = (
        f"staggered χ_s peak at T={peak_T:.3f} vs Onsager exact {ONSAGER_TC:.4f} "
        f"(tol ±{tol}); uniform ⟨|m|⟩ ≤ {max_unif:.3f}"
    )
    if not unif_small:
        detail += " ✗ (uniform moment too large — looks like the FM, not the AFM)"
    return ok, detail


def check_m11(report: dict) -> tuple[bool | None, str]:
    """2D Edwards–Anderson spin glass: P(q) BROADENS as T → 0 — the T=0-critical signature.

    Returns ``None`` unless this is an M11 report. Like M09 (Mermin–Wagner) this
    milestone has **no finite-T transition to locate** — the 2D EA glass sits at the
    lower critical dimension (T_c = 0), so the verification is the *expected approach
    to the T = 0 critical point*: the disorder-averaged overlap distribution P(q)
    **broadens monotonically as T falls** (its second moment ⟨q²⟩ grows toward T = 0).
    A finite-T transition claim, or a P(q) that does **not** broaden, is the failure.

    The check re-derives the verdict from the report's (T, ⟨q²⟩) arrays — a receipt,
    not an echo of the reported ``monotone_broadening`` — and adds two physical
    guards so a broken/un-equilibrated run can't pass by accident:

    * **Broadening**: sorted by T ascending, ⟨q²⟩ is (weakly) decreasing — i.e. it
      grows as T → 0. A small fraction of non-monotone steps is tolerated at the noisy
      low-T end (≥ 80% of steps must broaden, AND ⟨q²⟩_cold must exceed ⟨q²⟩_hot by a
      clear margin), since spin glasses are hard to equilibrate; a flat or shrinking
      ⟨q²⟩ fails.
    * **Symmetry**: P(q) = P(−q) by the ±J / spin-inversion symmetry, so the
      disorder-averaged ⟨q⟩ must stay ≈ 0 (the equilibration diagnostic). A large
      |⟨q⟩| means a single broken-symmetry replica leaked through (un-equilibrated or
      buggy), so it fails even if ⟨q²⟩ happened to rise.
    """
    if report.get("experiment") != "M11-spin-glass-2d":
        return None, "not an M11 spin-glass report"
    T, q2 = report.get("T"), report.get("q2_mean")
    if not T or not q2 or len(T) != len(q2) or len(T) < 3:
        return None, "M11 report missing (T, q2_mean) arrays (need ≥3 temperatures)"

    # Re-derive the broadening trend: sort by T, ⟨q²⟩ should fall as T rises.
    order = sorted(range(len(T)), key=lambda i: T[i])
    Ts = [T[i] for i in order]
    q2s = [q2[i] for i in order]
    steps = [q2s[i + 1] - q2s[i] for i in range(len(q2s) - 1)]
    n_down = sum(1 for d in steps if d <= 1e-9)
    frac = n_down / len(steps) if steps else 0.0
    q2_cold, q2_hot = q2s[0], q2s[-1]
    # Cold ⟨q²⟩ must clearly exceed hot (a real broadening, not noise), and ≥80% of
    # the adjacent steps must broaden (tolerating a little low-T Monte-Carlo jitter).
    broadens = frac >= 0.8 and q2_cold > q2_hot + 0.05

    # Symmetry / equilibration guard: |⟨q⟩| ≈ 0 by the ±J symmetry. Prefer the
    # re-derivable per-T ⟨q⟩ if present; else fall back to the reported diagnostic.
    # With NEITHER present the guard has nothing to grade — a named failure, never
    # a default-0.0 pass (fail closed, not open).
    qm = report.get("q_mean")
    if qm:
        max_abs_qmean = max(abs(v) for v in qm)
    elif "max_abs_q_mean" in report:
        max_abs_qmean = report["max_abs_q_mean"]
    else:
        return False, ("M11 report carries no symmetry/equilibration evidence "
                       "(neither q_mean nor max_abs_q_mean) — the P(q)=P(−q) "
                       "guard cannot run; failing closed")
    symmetric = max_abs_qmean <= 0.15

    ok = broadens and symmetric
    detail = (
        f"⟨q²⟩ grows {q2_hot:.3f}→{q2_cold:.3f} as T falls {Ts[-1]:.2f}→{Ts[0]:.2f} "
        f"({n_down}/{len(steps)} steps broaden); max|⟨q⟩|={max_abs_qmean:.3f} — "
        + ("P(q) broadens toward the T=0 critical point (2D EA orders only at T=0; "
           "no finite-T glass phase) — reproduced"
           if ok else
           ("⟨q²⟩ does NOT broaden monotonically toward T=0 — not the expected "
            "T=0-critical behaviour" if not broadens else
            "P(q) is not symmetric (|⟨q⟩| too large) — un-equilibrated or broken, "
            "not a clean overlap"))
    )
    return ok, detail


def _binder_crossing_stdlib(Ts, G_by_L) -> tuple[float | None, list[tuple]]:
    """Re-derive the multi-L Binder crossing from sorted arrays — stdlib, a receipt.

    ``Ts`` is the ascending temperature ladder; ``G_by_L`` maps each L (int) to its
    g_L(T) on that ladder. For each size pair the crossing is the first ``+ → −`` sign
    change of ``d(T) = g_large − g_small`` (larger L is more ordered below T_SG, less
    above), linear-interpolated to the zero of ``d``. Returns ``(primary_T, pairs)``
    where the primary estimate is the crossing of the two largest sizes (or the median
    of all pairwise crossings if that pair does not cross), and ``pairs`` is the list of
    ``(L_small, L_large, T)`` crossings. ``(None, [])`` when nothing crosses — an honest
    no-crossing, not an invented T_SG. Mirrors ``m12.locate_tsg`` deliberately: the
    check re-computes the number independently rather than echoing the reported one.
    """
    Ls = sorted(G_by_L)
    pairs: list[tuple] = []
    for a in range(len(Ls)):
        for b in range(a + 1, len(Ls)):
            gs, gl = G_by_L[Ls[a]], G_by_L[Ls[b]]
            d = [x - y for y, x in zip(gs, gl)]
            for i in range(len(d) - 1):
                if d[i] >= 0.0 and d[i + 1] < 0.0:
                    denom = d[i + 1] - d[i]
                    t = Ts[i] if denom == 0 else Ts[i] + (-d[i]) * (Ts[i + 1] - Ts[i]) / denom
                    pairs.append((Ls[a], Ls[b], float(t)))
                    break
    if not pairs:
        return None, []
    big = {Ls[-1], Ls[-2]} if len(Ls) >= 2 else {Ls[-1]}
    top = next((t for (a, b, t) in pairs if {a, b} == big), None)
    if top is None:
        ts = sorted(t for (_, _, t) in pairs)
        top = ts[len(ts) // 2]
    return float(top), pairs


def check_m12(report: dict) -> tuple[bool | None, str]:
    """3D Edwards–Anderson spin glass: a multi-L Binder crossing locates T_SG ≈ 1.10.

    Returns ``None`` unless this is an M12 report. Unlike M11 (2D, T_c = 0, no finite-T
    phase), the **3D** ±J glass has a genuine finite-temperature spin-glass transition;
    its fingerprint is the disorder-averaged Binder cumulant g_L(T) crossing at a single
    temperature across ≥3 lattice sizes on one shared ladder. The check **re-derives**
    that crossing from the report's per-L ``binder_by_L`` arrays (a receipt, not an echo
    of the reported ``crossing_T``) and asserts it lands near the bimodal-±J benchmark
    ``TC_SG_3D`` within the check-owned ``TC_SG_3D_TOL`` band, plus three guards so an
    under-equilibrated run can't pass:

    * **A crossing must exist**: ≥3 sizes must actually intersect. A smeared, crossing-
      free g_L(T) — the signature of parallel-tempering under-equilibration (M11's
      documented failure mode) — has no crossing and fails, rather than passing on a
      flat curve.
    * **PT scheduling, from the raw counters**: when the report carries the per-gap
      ``swap_attempts_by_L`` counters, every ladder must have attempted every gap. A
      partial pattern (some gaps attempted, some never) is the fragmented-scheduling
      signature of the even-``swap_every`` parity bug — the ladder decomposed into
      islands, so its crossing is not evidence. Re-derived from the counters, never
      from the ``pt_health_by_L`` strings; all-zero counters mean PT was off (the
      engine's own health rule), which the other guards grade. Reports without
      counters (pre-counter receipts) skip this guard.
    * **Symmetry / equilibration**: P(q) = P(−q) by the ±J symmetry, so the disorder-
      averaged ⟨q⟩ must stay ≈ 0 across every size and temperature. A large |⟨q⟩| means
      a broken-symmetry replica leaked through, so it fails even if a crossing appeared.
      With neither ``q_mean_by_L`` nor ``max_abs_q_mean`` present the guard fails
      closed — missing guard data is a named failure, never a default pass.
    """
    if report.get("experiment") != "M12-spin-glass-3d":
        return None, "not an M12 spin-glass report"
    T = report.get("T")
    binder_by_L = report.get("binder_by_L")
    if (not T or not binder_by_L or len(binder_by_L) < 3 or len(T) < 3
            or any(len(v) != len(T) for v in binder_by_L.values())):
        return None, "M12 report missing a shared T ladder or ≥3 per-L Binder arrays"

    # PT scheduling guard, re-derived from the raw attempt counters when present.
    attempts = report.get("swap_attempts_by_L")
    if attempts is not None:
        try:
            fragmented = []
            for L in sorted(attempts, key=lambda k: int(k)):
                counts = [float(a) for a in attempts[L]]
                if not counts or any(not math.isfinite(c) or c < 0 for c in counts):
                    raise ValueError("unreadable attempt counts")
                dead = [g for g, c in enumerate(counts) if c == 0]
                if dead and len(dead) < len(counts):     # partial = fragmented; all-zero = PT off
                    fragmented.append(f"L={L}: gaps {dead}")
        except (TypeError, ValueError, KeyError):
            return False, ("M12 swap_attempts_by_L is malformed — the PT scheduling "
                           "receipt cannot be re-derived; failing closed")
        if fragmented:
            return False, ("PT ladder fragmented — swap gaps never attempted "
                           f"({'; '.join(fragmented)}); the ladder decomposed into "
                           "islands, so the crossing is not evidence of the transition")

    order = sorted(range(len(T)), key=lambda i: T[i])
    Ts = [float(T[i]) for i in order]
    G_by_L = {int(k): [float(v[i]) for i in order] for k, v in binder_by_L.items()}
    crossing_T, pairs = _binder_crossing_stdlib(Ts, G_by_L)

    # Symmetry / equilibration guard: |⟨q⟩| ≈ 0 across all sizes and temperatures.
    # Prefer the re-derivable per-L arrays; else the reported scalar; with neither,
    # fail closed rather than defaulting the guard value to a pass.
    qm = report.get("q_mean_by_L") or {}
    max_abs_qmean = max((abs(x) for v in qm.values() for x in v), default=None)
    if max_abs_qmean is None:
        if "max_abs_q_mean" in report:
            max_abs_qmean = report["max_abs_q_mean"]
        else:
            return False, ("M12 report carries no symmetry/equilibration evidence "
                           "(neither q_mean_by_L nor max_abs_q_mean) — the "
                           "P(q)=P(−q) guard cannot run; failing closed")

    has_crossing = crossing_T is not None
    near = has_crossing and abs(crossing_T - TC_SG_3D) <= TC_SG_3D_TOL
    symmetric = max_abs_qmean <= 0.15
    ok = near and symmetric

    ct_str = f"{crossing_T:.3f}" if has_crossing else "none"
    pair_str = ", ".join(f"{a}/{b}→{t:.3f}" for (a, b, t) in pairs) or "no pair crosses"
    detail = (
        f"Binder crossing T_SG = {ct_str} vs benchmark {TC_SG_3D:.2f} "
        f"(tol ±{TC_SG_3D_TOL}); pairwise [{pair_str}]; max|⟨q⟩|={max_abs_qmean:.3f} — "
        + (f"g_L(T) cross near T_SG≈{TC_SG_3D:.2f} — the finite-T 3D spin-glass "
           "transition, reproduced" if ok else
           ("no multi-L Binder crossing resolved (smeared g_L(T) — likely "
            "under-equilibrated; needs more disorder realizations / longer parallel "
            "tempering)" if not has_crossing else
            (f"crossing far from the {TC_SG_3D:.2f} benchmark" if not near else
             "P(q) not symmetric (|⟨q⟩| too large) — un-equilibrated or broken")))
    )
    return ok, detail


def check_m13(report: dict) -> tuple[bool | None, str]:
    """Frustrated triangular antiferromagnet: the integrated residual entropy ≈ 0.3383 k_B.

    Returns ``None`` unless this is an M13 report. Otherwise **re-derives** the residual
    entropy from the report's own ``(T, specific_heat)`` arrays — re-integrating C(T)/T
    down from the free-spin reference S(∞) = ln 2 with the shared ``entropy`` primitive
    (a receipt, not an echo of the reported ``s0_measured``) — and asserts it lands near
    Wannier's exact ``S0/N = 0.3383`` within the check-owned ±0.03 band. Two things make
    the pass honest rather than lucky:

    * **The integration is redone here**, from the raw C(T), so a report cannot ship a
      hand-set residual; the number is recomputed from the curve every grade.
    * **A ground-state anchor**: the frustrated triangular AFM has an exact ground energy
      of −1 per spin (two of every triangle's three bonds satisfied). The coldest measured
      energy must sit near −1, so an accidental ferromagnet (e → −3) or a wrong-geometry
      run fails outright even if its integral happened to land near 0.3383.

    A miss (coarse grid / small lattice / broken model) fails, and the milestone ships as
    an honest ``[~]`` failed-calibration null — never a fake green.
    """
    if report.get("experiment") != "M13-triangular-afm":
        return None, "not an M13 triangular-AFM report"
    T, C = report.get("T"), report.get("specific_heat")
    if not T or not C or len(T) != len(C) or len(T) < 3:
        return None, "M13 report missing parallel (T, specific_heat) arrays"

    from .entropy import LN2, residual_entropy
    s0 = residual_entropy(T, C, s_inf=LN2, add_high_t_tail=True)
    near = abs(s0 - WANNIER_S0) <= WANNIER_S0_TOL

    # Ground-state energy anchor: the coldest measured energy per spin ≈ −1.
    energy = report.get("energy") or []
    e_ground = min(energy) if energy else None
    ground_ok = e_ground is not None and abs(e_ground - TRI_AFM_GROUND_ENERGY) <= TRI_AFM_GROUND_ENERGY_TOL

    ok = bool(near and ground_ok)
    e_str = f"{e_ground:.3f}" if e_ground is not None else "—"
    detail = (
        f"integrated residual S0/N = {s0:.4f} vs Wannier exact {WANNIER_S0:.4f} "
        f"(tol ±{WANNIER_S0_TOL}); ground-state energy {e_str}/spin (exact −1) — "
        + ("frustrated residual entropy reproduced by C/T integration" if ok else
           ("residual near 0.3383 but the ground energy is off (wrong sign/geometry?)"
            if near and not ground_ok else
            ("ground energy sane but the integrated residual misses 0.3383 — coarse "
             "grid / small lattice / under-converged C" if ground_ok and not near else
             "both the residual and the ground energy are off — broken run")))
    )
    return ok, detail


def check_m14(report: dict) -> tuple[bool | None, str]:
    """Random-bond Ising: the disorder-averaged energy ON the Nishimori line is exact.

    Returns ``None`` unless this is an M14 report. M14's verified claim is NOT the
    (genuinely hard) multicritical-point location — it is the **exact Nishimori-line
    internal energy**. On the line ``tanh(J/T) = 1 − 2p``, and Nishimori's gauge symmetry
    fixes the disorder-averaged energy per spin to the identity

        E/N = −2 J tanh(J/T) = −2 J (1 − 2p)      (square lattice, exact, any L),

    so the check **re-derives** the exact target from each calibration point's own ``T``
    (a receipt, not an echo of the reported ``energy_exact``) and asserts the measured
    disorder-averaged energy lands within the check-owned ±0.05 band, at every point. Two
    guards keep the pass honest:

    * **On the line**: each point must actually sit on the Nishimori line — the check
      re-checks ``tanh(1/T) ≈ 1 − 2p`` — else there is no exact identity to grade against
      and the point is rejected (a run can't smuggle in an off-line point that happens to
      match some other energy).
    * **A spread of points**: ≥3 distinct ``p`` must be graded, so a single lucky point
      can't carry the leaf.

    The precise MNP (p_c ≈ 0.109, T_c ≈ 0.953) is mapped only approximately at reachable
    scale and is deliberately **not** gated — a documented open edge, not a fake green.
    """
    if report.get("experiment") != "M14-random-bond-nishimori":
        return None, "not an M14 random-bond report"
    pts = report.get("calibration_points")
    if not pts or len(pts) < 3:
        return None, "M14 report missing ≥3 Nishimori-line calibration points"

    parts: list[str] = []
    all_ok = True
    graded = 0
    off_line_count = 0
    for pt in pts:
        p, T, e = pt.get("p"), pt.get("T"), pt.get("energy")
        if p is None or T is None or e is None or T <= 0:
            continue
        # Guard 1 — the point must be on the Nishimori line, else the identity doesn't apply.
        on_line = abs(math.tanh(1.0 / T) - (1.0 - 2.0 * p)) <= NISHIMORI_LINE_TOL
        if not on_line:
            off_line_count += 1
            all_ok = False
            parts.append(f"p={p:.3f}: OFF the Nishimori line ✗")
            continue
        graded += 1
        # Re-derive the exact target from T alone (a receipt): E/N = −2·tanh(1/T).
        e_exact = -2.0 * math.tanh(1.0 / T)
        dev = abs(e - e_exact)
        ok = dev <= MNP_ENERGY_TOL
        all_ok = all_ok and ok
        parts.append(f"p={p:.3f}: E={e:.3f} vs {e_exact:.3f} (Δ={dev:.3f}){'' if ok else ' ✗'}")

    # An off-line point is breakage evidence (broken temperature or p wiring — the
    # exact failure the on-line guard exists to catch), so it grades FAIL here even
    # when <3 points remain on-line; ``None`` (fall through to an older report) is
    # reserved for reports that structurally lack gradable points.
    if graded < 3 and off_line_count == 0:
        return None, "M14 report has <3 gradable on-line calibration points"
    detail = (
        f"Nishimori-line energy E/N vs exact −2·tanh(1/T) — " + "; ".join(parts) + " — "
        + ("the exact disorder-averaged Nishimori-line energy is reproduced across the "
           "line (the MNP p_c≈0.109 itself is mapped only approximately at this scale)"
           if all_ok else
           (f"{off_line_count} calibration point(s) sit OFF the Nishimori line — "
            "broken (p, T) wiring, graded as failure rather than skipped"
            if off_line_count else
            "measured energy departs from the exact Nishimori-line identity — a broken "
            "random-bond run, not the expected exact energy"))
    )
    return all_ok, detail


def _loglog_slope_r2(xs: list[float], ys: list[float]) -> tuple[float, float, int]:
    """Least-squares slope + R² of ``log y`` vs ``log x`` (stdlib), plus the point count.

    Distinct from ``_loglog_slope`` (which takes raw x,y and logs them): here ``xs``/``ys``
    are ALREADY the window-selected raw ``t``/``L`` and this logs them once. Returns
    ``(slope, r2, n)``. The check re-fits the M15 growth exponent itself — a receipt, not an
    echo of the reported number.
    """
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    n = len(lx)
    mx, my = sum(lx) / n, sum(ly) / n
    sxx = sum((a - mx) ** 2 for a in lx)
    sxy = sum((a - mx) * (b - my) for a, b in zip(lx, ly))
    slope = sxy / sxx if sxx > 0 else 0.0
    intercept = my - slope * mx
    ss_res = sum((b - (slope * a + intercept)) ** 2 for a, b in zip(lx, ly))
    ss_tot = sum((b - my) ** 2 for b in ly)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, r2, n


def check_m15(report: dict) -> tuple[bool | None, str]:
    """Glauber domain growth: the coarsening exponent n in L(t) ∼ t^n is Allen–Cahn's ½.

    Returns ``None`` unless this is an M15 report. Otherwise **re-derives** the growth
    exponent from the report's own ``(times, L_corr)`` arrays — re-selecting the scaling
    window (t ≥ t_fit_min, L ∈ [L_min_fit, sat_frac·L]) with the *stored* window rule and
    re-fitting ``log L`` vs ``log t`` (a receipt, not an echo of the reported ``exponent``) —
    and asserts it lands near the Allen–Cahn ½ within the check-owned ±0.06 band. Two guards
    keep the pass honest:

    * **A clean power law**: the re-fit R² must clear ``M15_MIN_R2`` (0.99). A noisy or curved
      L(t) — an un-quenched run, or a fit dragged across the finite-size saturation knee —
      fails rather than passing on a slope through bad points.
    * **Real growth over range**: ≥5 window points spanning at least a decade in ``t`` and a
      clearly growing L (L_hi ≥ 2·L_lo), so a nearly-flat/frozen curve can't score a fit.

    The graded estimator is the **correlation length** (the energy length rides along in the
    report as a documented cross-check). The finite-time effective exponent honestly sits a
    few percent below ½; the band absorbs that documented preasymptotic bias without admitting
    a broken exponent (diffusive ¼, ballistic 1, frozen ~0).
    """
    if report.get("experiment") != "M15-glauber-domain-growth":
        return None, "not an M15 Glauber domain-growth report"
    t, L = report.get("times"), report.get("L_corr")
    if not t or not L or len(t) != len(L) or len(t) < 5:
        return None, "M15 report missing parallel (times, L_corr) arrays"

    L_box = report.get("L")
    if not L_box:
        return None, "M15 report missing the lattice size L"
    t_fit_min = _window_param(report, "t_fit_min", M15_T_FIT_MIN, M15_T_FIT_MIN_BOUNDS)
    l_min_fit = _window_param(report, "l_min_fit", M15_L_MIN_FIT, M15_L_MIN_FIT_BOUNDS)
    sat_frac = _window_param(report, "sat_frac", M15_SAT_FRAC, M15_SAT_FRAC_BOUNDS)
    if t_fit_min is None or l_min_fit is None or sat_frac is None:
        return False, (
            "M15 scaling-window parameters sit outside the check-owned bounds "
            f"(t_fit_min∈{M15_T_FIT_MIN_BOUNDS}, l_min_fit∈{M15_L_MIN_FIT_BOUNDS}, "
            f"sat_frac∈{M15_SAT_FRAC_BOUNDS}) — a run cannot choose its own fit window"
        )

    # Re-select the scaling window from the stored rule and re-fit the exponent.
    xs, ys = [], []
    for ti, Li in zip(t, L):
        if (Li is None or ti is None or Li <= 0 or not math.isfinite(Li)):
            continue
        if ti >= t_fit_min and l_min_fit <= Li <= sat_frac * L_box:
            xs.append(float(ti)); ys.append(float(Li))
    if len(xs) < 5:
        return None, "M15 report has <5 points inside the scaling window"

    slope, r2, n = _loglog_slope_r2(xs, ys)
    t_lo, t_hi = min(xs), max(xs)
    L_lo, L_hi = min(ys), max(ys)
    decade = t_hi / t_lo >= 10.0
    grew = L_hi >= 2.0 * L_lo
    clean = r2 >= M15_MIN_R2
    near = abs(slope - ALLEN_CAHN_EXPONENT) <= ALLEN_CAHN_TOL
    ok = bool(near and clean and decade and grew)

    detail = (
        f"coarsening exponent n = {slope:.3f} vs Allen–Cahn {ALLEN_CAHN_EXPONENT:.2f} "
        f"(tol ±{ALLEN_CAHN_TOL}, R²={r2:.4f}, {n} pts, t∈[{t_lo:.0f},{t_hi:.0f}], "
        f"L∈[{L_lo:.1f},{L_hi:.1f}]) — "
        + ("L(t)∼t^n grows as Allen–Cahn t^(1/2) predicts (effective exponent a few percent "
           "below ½ is the documented preasymptotic correction)" if ok else
           ("R² too low — L(t) is not a clean power law (un-quenched or fit across the "
            "saturation knee)" if not clean else
            ("window too short — needs ≥1 decade in t and a clearly growing L" if not (decade and grew) else
             "exponent off the Allen–Cahn ½ prediction — a broken coarsening run")))
    )
    return ok, detail


def check_m16(report: dict) -> tuple[bool | None, str]:
    """Re-derive whether a quenched 3D glass ages on the ``dt/t_w`` clock."""
    if report.get("experiment") != "M16-spin-glass-aging":
        return None, "not an M16 spin-glass aging report"
    tws, dts = report.get("waiting_times"), report.get("delta_times")
    rows = report.get("correlations")
    if not isinstance(tws, list) or not isinstance(dts, list) or not isinstance(rows, dict):
        return None, "M16 report missing waiting-time correlation table"
    try:
        metrics = _m16_aging_metrics(tws, dts, rows)
    except (TypeError, ValueError, OverflowError) as exc:
        return False, f"invalid M16 correlation table: {exc}"

    ratio_groups = metrics["ratio_groups"]
    diff_groups = metrics["difference_groups"]
    collapse_ratio = metrics["collapse_ratio"]
    fixed_lag = metrics["fixed_lag"]
    fixed = metrics["fixed_lag_correlations"]
    separation = metrics["fixed_lag_separation"]
    ok = _m16_aging_gate(metrics)
    return ok, (
        f"3D EA two-time correlation: t/t_w collapse residual is {collapse_ratio:.2f}× "
        f"the t−t_w residual ({ratio_groups} ratio groups, {diff_groups} lag groups); "
        f"at fixed Δt={fixed_lag}, C rises {fixed[0]:.3f}→{fixed[-1]:.3f} "
        f"(Δ={separation:+.3f}) — " +
        ("aging/time-translation breaking resolved" if ok else "aging gate not resolved")
    )


def _refit_growth_exponent(times, width, t_fit_min: float, w_fit_min: float):
    """Re-select M17's scaling window from the stored rule and re-fit ``log w`` vs ``log t``.

    Stdlib-only twin of ``m17.fit_exponent`` — the check must arrive at the exponent from the
    raw curve, never by reading the reported one. Returns ``(slope, r2, n, t_lo, t_hi)`` or
    ``None`` when fewer than four points survive the window.
    """
    xs, ys = [], []
    for t, w in zip(times or [], width or []):
        if t is None or w is None:
            continue
        t, w = float(t), float(w)
        if not (math.isfinite(t) and math.isfinite(w)) or w <= 0:
            continue
        if t >= t_fit_min and w >= w_fit_min:
            xs.append(t); ys.append(w)
    if len(xs) < 4:
        return None
    slope, r2, n = _loglog_slope_r2(xs, ys)
    return slope, r2, n, min(xs), max(xs)


def check_m17(report: dict) -> tuple[bool | None, str]:
    """KPZ growth on a ring: β = 1/3, α = 1/2, z = 3/2 — and the controls must NOT agree.

    Returns ``None`` unless this is an M17 report. Otherwise **re-derives** every graded
    number from the report's own raw arrays and grades five things, all of which must hold:

    1. **β = 1/3 for the KPZ model**, re-fit from ``growth.kpz.{times,width}`` with the stored
       window rule, inside the check-owned ±0.04 band, on a clean power law (R² ≥ 0.99).
    2. **The controls separate.** The *same* re-fit applied to the Edwards–Wilkinson and
       random-deposition curves must land on *their* exact exponents (1/4 and 1/2) — this is
       the negative control in the strict sense. A pipeline that manufactured 1/3 from any
       curve would report 1/3 three times and fail here; three exponents landing on three
       different exact values is what makes the KPZ number a measurement.
    3. **Random deposition matches its closed form** ``w²(t) = p(1−p)t`` point by point, to
       within ``RD_EXACT_TOL``. Re-computed here from the stored ``width_sq``, so it grades an
       exact curve with nothing fitted — the strongest single anchor in the milestone.
    4. **α = 1/2 from saturation**, re-fit from the stored ``(L, w_sat)`` table, giving
       ``z = α/β`` near 3/2.
    5. **Tracy–Widom class assignment.** The droplet sample's skewness must sit nearer the
       (λ<0-mirrored) GUE value and the flat sample's nearer GOE, each within ``TW_SKEW_TOL``.
       Grading the *assignment* — not merely "non-Gaussian" — is what makes the geometry
       dependence falsifiable. The fourth moment is deliberately NOT graded: it does not
       resolve at reachable ``t`` and the report says so.
    """
    if report.get("experiment") != "M17-kpz-growth":
        return None, "not an M17 KPZ growth report"
    growth = report.get("growth")
    if not isinstance(growth, dict) or "kpz" not in growth:
        return None, "M17 report missing the per-model growth curves"

    t_fit_min = _window_param(report, "t_fit_min", M17_T_FIT_MIN, M17_T_FIT_MIN_BOUNDS)
    w_fit_min = _window_param(report, "w_fit_min", M17_W_FIT_MIN, M17_W_FIT_MIN_BOUNDS)
    if t_fit_min is None or w_fit_min is None:
        return False, (
            "M17 scaling-window parameters sit outside the check-owned bounds "
            f"(t_fit_min∈{M17_T_FIT_MIN_BOUNDS}, w_fit_min∈{M17_W_FIT_MIN_BOUNDS}) "
            "— a run cannot choose its own fit window"
        )

    fits = {}
    for name in ("kpz", "ew", "rd"):
        block = growth.get(name)
        if not isinstance(block, dict):
            return None, f"M17 report missing the {name} growth curve"
        got = _refit_growth_exponent(block.get("times"), block.get("width"),
                                     t_fit_min, w_fit_min)
        if got is None:
            return None, f"M17 {name} curve has <4 points inside the scaling window"
        fits[name] = got

    beta, beta_r2, beta_n, t_lo, t_hi = fits["kpz"]
    ew_beta = fits["ew"][0]
    rd_beta = fits["rd"][0]

    # (1) the KPZ exponent, on a clean line spanning at least a decade
    beta_near = abs(beta - KPZ_BETA) <= KPZ_BETA_TOL
    clean = beta_r2 >= M17_MIN_R2
    decade = t_hi / t_lo >= 10.0

    # (2) the controls land on *their* exact exponents — the negative control
    ew_ok = abs(ew_beta - EW_BETA) <= EW_BETA_TOL
    rd_ok = abs(rd_beta - RD_BETA) <= RD_BETA_TOL
    # …and the three are genuinely distinct, not three noisy copies of one slope.
    separated = (abs(beta - ew_beta) > 0.04 and abs(rd_beta - beta) > 0.10)

    # (3) random deposition against its closed form w² = p(1−p)t, recomputed here
    rd_block = growth["rd"]
    p = float(report.get("config", {}).get("p_flip", 0.5))
    rd_dev, rd_pts = 0.0, 0
    for t, w2 in zip(rd_block.get("times") or [], rd_block.get("width_sq") or []):
        exact = p * (1.0 - p) * float(t)
        if exact > 0:
            rd_dev = max(rd_dev, abs(float(w2) - exact) / exact)
            rd_pts += 1
    rd_exact_ok = rd_pts >= 5 and rd_dev <= RD_EXACT_TOL

    # (4) α from the saturation table, and z = α/β
    sat = report.get("saturation")
    alpha = None
    if isinstance(sat, list) and len(sat) >= 3:
        Ls = [float(s["L"]) for s in sat]
        ws = [float(s["w_sat"]) for s in sat]
        alpha = _loglog_slope_r2(Ls, ws)[0]
    alpha_ok = alpha is not None and abs(alpha - KPZ_ALPHA) <= KPZ_ALPHA_TOL
    z = (alpha / beta) if (alpha is not None and beta > 0) else None

    # (5) Tracy–Widom class assignment from the skewness of each geometry
    dists = report.get("distributions") or {}
    targets = {"droplet": TW_GUE_SKEW, "flat": TW_GOE_SKEW}
    tw_ok, tw_bits = True, []
    for ic, target in targets.items():
        s = (dists.get(ic) or {}).get("skewness")
        if s is None:
            tw_ok = False
            tw_bits.append(f"{ic}: missing")
            continue
        s = float(s)
        other = targets["flat"] if ic == "droplet" else targets["droplet"]
        nearer_own = abs(s - target) < abs(s - other)
        within = abs(s - target) <= TW_SKEW_TOL
        tw_ok = tw_ok and nearer_own and within
        tw_bits.append(
            f"{ic} skew {s:+.4f} vs {'GUE' if ic == 'droplet' else 'GOE'} {target:+.4f}"
            f" (Δ={abs(s - target):.4f}{'' if nearer_own else ', WRONG CLASS'})"
        )

    ok = bool(beta_near and clean and decade and ew_ok and rd_ok and separated
              and rd_exact_ok and alpha_ok and tw_ok)

    if ok:
        why = ("three growth classes separate on one pipeline and the KPZ exponents, "
               "saturation and Tracy–Widom class assignment all reproduce")
    elif not (beta_near and clean and decade):
        why = ("the KPZ growth exponent is off 1/3, the log-log line is not clean, or the "
               "fit window spans under a decade")
    elif not (ew_ok and rd_ok and separated and rd_exact_ok):
        why = ("a CONTROL failed: the EW/RD exponents did not land on their own exact values, "
               "the three classes did not separate, or random deposition drifted off its "
               "exact w²=p(1−p)t curve — the exponent pipeline is not trustworthy")
    elif not alpha_ok:
        why = ("the saturation table is missing or too short to re-fit α"
               if alpha is None else
               "the roughness exponent α from saturation is off the exact 1/2")
    else:
        why = ("the height-fluctuation skewness did not land on the λ<0-mirrored Tracy–Widom "
               "law its geometry predicts")

    # ``α`` may be None on a growth-only (partial) report — grade it, never crash on it.
    alpha_str = f"α={alpha:.4f}" if alpha is not None else "α=— (no saturation table)"
    detail = (
        f"β = {beta:.4f} vs KPZ 1/3 (tol ±{KPZ_BETA_TOL}, R²={beta_r2:.4f}, {beta_n} pts, "
        f"t∈[{t_lo:.0f},{t_hi:.0f}]); controls on the same pipeline: EW β={ew_beta:.4f} vs 1/4, "
        f"RD β={rd_beta:.4f} vs 1/2 and w² within {100 * rd_dev:.1f}% of the exact p(1−p)t; "
        + alpha_str + " vs 1/2" + (f", z=α/β={z:.3f} vs 3/2" if z else "") + "; "
        + "; ".join(tw_bits) + " — " + why
    )
    return ok, detail


_C01_OEIS_SEQUENCE = "A000045"
_C01_OEIS_BFILE_URL = "https://oeis.org/A000045/b000045.txt"
_C01_TERMS = 40
_C01_MERSENNE_EXPONENT = 31


def _fib_segment(n_terms: int) -> str:
    a, b = 0, 1
    lines = []
    for i in range(n_terms):
        lines.append(f"{i} {a}\n")
        a, b = b, a + b
    return "".join(lines)


def _finite_floats(values, n: int | None = None) -> list[float] | None:
    """A list of finite floats of the expected length, or ``None`` if unreadable.

    Unreadable guard data is a named failure at the call site, never a default —
    a receipt carrying ``null`` or ``"1.0"`` where a number belongs must not be
    graded as if it had carried the number.
    """
    if not isinstance(values, list) or (n is not None and len(values) != n):
        return None
    out: list[float] = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        f = float(v)
        if not math.isfinite(f):
            return None
        out.append(f)
    return out


def check_k01(report: dict) -> tuple[bool | None, str]:
    """Kuramoto synchronization: the fluctuation peak locates the exact K_c = 2γ.

    Returns ``None`` unless this is a K01 report. Otherwise it re-derives every
    graded number from the run's raw per-coupling arrays rather than trusting the
    headline the runner wrote — a receipt, not an echo. Three independent gates,
    all of which must hold:

    1. **The transition.** ``χ(K) = N·Var_t(r)`` is re-computed from the reported
       ``n`` and ``r_var`` (a stored ``chi`` that disagrees with ``n·r_var`` is a
       tampered or broken receipt and fails here), its peak re-located with the
       same 3-point parabola M04/M05/M06 use, and required to sit within
       ``KURAMOTO_KC_TOL`` of the exact ``K_c = 2γ``.
    2. **The ordered branch.** The closed form ``r(K) = √(1 − K_c/K)`` is
       re-derived here from the *check-owned* ``K_c`` and compared to the measured
       ⟨r⟩ at every coupling ``K ≥ 1.5·K_c``. Nothing is fitted, so this is the
       hard half: a run would have to reproduce seven un-fitted coherence values.
    3. **The negative control.** At ``K = 0`` the measured coherence must be the
       ``1/√N`` random-walk floor — no coupling, no order.

    The fixed calibration identity (γ, N, and the swept grid) is asserted first,
    so a run cannot grade itself against a critical coupling of its own choosing.
    """
    if report.get("experiment") != "K01-kuramoto-synchronization":
        return None, "not a K01 Kuramoto report"

    n, gamma = report.get("n"), report.get("gamma")
    K = report.get("K")
    r_mean, r_var = report.get("r_mean"), report.get("r_var")
    if (
        not isinstance(n, int) or isinstance(n, bool)
        or isinstance(gamma, bool) or not isinstance(gamma, (int, float))
        or not isinstance(K, list) or len(K) < 3
    ):
        return None, "K01 report missing the swept couplings or the population size"

    # ── the fixed calibration identity, asserted before anything is graded ──
    n_points = len(K)
    expected_K = [
        i * (KURAMOTO_K_MAX_OVER_GAMMA * KURAMOTO_GAMMA) / (KURAMOTO_POINTS - 1)
        for i in range(KURAMOTO_POINTS)
    ]
    swept = _finite_floats(K, KURAMOTO_POINTS)
    grid_ok = swept is not None and all(
        abs(a - b) <= 1e-9 for a, b in zip(swept, expected_K)
    )
    if not (
        n == KURAMOTO_N
        and float(gamma) == KURAMOTO_GAMMA
        and n_points == KURAMOTO_POINTS
        and grid_ok
    ):
        return False, (
            f"K01 must sweep {KURAMOTO_POINTS} couplings over "
            f"[0, {KURAMOTO_K_MAX_OVER_GAMMA:g}γ] with N={KURAMOTO_N} oscillators at "
            f"γ={KURAMOTO_GAMMA} (exact K_c = 2γ = {KURAMOTO_KC:g}) — "
            "synchronization calibration identity changed"
        )

    means = _finite_floats(r_mean, KURAMOTO_POINTS)
    variances = _finite_floats(r_var, KURAMOTO_POINTS)
    if means is None or variances is None:
        return None, "K01 report missing readable per-coupling ⟨r⟩ / Var(r) arrays"
    if any(v < 0.0 for v in variances) or any(not (0.0 <= m <= 1.0) for m in means):
        return False, "K01 coherence values are outside [0,1] or the variance is negative"

    # ── gate 1: the transition, re-derived from n·Var(r) ──
    chi = [n * v for v in variances]
    stored_chi = _finite_floats(report.get("chi"), KURAMOTO_POINTS)
    # The report's own χ must be the χ this check re-derives; a receipt whose
    # stored fluctuation curve disagrees with its variances is not gradeable.
    chi_consistent = stored_chi is not None and all(
        abs(a - b) <= 1e-6 * max(1.0, abs(b)) for a, b in zip(stored_chi, chi)
    )
    peak_k = _refine_peak_stdlib(swept, chi)
    peak_dev = abs(peak_k - KURAMOTO_KC)
    peak_ok = peak_dev <= KURAMOTO_KC_TOL

    # ── gate 2: the exact ordered branch √(1 − K_c/K), nothing fitted ──
    graded = [
        (k, m) for k, m in zip(swept, means)
        if k >= KURAMOTO_BRANCH_K_MIN_FACTOR * KURAMOTO_KC
    ]
    branch_dev = max(
        (abs(m - math.sqrt(1.0 - KURAMOTO_KC / k)) for k, m in graded), default=None,
    )
    branch_ok = len(graded) >= 5 and branch_dev is not None and branch_dev <= KURAMOTO_BRANCH_TOL

    # ── gate 3: the negative control at zero coupling ──
    floor = 1.0 / math.sqrt(n)
    incoherent = means[0]
    incoherent_ok = swept[0] == 0.0 and incoherent <= KURAMOTO_INCOHERENT_MAX_SIGMA * floor

    ok = bool(chi_consistent and peak_ok and branch_ok and incoherent_ok)
    branch_str = "n/a" if branch_dev is None else f"{branch_dev:.1e}"
    if not chi_consistent:
        verdict = "stored χ does not equal N·Var(r) — receipt is not self-consistent"
    elif not incoherent_ok:
        verdict = (
            f"uncoupled control failed: ⟨r⟩(K=0)={incoherent:.4f} exceeds "
            f"{KURAMOTO_INCOHERENT_MAX_SIGMA:g}/√N={KURAMOTO_INCOHERENT_MAX_SIGMA * floor:.4f}"
        )
    elif not branch_ok:
        verdict = (
            f"ordered branch not reproduced ({len(graded)} pts, "
            f"tol ±{KURAMOTO_BRANCH_TOL})"
        )
    elif not peak_ok:
        verdict = "synchronization calibration failed"
    else:
        verdict = "synchronization transition reproduced"
    return ok, (
        f"χ=N·Var(r) peak at K={peak_k:.4f} vs exact 2γ = {KURAMOTO_KC:g} "
        f"(Δ={peak_dev:.4f}, tol ±{KURAMOTO_KC_TOL}); ordered branch √(1−K_c/K) "
        f"matched to {branch_str} over {len(graded)} couplings "
        f"(tol ±{KURAMOTO_BRANCH_TOL}); ⟨r⟩(K=0)={incoherent:.4f} vs 1/√N={floor:.4f} — "
        f"{verdict}"
    )


def _parabola_vertex_stdlib(x0, y0, x1, y1, x2, y2) -> float:
    """Vertex of the quadratic through three **unequally spaced** points.

    ``_refine_peak_stdlib`` assumes a uniform abscissa. That holds for every M-track
    temperature sweep and for K01's grid, and fails for both of K02's axes: its
    coupling grid is deliberately non-uniform, and the r-axis that grid induces is
    wildly non-uniform (one step in K can be four times wider in r on one side of the
    peak than the other). Stdlib port of ``k02.parabola_vertex``.
    """
    d1, d2 = x1 - x0, x1 - x2
    num = d1 * d1 * (y1 - y2) - d2 * d2 * (y1 - y0)
    den = d1 * (y1 - y2) - d2 * (y1 - y0)
    return float(x1) if den == 0 else float(x1 - 0.5 * num / den)


def check_k02(report: dict) -> tuple[bool | None, str]:
    """The χ peak on the r-axis: does an interior maximum exist, and is it resolved?

    Returns ``None`` unless this is a K02 report. Otherwise it re-derives every graded
    number from each rung's raw per-coupling arrays — a receipt, not an echo.

    **What is gated, and what deliberately is not.** K02 tests a shape law that came
    out of the lab's own research, not a textbook exact result, so the check is built
    to certify the *instrument and the measurement's resolution* and to leave the
    scientific verdict to the numbers it reports. Gating on r\\* landing at (or away
    from) Run 01's 2/5 would let the grader manufacture its own answer, and gating on
    the direction r\\*(N) happened to move would be a tolerance written after the fact.
    **The headline is a calibration, not a discovery.** After the 2026-08-02 literature
    assay, K02's load-bearing number is the coherence at the *exact* critical coupling,
    ``r(K_c, N) ~ N^(−β/ν̄_c)``, graded against the published **0.39(2)** for this
    engine's exact configuration. It is re-fitted here from the per-rung values rather
    than read from the report. The estimator it replaced — the Beta fit's ``p/(p+q)`` —
    is demoted and deliberately **not** graded: it is a ratio of parameters that
    themselves track N inside a misspecified family.

    Five gates, all of which must hold at **every** rung of the ladder:

    0. **The calibration.** The re-fitted exponent must land within ``K02_CRITICAL_TOL``
       of the published value, and every rung must be **equilibrated** — the fractional
       drift between the halves of its own measurement window under
       ``K02_EQUILIBRATION_MAX_DRIFT``. That second half is not ceremony: measuring a
       transient instead of a stationary state is exactly what produced the wrong
       headline the first time.
    1. **An interior peak in r exists** — the χ argmax is at neither end of the swept
       range, and stands at least ``K02_INTERIOR_PEAK_RATIO`` above the χ at both ends.
       A flat, noise-dominated curve satisfies a bare argmax test and fails this one.
    2. **r\\* is resolved relative to the claim it tests.** The error floor σ is the
       local r half-spacing re-derived here, widened by ``K02_K_PEAK_STEPS`` because
       what is uncertain is *which coupling* carries the maximum and r(K) has infinite
       slope at K_c⁺, so a peak index that wanders a couple of grid steps drags r* a
       long way. ``r*`` must then sit more than σ away from Run 01's 2/5 — **in either
       direction**. A rung landing on 2/5 within its own error is genuinely
       inconclusive and fails; so does a rung whose grid is too coarse to address the
       claim at all. This is the gate that bites hardest, and it is deliberately
       symmetric: it certifies that the instrument can *speak to* the question, never
       that the answer came out a particular way.
    3. **The χ peak in K is consistent with K_c.** Its refined position must sit within
       ``K02_KC_TOL`` of ``K_c = 2γ`` at every N. Read the wording carefully: this
       asserts *consistency*, not that the peak is fixed at K_c. The literature has the
       finite-N peak sitting subcritical and drifting toward K_c as N grows, below this
       ladder's resolution — see ``K02_KC_TOL``'s note. The mechanism argument in
       ``k02``'s docstring only needs the peak to be asymptotically at K_c.
    4. **The negative controls.** At K = 0 the measured coherence must still be the
       1/√N random-walk floor at every population size; and loosening the Lorentzian's
       tail clip 2.5× must not move r(K_c) — the clip is a documented deviation from
       the published configuration, so the run measures whether it matters instead of
       arguing that it doesn't.

    The verdict string then *reports* the measured r\\*(N) ladder, its separation from
    2/5 in units of σ, and whether the two ends of the ladder are resolvably different
    — the scientific finding, stated but not graded.
    """
    if report.get("experiment") != "K02-coherence-susceptibility-shape":
        return None, "not a K02 susceptibility-shape report"

    gamma = report.get("gamma")
    rungs = report.get("rungs")
    ladder = report.get("ladder")
    seeds = report.get("seeds")
    if (
        isinstance(gamma, bool) or not isinstance(gamma, (int, float))
        or not isinstance(rungs, list) or not rungs
        or not isinstance(ladder, list) or not isinstance(seeds, list)
    ):
        return None, "K02 report missing the ladder, the seeds, or the per-N rungs"

    # ── the fixed identity, asserted before anything is graded ──
    k_c = 2.0 * KURAMOTO_GAMMA
    if not (
        float(gamma) == KURAMOTO_GAMMA
        and tuple(ladder) == K02_LADDER
        and tuple(seeds) == K02_SEEDS
        and [r.get("n") for r in rungs] == list(K02_LADDER)
    ):
        return False, (
            f"K02 must sweep the N-ladder {list(K02_LADDER)} over initial conditions "
            f"{list(K02_SEEDS)} at γ={KURAMOTO_GAMMA} (exact K_c = 2γ = {k_c:g}) — "
            "ladder identity changed"
        )

    failures: list[str] = []
    summary: list[str] = []
    measured: list[tuple[float, float]] = []   # (r*, σ) per rung, in ladder order

    for rung in rungs:
        n = rung.get("n")
        K = rung.get("K")
        if not isinstance(n, int) or isinstance(n, bool) or not isinstance(K, list) or len(K) < 5:
            return None, f"K02 rung {n!r} missing its swept couplings"
        points = len(K)
        swept = _finite_floats(K, points)
        means = _finite_floats(rung.get("r_mean"), points)
        variances = _finite_floats(rung.get("r_var"), points)
        if swept is None or means is None or variances is None:
            return None, f"K02 rung N={n} missing readable ⟨r⟩ / Var(r) arrays"
        if any(v < 0.0 for v in variances) or any(not (0.0 <= m <= 1.0) for m in means):
            return False, f"K02 rung N={n}: coherence outside [0,1] or negative variance"

        # χ is re-derived from n and Var(r); a stored curve that disagrees is a
        # tampered or broken receipt and is not gradeable.
        chi = [n * v for v in variances]
        stored = _finite_floats(rung.get("chi"), points)
        if stored is None or any(
            abs(a - b) > 1e-6 * max(1.0, abs(b)) for a, b in zip(stored, chi)
        ):
            return False, (
                f"K02 rung N={n}: stored χ does not equal N·Var(r) — "
                "receipt is not self-consistent"
            )

        i = max(range(points), key=lambda k: chi[k])

        # ── gate 1: an interior peak in r, with a margin ──
        interior = 0 < i < points - 1
        end_chi = max(chi[0], chi[-1])
        ratio = chi[i] / end_chi if end_chi > 0 else float("inf")
        if not interior:
            failures.append(f"N={n}: χ peaks at a sweep endpoint — no interior peak in r")
        elif ratio < K02_INTERIOR_PEAK_RATIO:
            failures.append(
                f"N={n}: χ peak only {ratio:.2f}× the ends of the r-range "
                f"(needs ≥{K02_INTERIOR_PEAK_RATIO:g}) — no resolved interior maximum"
            )

        # ── gate 2: r* is resolved relative to the claim under test ──
        r_star = means[i]
        spacing = 0.5 * abs(means[i + 1] - means[i - 1]) if interior else float("inf")
        sigma = max(K02_K_PEAK_STEPS * spacing, K02_R_STAR_SCATTER)
        gap = abs(r_star - K02_RUN01_R_STAR)
        if not (gap > K02_R_STAR_EXCLUSION_SIGMA * sigma):
            failures.append(
                f"N={n}: r*={r_star:.3f}±{sigma:.3f} is only {gap / sigma:.1f}σ from "
                f"Run 01's r*={K02_RUN01_R_STAR:.2f} — this rung cannot tell the two "
                "apart, in either direction"
            )

        # ── gate 3: the exact-theory anchor, χ still peaks at K_c in the control ──
        k_peak = (
            _parabola_vertex_stdlib(swept[i - 1], chi[i - 1], swept[i], chi[i],
                                    swept[i + 1], chi[i + 1])
            if interior else swept[i]
        )
        if abs(k_peak - k_c) > K02_KC_TOL:
            failures.append(
                f"N={n}: χ peaks at K={k_peak:.4f}, off the exact K_c=2γ={k_c:g} by "
                f"{abs(k_peak - k_c):.4f} (tol ±{K02_KC_TOL:g})"
            )

        # ── gate 4: the negative control at zero coupling ──
        floor = KURAMOTO_INCOHERENT_MAX_SIGMA / math.sqrt(n)
        if not (swept[0] == 0.0 and means[0] <= floor):
            failures.append(
                f"N={n}: uncoupled control failed, ⟨r⟩(K=0)={means[0]:.4f} exceeds "
                f"{KURAMOTO_INCOHERENT_MAX_SIGMA:g}/√N={floor:.4f}"
            )

        summary.append(f"N={n}: r*={r_star:.3f}±{sigma:.3f} (K_peak={k_peak:.3f})")
        measured.append((r_star, sigma))

    # ── gate 5: the calibration against a published finite-size exponent ──
    # Re-fitted HERE from the per-rung r(K_c) values rather than trusting the runner's
    # reported slope — a receipt, not an echo.
    critical = report.get("critical")
    exponent = float("nan")
    if not isinstance(critical, list) or len(critical) != len(K02_LADDER):
        failures.append(
            "K02 is missing its r(K_c, N) calibration block — the headline measurement"
        )
    else:
        xs: list[float] = []
        ys: list[float] = []
        for entry in critical:
            if not isinstance(entry, dict):
                return None, "K02 calibration block is unreadable"
            n = entry.get("n")
            r_c = entry.get("r_critical")
            drift = entry.get("equilibration_drift")
            if (
                not isinstance(n, int) or isinstance(n, bool)
                or isinstance(r_c, bool) or not isinstance(r_c, (int, float))
                or isinstance(drift, bool) or not isinstance(drift, (int, float))
                or not math.isfinite(float(r_c)) or not math.isfinite(float(drift))
                or float(r_c) <= 0.0
            ):
                return None, f"K02 calibration rung {n!r} is unreadable"
            # gate 4b: each rung must actually be equilibrated. Graded on the drift's
            # SIGNIFICANCE — see K02_EQUILIBRATION_MAX_DRIFT_SIGMA for why a bare
            # percentage was the wrong instrument here.
            sigma_drift = entry.get("equilibration_drift_sigma")
            readable_sigma = (
                not isinstance(sigma_drift, bool)
                and isinstance(sigma_drift, (int, float))
                and math.isfinite(float(sigma_drift))
            )
            if readable_sigma and float(sigma_drift) > K02_EQUILIBRATION_MAX_DRIFT_SIGMA:
                failures.append(
                    f"N={n}: r(K_c) still drifting between the halves of its measurement "
                    f"window at {float(sigma_drift):.1f}σ (max "
                    f"{K02_EQUILIBRATION_MAX_DRIFT_SIGMA:g}σ, |Δ|={float(drift) * 100:.1f}%) "
                    "— a transient, not a stationary state"
                )
            elif float(drift) > K02_EQUILIBRATION_MAX_DRIFT:
                failures.append(
                    f"N={n}: r(K_c) drifted {float(drift) * 100:.1f}% between the halves "
                    f"of its measurement window, past the absolute cap "
                    f"{K02_EQUILIBRATION_MAX_DRIFT * 100:.0f}% — a transient, not a "
                    "stationary state"
                )
            xs.append(math.log(float(n)))
            ys.append(math.log(float(r_c)))
        if [e.get("n") for e in critical] != list(K02_LADDER):
            failures.append("K02 calibration block does not cover the fixed N-ladder")
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx > 0 else float("nan")
        exponent = -slope
        gap = abs(exponent - K02_CRITICAL_EXPONENT)
        if not (gap <= K02_CRITICAL_TOL):
            failures.append(
                f"r(K_c,N) ~ N^−{exponent:.3f} misses the published β/ν̄_c = "
                f"{K02_CRITICAL_EXPONENT}({int(K02_CRITICAL_EXPONENT_ERR * 100)}) by "
                f"{gap:.3f} (tol ±{K02_CRITICAL_TOL})"
            )

    # ── gate 6: the tail-clip negative control ──
    clip = report.get("clip_control")
    clip_sigma = float("nan")
    if not isinstance(clip, list) or len(clip) != 2:
        failures.append("K02 is missing its tail-clip negative control")
    else:
        vals, sems = [], []
        for entry in clip:
            if not isinstance(entry, dict):
                return None, "K02 clip control is unreadable"
            v, s = entry.get("r_critical"), entry.get("r_sem")
            if (
                isinstance(v, bool) or not isinstance(v, (int, float))
                or isinstance(s, bool) or not isinstance(s, (int, float))
                or not math.isfinite(float(v)) or not math.isfinite(float(s))
            ):
                return None, "K02 clip control is missing readable values"
            vals.append(float(v))
            sems.append(float(s))
        if clip[0].get("clip_scale") == clip[1].get("clip_scale"):
            failures.append(
                "K02 clip control compared the SAME clip to itself — no control at all"
            )
        combined = math.sqrt(sems[0] ** 2 + sems[1] ** 2)
        clip_sigma = abs(vals[0] - vals[1]) / combined if combined > 0 else float("inf")
        if clip_sigma > K02_CLIP_CONTROL_MAX_SIGMA:
            failures.append(
                f"tail-clip control failed: r(K_c) moves {abs(vals[0] - vals[1]):.5f} "
                f"({clip_sigma:.1f}σ, max {K02_CLIP_CONTROL_MAX_SIGMA:g}σ) when the "
                "frequency clip is loosened — the exponent is riding on the clip"
            )

    # ── the finding, REPORTED rather than graded ──
    (r_first, s_first), (r_last, s_last) = measured[0], measured[-1]
    drift = r_first - r_last
    combined = s_first + s_last
    if drift > combined:
        trend = (
            f"r* COLLAPSES with N: {r_first:.3f}→{r_last:.3f} across N={K02_LADDER[0]}→"
            f"{K02_LADDER[-1]}, a drop of {drift:.3f} against a combined floor of "
            f"±{combined:.3f}"
        )
    elif abs(drift) <= combined:
        trend = (
            f"r* is N-INDEPENDENT at this resolution: {r_first:.3f}→{r_last:.3f}, "
            f"|Δ|={abs(drift):.3f} inside the combined floor ±{combined:.3f}"
        )
    else:
        trend = (
            f"r* GROWS with N: {r_first:.3f}→{r_last:.3f}, a rise of {-drift:.3f} "
            f"against a combined floor of ±{combined:.3f}"
        )
    gaps = [abs(r - K02_RUN01_R_STAR) / s for r, s in measured]
    side = "below" if all(r < K02_RUN01_R_STAR for r, _ in measured) else "away from"
    verdict_run01 = f"every rung sits ≥{min(gaps):.1f}σ {side} Run 01's r*=2/5"

    ok = not failures
    calibration = (
        f"r(K_c,N) ~ N^−{exponent:.3f} vs published β/ν̄_c = {K02_CRITICAL_EXPONENT}"
        f"({int(K02_CRITICAL_EXPONENT_ERR * 100)}) [Hong et al. 2015 Eq. 4.3, regular "
        f"Lorentzian] (tol ±{K02_CRITICAL_TOL})"
        if math.isfinite(exponent) else "r(K_c,N) calibration unavailable"
    )
    detail = (
        f"{calibration}. {'; '.join(summary)} — {trend}; {verdict_run01}. "
        + ("coherence at criticality reproduces the published finite-size exponent; "
           "interior χ maximum in r resolved at every rung; the χ peak in K is "
           f"unresolved from K_c=2γ={k_c:g} throughout (it is subcritical and drifting "
           "in the literature, below this ladder's resolution); uncoupled control held; "
           f"tail-clip control agrees at {clip_sigma:.1f}σ"
           if ok else "FAILED: " + "; ".join(failures))
    )
    return ok, detail


def _lucas_lehmer_residue(exponent: int) -> int:
    modulus = (1 << exponent) - 1
    residue = 4
    for _ in range(exponent - 2):
        residue = (residue * residue - 2) % modulus
    return residue


def check_c01(report: dict) -> tuple[bool | None, str]:
    if report.get("experiment") != "C01-arithmetic-calibration":
        return None, "not a C01 arithmetic calibration"

    n = report.get("n_terms")
    prefix = report.get("source_prefix_text")
    p = report.get("mersenne_exponent")
    candidate = report.get("mersenne_candidate")
    reported_residue = report.get("lucas_lehmer_residue")
    source_bytes = report.get("source_bytes")
    if (
        not isinstance(n, int) or isinstance(n, bool)
        or not isinstance(prefix, str)
        or not isinstance(p, int) or isinstance(p, bool)
        or not isinstance(candidate, int) or isinstance(candidate, bool)
        or not isinstance(reported_residue, int) or isinstance(reported_residue, bool)
        or not isinstance(source_bytes, int) or isinstance(source_bytes, bool)
    ):
        return None, "C01 report missing b-file bytes or Mersenne exponent"

    # C01 is one fixed calibration, not a caller-selected amount of easy work.
    # Reject identity changes before generating a sequence or shifting by a
    # report-owned exponent; that also keeps hostile receipts computationally
    # bounded.
    identity_ok = bool(
        report.get("oeis_sequence") == _C01_OEIS_SEQUENCE
        and report.get("oeis_bfile_url") == _C01_OEIS_BFILE_URL
        and n == _C01_TERMS
        and p == _C01_MERSENNE_EXPONENT
    )
    if not identity_ok:
        return False, (
            f"C01 must reproduce OEIS {_C01_OEIS_SEQUENCE} first {_C01_TERMS} terms "
            f"and Lucas–Lehmer for exponent {_C01_MERSENNE_EXPONENT} — "
            "arithmetic calibration identity changed"
        )

    expected = _fib_segment(_C01_TERMS)
    expected_bytes = expected.encode("utf-8")
    expected_hash = hashlib.sha256(expected_bytes).hexdigest()
    exact = prefix == expected
    source_size_ok = source_bytes >= len(expected_bytes)

    hash_names = (
        "source_sha256",
        "source_prefix_sha256",
        "generated_prefix_sha256",
    )
    hashes_well_formed = all(
        isinstance(report.get(name), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", report[name]) is not None
        for name in hash_names
    )
    prefix_hashes_ok = bool(
        hashes_well_formed
        and report["source_prefix_sha256"].lower() == expected_hash
        and report["generated_prefix_sha256"].lower() == expected_hash
    )

    residue = _lucas_lehmer_residue(_C01_MERSENNE_EXPONENT)
    intended_candidate = (1 << _C01_MERSENNE_EXPONENT) - 1
    mersenne_ok = bool(
        candidate == intended_candidate
        and reported_residue == residue
        and residue == 0
    )
    ok = bool(
        exact
        and source_size_ok
        and prefix_hashes_ok
        and mersenne_ok
    )

    if not hashes_well_formed:
        evidence = "malformed SHA-256 evidence"
    elif not prefix_hashes_ok:
        evidence = "prefix SHA-256 evidence does not match the fixed bytes"
    elif not source_size_ok:
        evidence = "source byte count is shorter than the retained prefix"
    else:
        evidence = "prefix SHA-256 evidence matches"

    return ok, (
        f"OEIS {_C01_OEIS_SEQUENCE} first {_C01_TERMS} terms " +
        ("match byte-for-byte" if exact else "do not match") +
        f" ({evidence}); Lucas–Lehmer final residue for "
        f"2^{_C01_MERSENNE_EXPONENT}−1 is {residue} — " +
        ("arithmetic calibration reproduced" if ok else "arithmetic calibration failed")
    )


def _linear_slope(xs, ys) -> float:
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom <= 0:
        raise ValueError("degenerate ephemeris epochs")
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom


def check_a01(report: dict) -> tuple[bool | None, str]:
    if report.get("experiment") != "A01-tess-hot-jupiter-calibration":
        return None, "not an A01 TESS calibration"
    times, epochs = report.get("transit_times"), report.get("transit_epochs")
    depths, kept = report.get("transit_depths"), report.get("kept_transits")
    products = report.get("products")
    if not all(isinstance(x, list) for x in (times, epochs, depths, kept)):
        return None, "A01 report missing timed transits"
    if not (len(times) == len(epochs) == len(depths) == len(kept)):
        return False, "A01 transit arrays are not parallel"
    selected = [i for i, use in enumerate(kept) if use]
    if len(selected) < 8:
        return False, "A01 has fewer than eight accepted transit timings"
    try:
        xs = [float(epochs[i]) for i in selected]
        ys = [float(times[i]) for i in selected]
        period = _linear_slope(xs, ys)
        depth = statistics.median(float(depths[i]) for i in selected)
    except (TypeError, ValueError, OverflowError) as exc:
        return False, f"A01 transit values are invalid: {exc}"
    p_ref, p_tol = WASP18_PERIOD_DAYS, WASP18_PERIOD_TOL_DAYS
    d_ref, d_tol = WASP18_DEPTH_FRACTION, WASP18_DEPTH_TOL_FRACTION
    p_err, d_err = abs(period - p_ref), abs(depth - d_ref)
    hashes_ok = isinstance(products, list) and bool(products) and all(
        isinstance(product, dict)
        and isinstance(product.get("sha256"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", product["sha256"]) is not None
        for product in products
    )
    ok = bool(p_err <= p_tol and d_err <= d_tol and hashes_ok)
    return ok, (
        f"WASP-18 b from {len(products or [])} TESS SPOC products / {len(selected)} transits: "
        f"P={period:.8f} d vs {p_ref:.8f} (Δ={p_err:.2g}, tol {p_tol:.2g}); "
        f"depth={100*depth:.3f}% vs {100*d_ref:.3f}% "
        f"(Δ={100*d_err:.3f}%, tol {100*d_tol:.3f}%) — " +
        ("archive photometry calibration reproduced" if ok else "published error bars not both recovered")
    )


def check_m18(report: dict) -> tuple[bool | None, str]:
    """Re-derive M18's bracket and every control from the saved numbers.

    The graded claim is deliberately NOT "delta = 0.4505". delta_eff decreases
    monotonically in p, so a subcritical and a supercritical run BOUND the true
    exponent, and that bound is what a finite lattice can honestly support. Four
    things have to hold together:

      1. the two runs really straddle p_c (curvatures of opposite sign) — without
         this a "bracket" is just two runs on the same side;
      2. the bracket contains the (2+1)d DP value 0.4505;
      3. it excludes the mean-field value 1.0 — otherwise the run has shown only
         that something decreases, not which universality class it belongs to;
      4. it is narrow enough to mean something; [0, 2] would "contain" 0.4505.

    Plus the controls and fit quality, because a pipeline that calls any falling
    curve a critical power law would pass 1-4 on noise alone. Summary booleans,
    echoed brackets, report-owned benchmarks, and report-owned tolerances are
    deliberately ignored.
    """
    if report.get("experiment") != "M18-directed-percolation-2plus1d":
        return None, "not an M18 directed-percolation run"
    try:
        # Rebuild the bracket from the two measured fits. p_high is the slower
        # decay (lower exponent); p_low is the faster decay (upper exponent).
        lo = float(report["delta_at_p_high"])
        hi = float(report["delta_at_p_low"])
        r2_lo = float(report["r2_at_p_low"])
        r2_hi = float(report["r2_at_p_high"])
        c_lo = float(report["curvature_at_p_low"])
        c_hi = float(report["curvature_at_p_high"])
        p_low = float(report["p_low"])
        p_high = float(report["p_high"])
        lattice = report["lattice"]
        L = int(lattice["L"])
        t_max = int(lattice["t_max"])
        controls = report["controls"]
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        return None, f"M18 report is missing bracket/control fields: {exc}"

    required_controls = {"deep_subcritical", "deep_supercritical", "absorbing_state"}
    if not isinstance(controls, dict) or not required_controls <= set(controls):
        return None, "M18 report carries fewer than three named controls"
    try:
        sub = controls["deep_subcritical"]
        sup = controls["deep_supercritical"]
        absorbing = controls["absorbing_state"]
        failed = []
        if (sub.get("absorbed_at") is None
                or float(sub["exponential_r2"]) <= float(sub["power_law_r2"])):
            failed.append("deep_subcritical")
        if (float(sup["plateau_density"]) <= 0.05
                or abs(float(sup["delta_eff"])) >= 0.05):
            failed.append("deep_supercritical")
        if absorbing.get("stayed_empty") is not True:
            failed.append("absorbing_state")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return None, f"M18 control metrics are unreadable: {exc}"
    if failed:
        return False, (
            f"M18 control(s) failed: {', '.join(sorted(failed))} — the exponent "
            "is not readable through a pipeline that cannot tell an exponential "
            "from a power law"
        )

    benchmark = M18_DP_DELTA
    mean_field = M18_MEAN_FIELD_DELTA
    max_width = M18_MAX_BRACKET_WIDTH
    min_headroom = M18_MIN_HEADROOM
    headroom = L / (float(t_max) ** (1.0 / M18_DYNAMIC_EXPONENT_Z))
    p_c = 0.5 * (p_low + p_high)
    p_c_unc = 0.5 * (p_high - p_low)
    finite = all(math.isfinite(x) for x in (
        lo, hi, r2_lo, r2_hi, c_lo, c_hi, p_low, p_high, headroom,
    ))
    straddles = c_lo > 0.0 > c_hi
    width = hi - lo
    contains = lo <= benchmark <= hi
    excludes_mf = hi < mean_field

    problems = []
    if not finite:
        problems.append("one or more graded measurements are not finite")
    if not p_low < p_high:
        problems.append(f"p bracket is not ordered ({p_low}/{p_high})")
    if not straddles:
        problems.append(
            f"the runs do not straddle p_c (curvature {c_lo:+.3f} at p_low, "
            f"{c_hi:+.3f} at p_high — need + then −)")
    if not contains:
        problems.append(f"bracket [{lo:.4f}, {hi:.4f}] misses DP {benchmark}")
    if not excludes_mf:
        problems.append(f"bracket does not exclude mean-field {mean_field}")
    if not (0.0 < width <= max_width):
        problems.append(f"bracket width {width:.4f} outside (0, {max_width}]")
    if min(r2_lo, r2_hi) < M18_MIN_R2:
        problems.append(
            f"power-law fit R² {r2_lo:.4f}/{r2_hi:.4f} below {M18_MIN_R2}"
        )
    if headroom < min_headroom:
        problems.append(f"finite-size headroom {headroom:.1f} < {min_headroom} "
                        "— the correlation length reached the box")

    detail = (
        f"2+1d DP: delta bracketed to [{lo:.4f}, {hi:.4f}] (width {width:.4f}) by a "
        f"straddling pair at p={p_low}/{p_high}, "
        f"curvature {c_lo:+.3f}/{c_hi:+.3f}; p_c = {p_c:.5f}±{p_c_unc:.5f} measured, "
        f"not assumed; L/xi = {headroom:.1f}; controls: exponential-not-power-law "
        f"below, saturation above, absorbing state holds"
    )
    if problems:
        return False, detail + " — " + "; ".join(problems)
    return True, (
        detail + f" — contains the DP value {benchmark} and excludes mean-field "
        f"{mean_field}: the measured decay is consistent with the DP class"
    )


def check_a04(report: dict) -> tuple[bool | None, str]:
    """Re-derive A04's survey verdict from its saved rows.

    Three gates, ordered so a broken search cannot read as an empty sky:

    1. CONTROL — injected transits must be recovered. If the pipeline cannot find
       a signal it planted itself, nothing it says about real targets means
       anything, so this returns None (uninterpretable), never False.
    2. FLOOR — the false-alarm SDE distribution must sit entirely below the
       detection threshold. A threshold inside the noise is not a threshold.
    3. RECOVERY — every known planet in the sample must be found blind, with its
       period matching the published one and never read from the catalog first.
    """
    if report.get("experiment") != "A04-blind-transit-search":
        return None, "not an A04 blind transit search"
    injections = report.get("injections")
    recoveries = report.get("recoveries")
    floor = report.get("false_alarm_sde")
    if not isinstance(injections, list) or not injections:
        return None, "A04 report carries no injection control"
    if not isinstance(recoveries, list) or not recoveries:
        return None, "A04 report carries no known-planet recovery targets"
    if not isinstance(floor, list) or len(floor) < 3:
        return None, "A04 report carries too few false-alarm samples to set a floor"
    threshold = A04_SDE_THRESHOLD
    tol = A04_PERIOD_TOL_FRAC

    # Require the whole predeclared sensitivity ladder, not any convenient one
    # injection that happened to pass.
    missing_injections = []
    for expected_depth, expected_period in A04_EXPECTED_INJECTIONS:
        if not any(
            math.isclose(float(i.get("injected_depth", -1)), expected_depth,
                         rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(float(i.get("injected_period_days", -1)), expected_period,
                             rel_tol=0.0, abs_tol=1e-12)
            for i in injections
        ):
            missing_injections.append((expected_depth, expected_period))
    if missing_injections:
        return None, f"A04 report is missing required injection(s): {missing_injections}"

    bad_inj = [i for i in injections
               if not (abs(float(i["recovered_period_days"]) / float(i["injected_period_days"]) - 1.0) <= tol
                       and float(i["sde"]) >= threshold)]
    if bad_inj:
        worst = bad_inj[0]
        return None, (
            f"A04 CONTROL FAILED — an injected transit at P="
            f"{worst['injected_period_days']} d, depth "
            f"{100*float(worst['injected_depth']):.2f}% was not recovered "
            f"(got P={float(worst['recovered_period_days']):.4f}, SDE="
            f"{float(worst['sde']):.1f}); the survey result is uninterpretable, "
            "not negative"
        )

    fa = [float(x) for x in floor]
    if len(fa) < A04_MIN_FALSE_ALARM_SAMPLES:
        return None, (
            f"A04 false-alarm floor has n={len(fa)}; need at least "
            f"{A04_MIN_FALSE_ALARM_SAMPLES} pre-threshold targets"
        )
    floor_max = max(fa)
    floor_ok = floor_max < threshold

    # Above-threshold non-planets are CANDIDATES, not false alarms. The survey's
    # job is to vet them; an unvetted one means the run stopped halfway, so it is
    # unreadable rather than failing.
    candidates = report.get("candidates") or []
    unvetted = [c for c in candidates
                if (c.get("vetting") or {}).get("verdict") in (None, "insufficient-coverage")]
    if unvetted:
        return None, (
            f"A04 has {len(unvetted)} unvetted candidate(s) above SDE {threshold:g} "
            f"(e.g. TIC {unvetted[0].get('tic')}); vetting is the milestone's own "
            "step and its absence makes the survey unreadable, not negative")
    cand_txt = "; ".join(
        f"TIC {c.get('tic')} SDE {float(c['sde']):.1f} → {(c.get('vetting') or {}).get('verdict')}"
        for c in candidates) or "none above threshold"

    by_name = {r.get("known_planet"): r for r in recoveries}
    missing_recoveries = sorted(set(A04_EXPECTED_RECOVERIES) - set(by_name))
    if missing_recoveries:
        return None, f"A04 report is missing recovery target(s): {', '.join(missing_recoveries)}"
    found, missed = [], []
    for name, published_period in A04_EXPECTED_RECOVERIES.items():
        r = by_name[name]
        err = abs(float(r["period_days"]) / published_period - 1.0)
        (found if (err <= tol and float(r["sde"]) >= threshold) else missed).append(
            (name, float(r["period_days"]), published_period, err, float(r["sde"])))

    # The public result says three known planets were recovered. The third is a
    # serendipitous candidate, catalogued only after the blind search, so grade
    # that post-search cross-check explicitly too.
    ser_name, ser_period = A04_SERENDIPITOUS_RECOVERY
    serendipitous = [c for c in candidates
                     if (c.get("catalog") or {}).get("known_planet") == ser_name]
    if not serendipitous:
        return None, f"A04 report carries no post-search catalog recovery of {ser_name}"
    ser = serendipitous[0]
    ser_err = abs(float(ser["period_days"]) / ser_period - 1.0)
    if (ser_err > tol or float(ser["sde"]) < threshold
            or (ser.get("vetting") or {}).get("verdict") != "planet-candidate"):
        missed.append((ser_name, float(ser["period_days"]), ser_period,
                       ser_err, float(ser["sde"])))
    else:
        found.append((ser_name, float(ser["period_days"]), ser_period,
                      ser_err, float(ser["sde"])))

    inj_txt = ", ".join(
        f"{100*float(i['injected_depth']):.1f}%@{i['injected_period_days']}d"
        f"→SDE {float(i['sde']):.1f}" for i in injections)
    rec_txt = ", ".join(
        f"{n} P={p:.5f} vs {pub:.5f} (Δ={e:.1e}, SDE {s:.1f})"
        for n, p, pub, e, s in found + missed)
    ok = bool(floor_ok and not missed)
    detail = (
        f"sector {report.get('sector')}: {report.get('targets_searched')} targets searched "
        f"blind; injections recovered [{inj_txt}]; false-alarm floor n={len(fa)} "
        f"median {statistics.median(fa):.1f} max {floor_max:.1f} vs threshold "
        f"{threshold:g}; candidates vetted: {cand_txt}; recoveries: {rec_txt}"
    )
    if not ok:
        problems = []
        if not floor_ok:
            problems.append(f"false-alarm max {floor_max:.1f} reaches the threshold "
                            f"{threshold:g} — no measured gap")
        if missed:
            problems.append(f"{len(missed)} known planet(s) not recovered")
        return False, detail + " — " + "; ".join(problems)
    return True, detail + " — known planets recovered by a search never told about them"


def _a05_gumbel_mle(x: list[float]) -> tuple[float, float] | None:
    """The check's OWN Gumbel MLE — independent code, same estimator.

    Method-of-moments seed, 1-D Newton on the profile equation in beta, mu in
    closed form. Written in pure Python against plain lists so the refit
    shares nothing with the engine but the mathematics; if the two disagree
    beyond ``A05_GUMBEL_RTOL`` on the same stored maxima, one of them is
    wrong or the receipt's block was not fit from these numbers.
    """
    n = len(x)
    if n < 8:
        return None
    mean = sum(x) / n
    var = sum((v - mean) ** 2 for v in x) / n
    if var <= 0:
        return None
    beta = math.sqrt(var) * math.sqrt(6.0) / math.pi
    shift = min(x)
    xs = [v - shift for v in x]
    for _ in range(200):
        w = [math.exp(-v / beta) for v in xs]
        s0 = sum(w)
        s1 = sum(v * wi for v, wi in zip(x, w))
        s2 = sum(v * v * wi for v, wi in zip(x, w))
        g = beta - mean + s1 / s0
        gprime = 1.0 + (s2 * s0 - s1 * s1) / (beta * beta * s0 * s0)
        beta_next = beta - g / gprime
        if beta_next <= 0:
            beta_next = beta / 2.0
        if abs(beta_next - beta) < 1e-12 * max(1.0, beta):
            beta = beta_next
            break
        beta = beta_next
    if not math.isfinite(beta) or beta <= 0:
        return None
    mu = shift - beta * math.log(
        sum(math.exp(-v / beta) for v in xs) / n)
    if not math.isfinite(mu):
        return None
    return mu, beta


def _a05_ks_uniform(ps: list[float]) -> float:
    """One-sample KS distance from Uniform(0,1), both sides of every step."""
    s = sorted(ps)
    n = len(s)
    return max(max((i + 1) / n - v for i, v in enumerate(s)),
               max(v - i / n for i, v in enumerate(s)))


def _a05_spot(report: dict, cache_dir) -> tuple[bool | None, str]:
    """Spot reproduction: one stored null, re-derived from pinned bytes.

    The row is picked by hashing the receipt's own content (so neither the
    run nor the checker chooses a convenient target), its cached FITS is
    verified against the row's SHA-256, and the iid-scheme null maxima are
    recomputed from the bytes through the pipeline's own loading path with
    the receipt's declared grid and the row's pinned seed. Missing or
    corrupt cache -> ``None`` (nothing to re-derive from); a mismatch beyond
    ``A05_SPOT_RTOL`` -> ``False`` (the receipt does not reproduce).
    """
    rows = [r for r in report.get("targets", [])
            if r.get("outcome") == "searched" and r.get("stage2")
            and r.get("fap") and r.get("cache_sha256") and r.get("cache_file")]
    if not rows:
        return None, "no stage-2 row carries a pinned cache to reproduce from"
    rows.sort(key=lambda r: str(r["tic"]))
    content = json.dumps(
        [[str(r["tic"]), r["cache_sha256"], r["fap"]["seed"]] for r in rows],
        sort_keys=True)
    pick = rows[int(hashlib.sha256(content.encode()).hexdigest()[:8], 16)
                % len(rows)]
    path = Path(cache_dir) / str(pick["cache_file"])
    if not path.exists():
        return None, f"spot cache missing: {path.name}"
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != pick["cache_sha256"]:
        return None, f"spot cache sha256 mismatch for {path.name}"
    # The replay needs the numeric stack; import it only here so every other
    # gate stays stdlib and a numpy-less environment still grades them.
    from . import a05 as _a05           # noqa: PLC0415
    from . import a05_stats as _stats   # noqa: PLC0415
    from . import a05_vetting as _vet   # noqa: PLC0415
    grid = report.get("search_grid") or {}
    curve = _a05.curve_from_blob(blob)
    fw, _ = _vet.prewhiten(curve["t"], curve["f"],
                           **(grid.get("prewhiten") or {}))
    got = _stats.batched_null(curve["t"], fw, B=int(pick["fap"]["B"]),
                              scheme="iid", seed=int(pick["fap"]["seed"]),
                              n_periods=int(grid.get("n_periods", 3000)))
    stored = [float(v) for v in pick["fap"]["schemes"]["iid"]["raw_maxima"]]
    if len(stored) != len(got):
        return False, f"spot row TIC {pick['tic']}: stored {len(stored)} maxima, recomputed {len(got)}"
    worst = max(abs(a - b) / max(abs(b), 1e-8) for a, b in zip(stored, got))
    if worst > A05_SPOT_RTOL:
        if worst > A05_SPOT_GROSS:
            return False, (
                f"spot reproduction FAILED on TIC {pick['tic']}: max relative "
                f"deviation {worst:.2e} is GROSS despite a matching cache "
                "sha256 — tampered maxima/seed, or a discrete prewhiten "
                "branch flipped on this platform; either way the receipt "
                "does not reproduce here")
        return False, (f"spot reproduction FAILED on TIC {pick['tic']}: "
                       f"max relative deviation {worst:.2e} > {A05_SPOT_RTOL:g}")
    return True, (f"spot: TIC {pick['tic']} null re-derived from pinned FITS, "
                  f"max dev {worst:.1e}")


def check_a05(report: dict, cache_dir=None) -> tuple[bool | None, str]:
    """Re-derive an A05 hunt receipt without trusting one carried number.

    Gate order is the argument: structure first (a receipt the checker cannot
    read is ``None`` — unreadable, never negative), then recomputation (a
    number that contradicts its own raw evidence is ``False`` — fabricated,
    never merely absent), then the controls (a failed control makes the whole
    survey UNINTERPRETABLE, so ``None``), then the one physical replay. This
    mirrors the check_a04 doctrine: broken evidence must never be mistaken
    for an empty sky.
    """
    if report.get("experiment") != "a05-survey-hunt":
        return None, "not an A05 survey hunt receipt"
    rows = report.get("targets")
    if not isinstance(rows, list) or not rows:
        return None, "A05 receipt carries no target rows"

    # -- 1. counts reconcile from ROWS, never from the counts block ----------
    searched = [r for r in rows if r.get("outcome") == "searched"]
    skipped = [r for r in rows if r.get("outcome") == "skipped-no-product"]
    errors = [r for r in rows if str(r.get("outcome", "")).startswith("error:")]
    if len(searched) + len(skipped) + len(errors) != len(rows):
        return None, "A05 rows carry outcomes outside the searched/skipped/error vocabulary"
    # A searched row's SDE must be a NUMBER. A string "9.3" (or a missing
    # field) would silently fall out of every >= comparison below — the
    # laundering hole through which an above-threshold hit dodges its
    # disposition gates — so it is refused as unreadable, never skipped.
    for r in searched:
        if isinstance(r.get("sde"), bool) or not isinstance(
                r.get("sde"), (int, float)):
            return None, (f"A05 searched row TIC {r.get('tic')} carries a "
                          f"non-numeric sde {r.get('sde')!r} — unreadable, "
                          "and unreadable rows do not get to skip their gates")
    stage2 = [r for r in searched if r.get("stage2")]
    above = [r for r in searched if float(r["sde"]) >= A05_SDE_THRESHOLD]
    leads = [r for r in searched
             if r.get("disposition") == "lead-awaiting-human-review"]
    derived = {"attempted": len(rows), "searched": len(searched),
               "skipped": len(skipped), "errors": len(errors),
               "stage2": len(stage2), "above_threshold": len(above),
               "dispositioned": sum(1 for r in above if r.get("disposition")),
               "leads_awaiting_human_review": len(leads)}
    counts = report.get("counts") or {}
    mismatched = {k: (counts.get(k), v) for k, v in derived.items()
                  if counts.get(k) != v}
    if mismatched:
        return None, (f"A05 counts do not reconcile with the rows "
                      f"(stated, derived): {mismatched} — unreadable by "
                      "contract rule 2")

    # -- 2. the triage line is the check's line, not the run's ---------------
    (n1, f1), (n2, f2) = A05_TRIAGE_FLOOR_POINTS
    beta = (f2 - f1) / (math.log(n2) - math.log(n1))
    mu = f1 - beta * math.log(n1)
    triage = report.get("triage") or {}
    try:
        t_n = int(triage["n"])
        own_level = mu + beta * math.log(t_n) - A05_TRIAGE_SAFETY_MARGIN
        agree = (math.isclose(float(triage["mu"]), mu, rel_tol=1e-9)
                 and math.isclose(float(triage["beta"]), beta, rel_tol=1e-9)
                 and math.isclose(float(triage["safety_margin"]),
                                  A05_TRIAGE_SAFETY_MARGIN, rel_tol=1e-9)
                 and math.isclose(float(triage["level"]), own_level, rel_tol=1e-9))
    except (KeyError, TypeError, ValueError):
        return None, "A05 triage block is absent or malformed"
    if not agree:
        return None, ("A05 triage block disagrees with the check's own line "
                      "through the measured floor points — the run moved its "
                      "own triage line")
    if t_n != len(rows):
        return None, (f"A05 triage n={t_n} disagrees with the receipt's own "
                      f"{len(rows)} rows — inflating n raises the triage line, "
                      "so n must re-derive from the slice itself")

    # -- 2b. the stage-2 flag is DERIVED, never trusted ----------------------
    # The engine promises stage2 for every row at or above the triage line
    # (and for every predeclared control member). A row whose sde clears the
    # verified line but whose flag says otherwise skipped a FAP it owed —
    # the receipt is unreadable, whatever its counts say.
    stage2_line = min(own_level, A05_SDE_THRESHOLD)
    for r in searched:
        if float(r["sde"]) >= stage2_line and r.get("stage2") is not True:
            return None, (f"A05 TIC {r.get('tic')} sits at SDE "
                          f"{float(r['sde']):.2f}, at or above the verified "
                          f"stage-2 line {stage2_line:.2f}, with stage2="
                          f"{r.get('stage2')!r} — the flag cannot excuse a "
                          "row from the FAP it owes")

    # -- 2c. control membership re-derives from the declared seed ------------
    # The uniformity ensemble calibrates the calibrator, so its membership
    # must be a pure function of (seed, control_fraction, tic) — decided
    # before any photon. A schema>=1 receipt without the derivation inputs is
    # unreadable; a membership flag that contradicts the derivation is forged.
    if isinstance(report.get("schema"), (int, float)) and report["schema"] >= 1:
        try:
            ctrl_seed = int(report["seed"])
            ctrl_frac = float(report["control_fraction"])
        except (KeyError, TypeError, ValueError):
            return None, ("A05 schema>=1 receipt does not declare seed + "
                          "control_fraction — control membership cannot be "
                          "re-derived, so the calibration is unreadable")
        for r in searched:
            digest = hashlib.sha256(
                f"{ctrl_seed}|a05-control|{r.get('tic')}".encode()).digest()
            expected = int.from_bytes(digest[:8], "big") / float(2**64) < ctrl_frac
            if bool(r.get("control_subsample")) != expected:
                return False, (f"A05 TIC {r.get('tic')} control_subsample="
                               f"{r.get('control_subsample')!r} does not "
                               "re-derive from the declared seed — the "
                               "calibration ensemble was edited")

    # -- 3. FAP structure: both schemes' raw maxima, B, block length ---------
    # Applied to EVERY row that carries a fap block, not only stage-2 rows:
    # a carried fap_empirical with no maxima behind it would otherwise slide
    # straight into the uniformity ensemble (gate 10) unaudited.
    fap_rows = [r for r in searched if r.get("fap") is not None]
    for r in stage2:
        fap = r.get("fap")
        if not isinstance(fap, dict):
            return None, f"A05 stage-2 row TIC {r.get('tic')} carries no fap block"
    for r in fap_rows:
        fap = r.get("fap")
        if not isinstance(fap, dict):
            return None, f"A05 row TIC {r.get('tic')} carries a non-dict fap block"
        try:
            b_val = int(fap["B"])
            int(fap["seed"])
            schemes = fap["schemes"]
            iid = schemes["iid"]["raw_maxima"]
            block = schemes["block"]["raw_maxima"]
            block_days = float(schemes["block"]["block_days"])
        except (KeyError, TypeError, ValueError):
            return None, (f"A05 row TIC {r.get('tic')} carries a fap block "
                          "missing scheme maxima, seed, or block length")
        if b_val < A05_MIN_B:
            return None, (f"A05 TIC {r.get('tic')} graded on B={b_val} < "
                          f"{A05_MIN_B} permutations")
        if len(iid) != b_val or len(block) != b_val:
            return None, (f"A05 TIC {r.get('tic')} stores "
                          f"{len(iid)}/{len(block)} maxima for B={b_val}")
        if not math.isclose(block_days, A05_BLOCK_DAYS, rel_tol=1e-9):
            return None, (f"A05 TIC {r.get('tic')} declares block_days="
                          f"{block_days}, contract is {A05_BLOCK_DAYS}")
    # Every stage-2 row must pin its input bytes: without cache_sha256 +
    # cache_file the row can never enter the spot-reproduction pool, and a
    # run that strips its pins shrinks the pool to the rows it prefers.
    for r in stage2:
        if not r.get("cache_sha256") or not r.get("cache_file"):
            return None, (f"A05 stage-2 row TIC {r.get('tic')} carries no "
                          "pinned cache (sha256 + file) — it can never be "
                          "spot-reproduced, so the receipt is unauditable")

    # -- 4. every above-threshold row is dispositioned, in vocabulary --------
    for r in above:
        disp = r.get("disposition")
        if not disp:
            return None, (f"A05 TIC {r.get('tic')} sits above SDE "
                          f"{A05_SDE_THRESHOLD:g} with no machine disposition "
                          "— the run stopped halfway, unreadable")
    for r in searched:
        disp = r.get("disposition")
        if disp is None:
            continue
        if disp not in A05_MACHINE_VOCABULARY:
            return False, (f"A05 TIC {r.get('tic')} carries disposition "
                           f"{disp!r}, outside the machine vocabulary — the "
                           "machine has no word for 'planet' and may not "
                           "invent one")

    # -- 5. a community-refuted TOI is never a recovery, never a lead --------
    recovery_tics = {str(r.get("tic")) for r in (report.get("recoveries") or [])}
    for r in searched:
        cat = (r.get("disposition_evidence") or {}).get("catalog") or {}
        refuted = (cat.get("known_toi") is not None
                   and str(cat.get("disposition") or "").strip().upper()
                   in A05_TOI_REFUTED)
        if refuted and float(r.get("sde", 0.0)) >= A05_SDE_THRESHOLD:
            if r.get("disposition") != "toi-known-fp":
                return False, (f"A05 TIC {r.get('tic')} matches a TOI with "
                               f"TFOPWG disposition "
                               f"{cat.get('disposition')!r} but is "
                               f"dispositioned {r.get('disposition')!r} — a "
                               "refuted TOI must be toi-known-fp")
        if r.get("disposition") == "toi-known-fp" and str(r.get("tic")) in recovery_tics:
            return False, (f"A05 TIC {r.get('tic')} is toi-known-fp AND "
                           "listed as a recovery — a refuted signal re-found "
                           "is not a recovery")

    # -- 5b. an outage cannot certify "uncatalogued" -------------------------
    for r in leads:
        cat = (r.get("disposition_evidence") or {}).get("catalog") or {}
        if cat.get("lookup_error"):
            return None, (f"A05 TIC {r.get('tic')} is a lead whose catalog "
                          "evidence records a lookup error — an outage cannot "
                          "certify 'uncatalogued', so the lead is unreadable")

    # -- 6. every lead carries a full dossier --------------------------------
    for r in leads:
        dossier = r.get("dossier")
        if not isinstance(dossier, dict):
            return None, (f"A05 lead TIC {r.get('tic')} carries no dossier — "
                          "a lead without evidence is not reviewable")
        missing = [p for p in A05_DOSSIER_PANELS if p not in dossier]
        if missing:
            return None, (f"A05 lead TIC {r.get('tic')} dossier is missing "
                          f"panels: {missing}")
        if dossier.get("status") != "lead-awaiting-human-review":
            return False, (f"A05 lead TIC {r.get('tic')} dossier status is "
                           f"{dossier.get('status')!r} — the machine-terminal "
                           "state is lead-awaiting-human-review")

    # -- 7. the injection ladder, in full, per stage-2 host ------------------
    full_ladder = {(d, p, e) for d in A05_INJECTION_DEPTHS
                   for p in A05_INJECTION_PERIODS
                   for e in range(A05_INJECTION_EPOCHS)}
    for r in stage2:
        inj = r.get("injections")
        if not isinstance(inj, list) or not inj:
            return None, (f"A05 stage-2 host TIC {r.get('tic')} carries no "
                          "injection block — its depth limit was never measured")
        cells = {(float(i.get("depth", -1)), float(i.get("period_days", -1)),
                  int(i.get("epoch", -1))) for i in inj}
        missing_cells = full_ladder - cells
        if missing_cells:
            return None, (f"A05 TIC {r.get('tic')} injection ladder is "
                          f"missing {len(missing_cells)} predeclared cell(s)")
        if r.get("injections_recovery_rule") not in A05_INJECTION_RULES:
            return None, (f"A05 TIC {r.get('tic')} does not declare its "
                          "injection recovery rule — an undeclared rule "
                          "cannot be audited")
        if not isinstance(r.get("d_min"), dict):
            return None, (f"A05 TIC {r.get('tic')} carries injections but no "
                          "folded d_min")

    # -- 8. recompute every empirical FAP from the stored maxima -------------
    # Over every row carrying a fap block (control rows included), so no
    # carried number reaches gate 10's ensemble without recomputation.
    for r in fap_rows:
        fap = r["fap"]
        b_val = int(fap["B"])
        sde = float(r["sde"])
        recomputed = {}
        for name in ("iid", "block"):
            maxima = [float(v) for v in fap["schemes"][name]["raw_maxima"]]
            k = sum(1 for v in maxima if v >= sde)
            p = (1 + k) / (b_val + 1)
            recomputed[name] = p
            stored = float(fap["schemes"][name]["fap_empirical"])
            if abs(stored - p) > A05_FAP_ABS_TOL:
                return False, (f"A05 TIC {r['tic']} {name} fap_empirical "
                               f"{stored:.6f} does not recompute from its own "
                               f"maxima ({p:.6f}) — fabricated or corrupted")
        graded = max(recomputed.values())
        if abs(float(fap.get("fap_graded", -1)) - graded) > A05_FAP_ABS_TOL:
            return False, (f"A05 TIC {r['tic']} fap_graded "
                           f"{fap.get('fap_graded')} is not the conservative "
                           f"max of its schemes ({graded:.6f})")

    # -- 9. refit every reported gumbel with the check's own fitter ----------
    for r in fap_rows:
        fap = r["fap"]
        gumbel = fap.get("gumbel")
        if gumbel is None:
            continue
        scheme = fap.get("graded_scheme")
        if scheme not in ("iid", "block"):
            return None, f"A05 TIC {r['tic']} reports a gumbel with no graded scheme"
        maxima = [float(v) for v in fap["schemes"][scheme]["raw_maxima"]]
        refit = _a05_gumbel_mle(maxima)
        if refit is None:
            return False, (f"A05 TIC {r['tic']} reports a gumbel block the "
                           "check's own fitter refuses on the same maxima")
        mu_fit, beta_fit = refit
        try:
            mu_rep, beta_rep = float(gumbel["mu"]), float(gumbel["beta"])
        except (KeyError, TypeError, ValueError):
            return None, f"A05 TIC {r['tic']} gumbel block is malformed"
        if (abs(mu_rep - mu_fit) > A05_GUMBEL_RTOL * max(1.0, abs(mu_fit))
                or abs(beta_rep - beta_fit) > A05_GUMBEL_RTOL * max(0.1, abs(beta_fit))):
            return False, (f"A05 TIC {r['tic']} gumbel (mu={mu_rep:.3f}, "
                           f"beta={beta_rep:.3f}) disagrees with the check's "
                           f"refit (mu={mu_fit:.3f}, beta={beta_fit:.3f})")

    # -- 10. uniformity: the calibration of the calibrator, re-run -----------
    uniformity = report.get("uniformity") or {}
    p_values = uniformity.get("p_values")
    if not isinstance(p_values, list) or len(p_values) < A05_UNIFORMITY_MIN_N:
        return None, (f"A05 uniformity control has "
                      f"{len(p_values) if isinstance(p_values, list) else 0} "
                      f"p-values; need >= {A05_UNIFORMITY_MIN_N} to grade the "
                      "calibrator")
    control_ps = sorted(
        float(r["fap"]["schemes"]["iid"]["fap_empirical"])
        for r in searched if r.get("control_subsample") and r.get("fap"))
    if [round(v, 12) for v in sorted(float(p) for p in p_values)] != [
            round(v, 12) for v in control_ps]:
        return False, ("A05 uniformity p-values are not the control rows' own "
                       "iid FAPs — the ensemble was edited")
    ks = _a05_ks_uniform([float(p) for p in p_values])
    n_ks = len(p_values)
    ks_pass = ks < A05_UNIFORMITY_CRIT / (
        math.sqrt(n_ks) + 0.12 + 0.11 / math.sqrt(n_ks))   # Stephens (1970)
    if uniformity.get("pass") is not bool(ks_pass) or not math.isclose(
            float(uniformity.get("ks_stat", -1)), ks, rel_tol=1e-6, abs_tol=1e-9):
        return False, (f"A05 uniformity block (D={uniformity.get('ks_stat')}, "
                       f"pass={uniformity.get('pass')}) contradicts the "
                       f"re-run (D={ks:.4f}, pass={ks_pass})")
    if not ks_pass:
        return None, (f"A05 UNIFORMITY CONTROL FAILED (D={ks:.3f} over "
                      f"n={len(p_values)}): the permutation null does not "
                      "describe this sample's noise, so every graded FAP is "
                      "uninterpretable, not negative")

    # -- 11. placebo: the whole ladder must refuse a scrambled sky -----------
    placebo = report.get("placebo") or {}
    prows = placebo.get("rows")
    if not isinstance(prows, list) or not prows:
        return None, "A05 placebo block carries no per-curve rows to re-derive"
    n_pc = sum(1 for p in prows
               if (p.get("vetting") or {}).get("verdict") == "planet-candidate")
    if placebo.get("n_scrambled") != len(prows) or placebo.get(
            "planet_candidates") != n_pc or placebo.get("pass") is not (n_pc == 0):
        return False, ("A05 placebo summary contradicts its own rows "
                       f"(rows say {len(prows)} scrambled, {n_pc} candidates)")
    if n_pc > 0:
        return None, (f"A05 PLACEBO FAILED — {n_pc} planet-candidate(s) from "
                      "phase-scrambled curves: the pipeline manufactures "
                      "discoveries and nothing it reports is interpretable")

    # -- 12. budget: shares re-derived from the rows' own clocks -------------
    budget = report.get("budget") or {}
    try:
        soft = float(budget["soft_budget_seconds"])
        share = float(budget["per_target_share"])
        reported_sum = float(budget["survey_sum_reported"])
    except (KeyError, TypeError, ValueError):
        return None, "A05 budget block is absent or malformed"
    if not (soft > 0 and 0 < share <= 1):
        return None, "A05 budget declares a non-positive budget or share"
    walls = [float(r.get("wall_seconds") or 0.0) for r in rows]
    derived_sum = sum(walls) / soft
    if abs(derived_sum - reported_sum) > A05_BUDGET_RTOL * max(derived_sum, 0.01):
        return False, (f"A05 survey_sum_reported {reported_sum:.4f} does not "
                       f"re-derive from the rows ({derived_sum:.4f})")
    worst = max(walls, default=0.0)
    if worst > share * soft * (1 + A05_BUDGET_RTOL):
        return False, (f"A05 a single target consumed {worst:.0f}s, over its "
                       f"declared share ({share:.3f} of {soft:.0f}s)")

    # -- 13. floor history: the extrapolation stays testable -----------------
    history = report.get("floor_history")
    if not isinstance(history, list):
        return None, "A05 receipt carries no floor_history"
    by_source = {h.get("source"): h for h in history if isinstance(h, dict)}
    for source, n_pt, floor_pt in A05_FLOOR_PRIOR:
        h = by_source.get(source)
        if (h is None or h.get("n") != n_pt
                or not math.isclose(float(h.get("floor_max", -1)), floor_pt,
                                    rel_tol=1e-9)):
            return None, (f"A05 floor_history dropped or altered the prior "
                          f"point {source} — the triage extrapolation is no "
                          "longer testable")
    if len(history) <= len(A05_FLOOR_PRIOR):
        return None, ("A05 floor_history carries no point from this run — "
                      "every hunt must append its own measured floor")
    # The run's own point (appended LAST by to_report) must re-derive from
    # the receipt's rows: n = the sub-threshold searched rows, floor_max =
    # their max SDE. A floor that cannot be recomputed from its own rows is
    # a fabricated calibration datum for every future triage line.
    own = history[-1]
    noise = [float(r["sde"]) for r in searched
             if float(r["sde"]) < A05_SDE_THRESHOLD]
    own_floor = max(noise) if noise else None
    if not isinstance(own, dict):
        return None, "A05 floor_history's own point is malformed"
    stated_floor = own.get("floor_max")
    floor_agrees = (stated_floor is None and own_floor is None) or (
        isinstance(stated_floor, (int, float)) and own_floor is not None
        and math.isclose(float(stated_floor), own_floor, rel_tol=1e-9))
    if own.get("n") != len(noise) or not floor_agrees:
        return False, (f"A05 floor_history's own point (n={own.get('n')}, "
                       f"floor_max={stated_floor}) does not re-derive from "
                       f"the rows (n={len(noise)}, floor_max={own_floor}) — "
                       "the run misreported its measured floor")

    # -- 14. spot reproduction from the SHA-256-pinned cache -----------------
    from . import a01 as _a01           # noqa: PLC0415 — path constant only
    spot_ok, spot_txt = _a05_spot(report, cache_dir or _a01.CACHE_DIR)
    if spot_ok is None:
        return None, f"A05 receipt is internally consistent but {spot_txt} — cannot re-derive the physics"
    if spot_ok is False:
        return False, spot_txt

    detail = (
        f"sector {report.get('sector')}: {derived['searched']}/"
        f"{derived['attempted']} searched, {derived['stage2']} stage-2 "
        f"(all FAPs recomputed from raw maxima, graded = conservative max), "
        f"{derived['above_threshold']} above SDE {A05_SDE_THRESHOLD:g} all "
        f"dispositioned in-vocabulary, uniformity D={ks:.3f} over "
        f"n={len(p_values)}, placebo {len(prows)} scrambled / 0 candidates, "
        f"{derived['leads_awaiting_human_review']} lead(s) with full "
        f"dossiers; {spot_txt}"
    )
    return True, detail


def check_a03(report: dict) -> tuple[bool | None, str]:
    """Re-derive A03's verdict from the saved numbers, not its pass flags.

    Two gates, and the order is the point. The CONTROL gate asks whether the
    pipeline can recover a chirp mass it planted itself — if that fails, the run
    says nothing about the sky either way and the milestone is unreadable rather
    than false. Only if the control holds does the SKY gate mean anything.
    """
    if report.get("experiment") != "A03-gwosc-chirp-mass":
        return None, "not an A03 GWOSC chirp-mass run"
    dets = report.get("detectors")
    products = report.get("products")
    if not isinstance(dets, list) or not dets:
        return None, "A03 report carries no per-detector results"
    if len(dets) < 2:
        return False, "A03 needs at least two independent detectors"

    hashes_ok = isinstance(products, list) and bool(products) and all(
        isinstance(p, dict) and isinstance(p.get("sha256"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", p["sha256"]) is not None
        for p in products
    )
    if not hashes_ok:
        return False, "A03 strain products are not pinned by SHA-256"

    try:
        mc_pub_src = float(report["published_chirp_mass_source"])
        mc_pub_det = float(report["published_chirp_mass_detector"])
        tol = max(float(report.get("published_chirp_mass_source_lower") or 0.0),
                  float(report.get("published_chirp_mass_source_upper") or 0.0))
        ctrl_tol = float(report.get("control_tolerance_msun", 1e-3))
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"A03 published parameters are unusable: {exc}"
    if tol <= 0:
        return False, "A03 has no published error bar to grade against"

    ctrl_errs, sky = [], []
    for d in dets:
        try:
            c, r = d["control"], d["real"]
            ce = abs(float(c["mc_detector"]) - mc_pub_det)
            ctrl_ok = float(c["peak_snr"]) > float(c["background_max"]) and ce <= ctrl_tol
            re_src = float(r["mc_detector"]) / (1.0 + float(report["redshift"]))
            sky_ok = (float(r["peak_snr"]) > float(r["background_max"])
                      and abs(re_src - mc_pub_src) <= tol)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            return False, f"A03 detector row is malformed: {exc}"
        ctrl_errs.append((d.get("detector", "?"), ce, ctrl_ok, float(c["peak_snr"])))
        sky.append((d.get("detector", "?"), re_src, sky_ok,
                    float(r["peak_snr"]), float(r["background_max"])))

    if not all(ok for _, _, ok, _ in ctrl_errs):
        worst = max(ctrl_errs, key=lambda x: x[1])
        return None, (
            f"A03 CONTROL FAILED — the pipeline could not recover its own injection "
            f"({worst[0]}: {worst[1]:.2e} Msun off, tol {ctrl_tol:.0e}); the sky result "
            "is uninterpretable, not negative"
        )

    ctrl_txt = ", ".join(f"{n} {e:.1e} (SNR {s:.1f})" for n, e, _, s in ctrl_errs)
    sky_txt = ", ".join(
        f"{n} Mc={v:.5f} (SNR {p:.1f} vs background {b:.1f})" for n, v, _, p, b in sky)
    ok = all(o for _, _, o, _, _ in sky)
    return ok, (
        f"{report.get('event', 'event')}: injection recovered to {ctrl_txt} — "
        f"pipeline validated at {ctrl_tol:.0e} Msun, "
        f"{max(1, int(tol / max(max(e for _, e, _, _ in ctrl_errs), 1e-12)))}x "
        f"tighter than the published +/-{tol:g}; sky: {sky_txt} vs published "
        f"{mc_pub_src:g} — " + (
            "published chirp mass reproduced" if ok else
            "event NOT recovered by an inspiral-only template (see claim_boundary)")
    )


def check_i01(report: dict) -> tuple[bool | None, str]:
    if report.get("experiment") != "I01-cmos-particle-detector-calibration":
        return None, "not an I01 CMOS calibration"
    if not report.get("hardware_available"):
        return False, "no real capped-sensor dark frames were available; hardware-null recorded"
    analysis = report.get("analysis") or {}
    if not isinstance(analysis, dict):
        return False, "I01 analysis receipt is malformed"

    malformed: list[str] = []

    def receipt_int(name: str, value: object, *, minimum: int = 0) -> int | None:
        """Parse an integral JSON receipt field without leaking conversion errors."""
        try:
            if isinstance(value, bool):
                raise ValueError("booleans are not counts")
            if isinstance(value, float) and (
                not math.isfinite(value) or not value.is_integer()
            ):
                raise ValueError("not a finite integer")
            if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()) is None:
                raise ValueError("not an integer string")
            parsed = int(value)
            if parsed < minimum:
                raise ValueError("below minimum")
            return parsed
        except (TypeError, ValueError, OverflowError):
            malformed.append(name)
            return None

    raw_shape = analysis.get("shape")
    shape: list[int | None] = []
    if isinstance(raw_shape, (list, tuple)) and len(raw_shape) == 3:
        shape = [
            receipt_int(f"shape[{index}]", value, minimum=1)
            for index, value in enumerate(raw_shape)
        ]
    else:
        malformed.append("shape")
    frame_count = shape[0] if len(shape) == 3 and shape[0] is not None else 0
    enough = len(shape) == 3 and all(value is not None for value in shape) and frame_count >= 16

    try:
        noise_value = float(analysis.get("temporal_noise_sigma", 0))
        if not math.isfinite(noise_value):
            raise ValueError("noise is not finite")
    except (TypeError, ValueError, OverflowError):
        noise_value = 0.0
        malformed.append("temporal_noise_sigma")
    noise = noise_value > 0
    unique = receipt_int("unique_frame_count", analysis.get("unique_frame_count", 0))
    flood_count = receipt_int(
        "candidate_flood_frame_count",
        analysis.get("candidate_flood_frame_count", 0),
    )
    hot_pixel_count = receipt_int("hot_pixel_count", analysis.get("hot_pixel_count", 0))
    track_candidate_count = receipt_int(
        "track_candidate_count",
        analysis.get("track_candidate_count", 0),
    )
    minimum_unique = max(2, (frame_count + 1) // 2) if enough else 2
    quality = (
        analysis.get("stack_quality_passed") is True
        and analysis.get("stack_constant") is False
        and unique is not None
        and unique >= minimum_unique
        and flood_count == 0
    )
    evidence = report.get("input_evidence") or []
    hashes = isinstance(evidence, list) and bool(evidence) and all(
        isinstance(item, dict)
        and isinstance(item.get("sha256"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"]) is not None
        and item.get("synthetic") is not True
        for item in evidence
    )
    ok = bool(enough and noise and quality and hashes and not malformed)
    raw_failures = analysis.get("quality_failures") or []
    failures = raw_failures if isinstance(raw_failures, list) else [raw_failures]
    reasons = [str(item) for item in failures]
    if malformed:
        reasons.append("malformed numeric receipt: " + ", ".join(malformed))
    return ok, (
        f"CMOS dark stack: {frame_count} frames, "
        f"noise σ={noise_value:.3g}, {unique if unique is not None else 0} distinct frames, "
        f"{hot_pixel_count if hot_pixel_count is not None else 0} persistent hot pixels, "
        f"{track_candidate_count if track_candidate_count is not None else 0} "
        "transient track-like components — " +
        ("instrument calibration operational" if ok else
         "instrument calibration incomplete" +
         (f" ({'; '.join(reasons)})" if reasons else ""))
    )


def check_controls(report: dict) -> tuple[bool | None, str]:
    """Grade a published-controls report: cross-updater agreement + a null that must fail.

    Returns ``None`` unless this is a controls report. Otherwise grades two
    independent probes (a receipt, not prose):

    * **Cross-updater agreement** (positive control): every ``controls`` entry
      compares an observable measured by two independent correct algorithms
      (single-spin Metropolis vs single-cluster Wolff). Each must agree within the
      check-owned ``CROSS_UPDATER_TOL`` — two updaters, one number. A silently
      broken updater pushes |metropolis − wolff| past the band and this fails.
    * **Null-coupling baseline** (negative control): with ``J=0`` there is no
      transition, so χ(T) must be flat — its peak/median prominence stays below
      the check-owned cap (a real critical peak is many times its baseline; a flat
      noisy 1/T curve is ≈1×). The control's job is to **fail** the "there is a
      T_c peak" gate; PASS here means that failure was reproduced — proving M01's
      peak is physics, not an artifact the analysis manufactures from noise.
      (Prominence, not the noisy argmax *location*, is the discriminator: a flat
      curve's argmax wanders, but its peak never towers over its baseline.)

    Every graded quantity is **re-derived from the raw arrays** — ``delta`` from
    each entry's own ``metropolis``/``wolff`` values, the null prominence from the
    null's own ``chi`` array — against the check-owned ``CROSS_UPDATER_TOL`` /
    ``NULL_PEAK_RATIO_MAX``. Report-carried ``tol``/``ratio_max`` never grade
    anything, and a summary field that contradicts its own raw values (a tampered
    ``delta`` or ``peak_to_median_ratio``) is malformed evidence and fails.
    """
    if report.get("experiment") != "CTRL-published-controls":
        return None, "not a published-controls report"
    entries = report.get("controls") or []
    null = report.get("null_control") or {}
    if len(entries) < 2 or not null:
        return None, "controls report missing cross-updater entries or the null control"

    parts: list[str] = []
    all_ok = True
    graded = 0
    for e in entries:
        try:
            mv, wv = float(e["metropolis"]), float(e["wolff"])
        except (KeyError, TypeError, ValueError):
            continue                       # no raw values → nothing to re-derive
        if not (math.isfinite(mv) and math.isfinite(wv)):
            continue
        graded += 1
        delta = abs(mv - wv)
        ok = delta <= CROSS_UPDATER_TOL
        # A carried delta that contradicts the raw values is a tampered/malformed
        # receipt — fail it even when the re-derived delta itself is in band.
        carried = e.get("delta")
        if carried is not None:
            try:
                consistent = math.isclose(float(carried), delta, rel_tol=1e-3, abs_tol=1e-3)
            except (TypeError, ValueError):
                consistent = False
            ok = ok and consistent
        all_ok = all_ok and ok
        t = e.get("T")
        t_str = f"{t:.1f}" if isinstance(t, (int, float)) else "?"
        parts.append(
            f"{e.get('observable')}@T={t_str}: |Δ|={delta:.3f}≤{CROSS_UPDATER_TOL}"
            + ("" if ok else " ✗")
        )
    if graded < 2:
        return None, ("controls report has <2 cross-updater entries with raw "
                      "metropolis/wolff values to re-derive from")

    # The negative control must NOT show a prominent peak, re-derived from the
    # null's own χ array. No re-derivable χ = the guard cannot run = named failure.
    chi = null.get("chi")
    if (isinstance(chi, list) and len(chi) >= 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in chi)):
        median = statistics.median(chi)
        ratio = (max(chi) / median) if median > 0 else math.inf
        null_flat = ratio <= NULL_PEAK_RATIO_MAX
        carried_ratio = null.get("peak_to_median_ratio")
        if carried_ratio is not None:
            try:
                null_flat = null_flat and math.isclose(
                    float(carried_ratio), ratio, rel_tol=1e-3, abs_tol=1e-3)
            except (TypeError, ValueError):
                null_flat = False
        null_str = (f"J=0 null χ flat (peak/median={ratio:.2f}≤{NULL_PEAK_RATIO_MAX})"
                    if null_flat else
                    f"J=0 null χ prominence re-derived at {ratio:.2f} "
                    f"(cap {NULL_PEAK_RATIO_MAX}) ✗")
    else:
        null_flat = False
        null_str = "J=0 null carries no re-derivable χ array ✗"
    all_ok = all_ok and null_flat

    detail = (
        "cross-updater [" + "; ".join(parts) + "] · " + null_str + " — "
        + ("two independent updaters agree and the J=0 null shows no peak — the M01 "
           "transition is physics, not an analysis artifact"
           if all_ok else
           "a control failed: the updaters disagree, a summary contradicts its raw "
           "values, or the J=0 null grew a spurious peak")
    )
    return all_ok, detail


# ── the planner decision check: does a scheduled receipt's `planned` block
# reconcile with the ledger it claims to have been derived from? ─────────────
# Cross-cutting, not per-milestone: ANY scheduled receipt may carry a compact
# `planned` block (receipt.planned_block — chosen + reason + top-3 scoreboard),
# whatever experiment it ran. So this is a standalone gate over receipts plus
# one aggregate verify() row, NOT a CHECKS entry — the CHECKS registry grades
# "did milestone X's number reproduce", keyed by milestone id, and forcing the
# planner audit through it would grade the wrong axis (and would force every
# historical receipt to carry planned blocks, which manual and pre-planner
# receipts never will).
#
# Score-reconciliation slack, owned by the check. The planner rounds value and
# score to 4 decimals (curriculum.plan_turn), so two honest derivations agree
# to ~5e-5; 1e-3 absorbs that and float noise, while a fabricated score misses
# its class ceiling by whole units, not thousandths.
PLANNED_SCORE_TOL = 1e-3
# The v1 class VOCABULARY → base value. The values are imported from
# curriculum (one source of truth — they cannot drift), but the vocabulary
# KEYS are restated here on purpose: a planner that grew a new class would
# grade False ("outside the v1 vocabulary") instead of silently teaching its
# own audit new law, and test_planner_check pins this map against what
# plan_turn actually emits. "hunt" maps to its CEILING: the remaining-target
# scaling that shrinks a real hunt value lives in reports/hunts state this
# check does not reconstruct. "verified-canary" is absent on purpose — its
# value is staleness-derived per entry, not a constant.
_PLANNED_BASE_VALUE = {
    "open-frontier": OPEN_FRONTIER_VALUE,
    "never-run": NEVER_RUN_VALUE,
    "null-retry": NULL_RETRY_VALUE,
    "hunt": OPEN_FRONTIER_VALUE,
}
_REPEAT_CAP_SUFFIX = " (repeat-capped)"


def check_planned_decision(receipt: dict, records) -> tuple[bool | None, str]:
    """Audit a scheduled receipt's ``planned`` block against the receipts ledger.

    ``records`` are the ``(stamp, mid)`` ledger tuples the scheduler itself
    plans from (``cli._planner_ledger`` shape). The check reconstructs the
    ledger AS THE PLANNER SAW IT — records whose parsed stamp is **strictly
    older** than this receipt's ``generated_at`` — and grades the block's
    claims against it.

    **The boundary, precisely.** Strictly-older is correct because the plan
    precedes the run that stamps the receipt: the receipt's own ledger record
    carries ``stamp == generated_at`` and was not on disk at plan time, and any
    other record stamped at-or-after ``generated_at`` was written concurrently
    or later, so it cannot have informed the decision either. Records whose
    stamps do not parse cannot be placed on either side and are excluded
    (named limitation: the planner would have kept them under a lexicographic
    order; an unparseable committed stamp is already its own defect).

    **What this check CAN prove** (all re-derivable from the block + ledger):

    * the chosen mid is the argmax of its own claimed scoreboard, and the
      board is sorted by descending score (a hand-edited ``chosen`` fails);
    * ledger-refutable class claims: ``never-run`` for a mid the older ledger
      already holds a receipt for is a fabrication; ``verified-canary`` /
      ``null-retry`` for a mid with NO older receipt is one too (both classes
      require a prior receipt under v1 law);
    * value/cost arithmetic as a CEILING: cost divides by ≥ 1.0 and never
      boosts, so every claimed score must sit at or under its class base value
      × the staleness multiplier (re-derived from the mid's newest older
      receipt) × the repeat decay 2^-repeats (repeats re-derived from the
      ledger head, hunt exempt). A score above its ceiling is arithmetic that
      cannot reconcile;
    * the repeat law: a ``(repeat-capped)`` entry must score 0.0 and must
      actually sit at ≥ REPEAT_HARD_CAP re-derived repeats; an entry AT the
      cap with a nonzero score while another entry still scores is the cap
      erased.

    **What it CANNOT prove**, stated so a pass is never over-read:

    * the status classification itself — open/verified/null come from the
      MILESTONES.md of that moment, which history does not preserve, so the
      claimed classes are taken as given wherever the ledger cannot refute
      them (an ``open-frontier`` claim is ungraded by construction);
    * the exact cost divisor (per-mid wall-clock medians are not in the
      ``(stamp, mid)`` ledger) and the hunt's remaining-target scaling — both
      graded only via the ceiling;
    * staleness to the second: the planner's ``now`` is plan time, slightly
      BEFORE ``generated_at``, so the re-derived multiplier is computed at the
      later instant and is ≥ the planner's — the ceiling stays valid and errs
      in the receipt's favor, never against an honest block;
    * single-writer assumption: a receipt committed by another box inside this
      receipt's own run window would land strictly-older here yet was unseen
      at plan time, which can shift the reconstructed head/repeats. The lab's
      run lock makes turns serial per box; a cross-box collision would surface
      as a named repeat mismatch a human then reads against this caveat.

    **Verdict discipline (None is never False):** a receipt WITHOUT a planned
    block passes vacuously (manual runs, historical receipts — carrying no
    claim is not a violation). A block written under a DIFFERENT planner
    version also passes vacuously by design: PLANNER_VERSION exists so an old
    receipt is never re-derived against new law (the version escape is a
    visible hand-edit in a committed file, not a silent one). A block that is
    structurally unreadable — not an object, missing chosen/scoreboard/planner,
    a non-numeric score, a receipt with no parseable ``generated_at`` to
    anchor the boundary — returns ``None``: unreadable evidence, not proof of
    fabrication. ``False`` is reserved for readable arithmetic that does not
    reconcile — the fabrication verdict.
    """
    pr = receipt.get("public_receipt")
    if not isinstance(pr, dict) or "planned" not in pr:
        return True, ("no planned block — a manual or pre-planner receipt; "
                      "passes vacuously")
    block = pr.get("planned")
    if not isinstance(block, dict):
        return None, "planned block is not an object — unreadable, not graded"
    version = block.get("planner")
    if not isinstance(version, str) or not version:
        return None, ("planned block carries no planner version — unreadable, "
                      "not graded")
    if version != PLANNER_VERSION:
        return True, (
            f"planned block written under planner {version!r}, not the current "
            f"{PLANNER_VERSION} law — old decisions are never re-derived "
            f"against new law (PLANNER_VERSION boundary); passes vacuously"
        )
    stamp_raw = receipt.get("generated_at")
    stamp_dt = _parse_stamp(stamp_raw) if isinstance(stamp_raw, str) else None
    if stamp_dt is None:
        return None, ("receipt carries a planned block but no parseable "
                      "generated_at — the strictly-older ledger boundary "
                      "cannot be anchored; unreadable, not graded")

    chosen = block.get("chosen")
    board = block.get("scoreboard")
    if not isinstance(chosen, str) or not chosen \
            or not isinstance(board, list) or not board:
        return None, ("planned block missing its chosen mid or a non-empty "
                      "scoreboard — unreadable, not graded")
    entries: list[tuple[str, str, float]] = []
    for e in board:
        if not isinstance(e, dict):
            return None, "scoreboard entry is not an object — unreadable"
        mid, cls, score = e.get("mid"), e.get("cls"), e.get("score")
        if not isinstance(mid, str) or not mid \
                or not isinstance(cls, str) or not cls:
            return None, ("scoreboard entry missing mid or cls — unreadable, "
                          "not graded")
        if isinstance(score, bool) or not isinstance(score, (int, float)) \
                or not math.isfinite(score):
            return None, (f"scoreboard entry {mid!r} carries a non-numeric "
                          f"score — unreadable, not graded")
        entries.append((mid, cls, float(score)))

    # The ledger as the planner saw it: strictly older, planner's own sort.
    older = []
    for stamp, mid in records or []:
        if not stamp or not mid:
            continue
        dt = _parse_stamp(str(stamp))
        if dt is not None and dt < stamp_dt:
            older.append((str(stamp), str(mid)))
    ordered = sorted(older)
    head_mid, head_run = _head_run(ordered)
    last_stamp: dict[str, str] = {}
    for s, m in ordered:
        last_stamp[m] = s          # ordered ascending — the last write wins

    problems: list[str] = []
    scores = [s for _mid, _cls, s in entries]
    if scores != sorted(scores, reverse=True):
        problems.append("scoreboard is not sorted by descending score")
    seen_mids = [m for m, _c, _s in entries]
    if len(set(seen_mids)) != len(seen_mids):
        problems.append("scoreboard repeats a mid")
    chosen_scores = [s for m, _c, s in entries if m == chosen]
    if not chosen_scores:
        problems.append(f"chosen {chosen} is absent from its own scoreboard")
    elif chosen_scores[0] + PLANNED_SCORE_TOL < max(scores):
        top_mid = entries[scores.index(max(scores))][0]
        problems.append(
            f"chosen {chosen} (score {chosen_scores[0]:.4f}) is not the argmax "
            f"of its own scoreboard (max {max(scores):.4f} at {top_mid})"
        )

    for mid, cls, score in entries:
        capped = cls.endswith(_REPEAT_CAP_SUFFIX)
        base_cls = cls[:-len(_REPEAT_CAP_SUFFIX)] if capped else cls
        if score < -PLANNED_SCORE_TOL:
            problems.append(f"{mid}: negative score {score:.4f}")
            continue
        if (base_cls == "hunt") != (mid == HUNT_CANDIDATE):
            problems.append(
                f"{mid}: v1 law assigns class 'hunt' to {HUNT_CANDIDATE} and "
                f"nothing else (claimed {cls!r})"
            )
            continue
        # Ledger-refutable class claims.
        if base_cls == "never-run" and mid in last_stamp:
            problems.append(
                f"{mid}: claims never-run but the older ledger holds a "
                f"receipt stamped {last_stamp[mid]}"
            )
            continue
        if base_cls in ("verified-canary", "null-retry") \
                and mid not in last_stamp:
            problems.append(
                f"{mid}: claims {base_cls} but the older ledger holds no "
                f"receipt for it (v1 would class it never-run)"
            )
            continue
        # The re-derivable ceiling: base value × staleness × repeat decay.
        if base_cls == "verified-canary":
            stamped = _parse_stamp(last_stamp[mid])
            if stamped is None:
                multiplier = 1.0   # the planner's own unreadable-stamp rule
            else:
                days = max(
                    0.0, (stamp_dt - stamped).total_seconds() / 86400.0)
                multiplier = min(
                    STALENESS_CAP,
                    math.log2(1.0 + days / CANARY_HALF_LIFE_DAYS),
                )
            ceiling = VERIFIED_CANARY_VALUE * multiplier
        elif base_cls in _PLANNED_BASE_VALUE:
            ceiling = _PLANNED_BASE_VALUE[base_cls]
        else:
            problems.append(
                f"{mid}: class {base_cls!r} is outside the v1 vocabulary")
            continue
        repeats = head_run if (mid == head_mid and mid != HUNT_CANDIDATE) \
            else 0
        if mid != HUNT_CANDIDATE:
            ceiling *= 2.0 ** -repeats
        if capped:
            if score > PLANNED_SCORE_TOL:
                problems.append(
                    f"{mid}: claims the repeat cap yet scores {score:.4f} "
                    f"(a capped entry scores exactly 0)"
                )
            if repeats < REPEAT_HARD_CAP:
                problems.append(
                    f"{mid}: claims the repeat cap at {repeats} re-derived "
                    f"consecutive repeats (cap fires at {REPEAT_HARD_CAP})"
                )
            continue
        if repeats >= REPEAT_HARD_CAP and score > PLANNED_SCORE_TOL and any(
                s > PLANNED_SCORE_TOL for m, _c, s in entries if m != mid):
            problems.append(
                f"{mid}: {repeats} re-derived consecutive repeats meet the "
                f"hard cap, another candidate still scores, yet the entry "
                f"scores {score:.4f} — the repeat law erased"
            )
            continue
        if score > ceiling + PLANNED_SCORE_TOL:
            problems.append(
                f"{mid}: score {score:.4f} exceeds its re-derived ceiling "
                f"{ceiling:.4f} ({base_cls} at {repeats} repeat(s); cost "
                f"only divides, it never boosts)"
            )

    if problems:
        return False, ("planned block does not reconcile with the ledger it "
                       "claims — " + "; ".join(problems))
    return True, (
        f"planned {PLANNER_VERSION} block reconciles: chosen {chosen} is the "
        f"argmax of its own top-{len(entries)} scoreboard, and every claimed "
        f"class/staleness/repeat score sits at or under its ceiling against "
        f"{len(ordered)} strictly-older ledger record(s)"
    )


def _planned_ledger_records() -> list[tuple[str, str]]:
    """``(stamp, mid)`` tuples from the committed receipts ledger.

    The checker's own thin reader of the SAME ledger the scheduler plans from
    (``cli._planner_ledger``), using the same stem parser as the writer
    (``publish._split_receipt_stem``) so the two can never disagree about a
    name, and reading through this module's ``REPORTS_DIR`` so the verify
    tests' path isolation covers it. Durations are deliberately not read —
    the audit grades cost only as a ceiling (see ``check_planned_decision``).
    """
    from .publish import _split_receipt_stem
    records: list[tuple[str, str]] = []
    receipts = REPORTS_DIR / "receipts"
    if not receipts.exists():
        return records
    date_glob = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
    for path in sorted(receipts.glob(f"run-{date_glob}-*.json")):
        date, _turn, slug = _split_receipt_stem(path.stem[len("run-"):])
        if not slug:
            continue
        stamp = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                stamp = data.get("generated_at")
        except (OSError, ValueError):
            pass
        if not (isinstance(stamp, str) and stamp):
            stamp = date
        records.append((stamp, slug.upper()))
    return records


def audit_planned_decisions(reports: list[dict], records=None) -> dict | None:
    """The cross-cutting verify() row over every receipt carrying a planned block.

    Returns ``None`` when NO report carries one — vacuous by absence, no row:
    manual and pre-planner receipts owe nothing, and a permanent all-clear row
    for a check with nothing to check would be surface spam. Otherwise one
    aggregate row: ``fail`` when any block's arithmetic does not reconcile
    (the fabrication verdict), else ``unreadable`` when any block could not be
    graded (unreadable evidence blocks the gate without being called
    fabricated — the None-is-never-False discipline carried to the surface),
    else ``pass`` with the count. Vacuous per-receipt passes (no block,
    version boundary) are not counted as audited.
    """
    if records is None:
        records = _planned_ledger_records()
    graded: list[tuple[str, bool | None, str]] = []
    for rep in reports:
        pr = rep.get("public_receipt")
        if not (isinstance(pr, dict) and "planned" in pr):
            continue
        ok, detail = check_planned_decision(rep, records)
        if ok is True and "PLANNER_VERSION boundary" in detail:
            continue               # version-boundary blocks are not audits
        name = str(rep.get("generated_at") or rep.get("experiment") or "?")
        graded.append((name, ok, detail))
    if not graded:
        return None
    failed = [(n, d) for n, ok, d in graded if ok is False]
    unreadable = [(n, d) for n, ok, d in graded if ok is None]
    if failed:
        named = "; ".join(f"{n}: {d}" for n, d in failed[:3])
        return {"id": "PLANNED", "status": "fail",
                "detail": (f"{len(failed)}/{len(graded)} planned block(s) do "
                           f"not reconcile — {named}")}
    if unreadable:
        named = "; ".join(f"{n}: {d}" for n, d in unreadable[:3])
        return {"id": "PLANNED", "status": "unreadable",
                "detail": (f"{len(unreadable)}/{len(graded)} planned block(s) "
                           f"unreadable — {named}")}
    return {"id": "PLANNED", "status": "pass",
            "detail": (f"{len(graded)} planned block(s) re-derive against "
                       f"the strictly-older receipts ledger")}


# milestone id → check. Add entries as milestones land; the rest report
# "unchecked" so the gap is visible rather than silently assumed.
CHECKS = {"M01": check_m01, "M02": check_m02, "M03": check_m03,
          "M04": check_m04, "M05": check_m05, "M06": check_m06,
          "M07": check_m07, "M08": check_m08, "M09": check_m09,
          "M10": check_m10, "M11": check_m11, "M12": check_m12,
          "M13": check_m13, "M14": check_m14, "M15": check_m15,
          "M16": check_m16, "M17": check_m17, "M18": check_m18,
          "K01": check_k01, "K02": check_k02,
          "C01": check_c01, "A01": check_a01, "A03": check_a03, "A04": check_a04,
          "A05": check_a05, "I01": check_i01, "CTRL": check_controls}


def _grade(fn, reports: list[dict]) -> tuple[str, str]:
    """Grade a milestone against the newest report its check can evaluate.

    A checker that raises on a report is a named failure, not a dead gate: the
    exception text is surfaced as the detail and the other milestones keep grading.
    """
    for rep in reports:
        try:
            ok, detail = fn(rep)
        except Exception as exc:                # noqa: BLE001 — any crash must grade
            return "fail", f"checker crashed: {type(exc).__name__}: {exc}"
        if ok is not None:
            return ("pass" if ok else "fail"), detail
    return "no-report", "no report this check can evaluate"


def verify(ids: list[str] | None = None) -> list[dict]:
    """Run registered checks against every verified milestone (or just ``ids``).

    Each result: ``pass`` / ``fail`` (check ran), ``unchecked`` (no check yet),
    or ``no-report`` (nothing the check can read). A report file that cannot be
    parsed as a JSON object — a truncated campaign write, a corrupt disk read —
    is emitted as its own named ``unreadable`` row (which fails the CLI gate)
    while every readable report still grades: one bad file degrades to a named
    failure instead of killing the whole gate.

    A full run (no ``ids`` filter) also grades the cross-cutting planner audit:
    every readable report carrying a ``planned`` block is checked against the
    receipts ledger (``audit_planned_decisions``) and the result lands as one
    aggregate ``PLANNED`` row — absent entirely when no report carries a block,
    so historical and manual receipts are never forced to carry one.
    """
    ms = parse_milestones(MILESTONES_MD.read_text(encoding="utf-8") if MILESTONES_MD.exists() else "")
    reports: list[dict] = []
    results: list[dict] = []
    for p in _reports_newest_first():
        try:
            rep = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            results.append({"id": p.name, "status": "unreadable",
                            "detail": f"unreadable report: {exc}"})
            continue
        if not isinstance(rep, dict):
            results.append({"id": p.name, "status": "unreadable",
                            "detail": "unreadable report: JSON root is not an object"})
            continue
        reports.append(rep)
    for m in ms:
        if m["status"] != "verified" or (ids and m["id"] not in ids):
            continue
        fn = CHECKS.get(m["id"])
        if fn is None:
            results.append({"id": m["id"], "status": "unchecked", "detail": "no check registered"})
        else:
            status, detail = _grade(fn, reports)
            results.append({"id": m["id"], "status": status, "detail": detail})
    if ids is None:
        planned_row = audit_planned_decisions(reports)
        if planned_row is not None:
            results.append(planned_row)
    return results
