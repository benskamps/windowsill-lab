"""The limit auditor — an instrument that audits other instruments.

Half the quantities this lab reports are defined as **limits**: a susceptibility
at h → 0, a peak frequency at grid spacing → 0, an exponent at L → ∞, an
equilibrium average at t → ∞. Every one of them is computed at a single
convenient finite value of that control, and until 2026-08-24 not one of them
had ever been checked against the limit it claims to be.

The cost of not checking, measured the same day:

* **K03** estimated χ from one field ladder. The bias was **11–33%**, and — the
  part that kills you — it SHRANK with ε, so it did not cancel in the power-law
  fit, it tilted it. The reported γ = 1.064 was not a measurement.
* **A02** refines a periodogram peak by parabolic interpolation on a grid fixed
  at ``OVERSAMPLE = 10``, with a docstring saying this "only has to be fine
  [enough]" — an assumption, never tested. One of six committed stars moves
  **149 ppm** across the oversample sweep.

## The question this module insists on

*Converged?* is the wrong question, and asking it produces a machine that
generates nitpicks forever. Nothing is ever exactly converged. The question is

> **Is the residual bias smaller than the tolerance this result is graded at?**

By that standard the two findings above are opposite verdicts from identical
defects. A02's residual is 40 ppm against a 20,975 ppm Rayleigh tolerance —
0.19% of it, and harmless. K03's tilted the fit it fed. A verdict that cannot
tell those apart is not worth having.

## Fitting the order rather than assuming it

An earlier estimator in this estate assumed its bias was linear in the control.
It was cubic, and the "correction" overshot by 17% — in the same direction and
roughly the same size as the error it was removing. So the convergence order is
**fitted here, not assumed**, and sufficiency is checked by ADDING a term: if
the next order changes the extrapolated limit, the sweep has not converged and
the auditor says so instead of returning a confident number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

#: Extrapolated limits from consecutive orders must agree this closely before
#: the sweep is considered to determine the limit at all.
ORDER_TOL = 0.05

#: Orders tried when fitting value(control) = limit + a·control^p.
ORDERS = (1, 2, 3, 4)


@dataclass
class Audit:
    """One estimator, swept across the control it is a limit in."""

    name: str
    control_name: str
    controls: list
    values: list
    shipped_control: float | None = None
    tolerance: float | None = None
    tolerance_meaning: str = ""
    limit: float | None = None
    order: int | None = None
    determined: bool = False
    notes: list = field(default_factory=list)

    @property
    def shipped_value(self) -> float | None:
        if self.shipped_control is None:
            return None
        for c, v in zip(self.controls, self.values):
            if c == self.shipped_control:
                return v
        return None

    @property
    def bias(self) -> float | None:
        """How far the SHIPPED number sits from the limit it claims to be."""
        sv, lim = self.shipped_value, self.limit
        return None if sv is None or lim is None else abs(sv - lim)

    @property
    def swept_range(self) -> float:
        """How far the estimator moves across the whole sweep."""
        return float(max(self.values) - min(self.values)) if self.values else 0.0

    @property
    def verdict(self) -> str:
        """Harmless / MATTERS / undetermined — judged against the grading scale.

        The first branch is the one that keeps this from being a nitpick
        machine: **if the estimator moves less than the tolerance across the
        ENTIRE sweep, the limit cannot matter**, and no extrapolation is needed
        to say so. Four of A02's six stars land here, moving under 1 ppm against
        tolerances of thousands. Demanding a determined extrapolation from data
        that flat would report "undetermined" on the most converged results in
        the estate — precisely backwards.
        """
        if self.tolerance is not None and self.swept_range <= self.tolerance:
            return "harmless"
        if not self.determined:
            return "undetermined"
        if self.tolerance is None or self.bias is None:
            return "measured"
        return "harmless" if self.bias <= self.tolerance else "MATTERS"

    def to_json(self) -> dict:
        return {
            "name": self.name, "control": self.control_name,
            "controls": list(self.controls), "values": list(self.values),
            "shipped_control": self.shipped_control,
            "shipped_value": self.shipped_value,
            "limit": self.limit, "fitted_order": self.order,
            "determined": self.determined, "bias": self.bias,
            "tolerance": self.tolerance,
            "tolerance_meaning": self.tolerance_meaning,
            "bias_over_tolerance": (self.bias / self.tolerance
                                    if self.bias is not None and self.tolerance
                                    else None),
            "verdict": self.verdict, "notes": list(self.notes),
        }


def _poly_limit(controls: np.ndarray, values: np.ndarray, degree: int) -> float:
    """Constant term of a degree-``degree`` polynomial in the control.

    The polynomial is NESTED — every lower power is present — because the
    sufficiency check adds a term to this model rather than swapping one power
    for another. Swapping was tried first and rejected exactly one function
    down: on data that is exactly linear in the control, refitting with h²
    instead of h fits badly, the two limits disagree, and a perfect sweep gets
    reported as undetermined.
    """
    V = np.vander(controls, degree + 1, increasing=True)
    coef, *_ = np.linalg.lstsq(V, values, rcond=None)
    return float(coef[0])


def extrapolate(controls: Sequence[float], values: Sequence[float]) -> dict:
    """The limit as control → 0, with the order chosen by stability.

    ``controls`` are the quantity the estimator is a limit in — a field
    amplitude, a grid spacing, an inverse system size. Larger means further from
    the limit.

    The degree is not fitted by goodness-of-fit, because a higher degree always
    fits better and the sequence would run to interpolation. It is chosen as the
    **lowest degree whose limit survives adding another term** — and if no
    degree does, the sweep is reported as not determining the limit at all.
    That refusal is the whole value of the module: a confident number from an
    undetermined extrapolation is worse than no number, because it looks like a
    correction.
    """
    c = np.asarray(controls, dtype=float)
    v = np.asarray(values, dtype=float)
    if c.size < 4:
        return {"limit": None, "order": None, "determined": False,
                "reason": "fewer than four points — a degree cannot be chosen "
                          "and then checked"}
    span = float(np.ptp(v))
    if span <= abs(float(v[0])) * 1e-12:
        return {"limit": float(v[0]), "order": 0, "determined": True,
                "reason": None}

    max_degree = min(max(ORDERS), c.size - 2)
    for degree in range(1, max_degree + 1):
        here = _poly_limit(c, v, degree)
        nxt = _poly_limit(c, v, degree + 1)
        if abs(nxt - here) / span > ORDER_TOL:
            continue                      # this degree is not enough
        # Adding a term is necessary but not sufficient: a bias of order 8
        # fitted by degrees 3 and 4 is fitted badly by BOTH, in the same way,
        # so they agree. Dropping the control FURTHEST from the limit and
        # refitting is what catches it — a sound extrapolation barely moves.
        sub = _poly_limit(c[:-1], v[:-1], min(degree, c.size - 2))
        if abs(sub - here) / span > ORDER_TOL:
            return {"limit": here, "order": degree, "determined": False,
                    "limit_next_order": nxt, "limit_without_furthest": sub,
                    "reason": f"dropping the furthest control moves the limit by "
                              f"{abs(sub - here) / span:.0%} of the swept range "
                              f"— the extrapolation is carried by the point "
                              f"least entitled to carry it"}
        return {"limit": here, "order": degree, "determined": True,
                "limit_next_order": nxt, "limit_without_furthest": sub,
                "reason": None}
    return {"limit": _poly_limit(c, v, max_degree), "order": None,
            "determined": False, "reason":
            f"no degree up to {max_degree} gives a limit that survives adding "
            f"another term — the sweep does not reach far enough toward the "
            f"limit to determine it"}


def audit(name: str, estimator: Callable[[float], float],
          controls: Sequence[float], *, control_name: str = "control",
          shipped: float | None = None, tolerance: float | None = None,
          tolerance_meaning: str = "") -> Audit:
    """Sweep one estimator across its control and judge the residual bias.

    ``tolerance`` is the thing that makes this useful: the scale at which the
    result is actually graded. Without it the auditor can only say the bias
    exists, which is true of every numerical method ever written.
    """
    values = [float(estimator(c)) for c in controls]
    ex = extrapolate(controls, values)
    a = Audit(name=name, control_name=control_name, controls=list(controls),
              values=values, shipped_control=shipped, tolerance=tolerance,
              tolerance_meaning=tolerance_meaning,
              limit=ex["limit"], order=ex["order"], determined=ex["determined"])
    if ex.get("reason"):
        a.notes.append(ex["reason"])
    if a.verdict == "MATTERS":
        a.notes.append(
            f"the shipped value sits {a.bias / a.tolerance:.1f}x the grading "
            f"tolerance from its own limit — this is not a rounding question")
    elif a.verdict == "harmless" and a.bias:
        a.notes.append(
            f"bias is {a.bias / a.tolerance:.1%} of the tolerance; real, "
            f"measured, and does not move any verdict")
    return a
