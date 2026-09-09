"""C03 — OEIS b-file extension: reproduce, cross-verify, price the reach, extend.

C01 calibrated the arithmetic stack by matching a 40-term prefix of A000045.
C03 is the frontier version of the same muscle: take a sequence whose b-file
ENDS somewhere, prove we can regenerate every term it already has, and then
compute terms it does not.

**Why this milestone is shaped like a gate and not like a run.** The lab's
standing failure mode is an instrument that cannot say "unsure", so nothing
here is allowed to claim an extension it has not earned:

1. **reproduce** — regenerate EVERY known term with method A and compare the
   reconstructed b-file bytes to OEIS's own. One mismatch and the run refuses.
   We do not get to extend a sequence we cannot reproduce.
2. **cross-verify** — a SECOND, algorithmically independent method must agree
   with the first. Independence is the point: two runs of one algorithm agree
   about their shared bug. The pair is declared per target below.
3. **price the reach** — time the terms we did compute, project the cost of the
   ones we have not, and return the number. ``out-of-reach`` is a RESULT
   (UNKNOWNS.md's rule), not a failure, and it is reported with its projection.
4. **extend** — only inside the measured budget, and a new term is claimed only
   where BOTH methods produce the same integer.

**The boundary, stated once and repeated into every receipt.** Computing a term
is not the same act as OEIS accepting one. Submission is an account action a
human takes, exactly as A02 holds the AAVSO half open; this module emits a
submission-ready fragment and claims nothing about its fate. A b-file's length
is also frequently a CURATION decision rather than a computational limit — a
sequence stopping at 10,000 terms usually stopped on purpose — so "we computed
more terms than the b-file holds" is a statement about this machine, and only
becomes a contribution where the editors say the terms were wanted.

**Measured 2026-09-09, and it is why the target registry is small.** The famous
short b-files are short because they are HARD, not because nobody pushed:
A000105 (polyominoes) stops at n=59, A000170 (n-queens) at 27 and A007764
(self-avoiding rook paths) at 27 — every one a standing record. OEIS also
publishes its own soft frontier and it is empty: ``keyword:more keyword:easy``
returns exactly ONE sequence. There is no pile of easy wanted terms lying
around, which is the honest reason this file ships as an instrument with a
calibrated target rather than as a claimed crossing.

**A note on the OEIS probe, for whoever automates the target search next.** The
search endpoint answers an over-broad query with a literal ``null`` body under
HTTP 200 — that is "TOO MANY to return", and a probe that reads it as "zero
results" will report an empty frontier that is actually a crowded one. It also
rate-limits to 403 under steady polling. :func:`oeis_search` encodes both.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = "windowsill-lab/0.1 C03 b-file extension"

#: Terms to attempt beyond the b-file's end, and the wall-clock the attempt is
#: allowed. Both are receipt fields: a run that spends its budget without
#: finishing reports what it reached, it does not run long.
DEFAULT_EXTEND_TERMS = 64
DEFAULT_BUDGET_SECONDS = 120.0

#: How many of the newest known terms are timed to build the cost projection.
REACH_SAMPLE_TERMS = 24

#: Cross-check depth. Method A runs over EVERY known term (it is the generator
#: whose bytes are compared to OEIS). Method B is the independent witness and
#: is often asymptotically dearer, so it runs over the newest terms plus a
#: seeded sample of the rest — the indices it covered are listed in the receipt
#: so the claim is exactly as wide as the work.
CROSS_CHECK_TAIL = 32
CROSS_CHECK_SAMPLE = 32
CROSS_CHECK_SEED = 20260909


# ── the sequences, each with two independent generators ──────────────────────

def _motzkin_recurrence(n_terms: int) -> list[int]:
    """Motzkin numbers by the three-term linear recurrence.

    ``(n+2)·M(n) = (2n+1)·M(n-1) + 3(n-1)·M(n-2)``, exact integer division.
    """
    if n_terms <= 0:
        return []
    terms = [1]
    if n_terms == 1:
        return terms
    terms.append(1)
    for n in range(2, n_terms):
        num = (2 * n + 1) * terms[n - 1] + 3 * (n - 1) * terms[n - 2]
        q, r = divmod(num, n + 2)
        if r:                      # the recurrence is exact over the integers;
            raise ArithmeticError(  # a remainder means the arithmetic broke
                f"Motzkin recurrence left remainder {r} at n={n}")
        terms.append(q)
    return terms


def _motzkin_binomial(indices: list[int]) -> dict[int, int]:
    """Motzkin numbers by ``M(n) = Σ_k C(n,2k)·Catalan(k)``.

    Independent of the recurrence in the way that matters: it evaluates a
    closed form per index from binomials and Catalan numbers rather than
    stepping a state forward, so a defect in one cannot be a defect in the
    other. Slower by construction — it is the witness, not the generator.
    """
    if not indices:
        return {}
    top = max(indices)
    catalan = [1]
    for k in range(1, top // 2 + 2):
        catalan.append(catalan[-1] * 2 * (2 * k - 1) // (k + 1))
    out = {}
    for n in indices:
        total = 0
        for k in range(n // 2 + 1):
            total += math.comb(n, 2 * k) * catalan[k]
        out[n] = total
    return out


def _fibonacci_iterative(n_terms: int) -> list[int]:
    """A000045 by the obvious forward iteration."""
    terms, a, b = [], 0, 1
    for _ in range(n_terms):
        terms.append(a)
        a, b = b, a + b
    return terms


def _fibonacci_fast_doubling(indices: list[int]) -> dict[int, int]:
    """A000045 by fast doubling — O(log n) per index, no shared state.

    ``F(2k) = F(k)·(2F(k+1) − F(k))``, ``F(2k+1) = F(k)² + F(k+1)²``.
    """
    def pair(n: int) -> tuple[int, int]:
        if n == 0:
            return 0, 1
        a, b = pair(n >> 1)
        c = a * (2 * b - a)
        d = a * a + b * b
        return (d, c + d) if n & 1 else (c, d)
    return {n: pair(n)[0] for n in indices}


@dataclass(frozen=True)
class Target:
    """One extendable sequence and the two methods that must agree on it."""
    a_number: str
    name: str
    offset: int                     # the b-file's first index
    method_a: str                   # name of the generator, for the receipt
    method_b: str                   # name of the independent witness
    generate: object                # (n_terms) -> list[int], indices from offset
    witness: object                 # (indices) -> {index: value}
    curation_note: str


TARGETS: dict[str, Target] = {
    "A001006": Target(
        a_number="A001006",
        name="Motzkin numbers",
        offset=0,
        method_a="three-term linear recurrence (n+2)M(n)=(2n+1)M(n-1)+3(n-1)M(n-2)",
        method_b="closed form M(n)=sum_k C(n,2k)*Catalan(k)",
        generate=_motzkin_recurrence,
        witness=_motzkin_binomial,
        curation_note=(
            "A001006's b-file runs to n=2106 — long by OEIS convention, not by "
            "computational limit. Terms past it are cheap here, so this target "
            "CALIBRATES the instrument end to end; it is not a claim that the "
            "editors want more Motzkin numbers."
        ),
    ),
    "A000045": Target(
        a_number="A000045",
        name="Fibonacci numbers",
        offset=0,
        method_a="forward iteration",
        method_b="fast doubling",
        generate=_fibonacci_iterative,
        witness=_fibonacci_fast_doubling,
        curation_note=(
            "The same sequence C01 calibrates a 40-term prefix against, carried "
            "the whole length of its b-file. Present so the registry has a "
            "second target and the two-method contract is exercised twice."
        ),
    ),
}

DEFAULT_TARGET = "A001006"


# ── OEIS access: cached, pinned, and honest about its own failure modes ──────

def _cache_dir() -> Path:
    root = os.environ.get("LAB_HOME") or (Path.home() / ".lab")
    d = Path(root) / "oeis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_bfile(a_number: str, *, timeout: int = 30,
                refresh: bool = False) -> tuple[bytes, str, bool]:
    """Return ``(raw_bytes, source_url, from_cache)`` for a sequence's b-file.

    Cached on disk and pinned by SHA-256 into the receipt, for the same reason
    A01 pins its FITS bytes: a check must re-derive every number offline, and
    OEIS rate-limits a polite client to 403 under steady use.
    """
    url = f"https://oeis.org/{a_number}/b{a_number[1:]}.txt"
    cached = _cache_dir() / f"b{a_number[1:]}.txt"
    if cached.exists() and not refresh:
        return cached.read_bytes(), url, True
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    cached.write_bytes(raw)
    return raw, url, False


def oeis_search(query: str, start: int = 0, *, timeout: int = 30):
    """Search OEIS. Returns a list of entries, or ``None`` for TOO MANY.

    ``None`` is not "no results" — the endpoint answers an over-broad query
    with a literal ``null`` body under HTTP 200, and a probe that collapses the
    two reports an empty frontier that is in fact a crowded one. Callers must
    branch on ``is None`` explicitly. A 403 is raised as
    :class:`urllib.error.HTTPError` and means the client is being rate-limited,
    not that the query is malformed.
    """
    url = ("https://oeis.org/search?q=" + urllib.parse.quote(query)
           + f"&fmt=json&start={int(start)}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
    if body.strip() == "null":
        return None
    return json.loads(body)


def parse_bfile(raw: bytes) -> list[tuple[int, int]]:
    """``(index, value)`` pairs from b-file bytes; comments and blanks dropped."""
    pairs = []
    for line in raw.decode("utf-8", "strict").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"unparseable b-file line: {line!r}")
        pairs.append((int(parts[0]), int(parts[1])))
    return pairs


def bfile_bytes(pairs: list[tuple[int, int]]) -> bytes:
    """The canonical b-file rendering of ``(index, value)`` pairs."""
    return "".join(f"{i} {v}\n" for i, v in pairs).encode("utf-8")


# ── the run ──────────────────────────────────────────────────────────────────

@dataclass
class C03Result:
    target: str
    sequence_name: str
    source_url: str
    source_from_cache: bool
    source_bytes: int
    source_sha256: str
    known_terms: int
    known_first_index: int
    known_last_index: int
    method_a: str
    method_b: str
    # stage 1
    reproduced: bool
    reproduce_detail: str
    generated_prefix_sha256: str
    source_prefix_sha256: str
    first_mismatch: dict | None
    # stage 2
    cross_checked: bool
    cross_check_detail: str
    cross_check_indices: list[int]
    cross_check_disagreements: list[dict]
    # stage 3
    reach_verdict: str
    reach_detail: str
    seconds_per_known_term: float
    projected_seconds_for_extension: float
    budget_seconds: float
    # stage 4
    extension_attempted: bool
    extension_terms_requested: int
    new_terms: list[dict] = field(default_factory=list)
    new_terms_agreed: int = 0
    extension_fragment: str = ""
    extension_fragment_sha256: str = ""
    status: str = "refused"
    wall_seconds: float = 0.0


def run_c03(target_id: str = DEFAULT_TARGET,
            extend_terms: int = DEFAULT_EXTEND_TERMS,
            budget_seconds: float = DEFAULT_BUDGET_SECONDS,
            refresh: bool = False) -> C03Result:
    t0 = time.time()
    if target_id not in TARGETS:
        raise KeyError(f"C03 has no registered target {target_id!r}; "
                       f"known: {sorted(TARGETS)}")
    tgt = TARGETS[target_id]

    raw, url, from_cache = fetch_bfile(tgt.a_number, refresh=refresh)
    pairs = parse_bfile(raw)
    if not pairs:
        raise ValueError(f"{tgt.a_number}: b-file parsed to zero terms")
    n_known = len(pairs)
    first_index, last_index = pairs[0][0], pairs[-1][0]

    # ── stage 1 · reproduce every known term, bytes and all ──────────────────
    gen_all = tgt.generate(first_index + n_known)
    generated = [(first_index + k, gen_all[first_index + k])
                 for k in range(n_known)]
    gen_bytes = bfile_bytes(generated)
    src_bytes = bfile_bytes(pairs)          # renormalised: whitespace is not
    reproduced = gen_bytes == src_bytes     # the claim, the integers are
    first_mismatch = None
    if not reproduced:
        for (i_s, v_s), (i_g, v_g) in zip(pairs, generated):
            if (i_s, v_s) != (i_g, v_g):
                first_mismatch = {"index": i_s, "oeis": str(v_s),
                                  "generated": str(v_g)}
                break
    reproduce_detail = (
        f"{n_known} terms n={first_index}..{last_index} regenerated by "
        f"{tgt.method_a} and compared as canonical b-file bytes: "
        + ("EXACT" if reproduced else f"MISMATCH at {first_mismatch}")
    )

    # ── stage 2 · an independent method must agree ───────────────────────────
    tail = [i for i, _v in pairs[-CROSS_CHECK_TAIL:]]
    rest = [i for i, _v in pairs[:-CROSS_CHECK_TAIL]] if n_known > CROSS_CHECK_TAIL else []
    sample: list[int] = []
    if rest:
        # Deterministic stride, not a shuffle: a seeded shuffle over a listing
        # that changes length is not a fixed sample (2026-09-01).
        stride = max(1, len(rest) // CROSS_CHECK_SAMPLE)
        sample = rest[(CROSS_CHECK_SEED % stride)::stride][:CROSS_CHECK_SAMPLE]
    check_indices = sorted(set(sample) | set(tail))
    known = dict(pairs)
    witness = tgt.witness(check_indices) if reproduced else {}
    disagreements = [
        {"index": i, "oeis": str(known[i]), "witness": str(witness[i])}
        for i in check_indices if i in witness and witness[i] != known[i]
    ]
    cross_checked = reproduced and bool(witness) and not disagreements
    cross_check_detail = (
        f"{len(check_indices)} indices ({len(tail)} newest + {len(sample)} "
        f"strided) re-derived by {tgt.method_b}: "
        + ("all agree" if cross_checked else
           (f"{len(disagreements)} DISAGREE" if reproduced else
            "not run — stage 1 refused"))
    )

    # ── stage 3 · price the reach ────────────────────────────────────────────
    sample_n = min(REACH_SAMPLE_TERMS, n_known)
    t_reach = time.time()
    tgt.generate(first_index + n_known + sample_n)
    reach_span = time.time() - t_reach
    # Cost of the WHOLE regeneration divided across the sampled tail: the
    # generators are prefix-recursive, so a term is never cheaper than this.
    per_term = reach_span / max(1, sample_n)
    projected = per_term * extend_terms
    in_reach = projected <= budget_seconds
    reach_verdict = "in-reach" if in_reach else "out-of-reach"
    reach_detail = (
        f"{sample_n} terms past the b-file cost {reach_span:.3f}s "
        f"({per_term * 1000:.2f} ms/term); {extend_terms} terms project to "
        f"{projected:.2f}s against a {budget_seconds:.0f}s budget"
    )

    # ── stage 4 · extend, both methods or not at all ─────────────────────────
    new_terms: list[dict] = []
    attempted = bool(reproduced and cross_checked and in_reach
                     and extend_terms > 0)
    if attempted:
        want = first_index + n_known + extend_terms
        extended = tgt.generate(want)
        new_indices = [last_index + 1 + k for k in range(extend_terms)]
        wit = tgt.witness(new_indices)
        for idx in new_indices:
            a_val = extended[idx]
            b_val = wit.get(idx)
            new_terms.append({
                "index": idx,
                "value": str(a_val),
                "agreed": b_val is not None and b_val == a_val,
            })
    agreed = [t for t in new_terms if t["agreed"]]
    fragment = "".join(f"{t['index']} {t['value']}\n" for t in agreed)
    status = ("pass" if (reproduced and cross_checked and agreed)
              else ("null" if reproduced and cross_checked else "refused"))

    return C03Result(
        target=tgt.a_number,
        sequence_name=tgt.name,
        source_url=url,
        source_from_cache=from_cache,
        source_bytes=len(raw),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        known_terms=n_known,
        known_first_index=first_index,
        known_last_index=last_index,
        method_a=tgt.method_a,
        method_b=tgt.method_b,
        reproduced=reproduced,
        reproduce_detail=reproduce_detail,
        generated_prefix_sha256=hashlib.sha256(gen_bytes).hexdigest(),
        source_prefix_sha256=hashlib.sha256(src_bytes).hexdigest(),
        first_mismatch=first_mismatch,
        cross_checked=cross_checked,
        cross_check_detail=cross_check_detail,
        cross_check_indices=check_indices,
        cross_check_disagreements=disagreements,
        reach_verdict=reach_verdict,
        reach_detail=reach_detail,
        seconds_per_known_term=round(per_term, 9),
        projected_seconds_for_extension=round(projected, 6),
        budget_seconds=budget_seconds,
        extension_attempted=attempted,
        extension_terms_requested=extend_terms,
        new_terms=new_terms,
        new_terms_agreed=len(agreed),
        extension_fragment=fragment,
        extension_fragment_sha256=hashlib.sha256(
            fragment.encode("utf-8")).hexdigest(),
        status=status,
        wall_seconds=round(time.time() - t0, 3),
    )


def to_report(result: C03Result) -> dict:
    return {
        "experiment": "C03-oeis-bfile-extension",
        "headline": (
            f"{result.target} ({result.sequence_name}): {result.known_terms} "
            f"known terms regenerated "
            f"{'EXACTLY' if result.reproduced else 'WITH A MISMATCH'} and "
            f"cross-verified by a second method "
            f"({'agree' if result.cross_checked else 'NOT VERIFIED'}); "
            f"{result.new_terms_agreed} new terms computed past n="
            f"{result.known_last_index} in {result.wall_seconds}s "
            f"[{result.reach_verdict}]"
        ),
        "status": result.status,
        "target": result.target,
        "sequence_name": result.sequence_name,
        "source_url": result.source_url,
        "source_from_cache": result.source_from_cache,
        "source_bytes": result.source_bytes,
        "source_sha256": result.source_sha256,
        "known_terms": result.known_terms,
        "known_first_index": result.known_first_index,
        "known_last_index": result.known_last_index,
        "method_a": result.method_a,
        "method_b": result.method_b,
        "reproduced": result.reproduced,
        "reproduce_detail": result.reproduce_detail,
        "generated_prefix_sha256": result.generated_prefix_sha256,
        "source_prefix_sha256": result.source_prefix_sha256,
        "first_mismatch": result.first_mismatch,
        "cross_checked": result.cross_checked,
        "cross_check_detail": result.cross_check_detail,
        "cross_check_indices": result.cross_check_indices,
        "cross_check_disagreements": result.cross_check_disagreements,
        "reach_verdict": result.reach_verdict,
        "reach_detail": result.reach_detail,
        "seconds_per_known_term": result.seconds_per_known_term,
        "projected_seconds_for_extension":
            result.projected_seconds_for_extension,
        "budget_seconds": result.budget_seconds,
        "extension_attempted": result.extension_attempted,
        "extension_terms_requested": result.extension_terms_requested,
        "new_terms": result.new_terms,
        "new_terms_agreed": result.new_terms_agreed,
        "extension_fragment": result.extension_fragment,
        "extension_fragment_sha256": result.extension_fragment_sha256,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "What is graded: every term already in the b-file was regenerated "
            f"from scratch by {result.method_a} and matched as canonical "
            "b-file bytes, and an algorithmically independent second method "
            f"({result.method_b}) agrees on the newest terms plus a strided "
            "sample of the rest and on every new term claimed. What is NOT "
            "claimed: that OEIS wants these terms, or has accepted them. "
            "Submitting a b-file is an account action a human takes, exactly "
            "as A02 holds its AAVSO half open, and a b-file's length is "
            "frequently a curation decision rather than a computational "
            "limit. " + TARGETS[result.target].curation_note
        ),
    }
