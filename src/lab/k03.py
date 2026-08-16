"""K03 — Daido vs Hong: is the susceptibility exponent asymmetric across K_c?

χ ~ |K − K_c|^(−γ) above the transition and ^(−γ') below. Daido's perturbation
theory (Prog. Theor. Phys. 75, 1460 (1986); J. Stat. Phys. 60, 753 (1990))
predicts an ASYMMETRIC pair — γ = 1/4 supercritical, γ' = 1 subcritical — on
the regular (deterministic-quantile) frequency distribution. Hong, Chaté, Tang
& Park, PRE 92, 022122 (2015) §IV contradict it: γ = γ' = 1/4 for the same
class. The 2026-08-02 assay established this engine's frequency set is that
class term for term, so the disagreement is measurable here.

### Why this is a FIELD measurement and not a fluctuation one

The 2026-08-08 estimator assay (docs/assays/2026-08-08-k03-estimator-assay.md)
disqualified four estimators, each of which returned a precise wrong answer.
What survives is linear response to an explicit pinning field h along Θ = 0,
with **two observables, one per branch, because the symmetry differs**:

    below K_c   χ' = ∂⟨cos θ⟩/∂h    no order, ψ undefined, no Goldstone mode
    above K_c   χ  = ∂⟨r⟩/∂h        longitudinal — the magnitude of order;
                                     ⟨cos θ⟩ would measure the trivially
                                     divergent transverse (Goldstone) response

and four non-negotiables from the assay, all enforced here:

1. every fit carries an INTERCEPT — never through the origin;
2. a LINEARITY GATE that refuses: a column whose field-ladder secants are not
   constant to ``SECANT_TOL`` is excluded from the branch fit and reported,
   never fitted anyway;
3. a PER-COLUMN field ladder, scaled from a cheap pilot pass — χ ranges over
   ~50× across the grid and one global h cannot keep χ·h small everywhere;
4. the grid starts a decade outside the finite-size rounding: ν̄ ≈ 5/4 puts
   rounding at ε ~ N^(−4/5) = 0.0023 at N = 2000, and the grid floor is 0.02.

### What is graded, and what deliberately is not

``check_k03`` gates the MEASUREMENT — enough surviving columns per branch,
positive exponents (a negative one is the assay's bug-class-6 signature),
baseline controls, fit quality. The Daido-vs-Hong verdict itself is REPORTED,
never gated: gating on either paper's number would let the grader manufacture
the answer, exactly the trap K02's check documents.

The dynamics are a deterministic ODE (fixed-step RK4), so h = 0 and h > 0
trajectories from ONE shared initial condition differ only by the field —
the response is a controlled comparison with no sampling noise on top.

NumPy only — the mean-field collapse keeps N = 2000 a CPU problem.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .kuramoto import (
    DT, GAMMA, critical_coupling, lorentzian_frequencies, mean_field_r,
    order_parameter, rk4_step,
)

# ── the measurement's identity ───────────────────────────────────────────────
# Symmetric log-spaced grid in ε = |K − K_c|/K_c, both branches. The floor sits
# a decade above the N=2000 finite-size rounding (assay §"What K03 needs" #4).
EPS_MIN = 0.02
EPS_MAX = 0.32
EPS_POINTS = 7
N_OSCILLATORS = 2000
# Field-ladder rungs per column, h > 0 (h = 0 is always measured as baseline).
LADDER_RUNGS = 3
# The pilot's single probe field: the assay's corrected runs used 0.002.
PILOT_FIELD = 0.002
# Target response at the ladder top: χ·h_max ≈ this, per column. Small against
# every observable scale in the problem (the subcritical m floor is ~1/√N).
TARGET_RESPONSE = 0.02
# Ladder fields are clipped into this range whatever the pilot says.
H_MIN, H_MAX = 1e-5, 0.05
# The linearity gate: max relative secant spread a column may show and still
# count as linear response. On the assay's corrected run this gate passed 1 of
# 12 columns — the honest verdict that that measurement did not happen.
SECANT_TOL = 0.15
# Equilibration windows. K02's lesson: reading a too-short window at large N
# measures a transient. Off-critical (ε ≥ 0.02) relaxes faster than K_c, but
# the budget is cheap enough to keep the long window.
T_BURN = 1000.0
T_MEASURE = 2000.0
PILOT_T_BURN = 300.0
PILOT_T_MEASURE = 600.0
# ── the two published claims this measurement adjudicates (reported, not gated)
DAIDO = {"gamma": 0.25, "gamma_prime": 1.0,
         "source": "Daido, Prog. Theor. Phys. 75, 1460 (1986); "
                   "J. Stat. Phys. 60, 753 (1990)"}
HONG = {"gamma": 0.25, "gamma_prime": 0.25,
        "source": "Hong, Chaté, Tang & Park, PRE 92, 022122 (2015) §IV"}
# ── validity gates for check_k03 ─────────────────────────────────────────────
MIN_COLUMNS_PER_BRANCH = 4
# Subcritical baseline: m(h=0) is the finite-N random-walk floor, |m| ≲ 1/√N.
BASELINE_FLOOR_SCALE = 5.0
# Supercritical baseline: r(h=0) vs the exact √(1 − K_c/K), which finite N
# smears near the transition. Generous but bounding — a Goldstone/transverse
# confusion misses by the whole spontaneous r, not by a smearing width.
BASELINE_R_TOL = 0.08
# Branch power-law fit must at least look like a power law.
BRANCH_R2_MIN = 0.80


def eps_grid(n_points: int = EPS_POINTS, eps_min: float = EPS_MIN,
             eps_max: float = EPS_MAX) -> np.ndarray:
    """The symmetric log-spaced ε grid used on BOTH branches."""
    if n_points < 2:
        raise ValueError("the ε grid needs at least two points")
    return np.geomspace(eps_min, eps_max, n_points)


def _ols_line(x: np.ndarray, y: np.ndarray) -> dict:
    """Least-squares y = a + b·x WITH intercept: slope, intercept, R², stderr.

    The intercept is assay rule #1 — a through-origin fit silently absorbs any
    baseline into the slope (that defect manufactured γ = −0.306 at R² 0.995).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = x.size
    xm, ym = x.mean(), y.mean()
    sxx = float(((x - xm) ** 2).sum())
    if sxx == 0.0:
        raise ValueError("degenerate abscissa in OLS")
    slope = float(((x - xm) * (y - ym)).sum() / sxx)
    intercept = float(ym - slope * xm)
    resid = y - (intercept + slope * x)
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - ym) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    stderr = (np.sqrt(ss_res / (n - 2) / sxx) if n > 2 else float("nan"))
    return {"slope": slope, "intercept": intercept, "r2": r2,
            "stderr": float(stderr)}


