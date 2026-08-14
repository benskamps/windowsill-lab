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


def test_field_notes_fall_back_to_the_v5_run_ledger_for_public_receipts():
    """v5 no longer duplicates record URLs into milestone rows."""
    html = PAGE.read_text(encoding="utf-8")
    assert "var matchingReport = reportForMilestone(" in html
    assert "_lastFeedState && _lastFeedState.reports" in html
    assert "matchingReport && matchingReport.receipt_url" in html
    assert "matchingReport && matchingReport.href" in html


def test_host_only_walk_does_not_404_in_local_file_mode():
    html = PAGE.read_text(encoding="utf-8")
    assert '<script defer src="/walk/walk.js"></script>' not in html
    assert "brokenbranch\\.dev" in html


def test_the_page_carries_its_own_host_gated_analytics_beacon():
    """The page must measure itself, and only on the host.

    The page is mirrored VERBATIM into the site repo, where the other 23 pages
    have the Vercel beacon hand-added per file. Anything added on the site side is
    clobbered by the next mirror-pull, so windowsill and leanto were the only two
    unmeasured pages on brokenbranch.dev — a side effect of being a mirror target,
    not an oversight. The beacon therefore has to live upstream, here.

    Two invariants:

    * host-gated, like the walk — a downloadable ``lab web`` copy must not 404 on
      ``/_vercel/*``, so there is no unconditional beacon <script> tag;
    * the queue stub must not be clobbered. At the top level of a classic script
      ``var va`` becomes ``window.va``, which would overwrite the stub that the
      real script drains, so the loader is wrapped in an IIFE and must not
      declare a top-level ``va``.
    """
    html = PAGE.read_text(encoding="utf-8")

    # No unconditional beacon: it is injected behind the host check, never a tag.
    assert '<script defer src="/_vercel/insights/script.js"></script>' not in html
    assert "'/_vercel/insights/script.js'" in html
    # The queue stub is inlined (the site's /js/va-shim.js is not mirrored here).
    assert "window.va = window.va ||" in html
    # The comment above the loader names the shim; what must not appear is a
    # *reference* to it, since that asset is not mirrored with this page.
    assert 'src="/js/va-shim.js"' not in html, "site-only asset must not be loaded"
    # ...and it is never shadowed by a top-level var of the same name.
    assert "var va =" not in html, "top-level `var va` would overwrite window.va"


def test_conservatory_is_feed_driven_and_opens_real_field_notes():
    """Every specimen must report the feed, not repeat decorative sample plants."""
    html = PAGE.read_text(encoding="utf-8")
    assert "Six instruments. One standard of proof." in html
    assert "function drawGarden(milestones, reports)" in html
    assert "count:closed.length, total:total" in html
    assert "reportForMilestone(reports, latest && latest.id)" in html
    assert "specimen-leaf ' + (milestone.status" in html
    assert "openFieldNote(focusMilestone, action)" in html
    assert "garden: garden" in html
    assert "count:5, total:8" not in html


def test_latest_turn_names_its_milestone_and_future_work_has_no_fake_receipt():
    """The current question and latest result are different concepts.

    A stranger must not have to infer that the K03 expedition and the M15
    heartbeat belong to different experiments. Likewise a planned venue alone
    is not a receipt for an experiment that has never run.
    """
    html = PAGE.read_text(encoding="utf-8")
    assert "var repTag = 'latest turn' + repId + ' · ' + repState;" in html
    assert "rep.milestone" in html
    assert "var hasReceiptEvidence" in html
    assert "Boolean(m.result)" in html
    assert "Boolean(safeUrl)" in html


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


def test_measurement_panel_names_its_compatible_calibration_not_the_latest_turn():
    """physics-latest is the newest M01-shaped panel, not the newest lab turn.

    Calling it “the latest committed run” made an August 1 M01 panel sound like
    the August 13 M15 heartbeat shown directly above it.
    """
    html = PAGE.read_text(encoding="utf-8")
    assert "latest compatible calibration" in html
    assert "live plant above follows the newest turn" in html
    assert "the same committed heartbeat report the plant grows from" not in html
    assert "In the compatible calibration plotted above it landed" in html
    assert "Last run it landed" not in html
    assert "snapshots_date" in html


def test_scene_svg_role_keeps_leaf_and_bud_buttons_exposed():
    """role="img" makes an SVG's children presentational, stripping the leaf
    and bud button semantics from the accessibility tree; the scene must use a
    role that keeps its interactive children exposed."""
    html = PAGE.read_text(encoding="utf-8")
    assert '<svg viewBox="0 0 800 560" role="group"' in html
    assert '<svg viewBox="0 0 800 560" role="img"' not in html


