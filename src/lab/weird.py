"""weird — find what nobody looked at, in data you already own.

A survey's discards are somebody's dataset. A05 measured depth, period,
crowding, odd-even, secondaries and stellar parameters on 13,621 targets while
searching for exactly one thing. Nobody ever asked that table a different
question.

## The design rule

**No domain knowledge in this module.** It learns each corpus's own normal and
reports what breaks it, so the same code runs against hunt receipts, physics
receipts, Ember's brain, or any list of dicts. A finding here is always of the
form *"this relation holds N times and not here"* — a question with its own
falsifier already attached, which is what makes it safe to generate at volume.

## Every detector must prove it can see

Each family takes a ``control`` — an anomaly already known to be in the corpus —
and **withholds its entire report if it fails to rediscover it**. This is not
decoration. The first two versions of the sibling dead-gate linter reported a
clean floor because they could not see the floor, and only a planted control
caught them. A detector whose silence has never been tested is a detector whose
silence means nothing.

## The families

``ratio_violations``  Relations the corpus obeys everywhere and one row does not.
                      Found the d_min ceiling from a blind field pair.
``censored_values``   Values pinned exactly at the edge of a declared set. A
                      right-censored bound stored as a measurement — 377 of the
                      survey's 5,130 sensitivity cells.
``group_signature``   Given outlier rows, what do they share that the corpus
                      does not? One outlier is noise; a population has a cause.
``absent_fields``     Negative space: fields that stop, start, or hold on a
                      subgroup and nowhere else. The only family that looks for
                      what is NOT there.
"""
from __future__ import annotations

import itertools
import collections
import functools
import hashlib
import re
import json
import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field as dc_field
from pathlib import Path

#: Below this many shared rows a "relation" is a coincidence, not a norm.
MIN_PAIRS = 200
#: log-space MAD above which a ratio is too loose to call a relation at all.
MAX_RELATION_MAD = 0.35
#: Deviations beyond this many MADs are reported.
Z_REPORT = 12.0


@dataclass
class Finding:
    family: str
    subject: str                  # the row/id the finding is about
    detail: str
    z: float = 0.0
    evidence: dict = dc_field(default_factory=dict)

    def __str__(self) -> str:
        if self.z == float("inf"):
            z = "    inf MAD  "
        else:
            z = f"{self.z:7.1f} MAD  " if self.z else " " * 13
        return f"{z}[{self.family}] {self.subject}: {self.detail}"


@dataclass
class Report:
    family: str
    findings: list[Finding]
    saw_control: bool
    control: str

    def __bool__(self) -> bool:
        return self.saw_control

    def render(self) -> str:
        if not self.saw_control:
            return (f"[{self.family}] BLIND — failed to rediscover its control "
                    f"({self.control}). Its silence proves nothing; the "
                    f"{len(self.findings)} finding(s) it produced are withheld.")
        if not self.findings:
            return (f"[{self.family}] trusted and QUIET — {self.control}. "
                    f"Nothing found, and that is a result.")
        head = (f"[{self.family}] trusted ({self.control}) — "
                f"{len(self.findings)} finding(s)")
        return "\n".join([head] + ["  " + str(f) for f in self.findings])


# ── loading: any corpus of dicts, flattened ──────────────────────────────────

def flatten(obj, prefix: str = "") -> dict:
    """Numeric leaves only, dotted keys. Booleans are not numbers.

    Refuses a non-mapping rather than raising. Real corpora hand you lists of
    strings where you expected records — the coherence-lab results keep their
    cells in a dict keyed by NAME, and the first port crashed on a `str` that
    had no `.items()`. An adapter should get an empty row and notice, not a
    traceback halfway through a sweep.
    """
    if not isinstance(obj, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool) \
                and math.isfinite(v):
            out[key] = float(v)
    return out


def load_rows(paths: Iterable[Path], key: str, id_field: str = "tic") -> list[dict]:
    """``[{_id, _src, <numeric fields>}]`` from a directory of JSON documents."""
    rows: list[dict] = []
    for p in sorted(paths):
        try:
            doc = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            continue
        for item in (doc.get(key) or []):
            if not isinstance(item, dict):
                continue
            flat = flatten(item)
            flat["_id"] = str(item.get(id_field))
            flat["_src"] = Path(p).name
            rows.append(flat)
    return rows


#: A column must appear on at least this many rows to be OFFERED to a family.
#: Deliberately near the floor: every family already enforces its own
#: statistical minimum (ratio and redundant need MIN_PAIRS, Benford and
#: modality need 100, pileup and discrete 50, runs 40), so a global gate adds
#: no protection and only blinds.
#:
#: It cost a great deal to learn that. The original used 5% of the corpus —
#: 681 rows here — and dropped 114 of 131 columns. The survey's sparse fields
#: are precisely its SCIENCE: centroid shifts, blend evidence, catalogue
#: crosschecks, fold gates. They are sparse because they only exist on rows
#: that crossed threshold, which is to say on the interesting ones. The tool
#: was auditing the pipeline's plumbing and structurally could not see the sky.
MIN_ROWS_FOR_FIELD = 12


def _fields(rows: Sequence[dict], min_rows: int = MIN_ROWS_FOR_FIELD) -> list[str]:
    """Every numeric column present on enough rows to say anything about.

    Zero and negative values COUNT. The first version required ``v > 0``, which
    made a column clamped at -1.0 and an all-zero column invisible to every
    family — including the constant-detector that `explain_away` depends on, so
    a zero-valued constant could never be explained away at all.
    """
    counts: dict[str, int] = {}
    for r in rows:
        for k, v in r.items():
            if not k.startswith("_") and isinstance(v, float):
                counts[k] = counts.get(k, 0) + 1
    return sorted(k for k, n in counts.items() if n >= min_rows)


def _mad(values: Sequence[float]) -> tuple[float, float]:
    med = statistics.median(values)
    return med, statistics.median([abs(v - med) for v in values])


# ── family 1: relations the corpus obeys, and what breaks them ───────────────

