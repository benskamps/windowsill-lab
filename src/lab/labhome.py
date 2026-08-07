"""Where the lab keeps its working data — one definition, overridable.

``~/.lab`` holds the dated reports, the caches, the campaign counter and the
one-turn-per-box lock. It used to be spelled ``Path.home() / ".lab"`` in four
separate modules, which meant two things:

1. **A stranger could not try the lab without writing into it.** Clone the repo,
   run `lab run`, and it lands in the same directory your existing lab uses.
   A fork could not coexist with the original, and there was no way to take the
   instrument for a drive without touching your own record. That is a real cost
   for a project whose whole pitch is "pull this, fork it, point it at your own
   feed" — found by the 2026-08-07 stranger pass, which had to override ``HOME``
   itself to exercise `lab run` without writing into a live campaign's directory
   mid-pass.
2. Four copies of one fact, free to drift.

``LAB_HOME`` in the environment overrides it. Resolved at import, like the
constant it replaces, so nothing downstream changes shape.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Default when nothing is configured — unchanged from the original behaviour.
DEFAULT = Path.home() / ".lab"


def resolve(env: dict[str, str] | None = None) -> Path:
    """The lab's working directory: ``$LAB_HOME`` if set and non-empty, else ``~/.lab``."""
    raw = (env if env is not None else os.environ).get("LAB_HOME", "")
    return Path(raw).expanduser() if raw.strip() else Path.home() / ".lab"


LAB_HOME = resolve()

#: Downloaded inputs a run may reuse (TESS FITS, GWOSC strain). Kept under the
#: same root so one override moves the whole footprint.
CACHE = LAB_HOME / "cache"
