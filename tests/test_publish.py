"""Tests for the seed-in-a-pot snapshot builder (stdlib-only, no torch)."""
from lab.publish import build_snapshot, parse_milestones


SAMPLE = """
## Phase 1 — verify (we are here)

- [x] **M01** — 2D Ising verification. Reproduce Onsager's M(T) curve, locate T_c via susceptibility peak. (done 2026-06-08 — peak at T=2.30 ± 0.05, Onsager: 2.2692)
- [ ] **M02** — Finite-size scaling: rerun at L = 32, 64, 128, 256, 512 and check collapse.
- [~] **M03** — Specific heat curve C(T). Should diverge. (binning unstable — failed calibration)
- [ ] **M04** — Verify lattice geometries beyond square: triangular (T_c ≈ 3.641).

## Conventions
- Each milestone PR includes the report it generated.
"""


def test_parses_all_milestone_lines_only():
    ms = parse_milestones(SAMPLE)
    assert [m["id"] for m in ms] == ["M01", "M02", "M03", "M04"]


def test_status_mapping():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert ms["M01"]["status"] == "verified"
    assert ms["M02"]["status"] == "open"      # first pending → the open experiment
    assert ms["M03"]["status"] == "null"      # [~] → honest null
    assert ms["M04"]["status"] == "pending"   # later pending stays pending


def test_title_is_first_clause():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert ms["M01"]["title"] == "2D Ising verification"
    assert ms["M02"]["title"] == "Finite-size scaling"  # split on the colon


def test_verified_result_lifts_parenthetical():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert "peak at T=2.30" in ms["M01"]["result"]
    assert "done" not in ms["M01"]["result"]   # the "done <date> —" prefix is stripped


def test_null_has_no_result_field():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert "result" not in ms["M03"]


def test_only_first_pending_is_open():
    statuses = [m["status"] for m in parse_milestones(SAMPLE)]
    assert statuses.count("open") == 1


def test_build_snapshot_shape():
    ms = parse_milestones(SAMPLE)
    snap = build_snapshot(ms, "2026-06-08T00:00:00+00:00", 1, 47.0)
    assert snap["source"] == "windowsill-lab"
    assert snap["total"] == 4
    assert snap["runs"] == 1
    assert snap["temp_c"] == 47.0
    assert snap["last_run"].startswith("2026-06-08")
    assert "updated" in snap
    assert snap["schema_version"] >= 1
    prov = snap["provenance"]
    assert "code_sha" in prov and "env" in prov and isinstance(prov["deps"], dict)


def test_handles_empty_text():
    assert parse_milestones("") == []


# ── The Citizen Science book: letter-prefixed tracks + record tags ──────────
CITIZEN = """
- [x] **M01** — 2D Ising verification. (done 2026-06-08 — Onsager check)
- [x] **C03** — Extend OEIS A000123. (done 2026-08-01 — accepted) {venue=OEIS; url=https://oeis.org/A000123; doi=10.5281/zenodo.123456}
- [ ] **A02** — Recover a variable star and submit. {venue=AAVSO}
- [ ] **I02** — Log cosmic-ray muon candidates for a month. {venue=DECO}
"""


def test_track_is_derived_from_prefix():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert ms["M01"]["track"] == "physics"
    assert ms["C03"]["track"] == "compute"
    assert ms["A02"]["track"] == "astronomy"
    assert ms["I02"]["track"] == "instrument"


def test_record_tags_are_parsed():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert ms["C03"]["venue"] == "OEIS"
    assert ms["C03"]["url"] == "https://oeis.org/A000123"
    assert ms["C03"]["doi"] == "10.5281/zenodo.123456"


def test_tag_block_stripped_from_title_and_result():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert "{" not in ms["C03"]["title"]
    assert "venue" not in ms["C03"].get("result", "")


def test_tags_flow_on_pending_too():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert ms["A02"]["venue"] == "AAVSO"
    # A02 is the first pending across the sample → promoted to the open experiment
    assert ms["A02"]["status"] == "open"


# ── Explicit open marker + progress: the lab can pick any track as its front ──
EXPLICIT = """
- [x] **M01** — 2D Ising. (done — ok)
- [ ] **M02** — next physics rung.
- [>] **A02** — Recover a variable star and submit. {venue=AAVSO; progress=0.4}
"""


def test_explicit_open_marker_overrides_auto_promotion():
    ms = {m["id"]: m for m in parse_milestones(EXPLICIT)}
    assert ms["A02"]["status"] == "open"      # explicitly marked [>]
    assert ms["M02"]["status"] == "pending"   # NOT auto-promoted while [>] exists


def test_progress_tag_is_parsed_and_clamped():
    ms = {m["id"]: m for m in parse_milestones(EXPLICIT)}
    assert ms["A02"]["progress"] == 0.4
    over = parse_milestones("- [>] **C01** — calibrate. {progress=9}")[0]
    assert over["progress"] == 1.0
    bad = parse_milestones("- [>] **C01** — calibrate. {progress=soon}")[0]
    assert "progress" not in bad
