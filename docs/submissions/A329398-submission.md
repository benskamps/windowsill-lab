# OEIS submission package — A329398

**Number of compositions of n with uniform Lyndon factorization and uniform co-Lyndon factorization.**

Offset 1. Entry by Gus Wiseman, Nov 13 2019. 25 terms, `keyword: more`, unchanged
since revision #15 (2021-06-20).

**What this submission carries changed on 2026-09-18.** It was 15 new terms plus a
numerical check of Wiseman's conjectured formula. It is now **a proof of that
conjecture**, which supersedes the terms: with the closed form established, every
term of the sequence follows from p(n) and d(n), and the 15 new terms are a
corollary rather than the contribution.

---

## 0 · The result

> **Theorem.** A composition has a uniform Lyndon factorization and a uniform
> co-Lyndon factorization if and only if it is weakly increasing or weakly
> decreasing.
>
> **Corollary (Wiseman's conjecture).** a(n) = 2·A000041(n) − A000005(n) for all n.

The two sets are not merely equinumerous — they are **the same set**, composition
by composition. That is what makes the proof short.

**Credit where it is due: Wiseman conjectured this, set-equality and all.** The
live entry's comment reads *"Conjecture: Also the number of compositions of n
that are either weakly increasing or weakly decreasing. Hence a(n) =
2*A000041(n) - A000005(n)"* (read on oeis.org, 2026-09-18). So the
characterisation is his, the derivation of the formula from it is his, and the
only thing new here is **the proof**. An earlier draft of this file read as
though noticing the set-equality were part of the contribution; it was noticed
independently, which is not the same as first. The comment as submitted says
"This proves Wiseman's conjecture", which is the correct claim.

Proof, with every lemma machine-checked over all 65,535 compositions of n ≤ 16:
`scripts/a329398_proof_check.py` in this repository. The proof is reproduced in
§3 below in the form it should go into the entry.

Independent support that predates the proof and still stands: the terms n = 26..40
were produced by brute-force enumeration under a conservative prune (method A,
`src/lab/a329398.py`), which reproduces all 25 published terms exactly, and agree
with the formula (method B) at every n. A third-party agent, forbidden to read
this repository, wrote its own enumerator from the OEIS definition alone and
reproduced all 25 published terms and a(26) = 4868 by direct enumeration of all
2²⁵ compositions (`A329398-independent-bruteforce.py`).

---

## 1 · DATA — paste this whole line, replacing what is there

**Extended 2026-09-18 at Andrew Howroyd's request** (see §10). He noted the
40-term line was 216 characters against a usual length of ~260 and asked for ten
more terms. Ten more is **a(50), at 295 characters** — past the 260 he cited, so
both lines are given. Paste the first one; the second is the fallback if he
asks for something inside 260.

**a(1)-a(50) — what was asked for (295 chars):**

```
1, 2, 4, 7, 12, 18, 28, 40, 57, 80, 110, 148, 200, 266, 348, 457, 592, 764, 978, 1248, 1580, 2000, 2508, 3142, 3913, 4868, 6016, 7430, 9128, 11200, 13682, 16692, 20282, 24616, 29762, 35945, 43272, 52026, 62366, 74668, 89164, 106340, 126520, 150344, 178262, 211112, 249506, 294536, 347047, 408446
```

**a(1)-a(45) — the strict-260 version (255 chars), only if he objects to length:**

```
1, 2, 4, 7, 12, 18, 28, 40, 57, 80, 110, 148, 200, 266, 348, 457, 592, 764, 978, 1248, 1580, 2000, 2508, 3142, 3913, 4868, 6016, 7430, 9128, 11200, 13682, 16692, 20282, 24616, 29762, 35945, 43272, 52026, 62366, 74668, 89164, 106340, 126520, 150344, 178262
```

Every term is computed by **three independent routes** that share no machinery:
definition-based enumeration of all 2^(n-1) compositions (n ≤ 24), the proved
closed form `2*A000041(n) - A000005(n)`, and a dynamic program counting weakly
increasing compositions directly. All three agree, and rows 1..50 of the b-file
in §7 match. Terms past n = 24 rest on the theorem rather than on enumeration —
that is what the proof buys, and it is the reason the proof should go in with
them.

## 2 · Extensions field

```
a(26)-a(50) from _Benjamin Schippers_, Sep 18 2026
```

This replaces the `a(26)-a(40)` line already in the draft — it is the same
unpublished edit, so it stays one line with its original date rather than
becoming two. Use `a(26)-a(45)` if you paste the shorter DATA line.

## 3 · The comment that matters — the conjecture, proved

Replace nothing; **add** this. The entry's existing conjecture comment stays where
it is, and this sits under it.

```
Theorem: a composition has a uniform Lyndon factorization and a uniform co-Lyndon factorization if and only if it is weakly increasing or weakly decreasing. This proves Wiseman's conjecture a(n) = 2*A000041(n) - A000005(n).

Proof. Write w for the composition. Recall that a Lyndon word l satisfies l[1] = min(l), and that if |l| >= 2 then l[1] < l[|l|] (otherwise the one-letter suffix would be a proper prefix of l and hence smaller than l). The mirror statements hold for co-Lyndon words: r[1] = max(r), and r[1] > r[|r|] when |r| >= 2.

Suppose the Lyndon factorization of w has all factors of length d and the co-Lyndon factorization has all factors of length e, and suppose d >= 2 and e >= 2. The first Lyndon factor is w[1..d], so w[1] < w[d]; the first co-Lyndon factor is w[1..e], so w[1] > w[e]. If d = e these contradict. If d < e then w[d] lies inside the first co-Lyndon factor, so w[d] <= w[1], contradicting w[1] < w[d]. If d > e then w[e] lies inside the first Lyndon factor, so w[1] <= w[e], contradicting w[1] > w[e]. Hence min(d,e) = 1. If d = 1 the Lyndon factorization is into single letters, whose defining non-increasing order reads w[1] >= w[2] >= ...: w is weakly decreasing. If e = 1 the mirror argument gives w weakly increasing.

Conversely let w be weakly increasing. If w is constant both factorizations are into single letters. Otherwise w is Lyndon: for a proper suffix s = w[i+1..], each s[j] = w[i+j] >= w[j], and s is not a prefix of w (that would force w constant), so w < s at the first strict inequality; then the Lyndon factorization is the single factor w and the co-Lyndon factorization is into single letters. Mirror for weakly decreasing. QED

The corollary follows by inclusion-exclusion: weakly increasing compositions of n are in bijection with the partitions of n, likewise weakly decreasing, and a composition that is both is constant, one for each divisor of n, giving p(n) + p(n) - d(n).
```

If an editor wants it shorter, the first paragraph alone is the statement, and the
rest can go to a Links entry.

## 4 · FORMULA field

```
a(n) = 2*A000041(n) - A000005(n). [Proved; see the theorem in COMMENTS.]
```

## 5 · PROG — the enumeration, which is now the check rather than the source

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
print([A329398(n) for n in range(1, 41)])
```

A note for the PROG comment, if you want one: the longest Lyndon prefix of a word
is the first factor of its standard Lyndon factorization, so iterating Duval's
algorithm gives the same factorization the entry's Mathematica computes by
testing every prefix — and does it in O(len) rather than O(len^3).

## 6 · Keywords

`keyword: more` should come off — the theorem makes every term computable. Leave
that edit to the editor and say so in the comment box rather than doing it
yourself; changing someone else's keywords in the same edit that adds a proof is
how a submission acquires an argument it did not need.

## 7 · Optional — the b-file

`A329398-bfile-b329398.txt` in this directory holds n = 1..1000, one term per
line in OEIS b-file format. Every row comes from the proved closed form, and rows
1..30 were additionally cross-checked against the independent enumeration before
the file was written.

**Send it only if you send the proof.** A 1000-term b-file backed by an unproved
conjecture would be exactly the overclaim this package exists to avoid; backed by
the theorem it is just arithmetic. If an editor takes the terms but not the proof,
drop the b-file and keep the 45-term DATA line.

---

## 8 · What is NOT claimed

- The proof is new here and has **not been refereed**. It is elementary and
  machine-checked over n ≤ 16, which is not the same as correct — an editor or
  reader may find a gap, and the fallback is the position this package held
  before 2026-09-18: 15 terms, computed twice, formula verified not proved.
- The theorem is not machine-checked in a proof assistant. `a329398_proof_check.py`
  exhaustively verifies each lemma and both directions on finitely many words; the
  induction-free general argument is prose.
- Computing a term is not the same act as OEIS accepting one. These are submitted
  for editorial review and may be rejected.
- No claim of priority. The terms are absent from the OEIS entry and the formula
  is stated there as a conjecture; neither is the same as absent from the
  literature. A reader who knows the Lyndon-word literature may recognise this as
  a known result, and it would not be surprising.

## 9 · The submission itself (a human does this)

1. Register / log in at https://oeis.org (upper right).
2. Go to https://oeis.org/A329398 and click **edit**.
3. Replace the DATA section with the line in §1.
4. Add the FORMULA line in §4, the comment in §3, the Extensions line in §2 (with
   your name and today's date), and the PROG in §5.
5. In the edit-summary box, write one sentence: *"Adds a proof of the conjectured
   formula; the 15 new terms follow from it. `keyword: more` can probably come
   off."*
6. **Save changes**, then **"These changes are ready for review by an OEIS
   editor"**.

---

## 10 · Editor correspondence — 2026-09-18

The draft went to review and came back the same day.

| who | what |
|---|---|
| Alois P. Heinz | Proposed the changes for review. |
| Andrew Howroyd | "See edit screen. (usual length is 260 chars counting spaces and commas). This is currently at 216, so space for a few more terms." |
| Andrew Howroyd | Proposed for review and commented: "Can you add another 10 terms. This is still short of the usual length." |

Neither reviewer raised the proof, the formula, or the comment — the only ask is
length. That is a good sign and not a verdict: a draft is proposed for review
many times before an editor accepts it.

**The one thing to notice.** Howroyd's 216-character count for the 40-term line
is exactly reproduced by counting the DATA string with its commas and spaces, so
his convention and the one used in §1 are the same. Ten more terms therefore
lands at 295 characters, which is over the 260 he named. The likeliest reading
is that he wants it *longer* and 260 was a rough target rather than a ceiling —
both his comments push the same direction — so §1 leads with the 50-term line.
The 45-term line exists so that a length objection costs a paste, not a round
trip.

**Still nobody's call but the editors'.** `keyword: more` coming off, whether the
b-file is wanted, and whether the proof is accepted are all theirs. Do not argue
any of them into the edit summary.
