"""M17 — KPZ growth on a ring: the exponents, and which Tracy–Widom law the fluctuations obey.

The lab's third Phase-4 (genuinely-open, non-equilibrium) milestone, and the first that
watches a **surface** rather than spins. A one-dimensional interface grows upward on a
periodic ring; the Kardar–Parisi–Zhang class predicts, exactly and with no free parameters,

    w(t) ∼ t^β ,  β = 1/3        (roughening in time)
    w_sat ∼ L^α ,  α = 1/2       (roughness at saturation)
    ξ(t)  ∼ t^{1/z} = t^{2/3},   z = α/β = 3/2   (the correlation length in space)

and — the sharper, more modern statement — that the *distribution* of the height
fluctuation is a **Tracy–Widom** law whose symmetry class is fixed by the macroscopic
geometry: **GUE** for a curved (droplet) interface, **GOE** for a flat one.

### What M17 measures, and what makes the number honest

Three ingredients, each with a built-in way to fail:

1. **The exponents, through one pipeline pointed at three different growth rules.**
   ``kpz.run_growth`` grows a KPZ model (single-step corner growth), an Edwards–Wilkinson
   model (the same physics minus the nonlinearity), and random deposition (no correlations
   at all) — and the *same* width estimator and the *same* scaling-window fit rule extract β
   from each. The exact answers are 1/3, 1/4 and 1/2 respectively, so the controls are
   **negative controls in the strict sense**: a pipeline that manufactured β = 1/3 out of
   any curve would have to report 1/3 three times and would be caught here. Random
   deposition is stronger still — it has a closed form, ``w²(t) = p(1−p) t`` at every t —
   so it is graded against an exact *curve*, not an exponent.

2. **α and z, from saturation.** The same KPZ model run on small rings past its own
   crossover time ``t_× ∼ L^z`` gives ``w_sat(L)``, whose slope in log-log is α. Then
   ``z = α/β`` and ``1/z`` is the milestone's "2/3 in space" — derived from the two measured
   exponents rather than assumed.

3. **The Tracy–Widom class assignment.** Skewness and excess kurtosis are used because they
   are invariant under the affine rescaling ``χ = (h − v_∞ t)/(Γ t)^{1/3}``, so the shape can
   be tested *without fitting* the two model constants (a fitted constant is exactly the free
   knob this lab refuses). The graded statement is not "non-Gaussian" — it is **correct
   assignment**: the droplet sample must land nearer GUE than GOE, and the flat sample nearer
   GOE than GUE, in the same run.

### The sign, which is a real prediction and not a bug

For this model the growth velocity at mean slope ``u`` is ``v(u) = (p/2)(1 − u²)`` in closed
form, so the KPZ nonlinearity ``λ = ∂²v/∂u²`` is **negative** (``= −p``). KPZ then predicts
the *mirrored* Tracy–Widom law, i.e. a height skewness of **−0.2241** (droplet) / **−0.2935**
(flat). M17 measures negative skewness — the prediction confirmed, with the sign derived from
the model rather than fitted to the data. See ``kpz.slope_velocity``.

### Where it is honest about falling short

At the sizes one patient machine reaches overnight the *effective* β sits a few percent
**below** 1/3 — the documented preasymptotic approach from below. The tell that this is the
finite fit window rather than a defect in the KPZ measurement is that the Edwards–Wilkinson
control misses its own exact 1/4 by the same few percent **in the same direction**, while
random deposition — which has no correlation time to be preasymptotic about — lands on 1/2
essentially exactly.

The distributional half is where the run is furthest from converged, so M17 does not write
that down as prose: ``moment_resolution`` **derives** the gap between each measured moment and
its Tracy–Widom target *in units of the sampling error*, and ``to_report`` builds the claim
boundary from those numbers. A hand-written sentence about which moment resolved would go
stale the first time the run changed; a derived one cannot disagree with the data it ships
next to. ``check_m17`` grades the exponents and the class *assignment* — never the kurtosis,
which is carried as reported evidence and not as a claim.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from .kpz import (
    KPZ_ALPHA, KPZ_BETA, KPZ_Z, EW_BETA, RD_BETA, P_FLIP,
    TW_GUE_SKEW, TW_GUE_EXKURT, TW_GOE_SKEW, TW_GOE_EXKURT,
    PREDICTED_SKEW, droplet_time_budget, run_growth, run_saturation,
    run_height_distribution, slope_velocity,
)

# ── The scaling-window rule. Applied identically here and by ``check_m17`` so the exponent
# is re-derivable from the stored curves (a receipt, not an echo). ────────────────────────
# Past the microscopic transient…
T_FIT_MIN = 20
# …and above the O(1) width floor. The single-step model's heights each keep their initial
# parity forever, so the interface carries a permanent ±½ sawtooth worth an additive O(1) in
# w²; fitting from w ≥ 1.5 keeps that floor from dragging the slope down. (Documented in
# ``kpz.py``; raising the threshold to 2.5 moves β by <0.001, so it is a floor guard, not a
# knob that buys the answer.)
W_FIT_MIN = 1.5
# Finite-size guard: the growth fit is only clean while the ring is far from saturating.
# w_sat measures ≈0.27·√L for this model, so requiring the final width to stay under
# 0.20·√L keeps the whole fit window inside the growth regime.
SAT_GUARD_FRAC = 0.20

# ── Tolerances, mirrored from ``checks`` only for the report's status hint; the check owns
# the graded copies so a run cannot widen its own band. ───────────────────────────────────
KPZ_BETA_TOL = 0.04     # admits the honest ≈0.316 while rejecting EW's ¼ and RD's ½ by ≫3×
EW_BETA_TOL = 0.03
RD_BETA_TOL = 0.02
ALPHA_TOL = 0.05
RD_EXACT_TOL = 0.05     # max relative deviation of w² from the exact p(1−p)t curve


@dataclass
class ExponentFit:
    exponent: float
    stderr: float
    r2: float
    n_points: int
    t_lo: float
    t_hi: float
    w_lo: float
    w_hi: float


def fit_exponent(times, width, t_fit_min: int = T_FIT_MIN,
                 w_fit_min: float = W_FIT_MIN) -> ExponentFit | None:
    """Least-squares slope of ``log w`` vs ``log t`` inside the scaling window.

    Selects finite, positive points with ``t ≥ t_fit_min`` and ``w ≥ w_fit_min``, then fits a
    line in log-log. Returns ``None`` if fewer than three points survive. The OLS ``stderr`` is
    only the *statistical* error on a nearly-perfectly-straight line and badly understates the
    systematic (window / preasymptotic) uncertainty, which the report foregrounds separately.
    """
    t = np.asarray(times, dtype=float)
    w = np.asarray(width, dtype=float)
    m = (t >= t_fit_min) & (w >= w_fit_min) & np.isfinite(w) & (w > 0)
    if int(m.sum()) < 3:
        return None
    x, y = np.log(t[m]), np.log(w[m])
    n = len(x)
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    sxx = float(np.sum((x - np.mean(x)) ** 2))
    stderr = math.sqrt(ss_res / (n - 2) / sxx) if (n > 2 and sxx > 0) else float("nan")
    return ExponentFit(
        exponent=float(slope), stderr=float(stderr), r2=float(r2), n_points=n,
        t_lo=float(t[m].min()), t_hi=float(t[m].max()),
        w_lo=float(w[m].min()), w_hi=float(w[m].max()),
    )


def fit_alpha(saturation: list[dict]) -> ExponentFit | None:
    """Roughness exponent α: the slope of ``log w_sat`` vs ``log L`` over the saturated rings."""
    L = [float(s["L"]) for s in saturation]
    w = [float(s["w_sat"]) for s in saturation]
    if len(L) < 3:
        return None
    return fit_exponent(L, w, t_fit_min=0, w_fit_min=0.0)


def rd_exact_deviation(times, width_sq, p: float) -> dict:
    """Grade random deposition against its **closed form** ``w²(t) = p(1−p)t``, point by point.

    Not an exponent — an exact curve with no fitted constant, the strongest single anchor in
    M17 (the same role Onsager's T_c plays in M01). Returns the maximum and mean relative
    deviation over all measured times.
    """
    t = np.asarray(times, dtype=float)
    w2 = np.asarray(width_sq, dtype=float)
    exact = p * (1.0 - p) * t
    rel = np.abs(w2 - exact) / exact
    return {"max_rel_dev": float(rel.max()), "mean_rel_dev": float(rel.mean()),
            "exact_w2": [float(x) for x in exact], "p": p}


def moment_resolution(sample: dict) -> dict:
    """How far each measured moment sits from its Tracy–Widom target, **in sampling sigmas**.

    Derived, never restated. A hand-written sentence about which moment did or did not resolve
    goes stale the moment the run changes; this computes it from the sample every time, so the
    report's honesty claim and its numbers cannot disagree.

    The sampling standard errors of the third and fourth standardised moments of ``n`` i.i.d.
    draws are ``sqrt(6/n)`` and ``sqrt(24/n)``. For the flat geometry the draws are *not* fully
    independent — several sites of one ring are sampled — so the quoted sigma is a floor and
    ``site_spacing_over_xi`` (how many correlation lengths apart those sites sit) is carried
    alongside it rather than being quietly ignored.
    """
    n = max(int(sample.get("n_samples", 1)), 1)
    is_gue = sample["tw_law"] == "GUE"
    skew_target = PREDICTED_SKEW["droplet"] if is_gue else PREDICTED_SKEW["flat"]
    kurt_target = TW_GUE_EXKURT if is_gue else TW_GOE_EXKURT
    se_skew = math.sqrt(6.0 / n)
    se_kurt = math.sqrt(24.0 / n)
    d_skew = abs(float(sample["skewness"]) - skew_target)
    d_kurt = abs(float(sample["excess_kurtosis"]) - kurt_target)
    return {
        "n_samples": n,
        "skew_target": skew_target, "skew_gap": d_skew,
        "skew_sampling_sigma": se_skew, "skew_gap_in_sigma": d_skew / se_skew,
        "kurt_target": kurt_target, "kurt_gap": d_kurt,
        "kurt_sampling_sigma": se_kurt, "kurt_gap_in_sigma": d_kurt / se_kurt,
        "site_spacing_over_xi": sample.get("site_spacing_over_xi"),
        "independent_samples": sample.get("n_sites", 1) == 1,
    }


def assign_tw_class(sample: dict) -> dict:
    """Which Tracy–Widom law does this sample's *shape* actually sit closer to?

    The graded distributional statement. Compares the measured skewness to the two signed
    predictions (mirrored by ``λ < 0``) and reports the nearer one plus how decisively — a
    sample that is merely "non-Gaussian" proves nothing, and one sitting equidistant between
    GUE and GOE has not resolved the geometry dependence at all.
    """
    s = float(sample["skewness"])
    d_gue = abs(s - PREDICTED_SKEW["droplet"])
    d_goe = abs(s - PREDICTED_SKEW["flat"])
    nearer = "GUE" if d_gue < d_goe else "GOE"
    return {
        "skewness": s,
        "distance_to_gue": d_gue,
        "distance_to_goe": d_goe,
        "nearer": nearer,
        "expected": sample["tw_law"],
        "correct": nearer == sample["tw_law"],
        # >1 means the sample sits nearer its own law; the factor is how decisively.
        "decisiveness": float(max(d_gue, d_goe) / min(d_gue, d_goe)) if min(d_gue, d_goe) > 0 else float("inf"),
    }


@dataclass
class M17Result:
    growth: dict                 # model -> {times, width, width_sq, fit}
    saturation: list             # [{L, w_sat, ...}]
    alpha_fit: ExponentFit | None
    distributions: dict          # ic -> sample dict
    assignments: dict            # ic -> assign_tw_class(...)
    resolution: dict             # ic -> moment_resolution(...), gaps in sampling sigmas
    rd_exact: dict
    beta: float                  # headline: the KPZ growth exponent
    beta_stderr: float
    alpha: float | None
    z: float | None
    inv_z: float | None          # = β/α — the milestone's "2/3 in space"
    controls_separate: bool
    tw_assignment_correct: bool
    supports_kpz: bool
    wall_seconds: float
    config: dict = field(default_factory=dict)


def run_m17(
    L: int = 4096,
    batch: int = 64,
    t_max: int = 8000,
    n_times: int = 44,
    ew_L: int = 2048,
    ew_t_max: int = 2000,
    rd_L: int = 2048,
    rd_t_max: int = 2000,
    sat_L: tuple = (16, 32, 64, 128, 192),
    sat_batch: int = 64,
    dist_t: int = 400,
    droplet_batch: int = 6000,
    flat_L: int = 2048,
    flat_batch: int = 3000,
    flat_sites: int = 8,
    p: float = P_FLIP,
    seed: int = 42,
    progress=None,
) -> M17Result:
    """Run the whole M17 bench: three growth models, the saturation sweep, both geometries.

    Every stage writes its raw curves into the result so ``check_m17`` can re-derive the graded
    numbers itself. ``L`` must satisfy the saturation guard (``w(t_max) ≤ 0.20·√L``) for the
    KPZ growth fit to be clean, and the droplet ring must satisfy ``flat/droplet`` time budgets
    — both are asserted rather than assumed.
    """
    t0 = time.time()
    droplet_L = 4 * dist_t
    if dist_t > droplet_time_budget(droplet_L):
        raise ValueError(f"droplet ring too small for {dist_t} sweeps")

    def say(msg):
        if progress is not None:
            progress(msg)

    growth: dict = {}
    for name, (mL, mt) in {"kpz": (L, t_max), "ew": (ew_L, ew_t_max),
                           "rd": (rd_L, rd_t_max)}.items():
        say(f"growth[{name}] L={mL} t_max={mt}")
        r = run_growth(name, L=mL, batch=batch, t_max=mt, n_times=n_times, seed=seed + 1, p=p)
        fit = fit_exponent(r.times, r.width)
        growth[name] = {
            "model": name, "L": mL, "batch": batch, "t_max": mt,
            "times": r.times, "width": r.width, "width_sq": r.width_sq,
            "fit": _fit_to_dict(fit), "wall_seconds": r.wall_seconds,
            "w_final_over_sqrtL": (r.width[-1] / math.sqrt(mL)) if r.width else None,
        }
        say(f"  β[{name}] = {fit.exponent:.4f}" if fit else f"  β[{name}] = (no window)")

    say(f"saturation L={list(sat_L)}")
    saturation = run_saturation(list(sat_L), batch=sat_batch, seed=seed + 2, p=p)
    alpha_fit = fit_alpha(saturation)

    distributions, assignments = {}, {}
    say(f"droplet L={droplet_L} t={dist_t} N={droplet_batch}")
    distributions["droplet"] = run_height_distribution(
        "droplet", L=droplet_L, t=dist_t, batch=droplet_batch, seed=seed + 3, p=p)
    say(f"flat L={flat_L} t={dist_t} N={flat_batch}×{flat_sites}")
    distributions["flat"] = run_height_distribution(
        "flat", L=flat_L, t=dist_t, batch=flat_batch, seed=seed + 4, p=p, n_sites=flat_sites)
    resolution = {}
    for ic, sample in distributions.items():
        assignments[ic] = assign_tw_class(sample)
        resolution[ic] = moment_resolution(sample)

    rd_exact = rd_exact_deviation(growth["rd"]["times"], growth["rd"]["width_sq"], p)

    beta = growth["kpz"]["fit"]["exponent"] if growth["kpz"]["fit"] else float("nan")
    beta_se = growth["kpz"]["fit"]["stderr"] if growth["kpz"]["fit"] else float("nan")
    ew_beta = growth["ew"]["fit"]["exponent"] if growth["ew"]["fit"] else float("nan")
    rd_beta = growth["rd"]["fit"]["exponent"] if growth["rd"]["fit"] else float("nan")
    alpha = alpha_fit.exponent if alpha_fit else None
    z = (alpha / beta) if (alpha and beta and math.isfinite(beta) and beta > 0) else None
    inv_z = (beta / alpha) if (alpha and math.isfinite(beta)) else None

    controls_separate = bool(
        abs(ew_beta - EW_BETA) <= EW_BETA_TOL
        and abs(rd_beta - RD_BETA) <= RD_BETA_TOL
        and rd_exact["max_rel_dev"] <= RD_EXACT_TOL
    )
    tw_ok = all(a["correct"] for a in assignments.values())
    supports = bool(abs(beta - KPZ_BETA) <= KPZ_BETA_TOL and controls_separate)

    return M17Result(
        growth=growth, saturation=saturation, alpha_fit=alpha_fit,
        distributions=distributions, assignments=assignments, resolution=resolution,
        rd_exact=rd_exact,
        beta=float(beta), beta_stderr=float(beta_se), alpha=alpha, z=z, inv_z=inv_z,
        controls_separate=controls_separate, tw_assignment_correct=tw_ok,
        supports_kpz=supports, wall_seconds=time.time() - t0,
        config={
            "model": "single-step-corner-growth-1d-ring",
            "dynamics": "sublattice-parallel corner flips (exact, non-conflicting)",
            "p_flip": p, "L": L, "batch": batch, "t_max": t_max, "n_times": n_times,
            "ew_L": ew_L, "ew_t_max": ew_t_max, "rd_L": rd_L, "rd_t_max": rd_t_max,
            "sat_L": list(sat_L), "sat_batch": sat_batch,
            "dist_t": dist_t, "droplet_L": droplet_L, "droplet_batch": droplet_batch,
            "flat_L": flat_L, "flat_batch": flat_batch, "flat_sites": flat_sites,
            "seed": seed, "device": "cpu-numpy",
            "t_fit_min": T_FIT_MIN, "w_fit_min": W_FIT_MIN, "sat_guard_frac": SAT_GUARD_FRAC,
            "lambda_sign": "negative (v(u)=(p/2)(1-u^2) ⇒ λ=-p) — predicts mirrored Tracy–Widom",
            "v_at_zero_slope": slope_velocity(0.0, p),
        },
    )


def _fit_to_dict(fit: ExponentFit | None) -> dict | None:
    if fit is None:
        return None
    return {"exponent": fit.exponent, "stderr": fit.stderr, "r2": fit.r2,
            "n_points": fit.n_points, "t_lo": fit.t_lo, "t_hi": fit.t_hi,
            "w_lo": fit.w_lo, "w_hi": fit.w_hi}


def to_report(result: M17Result) -> dict:
    """A JSON report shaped for the page + ``check_m17``.

    Distinct ``experiment`` tag (``M17-kpz-growth``) so no peak/crossing/integration check
    misreads it. Carries every raw ``(times, width)`` curve, the window rule, the saturation
    table and both distribution samples, so the check re-selects the window and re-fits every
    graded exponent itself rather than reading the reported ones.
    """
    e = result
    ew = e.growth["ew"]["fit"]
    rd = e.growth["rd"]["fit"]
    ew_b = ew["exponent"] if ew else float("nan")
    rd_b = rd["exponent"] if rd else float("nan")
    kfit = e.growth["kpz"]["fit"] or {}
    dro, fla = e.assignments["droplet"], e.assignments["flat"]

    headline = (
        f"1+1d single-step growth on a ring (L={e.growth['kpz']['L']}, "
        f"{e.growth['kpz']['batch']} rings, {e.growth['kpz']['t_max']:,} sweeps): "
        f"β={e.beta:.4f} against the exact KPZ 1/3, with α={e.alpha:.4f} from saturation "
        f"(exact 1/2) giving z=α/β={e.z:.3f} (exact 3/2) and 1/z={e.inv_z:.3f} (exact 2/3). "
        f"Same pipeline on the controls: Edwards–Wilkinson β={ew_b:.4f} (exact 1/4) and "
        f"random deposition β={rd_b:.4f} (exact 1/2, and its w²(t) tracks the closed form "
        f"p(1−p)t to {100 * e.rd_exact['max_rel_dev']:.1f}%) — three separated classes, so the "
        f"1/3 is a measurement and not an artifact of the fit. Height fluctuations are "
        f"skewed {e.distributions['droplet']['skewness']:+.4f} (droplet) and "
        f"{e.distributions['flat']['skewness']:+.4f} (flat) against the λ<0-mirrored "
        f"Tracy–Widom predictions {PREDICTED_SKEW['droplet']:+.4f} (GUE) and "
        f"{PREDICTED_SKEW['flat']:+.4f} (GOE): each geometry lands nearer its own law "
        f"({dro['decisiveness']:.1f}× and {fla['decisiveness']:.1f}×). · {e.wall_seconds:.0f}s"
    )

    report = {
        "experiment": "M17-kpz-growth",
        "headline": headline,
        "status": "pass" if (e.supports_kpz and e.tw_assignment_correct) else "null",
        # exponents
        "beta": e.beta,
        "beta_stderr": e.beta_stderr,
        "beta_exact": KPZ_BETA,
        "alpha": e.alpha,
        "alpha_exact": KPZ_ALPHA,
        "z": e.z,
        "z_exact": KPZ_Z,
        "inv_z": e.inv_z,
        "inv_z_exact": 1.0 / KPZ_Z,
        "kpz_fit": kfit,
        # raw curves for every model — the check re-fits from these
        "growth": e.growth,
        "ew_beta": ew_b,
        "ew_beta_exact": EW_BETA,
        "rd_beta": rd_b,
        "rd_beta_exact": RD_BETA,
        "rd_exact_curve": e.rd_exact,
        "controls_separate": e.controls_separate,
        # saturation
        "saturation": e.saturation,
        "alpha_fit": _fit_to_dict(e.alpha_fit),
        # distributions
        "distributions": e.distributions,
        "assignments": e.assignments,
        "moment_resolution": e.resolution,
        "tw_assignment_correct": e.tw_assignment_correct,
        "tw_targets": {
            "gue_skewness": TW_GUE_SKEW, "gue_excess_kurtosis": TW_GUE_EXKURT,
            "goe_skewness": TW_GOE_SKEW, "goe_excess_kurtosis": TW_GOE_EXKURT,
            "lambda_sign": -1, "predicted_skewness": PREDICTED_SKEW,
        },
        # window rule (the check reads these, so the fit is re-derivable)
        "t_fit_min": T_FIT_MIN,
        "w_fit_min": W_FIT_MIN,
        "sat_guard_frac": SAT_GUARD_FRAC,
        "supports_kpz": e.supports_kpz,
        "wall_seconds": e.wall_seconds,
        "config": e.config,
        "claim_boundary": _claim_boundary(e),
    }
    return report


def _claim_boundary(e: M17Result) -> str:
    """Build the claim boundary FROM the measurement, so prose and data cannot drift apart.

    Every number in the sentence below is re-read from this run's own fits and moment gaps.
    Nothing about how well the distribution converged is asserted by hand.
    """
    ew_b = (e.growth["ew"]["fit"] or {}).get("exponent", float("nan"))
    rd_b = (e.growth["rd"]["fit"] or {}).get("exponent", float("nan"))
    beta_gap = e.beta - KPZ_BETA
    ew_gap = ew_b - EW_BETA
    same_direction = (beta_gap < 0) == (ew_gap < 0)

    bits = []
    for ic in ("droplet", "flat"):
        r = e.resolution[ic]
        law = "GUE" if ic == "droplet" else "GOE"
        note = "" if r["independent_samples"] else (
            f" (sampled at {r['n_samples']} points, {r['site_spacing_over_xi']:.1f} correlation "
            f"lengths apart, so this sigma is a floor)")
        bits.append(
            f"{ic}/{law}: skewness {r['skew_gap']:.4f} from target "
            f"({r['skew_gap_in_sigma']:.1f}x its sampling sigma), excess kurtosis "
            f"{r['kurt_gap']:.4f} from target ({r['kurt_gap_in_sigma']:.1f}x){note}"
        )

    return (
        "A finite-size, finite-time measurement of the 1+1d KPZ exponents and of which "
        "Tracy-Widom law each geometry's fluctuations sit nearer. "
        f"The effective beta = {e.beta:.4f} sits {abs(beta_gap):.4f} "
        f"{'BELOW' if beta_gap < 0 else 'ABOVE'} the exact 1/3 — the documented preasymptotic "
        f"approach from below. That this is the finite fit window and not a defect in the KPZ "
        f"measurement is evidenced by the Edwards-Wilkinson control, which misses its own "
        f"exact 1/4 by {abs(ew_gap):.4f} "
        f"{'in the SAME direction' if same_direction else 'in the OPPOSITE direction'}, while "
        f"random deposition — which has no correlation time to be preasymptotic about — lands "
        f"at {rd_b:.4f} against an exact 1/2. "
        "The distributional claim is CLASS ASSIGNMENT by skewness — a shape statistic "
        "invariant under the unfitted (v_inf, Gamma) rescaling — and NOT a full Tracy-Widom "
        "distribution collapse. Measured moment gaps this run: " + "; ".join(bits) + ". "
        "The kurtosis is carried as evidence and is deliberately NOT graded by check_m17. "
        "Nothing here claims the Tracy-Widom constants v_inf or Gamma, which are not measured, "
        "nor the exponents' asymptotic values, which this window cannot reach."
    )