def ratio_violations(rows: Sequence[dict], control_id: str,
                     z_report: float = Z_REPORT) -> Report:
    """Field pairs whose ratio is tight corpus-wide; rows that break them."""
    findings: list[Finding] = []
    for a, b in itertools.combinations(_fields(rows), 2):
        pairs = [(r, r[a] / r[b]) for r in rows
                 if r.get(a, 0) > 0 and r.get(b, 0) > 0]
        if len(pairs) < MIN_PAIRS:
            continue
        logs = [math.log(x) for _r, x in pairs]
        med, mad = _mad(logs)
        if mad > MAX_RELATION_MAD:
            continue
        if mad <= 0:
            # An EXACT relation — b is a fixed multiple of a on every row that
            # obeys it. Skipping this made the tightest relations in any corpus
            # invisible; reporting it unguarded made 3,306 findings of which
            # almost none were anomalies. TWO guards, both learned the hard way:
            #
            #  * a LATTICE column has a modal ratio by construction. `d_min`
            #    takes 3 values and `fap.B` is the constant 256, so two thirds
            #    of that pair "violate" a relation that was never a relation.
            #  * a column DEFINED as one of two others (fap_graded = max(iid,
            #    block)) equals each of them most of the time, and the rows
            #    where the other won are the definition working.
            #
            # So: both columns must be genuinely continuous, and the exact
            # relation must hold on the overwhelming majority before a departure
            # from it means anything.
            da = len({r[a] for r, _x in pairs})
            db = len({r[b] for r, _x in pairs})
            conform = sum(1 for _r, x in pairs
                          if abs(math.log(x) - med) <= 1e-12) / len(pairs)
            if min(da, db) <= 12 or conform < 0.90:
                continue
            for r, ratio in pairs:
                if abs(math.log(ratio) - med) > 1e-12:
                    findings.append(Finding(
                        "ratio", r["_id"],
                        f"{a}/{b} = {ratio:.6g} where the relation is EXACT at "
                        f"{math.exp(med):.6g} on every other row — no scale to "
                        f"measure against, so the deviation is unbounded",
                        float("inf"),
                        {"field_a": a, "field_b": b, "src": r["_src"],
                         "exact": True}))
            continue
        for r, ratio in pairs:
            z = abs(math.log(ratio) - med) / mad
            if z > z_report:
                findings.append(Finding(
                    "ratio", r["_id"],
                    f"{a}/{b} = {ratio:.4g}, corpus typical {math.exp(med):.4g}",
                    z, {"field_a": a, "field_b": b, "src": r["_src"]}))
    findings.sort(key=lambda f: -f.z)
    # A star searched in several receipts yields the same violation once per
    # receipt. That is one anomaly, not four — the same row-vs-star distinction
    # that made the shelf read 10 leads where there were 9.
    seen, unique = set(), []
    for f in findings:
        key = (f.subject, f.evidence.get("field_a"), f.evidence.get("field_b"))
        if key in seen:
            continue
        seen.add(key); unique.append(f)
    findings = unique
    return Report("ratio", findings,
                  any(f.subject == control_id for f in findings),
                  f"TIC {control_id} breaks a known relation")


# ── family 2: values pinned at a declared boundary ───────────────────────────

def censored_values(rows: Sequence[dict], declared: dict[str, Sequence[float]],
                    control_field: str) -> Report:
    """A value sitting exactly on the edge of its own declared set is a BOUND.

    An injection ladder topping out at 1% stores ``0.010`` for a host that
    recovered only the deepest rung — indistinguishable from a host genuinely
    measured at 1%. The prose may say ">=" and be honest; the DATA does not, so
    every consumer that computes on it reads a floor as a measurement.
    """
    findings: list[Finding] = []
    for field, rungs in declared.items():
        ceiling = max(rungs)
        vals = [(r, r[field]) for r in rows if field in r]
        if not vals:
            continue
        at = [r for r, v in vals if abs(v - ceiling) < 1e-12]
        if not at:
            continue
        findings.append(Finding(
            "censored", field,
            f"{len(at)} of {len(vals)} values sit exactly on the declared "
            f"ceiling {ceiling:g} ({100*len(at)/len(vals):.1f}%) — these are "
            f"lower bounds stored as measurements",
            0.0, {"ceiling": ceiling, "n_censored": len(at), "n_total": len(vals),
                  "ids": sorted({r['_id'] for r in at})[:20]}))
    return Report("censored", findings,
                  any(f.subject == control_field for f in findings),
                  f"{control_field} is known to be censored")


# ── family 3: what a set of outliers shares ─────────────────────────────────

def group_signature(rows: Sequence[dict], group_ids: set[str],
                    control_field: str, z_report: float = 6.0) -> Report:
    """One outlier is noise. A population breaking the same rule has a cause."""
    grp = [r for r in rows if r["_id"] in group_ids]
    rest = [r for r in rows if r["_id"] not in group_ids]
    findings: list[Finding] = []
    if len(grp) < 3:
        return Report("signature", findings, False, control_field)
    for k in sorted({k for r in grp for k in r if not k.startswith("_")}):
        g = [r[k] for r in grp if k in r]
        o = [r[k] for r in rest if k in r]
        if len(g) < 3 or len(o) < MIN_PAIRS:
            continue
        med_o, mad_o = _mad(o)
        med_g = statistics.median(g)
        if mad_o <= 0:
            # The corpus has NO spread in this field. There is no scale to
            # divide by — but "I cannot compute a z" is not "there is nothing
            # here", and skipping silently is the two-state failure this whole
            # module exists to refuse. A group that differs from a constant
            # differs infinitely.
            if med_g != med_o:
                findings.append(Finding(
                    "signature", k,
                    f"group median {med_g:.5g} vs corpus {med_o:.5g}, which is "
                    "CONSTANT across the corpus — no scale to measure against, "
                    "so the deviation is unbounded rather than unmeasured",
                    float("inf"), {"corpus_constant": med_o}))
            continue
        z = (med_g - med_o) / mad_o
        if abs(z) > z_report:
            findings.append(Finding(
                "signature", k,
                f"group median {statistics.median(g):.5g} vs corpus "
                f"{med_o:.5g}", abs(z), {"signed_z": z}))
    findings.sort(key=lambda f: -f.z)
    return Report("signature", findings,
                  any(f.subject == control_field for f in findings),
                  f"the group is distinctive in {control_field}")


# ── family 4: negative space ────────────────────────────────────────────────

