"""Make a bare `pytest` test the tree it is run from.

STR-9: `lab` is installed editable, and an editable install points at exactly ONE
tree (the primary clone). Without this file a bare `pytest` inside a git worktree
collected that worktree's *tests* and ran them against the primary clone's *code* —
two different checkouts, reported green. CI never saw it, because
.github/workflows/ci.yml sets PYTHONPATH=src explicitly; only humans and agents
working in worktrees were affected, and they got a silent false result.

Prepending ./src here — rather than `[tool.pytest.ini_options] pythonpath = ["src"]` —
anchors the fix to the location of THIS file, so it holds for every invocation
form (`pytest`, `pytest tests/`, `python -m pytest` from a subdirectory) instead
of depending on pytest resolving its rootdir to the same tree the tests live in.
tests/test_import_hygiene.py is the tripwire that proves it still works.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
