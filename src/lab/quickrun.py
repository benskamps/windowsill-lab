"""``--quick`` runs never touch the live surfaces.

``--quick`` is a fast sanity pass: it proves a pipeline end to end on a toy
configuration. Before this module every milestone command still ended by
committing its report into ``reports/``, writing a public receipt, refreshing
``reports/latest.html``, and publishing ``pot.json`` — so on 2026-08-19
``lab m11 --quick`` made a 6-second L=8 toy run the lab's public headline,
with a ``receipt_url`` pointing at a receipt that was never meant to exist
(BACKLOG #6). The campaign cron stages ``pot.json``, so the next pass would
have committed it.

The fix is one switch at the two chokepoints every milestone already funnels
through, rather than an ``if not ns.quick`` at each of ~20 call sites (and
every future one):

* ``render._commit_report`` writes the report into ``$LAB_HOME/quick/``
  instead of the tracked ``reports/``, and writes no receipt and no
  ``latest.html``.
* ``publish.publish`` refuses with :class:`QuickRunNotPublished`, which the
  CLI's existing best-effort ``except`` prints as "snapshot skipped".

The CLI turns the switch on from the parsed ``--quick`` flag (so argparse
abbreviations like ``--qui`` count too) and turns it off on both sides of
every ``main`` call, so one in-process quick run cannot leak into the next.
Stdlib only: imported by the torch-free publish surface.
"""
from __future__ import annotations

from pathlib import Path

from . import labhome

_active = False


class QuickRunNotPublished(RuntimeError):
    """Raised by ``publish.publish`` while a ``--quick`` run is active."""

    def __init__(self) -> None:
        super().__init__("--quick run: live feed left untouched")


def enter() -> None:
    global _active
    _active = True


def reset() -> None:
    global _active
    _active = False


def active() -> bool:
    return _active


def scratch_dir() -> Path:
    """Where a quick run's report lands: untracked, outside the repo."""
    return labhome.LAB_HOME / "quick"
