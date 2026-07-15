"""C01 — calibrate the arithmetic stack against OEIS and Lucas–Lehmer.

The sequence half generates a prefix of Fibonacci b-file A000045 locally and
compares the exact UTF-8 bytes with OEIS.  The primality half independently
re-runs Lucas–Lehmer for the known Mersenne prime ``2^31 - 1``.  The public
receipt retains the compared source prefix, hashes, and final residue so CI can
re-derive the arithmetic without contacting either service.
"""
from __future__ import annotations

import hashlib
import time
import urllib.request
from dataclasses import dataclass


OEIS_SEQUENCE = "A000045"
OEIS_BFILE_URL = "https://oeis.org/A000045/b000045.txt"
MERSENNE_EXPONENT = 31


def fibonacci_bfile_segment(n_terms: int) -> bytes:
    if n_terms < 2:
        raise ValueError("C01 needs at least two Fibonacci terms")
    a, b = 0, 1
    lines = []
    for i in range(n_terms):
        lines.append(f"{i} {a}\n")
        a, b = b, a + b
    return "".join(lines).encode("utf-8")


def lucas_lehmer(exponent: int) -> tuple[bool, int]:
    """Return ``(is_mersenne_prime, final_residue)`` for prime exponent p."""
    if exponent == 2:
        return True, 0
    if exponent < 2:
        raise ValueError("Mersenne exponent must be >=2")
    candidate = (1 << exponent) - 1
    residue = 4
    for _ in range(exponent - 2):
        residue = (residue * residue - 2) % candidate
    return residue == 0, residue


def _download(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "windowsill-lab/0.1 C01 calibration"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


@dataclass
class C01Result:
    n_terms: int
    source_bytes: int
    source_sha256: str
    source_prefix_text: str
    source_prefix_sha256: str
    generated_prefix_sha256: str
    bfile_exact_match: bool
    mersenne_exponent: int
    mersenne_candidate: int
    lucas_lehmer_residue: int
    mersenne_prime_verified: bool
    calibration_passed: bool
    wall_seconds: float


def run_c01(n_terms: int = 40, source_url: str = OEIS_BFILE_URL) -> C01Result:
    t0 = time.time()
    expected = fibonacci_bfile_segment(n_terms)
    source = _download(source_url)
    prefix = source[:len(expected)]
    prime, residue = lucas_lehmer(MERSENNE_EXPONENT)
    exact = prefix == expected
    return C01Result(
        n_terms=n_terms,
        source_bytes=len(source),
        source_sha256=hashlib.sha256(source).hexdigest(),
        source_prefix_text=prefix.decode("utf-8", errors="strict"),
        source_prefix_sha256=hashlib.sha256(prefix).hexdigest(),
        generated_prefix_sha256=hashlib.sha256(expected).hexdigest(),
        bfile_exact_match=exact,
        mersenne_exponent=MERSENNE_EXPONENT,
        mersenne_candidate=(1 << MERSENNE_EXPONENT) - 1,
        lucas_lehmer_residue=residue,
        mersenne_prime_verified=prime,
        calibration_passed=bool(exact and prime),
        wall_seconds=time.time() - t0,
    )


def to_report(result: C01Result) -> dict:
    return {
        "experiment": "C01-arithmetic-calibration",
        "headline": (
            f"OEIS {OEIS_SEQUENCE}: {result.n_terms} terms matched byte-for-byte; "
            f"Lucas–Lehmer residue for 2^{result.mersenne_exponent}−1 is "
            f"{result.lucas_lehmer_residue}"
        ),
        "status": "pass" if result.calibration_passed else "null",
        "oeis_sequence": OEIS_SEQUENCE,
        "oeis_bfile_url": OEIS_BFILE_URL,
        "n_terms": result.n_terms,
        "source_bytes": result.source_bytes,
        "source_sha256": result.source_sha256,
        "source_prefix_text": result.source_prefix_text,
        "source_prefix_sha256": result.source_prefix_sha256,
        "generated_prefix_sha256": result.generated_prefix_sha256,
        "bfile_exact_match": result.bfile_exact_match,
        "mersenne_exponent": result.mersenne_exponent,
        "mersenne_candidate": result.mersenne_candidate,
        "lucas_lehmer_residue": result.lucas_lehmer_residue,
        "mersenne_prime_verified": result.mersenne_prime_verified,
        "calibration_passed": result.calibration_passed,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "This calibrates local integer arithmetic and source-byte handling. It does not "
            "constitute new OEIS terms, a GIMPS assignment, or a submitted contribution."
        ),
    }
