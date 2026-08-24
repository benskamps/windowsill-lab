"""K03 on the GPU — the same experiment, a different integrator.

Only the trajectory integration is new. The pilot design, the per-column field
ladder, the linearity gate, the branch fits and the adjudication are imported
from `k03` and called unchanged, so this is not a second measurement of the same
thing — it is the same measurement, run at an N the CPU engine could not afford.
If any physics decision were re-implemented here, the two runs would stop being
comparable and the whole point would be lost.

## What changes, and why

U-K02 measured the blocker: subcritical noise scaling as ε^-0.76 (critical
slowing down against a fixed `T_MEASURE`), and a gate thresholding that noise so
erratically that ε = 0.127 was refused while ε = 0.08 — closer to K_c — passed.
Two changes follow, and only these two:

1. **N = 200,000 rather than 2,000.** Error falls as 1/sqrt(N·T), and on this
   box the GPU delivers 100× the oscillators for 2.6× the wall-clock. This is
   the whole reason the run is affordable.
2. **`T_MEASURE` scaled per ε** by the measured noise law, instead of one value
   for every column. A column near K_c needs more time for the same precision;
   spending it uniformly either wastes it far out or starves it near in.

Everything else — including the ε grid's shape, the observable per branch, and
the gate's tolerance — is left exactly as the CPU run had it.

## Batched by ε, on purpose

The columns of one ε value (two branches × the ladder) are integrated as a
single block, which is both the controlled-comparison rule `measure_grid`
already follows and, measured on this box, the throughput peak: 6.8e8
oscillator-steps/s at 8×200,000 against 4.3e8 at 64×200,000, where memory
pressure starts to bite.
"""
from __future__ import annotations

import time

import numpy as np

from . import k03, kuramoto_gpu as gpu
from .kuramoto import lorentzian_frequencies

#: Burn-in as a fraction of that column's measurement window. Equilibration
#: slows near K_c for the same reason measurement does, so a fixed burn-in would
#: under-equilibrate exactly the columns that matter. The half-window drift is
#: recorded per column regardless, so an under-burned column reports itself.
BURN_FRACTION = 0.4


def measure_grid(couplings, fields, n, gamma, dt, t_burn, t_measure,
                 sample_every=10, seed=42, device="cuda"):
    """GPU twin of `k03.measure_grid` — same inputs, same returns, same rules.

    One frequency set and one seeded initial condition shared across every
    column, so columns differ only in (K, h). Observables are accumulated on the
    device: at N = 200,000 over 650,000 steps a returned trajectory would be
    hundreds of gigabytes, and the only quantities needed are two scalars per
    column per half-window.
    """
    torch = gpu.torch_or_none()
    if torch is None:
        raise ModuleNotFoundError("torch is not installed")
    K = np.asarray(couplings, dtype=np.float64).reshape(-1)
    h = np.asarray(fields, dtype=np.float64).reshape(-1)
    if K.size != h.size or K.size == 0:
        raise ValueError("couplings and fields must be equal-length, non-empty")

    omega_np = lorentzian_frequencies(n, gamma)
    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * np.pi, size=n)

    dev = device
    theta = torch.as_tensor(np.repeat(theta0[None, :], K.size, axis=0),
                            dtype=torch.float64, device=dev)
    omega = torch.as_tensor(omega_np, dtype=torch.float64, device=dev)
    k_col = torch.as_tensor(K[:, None], dtype=torch.float64, device=dev)
    h_col = (torch.as_tensor(h[:, None], dtype=torch.float64, device=dev)
             if np.any(h) else None)

    n_burn = int(round(t_burn / dt))
    n_meas = int(round(t_measure / dt))
    for _ in range(n_burn):
        theta = gpu.rk4_step(theta, omega, k_col, dt, h_col)

    half = n_meas // 2
    sums_r = [torch.zeros(K.size, dtype=torch.float64, device=dev) for _ in (0, 1)]
    sums_m = [torch.zeros(K.size, dtype=torch.float64, device=dev) for _ in (0, 1)]
    counts = [0, 0]
    for step in range(n_meas):
        theta = gpu.rk4_step(theta, omega, k_col, dt, h_col)
        if step % sample_every == 0:
            cos_t, sin_t = theta.cos(), theta.sin()
            c = cos_t.mean(dim=-1)
            s = sin_t.mean(dim=-1)
            idx = 0 if step < half else 1
            sums_r[idx] += (c * c + s * s).sqrt()
            sums_m[idx] += c
            counts[idx] += 1
    r_half = [(sums_r[i] / counts[i]).cpu().numpy() for i in (0, 1)]
    m_half = [(sums_m[i] / counts[i]).cpu().numpy() for i in (0, 1)]
    del theta, omega, k_col, h_col, sums_r, sums_m
    torch.cuda.empty_cache()
    return {
        "r_mean": (r_half[0] + r_half[1]) / 2.0,
        "m_mean": (m_half[0] + m_half[1]) / 2.0,
        "r_drift": r_half[1] - r_half[0],
        "m_drift": m_half[1] - m_half[0],
        "n_samples": int(sum(counts)),
    }


