# OEIS submission package — A329398

**Number of compositions of n with uniform Lyndon factorization and uniform co-Lyndon factorization.**

Offset 1. Entry by Gus Wiseman, Nov 13 2019. Generated from `pruned.log`; DATA digest `1d1f1d3bf537279d`.

- Published terms reproduced: **25** (n=1..25), all exact.
- New terms: **8** (n=26..33).
- Every term produced by two independent methods that agree.

---

## 1 · DATA — paste this whole line, replacing what is there

OEIS wants the FULL sequence, not only the new terms.

```
1, 2, 4, 7, 12, 18, 28, 40, 57, 80, 110, 148, 200, 266, 348, 457, 592, 764, 978, 1248, 1580, 2000, 2508, 3142, 3913, 4868, 6016, 7430, 9128, 11200, 13682, 16692, 20282
```

## 2 · Extensions field

```
a(26)-a(33) from <YOUR NAME>, <Mon DD YYYY>
```

## 3 · New comment — the conjecture check

This is the part an editor is most likely to care about, and it is
stated as a VERIFICATION, never as a proof.

```
Gus Wiseman's conjecture a(n) = 2*A000041(n) - A000005(n) holds for all n <= 33: each term above was computed independently by brute-force enumeration of the compositions of n and by that formula, and the two agree throughout. This is a verification, not a proof.
```

## 4 · PROG — the program that produced the terms

```
(Python)
def duval_lengths(s):
    # standard Lyndon factorization, O(len)
    n, i, out = len(s), 0, []
    while i < n:
        j, k = i + 1, i
        while j < n and s[k] <= s[j]:
            k = i if s[k] < s[j] else k + 1
            j += 1
        step = j - k
        while i <= k:
            out.append(step); i += step
    return out
def uniform(t): return len(set(t)) <= 1
def A329398(n):
    c, stack = 0, [((), n)]
    while stack:
        p, rem = stack.pop()
        if rem == 0:
            if uniform(duval_lengths(p)) and \
               uniform(duval_lengths(tuple(-x for x in p))): c += 1
            continue
        for q in range(1, rem + 1): stack.append((p + (q,), rem - q))
    return c
print([A329398(n) for n in range(1, 34)])
```

A note for the PROG comment, if you want one: the longest Lyndon prefix
of a word is the first factor of its standard Lyndon factorization, so
iterating Duval's algorithm gives the same factorization the entry's
Mathematica computes by testing every prefix — and does it in O(len)
rather than O(len^3).

---

## 5 · Evidence behind the terms

Three independent lines, all reproducible from this repo:

1. **Reproduction.** The Duval implementation returns all 25 published terms exactly. A generator that could not reproduce the entry would not be allowed to extend it.
2. **A second algorithm.** A literal transcription of the entry's own Mathematica (test every prefix, take the longest Lyndon one) agrees with the Duval implementation on every n it reaches.
3. **A second characterisation.** Wiseman's conjectured closed form agrees on every term, published and new. It shares no machinery with the enumeration.

## 6 · What is NOT claimed

- The conjecture is **not proved**; it is verified over a finite range.
- Computing a term is not the same act as OEIS accepting one. These terms are submitted for editorial review and may be rejected.
- No claim of priority: the terms are absent from the OEIS entry, which is not the same as absent from the world.

## 7 · The submission itself (a human does this)

1. Register / log in at https://oeis.org (upper right).
2. Go to https://oeis.org/A329398 and click **edit**.
3. Replace the DATA section with the line in §1.
4. Add the comment in §3, the Extensions line in §2 (with your name and today's date), and the PROG in §4.
5. **Save changes**, then **"These changes are ready for review by an OEIS editor"**.

No b-file: b-files are for 100/1000/10000/20000-term runs, and this sequence is far shorter than that. The DATA line is the right home.
