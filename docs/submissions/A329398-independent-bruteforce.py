#!/usr/bin/env python3
"""
Independent brute-force verification of OEIS A329398:
"Number of compositions of n with uniform Lyndon factorization
and uniform co-Lyndon factorization."

Written from scratch from the definitions only (no reference to
windowsill-lab source):

- A composition of n is an ordered tuple of positive integers summing to n.
- A word w is a LYNDON word if it is strictly lexicographically smaller
  than every one of its proper (nontrivial) rotations.
- Every finite word has a unique factorization into Lyndon words that
  are weakly DECREASING in lexicographic order (the standard Chen-Fox-Lyndon
  / Duval factorization, read as a multiset of Lyndon factors arranged
  in nonincreasing order). This factorization is "uniform" if every
  factor is the same word (hence has the same length, and since they
  concatenate to a fixed word, there are len(w)/L factors each of
  length L, for the L found).
- A word w is a CO-LYNDON word if it is strictly lexicographically GREATER
  than every one of its proper rotations. The co-Lyndon factorization
  is the same construction with the order reversed: factorize into
  co-Lyndon words arranged in weakly INCREASING lexicographic order.
  Equivalently (and this is the convention actually used to build the
  fast algorithm below): apply the standard Duval algorithm for the
  *complement* comparator (i.e., treat "greater" as the primitive
  ordering relation) to get co-Lyndon factors in decreasing order of
  "co-Lyndon-ness", then present them increasing.

Implementation strategy (kept deliberately naive/definitional, not
copied from any repository):
  1. Enumerate all 2^(n-1) compositions of n directly from the
     standard "binary string of gap/no-gap between n unit dots" bijection.
  2. For each composition (as a tuple of positive integers), compute its
     Lyndon factorization by the direct "peel off the longest run that
     is itself broken by the standard greedy Lyndon-prefix rule" method:
     the classical algorithm is: repeatedly find the LONGEST PREFIX of
     the remaining word that is a "Lyndon-run" via Duval's algorithm,
     which naturally outputs the factors already in nonincreasing order
     for Lyndon factorization. We implement Duval's algorithm directly
     from its textbook definition (not copied from any project code).
  3. For co-Lyndon we run the mirror algorithm using the reversed
     comparator (>) in place of (<), which is the textbook way to get
     the co-Lyndon / decreasing-word factorization; by symmetry this
     produces factors in nondecreasing lexicographic order automatically
     when read left to right? -- NO: Duval's algorithm on the reversed
     order gives factors nonincreasing in the REVERSED order, i.e.
     nondecreasing in the original order, which is exactly the co-Lyndon
     convention (factors weakly increasing). This matches OEIS A329313 /
     A275692 convention referenced by A329398.
  4. "Uniform" = all factors are literally equal (same tuple).

We compute a(n) as the count of compositions of n where BOTH
factorizations are uniform, for n = 1..25 (and push further while fast).
"""

import sys
import time

def duval_lyndon_factorization(w):
    """
    Standard Duval algorithm (1983) for the Lyndon factorization of a
    finite word w (list/tuple of comparable symbols), returning the
    factors in the order they occur (which is automatically weakly
    NONINCREASING in lexicographic order -- a standard fact about the
    Lyndon factorization).
    """
    n = len(w)
    i = 0
    factors = []
    while i < n:
        j = i + 1
        k = i
        while j < n and w[k] <= w[j]:
            if w[k] < w[j]:
                k = i
            else:
                k += 1
            j += 1
        # length of the repeating block found
        length = j - k
        while i <= k:
            factors.append(tuple(w[i:i+length]))
            i += length
    return factors


def duval_colyndon_factorization(w):
    """
    Co-Lyndon factorization: run Duval's algorithm with the comparator
    reversed (i.e. on the sequence with '<=' and '<' replaced by '>=' and
    '>'). This is the textbook mirror construction and yields factors
    that are co-Lyndon words (each strictly greater than all of its
    proper rotations), emitted in weakly INCREASING lexicographic order
    (the "co-Lyndon" convention: weakly increasing, mirroring the
    Lyndon convention's weakly decreasing).
    """
    n = len(w)
    i = 0
    factors = []
    while i < n:
        j = i + 1
        k = i
        while j < n and w[k] >= w[j]:
            if w[k] > w[j]:
                k = i
            else:
                k += 1
            j += 1
        length = j - k
        while i <= k:
            factors.append(tuple(w[i:i+length]))
            i += length
    return factors


def is_uniform(factors):
    """Per the OEIS A329398 COMMENTS text (fetched verbatim from the live
    entry): 'A sequence of words is uniform if they all have the same
    length.' This is NOT the same as all factors being literally equal
    -- only their lengths must agree."""
    if not factors:
        return True
    first_len = len(factors[0])
    return all(len(f) == first_len for f in factors)


def compositions(n):
    """Yield all compositions of n (tuples of positive ints summing to n)
    via the standard 2^(n-1) bijection: choose a subset of the n-1
    internal gaps between n dots to place a 'cut'."""
    if n == 0:
        yield ()
        return
    for mask in range(1 << (n - 1)):
        parts = []
        run = 1
        for bit in range(n - 1):
            if mask & (1 << bit):
                parts.append(run)
                run = 1
            else:
                run += 1
        parts.append(run)
        yield tuple(parts)


def a(n):
    count = 0
    for comp in compositions(n):
        lyn = duval_lyndon_factorization(comp)
        coly = duval_colyndon_factorization(comp)
        if is_uniform(lyn) and is_uniform(coly):
            count += 1
    return count


def sanity_checks():
    # Known Lyndon word check: (1,0,0,1) -> sorted Lyndon factorization
    # should be (0,0,1)(1) per the OEIS comment example "(1001) has sorted
    # Lyndon factorization (001)(1)". Duval on (1,0,0,1) with '<' meaning
    # numeric less-than: let's verify.
    w = (1, 0, 0, 1)
    f = duval_lyndon_factorization(w)
    # OEIS comment: "(1001) has sorted Lyndon factorization (001)(1)"
    # -- the unique factorization's factor MULTISET must be {(0,0,1),(1,)}
    # (display order in the comment is a "sorted for readability" order,
    # not necessarily the true left-to-right decreasing Duval order).
    assert sorted(f) == sorted([(0, 0, 1), (1,)]), f
    # concatenation must reconstruct the word, and each factor must
    # actually be Lyndon (< all its own rotations)
    assert tuple(x for fac in f for x in fac) == w
    for fac in f:
        rots = [fac[r:] + fac[:r] for r in range(1, len(fac))]
        assert all(fac < r for r in rots), (fac, "not Lyndon")

    cf = duval_colyndon_factorization((1, 0, 0, 1))
    # OEIS comment: "(1001) has sorted co-Lyndon factorization (1)(100)"
    assert sorted(cf) == sorted([(1,), (1, 0, 0)]), cf
    assert tuple(x for fac in cf for x in fac) == w
    for fac in cf:
        rots = [fac[r:] + fac[:r] for r in range(1, len(fac))]
        assert all(fac > r for r in rots), (fac, "not co-Lyndon")

    print("Sanity checks on (1,0,0,1) passed:", f, cf)


if __name__ == "__main__":
    sanity_checks()
    max_n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    results = {}
    for n in range(1, max_n + 1):
        t0 = time.time()
        val = a(n)
        dt = time.time() - t0
        results[n] = val
        print(f"n={n:3d}  a(n)={val:8d}   ({dt:.3f}s, {2**(n-1) if n>0 else 1} compositions)")
        sys.stdout.flush()
