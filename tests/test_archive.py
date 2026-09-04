"""Tests for the full-provenance ARCHIVE index — the honest every-run ledger.

The windowsill page shows the *living* face of the lab (the seedling). The
archive is its honest back-room: a flat, newest-first index of EVERY run on
record — verified nodes on the stem AND folded grey leaves (failed
calibrations), each deep-linking the exact report it came from. Nothing is
hidden, nothing is deleted; an off run keeps its real numbers as a null row.

Stdlib-only, all fixtures in ``tmp_path`` with ``archive.REPORTS_DIR`` /
``archive.LAB_HOME`` monkeypatched — these tests NEVER touch the live
``reports/`` or ``~/.lab`` (same discipline as test_publish/test_render).
"""
import json
import os

import pytest

from lab import archive, publish
from lab.archive import (
    classify_run, scan_runs, run_ledger, render_index, write_index,
)


def _write_report(directory, stem, mtime, **extra):
    """Drop a minimal report JSON dated `stem`, stamped at `mtime`.

    Defaults to an M01-shaped Ising χ-sweep (peaks at T=2.3); ``extra`` adds or
    overrides fields (``experiment=``, ``status=``, ``curves=`` …).
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


# An M02 finite-size-scaling report that PASSES its check (slope ≈ 7/4).
def _m02_good():
    # χ_max ∝ L^1.75 exactly: chi_max = L**1.75, so the log-log slope is 1.75.
    Ls = [32, 64, 128, 256]
    return {
        "experiment": "M02-finite-size-scaling",
        "headline": "finite-size scaling",
        "wall_seconds": 120.0,
        "gamma_over_nu_fit": 1.75,
        "fit_r2": 0.999,
        "curves": [{"L": L, "chi_max": float(L) ** 1.75,
                    "T": [2.27, 2.30], "chi": [1.0, 2.0]} for L in Ls],
    }


# An M02 report whose scaling is UNPHYSICAL — the L=512 honesty case. The check
# fails (slope far from 7/4), so it's an honest null that KEEPS its real numbers.
def _m02_null():
    Ls = [32, 64, 128, 256, 512]
    # chi_max climbs only as L^0.5 — way off γ/ν = 1.75 → the check fails.
    return {
        "experiment": "M02-finite-size-scaling",
        "headline": "scaling came out wrong",
        "wall_seconds": 130.0,
        "gamma_over_nu_fit": 0.50,
        "fit_r2": 0.40,
        "curves": [{"L": L, "chi_max": float(L) ** 0.5,
                    "T": [2.27, 2.30], "chi": [1.0, 2.0]} for L in Ls],
    }


def _patch(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    monkeypatch.setattr(archive, "RECEIPTS_DIR", reports / "receipts")
    monkeypatch.setattr(archive, "LAB_HOME", lab_home)
    # publish's discovery shares the same dirs (archive defers to it).
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "RECEIPTS_DIR", reports / "receipts")
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    return reports, lab_home


# ── classify_run: the verdict is a RECEIPT, graded through checks.CHECKS ──────

def test_classify_m01_chi_sweep_is_verified():
    rec = classify_run({"experiment": "M01-ising-verification",
                        "T": [2.2, 2.3, 2.4], "chi": [1.0, 9.0, 1.0],
                        "headline": "ising"})
    assert rec["milestone"] == "M01"
    assert rec["verdict"] == "verified"          # χ peak near Onsager → green leaf
    assert rec["kind"] == "ising"


def test_classify_m01_replaces_stale_raw_headline_with_checked_peak():
    rec = classify_run({
        "experiment": "M01-ising-verification",
        "T": [1.5, 1.6, 2.3],
        "chi": [1900.0, 2.0, 81.0],
        "abs_mag": [0.62, 0.98, 0.65],
        "abs_mag_err": [0.02, 0.001, 0.005],
        "headline": "χ peaked at T≈1.500",
    })
    assert rec["verdict"] == "verified"
    assert "T=2.300" in rec["headline"]
    assert "excluded" in rec["headline"]
    assert "1.500" not in rec["headline"].split(" vs ")[0]


def test_classify_m02_good_is_verified():
    rec = classify_run(_m02_good())
    assert rec["milestone"] == "M02"
    assert rec["kind"] == "fss"
    assert rec["verdict"] == "verified"


def test_classify_m02_null_keeps_its_real_numbers():
    """The L=512 honesty case: a failed scaling stays a folded grey leaf and
    KEEPS its real slope/R²/L-values in the detail — shown, never deleted."""
    rec = classify_run(_m02_null())
    assert rec["milestone"] == "M02"
    assert rec["verdict"] == "null"              # check FAILED → folded grey leaf
    # Its real measured numbers survive in the row, not just "it failed". The
    # check's own sentence keeps the off slope; the numbers field keeps the
    # L-values — together, the L=512 run is shown on the books, never deleted.
    assert "0.5" in rec["detail"] or "0.50" in rec["detail"]
    assert "512" in rec["numbers"]               # the L-values are kept on the books


def test_classify_unscored_run_is_kept_not_dropped():
    """A report no registered check understands is UNSCORED — a plain node, kept
    on the books (verdict is never silently dropped)."""
    rec = classify_run({"experiment": "Z99-unknown", "headline": "mystery"})
    assert rec["verdict"] == "unscored"
    assert rec["milestone"] in (None, "Z99")     # inferred id or none, but kept


# ── scan_runs: every run, newest-first, honest about gaps ────────────────────

def test_scan_runs_newest_first_by_date_not_mtime(tmp_path, monkeypatch):
    """Newest-first is keyed on the run's own DATE, never on the file's mtime.

    This test used to assert the opposite — that the more recently *written*
    file leads — to stop a stale future-dated report masquerading as the latest.
    That guard bought one narrow case at the cost of the ledger's determinism:
    mtimes are not repo content, so a clone or a ``git pull`` re-stamped them
    and two boxes published different feeds from the same commit (DET-2). The
    run's date is what the run says about itself and it is identical in every
    clone, so it leads — and the same fixture must produce the same order no
    matter which file was touched last.
    """
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(lab_home, "2026-06-16", mtime=1000)   # higher date, OLDER write
    _write_report(lab_home, "2026-06-15", mtime=2000)   # lower date, NEWER write
    assert [r["date"] for r in scan_runs()] == ["2026-06-16", "2026-06-15"]

    # Swap which file is "newest on disk": the order must not move.
    os.utime(lab_home / "2026-06-16.json", (2000, 2000))
    os.utime(lab_home / "2026-06-15.json", (1000, 1000))
    assert [r["date"] for r in scan_runs()] == ["2026-06-16", "2026-06-15"]


def test_scan_runs_prefers_committed_copy_and_flags_local_only(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    # Same (date, slug) in both — the committed repo copy must win the dedupe.
    _write_report(lab_home, "2026-06-15-m01", mtime=2000, headline="lab copy")
    _write_report(reports, "2026-06-15-m01", mtime=1000, headline="repo copy")
    # A run that exists ONLY in ~/.lab → flagged local_only.
    _write_report(lab_home, "2026-06-08-m01", mtime=500, headline="only local")
    runs = scan_runs()
    by_date = {r["date"]: r for r in runs}
    assert by_date["2026-06-15"]["headline"] == "repo copy"
    assert by_date["2026-06-15"]["local_only"] is False
    assert by_date["2026-06-08"]["local_only"] is True


def test_scan_runs_keeps_corrupt_json_as_honest_unreadable_gap(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m01", mtime=1000)
    bad = reports / "2026-06-14-run.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")
    os.utime(bad, (900, 900))
    runs = scan_runs()
    by_date = {r["date"]: r for r in runs}
    # The corrupt file is NOT silently dropped — it's an honest unreadable row.
    assert "2026-06-14" in by_date
    assert by_date["2026-06-14"]["verdict"] == "unreadable"


def test_scan_runs_committed_run_links_to_exact_archive_row(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m01", mtime=1000)
    (reports / "2026-06-15-m01.html").write_text("<html>r</html>", encoding="utf-8")
    runs = scan_runs()
    r = runs[0]
    assert r["has_dated_html"] is True
    # Dated per-run renders are gitignored (never on GitHub), so a committed run
    # deep-links to the exact row on the committed, htmlpreview-able archive
    # index — not its own uncommitted dated render, which would 400.
    assert r["report_href"] == publish.archive_url() + "#run-2026-06-15-m01"
    assert "2026-06-15-m01.html" not in r["report_href"]


def test_scan_runs_local_only_links_to_dated_json(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(lab_home, "2026-06-08-m01", mtime=500)   # only in ~/.lab, no html
    runs = scan_runs()
    r = runs[0]
    assert r["has_dated_html"] is False
    # Falls back to the dated JSON so the run is still traceable before backfill.
    assert "2026-06-08" in r["report_href"]
    assert r["report_href"].endswith(".json")


# ── run_ledger: the sanitized rows that go into pot.json ──────────────────────

def test_run_ledger_rows_are_sanitized(tmp_path, monkeypatch):
    """A ledger row is only {date, milestone, verdict, headline, href} — no
    config, no curves, no raw arrays leak into the public feed."""
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m02", mtime=1000, **_m02_good())
    rows = run_ledger()
    assert rows
    assert set(rows[0]) == {
        "date", "milestone", "verdict", "headline", "href", "receipt_url",
    }


def test_run_ledger_non_http_href_becomes_none(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(lab_home, "2026-06-08-m01", mtime=500)
    rows = run_ledger()
    # A publisher-local cache file is not part of the PUBLIC run ledger. Keeping
    # it with href=None still inflated the public total and later generated a
    # dead file:///home/... link in reports/index.html.
    assert rows == []


def test_public_surfaces_do_not_double_count_the_publishers_raw_cache(
    tmp_path, monkeypatch
):
    """One real receipt stays one public run when ~/.lab keeps its raw input.

    The publisher writes an un-stamped raw report to LAB_HOME, then enriches and
    commits the receipt. They are two files for one run, not two runs. The local
    scanner may retain both for recovery, but neither pot.json nor the committed
    archive may expose the publisher's private path or count it again.
    """
    reports, lab_home = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    receipts.mkdir(parents=True)
    payload = {
        "experiment": "M01-ising-verification",
        "headline": "one measurement",
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 9.0, 1.0],
    }
    _write_report(lab_home, "2026-08-13-m01", mtime=1000, **payload)
    (receipts / "run-2026-08-13-1803-m01.json").write_text(
        json.dumps({**payload, "generated_at": "2026-08-13T22:03:00+00:00"}),
        encoding="utf-8",
    )

    assert len(scan_runs()) == 2             # recovery view keeps both files
    rows = run_ledger()
    assert len(rows) == 1                    # public feed counts the receipt once
    assert rows[0]["receipt_url"].endswith("run-2026-08-13-1803-m01.json")

    html = render_index()
    assert "Every committed run on the public record — 1 so far" in html
    assert "file://" not in html
    assert "local report" not in html


def test_committed_receipt_replaces_same_turn_local_raw_report(
    tmp_path, monkeypatch
):
    """A turn-stamped LAB_HOME file cannot shadow its committed receipt.

    The Windows publisher keeps exact-turn raw files such as
    ``2026-08-14-0733-c01.json``. Once the matching receipt is committed, the
    public scanner must use that receipt-backed row rather than retaining the
    local row and filtering the whole turn out at the publication boundary.
    """
    reports, lab_home = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    receipts.mkdir(parents=True)
    payload = {
        "experiment": "M01-ising-verification",
        "headline": "one turn-stamped measurement",
        "generated_at": "2026-08-14T07:33:00-04:00",
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 9.0, 1.0],
    }
    _write_report(
        lab_home, "2026-08-14-0733-m01", mtime=2000, **payload
    )
    receipt = receipts / "run-2026-08-14-0733-m01.json"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(receipt, (1000, 1000))

    rows = scan_runs()
    assert len(rows) == 1
    assert rows[0]["local_only"] is False
    assert rows[0]["receipt_href"].endswith(receipt.name)
    assert len(archive.public_runs()) == 1


def test_run_ledger_validates_against_pot_schema(tmp_path, monkeypatch):
    """build_snapshot(reports_ledger=run_ledger()) conforms to pot.schema.json."""
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m02", mtime=1000, **_m02_good())
    _write_report(reports, "2026-06-14-m02", mtime=900, **_m02_null())
    ledger = run_ledger()
    snap = publish.build_snapshot(
        publish.parse_milestones(""), "x", 2, 47.0, reports_ledger=ledger,
    )
    # Reuse the dependency-free validator from the schema test suite.
    from tests.test_schema import SCHEMA, validate
    assert validate(snap, SCHEMA) == []


# ── run_ledger grouping: consecutive same-(milestone, verdict) streaks ────────
# Presentation-only collapse (2026-08-01): repeated nightly reruns of the same
# milestone with the same verdict ride pot.json as ONE row carrying
# ``group_count`` / ``group_first_date``. The archive index + receipts keep
# every run untouched. The grouping key includes the VERDICT, so a verdict
# change always breaks the streak by construction — a null after verified can
# never be swallowed into a green group.

def _m01_null_sweep():
    """A χ-sweep peaking at T=1.6 — far from Onsager 2.269 → honest null."""
    return {"T": [1.5, 1.6, 1.7], "chi": [1.0, 9.0, 1.0]}


def test_run_ledger_verdict_change_always_breaks_streak(tmp_path, monkeypatch):
    """N1 — the load-bearing negative control. Mirrors the real committed
    M01 history: 7/28 verified / 7/29 null / 7/30 verified. Three rows MUST
    come out — merging any of them would hide a failed calibration inside a
    green group (or a recovery inside a grey one)."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-07-28-m01", mtime=1000)
    _write_report(reports, "2026-07-29-m01", mtime=2000, **_m01_null_sweep())
    _write_report(reports, "2026-07-30-m01", mtime=3000)
    rows = run_ledger()
    assert [(r["date"], r["verdict"]) for r in rows] == [
        ("2026-07-30", "verified"),
        ("2026-07-29", "null"),
        ("2026-07-28", "verified"),
    ]
    # Streaks of one carry NO group fields — a lone run is not a group.
    for r in rows:
        assert "group_count" not in r
        assert "group_first_date" not in r


