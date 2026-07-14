"""The windowsill page (``web/index.html``) ships a single downloadable file —
the mirror to brokenbranch.dev copies only ``index.html`` — so the growth-form
registry is INLINED into the page from ``web/growth-forms.js``. This guards the
two copies against drift: the block between the markers in ``index.html`` must be
byte-for-byte the contents of ``web/growth-forms.js``.

Stdlib-only (no Node) so it runs in the same fast CI lane as the contract tests.
The behavioural test of the forms themselves lives in
``web/growth-forms.test.mjs`` (``node --test``)."""

from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
MODULE = WEB / "growth-forms.js"
PAGE = WEB / "index.html"

BEGIN = "<!-- BEGIN growth-forms.js (inlined; source of truth: web/growth-forms.js) -->"
END = "<!-- END growth-forms.js (inlined) -->"


def _inlined_block() -> str:
    """The JS between the page's two markers, with the wrapping <script> tags
    stripped — i.e. what should equal ``growth-forms.js`` verbatim."""
    html = PAGE.read_text(encoding="utf-8")
    assert BEGIN in html, "growth-forms BEGIN marker missing from index.html"
    assert END in html, "growth-forms END marker missing from index.html"
    inner = html.split(BEGIN, 1)[1].split(END, 1)[0]
    # drop the <script> ... </script> wrapper lines, keep the JS body
    open_tag = inner.index("<script>") + len("<script>")
    close_tag = inner.rindex("</script>")
    return inner[open_tag:close_tag].strip()


def test_module_file_exists_and_is_nonempty():
    assert MODULE.exists(), "web/growth-forms.js (the source of truth) is missing"
    assert MODULE.read_text(encoding="utf-8").strip(), "growth-forms.js is empty"


def test_inlined_block_matches_module_source():
    """No drift: the inlined page copy == the standalone module, byte for byte.
    If this fails, edit web/growth-forms.js then re-sync the block in index.html."""
    module_src = MODULE.read_text(encoding="utf-8").strip()
    assert _inlined_block() == module_src, (
        "index.html's inlined growth-forms block has drifted from "
        "web/growth-forms.js — re-sync the block between the markers."
    )


def test_page_uses_the_registry_not_the_old_hardcoded_stem():
    """The render must go through the pluggable registry, not the retired
    single-form stem builder."""
    html = PAGE.read_text(encoding="utf-8")
    assert "GF.pageGrowthForm(milestones)" in html, "page must pick a form from the feed"
    assert "GF.build(formName" in html, "page must build geometry via the registry"


def test_module_exposes_three_distinct_shipped_forms():
    """BACKLOG asked for 2–3 forms behind one interface; assert the builders and
    the contract enum are all present as a coarse contract check (the behavioural
    proof is the node test)."""
    src = MODULE.read_text(encoding="utf-8")
    for builder in ("function fern(", "function vine(", "function succulent("):
        assert builder in src, f"missing growth-form builder: {builder}"
    # every value publish.py's GROWTH_FORMS can emit must be a registry key
    for form in ("fern", "vine", "creeper", "succulent", "moss", "sprout"):
        assert f"{form}:" in src, f"feed form '{form}' not wired into the registry"


def test_page_has_one_canonical_feed_for_readout_and_snapshot_link():
    html = PAGE.read_text(encoding="utf-8")
    canonical = (
        "https://raw.githubusercontent.com/benskamps/windowsill-lab/main/pot.json"
    )
    assert html.count(canonical) == 1
    assert "data-feed-url=" in html
    assert "snapshotLink.href = feedUrl" in html
    assert "fetch(feedUrl" in html
    assert "fetch('/api/pot'" not in html


def test_review_pending_runs_are_not_painted_as_promoted():
    html = PAGE.read_text(encoding="utf-8")
    assert "milestoneStatus[r.milestone] === 'review'" in html
    assert "ARC_GLYPH = { verified:'●', review:'◆'" in html


def test_host_only_walk_does_not_404_in_local_file_mode():
    html = PAGE.read_text(encoding="utf-8")
    assert '<script defer src="/walk/walk.js"></script>' not in html
    assert "brokenbranch\\.dev" in html
