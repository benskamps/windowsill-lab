"""C05 — BBP hex-digit extraction of π, cross-verified against Machin.

The Bailey–Borwein–Plouffe formula (Bailey, Borwein & Plouffe 1997,
*Math. Comp.* 66, 903) computes hexadecimal digits of π starting at position
``d`` WITHOUT computing any earlier digit — the digit-extraction identity

    π = Σ_k 16^-k [ 4/(8k+1) − 2/(8k+4) − 1/(8k+5) − 1/(8k+6) ]

evaluated with modular exponentiation so 16^(d−k) mod (8k+j) never grows.

C01's doctrine, scaled up: two INDEPENDENT algorithms must agree
byte-for-byte. The reference expansion is computed by Machin's 1706 arctan
formula (π/4 = 4·arctan(1/5) − arctan(1/239)) in pure-integer scaled
arithmetic — exact by construction, no floats anywhere in it — and then BBP
windows sampled across the whole expansion are graded byte-for-byte against
it. The two methods share no code, no series, and no failure mode: Machin is
one global sum from digit zero, BBP teleports to a position. Agreement is
therefore evidence about the arithmetic stack itself.

Three graded layers plus one honestly-bounded reported layer:

* **cross-algorithm** — every sampled BBP window equals the Machin reference
  at its position, byte-for-byte; one mismatched digit fails the run.
* **overlap self-consistency** — windows at ``d`` and ``d+4`` must agree on
  their four shared digits; this needs no reference at all and is the only
  gate that still applies beyond the reference's reach.
* **identity** — the calibration is one fixed measurement (N, window width,
  seeded sample); a caller cannot weaken the public gate with smaller work.
* **the deep extraction is REPORTED, graded only by overlap** — at the deep
  position there is no independent expansion on this machine, so the graded
  claim there is self-consistency of adjacent windows, deliberately NOT
  "the ten-millionth digit was verified against authority".

The float tail in the BBP fractional accumulation is the known precision
boundary of the method; the window width (8 hex digits) sits well inside
float64's ~12 reliable hex digits, and if that ever stops being true the
overlap gate fails loudly rather than shipping a wrong digit quietly.
"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field

#: One fixed calibration, C01-style: these constants ARE the milestone
#: identity, mirrored by ``checks._C05_*`` — change both or the lockstep
#: test fails.
CALIBRATION_HEX_DIGITS = 12_000
WINDOW = 8
SAMPLE_SEED = 20260822
N_SAMPLED_POSITIONS = 24
DEEP_POSITION = 10_000_000

#: First 32 fractional hex digits of π (3.243F6A88…), a fixed public
#: constant — the same role C01's Fibonacci prefix plays: a literal the
#: arithmetic must reproduce before anything else is believed.
KNOWN_PREFIX_32 = "243F6A8885A308D313198A2E03707344"


# ------------------------------------------------------------------ Machin --

def machin_pi_hex(n_digits: int, guard: int = 12) -> str:
    """The first ``n_digits`` fractional hex digits of π, exactly.

    Machin (1706): π = 16·arctan(1/5) − 4·arctan(1/239), evaluated on
    integers scaled by 16^(n_digits+guard). ``arctan(1/x)`` is the
    alternating series Σ (−1)^k / ((2k+1) x^(2k+1)); on scaled integers each
    term is an exact integer division and the series stops when the term
    underflows the scale. Guard digits absorb the truncation of both series
    and the final division; 12 hex guard digits is ~2^48 of slack against a
    tail bounded by the first dropped term.
    """
    if n_digits < 1:
        raise ValueError("C05 needs at least one hex digit")
    scale = 1 << (4 * (n_digits + guard))

    def arctan_inv(x: int) -> int:
        total = 0
        power = scale // x          # x^-1 at scale
        x2 = x * x
        k = 0
        while power:
            term = power // (2 * k + 1)
            if term == 0:
                break
            total += -term if (k & 1) else term
            power //= x2
            k += 1
        return total

    pi_scaled = 16 * arctan_inv(5) - 4 * arctan_inv(239)
    frac = pi_scaled - 3 * scale            # drop the integer part (3)
    frac >>= 4 * guard                      # drop the guard digits
    return format(frac, "x").upper().zfill(n_digits)[:n_digits]


# --------------------------------------------------------------------- BBP --

def _bbp_series(j: int, d: int) -> float:
    """Fractional part of Σ_k 16^(d−k)/(8k+j) — modular exponentiation for
    k ≤ d (the integer parts are discarded exactly, term by term), a fast
    convergent float tail for k > d."""
    total = 0.0
    for k in range(d + 1):
        m = 8 * k + j
        total += pow(16, d - k, m) / m
        total -= int(total)
    # tail: k = d+1 … converges as 16^-(k-d)
    t = 16.0 ** -1
    k = d + 1
    while t > 1e-19:
        total += t / (8 * k + j)
        total -= int(total)
        k += 1
        t /= 16.0
    return total - int(total)


def bbp_window(d: int, width: int = WINDOW) -> str:
    """``width`` hex digits of π's fractional expansion starting at index
    ``d`` (0-based: ``bbp_window(0)`` starts at the 2 of 243F…), computed
    without any digit before ``d``."""
    if d < 0:
        raise ValueError("digit position must be non-negative")
    frac = (4.0 * _bbp_series(1, d)
            - 2.0 * _bbp_series(4, d)
            - _bbp_series(5, d)
            - _bbp_series(6, d))
    frac -= int(frac)
    if frac < 0:
        frac += 1.0
    digits = []
    for _ in range(width):
        frac *= 16.0
        digit = int(frac)
        digits.append(format(digit, "X"))
        frac -= digit
    return "".join(digits)


def sampled_positions(n_digits: int = CALIBRATION_HEX_DIGITS,
                      n_samples: int = N_SAMPLED_POSITIONS,
                      seed: int = SAMPLE_SEED,
                      width: int = WINDOW) -> list[int]:
    """The deterministic seeded sample, both edges always included."""
    rng = random.Random(seed)
    hi = n_digits - width
    inner = sorted(rng.sample(range(1, hi), n_samples - 2))
    return [0, *inner, hi]


# ------------------------------------------------------------------ runner --

@dataclass
class C05Result:
    n_hex_digits: int
    window: int
    sample_seed: int
    reference_method: str
    reference_sha256: str
    reference_prefix_text: str
    reference_prefix_sha256: str
    known_prefix_match: bool
    windows: list[dict] = field(default_factory=list)
    all_windows_match: bool = False
    overlap_pairs: list[dict] = field(default_factory=list)
    all_overlaps_agree: bool = False
    deep: dict | None = None
    calibration_passed: bool = False
    wall_seconds: float = 0.0


def run_c05(n_digits: int = CALIBRATION_HEX_DIGITS,
            deep_position: int = DEEP_POSITION) -> C05Result:
    t0 = time.time()
    reference = machin_pi_hex(n_digits)
    prefix = reference[:2048] if n_digits >= 2048 else reference
    known_ok = reference[:32] == KNOWN_PREFIX_32 if n_digits >= 32 else False

    windows: list[dict] = []
    for d in sampled_positions(n_digits):
        t_w = time.time()
        got = bbp_window(d)
        expected = reference[d:d + WINDOW]
        windows.append({
            "position": d, "bbp": got, "reference": expected,
            "match": got == expected,
            "wall_seconds": round(time.time() - t_w, 4),
        })
    all_match = all(w["match"] for w in windows)

    overlaps: list[dict] = []
    for d in sampled_positions(n_digits)[:6]:
        a, b = bbp_window(d), bbp_window(d + 4)
        overlaps.append({"position": d, "shared_from_d": a[4:],
                         "shared_from_d4": b[:4], "agree": a[4:] == b[:4]})
    all_overlap = all(o["agree"] for o in overlaps)

    t_deep = time.time()
    deep_a = bbp_window(deep_position)
    deep_b = bbp_window(deep_position + 4)
    deep = {
        "position": deep_position,
        "digits": deep_a,
        "adjacent_digits": deep_b,
        "adjacent_overlap_agree": deep_a[4:] == deep_b[:4],
        "wall_seconds": round(time.time() - t_deep, 2),
    }

    return C05Result(
        n_hex_digits=n_digits,
        window=WINDOW,
        sample_seed=SAMPLE_SEED,
        reference_method=("Machin 1706 arctan formula, integer-scaled "
                         "(pi/4 = 4*arctan(1/5) - arctan(1/239))"),
        reference_sha256=hashlib.sha256(reference.encode("ascii")).hexdigest(),
        reference_prefix_text=prefix,
        reference_prefix_sha256=hashlib.sha256(prefix.encode("ascii")).hexdigest(),
        known_prefix_match=known_ok,
        windows=windows,
        all_windows_match=all_match,
        overlap_pairs=overlaps,
        all_overlaps_agree=all_overlap,
        deep=deep,
        # The fixed identity is part of the pass, C01-style: a caller running
        # --digits 64 gets a useful diagnostic, not the public calibration.
        calibration_passed=bool(
            known_ok and all_match and all_overlap
            and deep["adjacent_overlap_agree"]
            and n_digits == CALIBRATION_HEX_DIGITS
            and deep_position == DEEP_POSITION
        ),
        wall_seconds=time.time() - t0,
    )


def to_report(result: C05Result) -> dict:
    n_match = sum(1 for w in result.windows if w["match"])
    return {
        "experiment": "C05-bbp-digit-extraction",
        "headline": (
            f"BBP windows at {len(result.windows)} positions across "
            f"{result.n_hex_digits} hex digits: {n_match}/{len(result.windows)} "
            f"byte-identical with the Machin expansion; deep window at "
            f"{result.deep['position']:,} self-consistent in "
            f"{result.deep['wall_seconds']}s"
        ),
        "status": "pass" if result.calibration_passed else "null",
        "n_hex_digits": result.n_hex_digits,
        "window": result.window,
        "sample_seed": result.sample_seed,
        "reference_method": result.reference_method,
        "reference_sha256": result.reference_sha256,
        "reference_prefix_text": result.reference_prefix_text,
        "reference_prefix_sha256": result.reference_prefix_sha256,
        "known_prefix_match": result.known_prefix_match,
        "windows": result.windows,
        "all_windows_match": result.all_windows_match,
        "overlap_pairs": result.overlap_pairs,
        "all_overlaps_agree": result.all_overlaps_agree,
        "deep": result.deep,
        "calibration_passed": result.calibration_passed,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "Two independent algorithms (Machin integer arctan; BBP digit "
            "extraction) agree byte-for-byte on sampled 8-digit windows across "
            f"the first {result.n_hex_digits} hex digits of pi, and adjacent "
            "deep windows are self-consistent. The deep extraction at position "
            f"{result.deep['position']:,} is graded ONLY by that overlap — no "
            "independent expansion reaches it on this machine, so no claim of "
            "external verification is made there. No new mathematics is "
            "claimed anywhere: every digit of pi computed here has been known "
            "for decades; the measurement is of this machine's arithmetic."
        ),
    }
