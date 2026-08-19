"""M11 — 2D Edwards–Anderson spin glass: P(q) broadens toward the T=0 critical point.

The first Phase-3 rung, and — like M09 (Mermin–Wagner) — a milestone whose
*correct* answer is not a transition temperature but an **expected behaviour**.

⚠️ **The 2D EA spin glass orders only at T = 0** (d = 2 is the lower critical
dimension): there is **no finite-temperature spin-glass phase**. So M11 does **not**
hunt for a transition. The verification is the approach to the T = 0 critical point:
the disorder-averaged overlap distribution **P(q) broadens monotonically as T is
lowered** — its width / second moment ⟨q²⟩ grows toward T = 0 — without ever
developing a stable finite-T glass phase. (The finite-T transition T_SG ≈ 0.95 with
a Binder-cumulant crossing is the **3D** model, M12 — not this one.)

The order parameter is the **overlap** q = (1/N) Σ_i s_i^α s_i^β between two replicas
α, β that share the same quenched ±J bonds but run independently; P(q) is built per
disorder realization and **averaged over many realizations** (mandatory — a single
realization is sample-specific noise). At high T, P(q) is a narrow peak at q = 0;
as T → 0 it broadens and grows weight at large |q|, symmetric about 0.

``run_m11`` drives ``spin_glass.run`` (one batched GPU pass over
realizations × temperatures × 2 replicas) and reduces it to the broadening summary
the page shows and ``check_m11`` re-derives: ⟨q²⟩(T) increasing as T falls, P(q)
symmetric, and ⟨q⟩ ≈ 0 (the equilibration diagnostic). **Honest-null is on the
table**: 2D spin glasses are hard to equilibrate at low T, and if the lowest-T
points are not trustworthy the milestone says so rather than overclaiming a T = 0
result it cannot equilibrate to.
"""
from __future__ import annotations
from .hw import hw

import time
from dataclasses import dataclass

import numpy as np


def broadening_trend(T, q2) -> tuple[bool, float]:
    """``(monotone, frac)`` for the broadening of P(q): does ⟨q²⟩ rise as T falls?

    Sorts by temperature ascending, then checks that ⟨q²⟩ is (weakly) *decreasing*
    in T — equivalently increasing as T → 0, the broadening of P(q). Returns whether
    every adjacent step decreases with rising T and the fraction of steps that do
    (a soft score, robust to a little Monte-Carlo jitter at the noisy low-T end).
    NumPy-only so ``check_m11`` can re-derive it without torch.
    """
    T = np.asarray(T, dtype=float)
    q2 = np.asarray(q2, dtype=float)
    order = np.argsort(T)
    q2s = q2[order]
    # As T increases, q2 should decrease (P(q) narrows toward the high-T delta at 0).
    steps = np.diff(q2s)
    n = len(steps)
    if n == 0:
        return False, 0.0
    n_down = int((steps <= 0).sum())
    return n_down == n, n_down / n


@dataclass
class M11Result:
    T: list
    q_bin_centers: list
    pq: list                 # disorder-averaged P(q) per T, (n_temps, n_qbins)
    q2_mean: list            # ⟨q²⟩(T) — the broadening signal (grows as T→0)
    q4_mean: list
    q_abs_mean: list
    q_mean: list             # ⟨q⟩(T) ≈ 0 by symmetry — the equilibration diagnostic
    binder: list
    energy: list
    L: int
    n_realizations: int
    monotone_broadening: bool     # headline: ⟨q²⟩ rises monotonically as T → 0
    broadening_fraction: float    # fraction of adjacent T-steps that broaden
    q2_cold: float                # ⟨q²⟩ at the coldest T
    q2_hot: float                 # ⟨q²⟩ at the hottest T
    max_abs_q_mean: float         # max_T |⟨q⟩| — equilibration health (≈0 ideal)
    pq_symmetry_resid: float      # mean |P(q) − P(−q)| at the coldest T (≈0 ideal)
    wall_seconds: float
    config: dict
    swap_health: dict | None = None      # tempering ladder diagnostics, None when off
    comparison: dict | None = None       # the same ladder with the exchange off
    below_untempered_floor: bool = False # cold AND untempered -- publishing a transient


# The cold edge of the trustworthy window. Below T ≈ 0.5–0.6 single-spin
# checkerboard Metropolis can no longer equilibrate the 2D ±J glass at L=16 in
# tractable time (verified: even 4× burn-in leaves the two coldest points in an
# under-equilibration *dip* where ⟨q²⟩ is suppressed, not enhanced) — the
# textbook reason parallel tempering exists. We therefore report the broadening
# over [T_FLOOR, T_max], where ⟨q²⟩ grows cleanly and monotonically as T → T_FLOOR
# and the overlap stays symmetric (⟨q⟩ ≈ 0), and document the floor honestly. The
# *trend toward T = 0* is the claim; the un-equilibrable T ≲ 0.5 tail is not.
T_FLOOR = 0.6