def column_response(h: np.ndarray, obs: np.ndarray,
                    secant_tol: float = SECANT_TOL) -> dict:
    """One column's susceptibility from its field ladder — or its refusal.

    ``h`` ascending with ``h[0] == 0`` (the baseline). The gate: successive
    secants ``Δobs/Δh`` must agree with their own mean to ``secant_tol``; a
    drifting secant means no single slope exists and the column is refused
    (assay rule #2), with the secants in the record so the check can re-refuse.
    """
    h = np.asarray(h, dtype=np.float64)
    obs = np.asarray(obs, dtype=np.float64)
    if h.size < 3 or h[0] != 0.0 or np.any(np.diff(h) <= 0):
        raise ValueError("a column needs an h=0 baseline and ascending fields")
    secants = np.diff(obs) / np.diff(h)
    mean_sec = float(secants.mean())
    if mean_sec == 0.0:
        return {"ok": False, "reason": "flat-response", "chi": None,
                "secants": secants.tolist(), "secant_spread": None,
                "fit": None, "baseline": float(obs[0])}
    spread = float(np.max(np.abs(secants / mean_sec - 1.0)))
    fit = _ols_line(h, obs)
    if spread > secant_tol:
        return {"ok": False, "reason": "nonlinear-secants",
                "chi": None, "secants": secants.tolist(),
                "secant_spread": spread, "fit": fit,
                "baseline": float(obs[0])}
    return {"ok": True, "reason": None, "chi": fit["slope"],
            "secants": secants.tolist(), "secant_spread": spread,
            "fit": fit, "baseline": float(obs[0])}


