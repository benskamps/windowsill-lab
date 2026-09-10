"""U-K02 — an attempt on the field unknown, not another price of it.

**The question, exactly as narrowed on 2026-09-03.** On a regular
(deterministic-quantile) Lorentzian frequency class, is the *subcritical*
Kuramoto **fluctuation** exponent γ′ — the one on ``χ = N·Var_t(r)`` — Daido's
value or Hong, Chaté, Tang & Park's? Both parties agree on the supercritical
γ = 1/4; the contested cell is exactly one, and this module measures that cell.

**Why K03 cannot answer it.** K03 instruments a linear RESPONSE, ``∂⟨cos θ⟩/∂h``.
Both published rivals are FLUCTUATION exponents. They are different objects and
Hong et al. give the response a different symbol and a different value in the
same paragraph. A response slope landing near 1 would coincide numerically with
Daido's γ′ and report "Daido confirmed, Hong refuted" with both halves wrong.
So this module measures ``N·Var_t(r)`` and nothing else.

**Units, stated because the literature does not.** Daido writes exponents on
``σ = sqrt(N·Var)``; the modern literature squares them silently onto χ. On χ:

    Daido  γ′ = 1        (σ-exponent 1/2, Prog. Theor. Phys. 81, 727 (1989) Eq. 12)
    Hong   γ′ = 0.25(1)  (PRE 92, 022122 (2015) §IV B, regular class)

Every number this module reports is in **χ units**, and the receipt says so.
Reporting a σ-exponent against a χ rival is the same class of error as the
response/fluctuation mismatch above, and it is the one this entry has already
been bitten by twice.

**The clip is controlled before anything expensive.** ``lorentzian_frequencies``
clips the tails at |ω| ≤ 40γ, which moves 32 of 2000 oscillators — the largest by
616.6 in ω. UNKNOWNS.md records the effect on the exponent as *undetermined* and
says so: "that is the argument for running the clip control before anything
expensive, not after." :func:`clip_control` widens the clip and asks whether the
answer moves. A run that skips it is measuring this engine's g(ω), which is
strictly neither paper's.

**Critical slowing down is budgeted.** The noise on the subcritical branch scales
as ε^-0.76 while K03 pinned ``T_MEASURE`` at 2000 for every column, which is what
made its subcritical columns unusable. Measurement time here scales with ε.
UNKNOWNS.md is explicit that ``T_MEASURE`` is the one axis that must not be cut.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field as dc_field

import numpy as np

from . import kuramoto as ku
from . import kuramoto_gpu as kgpu

#: Rival predictions, in CHI units. See the units note above.
DAIDO_GAMMA_PRIME = 1.0
HONG_GAMMA_PRIME = 0.25
HONG_GAMMA_PRIME_ERR = 0.01
RIVAL_GAP = DAIDO_GAMMA_PRIME - HONG_GAMMA_PRIME      # 0.75

#: The measured noise scaling that sets the time budget (U-K02 reach evidence).
NOISE_EPS_EXPONENT = -0.76

#: Reference column for the time budget: ε and the steps that sufficed there.
REF_EPS = 0.30
REF_MEASURE_STEPS = 200_000

OBSERVE_EVERY = 20          # samples of r; dt=0.01 ⇒ one sample per 0.2 time units
BURN_FRACTION = 0.25        # discard this share of the run before measuring
#: Measurement blocks. Block-to-block scatter of chi is the error bar; a
#: running variance over autocorrelated samples carries none of its own.
BLOCKS = 8


def measure_steps_for(eps: float, *, ref_eps: float = REF_EPS,
                      ref_steps: int = REF_MEASURE_STEPS,
                      cap: int = 6_000_000) -> int:
    """Steps needed at ``eps`` so the statistical error matches the reference.

    Noise ~ ε^-0.76 and the error on a time average falls as 1/sqrt(T), so the
    time needed to hold the error fixed grows as ε^(2*-0.76) = ε^-1.52. Capped,
    because an uncapped budget silently turns a night into a week.
    """
    if eps <= 0:
        raise ValueError("eps must be positive (subcritical branch)")
    scale = (eps / ref_eps) ** (2.0 * NOISE_EPS_EXPONENT)
    return int(min(cap, max(ref_steps, ref_steps * scale)))


@dataclass
class Column:
    eps: float
    coupling: float
    n: int
    clip_scale: float
    dt: float
    steps: int
    burn_steps: int
    samples: int
    mean_r: float
    mean_r2: float
    var_r: float
    chi: float                  # N * Var_t(r)
    chi_err: float              # block-to-block standard error on chi
    blocks: int
    block_chi: list[float]
    sigma: float                # sqrt(N * Var_t(r)) — Daido's own units
    wall_seconds: float


def chi_column(eps: float, *, n: int, clip_scale: float = ku.OMEGA_CLIP_SCALE,
               dt: float | None = None, steps: int | None = None,
               gamma: float = ku.GAMMA, seed: int = 20260909,
               device: str = "cuda") -> Column:
    """Measure ``χ = N·Var_t(r)`` at one SUBCRITICAL ε = (K_c − K)/K_c."""
    kc = ku.critical_coupling(gamma)
    coupling = kc * (1.0 - eps)
    # Widening the clip lengthens the fastest drifter, so dt must shrink with it
    # or RK4 is integrating a frequency it cannot resolve. |ω|·dt is held fixed.
    if dt is None:
        dt = ku.DT * (ku.OMEGA_CLIP_SCALE / clip_scale)
    if steps is None:
        steps = measure_steps_for(eps)
        steps = int(steps * (ku.DT / dt))       # same physical time, finer steps
    burn = int(steps * BURN_FRACTION)

    omega = ku.lorentzian_frequencies(n, gamma=gamma, clip_scale=clip_scale)
    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(-math.pi, math.pi, size=n)

    t0 = time.time()
    th = kgpu.to_device(theta0, device=device)
    om = kgpu.to_device(omega, device=device)
    kk = kgpu.to_device(np.array(coupling), device=device)
    out = kgpu.evolve(th, om, kk, dt, burn, observe_every=0)   # burn in, unobserved

    # Measure in BLOCKS. r is strongly autocorrelated near K_c, so the spread of
    # a running variance says nothing about its error. Block means are close
    # enough to independent to carry one, and the block-to-block scatter of chi
    # IS the error bar. Without it the fit's stderr would only describe scatter
    # about the line and would badly under-report — which is how a noisy window
    # produces a confident wrong exponent.
    per_block = max(1, (steps - burn) // BLOCKS)
    block_chi, block_r, block_r2, samples = [], [], [], 0
    theta = out["theta"]
    for _ in range(BLOCKS):
        out = kgpu.evolve(theta, om, kk, dt, per_block,
                          observe_every=OBSERVE_EVERY, observable="r")
        theta = out["theta"]
        if not out["n_samples"]:
            continue
        b_var = max(0.0, out["mean_r2"] - out["mean_r"] ** 2)
        block_chi.append(n * b_var)
        block_r.append(out["mean_r"])
        block_r2.append(out["mean_r2"])
        samples += out["n_samples"]
    wall = time.time() - t0

    if not block_chi:
        raise RuntimeError(f"eps={eps}: no block produced a sample")
    chi = float(np.mean(block_chi))
    chi_err = (float(np.std(block_chi, ddof=1) / math.sqrt(len(block_chi)))
               if len(block_chi) > 1 else float("nan"))
    mean_r = float(np.mean(block_r))
    mean_r2 = float(np.mean(block_r2))
    var_r = max(0.0, mean_r2 - mean_r * mean_r)
    return Column(eps=eps, coupling=coupling, n=n, clip_scale=clip_scale, dt=dt,
                  steps=steps, burn_steps=burn, samples=samples,
                  mean_r=mean_r, mean_r2=mean_r2, var_r=var_r,
                  chi=chi, chi_err=chi_err, blocks=len(block_chi),
                  block_chi=[float(c) for c in block_chi],
                  sigma=math.sqrt(chi), wall_seconds=round(wall, 2))


def fit_exponent(columns: list[Column]) -> dict:
    """Fit ``χ ~ ε^(−γ′)`` by least squares on log χ vs log ε.

    Returns the slope with its standard error AND the per-adjacent-pair local
    slopes, because a true power law has a constant local slope and a drifting
    one is a crossover being averaged over — the defect U-K01 found in K03.
    """
    cols = sorted(columns, key=lambda c: c.eps)
    x = np.log(np.array([c.eps for c in cols]))
    y = np.log(np.array([c.chi for c in cols]))
    if len(x) < 3:
        raise ValueError("need at least three columns to fit and to see drift")
    # Weight by each column's own measured error, propagated into log space
    # (d(log chi) = dchi/chi). A column the instrument could barely see must not
    # pull the slope as hard as one it saw cleanly.
    w = np.array([1.0 / max(1e-12, (c.chi_err / c.chi)) ** 2
                  if c.chi > 0 and math.isfinite(c.chi_err) else 1.0
                  for c in cols])
    slope, intercept = np.polyfit(x, y, 1, w=np.sqrt(w))
    resid = y - (slope * x + intercept)
    dof = len(x) - 2
    chi2 = float((w * resid * resid).sum())
    s_err = float(np.sqrt(max(chi2 / dof, 1.0) / (w * (x - x.mean()) ** 2).sum()))
    local = [float(-(y[i + 1] - y[i]) / (x[i + 1] - x[i])) for i in range(len(x) - 1)]
    return {
        "gamma_prime": float(-slope),
        "stderr": s_err,
        "r_squared": float(1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))),
        "local_slopes": local,
        "local_slope_spread": float(max(local) - min(local)) if local else 0.0,
        "chi2_per_dof": chi2 / dof,
        "units": "chi = N*Var_t(r)",
    }


def adjudicate(fit: dict) -> dict:
    """Distance to each rival, in the fit's own sigmas. Refuses when it cannot see.

    A fit whose local slopes scatter is not measuring a power law, and a number
    produced from one must not be pointed at a published claim. That is the
    U-K01 lesson applied before the verdict rather than after it.
    """
    g, se = fit["gamma_prime"], fit["stderr"]
    if not (se > 0) or not math.isfinite(g):
        return {"verdict": "unresolved", "why": "the fit returned no usable error"}
    drift = fit["local_slope_spread"]
    d_daido = abs(g - DAIDO_GAMMA_PRIME) / se
    d_hong = abs(g - HONG_GAMMA_PRIME) / se
    out = {"sigma_from_daido": d_daido, "sigma_from_hong": d_hong,
           "local_slope_spread": drift}
    # The window must be a power law before its slope means anything. A spread
    # comparable to the rival gap says the columns disagree with each other more
    # than the rivals disagree with one another.
    if drift > RIVAL_GAP:
        out["verdict"] = "unresolved"
        out["why"] = (f"local slopes span {drift:.3f}, wider than the {RIVAL_GAP} "
                      "gap between the rivals — this window is not a power law, "
                      "so its slope adjudicates nothing")
        return out
    if d_daido < 3 and d_hong < 3:
        out["verdict"] = "unresolved"
        out["why"] = "within 3 sigma of BOTH rivals — the fit does not separate them"
    elif d_hong < 3 <= d_daido:
        out["verdict"] = "supports-hong"
        out["why"] = f"{d_hong:.1f} sigma from Hong, {d_daido:.1f} from Daido"
    elif d_daido < 3 <= d_hong:
        out["verdict"] = "supports-daido"
        out["why"] = f"{d_daido:.1f} sigma from Daido, {d_hong:.1f} from Hong"
    else:
        out["verdict"] = "excludes-both"
        out["why"] = (f"{d_daido:.1f} sigma from Daido and {d_hong:.1f} from Hong "
                      "— consistent with neither published value")
    return out


@dataclass
class ClipControl:
    eps_values: list[float]
    n: int
    narrow: list[Column] = dc_field(default_factory=list)
    wide: list[Column] = dc_field(default_factory=list)
    verdict: str = "unrun"
    detail: str = ""


def clip_control(eps_values, *, n: int = 20_000, wide_scale: float = 400.0,
                 steps: int | None = None, device: str = "cuda") -> ClipControl:
    """Does the tail clip move the answer? Run this before anything expensive.

    Same ε at the production clip (40γ, 32 of 2000 oscillators displaced) and at
    a clip ten times wider (4 of 2000), with dt scaled so |ω|·dt is unchanged. If
    χ agrees column by column, the clip is not deciding the exponent. If it does
    not, every number this engine has produced on this branch is about a
    frequency distribution that is neither paper's, and that is the finding.
    """
    cc = ClipControl(eps_values=list(eps_values), n=n)
    for eps in cc.eps_values:
        cc.narrow.append(chi_column(eps, n=n, clip_scale=ku.OMEGA_CLIP_SCALE,
                                    steps=steps, device=device))
        cc.wide.append(chi_column(eps, n=n, clip_scale=wide_scale,
                                  steps=steps, device=device))
    ratios = [w.chi / nn.chi for nn, w in zip(cc.narrow, cc.wide) if nn.chi > 0]
    if not ratios:
        cc.verdict, cc.detail = "unreadable", "no column produced a positive chi"
        return cc
    worst = max(abs(math.log(r)) for r in ratios)
    spread = max(ratios) - min(ratios)
    # 10% in chi is well under what would move a slope across the 0.75 rival gap.
    if worst < math.log(1.10):
        cc.verdict = "clip-harmless"
        cc.detail = (f"chi agrees to within {100*(math.exp(worst)-1):.1f}% at every "
                     f"eps across a 10x clip widening (ratios {min(ratios):.3f}"
                     f"-{max(ratios):.3f}); the clip is not setting the exponent")
    else:
        cc.verdict = "clip-matters"
        cc.detail = (f"chi moves by up to {100*(math.exp(worst)-1):.1f}% when the "
                     f"clip is widened 10x (spread {spread:.3f}) — this engine's "
                     "g(omega) is deciding the answer, and it is neither paper's")
    return cc