#: The floor with parallel tempering on. Measured 2026-08-19: the exchange move
#: lifts the dip entirely over [0.30, 2.0] at the SAME wall-clock (75.7 s tempered
#: vs 78.3 s plain), with the overlap monotone to the coldest rung, |<q>| an order
#: of magnitude smaller, and a 4x-burn-in control that fails exactly as the comment
#: above predicted. 0.30 is where that benchmark stopped, NOT where the tempered
#: floor is -- nothing here locates the new floor, it only shows the old one is not
#: binding. See docs/investigations/2026-08-19-parallel-tempering-lifts-the-floor.md.
T_FLOOR_TEMPERED = 0.30

#: Sweeps between exchange attempts. 50 and 10 agreed to three decimals at every
#: rung in the benchmark, so the cheaper one is the default: the swap is not the
#: expensive part, and a rate that changes nothing is a rate that can be lowered.
SWAP_EVERY = 50


def run_m11(
    L: int = 16,
    T_min: float = T_FLOOR_TEMPERED,
    T_max: float = 2.0,
    n_temps: int = 16,
    n_realizations: int = 64,
    n_sweeps: int = 60000,
    n_burnin: int = 30000,
    seed: int = 42,
    device: str = "cuda",
    swap_every: int = SWAP_EVERY,
    comparison: bool = True,
    progress=None,
) -> M11Result:
    """Run the 2D ±J EA sweep and reduce it to the P(q)-broadening summary.

    One batched ``spin_glass.run`` pass (realizations × temperatures × 2 replicas),
    then: the disorder-averaged P(q) per T, ⟨q²⟩(T) (the broadening signal that grows
    as T → 0), the Binder cumulant, and two equilibration diagnostics — max_T |⟨q⟩|
    (should be ≈ 0 by symmetry) and the P(q) symmetry residual at the coldest T.
    ``check_m11`` re-derives the monotone-broadening verdict from the report arrays.

    **Tempered by default since 2026-08-19**, over [T_FLOOR_TEMPERED, T_max] --
    six rungs colder than this milestone could previously claim. ``comparison``
    runs the identical ladder a second time with the exchange move OFF and keeps
    it in the result. That doubles the wall-clock and it is the point: the
    untempered ladder is what single-spin Metropolis can see, the tempered one is
    what the glass actually does, and publishing the second without the first
    would quietly replace numbers this milestone has already shipped. Nothing is
    revised away; the dip becomes part of the record.

    Setting ``swap_every=0`` while ``T_min`` sits below :data:`T_FLOOR` produces
    the under-equilibration dip on purpose. That combination is flagged on the
    result (``below_untempered_floor``) and ``check_m11`` fails it -- a run may go
    cold, or it may go untempered, but a report that does both is publishing a
    transient.
    """
    from .spin_glass import SpinGlassConfig, run

    t0 = time.time()
    cfg = SpinGlassConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_realizations=n_realizations, n_sweeps=n_sweeps, n_burnin=n_burnin,
        seed=seed, device=device, swap_every=swap_every,
    )
    r = run(cfg)

    # The side-by-side: identical ladder, exchange move off. Same seed, so the
    # bonds and the initial spins are the same disorder realizations -- the two
    # runs differ ONLY in whether configurations were allowed to change
    # temperature, which is what makes the comparison a comparison.
    comparison_block = None
    if comparison and swap_every:
        r_plain = run(SpinGlassConfig(
            L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
            n_realizations=n_realizations, n_sweeps=n_sweeps, n_burnin=n_burnin,
            seed=seed, device=device, swap_every=0,
        ))
        mono_plain, frac_plain = broadening_trend(r_plain.T, r_plain.q2_mean)
        comparison_block = {
            "label": "single-spin Metropolis, no exchange",
            "swap_every": 0,
            "T": r_plain.T.tolist(),
            "q2_mean": r_plain.q2_mean.tolist(),
            "q_mean": r_plain.q_mean.tolist(),
            "monotone_broadening": mono_plain,
            "broadening_fraction": frac_plain,
            "max_abs_q_mean": float(np.max(np.abs(r_plain.q_mean))),
            # Where the dip turns over: the temperature of the MAXIMUM. Anything
            # but the coldest rung means the overlap turned over on the way down.
            "q2_argmax_T": float(r_plain.T[int(np.argmax(r_plain.q2_mean))]),
            "note": (
                "Identical ladder and seed with the exchange move off. Kept so "
                "the tempered numbers do not silently replace what this "
                "milestone previously published: where this ladder turns over "
                "is the under-equilibration dip, not physics."
            ),
        }

    monotone, frac = broadening_trend(r.T, r.q2_mean)
    # Coldest / hottest by temperature value (not array position).
    i_cold = int(np.argmin(r.T))
    i_hot = int(np.argmax(r.T))
    pq_cold = np.asarray(r.pq[i_cold], dtype=float)
    sym_resid = float(np.abs(pq_cold - pq_cold[::-1]).mean())

    result = M11Result(
        T=r.T.tolist(),
        q_bin_centers=r.q_bin_centers.tolist(),
        pq=r.pq.tolist(),
        q2_mean=r.q2_mean.tolist(),
        q4_mean=r.q4_mean.tolist(),
        q_abs_mean=r.q_abs_mean.tolist(),
        q_mean=r.q_mean.tolist(),
        binder=r.binder.tolist(),
        energy=r.energy.tolist(),
        L=L,
        n_realizations=n_realizations,
        monotone_broadening=monotone,
        broadening_fraction=frac,
        q2_cold=float(r.q2_mean[i_cold]),
        q2_hot=float(r.q2_mean[i_hot]),
        max_abs_q_mean=float(np.max(np.abs(r.q_mean))),
        pq_symmetry_resid=sym_resid,
        wall_seconds=time.time() - t0,
        swap_health=r.swap_health,
        comparison=comparison_block,
        below_untempered_floor=bool(T_min < T_FLOOR and not swap_every),
        config={
            "L": L, "T_min": T_min, "T_max": T_max, "n_temps": n_temps,
            "n_realizations": n_realizations, "n_sweeps": n_sweeps,
            "n_burnin": n_burnin, "seed": seed, "model": "edwards-anderson-2d",
            # `hw()` labels a config with no device key as CPU -- absence of
            # evidence never claims the GPU -- so a run that omitted this was
            # under-reporting its own hardware in a public headline.
            "disorder": "bimodal-pm-J", "swap_every": swap_every, "device": device,
        },
    )
    if progress is not None:
        progress(result)
    return result


