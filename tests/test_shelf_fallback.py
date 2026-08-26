"""The no-JS fallback — what every crawler, search index and model actually reads.

The page fetches `pot.json` live, so a reader with JavaScript sees the truth.
Everyone else sees whatever is baked into the HTML, and on 2026-08-25 that had
been frozen since roughly June: **25 captured runs, 22 verified, 3 null**
against a live **28, 25, 2**. Fetching the public page returned the stale set,
which means the lab had been presenting a smaller version of itself to every
non-JS reader for two months.

The JS beside it carries the comment *"wire the shelf-hero counts from the live
data so they can't drift"* — true of the rendered values, and never true of the
fallback.
"""
from __future__ import annotations

import re

import pytest

from lab.publish import refresh_shelf_fallback, shelf_counts

HTML = ('<p><span id="shelf-total">1</span> captured runs'
        ' <span id="shelf-moss-count">1</span><span id="shelf-moss-plural">s</span>'
        ' <span id="shelf-amber-count">1</span><span id="shelf-amber-plural">s</span>'
        ' <span id="shelf-clay-count">1</span><span id="shelf-clay-plural">s</span></p>')


def _snap(milestones, reports=None):
    return {"milestones": milestones, "reports": reports or []}


def test_counts_come_from_MILESTONES_not_reports():
    """The bug this file exists for. `web/index.html:4636` filters MILESTONES by
    status; a first draft of the counter read `reports` by verdict and would
    have written 100 where the page means 28.

    That is not an off-by-something — the hero sentence is *"N captured runs,
    every one with a live explainer"*, and there are ~27 explainer rooms. The
    wrong list would have converted a stale number into an OVERCLAIM, which is
    strictly worse than being stale."""
    snap = _snap(
        milestones=[{"status": "verified"}, {"status": "verified"},
                    {"status": "null"}, {"status": "planned"}],
        reports=[{"verdict": "verified"}] * 90)          # a much larger list
    got = shelf_counts(snap)
    assert got == {"verified": 2, "review": 0, "null": 1, "total": 3}, got


def test_planned_and_unscored_milestones_are_excluded():
    """Total is verified + review + null, exactly as the page computes it. A
    planned rung is not a captured run."""
    got = shelf_counts(_snap([{"status": s} for s in
                              ("verified", "review", "null", "planned", "unscored")]))
    assert got["total"] == 3


def test_the_fallback_is_rewritten_in_place(tmp_path):
    p = tmp_path / "index.html"
    p.write_text(HTML, encoding="utf-8")
    out = refresh_shelf_fallback(
        _snap([{"status": "verified"}] * 25 + [{"status": "review"}]
              + [{"status": "null"}] * 2), p)
    assert out["updated"] is True and out["total"] == 28
    body = p.read_text(encoding="utf-8")
    assert '<span id="shelf-total">28</span>' in body
    assert '<span id="shelf-moss-count">25</span>' in body


def test_plurals_follow_the_count(tmp_path):
    """A page reading '1 runs remain in review' is a small thing that makes a
    reader trust nothing else on it."""
    p = tmp_path / "index.html"
    p.write_text(HTML, encoding="utf-8")
    refresh_shelf_fallback(_snap([{"status": "verified"}, {"status": "review"}]), p)
    body = p.read_text(encoding="utf-8")
    assert '<span id="shelf-amber-plural"></span>' in body, "review=1 must be singular"
    assert '<span id="shelf-moss-plural"></span>' in body, "verified=1 must be singular"


def test_a_missing_page_is_reported_not_raised(tmp_path):
    """The feed must never be blocked by the page."""
    out = refresh_shelf_fallback(_snap([]), tmp_path / "absent.html")
    assert out["updated"] is False and "not present" in out["reason"]


def test_rewriting_twice_is_a_no_op(tmp_path):
    p = tmp_path / "index.html"
    p.write_text(HTML, encoding="utf-8")
    snap = _snap([{"status": "verified"}] * 4)
    assert refresh_shelf_fallback(snap, p)["updated"] is True
    assert refresh_shelf_fallback(snap, p)["updated"] is False


def test_the_shipped_page_matches_the_shipped_feed():
    """Non-hermetic, and the one that would have caught the original drift: the
    committed HTML must agree with the committed feed."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    pot, page = root / "pot.json", root / "web" / "index.html"
    if not (pot.exists() and page.exists()):
        pytest.skip("not a full checkout")
    want = shelf_counts(json.loads(pot.read_text(encoding="utf-8")))
    body = page.read_text(encoding="utf-8")
    for span, key in (("shelf-total", "total"), ("shelf-moss-count", "verified"),
                      ("shelf-amber-count", "review"), ("shelf-clay-count", "null")):
        m = re.search(rf'<span id="{span}">([^<]*)</span>', body)
        assert m and m.group(1) == str(want[key]), (
            f"{span} says {m.group(1) if m else '?'}, feed says {want[key]}")
