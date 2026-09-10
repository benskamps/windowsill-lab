"""The statistical floor `weird` stands on. Robust, dependency-light, honest.

Three rules, and they are the reason this file exists rather than a scipy import:

**Robust before parametric.** Medians and MADs, not means and sigmas. A corpus
of survey receipts is contaminated by construction — errored rows, retries,
saturated estimators — and a mean is a vote every outlier wins.

**Every estimator returns its own uncertainty, or says it cannot.** A number
without a scale cannot be compared to anything. Functions here return ``None``
rather than a value they cannot stand behind, and callers must branch on it.

**Nothing here knows what it is measuring.** No physics, no astronomy, no field
names. That is what lets the same code run against transit receipts, Ising
sweeps, and an embedding store.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence


# ── robust location and scale ───────────────────────────────────────────────

def median(xs: Sequence[float]) -> float | None:
    return statistics.median(xs) if xs else None


def mad(xs: Sequence[float]) -> float | None:
    """Median absolute deviation. ``None`` for an empty or constant sample.

    Constant is not zero-spread-with-a-scale; it is NO scale, and returning 0.0
    invites a division that silently yields infinity or a skipped test. The
    caller must decide what a constant field means.
    """
    if len(xs) < 2:
        return None
    m = statistics.median(xs)
    d = statistics.median([abs(x - m) for x in xs])
    return d if d > 0 else None


def robust_z(x: float, xs: Sequence[float]) -> float | None:
    """Deviation of ``x`` from the sample, in MADs. ``None`` if unscalable."""
    m, s = median(xs), mad(xs)
    if m is None or s is None:
        return None
    return (x - m) / s


def trimmed_mean(xs: Sequence[float], frac: float = 0.1) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = int(len(s) * frac)
    core = s[k:len(s) - k] or s
    return sum(core) / len(core)


# ── dependence, without assuming a shape ────────────────────────────────────

def _rank(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Monotone association. Catches curved relations a Pearson r would miss."""
    if len(xs) != len(ys) or len(xs) < 8:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def mutual_information(xs: Sequence[float], ys: Sequence[float],
                       bins: int = 8) -> float | None:
    """Dependence of ANY shape, in nats. Non-monotone, non-linear, all of it.

    Spearman sees a curve; this sees a ring, an XOR, a bimodal split. A pair
    with high MI and near-zero Spearman is exactly the shape nobody plots.
    """
    if len(xs) != len(ys) or len(xs) < 40:
        return None

    def binned(vs):
        lo, hi = min(vs), max(vs)
        if hi <= lo:
            return None
        w = (hi - lo) / bins
        return [min(bins - 1, int((v - lo) / w)) for v in vs]

    bx, by = binned(xs), binned(ys)
    if bx is None or by is None:
        return None
    n = len(xs)
    pxy = Counter(zip(bx, by))
    px, py = Counter(bx), Counter(by)
    mi = 0.0
    for (i, j), c in pxy.items():
        p = c / n
        mi += p * math.log(p / ((px[i] / n) * (py[j] / n)))
    return max(0.0, mi)


# ── distribution shape: the tells that mean a human or a cap touched it ─────

BENFORD = [math.log10(1 + 1 / d) for d in range(1, 10)]


def benford_deviation(xs: Sequence[float]) -> tuple[float, int] | None:
    """How far leading digits fall from Benford. Returns ``(chi2_per_dof, n)``.

    Real measurements spanning orders of magnitude obey Benford. Values that do
    not are typically generated, rounded, capped, or drawn from a narrow range —
    all of which are things worth knowing about a column nobody has inspected.
    Requires a wide range or the law does not apply and this returns ``None``.
    """
    vals = [abs(x) for x in xs if x and math.isfinite(x)]
    if len(vals) < 100:
        return None
    if max(vals) / min(vals) < 100:          # too narrow for the law to bind
        return None
    lead = Counter(int(str(f"{v:e}")[0]) for v in vals)
    n = sum(lead.values())
    chi2 = sum((lead.get(d, 0) - n * BENFORD[d - 1]) ** 2 / (n * BENFORD[d - 1])
               for d in range(1, 10))
    return chi2 / 8.0, n


