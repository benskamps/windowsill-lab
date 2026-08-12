# Pots per track — "the pot wears the work"

Design addendum to `2026-08-07-plant-rethink-design.md` (the organ grammar) and
`docs/salvage-2026-08-01-reboot/design-spec-turns.md` §6b (the nod-gated
pot-per-track sketch). Ben's nod arrived 2026-08-11:

> "I'd like windowsill plants to each have their own pots so we can tell them
> apart from each other. We can invest more in each pot, so it can be fun,
> dynamic, and give visitors something to watch, as they read the new science…
> And I want the so-what so painfully clear, it hurts to see it at the top right
> before the windowsill. Windowsill is doing the work, and its effort, is the
> artform."

Two things ship: **a pot layer** and **a so-what strip**.

---

## 0. The one-paragraph design

A pot is a **track's identity** (a silhouette you can name at a glance) wearing
a **track's labour** (marks that are all re-derived from the feed, every render).
The silhouette is authored and constant — it answers *which science is this?*
The marks are data and only data — they answer *how hard has it been worked?*
Glaze climbs the wall as the ladder is climbed and stops at the frontier, leaving
raw clay above it. Scratches tally the runs. Chips and repair seams record the
nulls, kept in daylight the way the folded grey leaves are. A pot nobody has run
yet is bare, unglazed and unscratched — and still on the sill. Nothing on a pot
is decorative-and-untied; if a detail cannot be re-derived from `pot.json` it
does not ship.

## 1. Why a pot, and why now

The plant rethink gave six growth forms. `publish.GROWTH_FORMS` maps **six
tracks onto five forms** — `coherence` deliberately reuses `fern`, because a
coherence ladder *is* a convergence ladder and a seventh plant nobody asked for
would be a lie about the shape of the climb. So the page has two fern tracks and
no way to tell them apart. The pot is the honest answer: same plant, different
vessel. This is the reason the pot layer earns its place instead of being
decoration.

It also closes a live gap: `GARDEN_SPECS` shipped **five** cards under a heading
that says **"Six instruments. One standard of proof."** and metas that say "six
kinds of patient science" (asserted by `test_meta_descriptions_enumerate_every_track`).
The `coherence` track — three milestones, the *currently open experiment* K03 —
had no card at all. It gets one here.

## 2. What is NOT in this pass (and why)

**Amended mid-run, 2026-08-11.** Ben, while this was being built:

> "I want to see all of the pots out at once. Not one at a time."

So the sill *is* a garden. Every track gets a pot and a plant on the windowsill,
visible on load — no carousel, no tabs, no featured-one-with-the-rest-hidden, no
click-to-reveal as the mechanism for seeing a pot. This is salvage §6b's shelf,
built:

- **Layout.** Read left to right, the shelf is in curriculum order, with
  whichever experiment is OPEN standing full-size at the centre. That centre
  specimen is the existing `#plant` group, so it keeps the whole organ grammar,
  the growth theater, the bud, and every per-leaf field note — but it grows
  **only the bench track's own ladder** (see §2b). The others are
  placed either side at one shared scale — a sill whose left-hand pots are
  bigger than its right-hand ones reads as perspective, which is a claim about
  distance nobody made.
- **Geometry.** Every specimen is built in the canonical frame (root x=400, soil
  y=344, foot y=470) and placed with ONE attribute transform:
  `translate(cx − 400s, 470 − 470s) scale(s)`. So a flank is the same geometry
  as the centre, smaller, and every foot lands on the same board.
- **Flank plants** are drawn by `sillPlant()` — stem, one branch+leaf per closed
  milestone in its status colour, the unreached rungs dashed from the REAL tip
  up the shared height envelope (never a second build at full height, which
  re-parameterizes the form into a different, diverging plant).
- **One wind.** Every specimen rides the same 47s `sway` timeline, offset only by
  `--lag` = how far down the sill it stands, so a gust crosses the whole shelf.
  The placement transform is an attribute on the outer group and the animation is
  a class on an inner one, because a CSS transform overrides the attribute. A pot
  never sways; only the green thing above it does.
- **Enrichment on top.** Each flank is a focusable button that opens that track's
  latest field note. That is enrichment — it is never how a pot becomes visible.
- **Narrow viewports.** The scene is one SVG, so the whole shelf scales down
  together and all six stay on screen at 390px. It never degrades to one at a
  time.
- **Locked by test:** `test_the_sill_shows_every_track_at_once` and
  `test_the_shelf_rides_one_wind_and_the_clay_never_sways`.

