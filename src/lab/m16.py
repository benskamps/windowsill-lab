"""M16 — two-time aging after a quench in the 3D Edwards–Anderson glass.

Equilibrium dynamics is time-translation invariant: a two-time correlation
``C(t_w + dt, t_w)`` depends only on ``dt``.  A quenched glass remembers its age,
so curves taken after different waiting times separate at fixed ``dt`` and align
better against the scale-free age ``dt / t_w``.  This module measures both
competing collapses from the saved correlation table; the checker re-derives the
comparison instead of trusting the runner's cached verdict.

The dynamics is deliberately local single-spin Metropolis.  Cluster updates or
parallel-tempering swaps would erase the physical clock M16 is trying to measure.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict
from collections.abc import Mapping, Sequence


AGING_COLLAPSE_RATIO_MAX = 0.80
MIN_FIXED_LAG_SEPARATION = 0.03
MIN_WAITING_TIMES = 3
MIN_DELTA_TIMES = 4
MIN_RATIO_GROUPS = 2
MIN_DIFFERENCE_GROUPS = 4


@dataclass
class M16Config:
    L: int = 12
    T: float = 0.60
    n_realizations: int = 64
    waiting_times: tuple[int, ...] = (16, 32, 64, 128)
    delta_times: tuple[int, ...] = (8, 16, 32, 64, 128, 256)
    seed: int = 42
    device: str = "cuda"


@dataclass
class M16Result:
    waiting_times: list[int]
    delta_times: list[int]
    correlations: dict[str, list[float]]
    ratio_residual: float
    difference_residual: float
    collapse_ratio: float
    fixed_lag: int
    fixed_lag_correlations: list[float]
    fixed_lag_separation: float
    aging_resolved: bool
    wall_seconds: float
    config: dict


def _group_residual(xs, ys, *, digits: int = 8) -> tuple[float, int]:
    """Mean within-abscissa RMS scatter for groups containing >=3 curves."""
    groups: dict[float, list[float]] = {}
    for x, y in zip(xs, ys):
        if math.isfinite(float(x)) and math.isfinite(float(y)):
            groups.setdefault(round(float(x), digits), []).append(float(y))
    scatters = []
    for values in groups.values():
        if len(values) < 3:
            continue
        mean = sum(values) / len(values)
        scatters.append(math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)))
    if not scatters:
        return float("inf"), 0
    return sum(scatters) / len(scatters), len(scatters)


def _positive_int(value, *, name: str) -> int:
    """Return an exact positive integer, rejecting booleans and truncation."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if not math.isfinite(number) or not number.is_integer() or number <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(number)


def _time_grid(values, *, name: str, minimum: int) -> list[int]:
    """Validate a receipt time axis without silently sorting or deduplicating it."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be a sequence of positive integers")
    grid = [_positive_int(value, name=f"{name} value") for value in values]
    if len(grid) < minimum:
        raise ValueError(f"M16 needs >={minimum} {name.replace('_', ' ')}")
    if len(set(grid)) != len(grid):
        raise ValueError(f"{name} must contain distinct times")
    if grid != sorted(grid):
        raise ValueError(f"{name} must be strictly increasing")
    return grid


def validate_time_grids(waiting_times, delta_times) -> tuple[list[int], list[int]]:
    """Validate that an M16 clock can support both collapse diagnostics.

    Besides positive, ordered, distinct axes, the chosen grid must create at
    least two ``dt/t_w`` groups and four fixed-``dt`` groups containing three or
    more waiting-time curves. Otherwise the aging gate is impossible to resolve,
    so the runner fails before spending simulation time.
    """
    tws = _time_grid(
        waiting_times, name="waiting_times", minimum=MIN_WAITING_TIMES
    )
    dts = _time_grid(delta_times, name="delta_times", minimum=MIN_DELTA_TIMES)
    _, ratio_groups = _group_residual(
        [dt / tw for tw in tws for dt in dts],
        [0.0] * (len(tws) * len(dts)),
    )
    _, difference_groups = _group_residual(
        [dt for _tw in tws for dt in dts],
        [0.0] * (len(tws) * len(dts)),
    )
    if ratio_groups < MIN_RATIO_GROUPS:
        raise ValueError(
            "M16 time grids need >=2 repeated dt/t_w ratio groups "
            "containing >=3 curves"
        )
    if difference_groups < MIN_DIFFERENCE_GROUPS:
        raise ValueError(
            "M16 time grids need >=4 repeated delta-time groups "
            "containing >=3 curves"
        )
    return tws, dts


def validate_run_inputs(
    L, T, n_realizations, waiting_times, delta_times
) -> tuple[int, float, int, list[int], list[int]]:
    """Validate all parameters that determine M16's allocation and clock."""
    lattice_size = _positive_int(L, name="L")
    if lattice_size % 2:
        raise ValueError("M16 requires a positive even L for the periodic 3D checkerboard")
    if isinstance(T, bool):
        raise ValueError("T must be finite and > 0")
    try:
        temperature = float(T)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("T must be finite and > 0") from exc
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("T must be finite and > 0")
    realizations = _positive_int(n_realizations, name="n_realizations")
    tws, dts = validate_time_grids(waiting_times, delta_times)
    return lattice_size, temperature, realizations, tws, dts