def branch_exponent(eps: np.ndarray, chi: np.ndarray) -> dict:
    """γ from χ ~ ε^(−γ): the log-log OLS slope, negated, with its stderr."""
    eps = np.asarray(eps, dtype=np.float64)
    chi = np.asarray(chi, dtype=np.float64)
    if np.any(chi <= 0):
        # A non-positive susceptibility on either branch is physically
        # impossible for this response and voids the log — the caller
        # reports the branch as unmeasured rather than fitting around it.
        return {"gamma": None, "err": None, "r2": None,
                "reason": "non-positive susceptibility in branch"}
    fit = _ols_line(np.log10(eps), np.log10(chi))
    return {"gamma": -fit["slope"], "err": fit["stderr"], "r2": fit["r2"],
            "reason": None}


def measure_grid(
    couplings: np.ndarray,
    fields: np.ndarray,
    n: int = N_OSCILLATORS,
    gamma: float = GAMMA,
    dt: float = DT,
    t_burn: float = T_BURN,
    t_measure: float = T_MEASURE,
    sample_every: int = 10,
    seed: int = 42,
    progress=None,
) -> dict:
    """Integrate a (column) grid of (K, h) pairs at once; return ⟨r⟩ and ⟨cos θ⟩.

    ``couplings`` and ``fields`` are equal-length 1-D arrays — one entry per
    column of the shared phase block. Everything shares one frequency set and
    ONE seeded initial condition (the K01/K02 controlled-comparison rule), so
    columns differ only in (K, h). Returns per-column time means over the
    measurement window plus the drift between its halves — K02's equilibration
    receipt, carried so the check can refuse a still-settling column.
    """
    K = np.asarray(couplings, dtype=np.float64).reshape(-1)
    h = np.asarray(fields, dtype=np.float64).reshape(-1)
    if K.size != h.size or K.size == 0:
        raise ValueError("couplings and fields must be equal-length, non-empty")
    omega = lorentzian_frequencies(n, gamma)
    rng = np.random.default_rng(seed)
    theta = np.repeat(rng.uniform(0.0, 2.0 * np.pi, size=n)[None, :],
                      K.size, axis=0)
    k_col = K[:, None]
    h_col = h[:, None]

    n_burn = int(round(t_burn / dt))
    n_meas = int(round(t_measure / dt))
    for step in range(n_burn):
        theta = rk4_step(theta, omega, k_col, dt, h_col)
        if progress is not None and step % 5000 == 0:
            progress("burn-in", step, n_burn)
    half = n_meas // 2
    sums = {"r": [0.0, 0.0], "m": [0.0, 0.0]}
    counts = [0, 0]
    for step in range(n_meas):
        theta = rk4_step(theta, omega, k_col, dt, h_col)
        if step % sample_every == 0:
            r, _ = order_parameter(theta)
            m = np.cos(theta).mean(axis=-1)
            idx = 0 if step < half else 1
            sums["r"][idx] = sums["r"][idx] + r
            sums["m"][idx] = sums["m"][idx] + m
            counts[idx] += 1
        if progress is not None and step % 5000 == 0:
            progress("measure", step, n_meas)
    r_half = [np.asarray(sums["r"][i] / counts[i]) for i in (0, 1)]
    m_half = [np.asarray(sums["m"][i] / counts[i]) for i in (0, 1)]
    return {
        "r_mean": ((r_half[0] + r_half[1]) / 2.0),
        "m_mean": ((m_half[0] + m_half[1]) / 2.0),
        "r_drift": (r_half[1] - r_half[0]),
        "m_drift": (m_half[1] - m_half[0]),
        "n_samples": int(sum(counts)),
    }


@dataclass
class K03Result:
    eps: np.ndarray                 # the shared ε grid
    below: list                     # per-column records, subcritical branch
    above: list                     # per-column records, supercritical branch
    fit_below: dict                 # γ' fit over surviving columns
    fit_above: dict                 # γ fit over surviving columns
    n: int
    gamma_width: float              # the Lorentzian γ (name dodges the exponent)
    k_c: float
    dt: float
    t_burn: float
    t_measure: float
    seed: int
    pilot: dict = field(default_factory=dict)
    wall_seconds: float = 0.0


