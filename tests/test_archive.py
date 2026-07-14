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

def test_scan_runs_newest_first_by_mtime_not_date_string(tmp_path, monkeypatch):
    """A stale FUTURE-dated file written earlier must NOT lead (the test_publish
    trap): newest-first is keyed on (mtime, date_stem)."""
    reports, lab_home = _patch(tmp_path, monkeypatch)
    _write_report(lab_home, "2026-06-16", mtime=1000)   # higher date, OLDER write
    _write_report(lab_home, "2026-06-15", mtime=2000)   # lower date, NEWER write
    runs = scan_runs()
    assert runs[0]["date"] == "2026-06-15"              # the truly-newest run leads


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
    assert r["report_href"] == publish.ARCHIVE_URL + "#run-2026-06-15-m01"
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
    p = _write_report(lab_home, "2026-06-08-m01", mtime=500)
    rows = run_ledger()
    # A local file:// / bare-path href is NOT a public link → None (link-guard).
    for r in rows:
        assert r["href"] is None or r["href"].startswith("http")


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
    # ... and a local-only run still carries its dated JSON path for traceability.
    assert "2026-06-08" in html and "local report" in html


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
