"""A329398 — the solver that produced the lab's first new numbers.

The load-bearing test is `test_the_prune_reproduces_every_published_term`: the
prune is an optimisation over a definition nobody can check by eye, so its only
defence is that it returns the 25 terms OEIS already publishes. A prune that is
too aggressive does not crash — it silently returns a smaller number, and that
number would go to an editor.
"""
import pytest

from lab import a329398


def _naive_lyndon_lengths(q):
    """The entry's own method: test every prefix, take the longest Lyndon one.

    Deliberately the slow O(len^3) transcription, kept as the independent
    witness for the fast one. `q < rotation` for every proper rotation is the
    Mathematica's lynQ.
    """
    def lyn(w):
        return all(w < w[-i:] + w[:-i] for i in range(1, len(w)))
    out = []
    while q:
        best = max(i for i in range(1, len(q) + 1) if lyn(q[:i]))
        out.append(best)
        q = q[best:]
    return out


# ── the algorithms agree with each other ─────────────────────────────────────

@pytest.mark.parametrize("word", [
    (1,), (1, 2), (2, 1), (1, 1, 1), (1, 2, 3), (3, 2, 1), (2, 1, 2, 1),
    (1, 3, 2, 3, 1), (5, 1, 4, 1, 4), (2, 2, 1, 3, 1, 3),
])
def test_duval_matches_the_naive_longest_prefix_factorisation(word):
    """The Duval rewrite's whole justification: the longest Lyndon prefix IS the
    first factor of the standard factorisation, so iterating it gives the same
    answer as the entry's Mathematica — 25x faster and identical."""
    assert a329398.duval_lengths(word) == _naive_lyndon_lengths(word)


def test_duval_lengths_sum_to_the_word():
    for n in range(1, 9):
        for word in [(n,), tuple(range(1, n + 1)), tuple(range(n, 0, -1))]:
            assert sum(a329398.duval_lengths(word)) == len(word)


# ── the prune keeps every answer ─────────────────────────────────────────────

def test_the_prune_reproduces_every_published_term():
    """The positive control, and the only thing standing between an optimisation
    and a wrong number in the OEIS. All 25 terms, exactly."""
    for i, want in enumerate(a329398.PUBLISHED, start=a329398.OFFSET):
        assert a329398.count(i) == want, f"a({i})"


def test_reproduces_published_is_the_same_control():
    assert a329398.reproduces_published() is True


def test_the_prune_agrees_with_an_unpruned_enumeration():
    """Independent of the published terms: enumerate WITHOUT the prune and
    compare. If the prune ever cuts a live branch, these separate."""
    def unpruned(n):
        total = 0
        stack = [((), n)]
        while stack:
            pref, rem = stack.pop()
            if rem == 0:
                a = a329398.duval_lengths(pref)
                b = a329398.duval_lengths(tuple(-x for x in pref))
                if len(set(a)) <= 1 and len(set(b)) <= 1:
                    total += 1
                continue
            for p in range(1, rem + 1):
                stack.append((pref + (p,), rem - p))
        return total
    for n in range(1, 17):
        assert a329398.count(n) == unpruned(n), f"prune lost answers at n={n}"


# ── the witness is a check, never a source ───────────────────────────────────

def test_the_conjecture_witness_agrees_on_every_published_term():
    for i, want in enumerate(a329398.PUBLISHED, start=a329398.OFFSET):
        assert a329398.witness(i) == want, f"witness disagrees at a({i})"


def test_the_witness_is_computed_from_partitions_and_divisors_only():
    """2*A000041(n) - A000005(n) on small n, by hand.

    n=6: p(6)=11, d(6)=4 -> 18.  n=12: p(12)=77, d(12)=6 -> 148.
    Both appear in PUBLISHED, so this pins the witness to arithmetic rather
    than to a lookup of the answer it is supposed to be checking.
    """
    assert a329398.witness(6) == 2 * 11 - 4 == 18
    assert a329398.witness(12) == 2 * 77 - 6 == 148


def test_the_two_methods_agree_past_the_published_range():
    """n=26 and 27 are terms OEIS does not carry. Both methods, still agreeing —
    the property that makes a new term submittable at all."""
    assert a329398.count(26) == a329398.witness(26) == 4868
    assert a329398.count(27) == a329398.witness(27) == 6016


def test_degenerate_inputs_do_not_invent_answers():
    assert a329398.count(0) == 0
    assert a329398.count(-3) == 0
    assert a329398.witness(0) == 0
