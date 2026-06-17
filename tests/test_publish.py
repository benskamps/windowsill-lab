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


def _write_report(directory, stem, mtime, **extra):
    """Drop a minimal valid report JSON dated `stem`, stamped at `mtime`.

    Defaults to an M01-shaped Ising χ-sweep; ``extra`` overrides/adds fields
    (e.g. ``experiment=``, ``status=``) so one helper covers every report kind.
    """
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{stem}.json"
    payload = {
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 9.0, 1.0],          # peaks at T=2.3
        "wall_seconds": 35.0,
        "headline": f"run {stem}",
    }
    payload.update(extra)
    p.write_text(json.dumps(payload), encoding="utf-8")
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


def test_newest_report_breaks_mtime_tie_by_date_stem(tmp_path, monkeypatch):
    """FIX 4: a fresh git clone resets every file mtime to the SAME value, so
    mtime alone leaves "newest" arbitrary. The higher leading date stem must win
    the tie — stable ordering after a clone (mirrors archive.scan_runs)."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # Equal mtimes (the post-clone reality): the higher date stem is the latest.
    _write_report(lab_home, "2026-06-14", mtime=1000)
    _write_report(lab_home, "2026-06-15", mtime=1000)
    rep = _newest_report()
    assert rep["_date"] == "2026-06-15"


def test_run_cadence_last_breaks_mtime_tie_by_date_stem(tmp_path, monkeypatch):
    """FIX 4: with equal mtimes, run_cadence's last_run tracks the higher date."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(lab_home, "2026-06-14", mtime=1000)
    _write_report(lab_home, "2026-06-15", mtime=1000)   # same mtime, higher date
    last_iso, total = run_cadence()
    assert total == 2
    # last_run is stamped from the winning file's mtime; both share it here, but
    # the WINNER must be the 06-15 file (its date breaks the tie).
    assert last_iso == datetime.fromtimestamp(1000, timezone.utc).isoformat()


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


# ── Permanence refactor: slug, run records, discovery, snapshot, backfill ────
# The bug being fixed: render() clobbered a single reports/latest.html every
# run, so milestone reports were buried; latest_report was a single object so
# the page couldn't deep-link history. The fix adds permanent per-run report
# files, a reports[] array in pot.json, and an idempotent backfill().

from lab.publish import (
    _slug_for, _run_record, discover_runs, backfill, SCHEMA_VERSION,
)
from pathlib import Path


def test_schema_version_bumped_to_3():
    assert SCHEMA_VERSION == 3


def test_slug_for_rules():
    assert _slug_for({"experiment": "M02-finite-size-scaling"}) == "m02"
    assert _slug_for({"experiment": "M03-data-collapse"}) == "m03"
    assert _slug_for({"experiment": "M01-ising-verification"}) == "m01"
    # legacy M01 dump: no experiment, but has T + chi
    assert _slug_for({"T": [2.2, 2.3], "chi": [1.0, 9.0]}) == "m01"
    # nothing recognizable
    assert _slug_for({}) == "run"


def test_run_record_shape_for_m01(tmp_path):
    p = _write_report(tmp_path, "2026-06-15", mtime=1000)
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    # The compact record the page consumes.
    assert set(rec) == {
        "date", "milestone", "experiment", "headline",
        "peak_t", "wall_s", "url", "code_sha", "status",
    }
    assert rec["date"] == "2026-06-15"
    assert rec["milestone"] == "M01"
    assert rec["peak_t"] == 2.3            # derived from T/chi peak
    assert rec["wall_s"] == 35.0
    # Honest default: no verdict info → "unscored", never "verified" (FIX 1).
    assert rec["status"] == "unscored"
    assert rec["url"].startswith("http")


def test_run_record_status_null_for_failed_calibration(tmp_path):
    p = _write_report(tmp_path, "2026-06-15", mtime=1000, status="null")
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    assert rec["status"] == "null"         # a folded grey leaf — honest null


