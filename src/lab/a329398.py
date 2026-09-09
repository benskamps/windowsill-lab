"""A329398 — compositions with uniform Lyndon AND uniform co-Lyndon factorization.

The C03 target, and the lab's first genuinely new numbers. OEIS carries 25 terms
(Gus Wiseman, Nov 2019) under ``keyword:more`` — the catalogue's own marker for
*more terms wanted*.

Two independent methods, which is the whole point:

**Method A — the definition.** Enumerate the compositions of n, factor each into
Lyndon words and into co-Lyndon words, keep the ones where both factorisations
have uniform factor length. This is what the entry's own Mathematica does.

**Method B — the witness.** Wiseman's 2020 conjecture, ``a(n) = 2*A000041(n) -
A000005(n)``: also the number of compositions that are weakly increasing or
weakly decreasing. It shares no machinery with the enumeration, so agreement is
evidence and disagreement would be a counterexample to a standing conjecture.
Method B is NEVER used to produce a submitted term — only to check one.

## Two solver evolutions, both measured

The entry's Mathematica tests every prefix for Lyndon-ness and takes the longest,
which is O(len^3) per composition. Measured growth: **x4 per term** (x2 for the
doubling composition count, x2 more for the lengthening words), reaching n=26 in
about nine hours.

1. **Duval.** The longest Lyndon prefix of a word is exactly the first factor of
   its standard factorisation, so iterating Duval's O(len) algorithm gives the
   same factorisation. 25x faster; growth falls to **x2**, the floor for
   enumerating 2^(n-1) compositions.
2. **The prune.** Duval emits factors left to right and an emitted factor is
   FINAL — appending letters can never change it, only the trailing open region
   grows. So a prefix whose settled factors already differ in length cannot be
   completed into a solution, and the subtree dies. A further 16x at n=30, and
   growth falls to **x1.73**.

The prune is deliberately conservative: it ignores the LAST factor Duval reports
for a prefix, because that one can still merge or grow. Only strictly settled
factors may kill a branch. A weak prune costs time; a strong one silently
deletes answers — and this module exists to produce numbers nobody can check by
eye, so it errs toward slow.

Soundness is not argued, it is checked: :data:`PUBLISHED` is reproduced exactly
before any new term is reported, and ``tests/test_a329398.py`` pins it.
"""
from __future__ import annotations

#: The terms OEIS carried before this work. A solver that cannot return these
#: has no business returning the next one.
PUBLISHED = (1, 2, 4, 7, 12, 18, 28, 40, 57, 80, 110, 148, 200, 266, 348, 457,
             592, 764, 978, 1248, 1580, 2000, 2508, 3142, 3913)

A_NUMBER = "A329398"
OFFSET = 1


def duval_lengths(s: tuple[int, ...]) -> list[int]:
    """Standard Lyndon factorisation of ``s``, as factor lengths. O(len)."""
    n, i, out = len(s), 0, []
    while i < n:
        j, k = i + 1, i
        while j < n and s[k] <= s[j]:
            k = i if s[k] < s[j] else k + 1
            j += 1
        step = j - k
        while i <= k:
            out.append(step)
            i += step
    return out


def _settled_uniform(lengths: list[int]) -> bool:
    """Can a prefix with these factor lengths still become uniform?

    The last factor is dropped: Duval may still merge or extend it when the word
    grows, so it is not evidence. Everything before it is settled and final.
    """
    if len(lengths) <= 1:
        return True
    first = lengths[0]
    return all(x == first for x in lengths[:-1])


def _uniform(lengths: list[int]) -> bool:
    return len(set(lengths)) <= 1


def count(n: int) -> int:
    """a(n) by method A — enumeration under the settled-factor prune."""
    if n <= 0:
        return 0
    total = 0
    stack: list[tuple[tuple[int, ...], int]] = [((), n)]
    while stack:
        pref, rem = stack.pop()
        if pref:
            if not _settled_uniform(duval_lengths(pref)):
                continue
            if not _settled_uniform(duval_lengths(tuple(-x for x in pref))):
                continue
        if rem == 0:
            if _uniform(duval_lengths(pref)) and \
               _uniform(duval_lengths(tuple(-x for x in pref))):
                total += 1
            continue
        for p in range(1, rem + 1):
            stack.append((pref + (p,), rem - p))
    return total


def _partition_counts(n: int) -> list[int]:
    p = [0] * (n + 1)
    p[0] = 1
    for k in range(1, n + 1):
        for i in range(k, n + 1):
            p[i] += p[i - k]
    return p


def _num_divisors(n: int) -> int:
    return sum(1 for d in range(1, n + 1) if n % d == 0)


def witness(n: int, _cache: dict[int, list[int]] = {}) -> int:
    """a(n) by method B — Wiseman's conjecture, 2*A000041(n) - A000005(n).

    A CHECK, never a source. No term is ever submitted on this method's word.
    """
    if n <= 0:
        return 0
    top = _cache.get("top", 0)
    if n > top:
        _cache["p"] = _partition_counts(max(n, 64))
        _cache["top"] = max(n, 64)
    return 2 * _cache["p"][n] - _num_divisors(n)


def reproduces_published() -> bool:
    """The positive control: method A returns every published term exactly."""
    return all(count(i) == want
               for i, want in enumerate(PUBLISHED, start=OFFSET))
