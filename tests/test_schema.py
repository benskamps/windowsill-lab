"""The pot.json contract — validate snapshots against the shared JSON Schema.

A tiny dependency-free validator (the subset the schema uses) so the producer
(this repo) and the consumer (the windowsill page) can't silently drift. The
page mirrors the same schema + a sibling validator in JS.
"""
import json
import re
from pathlib import Path

from lab.publish import build_snapshot, parse_milestones

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schema" / "pot.schema.json").read_text()
)

_IS_TYPE = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _resolve(ref, root):
    node = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def validate(inst, schema, root=None, path="$"):
    root = root or schema
    if "$ref" in schema:
        return validate(inst, _resolve(schema["$ref"], root), root, path)
    errs = []
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        if not any(_IS_TYPE[x](inst) for x in types):
            return [f"{path}: expected {t}, got {type(inst).__name__}"]
    if "enum" in schema and inst not in schema["enum"]:
        errs.append(f"{path}: {inst!r} not in {schema['enum']}")
    if isinstance(inst, str) and "pattern" in schema and not re.search(schema["pattern"], inst):
        errs.append(f"{path}: {inst!r} does not match /{schema['pattern']}/")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append(f"{path}: {inst} < minimum {schema['minimum']}")
        if "maximum" in schema and inst > schema["maximum"]:
            errs.append(f"{path}: {inst} > maximum {schema['maximum']}")
    if isinstance(inst, dict):
        for req in schema.get("required", []):
            if req not in inst:
                errs.append(f"{path}: missing required {req!r}")
        props = schema.get("properties", {})
        for k, v in inst.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
    if isinstance(inst, list) and "items" in schema:
        for i, item in enumerate(inst):
            errs += validate(item, schema["items"], root, f"{path}[{i}]")
    return errs


SAMPLE = """
- [x] **M01** — 2D Ising. (done — T_c 2.27 ✓)
- [>] **A02** — Recover a variable star. {venue=AAVSO; url=https://www.aavso.org; doi=10.5281/zenodo.1; progress=0.4}
- [ ] **C01** — Calibrate the number stack.
"""


def test_real_snapshot_conforms():
    snap = build_snapshot(parse_milestones(SAMPLE), "2026-06-08T00:00:00+00:00", 3, 47.0)
    assert validate(snap, SCHEMA) == []


def test_bad_status_is_rejected():
    bad = {"milestones": [{"id": "M01", "status": "sideways"}]}
    assert validate(bad, SCHEMA)


def test_non_http_url_is_rejected():
    # Mirrors the windowsill page's link guard: only http(s) records become links.
    bad = {"milestones": [{"id": "M01", "status": "verified", "url": "javascript:alert(1)"}]}
    assert validate(bad, SCHEMA)


def test_schema_is_self_consistent():
    ms = SCHEMA["definitions"]["milestone"]
    assert set(ms["required"]) <= set(ms["properties"])


# ── Permanence refactor: the reports[] array contract ───────────────────────
# pot.json gains a newest-first reports[] list so the page can deep-link every
# run (a node on the seedling stem) including honest nulls (folded grey leaves).
# All fields optional + additive, so a v2 pot with no reports key still validates.

VALID_REPORT = {
    "date": "2026-06-15",
    "milestone": "M02",
    "experiment": "M02-finite-size-scaling",
    "headline": "χ_max ∝ L^1.74",
    "peak_t": 2.30,
    "wall_s": 120.0,
    "url": "https://htmlpreview.github.io/?https://example/reports/2026-06-15-m02.html",
    "code_sha": "abc1234",
    "status": "verified",
}


def test_snapshot_with_reports_array_conforms():
    null_run = dict(VALID_REPORT, milestone="M03", status="null")
    snap = build_snapshot(
        parse_milestones(SAMPLE), "2026-06-08T00:00:00+00:00", 3, 47.0,
        reports=[VALID_REPORT, null_run],
    )
    assert validate(snap, SCHEMA) == []


def test_report_bad_status_is_rejected():
    bad = {"reports": [dict(VALID_REPORT, status="sideways")]}
    assert validate(bad, SCHEMA)


def test_report_non_http_url_is_rejected():
    bad = {"reports": [dict(VALID_REPORT, url="javascript:alert(1)")]}
    assert validate(bad, SCHEMA)


def test_v2_pot_without_reports_still_validates():
    # A snapshot with NO reports key (legacy v2 shape) degrades gracefully.
    snap = build_snapshot(parse_milestones(SAMPLE), "x", 1, 47.0)
    assert "reports" not in snap or snap["reports"] == []
    assert validate(snap, SCHEMA) == []


def test_report_definition_is_self_consistent():
    rep = SCHEMA["definitions"]["report"]
    assert set(rep.get("required", [])) <= set(rep["properties"])


def test_report_status_enum_allows_unscored():
    """FIX 1: _run_record's honest fallback emits status="unscored"; the schema's
    report.status enum must accept it, or a truthful snapshot would fail to
    validate. A run claiming no verification it didn't perform is the whole point.
    """
    enum = SCHEMA["definitions"]["report"]["properties"]["status"]["enum"]
    assert "unscored" in enum
    ok = dict(VALID_REPORT, status="unscored")
    assert validate({"reports": [ok]}, SCHEMA) == []
