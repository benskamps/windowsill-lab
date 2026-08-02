"""Coupled phase oscillators — the engine behind the K (coherence) track.

Every M-track milestone asks when a lattice of *spins* agrees. The K track asks
the same question of **clocks**: N oscillators, each running at its own natural
frequency ``ω_i``, each nudged toward its neighbours' phase. Kuramoto's model is
the canonical answer,

    dθ_i/dt = ω_i + (K/N) · Σ_j sin(θ_j − θ_i)

and its order parameter is a single complex number — the centroid of the
oscillators on the unit circle,

    r(t) · e^{iψ(t)} = (1/N) · Σ_j e^{iθ_j(t)}

with ``r = 0`` for a scattered crowd and ``r = 1`` for perfect lockstep. Below a
critical coupling the crowd never agrees; above it a macroscopic fraction of the
oscillators lock onto the mean phase and ``r`` becomes finite. That is the
synchronization transition, and it is the K track's Onsager point.

### Why the coupling is O(N), not O(N²)

The pair sum collapses exactly. Substituting the definition of ``r e^{iψ}``,

    (K/N) · Σ_j sin(θ_j − θ_i) = K · r · sin(ψ − θ_i)

so each oscillator only ever sees the *mean field* ``(r, ψ)``. Every oscillator's
drift is then one centroid reduction plus one elementwise update — O(N) per step
instead of O(N²), which is what makes a 2000-oscillator sweep a NumPy job rather
than a GPU one. Expanded once more for the code below,

    r · sin(ψ − θ_i) = s · cos θ_i − c · sin θ_i,   c = ⟨cos θ⟩, s = ⟨sin θ⟩

so a step costs exactly two transcendental evaluations per stage.

### The exact answer this engine has to reproduce

For natural frequencies drawn from a Lorentzian (Cauchy) density of half-width γ
centred on zero,

    g(ω) = γ / (π · (ω² + γ²))

Kuramoto's self-consistency condition ``r = K r ∫ g(ω) √(1 − (ω/Kr)²) dω`` is
solvable in closed form in the N → ∞ limit, and gives two exact statements:

    K_c = 2 / (π · g(0)) = 2γ                      the critical coupling
    r(K) = √(1 − K_c/K)      for K > K_c           the whole ordered branch

The second is stronger than the first — it is a *curve*, not a point, with
nothing fitted — which is why ``mean_field_r`` is carried here as an independent
anchor alongside the transition itself (the same role random deposition's exact
``w² = p(1−p)t`` plays in ``kpz.py``).

### Reproducibility: quantile frequencies, not sampled ones

The natural frequencies are drawn by **inverse-CDF quantile sampling** on the
deterministic grid ``u_i = (i + ½)/N`` rather than from a random generator:

    F(ω) = ½ + (1/π)·arctan(ω/γ)   ⇒   ω_i = γ · tan(π · (u_i − ½))

This is reproducible without a seed, and — because the grid is symmetric about
½ — the frequency set is exactly antisymmetric, so ``Σ ω_i = 0`` identically and
the mean phase ψ has no spurious drift to integrate. It also removes the
sampling noise a finite random draw would add on top of the finite-size effect
this milestone is trying to measure.

**The tails are clipped**, at ``|ω| ≤ 40γ``. A Lorentzian has no finite variance,
so the outermost quantiles run to ``|ω| ≈ γN/π`` — at N=2000 that is ω ≈ 637, and
with dt = 0.01 such an oscillator advances 6.4 rad per step: aliased, and (worse)
an ω landing near 2π/dt would appear *stationary* in the sampled dynamics and
could lock spuriously. Clipping — as opposed to truncating and renormalizing —
leaves ``g(0)`` exactly unchanged, so the exact ``K_c = 2/(π g(0)) = 2γ`` this
engine is graded against does not move. The clipped oscillators (≈1.6% of the
population at 40γ) sit at |ω| = 40γ ≫ K·r over the whole swept range and cannot
lock anywhere in it, so the physics near the transition is untouched.

NumPy only — the mean-field collapse makes this a CPU-scale problem.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Half-width of the Lorentzian natural-frequency distribution. Sets the whole
# scale of the problem: the exact critical coupling is 2γ.
GAMMA = 0.5
# K_c / γ for a Lorentzian g(ω) — the exact infinite-N mean-field result.
KC_OVER_GAMMA = 2.0
# Where the Lorentzian tails are clipped, in units of γ. See the module docstring:
# clipping preserves g(0) (and therefore K_c) exactly while bounding |ω|·dt.
OMEGA_CLIP_SCALE = 40.0
# Integration step. |ω|·dt ≤ 40γ·dt = 0.2 rad at the defaults — comfortably inside
# the RK4 stability and sampling regime for the fastest drifter in the population.
DT = 0.01


def critical_coupling(gamma: float = GAMMA) -> float:
    """The exact infinite-N mean-field critical coupling ``K_c = 2γ``."""
    return KC_OVER_GAMMA * gamma


def lorentzian_frequencies(
    n: int, gamma: float = GAMMA, clip_scale: float = OMEGA_CLIP_SCALE,
) -> np.ndarray:
    """Deterministic inverse-CDF Lorentzian quantiles, symmetric and tail-clipped.

    ``n`` must be even so the grid ``(i+½)/n`` pairs u with 1−u exactly and the
    returned frequencies sum to zero identically. Raises rather than silently
    returning a drifting population.
    """
    if n < 4:
        raise ValueError("Kuramoto needs at least 4 oscillators")
    if n % 2:
        raise ValueError("n must be even so the frequency set is exactly symmetric")
    if gamma <= 0:
        raise ValueError("the Lorentzian half-width γ must be positive")
    u = (np.arange(n, dtype=np.float64) + 0.5) / n
    omega = gamma * np.tan(np.pi * (u - 0.5))
    bound = clip_scale * gamma
    return np.clip(omega, -bound, bound)


def order_parameter(theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(r, ψ)`` — the centroid of the oscillators on the unit circle.

    Reduces over the LAST axis, so a ``(n_K, N)`` phase block returns one
    ``(r, ψ)`` pair per coupling in a single call.
    """
    c = np.cos(theta).mean(axis=-1)
    s = np.sin(theta).mean(axis=-1)
    return np.hypot(c, s), np.arctan2(s, c)


