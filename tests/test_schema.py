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
    (Path(__file__).resolve().parents[1] / "schema" / "pot.schema.json")
    .read_text(encoding="utf-8")
)
PHYSICS_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schema" / "physics.schema.json")
    .read_text(encoding="utf-8")
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
        # `additionalProperties` as a SCHEMA (not a bool) is how this contract
        # describes a MAP whose keys are data — `turns.last_by_machine` and, since
        # 2026-09-04, `tests`. Until it was honoured here the validator walked
        # `properties` only, so every row of both maps went entirely unchecked:
        # `tests` could have shipped a machine row with `status: "green"` or a
        # `passed: -1` and this file would have called the snapshot conforming.
        extra = schema.get("additionalProperties")
        for k, v in inst.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            elif isinstance(extra, dict):
                errs += validate(v, extra, root, f"{path}.{k}")
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


def test_review_status_and_runner_capability_conform():
    candidate = {
        "milestones": [{
            "id": "M15", "status": "review", "track": "physics",
            "growth_form": "fern", "runner_available": True,
        }]
    }
    assert validate(candidate, SCHEMA) == []


def test_non_http_url_is_rejected():
    # Mirrors the windowsill page's link guard: only http(s) records become links.
    bad = {"milestones": [{"id": "M01", "status": "verified", "url": "javascript:alert(1)"}]}
    assert validate(bad, SCHEMA)


def test_schema_is_self_consistent():
    ms = SCHEMA["definitions"]["milestone"]
    assert set(ms["required"]) <= set(ms["properties"])


def test_growth_form_in_snapshot_conforms_and_enum_is_enforced():
    """The derived `growth_form` on every milestone validates against the schema's
    enum, and a bogus form is rejected — the producer's mapping and the contract
    can't silently drift."""
    snap = build_snapshot(parse_milestones(SAMPLE), "2026-06-08T00:00:00+00:00", 3, 47.0)
    assert validate(snap, SCHEMA) == []
    assert all("growth_form" in m for m in snap["milestones"])
    # A form outside the enum is rejected (mirrors the page's contract).
    bad = {"milestones": [{"id": "M01", "status": "verified", "growth_form": "cactus"}]}
    assert validate(bad, SCHEMA)
    # Every form the producer can emit is in the schema enum (no producer/contract drift).
    from lab.publish import GROWTH_FORMS
    enum = set(SCHEMA["definitions"]["milestone"]["properties"]["growth_form"]["enum"])
    assert set(GROWTH_FORMS.values()) <= enum


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


# ── v5: presentation grouping — group_count / group_first_date ───────────────
# Consecutive same-milestone same-verdict runs collapse to their newest row in
# pot.json's reports[]; the archive index keeps every run. The fields are
# additive + optional so old consumers degrade cleanly.

def test_grouped_report_row_conforms():
    grouped = dict(
        VALID_REPORT, verdict="verified",
        group_count=4, group_first_date="2026-07-20",
    )
    assert validate({"reports": [grouped]}, SCHEMA) == []
    # group_first_date may be null (an undated streak start degrades honestly).
    undated = dict(VALID_REPORT, group_count=2, group_first_date=None)
    assert validate({"reports": [undated]}, SCHEMA) == []


def test_group_count_of_one_is_rejected():
    """N3 — a lone run is NOT a group: the producer omits the fields entirely
    for streaks of one, and the contract enforces it (minimum 2). A row
    claiming group_count 1 is a producer bug, not a valid degenerate group."""
    bad = {"reports": [dict(VALID_REPORT, group_count=1)]}
    assert validate(bad, SCHEMA)


def test_schema_version_5_accepted_and_6_rejected():
    assert validate({"schema_version": 5}, SCHEMA) == []
    assert validate({"schema_version": 6}, SCHEMA)


# ── v5: turns — the pass counter, the declared cadence, machine provenance ───

def test_turns_object_and_provenance_fields_conform():
    snap = {
        "schema_version": 5,
        "turns": {
            "count": 61, "today": 3, "expected_interval_h": 3,
            "last_by_machine": {
                "windows-cuda": "2026-08-01T12:03:11-04:00",
                "linux-rocm": None,          # declared, never run — a fact
            },
        },
        "divergence": [{"milestone": "M01", "machines": {
            "windows-cuda": "verified", "linux-rocm": "null"}}],
        "reports": [dict(
            VALID_REPORT, verdict="verified", machine="windows-cuda",
            at="2026-08-01T12:03:11-04:00",
            group_count=4, group_first_date="2026-07-30",
            group_machines=["linux-rocm", "windows-cuda"],
        )],
    }
    assert validate(snap, SCHEMA) == []


def test_a_pre_turns_feed_still_validates():
    """A feed built before any of this — no turns, no divergence, no machine or
    at on its rows — is still a conforming pot.json. The page degrades to the
    days-tended counter and its legacy constants rather than breaking."""
    legacy = {
        "schema_version": 5, "runs": 39,
        "reports": [dict(VALID_REPORT, verdict="verified")],
    }
    assert validate(legacy, SCHEMA) == []


def test_machine_string_format_is_enforced():
    """The mark is rendered into the page, so its shape is a contract, not a
    convention: lowercase, hyphenated, bounded."""
    for bad_value in ("Windows-CUDA", "-leading", "9front",
                      "a" * 25, "win<script>"):
        bad = {"reports": [dict(VALID_REPORT, machine=bad_value)]}
        assert validate(bad, SCHEMA), f"{bad_value!r} should be rejected"
    for good in ("windows-cuda", "linux-rocm", "linux"):
        assert validate({"reports": [dict(VALID_REPORT, machine=good)]}, SCHEMA) == []


def test_latest_report_documents_ledger_identity_fields():
    latest = {
        "milestone": "M01",
        "verdict": "verified",
        "headline": "qualified peak",
        "receipt_url": "https://example.test/receipt.json",
    }
    assert validate({"latest_report": latest}, SCHEMA) == []


def test_physics_v2_quality_contract_conforms(tmp_path):
    from lab import physics_feed

    reports = tmp_path / "reports"
    reports.mkdir()
    report = {
        "experiment": "M01-ising-verification",
        "T": [1.5, 1.6, 2.3],
        "chi": [1900.0, 2.0, 81.0],
        "abs_mag": [0.62, 0.98, 0.65],
        "abs_mag_err": [0.02, 0.001, 0.005],
        "snapshots": {"T=1.500": [[1, -1], [-1, 1]]},
    }
    (reports / "2026-07-25-m01.json").write_text(json.dumps(report), encoding="utf-8")
    feed = physics_feed.build_feed(reports_dir=reports, lab_home=tmp_path / "none")
    assert validate(feed, PHYSICS_SCHEMA) == []
    assert feed["m01"]["raw_chi_peak_t"] == 1.5
    assert feed["m01"]["chi_peak_t"] == 2.3


def test_committed_physics_feed_conforms():
    repo_root = Path(__file__).resolve().parents[1]
    committed = json.loads(
        (repo_root / "physics-latest.json").read_text(encoding="utf-8")
    )
    assert validate(committed, PHYSICS_SCHEMA) == []
    source_report = (repo_root / committed["generated_from"]).resolve()
    assert source_report.is_relative_to((repo_root / "reports").resolve())
    assert source_report.is_file()
    assert "/receipts/run-" in committed["generated_from"]
    source = json.loads(source_report.read_text(encoding="utf-8"))
    assert source.get("experiment") == "M01-ising-verification"
    assert committed["m01"]["source_report"] == committed["generated_from"]
    assert committed["provenance"] == source.get("provenance")