### 2b. The centre grows only what is on the bench (amended 2026-08-12)

The shelf shipped with the centre still built from the WHOLE lab's milestone
ledger — the legacy hero plant — while standing in the bench track's pot. Ben,
the next morning, comparing the sill against the six conservatory cards below it:

> "it still seems to be 'all of the leafs in one' and it doesn't match the 6
> images."

He was right, and it was the one thing on the sill that could not be re-derived
from the vessel it stood in: 25 leaves from six sciences over a 34-rung ladder,
in a coherence pot whose own card is a sparse young fern with two. A pot wears
one track's labour; the plant in it has to be that same track's work or the
whole layer is decoration.

So the centre is now parameterized exactly the way a flank and a card are —
`benchLadder(milestones, heroTrack)`: the track's own milestones over the
track's own ladder length, its own growth-form archetype, its own open bud.
Bigger and richer, never different. It keeps everything the flanks don't have
(the stem ribbon, the per-leaf field notes, dew, phototropism, the breathing bud
husks, the growth theater); only the data set narrows. When the rotation moves
the bench to another science, the centre becomes that science's plant, form and
all — coherence's fern becomes compute's vine.

Three consequences worth naming:

- **Unreached rungs come to the centre.** One track's ladder is short, so compute
  at 1 of 4 would read as a snapped twig at centre stage — the exact defect the
  cards fixed. Same technique, same gotcha: dashed from the REAL tip up the
  shared height envelope (`GF._nodeY`), never a second build at full height,
  which re-parameterizes vine's coil and creeper's sweep into a diverging plant.
- **The theater's memory stays lab-wide.** `rememberClosedIds` is given the whole
  ledger's closed set, not the bench track's. What a visitor has already seen
  belongs to the visitor; storing one track's ids would make every other track's
  leaves read as brand-new news the next time the rotation came round.
- **The readout stopped lying.** `render_game_to_text()`'s `plant` block now
  reports `track`, `ladder`, `leaves` and `unreached` for the plant that is
  actually drawn, and the lab-wide counts moved to their own `ledger` key
  instead of being labelled leaves. The explainer's "the counts under the plant"
  became "the milestone counts under the sill are the whole lab's," which is
  what they were all along.

Copy needed no hedge: "Every leaf is one real experiment" was true of a whole-lab
plant and is true of a per-track one. Locked by `web/centre-plant.test.mjs`
(behavioural, run against the committed feed, negative control on the 2-vs-25
gap) and two guards in `tests/test_web_growth_forms.py`.

Still not in this pass: the og PNG re-render (the social card still shows one
plant in one pot — true of the page until this lands), retiring the conservatory
figure row (it collides with the frozen `drawGarden` literal tests and the
2026-08-06 whole-ladder guard), and any per-machine pot — a machine grows
nothing; it waters.

## 3. Architecture

```
web/pots.js  (pure, no DOM, test-imported, INLINED into index.html like growth-forms.js)
  POTS.marksFrom(stats) -> { glaze, tally, chips, seams, matte, patina, damp, virgin, runs }
      the ONLY place feed numbers become pot character
  POTS.build(track, marks, geom) -> pathSpec[]
      local coordinates: origin = the MOUTH CENTRE, +y down, +x right;
      geom = { mouth, depth } — mouth = rim outer half-width, depth = mouth→foot
  POTS.TRACKS / POTS.DEFAULT_TRACK — the registry, mirroring GROWTH_FORMS' keys

index.html painter
  drawPot(track, marks, target, geom)  — instances a pathSpec[] under one
      translate; used by BOTH the hero vessel (#pot-vessel) and each
      conservatory card (a .specimen-pot group)
```

Same discipline as `growth-forms.js`: one module file, one inlined copy between
`<!-- BEGIN pots.js … -->` / `<!-- END pots.js (inlined) -->`, one byte-for-byte
pytest guard (`tests/test_web_pots.py`), one behavioural node suite
(`web/pots.test.mjs`).

**Invariants the module owes the page** (asserted in the node suite):

- the mouth is shared: every pot's rim spans exactly `±mouth` at local y=0, and
  every pot's inner mouth is `±62·(mouth/70)` — so the soil ellipse, the root
  collar, and every growth form's root at `CX` land in the same place in all
  seven vessels. One sill, one soil line.
- the foot is shared: every pot's lowest geometry is `depth`, so all pots stand
  on the same board.
- silhouettes are mutually distinct (body path strings differ pairwise).
- no `Math.random`, no `Date` inside `build` — pot geometry is a pure function
  of `(track, marks, geom)`.