def aging_metrics(waiting_times, delta_times, correlations) -> dict:
    """Re-derive the ratio-collapse and fixed-lag aging diagnostics.

    ``correlations`` maps each waiting time (string or int) to values parallel to
    ``delta_times``.  The function is NumPy-free by design so CI can grade a
    public receipt without the simulation stack.
    """
    tws, dts = validate_time_grids(waiting_times, delta_times)
    if not isinstance(correlations, Mapping):
        raise ValueError("M16 correlations must be a waiting-time table")

    ratios, differences, values = [], [], []
    for tw in tws:
        row = correlations.get(str(tw), correlations.get(tw))
        if (
            isinstance(row, (str, bytes))
            or not isinstance(row, Sequence)
            or len(row) != len(dts)
        ):
            raise ValueError(f"M16 missing a complete correlation row for t_w={tw}")
        for dt, value in zip(dts, row):
            if isinstance(value, bool):
                raise ValueError("M16 correlations must be finite numbers")
            try:
                correlation = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("M16 correlations must be finite numbers") from exc
            if not math.isfinite(correlation):
                raise ValueError("M16 correlations must be finite numbers")
            ratios.append(dt / tw)
            differences.append(dt)
            values.append(correlation)

    ratio_residual, ratio_groups = _group_residual(ratios, values)
    difference_residual, difference_groups = _group_residual(differences, values)
    collapse_ratio = (ratio_residual / difference_residual
                      if difference_residual > 0 else float("inf"))

    # A fixed lag common to every curve, near the geometric centre of the grid.
    fixed_lag = dts[len(dts) // 2]
    j = dts.index(fixed_lag)
    fixed = [float(correlations.get(str(tw), correlations.get(tw))[j]) for tw in tws]
    separation = fixed[-1] - fixed[0]
    return {
        "ratio_residual": ratio_residual,
        "difference_residual": difference_residual,
        "collapse_ratio": collapse_ratio,
        "ratio_groups": ratio_groups,
        "difference_groups": difference_groups,
        "fixed_lag": fixed_lag,
        "fixed_lag_correlations": fixed,
        "fixed_lag_separation": separation,
        "correlations_in_range": all(-1.0 <= value <= 1.0 for value in values),
    }


def aging_gate(metrics: Mapping) -> bool:
    """The one M16 pass gate shared by simulation and receipt verification."""
    try:
        collapse_ratio = float(metrics["collapse_ratio"])
        separation = float(metrics["fixed_lag_separation"])
        ratio_groups = int(metrics["ratio_groups"])
        difference_groups = int(metrics["difference_groups"])
        correlations_in_range = metrics["correlations_in_range"] is True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return bool(
        math.isfinite(collapse_ratio)
        and collapse_ratio <= AGING_COLLAPSE_RATIO_MAX
        and math.isfinite(separation)
        and separation >= MIN_FIXED_LAG_SEPARATION
        and ratio_groups >= MIN_RATIO_GROUPS
        and difference_groups >= MIN_DIFFERENCE_GROUPS
        and correlations_in_range
    )


def run_m16(
    L: int = 12,
    T: float = 0.60,
    n_realizations: int = 64,
    waiting_times=(16, 32, 64, 128),
    delta_times=(8, 16, 32, 64, 128, 256),
    seed: int = 42,
    device: str = "cuda",
    progress=None,
) -> M16Result:
    """Quench a 3D ±J glass and measure ``C(t_w+dt,t_w)`` on one trajectory."""
    L, T, n_realizations, tws, dts = validate_run_inputs(
        L, T, n_realizations, waiting_times, delta_times
    )

    import torch
    from .spin_glass3d import _checkerboard_masks_3d, _half_sweep_3d

    cfg = M16Config(
        L=L, T=T, n_realizations=n_realizations,
        waiting_times=tuple(tws), delta_times=tuple(dts), seed=seed, device=device,
    )
    t0 = time.time()
    dev = torch.device(device)
    rng_bond = torch.Generator(device=dev).manual_seed(seed)
    rng_spin = torch.Generator(device=dev).manual_seed(seed + 1)
    rng_step = torch.Generator(device=dev).manual_seed(seed + 2)

    shape = (n_realizations, L, L, L)
    spins = torch.randint(0, 2, shape, generator=rng_spin, device=dev,
                          dtype=torch.int8) * 2 - 1

    def bonds():
        return (torch.randint(0, 2, shape, generator=rng_bond, device=dev,
                              dtype=torch.int8) * 2 - 1).float()

    Jx, Jy, Jz = bonds(), bonds(), bonds()
    masks = _checkerboard_masks_3d(L, dev)
    beta = torch.tensor(1.0 / T, device=dev)
    references: dict[int, object] = {}
    wanted = {(tw + dt): [] for tw in tws for dt in dts}
    for tw in tws:
        for dt in dts:
            wanted[tw + dt].append((tw, dt))
    measured: dict[tuple[int, int], float] = {}
    last = max(tw + max(dts) for tw in tws)

    for sweep in range(1, last + 1):
        for mask in masks:
            spins = _half_sweep_3d(spins, beta, Jx, Jy, Jz, mask, rng_step)
        if sweep in tws:
            references[sweep] = spins.clone()
        for tw, dt in wanted.get(sweep, ()):
            ref = references.get(tw)
            if ref is None:
                raise RuntimeError(f"M16 internal clock missed t_w={tw}")
            measured[(tw, dt)] = float((ref.float() * spins.float()).mean().item())
        if progress is not None and (sweep in tws or sweep == last):
            progress(sweep, last)

    if dev.type == "cuda":
        torch.cuda.synchronize(dev)
    correlations = {
        str(tw): [measured[(tw, dt)] for dt in dts]
        for tw in tws
    }
    metrics = aging_metrics(tws, dts, correlations)
    resolved = aging_gate(metrics)
    return M16Result(
        waiting_times=tws,
        delta_times=dts,
        correlations=correlations,
        ratio_residual=metrics["ratio_residual"],
        difference_residual=metrics["difference_residual"],
        collapse_ratio=metrics["collapse_ratio"],
        fixed_lag=metrics["fixed_lag"],
        fixed_lag_correlations=metrics["fixed_lag_correlations"],
        fixed_lag_separation=metrics["fixed_lag_separation"],
        aging_resolved=resolved,
        wall_seconds=time.time() - t0,
        config=asdict(cfg),
    )


def to_report(result: M16Result) -> dict:
    status = "pass" if result.aging_resolved else "null"
    return {
        "experiment": "M16-spin-glass-aging",
        "headline": (
            f"3D glass aging: t/t_w collapse residual is {result.collapse_ratio:.2f}× "
            f"the fixed-lag residual; ΔC={result.fixed_lag_separation:+.3f} at "
            f"Δt={result.fixed_lag}"
        ),
        "status": status,
        "waiting_times": result.waiting_times,
        "delta_times": result.delta_times,
        "correlations": result.correlations,
        "ratio_residual": result.ratio_residual,
        "difference_residual": result.difference_residual,
        "collapse_ratio": result.collapse_ratio,
        "fixed_lag": result.fixed_lag,
        "fixed_lag_correlations": result.fixed_lag_correlations,
        "fixed_lag_separation": result.fixed_lag_separation,
        "aging_resolved": result.aging_resolved,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
        "claim_boundary": (
            "A finite-size, finite-time nonequilibrium calibration: it distinguishes aging "
            "from time-translation invariance but is not a universal scaling-function claim."
        ),
    }
