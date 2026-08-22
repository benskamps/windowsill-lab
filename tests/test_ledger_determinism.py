"""DET-2 — the committed feed is a pure function of the repo, not of mtimes.

``scan_runs`` ordered the ledger newest-first by **file mtime as the primary
key**. Nothing in a git repository preserves mtimes: a clone stamps every file
with the checkout time, and ``git pull`` re-stamps whatever it touched. So two
boxes holding byte-identical repo content regenerated ``pot.json`` in different
orders, each saw the other's feed as "changed", and each committed its own —
the structural root of the 7/31 double-conflict, the 8/05 stranding and the
8/08-11 freeze. Every unwedge script in this repo treats that symptom.

The fix keys the order on the run's own content: ``(date, turn, at, slug)``,
with no mtime term anywhere — not in the sort, and not in the same-key
tiebreak that decides WHICH file becomes a row.

The headline is ``test_pot_regeneration_is_byte_identical_under_mtime_shuffle``:
build a fixture, regenerate the feed, shuffle every mtime, regenerate again,
compare the bytes. It fails on the unfixed tree.

The two inputs that are legitimately not repo content — the ``updated`` stamp
and the CPU temperature — are frozen here on purpose. This test is about the
filesystem's timestamps; freezing the honest clocks is what makes the
dishonest one visible.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from lab import archive, publish


FROZEN = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN if tz else FROZEN.replace(tzinfo=None)


def _freeze(monkeypatch):
    """Pin the feed's two honest non-repo inputs: the clock and the thermometer."""
    monkeypatch.setattr(publish, "datetime", _FrozenDatetime)
    monkeypatch.setattr(publish, "cpu_temp_c", lambda: 41.0)
    monkeypatch.setattr(publish, "provenance", lambda: {"machine": "fixture-box"})


