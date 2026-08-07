"""M18 — directed percolation in 2+1d at the absorbing-state transition.

The lab's first milestone on a **non-equilibrium** phase transition of the
absorbing-state kind, and the fourth Phase-4 rung. Everything up to M17 relaxed
toward an equilibrium the dynamics could always leave again; here the all-zero
state is a trap with no way out, and the transition is between "activity
survives forever" and "activity dies", not between two thermodynamic phases.

### The claim, and the shape of the evidence

At the critical transmission probability the density decays as a pure power law

    rho(t) ~ t^(−delta),   delta = beta / nu_parallel = **0.4505** in (2+1)d

(Hinrichsen 2000, Adv. Phys. 49, 815). Above the upper critical dimension
d_c = 4 the mean-field answer delta = 1 takes over, so this measurement has to
land on 0.4505 and *not* on 1 — excluding mean-field is a graded claim here, not
a footnote, because it is the difference between measuring a universality class
and measuring the fact that something decreases.

### Why this brackets rather than quoting a single number

delta_eff(t) = −dln rho/dln t is **monotonically decreasing in p**. A subcritical
run curves upward without bound; a supercritical run bends over toward zero. So a
pair of runs that straddle p_c *bounds* the true exponent between their curves,
and the graded statement becomes "the bracket contains 0.4505 and excludes 1.0" —
a claim a finite lattice can actually support. Quoting delta at one p instead
would need p_c to more digits than this box can resolve, and would quietly turn
an unresolved p_c into a fitted knob. p_c is reported as a *measurement* (the
bracket midpoint, with the bracket as its uncertainty), never taken from a table.

### The controls, and what each one would catch

1. **Deep subcritical (p ≪ p_c)** — decay must be exponential, not power law, and
   the check compares the two fits head to head. This catches the pipeline's most
   likely lie: calling any falling curve a critical power law.
2. **Deep supercritical (p ≫ p_c)** — density must saturate to a finite plateau,
   delta_eff → 0. The other side of the same trap.
3. **The absorbing state must absorb** — from an all-zero lattice, at p = 0.9,
   nothing may ever switch on. A sign slip or an off-by-one in the parent count
   would let activity appear from nothing, and every exponent above it would
   describe a different model than the one claimed.
4. **Finite-size headroom** — xi_perp ~ t^(1/z) with z = 1.766 must stay well
   inside L for the whole window, or the measurement is reading the box.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import dp

#: Bracket endpoints, from a p-scan on this engine (2026-08-07). They are the
#: measurement's INPUT, not its answer: the run re-proves they straddle p_c by
#: checking their curvatures have opposite sign, and refuses if they do not.
P_LOW_DEFAULT = 0.22410
P_HIGH_DEFAULT = 0.22420

#: Controls, deliberately far from p_c so their behaviour is unambiguous.
P_DEEP_SUB = 0.15
P_DEEP_SUPER = 0.32

L_DEFAULT = 2048
BATCH_DEFAULT = 4
T_MAX_DEFAULT = 50_000

#: Primary fit window. Late enough that the initial transient is gone, early
#: enough that rho is still large enough to differentiate cleanly.
FIT_LO, FIT_HI = 1_000, 5_000

#: The bracket must be tight enough to mean something. A bracket spanning
#: [0, 2] would "contain 0.4505" and say nothing.
MAX_BRACKET_WIDTH = 0.30

#: Correlation length must fit in the box this many times over.
MIN_HEADROOM = 2.0


@dataclass
class M18Result:
    p_low: float
    p_high: float
    delta_low_p: float          # delta measured at p_low  (the UPPER bound)
    delta_high_p: float         # delta measured at p_high (the LOWER bound)
    r2_low_p: float
    r2_high_p: float
    curvature_low_p: float
    curvature_high_p: float
    straddles: bool
    bracket: tuple[float, float]
    bracket_width: float
    contains_dp: bool
    excludes_mean_field: bool
    p_c_estimate: float
    p_c_uncertainty: float
    headroom: float
    windows: list[dict] = field(default_factory=list)
    controls: dict = field(default_factory=dict)
    calibration_passed: bool = False
    device: str = "cuda"
    L: int = L_DEFAULT
    batch: int = BATCH_DEFAULT
    t_max: int = T_MAX_DEFAULT
    wall_seconds: float = 0.0


def _windows(run_lo: dp.DecayRun, run_hi: dp.DecayRun) -> list[dict]:
    """Report the bracket over several windows; only FIT_LO..FIT_HI is graded."""
    out = []
    for lo, hi in ((FIT_LO, FIT_HI), (5_000, 20_000), (10_000, 50_000)):
        if hi > run_lo.t_max:
            continue
        d_lo, r_lo, n_lo = dp.fit_exponent(run_lo.rho, lo, hi)
        d_hi, r_hi, n_hi = dp.fit_exponent(run_hi.rho, lo, hi)
        out.append({
            "t_lo": lo, "t_hi": hi,
            "delta_at_p_low": d_lo, "delta_at_p_high": d_hi,
            "r2_at_p_low": r_lo, "r2_at_p_high": r_hi,
            "bracket": [d_hi, d_lo],
            "contains_dp": bool(d_hi <= dp.DELTA_DP_2P1 <= d_lo),
            "graded": lo == FIT_LO and hi == FIT_HI,
            "points": min(n_lo, n_hi),
        })
    return out


def run_controls(L: int, batch: int, t_max: int, device: str,
                 seed: int, progress=None) -> dict:
    """The three controls that make the headline number worth reading."""
    # Cheaper than the headline runs: these are qualitative, not exponent-grade.
    cl, ct = max(L // 4, 128), max(t_max // 25, 500)

    if progress:
        progress("deep-subcritical")
    sub = dp.run_decay(P_DEEP_SUB, L=cl, batch=batch, t_max=ct,
                       device=device, seed=seed + 1)
    sub_pow_delta, sub_pow_r2, _ = dp.fit_exponent(sub.rho, 8, min(200, ct))
    sub_exp_r2 = dp.exponential_decay_quality(sub.rho, 8, min(200, ct))

    if progress:
        progress("deep-supercritical")
    sup = dp.run_decay(P_DEEP_SUPER, L=cl, batch=batch, t_max=ct,
                       device=device, seed=seed + 2)
    sup_delta_eff = dp.effective_exponent(sup.rho, ct)
    sup_plateau = sup.rho[-1]

    if progress:
        progress("absorbing-state")
    absorbing = dp.absorbing_state_holds(device=device, seed=seed + 3)

    return {
        "deep_subcritical": {
            "p": P_DEEP_SUB,
            "absorbed_at": sub.absorbed_at,
            "power_law_r2": sub_pow_r2,
            "power_law_delta": sub_pow_delta,
            "exponential_r2": sub_exp_r2,
            # exponential must describe it BETTER than a power law
            "passed": bool(sub.absorbed_at is not None
                           and sub_exp_r2 > sub_pow_r2),
        },
        "deep_supercritical": {
            "p": P_DEEP_SUPER,
            "plateau_density": sup_plateau,
            "delta_eff": sup_delta_eff,
            "passed": bool(sup_plateau > 0.05 and abs(sup_delta_eff) < 0.05),
        },
        "absorbing_state": {
            "p": 0.9,
            "stayed_empty": absorbing,
            "passed": bool(absorbing),
        },
    }


def run_m18(p_low: float = P_LOW_DEFAULT, p_high: float = P_HIGH_DEFAULT,
            L: int = L_DEFAULT, batch: int = BATCH_DEFAULT,
            t_max: int = T_MAX_DEFAULT, device: str = "cuda",
            seed: int = 2026, progress=None, phase=None) -> M18Result:
    t0 = time.time()

    if phase:
        phase("bracket-low", {"p": p_low})
    run_lo = dp.run_decay(p_low, L=L, batch=batch, t_max=t_max,
                          device=device, seed=seed, progress=progress)
    if phase:
        phase("bracket-high", {"p": p_high})
    run_hi = dp.run_decay(p_high, L=L, batch=batch, t_max=t_max,
                          device=device, seed=seed, progress=progress)

    d_lo, r2_lo, _ = dp.fit_exponent(run_lo.rho, FIT_LO, FIT_HI)
    d_hi, r2_hi, _ = dp.fit_exponent(run_hi.rho, FIT_LO, FIT_HI)
    c_lo = dp.curvature(run_lo.rho, t_max)
    c_hi = dp.curvature(run_hi.rho, t_max)

    # A real straddle: the low-p run still curving UP, the high-p run bending
    # over. Without this the "bracket" is two runs on the same side of p_c.
    straddles = bool(c_lo > 0.0 > c_hi)
    bracket = (d_hi, d_lo)
    width = d_lo - d_hi
    contains = bool(d_hi <= dp.DELTA_DP_2P1 <= d_lo)
    excludes_mf = bool(d_lo < dp.DELTA_MEAN_FIELD)

    if phase:
        phase("controls", {})
    controls = run_controls(L, batch, t_max, device, seed,
                            progress=(lambda n: phase("control", {"name": n})) if phase else None)

    headroom = run_lo.finite_size_headroom
    passed = bool(
        straddles
        and contains
        and excludes_mf
        and 0.0 < width <= MAX_BRACKET_WIDTH
        and headroom >= MIN_HEADROOM
        and all(c["passed"] for c in controls.values())
    )

    return M18Result(
        p_low=p_low, p_high=p_high,
        delta_low_p=d_lo, delta_high_p=d_hi,
        r2_low_p=r2_lo, r2_high_p=r2_hi,
        curvature_low_p=c_lo, curvature_high_p=c_hi,
        straddles=straddles, bracket=bracket, bracket_width=width,
        contains_dp=contains, excludes_mean_field=excludes_mf,
        p_c_estimate=0.5 * (p_low + p_high),
        p_c_uncertainty=0.5 * (p_high - p_low),
        headroom=headroom,
        windows=_windows(run_lo, run_hi),
        controls=controls,
        calibration_passed=passed,
        device=device, L=L, batch=batch, t_max=t_max,
        wall_seconds=time.time() - t0,
    )


def to_report(r: M18Result) -> dict:
    return {
        "experiment": "M18-directed-percolation-2plus1d",
        "headline": (
            f"2+1d DP: delta bracketed to [{r.bracket[0]:.4f}, {r.bracket[1]:.4f}] "
            f"around p_c = {r.p_c_estimate:.5f}±{r.p_c_uncertainty:.5f}; "
            + ("contains the DP value 0.4505 and excludes mean-field 1.0"
               if r.contains_dp and r.excludes_mean_field
               else "does NOT bracket the DP value")
        ),
        "status": "pass" if r.calibration_passed else "null",
        "model": "synchronous PCA, 5 parents (self + 4 NN), P(active) = 1-(1-p)^n",
        "benchmark_delta": dp.DELTA_DP_2P1,
        "benchmark_source": "Hinrichsen 2000, Adv. Phys. 49, 815 (beta=0.583(4), nu_par=1.295(6))",
        "mean_field_delta": dp.DELTA_MEAN_FIELD,
        "p_low": r.p_low, "p_high": r.p_high,
        "delta_at_p_low": r.delta_low_p, "delta_at_p_high": r.delta_high_p,
        "r2_at_p_low": r2_or_nan(r.r2_low_p), "r2_at_p_high": r2_or_nan(r.r2_high_p),
        "curvature_at_p_low": r.curvature_low_p,
        "curvature_at_p_high": r.curvature_high_p,
        "straddles_pc": r.straddles,
        "bracket": list(r.bracket),
        "bracket_width": r.bracket_width,
        "max_bracket_width": MAX_BRACKET_WIDTH,
        "contains_dp_value": r.contains_dp,
        "excludes_mean_field": r.excludes_mean_field,
        "p_c_estimate": r.p_c_estimate,
        "p_c_uncertainty": r.p_c_uncertainty,
        "finite_size_headroom": r.headroom,
        "min_headroom": MIN_HEADROOM,
        "fit_window": [FIT_LO, FIT_HI],
        "windows": r.windows,
        "controls": r.controls,
        "calibration_passed": r.calibration_passed,
        "lattice": {"L": r.L, "batch": r.batch, "t_max": r.t_max,
                    "device": r.device, "sites": r.batch * r.L * r.L},
        "wall_seconds": r.wall_seconds,
        "claim_boundary": (
            "This brackets the (2+1)d DP density-decay exponent between a "
            "subcritical and a supercritical run and locates p_c to the width of "
            "that bracket; it is NOT a precision determination of either. p_c is a "
            "property of THIS transmission rule (5 parents, synchronous update), "
            "not a universal number, so only delta is compared to the literature. "
            "One lattice size is used, so no finite-size-scaling collapse is "
            "claimed — the finite-size guard is headroom (xi_perp stays inside L), "
            "not an extrapolation."
        ),
    }


def r2_or_nan(x: float) -> float:
    return x if x == x else None
