#!/usr/bin/env python3
"""Independent finite check of the A329398 CHARACTERIZATION (not its values).

There are now three witnesses on this entry and they check different things.
Keeping them distinct is the point, so start here:

* ``scripts/a329398_extend.py`` computes terms from the tested lab module.
* ``docs/submissions/A329398-independent-bruteforce.py`` was written clean-room
  from the OEIS definition and reproduces the 25 PUBLISHED TERMS. It grades
  **numbers**: does our count of A329398(n) equal the count on the entry?
* This file grades the **statement**. Gus Wiseman's conjecture on the entry is
  not only a counting formula, it is a set equality:

      "Also the number of compositions of n that are either weakly increasing
       or weakly decreasing. Hence a(n) = 2*A000041(n) - A000005(n)."

  Two sets can have equal counts at every n and still be different sets. This
  script tests membership composition by composition: for every composition of
  n, does "uniform Lyndon factorization AND uniform co-Lyndon factorization"
  hold exactly when "weakly increasing OR weakly decreasing" holds? A single
  composition on which the two disagree refutes the characterization outright,
  and no amount of matching totals would have shown it.

That distinction is the whole reason this file exists. A proof of the counting
formula that went via the set equality is only as good as the set equality.

WHAT THIS IS NOT
----------------
This is a finite check, so it is not a proof and must never be reported as one.
It rules out the characterization being false on small compositions; it says
nothing about large n, and nothing whatever about whether a proof of it is
novel. Those are different questions with different referees.

It is also deliberately naive. Duval is re-implemented here from the textbook
description rather than imported from ``lab.a329398`` or copied from the
clean-room file, because a witness that shares machinery with the thing it is
checking is not a witness. It is slow by construction: compositions of n number
2^(n-1), so the default ceiling is small on purpose.

Usage:
  python3 docs/submissions/A329398-characterization-check.py [--to N]

Exit 0 if the two sets agree at every n checked, 1 on any disagreement.
"""
from __future__ import annotations

import argparse
import sys
from typing import Iterator, Sequence


def lyndon_factorization(word: Sequence[int]) -> list[tuple[int, ...]]:
    """Duval's algorithm: the unique factorization into non-increasing Lyndon words.

    Written from the standard description of the algorithm rather than adapted
    from this repository's solver, so that a bug shared with the solver cannot
    hide here too.
    """
    n, i = len(word), 0
    factors: list[tuple[int, ...]] = []
    while i < n:
        j, k = i + 1, i
        while j < n and word[k] <= word[j]:
            k = i if word[k] < word[j] else k + 1
            j += 1
        while i <= k:
            factors.append(tuple(word[i:i + j - k]))
            i += j - k
    return factors


def is_uniform(factors: Sequence[Sequence[int]]) -> bool:
    """A factorization is uniform when every factor has the same LENGTH.

    The entry's own COMMENTS define uniformity by length, not by equality of
    the factor words. Reading it as "all factors are the same word" is the
    natural misreading and it changes the sequence, so it is stated here
    explicitly rather than left to the reader.
    """
    return len({len(f) for f in factors}) <= 1


def in_a329398(composition: Sequence[int]) -> bool:
    """The entry's defining property, applied directly.

    A co-Lyndon factorization is the Lyndon factorization under the reversed
    alphabet order, which for integer letters is Duval over the negated word.
    """
    lyndon = is_uniform(lyndon_factorization(composition))
    colyndon = is_uniform(lyndon_factorization([-x for x in composition]))
    return lyndon and colyndon


def is_weakly_monotone(composition: Sequence[int]) -> bool:
    """Wiseman's conjectured description of the same set."""
    pairs = list(zip(composition, composition[1:]))
    return all(a <= b for a, b in pairs) or all(a >= b for a, b in pairs)


def compositions(n: int) -> Iterator[tuple[int, ...]]:
    """Every ordered tuple of positive integers summing to n."""
    if n == 0:
        yield ()
        return
    for head in range(1, n + 1):
        for tail in compositions(n - head):
            yield (head,) + tail


def partition_count(n: int, _memo: dict[int, int] = {}) -> int:
    """A000041 by Euler's pentagonal number recurrence."""
    if n == 0:
        return 1
    if n in _memo:
        return _memo[n]
    total, k = 0, 1
    while True:
        g1, g2 = k * (3 * k - 1) // 2, k * (3 * k + 1) // 2
        if g1 > n and g2 > n:
            break
        sign = -1 if k % 2 == 0 else 1
        if g1 <= n:
            total += sign * partition_count(n - g1)
        if g2 <= n:
            total += sign * partition_count(n - g2)
        k += 1
    _memo[n] = total
    return total


def divisor_count(n: int) -> int:
    """A000005."""
    return sum(1 for d in range(1, n + 1) if n % d == 0)


def check(limit: int, verbose: bool = True) -> tuple[bool, list[tuple[int, ...]]]:
    """Compare the two sets element by element for every n up to `limit`.

    Returns (agreed, counterexamples). Counterexamples are collected rather
    than raised on first sight, because if the characterization is wrong it is
    more useful to see the shape of several failures than the first one.
    """
    counterexamples: list[tuple[int, ...]] = []
    if verbose:
        print(f"{'n':>3} {'defining':>9} {'monotone':>9} {'2p(n)-d(n)':>11}  verdict")
    for n in range(1, limit + 1):
        by_definition = by_description = 0
        for c in compositions(n):
            defining = in_a329398(c)
            described = is_weakly_monotone(c)
            by_definition += defining
            by_description += described
            if defining != described:
                counterexamples.append(c)
        formula = 2 * partition_count(n) - divisor_count(n)
        agrees = by_definition == by_description == formula
        if verbose:
            verdict = "agree" if agrees else "DISAGREE"
            print(f"{n:>3} {by_definition:>9} {by_description:>9} {formula:>11}  {verdict}")
    return not counterexamples, counterexamples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--to", type=int, default=14, metavar="N",
        help="check every composition of n for n up to N (default 14; cost is 2^(N-1))",
    )
    args = parser.parse_args(argv)

    if args.to < 1:
        print("--to must be at least 1", file=sys.stderr)
        return 2

    agreed, counterexamples = check(args.to)
    print()
    if agreed:
        print(
            f"AGREE — the defining property and the weakly-monotone description "
            f"select the same compositions for every n <= {args.to}."
        )
        print("This is a finite check, not a proof.")
        return 0

    print(f"DISAGREE — {len(counterexamples)} composition(s) where the two differ:")
    for c in counterexamples[:10]:
        print(f"  {c}  defining={in_a329398(c)}  monotone={is_weakly_monotone(c)}")
    if len(counterexamples) > 10:
        print(f"  ... and {len(counterexamples) - 10} more")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
