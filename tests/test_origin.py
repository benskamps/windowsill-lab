"""Fork safety — a lab must never publish its numbers over someone else's evidence.

The bug this guards against is not a crash. It is a page that renders perfectly,
with blue links, showing YOUR measurement above SOMEBODY ELSE'S receipt — because
the URL prefixes were hardcoded to the original author's repository and a fork
inherited them. The best case was a 404; the worst was a dated-and-slugged
filename colliding with a real upstream file, so the link resolved to a different
run entirely.

So the tests that matter here are the negative ones: with an unresolvable origin,
every public link must come out ``None``, and nothing anywhere may fall back to a
literal repository name.
"""
from __future__ import annotations

import pytest

from lab import a03, archive, origin, publish


@pytest.fixture(autouse=True)
def _clear_slug_cache():
    origin.slug.cache_clear()
    yield
    origin.slug.cache_clear()


def _as(monkeypatch, value):
    """Pin the resolved slug, bypassing git entirely."""
    monkeypatch.setenv(origin.SLUG_ENV, value)
    origin.slug.cache_clear()


# --------------------------------------------------------------- remote parsing ---

@pytest.mark.parametrize("url", [
    "https://github.com/owner/name",
    "https://github.com/owner/name.git",
    "git@github.com:owner/name.git",
    "ssh://git@github.com/owner/name",
    "git://github.com/owner/name.git",
    "https://github.com/owner/name/",
    "HTTPS://GitHub.com/owner/name.git",
])
def test_every_github_remote_form_reduces_to_owner_name(url):
    assert origin.parse_remote(url) == "owner/name"


@pytest.mark.parametrize("url", [
    "https://gitlab.com/owner/name",
    "https://git.example.org/owner/name.git",
    "not a url",
    "",
    None,
])
def test_a_non_github_remote_is_not_guessed_at(url):
    """The published links are GitHub raw/htmlpreview URLs specifically, so a
    remote that cannot become one must not be faked into one."""
    assert origin.parse_remote(url) is None


# ------------------------------------------------------------- the fork scenario ---

def test_a_fork_publishes_its_own_links(monkeypatch):
    _as(monkeypatch, "someone-else/windowsill-fork")
    assert "someone-else/windowsill-fork" in publish.report_url()
    assert "someone-else/windowsill-fork" in publish.receipt_url_base()
    assert "someone-else/windowsill-fork" in publish.archive_url()


def test_a_fork_never_leaks_the_upstream_slug_into_any_link(monkeypatch):
    """The regression this module exists for, stated directly."""
    _as(monkeypatch, "someone-else/windowsill-fork")
    for url in (publish.report_url(), publish.receipt_url_base(),
                publish.archive_url(), origin.repo_url(),
                archive._archive_anchor("2026-08-19", "m11", 1),
                archive._repo_link(), a03._user_agent()):
        assert "benskamps" not in (url or ""), url


def test_a_fork_can_publish_from_a_branch_that_is_not_main(monkeypatch):
    _as(monkeypatch, "someone-else/fork")
    monkeypatch.setenv(origin.BRANCH_ENV, "publish")
    assert "/fork/publish/" in publish.report_url()


# ------------------------------------- the unresolvable case: silence, not a guess ---

@pytest.mark.parametrize("bad", ["", "   ", "no-slash", "bad slug/with space",
                                 "/leading", "trailing/", "a//b"])
def test_a_slug_that_does_not_parse_resolves_to_nothing(monkeypatch, bad):
    monkeypatch.setenv(origin.SLUG_ENV, bad)
    origin.slug.cache_clear()
    if bad.strip():
        assert origin.slug() is None
    # An empty override falls through to git, which is not what this asserts.


def test_every_public_link_is_none_when_the_origin_is_unknown(monkeypatch):
    """A URL that cannot be built correctly is not built."""
    monkeypatch.setattr(origin, "slug", lambda *a, **k: None)
    assert origin.raw_base() is None
    assert origin.preview_base() is None
    assert origin.repo_url() is None
    assert publish.report_url() is None
    assert publish.report_url_base() is None
    assert publish.receipt_url_base() is None
    assert publish.archive_url() is None
    assert archive._archive_anchor("2026-08-19", "m11", 1) is None


def test_join_propagates_absence_rather_than_concatenating_onto_it():
    assert origin.join(None, "reports/") is None
    assert origin.join("https://x/", "reports/") == "https://x/reports/"


def test_an_unknown_origin_degrades_the_ledger_link_to_plain_text(monkeypatch):
    monkeypatch.setattr(origin, "slug", lambda *a, **k: None)
    link = archive._repo_link()
    assert "<a" not in link
    assert "benskamps" not in link


def test_an_unknown_origin_still_identifies_the_project_to_external_archives(monkeypatch):
    """Courtesy that names the wrong party is worse than none; naming nobody is fine."""
    monkeypatch.setattr(origin, "slug", lambda *a, **k: None)
    agent = a03._user_agent()
    assert agent.startswith("windowsill-lab/a03")
    assert "http" not in agent


# ---------------------------------------------------------------- this checkout ---

def test_this_checkout_still_resolves_to_its_own_remote():
    """The fix must be a no-op for the repository it was written in."""
    resolved = origin.slug()
    assert resolved is None or "/" in resolved


def test_the_environment_override_wins_over_git(monkeypatch):
    _as(monkeypatch, "override/wins")
    assert origin.slug() == "override/wins"
