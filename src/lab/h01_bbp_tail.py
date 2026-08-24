"""H01 — is float64 already lying in C05's deep window?

The first runner written hypothesis-first: the question, the way it dies, and
the experiment that decides, in one file.

The BBP formula extracts a hex digit of π at position d without computing any
digit before it. `c05.bbp_window` does the head exactly — modular exponentiation,
integers only — and then accumulates in **float64**, and its own docstring names
that as the precision boundary: *"the float tail ... is the known precision
limit ... and if that ever stops being true"*. Nobody has checked whether it has.

So: recompute the same window in scaled-integer arithmetic with a provable
truncation bound and diff the two strings.
"""
from __future__ import annotations

import time

from .hypothesis import (CALIBRATE, KILLED, SUPPORTED, UNRESOLVED,
                         Finding, Hypothesis)
from . import c05

HYPOTHESIS = Hypothesis(
    id="H01",
    track="C",
    # An audit of our own arithmetic against a second method. This is exactly
    # what the calibrate side of the gate IS, and saying so is the point of the
    # field — a lab that lets its self-audits count as discovery has stopped
    # being able to answer the only question that matters about its aim.
    stage=CALIBRATE,
    question=("Does C05's deep BBP window at hex position 10^7 survive an "
              "independent exact-integer computation, or has float64's tail "
              "already corrupted digits the lab is reporting?"),
    why_unanswered=("c05.py names the float tail as its precision boundary and "
                    "grades the deep window only by overlap with an adjacent "
                    "window — two float computations agreeing with each other, "
                    "which is not independence. And `reports/receipts/` holds no "
                    "C05 receipt at all: the runner has never been executed."),
    observable=("The hex digit strings from the float path and the exact path at "
                "the same position. They are equal, or the index of the first "
                "digit at which they differ."),
    kill_condition=("Any disagreement inside the reported window kills the "
                    "claim: C05's deep digits are retracted, and the position "
                    "of the first failing digit becomes the measured result."),
    cheapest_decisive=("One exact recomputation of the same window: ~4 "
                       "engineering-hours, minutes of CPU, no GPU."),
    why_this_might_be_nothing=("An 8-hex-digit window is ~32 bits, comfortably "
                               "inside float64's ~52-bit mantissa, so the most "
                               "likely outcome by far is exact agreement and one "
                               "caveat sentence deleted. It is worth four hours "
                               "only because that sentence is the one Track C's "
                               "own goal — verifiable by a second, independent "
                               "method — is currently failing on."),
)

#: Scaled-integer precision. Every term contributes at most one unit of
#: truncation error, so d+1 head terms plus ~P/4 tail terms bound the total
#: error at (d + P/4 + 2) * 2^-P — at d = 10^7 and P = 192 that is ~10^-51,
#: which is forty orders of magnitude below the last digit of an 8-hex window.
PRECISION_BITS = 192


def exact_bbp_series(j: int, d: int, precision_bits: int = PRECISION_BITS) -> int:
    """Fractional part of Σ_k 16^(d−k)/(8k+j), as an integer scaled by 2^P.

    The same series `c05._bbp_series` computes, with every division replaced by
    a floored scaled-integer division. Floor only ever loses, never gains, and
    it loses less than one unit per term — which is what makes the error bound
    above a bound rather than an estimate.
    """
    scale = 1 << precision_bits
    total = 0
    for k in range(d + 1):
        m = 8 * k + j
        total += ((pow(16, d - k, m) << precision_bits) // m)
        total &= scale - 1                      # keep the fractional part only
    # Tail, k > d: the term is 1/(16^(k-d) · (8k+j)), which falls by 16 each
    # step. Stop when a whole term is smaller than one unit of the scale — at
    # that point it cannot change the answer.
    k = d + 1
    while True:
        shift = 4 * (k - d)
        if shift >= precision_bits:
            break
        term = (scale >> shift) // (8 * k + j)
        if term == 0:
            break
        total = (total + term) & (scale - 1)
        k += 1
    return total


def exact_bbp_window(d: int, width: int = c05.WINDOW,
                     precision_bits: int = PRECISION_BITS) -> str:
    """``width`` hex digits of π from position ``d``, integers throughout."""
    scale = 1 << precision_bits
    frac = (4 * exact_bbp_series(1, d, precision_bits)
            - 2 * exact_bbp_series(4, d, precision_bits)
            - exact_bbp_series(5, d, precision_bits)
            - exact_bbp_series(6, d, precision_bits)) % scale
    digits = []
    for _ in range(width):
        frac *= 16
        digits.append(format(frac >> precision_bits, "X"))
        frac &= scale - 1
    return "".join(digits)


def first_difference(a: str, b: str) -> int | None:
    """Index of the first differing character, or ``None`` if identical."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def run(deep_position: int = c05.DEEP_POSITION,
        control_positions=(0, 16, 1000),
        width: int = c05.WINDOW) -> Finding:
    """Control first, then the question. Never the other way round.

    The controls are the whole safety argument: at shallow positions the exact
    path is checked against BOTH the float path and π's digits computed by a
    completely different route (Machin's arctan formula, already in `c05`). An
    exact implementation that has not been shown to agree with a known answer
    somewhere cannot be used to accuse the float path anywhere.
    """
    t0 = time.time()
    controls: dict = {}

    machin = c05.machin_pi_hex(max(control_positions) + width + 8)
    for pos in control_positions:
        expected = machin[pos:pos + width]
        got_exact = exact_bbp_window(pos, width)
        got_float = c05.bbp_window(pos, width)
        controls[str(pos)] = {
            "machin": expected, "exact": got_exact, "float": got_float,
            "exact_matches_machin": got_exact == expected,
            "float_matches_machin": got_float == expected,
        }
    if not all(c["exact_matches_machin"] for c in controls.values()):
        bad = [p for p, c in controls.items() if not c["exact_matches_machin"]]
        return Finding(
            hypothesis=HYPOTHESIS, verdict=UNRESOLVED,
            detail=("the EXACT path disagrees with Machin at shallow positions "
                    f"{bad} — the instrument is broken, so it cannot be used to "
                    "judge the float path; nothing is concluded about the deep "
                    "window"),
            controls=controls, wall_seconds=time.time() - t0)

    deep_exact = exact_bbp_window(deep_position, width)
    deep_float = c05.bbp_window(deep_position, width)
    idx = first_difference(deep_float, deep_exact)
    evidence = {
        "position": deep_position, "width": width,
        "float": deep_float, "exact": deep_exact,
        "first_difference_index": idx,
        "precision_bits": PRECISION_BITS,
    }

    if idx is None:
        verdict, detail = SUPPORTED, (
            f"at hex position {deep_position:,} the float and exact paths agree "
            f"on all {width} digits ({deep_exact}); the float tail has not "
            "corrupted the reported window, and C05's caveat can be narrowed "
            "from 'unverified' to 'verified to this depth by exact arithmetic'")
    else:
        verdict, detail = KILLED, (
            f"at hex position {deep_position:,} the paths diverge at digit "
            f"{idx}: float says {deep_float}, exact says {deep_exact}. C05's "
            "deep window is retracted, and the depth at which float64 first "
            "fails is the result")
    return Finding(hypothesis=HYPOTHESIS, verdict=verdict, detail=detail,
                   evidence=evidence, controls=controls,
                   wall_seconds=time.time() - t0)