def test_meta_descriptions_enumerate_every_track():
    """Search results and social unfurls must describe the page they open.

    The count is the number of TRACKS in ``publish.TRACKS`` (physics, coherence,
    compute, astronomy, instrument, boinc) — it went four → five → six as tracks
    landed, so this asserts the current count and that no stale one survives.
    """
    html = PAGE.read_text(encoding="utf-8")
    for stale in ("four kinds of patient science", "Four quiet plants",
                  "five kinds of patient science", "Five quiet plants",
                  "Five instruments."):
        assert stale not in html, f"stale track count on the page: {stale!r}"
    assert "six kinds of patient science" in html
    assert "Six quiet plants" in html
    assert "Six instruments. One standard of proof." in html


def test_the_centre_plant_grows_only_the_bench_track():
    """The full-size plant at the centre of the sill is ONE track's plant.

    Until 2026-08-12 it was built from the whole lab's milestone ledger — every
    science's leaves on a single stem — while standing in the bench track's pot.
    Ben, comparing the sill against the six conservatory cards: it "still seems
    to be 'all of the leafs in one' and it doesn't match the 6 images."

    So the centre is parameterized like a flank and like a card: the track's own
    milestones over the track's own ladder length. The behavioural proof (run
    against the committed feed) is ``web/centre-plant.test.mjs``; this is the
    fast-lane guard on the wiring, so the regression cannot land on a day node
    does not run.
    """
    html = PAGE.read_text(encoding="utf-8")

    # the derivation exists, and is the same filter the cards and flanks use
    assert "function benchLadder(milestones, track, fallbackTotal)" in html
    assert "var own = list.filter(function (m) { return m && m.track === track; });" in html
    # ...falling back to the whole ledger only when nothing carries a track
    assert "if (!own.length) return { milestones: list, total: fallbackTotal, whole: true };" in html

    # render() feeds the centre the bench ladder, never the page-wide one
    render_block = html.split("function render(state)", 1)[1].split("function wetFromRun", 1)[0]
    assert "var bench = benchLadder(milestones, heroTrack, total);" in render_block
    assert "drawStalk(bench.milestones, bench.total, season," in render_block
    assert "drawStalk(milestones," not in render_block, (
        "the centre plant is being built from the whole ledger again"
    )

    # the whole lab's closed set still reaches drawStalk, but only as the growth
    # theater's memory — what a visitor has already seen belongs to the visitor,
    # not to whichever track is on the bench. It is never foliage.
    assert "milestones.filter(isClosed));" in render_block
    assert (
        "rememberClosedIds(Array.isArray(ledgerClosed) ? ledgerClosed : closed);"
    ) in html

    # and the harness readout reports the plant as one track's ladder, with the
    # lab-wide counts moved to their own key rather than mislabelled as leaves
    assert "growth_form: GF.pageGrowthForm(bench.milestones)," in html
    assert "leaves: benchClosed.length," in html
    assert "ledger: {" in html


def test_the_centre_plant_draws_the_rungs_it_has_not_reached():
    """A centre plant showing one track has to show that track's whole climb, or
    compute at 1 of 4 reads as a snapped twig at centre stage — the same defect
    the conservatory cards fixed. Drawn from the REAL tip up the shared height
    envelope, never a second build at full height (that re-parameterizes vine's
    coil and creeper's sweep into a different, diverging plant)."""
    html = PAGE.read_text(encoding="utf-8")
    assert '<g id="unreached" aria-hidden="true"></g>' in html
    assert "var reached = closed.length + (open ? 1 : 0);   // the open one IS the tip" in html
    assert "var ceiling = GF._nodeY(env, total - 1);" in html
    # the ghost continues from geo.tip — the progress geometry — not from a rebuild
    assert "ghostStem.setAttribute('d', 'M ' + geo.tip.x.toFixed(1) + ' ' + geo.tip.y.toFixed(1) +" in html
    assert html.count("GF.build(formName") == 1, "the centre built its form twice"
    for rule in (".plant-rung.unreached", ".plant-leaf.unreached"):
        assert rule in html, f"missing style for the centre's unreached rungs: {rule}"


def test_a_garden_card_draws_its_whole_ladder_not_only_the_measured_rungs():
    """A young track must read as young, not as broken.

    Node count used to equal the number of CLOSED milestones, so compute (1 of
    4), astronomy (1 of 4) and instrument (1 of 3) each drew a bare stalk with a
    single blob, and boinc at 0 of 2 drew a stalk with nothing on it at all. Four
    of the six specimens looked like snapped twigs beside the physics fern, and
    the length of each climb was invisible until it was finished.

    So the card builds a second geometry over the FULL track length and draws the
    rungs it has not reached as faint dashed outlines. Two invariants matter and
    are asserted here:

    * height still means real progress — the SOLID stem and the tip come from the
      progress-scaled build, never from the full-ladder one;
    * the open milestone is drawn once. It is already the growing tip, so it must
      not also get a ghost rung.
    """
    html = PAGE.read_text(encoding="utf-8")

    # The measured plant is still the ONLY thing the form builds: one build,
    # progress-scaled, owning the solid stem and the tip.
    assert html.count("GF.build(spec.form, {") == 1
    assert "count:closed.length, total:total, openProg:progress" in html
    assert "stem.setAttribute('d', geo.stem)" in html
    assert "tip.setAttribute('cx', geo.tip.x.toFixed(1))" in html
    # Unreached rungs continue from the real tip on the shared height envelope —
    # NOT a second build of the form, which re-parameterizes vine's coil and
    # creeper's sweep and renders as a second, diverging plant.
    assert "var reached = closed.length + (open ? 1 : 0);" in html
    assert "GF._nodeY(env, g)" in html
    assert "if (GF._nodeY && total > reached) {" in html
    for rule in ("path.specimen-stem.unreached",
                 "path.specimen-branch.unreached",
                 ".specimen-leaf.unreached"):
        assert rule in html, f"missing style for unreached rungs: {rule}"


