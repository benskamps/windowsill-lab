"""Parallel tempering — the exchange move, isolated so it can be graded alone.

`spin_glass.py` says, in its own docstring, exactly where single-spin Metropolis
gives out: *"There is a concrete equilibration floor at T ≈ 0.5–0.6 for L=16:
below it, single-spin Metropolis can no longer equilibrate the glass in tractable
time, and the coldest points fall into an under-equilibration dip where ⟨q²⟩ is
suppressed below the peak rather than continuing to grow (verified directly —
even 4× the burn-in does not lift the two coldest points out of the dip)."*

Four times the burn-in not lifting the dip is the important half of that
sentence. It says the wall is not compute — more sweeps do not help, because the
chain is trapped in a basin it cannot leave one spin at a time. On two home
machines with no hardware upgrade coming, an algorithm that buys ergodicity is
worth more than any number of extra sweeps, and this is the same argument Wolff
already won for the critical ferromagnet in June: *pick a better move, not a
longer wait.*

### The move

Run the temperature ladder simultaneously (which this engine already does — the
temperatures are a batch axis) and periodically offer to **exchange whole
configurations between adjacent temperatures**. A cold, trapped configuration
gets carried up to a hot temperature where barriers are cheap, wanders to a
different basin, and comes back down. Detailed balance on the extended ensemble
fixes the acceptance probability exactly:

    A = min(1, exp[(β_i − β_j)(E_i − E_j)])

with no free parameters. Note what the formula does NOT contain: any property of
the model. It is the same swap for a spin glass, a Potts model or a polymer, so
this module knows nothing about lattices and takes energies as an argument.

### Why alternating parity

Attempting every adjacent pair at once would have configuration *m* asked to swap
both up and down in the same instant, which is not a well-defined move. Standard
practice is to alternate: even pairs (0,1), (2,3)… on one attempt, odd pairs
(1,2), (3,4)… on the next. Every pair is therefore offered an exchange every two
attempts, and each attempt is a proper Metropolis move on a disjoint set of pairs.

### The diagnostic that matters more than the acceptance rate

A ladder can have a healthy-looking average acceptance and still be broken, if
one adjacent pair has near-zero acceptance: that pair is a wall, and no
configuration crosses it. :func:`ladder_health` therefore reports the **minimum**
adjacent acceptance alongside the mean, because the minimum is what decides
whether the cold end is actually connected to the hot end. Reporting only the
mean is how a tempering run convinces itself it is mixing while the coldest two
rungs sit in permanent isolation.
"""
from __future__ import annotations

import torch

#: Below this adjacent-pair acceptance the ladder is treated as broken at that
#: rung: configurations effectively do not cross. The usual target band for a
#: well-spaced ladder is 20–40 %; 5 % is not "a bit low", it is a wall.
MIN_HEALTHY_ACCEPTANCE = 0.05

#: The band a well-tuned ladder should sit in. Reported, never enforced — the
#: right response to a badly spaced ladder is to respace it, not to clamp the
#: number that revealed it.
TARGET_ACCEPTANCE = (0.20, 0.40)