def test_run_record_status_unscored_when_no_verdict_info(tmp_path):
    """The honesty invariant: a run with NO verdict info is "unscored", never
    "verified". ``_run_record`` is the fallback path when the verdict-graded
    archive ledger raises — claim no verification you didn't perform.

    The legacy default labelled any non-null run "verified", so a failed run
    could ride out as a green leaf. It must default to "unscored" instead.
    """
    # A report carrying neither an explicit "null" marker nor any check-derived
    # verdict — the bare structural record can't know it passed.
    p = _write_report(tmp_path, "2026-06-15", mtime=1000)
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    assert rec["status"] == "unscored"     # NOT "verified" — no verification performed
    # The explicit honest-null marker is still honored.
    p2 = _write_report(tmp_path, "2026-06-14", mtime=900, status="null")
    rec2 = _run_record(p2, json.loads(p2.read_text(encoding="utf-8")))
    assert rec2["status"] == "null"


def test_discover_runs_never_defaults_to_verified(tmp_path, monkeypatch):
    """Through the full discover_runs path: a plain run JSON surfaces as
    "unscored", never "verified" — the fallback can't manufacture a green leaf."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(reports, "2026-06-15-m01", mtime=1000,
                  experiment="M01-ising-verification")
    runs = discover_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "unscored"


def test_run_record_milestone_for_m02(tmp_path):
    p = _write_report(
        tmp_path, "2026-06-16", mtime=1000,
        experiment="M02-finite-size-scaling",
    )
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    assert rec["milestone"] == "M02"
    assert rec["experiment"] == "M02-finite-size-scaling"


def test_discover_runs_newest_first_and_deduped(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)

    # Same (date, slug) in BOTH places — repo must win.
    _write_report(lab_home, "2026-06-15-m02", mtime=1000,
                  experiment="M02-finite-size-scaling", headline="lab copy")
    _write_report(reports, "2026-06-15-m02", mtime=900,
                  experiment="M02-finite-size-scaling", headline="repo copy")
    # An older, distinct M01 run only in the repo.
    _write_report(reports, "2026-06-08-m01", mtime=500,
                  experiment="M01-ising-verification", headline="old m01")

    runs = discover_runs()
    # Deduped to two distinct (date, slug) runs.
    assert len(runs) == 2
    # Newest-first by mtime: the m02 run (mtime 1000 in lab) comes first.
    assert runs[0]["date"] == "2026-06-15"
    assert runs[1]["date"] == "2026-06-08"
    # Repo wins the dedupe even though the lab copy had the newer mtime: the
    # record is built from the repo file's content.
    assert runs[0]["headline"] == "repo copy"


def test_discover_runs_matches_legacy_bare_date_names(tmp_path, monkeypatch):
    """A legacy <date>.json (no slug) is still discovered and inferred as M01."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(reports, "2026-06-08", mtime=500)   # legacy bare-date M01 dump
    runs = discover_runs()
    assert len(runs) == 1
    assert runs[0]["date"] == "2026-06-08"
    assert runs[0]["milestone"] == "M01"


def test_build_snapshot_emits_reports_array_and_back_compat_latest():
    r1 = {"date": "2026-06-15", "milestone": "M02", "status": "verified"}
    r2 = {"date": "2026-06-08", "milestone": "M01", "status": "verified"}
    snap = build_snapshot(parse_milestones(SAMPLE), "x", 2, 47.0, reports=[r1, r2])
    assert snap["reports"] == [r1, r2]
    assert snap["latest_report"] == r1     # newest run is the headline


def test_build_snapshot_back_compat_without_reports():
    rep = {"date": "2026-06-08", "headline": "legacy single report"}
    snap = build_snapshot(parse_milestones(SAMPLE), "x", 1, 47.0, report=rep)
    # No reports kwarg → legacy single-report behavior preserved.
    assert snap["latest_report"] == rep
    assert snap.get("reports", []) == []


