"""Whose repository is this? — resolved, never assumed.

Every public link this lab emits (the per-run report, the archive ledger, the
per-run receipt) is built from a GitHub `owner/name` slug. Until 2026-08-19 that
slug was a hardcoded constant naming the original author's repository, which
worked perfectly on the two machines it was written on and failed in a specific,
nasty way everywhere else:

**A fork would publish its own numbers linked to somebody else's evidence.**
Clone the repo, run a milestone, and `pot.json` came out carrying your run's
results with `receipt_url` and `report_href` pointing into the upstream author's
repository. The best case is a 404. The worst case is that the filename — dated
and slugged, so highly collidable — *resolves* upstream to a different run
entirely, and the page shows one lab's measurement above another lab's receipt.

For a project whose entire claim is that every number is checkable, silently
attributing your evidence to a stranger's repository is the most damaging bug
available. It is also invisible to the person it happens to: their page renders,
the links are blue, and nothing errors.

### The rule

Resolve the slug; never assume it. In order:

1. ``LAB_REPO_SLUG`` in the environment — the explicit override, for CI, mirrors,
   and anyone publishing from a checkout whose remote is not the public home.
2. The ``origin`` remote, parsed from `git remote get-url origin`. HTTPS, SSH and
   `git://` forms all reduce to `owner/name`.
3. **Nothing.** Not a default, not the upstream author's slug — ``None``.

Step 3 is the whole point. A URL that cannot be built correctly is not built:
:func:`join` returns ``None`` and every consumer omits the link rather than
emitting one that points somewhere wrong. This is the same rule `lab.hw` already
follows for the GPU label — *absence of evidence never claims* — applied to
provenance, where the cost of guessing is higher.

A lab that cannot say where its evidence lives should say nothing, not point at
someone else's.
"""
from __future__ import annotations

import os
import re
import subprocess
from functools import lru_cache

#: Environment override. Set to ``owner/name``.
SLUG_ENV = "LAB_REPO_SLUG"

#: Branch the published links point at. Overridable for the same reason the slug
#: is: a fork may publish from something other than ``main``.
BRANCH_ENV = "LAB_REPO_BRANCH"
DEFAULT_BRANCH = "main"

# owner/name from any of:
#   https://github.com/owner/name(.git)
#   git@github.com:owner/name(.git)
#   ssh://git@github.com/owner/name(.git)
#   git://github.com/owner/name(.git)
_REMOTE_RE = re.compile(
    r"github\.com[:/]+(?P<owner>[^/\s]+)/(?P<name>[^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

#: A slug we will accept from the environment. Deliberately strict: this string
#: is interpolated into URLs that a reader is invited to trust.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_remote(url: str | None) -> str | None:
    """``owner/name`` from a git remote URL, or None if it is not a GitHub one.

    Non-GitHub remotes return None rather than a guess: the published links are
    GitHub raw / htmlpreview URLs specifically, so a GitLab or self-hosted remote
    cannot be turned into one and must not be faked.
    """
    if not url:
        return None
    match = _REMOTE_RE.search(url.strip())
    if not match:
        return None
    return f"{match.group('owner')}/{match.group('name')}"


@lru_cache(maxsize=1)
def slug(cwd: str | None = None) -> str | None:
    """This checkout's ``owner/name``, or None when it cannot be established."""
    override = (os.environ.get(SLUG_ENV) or "").strip()
    if override:
        return override if _SLUG_RE.match(override) else None
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
            cwd=cwd or os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return parse_remote(out.stdout)


def branch() -> str:
    return (os.environ.get(BRANCH_ENV) or "").strip() or DEFAULT_BRANCH


def raw_base() -> str | None:
    """`https://raw.githubusercontent.com/<slug>/<branch>/`, or None."""
    s = slug()
    return f"https://raw.githubusercontent.com/{s}/{branch()}/" if s else None


def preview_base() -> str | None:
    """htmlpreview prefix over this repo's raw files, or None."""
    raw = raw_base()
    return f"https://htmlpreview.github.io/?{raw}" if raw else None


def repo_url() -> str | None:
    s = slug()
    return f"https://github.com/{s}" if s else None


def join(base: str | None, suffix: str) -> str | None:
    """``base + suffix``, or None when there is no base.

    The one-line reason this module exists: callers that would otherwise
    concatenate onto a wrong constant now concatenate onto ``None`` and get
    ``None``, so a link that cannot be built correctly is simply absent.
    """
    return None if base is None else base + suffix