def swap_acceptance(beta: torch.Tensor, energy: torch.Tensor,
                    parity: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Acceptance probabilities for the adjacent pairs of the given parity.

    ``beta`` is ``(M,)`` over the temperature ladder; ``energy`` is ``(..., M)``
    TOTAL energy (not per spin — the exponent is extensive and dividing by N
    would silently make every swap look acceptable on a large lattice).

    Returns ``(prob, lo_index)``: the acceptance for each offered pair, shaped
    ``(..., n_pairs)``, and the ``M``-index of the lower member of each pair.
    """
    m = beta.shape[-1]
    lo = torch.arange(parity, m - 1, 2, device=beta.device)
    if lo.numel() == 0:
        return energy.new_zeros(energy.shape[:-1] + (0,)), lo
    hi = lo + 1
    d_beta = beta[lo] - beta[hi]                       # (n_pairs,)
    d_energy = energy[..., lo] - energy[..., hi]       # (..., n_pairs)
    return torch.exp(d_beta * d_energy).clamp(max=1.0), lo


def exchange(state: torch.Tensor, beta: torch.Tensor, energy: torch.Tensor,
             parity: int, rng: torch.Generator,
             temp_axis: int = 1) -> tuple[torch.Tensor, torch.Tensor]:
    """Offer swaps along ``temp_axis``; return the new state and per-pair accepts.

    ``state`` carries the configurations with the temperature ladder on
    ``temp_axis``; everything else is batch. Swapping is done by exchanging the
    configurations, not the temperatures, so every downstream observable stays
    indexed by temperature and nothing else in the engine has to know a swap
    happened.

    The returned accept mask is ``(..., n_pairs)`` with the batch axes of
    ``energy``, for the health diagnostics.
    """
    prob, lo = swap_acceptance(beta, energy, parity)
    if lo.numel() == 0:
        return state, prob
    draw = torch.rand(prob.shape, generator=rng, device=prob.device)
    accept = draw < prob                               # (..., n_pairs)
    if not bool(accept.any()):
        return state, accept

    state = state.clone()
    moved = state.movedim(temp_axis, 0)                # (M, ...) view onto the clone
    hi = lo + 1
    for k in range(lo.numel()):
        i, j = int(lo[k]), int(hi[k])
        # accept[..., k] has the energy tensor's batch shape; broadcast it over
        # whatever per-configuration shape the state carries (L, L, …).
        sel = accept[..., k]
        while sel.dim() < moved[i].dim():
            sel = sel.unsqueeze(-1)
        a, b = moved[i].clone(), moved[j].clone()
        moved[i] = torch.where(sel, b, a)
        moved[j] = torch.where(sel, a, b)
    return state, accept


def ladder_health(accept_counts: torch.Tensor, attempts: torch.Tensor) -> dict:
    """Per-pair acceptance, and the summary that says whether the ladder connects.

    ``accept_counts`` and ``attempts`` are ``(M-1,)`` over adjacent pairs. The
    minimum is reported first because it is the binding constraint: one dead rung
    disconnects the cold end from the hot end no matter how good the mean looks.
    """
    attempts = attempts.clamp_min(1)
    rate = (accept_counts.float() / attempts.float())
    rates = [float(x) for x in rate.detach().cpu()]
    if not rates:
        return {"per_pair": [], "min": None, "mean": None,
                "connected": None, "reason": "no-pairs"}
    lowest = min(rates)
    return {
        "per_pair": rates,
        "min": lowest,
        "mean": float(sum(rates) / len(rates)),
        "argmin_pair": int(rate.argmin()),
        "connected": bool(lowest >= MIN_HEALTHY_ACCEPTANCE),
        "in_target_band": bool(TARGET_ACCEPTANCE[0] <= lowest <= TARGET_ACCEPTANCE[1]),
    }


def geometric_ladder(t_min: float, t_max: float, n: int) -> torch.Tensor:
    """Temperatures spaced geometrically — constant ratio, not constant step.

    A linear ladder wastes rungs at the hot end and starves the cold end, where
    the energy distributions are narrowest and the swap acceptance therefore
    falls fastest. Geometric spacing keeps Δβ·σ_E roughly constant when the heat
    capacity is roughly flat, which is the cheapest ladder that does not collapse
    at the cold end. Offered as a helper, not imposed: the existing linear ladder
    stays the default so nothing already measured moves.
    """
    if n < 2 or not (0 < t_min < t_max):
        raise ValueError("geometric_ladder needs 0 < t_min < t_max and n >= 2")
    ratio = (t_max / t_min) ** (1.0 / (n - 1))
    return torch.tensor([t_min * ratio ** k for k in range(n)], dtype=torch.float32)