def _one_epsilon(eps, *, n, gamma, dt, t_measure, rungs, seed, device):
    """Pilot then graded pass for one ε — both branches, one block each."""
    k_c = k03.critical_coupling(gamma)
    grid_K = np.array([k_c * (1.0 - eps), k_c * (1.0 + eps)])

    pilot = measure_grid(
        np.concatenate([grid_K, grid_K]),
        np.concatenate([np.zeros(2), np.full(2, k03.PILOT_FIELD)]),
        n=n, gamma=gamma, dt=dt, t_burn=k03.PILOT_T_BURN,
        t_measure=k03.PILOT_T_MEASURE, seed=seed, device=device)
    # Branch-appropriate observable, exactly as run_k03 selects it.
    obs0 = np.array([pilot["m_mean"][0], pilot["r_mean"][1]])
    obs1 = np.array([pilot["m_mean"][2], pilot["r_mean"][3]])
    chi_pilot = np.abs(obs1 - obs0) / k03.PILOT_FIELD
    h_max = np.clip(k03.TARGET_RESPONSE / np.maximum(chi_pilot, 1e-12),
                    k03.H_MIN, k03.H_MAX)

    fracs = np.arange(rungs + 1) / rungs
    graded_K = np.tile(grid_K, rungs + 1)
    graded_h = np.concatenate([h_max * f for f in fracs])
    graded = measure_grid(graded_K, graded_h, n=n, gamma=gamma, dt=dt,
                          t_burn=t_measure * BURN_FRACTION,
                          t_measure=t_measure, seed=seed, device=device)

    out = {}
    for i, branch in ((0, "below"), (1, "above")):
        rows = [i + j * 2 for j in range(rungs + 1)]
        obs_key = "m_mean" if branch == "below" else "r_mean"
        drift_key = "m_drift" if branch == "below" else "r_drift"
        h_ladder = graded_h[rows]
        obs = np.asarray([graded[obs_key][r] for r in rows])
        rec = k03.column_response(h_ladder, obs)      # the SAME gate
        rec.update({
            "eps": float(eps), "K": float(grid_K[i]), "branch": branch,
            "h_ladder": h_ladder.tolist(), "obs": obs.tolist(),
            "half_window_drift": float(np.max(np.abs(
                [graded[drift_key][r] for r in rows]))),
            "pilot_chi": float(chi_pilot[i]),
            "t_measure": float(t_measure),
        })
        out[branch] = rec
    return out


def run(n=200_000, gamma=k03.GAMMA, eps_floor=0.005, eps_max=k03.EPS_MAX,
        n_points=8, rungs=k03.LADDER_RUNGS, dt=k03.DT, seed=42,
        device="cuda", progress=None) -> dict:
    """The full two-branch measurement at an N the CPU engine could not afford."""
    from . import u_k02_reach as reach
    t0 = time.time()
    eps = np.geomspace(eps_floor, eps_max, n_points)
    below, above = [], []
    for i, e in enumerate(eps):
        t_meas = reach.required_t_measure(
            float(e), ref_eps=0.02, ref_spread=0.400, ref_t=k03.T_MEASURE,
            secant_tol=k03.SECANT_TOL, n_ratio=n / k03.N_OSCILLATORS)
        if progress:
            progress(i, len(eps), float(e), t_meas)
        cols = _one_epsilon(float(e), n=n, gamma=gamma, dt=dt,
                            t_measure=t_meas, rungs=rungs, seed=seed,
                            device=device)
        below.append(cols["below"])
        above.append(cols["above"])

    ok_b = [c for c in below if c["ok"]]
    ok_a = [c for c in above if c["ok"]]
    fit_below = (k03.branch_exponent([c["eps"] for c in ok_b],
                                     [c["chi"] for c in ok_b])
                 if len(ok_b) >= k03.MIN_COLUMNS_PER_BRANCH
                 else {"gamma": None, "err": None, "r2": None,
                       "reason": f"only {len(ok_b)} column(s) passed the "
                                 f"linearity gate (need "
                                 f"{k03.MIN_COLUMNS_PER_BRANCH})"})
    fit_above = (k03.branch_exponent([c["eps"] for c in ok_a],
                                     [c["chi"] for c in ok_a])
                 if len(ok_a) >= k03.MIN_COLUMNS_PER_BRANCH
                 else {"gamma": None, "err": None, "r2": None,
                       "reason": f"only {len(ok_a)} column(s) passed the "
                                 f"linearity gate (need "
                                 f"{k03.MIN_COLUMNS_PER_BRANCH})"})
    return {
        "experiment": "K03-gpu-deep", "milestone": "K03", "schema": 1,
        "engine": "kuramoto_gpu", "device": gpu.device_name(),
        "n_oscillators": n, "eps": eps.tolist(),
        "columns_below": below, "columns_above": above,
        "fit_below": fit_below, "fit_above": fit_above,
        "verdict": k03._verdict(fit_above, fit_below),   # the SAME adjudicator
        "wall_seconds": time.time() - t0,
    }


