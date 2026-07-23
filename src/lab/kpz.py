"""Kinetic roughening on a ring — the 1+1d growth engine behind M17 (KPZ).

Every earlier milestone watches *spins*. M17 watches a **surface**: a one-dimensional
interface ``h(x, t)`` wrapping a periodic ring, growing upward in Monte-Carlo time. The
question is not where a transition sits but which **universality class** the roughening
belongs to — and that class is read off two exponents in the Family–Vicsek scaling form

    w(L, t)  ∼  t^β          (early, before the correlation length reaches L)
    w(L, t)  ∼  L^α          (late, saturated)
    z = α / β                (dynamic exponent; ξ(t) ∼ t^{1/z})

where ``w`` is the interface width, the RMS deviation of ``h`` from its own mean.

### Three models, one measurement pipeline

The whole point of this module is that **the same width estimator and the same fit rule**
are pointed at three microscopically different growth rules whose exponents are known
*exactly and differently*. That is the negative control: a pipeline that reported KPZ's
β = 1/3 for all three would be broken, and would be caught here rather than believed.

| model | rule | β (exact) | α (exact) | saturates? |
|---|---|---|---|---|
| ``random_deposition``  | independent Bernoulli drops, no relaxation | **1/2** | — | **never** |
| ``edwards_wilkinson``  | linear (diffusive) relaxation + noise      | **1/4** | 1/2 | yes |
| ``single_step`` (KPZ)  | nonlinear, slope-constrained corner growth | **1/3** | 1/2 | yes |

Random deposition is the strongest anchor of the three because it is not merely an
exponent but a **closed form**: with drop probability ``p`` per site per sweep the columns
are independent binomials, so

    w²(t) = p (1 − p) t          exactly, at every t, with no fitting.

That is an exact curve the engine must land on, not a slope it can approximately match —
the same flavour of anchor as Onsager's T_c in M01 or Wannier's 0.3383 in M13.

### The KPZ model: single-step (corner) growth, sublattice-parallel

Heights live on a ring of ``L`` sites (``L`` even) under the **single-step constraint**

    h_{i+1} − h_i = ±1     for every bond,

i.e. the interface is a zig-zag path. The only move is a **corner flip**: a local minimum
(``h_{i−1} = h_{i+1} = h_i + 1``) becomes a local maximum, ``h_i → h_i + 2``, attempted with
probability ``p`` per site per half-sweep. This is the standard single-step growth model —
equivalent to the totally asymmetric exclusion process (TASEP) under the usual slope↔particle
map ``n_i = (1 + h_{i+1} − h_i)/2`` — and it is the textbook lattice representative of the KPZ
class in 1+1 dimensions, because the growth velocity depends on the local slope quadratically
(exactly the ``(∇h)²`` nonlinearity KPZ is named for).

Two implementation notes that are load-bearing:

* **Sublattice-parallel updates are exact here, not an approximation.** Sites of one parity
  are never adjacent, so flipping all eligible even sites simultaneously can never produce a
  conflict or violate the single-step constraint — the same checkerboard argument that makes
  ``ising.py``'s red/black sweep exact. One *sweep* = one even half-step + one odd half-step.
* **``p`` must be < 1.** At ``p = 1`` the sublattice-parallel rule degenerates into a
  deterministic cellular automaton (Rule-184-like), whose interface grows ballistically with
  *no* stochastic roughening — the noise that makes it KPZ is gone. ``P_FLIP = 0.5`` by default.

Because ``h_i`` only ever changes by 2, each site keeps its initial parity forever: the
interface carries a permanent ±½ sawtooth. That is an **O(1) additive floor on w²**, harmless
once ``w ≫ 1`` but the reason the fit window in ``m17.py`` starts above a width threshold
rather than at ``t = 1``. It is documented, not hidden.

### Two initial conditions — flat and droplet

The exponents do not care about the initial condition; the **fluctuation distribution** does.
This is the sharpest known fact about 1+1d KPZ: the rescaled height

    χ = ( h(t) − v_∞ t ) / (Γ t)^{1/3}

converges to a *different* Tracy–Widom law depending on the macroscopic geometry —
**GOE** Tracy–Widom from a flat interface, **GUE** Tracy–Widom from a curved (droplet) one.

* ``flat_heights`` — the zig-zag ``h_i = i mod 2``. Flat geometry → GOE-TW.
* ``droplet_heights`` — the wedge ``h_i = |i − L/2|``, a single corner at the centre. Growth
  nucleates there and spreads outward, so the interface is macroscopically curved → GUE-TW.
  The wedge only stays a wedge while the active region is inside the ring, which sets the
  hard budget ``L > 4 t`` (the corner front advances at most one site per half-step in each
  direction); ``m17.py`` enforces it.

``skewness``/``excess_kurtosis`` are used to grade the distribution because they are
**invariant under the affine rescaling above** — ``v_∞`` and ``Γ`` are deterministic model
constants, and shifting/scaling a random variable leaves its standardised third and fourth
moments alone. So the Tracy–Widom shape can be tested *without* knowing either constant, which
would otherwise have to be fitted (and a fitted constant is exactly the kind of free knob this
lab refuses).

Stdlib + NumPy only; a ``batch`` axis carries independent realisations so the ensemble average
is one tensor op.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

# Corner-flip probability for the single-step KPZ model. Strictly inside (0, 1): at p = 1 the
# sublattice-parallel rule is deterministic and the surface stops being stochastically rough.
P_FLIP = 0.5

# ── Exactly-known targets. These are literature/derivation constants, never fitted here. ──
# 1+1d KPZ (Kardar–Parisi–Zhang 1986): the growth and roughness exponents are exact.
KPZ_BETA = 1.0 / 3.0
KPZ_ALPHA = 0.5
KPZ_Z = KPZ_ALPHA / KPZ_BETA          # = 3/2
# 1+1d Edwards–Wilkinson (linear theory) — the control class one nonlinearity away from KPZ.
EW_BETA = 0.25
EW_ALPHA = 0.5
# Random deposition: independent columns, no correlations at all.
RD_BETA = 0.5

# Tracy–Widom standardised moments (Bornemann 2010, high-precision quadrature of the
# Painlevé-II Fredholm determinants). Only skewness and excess kurtosis are used, because
# they survive the unknown (v_inf, Gamma) affine rescaling.
TW_GUE_SKEW = 0.2241
TW_GUE_EXKURT = 0.0935
TW_GOE_SKEW = 0.2935
TW_GOE_EXKURT = 0.1652


# ────────────────────────────── initial conditions ──────────────────────────────
def flat_heights(batch: int, L: int) -> np.ndarray:
    """The flat (zig-zag) initial condition: ``h_i = i mod 2``, every bond a ±1 step.

    Macroscopically flat, so every site is statistically equivalent and the one-point height
    fluctuation is expected to converge to **GOE** Tracy–Widom.
    """
    if L % 2:
        raise ValueError("single-step growth needs an even ring length L")
    row = (np.arange(L, dtype=np.int64) % 2)
    return np.tile(row, (batch, 1))


def droplet_heights(batch: int, L: int) -> np.ndarray:
    """The droplet (wedge) initial condition: ``h_i = |i − L/2|``.

    A single corner at the ring centre. Growth nucleates there and spreads outward, so the
    interface is macroscopically **curved** — the geometry whose height fluctuation is
    expected to converge to **GUE** Tracy–Widom. Valid only while the growing region has not
    wrapped the ring (see ``droplet_time_budget``).
    """
    if L % 2:
        raise ValueError("single-step growth needs an even ring length L")
    x = np.arange(L, dtype=np.int64)
    row = np.abs(x - L // 2)
    return np.tile(row, (batch, 1))


def droplet_time_budget(L: int) -> int:
    """Largest number of sweeps a droplet run may take on a ring of ``L`` sites.

    Each half-step can advance the active corner region by at most one site in each direction,
    so a sweep costs at most 2 sites per side: the two fronts meet after ``L/4`` sweeps. Past
    that the geometry silently stops being a droplet and the distribution stops being the one
    being tested — so this is a hard budget, checked rather than hoped for.
    """
    return max(1, L // 4)


def is_single_step(h: np.ndarray) -> bool:
    """True iff every bond of every ring in ``h`` is a ±1 step (the model's invariant)."""
    d = np.diff(np.concatenate([h, h[:, :1]], axis=1), axis=1)
    return bool(np.all(np.abs(d) == 1))


# ────────────────────────────── the growth rules ──────────────────────────────
def single_step_half_sweep(h: np.ndarray, parity: int, p: float, rng: np.random.Generator) -> None:
    """One sublattice half-step of single-step (corner) growth, **in place**.

    Every site ``i ≡ parity (mod 2)`` that is a local minimum (``h_{i−1} = h_{i+1} = h_i + 1``)
    flips up by 2 with probability ``p``. Same-parity sites are never adjacent, so doing them
    all at once is exact — no conflict can arise and the single-step constraint is preserved
    (a local minimum becomes a local maximum, and both bonds stay ±1).
    """
    left = np.roll(h, 1, axis=1)
    right = np.roll(h, -1, axis=1)
    is_min = (left == h + 1) & (right == h + 1)
    sub = is_min[:, parity::2]
    fire = sub & (rng.random(sub.shape) < p)
    h[:, parity::2] += 2 * fire


def single_step_sweep(h: np.ndarray, p: float, rng: np.random.Generator) -> None:
    """One full sweep = even half-step then odd half-step. The unit of MC time for M17."""
    single_step_half_sweep(h, 0, p, rng)
    single_step_half_sweep(h, 1, p, rng)


def random_deposition_sweep(h: np.ndarray, p: float, rng: np.random.Generator) -> None:
    """Independent Bernoulli(``p``) drop on every column — no relaxation, no correlations.

    Each column is its own binomial random walk, so ``w²(t) = p(1−p)·t`` **exactly**. The
    control with a closed form, not just an exponent.
    """
    h += (rng.random(h.shape) < p)


def edwards_wilkinson_step(h: np.ndarray, nu: float, D: float, dt: float,
                           rng: np.random.Generator) -> None:
    """One explicit Euler step of the Edwards–Wilkinson equation, **in place**.

    ``∂_t h = ν ∇²h + η`` with ``⟨ηη⟩ = 2D δδ``. The linear theory: identical to KPZ except
    for the missing ``(λ/2)(∇h)²`` term, and that single missing nonlinearity moves β from
    1/3 to **1/4** — which is exactly why it is the sharpest control in the set. Stability of
    the explicit scheme needs ``ν dt ≤ 1/2`` on a unit lattice; ``m17`` uses ν=1, dt=0.1.
    """
    lap = np.roll(h, 1, axis=1) + np.roll(h, -1, axis=1) - 2.0 * h
    h += nu * dt * lap + math.sqrt(2.0 * D * dt) * rng.standard_normal(h.shape)


# ────────────────────────────── observables ──────────────────────────────
def interface_width(h: np.ndarray) -> float:
    """Ensemble-averaged interface width ``w = ⟨ sqrt( ⟨(h−h̄)²⟩_x ) ⟩_batch``.

    The per-realisation mean is subtracted *before* averaging over the batch — the width
    measures roughness, not the (large, deterministic) overall rise of the surface. Averaging
    the width itself rather than w² keeps the estimator directly comparable across models.
    """
    hf = h.astype(np.float64)
    var = np.mean((hf - hf.mean(axis=1, keepdims=True)) ** 2, axis=1)
    return float(np.mean(np.sqrt(var)))


def width_squared(h: np.ndarray) -> float:
    """Ensemble-averaged ``w²`` — the quantity with the exact random-deposition closed form."""
    hf = h.astype(np.float64)
    return float(np.mean((hf - hf.mean(axis=1, keepdims=True)) ** 2))


def skewness(x: np.ndarray) -> float:
    """Standardised third moment. Invariant under ``x → (x − a)/b`` for constants a, b>0."""
    v = np.asarray(x, dtype=np.float64).ravel()
    c = v - v.mean()
    s = c.std()
    return float(np.mean(c ** 3) / s ** 3) if s > 0 else 0.0


def excess_kurtosis(x: np.ndarray) -> float:
    """Standardised fourth moment minus 3 (so a Gaussian scores 0). Same affine invariance."""
    v = np.asarray(x, dtype=np.float64).ravel()
    c = v - v.mean()
    s = c.std()
    return float(np.mean(c ** 4) / s ** 4 - 3.0) if s > 0 else 0.0


def log_spaced_times(t_max: int, n_times: int) -> list[int]:
    """Ascending, de-duplicated, log-spaced measurement sweeps in ``[1, t_max]``."""
    raw = np.unique(np.round(np.geomspace(1, max(t_max, 2), n_times)).astype(int))
    return [int(t) for t in raw if 1 <= t <= t_max]


# ────────────────────────────── run drivers ──────────────────────────────
@dataclass
class GrowthRun:
    model: str
    L: int
    batch: int
    times: list          # measurement sweeps
    width: list          # w(t)
    width_sq: list       # w²(t)
    wall_seconds: float
    config: dict = field(default_factory=dict)


def run_growth(model: str, L: int = 2048, batch: int = 64, t_max: int = 4000,
               n_times: int = 40, seed: int = 42, p: float = P_FLIP,
               nu: float = 1.0, D: float = 1.0, dt: float = 0.1,
               progress=None) -> GrowthRun:
    """Grow a flat interface under ``model`` and record ``w(t)`` at log-spaced sweeps.

    ``model`` ∈ {``"kpz"`` (single-step corner growth), ``"ew"`` (Edwards–Wilkinson),
    ``"rd"`` (random deposition)}. All three share this driver, this width estimator, and
    (in ``m17.py``) this fit rule — which is what makes the exponent separation between them
    a control rather than three unrelated runs.

    For ``"ew"`` one recorded sweep is one unit of EW time (``1/dt`` Euler steps), so the
    x-axis is a physical time in every model and the exponent stays comparable.
    """
    t0 = time.time()
    rng = np.random.default_rng(seed)
    if model == "kpz":
        h = flat_heights(batch, L)
    elif model == "rd":
        h = np.zeros((batch, L), dtype=np.int64)
    elif model == "ew":
        h = np.zeros((batch, L), dtype=np.float64)
    else:
        raise ValueError(f"unknown growth model {model!r} (expected 'kpz', 'ew' or 'rd')")

    marks = log_spaced_times(t_max, n_times)
    want = set(marks)
    times, width, width_sq = [], [], []
    sub_steps = max(1, int(round(1.0 / dt))) if model == "ew" else 1
    for t in range(1, t_max + 1):
        if model == "kpz":
            single_step_sweep(h, p, rng)
        elif model == "rd":
            random_deposition_sweep(h, p, rng)
        else:
            for _ in range(sub_steps):
                edwards_wilkinson_step(h, nu, D, dt, rng)
        if t in want:
            times.append(t)
            width.append(interface_width(h))
            width_sq.append(width_squared(h))
            if progress is not None:
                progress(model, t, width[-1])
    return GrowthRun(
        model=model, L=L, batch=batch, times=times, width=width, width_sq=width_sq,
        wall_seconds=time.time() - t0,
        config={"model": model, "L": L, "batch": batch, "t_max": t_max,
                "n_times": n_times, "seed": seed, "p": p,
                **({"nu": nu, "D": D, "dt": dt} if model == "ew" else {})},
    )


def run_saturation(L_values: list[int], batch: int = 64, sweeps_per_Lz: float = 12.0,
                   seed: int = 7, p: float = P_FLIP, progress=None) -> list[dict]:
    """Saturated width ``w_sat(L)`` for the KPZ model — the roughness exponent α.

    Each ring is grown for ``sweeps_per_Lz · L^z`` sweeps (with the KPZ ``z = 3/2``) so it is
    well past its own crossover time, then ``w`` is time-averaged over the final third of the
    run to kill the residual fluctuation. ``α`` is the slope of ``log w_sat`` vs ``log L``;
    the exact 1+1d value is **1/2** for KPZ *and* for EW (the two classes differ in β, not α,
    which is why β is the graded exponent and α is the corroborating one).
    """
    out = []
    for L in L_values:
        t_total = int(sweeps_per_Lz * L ** KPZ_Z)
        t_avg_from = int(t_total * 2 / 3)
        rng = np.random.default_rng(seed + L)
        h = flat_heights(batch, L)
        acc, n_acc = 0.0, 0
        for t in range(1, t_total + 1):
            single_step_sweep(h, p, rng)
            if t > t_avg_from:
                acc += interface_width(h)
                n_acc += 1
        w_sat = acc / max(n_acc, 1)
        out.append({"L": L, "w_sat": w_sat, "sweeps": t_total, "averaged_over": n_acc})
        if progress is not None:
            progress(L, w_sat)
    return out


def local_minimum_density(h: np.ndarray) -> float:
    """Fraction of sites that are local minima — the only sites the growth rule can act on.

    Used to *derive* the sign of the KPZ nonlinearity rather than assert it (see
    ``slope_velocity``): the growth velocity is ``2p`` times this density.
    """
    left = np.roll(h, 1, axis=1)
    right = np.roll(h, -1, axis=1)
    return float(np.mean((left == h + 1) & (right == h + 1)))


def slope_velocity(u: float, p: float = P_FLIP) -> float:
    """Growth velocity of the single-step model at mean slope ``u`` — closed form ``(p/2)(1−u²)``.

    A site is a local minimum iff the bond entering it steps down and the bond leaving it steps
    up. Under the product measure with up-step fraction ``q`` that probability is ``q(1−q)``
    (verified numerically in ``test_m17.py`` against random step sequences), and the mean slope
    is ``u = 2q − 1``, so

        v(u) = 2p · q(1−q) = (p/2)(1 − u²)   ⇒   λ ≡ ∂²v/∂u² = **−p < 0**.

    **This sign is load-bearing for M17's distribution claim.** KPZ's universal fluctuation is
    ``h ≃ v_∞ t + sign(λ)·(Γt)^{1/3} χ`` with ``χ`` Tracy–Widom distributed; a *negative* λ
    therefore predicts the **mirrored** law, i.e. a height whose skewness is **−0.2241**
    (droplet) or **−0.2935** (flat), not +. Measuring a negative skewness here is the
    prediction being confirmed, not a sign bug — and because ``λ ≠ 0`` is exactly what
    separates KPZ from Edwards–Wilkinson, this closed form is also *why* the model is in the
    KPZ class at all.
    """
    return 0.5 * p * (1.0 - u * u)


# λ < 0 for this model (see ``slope_velocity``), so the predicted skewness is the mirrored
# Tracy–Widom value. The distribution check grades against these signed targets.
KPZ_LAMBDA_SIGN = -1.0
PREDICTED_SKEW = {"droplet": KPZ_LAMBDA_SIGN * TW_GUE_SKEW,
                  "flat": KPZ_LAMBDA_SIGN * TW_GOE_SKEW}


def run_height_distribution(ic: str, L: int, t: int, batch: int, seed: int = 11,
                            p: float = P_FLIP, n_sites: int = 1) -> dict:
    """One-point height fluctuation for the flat vs droplet geometry — the Tracy–Widom test.

    Grows ``batch`` independent rings for ``t`` sweeps and samples the height where the
    geometry singles it out: the ring centre for ``"droplet"`` (the wedge apex, the one point
    of the curved interface whose fluctuation is the GUE one), a fixed site for ``"flat"``.

    ``n_sites > 1`` (flat only) additionally samples equally-spaced sites. The interface is
    correlated over ``ξ(t) ∼ t^{2/3}``, so this only buys statistics when the spacing ``L /
    n_sites`` comfortably exceeds ``ξ``; the returned ``site_spacing_over_xi`` records that
    ratio so the report can state it rather than the caller having to trust it. On a droplet
    the sites are *not* statistically equivalent (only the apex is the GUE point), so
    ``n_sites`` is refused there.

    Returns the sample's skewness and excess kurtosis — the two shape statistics that survive
    the unknown affine ``(v_∞, Γ)`` rescaling, so neither constant has to be fitted. Raises if
    a droplet run would outlast its ring (``droplet_time_budget``), because past that point
    the interface is no longer a droplet and the GUE expectation no longer applies.
    """
    if ic == "droplet":
        if n_sites != 1:
            raise ValueError("droplet geometry has one GUE point (the apex) — n_sites must be 1")
        budget = droplet_time_budget(L)
        if t > budget:
            raise ValueError(
                f"droplet run of {t} sweeps outgrows a ring of L={L} (budget {budget} sweeps) — "
                f"the wedge would wrap and stop being a droplet; use L >= {4 * t}"
            )
        h = droplet_heights(batch, L)
        sites = [L // 2]
    elif ic == "flat":
        h = flat_heights(batch, L)
        step = max(1, L // max(1, n_sites))
        sites = [(i * step) % L for i in range(max(1, n_sites))]
        # Keep every sampled site on one sublattice: h_i only ever changes by 2, so mixing
        # parities would mix two rigidly offset populations and fake a bimodal distribution.
        sites = [s - (s % 2) for s in sites]
    else:
        raise ValueError(f"unknown initial condition {ic!r} (expected 'flat' or 'droplet')")

    rng = np.random.default_rng(seed)
    for _ in range(t):
        single_step_sweep(h, p, rng)
    sample = h[:, sites].astype(np.float64).ravel()
    xi = t ** (1.0 / KPZ_Z)
    return {
        "ic": ic, "L": L, "t": t, "batch": batch, "n_sites": len(sites),
        "n_samples": int(sample.size), "sites": sites,
        "correlation_length": xi,
        "site_spacing_over_xi": float((L / len(sites)) / xi) if len(sites) > 1 else None,
        "mean": float(sample.mean()), "std": float(sample.std()),
        "skewness": skewness(sample), "excess_kurtosis": excess_kurtosis(sample),
        "predicted_skewness": PREDICTED_SKEW[ic],
        "tw_law": "GUE" if ic == "droplet" else "GOE",
    }
