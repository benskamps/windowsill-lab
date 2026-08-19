"""ExoFOP CTOI crosscheck tests — the third catalog, offline.

Every test here passes an explicit ``table``, so nothing touches the network:
the parsing, the alias arithmetic and the verdict logic are the parts that can
be wrong, and none of them need a live endpoint to be graded. The two rows in
the fixture are the real 2019 filings on TIC 287328866, copied from the ExoFOP
CSV — the case that opened the hole.
"""
from __future__ import annotations

import json
import time

import pytest

from lab import exofop


HEADER = ("TIC ID,CTOI,Promoted to TOI,Discovery Data Source,Candidate Name,"
          "MASTER,SG1A,SG1B,SG2,SG3,SG4,SG5,User Disposition,"
          "TFOPWG Disposition,TESS Mag,TESS Mag err,RA,Dec,PM RA (mas/yr),"
          "PM RA err (mas/yr),PM Dec (mas/yr),PM Dec err (mas/yr),"
          "Transit Epoch (BJD),Transit Epoch (BJD) err,Period (days),"
          "Period (days) Error,Depth mmag,Depth mmag Error,Depth ppm,"
          "Depth ppm Error,Duration (hrs),Duration (hrs) Error")


def _row(tic, ctoi, period, depth_ppm, duration):
    cells = [""] * 32
    cells[0], cells[1] = str(tic), str(ctoi)
    cells[24], cells[28], cells[30] = str(period), str(depth_ppm), str(duration)
    return ",".join(cells)


CSV = "\n".join([
    HEADER,
    _row(287328866, "287328866.01", 2.063194, 11876.256862818, 2.7),
    _row(287328866, "287328866.02", 2.079861, 17497.7116893515, 2.53333333333333),
    _row(11111111, "11111111.01", 4.9, 900.0, 3.1),
    "not-a-tic,junk.01,,,,,,,,,,,,,,,,,,,,,,,1.0,,,,100,,1.0,",
]) + "\n"


@pytest.fixture(scope="module")
def table():
    return exofop.parse_ctoi_csv(CSV)


# ------------------------------------------------------------------ parsing ---

def test_parse_groups_rows_by_tic(table):
    assert set(table) == {"287328866", "11111111"}
    assert len(table["287328866"]) == 2


def test_parse_reads_the_fields_the_gate_uses(table):
    rows = sorted(table["287328866"], key=lambda r: r["period_days"])
    assert rows[0]["ctoi"] == "287328866.01"
    assert rows[0]["period_days"] == pytest.approx(2.063194)
    assert rows[0]["depth_ppm"] == pytest.approx(11876.26, rel=1e-4)
    assert rows[1]["duration_hours"] == pytest.approx(2.5333, rel=1e-3)


def test_parse_drops_rows_whose_tic_will_not_parse(table):
    """A malformed line must not become a phantom candidate under a junk key."""
    assert all(k.isdigit() for k in table)


def test_parse_survives_an_empty_table():
    assert exofop.parse_ctoi_csv(HEADER + "\n") == {}


# ---------------------------------------------------------------- alias math ---

def test_alias_match_finds_a_direct_match():
    assert exofop.alias_match(2.063, 2.063194) == 1


def test_alias_match_finds_the_p_over_2_case():
    """The one that bit: detected at half the filed period."""
    assert exofop.alias_match(1.0382373, 2.063194) == 2


def test_alias_match_finds_the_other_direction():
    assert exofop.alias_match(4.126, 2.063) == -2


def test_alias_match_rejects_an_unrelated_period():
    assert exofop.alias_match(3.7, 2.063194) is None


def test_alias_match_respects_the_tolerance_from_both_sides():
    tol = exofop.PERIOD_TOL_FRAC
    assert exofop.alias_match(2.0 * (1 + 0.5 * tol), 2.0) == 1
    assert exofop.alias_match(2.0 * (1 + 2 * tol), 2.0) is None