# ── the h→0 estimator ────────────────────────────────────────────────────────
#
# The 2026-08-24 h-scan found that K03's single-ladder χ carries a saturation
# bias of 11–33%, and — the part that matters — the bias SHRINKS with ε. A
# systematic that varies across the fit range does not cancel in a power-law
# fit; it tilts it. Every supercritical column of the deep run was affected,
# which is why its γ = 1.064 is not a measurement.
#
# Linear response is defined in the limit h → 0, so the fix is to measure it
# there rather than at one convenient h: walk a long ladder, fit χ over
# progressively shorter sub-ladders, and extrapolate χ(h_top) to h_top = 0. For
# a response with a leading cubic correction the single-ladder slope is biased
# linearly in h_top, so the extrapolation is a straight line — which is exactly
# what the scan observed.

#: Shortest sub-ladder to fit. Below three points there is no secant spread to
#: judge linearity by, and the fit becomes a two-point slope with no diagnostic.
MIN_SUBLADDER = 3


def _poly_fit(h, obs, order):
    """Least-squares ``obs = a + b·h + … `` returning coefficients low-order first."""
    V = np.vander(np.asarray(h, dtype=np.float64), order + 1, increasing=True)
    coef, *_ = np.linalg.lstsq(V, np.asarray(obs, dtype=np.float64), rcond=None)
    resid = obs - V @ coef
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((obs - obs.mean()) ** 2).sum())
    return coef, (1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0)


def chi_h0(h, obs, order: int = 4) -> dict:
    """χ as the LINEAR coefficient of the response, measured where it is defined.

    Linear response is a statement about the h → 0 limit, so the estimator must
    separate the linear term from the curvature rather than average over it. The
    direct way is to fit the response itself,

        ⟨obs⟩(h) = a + b·h + c·h² + d·h³ + …

    and report ``b``. The intercept ``a`` absorbs the h = 0 baseline (assay rule
    #1); the higher terms absorb the saturation that biased K03's single-ladder
    slope by 11–33%.

    An earlier version of this function extrapolated *nested sub-ladder slopes*
    to h_top = 0 instead. On a synthetic cubic response that estimator returned
    49.1 for a true χ of 42 — it assumes the bias is linear in h_top, which
    holds for a quadratic response and not a cubic one. The negative controls in
    `test_k03_h0.py` exist because that defect was found by them and not by
    reasoning.

    Sufficiency is checked by ADDING a term, not by removing one. A response
    with genuine cubic content will disagree with a quadratic fit — and the
    cubic is the correct one there, so comparing those two would reject good
    columns. The question is instead whether the cubic is *enough*: if a quartic
    fit returns the same linear coefficient, the expansion has converged. If it
    does not, the ladder reaches too far into the nonlinear regime to determine
    b at all, and the column says so rather than picking the prettier number.
    """
    h = np.asarray(h, dtype=np.float64)
    obs = np.asarray(obs, dtype=np.float64)
    if h.size < order + 2:
        return {"chi": None, "reason": f"ladder of {h.size} points cannot "
                                       f"support an order-{order} fit"}
    coef3, r2_3 = _poly_fit(h, obs, 3)
    coef2, r2_2 = _poly_fit(h, obs, 2)
    coef4, _ = _poly_fit(h, obs, 4)
    chi3, chi2, chi4 = float(coef3[1]), float(coef2[1]), float(coef4[1])
    single = k03._ols_line(h, obs)["slope"]      # what K03's estimator would say
    disagreement = abs(chi4 - chi3) / abs(chi3) if chi3 else float("inf")
    return {
        "chi": chi3,
        "chi_quadratic": chi2,
        "chi_quartic": chi4,
        "order_disagreement": disagreement,   # cubic vs quartic
        "orders_agree": disagreement <= 0.05,
        "curvature": float(coef3[2]),
        "cubic_term": float(coef3[3]),
        "fit_r2": r2_3,
        "fit_r2_quadratic": r2_2,
        "baseline": float(coef3[0]),
        "single_ladder_chi": single,
        "bias_fraction": (1.0 - single / chi3) if chi3 else None,
        "reason": None,
    }