def run_k03(
    n: int = N_OSCILLATORS,
    gamma: float = GAMMA,
    n_points: int = EPS_POINTS,
    eps_min: float = EPS_MIN,
    eps_max: float = EPS_MAX,
    rungs: int = LADDER_RUNGS,
    dt: float = DT,
    t_burn: float = T_BURN,
    t_measure: float = T_MEASURE,
    pilot_t_burn: float = PILOT_T_BURN,
    pilot_t_measure: float = PILOT_T_MEASURE,
    seed: int = 42,
    progress=None,
) -> K03Result:
    """The two-pass, two-branch, gated linear-response measurement.

    Pass 1 (pilot): every grid column at h = 0 and h = PILOT_FIELD, short
    windows — a χ estimate per column, nothing graded. Pass 2 (graded): each
    column's own ladder ``h_max·{0, 1/rungs, …, 1}`` with ``h_max`` scaled so
    the expected response stays ≈ TARGET_RESPONSE, long windows. Observable
    per branch per the assay: ⟨cos θ⟩ below K_c, longitudinal ⟨r⟩ above.
    """
    t0 = time.time()
    k_c = critical_coupling(gamma)
    eps = eps_grid(n_points, eps_min, eps_max)
    k_below = k_c * (1.0 - eps)
    k_above = k_c * (1.0 + eps)
    grid_K = np.concatenate([k_below, k_above])
    n_cols = grid_K.size

    # ── pilot: one probe field, shared, short windows ────────────────────────
    if progress is not None:
        progress("pilot", 0, 1)
    pilot_K = np.concatenate([grid_K, grid_K])
    pilot_h = np.concatenate([np.zeros(n_cols),
                              np.full(n_cols, PILOT_FIELD)])
    pilot = measure_grid(pilot_K, pilot_h, n=n, gamma=gamma, dt=dt,
                         t_burn=pilot_t_burn, t_measure=pilot_t_measure,
                         seed=seed, progress=None)
    # Branch-appropriate observable for the pilot's χ estimate.
    obs0 = np.concatenate([pilot["m_mean"][:n_points],
                           pilot["r_mean"][n_points:n_cols]])
    obs1 = np.concatenate([
        pilot["m_mean"][n_cols:n_cols + n_points],
        pilot["r_mean"][n_cols + n_points:],
    ])
    chi_pilot = np.abs(obs1 - obs0) / PILOT_FIELD
    h_max = np.clip(TARGET_RESPONSE / np.maximum(chi_pilot, 1e-12),
                    H_MIN, H_MAX)

    # ── graded pass: per-column ladders, one big block ───────────────────────
    ladder_fracs = np.arange(rungs + 1) / rungs          # 0, 1/r, …, 1
    graded_K = np.tile(grid_K, rungs + 1)
    graded_h = np.concatenate([h_max * f for f in ladder_fracs])
    if progress is not None:
        progress("graded", 0, 1)
    graded = measure_grid(graded_K, graded_h, n=n, gamma=gamma, dt=dt,
                          t_burn=t_burn, t_measure=t_measure, seed=seed,
                          progress=progress)

    def _column(i: int, branch: str) -> dict:
        rows = [i + j * n_cols for j in range(rungs + 1)]
        h_ladder = graded_h[rows]
        obs_key = "m_mean" if branch == "below" else "r_mean"
        drift_key = "m_drift" if branch == "below" else "r_drift"
        obs = np.asarray([graded[obs_key][r] for r in rows])
        drift = float(np.max(np.abs(np.asarray(
            [graded[drift_key][r] for r in rows]))))
        rec = column_response(h_ladder, obs)
        rec.update({
            "eps": float(eps[i % n_points]),
            "K": float(grid_K[i]),
            "branch": branch,
            "h_ladder": h_ladder.tolist(),
            "obs": obs.tolist(),
            "half_window_drift": drift,
            "pilot_chi": float(chi_pilot[i]),
        })
        return rec

    below = [_column(i, "below") for i in range(n_points)]
    above = [_column(n_points + i, "above") for i in range(n_points)]

    def _branch_fit(cols: list) -> dict:
        ok = [c for c in cols if c["ok"]]
        if len(ok) < MIN_COLUMNS_PER_BRANCH:
            return {"gamma": None, "err": None, "r2": None,
                    "n_columns": len(ok),
                    "reason": f"only {len(ok)} column(s) passed the linearity "
                              f"gate (need {MIN_COLUMNS_PER_BRANCH}) — the "
                              "measurement did not happen on this branch"}
        fit = branch_exponent(np.asarray([c["eps"] for c in ok]),
                              np.asarray([c["chi"] for c in ok]))
        fit["n_columns"] = len(ok)
        return fit

    result = K03Result(
        eps=eps, below=below, above=above,
        fit_below=_branch_fit(below), fit_above=_branch_fit(above),
        n=n, gamma_width=gamma, k_c=k_c, dt=dt,
        t_burn=t_burn, t_measure=t_measure, seed=seed,
        pilot={"field": PILOT_FIELD, "chi": chi_pilot.tolist(),
               "h_max": h_max.tolist()},
        wall_seconds=time.time() - t0,
    )
    return result


