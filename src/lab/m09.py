"""M09 — 2D Heisenberg model: verifying the *absence* of order (Mermin–Wagner).

Every milestone before this located a known transition and checked we landed on
it. M09 is different in kind: there is **no transition to find**. Mermin–Wagner
forbids a 2D system with a continuous symmetry (here O(3)) from spontaneously
ordering at any T > 0, and — unlike the XY model (M08) — the Heisenberg model has
**no BKT escape hatch** either (the sphere S² is simply connected, π₁ = 0, so no
stable vortices). So the isotropic 2D Heisenberg ferromagnet is disordered at
*every* finite temperature; correlations decay exponentially; order lives only at
T = 0.

The verification is therefore a **null done honestly**: we reproduce the *known
absence* of order rather than a number. The clean, falsifiable signature is a
finite-size drift — at a fixed moderate temperature the per-spin vector
magnetization

    ⟨|m|⟩(L)   DECREASES monotonically as L grows: ⟨|m|⟩(16) > ⟨|m|⟩(32) > …

heading toward 0. If there were spontaneous order, ⟨|m|⟩ would approach a finite
plateau; under Mermin–Wagner it keeps shrinking (the only thing holding |m| up on
a small lattice is the finite ξ(T) being comparable to L). **Reading a single
small L is the #1 failure mode** — at one L, ⟨|m|⟩ is appreciable and *fakes* a
transition — so ``run_m09`` sweeps a *family* of L at a fixed T and reports the
drift, and ``check_m09`` asserts the monotone decrease. A PASS means "the expected
*absence* of 2D Heisenberg order is reproduced"; a non-decreasing ⟨|m|⟩(L) (a fake
finite-T transition, or a broken simulation) fails.

We summarise the drift two ways: the per-step ratio ⟨|m|⟩(2L)/⟨|m|⟩(L) (each < 1
under the theorem) and a least-squares slope of ⟨|m|⟩ vs 1/√N = 1/L. A finite-size
order parameter that washes out as L grows has a negative such slope; genuine
spontaneous order would extrapolate to a positive intercept as 1/L → 0. Both are
re-derivable from the report's (L, ⟨|m|⟩) arrays — receipts, not echoes.
"""
from __future__ import annotations
from .hw import hw

import time
from dataclasses import dataclass

import numpy as np


# The default L-family and fixed temperature for the Mermin–Wagner drift. T=0.7
# is moderate: cold enough that a small lattice carries an appreciable (and so
# falsifiable) ⟨|m|⟩, warm enough that ξ(T) stays well below L=64 so the drift to
# 0 is already visible across {16, 32, 64} without needing L=128+.
DEFAULT_L = (16, 32, 64)
DEFAULT_T = 0.7


def drift_slope(Ls, abs_mag) -> float:
    """Least-squares slope of ⟨|m|⟩ vs 1/L (= 1/√N) — the finite-size-drift sign.

    A finite-size order parameter that washes out as L grows is an *increasing*
    function of 1/L (smaller L → larger |m|), so the slope of ⟨|m|⟩ against 1/L is
    **positive**; equivalently ⟨|m|⟩ falls toward its 1/L → 0 (infinite-volume)
    intercept. Genuine spontaneous order would instead sit on a roughly flat line
    with a positive intercept. NumPy-only so the check can re-derive it without
    torch. Returns the slope d⟨|m|⟩/d(1/L).
    """
    x = np.asarray([1.0 / L for L in Ls], dtype=float)
    y = np.asarray(abs_mag, dtype=float)
    n = len(x)
    mx, my = x.mean(), y.mean()
    sxx = float(((x - mx) ** 2).sum())
    sxy = float(((x - mx) * (y - my)).sum())
    return sxy / sxx if sxx > 0 else 0.0


@dataclass
class M09Result:
    L_values: list
    T: float
    abs_mag: list          # ⟨|m|⟩ at each L — the Mermin–Wagner drift, one per L
    abs_mag_err: list      # standard error of ⟨|m|⟩ at each L
    chi: list              # |m|-susceptibility at each L
    energy: list           # mean energy per spin at each L
    acceptance: list       # realized Metropolis acceptance at each L
    ratios: list           # ⟨|m|⟩(L_{k+1}) / ⟨|m|⟩(L_k) — each < 1 under the theorem
    slope_vs_inv_L: float  # d⟨|m|⟩/d(1/L); positive ⇒ |m| washes out as L grows
    monotone_decreasing: bool   # the headline: ⟨|m|⟩ strictly drifts down with L
    updater: str
    wall_seconds: float
    config: dict


