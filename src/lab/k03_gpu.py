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
