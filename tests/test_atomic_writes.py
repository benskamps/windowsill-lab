"""DET-1 — every canonical artifact write survives an interrupted write.

The lab's public record is a pile of files on disk: ``pot.json``, the run
receipts, ``physics-latest.json``, ``reports/index.html`` and every dated
report pair. Each was written IN PLACE (``dest.write_text(...)``), so a crash,
a full disk, or a killed nightly halfway through a write left a truncated file
where the evidence used to be. For receipts that is permanent: publish keeps
any receipt already on disk (``publish.ensure_public_receipts``), by design —
evidence is immutable — so a torn receipt is frozen forever.

The repo already had the right pattern in exactly one place
(``scripts/a05_hunt.py`` — tmp + fsync + atomic replace). These tests hold every
other canonical writer to it.

Fault injection is deliberately symmetric: it patches the ONE call both the old
and the new path bottom out in (``io.TextIOWrapper.write``), tears any write
whose open file name mentions the destination, and then asks the only question
that matters — is the file that was already on disk still there, whole?
"""
from __future__ import annotations

import io
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from lab import archive, physics_feed, publish, receipt


class PowerLoss(RuntimeError):
    """The write that stopped halfway."""


class _TornFile:
    """A file handle that writes half of what it is given, then dies."""

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def write(self, s):
        self._wrapped.write(s[: len(s) // 2])
        raise PowerLoss(f"power loss writing {getattr(self._wrapped, 'name', '?')}")

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._wrapped.close()
        return False


@contextmanager
def tearing(monkeypatch, token: str):
    """Truncate-and-raise any text write to a file whose path mentions ``token``.

    The seam is ``io.open``, which BOTH ``Path.write_text`` and an explicit
    ``path.open("w")`` bottom out in — so the in-place writer and the tmp-file
    writer face exactly the same fault and only the destination differs. That
    symmetry is the whole point: nothing here favours the fix.
    """
    real_open = io.open

    def torn_open(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if "w" in mode and token in str(file):
            return _TornFile(handle)
        return handle

    monkeypatch.setattr(io, "open", torn_open)
    yield
    monkeypatch.undo()


def _survives_json(path: Path, expected: dict) -> None:
    assert path.exists(), f"{path} vanished — the original evidence is gone"
    assert json.loads(path.read_text(encoding="utf-8")) == expected, (
        f"{path} was overwritten by a torn write — the original is unreadable"
    )


# ── receipt.write_public_receipt ─────────────────────────────────────────────

def test_torn_receipt_write_leaves_the_committed_receipt_intact(tmp_path, monkeypatch):
    """A receipt is immutable evidence; a torn write must not become the record."""
    dest = tmp_path / "receipts" / "run-2026-08-21-0730-m03.json"
    dest.parent.mkdir(parents=True)
    good = {"experiment": "M03-good", "headline": "the committed evidence"}
    dest.write_text(json.dumps(good), encoding="utf-8")

    with tearing(monkeypatch, dest.name):
        with pytest.raises(PowerLoss):
            receipt.write_public_receipt(
                {"experiment": "M03-torn", "headline": "x" * 400}, dest, b"src")

    _survives_json(dest, good)


# ── physics_feed.build_physics_feed ──────────────────────────────────────────

def test_torn_physics_feed_write_leaves_the_previous_feed_intact(tmp_path, monkeypatch):
    dest = tmp_path / "physics-latest.json"
    good = {"schema": "physics.v1", "m01": {"T": [2.2], "chi": [1.0]}}
    dest.write_text(json.dumps(good), encoding="utf-8")
    monkeypatch.setattr(physics_feed, "build_feed",
                        lambda *a, **k: {"schema": "physics.v1", "m01": {"x": "y" * 400}})

    with tearing(monkeypatch, dest.name):
        with pytest.raises(PowerLoss):
            physics_feed.build_physics_feed(
                out_path=dest, reports_dir=tmp_path / "reports",
                lab_home=tmp_path / "lab", previous_feed=good)

    _survives_json(dest, good)


# ── archive.write_index ──────────────────────────────────────────────────────

def test_torn_archive_index_write_leaves_the_committed_index_intact(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    dest = reports / "index.html"
    good = "<html><body>the committed archive</body></html>"
    dest.write_text(good, encoding="utf-8")
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    monkeypatch.setattr(archive, "render_index", lambda: "<html>" + "z" * 400 + "</html>")

    with tearing(monkeypatch, "index.html"):
        with pytest.raises(PowerLoss):
            archive.write_index()

    assert dest.read_text(encoding="utf-8") == good


# ── publish.publish → pot.json (the live feed) ───────────────────────────────

def test_torn_pot_write_leaves_the_committed_feed_intact(tmp_path, monkeypatch):
    dest = tmp_path / "pot.json"
    good = {"schema": "windowsill.pot.v5", "reports": [{"date": "2026-08-21"}]}
    dest.write_text(json.dumps(good, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(publish, "POT_JSON", dest)
    monkeypatch.setattr(publish, "LAB_HOME", tmp_path / "lab")
    # publish() also rewrites the page's shelf counters from the snapshot
    # it writes (refresh_shelf_fallback). Redirect that too, or a fixture
    # snapshot scribbles zeros over the SHIPPED web/index.html mid-suite.
    monkeypatch.setattr(publish, "WEB_INDEX", tmp_path / "index.html")
    monkeypatch.setattr(publish, "ensure_public_receipts", lambda *a, **k: [])
    monkeypatch.setattr(publish, "collect",
                        lambda: {"schema": "windowsill.pot.v5", "junk": "q" * 400})

    with tearing(monkeypatch, "pot.json"):
        with pytest.raises(PowerLoss):
            publish.publish(quiet=True)

    _survives_json(dest, good)


# ── the whole writer surface, not just the four sampled above ────────────────

CANONICAL_WRITERS = ("publish.py", "physics_feed.py", "receipt.py",
                     "archive.py", "render.py")


def test_no_canonical_writer_writes_in_place():
    """Every artifact writer goes through the one shared atomic helper.

    The four fault-injection tests above pin four call sites; ``render.py``
    alone has fifty more (one html + one json + one ``latest.html`` per
    renderer). A grep-level pin is the only thing that keeps the next renderer
    from being added with a bare ``write_text`` — which is exactly how all of
    them got here.
    """
    src = Path(__file__).resolve().parents[1] / "src" / "lab"
    offenders = []
    for name in CANONICAL_WRITERS:
        for lineno, line in enumerate(
                (src / name).read_text(encoding="utf-8").splitlines(), 1):
            if ".write_text(" in line or ".write_bytes(" in line:
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "in-place canonical writes (use lab.atomic.atomic_write_text):\n"
        + "\n".join(offenders))