def run_m09(
    L_values=DEFAULT_L,
    T: float = DEFAULT_T,
    n_sweeps: int = 20000,
    n_burnin: int = 8000,
    over_relax: int = 3,
    seed: int = 42,
    device: str = "cuda",
    updater: str = "metropolis",
    progress=None,
) -> M09Result:
    """Sweep a family of L at a fixed T and measure the Mermin–Wagner ⟨|m|⟩ drift.

    Runs the O(3) Heisenberg engine ``heisenberg.run`` once per L (each a single
    lattice at the fixed temperature ``T``), collects ⟨|m|⟩(L), and computes the
    absence-of-order signature: the per-step ratios ⟨|m|⟩(2L)/⟨|m|⟩(L) (each < 1
    under Mermin–Wagner) and the slope of ⟨|m|⟩ vs 1/L. ``check_m09`` re-derives
    the monotone-decrease verdict from the report's (L, ⟨|m|⟩) arrays.

    The same fixed seed drives every L (the engine offsets it internally), so the
    only thing changing across the family is the lattice size — exactly the
    controlled comparison the theorem is about. ``progress`` (if given) is called
    after each L with the per-L result for live CLI output.
    """
    from .heisenberg import HeisenbergRunConfig, run

    t0 = time.time()
    abs_mag, abs_mag_err, chi, energy, acceptance = [], [], [], [], []
    for L in L_values:
        cfg = HeisenbergRunConfig(
            L=L, T_min=T, T_max=T, n_temps=1,
            n_sweeps=n_sweeps, n_burnin=n_burnin, over_relax=over_relax,
            seed=seed, device=device, updater=updater,
        )
        r = run(cfg)
        abs_mag.append(float(r.abs_mag[0]))
        abs_mag_err.append(float(r.abs_mag_err[0]))
        chi.append(float(r.chi[0]))
        energy.append(float(r.energy[0]))
        acceptance.append(float(r.acceptance[0]))
        if progress is not None:
            progress(L, r)

    ratios = [abs_mag[i + 1] / abs_mag[i] if abs_mag[i] > 0 else float("inf")
              for i in range(len(abs_mag) - 1)]
    slope = drift_slope(L_values, abs_mag)
    # The headline verdict: ⟨|m|⟩ strictly decreases as L grows (the absence of
    # order). A tiny noise floor (1.5·the larger of the two adjacent SEMs) keeps a
    # statistically-flat pair from flipping the verdict on Monte-Carlo jitter.
    monotone = all(
        abs_mag[i + 1] < abs_mag[i] - 1.5 * max(abs_mag_err[i], abs_mag_err[i + 1])
        for i in range(len(abs_mag) - 1)
    )

    result = M09Result(
        L_values=list(L_values),
        T=T,
        abs_mag=abs_mag,
        abs_mag_err=abs_mag_err,
        chi=chi,
        energy=energy,
        acceptance=acceptance,
        ratios=ratios,
        slope_vs_inv_L=slope,
        monotone_decreasing=monotone,
        updater=updater,
        wall_seconds=time.time() - t0,
        config={
            "L_values": list(L_values), "T": T, "n_sweeps": n_sweeps,
            "n_burnin": n_burnin, "over_relax": over_relax, "seed": seed,
            "updater": updater, "model": "heisenberg",
        },
    )
    if progress is not None and False:
        progress(result)
    return result


def to_report(result: M09Result) -> dict:
    """A JSON report shaped for the page + the M09 check.

    Distinct ``experiment`` tag (``M09-heisenberg``) so every single-peak χ/C check
    and the BKT-crossing M08 check skip it (M09 carries NO transition to locate —
    its signature is the ⟨|m|⟩(L) drift toward 0), and ``check_m09`` claims it, with
    the per-L (L, ⟨|m|⟩) arrays the page needs and the headline drift verdict the
    check re-derives.
    """
    ratio_str = " → ".join(f"{r:.3f}" for r in result.ratios) or "—"
    verdict = ("Mermin–Wagner confirmed" if result.monotone_decreasing
               else "ABSENCE NOT reproduced")
    headline = (
        f"2D Heisenberg (T={result.T}): ⟨|m|⟩ drifts "
        f"{', '.join(f'{m:.3f}' for m in result.abs_mag)} across L="
        f"{', '.join(map(str, result.L_values))} (ratios {ratio_str}) — "
        f"{verdict}: no finite-T order · {result.wall_seconds:.0f}s on {hw(result.config)}"
    )
    return {
        "experiment": "M09-heisenberg",
        "headline": headline,
        "L_values": result.L_values,
        "T": result.T,
        "abs_mag": result.abs_mag,
        "abs_mag_err": result.abs_mag_err,
        "chi": result.chi,
        "energy": result.energy,
        "acceptance": result.acceptance,
        "ratios": result.ratios,
        "slope_vs_inv_L": result.slope_vs_inv_L,
        "monotone_decreasing": result.monotone_decreasing,
        "updater": result.updater,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
