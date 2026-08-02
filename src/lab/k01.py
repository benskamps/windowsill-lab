"""K01 — the Kuramoto synchronization transition, calibrated against K_c = 2γ.

The K track opens the same way the M track did. M01 pointed the lattice engine at
the one 2D Ising number that is known exactly — Onsager's T_c = 2.2692 — and asked
whether the instrument could find it at all. K01 does that for **coherence**: N
oscillators, each with its own natural frequency, each pulled toward the crowd's
mean phase, and one exactly-known threshold where they stop ignoring each other.

For natural frequencies drawn from a Lorentzian of half-width γ, Kuramoto's
mean-field theory is exactly solvable as N → ∞ and gives

    K_c = 2 / (π · g(0)) = 2γ                            (the transition)
    r(K) = √(1 − K_c/K)   for K > K_c                    (the whole ordered branch)

At the shipped γ = 0.5 that is **K_c = 1.0** — the number this milestone has to
reproduce from a finite population that knows nothing about the formula.

### The estimator (primary), and why

The **primary** estimator is the peak of the susceptibility-style fluctuation

    χ(K) = N · Var_t(r)

time-averaged over the measurement window and located with the *same* 3-point
parabola refinement ``m06.refine_peak`` uses for the χ peak of an Ising sweep. The
K track therefore locates its transition with the estimator the M track already
trusts (M04/M05/M06 all grade a refined χ peak), rather than inventing one. Below
K_c the crowd is scattered and r wobbles around its 1/√N floor; above K_c a locked
core pins r; *at* the transition the coherence is maximally soft and its
fluctuation spikes. On the shipped sweep χ rises smoothly to a single sharp spike
2× its neighbours and falls away — one unambiguous peak.

A **cross-check** estimator is carried but not graded: the coupling at which
⟨r⟩(K) rises fastest (``steepest_slope_crossing``). It reads a different feature of
the same sweep, but it is grid-limited in a way the fluctuation peak is not —
r(K) = √(1 − K_c/K) has *infinite* slope at K_c⁺, so a central difference on a
finite grid can never place it better than one grid step above the transition
(measured: 1.068 against 1.000, i.e. ≈ 0.8·ΔK high, at every N and seed tried).
That is a documented property of the estimator, not a defect of the run, which is
exactly why it is the cross-check and the fluctuation peak is the headline.

### The stronger anchor: a curve, not a point

Locating one peak is the weaker half of this milestone. The **ordered branch**
r(K) = √(1 − K_c/K) is a closed form with nothing fitted, so the run is also
graded against the whole curve for K ≥ 1.5·K_c — the same role random deposition's
exact ``w² = p(1−p)t`` plays in M17, and the Nishimori-line energy identity plays
in M14. A pipeline that manufactured a plausible-looking transition would still
have to reproduce seven independent coherence values it never fitted; the shipped
run matches them to **1.5 × 10⁻⁴**.

A third, negative-control gate closes the loop at the other end: at K = 0 there is
no coupling at all, so the measured coherence must be nothing but the random-walk
centroid of N scattered phases, r ≈ 1/√N. A frequency draw that collapsed (all ω
equal) would order at K = 0 and is caught here before any peak is fitted.

### The honest boundary (finite N, finite grid)

The exact K_c = 2γ is an N → ∞ statement, and the sweep is a finite grid. Both
systematics were *measured* before the tolerance was declared, not assumed:

    N =  250  →  K_c = 1.0504   (+0.050)
    N =  500  →  K_c = 1.0256   (+0.026)
    N = 1000  →  K_c = 1.0083   (+0.008)
    N = 2000  →  K_c = 1.0007   (+0.001)   ← shipped
    N = 2000, a different initial condition  →  0.9910  (−0.009)

The finite-N estimate approaches 2γ from above and is within a percent by N = 2000,
where the run-to-run scatter from the initial condition (±0.01) has overtaken it.
The floor under both is the sweep's own resolution: ΔK = 4γ/24 = γ/6 = 0.0833, and
no peak refinement recovers more than a fraction of one grid step. The declared
tolerance in ``checks.py`` is therefore set by the **grid**, not by the lucky
agreement of the shipped run — see ``KURAMOTO_KC_TOL`` there for the arithmetic.
This is the same posture M01 takes when it reports 2.300 against an exact 2.2692:
the finite instrument's answer, with the reason it differs stated out loud.

Integration is fixed-step RK4 at dt = 0.02, cross-checked against dt = 0.01: the
two agree on the graded peak to four decimals (1.0007 both), so the reported number
is a property of the model and not of the integrator.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

# ── the fixed K01 calibration identity ───────────────────────────────────────
# K01 is ONE calibration, not a caller-selected amount of easy work. These four
# facts define it; ``checks.check_k01`` re-derives them and refuses to grade a run
# that changed any of them (the same identity gate check_c01 puts on its 40-term
# OEIS prefix). A smaller/cheaper run is still useful as a diagnostic — it just
# isn't this calibration, and says so.
CALIBRATION_GAMMA = 0.5          # Lorentzian half-width ⇒ exact K_c = 2γ = 1.0
CALIBRATION_N = 2000             # oscillators
CALIBRATION_POINTS = 25          # couplings swept
CALIBRATION_K_MAX_OVER_GAMMA = 4.0   # sweep spans K ∈ [0, 4γ], straddling K_c = 2γ

# Where the exact ordered branch is graded. Close above K_c the finite-N curve is
# still rounding the transition's corner, so the closed form is compared only where
# it is genuinely asymptotic — K ≥ 1.5·K_c.
BRANCH_K_MIN_FACTOR = 1.5


@dataclass
class K01Result:
    K: list
    r_mean: list
    r_var: list
    chi: list
    mean_field_r: list
    n: int
    gamma: float
    kc_exact: float             # 2γ — the exact infinite-N mean-field answer
    kc_chi_peak: float          # HEADLINE: refined peak of N·Var(r)
    kc_slope_crossing: float    # cross-check: steepest rise of ⟨r⟩(K), grid-limited
    rel_error: float            # |kc_chi_peak − 2γ| / 2γ
    branch_points: int          # couplings graded against the closed form
    branch_max_dev: float       # max |⟨r⟩ − √(1−K_c/K)| over those couplings
    r_incoherent: float         # ⟨r⟩ at K=0 — should be the 1/√N random-walk floor
    r_incoherent_scale: float   # 1/√N
    n_samples: int
    dt: float
    t_burn: float
    t_measure: float
    seed: int
    is_calibration: bool        # the fixed identity above was run unchanged
    wall_seconds: float
    config: dict


def run_k01(
    n: int = CALIBRATION_N,
    gamma: float = CALIBRATION_GAMMA,
    n_points: int = CALIBRATION_POINTS,
    k_max_over_gamma: float = CALIBRATION_K_MAX_OVER_GAMMA,
    dt: float = 0.02,
    t_burn: float = 100.0,
    t_measure: float = 300.0,
    sample_every: int = 10,
    seed: int = 42,
    progress=None,
) -> K01Result:
    """Sweep the coupling across the transition and locate K_c from the finite-N data.

    Mirrors ``run_m04``: one batched sweep straddling the exact critical point,
    wall-clock timing, an optional ``progress`` callback, and a ``to_report``-ready
    result. Every coupling is integrated simultaneously from the same initial
    condition, so the only difference between points in the sweep is K.
    """
    import numpy as np

    from .kuramoto import (
        critical_coupling, mean_field_r, refine_peak, run_sweep,
        steepest_slope_crossing,
    )

    t0 = time.time()
    k_c = critical_coupling(gamma)
    K = np.linspace(0.0, k_max_over_gamma * gamma, n_points)
    sweep = run_sweep(
        K, n=n, gamma=gamma, dt=dt, t_burn=t_burn, t_measure=t_measure,
        sample_every=sample_every, seed=seed, progress=progress,
    )

    kc_peak = refine_peak(sweep.K, sweep.chi)
    kc_slope = steepest_slope_crossing(sweep.K, sweep.r_mean)
    branch = mean_field_r(sweep.K, gamma)
    graded = sweep.K >= BRANCH_K_MIN_FACTOR * k_c
    dev = np.abs(sweep.r_mean[graded] - branch[graded])

    result = K01Result(
        K=sweep.K.tolist(),
        r_mean=sweep.r_mean.tolist(),
        r_var=sweep.r_var.tolist(),
        chi=sweep.chi.tolist(),
        mean_field_r=branch.tolist(),
        n=n,
        gamma=gamma,
        kc_exact=k_c,
        kc_chi_peak=kc_peak,
        kc_slope_crossing=kc_slope,
        rel_error=abs(kc_peak - k_c) / k_c,
        branch_points=int(graded.sum()),
        branch_max_dev=float(dev.max()) if dev.size else float("nan"),
        r_incoherent=float(sweep.r_mean[0]),
        r_incoherent_scale=float(1.0 / np.sqrt(n)),
        n_samples=sweep.n_samples,
        dt=dt,
        t_burn=t_burn,
        t_measure=t_measure,
        seed=seed,
        # A run that changed the fixed identity is a diagnostic, not this
        # calibration — the same rule C01 applies to a short OEIS prefix.
        is_calibration=bool(
            n == CALIBRATION_N
            and gamma == CALIBRATION_GAMMA
            and n_points == CALIBRATION_POINTS
            and k_max_over_gamma == CALIBRATION_K_MAX_OVER_GAMMA
        ),
        wall_seconds=time.time() - t0,
        config={
            "n": n, "gamma": gamma, "n_points": n_points,
            "k_max_over_gamma": k_max_over_gamma, "dt": dt,
            "t_burn": t_burn, "t_measure": t_measure,
            "sample_every": sample_every, "seed": seed,
        },
    )
    if progress is not None:
        progress("done", 1, 1)
    return result


def to_report(result: K01Result) -> dict:
    """A JSON report shaped for the page + the K01 check.

    Distinct ``experiment`` tag so no M-track check claims it, with the per-K
    arrays ``check_k01`` re-derives every graded number from. ``status`` is the
    honest verdict the renderer paints: the identity, the peak, the closed-form
    branch, and the incoherent floor all have to hold.
    """
    from .checks import check_k01

    report = {
        "experiment": "K01-kuramoto-synchronization",
        "K": result.K,
        "r_mean": result.r_mean,
        "r_var": result.r_var,
        "chi": result.chi,
        "mean_field_r": result.mean_field_r,
        "n": result.n,
        "gamma": result.gamma,
        "kc_exact": result.kc_exact,
        "kc_chi_peak": result.kc_chi_peak,
        "kc_slope_crossing": result.kc_slope_crossing,
        "rel_error": result.rel_error,
        "branch_k_min_factor": BRANCH_K_MIN_FACTOR,
        "branch_points": result.branch_points,
        "branch_max_dev": result.branch_max_dev,
        "r_incoherent": result.r_incoherent,
        "r_incoherent_scale": result.r_incoherent_scale,
        "n_samples": result.n_samples,
        "dt": result.dt,
        "t_burn": result.t_burn,
        "t_measure": result.t_measure,
        "seed": result.seed,
        "is_calibration": result.is_calibration,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
    report["headline"] = (
        f"Kuramoto synchronization (N={result.n}, γ={result.gamma}): "
        f"χ=N·Var(r) peaks at K_c={result.kc_chi_peak:.4f} vs exact 2γ="
        f"{result.kc_exact:.4f} (rel. err {result.rel_error*100:.1f}%); "
        f"ordered branch √(1−K_c/K) matched to {result.branch_max_dev:.1e} "
        f"over {result.branch_points} couplings · {result.wall_seconds:.0f}s"
    )
    # The verdict is the CHECK's, not the runner's: one gate, graded once, so the
    # page and the CI receipt can never disagree about whether K01 passed.
    passed, _ = check_k01(report)
    report["status"] = "pass" if passed else "null"
    report["claim_boundary"] = (
        "A finite population of 2000 oscillators on a 25-point coupling grid locates the "
        "mean-field synchronization threshold; the exact K_c = 2γ is an N → ∞ result and "
        "the grid resolves K only to ΔK = γ/6, so this is a calibrated finite-N estimate, "
        "not a precision measurement of K_c. No claim is made about the critical exponents "
        "of the transition or about non-Lorentzian frequency distributions."
    )
    return report