def test_run_ledger_non_adjacent_same_milestone_stays_separate(tmp_path, monkeypatch):
    """N2 — consecutiveness is required: M01, M02, M01 never groups the two
    M01 rows across the M02 between them."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-07-01-m01", mtime=1000)
    _write_report(reports, "2026-07-02-m02", mtime=2000, **_m02_good())
    _write_report(reports, "2026-07-03-m01", mtime=3000)
    rows = run_ledger()
    assert [r["milestone"] for r in rows] == ["M01", "M02", "M01"]
    for r in rows:
        assert "group_count" not in r


def test_run_ledger_never_groups_milestone_none_rows(tmp_path, monkeypatch):
    """N4 — a ``None`` milestone is an UNKNOWN identity, not a shared one.
    Two consecutive freeform runs (different experiments, both ``unscored``,
    both inferring no milestone) must never merge: a ×N chip claiming
    'N consecutive runs of this experiment' would be false. Fail closed —
    grouping requires a named milestone on both rows."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-07-20-x", mtime=1000, T=None, chi=None,
                  experiment="freeform-quench", headline="quench doodle")
    _write_report(reports, "2026-07-21-x", mtime=2000, T=None, chi=None,
                  experiment="tensor-doodle", headline="tensor doodle")
    rows = run_ledger()
    assert [(r["milestone"], r["verdict"]) for r in rows] == [
        (None, "unscored"),
        (None, "unscored"),
    ]
    for r in rows:
        assert "group_count" not in r
        assert "group_first_date" not in r


