"""U-K02 reach test — can this box settle Daido vs Hong, and what would it cost?

U-K01 established that K03's ε window sits outside the critical scaling regime
and that the *subcritical* branch — the only one carrying any discriminating
power — cannot be measured there at all. This runner asks the next question,
and asks it before spending a single GPU-hour: **what would it take, and does
this box have it?**

## The chain of measured facts it rests on

1. Daido and Hong predict the same supercritical γ = 1/4. All discrimination
   lives in γ' below K_c, where the gap is Δγ' = 0.75.
2. K03 achieved stderr 0.0177 on a branch it could measure — a **42σ**
   separation against that gap. Precision was never the blocker.
3. The subcritical gate refusals are *not* saturation. Saturating secants fall
   monotonically; these rise and scatter, which is noise. And ε = 0.127 was
   refused while ε = 0.08 — closer to K_c — passed, so the gate is thresholding
   a noisy statistic and its passes are partly luck.
4. Fitting the implied noise against ε gives **noise ~ ε^-0.76**: the
   correlation time diverges approaching K_c while ``T_MEASURE`` stays pinned at
   2000 for every column. Textbook critical slowing down, unbudgeted.

## Why N is the lever and T is not

The statistical error on ⟨cos θ⟩ falls as ``1/sqrt(N · T/τ)``, so N and T trade
evenly in total *work*. They do not trade evenly in *wall-clock*: time is
strictly serial, while N is embarrassingly parallel. `kuramoto.py` collapses the
pair sum to a mean field, making each step O(N) — and its docstring concluded
that this "makes a 2000-oscillator sweep a NumPy job rather than a GPU one."

That was correct when 2000 was the target. Measured on this box today, it stops
being correct somewhere below N = 20,000, and by N = 200,000 the GPU is 33×
faster than NumPy — 100× the oscillators for ~2.6× the wall-clock, which buys a
10× noise reduction that would otherwise cost 100× the measurement time.

An out-of-reach verdict here would mean the disagreement is not settleable on
this hardware, which is worth knowing before a night is spent finding out.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

#: From the fit against the committed receipt's subcritical secant spreads.
#: Not a theoretical exponent — a measured property of this engine at this N and
#: T, and it is used only to extrapolate one decade, which is about as far as a
#: seven-point fit should ever be asked to carry.
NOISE_EPS_EXPONENT = -0.76

#: Aim at half the gate tolerance, not at it. A column that lands exactly on the
#: threshold passes or fails on the draw — which is precisely the luck the
#: 2026-08-23 run exhibited, and the reason its passes cannot be trusted.
SAFETY = 0.5

#: Measured on this box, 2026-08-24, RK4 with float64, seconds per step.
#: Recorded rather than assumed because the whole verdict turns on it.
STEP_SECONDS = {2_000: 203e-6, 20_000: 1737e-6, 200_000: 17680e-6}   # numpy CPU
GPU_STEP_SECONDS = {2_000: 306e-6, 20_000: 310e-6,
                    200_000: 527e-6, 2_000_000: 3245e-6}


def spread_at(eps: float, *, ref_eps: float, ref_spread: float,
              n_ratio: float = 1.0, t_ratio: float = 1.0) -> float:
    """Predicted secant spread at ``eps`` after scaling N and T.

    Two separable effects: the ε-dependence measured above, and the
    ``1/sqrt(N·T)`` improvement bought by more oscillators or more time.
    """
    eps_factor = (eps / ref_eps) ** NOISE_EPS_EXPONENT
    return ref_spread * eps_factor / math.sqrt(max(n_ratio * t_ratio, 1e-12))


def required_t_measure(eps: float, *, ref_eps: float, ref_spread: float,
                       ref_t: float, secant_tol: float, n_ratio: float) -> float:
    """Measurement time needed at ``eps`` to land at ``SAFETY`` × tolerance."""
    target = secant_tol * SAFETY
    have = spread_at(eps, ref_eps=ref_eps, ref_spread=ref_spread, n_ratio=n_ratio)
    return ref_t * (have / target) ** 2 if have > target else ref_t


def _interp_step_seconds(n: int, table: dict) -> float:
    """Per-step cost at N, log-interpolated between measured points.

    Extrapolation past the measured range is refused — the whole point of the
    benchmark is that the cost curve changes shape (launch-bound to
    bandwidth-bound), so guessing beyond it would defeat the exercise.
    """
    keys = sorted(table)
    if n in table:
        return table[n]
    if n < keys[0] or n > keys[-1]:
        raise ValueError(f"N={n} is outside the benchmarked range {keys[0]}-{keys[-1]}")
    lo = max(k for k in keys if k <= n)
    hi = min(k for k in keys if k >= n)
    f = (math.log(n) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return math.exp(math.log(table[lo]) * (1 - f) + math.log(table[hi]) * f)


def project(receipt: Path, *, n_target: int = 200_000, eps_floor: float = 0.005,
            eps_points: int = 8, dt: float = 0.01, ladder_rungs: int = 3,
            burn_fraction: float = 0.4, budget_hours: float = 8.0) -> dict:
    """Price a run that could actually measure γ' — from committed bytes only."""
    from . import k03

    d = json.loads(receipt.read_text(encoding="utf-8"))
    below = [c for c in d.get("columns_below", []) if c.get("secant_spread")]
    if not below:
        return {"unknown": "U-K02", "reach": "out-of-reach",
                "detail": "the receipt records no subcritical secant spreads to "
                          "extrapolate from — reach cannot be estimated"}
    ref = min(below, key=lambda c: c["eps"])         # the hardest column measured
    ref_eps, ref_spread = ref["eps"], ref["secant_spread"]
    n_ratio = n_target / k03.N_OSCILLATORS

    eps_grid = [eps_floor * (k03.EPS_MAX / eps_floor) ** (i / (eps_points - 1))
                for i in range(eps_points)]
    rows, total_time_units = [], 0.0
    for eps in eps_grid:
        t_meas = required_t_measure(
            eps, ref_eps=ref_eps, ref_spread=ref_spread, ref_t=k03.T_MEASURE,
            secant_tol=k03.SECANT_TOL, n_ratio=n_ratio)
        t_burn = t_meas * burn_fraction
        # both branches, each with an h=0 baseline plus the ladder rungs
        per_column = (t_burn + t_meas) * (ladder_rungs + 1) * 2
        total_time_units += per_column
        rows.append({
            "eps": eps,
            "spread_predicted": spread_at(eps, ref_eps=ref_eps,
                                          ref_spread=ref_spread,
                                          n_ratio=n_ratio,
                                          t_ratio=t_meas / k03.T_MEASURE),
            "t_measure": t_meas,
        })

    steps = total_time_units / dt
    gpu_hours = steps * _interp_step_seconds(n_target, GPU_STEP_SECONDS) / 3600
    cpu_hours = steps * _interp_step_seconds(
        min(n_target, max(STEP_SECONDS)), STEP_SECONDS) / 3600

    fits = gpu_hours <= budget_hours
    if fits:
        detail = (
            f"a grid reaching ε = {eps_floor:g} at N = {n_target:,} costs "
            f"**{gpu_hours:.1f} GPU-hours** — inside a {budget_hours:g}-hour "
            f"night. The same statistics on the CPU engine would take "
            f"{cpu_hours:.0f} hours. Precision was never the blocker (42σ "
            f"available against Δγ' = 0.75); the blocker was an engine sized "
            f"for N = 2,000 on a box whose GPU is idle")
    else:
        detail = (
            f"ε = {eps_floor:g} at N = {n_target:,} costs {gpu_hours:.1f} "
            f"GPU-hours, past a {budget_hours:g}-hour night. Raise the ε floor "
            f"or split the grid across nights — but do NOT trim T_MEASURE, "
            f"which is the one axis that cannot be cut without reopening the "
            f"noise problem this run exists to close")
    return {
        "unknown": "U-K02",
        "receipt": receipt.name,
        "reference_column": {"eps": ref_eps, "spread": ref_spread},
        "n_target": n_target, "n_ratio": n_ratio,
        "eps_floor": eps_floor, "grid": rows,
        "total_time_units": total_time_units, "steps": steps,
        "gpu_hours": gpu_hours, "cpu_hours": cpu_hours,
        "speedup_vs_cpu": cpu_hours / gpu_hours if gpu_hours else None,
        "reach": "in-reach" if fits else "out-of-reach",
        "detail": detail,
    }