- `build("no-such-track", …)` deep-equals `build(DEFAULT_TRACK, …)`.

## 4. The seven silhouettes

Every vessel is the same terracotta (`#clayGrad` / `#clayGradV`), the same
palette, one sky, one beam. Difference lives in **profile, rim, and feet** only —
never in hue, never in a label. (Salvage §6b's absolute guard: *no text, labels,
counts or machine marks on the sill, ever.*)

| track | form | vessel | why this shape |
|---|---|---|---|
| **physics** | fern | **the ladder pot** — the classic thrown terracotta: broad flared rim, gently bellied wall, three throwing ridges, no feet | the reference vessel. Physics is the calibration spine, so it keeps today's exact pot: continuity, not novelty |
| **coherence** | fern | **the coupled pot** — a pinched waist between two lobes, a rolled bead rim, a low ring foot | two oscillators finding each other. The waist is the coupling; it reads instantly against the physics fern in the same green |
| **compute** | vine | **the stepped pot** — five discrete faceted steps down the wall, a squared rim, four block feet | exact arithmetic has no smooth interior. A staircase, not a curve |
| **astronomy** | creeper | **the collecting dish** — a wide shallow bowl on a narrow stem and a flared base, rolled rim | a dish that gathers light over a long baseline. The widest mouth on the sill |
| **instrument** | succulent | **the bench crucible** — straight machined walls, a heavy double-banded collar, three tripod feet | lab glassware rendered in clay: dark noise, patient counts, a cell you clamp to a bench |
| **boinc** | moss | **the seed pan** — a strongly flaring pan with a broad foot ring pierced by many small drain slots | many small contributors draining into one tray |
| **misc / unknown** | sprout | **the nursery pot** — a plain thin-rimmed taper | the homogeneous default, exactly as `sprout` is for forms |

## 5. The marks — data → pot detail (the whole mapping)

