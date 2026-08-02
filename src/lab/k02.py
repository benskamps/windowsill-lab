"""K02 — the susceptibility's *shape*, and whether it survives N.

K01 asked where the coherence transition is and graded the answer against a number
theory pins exactly (``K_c = 2γ``). K02 tests a shape law that came out of Ben's own
coherence research rather than a textbook — and, after a literature cross-check,
calibrates the finite-size scaling underneath it against a **published** exponent.

### Provenance: this is a REDISCOVERY, and it says so

An adversarial literature assay (`docs/assays/2026-08-02-k02-literature-crosscheck.md`)
established that essentially every element of K02 is published, in this model, with
this frequency distribution, this sampling rule, and this estimator — over a wider N
range and with far longer runs. Specifically:

* **The engine is a published configuration, verbatim.** ``kuramoto.lorentzian_frequencies``
  builds ω from the midpoint quantiles ``(i+½)/N``, which is Hong et al. 2015
  Eq. (4.1)'s "regular" frequency set and Park & Park 2024 Eq. (9)'s "equally spaced"
  (ES, s = ½) case. Hong et al. §IV A then treat the **regular Lorentzian**
  explicitly — their ``ω_j = γ tan[jπ/N − (N+1)π/(2N)]`` is this module's frequency
  set term for term.
* **The estimator is standard.** ``χ = N·Var_t(r)`` is Park & Park Eq. (6) and Hong
  et al.'s "dynamic fluctuations of the order parameter".
* **The regular-vs-random sampling distinction is the field's organizing axis**, not
  an incidental detail: it changes the universality class (β/ν̄ = 0.39 regular vs
  0.20 random).

So K02 claims no novelty about the Kuramoto model. What it does is (a) **calibrate**
this engine against a published finite-size exponent, and (b) refute a specific
closed form — Run 01's — that only this lab ever proposed. Both are worth having;
neither is a discovery. See the "what is actually unpublished" note at the bottom.

Citations, pinned:

* H. Hong, H. Chaté, L.-H. Tang, H. Park, *"Finite-size scaling, dynamic
  fluctuations, and hyperscaling relation in the Kuramoto model,"* Phys. Rev. E
  **92**, 022122 (2015), arXiv:1503.06393. §IV Eq. (4.1) (regular sampling);
  §IV A (regular **Lorentzian** — this engine); Eq. (4.2)–(4.3) (β/ν̄ = 0.39(2));
  §III Eq. (3.10) (the χ peak is **subcritical** and drifts to K_c as N^(−1/ν̄')).
* S.-C. Park, H. Park, *"Finite-size scaling of the Kuramoto model at criticality,"*
  Phys. Rev. E **110**, 034216 (2024), arXiv:2406.18904. Eq. (6) (χ); Eq. (7)
  (r ~ N^(−β/ν̄_c)); Eq. (20) (asymptotic β/ν̄_c = 0.325(15), reached only for
  N ≳ 2¹⁵); §II (why they avoid the Lorentzian under regular sampling).

### The claim under test

Run 01 of the coherence-window work (`~/projects/coherence-lab/coherence-window/
report/REPORT.md`) replotted the order-parameter susceptibility

    χ = N · Var_t(r)

against the *measured coherence* ``r`` instead of the control ``K``, found an
interior maximum at **partial** order (r\\* ≈ 0.40), and fitted the closed form

    χ(r) = a · r²(1−r)³        interior maximum at r\\* = p/(p+q) = 2/5

with R² = 0.967. That fit is **empirical, not derived** — the report's own Knuth
tag. It was measured at a **single population size, N = 24**, with an added noise
term D = 0.20. The analytic part of Run 01 derives only the *family* (two zeros and
one interior max ⇒ a Beta-shaped bump), never the exponents (2, 3).

K02 puts that form on the lab's calibrated engine and asks the one question a
single-N fit cannot answer: **does the shape survive N?**

### Four graded-differently claims

0. **The calibration (the headline).** ``⟨r⟩`` measured at the *exact* coupling
   ``K = K_c = 2γ`` decays with population size as ``r(K_c, N) ~ N^(−β/ν̄_c)``, and
   the measured exponent is graded against the published **0.39(2)**. This replaced
   an earlier headline that was an artifact — see "the estimator that had to be
   demoted" below. It is the only number here comparable to anything outside this
   lab, and it needs no peak-finding at all.
1. **An interior peak in r exists** — χ is maximal at partial coherence, not at
   r → 0 or r → 1. Robust, and gated.
2. **Where the peak sits, as N grows.** ``r\\*`` is measured (never assumed) at every
   rung of an N-ladder, with an honest floor. Whether it lands on 2/5 is *reported*,
   not assumed.
3. **The shape itself.** ``a·r^p(1−r)^q`` is fitted with p and q **free** at each N,
   and the Run 01 exponents (2, 3) are fitted as a constrained special case for a
   like-for-like R². This sub-claim is **exploratory and deliberately not gated** —
   hard-gating on (2, 3) landing would manufacture the answer.

### The estimator that had to be demoted

The first version of this milestone reported the collapse exponent as **−0.28**,
read off the free Beta fit's interior maximum ``p/(p+q)`` because the raw argmax was
too noisy to resolve. The literature assay identified that as an estimator defect
rather than a measurement, and it was right: ``p/(p+q)`` is a ratio of two parameters
that are themselves drifting with N (p: 0.50 → 0.91, q: 2.00 → 8.74) inside a family
that demonstrably does not fit the data (free-fit R² only 0.73–0.82). Its
N-dependence therefore compounds the real physics with the family's own misfit drift,
and there is no way to separate the two after the fact. The numbers are still
reported below as a documented property of that fit — they are **not** evidence for
a scaling exponent, and −0.28 should not be quoted as one anywhere.

The replacement is claim 0: evaluate ⟨r⟩ at a coupling theory pins exactly instead of
at one that has to be searched for. No argmax, no singular Jacobian, no fitted family.

### Why the r-axis is ill-conditioned near the transition (the honest floor)

Above the transition the exact mean-field branch is ``r(K) = √(1 − K_c/K)``, whose
slope ``dr/dK = K_c/(2r K²)`` **diverges as r → 0⁺**. The χ peak sits essentially at
K_c, which is exactly where that slope blows up: a uniform grid in K lands almost no
points in the r-interval where the peak lives, and one grid step in K is a large,
strongly asymmetric step in r. This is the *same* pathology K01 documented for its
steepest-rise cross-check estimator, seen from the other side — and it is a property
of the parameterization, not a defect of the run. It is why the coupling grid here is
**non-uniform** (dense across [0.98, 1.12]·K_c, sparse elsewhere), and why ``r\\*``
carries the local r-spacing as an explicit resolution floor rather than a refined
sub-grid number pretending to more precision than the axis can hold.

### The finite-size argument this milestone actually lands

χ(K) peaks **at or near** the transition, and the coherence *there* is not a
constant: for a finite population it is r(K_c, N), which falls as a power of N —
claim 0 above, and Hong et al. Eq. (4.3). Compose the two and the conclusion is
structural rather than empirical:

    the χ peak's fixed point lives in **K**, not in **r**,

so ``r\\*`` inherits the finite-size scaling of the coherence at criticality and
**cannot** be an N-independent constant. Any single-N measurement of r\\* — including
Run 01's 2/5 — is reading the population size, not a law.

**"At or near" is doing real work there, and this module's earlier wording got it
wrong.** It claimed the peak sits at a *fixed* K_c at every N. The literature is
sharper: Hong et al. §III report the peak coupling is **always on the subcritical
side** and only *approaches* K_c as N grows, drifting as δK_max ~ N^(−1/ν̄') (their
Eq. 3.10). This ladder's measured peak couplings scatter on *both* sides of K_c with
a standard deviation of ≈0.024 — wider than the drift it would need to resolve — so
the honest statement is that the peak's location is **unresolved from K_c at this
resolution**, not that it is fixed there. The mechanism survives intact, because the
drift vanishes as N → ∞ and the argument only needs the peak to be *asymptotically*
at K_c; but the measurement must not be reported as sharper than it is.

This is not a new doubt about Run 01 either. A later coherence-lab run
(`sims/unified-engine/docs/ensemble-chi-finite-size-2026-06-08.md`) had already found
the (1−r)³ exponent rejected at larger N, with R² collapsing 0.967 → 0.674 and the
argmax drifting 0.401 → 0.367 → 0.319 across N = 24, 48, 96.

**A numerical coincidence to keep apart.** Run 01's r\\* = 2/5 is a *coherence* — a
dimensionless order parameter in [0,1]. Hong et al.'s β/ν̄ = 0.39(2) ≈ 2/5 is a
*scaling exponent*. Different quantities, different dimensions, landing on the same
number in this model by accident. Nothing connects them, and any writeup that puts
both "2/5" figures near each other must say so — that collision is exactly how a
spurious "deep connection" gets manufactured.

### What is actually unpublished here

The assay ran four targeted searches and found no paper that plots χ against the
measured r rather than against K. That negative is real but it is **not** novelty:
reparametrizing a susceptibility by its own response variable discards the control
variable and introduces a singular Jacobian (dr/dK → ∞ at K_c⁺ — precisely the
conditioning problem this module fights). Specialists do not do it because it is a
worse way to look at the same physics, and "the fixed point is in K, not in r" is
closer to a definition than a finding. Its value here is **pedagogical**, and as a
correction to one specific error a non-specialist can easily make — a real
contribution to this lab's own project, and not one to the Kuramoto literature.

### What is different about this engine, stated out loud

Run 01 ran a **noisy** Kuramoto (D = 0.20) at N = 24. This engine is the
**deterministic** one K01 calibrated: fixed-step RK4, no stochastic forcing, natural
frequencies drawn by deterministic inverse-CDF quantile sampling. The fluctuation χ
measures here therefore comes from finite-N beating of unlocked oscillators alone,
not from thermal noise. That is a real difference in model, and it is a reason to
read the *mechanism* above — which is regime-independent — as the load-bearing
result, and the specific fitted exponents as engine-specific evidence.

### Statistics, and why the seeds are combined by MEDIAN

The only randomness in the engine is the initial condition, and it matters more than
it looks. Every rung is therefore run at ``CALIBRATION_SEEDS`` initial conditions and
combined before any peak is located — the same reason Run 01 averaged 8 seeds.

The combination is the **median**, not the mean, and that is a measured decision. A
first 3-seed pass over this exact ladder produced a clean, textbook χ curve at every
rung *except* N = 2000, where one point (K = 1.09·K_c) came back at χ = 2.78 between
neighbours of 1.63 and 0.52 — a 5× drop in one grid step, against smooth monotone
decay at N = 1000 and N = 4000. That is one initial condition undergoing a rare
intermittent de-synchronization excursion inside the measurement window: a real
dynamical event, but one whose contribution to a *time* variance is enormous and
whose arrival is Poisson-rare. Near criticality at finite N the per-seed Var_t(r) is
therefore heavy-tailed, and the mean of three draws from a heavy-tailed law is not a
location estimator — it hijacked the argmax and moved the measured peak from K_c to
1.088·K_c, wrecking the N-scaling fit (R² = 0.008) while every other rung sat on K_c.

The median over initial conditions is the robust answer, and it is the honest one
here because **χ is used in K02 as a peak locator across a ladder, not as an absolute
susceptibility amplitude**: a location estimator's downward bias relative to the mean
is close to uniform across the sweep, and the shape fit absorbs any uniform scale into
its free coefficient ``a``. The per-seed peaks are all reported in ``r_star_by_seed``
and the mean-combined peak is carried as an explicit cross-check, so the choice is
visible in the receipt rather than buried in it.

NumPy only, CPU: the mean-field collapse keeps this O(N)-per-step.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

# ── the fixed K02 identity ────────────────────────────────────────────────────
# K02 is ONE N-ladder measurement, not a caller-selected amount of easy work.
# ``checks.check_k02`` re-derives these and refuses to grade a run that changed
# any of them — the same identity gate check_k01 puts on its calibration.
CALIBRATION_GAMMA = 0.5              # Lorentzian half-width ⇒ exact K_c = 2γ = 1.0
CALIBRATION_LADDER = (250, 500, 1000, 2000, 4000)   # the N-ladder, 16× end to end
CALIBRATION_SEEDS = (42, 7, 1234, 2718, 31415)      # initial conditions per rung

# The coupling grid, in units of the exact K_c = 2γ. Deliberately NON-uniform: the
# χ peak sits at K_c, and r(K) = √(1−K_c/K) has infinite slope there, so a uniform
# grid would resolve the r-axis worst exactly where the measurement happens. The
# dense arm buys r-resolution around the peak; the sparse arms carry the rest of
# the r-range (out to r ≈ 0.71) that the shape fit needs, at almost no cost.
K_GRID_SPARSE_LOW = (0.0, 0.4, 0.8)                 # incl. K=0, the negative control
K_GRID_APPROACH = (0.90, 0.95)
K_GRID_DENSE = (0.98, 1.12, 15)                     # linspace(lo, hi, n) — ΔK = 0.01·K_c
K_GRID_SHOULDER = (1.20, 1.30, 1.40)
K_GRID_SPARSE_HIGH = (1.6, 1.8, 2.0)

# Run 01's fitted exponents and the interior maximum they imply — the numbers under
# test, carried here so the report can state what it is measuring against.
RUN01_P = 2.0
RUN01_Q = 3.0
RUN01_R_STAR = RUN01_P / (RUN01_P + RUN01_Q)         # 2/5

# ── the published benchmark this milestone is now calibrated against ─────────
# Hong, Chaté, Tang & Park, Phys. Rev. E 92, 022122 (2015), Eq. (4.3): for the
# REGULAR (deterministic-quantile) Lorentzian frequency set — this engine's exact
# configuration, see the module docstring — the order parameter at criticality
# decays as r(K_c, N) ~ N^(−β/ν̄_c) with
#
#     β/ν̄_c = 0.39(2)     measured over N = 200…12800
#
# Park & Park, Phys. Rev. E 110, 034216 (2024), Eq. (20) revise the ASYMPTOTIC
# value to 0.325(15), but are explicit that the effective exponent sits near 0.37
# until N ≳ 2^15 = 32768 and only then crosses over. This ladder tops out at
# N = 4000 = 2^12, deep in the pre-asymptotic regime, so 0.39(2) is the value to
# grade against and 0.325(15) is the asymptote it would eventually walk toward.
CRITICAL_EXPONENT_PUBLISHED = 0.39
CRITICAL_EXPONENT_PUBLISHED_ERR = 0.02
CRITICAL_EXPONENT_ASYMPTOTIC = 0.325
# The RANDOM (iid-draw) frequency set is a different universality class entirely —
# ν̄ = 5/2, β/ν̄ = 1/5 (Hong et al. 2015 §III). Carried as the negative benchmark:
# a run that accidentally sampled frequencies at random rather than on the
# deterministic quantile grid would land near 0.20, not 0.39.
CRITICAL_EXPONENT_RANDOM_SAMPLING = 0.20

# The critical-point measurement's own protocol. Long windows are not caution,
# they are a requirement measured directly: see ``critical_coherence``.
CRITICAL_SEEDS = 12
CRITICAL_T_BURN = 2000.0
CRITICAL_T_MEASURE = 2000.0

# ── the tail-clip negative control ───────────────────────────────────────────
# ``kuramoto`` clips the Lorentzian's tails at |ω| ≤ 40γ so no oscillator is aliased by
# the integrator. That preserves g(0) and therefore K_c exactly — but Hong et al.'s
# published Lorentzian is UNCLIPPED, and the clip collapses ~1.6% of the population onto
# two degenerate frequencies inside exactly the "running oscillator" population that
# Park & Park 2024 (Eq. 27, Appendix) argue may dominate the finite-size correction. So
# the clip is an uncontrolled difference from the configuration this milestone is graded
# against, and the honest response is to measure whether it matters rather than to argue
# that it doesn't. The control re-measures r(K_c) at a 2.5× looser clip with dt reduced
# 4× to keep the fastest drifter resolved (|ω|·dt stays at 0.25 rad); if the exponent
# were riding on the clip, the two would disagree.
CLIP_CONTROL_N = 1000
CLIP_CONTROL_SEEDS = 6
CLIP_CONTROL_ALT_SCALE = 100.0
CLIP_CONTROL_ALT_DT = 0.005
CLIP_CONTROL_T_BURN = 1500.0
CLIP_CONTROL_T_MEASURE = 1000.0

# Integration. Mirrors K01's shipped calibration (dt = 0.02 was cross-checked there
# against dt = 0.01 and agreed on the graded peak to four decimals), with a slightly
# shorter window so the whole 5-rung × 3-seed ladder stays a CPU-minutes job.
DT = 0.02
T_BURN = 100.0
T_MEASURE = 200.0
SAMPLE_EVERY = 10

# Where the ordered branch is clean enough for a "give the claim its best shot" fit:
# at K ≥ K_c the coherence is a genuine monotone function of K, whereas below the
# transition every coupling maps into the same narrow 1/√N noise floor and no smooth
# function of r can pass through that near-vertical pile. Fitting both ranges is the
# adversarial-audit move — the constrained fit gets its most favourable footing.
BRANCH_FIT_K_MIN_FACTOR = 1.0


@dataclass
class K02Rung:
    """One population size: the swept curve, the located peak, and the shape fits."""

    n: int
    K: list
    r_mean: list
    r_var: list
    chi: list
    peak_index: int
    r_star: float               # HEADLINE: measured r at the χ argmax
    r_star_refined: float       # cross-check: 3-point parabola on the (r, χ) points
    r_resolution: float         # error floor — half the local r-spacing at the peak
    r_star_by_seed: list        # per-initial-condition r*, evidence for the scatter
    r_star_mean_combined: float # cross-check: r* if the seeds were MEANED, not medianed
    k_peak_mean_combined: float
    k_peak: float               # anchor: where χ peaks in K — exact theory says K_c
    chi_peak: float
    chi_endpoint_ratio: float   # χ_peak / max(χ at the two ends of the r range)
    r_incoherent: float         # ⟨r⟩ at K=0 — the 1/√N negative control
    r_incoherent_scale: float
    fit_free: dict              # a·r^p(1−r)^q, p and q free, whole sweep
    fit_run01: dict             # a·r²(1−r)³, only a free, whole sweep
    fit_free_branch: dict       # same two, restricted to the clean ordered branch
    fit_run01_branch: dict
    wall_seconds: float


@dataclass
class K02Result:
    rungs: list = field(default_factory=list)
    critical: list = field(default_factory=list)   # r(K_c, N) per rung — the calibration
    critical_fit: dict = field(default_factory=dict)
    clip_control: list = field(default_factory=list)   # the tail-clip negative control
    gamma: float = CALIBRATION_GAMMA
    kc_exact: float = 0.0
    seeds: tuple = CALIBRATION_SEEDS
    scaling_exponent: float = float("nan")   # slope of log r* vs log N
    scaling_r2: float = float("nan")
    r_star_drift: float = float("nan")       # r*(N_min) − r*(N_max)
    is_calibration: bool = False
    wall_seconds: float = 0.0
    config: dict = field(default_factory=dict)


def coupling_grid(gamma: float = CALIBRATION_GAMMA):
    """The non-uniform coupling grid, in absolute units, built from K_c multiples."""
    import numpy as np

    k_c = 2.0 * gamma
    lo, hi, count = K_GRID_DENSE
    parts = [
        np.asarray(K_GRID_SPARSE_LOW, dtype=np.float64),
        np.asarray(K_GRID_APPROACH, dtype=np.float64),
        np.linspace(lo, hi, count),
        np.asarray(K_GRID_SHOULDER, dtype=np.float64),
        np.asarray(K_GRID_SPARSE_HIGH, dtype=np.float64),
    ]
    return np.unique(np.round(np.concatenate(parts) * k_c, 12))


def parabola_vertex(x0, y0, x1, y1, x2, y2) -> float:
    """Vertex of the quadratic through three **unequally spaced** points.

    ``kuramoto.refine_peak`` assumes a uniform abscissa, which is true of a coupling
    sweep and emphatically false of the r-axis it induces (one grid step in K can be
    a 4× wider step in r on one side of the peak than the other). Using the uniform
    formula here would report a sub-grid position biased toward the wide side.
    """
    d1, d2 = x1 - x0, x1 - x2
    num = d1 * d1 * (y1 - y2) - d2 * d2 * (y1 - y0)
    den = d1 * (y1 - y2) - d2 * (y1 - y0)
    if den == 0.0:
        return float(x1)
    return float(x1 - 0.5 * num / den)


def fit_beta_shape(r, chi, p_bounds=(0.05, 12.0), q_bounds=(0.05, 40.0), rounds=5, grid=41):
    """Least-squares fit of ``a·r^p(1−r)^q`` in χ-space, p and q free.

    ``a`` is *linear* given (p, q), so it is solved exactly at every trial pair and
    only the two exponents are searched — a nested grid refinement, which is fully
    deterministic and needs no optimizer (and therefore no SciPy). R² is reported
    against χ itself, the same space Run 01 quoted its 0.967 in; a log-space fit
    would minimise relative error instead and is not comparable.
    """
    import numpy as np

    r = np.asarray(r, dtype=np.float64)
    chi = np.asarray(chi, dtype=np.float64)
    mask = (r > 0.0) & (r < 1.0) & np.isfinite(chi)
    rr, yy = r[mask], chi[mask]
    if rr.size < 4:
        return {"p": float("nan"), "q": float("nan"), "a": float("nan"),
                "r2": float("nan"), "peak": float("nan"), "points": int(rr.size)}
    sst = float(((yy - yy.mean()) ** 2).sum())
    log_r, log_1mr = np.log(rr), np.log1p(-rr)
    p_lo, p_hi = p_bounds
    q_lo, q_hi = q_bounds
    best = None
    for _ in range(rounds):
        for p in np.linspace(p_lo, p_hi, grid):
            base = p * log_r
            for q in np.linspace(q_lo, q_hi, grid):
                b = np.exp(base + q * log_1mr)
                bb = float((b * b).sum())
                if bb <= 0.0 or not math.isfinite(bb):
                    continue
                a = float((b * yy).sum()) / bb
                sse = float(((yy - a * b) ** 2).sum())
                if best is None or sse < best[0]:
                    best = (sse, float(p), float(q), a)
        _, p, q, _ = best
        dp = 2.0 * (p_hi - p_lo) / (grid - 1)
        dq = 2.0 * (q_hi - q_lo) / (grid - 1)
        p_lo, p_hi = max(0.01, p - dp), p + dp
        q_lo, q_hi = max(0.01, q - dq), q + dq
    sse, p, q, a = best
    return {
        "p": p, "q": q, "a": a,
        "r2": 1.0 - sse / sst if sst > 0 else float("nan"),
        # The interior max of r^p(1−r)^q is at p/(p+q) — the fit's own prediction for
        # where the peak is, which can be compared to the MEASURED argmax. A family
        # that cannot put its maximum where the data's is has been refuted twice.
        "peak": p / (p + q) if (p + q) > 0 else float("nan"),
        "points": int(rr.size),
    }


def fit_fixed_shape(r, chi, p: float = RUN01_P, q: float = RUN01_Q) -> dict:
    """The same fit with the exponents **pinned** to Run 01's (2, 3) — only ``a`` free.

    This is the like-for-like test of the published form. Because a single scale is
    still fitted, R² < 0 is meaningful and damning: it means the closed form tracks
    the measured χ(r) *worse than a horizontal line through its own mean*.
    """
    import numpy as np

    r = np.asarray(r, dtype=np.float64)
    chi = np.asarray(chi, dtype=np.float64)
    mask = (r > 0.0) & (r < 1.0) & np.isfinite(chi)
    rr, yy = r[mask], chi[mask]
    if rr.size < 3:
        return {"p": p, "q": q, "a": float("nan"), "r2": float("nan"),
                "peak": p / (p + q), "points": int(rr.size)}
    b = rr ** p * (1.0 - rr) ** q
    bb = float((b * b).sum())
    a = float((b * yy).sum()) / bb if bb > 0 else float("nan")
    sse = float(((yy - a * b) ** 2).sum())
    sst = float(((yy - yy.mean()) ** 2).sum())
    return {
        "p": p, "q": q, "a": a,
        "r2": 1.0 - sse / sst if sst > 0 else float("nan"),
        "peak": p / (p + q),
        "points": int(rr.size),
    }


def locate_r_peak(r, chi):
    """Locate the χ maximum on the r-axis and state the axis's own resolution there.

    Returns ``(index, r_star, r_star_refined, resolution)``. ``r_star`` is the plain
    measured coherence at the argmax — deliberately the headline, because the r-axis
    spacing around the peak is strongly asymmetric and a refined sub-grid position
    would claim precision the parameterization does not have. ``resolution`` is half
    the r-interval the peak's two neighbours span: the honest error floor.
    """
    import numpy as np

    r = np.asarray(r, dtype=np.float64)
    chi = np.asarray(chi, dtype=np.float64)
    i = int(np.argmax(chi))
    if not (0 < i < r.size - 1):
        return i, float(r[i]), float(r[i]), float("nan")
    refined = parabola_vertex(r[i - 1], chi[i - 1], r[i], chi[i], r[i + 1], chi[i + 1])
    resolution = 0.5 * abs(float(r[i + 1]) - float(r[i - 1]))
    return i, float(r[i]), refined, resolution


def kuramoto_clip_default() -> float:
    """The engine's shipped tail-clip, in units of γ — read, never re-typed here.

    The clip-control test asserts the control actually *varies* the clip; hard-coding
    40.0 in two places would let the two drift apart and silently turn the control into
    a comparison of a setting with itself.
    """
    from .kuramoto import OMEGA_CLIP_SCALE

    return float(OMEGA_CLIP_SCALE)


def critical_coherence(
    n: int,
    gamma: float = CALIBRATION_GAMMA,
    seeds: int = CRITICAL_SEEDS,
    dt: float = DT,
    t_burn: float = CRITICAL_T_BURN,
    t_measure: float = CRITICAL_T_MEASURE,
    sample_every: int = SAMPLE_EVERY,
    clip_scale: float = None,
    seed: int = 20260802,
) -> dict:
    """⟨r⟩ at **exactly** K_c = 2γ, per initial condition — the literature's estimator.

    This is the measurement the K02 revision turns on, and it is deliberately *not*
    a peak-finding problem. ``r(K_c, N) ~ N^(−β/ν̄_c)`` is evaluated at a coupling
    that theory pins exactly, so there is no argmax to locate, no square-root
    Jacobian to fight, and no fitted family to inherit assumptions from. It is
    directly comparable to Hong et al. 2015 Eq. (4.2)–(4.3) and Park & Park 2024
    Eq. (7).

    **Initial conditions are batched, not couplings.** ``run_sweep`` replicates one
    IC across a column of couplings; here the column *is* the IC ensemble, at a
    single coupling — which is why this measurement costs ~1/26 of a sweep per seed
    and can afford the long windows the next paragraph turns out to require.

    **Equilibration is the whole game, and it is why this function exists.** The χ
    sweep's window (t_burn 100, t_measure 200) is ample at N = 250 and badly
    insufficient at N = 4000: relaxation at criticality slows with N, and a traced
    run at K_c showed ⟨r⟩ still falling long after the sweep had stopped looking —
    0.070 (t ∈ [100,300)) → 0.049 → 0.036 → 0.028 → 0.027 (t ∈ [2000,3000)), while
    N = 250 sat flat at 0.085 from t = 100 onward. Reading the sweep's window at
    N = 4000 therefore measures a transient, not a stationary state, and inflates
    ⟨r⟩ by ~2.5×. The defaults here are long enough for the largest rung, and the
    returned ``equilibration_drift`` — the fractional change between the first and
    second halves of the measurement window — lets the check *refuse* a rung that
    is still settling rather than quietly averaging a transient.

    Seeds are combined by **mean** here, unlike the sweep's median. The median is
    the right call for ``Var_t(r)``, whose per-seed distribution is heavy-tailed
    near criticality; ⟨r⟩ itself is well behaved, the literature's ``[⟨Δ⟩]`` is an
    average over realizations, and the mean's standard error over independent ICs
    is the error bar the exponent needs.
    """
    import numpy as np

    from .kuramoto import OMEGA_CLIP_SCALE, lorentzian_frequencies, order_parameter, rk4_step

    if clip_scale is None:
        clip_scale = OMEGA_CLIP_SCALE
    k_c = 2.0 * gamma
    omega = lorentzian_frequencies(n, gamma, clip_scale=clip_scale)
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0.0, 2.0 * np.pi, size=(seeds, n))

    for _ in range(int(round(t_burn / dt))):
        theta = rk4_step(theta, omega, k_c, dt)

    n_meas = int(round(t_measure / dt))
    half = n_meas // 2
    totals = np.zeros(seeds)
    first = np.zeros(seeds)
    second = np.zeros(seeds)
    n_first = n_second = 0
    for step in range(n_meas):
        theta = rk4_step(theta, omega, k_c, dt)
        if step % sample_every == 0:
            r, _ = order_parameter(theta)
            totals += r
            if step < half:
                first += r
                n_first += 1
            else:
                second += r
                n_second += 1
    samples = n_first + n_second
    per_seed = totals / samples
    mean = float(per_seed.mean())
    # Per-INITIAL-CONDITION half-window means. Keeping these (rather than only their
    # ensemble averages) is what lets the drift carry its own error bar: a half-to-half
    # change is only evidence of non-equilibration if it is larger than the scatter
    # between independent runs would produce on its own. Without this the check would
    # be comparing a noisy number to a bare constant and calling the difference physics.
    first_by_seed = first / max(n_first, 1)
    second_by_seed = second / max(n_second, 1)
    delta = second_by_seed - first_by_seed
    drift_sem = (
        float(delta.std(ddof=1) / math.sqrt(seeds)) if seeds > 1 else float("nan")
    )
    return {
        "n": n,
        "r_critical": mean,
        # Standard error over INDEPENDENT initial conditions — the honest bar. The
        # within-run time samples are strongly correlated near criticality and
        # would give a spuriously tiny error if used instead.
        "r_sem": float(per_seed.std(ddof=1) / math.sqrt(seeds)) if seeds > 1 else float("nan"),
        "r_by_seed": per_seed.tolist(),
        "r_first_half": float(first_by_seed.mean()),
        "r_second_half": float(second_by_seed.mean()),
        "equilibration_drift": abs(float(delta.mean())) / mean if mean > 0 else float("nan"),
        # ...and the same drift in units of its own standard error. THIS is what the
        # check grades: |Δ|/σ_Δ ≈ 1 means "indistinguishable from a settled run".
        "equilibration_drift_sigma": (
            abs(float(delta.mean())) / drift_sem
            if drift_sem and math.isfinite(drift_sem) and drift_sem > 0 else float("nan")
        ),
        "equilibration_drift_sem": drift_sem,
        "seeds": seeds,
        "dt": dt,
        "t_burn": t_burn,
        "t_measure": t_measure,
        "clip_scale": clip_scale,
        "samples": samples,
    }


def fit_critical_exponent(rungs) -> dict:
    """β/ν̄_c from ``log r(K_c) vs log N``, with an error bar that is not decorative.

    Two independent uncertainties are computed and the **larger** is reported:
    the ordinary regression standard error on the slope, and the same slope's error
    propagated from each rung's own initial-condition scatter. Quoting only the
    first would let five tidy points on a line claim a precision the underlying
    ⟨r⟩ measurements do not have.
    """
    import numpy as np

    usable = [r for r in rungs if r["r_critical"] > 0 and math.isfinite(r["r_critical"])]
    if len(usable) < 3:
        return {"exponent": float("nan"), "err": float("nan"), "r2": float("nan"),
                "points": len(usable)}
    x = np.log(np.array([r["n"] for r in usable], dtype=np.float64))
    y = np.log(np.array([r["r_critical"] for r in usable], dtype=np.float64))
    sigma_y = np.array(
        [r["r_sem"] / r["r_critical"] if r["r_critical"] > 0 else np.nan for r in usable],
    )
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    sxx = float(((x - x.mean()) ** 2).sum())
    dof = len(x) - 2
    se_regression = math.sqrt(float((resid ** 2).sum()) / dof / sxx) if dof > 0 else float("nan")
    se_propagated = (
        math.sqrt(float((((x - x.mean()) * sigma_y) ** 2).sum())) / sxx
        if np.all(np.isfinite(sigma_y)) else float("nan")
    )
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        # Reported as the POSITIVE decay exponent β/ν̄_c, matching the literature's
        # sign convention r ~ N^(−β/ν̄_c).
        "exponent": float(-slope),
        "err": float(max(se_regression, se_propagated)),
        "err_regression": float(se_regression),
        "err_propagated": float(se_propagated),
        "r2": float(1.0 - float((resid ** 2).sum()) / ss_tot) if ss_tot > 0 else float("nan"),
        "points": len(usable),
    }


def combine_over_seeds(stack):
    """Combine per-initial-condition curves into one, robustly.

    ``stack`` is ``(n_seeds, n_couplings)``. The combination is the **median** down
    the seed axis: near criticality a finite population occasionally makes a rare
    intermittent de-synchronization excursion inside the measurement window, which
    inflates that seed's ``Var_t(r)`` at one coupling by several-fold. Those draws are
    real dynamics but they make the per-seed distribution heavy-tailed, and a mean
    over a handful of heavy-tailed draws is not a location estimator — it lets one
    excursion decide where the peak is. See the module docstring for the measured case
    that forced this (N = 2000, K = 1.09·K_c, χ = 2.78 between neighbours 1.63 and
    0.52) and for why a location estimator is the right thing to want here.
    """
    import numpy as np

    return np.median(np.asarray(stack, dtype=np.float64), axis=0)


def _least_squares_line(xs, ys):
    """Plain OLS slope/intercept/R² — used for log r* vs log N."""
    import numpy as np

    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    if xs.size < 2:
        return float("nan"), float("nan"), float("nan")
    slope, intercept = np.polyfit(xs, ys, 1)
    pred = slope * xs + intercept
    ss_res = float(((ys - pred) ** 2).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum())
    return float(slope), float(intercept), (1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"))


def run_k02(
    ladder=CALIBRATION_LADDER,
    gamma: float = CALIBRATION_GAMMA,
    seeds=CALIBRATION_SEEDS,
    dt: float = DT,
    t_burn: float = T_BURN,
    t_measure: float = T_MEASURE,
    sample_every: int = SAMPLE_EVERY,
    critical_seeds: int = CRITICAL_SEEDS,
    critical_t_burn: float = CRITICAL_T_BURN,
    critical_t_measure: float = CRITICAL_T_MEASURE,
    clip_control_n: int = CLIP_CONTROL_N,
    clip_control_seeds: int = CLIP_CONTROL_SEEDS,
    clip_control_t_burn: float = CLIP_CONTROL_T_BURN,
    clip_control_t_measure: float = CLIP_CONTROL_T_MEASURE,
    progress=None,
) -> K02Result:
    """The whole milestone: the χ(r) sweep ladder, then the r(K_c, N) calibration."""
    import numpy as np

    from .kuramoto import run_sweep

    t0 = time.time()
    ladder = tuple(int(n) for n in ladder)
    seeds = tuple(int(s) for s in seeds)
    K = coupling_grid(gamma)
    k_c = 2.0 * gamma
    rungs: list[K02Rung] = []

    for rung_i, n in enumerate(ladder):
        t_rung = time.time()
        if progress is not None:
            progress("rung", rung_i, len(ladder), n)
        per_seed_r = []
        per_seed_var = []
        r_star_by_seed: list[float] = []
        for seed in seeds:
            sweep = run_sweep(
                K, n=n, gamma=gamma, dt=dt, t_burn=t_burn, t_measure=t_measure,
                sample_every=sample_every, seed=seed,
            )
            per_seed_r.append(sweep.r_mean)
            per_seed_var.append(sweep.r_var)
            # Per-seed peak, kept as evidence for the run-to-run scatter that a
            # single initial condition would otherwise report as signal.
            r_star_by_seed.append(locate_r_peak(sweep.r_mean, sweep.chi)[1])
        stack_r = np.vstack(per_seed_r)
        stack_var = np.vstack(per_seed_var)
        r_mean = combine_over_seeds(stack_r)
        r_var = combine_over_seeds(stack_var)
        chi = n * r_var
        # The mean-combined peak, carried as a visible cross-check on that choice.
        chi_mean_combined = n * stack_var.mean(axis=0)
        r_mean_combined = stack_r.mean(axis=0)
        mean_idx, r_star_mean, _, _ = locate_r_peak(r_mean_combined, chi_mean_combined)

        idx, r_star, r_star_refined, resolution = locate_r_peak(r_mean, chi)
        # The anchor against exact theory: where does χ peak in the CONTROL parameter?
        # K01 says K_c = 2γ, with nothing fitted. Re-confirmed at every rung here.
        if 0 < idx < K.size - 1:
            k_peak = parabola_vertex(K[idx - 1], chi[idx - 1], K[idx], chi[idx],
                                     K[idx + 1], chi[idx + 1])
        else:
            k_peak = float(K[idx])

        if 0 < mean_idx < K.size - 1:
            k_peak_mean = parabola_vertex(
                K[mean_idx - 1], chi_mean_combined[mean_idx - 1],
                K[mean_idx], chi_mean_combined[mean_idx],
                K[mean_idx + 1], chi_mean_combined[mean_idx + 1],
            )
        else:
            k_peak_mean = float(K[mean_idx])

        branch = K >= BRANCH_FIT_K_MIN_FACTOR * k_c
        rungs.append(K02Rung(
            n=n,
            K=K.tolist(),
            r_mean=r_mean.tolist(),
            r_var=r_var.tolist(),
            chi=chi.tolist(),
            peak_index=idx,
            r_star=r_star,
            r_star_refined=r_star_refined,
            r_resolution=resolution,
            r_star_by_seed=r_star_by_seed,
            r_star_mean_combined=r_star_mean,
            k_peak_mean_combined=k_peak_mean,
            k_peak=k_peak,
            chi_peak=float(chi[idx]),
            chi_endpoint_ratio=float(chi[idx] / max(chi[0], chi[-1])),
            r_incoherent=float(r_mean[0]),
            r_incoherent_scale=float(1.0 / math.sqrt(n)),
            fit_free=fit_beta_shape(r_mean, chi),
            fit_run01=fit_fixed_shape(r_mean, chi),
            fit_free_branch=fit_beta_shape(r_mean[branch], chi[branch]),
            fit_run01_branch=fit_fixed_shape(r_mean[branch], chi[branch]),
            wall_seconds=time.time() - t_rung,
        ))

    # ── the calibration: ⟨r⟩ at the EXACT K_c, graded against a published exponent ──
    # Deliberately a separate pass rather than a column of the sweep: it needs windows
    # an order of magnitude longer (see ``critical_coherence``), and being at a single
    # coupling it can afford them.
    critical = []
    for rung_i, n in enumerate(ladder):
        if progress is not None:
            progress("critical", rung_i, len(ladder), n)
        critical.append(critical_coherence(
            n, gamma=gamma, seeds=critical_seeds, dt=dt,
            t_burn=critical_t_burn, t_measure=critical_t_measure,
            sample_every=sample_every,
        ))

    if progress is not None:
        progress("clip-control", 0, 1, clip_control_n)
    clip_control = [
        critical_coherence(
            clip_control_n, gamma=gamma, seeds=clip_control_seeds, dt=dt,
            t_burn=clip_control_t_burn, t_measure=clip_control_t_measure,
            sample_every=sample_every,
        ),
        critical_coherence(
            clip_control_n, gamma=gamma, seeds=clip_control_seeds,
            dt=CLIP_CONTROL_ALT_DT, t_burn=clip_control_t_burn,
            t_measure=clip_control_t_measure,
            sample_every=max(1, int(sample_every * dt / CLIP_CONTROL_ALT_DT)),
            clip_scale=CLIP_CONTROL_ALT_SCALE,
        ),
    ]

    r_stars = [rung.r_star for rung in rungs]
    slope, _, fit_r2 = _least_squares_line(
        [math.log(n) for n in ladder], [math.log(v) for v in r_stars],
    )
    result = K02Result(
        rungs=rungs,
        critical=critical,
        critical_fit=fit_critical_exponent(critical),
        clip_control=clip_control,
        gamma=gamma,
        kc_exact=k_c,
        seeds=seeds,
        scaling_exponent=slope,
        scaling_r2=fit_r2,
        r_star_drift=r_stars[0] - r_stars[-1],
        is_calibration=bool(
            ladder == CALIBRATION_LADDER
            and seeds == CALIBRATION_SEEDS
            and gamma == CALIBRATION_GAMMA
            and critical_seeds == CRITICAL_SEEDS
            and critical_t_burn == CRITICAL_T_BURN
            and critical_t_measure == CRITICAL_T_MEASURE
            and clip_control_n == CLIP_CONTROL_N
            and clip_control_seeds == CLIP_CONTROL_SEEDS
            and clip_control_t_burn == CLIP_CONTROL_T_BURN
            and clip_control_t_measure == CLIP_CONTROL_T_MEASURE
        ),
        wall_seconds=time.time() - t0,
        config={
            "ladder": list(ladder), "gamma": gamma, "seeds": list(seeds),
            "dt": dt, "t_burn": t_burn, "t_measure": t_measure,
            "sample_every": sample_every, "k_points": int(K.size),
        },
    )
    if progress is not None:
        progress("done", len(ladder), len(ladder), 0)
    return result


def to_report(result: K02Result) -> dict:
    """A JSON report shaped for the page + the K02 check."""
    from .checks import check_k02

    # A SECOND, better-conditioned reading of the same question. The raw argmax is a
    # single sample of a curve that is broad in r, so it jitters by whole grid steps;
    # the free fit's own interior maximum p/(p+q) is a property of the *whole* swept
    # curve and is correspondingly steadier. It is reported alongside — never instead
    # of — the family-free argmax, because it inherits the Beta family's assumptions
    # and that family is part of what K02 is testing. Used here only as a smooth
    # interpolant for *where* the maximum sits, which a mediocre fit can still track.
    fit_peaks = [rung.fit_free["peak"] for rung in result.rungs]
    ladder_n = [rung.n for rung in result.rungs]
    usable = [
        (n, p) for n, p in zip(ladder_n, fit_peaks)
        if isinstance(p, float) and math.isfinite(p) and p > 0
    ]
    if len(usable) >= 2:
        fit_slope, _, fit_peak_r2 = _least_squares_line(
            [math.log(n) for n, _ in usable], [math.log(p) for _, p in usable],
        )
    else:
        fit_slope, fit_peak_r2 = float("nan"), float("nan")
    fit_peak_monotone = all(a > b for a, b in zip(fit_peaks, fit_peaks[1:]))

    report = {
        # ── the calibration (the headline) ──
        "critical": result.critical,
        "critical_fit": result.critical_fit,
        "clip_control": result.clip_control,
        "critical_exponent_published": CRITICAL_EXPONENT_PUBLISHED,
        "critical_exponent_published_err": CRITICAL_EXPONENT_PUBLISHED_ERR,
        "critical_exponent_asymptotic": CRITICAL_EXPONENT_ASYMPTOTIC,
        "critical_exponent_random_sampling": CRITICAL_EXPONENT_RANDOM_SAMPLING,
        # ── the DEMOTED estimator: kept as a documented property of a misspecified
        # fit, NOT as evidence for a scaling exponent. See the module docstring.
        "fit_peak_ladder": fit_peaks,
        "fit_peak_exponent": fit_slope,
        "fit_peak_r2": fit_peak_r2,
        "fit_peak_monotone_decreasing": fit_peak_monotone,
        "fit_peak_is_demoted": True,
        "fit_peak_demotion_reason": (
            "p/(p+q) is a ratio of two parameters that themselves track N inside a "
            "family that does not fit the data (free-fit R² 0.73–0.82), so its "
            "N-dependence compounds the physics with the family's misfit drift. "
            "Reported as a property of the fit; NOT a scaling exponent. The "
            "literature-comparable measurement is the 'critical' block above."
        ),
        "experiment": "K02-coherence-susceptibility-shape",
        "gamma": result.gamma,
        "kc_exact": result.kc_exact,
        "ladder": [rung.n for rung in result.rungs],
        "seeds": list(result.seeds),
        "run01_p": RUN01_P,
        "run01_q": RUN01_Q,
        "run01_r_star": RUN01_R_STAR,
        "scaling_exponent": result.scaling_exponent,
        "scaling_r2": result.scaling_r2,
        "r_star_drift": result.r_star_drift,
        "is_calibration": result.is_calibration,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
        "rungs": [
            {
                "n": rung.n,
                "K": rung.K,
                "r_mean": rung.r_mean,
                "r_var": rung.r_var,
                "chi": rung.chi,
                "peak_index": rung.peak_index,
                "r_star": rung.r_star,
                "r_star_refined": rung.r_star_refined,
                "r_resolution": rung.r_resolution,
                "r_star_by_seed": rung.r_star_by_seed,
                "r_star_mean_combined": rung.r_star_mean_combined,
                "k_peak_mean_combined": rung.k_peak_mean_combined,
                "k_peak": rung.k_peak,
                "chi_peak": rung.chi_peak,
                "chi_endpoint_ratio": rung.chi_endpoint_ratio,
                "r_incoherent": rung.r_incoherent,
                "r_incoherent_scale": rung.r_incoherent_scale,
                "fit_free": rung.fit_free,
                "fit_run01": rung.fit_run01,
                "fit_free_branch": rung.fit_free_branch,
                "fit_run01_branch": rung.fit_run01_branch,
                "wall_seconds": rung.wall_seconds,
            }
            for rung in result.rungs
        ],
    }
    first, last = result.rungs[0], result.rungs[-1]
    worst_run01_r2 = max(rung.fit_run01["r2"] for rung in result.rungs)
    cf = result.critical_fit or {}
    report["headline"] = (
        f"Coherence at the exact K_c decays as r ~ N^−{cf.get('exponent', float('nan')):.3f}"
        f"±{cf.get('err', float('nan')):.3f} over N={first.n}→{last.n}, against the "
        f"published β/ν̄_c = {CRITICAL_EXPONENT_PUBLISHED}({int(CRITICAL_EXPONENT_PUBLISHED_ERR*100)}) "
        f"for this exact regular-Lorentzian configuration (Hong et al. 2015 Eq. 4.3) — "
        f"so no N-independent χ(r) peak can exist, and Run 01's pinned a·r²(1−r)³ "
        f"scores R² ≤ {worst_run01_r2:.2f}, worse than a flat line, at every N · "
        f"{result.wall_seconds:.0f}s"
    )
    passed, _ = check_k02(report)
    report["status"] = "pass" if passed else "null"
    report["claim_boundary"] = (
        "This milestone claims NO novelty about the Kuramoto model. Its engine is a "
        "published configuration verbatim (the regular Lorentzian of Hong et al. 2015 "
        "§IV A), its estimator is standard, and the finite-size decay it measures is a "
        "known result — so the headline is a CALIBRATION against β/ν̄_c = 0.39(2), not a "
        "discovery. Graded: that measured exponent against the published one; an interior "
        "χ maximum in r at every rung; r* sitting more than its own floor from Run 01's "
        "2/5, in either direction; equilibration at every rung; and the K=0 negative "
        "control. Everything else is reported, not graded. Three boundaries stated out "
        "loud. (1) The χ peak's position in K is UNRESOLVED from K_c here — the "
        "literature has it sitting subcritical and drifting as N^(−1/ν̄'), and this "
        "ladder's ±0.024 scatter cannot see that; the mechanism argument only needs the "
        "peak to be asymptotically at K_c, which it is. (2) The ladder tops out at "
        "N = 4000 = 2^12, deep in the pre-asymptotic regime where the effective exponent "
        "is ≈0.37–0.39; Park & Park 2024 show the true asymptote 0.325(15) is reached "
        "only for N ≳ 2^15. (3) This is the DETERMINISTIC model with Lorentzian tails "
        "clipped at |ω| ≤ 40γ — a deviation from the unclipped published configuration, "
        "checked by a negative control but not eliminated; Run 01's fit came from a NOISY "
        "(D = 0.20) system at N = 24. No claim is made that any other Beta-family "
        "exponent pair is the true shape — only that the published (2, 3) with its "
        "N-independent r* = 2/5 is not reproduced here. NOTE: Run 01's r* = 2/5 (a "
        "coherence) and β/ν̄ = 0.39 ≈ 2/5 (an exponent) are unrelated quantities that "
        "happen to coincide numerically."
    )
    return report
