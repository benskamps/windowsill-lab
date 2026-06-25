"""M07 — 2D q-state Potts model: the continuous → first-order transition.

M01–M06 lived in the Ising world (two states, s = ±1). M07 turns the dial that
matters most for *critical behaviour*: the number of states q. The q-state Potts
model is the Ising generalisation where a bond pays energy only when its two
sites carry the same flavour s ∈ {0,…,q−1},

    E = -J · Σ_<ij> δ(s_i, s_j)            (J = 1),

and on the square lattice its critical temperature is **exact** (the self-dual
point, Baxter):

    T_c(q) = 1 / ln(1 + √q)
        q=3 → 0.99497   q=4 → 0.91024   q=5 → 0.85153   q=6 → 0.80760

The headline of M07 is not just *where* the transition sits but *what kind* it
is. The Potts transition is **continuous (2nd order)** for q ≤ 4 and
**first-order (discontinuous)** for q ≥ 5. So M07 runs the four values q = 3, 4,
5, 6, locates each T_c from the order-parameter susceptibility peak, checks it
against the exact value, and reads the **order-of-transition signature** off the
same sweep: a first-order transition has a sharper, taller susceptibility spike
and a steeper (discontinuous in the L→∞ limit) drop in the order parameter
across T_c than a continuous one.

### What is calibrated vs qualitative

q = 3 and q = 4 are continuous and calibrate cleanly: their χ peak lands within
the finite-L tolerance of the exact T_c. q = 5 and q = 6 are first-order, which
brings **stronger finite-size effects and metastability** — the pseudo-critical
peak on a finite lattice can sit a little further from the infinite-volume T_c,
and the transition can hysterese. We use ample sweeps and a window straddling
each T_c; where q ≥ 5 still lands inside the (slightly wider, physically
justified) tolerance it is a calibration pass, and the **first-order signature**
(sharper spike, steeper m-drop than q ≤ 4) is the qualitative claim the
milestone asks for either way.

``run_m07`` drives the batched Potts engine ``potts.run`` once per q; the χ-peak
refinement reuses m06's NumPy-only ``refine_peak``.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from .m06 import refine_peak


def TC_POTTS(q: int) -> float:
    """Exact square-lattice q-state Potts critical temperature, 1/ln(1+√q)."""
    return 1.0 / math.log(1.0 + math.sqrt(q))


# The q values M07 sweeps: two continuous (q ≤ 4), two first-order (q ≥ 5).
Q_VALUES = (3, 4, 5, 6)
# Half-width of the temperature window straddling each q's exact T_c.
T_HALF_WINDOW = 0.12


def _order_drop(T, order) -> float:
    """Steepest single-step drop in the order parameter across the sweep.

    A continuous transition softens the order parameter gradually; a first-order
    one drops it (discontinuously, as L→∞) at T_c. The largest adjacent decrease
    ``max_i (m[i] − m[i+1])`` is a cheap, monotone-in-sharpness proxy for that —
    larger means a steeper melt, the first-order fingerprint. NumPy only.
    """
    order = np.asarray(order, dtype=float)
    if len(order) < 2:
        return 0.0
    drops = order[:-1] - order[1:]
    return float(drops.max())


@dataclass
class QResult:
    q: int
    T: list
    order: list
    order_err: list
    chi: list
    energy: list
    specific_heat: list
    tc_chi: float            # χ-peak T_c estimate (coarse-grid argmax)
    tc_chi_refined: float    # parabola-refined χ-peak (the finite-L T_c)
    tc_exact: float          # 1/ln(1+√q)
    rel_error: float         # |tc_chi_refined − tc_exact| / tc_exact
    chi_max: float           # peak susceptibility (taller for first-order)
    order_drop: float        # steepest m drop (steeper for first-order)
    wall_seconds: float


@dataclass
class M07Result:
    per_q: list              # list[QResult], one per q in Q_VALUES
    L: int
    transition_order: dict   # {q: "continuous"|"first-order"} — the known truth
    wall_seconds: float
    config: dict


def run_one_q(
    q: int,
    L: int = 128,
    n_temps: int = 25,
    n_sweeps: int = 8000,
    n_burnin: int = 3000,
    seed: int = 42,
    device: str = "cuda",
    half_window: float = T_HALF_WINDOW,
    updater: str = "wolff",
) -> QResult:
    """Run the Potts engine for one q over a window straddling its exact T_c.

    The window is ``T_c(q) ± half_window``; the χ-peak (parabola-refined) is the
    finite-L T_c, compared against the exact ``1/ln(1+√q)``. Also captures the
    peak height and the steepest order-parameter drop — the two qualitative
    fingerprints that separate the first-order (q≥5) from the continuous (q≤4)
    transition. The default ``updater='wolff'`` is the cluster algorithm M07
    needs through the (first-order for q≥5) Potts transition — single-spin
    Metropolis gets metastably trapped and reports noise; ``n_sweeps``/``n_burnin``
    are cluster updates here.
    """
    from .potts import PottsRunConfig, run

    tc = TC_POTTS(q)
    t0 = time.time()
    cfg = PottsRunConfig(
        q=q, L=L, T_min=tc - half_window, T_max=tc + half_window,
        n_temps=n_temps, n_sweeps=n_sweeps, n_burnin=n_burnin,
        seed=seed, device=device, updater=updater,
    )
    r = run(cfg)

    tc_chi = float(r.T[int(np.argmax(r.chi))])
    tc_chi_refined = refine_peak(r.T, r.chi)
    rel_err = abs(tc_chi_refined - tc) / tc

    return QResult(
        q=q,
        T=r.T.tolist(),
        order=r.order.tolist(),
        order_err=r.order_err.tolist(),
        chi=r.chi.tolist(),
        energy=r.energy.tolist(),
        specific_heat=r.specific_heat.tolist(),
        tc_chi=tc_chi,
        tc_chi_refined=tc_chi_refined,
        tc_exact=tc,
        rel_error=rel_err,
        chi_max=float(np.max(r.chi)),
        order_drop=_order_drop(r.T, r.order),
        wall_seconds=time.time() - t0,
    )


def run_m07(
    L: int = 128,
    q_values=Q_VALUES,
    n_temps: int = 25,
    n_sweeps: int = 8000,
    n_burnin: int = 3000,
    seed: int = 42,
    device: str = "cuda",
    half_window: float = T_HALF_WINDOW,
    updater: str = "wolff",
    progress=None,
) -> M07Result:
    """Run the q-state Potts model for each q and locate every T_c.

    Mirrors ``run_m04``/``run_m05``: one batched sweep per q over a window
    straddling that q's exact T_c, wall-clock timing, a ``progress`` callback
    (called with each ``QResult`` as it finishes), and a ``to_report``-ready
    result carrying the per-q arrays, measured + exact T_c, and the
    order-of-transition signature. The default Wolff updater (``n_sweeps``/
    ``n_burnin`` in cluster updates) is what makes the χ peaks clean through the
    Potts transition; see ``potts.run``.
    """
    t0 = time.time()
    per_q: list[QResult] = []
    for q in q_values:
        qr = run_one_q(
            q=q, L=L, n_temps=n_temps, n_sweeps=n_sweeps, n_burnin=n_burnin,
            seed=seed, device=device, half_window=half_window, updater=updater,
        )
        per_q.append(qr)
        if progress is not None:
            progress(qr)

    # The known physics: continuous for q ≤ 4, first-order for q ≥ 5.
    transition_order = {q: ("continuous" if q <= 4 else "first-order") for q in q_values}

    return M07Result(
        per_q=per_q,
        L=L,
        transition_order=transition_order,
        wall_seconds=time.time() - t0,
        config={
            "L": L, "q_values": list(q_values), "n_temps": n_temps,
            "n_sweeps": n_sweeps, "n_burnin": n_burnin, "seed": seed,
            "half_window": half_window, "updater": updater,
        },
    )


def to_report(result: M07Result) -> dict:
    """A JSON report shaped for the page + the M07 check.

    Distinct ``experiment`` tag (``M07-potts``) so the other χ-peak checks skip
    it, carrying per-q arrays (T, chi, order, energy), the measured + exact T_c
    for each q, the rel. error, and the order-of-transition signature
    (peak height + steepest order-parameter drop, sharper for the first-order
    q ≥ 5 transitions). ``check_m07`` re-derives each χ peak from these arrays.
    """
    # Sharpness summary for the qualitative continuous→first-order story. The
    # clean discriminant is the *peak susceptibility* χ_max — a first-order
    # transition spikes far taller and sharper than a continuous one (here it
    # climbs monotonically across the q≤4 → q≥5 boundary). The steepest
    # order-parameter drop is carried too, but on a finite grid it is largely
    # grid-resolution-limited, so χ_max is the headline signature.
    cont = [qr for qr in result.per_q if qr.q <= 4]
    first = [qr for qr in result.per_q if qr.q >= 5]
    cont_drop = float(np.mean([qr.order_drop for qr in cont])) if cont else None
    first_drop = float(np.mean([qr.order_drop for qr in first])) if first else None
    cont_chimax = float(np.mean([qr.chi_max for qr in cont])) if cont else None
    first_chimax = float(np.mean([qr.chi_max for qr in first])) if first else None

    per_q = []
    for qr in result.per_q:
        per_q.append({
            "q": qr.q,
            "T": qr.T,
            "chi": qr.chi,
            "order": qr.order,
            "order_err": qr.order_err,
            "energy": qr.energy,
            "specific_heat": qr.specific_heat,
            "tc_chi": qr.tc_chi,
            "tc_chi_refined": qr.tc_chi_refined,
            "tc_exact": qr.tc_exact,
            "rel_error": qr.rel_error,
            "chi_max": qr.chi_max,
            "order_drop": qr.order_drop,
            "transition": result.transition_order[qr.q],
            "wall_seconds": qr.wall_seconds,
        })

    worst = max(result.per_q, key=lambda qr: qr.rel_error)
    headline = (
        f"2D q-state Potts (L={result.L}): "
        + ", ".join(
            f"q={qr.q} T_c={qr.tc_chi_refined:.3f}(exact {qr.tc_exact:.3f})"
            for qr in result.per_q
        )
        + f" · worst rel. err {worst.rel_error*100:.1f}% (q={worst.q})"
        + f" · {result.wall_seconds:.0f}s on GPU"
    )

    return {
        "experiment": "M07-potts",
        "headline": headline,
        "L": result.L,
        "per_q": per_q,
        "transition_order": {str(k): v for k, v in result.transition_order.items()},
        "continuous_mean_order_drop": cont_drop,
        "first_order_mean_order_drop": first_drop,
        "continuous_mean_chi_max": cont_chimax,
        "first_order_mean_chi_max": first_chimax,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
