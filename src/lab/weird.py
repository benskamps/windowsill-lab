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
        head = (f"[{self.family}] control OK ({self.control}) — "
                f"{len(self.findings)} finding(s)")
        return "\n".join([head] + ["  " + str(f) for f in self.findings])


# ── loading: any corpus of dicts, flattened ──────────────────────────────────

def flatten(obj: dict, prefix: str = "") -> dict:
    """Numeric leaves only, dotted keys. Booleans are not numbers."""
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


def _fields(rows: Sequence[dict], min_share: float = 0.05) -> list[str]:
    counts: dict[str, int] = {}
    for r in rows:
        for k, v in r.items():
            if not k.startswith("_") and isinstance(v, float) and v > 0:
                counts[k] = counts.get(k, 0) + 1
    floor = len(rows) * min_share
    return sorted(k for k, n in counts.items() if n >= floor)


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
        if mad <= 0 or mad > MAX_RELATION_MAD:
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