def _drift(theta: np.ndarray, omega: np.ndarray, coupling: np.ndarray) -> np.ndarray:
    """``dθ/dt = ω + K·r·sin(ψ − θ)`` via the O(N) mean-field form."""
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    c = cos_t.mean(axis=-1, keepdims=True)
    s = sin_t.mean(axis=-1, keepdims=True)
    # r·sin(ψ−θ) = ⟨sin θ⟩·cos θ − ⟨cos θ⟩·sin θ
    return omega + coupling * (s * cos_t - c * sin_t)


def rk4_step(
    theta: np.ndarray, omega: np.ndarray, coupling: np.ndarray, dt: float,
) -> np.ndarray:
    """One classical fixed-step RK4 step of the phase dynamics.

    The system is autonomous, so all four stages evaluate the same ``_drift``;
    each stage recomputes the mean field from that stage's phases (using the
    stage-start centroid instead would silently demote this to Euler).
    """
    k1 = _drift(theta, omega, coupling)
    k2 = _drift(theta + 0.5 * dt * k1, omega, coupling)
    k3 = _drift(theta + 0.5 * dt * k2, omega, coupling)
    k4 = _drift(theta + dt * k3, omega, coupling)
    return theta + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def mean_field_r(coupling, gamma: float = GAMMA) -> np.ndarray:
    """The exact infinite-N ordered branch ``r(K) = √(1 − K_c/K)``, 0 below K_c.

    A closed form with nothing fitted — the K track's strongest anchor, and the
    one an estimator bug cannot fake: reproducing a *curve* over many couplings
    is a much harder target than landing one peak.
    """
    k = np.asarray(coupling, dtype=np.float64)
    k_c = critical_coupling(gamma)
    with np.errstate(divide="ignore", invalid="ignore"):
        branch = np.sqrt(np.clip(1.0 - k_c / np.where(k > 0, k, np.nan), 0.0, 1.0))
    return np.where(k > k_c, branch, 0.0)


@dataclass
class SweepResult:
    """One coupling sweep: the time-averaged coherence and its fluctuation."""

    K: np.ndarray          # the swept couplings
    r_mean: np.ndarray     # ⟨r⟩ time-averaged after burn-in, per coupling
    r_var: np.ndarray      # Var_t(r) over the same window, per coupling
    chi: np.ndarray        # N·Var_t(r) — the susceptibility-style fluctuation
    n: int
    gamma: float
    dt: float
    t_burn: float
    t_measure: float
    n_samples: int
    seed: int