def test_run_ledger_never_groups_unreadable_gap_rows(tmp_path, monkeypatch):
    """N4b — same guard for the corrupt-JSON gap rows (milestone ``None``,
    verdict ``unreadable``): two adjacent unreadable gaps are two distinct
    disclosed absences, never one '×2 nights' group."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    for i, d in enumerate(["2026-07-20", "2026-07-21"]):
        p = reports / f"{d}-broken.json"
        reports.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")
        os.utime(p, (1000 + i, 1000 + i))
    rows = run_ledger()
    assert [(r["milestone"], r["verdict"]) for r in rows] == [
        (None, "unreadable"),
        (None, "unreadable"),
    ]
    for r in rows:
        assert "group_count" not in r


def test_run_ledger_collapses_streak_to_newest_row_with_count(tmp_path, monkeypatch):
    """A 5-night verified M01 streak rides pot.json as ONE row: newest date,
    ``group_count`` 5, ``group_first_date`` = the oldest night."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    dates = ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"]
    for i, d in enumerate(dates):
        _write_report(reports, f"{d}-m01", mtime=1000 + i)
    rows = run_ledger()
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-07-24"
    assert row["verdict"] == "verified"
    assert row["group_count"] == 5
    assert row["group_first_date"] == "2026-07-20"


def test_run_ledger_rotation_day_never_merges_across_milestones(tmp_path, monkeypatch):
    """A rotation-shaped day — several different milestones sharing one date —
    stays several rows: the group key is (milestone, verdict), never the date."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-08-01-m01", mtime=1000)
    _write_report(reports, "2026-08-01-m02", mtime=2000, **_m02_good())
    _write_report(reports, "2026-08-01-m03", mtime=3000,
                  experiment="M03-data-collapse", headline="collapse run")
    _write_report(reports, "2026-08-01-m06", mtime=4000,
                  experiment="M06-3d-ising", headline="3d run")
    rows = run_ledger()
    assert len(rows) == 4
    assert {r["milestone"] for r in rows} == {"M01", "M02", "M03", "M06"}
    for r in rows:
        assert "group_count" not in r


def test_run_ledger_grouping_leaves_archive_surfaces_untouched(tmp_path, monkeypatch):
    """The collapse is presentation-only: ``scan_runs`` still returns every raw
    run and ``render_index`` (reports/index.html) still lists every night of a
    collapsed streak — nothing is deleted anywhere."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    dates = ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"]
    for i, d in enumerate(dates):
        _write_report(reports, f"{d}-m01", mtime=1000 + i)
    assert len(scan_runs()) == 5
    html = render_index()
    for d in dates:
        assert d in html
    assert len(run_ledger()) == 1                 # while the public rail groups


def test_grouped_ledger_validates_against_pot_schema(tmp_path, monkeypatch):
    """A grouped ledger row (group_count + group_first_date) conforms to
    pot.schema.json v5 inside a full snapshot."""
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-07-22-m01", mtime=1000)
    _write_report(reports, "2026-07-23-m01", mtime=2000)
    _write_report(reports, "2026-07-24-m01", mtime=3000)
    ledger = run_ledger()
    assert len(ledger) == 1 and ledger[0]["group_count"] == 3
    snap = publish.build_snapshot(
        publish.parse_milestones(""), "x", 3, 47.0, reports_ledger=ledger,
    )
    from tests.test_schema import SCHEMA, validate
    assert validate(snap, SCHEMA) == []