def to_report(result: M11Result) -> dict:
    """A JSON report shaped for the page + the M11 check.

    Distinct ``experiment`` tag (``M11-spin-glass-2d``) so every single-peak χ/C
    check skips it — M11 carries NO transition to locate; its signature is the
    P(q)-broadening trend ⟨q²⟩(T) rising as T → 0 — and ``check_m11`` claims it, with
    the per-T (T, ⟨q²⟩) arrays and the P(q) histograms the page needs and the
    headline verdict the check re-derives.
    """
    verdict = ("P(q) broadens toward T=0" if result.monotone_broadening
               else "broadening NOT reproduced")
    # The sampler belongs in the headline. This milestone spent its whole life
    # stopping at T=0.6 because single-spin Metropolis could not go colder, so a
    # headline that reaches 0.30 without saying WHY would read as the same
    # measurement getting a better answer. It is a different sampler.
    sampler = ("parallel tempering" if result.config.get("swap_every")
               else "single-spin Metropolis")
    # ...and so does the untempered ladder's turnover, when there is one: the
    # comparison exists to keep the dip visible, and burying it in a JSON block
    # while the headline quotes only the tempered number is exactly the silent
    # replacement the side-by-side was ruled in to prevent.
    comp = result.comparison or {}
    dip = ""
    if comp and not comp.get("monotone_broadening"):
        dip = (f"; the same ladder without the exchange move turns over at "
               f"T={comp['q2_argmax_T']:.2f}")
    headline = (
        f"2D Edwards–Anderson spin glass (L={result.L}, {result.n_realizations} "
        f"disorder realizations, {sampler}): ⟨q²⟩ grows {result.q2_hot:.3f} → "
        f"{result.q2_cold:.3f} as T falls {result.T[int(np.argmax(result.T))]:.2f} → "
        f"{result.T[int(np.argmin(result.T))]:.2f} — {verdict} (T_c=0 in 2D, no "
        f"finite-T glass phase){dip} · {result.wall_seconds:.0f}s on "
        f"{hw(result.config)}"
    )
    return {
        "experiment": "M11-spin-glass-2d",
        "headline": headline,
        "L": result.L,
        "n_realizations": result.n_realizations,
        "T": result.T,
        "q_bin_centers": result.q_bin_centers,
        "pq": result.pq,
        "q2_mean": result.q2_mean,
        "q4_mean": result.q4_mean,
        "q_abs_mean": result.q_abs_mean,
        "q_mean": result.q_mean,
        "binder": result.binder,
        "energy": result.energy,
        "monotone_broadening": result.monotone_broadening,
        "broadening_fraction": result.broadening_fraction,
        "q2_cold": result.q2_cold,
        "q2_hot": result.q2_hot,
        "max_abs_q_mean": result.max_abs_q_mean,
        "pq_symmetry_resid": result.pq_symmetry_resid,
        "wall_seconds": result.wall_seconds,
        "swap_health": result.swap_health,
        "comparison": result.comparison,
        "below_untempered_floor": result.below_untempered_floor,
        "config": result.config,
    }
