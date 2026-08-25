"""U-A01 reach test — can a threshold crossing be PRICED, or only bounded?

Track A's goal is "a blind planet search that can price its own false alarms."
That is not the same as having a threshold. A threshold says *whether* to
promote; a price says *what a promotion is worth*, and without one a lead is a
number with no meaning attached.

The instrument for pricing already exists and had never been pooled: every hunt
runs an epoch-scramble placebo, and a scrambled light curve is by construction a
draw from the null. Across 58 hunts that is 1,400 null draws sitting in
`reports/hunts/`, unused.

## The two numbers, and why only one of them is enough

**Model-free.** Zero of 1,400 scrambles reached the SDE = 8 promotion threshold.
By the rule of three that bounds the per-curve false-alarm probability at
~2e-3 (95%). Multiplied by the trials actually run, that permits ~22 false
alarms across the survey — under which a single crossing means nothing.

**Tail-modelled.** Fitting the exponential excess above a cut and extrapolating
one SDE past the data gives ~5e-5 per curve, and the answer moves only ~6x
across reasonable cuts. That permits ~0.5 false alarms across the whole survey
— under which a single crossing is worth taking seriously.

So the verdict turns entirely on whether the tail model is trusted, and the
honest reading is that it is a *defensible extrapolation carrying the whole
claim*. This runner therefore reports both and refuses to quote the modelled
number without the bound beside it.
"""
from __future__ import annotations

import glob
import json
import math
from pathlib import Path

import numpy as np

from .a04 import SDE_THRESHOLD

#: Cuts to fit the exponential excess above. Reported together rather than
#: chosen, because the spread across them IS the systematic — picking one and
#: quoting its answer would hide the only uncertainty that matters here.
TAIL_CUTS = (5.0, 5.25, 5.5, 5.75, 6.0)

#: Minimum excesses above a cut before its fit is allowed to speak.
MIN_TAIL = 20

#: An extrapolation is trusted only if the answer is stable across the cut.
#: One order of magnitude, for a projection reaching a full SDE beyond the
#: largest sample ever drawn, is generous — and stated so.
MAX_CUT_SPREAD = 10.0


def pool_placebos(hunt_dir: Path | str = "reports/hunts") -> dict:
    """Every scrambled-curve SDE ever recorded, and the trials they price."""
    sde, trials, files = [], 0, 0
    for f in sorted(glob.glob(str(Path(hunt_dir) / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        files += 1
        sde += [r["sde"] for r in ((d.get("placebo") or {}).get("rows") or [])
                if r.get("sde") is not None]
        trials += len(d.get("targets") or [])
    return {"sde": np.sort(np.asarray(sde, dtype=float)),
            "trials": trials, "files": files}


def rule_of_three(n_draws: int, n_exceed: int) -> float:
    """Model-free 95% upper bound on a rate. With zero events in n draws the
    bound is 3/n — the only honest statement available without a tail model."""
    if n_exceed:
        return (n_exceed + 1.96 * math.sqrt(n_exceed)) / n_draws
    return 3.0 / n_draws


def tail_fap(sde: np.ndarray, threshold: float, cut: float) -> dict | None:
    """FAP at ``threshold`` from an exponential fit to the excess above ``cut``."""
    tail = sde[sde > cut]
    if tail.size < MIN_TAIL:
        return None
    beta = float((tail - cut).mean())            # exponential MLE
    if beta <= 0:
        return None
    return {"cut": cut, "n_tail": int(tail.size), "scale": beta,
            "fap": float(tail.size / sde.size * math.exp(-(threshold - cut) / beta))}


def run(hunt_dir: Path | str = "reports/hunts",
        threshold: float = SDE_THRESHOLD) -> dict:
    pooled = pool_placebos(hunt_dir)
    sde, trials = pooled["sde"], pooled["trials"]
    if sde.size < 100:
        return {"unknown": "U-A01", "reach": "out-of-reach",
                "detail": f"only {sde.size} pooled null draws — too few to say "
                          "anything about a tail"}

    n_exceed = int((sde >= threshold).sum())
    bound = rule_of_three(sde.size, n_exceed)
    fits = [f for f in (tail_fap(sde, threshold, c) for c in TAIL_CUTS) if f]
    faps = [f["fap"] for f in fits]
    spread = (max(faps) / min(faps)) if faps and min(faps) > 0 else float("inf")
    modelled = float(np.median(faps)) if faps else None

    expect_bound = bound * trials
    expect_model = modelled * trials if modelled is not None else None
    stable = spread <= MAX_CUT_SPREAD

    if n_exceed:
        reach, detail = "in-reach", (
            f"{n_exceed} of {sde.size} null draws reached SDE {threshold} — the "
            f"false-alarm rate is measured directly at {n_exceed/sde.size:.2e} "
            "and needs no tail model at all")
    elif stable and expect_model is not None and expect_model < 1.0:
        reach, detail = "in-reach", (
            f"zero of {sde.size:,} null draws reached SDE {threshold}; the "
            f"largest was {sde.max():.2f}. An exponential tail fit extrapolates "
            f"~{modelled:.1e} per curve, stable to {spread:.1f}x across the cut, "
            f"which over {trials:,} trials expects **{expect_model:.2f} false "
            f"alarms across the entire survey** — so a crossing would be worth "
            f"taking seriously. But the model-free bound is {bound:.1e} per "
            f"curve, i.e. up to {expect_bound:.0f} false alarms, so the price "
            f"rests entirely on a one-SDE extrapolation and must never be "
            f"quoted without that bound beside it")
    else:
        reach, detail = "out-of-reach", (
            f"zero of {sde.size:,} null draws reached SDE {threshold} and the "
            f"tail extrapolation moves {spread:.0f}x across the fit cut, so no "
            f"defensible price exists. Only the model-free bound survives: up "
            f"to {expect_bound:.0f} false alarms over {trials:,} trials, under "
            f"which a single crossing proves nothing")

    return {
        "unknown": "U-A01", "reach": reach, "detail": detail,
        "n_null_draws": int(sde.size), "hunt_files": pooled["files"],
        "trials": trials, "threshold": threshold,
        "max_null_sde": float(sde.max()),
        "n_exceedances": n_exceed,
        "fap_bound_model_free": bound,
        "fap_modelled": modelled,
        "cut_spread": spread,
        "expected_false_alarms_modelled": expect_model,
        "expected_false_alarms_bound": expect_bound,
        "tail_fits": fits,
        "what_would_remove_the_assumption": (
            f"~{int(20/max(modelled, 1e-9)):,} pooled scrambles would put "
            "exceedances at the threshold into the sample and replace the "
            "extrapolation with a measurement. Scrambles are cheap — they reuse "
            "light curves already on disk — and this is CPU work that does not "
            "compete with the GPU lane"),
    }