# ── render_index: the HTML page — every run, nulls honest, all linked ─────────

def test_render_index_shows_every_run_including_null(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m02", mtime=1000, **_m02_good())
    _write_report(reports, "2026-06-14-m02", mtime=900, **_m02_null())
    _write_report(reports, "2026-06-08-m01", mtime=500)   # M01 verified
    html = render_index()
    # All three dates appear — no run is hidden.
    assert "2026-06-15" in html
    assert "2026-06-14" in html
    assert "2026-06-08" in html


def test_render_index_null_keeps_numbers_and_folded_grey_marker(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-14-m02", mtime=900, **_m02_null())
    html = render_index()
    # The null run shows its REAL numbers (the L=512 honesty) ...
    assert "512" in html
    assert "0.5" in html
    # ... and is marked as a folded grey leaf / honest null, not a success.
    assert "null" in html.lower() or "folded" in html.lower()


def test_render_index_links_committed_run_to_public_receipt(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m01", mtime=1000)
    (reports / "2026-06-15-m01.html").write_text("<html>r</html>", encoding="utf-8")
    receipts = reports / "receipts"
    receipts.mkdir()
    (receipts / "run-2026-06-15-m01.json").write_text("{}", encoding="utf-8")
    _write_report(lab_home, "2026-06-08-m01", mtime=500)   # local-only, json only
    html = render_index()
    # A committed run links its compact, durable evidence rather than claiming
    # the gitignored full dated HTML is public.
    assert "run-2026-06-15-m01.json" in html
    assert "receipt.json" in html
    assert "2026-06-15-m01.html" not in html
    # ... and the committed PUBLIC archive never leaks the publisher's local path.
    assert "2026-06-08" not in html
    assert "local report" not in html
    assert "file://" not in html


def test_render_index_states_verdicts_without_certifying_its_own_honesty():
    html = render_index(runs=[
        {"date": "2026-06-14", "milestone": "M02", "verdict": "null",
         "kind": "fss", "headline": "off", "detail": "slope 0.50",
         "report_href": "https://example/run", "receipt_href": None,
         "has_dated_html": False, "local_only": False, "numbers": "slope=0.50"},
        {"date": "2026-06-13", "milestone": "C02", "verdict": "unscored",
         "kind": "other", "headline": "not graded", "detail": "",
         "report_href": "https://example/unscored", "receipt_href": None,
         "has_dated_html": False, "local_only": False, "numbers": "—"},
    ])
    assert "1 null" in html
    assert "1 unscored" in html
    assert "honest null" not in html.lower()
    assert "two honesties" not in html.lower()
    assert "nothing hidden, nothing deleted" not in html.lower()


def test_render_index_is_html_escaped(tmp_path, monkeypatch):
    """A headline with HTML metacharacters is escaped, never injected raw."""
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m01", mtime=1000,
                  headline="peak <b>spiked</b> & dropped")
    html = render_index()
    assert "<b>spiked</b>" not in html          # not injected raw
    assert "&lt;b&gt;spiked&lt;/b&gt;" in html  # escaped
    assert "&amp;" in html                       # ampersand escaped too


def test_render_index_groups_by_milestone(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m02", mtime=1000, **_m02_good())
    _write_report(reports, "2026-06-08-m01", mtime=500)
    html = render_index()
    # Both milestone ids head their group.
    assert "M01" in html
    assert "M02" in html
    assert 'id="run-2026-06-15-m02"' in html


def test_render_index_accepts_explicit_runs_list():
    """render_index(runs=...) is pure — no disk read when runs are supplied."""
    runs = [
        {"date": "2026-06-15", "milestone": "M02", "verdict": "verified",
         "kind": "fss", "headline": "good", "detail": "slope 1.75",
         "report_href": "https://example/2026-06-15-m02.html",
         "has_dated_html": True, "local_only": False, "numbers": "slope=1.75"},
        {"date": "2026-06-14", "milestone": "M02", "verdict": "null",
         "kind": "fss", "headline": "off", "detail": "slope 0.50 · L up to 512",
         "report_href": "https://example/2026-06-14-m02.html",
         "has_dated_html": True, "local_only": False, "numbers": "slope=0.50"},
    ]
    html = render_index(runs=runs)
    assert "2026-06-15" in html and "2026-06-14" in html
    assert "512" in html                         # null numbers shown
    assert "null" in html.lower()


# ── write_index: emit reports/index.html (never the live tree) ────────────────

def test_write_index_writes_reports_index_html(tmp_path, monkeypatch):
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-15-m01", mtime=1000)
    path = write_index()
    assert path == reports / "index.html"
    assert path.exists()
    assert "2026-06-15" in path.read_text(encoding="utf-8")


# ── receipts fallback: a committed receipt keeps a run on the books ──────────
# Multi-box regression (2026-07-19): loam's nightly published a 10-row
# pot.json because most dated report JSONs live only on win's disk (gitignored
# by design — too heavy for git). Receipts ARE committed, one per run, and
# carry the regradeable measurements. A box that has only the receipt must
# still keep the run on the public books with working http links.

def test_receipt_only_run_survives_on_a_box_without_the_dated_json(
    tmp_path, monkeypatch
):
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "run-2026-06-14-m01.json").write_text(
        json.dumps({
            "experiment": "M01-ising-verification",
            "headline": "ising sweep",
            "T": [2.2, 2.3, 2.4],
            "chi": [1.0, 9.0, 1.0],
        }),
        encoding="utf-8",
    )

    rows = scan_runs()
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-06-14"
    assert row["milestone"] == "M01"
    assert row["verdict"] == "verified"
    assert row["local_only"] is False
    assert str(row["report_href"]).startswith("http")
    assert str(row["receipt_href"]).startswith("http")


def test_dated_json_still_beats_its_own_receipt(tmp_path, monkeypatch):
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    _write_report(reports, "2026-06-14-m01", mtime=1_700_000_000,
                  experiment="M01-ising-verification",
                  headline="the richer dated report")
    receipts = reports / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "run-2026-06-14-m01.json").write_text(
        json.dumps({
            "experiment": "M01-ising-verification",
            "headline": "the thin receipt",
            "T": [2.2, 2.3, 2.4],
            "chi": [1.0, 9.0, 1.0],
        }),
        encoding="utf-8",
    )

    rows = scan_runs()
    assert len(rows) == 1
    assert rows[0]["headline"] == "the richer dated report"


def test_corrupt_receipt_is_an_honest_gap_row(tmp_path, monkeypatch):
    reports, _lab_home = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "run-2026-06-15-m02.json").write_text("{not json", encoding="utf-8")

    rows = scan_runs()
    assert len(rows) == 1
    assert rows[0]["verdict"] == "unreadable"
    assert rows[0]["date"] == "2026-06-15"