All inputs come from `pot.json` for one track: its milestones, its rows in
`reports[]` (a row's `group_count` is how many runs that row collapses), the
declared cadence `turns.expected_interval_h`, and the reader's clock.

| pot detail | formula | source | what it says |
|---|---|---|---|
| **glaze line** (wall glazed from the foot up to a fraction of its height; raw clay above) | `glaze = closed / total` | milestones of the track: `closed = verified+review+null`, `total = track length` | how far up the ladder this science has climbed. **The unglazed band IS the open frontier** |
| **matte top band** (the topmost glazed band drawn without its specular — unfired) | `matte = reviews > 0` | milestone `status === 'review'` | a result whose checker passed and whose human read is still owed. The kiln is waiting on a person |
| **tally scratches** (short incised strokes above the foot, in gates of five) | `tally = min(12, round(sqrt(runs)))` | `Σ group_count` over the track's report rows | the labour. One scratch per √run, stated plainly so a 111-run pot is scratched, not shredded |
| **patina** (speckle count + wall darkening) | `patina = 1 − exp(−runs/25)`, continuous | same `runs` | wear that never saturates: a much-used pot keeps getting slightly darker forever |
| **rim chips** (a notch bitten out of the rim's *lower* edge — the top edge is the mouth, and the page paints the pot's dark interior over it) | `chips = min(4, nullRuns)` | report rows with `verdict === 'null'` | every miss the instrument actually ran |
| **repair seams** (a fine slip-filled line across the wall with two staples) | `seams = min(4, nullMilestones)` | milestones with `status === 'null'` | a boundary kept on the permanent record — mended in daylight, in-house clay slip, never gold |
| **damp ring** (a dark water band at the foot + the existing soil wet) | `damp = clamp01(1 − hoursSince(newest row)/(2·interval))`, `interval = turns.expected_interval_h ?? 16` | newest report `at` (else `date`) for that track | tended this turn vs resting. **Resting is never distress** — a track the rotation didn't schedule and a track whose turn failed both simply read dry |
| **bare pot** (no glaze, no scratches, no patina) | `virgin = runs === 0` | no report rows | a pot waiting for its first turn. It still stands on the sill: the sill filling over months is itself the story |

Values on the 2026-08-11 feed (34 milestones, 58 rows, 112 turns):

| track | closed/total | runs | glaze | tally | chips | seams | note |
|---|---|---|---|---|---|---|---|
| physics | 12/18 | 111 | 0.67 | 11 | 2 | 2 | the worked pot |
| coherence | 2/3 | 2 | 0.67 | 1 | 0 | 0 | hero vessel today (K03 open) |
| compute | 1/4 | 1 | 0.25 | 1 | 0 | 0 | |
| astronomy | 4/4 | 10 | 1.00 | 3 | 0 | 0 | fully glazed |
| instrument | 1/3 | 1 | 0.33 | 1 | 0 | 0 | |
| boinc | 0/2 | 0 | 0.00 | 0 | 0 | 0 | **bare** |

(Exact numbers are recomputed every render; this table is the read at authoring
time, not a stored value.)

## 6. Watchable, without a second wind

The one-wind one-light law is untouched. A pot is clay on a board: it does not
sway, it does not breathe, and the conservatory keeps the animator's no-wind
rule. What a pot does is **catch the light the scene already has**:

- **the glaze glint rides the sundial.** `#scene[data-sunside]` — already set by
  `placeSun` — swaps which side of the vessel carries its specular crescent, on
  the page's existing 3s opacity transition. The pot brightens on the side the
  sun is actually on, twice a day, with zero new JS and zero new keyframes.
- **dawn condensation.** The glazed band beads on the same
  `body[data-phase="dawn"] .dew { opacity }` rule the leaves use. Same register,
  no new lane.
- **the damp ring dries** over two cadence intervals through the existing 2.5s
  `--wet` transition — the pot goes visibly from just-watered to resting between
  turns.
- **night**: the raw clay above the glaze line stays matte at night while the
  glaze keeps a weak cool reflection — the frontier reads darker than the
  climbed wall.

Nothing loud, nothing per-frame, no rAF, no filters inside animated groups.

## 7. The so-what strip

Placed immediately before `.scene`, replacing the run-on `.tagline` paragraph.
Three rungs, biggest first, so it is read in the order it hurts:

1. **The goal**, at display size — the ambition, unhedged.
2. **Who does it and who gates it**, one line — the agents *and* the human, which
   must always travel together (that pairing is asserted by
   `test_the_concept_line_is_on_the_page`).
3. **What you are about to look at**, one line — including the sentence that
   makes the pots legible before the reader meets them.

Verbatim copy shipped:

> **The goal is a measurement nobody has made yet, given away free.**
>
> A fleet of AI agents wrote this instrument and keeps it running; a human decides what earns a leaf. Two home machines take the turns.
>
> Below: six pots on one windowsill, one for each science. Every leaf is one real experiment — green means a person checked it, amber is waiting for one, grey is a miss we kept on purpose. And the pots wear the work: the glaze climbs as a track climbs, the scratches count its runs, the chips are its failures.

No new hedge is introduced. The existing balance is untouched and still asserted:
the ambition is here and repeated at the curriculum, `"That is the destination,
not the status."` and `"does not jump from a pretty simulation to a discovery
claim"` keep their places further down the page. Ambition at the top,
discipline where the claims are made — that ordering is the point.

## 8. Don't-do list (binding, extends §14 of the plant spec)

1. **No pot detail without a formula.** Every scratch, chip, seam, band and
   speckle in §5 has a row in that table. A new detail needs a new row or it
   does not ship.
2. **No status hue on a vessel.** Green/amber/grey belong to leaves. Pots are
   clay. A pot must never rank or claim.
3. **No text on the sill** — no counts, no labels, no machine marks. Ever.
4. **No pot per machine, no pot per milestone, no pot per phase.** A pot answers
   "what is growing?". The cap is the track taxonomy; a seventh pot requires a
   seventh science.
5. **Resting is never distress.** Dry is dry. Missed cadence lives in the
   legend, the footer and the freshness line — never as a sick-looking plant.
6. **No second wind, no pot animation lane, no filters, no `Math.random`,**
   no `Date` inside `build`.
7. **The mouth and the foot are law.** Every vessel shares the soil line and the
   board. Expressiveness lives between them.
8. **Do not skip the inline re-sync** after any `pots.js` edit — the byte-for-byte
   test will catch you, but don't make it.

## 9. Guards

- `node --test web/*.test.mjs` — pots (geometry, purity, distinctness, mark
  maths), growth forms (unchanged, must stay green), and the centre plant's data
  set. The glob, not a named file: `web/pots.test.mjs` shipped 2026-08-11 and CI
  never once ran it, because the workflow named `growth-forms.test.mjs` by hand.
- `python -m pytest tests/test_web_pots.py tests/test_web_growth_forms.py tests/test_turns.py tests/test_labhome.py -q`
- Full `python -m pytest` before landing.
- Manual: all six tracks forced on the hero; dawn/day/dusk/night walked with
  `advanceTime`; reduced motion; the conservatory at 1280px and 390px.
