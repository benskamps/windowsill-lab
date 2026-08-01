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


def test_field_notes_and_rail_fail_closed_for_unknown_milestone_status():
    html = PAGE.read_text(encoding="utf-8")
    assert "function milestoneStatusOrPending(status)" in html
    assert (
        "return /^(verified|review|null|open|pending)$/.test(status) "
        "? status : 'pending';"
    ) in html
    assert "var status = milestoneStatusOrPending(m.status);" in html
    assert "var allowed = milestoneStatusOrPending(m.status);" in html
    assert "pending: 'ahead · unscored'" in html
    assert "m.status || 'verified'" not in html


def test_host_only_walk_does_not_404_in_local_file_mode():
    html = PAGE.read_text(encoding="utf-8")
    assert '<script defer src="/walk/walk.js"></script>' not in html
    assert "brokenbranch\\.dev" in html


def test_conservatory_is_feed_driven_and_opens_real_field_notes():
    """Every specimen must report the feed, not repeat decorative sample plants."""
    html = PAGE.read_text(encoding="utf-8")
    assert "Five instruments. One standard of proof." in html
    assert "function drawGarden(milestones, reports)" in html
    assert "count:closed.length, total:total" in html
    assert "reportForMilestone(reports, latest && latest.id)" in html
    assert "specimen-leaf ' + (milestone.status" in html
    assert "openFieldNote(focusMilestone, action)" in html
    assert "garden: garden" in html
    assert "count:5, total:8" not in html


# ── One feed lifecycle: qualification in render, shared tick, change-detected
#    re-renders, triptych empty/stale states, scene a11y, five-track metas ─────


def test_headline_quality_rides_every_render_not_a_one_shot():
    """The quality reconciliation must be a function both feeds re-apply, not a
    one-shot patch: pot render() rewrites #report-line raw on every tick, so it
    must consult the physics side's quality state each time, and the physics
    side must re-apply when its feed arrives after the pot's (the t=0 race)."""
    html = PAGE.read_text(encoding="utf-8")
    assert "function applyHeadlineQuality()" in html
    assert "window.__windowsillPhysics" in html
    # pot render() consults the hook right after writing the headline
    assert "window.__windowsillPhysics.applyHeadlineQuality()" in html


def test_feeds_share_one_tick_and_skip_unchanged_responses():
    """Both feeds refresh on the same 5-minute tick (the physics panel used to
    fetch exactly once), each failing independently; byte-identical responses
    skip the re-render so focus, scroll, and animations are left alone."""
    html = PAGE.read_text(encoding="utf-8")
    assert "setInterval(refreshFeeds, 5 * 60 * 1000)" in html
    assert "setInterval(loadFeed, 5 * 60 * 1000)" not in html
    assert "Promise.allSettled" in html
    assert "_lastPotText" in html
    assert "_lastPhysicsText" in html


def test_rail_rebuild_preserves_focus_and_recenters_only_on_a_new_current():
    """A changed-feed rebuild wipes the rail; keyboard focus must come back to
    the same chip by data-mid, and the forced scroll recenter fires only when
    the current milestone actually moved (never undoing user scroll)."""
    html = PAGE.read_text(encoding="utf-8")
    assert "focusedMid" in html
    assert "_railCenteredOn" in html


def test_garden_entrance_animation_plays_once():
    """Fresh <li> nodes under [data-ready] replay specimen-rise on every
    rebuild; after the first paint the row is marked settled and the entrance
    animation is disabled."""
    html = PAGE.read_text(encoding="utf-8")
    assert '[data-settled="true"] .garden-specimen { animation:none' in html
    assert "dataset.settled" in html


def test_triptych_states_disclose_missing_or_carried_snapshots():
    """A feed without lattice snapshots must hide the triptych and say why —
    not render three blank canvases under a hardcoded 128x128 provenance
    claim. Dims come only from the feed's snapshot_L, and a carried lattice
    (feed's snapshots_date differs from the run date) names its producing run."""
    html = PAGE.read_text(encoding="utf-8")
    assert 'id="triptych-missing"' in html
    assert "omitted its lattice snapshots" in html
    assert 'id="ip-lattice-dims">128' not in html
    assert 'id="ip-lattice-src"' in html
    assert "snapshots_date" in html


def test_scene_svg_role_keeps_leaf_and_bud_buttons_exposed():
    """role="img" makes an SVG's children presentational, stripping the leaf
    and bud button semantics from the accessibility tree; the scene must use a
    role that keeps its interactive children exposed."""
    html = PAGE.read_text(encoding="utf-8")
    assert '<svg viewBox="0 0 800 560" role="group"' in html
    assert '<svg viewBox="0 0 800 560" role="img"' not in html


def test_meta_descriptions_enumerate_five_tracks():
    """Search results and social unfurls must describe the page they open:
    five instruments, not four."""
    html = PAGE.read_text(encoding="utf-8")
    assert "four kinds of patient science" not in html
    assert "Four quiet plants" not in html
    assert "five kinds of patient science" in html
    assert "Five quiet plants" in html