# ── era bands: the treadmill condensed, honestly ─────────────────────────────
# 84 of 136 receipts were M01 ×40 / M02 ×44 — two scheduler bugs (a stuck
# open-pointer falling back to M01 nightly; a stem-slice parse bug livelocking
# the rotation on M02 for 9 days) re-ran verified rungs on loop while CI
# stayed green. The index bundles those streaks into era bands WITHOUT
# deleting a byte: same rows, same anchors, same links, expanded in place.

def _synthetic_run(date, milestone="M01", verdict="verified", turn=None):
    """One explicit archive row (render_index is pure when given runs)."""
    slug = milestone.lower()
    return {
        "date": date, "milestone": milestone, "verdict": verdict,
        "kind": "ising", "headline": f"run {date}-{slug}",
        "detail": "", "numbers": "χ peak at T≈2.269",
        "slug": slug, "turn": turn, "has_dated_html": False,
        "local_only": False,
        "report_href": f"https://example/archive#run-{date}-{slug}",
        "receipt_href": f"https://example/receipts/run-{date}-{slug}.json",
    }


def test_six_run_streak_bands_and_keeps_every_row_and_link():
    """(a) A 6-run same-slug streak bands at threshold 4 — zero deletion."""
    dates = [f"2026-06-0{d}" for d in range(6, 0, -1)]      # newest first
    runs = [_synthetic_run(d) for d in dates]
    out = render_index(runs=runs)
    assert out.count('<details class="era"') == 1
    assert "M01 × 6" in out
    assert "2026-06-01 → 2026-06-06" in out
    assert "6 verified" in out
    # Every inner row survives inside the details body: anchor + receipt link.
    body = out.split('<details class="era"', 1)[1].split("</details>", 1)[0]
    for d in dates:
        assert f'id="run-{d}-m01"' in body
        assert f"https://example/receipts/run-{d}-m01.json" in body


def test_three_run_streak_does_not_band():
    """(b) Below ERA_MIN_STREAK, repetition is cadence, not a treadmill."""
    runs = [_synthetic_run(f"2026-06-0{d}") for d in (3, 2, 1)]
    out = render_index(runs=runs)
    assert '<details class="era"' not in out
    assert archive.ERA_MIN_STREAK == 4      # the threshold the test leans on


def test_interleaved_slugs_never_band_across_an_interruption():
    """(c) A single other-slug run breaks the streak — the seam is kept.

    3×M01, 1×M02, 3×M01 is six M01 runs total but NO fragment reaches the
    threshold: nothing bands, even though the fragments render adjacent
    inside the M01 group.
    """
    runs = (
        [_synthetic_run(f"2026-06-0{d}") for d in (7, 6, 5)]
        + [_synthetic_run("2026-06-04", milestone="M02")]
        + [_synthetic_run(f"2026-06-0{d}") for d in (3, 2, 1)]
    )
    out = render_index(runs=runs)
    assert '<details class="era"' not in out
    # All seven rows still render.
    assert out.count('id="run-') == 7


def test_annotations_label_the_real_stuck_pointer_and_livelock_eras():
    """(d) The two curated era labels render on the real committed receipts.

    This is the honest-history test: the M01 nightly-fallback bands carry the
    stuck-pointer diagnosis (PR #77) and the Aug M02 bands carry the livelock
    diagnosis (PR #97), derived from the actual receipts on disk.
    """
    if not archive.RECEIPTS_DIR.exists() or \
            len(list(archive.RECEIPTS_DIR.glob("run-*.json"))) < 50:
        pytest.skip("committed receipts not present")
    out = render_index()
    assert "the stuck-pointer era" in out and "PR #77" in out
    assert "the livelock era" in out and "PR #97" in out
    # The labels sit on bands, not loose in the page.
    assert out.count('<details class="era"') >= 2


def test_era_note_appears_iff_a_band_exists():
    """(e) The bundling disclosure rides exactly when a band does."""
    banded = [_synthetic_run(f"2026-06-0{d}") for d in (4, 3, 2, 1)]
    flat = banded[:3]
    note = "Repeated-run eras are bundled"
    assert note in render_index(runs=banded)
    assert note not in render_index(runs=flat)


def test_banded_render_keeps_the_unbundled_row_count():
    """(f) The no-deletion proof: banded rows + plain rows == unbundled rows.

    Run on the real committed data when present (the strongest form), else on
    a synthetic mix of streaks and singletons.
    """
    if archive.RECEIPTS_DIR.exists() and \
            len(list(archive.RECEIPTS_DIR.glob("run-*.json"))) >= 50:
        runs = archive.public_runs()
    else:
        runs = (
            [_synthetic_run(f"2026-06-1{d}") for d in (5, 4, 3, 2)]
            + [_synthetic_run("2026-06-11", milestone="M03")]
            + [_synthetic_run(f"2026-06-0{d}", milestone="M02", verdict="null")
               for d in (9, 8, 7, 6, 5)]
        )
    banded = render_index(runs=runs, era_min_streak=archive.ERA_MIN_STREAK)
    unbundled = render_index(runs=runs, era_min_streak=None)
    assert banded.count('id="run-') == unbundled.count('id="run-') == len(runs)
    assert '<details class="era"' not in unbundled


def test_none_milestone_rows_never_band():
    """Unfiled/unreadable rows share an UNKNOWN identity, not a common one."""
    runs = [
        {**_synthetic_run(f"2026-06-0{d}"), "milestone": None}
        for d in (5, 4, 3, 2, 1)
    ]
    out = render_index(runs=runs)
    assert '<details class="era"' not in out
    assert out.count('id="run-') == 5


