"""Which tree does the suite actually test?

STR-9: `lab` is installed editable, pointing at the primary clone. In a git
WORKTREE a bare `pytest` therefore collected the worktree's *tests* and ran them
against the primary clone's *code* — a silent false-result generator, and the
exact "passes for the wrong reason" class every other guard in this repo exists
to close. CI was never affected (.github/workflows/ci.yml sets PYTHONPATH=src),
which is why it survived: green CI could not see it.

This test is the tripwire. If it fails, nothing else in this run means anything.
"""
from pathlib import Path

import lab

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_lab_resolves_to_the_tree_the_tests_live_in():
    """The imported package must come out of THIS checkout, not whichever tree
    happens to own the editable install."""
    imported = Path(lab.__file__).resolve()
    assert imported.is_relative_to(REPO_ROOT), (
        f"tests in {REPO_ROOT} are exercising {imported} — a different tree.\n"
        "A bare `pytest` in a worktree resolved `lab` through the editable "
        "install instead of ./src; see conftest.py."
    )


def test_lab_resolves_under_src():
    """And specifically out of ./src — not a stray top-level copy."""
    assert Path(lab.__file__).resolve().is_relative_to(REPO_ROOT / "src")
