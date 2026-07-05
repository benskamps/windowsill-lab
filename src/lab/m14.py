"""M14 — random-bond Ising: the exact Nishimori-line energy, and a map toward the MNP.

The frontier of the physics ladder. The random-bond Ising model is the M11/M12 ±J
Edwards–Anderson machinery with the disorder *biased*: a fraction ``p`` of bonds are
antiferromagnetic (``J_ij = −J``), the rest ferromagnetic (``+J``). Its phase diagram
lives in the ``(p, T)`` plane, and the object of interest is the **multicritical
Nishimori point (MNP)** — where the ferro–paramagnet boundary crosses the special
**Nishimori line** ``tanh(J/T) = 1 − 2p``. The square-lattice benchmark is

    p_c ≈ 0.1094 ,   T_c ≈ 0.9528 .

### What M14 actually verifies — the exact Nishimori-line energy

Pinning the MNP *precisely* is genuinely hard (large ``L``, many realizations — a hero
run). But the Nishimori line hands the lab a **cheap, exact** calibration that needs no
critical-point precision: on the line the disorder-averaged internal energy per spin is
an identity,

    E/N = −2 J tanh(J/T) = −2 J (1 − 2p)        (square lattice, exact),

from Nishimori's gauge symmetry — true at any ``L``, not a finite-size-shifted T_c. So
M14's **verified** claim (the green leaf) is: at a spread of ``(p, T_NL(p))`` points along
the line, the measured disorder-averaged energy reproduces ``−2 tanh(1/T)`` within a tight
band. ``check_m14`` re-derives the exact target from each point's ``T`` and re-grades the
measured energy — a receipt, not an echo.

### What it maps but does NOT pin — the MNP itself

The *same* sweep walks ``p`` up the Nishimori line and watches the ferromagnetic order
parameter ⟨|m|⟩ collapse: strong order at small ``p``, gone by ``p ≈ 0.15``, passing
through the benchmark ``p_c ≈ 0.109`` region. That collapse **locates the MNP only
approximately** at the windowsill's reachable scale — and the two-lattice Binder cumulant
(the textbook precision estimator) does *not* resolve a clean crossing at ``L = 12, 24``
with tractable disorder averaging: the curves carry a large finite-size drift, exactly the
regime where the MNP is known to be hard. That approximation is reported honestly in the
prose and the report; it is **not** part of the pass/fail gate. A reproduced exact
Nishimori-line energy earns the leaf; the precise MNP stays a documented open edge — the
same honesty M12's ``[~]`` null carries, applied to the one sub-claim that is out of reach.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

# The square-lattice multicritical Nishimori point (MNP): the literature benchmark for
# the ±J random-bond Ising model (quoted p_c ≈ 0.109–0.110, T_c ≈ 0.953). The FERRO
# boundary crosses the Nishimori line here. M14 targets this as the "map" — approximately.
P_C_BENCHMARK = 0.1094
T_C_BENCHMARK = 0.9528
# The bonds-per-spin on the square lattice (2), so E/N = −2 J tanh(J/T) on the line.
BONDS_PER_SPIN = 2
# Energy-calibration tolerance, OWNED BY THE CHECK (mirrored here only for the runner-
# side hint). The Nishimori-line energy is an exact identity, so at modest L the measured
# disorder-averaged energy sits within a few ×0.01 of it (finite-size / finite-sampling);
# ±0.05 passes the trustworthy runs comfortably while a broken engine — wrong bond draw,
# wrong estimator, off the line — misses by far more. Not a fudge: it is a hard identity,
# not a fitted critical temperature.
ENERGY_TOL = 0.05


@dataclass
class M14Result:
    p_values: list                 # AF-bond fractions swept along the Nishimori line
    T_values: list                 # T_NL(p) for each p
    L_values: list                 # the map lattice sizes (gate uses the largest)
    gate_L: int                    # the L the energy calibration is graded on
    # Per-L map arrays (parallel to p_values), keyed by str(L):
    energy_by_L: dict              # {L: [E/N(p)]}
    energy_err_by_L: dict
    abs_mag_by_L: dict             # {L: [⟨|m|⟩(p)]} — the ferromagnetic order parameter
    binder_by_L: dict              # {L: [U(p)]} — magnetic Binder cumulant
    energy_exact: list             # exact −2 tanh(1/T) at each point (identical across L)
    calibration_points: list       # [{p, T, energy, energy_err, energy_exact, abs_dev}] at gate_L
    max_energy_dev: float          # max_p |E_measured − E_exact| at gate_L — the headline
    energy_resolved: bool          # every gate-L point within ENERGY_TOL (the [x] claim)
    on_nishimori_line: bool        # every (p, T) sits on the line
    mnp_order_p_half: float | None  # p where ⟨|m|⟩(gate_L) drops through ½ — approx MNP marker
    binder_crossing_p: float | None  # two-L Binder crossing in p, or None (does not resolve)
    p_c_benchmark: float
    t_c_benchmark: float
    n_realizations: int
    wall_seconds: float
    config: dict = field(default_factory=dict)


def _cross_below(xs, ys, level) -> float | None:
    """First x where ``ys`` crosses from above ``level`` to below, linear-interpolated.

    Used to locate where the ferromagnetic ⟨|m|⟩(p) falls through ½ as p rises — a
    scale-reachable *approximate* marker of where ferro order dies on the Nishimori line.
    Returns ``None`` if it never crosses in-window. Stdlib only, so the check could
    re-derive it too.
    """
    for i in range(len(xs) - 1):
        if ys[i] >= level > ys[i + 1]:
            denom = ys[i + 1] - ys[i]
            if denom == 0:
                return float(xs[i])
            return float(xs[i] + (level - ys[i]) * (xs[i + 1] - xs[i]) / denom)
    return None


def _binder_crossing_p(ps, u_small, u_large) -> float | None:
    """The p where two Binder curves cross (small-L above → below large-L), or ``None``.

    Below the MNP the larger lattice is more ordered (U_large > U_small); above it the
    order washes out faster on the larger lattice (U_large < U_small). So ``d = U_large −
    U_small`` runs ``+ → −`` with rising p, and the crossing is the first sign change.
    Mirrors ``m12.pair_crossing`` but in the p direction. Returns ``None`` when the curves
    do not cross in-window — the honest outcome at ``L = 12, 24`` (a documented no-resolve,
    never a fabricated p_c).
    """
    d = [ul - us for us, ul in zip(u_small, u_large)]
    for i in range(len(d) - 1):
        if d[i] >= 0.0 and d[i + 1] < 0.0:
            denom = d[i + 1] - d[i]
            if denom == 0:
                return float(ps[i])
            return float(ps[i] + (0.0 - d[i]) * (ps[i + 1] - ps[i]) / denom)
    return None


def run_m14(
    p_values=(0.04, 0.06, 0.08, 0.10, 0.1094, 0.12, 0.14, 0.16),
    L_values=(12, 24),
    n_realizations: int = 64,
    n_sweeps: int = 10000,
    n_burnin: int = 4000,
    seed: int = 42,
    device: str = "cuda",
    progress=None,
) -> M14Result:
    """Sweep the Nishimori line: verify the exact energy, map the ferro-order collapse.

    For each lattice size in ``L_values`` and each AF-bond fraction ``p``, run the
    random-bond engine at ``T = T_NL(p)`` over ``n_realizations`` disorder samples and
    collect the disorder-averaged energy/spin, ⟨|m|⟩ and magnetic Binder cumulant. The
    energy at the largest L is graded against the exact ``−2 tanh(1/T)`` (the verified
    claim); ⟨|m|⟩ and the two-L Binder crossing map the MNP approximately. ``check_m14``
    re-derives the energy verdict from the reported calibration points.
    """
    from .random_bond import (
        RandomBondConfig, run, nishimori_temperature, nishimori_energy_per_spin,
    )

    t0 = time.time()
    p_values = [float(p) for p in p_values]
    L_values = [int(L) for L in L_values]
    gate_L = max(L_values)
    T_values = [nishimori_temperature(p) for p in p_values]
    energy_exact = [nishimori_energy_per_spin(T) for T in T_values]

    energy_by_L, energy_err_by_L, abs_mag_by_L, binder_by_L = {}, {}, {}, {}
    on_nl = True
    for li, L in enumerate(L_values):
        e_row, ee_row, m_row, u_row = [], [], [], []
        for pi, p in enumerate(p_values):
            cfg = RandomBondConfig(
                L=L, p=p, T=T_values[pi], n_realizations=n_realizations,
                n_sweeps=n_sweeps, n_burnin=n_burnin,
                seed=seed + 1009 * li + 17 * pi, device=device,
            )
            r = run(cfg)
            e_row.append(r.energy)
            ee_row.append(r.energy_err)
            m_row.append(r.abs_mag)
            u_row.append(r.binder)
            on_nl = on_nl and r.on_nishimori_line
            if progress is not None:
                progress(L, p, r)
        energy_by_L[str(L)] = e_row
        energy_err_by_L[str(L)] = ee_row
        abs_mag_by_L[str(L)] = m_row
        binder_by_L[str(L)] = u_row

    # Energy calibration verdict, graded at the largest L (least finite-size drift).
    gate_e = energy_by_L[str(gate_L)]
    gate_ee = energy_err_by_L[str(gate_L)]
    calibration_points = []
    for pi, p in enumerate(p_values):
        dev = abs(gate_e[pi] - energy_exact[pi])
        calibration_points.append({
            "p": p, "T": T_values[pi], "energy": gate_e[pi],
            "energy_err": gate_ee[pi], "energy_exact": energy_exact[pi],
            "abs_dev": dev,
        })
    max_dev = max(pt["abs_dev"] for pt in calibration_points)
    energy_resolved = bool(max_dev <= ENERGY_TOL and on_nl)

    # Approximate MNP markers (reported, NOT gated): where ferro order dies on the line.
    p_half = _cross_below(p_values, abs_mag_by_L[str(gate_L)], 0.5)
    crossing_p = None
    if len(L_values) >= 2:
        Ls = sorted(L_values)
        crossing_p = _binder_crossing_p(
            p_values, binder_by_L[str(Ls[0])], binder_by_L[str(Ls[-1])]
        )

    result = M14Result(
        p_values=p_values, T_values=T_values, L_values=L_values, gate_L=gate_L,
        energy_by_L=energy_by_L, energy_err_by_L=energy_err_by_L,
        abs_mag_by_L=abs_mag_by_L, binder_by_L=binder_by_L,
        energy_exact=energy_exact, calibration_points=calibration_points,
        max_energy_dev=max_dev, energy_resolved=energy_resolved, on_nishimori_line=on_nl,
        mnp_order_p_half=p_half, binder_crossing_p=crossing_p,
        p_c_benchmark=P_C_BENCHMARK, t_c_benchmark=T_C_BENCHMARK,
        n_realizations=n_realizations,
        wall_seconds=time.time() - t0,
        config={
            "p_values": p_values, "L_values": L_values, "gate_L": gate_L,
            "n_realizations": n_realizations, "n_sweeps": n_sweeps,
            "n_burnin": n_burnin, "seed": seed, "device": device,
            "model": "random-bond-ising-2d", "disorder": "bimodal-pm-J",
            "line": "nishimori", "updater": "checkerboard-metropolis",
        },
    )
    if progress is not None and hasattr(progress, "done"):
        progress.done(result)
    return result


def to_report(result: M14Result) -> dict:
    """A JSON report shaped for the page + the M14 check.

    Distinct ``experiment`` tag (``M14-random-bond-nishimori``) so no other check
    misreads it. Carries the per-L Nishimori-line map (p, T, energy, ⟨|m|⟩, Binder), the
    exact energy targets, and the ``calibration_points`` at the gate L so ``check_m14`` can
    re-derive the exact-energy verdict. The MNP markers ride along as documented
    approximations. When the exact energy is NOT reproduced the report carries
    ``status: "null"`` — an honest failed-calibration grey leaf, never a fake green.
    """
    ph = result.mnp_order_p_half
    ph_str = f"p≈{ph:.3f}" if ph is not None else "unresolved"
    verdict = ("exact Nishimori-line energy reproduced"
               if result.energy_resolved
               else "Nishimori-line energy off — calibration null")
    headline = (
        f"2D random-bond Ising (±J, {result.n_realizations} disorder realizations) on the "
        f"Nishimori line: measured disorder-averaged energy matches the exact "
        f"−2·tanh(1/T) across p∈[{min(result.p_values):.2f},{max(result.p_values):.2f}] "
        f"to within Δ={result.max_energy_dev:.3f} (L={result.gate_L}) — {verdict}. "
        f"Ferro order collapses near {ph_str}, bracketing the multicritical Nishimori "
        f"point p_c≈{result.p_c_benchmark:.4f}, T_c≈{result.t_c_benchmark:.4f} "
        f"(precise pinning deferred — a hero run) · {result.wall_seconds:.0f}s"
    )
    report = {
        "experiment": "M14-random-bond-nishimori",
        "headline": headline,
        "p_values": result.p_values,
        "T_values": result.T_values,
        "L_values": result.L_values,
        "gate_L": result.gate_L,
        "energy_by_L": result.energy_by_L,
        "energy_err_by_L": result.energy_err_by_L,
        "abs_mag_by_L": result.abs_mag_by_L,
        "binder_by_L": result.binder_by_L,
        "energy_exact": result.energy_exact,
        "calibration_points": result.calibration_points,
        "max_energy_dev": result.max_energy_dev,
        "energy_resolved": result.energy_resolved,
        "on_nishimori_line": result.on_nishimori_line,
        "mnp_order_p_half": result.mnp_order_p_half,
        "binder_crossing_p": result.binder_crossing_p,
        "p_c_benchmark": result.p_c_benchmark,
        "t_c_benchmark": result.t_c_benchmark,
        "n_realizations": result.n_realizations,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
    # Honest failed-calibration marker: a folded grey leaf, never a green one. Omitted
    # when resolved (the archive/check grades that). The check re-derives independently.
    if not result.energy_resolved:
        report["status"] = "null"
    return report
