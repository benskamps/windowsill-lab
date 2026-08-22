"""One atomic-write helper for every canonical artifact this lab commits.

The pot, the receipts, ``physics-latest.json``, the archive index and every
dated report pair are the lab's public evidence. They used to be written in
place — ``dest.write_text(...)`` truncates the destination and then starts
filling it — so an interrupted write (crash, full disk, a killed nightly) left
a truncated file where the evidence had been. For receipts that damage is
permanent by design: ``publish.ensure_public_receipts`` keeps whatever receipt
is already on disk, because evidence is immutable and it cannot tell a
correction from a corruption. A torn receipt would be frozen forever.

The correct pattern already existed in this repo, in exactly one place — the
hunt receipt + pot refresh in ``scripts/a05_hunt.py`` (write a tmp file, fsync
it, then ``Path.replace`` it over the destination). ``replace`` is atomic on
POSIX and on Windows, so a reader sees either the whole old file or the whole
new one, never a half of either. This module is that pattern lifted out so
there is one of it, and every writer calls it.

Deliberately NOT changed here: the newline handling. ``open(mode="w")`` with
the default ``newline=None`` translates ``\n`` to ``os.linesep``, which is what
``Path.write_text`` did and therefore what every committed artifact's bytes
already are. Making these writes atomic must not change a single byte of what
they produce.
"""
from __future__ import annotations

import os
from pathlib import Path


def _tmp_for(path: Path) -> Path:
    """The scratch name a write lands on before it becomes ``path``.

    Dot-prefixed and ``.tmp``-suffixed so it cannot be picked up by any of the
    repo's discovery globs (``[0-9][0-9][0-9][0-9]-*.json``, ``run-*.json``,
    ``*.html``), and pid-stamped so two processes writing the same artifact
    cannot land on each other's scratch file — the ``.tmp`` sibling in
    ``a05_hunt.py`` predates the parallel lanes.
    """
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> Path:
    """Write ``text`` to ``path`` as one indivisible step; return ``path``.

    Creates the parent directory, writes + fsyncs a sibling tmp file, then
    atomically replaces the destination. If anything raises partway the
    destination is untouched and the tmp file is removed; the caller still sees
    the exception, so a failed write is never silently a successful one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_for(path)
    try:
        with tmp.open("w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path
