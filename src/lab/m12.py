"""M12 — 3D Edwards–Anderson spin glass: the finite-T transition via a Binder crossing.

The first milestone whose signature is a **multi-lattice-size crossing**, not a single-L
peak or trend. Where M11 (2D EA) ordered only at T = 0, the **3D** ±J Edwards–Anderson
glass has a genuine finite-temperature spin-glass transition at

    T_SG ≈ 0.95    (±J / bimodal, simple-cubic — the modern Monte-Carlo benchmark)

with no local order parameter. The clean fingerprint is the **disorder-averaged Binder
cumulant** g_L(T) = ½(3 − [⟨q⁴⟩]/[⟨q²⟩]²) computed for several lattice sizes on one
shared temperature ladder: the curves are scale-invariant at the transition, so they all
**cross at a single temperature — that intersection is T_SG**. Below it the larger
lattice is more ordered (g rises toward 1); above it the larger lattice is less ordered
(g falls toward 0).

``run_m12`` drives ``spin_glass3d.run`` (batched 3D ±J EA with **parallel tempering** —
the load-bearing tool that lets the cold rungs equilibrate; without it the crossing
washes out, M11's documented failure mode) once per lattice size on the shared ladder,
then reads off the multi-L Binder crossing. The reducers here (``pair_crossing``,
``binder_crossings``, ``locate_tsg``) are **NumPy/stdlib only** so ``check_m12`` can
re-derive the crossing from the report arrays without torch — the same discipline as
M11's ``broadening_trend``.

Honest-null is on the table and expected at small scale: resolving a clean 3-size
crossing near 0.95 needs many disorder realizations and long parallel-tempered
equilibration (a GPU run). A ``--quick`` CPU pass proves the code end-to-end but will not
generally resolve the physics; when the crossing is not clean the milestone ships as a
``[~]`` failed-calibration null with the reason in the report, never a fake green.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

# The modern Monte-Carlo benchmark for the ±J simple-cubic Edwards–Anderson
# spin-glass transition. Not a closed form; the literature clusters around
# T_SG ≈ 0.95 (e.g. Katzgraber–Körner–Young and follow-ups place it near 0.95).
T_SG_BENCHMARK = 0.95
# Documented crossing tolerance. Finite-size Binder crossings drift with the pair
# of sizes used and carry real corrections-to-scaling, so — like M08's ±0.07 BKT
# window — the check allows a physically-justified band around the benchmark. A
# broken run (no crossing, or one far from 0.95) still fails by a wide margin.
CROSSING_TOL = 0.15


def pair_crossing(T, g_small, g_large):
    """Temperature where two Binder curves cross, or ``None``.

    ``T`` ascending; ``g_small``/``g_large`` are g_L(T) for the smaller / larger L on
    the SAME ladder. Below T_SG the larger lattice is more ordered (g_large > g_small);
    above it g_large < g_small. So ``d(T) = g_large − g_small`` runs positive → negative
    with rising T, and the crossing is the first ``+ → −`` sign change, linear-
    interpolated to the zero of ``d``. Returns ``None`` when no such crossing exists in
    the window (e.g. the curves never separate, or the cold end is already unordered) —
    an honest "no transition resolved", not a fabricated number. Stdlib only.
    """
    d = [gl - gs for gs, gl in zip(g_small, g_large)]
    for i in range(len(d) - 1):
        if d[i] >= 0.0 and d[i + 1] < 0.0:
            denom = d[i + 1] - d[i]
            if denom == 0:
                return float(T[i])
            return float(T[i] + (0.0 - d[i]) * (T[i + 1] - T[i]) / denom)
    return None


def binder_crossings(T, binder_by_L) -> list[dict]:
    """All pairwise Binder crossings across the sizes, sorted by T ascending internally.

    ``binder_by_L`` maps L (int or str) → g_L(T) parallel to ``T``. Returns a list of
    ``{"L1", "L2", "T"}`` (L1 < L2) for every size pair that produces a crossing. NumPy/
    stdlib only so both the runner and ``check_m12`` share one source of truth.
    """
    Ls = sorted(binder_by_L, key=lambda k: int(k))
    order = sorted(range(len(T)), key=lambda i: T[i])
    Ts = [float(T[i]) for i in order]
    G = {L: [float(binder_by_L[L][i]) for i in order] for L in Ls}
    pairs: list[dict] = []
    for a in range(len(Ls)):
        for b in range(a + 1, len(Ls)):
            La, Lb = Ls[a], Ls[b]
            t = pair_crossing(Ts, G[La], G[Lb])
            if t is not None:
                pairs.append({"L1": int(La), "L2": int(Lb), "T": round(t, 4)})
    return pairs


def locate_tsg(T, binder_by_L):
    """``(crossing_T, pairs, mean_T)`` — the T_SG estimate from the Binder crossings.

    The primary estimate is the crossing of the **two largest lattice sizes** (the least
    finite-size-biased pair); if that pair does not cross, the median of all pairwise
    crossings is used. ``mean_T`` is the mean over all pairwise crossings — a robustness
    cross-check. Returns ``(None, [], None)`` when no pair crosses at all (an honest
    no-crossing, which fails the check rather than inventing a T_SG).
    """
    pairs = binder_crossings(T, binder_by_L)
    if not pairs:
        return None, [], None
    Ls = sorted(int(k) for k in binder_by_L)
    big = {Ls[-1], Ls[-2]} if len(Ls) >= 2 else {Ls[-1]}
    top = next((p["T"] for p in pairs if {p["L1"], p["L2"]} == big), None)
    if top is None:
        ts = sorted(p["T"] for p in pairs)
        top = ts[len(ts) // 2]
    mean_T = sum(p["T"] for p in pairs) / len(pairs)
    return float(top), pairs, float(mean_T)


@dataclass
class M12Result:
    T: list                        # shared temperature ladder
    L_values: list
    q_bin_centers: list
    pq_ref: list                   # P(q) at the largest L, (n_temps, n_qbins)
    pq_ref_L: int
    binder_by_L: dict              # {L: g_L(T)} — the crossing signal
    q2_by_L: dict
    q4_by_L: dict
    q_mean_by_L: dict              # {L: [⟨q⟩(T)]} — equilibration diagnostic
    energy_by_L: dict
    swap_rate_by_L: dict           # {L: [PT acceptance per T-gap]}
    crossing_T: float | None       # primary T_SG estimate (two largest L)
    crossing_pairs: list           # all pairwise crossings
    crossing_mean_T: float | None
    t_sg_benchmark: float
    tolerance: float
    crossing_resolved: bool        # crossing exists, near benchmark, and symmetric
    max_abs_q_mean: float          # max_{L,T} |⟨q⟩| — equilibration health (≈0 ideal)
    n_realizations: int
    wall_seconds: float
    config: dict


def run_m12(
    L_values=(4, 6, 8),
    T_min: float = 0.4,
    T_max: float = 1.6,
    n_temps: int = 16,
    n_realizations: int = 200,
    n_sweeps: int = 20000,
    n_burnin: int = 10000,
    swap_every: int = 10,
    seed: int = 42,
    device: str = "cuda",
    progress=None,
) -> M12Result:
    """Sweep ≥3 lattice sizes on a shared T ladder and locate the Binder crossing → T_SG.

    Runs ``spin_glass3d.run`` (3D ±J EA with parallel tempering) once per L in
    ``L_values`` on the identical ``(T_min, T_max, n_temps)`` ladder, collects the
    disorder-averaged Binder cumulant g_L(T) for each size, and reads off the multi-L
    crossing. The verdict ``crossing_resolved`` is True only when a crossing exists,
    lands within ``CROSSING_TOL`` of the T_SG ≈ 0.95 benchmark, AND the overlap stays
    symmetric (max|⟨q⟩| ≈ 0, the parallel-tempering equilibration guard). ``check_m12``
    re-derives the crossing from the reported per-L arrays.
    """
    from .spin_glass3d import SpinGlass3DConfig, run

    t0 = time.time()
    L_values = [int(L) for L in L_values]
    T_ref = None
    binder_by_L, q2_by_L, q4_by_L, qmean_by_L = {}, {}, {}, {}
    energy_by_L, swap_by_L = {}, {}
    pq_ref, centers, pq_ref_L = None, None, None
    max_abs_qmean = 0.0

    for i, L in enumerate(L_values):
        cfg = SpinGlass3DConfig(
            L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
            n_realizations=n_realizations, n_sweeps=n_sweeps, n_burnin=n_burnin,
            swap_every=swap_every, seed=seed + 101 * i, device=device,
        )
        r = run(cfg)
        if T_ref is None:
            T_ref = r.T.tolist()
        binder_by_L[L] = r.binder.tolist()
        q2_by_L[L] = r.q2_mean.tolist()
        q4_by_L[L] = r.q4_mean.tolist()
        qmean_by_L[L] = r.q_mean.tolist()
        energy_by_L[L] = r.energy.tolist()
        swap_by_L[L] = r.swap_rate.tolist()
        max_abs_qmean = max(max_abs_qmean, float(np.max(np.abs(r.q_mean))))
        # Keep the largest L's P(q) for the report figure (richest structure).
        pq_ref, centers, pq_ref_L = r.pq.tolist(), r.q_bin_centers.tolist(), L
        if progress is not None:
            progress(L, r)

    crossing_T, pairs, mean_T = locate_tsg(T_ref, binder_by_L)
    near = crossing_T is not None and abs(crossing_T - T_SG_BENCHMARK) <= CROSSING_TOL
    symmetric = max_abs_qmean <= 0.15
    resolved = bool(near and symmetric)

    result = M12Result(
        T=T_ref,
        L_values=L_values,
        q_bin_centers=centers,
        pq_ref=pq_ref,
        pq_ref_L=pq_ref_L,
        binder_by_L={str(k): v for k, v in binder_by_L.items()},
        q2_by_L={str(k): v for k, v in q2_by_L.items()},
        q4_by_L={str(k): v for k, v in q4_by_L.items()},
        q_mean_by_L={str(k): v for k, v in qmean_by_L.items()},
        energy_by_L={str(k): v for k, v in energy_by_L.items()},
        swap_rate_by_L={str(k): v for k, v in swap_by_L.items()},
        crossing_T=crossing_T,
        crossing_pairs=pairs,
        crossing_mean_T=mean_T,
        t_sg_benchmark=T_SG_BENCHMARK,
        tolerance=CROSSING_TOL,
        crossing_resolved=resolved,
        max_abs_q_mean=max_abs_qmean,
        n_realizations=n_realizations,
        wall_seconds=time.time() - t0,
        config={
            "L_values": L_values, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_realizations": n_realizations, "n_sweeps": n_sweeps, "n_burnin": n_burnin,
            "swap_every": swap_every, "seed": seed, "device": device,
            "model": "edwards-anderson-3d", "disorder": "bimodal-pm-J",
            "updater": "checkerboard-metropolis+parallel-tempering",
        },
    )
    if progress is not None and hasattr(progress, "done"):
        progress.done(result)
    return result


def to_report(result: M12Result) -> dict:
    """A JSON report shaped for the page + the M12 check.

    Distinct ``experiment`` tag (``M12-spin-glass-3d``) so no single-peak χ/C or 2D-EA
    check misreads it — M12's signature is a **multi-L Binder crossing** at the finite-T
    transition T_SG ≈ 0.95. Carries the shared T ladder, the per-L Binder / ⟨q²⟩ / ⟨q⁴⟩ /
    ⟨q⟩ arrays, the located crossing, and the P(q) at the largest L, so ``check_m12`` can
    re-derive the crossing verdict. When the crossing is not resolved the report carries
    ``status: "null"`` — an honest failed-calibration grey leaf (never a fake green, and
    never a mislabelled transition).
    """
    ct = result.crossing_T
    ct_str = f"{ct:.3f}" if ct is not None else "none"
    verdict = ("crossing at T_SG≈%.3f" % ct if result.crossing_resolved
               else "no clean crossing near 0.95 — calibration null")
    headline = (
        f"3D Edwards–Anderson spin glass (L={result.L_values}, "
        f"{result.n_realizations} disorder realizations, parallel tempering): "
        f"disorder-averaged Binder cumulant crossing at T_SG = {ct_str} "
        f"(benchmark {result.t_sg_benchmark:.2f} ± {result.tolerance:.2f}) — {verdict} · "
        f"{result.wall_seconds:.0f}s"
    )
    report = {
        "experiment": "M12-spin-glass-3d",
        "headline": headline,
        "L_values": result.L_values,
        "n_realizations": result.n_realizations,
        "T": result.T,
        "binder_by_L": result.binder_by_L,
        "q2_by_L": result.q2_by_L,
        "q4_by_L": result.q4_by_L,
        "q_mean_by_L": result.q_mean_by_L,
        "energy_by_L": result.energy_by_L,
        "swap_rate_by_L": result.swap_rate_by_L,
        "q_bin_centers": result.q_bin_centers,
        "pq_ref": result.pq_ref,
        "pq_ref_L": result.pq_ref_L,
        "crossing_T": result.crossing_T,
        "crossing_pairs": result.crossing_pairs,
        "crossing_mean_T": result.crossing_mean_T,
        "t_sg_benchmark": result.t_sg_benchmark,
        "tolerance": result.tolerance,
        "crossing_resolved": result.crossing_resolved,
        "max_abs_q_mean": result.max_abs_q_mean,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
    # Honest failed-calibration marker: a folded grey leaf on the windowsill, never a
    # green one. Omitted when the crossing resolves (the archive/check grades that).
    if not result.crossing_resolved:
        report["status"] = "null"
    return report
