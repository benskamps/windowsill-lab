"""U-M01 reach test — can this box tell RSB from droplet in the 3D spin glass?

The question is one of the long-standing open problems in statistical
mechanics: below T_c, does the Edwards-Anderson spin glass have the
many-states structure of replica symmetry breaking, or the two-state droplet
picture? The discriminator is standard and sharp — **the weight of the overlap
distribution at zero**:

* **RSB**: P(0) approaches a finite constant as L → ∞.
* **Droplet**: P(0) → 0 as ``L^-theta``, with θ ≈ 0.2 in three dimensions.

So the whole question is an L-scaling of one number, and the feasibility
question is whether this box can measure that number well enough, at enough
sizes, to tell a 13% decay from no decay.

## Why the error scales as 1/sqrt(realizations)

P(0) is the textbook example of a **non-self-averaging** observable: in the RSB
picture its sample-to-sample fluctuations do not shrink with system size, so
averaging more spins inside one disorder realization does not help. The
disorder average over independent realizations is therefore the binding
statistical resource, and error ~ 1/sqrt(N_realizations) is the right scaling
rather than a conservative one.

## The finding that came before any of that

M12 has run four times and **never stored P(q) per L** — only at a single
reference size. The one observable this question needs has been generated and
discarded on every pass. That is cheap to fix and it is the actual blocker,
which is exactly the kind of thing a feasibility test is for: the expensive
answer was not "we need a bigger computer".
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

#: Domain-wall stiffness exponent in 3D. The droplet prediction P(0) ~ L^-theta
#: uses it; the literature value sits near 0.2 and the verdict below is not
#: sensitive to the third digit.
THETA_3D = 0.20

#: Separation demanded before the two pictures count as distinguishable.
SIGMA_REQUIRED = 3.0


def p_at_zero(pq_row, n_bins: int) -> float:
    """Density of the overlap distribution at q = 0."""
    return float(pq_row[n_bins // 2])


def stat_error(p0: float, bin_width: float, n_realizations: int) -> float:
    """Error on the disorder-averaged P(0) from a finite realization count."""
    counts = max(p0 * bin_width * n_realizations, 1.0)
    return (math.sqrt(counts) / n_realizations) / bin_width


def droplet_drop(l_small: int, l_large: int, theta: float = THETA_3D) -> float:
    """Fractional fall in P(0) the droplet picture predicts across an L range."""
    return 1.0 - (l_large / l_small) ** (-theta)


def run(receipt: Path, l_small: int = 6, l_large: int = 12) -> dict:
    d = json.loads(Path(receipt).read_text(encoding="utf-8"))
    pq = np.asarray(d["pq_ref"], dtype=float)
    T = np.asarray(d["T"], dtype=float)
    tc = float(d["crossing_T"])
    n_real = int(d["n_realizations"])
    sizes = list(d["L_values"])
    n_bins = pq.shape[1]
    bin_width = 2.0 / (n_bins - 1)

    # Deepest temperature in the glass phase — where the two pictures differ most
    # and where equilibration is hardest, so it is also the honest place to ask.
    idx = int(np.argmin(T))
    p0 = p_at_zero(pq[idx], n_bins)
    err = stat_error(p0, bin_width, n_real)
    rel = err / p0 if p0 else float("inf")

    effect = droplet_drop(l_small, l_large)
    # Comparing two independent sizes, so the difference carries both errors.
    sigma = effect / (rel * math.sqrt(2.0)) if rel else float("inf")

    stored_per_size = "pq_by_L" in d or "pq" in d and isinstance(d.get("pq"), dict)
    needed = int(math.ceil(n_real * (SIGMA_REQUIRED / sigma) ** 2)) if sigma else None

    if not stored_per_size:
        reach = "out-of-reach"
        detail = (
            f"the discriminating observable is not recorded. M12 stores P(q) at "
            f"one reference size (L = {d.get('pq_ref_L')}) and the question is "
            f"entirely about how P(0) scales with L, so the number this needs "
            f"has been generated on every pass over sizes {sizes} and thrown "
            f"away. Fixing that is a serialisation change, not a compute one — "
            f"and until it lands, no amount of GPU time answers this")
    elif sigma >= SIGMA_REQUIRED:
        reach, detail = "in-reach", (
            f"P(0) = {p0:.4f} +/- {err:.4f} at T/Tc = {T[idx]/tc:.2f} separates "
            f"the two pictures at {sigma:.1f} sigma across L = {l_small}-{l_large}")
    else:
        reach = "out-of-reach"
        detail = (
            f"at T/Tc = {T[idx]/tc:.2f}, P(0) = {p0:.4f} +/- {err:.4f} — a "
            f"**{100*rel:.0f}%** relative error from {n_real} disorder "
            f"realizations. The droplet picture predicts only a "
            f"**{100*effect:.0f}%** fall across L = {l_small} to {l_large}, so "
            f"the two pictures sit **{sigma:.1f} sigma** apart in this data. "
            f"P(0) does not self-average, so the only lever is realizations: "
            f"reaching {SIGMA_REQUIRED:.0f} sigma needs about **{needed:,}** of "
            f"them, roughly {needed/n_real:.0f}x this run")

    return {
        "unknown": "U-M01", "receipt": Path(receipt).name,
        "reach": reach, "detail": detail,
        "sizes": sizes, "n_realizations": n_real,
        "T_over_Tc": float(T[idx] / tc), "p_at_zero": p0, "stat_error": err,
        "relative_error": rel, "droplet_effect": effect,
        "sigma_separation": sigma,
        "realizations_needed": needed,
        "pq_stored_per_size": bool(stored_per_size),
        "what_would_change_it": (
            "two things, in order: store P(q) per L instead of at one reference "
            "size, then raise the realization count. The first is free and "
            "without it the second is wasted"),
    }
