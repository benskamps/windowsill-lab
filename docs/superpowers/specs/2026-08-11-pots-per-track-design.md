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

Salvage §6b's "five pots in a row on the hero sill" is **not** built. That
version requires retiring the conservatory's figure row in the same change,
which collides head-on with the frozen `drawGarden` literal tests and with
`test_a_garden_card_draws_its_whole_ladder_not_only_the_measured_rungs`. The
sill stays **one plant, one pot** — the windowsill's oldest rule — but the hero
pot is now *the open track's pot*, so the vessel under the hero plant changes as
the rotation moves between sciences. The row of pots lives in the conservatory,
where six cards already exist and already carry the reading matter. Also unbuilt:
the og PNG re-render (the hero still truthfully shows one plant in one pot) and
any per-machine pot (a machine grows nothing; it waters).

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

- `node --test web/pots.test.mjs` — geometry, purity, distinctness, mark maths.
- `node --test web/growth-forms.test.mjs` — unchanged, must stay green.
- `python -m pytest tests/test_web_pots.py tests/test_web_growth_forms.py tests/test_turns.py tests/test_labhome.py -q`
- Full `python -m pytest` before landing.
- Manual: all six tracks forced on the hero; dawn/day/dusk/night walked with
  `advanceTime`; reduced motion; the conservatory at 1280px and 390px.
