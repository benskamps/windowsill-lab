#!/usr/bin/env python3
"""Machine-check every step of the proof that A329398(n) = 2*A000041(n) - A000005(n).

Wiseman's 2019 formula for A329398 has stood as a conjecture since the entry was
created. It is not a conjecture: the two sets it equates are literally the same
set, and the proof is four lines of Lyndon-word bookkeeping.

THEOREM. A composition w of n has a uniform Lyndon factorization AND a uniform
co-Lyndon factorization if and only if w is weakly increasing or weakly
decreasing.

("Uniform" = all factors have the same length, per the entry's own COMMENTS.
"co-Lyndon" = Lyndon with respect to the reversed alphabet order.)

COROLLARY. a(n) = #{weakly increasing} + #{weakly decreasing} - #{both}
              = p(n) + p(n) - d(n) = 2*A000041(n) - A000005(n),
because weakly increasing compositions of n are in bijection with partitions of
n, likewise weakly decreasing, and a composition that is both is constant --
c repeated k times with k*c = n, one for each divisor of n.

PROOF OF THE THEOREM.

Two standard facts, and their mirror images:

  (L1) If l is Lyndon then l[0] = min(l).
       l is strictly less than each of its proper suffixes; comparing l with the
       suffix starting at i forces l[0] <= l[i].
  (L2) If l is Lyndon and |l| >= 2 then l[0] < l[-1].
       By (L1), l[0] <= l[-1]. If they were equal, the one-letter suffix (l[-1])
       would be a proper prefix of l, hence lexicographically smaller than l,
       contradicting that l is smaller than all its proper suffixes.
  (C1), (C2) The same statements with the order reversed: if r is co-Lyndon then
       r[0] = max(r), and if |r| >= 2 then r[0] > r[-1].

Let w have a uniform Lyndon factorization with factor length d and a uniform
co-Lyndon factorization with factor length e. Write l_1 for the first Lyndon
factor (so l_1 = w[0:d]) and r_1 for the first co-Lyndon factor (r_1 = w[0:e]).

Suppose, for contradiction, that d >= 2 and e >= 2. Then:
  * by (L2) applied to l_1:  w[0] < w[d-1]
  * by (C2) applied to r_1:  w[0] > w[e-1]
  and exactly one of three cases holds.
    d == e : the two displayed inequalities contradict each other outright.
    d <  e : index d-1 lies inside r_1 = w[0:e], so (C1) gives w[d-1] <= w[0],
             contradicting w[0] < w[d-1].
    d >  e : index e-1 lies inside l_1 = w[0:d], so (L1) gives w[0] <= w[e-1],
             contradicting w[0] > w[e-1].
So min(d, e) = 1.

If d = 1 every Lyndon factor is a single letter, and the factorization's defining
non-increasing condition l_1 >= l_2 >= ... reads w[0] >= w[1] >= ... : w is
weakly decreasing. If e = 1 the mirror argument gives w weakly increasing.

Conversely, let w be weakly increasing. If w is constant, both factorizations are
into single letters (uniform, d = e = 1). If not, w is Lyndon: for any proper
suffix s = w[i:], s[j] = w[i+j] >= w[j] termwise, and s cannot be a prefix of w
(that would force w constant), so w < s at the first strict inequality. Its
Lyndon factorization is the single factor w (uniform), and its co-Lyndon
factorization is into single letters, since w[0] <= w[1] <= ... is exactly the
co-Lyndon factorization's ordering condition (uniform). Mirror for weakly
decreasing.                                                                  []

This script does not replace the proof. It checks, by exhaustive enumeration,
every intermediate claim the proof leans on, so that a reader who distrusts the
prose has something that fails loudly if the prose is wrong.
"""
from __future__ import annotations

import sys
from functools import lru_cache


def lyndon(w: tuple[int, ...]) -> bool:
    """Strictly smaller than all proper rotations -- the entry's own lynQ."""
    return all(w < w[-i:] + w[:-i] for i in range(1, len(w)))


def factor_lengths(w: tuple[int, ...]) -> list[int]:
    """Standard Lyndon factorization, by the slow longest-Lyndon-prefix route.

    Deliberately NOT Duval: this file is the independent witness for the repo's
    fast solver, so it must not share machinery with it.
    """
    out: list[int] = []
    while w:
        best = max(i for i in range(1, len(w) + 1) if lyndon(w[:i]))
        out.append(best)
        w = w[best:]
    return out