# ── the attempt ledger: which field-unknowns have a receipt behind them ──────
#
# G01's attempt condition used to be a case-sensitive substring search for
# "ATTEMPTED" in a markdown line the grading agent writes. These tests pin the
# replacement: a join between the catalogue's own ``crosses_the_gate`` verdict
# and the committed receipts, with every receipt re-derived through
# ``checks.check_hypothesis`` rather than believed. Hermetic — the catalogue is
# patched alongside the receipts directory, so nothing here reads the real
# UNKNOWNS.md or the real 196-receipt ledger.

def _unknown(**over):
    from lab import unknowns as U
    base = dict(id="U-X01", track="X", question="q?", why_open="w",
                known_to_whom=U.FIELD, who_would_care="us",
                feasibility_test="cheap", if_out_of_reach="buy more",
                status=U.CHARTED, reach=U.IN_REACH)
    base.update(over)
    return U.Unknown(**base)


def _patch_catalogue(monkeypatch, *entries):
    """Point BOTH readers of the catalogue at a fixture.

    ``attempt_ledger`` reads it for the gate join and ``check_hypothesis`` reads
    it again to confirm a DISCOVER receipt cites an id that exists, so a test
    patching only one would be grading half a fixture against the real estate.
    """
    from lab import unknowns as U
    cat = list(entries) or [_unknown()]
    monkeypatch.setattr(U, "load", lambda *a, **kw: list(cat))
    return cat


def _finding_receipt(verdict="unresolved", observations=1, stage="discover",
                     unknown_id="U-X01", **over):
    """A receipt in the shape a real run files — built by the real constructors.

    Deliberately NOT a hand-written dict: every derived string on a receipt is
    recomputed by the checker, so a fixture that authored its own headline would
    be testing the checker's patience rather than the ledger's join. ``over``
    is how a test forges one field AFTER the honest receipt exists.
    """
    from lab.hypothesis import Finding, Hypothesis
    hyp = Hypothesis(id=unknown_id, track="X", stage=stage,
                     unknown_id=unknown_id if stage == "discover" else "",
                     question="does the sector hold one?",
                     why_unanswered="nobody has looked with this instrument",
                     observable="a number", kill_condition="if it disagrees",
                     cheapest_decisive="an afternoon",
                     why_this_might_be_nothing="it is probably empty")
    obs = {f"evidence/observations/run/{i}.csv":
           {"path": f"evidence/observations/run/{i}.csv", "sha256": "0" * 64,
            "n_bytes": 12, "kind": "external-fetch"}
           for i in range(observations)}
    report = Finding(hypothesis=hyp, verdict=verdict, detail="d",
                     new_observations=obs).to_report()
    report.update(over)
    return report


def _write_receipt(receipts, name, payload):
    receipts.mkdir(parents=True, exist_ok=True)
    path = receipts / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_receipt_that_went_outside_is_an_attempt(tmp_path, monkeypatch):
    """The happy path, and the only shape that can close G01: a DISCOVER run
    citing a live field unknown, carrying observations that did not exist when
    the question was asked, under a verdict that is not a re-reading."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json",
                   _finding_receipt(verdict="killed", observations=2))
    led = archive.attempt_ledger()
    assert [a["unknown_id"] for a in led["attempts"]] == ["U-X01"]
    assert led["attempts"][0]["receipt"] == "run-2026-09-03-0100-u-x01.json"
    assert led["attempts"][0]["verdict"] == "killed"
    assert led["attempts"][0]["observations"] == 2
    assert led["refused"] == [] and led["undecidable"] == [] and not led["error"]


def test_a_re_analysis_is_not_an_attempt_and_is_not_a_fault(tmp_path, monkeypatch):
    """U-A01's committed receipt in miniature. Re-reading the archive with
    better statistics is real work — it put a measured false-alarm price on 173
    crossings — and it is not a crossing of the gate. It counts as nothing, and
    it is filed as nothing wrong."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json",
                   _finding_receipt(verdict="reanalysed", observations=0))
    led = archive.attempt_ledger()
    assert led["attempts"] == []
    assert led["refused"] == [] and led["unreadable"] == []


def test_a_re_analysis_carrying_observations_is_refused(tmp_path, monkeypatch):
    """The contradiction closed in hypothesis.py, seen from the ledger.

    ``reanalysed`` MEANS "consumed only committed bytes". A receipt wearing that
    label while recording new observations is an attempt hiding under the one
    verdict exempt from being counted as one — the 2026-08-25 failure with its
    sign flipped — and the constructor now refuses to rebuild it.
    """
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    payload = _finding_receipt(verdict="reanalysed", observations=0)
    payload["new_observations"] = {"evidence/observations/run/0.csv": {
        "path": "evidence/observations/run/0.csv", "sha256": "0" * 64,
        "n_bytes": 12, "kind": "external-fetch"}}
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json", payload)
    led = archive.attempt_ledger()
    assert led["attempts"] == []
    assert len(led["refused"]) == 1
    assert "terminus" in led["refused"][0]["why"]


def test_a_discovery_verdict_with_no_observations_is_refused(tmp_path, monkeypatch):
    """The 2026-08-25 failure itself: a claim about the world from a run that
    never went outside. It fails here even though the receipt reads pass."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    payload = _finding_receipt(verdict="killed", observations=1)
    payload["new_observations"] = {}
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json", payload)
    led = archive.attempt_ledger()
    assert led["attempts"] == [] and len(led["refused"]) == 1


def test_an_authored_headline_is_refused(tmp_path, monkeypatch):
    """Nothing on a receipt is believed, including the prose a reader sees. A
    headline edited after the run no longer matches what its own verdict
    produces, and a ledger that trusted it would be the substring search again
    with a JSON key instead of a markdown line."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json",
                   _finding_receipt(headline="U-X01 crossed the gate"))
    led = archive.attempt_ledger()
    assert led["attempts"] == []
    assert "headline" in led["refused"][0]["why"]