def test_alias_match_handles_zero_and_none():
    assert exofop.alias_match(0.0, 2.0) is None
    assert exofop.alias_match(2.0, None) is None


# ----------------------------------------------------------------- crosscheck ---

def test_crosscheck_finds_the_star_that_opened_the_hole(table):
    out = exofop.ctoi_crosscheck("287328866", 1.0382373, table=table)
    assert out["known_ctoi"] in ("287328866.01", "287328866.02")
    assert out["ctoi_alias_n"] == 2
    assert out["n_ctoi"] == 2
    assert len(out["matched_rows"]) == 2


def test_crosscheck_prefers_a_direct_match_over_an_alias(table):
    out = exofop.ctoi_crosscheck("287328866", 2.063194, table=table)
    assert out["ctoi_alias_n"] == 1
    assert out["known_ctoi"] == "287328866.01"


def test_crosscheck_reports_ctois_even_when_none_match_the_period(table):
    """Two entries on one star is a tell in itself — never hide the count."""
    out = exofop.ctoi_crosscheck("287328866", 11.7, table=table)
    assert out["known_ctoi"] is None
    assert out["n_ctoi"] == 2


def test_crosscheck_is_silent_on_a_star_with_no_ctoi(table):
    out = exofop.ctoi_crosscheck("999999999", 3.0, table=table)
    assert out["known_ctoi"] is None
    assert out["n_ctoi"] == 0
    assert out["lookup_error"] is None


def test_crosscheck_without_a_period_reports_rows_but_matches_nothing(table):
    out = exofop.ctoi_crosscheck("287328866", None, table=table)
    assert out["n_ctoi"] == 2
    assert out["known_ctoi"] is None


def test_crosscheck_reports_a_lookup_failure_instead_of_a_clean_negative(monkeypatch):
    """An outage must never read as 'no community candidate'."""
    def boom(*a, **k):
        raise OSError("exofop down")
    monkeypatch.setattr(exofop, "fetch_ctoi_csv", boom)
    out = exofop.ctoi_crosscheck("287328866", 1.038)
    assert out["lookup_error"] == "OSError"
    assert out["known_ctoi"] is None
    assert out["n_ctoi"] == 0


# ---------------------------------------------------------------- cache age ---

def test_cache_age_is_none_without_a_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(exofop, "CTOI_META", tmp_path / "absent.json")
    assert exofop.cache_age_days() is None


def test_cache_age_is_measured_in_days(tmp_path, monkeypatch):
    meta = tmp_path / "ctoi.meta.json"
    meta.write_text(json.dumps({"fetched_unix": time.time() - 3 * 86400}))
    monkeypatch.setattr(exofop, "CTOI_META", meta)
    assert exofop.cache_age_days() == pytest.approx(3.0, abs=0.01)


def test_a_corrupt_meta_file_reads_as_unknown_age_not_zero(tmp_path, monkeypatch):
    """Unknown age must not masquerade as a freshly fetched table."""
    meta = tmp_path / "ctoi.meta.json"
    meta.write_text("{not json")
    monkeypatch.setattr(exofop, "CTOI_META", meta)
    assert exofop.cache_age_days() is None


def test_a_stale_cache_is_served_when_the_refresh_fails(tmp_path, monkeypatch):
    """A fortnight-old answer beats no answer — the age is reported alongside."""
    csv_path, meta = tmp_path / "ctoi.csv", tmp_path / "ctoi.meta.json"
    csv_path.write_text(CSV, encoding="utf-8")
    meta.write_text(json.dumps({"fetched_unix": time.time() - 99 * 86400}))
    monkeypatch.setattr(exofop, "CTOI_CSV", csv_path)
    monkeypatch.setattr(exofop, "CTOI_META", meta)
    from lab import a01
    monkeypatch.setattr(a01, "_request", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    text = exofop.fetch_ctoi_csv()
    assert "287328866.01" in text