def terminal_digit_bias(xs: Sequence[float], places: int = 2
                        ) -> tuple[float, int] | None:
    """Excess mass on round terminal digits — the tell of hand entry or capping.

    Returns ``(share_on_0_or_5, n)``. Uniform expectation is 0.2.
    """
    digs = []
    for x in xs:
        if not math.isfinite(x) or x == 0:
            continue
        # The FIRST version stripped trailing zeros before taking the last
        # digit, which deleted exactly the zeros that are the evidence: the
        # zero count was always 0, the true null was 1/9 rather than the
        # documented 1/5, and a maximally-round column scored LOWER than noise.
        # Take the terminal digit at the stated precision, as written.
        digs.append(f"{abs(x):.{places}f}".replace(".", "")[-1])
    if len(digs) < 100:
        return None
    c = Counter(digs)
    return (c.get("0", 0) + c.get("5", 0)) / len(digs), len(digs)


def quantization(xs: Sequence[float]) -> tuple[float, int] | None:
    """Is a 'continuous' column secretly on a lattice? ``(share, n_distinct)``.

    A float field taking few distinct values is a categorical wearing a
    number's clothes, and every statistic computed on it means something else.
    """
    vals = [x for x in xs if math.isfinite(x)]
    if len(vals) < 50:
        return None
    d = len(set(vals))
    return d / len(vals), d


def boundary_pileup(xs: Sequence[float]) -> tuple[str, float, float] | None:
    """Mass sitting exactly on the sample's own min or max.

    A ceiling in the DATA rather than in a declared constant — the same
    censoring, found without being told where the ceiling is.
    """
    vals = [x for x in xs if math.isfinite(x)]
    if len(vals) < 50:
        return None
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return None
    at_lo = sum(1 for v in vals if v == lo) / len(vals)
    at_hi = sum(1 for v in vals if v == hi) / len(vals)
    # BOTH edges. The first version returned on the first match, so a column
    # piled at min AND max reported only one — architecturally unable to see
    # the double censoring it was written to find.
    out = []
    if at_lo > 0.02:
        out.append(("min", lo, at_lo))
    if at_hi > 0.02:
        out.append(("max", hi, at_hi))
    return out or None


def modality(xs: Sequence[float], bins: int = 24) -> int | None:
    """Count of separated peaks. >1 where 1 is expected means two populations."""
    vals = [x for x in xs if math.isfinite(x)]
    if len(vals) < 100:
        return None
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return None
    w = (hi - lo) / bins
    hist = [0] * bins
    for v in vals:
        hist[min(bins - 1, int((v - lo) / w))] += 1
    floor = max(hist) * 0.1
    peaks, prev_above = 0, False
    for h in hist:
        above = h > floor
        if above and not prev_above:
            peaks += 1
        prev_above = above
    return peaks


# ── ordering: is the corpus a sequence, and does it change partway? ─────────

def changepoint(xs: Sequence[float]) -> tuple[int, float] | None:
    """Split point maximising the median gap. ``(index, gap_in_MADs)``.

    A field whose distribution shifts partway through a corpus means every
    aggregate over the whole is a mixture of two regimes.
    """
    if len(xs) < 60:
        return None
    best = None
    lo, hi = len(xs) // 5, len(xs) * 4 // 5
    for i in range(lo, hi):
        a, b = xs[:i], xs[i:]
        if len(a) < 20 or len(b) < 20:
            continue
        # Scale by the WITHIN-segment spread, never the whole column's. The
        # first version divided by mad(xs), which the shift itself inflates —
        # so the larger the regime change, the smaller the reported signal, and
        # a 50-sigma step read as 2. An estimator least sensitive to the
        # biggest effect it exists to find.
        sa, sb = mad(a), mad(b)
        scales = [s for s in (sa, sb) if s is not None]
        if not scales:
            continue
        pooled = sum(scales) / len(scales)
        gap = abs(statistics.median(a) - statistics.median(b)) / pooled
        if best is None or gap > best[1]:
            best = (i, gap)
    return best


def runs_test(xs: Sequence[float]) -> float | None:
    """Z of the runs statistic about the median. |z| large ⇒ rows not independent.

    Committed rows are usually ordered by when they were produced. Structure in
    that order is a property of the RUN, not of the subject.
    """
    if len(xs) < 40:
        return None
    m = statistics.median(xs)
    seq = [x > m for x in xs if x != m]
    n1, n2 = sum(seq), len(seq) - sum(seq)
    if n1 < 10 or n2 < 10:
        return None
    runs = 1 + sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = (2 * n1 * n2 * (2 * n1 * n2 - n1 - n2)) / \
          ((n1 + n2) ** 2 * (n1 + n2 - 1))
    if var <= 0:
        return None
    return (runs - mu) / math.sqrt(var)
