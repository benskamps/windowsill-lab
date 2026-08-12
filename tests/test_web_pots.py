"""Guards for the pot layer (``web/pots.js`` + its wiring in ``web/index.html``).

Same shape as ``test_web_growth_forms.py``: the page ships as a single
downloadable file, so the pot registry is INLINED and must not drift from its
module. Stdlib only — the behavioural proof of the geometry lives in
``web/pots.test.mjs`` (``node --test``).

What is asserted here is the part a future edit could quietly break: that the
pot is a *record*, not decoration. Every mark on a vessel has to be derived from
the feed in the page's own code, no vessel may carry a status hue, and nothing
may print a number on the sill.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
MODULE = WEB / "pots.js"
PAGE = WEB / "index.html"
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-08-11-pots-per-track-design.md"

BEGIN = "<!-- BEGIN pots.js (inlined; source of truth: web/pots.js) -->"
END = "<!-- END pots.js (inlined) -->"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _inlined_block() -> str:
    html = _page()
    assert BEGIN in html, "pots BEGIN marker missing from index.html"
    assert END in html, "pots END marker missing from index.html"
    inner = html.split(BEGIN, 1)[1].split(END, 1)[0]
    open_tag = inner.index("<script>") + len("<script>")
    close_tag = inner.rindex("</script>")
    return inner[open_tag:close_tag].strip()


def test_module_file_exists_and_is_nonempty():
    assert MODULE.exists(), "web/pots.js (the source of truth) is missing"
    assert MODULE.read_text(encoding="utf-8").strip(), "pots.js is empty"


def test_inlined_block_matches_module_source():
    """No drift: the inlined page copy == the standalone module, byte for byte.
    If this fails, edit web/pots.js then re-sync the block in index.html."""
    module_src = MODULE.read_text(encoding="utf-8").strip()
    assert _inlined_block() == module_src, (
        "index.html's inlined pots block has drifted from web/pots.js — "
        "re-sync the block between the markers."
    )


def test_every_track_in_the_taxonomy_has_a_vessel():
    """The cap IS the track taxonomy. A seventh pot requires a seventh science,
    and a track publish.py can emit must never fall through to the default by
    accident."""
    src = MODULE.read_text(encoding="utf-8")
    from lab import publish

    for track in publish.TRACKS.values():
        assert f"  function {track}(" in src, f"no vessel builder for track {track!r}"
        assert f"    {track}: {track}," in src, f"track {track!r} not in the registry"
    assert 'DEFAULT_TRACK = "misc"' in src


def test_the_pot_layer_is_pure_geometry():
    """A pot must draw the same on every visit and every machine: no randomness,
    no clock, no DOM inside the module."""
    src = MODULE.read_text(encoding="utf-8")
    assert "Math.random" not in src
    assert "Date.now" not in src and "new Date" not in src
    assert "document." not in src


def test_the_page_draws_pots_from_the_registry_and_from_the_feed():
    html = _page()
    # the hero wears the OPEN track's vessel
    assert "var heroTrack = pageTrack(milestones);" in html
    assert "paintPot($('pot-vessel'), heroTrack, heroMarks" in html
    assert 'id="pot-vessel"' in html
    # ...and every conservatory card wears its own
    assert "paintPot(potG, spec.track," in html
    assert "potMarksFor(spec.track, milestones, reports, _lastFeedState)" in html
    # the marks come from PT.marksFrom, the single derivation site
    assert html.count("PT.marksFrom({") == 1
    assert "function potMarksFor(track, milestones, reports, state)" in html


def test_every_pot_mark_is_derived_from_the_feed():
    """The whole contract of the layer: silhouette is authored, marks are data.
    Each of these is the feed field the mark claims to report."""
    html = _page()
    block = html.split("function potMarksFor(", 1)[1].split("function pageTrack(", 1)[0]
    for source in (
        "ms.filter(isClosed).length",          # glaze — the ladder climbed
        "m.status === 'review'",               # the unfired band — a human read owed
        "m.status === 'null'",                 # repair seams — boundaries kept
        "Number(r.group_count)",               # tally + patina — the labour
        "r.verdict === 'null'",                # chips — misses actually run
        "state.turns.expected_interval_h",     # damp — tended vs resting
    ):
        assert source in block, f"pot mark no longer derived from {source!r}"
    # no invented numbers: the derivation reads the ledger, never the feed's
    # top-level provenance (that is the publishing box, not the work).
    assert "state.provenance" not in block


def test_the_hardcoded_hero_pot_is_gone():
    """The old pot was a fixed path pair — one silhouette forever, and no way to
    tell two tracks apart. If it comes back, the layer has been bypassed."""
    html = _page()
    assert "M354 470 C348 434 345 398 343 362" not in html
    assert "M338 366 L462 366 L470 344 L330 344 Z" not in html


def test_no_status_hue_and_no_text_ever_lands_on_a_vessel():
    """Green/amber/grey belong to leaves; pots are clay. And the sill carries no
    labels, counts, or machine marks — ever."""
    src = MODULE.read_text(encoding="utf-8")
    for hue in ("#7fae6b", "#d2aa67", "#8a8f82", "var(--leaf)", "var(--review)", "var(--null)"):
        assert hue not in src, f"status hue {hue} on a vessel"
    for text_api in ("createTextNode", "textContent", "<text"):
        assert text_api not in src, "a pot must never print a number on the sill"


def test_the_conservatory_shows_every_track_it_claims_to():
    """The heading and the metas said SIX; GARDEN_SPECS shipped five, and the
    coherence track — three milestones, and the currently open experiment — had
    no card at all. The pot layer makes the taxonomy load-bearing, so this is
    the assertion that keeps the two in step."""
    html = _page()
    from lab import publish

    specs = html.split("var GARDEN_SPECS = [", 1)[1].split("];", 1)[0]
    for track in publish.TRACKS.values():
        assert f"track:'{track}'" in specs, f"no conservatory card for track {track!r}"
    assert "Six instruments. One standard of proof." in html
    # coherence deliberately reuses the fern — the POT is what separates them
    assert "{ track:'coherence', form:'fern'" in specs
    assert "{ track:'physics', form:'fern'" in specs


def test_the_pots_add_no_animation_lane():
    """One wind, one light. A pot is clay on a board: it rides the sundial and
    the phase fades the page already runs, and adds nothing of its own."""
    html = _page()
    pot_css = html.split("/* ── The pots ─", 1)[1].split("/* The open experiment", 1)[0]
    rules = re.sub(r"/\*.*?\*/", "", "/*" + pot_css, flags=re.S)
    assert "animation" not in rules, "a pot grew its own animation lane"
    assert "@keyframes" not in rules
    # the only motion a pot is allowed is the page's shared opacity fade
    assert "transition:opacity" in rules
    # it reuses the plant's sundial attribute and the leaves' dew rule
    assert '#scene[data-sunside="left"]  .pot-glint.l' in pot_css
    assert 'cls: "dew"' in MODULE.read_text(encoding="utf-8")


def test_the_so_what_strip_sits_immediately_before_the_windowsill():
    """The reader should meet the ambition and then, in the same breath, the
    plants doing the work — so the strip is the last thing before the scene."""
    html = _page()
    assert '<section class="sowhat"' in html
    strip = html.split('<section class="sowhat"', 1)[1]
    before_scene, sep, _ = strip.partition('<div class="scene" id="scene">')
    assert sep, "the so-what strip is not above the scene"
    assert "</section>" in before_scene
    # nothing but the strip stands between it and the sill
    assert "<section" not in before_scene.split("</section>", 1)[1]

    # the three rungs, in order: what it is FOR, who does it and who gates it,
    # and how to read what you are about to see.
    goal = html.index("The goal is a measurement nobody has made yet, given away free.")
    who = html.index("A fleet of AI agents wrote this instrument and keeps it running")
    read = html.index("Below: six pots on one windowsill, one for each science.")
    scene = html.index('<div class="scene" id="scene">')
    assert goal < who < read < scene


def test_the_so_what_strip_makes_the_pots_legible_before_they_are_seen():
    """Ben's ask was that the effort be the artform. A visitor who is not told
    the pot is a record reads it as a flowerpot, and the whole layer is wasted."""
    html = _page()
    assert ("the pots wear the work: the glaze climbs as a track climbs, "
            "the scratches count its runs, the chips are its failures.") in html


def test_the_strip_states_the_ambition_without_adding_a_new_hedge():
    """The balance the 2026-08-06 framing pass fought for is unchanged: the
    ambition is at the top, the discipline stays where the claims get made.
    Neither half may quietly migrate into the other."""
    html = _page()
    strip = html.split('<section class="sowhat"', 1)[1].split("</section>", 1)[0]
    for hedge in ("not a new result", "destination, not the status",
                  "does not jump from a pretty simulation", "no claim is made"):
        assert hedge not in strip, f"the so-what strip re-hedged: {hedge!r}"
    # ...and the disclaimers are all still on the page, further down
    assert "That is the destination, not the status." in html
    assert "does not jump from a pretty simulation to a discovery claim" in html


def test_the_design_addendum_ships_with_the_layer():
    """A pot detail with no row in the mapping table is decoration. The table is
    the contract; it travels with the code."""
    assert SPEC.exists(), "the pots-per-track design addendum is missing"
    text = SPEC.read_text(encoding="utf-8")
    for mark in ("glaze line", "tally scratches", "rim chips", "repair seams",
                 "damp ring", "matte top band", "patina", "bare pot"):
        assert mark in text, f"{mark!r} has no row in the data -> pot mapping"


def test_the_sill_shows_every_track_at_once():
    """Ben, 2026-08-11 (mid-run steering): "I want to see all of the pots out at
    once. Not one at a time."

    The hard criterion, made mechanical: every track in the feed's taxonomy gets
    a pot AND a plant on the sill on load. The mechanism for seeing a pot may
    never be a tap — no carousel, no tabs, no featured-one-with-the-rest-hidden.
    Tap enrichment on top is welcome, and is what the click handler is for.
    """
    html = _page()
    from lab import publish

    # one painter, driven by the track list, called from the render path
    assert 'id="sill-garden"' in html
    assert "function drawSillGarden(milestones, reports, state, openTrack)" in html
    assert "var shelf = drawSillGarden(milestones, state.reports, state, heroTrack);" in html
    # every non-centre track is placed by iterating the SPEC list, not a subset
    assert "GARDEN_SPECS.slice(0, at)" in html
    assert "GARDEN_SPECS.slice(at + 1)" in html
    # ...and the centre one is the full-size #plant, so the union is every track
    shelf = html.split("function drawSillGarden(", 1)[1].split("\n    }", 1)[0]
    assert "host.appendChild(outer)" in shelf
    assert len(publish.TRACKS) == len(
        html.split("var GARDEN_SPECS = [", 1)[1].split("];", 1)[0].split("{ track:")
    ) - 1

    # the readout names how many pots are actually on the sill, so a regression
    # to one-at-a-time is visible to the harness and not only to an eye
    assert "pots_visible: shelf.length + 1" in html

    # nothing is gated behind a reveal
    for gate in ("carousel", "data-slide", 'hidden = true;  // pot', "click-to-reveal"):
        assert gate not in shelf, f"a pot was put behind {gate!r}"
    # the click handler exists, but as ENRICHMENT: it opens a field note, it is
    # not how a pot becomes visible
    assert "openFieldNote(built.focus, outer)" in shelf


def test_the_shelf_rides_one_wind_and_the_clay_never_sways():
    """One wind: every specimen shares the 47s `sway` timeline, offset only by
    how far down the sill it stands. And the animation sits on an INNER group,
    because a CSS transform would otherwise clobber the placement attribute."""
    html = _page()
    shelf_css = html.split("/* The shelf rides the SAME wind", 1)[1].split("/* ── The pots", 1)[0]
    assert "animation: sway 47s ease-in-out infinite" in shelf_css
    assert "animation-delay: calc(var(--lag, 0) * -1s)" in shelf_css
    # exactly one keyframe name is used by the shelf — no second wind
    assert shelf_css.count("animation:") + shelf_css.count("animation-play-state") == 2

    shelf = html.split("function drawSillGarden(", 1)[1].split("\n    }", 1)[0]
    # placement is an attribute on the outer g; the wind is a class on an inner g
    assert "outer.setAttribute('transform', 'translate(" in shelf
    assert "wind.setAttribute('class', 'sill-wind')" in shelf
    # the pot is painted into the OUTER group — clay does not sway
    assert "paintPot(outer, spec.track," in shelf
    assert "paintPot(wind" not in shelf
    # reduced motion kills it with everything else
    assert ".sill-wind { animation: none; }" in html or "#bud-tip .breath, .sill-wind { animation: none; }" in html


# ── "All of the pots out at once" ─────────────────────────────────────────────
# Ben, 2026-08-11, mid-build: "I want to see all of the pots out at once. Not one
# at a time." This block is the hard acceptance criterion, written as a guard so
# a later refactor cannot quietly walk it back into a carousel.


def test_every_track_has_a_pot_on_the_sill_at_once():
    """The sill is a shelf, not a slideshow.

    Every track in publish.TRACKS gets a pot and a plant in the ONE scene, on
    load: the open experiment stands full-size at the centre (the #plant group,
    carrying the whole organ grammar) and `drawSillGarden` places every other
    track beside it. No track is reachable only by clicking.
    """
    html = _page()
    from lab import publish

    # the shelf host lives inside the scene svg, above the centre plant
    scene = html.split('<div class="scene" id="scene">', 1)[1].split("</svg>", 1)[0]
    assert '<g id="sill-garden"></g>' in scene, "no shelf group in the scene"
    assert '<g id="pot-vessel"></g>' in scene, "no centre pot in the scene"

    # it is painted from render(), on the same pass as the centre plant — not
    # from a click handler, a hash change, or an IntersectionObserver
    render_block = html.split("function render(state)", 1)[1].split("function wetFromRun", 1)[0]
    assert "drawSillGarden(milestones, state.reports, state, heroTrack)" in render_block
    assert "paintPot($('pot-vessel'), heroTrack" in render_block

    # and it walks the whole taxonomy, skipping only the track already standing
    # at the centre — so centre + shelf == every track, always
    shelf = html.split("function drawSillGarden(", 1)[1].split("\n    }", 1)[0]
    assert "GARDEN_SPECS.forEach" in shelf or "GARDEN_SPECS.filter" in shelf
    assert "sp.track !== openTrack" in shelf, "the shelf must cover every non-centre track"
    assert "paintPot(outer, spec.track," in shelf, "a shelf slot without its own pot"
    specs = html.split("var GARDEN_SPECS = [", 1)[1].split("];", 1)[0]
    for track in publish.TRACKS.values():
        assert f"track:'{track}'" in specs, f"track {track!r} can never reach the sill"


def test_NEGATIVE_no_pot_is_hidden_behind_an_interaction():
    """A carousel, a tab strip, or a collapsed default state would satisfy every
    other assertion here and still break the ask. So: nothing in the shelf may
    hide a slot, and tapping is enrichment on top of an always-visible shelf."""
    html = _page()
    shelf = html.split("function drawSillGarden(", 1)[1].split("\n    }", 1)[0]
    shelf += html.split("function sillPlant(", 1)[1].split("\n    }", 1)[0]
    for gate in ("hidden", "display:none", "display: none", "aria-expanded",
                 "carousel", "scrollIntoView", "activeSlide", "aria-selected"):
        assert gate not in shelf, f"a pot is gated behind {gate!r}"
    # the click handler opens a field note; it never creates or reveals the slot
    assert "outer.addEventListener('click'" in shelf
    assert "openFieldNote(built.focus, outer)" in shelf
    host_clear = "host.textContent = '';"
    assert host_clear in shelf, "the shelf must be rebuilt wholesale, not toggled"


def test_the_whole_shelf_rides_one_wind():
    """All the plants animate at once, and that must not cost six clocks. Every
    specimen rides the SAME 47s `sway` timeline as the centre plant, offset by a
    negative delay (position lag) rather than a timer of its own."""
    html = _page()
    assert html.count("@keyframes sway") == 1, "a second wind appeared"
    assert "animation: sway 47s ease-in-out infinite" in html          # the centre plant
    assert ".sill-wind { transform-box:fill-box" in html
    shelf_css = html.split(".sill-wind {", 1)[1].split("}", 1)[0]
    assert "animation: sway 47s ease-in-out infinite" in shelf_css
    assert "animation-delay: calc(var(--lag, 0) * -1s)" in shelf_css
    # no per-plant JS clock anywhere in the shelf
    shelf = html.split("function drawSillGarden(", 1)[1].split("\n    }", 1)[0]
    for timer in ("setInterval", "setTimeout", "requestAnimationFrame"):
        assert timer not in shelf, f"the shelf started its own {timer} clock"
    # ...and reduced motion stops the whole shelf with everything else
    reduce_block = html.split("@media (prefers-reduced-motion: reduce)", 1)[1].split("}\n", 1)[0]
    assert ".sill-wind" in html.split("@media (prefers-reduced-motion: reduce)", 1)[1][:2000]


def test_the_harness_can_count_the_pots_that_are_out():
    """`render_game_to_text()` reports how many pots are standing, so a browser
    pass (and a future regression) can assert the number instead of eyeballing."""
    html = _page()
    assert "pots_visible: shelf.length + 1" in html
    assert "centre: heroTrack" in html
    assert "shelf: shelf" in html