def absent_fields(rows: Sequence[dict], order_key: str = "_src",
                  control_field: str = "") -> Report:
    """Fields that START or STOP partway through a corpus.

    The only family that looks for what is NOT there. A field present on every
    row after some point and none before is schema evolution — and every
    aggregate computed across the boundary silently mixes rows that could carry
    the field with rows that never could.
    """
    order = sorted({r[order_key] for r in rows})
    idx = {s: i for i, s in enumerate(order)}
    spans: dict[str, list[int]] = {}
    for r in rows:
        i = idx[r[order_key]]
        for k in r:
            if k.startswith("_"):
                continue
            spans.setdefault(k, [i, i])
            spans[k][0] = min(spans[k][0], i)
            spans[k][1] = max(spans[k][1], i)
    findings: list[Finding] = []
    last = len(order) - 1
    for k, (lo, hi) in sorted(spans.items()):
        if lo > 0:
            findings.append(Finding(
                "absent", k,
                f"first appears at {order[lo]} — absent from the {lo} earlier "
                f"source(s); anything aggregating across that line mixes rows "
                f"that could carry it with rows that never could", float(lo)))
        elif hi < last:
            findings.append(Finding(
                "absent", k,
                f"stops after {order[hi]} — gone for the last {last-hi} "
                f"source(s)", float(last - hi)))
    findings.sort(key=lambda f: -f.z)
    return Report("absent", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any field with a partial span")


# ═══════════════════════════════════════════════════════════════════════════
# The wider suite. Everything below takes the same corpus shape and returns
# the same Report, so `run_all` can drive them uniformly and a caller can add
# a family without touching anything else.
# ═══════════════════════════════════════════════════════════════════════════

from . import weird_stats as ws  # noqa: E402


def _column(rows: Sequence[dict], k: str) -> list[float]:
    return [r[k] for r in rows if k in r]


def boundary_pileups(rows: Sequence[dict], control_field: str = "") -> Report:
    """Censoring found WITHOUT being told where the ceiling is.

    ``censored_values`` needs a declared ladder. This one reads the sample's own
    extremes and asks whether an implausible share of the mass sits exactly on
    one — which is what a cap, a clamp, or a saturated estimator looks like from
    the outside.
    """
    findings = []
    for k in _fields(rows):
        hits = ws.boundary_pileup(_column(rows, k))
        if not hits:
            continue
        for edge, value, share in hits:
            findings.append(Finding(
                "pileup", k,
                f"{share:.1%} of values sit exactly on the sample {edge} "
                f"({value:g}) — a cap, a clamp or a saturated estimator, not a "
                f"measurement that happened to land there",
                share * 100, {"edge": edge, "value": value, "share": share}))
    findings.sort(key=lambda f: -f.z)
    return Report("pileup", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any column with mass on an extreme")


def digit_law_violations(rows: Sequence[dict], control_field: str = "") -> Report:
    """Leading digits that do not obey Benford where the range says they should.

    A column spanning orders of magnitude has a leading-digit law. Departure
    means generated, rounded, capped, or drawn from a hidden narrow band — all
    facts about the column that its name does not carry.
    """
    findings = []
    for k in _fields(rows):
        got = ws.benford_deviation(_column(rows, k))
        if not got:
            continue
        tv, n = got
        # 0.15 total variation is a digit distribution a person would call
        # visibly different — roughly a 15-point shift of probability mass.
        # Scale-free, so it means the same on 100 rows and on 13,000.
        if tv > 0.15:
            findings.append(Finding(
                "benford", k,
                f"leading digits depart from Benford by {tv:.0%} total "
                f"variation over {n} values — generated, rounded, capped or "
                f"drawn from a narrower band than the range implies", tv * 100,
                {"total_variation": tv, "n": n}))
    findings.sort(key=lambda f: -f.z)
    return Report("benford", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any column departing from Benford")


def rounding_tells(rows: Sequence[dict], control_field: str = "") -> Report:
    """Excess mass on terminal 0 and 5 — hand entry, or a rounded pipeline."""
    findings = []
    for k in _fields(rows):
        got = ws.terminal_digit_bias(_column(rows, k))
        if not got:
            continue
        share, n = got
        if share > 0.45:
            findings.append(Finding(
                "rounding", k,
                f"{share:.0%} of terminal digits are 0 or 5 against 20% "
                f"expected ({n} values) — the column was rounded or entered by "
                f"hand somewhere upstream", share * 100,
                {"share": share, "n": n}))
    findings.sort(key=lambda f: -f.z)
    return Report("rounding", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any column with round-digit excess")


def secretly_discrete(rows: Sequence[dict], control_field: str = "") -> Report:
    """Float columns on a lattice — a categorical wearing a number's clothes."""
    findings = []
    for k in _fields(rows):
        got = ws.quantization(_column(rows, k))
        if not got:
            continue
        share, distinct = got
        if distinct <= 12 and share < 0.05:
            findings.append(Finding(
                "discrete", k,
                f"only {distinct} distinct values across {len(_column(rows,k))} "
                f"rows — this is a category, and every mean, MAD or correlation "
                f"taken over it means something other than it appears to",
                1.0 / max(share, 1e-9), {"distinct": distinct}))
    findings.sort(key=lambda f: -f.z)
    return Report("discrete", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any float column on a small lattice")


def redundant_fields(rows: Sequence[dict], control_pair: tuple = ()) -> Report:
    """Pairs that are near-perfect functions of one another.

    Two columns carrying the same fact are TWO PRODUCERS. They agree today;
    the interesting day is the one where they stop, and nothing is watching.
    This is the drift bug found before it drifts.
    """
    findings = []
    fs = _fields(rows)
    for a, b in itertools.combinations(fs, 2):
        xs = [(r[a], r[b]) for r in rows if a in r and b in r]
        if len(xs) < MIN_PAIRS:
            continue
        rho = ws.spearman([x for x, _ in xs], [y for _, y in xs])
        if rho is not None and abs(rho) > 0.999:
            findings.append(Finding(
                "redundant", f"{a} ~ {b}",
                f"|rho| = {abs(rho):.5f} over {len(xs)} rows — one is derived "
                f"from the other. Two homes for one fact is a drift waiting to "
                f"happen; delete a home or bind them with a test.",
                abs(rho) * 1000, {"rho": rho, "n": len(xs), "a": a, "b": b}))
    findings.sort(key=lambda f: -f.z)
    return Report("redundant", findings,
                  (f"{control_pair[0]} ~ {control_pair[1]}" in
                   {f.subject for f in findings}) if control_pair
                  else bool(findings),
                  " ~ ".join(control_pair) if control_pair
                  else "any near-perfectly dependent pair")


def hidden_dependence(rows: Sequence[dict], control_pair: tuple = ()) -> Report:
    """Pairs with strong mutual information and NO monotone correlation.

    This is the shape nobody plots: a ring, a fork, an XOR, two populations
    crossing. Spearman reads zero and the pair looks independent in every
    summary table ever produced from it.
    """
    findings = []
    fs = _fields(rows)
    for a, b in itertools.combinations(fs, 2):
        xs = [(r[a], r[b]) for r in rows if a in r and b in r]
        if len(xs) < 200:
            continue
        u, v = [x for x, _ in xs], [y for _, y in xs]
        rho, mi = ws.spearman(u, v), ws.mutual_information(u, v)
        if mi is None or rho is None:
            continue
        if mi > 0.25 and abs(rho) < 0.15:
            findings.append(Finding(
                "hidden", f"{a} ~ {b}",
                f"mutual information {mi:.3f} nats with Spearman only "
                f"{rho:+.3f} over {len(xs)} rows — strongly related in a shape "
                f"no correlation reports. Plot this one.",
                mi * 100, {"mi": mi, "rho": rho, "n": len(xs), "a": a, "b": b}))
    findings.sort(key=lambda f: -f.z)
    return Report("hidden", findings,
                  (f"{control_pair[0]} ~ {control_pair[1]}" in
                   {f.subject for f in findings}) if control_pair
                  else bool(findings),
                  " ~ ".join(control_pair) if control_pair
                  else "any pair dependent without correlation")


def regime_changes(rows: Sequence[dict], order_key: str = "_src",
                   control_field: str = "") -> Report:
    """Columns whose distribution shifts partway through the corpus.

    Every aggregate spanning the shift is a mixture of two regimes reported as
    one number.
    """
    ordered = sorted(rows, key=lambda r: (r.get(order_key, ""), r.get("_id", "")))
    findings = []
    for k in _fields(rows):
        col = [r[k] for r in ordered if k in r]
        got = ws.changepoint(col)
        if not got:
            continue
        idx, gap = got
        if gap > 4.0:
            srcs = [r.get(order_key) for r in ordered if k in r]
            findings.append(Finding(
                "regime", k,
                f"distribution shifts by {gap:.1f} MADs at {srcs[idx]} "
                f"({idx}/{len(col)} through) — anything averaged across that "
                f"line mixes two regimes", gap,
                {"index": idx, "gap_mads": gap, "at": srcs[idx]}))
    findings.sort(key=lambda f: -f.z)
    return Report("regime", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any column with a shift in its ordering")


def order_dependence(rows: Sequence[dict], order_key: str = "_src",
                     control_field: str = "") -> Report:
    """Values that are not independent of the order they were produced in.

    A property of the RUN masquerading as a property of the subject.
    """
    ordered = sorted(rows, key=lambda r: (r.get(order_key, ""), r.get("_id", "")))
    findings = []
    for k in _fields(rows):
        z = ws.runs_test([r[k] for r in ordered if k in r])
        if z is not None and abs(z) > 6.0:
            findings.append(Finding(
                "order", k,
                f"runs test z = {z:+.1f} against the corpus ordering — the "
                f"value depends on WHEN the row was produced, which is a fact "
                f"about the run, not the subject", abs(z), {"runs_z": z}))
    findings.sort(key=lambda f: -f.z)
    return Report("order", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any column correlated with its ordering")


def multimodal_fields(rows: Sequence[dict], control_field: str = "") -> Report:
    """Columns with separated peaks — two populations summarised as one."""
    findings = []
    for k in _fields(rows):
        peaks = ws.modality(_column(rows, k))
        if peaks and peaks >= 3:
            findings.append(Finding(
                "modal", k,
                f"{peaks} separated peaks — this column is a mixture, and its "
                f"median describes none of its populations", float(peaks),
                {"peaks": peaks}))
    findings.sort(key=lambda f: -f.z)
    return Report("modal", findings,
                  any(f.subject == control_field for f in findings)
                  if control_field else bool(findings),
                  control_field or "any multimodal column")


def duplicate_rows(rows: Sequence[dict], control_id: str = "") -> Report:
    """Rows identical on every numeric field — one measurement, filed twice."""
    seen: dict[tuple, list[dict]] = {}
    for r in rows:
        key = tuple(sorted((k, v) for k, v in r.items() if not k.startswith("_")))
        if len(key) < 5:
            continue
        seen.setdefault(key, []).append(r)
    findings = []
    for key, group in seen.items():
        if len(group) < 2:
            continue
        srcs = sorted({g["_src"] for g in group})
        if len(srcs) < 2:
            continue                      # same file twice is a different bug
        findings.append(Finding(
            "duplicate", group[0]["_id"],
            f"identical on all {len(key)} numeric fields across {len(srcs)} "
            f"sources ({', '.join(srcs[:3])}) — one measurement filed more "
            f"than once, not repeated observation", float(len(group)),
            {"sources": srcs, "n": len(group)}))
    findings.sort(key=lambda f: -f.z)
    return Report("duplicate", findings,
                  any(f.subject == control_id for f in findings)
                  if control_id else bool(findings),
                  control_id or "any row duplicated across sources")


def subgroup_reversals(rows: Sequence[dict], group_field: str,
                       control_pair: tuple = ()) -> Report:
    """Simpson's paradox: a relation that reverses inside subgroups.

    The corpus-wide sign is the aggregate; the subgroup signs are the truth.
    Where they disagree, every conclusion drawn from the aggregate is backwards.
    """
    findings = []
    groups: dict[float, list[dict]] = {}
    for r in rows:
        if group_field in r:
            groups.setdefault(r[group_field], []).append(r)
    big = {g: rs for g, rs in groups.items() if len(rs) >= 100}
    if len(big) < 2:
        return Report("simpson", [], False, "at least two sizeable subgroups")
    for a, b in itertools.combinations(_fields(rows), 2):
        whole = [(r[a], r[b]) for r in rows if a in r and b in r]
        if len(whole) < MIN_PAIRS:
            continue
        rho_all = ws.spearman([x for x, _ in whole], [y for _, y in whole])
        if rho_all is None or abs(rho_all) < 0.25:
            continue
        signs = []
        for g, rs in big.items():
            sub = [(r[a], r[b]) for r in rs if a in r and b in r]
            if len(sub) < 60:
                continue
            rho = ws.spearman([x for x, _ in sub], [y for _, y in sub])
            if rho is not None and abs(rho) > 0.25:
                signs.append((g, rho))
        if len(signs) >= 2 and all(
                (rho > 0) != (rho_all > 0) for _g, rho in signs):
            findings.append(Finding(
                "simpson", f"{a} ~ {b}",
                f"corpus-wide rho {rho_all:+.2f}, but reverses in every "
                f"subgroup of {group_field} ({', '.join(f'{g:g}:{r:+.2f}' for g, r in signs[:4])}) "
                f"— the aggregate sign is an artefact of the mix",
                abs(rho_all) * 100,
                {"rho_all": rho_all, "subgroups": signs, "a": a, "b": b}))
    findings.sort(key=lambda f: -f.z)
    return Report("simpson", findings,
                  (f"{control_pair[0]} ~ {control_pair[1]}" in
                   {f.subject for f in findings}) if control_pair
                  else bool(findings),
                  " ~ ".join(control_pair) if control_pair
                  else "any relation reversing inside subgroups")


# ═══════════════════════════════════════════════════════════════════════════
# From findings to hypotheses.
#
# A finding says "X is anomalous". That is not yet a question — it is a
# surprise. A HYPOTHESIS says "X is anomalous BECAUSE Y", and carries the test
# that would kill it plus what that test costs. Generating questions is only
# safe when each one arrives with its own way of dying, and cheaply.
#
# Nothing here invents a mechanism. Each rule maps a finding SHAPE to the
# small set of causes that shape can have, which is a fact about statistics,
# not about the subject matter.
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Hypothesis:
    claim: str                    # what is being asserted
    because: str                  # the proposed mechanism
    falsifier: str                # the observation that would kill it
    cost: str                     # free | cheap | expensive
    surprise: float               # how much it is NOT explained by others
    source: Finding = None        # noqa: RUF013 - the finding it came from

    def __str__(self) -> str:
        return (f"[{self.cost:9}] {self.claim}\n"
                f"             because: {self.because}\n"
                f"             killed by: {self.falsifier}")


#: family -> (mechanism, falsifying test, what the test costs)
_MECHANISMS = {
    "pileup": ("the column is capped, clamped, or produced by an estimator "
               "that saturates — the pile is a bound, not a measurement",
               "find the declared maximum in the producing code; if the pile "
               "sits on it, every piled value is a lower bound and must be "
               "marked as one", "free"),
    "censored": ("values recovered only at the top rung of a declared ladder "
                 "are right-censored lower bounds",
                 "extend the ladder by one rung and re-run those hosts; if the "
                 "floor moves, every stored value was a bound", "expensive"),
    "ratio": ("either one of the two fields saturated on this row, or the row "
              "belongs to a different population from the corpus",
              "run group_signature over the violating rows; a shared field "
              "names the population, its absence leaves saturation", "free"),
    "absent": ("the schema changed at that source; rows before it could not "
               "carry the field rather than declining to",
               "compare outcomes either side of the boundary — if they differ, "
               "every aggregate spanning it is a mixture", "free"),
    "redundant": ("one column is computed from the other, so the corpus stores "
                  "one fact in two places",
                  "recover the formula on a sample; if it holds exactly, delete "
                  "a column or bind the pair with a test before they drift",
                  "free"),
    "hidden": ("a latent variable drives both columns in a shape no monotone "
               "statistic reports",
               "condition on each candidate grouping field in turn; the one "
               "that collapses the mutual information is the latent",
               "cheap"),
    "regime": ("something in the producing pipeline changed at that point — a "
               "version, a parameter, a machine",
               "read the commit log at that source's date; a matching change "
               "confirms it, its absence makes this interesting", "free"),
    "order": ("the value depends on when the row was produced: warm caches, "
              "drifting hardware, or an accumulating parameter",
              "re-derive a sample in shuffled order; if the statistic moves, "
              "the ordering was in the measurement", "cheap"),
    "modal": ("the column mixes two or more populations that were never "
              "separated",
              "search for a field that partitions the peaks; if one does, the "
              "column should never be summarised whole", "cheap"),
    "benford": ("the column was generated, rounded, capped, or drawn from a "
                "narrower band than its range suggests — real measurements "
                "spanning orders of magnitude obey the leading-digit law",
                "check the producing code for a formula, a round(), or a clamp; "
                "a derived column has no obligation to obey Benford and should "
                "be exempted rather than reported", "free"),
    "rounding": ("something upstream rounded or hand-entered the column, so its "
                 "precision is smaller than its stored digits imply",
                 "read the producing code; if a round() or a fixed constant is "
                 "there, every downstream tolerance tighter than that rounding "
                 "is measuring the rounding", "free"),
    "entity": ("this row was produced under conditions the corpus did not "
               "share — a different instrument, a different epoch, or a "
               "genuinely different object",
               "hold each of its odd fields fixed in turn and ask whether the "
               "rest normalise; the field that explains the others is the "
               "condition", "cheap"),
    "conditional": ("a relation real inside one stratum and absent elsewhere — "
                    "the corpus-wide zero is the strata cancelling",
                    "re-derive the relation within each stratum separately; if "
                    "it survives only where claimed, the stratum is the "
                    "mechanism and the pooled statistic was never meaningful",
                    "cheap"),
    "impossible": ("either a constraint nobody wrote down, or a branch of the "
                   "producing code that cannot be reached",
                   "read the producing code for the two values; a guard "
                   "confirms the constraint, its absence means dead code or a "
                   "sampling gap", "free"),
    "discrete": ("the column is a category stored as a float, so every mean "
                 "and correlation over it is a category average",
                 "read the producing code for the value set; if it is a fixed "
                 "menu, retype the column", "free"),
    "duplicate": ("one measurement was filed more than once — concurrent "
                  "producers writing beside each other rather than over",
                  "compare the input hashes; identical inputs mean one "
                  "observation, and one of the rows must declare it supersedes "
                  "the other", "free"),
    "simpson": ("a confounder correlated with both the grouping and the "
                "outcome — the aggregate sign is an artefact of the mix",
                "name the confounder and re-derive within strata; if the sign "
                "holds inside every stratum the aggregate was backwards",
                "cheap"),
    "signature": ("the outlier group shares a cause that the corpus does not",
                  "hold the shared field fixed and re-run the detector; if the "
                  "anomaly dissolves, the field was the mechanism", "cheap"),
}



def _cluster_key(f: Finding) -> tuple:
    """The mechanism a finding belongs to. ONE definition, used everywhere.

    `hypothesise` and `rank_by_surprise` each grew their own version of this and
    they disagreed: 179 clusters against 9, on the same findings. Two functions
    computing the same fact is the defect this whole module hunts, so the
    clustering has exactly one home now.

    The key is family-specific because a mechanism is: a ratio anomaly is about
    a PAIR, a schema gap is about the BOUNDARY it starts at, a pile is about the
    COLUMN. Clustering everything by subject splits one cause into many; by
    family alone it merges many causes into one.
    """
    ev = f.evidence
    if f.family in ("ratio", "redundant", "hidden", "simpson"):
        return (f.family, tuple(sorted(str(ev[k]) for k in
                                       ("field_a", "field_b", "a", "b") if k in ev)))
    if f.family == "absent":
        # every field appearing at the same source is ONE schema change
        m = re.search(r"(?:first appears at|stops after) (\S+)", f.detail)
        return (f.family, m.group(1) if m else f.subject)
    if f.family == "regime":
        return (f.family, str(ev.get("at", f.subject)))
    if f.family == "duplicate":
        return (f.family, tuple(ev.get("sources", (f.subject,))))
    return (f.family, f.subject)


def hypothesise(findings: Sequence[Finding]) -> list[Hypothesis]:
    """Turn findings into falsifiable claims, ranked by surprise.

    Surprise is deliberately not the deviation. A thousand rows breaking the
    same relation for the same reason is ONE fact, and reporting it a thousand
    times by z-score buries the single row that breaks a different one.
    """
    # Cluster by (family, the fields involved) — one mechanism per cluster.
    clusters: dict[tuple, list[Finding]] = {}
    for f in findings:
        clusters.setdefault(_cluster_key(f), []).append(f)

    out: list[Hypothesis] = []
    for (family, what), group in clusters.items():
        mech = _MECHANISMS.get(family)
        if mech is None:
            continue
        because, falsifier, cost = mech
        head = max(group, key=lambda f: f.z)
        # A cluster of one is a singleton nobody has explained; a cluster of
        # many is one mechanism repeating. Rarity is the surprise.
        surprise = 1.0 / len(group)
        label = " ~ ".join(what) if isinstance(what, tuple) else str(what)
        claim = (f"{head.subject}: {head.detail}" if len(group) == 1 else
                 f"{len(group)} findings share one {family} mechanism at "
                 f"{label} — strongest: {head.subject}: {head.detail}")
        out.append(Hypothesis(claim, because, falsifier, cost,
                              surprise, head))
    out.sort(key=lambda h: (-h.surprise, {"free": 0, "cheap": 1,
                                          "expensive": 2}[h.cost]))
    return out


def rank_by_surprise(findings: Sequence[Finding]) -> list[Finding]:
    """Collapse repeated mechanisms; keep the strongest of each, rarest first.

    2,627 ratio findings dominated by one saturating estimator is a firehose.
    The same list collapsed to one row per mechanism is a shortlist.
    """
    clusters: dict[tuple, list[Finding]] = {}
    for f in findings:
        clusters.setdefault(_cluster_key(f), []).append(f)
    heads = []
    for group in clusters.values():
        head = max(group, key=lambda f: f.z)
        head.evidence = dict(head.evidence, cluster_size=len(group))
        heads.append(head)
    heads.sort(key=lambda f: (f.evidence.get("cluster_size", 1), -f.z))
    return heads


def run_all(rows: Sequence[dict], controls: dict | None = None) -> dict[str, Report]:
    """Every family that can run on this corpus, each with its control.

    A family whose control is not supplied runs in *unguarded* mode: it reports
    whatever it finds and says so. Unguarded output is a lead, never a result —
    the whole point of a control is that silence means something.
    """
    c = controls or {}
    reports: dict[str, Report] = {}

    def add(name, fn, *args, **kw):
        # The control is the SELF-TEST, decided before the corpus is touched and
        # independent of what it happens to contain. The old rule was
        # `bool(findings)` — "did I find anything?" — which held for 11 of 13
        # families, made `trusted_only` a no-op, and inverted: a family that ran
        # cleanly and found nothing was stamped BLIND. Trusted-and-quiet is now
        # expressible, and it is a result.
        passed, why = self_test(name)
        try:
            rep = fn(*args, **kw)
        except Exception as exc:                            # noqa: BLE001
            reports[name] = Report(name, [], False,
                                   f"CRASHED on the corpus: "
                                   f"{type(exc).__name__}: {exc}")
            return
        rep.saw_control = passed
        rep.control = why
        reports[name] = rep

    add("ratio", ratio_violations, rows, c.get("ratio", ""))
    add("pileup", boundary_pileups, rows, c.get("pileup", ""))
    add("benford", digit_law_violations, rows, c.get("benford", ""))
    add("rounding", rounding_tells, rows, c.get("rounding", ""))
    add("discrete", secretly_discrete, rows, c.get("discrete", ""))
    add("redundant", redundant_fields, rows, c.get("redundant", ()))
    add("hidden", hidden_dependence, rows, c.get("hidden", ()))
    add("regime", regime_changes, rows, "_src", c.get("regime", ""))
    add("order", order_dependence, rows, "_src", c.get("order", ""))
    add("modal", multimodal_fields, rows, c.get("modal", ""))
    add("duplicate", duplicate_rows, rows, c.get("duplicate", ""))
    add("absent", absent_fields, rows, "_src", c.get("absent", ""))
    add("entity", entity_outliers, rows, c.get("entity", ""))
    add("conditional", conditional_relations, rows, c.get("conditional", ()))
    add("impossible", impossible_combinations, rows, c.get("impossible", ()))
    if "simpson_group" in c:
        add("simpson", subgroup_reversals, rows, c["simpson_group"],
            c.get("simpson", ()))
    else:
        # Discover a grouper rather than requiring one: any column taking 2-8
        # values on enough rows is a candidate label. Requiring the caller to
        # name one meant this family almost never ran.
        cands = [k for k in _fields(rows)
                 if 2 <= len({r[k] for r in rows if k in r}) <= 8
                 and sum(1 for r in rows if k in r) >= 400]
        if cands:
            add("simpson", subgroup_reversals, rows, cands[0], c.get("simpson", ()))
    if "censored_ladder" in c:
        add("censored", censored_values, rows, c["censored_ladder"],
            c.get("censored", ""))
    return reports


def all_findings(reports: dict[str, Report], trusted_only: bool = True
                 ) -> list[Finding]:
    """Findings from every report, optionally only those that proved they see."""
    out = []
    for rep in reports.values():
        if trusted_only and not rep.saw_control:
            continue
        out.extend(rep.findings)
    return out


def explain_away(reports: dict[str, Report]) -> tuple[list[Finding], list[str]]:
    """Suppress findings that another finding already accounts for.

    Surprise is not deviation, and it is not rarity either — it is what is left
    once the corpus has explained itself. A column with ONE distinct value makes
    every ratio involving it a rescaling of its partner, so those "anomalies"
    are the partner's, restated. A column piled on its own extreme explains
    every ratio that saturates against it.

    Without this the loudest findings are the most structural ones, and the
    single row that breaks a relation nothing else touches is on page nine.
    """
    notes: list[str] = []
    constant: set[str] = set()
    piled: set[str] = set()

    # ONLY trusted reports may explain anything away. The first version read
    # these two families' findings with no check, so a detector whose silence
    # "proves nothing" was authorised to delete a verified finding from a
    # family that had passed its control. Confirmed by the adversarial review:
    # ratio's planted anomaly vanished on the word of a BLIND discrete report.
    disc = reports.get("discrete")
    pile = reports.get("pileup")
    if disc is not None and disc.saw_control:
        for f in disc.findings:
            if f.evidence.get("distinct") == 1:
                constant.add(f.subject)
    if pile is not None and pile.saw_control:
        for f in pile.findings:
            if f.evidence.get("share", 0) > 0.20:
                piled.add(f.subject)
    if constant:
        notes.append(f"{len(constant)} constant column(s) — every ratio against "
                     f"them is their partner restated: {', '.join(sorted(constant))}")
    if piled:
        notes.append(f"{len(piled)} column(s) piled >20% on an extreme — ratios "
                     f"that saturate against them are that pile, not a new fact")

    kept: list[Finding] = []
    for rep in reports.values():
        if not rep.saw_control:
            continue
        for f in rep.findings:
            ev = f.evidence
            pair = {str(ev[k]) for k in ("field_a", "field_b", "a", "b") if k in ev}
            if f.family == "ratio" and pair & constant:
                continue                      # a rescaling, not an anomaly
            if f.family == "ratio" and pair & piled:
                continue                      # the pile, seen from the side
            if f.family in ("rounding", "benford") and f.subject in constant:
                continue                      # a constant has one digit
            kept.append(f)
    return kept, notes


# ═══════════════════════════════════════════════════════════════════════════
# SELF-TESTS — what `saw_control` should have meant all along.
#
# The first design let a family default to ``saw_control = bool(findings)``:
# "did I find anything?" On the real corpus that held for 11 of 13 families, so
# `trusted_only` filtered exactly the empty lists — zero bits. Worse, it
# INVERTED: three families ran cleanly, reported a true negative, and were
# stamped BLIND on the page. The one distinction the mechanism exists to make —
# blind versus genuinely quiet — it got backwards.
#
# A control must be independent of what the corpus happens to contain. So each
# family now carries a planted POSITIVE it must find and a planted NEGATIVE it
# must stay silent on, run before the corpus is touched. A family that passes
# both and then finds nothing is TRUSTED AND QUIET, which is a result.
# ═══════════════════════════════════════════════════════════════════════════

def _synth(n: int, **cols) -> list[dict]:
    out = []
    for i in range(n):
        r = {"_id": f"s{i}", "_src": f"{i // max(1, n // 4):02d}.json"}
        for k, fn in cols.items():
            r[k] = float(fn(i))
        out.append(r)
    return out


@functools.lru_cache(maxsize=1)
def _selftests() -> dict[str, tuple]:
    """``family -> (fn, positive_rows, must_find, negative_rows)``.

    The negative matters as much as the positive: a detector that fires on
    clean data is not a detector, it is a random number generator with prose.
    """
    # Deterministic but genuinely unordered: hash the index rather than stepping
    # a recurrence. An LCG sampled at sequential i carries real serial structure
    # (runs z = 18.8, against 1.1 for true randomness), so it is a fine fixture
    # everywhere EXCEPT as the clean negative for `order`, where it would
    # correctly fire and be misread as the detector over-firing.
    def lcg(i, s=7):
        h = hashlib.blake2b(f"{s}:{i}".encode(), digest_size=8).digest()
        return int.from_bytes(h, "big") / (1 << 64)

    pos_ratio = _synth(400, a=lambda i: 1 + lcg(i) / 10, b=lambda i: (1 + lcg(i) / 10) * 2)
    pos_ratio[123]["b"] *= 2000
    pos_ratio[123]["_id"] = "HIT"
    neg_ratio = _synth(400, a=lambda i: 1 + lcg(i) / 10, b=lambda i: (1 + lcg(i) / 10) * 2)

    return {
        "ratio": (lambda rs: ratio_violations(rs, "HIT"), pos_ratio, "HIT", neg_ratio),
        "pileup": (lambda rs: boundary_pileups(rs, "v"),
                   _synth(400, v=lambda i: 1.0 if i < 300 else 1 + i / 100), "v",
                   _synth(400, v=lambda i: 1 + lcg(i))),
        "discrete": (lambda rs: secretly_discrete(rs, "v"),
                     _synth(400, v=lambda i: i % 3), "v",
                     _synth(400, v=lambda i: 1 + lcg(i))),
        "redundant": (lambda rs: redundant_fields(rs, ("a", "b")),
                      _synth(400, a=lambda i: i + 1, b=lambda i: (i + 1) * 2.5),
                      "a ~ b",
                      _synth(400, a=lambda i: lcg(i), b=lambda i: lcg(i, 99))),
        "hidden": (lambda rs: hidden_dependence(rs, ("x", "y")),
                   _synth(600, x=lambda i: i - 300, y=lambda i: abs(i - 300)),
                   "x ~ y",
                   _synth(600, x=lambda i: lcg(i), y=lambda i: lcg(i, 31))),
        "regime": (lambda rs: regime_changes(rs, "_src", "v"),
                   _synth(400, v=lambda i: 1 + lcg(i) / 50 + (0 if i < 200 else 50)),
                   "v",
                   _synth(400, v=lambda i: 1 + lcg(i) / 50)),
        "order": (lambda rs: order_dependence(rs, "_src", "v"),
                  _synth(400, v=lambda i: float(i)), "v",
                  _synth(400, v=lambda i: lcg(i))),
        "modal": (lambda rs: multimodal_fields(rs, "v"),
                  _synth(600, v=lambda i: (i % 3) * 100 + (i % 5) * 0.1), "v",
                  _synth(600, v=lambda i: lcg(i))),
        "duplicate": (lambda rs: duplicate_rows(rs, "DUP"),
                      [{"_id": "DUP", "_src": "a.json", "p": 1.0, "q": 2.0,
                        "r": 3.0, "s": 4.0, "t": 5.0},
                       {"_id": "DUP", "_src": "b.json", "p": 1.0, "q": 2.0,
                        "r": 3.0, "s": 4.0, "t": 5.0}], "DUP",
                      [{"_id": "A", "_src": "a.json", "p": 1.0, "q": 2.0,
                        "r": 3.0, "s": 4.0, "t": 5.0},
                       {"_id": "B", "_src": "b.json", "p": 9.0, "q": 2.0,
                        "r": 3.0, "s": 4.0, "t": 5.0}]),
        "absent": (lambda rs: absent_fields(rs, "_src", "late"),
                   _synth(200, x=lambda i: 1.0) +
                   [{"_id": f"L{i}", "_src": "99.json", "x": 1.0, "late": 2.0}
                    for i in range(50)], "late",
                   _synth(200, x=lambda i: 1.0)),
        "censored": (lambda rs: censored_values(rs, {"d": (0.002, 0.004, 0.010)}, "d"),
                     [{"_id": f"c{i}", "_src": "a.json",
                       "d": 0.010 if i < 20 else 0.002} for i in range(200)], "d",
                     [{"_id": f"c{i}", "_src": "a.json", "d": 0.002}
                      for i in range(200)]),
        "benford": (lambda rs: digit_law_violations(rs, "v"),
                    _synth(400, v=lambda i: 10 ** (1 + (i % 4)) * 1.0), "v",
                    _synth(400, v=lambda i: 10 ** (4 * lcg(i)))),
        "entity": (lambda rs: entity_outliers(rs, "ODD"),
                   ([{"_id": f"n{i}", "_src": "a.json",
                      **{f"f{j}": 1.0 + lcg(i * 13 + j) / 20 for j in range(9)}}
                     for i in range(400)] +
                    [{"_id": "ODD", "_src": "a.json",
                      **{f"f{j}": 9.0 for j in range(9)}}]), "ODD",
                   [{"_id": f"n{i}", "_src": "a.json",
                     **{f"f{j}": 1.0 + lcg(i * 13 + j) / 20 for j in range(9)}}
                    for i in range(400)]),
        # SIX strata, strong in exactly one. With two the relation is visible
        # corpus-wide (rho ~ 0.5) and the detector correctly declines it — the
        # family hunts relations the pooled statistic CANNOT see, so the fixture
        # has to dilute the signal below the pooled threshold.
        "conditional": (lambda rs: conditional_relations(rs, ("x", "y", "g")),
                        [{"_id": f"c{i}", "_src": "a.json",
                          "g": float(i % 6),
                          "x": lcg(i),
                          "y": (lcg(i) if i % 6 == 0 else lcg(i, 77))}
                         for i in range(1800)], "x ~ y | g",
                        [{"_id": f"c{i}", "_src": "a.json", "g": float(i % 6),
                          "x": lcg(i), "y": lcg(i, 77)} for i in range(1800)]),
        "impossible": (lambda rs: impossible_combinations(rs, ("a", "b")),
                       [{"_id": f"i{i}", "_src": "a.json",
                         "a": float(i % 3),
                         "b": float(0 if i % 3 == 0 else 1)}
                        for i in range(600)], "a=0 & b=1",
                       [{"_id": f"i{i}", "_src": "a.json",
                         "a": float(i % 3), "b": float(i % 2)}
                        for i in range(600)]),
        # Simpson: strongly POSITIVE corpus-wide, strongly NEGATIVE in every
        # stratum. The classic shape, planted.
        "simpson": (lambda rs: subgroup_reversals(rs, "g", ("x", "y")),
                    ([{"_id": f"s{i}", "_src": "a.json", "g": 0.0,
                       "x": 1.0 + i / 200, "y": 5.0 - i / 300} for i in range(300)] +
                     [{"_id": f"t{i}", "_src": "a.json", "g": 1.0,
                       "x": 4.0 + i / 200, "y": 9.0 - i / 300} for i in range(300)]),
                    "x ~ y",
                    [{"_id": f"u{i}", "_src": "a.json", "g": float(i % 2),
                      "x": lcg(i), "y": lcg(i, 55)} for i in range(600)]),
        "rounding": (lambda rs: rounding_tells(rs, "v"),
                     _synth(400, v=lambda i: round(1 + lcg(i) * 20, 1)), "v",
                     _synth(400, v=lambda i: 1 + lcg(i) * 20)),
    }


@functools.lru_cache(maxsize=None)
def self_test(family: str) -> tuple[bool, str]:
    """Can this family see, and can it stay quiet? ``(passed, why)``.

    Independent of the corpus under study, which is the entire point — a
    control drawn from the data being examined tells you about the data, not
    about the detector.
    """
    spec = _selftests().get(family)
    if spec is None:
        return False, "no self-test defined — this family cannot be trusted"
    fn, pos, must_find, neg = spec
    try:
        found = {f.subject for f in fn(pos).findings}
        if must_find not in found:
            return False, (f"failed its POSITIVE: planted {must_find!r} and did "
                           f"not find it (found {sorted(found)[:3]})")
        n_neg = len(fn(neg).findings)
        if n_neg:
            return False, (f"failed its NEGATIVE: fired {n_neg} time(s) on clean "
                           f"data — it reports noise as signal")
    except Exception as exc:                                  # noqa: BLE001
        return False, f"self-test raised {type(exc).__name__}: {exc}"
    return True, "found its planted positive and stayed silent on clean data"


# ═══════════════════════════════════════════════════════════════════════════
# Families that need the wide aperture. Everything above asks about a COLUMN
# or a PAIR; these ask about an ENTITY, a CONDITION, and an ABSENCE — three
# questions no per-column statistic can pose.
# ═══════════════════════════════════════════════════════════════════════════

def entity_outliers(rows: Sequence[dict], control_id: str = "",
                    min_fields: int = 6, z_each: float = 2.5) -> Report:
    """Rows that are MILDLY odd on many axes at once.

    Every family above hunts a single large deviation. This hunts the opposite
    shape: nothing individually alarming, jointly improbable. A star 2.5 MADs
    out on nine unrelated measurements is not nine coincidences, and no
    per-column threshold will ever surface it — each axis says "unremarkable"
    and the row walks through.

    Scored as the SHARE of a row's populated fields that are mildly deviant, so
    a sparse row is not rewarded for having little to be odd about, then the
    share is itself judged against the corpus of shares.
    """
    fields = _fields(rows)
    scales: dict[str, tuple[float, float]] = {}
    for k in fields:
        col = _column(rows, k)
        m, sd = ws.median(col), ws.mad(col)
        if m is None:
            continue
        if sd is None:
            # MAD is 0 whenever a majority share one value — [1.0]*300 + [99.0]
            # has an obvious outlier and no scale. Declaring the column
            # unscalable threw that row away. If anything differs from the
            # median at all, "differs" IS the deviation.
            if len({v for v in col}) > 1:
                scales[k] = (m, None)
            continue
        scales[k] = (m, sd)
    if len(scales) < min_fields:
        return Report("entity", [], False, "too few scalable columns")

    scored = []
    for r in rows:
        have = [k for k in scales if k in r]
        if len(have) < min_fields:
            continue
        odd = [k for k in have
               if (scales[k][1] is None and r[k] != scales[k][0])
               or (scales[k][1] is not None
                   and abs(r[k] - scales[k][0]) / scales[k][1] > z_each)]
        scored.append((len(odd) / len(have), r, odd, len(have)))
    if len(scored) < 50:
        return Report("entity", [], False, "too few rows carry enough fields")

    shares = [s for s, _r, _o, _n in scored]
    med, sd = ws.median(shares), ws.mad(shares)
    findings = []
    for share, r, odd, n in scored:
        if sd is None:
            # Every row scores the SAME share — usually zero, because the corpus
            # is clean. There is no scale, so there is no z, and the first
            # version `break`-ed and discarded the outlier it exists to find.
            # A row departing from a constant departs unboundedly. (Third time
            # today: group_signature and ratio had the identical defect.)
            z = float("inf") if share > (med or 0) else 0.0
        else:
            z = (share - med) / sd
        if z > 8.0 and len(odd) >= min_fields:
            findings.append(Finding(
                "entity", r["_id"],
                f"{len(odd)} of {n} populated fields sit past {z_each} MADs — "
                f"{share:.0%} of what was measured about it is unusual, against "
                f"a corpus median of {med:.0%}. Nothing here is individually "
                f"alarming; jointly it is. Fields: {', '.join(sorted(odd)[:6])}"
                + ("…" if len(odd) > 6 else ""),
                z, {"n_odd": len(odd), "n_fields": n, "share": share,
                    "fields": sorted(odd), "src": r["_src"]}))
    findings.sort(key=lambda f: -f.z)
    return Report("entity", findings,
                  any(f.subject == control_id for f in findings)
                  if control_id else bool(findings),
                  control_id or "any row jointly odd across many fields")


def conditional_relations(rows: Sequence[dict], control_pair: tuple = (),
                          max_groupers: int = 8) -> Report:
    """Relations that hold INSIDE one subgroup and nowhere else.

    A corpus-wide correlation of zero can hide a strong relation confined to a
    stratum — the reverse of Simpson's paradox and far more common. Groupers are
    discovered, not supplied: any column taking 2-8 distinct values is a
    candidate label, which is what `secretly_discrete` was already telling us
    about but nothing acted on.
    """
    fields = _fields(rows)
    groupers = []
    for k in fields:
        vals = {r[k] for r in rows if k in r}
        if 2 <= len(vals) <= 8 and len([r for r in rows if k in r]) >= 200:
            groupers.append(k)
    groupers = groupers[:max_groupers]
    if not groupers:
        return Report("conditional", [], False, "no discrete grouping columns")

    findings = []
    for g in groupers:
        strata: dict[float, list[dict]] = {}
        for r in rows:
            if g in r:
                strata.setdefault(r[g], []).append(r)
        big = {v: rs for v, rs in strata.items() if len(rs) >= 120}
        if len(big) < 2:
            continue
        for a, b in itertools.combinations([f for f in fields if f != g], 2):
            whole = [(r[a], r[b]) for r in rows if a in r and b in r]
            if len(whole) < MIN_PAIRS:
                continue
            rho_all = ws.spearman([x for x, _ in whole], [y for _, y in whole])
            if rho_all is None or abs(rho_all) > 0.20:
                continue                      # visible corpus-wide; not hidden
            per = {}
            for v, rs in big.items():
                sub = [(r[a], r[b]) for r in rs if a in r and b in r]
                if len(sub) < 120:
                    continue
                rho = ws.spearman([x for x, _ in sub], [y for _, y in sub])
                if rho is not None:
                    per[v] = rho
            if len(per) < 2:
                continue
            strong = {v: rho for v, rho in per.items() if abs(rho) > 0.55}
            weak = {v: rho for v, rho in per.items() if abs(rho) < 0.20}
            if len(strong) == 1 and len(weak) == len(per) - 1:
                v, rho = next(iter(strong.items()))
                findings.append(Finding(
                    "conditional", f"{a} ~ {b} | {g}",
                    f"invisible corpus-wide (rho {rho_all:+.2f}) but rho "
                    f"{rho:+.2f} inside {g}={v:g} alone, and under 0.20 in every "
                    f"other stratum — a relation that exists only under a "
                    f"condition nobody separated", abs(rho) * 100,
                    {"a": a, "b": b, "grouper": g, "value": v,
                     "rho_in": rho, "rho_all": rho_all, "per_stratum": per}))
    findings.sort(key=lambda f: -f.z)
    return Report("conditional", findings,
                  (f"{control_pair[0]} ~ {control_pair[1]} | {control_pair[2]}"
                   in {f.subject for f in findings}) if len(control_pair) == 3
                  else bool(findings),
                  " ~ ".join(control_pair) if control_pair
                  else "any relation confined to one stratum")


def impossible_combinations(rows: Sequence[dict], control_pair: tuple = ()) -> Report:
    """Value pairs that NEVER co-occur though both are common. Negative space.

    ``absent_fields`` finds a column that is missing. This finds a combination
    that is missing — a hole in a grid whose rows and columns are both well
    populated. Those holes are either a constraint nobody wrote down, or a
    branch of the producing code that cannot be reached.
    """
    fields = [k for k in _fields(rows)
              if 2 <= len({r[k] for r in rows if k in r}) <= 12]
    findings = []
    for a, b in itertools.combinations(fields, 2):
        both = [r for r in rows if a in r and b in r]
        if len(both) < MIN_PAIRS:
            continue
        va = collections.Counter(r[a] for r in both)
        vb = collections.Counter(r[b] for r in both)
        seen = {(r[a], r[b]) for r in both}
        n = len(both)
        for x, cx in va.items():
            for y, cy in vb.items():
                if (x, y) in seen:
                    continue
                # expected count if the two were independent
                exp = cx * cy / n
                if exp >= 12:
                    findings.append(Finding(
                        "impossible", f"{a}={x:g} & {b}={y:g}",
                        f"never co-occur in {n} rows, though {a}={x:g} appears "
                        f"{cx}x and {b}={y:g} appears {cy}x — {exp:.0f} joint "
                        f"rows expected if independent. Either an unwritten "
                        f"constraint or an unreachable branch.", exp,
                        {"a": a, "b": b, "va": x, "vb": y, "expected": exp}))
    findings.sort(key=lambda f: -f.z)
    # A finding's subject is a VALUE combination ("a=0 & b=1"); a control names
    # the COLUMN pair. Match on the evidence, not on the rendered string.
    return Report("impossible", findings,
                  any({f.evidence.get("a"), f.evidence.get("b")} == set(control_pair)
                      for f in findings) if control_pair
                  else bool(findings),
                  " & ".join(str(c) for c in control_pair) if control_pair
                  else "any never-co-occurring pair of common values")
