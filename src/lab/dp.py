"""Directed percolation in 2+1 dimensions — the engine.

A synchronous probabilistic cellular automaton on a periodic L×L lattice. Each
site has five *parents* at the previous step — itself and its four nearest
neighbours — and each active parent transmits activity independently with
probability p, so

    P(s_i(t+1) = 1) = 1 − (1−p)^{n_i(t)},    n_i = # active among the 5 parents.

The all-zero configuration is **absorbing by construction**: n = 0 gives
probability exactly 0, with no thermal escape. That is what makes this a
non-equilibrium *absorbing-state* transition rather than an equilibrium one, and
it is why this is the right first Phase-4 rung — directed percolation is the
canonical, most robustly measured absorbing-state universality class there is.

### What is being measured

Starting from a fully active lattice, the density obeys

    rho(t) ~ t^(−delta)   at p = p_c,    delta = beta / nu_parallel.

For (2+1)d DP the literature value is **delta = 0.4505** (Hinrichsen 2000, Adv.
Phys. 49, 815, from beta = 0.583(4) and nu_par = 1.295(6)). Above the upper
critical dimension d_c = 4 mean-field takes over and delta = 1, so 2+1d sits
genuinely below d_c and the measurement distinguishes the real class from the
mean-field one instead of merely confirming that something decays.

### Why this engine brackets instead of hitting p_c exactly

At fixed t the effective exponent

    delta_eff(t) = − d ln rho / d ln t

is **monotonically decreasing in p**: more transmission means slower decay. So a
subcritical p makes delta_eff curve upward without bound and a supercritical p
makes it fall toward 0, and any pair that straddles p_c *bounds* the true
exponent between their two curves. That is a rigorous statement obtainable at
finite resolution, whereas quoting delta at a single p demands knowing p_c to
more digits than a finite lattice can deliver. p_c is reported as a measurement
with its bracket, never assumed and never read from a table.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch

#: Literature exponent for the (2+1)d DP class — the calibration target.
#: Hinrichsen (2000) Adv. Phys. 49, 815: beta = 0.583(4), nu_par = 1.295(6).
DELTA_DP_2P1 = 0.4505

#: Mean-field value, valid only at or above the upper critical dimension d_c = 4.
#: 2+1d must NOT land here; excluding it is a graded claim, not a remark.
DELTA_MEAN_FIELD = 1.0

#: self + 4 nearest neighbours
N_PARENTS = 5


def step(state: torch.Tensor, p: float, gen: torch.Generator) -> torch.Tensor:
    """One synchronous update of every site."""
    n = (state
         + torch.roll(state, 1, dims=-2) + torch.roll(state, -1, dims=-2)
         + torch.roll(state, 1, dims=-1) + torch.roll(state, -1, dims=-1))
    prob = 1.0 - torch.pow(1.0 - p, n)
    rand = torch.rand(state.shape, generator=gen, device=state.device,
                      dtype=torch.float32)
    return (rand < prob).to(state.dtype)


def correlation_reach(t: int, z: float = 1.766) -> float:
    """xi_perp ~ t^(1/z) — how far correlations have spread by time t.

    The lattice must stay comfortably larger than this or the measurement is
    reading the box instead of the physics.
    """
    return float(t) ** (1.0 / z)


@dataclass
class DecayRun:
    p: float
    L: int
    batch: int
    t_max: int
    seed: int
    device: str
    rho: list[float] = field(default_factory=list)
    absorbed_at: int | None = None

    @property
    def sites(self) -> int:
        return self.batch * self.L * self.L

    @property
    def finite_size_headroom(self) -> float:
        """L / xi_perp(t_max) — how many correlation lengths fit in the box."""
        return self.L / correlation_reach(self.t_max)


def run_decay(p: float, L: int = 2048, batch: int = 4, t_max: int = 50_000,
              device: str = "cuda", seed: int = 2026,
              progress=None) -> DecayRun:
    """Density decay from a fully active lattice."""
    dev = torch.device(device)
    gen = torch.Generator(device=dev)
    gen.manual_seed(seed)
    state = torch.ones((batch, L, L), device=dev, dtype=torch.uint8)
    run = DecayRun(p=p, L=L, batch=batch, t_max=t_max, seed=seed, device=device,
                   rho=[1.0])
    for t in range(1, t_max + 1):
        state = step(state, p, gen)
        r = float(state.to(torch.float32).mean())
        run.rho.append(r)
        if r == 0.0:
            # absorbing means absorbing: no need to keep stepping, and the tail
            # is exactly zero rather than approximately so.
            run.absorbed_at = t
            run.rho.extend([0.0] * (t_max - t))
            break
        if progress and t % max(1, t_max // 10) == 0:
            progress(t, t_max, r)
    return run


def fit_exponent(rho: list[float], t_lo: int, t_hi: int) -> tuple[float, float, int]:
    """Least-squares slope of ln rho vs ln t. Returns (delta, R^2, n_points)."""
    xs, ys = [], []
    for t in range(int(t_lo), min(int(t_hi), len(rho) - 1) + 1):
        if rho[t] > 0.0:
            xs.append(math.log(t))
            ys.append(math.log(rho[t]))
    n = len(xs)
    if n < 8:
        return float("nan"), float("nan"), n
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return float("nan"), float("nan"), n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    inter = my - slope * mx
    ss_res = sum((y - (slope * x + inter)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return -slope, r2, n


def effective_exponent(rho: list[float], t: int, b: float = 2.0) -> float:
    """delta_eff(t) from a two-point log-log slope over a factor-b window."""
    t2 = int(t / b)
    if t2 < 1 or t >= len(rho) or rho[t] <= 0 or rho[t2] <= 0:
        return float("nan")
    return -(math.log(rho[t]) - math.log(rho[t2])) / math.log(b)


def curvature(rho: list[float], t_max: int) -> float:
    """Drift of delta_eff across the last two octaves.

    Positive => still curving up (subcritical). Negative => bending over
    (supercritical). Near zero => the power law is holding, i.e. near p_c.
    """
    late = effective_exponent(rho, t_max)
    early = effective_exponent(rho, t_max // 4)
    if math.isnan(late) or math.isnan(early):
        return float("nan")
    return late - early


def exponential_decay_quality(rho: list[float], t_lo: int, t_hi: int) -> float:
    """R^2 of ln rho vs t (NOT ln t) — how exponential the decay looks.

    Deep in the absorbing phase the decay is exponential, so this should beat the
    power-law fit badly. It is the negative control that stops the pipeline from
    calling any falling curve a critical power law.
    """
    xs, ys = [], []
    for t in range(int(t_lo), min(int(t_hi), len(rho) - 1) + 1):
        if rho[t] > 0.0:
            xs.append(float(t))
            ys.append(math.log(rho[t]))
    n = len(xs)
    if n < 8:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return float("nan")
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    inter = my - slope * mx
    ss_res = sum((y - (slope * x + inter)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def absorbing_state_holds(L: int = 64, batch: int = 4, steps: int = 200,
                          p: float = 0.9, device: str = "cuda",
                          seed: int = 1) -> bool:
    """From an all-zero lattice, nothing may ever switch on — even at large p.

    The defining property of an absorbing state, and a decisive code check: a
    sign slip or an off-by-one in the parent count would let activity appear
    from nothing, and every exponent above it would be measuring a different
    model than the one claimed.
    """
    dev = torch.device(device)
    gen = torch.Generator(device=dev)
    gen.manual_seed(seed)
    state = torch.zeros((batch, L, L), device=dev, dtype=torch.uint8)
    for _ in range(steps):
        state = step(state, p, gen)
        if float(state.to(torch.float32).sum()) != 0.0:
            return False
    return True
