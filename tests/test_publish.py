"""Tests for the seed-in-a-pot snapshot builder (stdlib-only, no torch)."""
import json
import os
from datetime import date, datetime, timezone

from lab import publish
from lab.publish import build_snapshot, parse_milestones, run_cadence, today_local
from lab.publish import _newest_report


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


# ── Report dates are LOCAL, and "newest" is by mtime, not date-string ────────
# A report run in the evening should carry the operator's local day, not the
# UTC day (which can already be "tomorrow"). And the *newest* report is the one
# most recently written — never the one whose filename sorts highest. Those two
# facts are coupled: once dates are local, a stale future-dated file (e.g. a
# UTC-dated 06-16 left over from an evening run) must not shadow a fresh 06-15.

def test_today_local_is_the_wall_clock_date():
    assert today_local() == date.today().isoformat()


def _write_report(directory, stem, mtime):
    """Drop a minimal valid report JSON dated `stem`, stamped at `mtime`."""
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{stem}.json"
    p.write_text(json.dumps({
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 9.0, 1.0],          # peaks at T=2.3
        "wall_seconds": 35.0,
        "headline": f"run {stem}",
    }), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_newest_report_is_by_mtime_not_lexicographic_date(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # A stale future-dated file written EARLIER, and the real latest run written
    # LATER but with an earlier date string. mtime must win.
    _write_report(lab_home, "2026-06-16", mtime=1000)   # higher date, older write
    _write_report(lab_home, "2026-06-15", mtime=2000)   # lower date, newer write
    rep = _newest_report()
    assert rep["_date"] == "2026-06-15"                  # the truly-newest run


def test_run_cadence_last_is_by_mtime_total_is_distinct_days(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(reports, "2026-06-08", mtime=500)
    _write_report(lab_home, "2026-06-16", mtime=1000)   # future date, older write
    newest_mtime = 2000
    _write_report(lab_home, "2026-06-15", mtime=newest_mtime)   # the real last run
    last_iso, total = run_cadence()
    assert total == 3                                    # three distinct days on record
    # last_run is the actual moment the newest report was written (mtime), so it
    # tracks the 06-15 file even though 06-16 sorts higher as a string.
    assert last_iso == datetime.fromtimestamp(newest_mtime, timezone.utc).isoformat()
