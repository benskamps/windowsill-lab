"""DET-2, standalone: regenerate the feed twice with the mtimes shuffled.

Run it from the repo root:

    PYTHONPATH=src python docs/gauntlet/evidence/det2_regen_demo.py

Builds a fixture of five runs in a temp directory, regenerates the pot bytes,
re-stamps every file's mtime in the reverse order (what a ``git pull`` on the
other box does to a working tree), regenerates again, and prints the sha256 of
both. Exits 0 when the two runs agree.

Touches nothing in the repo: the fixture lives in a temp dir and the feed's two
honest non-repo inputs — the wall clock and the CPU thermometer — are pinned so
the only thing left that can move the bytes is the filesystem's timestamps.

Works unmodified at the pre-fix base, which is the point: it is the same
experiment on both trees.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lab import archive, publish


FROZEN = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN if tz else FROZEN.replace(tzinfo=None)


RUNS = [
    ("2026-08-19", "m01", "0700", "2026-08-19T07:00:00+00:00", "the oldest run"),
    ("2026-08-20", "m01", "0700", "2026-08-20T07:00:00+00:00", "first turn of the 20th"),
    ("2026-08-20", "m03", "1900", "2026-08-20T19:00:00+00:00", "second turn of the 20th"),
    ("2026-08-21", "m01", "0700", "2026-08-21T07:00:00+00:00", "same turn, milestone (a)"),
    ("2026-08-21", "m03", "0700", "2026-08-21T07:05:00+00:00", "same turn, milestone (b)"),
]


def build(reports: Path, receipts: Path) -> None:
    receipts.mkdir(parents=True, exist_ok=True)
    for date, slug, turn, at, headline in RUNS:
        # The slug is derived from the run's CONTENT (publish._slug_for), so
        # the experiment id has to agree with the filename or the fixture
        # invents phantom rows.
        payload = {
            "experiment": f"{slug.upper()}-fixture-run",
            "T": [2.2, 2.3, 2.4], "chi": [1.0, 9.0, 1.0],
            "wall_seconds": 35.0, "headline": headline, "generated_at": at,
            "provenance": {"machine": "fixture-box"},
        }
        text = json.dumps(payload)
        (reports / f"{date}-{slug}.json").write_text(text, encoding="utf-8")
        (receipts / f"run-{date}-{turn}-{slug}.json").write_text(text, encoding="utf-8")


def stamp(root: Path, reverse: bool) -> list[tuple[str, int]]:
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    base = 1_700_000_000
    stamps = []
    for i, path in enumerate(paths):
        mtime = base + 60 * (len(paths) - i if reverse else i)
        os.utime(path, (mtime, mtime))
        stamps.append((path.name, mtime))
    return stamps


def pot_bytes() -> bytes:
    return (json.dumps(publish.collect(), indent=2) + "\n").encode("utf-8")


def scan_order() -> list[str]:
    """The ledger's own order, before the feed collapses same-verdict streaks."""
    return [f"{r['date']} {r.get('turn') or '----'} {r['slug']}"
            for r in archive.scan_runs()]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="det2-regen-"))
    try:
        reports, receipts, lab_home = tmp / "reports", tmp / "reports" / "receipts", tmp / "lab"
        lab_home.mkdir(parents=True)
        for mod in (archive, publish):
            mod.REPORTS_DIR = reports
            mod.RECEIPTS_DIR = receipts
            mod.LAB_HOME = lab_home
        publish.datetime = _FrozenDatetime
        publish.cpu_temp_c = lambda: 41.0
        publish.provenance = lambda: {"machine": "fixture-box"}

        build(reports, receipts)

        first_stamps = stamp(reports, reverse=False)
        first, first_scan = pot_bytes(), scan_order()
        second_stamps = stamp(reports, reverse=True)
        second, second_scan = pot_bytes(), scan_order()

        print("fixture:", len(RUNS), "runs ->", len(first_stamps), "files in", tmp)
        print()
        print("run 1 mtimes (ascending, as a sequential checkout leaves them):")
        for name, mtime in first_stamps:
            print(f"    {mtime}  {name}")
        print()
        print("run 2 mtimes (reversed, as the other box's git pull leaves them):")
        for name, mtime in second_stamps:
            print(f"    {mtime}  {name}")
        print()
        sha1 = hashlib.sha256(first).hexdigest()
        sha2 = hashlib.sha256(second).hexdigest()
        print(f"run 1  sha256 {sha1}  {len(first)} bytes")
        print(f"run 2  sha256 {sha2}  {len(second)} bytes")
        print()
        print("run 1 scan order (every run, newest first):")
        for line in first_scan:
            print("   ", line)
        print("run 2 scan order (every run, newest first):")
        for line in second_scan:
            print("   ", line)
        print()
        print("run 1 published rows:",
              [f"{r['date']} x{r.get('group_count', 1)}"
               for r in json.loads(first)["reports"]])
        print("run 2 published rows:",
              [f"{r['date']} x{r.get('group_count', 1)}"
               for r in json.loads(second)["reports"]])
        print()
        if first == second:
            print("RESULT: BYTE-IDENTICAL — the feed is a pure function of repo content.")
            return 0
        print("RESULT: DIVERGED — the same commit publishes two different feeds.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