def run_sweep(
    K: np.ndarray | list[float],
    n: int = 2000,
    gamma: float = GAMMA,
    dt: float = DT,
    t_burn: float = 200.0,
    t_measure: float = 400.0,
    sample_every: int = 10,
    seed: int = 42,
    progress=None,
) -> SweepResult:
    """Integrate every coupling in ``K`` at once and measure ⟨r⟩ and N·Var(r).

    All couplings share one ``(n_K, N)`` phase block, one frequency set, and one
    seeded random initial condition, so the sweep is a controlled comparison:
    the only thing that differs between columns of the result is K.

    ``r`` is sampled every ``sample_every`` steps over the measurement window and
    reduced to its mean and variance; the raw series is deliberately not kept
    (a 25×4000 table would dominate the public receipt without adding evidence
    the check uses).
    """
    couplings = np.asarray(K, dtype=np.float64).reshape(-1)
    if couplings.size < 3:
        raise ValueError("a coupling sweep needs at least three points")
    if np.any(couplings < 0):
        raise ValueError("coupling K must be non-negative")
    if dt <= 0 or t_burn < 0 or t_measure <= 0:
        raise ValueError("dt and the measurement window must be positive")
    if sample_every < 1:
        raise ValueError("sample_every must be at least one step")

    omega = lorentzian_frequencies(n, gamma)
    rng = np.random.default_rng(seed)
    # One random initial condition, replicated across couplings: every column
    # starts from the SAME scattered crowd, so a difference in the answer is a
    # difference in K and nothing else.
    theta = np.repeat(
        rng.uniform(0.0, 2.0 * np.pi, size=n)[None, :], couplings.size, axis=0,
    )
    column = couplings[:, None]

    n_burn = int(round(t_burn / dt))
    n_meas = int(round(t_measure / dt))
    for step in range(n_burn):
        theta = rk4_step(theta, omega, column, dt)
        if progress is not None and step % 2000 == 0:
            progress("burn-in", step, n_burn)

    total = np.zeros(couplings.size)
    total_sq = np.zeros(couplings.size)
    samples = 0
    for step in range(n_meas):
        theta = rk4_step(theta, omega, column, dt)
        if step % sample_every == 0:
            r, _ = order_parameter(theta)
            total += r
            total_sq += r * r
            samples += 1
        if progress is not None and step % 2000 == 0:
            progress("measure", step, n_meas)

    r_mean = total / samples
    # Population variance over the sampled window; ``samples`` is in the
    # thousands, so the 1/N vs 1/(N−1) distinction is far below the physical
    # scatter and the simpler form keeps the check's re-derivation exact.
    r_var = np.maximum(total_sq / samples - r_mean * r_mean, 0.0)
    return SweepResult(
        K=couplings,
        r_mean=r_mean,
        r_var=r_var,
        chi=n * r_var,
        n=n,
        gamma=gamma,
        dt=dt,
        t_burn=t_burn,
        t_measure=t_measure,
        n_samples=samples,
        seed=seed,
    )


def refine_peak(x, y) -> float:
    """Sub-grid peak location via a 3-point parabola through the argmax.

    The same rule ``m06.refine_peak`` uses for a χ peak in temperature, applied
    here to a χ peak in coupling — so the K track locates its transition with
    the estimator the M track already trusts. Falls back to the discrete argmax
    when the peak sits on an endpoint.
    """
    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    i = int(np.argmax(ys))
    if 0 < i < xs.size - 1:
        y0, y1, y2 = ys[i - 1], ys[i], ys[i + 1]
        denom = y0 - 2.0 * y1 + y2
        if denom != 0:
            return float(xs[i] + 0.5 * (y0 - y2) / denom * (xs[i] - xs[i - 1]))
    return float(xs[i])


def steepest_slope_crossing(x, y) -> float:
    """Where ``dy/dx`` is largest — the coupling at which coherence turns on fastest.

    The cross-check estimator: a central-difference slope on the (K, ⟨r⟩) curve,
    with the same 3-point parabola refinement applied to the slope's own peak.
    It reads a different feature of the sweep than the fluctuation peak does, so
    the two agreeing is evidence and the two disagreeing wildly is a bug.
    """
    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    if xs.size < 3:
        raise ValueError("a slope crossing needs at least three points")
    slope = np.gradient(ys, xs)
    return refine_peak(xs, slope)