def run_h0(n=200_000, gamma=k03.GAMMA, eps_floor=0.005, eps_max=k03.EPS_MAX,
           n_points=8, rungs=6, dt=k03.DT, seed=42, t_floor=2500.0,
           device="cuda", progress=None) -> dict:
    """Both branches, long ladders, χ measured where linear response is defined.

    ``rungs``+1 field values per column instead of K03's four, because the
    estimator needs a ladder to extrapolate along rather than a single slope.
    """
    from . import u_k02_reach as reach
    t0 = time.time()
    eps = np.geomspace(eps_floor, eps_max, n_points)
    k_c = k03.critical_coupling(gamma)
    below, above = [], []

    for i, e in enumerate(eps):
        e = float(e)
        t_meas = max(t_floor, reach.required_t_measure(
            e, ref_eps=0.02, ref_spread=0.400, ref_t=k03.T_MEASURE,
            secant_tol=k03.SECANT_TOL, n_ratio=n / k03.N_OSCILLATORS))
        if progress:
            progress(i, len(eps), e, t_meas)
        grid_K = np.array([k_c * (1.0 - e), k_c * (1.0 + e)])
        pilot = measure_grid(
            np.concatenate([grid_K, grid_K]),
            np.concatenate([np.zeros(2), np.full(2, k03.PILOT_FIELD)]),
            n=n, gamma=gamma, dt=dt, t_burn=k03.PILOT_T_BURN,
            t_measure=k03.PILOT_T_MEASURE, seed=seed, device=device)
        chi_p = np.abs(np.array([pilot["m_mean"][2], pilot["r_mean"][3]])
                       - np.array([pilot["m_mean"][0], pilot["r_mean"][1]])
                       ) / k03.PILOT_FIELD
        h_max = np.clip(k03.TARGET_RESPONSE / np.maximum(chi_p, 1e-12),
                        k03.H_MIN, k03.H_MAX)

        fracs = np.arange(rungs + 1) / rungs
        graded = measure_grid(np.tile(grid_K, rungs + 1),
                              np.concatenate([h_max * f for f in fracs]),
                              n=n, gamma=gamma, dt=dt,
                              t_burn=t_meas * BURN_FRACTION, t_measure=t_meas,
                              seed=seed, device=device)
        H = np.concatenate([h_max * f for f in fracs])
        for j, branch in ((0, "below"), (1, "above")):
            rows = [j + k * 2 for k in range(rungs + 1)]
            obs_key = "m_mean" if branch == "below" else "r_mean"
            drift_key = "m_drift" if branch == "below" else "r_drift"
            h_ladder = H[rows]
            obs = np.asarray([graded[obs_key][r] for r in rows])
            rec = chi_h0(h_ladder, obs)
            rec.update({
                "eps": e, "K": float(grid_K[j]), "branch": branch,
                "h_ladder": h_ladder.tolist(), "obs": obs.tolist(),
                "t_measure": float(t_meas),
                "half_window_drift": float(np.max(np.abs(
                    [graded[drift_key][r] for r in rows]))),
                # A column is usable only if the ladder actually determines the
                # linear coefficient: the response must be well described, and
                # the quadratic and cubic fits must agree on b. If they do not,
                # the curvature is eating the term we came to measure.
                "ok": rec["chi"] is not None and rec["fit_r2"] > 0.999
                      and rec["orders_agree"],
            })
            (below if branch == "below" else above).append(rec)

    def _fit(cols):
        ok = [c for c in cols if c["ok"]]
        if len(ok) < k03.MIN_COLUMNS_PER_BRANCH:
            return {"gamma": None, "err": None, "r2": None,
                    "reason": f"only {len(ok)} column(s) usable "
                              f"(need {k03.MIN_COLUMNS_PER_BRANCH})"}
        return k03.branch_exponent([c["eps"] for c in ok], [c["chi"] for c in ok])

    fit_below, fit_above = _fit(below), _fit(above)
    return {
        "experiment": "K03-h0-extrapolated", "milestone": "K03", "schema": 1,
        "engine": "kuramoto_gpu", "estimator": "chi extrapolated to h=0",
        "device": gpu.device_name(), "n_oscillators": n, "rungs": rungs,
        "eps": eps.tolist(), "columns_below": below, "columns_above": above,
        "fit_below": fit_below, "fit_above": fit_above,
        "verdict": k03._verdict(fit_above, fit_below),
        "wall_seconds": time.time() - t0,
    }