def _patch_dirs(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    receipts = reports / "receipts"
    lab_home = tmp_path / "lab"
    for mod in (archive, publish):
        monkeypatch.setattr(mod, "REPORTS_DIR", reports)
        monkeypatch.setattr(mod, "RECEIPTS_DIR", receipts)
        monkeypatch.setattr(mod, "LAB_HOME", lab_home)
    receipts.mkdir(parents=True)
    lab_home.mkdir(parents=True)
    return reports, receipts, lab_home


def _run(reports, receipts, date, slug, turn, at, headline):
    """One run on the books: a dated report plus its turn-stamped receipt.

    The experiment id is derived from the slug because ``publish._slug_for``
    reads the slug out of the run's CONTENT, not its filename — a fixture whose
    two disagree grows phantom rows and stops meaning what it looks like.
    """
    payload = {
        "experiment": slug.upper() + "-fixture-run",
        "T": [2.2, 2.3, 2.4], "chi": [1.0, 9.0, 1.0],
        "wall_seconds": 35.0, "headline": headline,
        "generated_at": at,
        "provenance": {"machine": "fixture-box"},
    }
    (reports / (date + "-" + slug + ".json")).write_text(
        json.dumps(payload), encoding="utf-8")
    (receipts / ("run-" + date + "-" + turn + "-" + slug + ".json")).write_text(
        json.dumps(payload), encoding="utf-8")


def _fixture(reports, receipts):
    """Runs a clone can order only from content — never from mtimes.

    Two dates, two turns inside one of them, and two DIFFERENT milestones
    sharing one ``(date, turn)`` so the content-id tiebreak is actually
    exercised rather than assumed.
    """
    _run(reports, receipts, "2026-08-19", "m01", "0700",
         "2026-08-19T07:00:00+00:00", "the oldest run")
    _run(reports, receipts, "2026-08-20", "m01", "0700",
         "2026-08-20T07:00:00+00:00", "first turn of the 20th")
    _run(reports, receipts, "2026-08-20", "m03", "1900",
         "2026-08-20T19:00:00+00:00", "second turn of the 20th")
    _run(reports, receipts, "2026-08-21", "m01", "0700",
         "2026-08-21T07:00:00+00:00", "same turn, different milestone (a)")
    _run(reports, receipts, "2026-08-21", "m03", "0700",
         "2026-08-21T07:05:00+00:00", "same turn, different milestone (b)")


def _stamp_all(root, mtimes):
    """Re-stamp every file under ``root`` — what a clone or a pull does."""
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    for path, mtime in zip(paths, mtimes):
        os.utime(path, (mtime, mtime))
    return len(paths)


def _pot_bytes():
    """Exactly what ``publish.publish`` commits: the publisher's own bytes."""
    return (json.dumps(publish.collect(), indent=2) + "\n").encode("utf-8")


def _order(rows):
    return [(r["date"], r.get("turn"), r["slug"]) for r in rows]


# ── the headline: same repo content, two mtime arrangements, one feed ────────

def test_pot_regeneration_is_byte_identical_under_mtime_shuffle(tmp_path, monkeypatch):
    reports, receipts, lab_home = _patch_dirs(tmp_path, monkeypatch)
    _freeze(monkeypatch)
    _fixture(reports, receipts)

    # Box A: stamped ascending, as a sequential checkout leaves them.
    n = _stamp_all(reports, [1_700_000_000 + 60 * i for i in range(64)])
    first = _pot_bytes()

    # Box B: identical repo CONTENT, every mtime re-stamped the other way round
    # — precisely what a ``git pull`` on the other box produces.
    _stamp_all(reports, [1_700_000_000 + 60 * (n - i) for i in range(64)])
    second = _pot_bytes()

    sha_first = hashlib.sha256(first).hexdigest()
    sha_second = hashlib.sha256(second).hexdigest()
    assert sha_first == sha_second, (
        "pot.json is not a pure function of repo content — the two boxes "
        "regenerate different feeds:\n"
        "  run 1 sha256 " + sha_first + "\n"
        "  run 2 sha256 " + sha_second + "\n"
        "  run 1 order  " + str([r["headline"] for r in json.loads(first)["reports"]]) + "\n"
        "  run 2 order  " + str([r["headline"] for r in json.loads(second)["reports"]])
    )
    assert first == second


# ── the same property one layer down, where the ordering actually lives ──────

def test_scan_runs_order_is_independent_of_mtimes(tmp_path, monkeypatch):
    reports, receipts, lab_home = _patch_dirs(tmp_path, monkeypatch)
    _fixture(reports, receipts)

    _stamp_all(reports, [1_700_000_000 + 60 * i for i in range(64)])
    ascending = _order(archive.scan_runs())
    _stamp_all(reports, [1_700_000_000 + 60 * (64 - i) for i in range(64)])
    descending = _order(archive.scan_runs())
    # A third arrangement: every file stamped the SAME second, as a fresh clone
    # leaves them — the case the old key papered over with its date fallback.
    _stamp_all(reports, [1_700_000_000] * 64)
    flat = _order(archive.scan_runs())

    assert ascending == descending == flat


def test_scan_runs_is_newest_first_by_date_then_turn(tmp_path, monkeypatch):
    """The order the ledger claims: newest date first, latest turn of it first."""
    reports, receipts, lab_home = _patch_dirs(tmp_path, monkeypatch)
    _fixture(reports, receipts)
    order = [(r["date"], r.get("turn")) for r in archive.scan_runs()]
    assert order[0][0] == "2026-08-21"
    assert order[-1] == ("2026-08-19", "0700")
    assert order == sorted(order, key=lambda k: (k[0], k[1] or ""), reverse=True)


def test_same_key_file_choice_is_independent_of_mtimes(tmp_path, monkeypatch):
    """Which of two files becomes the row must not depend on which was touched last.

    The sort was the headline mtime term, but not the only one: when two files
    in one directory resolve to a single ``(date, slug, turn)`` key, the newest
    mtime used to win — so the row's CONTENT, not just its position, moved
    between boxes.
    """
    reports, receipts, lab_home = _patch_dirs(tmp_path, monkeypatch)
    payload = {
        "experiment": "M01-ising-verification",
        "T": [2.2, 2.3, 2.4], "chi": [1.0, 9.0, 1.0], "wall_seconds": 35.0,
        "generated_at": "2026-08-21T07:00:00+00:00",
    }
    bare = reports / "2026-08-21.json"
    perrun = reports / "2026-08-21-m01.json"
    bare.write_text(json.dumps({**payload, "headline": "bare legacy dump"}),
                    encoding="utf-8")
    perrun.write_text(json.dumps({**payload, "headline": "the per-run file"}),
                      encoding="utf-8")

    os.utime(bare, (2_000_000_000, 2_000_000_000))
    os.utime(perrun, (1_000_000_000, 1_000_000_000))
    one = [r.get("headline") for r in archive.scan_runs()]
    os.utime(bare, (1_000_000_000, 1_000_000_000))
    os.utime(perrun, (2_000_000_000, 2_000_000_000))
    two = [r.get("headline") for r in archive.scan_runs()]

    assert one == two