# ── The painterly repaint, phase 1 (2026-08-14): skin defs, group glow,
#    data-lit lumen, reduced-motion, and the committed art-bible reference ────


def test_painterly_skin_registry_lives_in_the_module_and_reaches_the_page():
    """SKINS (per-archetype luminous core→rim colours) is defined ONCE in
    growth-forms.js; the page builds its gradient defs from it at boot, so the
    module, the page, and the node tests cannot drift apart."""
    src = MODULE.read_text(encoding="utf-8")
    html = PAGE.read_text(encoding="utf-8")
    assert "var SKINS" in src, "growth-forms.js must carry the SKINS registry"
    assert "lumenOpacity" in src and "daysSinceNewestReceipt" in src
    # the page installs one radialGradient per archetype from that registry
    assert "function installSkinDefs()" in html
    assert "installSkinDefs();" in html, "boot must install the skin defs"
    assert "'leafCore-' + form" in html
    assert "GF.SKINS" in html


def test_organ_glow_filter_is_defined_and_applied_at_the_organ_group_level():
    """The soft outer glow (light from within, per the plant bible) is one
    feGaussianBlur+merge filter applied to the whole organ group — and a folded
    null opts out: a kept miss is matte."""
    html = PAGE.read_text(encoding="utf-8")
    assert '<filter id="organGlow"' in html
    glow = html.split('<filter id="organGlow"', 1)[1].split("</filter>", 1)[0]
    assert "feGaussianBlur" in glow and "feMerge" in glow
    assert ".leaf { filter:url(#organGlow); }" in html
    assert ".leaf.null-leaf { filter:none; }" in html


def test_lumen_is_data_lit_verified_only_and_rhymes_with_the_planner():
    """A verified leaf's glow opacity is derived from the run ledger already in
    the feed (no new network calls), through the SAME log2(1+days/7) staleness
    shape the planner uses — and only verified organs are lit."""
    html = PAGE.read_text(encoding="utf-8")
    # derivation: ledger in hand → days → opacity, guarded to verified organs
    assert "if (!nul && m.status === 'verified') {" in html
    assert "GF.daysSinceNewestReceipt(" in html
    assert "_lastFeedState && _lastFeedState.reports, m.id, Date.now())" in html
    assert "GF.lumenOpacity(lumenDays)" in html
    # the page comment names the deliberate rhyme with the planner's shape
    assert "log2(1+days/7)" in html
    assert "src/lab/curriculum.py" in html
    # the module clamps to the contract's window
    src = MODULE.read_text(encoding="utf-8")
    assert "LUMEN_FLOOR = 0.25, LUMEN_CEIL = 1.0" in src


def test_reduced_motion_stills_the_lumen_breathe():
    """The only pulsing the repaint adds (the freshest leaf's breathing wash)
    must hold steady under prefers-reduced-motion; the static glow stays."""
    html = PAGE.read_text(encoding="utf-8")
    assert "lumen-breathe" in html, "the fresh-leaf breathe animation exists"
    reduce_block = html.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    reduce_block = reduce_block.split("</style>", 1)[0]
    assert ".leaf-lumen { animation:none !important; }" in reduce_block


def test_the_committed_plant_bible_reference_exists_and_stays_small():
    """The PR is art-directed against docs/design/plant-bible/ — six plant
    portraits + four backdrops, shrunk to 512px/q80 so the committed reference
    stays around a third of a megabyte."""
    bible = Path(__file__).resolve().parent.parent / "docs" / "design" / "plant-bible"
    names = ["plant-bible-%s.jpg" % f
             for f in ("fern", "vine", "creeper", "succulent", "moss", "sprout")]
    names += ["backdrop-%s.jpg" % p for p in ("dawn", "day", "dusk", "night")]
    total = 0
    for name in names:
        p = bible / name
        assert p.exists(), "missing bible reference: %s" % name
        total += p.stat().st_size
    assert total < 1_000_000, "the committed bible reference must stay under ~1 MB"


def test_backdrops_are_reference_only_not_wired_into_the_live_page():
    """Phase 2 (backdrops on the live page) is gated on Ben; phase 1 commits
    them as reference only."""
    html = PAGE.read_text(encoding="utf-8")
    assert "backdrop-dawn" not in html
    assert "plant-bible/" not in html.replace("docs/design/plant-bible/", "")