def test_lab_cache_is_slug_keyed_no_same_day_collision(tmp_path, monkeypatch):
    """FIX 3: two different milestones run on the SAME day must both survive in
    the ~/.lab dated cache. The old bare ``<date>.json``/``.html`` names let the
    second run clobber the first locally; slug-keyed ``<date>-<slug>.json/.html``
    keeps both, and discovery still finds them."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # Simulate what the renderers now write to ~/.lab on the same day: two
    # distinct milestones, each under its own slug-keyed cache name.
    _write_report(lab_home, "2026-06-15-m02", mtime=1000,
                  experiment="M02-finite-size-scaling", headline="m02 same day")
    _write_report(lab_home, "2026-06-15-m03", mtime=1001,
                  experiment="M03-data-collapse", headline="m03 same day")
    # Both slug-keyed cache files coexist (no clobber).
    assert (lab_home / "2026-06-15-m02.json").exists()
    assert (lab_home / "2026-06-15-m03.json").exists()
    # Discovery finds BOTH same-day runs distinctly.
    runs = discover_runs()
    headlines = {r["headline"] for r in runs}
    assert headlines == {"m02 same day", "m03 same day"}
    assert {r["milestone"] for r in runs} == {"M02", "M03"}


def test_backfill_dry_run_writes_nothing(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(lab_home, "2026-06-15", mtime=2000)   # M01-shaped
    _write_report(lab_home, "2026-06-16", mtime=2100,
                  experiment="M02-finite-size-scaling")
    reports.mkdir(parents=True, exist_ok=True)

    planned = backfill(dry_run=True)
    assert len(planned) == 2                            # two reports to create
    # Nothing actually written under reports/.
    assert not list(reports.glob("*.json"))


def test_backfill_is_idempotent(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # discover_runs uses render dirs too for the URL; keep render writing to tmp.
    from lab import render
    monkeypatch.setattr(render, "REPO_REPORTS", reports)
    monkeypatch.setattr(render, "LAB_HOME", lab_home)

    src1 = _write_report(lab_home, "2026-06-15", mtime=2000)  # M01
    src2 = _write_report(lab_home, "2026-06-16", mtime=2100,
                         experiment="M02-finite-size-scaling")

    written = backfill()
    # The permanent JSON sidecars now exist in repo reports/.
    assert (reports / "2026-06-15-m01.json").exists()
    assert (reports / "2026-06-16-m02.json").exists()
    assert len(written) >= 2
    # Source ~/.lab files are COPIED, not moved/destroyed — history is preserved.
    assert src1.exists() and src2.exists()

    # A SECOND backfill is a no-op (skip-if-exists).
    again = backfill()
    assert again == []


def test_backfill_renders_m03_reports(tmp_path, monkeypatch):
    """FIX 2c: backfill re-renders M03 reports too, not just M02 — so a
    data-collapse run in ~/.lab lands a permanent reports/<date>-m03.html/.json."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    from lab import render
    monkeypatch.setattr(render, "REPO_REPORTS", reports)
    monkeypatch.setattr(render, "LAB_HOME", lab_home)

    # An M03 report cached in ~/.lab with NO sibling HTML — backfill must render it.
    import numpy as np
    from lab.m03 import to_report as m03_to_report, M03Result, M03Curve, T_C, BETA_OVER_NU, INV_NU, NU
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 24)
    cs = []
    for L in Ls:
        T = T_C + xs * L ** (-INV_NU)
        M = L ** (-BETA_OVER_NU) / (1.0 + np.exp(3.0 * xs))
        cs.append(M03Curve(L=L, T=T.tolist(), M=M.tolist(),
                           M_err=[0.0] * len(T), wall_seconds=1.0))
    rep = m03_to_report(M03Result(
        curves=cs, beta_over_nu_fit=BETA_OVER_NU, inv_nu_fit=1.0,
        collapse_quality=1e-15, tc=float(T_C), beta_over_nu_theory=BETA_OVER_NU,
        nu=NU, wall_seconds=120.0, config={"seed": 42}))
    lab_home.mkdir(parents=True, exist_ok=True)
    (lab_home / "2026-06-16.json").write_text(json.dumps(rep), encoding="utf-8")

    written = backfill()
    assert (reports / "2026-06-16-m03.json").exists()
    assert (reports / "2026-06-16-m03.html").exists()   # re-rendered, not skipped