def co_factor_lengths(w: tuple[int, ...]) -> list[int]:
    return factor_lengths(tuple(-x for x in w))


@lru_cache(maxsize=None)
def compositions(n: int) -> tuple[tuple[int, ...], ...]:
    if n == 0:
        return ((),)
    return tuple((f,) + rest for f in range(1, n + 1) for rest in compositions(n - f))


def partitions(n: int) -> int:
    p = [0] * (n + 1)
    p[0] = 1
    for k in range(1, n + 1):
        for i in range(k, n + 1):
            p[i] += p[i - k]
    return p[n]


def divisors(n: int) -> int:
    return sum(1 for d in range(1, n + 1) if n % d == 0)


def weakly_increasing(w) -> bool:
    return all(w[i] <= w[i + 1] for i in range(len(w) - 1))


def weakly_decreasing(w) -> bool:
    return all(w[i] >= w[i + 1] for i in range(len(w) - 1))


def main(nmax: int = 16) -> int:
    failures = 0

    def check(cond: bool, msg: str) -> None:
        nonlocal failures
        if not cond:
            print("  FAIL " + msg)
            failures += 1

    print(f"Checking every claim in the proof over all compositions of n = 1..{nmax}")
    print(f"(that is {sum(2 ** (n - 1) for n in range(1, nmax + 1)):,} words)\n")

    for n in range(1, nmax + 1):
        lhs = set()
        for w in compositions(n):
            a, b = factor_lengths(w), co_factor_lengths(w)
            ua, ub = len(set(a)) <= 1, len(set(b)) <= 1

            # (L1)/(L2) and their mirrors, on every factor this word produces.
            i = 0
            for L in a:
                f = w[i:i + L]
                i += L
                check(f[0] == min(f), f"(L1) on {f} from {w}")
                if L >= 2:
                    check(f[0] < f[-1], f"(L2) on {f} from {w}")
            i = 0
            for L in b:
                f = w[i:i + L]
                i += L
                check(f[0] == max(f), f"(C1) on {f} from {w}")
                if L >= 2:
                    check(f[0] > f[-1], f"(C2) on {f} from {w}")

            # The heart of the proof: d >= 2 and e >= 2 cannot co-occur.
            if ua and ub:
                check(min(a[0], b[0]) == 1,
                      f"d>=2 and e>=2 both occur on {w}: d={a[0]} e={b[0]}")
                lhs.add(w)

            # The two one-sided readings of min(d,e) = 1.
            if ua and a[0] == 1:
                check(weakly_decreasing(w), f"d=1 but {w} is not weakly decreasing")
            if ub and b[0] == 1:
                check(weakly_increasing(w), f"e=1 but {w} is not weakly increasing")

            # The converse direction, on every word, not only the counted ones.
            if weakly_increasing(w) or weakly_decreasing(w):
                check(ua and ub, f"{w} is monotone but a factorization is not uniform")

        rhs = {w for w in compositions(n)
               if weakly_increasing(w) or weakly_decreasing(w)}
        check(lhs == rhs, f"n={n}: the two SETS differ, not merely the counts")

        formula = 2 * partitions(n) - divisors(n)
        check(len(lhs) == formula,
              f"n={n}: |lhs|={len(lhs)} but 2*p(n)-d(n)={formula}")
        # And the corollary's own bookkeeping, counted directly.
        inc = sum(1 for w in compositions(n) if weakly_increasing(w))
        dec = sum(1 for w in compositions(n) if weakly_decreasing(w))
        both = sum(1 for w in compositions(n)
                   if weakly_increasing(w) and weakly_decreasing(w))
        check(inc == partitions(n), f"n={n}: weakly increasing != p(n)")
        check(dec == partitions(n), f"n={n}: weakly decreasing != p(n)")
        check(both == divisors(n), f"n={n}: constant compositions != d(n)")
        check(inc + dec - both == formula, f"n={n}: inclusion-exclusion")

        print(f"  n={n:>3}  a(n)={len(lhs):>6}  = 2*{partitions(n)} - {divisors(n)}"
              f"   sets equal, all lemmas hold")

    print()
    if failures:
        print(f"{failures} CHECK(S) FAILED -- the proof above is wrong somewhere.")
        return 1
    print("Every lemma, both directions, and the corollary's counting: verified")
    print(f"exhaustively for n <= {nmax}. The proof itself is general in n.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 16))