def test_a_stage_flipped_to_discovery_is_refused(tmp_path, monkeypatch):
    """A calibration run relabelled as discovery cannot be rebuilt: DISCOVER is
    not self-declarable, so the flipped receipt names no catalogued unknown and
    the constructor refuses it before the ledger has to notice."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    payload = _finding_receipt(verdict="unresolved", observations=1,
                               stage="calibrate", unknown_id="H99")
    payload["hypothesis"]["stage"] = "discover"
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-h99.json", payload)
    led = archive.attempt_ledger()
    assert led["attempts"] == []
    assert "contract" in led["refused"][0]["why"]


def test_an_attempt_that_does_not_cross_the_gate_is_not_counted(
        tmp_path, monkeypatch):
    """The join is against the CATALOGUE's verdict on the unknown, not the
    receipt's opinion of itself. A sound run against a `us` unknown is
    calibration and cannot close a discovery goal — and it is not a gap either,
    so it lands in no bucket at all."""
    from lab import unknowns as U
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch, _unknown(known_to_whom=U.US))
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json",
                   _finding_receipt())
    led = archive.attempt_ledger()
    assert led["attempts"] == [] and led["refused"] == []


def test_a_retired_unknown_cannot_be_attempted(tmp_path, monkeypatch):
    """Retirement removes an unknown from every denominator; it has to remove it
    from the numerator too, or a retired entry with an old receipt behind it
    would go on meeting the goal from beyond the grave."""
    from lab import unknowns as U
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch, _unknown(status=U.RETIRED))
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json",
                   _finding_receipt())
    assert archive.attempt_ledger()["attempts"] == []


def test_a_receipt_predating_the_contract_is_undecidable_never_a_pass(
        tmp_path, monkeypatch):
    """The committed H01 receipt's shape: written before ``stage`` existed. It
    cannot be graded under today's rule, which is an honest gap and is published
    as one — failing an old entry against a new standard is honest, calling it
    fraud is not, and calling it a pass is neither."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    payload = _finding_receipt()
    del payload["hypothesis"]["stage"]
    _write_receipt(reports / "receipts", "run-2026-08-24-1109-h01.json", payload)
    led = archive.attempt_ledger()
    assert led["attempts"] == [] and led["refused"] == []
    assert len(led["undecidable"]) == 1
    assert "predates" in led["undecidable"][0]["why"]


def test_an_unparseable_receipt_is_a_named_gap_not_a_crash(tmp_path, monkeypatch):
    """Corrupt bytes are kept as a row here for the reason the index keeps them
    as a row: a run that vanishes because its JSON broke is a run the ledger
    silently stopped counting."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    (reports / "receipts").mkdir(parents=True)
    (reports / "receipts" / "run-2026-09-03-0100-u-x01.json").write_text(
        "{not json", encoding="utf-8")
    led = archive.attempt_ledger()
    assert [r["receipt"] for r in led["unreadable"]] == \
           ["run-2026-09-03-0100-u-x01.json"]
    assert led["attempts"] == [] and not led["error"]


def test_calibration_receipts_are_not_gaps(tmp_path, monkeypatch):
    """194 of the 196 committed receipts carry no hypothesis block. They never
    claimed to attempt anything, so filing them as gaps would bury the two rows
    that matter under the whole ladder."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-m01.json",
                   {"experiment": "M01-ising-verification", "status": "pass"})
    assert archive.attempt_ledger() == {
        "attempts": [], "undecidable": [], "refused": [], "unreadable": [],
        "error": ""}


def test_the_receipts_directory_is_resolved_through_the_publish_module(
        tmp_path, monkeypatch):
    """The bug this landed one attribute lookup away from.

    ``archive`` binds ``RECEIPTS_DIR`` by value at import, and every fixture in
    tests/test_publish.py repoints ``publish.RECEIPTS_DIR`` and not this
    module's copy. A grader reading the bound name would therefore sit inside a
    ``tmp_path`` test and grade the real 196-receipt ledger — passing for
    entirely the wrong reason, and saying nothing about the fixture it was asked
    to read. So this test patches ONLY the publish module, exactly as
    test_publish does, and leaves the archive's stale copy pointing at the live
    estate.
    """
    from lab import unknowns as U
    receipts = tmp_path / "elsewhere" / "receipts"
    monkeypatch.setattr(publish, "RECEIPTS_DIR", receipts)
    monkeypatch.setattr(U, "load", lambda *a, **kw: [_unknown()])
    _write_receipt(receipts, "run-2026-09-03-0100-u-x01.json", _finding_receipt())
    led = archive.attempt_ledger()
    assert [a["receipt"] for a in led["attempts"]] == \
           ["run-2026-09-03-0100-u-x01.json"]
    assert archive.RECEIPTS_DIR != receipts     # the stale bound name, unpatched


def test_a_missing_receipts_directory_is_empty_not_broken(tmp_path, monkeypatch):
    """A checkout with no receipts has attempted nothing. That is a fact about
    the lab, not an error about the box."""
    monkeypatch.setattr(publish, "RECEIPTS_DIR", tmp_path / "no-such-dir")
    _patch_catalogue(monkeypatch)
    assert archive.attempt_ledger() == {
        "attempts": [], "undecidable": [], "refused": [], "unreadable": [],
        "error": ""}


def test_no_gap_the_ledger_publishes_carries_this_box_s_disk(
        tmp_path, monkeypatch):
    """These strings are PUBLISHED, so they answer to the public feed's rules.

    ``goal.progress()`` copies every gap row into ``attempt_ledger_gaps`` in
    ``pot.json``, which is committed and which the windowsill page reads. Today
    that file contains no absolute local path anywhere — ``_public_href`` keeps
    links to http(s) for exactly this reason, after a ``file:///home/...`` link
    once reached the archive index.

    ``OSError`` renders the absolute filename it touched, so a receipt the
    publishing box cannot open (a lock, a permission, a directory where a file
    should be) put ``C:\\Users\\<name>\\...`` one publish away from a public
    repo. Demonstrated on 2026-09-04 before ``_why`` existed. The receipt is
    already named in the row; the box's disk adds nothing a reader wants.
    """
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    receipts = reports / "receipts"
    receipts.mkdir(parents=True)
    # A directory where a receipt should be: read_text raises OSError, and the
    # message it carries is the whole absolute path.
    (receipts / "run-2026-09-03-0100-u-x01.json").mkdir()
    led = archive.attempt_ledger()
    why = led["unreadable"][0]["why"]
    assert "run-2026-09-03-0100-u-x01.json" in led["unreadable"][0]["receipt"]
    assert str(tmp_path) not in why, f"the publishing box's disk is in the feed: {why}"
    assert ":\\" not in why and "/" not in why, why
    assert why != "receipt will not parse: ", "the reason was dropped, not cleaned"


