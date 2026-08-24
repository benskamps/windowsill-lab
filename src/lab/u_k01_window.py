"""U-K01 reach test — is K03's fitted exponent a measurement, or a window artifact?

The first feasibility test in the catalogue, and the template for the rest: it
runs on **bytes already committed**, costs milliseconds, and its negative answer
is a result rather than a disappointment.

## The situation it was built for

K03 adjudicates Daido (γ = 1/4 supercritical, γ' = 1 subcritical) against Hong
et al. (γ = γ' = 1/4). Two things about that pair matter and neither was
written down anywhere:

1. **γ is identical in both claims.** The supercritical branch has *zero*
   discriminating power. Everything that separates the two papers lives in γ',
   on the subcritical branch, where the gap is Δγ' = 0.75.
2. The 2026-08-23 run measured the supercritical branch cleanly — six columns,
   R² = 0.999 — and got **γ = 1.07 ± 0.02**, which is ~46σ from the 0.25 that
   *both* papers predict. That fact has been sitting under a `status: fail`
   caused by the *other* branch failing its linearity gate, so nobody looked
   at it.

The tempting reading is that the engine contradicts two published papers. The
overwhelmingly likelier one is that ε ∈ [0.02, 0.32] is simply **outside the
asymptotic critical window**, where the response is the generic mean-field
χ ~ ε^-1 and the anomalous 1/4 has not switched on yet. An exponent of ~1 is
exactly what "not close enough to K_c" looks like.

## The test

A true asymptotic power law has a **constant local slope**. So fit the slope
between each adjacent pair of columns and ask whether those local exponents are
constant across the window, or drifting.

* **Constant** → the window is inside the scaling regime; the branch fit means
  what it says, and the exponent can be compared to a published claim.
* **Drifting** → the single fitted exponent is an artifact of where the window
  happens to sit. It is not γ. Comparing it to Daido or Hong is meaningless,
  and the honest verdict is that the instrument cannot reach the question at
  this ε floor.

That is the cheap kill test on ourselves, and it has to run before any hero run
at larger N, because a hero run inside the wrong window buys a more precise
artifact.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

#: Local exponents this far apart (as a fraction of their mean) are not
#: constant. A power law that wanders by more than a tenth across the fitted
#: window is not being measured, it is being averaged over a crossover.
DRIFT_TOL = 0.10

#: Both papers agree here, so the branch carries no information about which is
#: right. Recorded as a constant because it is the whole reason the subcritical
#: branch is the only one worth fighting for.
DISCRIMINATING_GAP = 0.75          # γ'_Daido (1.0) − γ'_Hong (0.25)


def local_exponents(eps, chi) -> list[dict]:
    """Log-log slope between each adjacent pair — the local exponent γ(ε).

    Pairwise rather than windowed because the grid is short: with six columns a
    sliding fit would smooth away exactly the drift being looked for.
    """
    pts = sorted(((float(e), float(c)) for e, c in zip(eps, chi)
                  if e is not None and c is not None and c > 0))
    out = []
    for (e0, c0), (e1, c1) in zip(pts, pts[1:]):
        gamma = -(math.log(c1) - math.log(c0)) / (math.log(e1) - math.log(e0))
        out.append({"eps_lo": e0, "eps_hi": e1, "gamma_local": gamma,
                    "eps_mid": math.sqrt(e0 * e1)})
    return out


def drift(locals_) -> dict:
    """Is the local exponent constant, and if not, which way is it going?

    The direction matters as much as the size: a local exponent that *falls* as
    ε shrinks is heading toward a smaller asymptotic value, which is the
    signature of a crossover we are watching from the wrong side.
    """
    if len(locals_) < 2:
        return {"measurable": False,
                "reason": "fewer than two local slopes — nothing to compare"}
    g = [x["gamma_local"] for x in locals_]
    lo, hi, mean = min(g), max(g), sum(g) / len(g)
    span = (hi - lo) / abs(mean) if mean else float("inf")
    # locals_ is ordered by increasing eps, so g[0] is the innermost pair.
    falling_inward = g[0] < g[-1]
    return {
        "measurable": True,
        "gamma_min": lo, "gamma_max": hi, "gamma_mean": mean,
        "relative_span": span,
        "constant": span <= DRIFT_TOL,
        "falling_toward_small_eps": falling_inward,
        "innermost": g[0], "outermost": g[-1],
    }


def _load_columns(receipt: Path) -> dict:
    d = json.loads(receipt.read_text(encoding="utf-8"))
    out = {}
    for branch, key in (("above", "columns_above"), ("below", "columns_below")):
        cols = [c for c in d.get(key, []) if c.get("ok") and c.get("chi")]
        out[branch] = {
            "eps": [c["eps"] for c in cols],
            "chi": [c["chi"] for c in cols],
            "refused": [c["eps"] for c in d.get(key, []) if not c.get("ok")],
        }
    out["fit_above"] = d.get("fit_above", {})
    out["fit_below"] = d.get("fit_below", {})
    return out


def run(receipt: Path) -> dict:
    """Read a committed K03 receipt and return the reach verdict.

    Nothing is simulated. If this needed a new run it would not be a
    feasibility test — it would be the experiment.
    """
    data = _load_columns(receipt)
    branches = {}
    for name in ("above", "below"):
        b = data[name]
        loc = local_exponents(b["eps"], b["chi"])
        branches[name] = {
            "n_columns": len(b["eps"]),
            "eps_floor": min(b["eps"]) if b["eps"] else None,
            "refused_eps": b["refused"],
            "local": loc,
            "drift": drift(loc),
        }

    above = branches["above"]["drift"]
    reachable = bool(above.get("measurable") and above.get("constant"))

    # Resolving power: given the precision this instrument actually achieved on
    # a branch it COULD measure, how many sigma would separate the two claims?
    err = data["fit_above"].get("err")
    sigma = (DISCRIMINATING_GAP / err) if err else None

    if not above.get("measurable"):
        verdict, detail = "out-of-reach", (
            "too few surviving columns to test constancy at all — the reach "
            "question cannot even be asked from this receipt")
    elif reachable:
        verdict, detail = "in-reach", (
            f"the local exponent is constant to {above['relative_span']:.1%} "
            f"across the window, so the fitted branch exponent is a "
            f"measurement and may be compared to a published claim")
    else:
        direction = ("falling as ε shrinks, which is the signature of a "
                     "crossover approached from outside"
                     if above.get("falling_toward_small_eps") else
                     "rising as ε shrinks")
        verdict, detail = "out-of-reach", (
            f"the local exponent drifts {above['relative_span']:.1%} across the "
            f"window ({above['innermost']:.3f} at the inner edge to "
            f"{above['outermost']:.3f} at the outer), {direction}. A single "
            f"fitted exponent over this range is an artifact of where the "
            f"window sits, not γ — so the {data['fit_above'].get('gamma', float('nan')):.3f} "
            f"on the record cannot be compared to Daido's or Hong's 0.25, and "
            f"a larger-N run inside the same window would buy a more precise "
            f"artifact rather than an answer")

    return {
        "unknown": "U-K01",
        "receipt": receipt.name,
        "branches": branches,
        "reach": verdict,
        "detail": detail,
        "discriminating_gap": DISCRIMINATING_GAP,
        "sigma_separation_if_measured": sigma,
        "note_on_discrimination": (
            "Daido and Hong predict the SAME supercritical γ = 0.25, so the "
            "above branch has no discriminating power at all; every bit of the "
            "adjudication lives in γ' on the subcritical branch, which this "
            "receipt failed to measure"),
    }
