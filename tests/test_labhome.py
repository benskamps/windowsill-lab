"""LAB_HOME is one definition, and it is overridable.

From the 2026-08-07 stranger pass. `~/.lab` was spelled `Path.home() / ".lab"` in
four modules, so a stranger could not take the lab for a drive without writing
into the same directory their existing lab uses — and a fork could not run beside
the original. The drive itself had to override `HOME` to exercise `lab run`
without landing in a live campaign's directory mid-pass.

Two properties are load-bearing and both are asserted here: the DEFAULT must not
move (this is a behaviour-preserving refactor for everyone who never sets the
variable), and every module must agree, because four copies of one fact is what
allowed them to drift in the first place.
"""
from __future__ import annotations

from pathlib import Path

from lab import labhome


def test_default_is_unchanged():
    """Nobody who never sets LAB_HOME should notice this refactor."""
    assert labhome.resolve({}) == Path.home() / ".lab"
    assert labhome.DEFAULT == Path.home() / ".lab"


def test_env_override_redirects_the_whole_footprint():
    assert labhome.resolve({"LAB_HOME": "/tmp/elsewhere"}) == Path("/tmp/elsewhere")


def test_tilde_is_expanded():
    """`LAB_HOME=~/lab-test` is the obvious thing to type; it must not make a
    literal directory called '~'."""
    assert labhome.resolve({"LAB_HOME": "~/lab-test"}) == Path.home() / "lab-test"


def test_blank_or_whitespace_falls_back_to_the_default():
    """An exported-but-empty variable is 'unset', not 'use the current directory'."""
    for blank in ("", "   ", "\t"):
        assert labhome.resolve({"LAB_HOME": blank}) == Path.home() / ".lab"


def test_every_module_shares_one_definition():
    """Four copies of one fact is what let them drift. There is now one."""
    from lab import cli, physics_feed, publish, render
    assert (cli.LAB_HOME
            is publish.LAB_HOME
            is render.LAB_HOME
            is physics_feed.LAB_HOME
            is labhome.LAB_HOME)


def test_download_caches_live_under_the_same_root():
    """One override has to move the whole footprint, including fetched inputs —
    otherwise a redirected clone still writes GWOSC strain into the real lab."""
    from lab import a01, a03
    assert a01.CACHE_DIR.parent == labhome.CACHE
    assert a03.CACHE_DIR.parent == labhome.CACHE
    assert labhome.CACHE.parent == labhome.LAB_HOME