def test_the_ledger_never_raises_and_fails_closed(tmp_path, monkeypatch):
    """``publish.py`` wraps the goal block in a bare ``except Exception: pass``
    that DELETES the goal key from pot.json — so an exception here does not fail
    a publish, it silently blanks the lab's public commitment from a pass that
    exits 0. A ledger this box cannot read must therefore return, with no
    attempts and the reason attached: a broken ledger cannot MEET the goal."""
    from lab import unknowns as U
    _patch(tmp_path, monkeypatch)

    def boom(*a, **kw):
        raise RuntimeError("UNKNOWNS.md is malformed")

    monkeypatch.setattr(U, "load", boom)
    led = archive.attempt_ledger()
    assert led["attempts"] == []
    assert "UNKNOWNS.md is malformed" in led["error"]


def test_a_discovery_run_that_could_not_get_its_data_is_not_an_attempt(
        tmp_path, monkeypatch):
    """The one legal shape the constructor lets through and only this stops.

    ``Finding`` refuses SUPPORTED and KILLED without observations, but it
    deliberately does NOT refuse UNRESOLVED: that verdict is the ABSENCE of a
    claim, and a DISCOVER runner which could not obtain its data at all has to
    be able to say so — the permission is written into
    ``attempted_the_question``'s docstring on purpose, and it is right. So this
    receipt is legal, re-derives cleanly through every check in
    ``check_hypothesis``, cites a live field unknown, and the ONLY thing between
    it and closing G01 is this ledger recomputing the terminus from the
    observations. The neighbouring test above uses ``killed``, which the
    constructor rejects one layer earlier and files as ``refused`` — so it never
    reaches this line. A run that never went outside is not an attempt, and it
    is not a fault either: it lands in no bucket.
    """
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json",
                   _finding_receipt(verdict="unresolved", observations=0))
    led = archive.attempt_ledger()
    assert led["attempts"] == []
    assert led["refused"] == [] and led["undecidable"] == []
    assert led["unreadable"] == [] and not led["error"]


def test_the_terminus_is_recomputed_even_when_the_receipt_does_not_state_it(
        tmp_path, monkeypatch):
    """``attempt_ledger``'s strongest sentence, made checkable.

    Its docstring promises the terminus is recomputed from ``stage`` +
    ``new_observations`` and "never read off ``attempted_the_question``, because
    a receipt asserting its own attempt status is the substring search again
    with a JSON key instead of a markdown line". Every other test in this group
    holds either way: ``check_hypothesis`` already refuses a receipt whose
    STATED flag disagrees with its re-derived one, so on a receipt carrying the
    field the two readings cannot differ, and swapping the recomputation for
    ``report.get("attempted_the_question")`` passed all 58 of them (checked
    2026-09-04, by doing it).

    They differ on a receipt that OMITS the field: ``check_hypothesis`` treats
    the absence as no contradiction rather than a fault, so a grader reading the
    key would drop a real attempt on the floor and publish OPEN over a crossing
    that happened. This is the test that notices — which is what makes the
    recomputation load-bearing rather than a sentence about itself.
    """
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    payload = _finding_receipt(verdict="killed", observations=1)
    del payload["attempted_the_question"]
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-u-x01.json",
                   payload)
    led = archive.attempt_ledger()
    assert [a["unknown_id"] for a in led["attempts"]] == ["U-X01"]
    assert led["refused"] == [] and led["undecidable"] == []


def test_a_calibration_run_citing_a_field_unknown_is_not_an_attempt(
        tmp_path, monkeypatch):
    """``stage`` is load-bearing here, not decorative.

    The contract only *requires* an ``unknown_id`` of DISCOVER; a calibrate
    hypothesis may carry one. So a calibration run that fetched fresh bytes
    while citing a field entry re-derives cleanly, is not tampering, and clears
    the gate join — the stage is the only thing left saying it audited our own
    arithmetic rather than going and looking. The flipped-stage test above
    covers a receipt EDITED to say discovery; this one is honest and still must
    not count.
    """
    from lab.hypothesis import Finding, Hypothesis
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    hyp = Hypothesis(id="H99", track="X", stage="calibrate",
                     unknown_id="U-X01",
                     question="is our own arithmetic right?",
                     why_unanswered="nobody has re-derived it",
                     observable="a number", kill_condition="if it disagrees",
                     cheapest_decisive="an afternoon",
                     why_this_might_be_nothing="it is probably fine")
    obs = {"evidence/observations/run/0.csv":
           {"path": "evidence/observations/run/0.csv", "sha256": "0" * 64,
            "n_bytes": 12, "kind": "external-fetch"}}
    _write_receipt(reports / "receipts", "run-2026-09-03-0100-h99.json",
                   Finding(hypothesis=hyp, verdict="unresolved", detail="d",
                           new_observations=obs).to_report())
    led = archive.attempt_ledger()
    assert led["attempts"] == []
    assert led["refused"] == [] and led["undecidable"] == []


def test_bytes_that_break_the_parser_are_one_gap_not_a_blanked_ledger(
        tmp_path, monkeypatch):
    """One unreadable receipt must cost one ROW, not the whole ledger.

    Fail-closed is the right direction for a ledger nobody can read, and the
    wrong answer for one file in a hundred: the outer handler CLEARS
    ``attempts``, so a failure that escapes the per-receipt catch silently
    deletes real attempts from the public feed and names no culprit — while
    this module's own comment promises a gap instead.

    ``json.loads`` is the live route to exactly that. Deeply nested bytes raise
    ``RecursionError``, which is neither ``OSError`` nor ``ValueError``; caught
    only by those two (as it was until 2026-09-04), the receipt below wiped the
    attempt above it and reported ``unreadable == []``. Verified in that
    direction before the widening landed.
    """
    reports, _ = _patch(tmp_path, monkeypatch)
    _patch_catalogue(monkeypatch)
    receipts = reports / "receipts"
    _write_receipt(receipts, "run-2026-09-03-0100-u-x01.json",
                   _finding_receipt(verdict="killed", observations=2))
    (receipts / "run-2026-09-03-0200-u-x01.json").write_text(
        "[" * 20_000 + "]" * 20_000, encoding="utf-8")
    led = archive.attempt_ledger()
    assert [a["receipt"] for a in led["attempts"]] == \
           ["run-2026-09-03-0100-u-x01.json"], \
        "one unparseable receipt erased an attempt that had already been read"
    assert [r["receipt"] for r in led["unreadable"]] == \
           ["run-2026-09-03-0200-u-x01.json"]
    assert "RecursionError" in led["unreadable"][0]["why"]
    assert not led["error"]