def _verdict(fit_above: dict, fit_below: dict) -> dict:
    """Nearest published claim by σ-distance — REPORTED, never graded."""
    g, gp = fit_above.get("gamma"), fit_below.get("gamma")
    if g is None or gp is None:
        return {"nearest": None,
                "note": "one or both branches unmeasured — no adjudication"}
    ge = fit_above.get("err") or 0.1
    gpe = fit_below.get("err") or 0.1

    def dist(claim):
        return np.hypot((g - claim["gamma"]) / max(ge, 1e-6),
                        (gp - claim["gamma_prime"]) / max(gpe, 1e-6))
    d_daido, d_hong = float(dist(DAIDO)), float(dist(HONG))
    nearest = "daido" if d_daido < d_hong else "hong"
    return {"nearest": nearest, "sigma_daido": d_daido, "sigma_hong": d_hong,
            "note": "nearest by combined sigma-distance; adjudication is for "
                    "the reader — the check gates only measurement validity"}


def to_report(result: K03Result) -> dict:
    """The receipts-grade report ``check_k03`` re-derives from."""
    ok_below = [c for c in result.below if c["ok"]]
    ok_above = [c for c in result.above if c["ok"]]
    measured = (result.fit_below.get("gamma") is not None
                and result.fit_above.get("gamma") is not None)
    fa, fb = result.fit_above, result.fit_below
    if measured:
        headline = (
            f"linear-response exponents: γ = {fa['gamma']:.3f}±{fa['err']:.3f} "
            f"(supercritical, {fa['n_columns']} columns) · "
            f"γ' = {fb['gamma']:.3f}±{fb['err']:.3f} "
            f"(subcritical, {fb['n_columns']} columns) — Daido predicts "
            f"(0.25, 1), Hong (0.25, 0.25)")
    else:
        headline = ("linearity gate refused too many columns — the exponents "
                    "were not measured; the refusals are the result")
    return {
        "experiment": "K03-daido-vs-hong",
        "milestone": "K03",
        "status": "pass" if measured else "fail",
        "headline": headline,
        "n": result.n,
        "gamma_width": result.gamma_width,
        "k_c": result.k_c,
        "dt": result.dt,
        "t_burn": result.t_burn,
        "t_measure": result.t_measure,
        "seed": result.seed,
        "eps_grid": result.eps.tolist(),
        "columns_below": result.below,
        "columns_above": result.above,
        "fit_below": result.fit_below,
        "fit_above": result.fit_above,
        "surviving_columns": {"below": len(ok_below), "above": len(ok_above)},
        "verdict": _verdict(result.fit_above, result.fit_below),
        "references": {"daido": DAIDO, "hong": HONG},
        "pilot": result.pilot,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "Finite-N (N={n}) linear-response exponents on the regular "
            "(deterministic-quantile, tail-clipped) Lorentzian Kuramoto model, "
            "measured over eps in [{lo:g}, {hi:g}] with per-column field "
            "ladders and a refusing linearity gate; two observables, one per "
            "branch (cos-theta below K_c, longitudinal r above). This grades "
            "the measurement's validity, not which published exponent pair is "
            "right: the Daido-vs-Hong comparison is reported with its "
            "sigma-distances and left to the reader. No infinite-N claim, no "
            "claim outside the swept eps window.").format(
                n=result.n, lo=float(result.eps[0]), hi=float(result.eps[-1])),
    }
