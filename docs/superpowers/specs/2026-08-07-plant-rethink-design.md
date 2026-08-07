# The Windowsill Plant Rethink — "One plant, one light, one wind"

Implementation spec for `web/index.html` + `web/growth-forms.js` in
`C:/Users/beschipp/projects/_workspaces/windowsill-plant-rethink/`.
One implementer, no open questions. Everything below was verified against the
actual files on 2026-08-07; line numbers are current.

---

## 0. The one-paragraph design

The plant stops being a stroked wire with lenses glued on and becomes a small
number of composed systems: a **tapered ribbon stem** sampled from the exact
geometry growth-forms.js already emits; **one organ per closed milestone**,
built from a per-form archetype (petiole → blade/frond/pad/tuft) in *local
coordinates* and placed with a single translate+rotate, so attachment, age
pitch, and flutter pivot are correct by construction; **one lighting rule**
(the scene's real sun, exposed as two data attributes, modulates lit edges,
powers a brief dawn/dusk backlight, and beads deterministic dew); and **one
wind** (a 47s shared gust timeline the stem and every leaf ride, lagged by
ladder height, dying at night to leave only the breathing bud). Nothing new
counts, claims, or randomizes. The null stays grey, folded, still, and painted
last. All six forms keep the same root, the same tip height, the same feed
contract, and the same 44px focusable field-note wiring.

---

## 1. Verified ground truth (do not re-derive; these are checked facts)

**growth-forms.js** (278 lines, also INLINED in index.html lines ~1211–1491):
- `build(ctx) -> { stem, nodes:[{x,y,dir,t}], tip:{x,y} }`; `CX=400`;
  `_tipY/_nodeY/_tipFrac` exported; six builders (fern cubic, vine 18-seg
  polyline coil, succulent 3-point spine + golden-angle rosette, creeper
  16-seg one-sided sweep, moss mat-outline+sprig in ONE path string, sprout
  quadratic). `t = (i+1)/max(1,total)`.
- `tests/test_web_growth_forms.py::test_inlined_block_matches_module_source`
  requires the inlined copy to equal the module **byte for byte**. Every module
  edit ends with re-syncing the block between
  `<!-- BEGIN growth-forms.js (inlined; …) -->` and `<!-- END … -->`.
- `web/growth-forms.test.mjs` asserts: nodes.length===count (counts 0/1/6/20),
  finite x/y, dir∈{1,-1}, shared tip height/x across all six forms, mutually
  distinct stem strings, node-layout distinctness via `[x,y]` signatures,
  fern nodes within 1px of CX (`fernSpread < 1` — so do NOT snap fern nodes
  onto its curved stem), and `deepEqual(build("tumbleweed"), build(DEFAULT))`
  (additive keys are safe: both sides run the same builder).

**index.html** (3358 lines):
- Plant markup (lines 906–915): `#plant` group contains: collar ellipse
  (6×3, `#4d7a3e`, at 400,344) → `#stem` (stroke `url(#stemGrad)`, width 5) →
  `#leaves` → `#bud-halo` → `#bud` → `#flower`. `#plant` sways
  (`sway 11s alternate`, origin `400px 344px`), `.scene:hover/.scene:focus-within`
  pauses it (line 245).
- `.leaf` (line 251): `transform-box: fill-box; transform-origin: center;
  animation: flutter var(--fdur,7s) alternate` — the center pivot is the bug
  the animator flagged. `.leaf.null-leaf { animation:none }`.
- `milestoneLeaf(x,y,dir,m,color,t)` (lines 1797–1934): quadratic lens blade,
  crease (null), lit-edge retrace, midrib, 2 side-veins, `circle.leaf-hit`
  r=22, `<title>`, `makeLeafInteractive` (tabindex=0, role=button, aria-label,
  click/keydown → `openFieldNote`). Null: class `leaf null-leaf`, opacity 0.78,
  fill `#8a8f82`. Review fill `#d2aa67`. Verified fill
  `shade(SEASON_LEAF[season], (seed%17)-8)`.
- `drawStalk` (1690–1765): builds geo, sets `$('stem')` d, paints living
  leaves then folded nulls LAST, positions bud/halo (tabindex, aria, title,
  `data-on`), calls `drawFlower`.
- `leafSeed(id)` (1786): hash mod 997. `shade(color, amt)` (1770) accepts hex
  or its own rgb() output.
- `placeSun(now)` (1519–1546): `frac = minutes/1440`, `x = 200+frac*400`,
  `day = h>=6 && h<19`, `arc = sin(frac·π)` (day) — **note: arc ≥ 0.7 for all
  day hours; never use `arc < 0.3` as a "sun low" gate** — moves `#sun-g`,
  `#beam`, `#pot-shadow`. Runs at boot via `applyPhase` BEFORE the first
  `render()` (boot block, lines 2851–2858), then every 60s via
  `refreshAmbient`.
- Phase palette: CSS vars per `body[data-phase]` (lines 72–105) incl. `--sun`,
  `--spill`, `--beam`, `--amb`. SVG gradient stops already read CSS vars
  (e.g. `stop-color="var(--sky-top)"` + `.sky-stop` transition) — the pattern
  is proven in this codebase.
- Reduced motion kill list (lines 698–710) zeroes `#plant, .dust, .star,
  .clouds, .leaf, .firefly, #bud-halo, .meteor` and holds the night halo at
  steady 0.6.
- Feed lifecycle: boot renders `{empty:true}` (DEFAULT_MILESTONES=[]), then
  `loadFeed()`; re-render only when the pot.json **bytes changed**
  (`_lastPotText`), every 5 min. `window.advanceTime(ms)` +
  `window.render_game_to_text()` exist for harness testing.
- `drawGarden` (2436–2640) is **frozen by literal source-string tests**. Do
  not restructure it. Load-bearing literals (from
  `tests/test_web_growth_forms.py`):
  `"function drawGarden(milestones, reports)"`,
  `"count:closed.length, total:total"`, `"count:closed.length, total:total, openProg:progress"`,
  `"reportForMilestone(reports, latest && latest.id)"`,
  `"specimen-leaf ' + (milestone.status"`,
  `"openFieldNote(focusMilestone, action)"`, `"garden: garden"`,
  `html.count("GF.build(spec.form, {") == 1`,
  `"stem.setAttribute('d', geo.stem)"`,
  `"var reached = closed.length + (open ? 1 : 0);"`,
  `"GF._nodeY(env, g)"`, `"if (GF._nodeY && total > reached) {"`,
  CSS selectors `path.specimen-stem.unreached`,
  `path.specimen-branch.unreached`, `.specimen-leaf.unreached`,
  `'[data-settled="true"] .garden-specimen { animation:none'`.
  Also page-level: `<svg viewBox="0 0 800 560" role="group"` must survive;
  `GF.pageGrowthForm(milestones)` and `GF.build(formName` must appear.
- Before renaming ANY keyframe/function, grep `tests/*.py` for the name. This
  spec renames nothing: keyframe `sway` keeps its name (new body), `flutter`
  keyframes are deleted (grep first to confirm no test coupling), function
  names `drawStalk`/`milestoneLeaf` are kept.

---

## 2. Architecture — division of labor (decided once)

```
growth-forms.js  (pure, no DOM, test-imported)
  build(ctx) -> { stem, nodes, tip,          // unchanged, byte-compatible
                  spine,                      // NEW: root→tip centerline path
                  mat }                       // NEW: moss only, closed colony silhouette
  nodes[i] gains: out                         // NEW: world radians — the direction
                                              // this node's organ leaves the stem
  (geometry decisions — where, which way — live here)

index.html painter (drawStalk + milestoneLeaf + ARCHETYPES)
  - ribbon stem: samples #stem's path via getTotalLength/getPointAtLength
    (DOM has the arc-length math; the module never duplicates it)
  - ARCHETYPES: one blade-organ builder per form, in LOCAL coordinates
    (origin = attachment, +x = outward), instanced with translate+rotate
  - paint order, status colors, a11y wiring, motion custom properties
  (rendering decisions — how it looks — live here)
```

The visionary's full parts-compiler is NOT adopted (see §13): the six build
functions stay as they are, plus small additive emissions. The archetype
library realizes the same "one painter per organ kind" idea where it actually
pays — in the paint layer.

**Organ group hierarchy (defined once — this resolves animator-vs-botanist):**

```
<g class="leaf [null-leaf]" data-mid data-dir>      world space; NO transform;
 │                                                   tabindex/role/aria/title/click
 ├─ [creeper null] path.runner-dead                  world space (dashed overdraw)
 ├─ <g class="place" transform="translate(x y) rotate(R)">   attribute transform ONLY
 │    └─ <g class="wind">                            CSS-animated (leaf-wind);
 │         │                                         transform-box: fill-box;
 │         │                                         transform-origin: 0% 50%  ← hinges
 │         │                                         at the attachment edge, because
 │         │                                         local (0,0) IS the attachment
 │         └─ archetype paths: petiole, faces, rim, veins, detail, glow, dew
 ├─ [creeper low nodes] rootlet paths                world space (pinned; never sway)
 └─ <circle class="leaf-hit" r="22">                 world space
```

Rules this hierarchy encodes:
- **Never put a CSS transform animation on an element that carries a
  `transform` attribute** (CSS transform overrides the attribute). `.place`
  owns the attribute; `.wind` owns the animation.
- Flutter/wind pivots at the attachment without `transform-box: view-box`
  (Safari risk): archetypes are drawn at final size in local coords with the
  attachment at (0,0) extending toward +x, so `fill-box` + origin `0% 50%`
  is the hinge. No per-leaf JS origin bookkeeping.
- Things that must not sway (hit target, rootlets, the null's dead-runner
  overdraw) live in the outer world-space g.

---

## 3. growth-forms.js changes (all additive; re-sync the inline block after)

Coordinate convention: SVG screen space, +y down. Stem tangent `ang` points in
the direction of growth (upward ⇒ ang ≈ −π/2). **`out = ang + dir·π/2`**
(verified: ang=−π/2, dir=+1 → out=0 → +x/right; dir=−1 → out=−π → left).

Per form, emit `out` on every node and `spine`:

| form | `out` per node | `spine` |
|---|---|---|
| fern | finite-difference its cubic: f = (node.y − base)/(top − base) clamped to [0.02, 0.98]; B(f±0.01) with the standard cubic point formula; ang = atan2(Δy, Δx); out = ang + dir·π/2. Do NOT move node.x (test: fernSpread < 1; the ≤3px seam is hidden by ribbon + petiole). | === stem |
| vine | segment tangent at the node's height from its own polyline (`atan2(y[s]−y[s−1], x[s]−x[s−1])`); out = ang + dir·π/2 | === stem |
| creeper | same polyline method; dir is always −1 | === stem |
| succulent | radial from rosette center: out = atan2(node.y − cy, node.x − CX) where cy = base − 20 (pads point outward from the crown) | === stem |
| moss | out = −π/2 (tufts point up; the archetype adds seeded splay) | `"M400 344 L400 <top>"` (the sprig only) |
| sprout | finite-difference its quadratic (same clamp as fern); out = ang + dir·π/2 | === stem |

`moss` additionally returns `mat`: a **closed, bumpy colony silhouette**
replacing nothing (the composite `stem` string stays exactly as today so the
garden minis are unchanged). Construction: for u in 0..1 at 12 samples across
[CX−mw, CX+mw], y(u) = matY − 4.2·sin(π·u) − 2.2·sin(3π·u + count·0.7)
(count-seeded phase — deterministic, evolves as the colony grows); emit
L-segments, close along the soil line back to (CX−mw, matY), `Z`.

**Test additions** (growth-forms.test.mjs — new asserts, no edits to existing):
- every node of every form has finite `out`;
- `spine` is a valid path for all six; `spine === stem` for all but moss;
- moss `mat` is a valid closed path (`/Z\s*$/`);
- (already covered) nodes.length === count remains the organ-count honesty guard.

Then: **copy the whole module verbatim into the inline block** (this is a
mechanical step; a small script or careful paste — the test diff will tell you
if you drifted).

---

## 4. The stem — tapered ribbon with a sun-side edge (painter technique)

In `drawStalk`, after `$('stem').setAttribute('d', geo.spine || geo.stem)`
(note: #stem now carries the SPINE — identical to stem for five forms; for
moss it's the sprig, and the mat gets its own fill, §below):

1. Sample once per render (never per frame):
   `var L = stemEl.getTotalLength(); var pts = []; for (var s=0; s<=22; s++)
   pts.push(stemEl.getPointAtLength(L*s/22));`
2. Unit normals from successive points; **flip guard**: if
   `dot(n[i], n[i−1]) < 0` negate n[i] (vine's coil needs this; ~4 lines).
3. Half-width with root flare:
   `w(f) = f < 0.06 ? lerp(4.6, 2.7, f/0.06) : lerp(2.7, 0.9, (f−0.06)/0.94)`
   (≈9px collar, ≈5.4px low stem — matches today's visual weight — 1.8px tip).
4. Closed polygon: up the left offsets, down the right; write to `#stem-body`.
5. Edge highlights: two open paths along the left/right offset points
   (skip the bottom 8% and top 6% of samples), written to `#stem-edge-l` /
   `#stem-edge-r`; stroke `#a5d18d`, width 1, linecap round.

**Static markup change** inside `#plant` (all additive siblings; no renames):

```html
<g id="plant">
  <ellipse cx="400" cy="344" rx="6" ry="3" fill="#3c5f30"/>      <!-- collar, darkened -->
  <ellipse cx="400" cy="344" rx="16" ry="5" fill="url(#soilAO)"/> <!-- root-collar AO -->
  <path id="mat" fill="#3f5433" stroke="#2c3d24" stroke-width="0.8" opacity="0" d="M0 0"/>
  <path id="stem-body" fill="url(#stemGrad)"/>
  <path id="stem" d="M400 344 C400 320 400 300 400 280" fill="none"
        stroke="#3a5c2f" stroke-width="1.7" stroke-linecap="round" opacity="0.55"/>
  <path id="stem-edge-l" class="stem-edge" fill="none" stroke="#a5d18d" stroke-width="1" stroke-linecap="round"/>
  <path id="stem-edge-r" class="stem-edge" fill="none" stroke="#a5d18d" stroke-width="1" stroke-linecap="round"/>
  <g id="leaves"></g>
  … #bud-halo, #bud-tip (new, §7), #bud, #flower unchanged order …
</g>
```

`#stem` keeps its id and a real `d` (structural tests + honesty: it IS the
progress geometry); it now reads as the stem's core shadow line inside the
ribbon. Moss: `#stem-body` ribbons the sprig; `#mat` gets `d = geo.mat`,
opacity 0.92; all other forms set `#mat` opacity 0.

New def (in `<defs>`):
```html
<radialGradient id="soilAO" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="#120904" stop-opacity="0.55"/>
  <stop offset="0.7" stop-color="#120904" stop-opacity="0.2"/>
  <stop offset="1" stop-color="#120904" stop-opacity="0"/>
</radialGradient>
```

---

## 5. The organ grammar — archetype library (one organ per closed milestone)

New JS: `ARCHETYPES = { fern, vine, creeper, succulent, moss, sprout }`.
Each is `function (opts) -> pathSpec[]` where
`opts = { seed, len, age, folded, review, fill, form, index }` and every
pathSpec is `{ d, fill?, stroke?, sw?, op?, cls? }` **in local coordinates:
attachment at (0,0), organ extends toward +x, at final size** (no scale
transform, no vector-effect needed). `milestoneLeaf` keeps its name and
becomes the instancer: it computes status fill, world placement, builds the
hierarchy of §2, appends archetype paths into `.wind`, then hit circle, title,
and `makeLeafInteractive` exactly as today.

**Placement math** (in milestoneLeaf; node now carries `out`):
- `age = 1 − clamp01(t)` (existing rule, 1 = oldest/lowest).
- pitch (degrees, + = toward the sky): `pitch = 34·t − 8 + ((seed % 9) − 4)`
  → old leaves droop ~−8°, young pitch up ~+26°, ±4° seeded jitter.
  Succulent: fixed `pitch = 15`; moss: `pitch = 0`.
- **rotation R = deg(out) − dir·pitch** (verified sign convention, §3).
- `len = (folded ? 14 : 23) · (0.9 + (seed % 100)/500) · (0.92 + age·0.18)`
  (today's law, unchanged) — archetypes may scale internally but the envelope
  is this.
- Reach clamp: if `|node.x + cos(out)·(p + len) − 400| > 78`, scale len down
  to fit (keeps blades off the pot rim x≈340/460 and window frame).
- `g.setAttribute('data-dir', dir)` for the CSS light modulation (§6).

**Universal petiole** (part of each archetype except succulent p≈1.5, moss
p=0): a quadratic from (0,0) to (p, droop) with p = 4 + (seed % 5) (fern) or
6 + (seed % 7) (vine/creeper/sprout), droop = +1.5px, control bowed 1px down;
stroke `shade(fill, −20)`, width 1.5, round cap. The blade starts at the
petiole's end — this is the single highest-leverage attachment cue.

**Shading system (the one rule — resolves painter-vs-visionary):** layered
paths, zero per-leaf gradients, zero filters. Large blades (vine cordate,
creeper oval, succulent pad, sprout oval/cotyledon) split along the midrib:
- shadow half (below midrib): `shade(fill, −26)`
- lit half (above midrib): `shade(fill, +8)`
- rim: retrace the upper edge, stroke `shade(fill, +48)`, width 1.1, op 0.55,
  `class="rim"`
- midrib + 2 side-veins: `shade(fill, +22..30)` (reuse today's vein code
  translated to local coords)
Small-element archetypes (fern pinnae, moss tufts) skip the midrib split
(invisible at that scale) and carry silhouette + detail + rim instead.

**Per-form organ specs:**

- **fern** (default; physics): one arching frond. Rachis: quadratic from
  petiole end, length `L = 26 + (seed % 9)` capped by the reach clamp;
  control at (0.5L, −0.42L·k) where k pitches with age (old = flatter);
  in local coords the pitch is already in R, so use control (0.5L, −0.3L),
  end (0.95L, −0.06L). Pinnae: `N = 5 + (seed % 5)`; for i in 0..N−1,
  `ti = 0.14 + 0.8·i/(N−1)`; point + tangent via the quadratic formulas
  already in the file; pinna length `7.5·(0.9 + age·0.2)·sin(π·(0.2+0.8·ti))`;
  each pinna = two short quadratics forming a slim lens rotated ~65° off the
  rachis, alternating sides by `i % 2`; **concatenate all pinnae into ONE
  path d** (subpaths, single fill = `fill`), plus rachis stroke
  `shade(fill,−15)` and a rachis lit retrace `shade(fill,+48)`. 3 paths/frond.
  Folded null: rachis droops (end below start, +0.25L), each pinna collapses
  to a short stroke hugging the rachis at ~15° — a grey fishbone. Pinna count
  is seeded cosmetic detail inside ONE organ; never data.
- **vine** (compute): cordate (heart) blade with a drip tip — out to widest at
  0.55·len, cusp tip (control placed just past the tip axis), back under;
  midrib split + rim + veins. A small node-swelling disc (rx 2.7, ry 1.9,
  fill `#41682f`) at local (0,0) — inside the organ, so organ count stays
  legible. Tendril only when `seed % 3 === 0`: a 14-point shrinking-spiral
  polyline (θk = k·0.55, rk = 8.5·(1 − k/16)) centered at (len·0.35, +3),
  stroke `shade(fill,−10)`, width 1, op 0.7 — part of the same organ, sways
  with it, never its own animation. Folded null: inward-rolled grey cordate
  (control points pulled toward the midrib, tip hooked 40° down); no tendril.
- **creeper** (astronomy): near-round blade on a 3px petiole, midrib split +
  rim. In milestoneLeaf (world space): if `(BASE − node.y) < 34`, add 2
  rootlet quadratics from (node.x, node.y) heading down-toward-soil, length
  `5 + seed % 4`, angles π/2 ± 0.35 seeded, stroke `shade(fill,−30)`, width
  0.9, op 0.6, round cap — pinned, outside `.place`. Null: folded grey blade
  PLUS a world-space dashed overdraw (`stroke-dasharray="2.5 2"`, `#8a8f82`,
  width 2) of the runner segment from this node to `geo.nodes[i−1]` (i===0 →
  to (400, 344)) — the miss written into the runner itself, inside the null's
  own last-painted group.
- **succulent** (instrument): obovate fleshy pad, near-sessile. Thickness cue:
  the pad path translated (0, +1.7) painted FIRST in `shade(fill, −38)` (the
  under-lip), then shadow/lit halves, then a highlight crescent retracing the
  upper-left third (`shade(fill,+42)`, width 1.5, op 0.5). Null: pad at 0.62
  scale, grey with two short wrinkle strokes; keeps the fold read via the
  two-face grey split.
- **moss** (boinc): a tuft — 3 upward strokes from (0,0), lengths 3–5 seeded,
  splayed ±25°, width 1.1 round cap, one 2.5px half-dome arc at the base;
  colors from `fill`. Null tuft: dried tan-grey `#9a927f`, tips curled down
  (flip end-control y). No petiole. (R = −90°, so local +x maps to screen-up.)
- **sprout** (misc): nodes[0] and nodes[1] render as **cotyledons** — smooth
  obovate blades, width ratio 0.62, len ×0.85, NO veins, no drip tip; each is
  its own organ/milestone/field note (a near-pair, honest to real staggered
  cotyledons). nodes[2+] get standard petiole + oval true leaf with the
  two side-veins. Null cotyledon: the folded grey variant — an asymmetric
  pair telling the truth beats a symmetric one hiding it.

**Folded nulls — universal law:** `folded:true` collapses the lit/shadow split
into a **two-face grey fold** — face A `shade('#8a8f82', +8)`, face B
`shade('#8a8f82', −14)`, split along the crease (this hard value step IS the
fold — it replaces the painter's paperGrad with the same layered-path system,
direction-correct by construction), plus the existing crease stroke
(`shade(fill,−25)`) and a second parallel micro-crease at 60% length, op 0.4.
Nulls get: NO rim, NO glow, NO dew, NO wind (`.null-leaf .wind
{ animation:none }`), opacity 0.78, and are ALWAYS appended last (§ paint
order). Grey never gains hue.

**Paint order** (in drawStalk's append loop — pure permutation, counts
unchanged):
1. Living organs, sorted: succulent by `node.y` ascending (rear pads behind);
   moss in given order; all other forms by `t` DESCENDING (young/high painted
   first = behind; old/low in front — real foliage).
2. ALL folded nulls, in milestone order, appended after — **nulls-last
   supremacy outranks every depth sort** (comment this in the code).
DOM order therefore = paint order; each organ keeps its own tabindex/label so
keyboard traversal remains complete, and the rail provides ordered
navigation. (Today's order is already not pure milestone order — nulls
already go last — so this is not a new class of change.)

**Hit target:** recenter the r=22 circle on the blade centroid: world point of
local `(p + len·0.55, 0)` through translate+rotate. r stays 22 (~48px
rendered).

**DOM budget:** worst case 31 organs × ≤8 paths ≈ 250 nodes + stem ribbon —
fine, static after render.

---

## 6. The light — sundial hookup, directional edges, backlight, dew

**Keystone (in `placeSun`, after computing x/day/frac):**
```js
var sc = $('scene');
sc.dataset.sunside = x < 400 ? 'left' : 'right';
var low = day && (frac < 8/24 || frac > 17/24);   // before 08:00 / after 17:00
if (low) sc.dataset.sunlow = ''; else delete sc.dataset.sunlow;
```
(Do NOT gate on `arc < 0.3` — verified impossible during day hours. The clock
window intersected with the dawn/dusk phase gates below yields ~2h of glow at
each end of the day: a moment, not a neon sign.)

**Directional modulation — CSS only, no JS after render:**
```css
.stem-edge { opacity:0.14; transition:opacity 3s ease; }
#scene[data-sunside="left"]  #stem-edge-l,
#scene[data-sunside="right"] #stem-edge-r { opacity:0.5; }
.leaf .rim { transition:opacity 3s ease; }
#scene[data-sunside="left"]  .leaf[data-dir="-1"] .rim,
#scene[data-sunside="right"] .leaf[data-dir="1"]  .rim { opacity:0.7; }
#scene[data-sunside="left"]  .leaf[data-dir="1"]  .rim,
#scene[data-sunside="right"] .leaf[data-dir="-1"] .rim { opacity:0.3; }
body[data-phase="night"] .stem-edge,
body[data-phase="night"] .leaf .rim { opacity:0.12; }   /* moonlight: weak, cool-ish */
```

**Backlit blades at dawn/dusk** (the magic moment; living leaves only): each
archetype returns a `glow` pathSpec whose `d` is the concatenation of its face
subpaths (its own silhouette — no `<use>`, fill overrides don't work through
use). One shared def:
```html
<radialGradient id="bladeBacklight" cx="0.5" cy="0.35" r="0.75">
  <stop offset="0" class="backlight-stop" stop-opacity="0.5"/>
  <stop offset="1" class="backlight-stop" stop-opacity="0"/>
</radialGradient>
```
```css
.backlight-stop { stop-color: var(--sun); }   /* inherits dawn #ffe9c6 / dusk #ffce9c */
.blade-glow { opacity:0; transition:opacity 3s ease; }
body[data-phase="dawn"] #scene[data-sunlow] .blade-glow,
body[data-phase="dusk"] #scene[data-sunlow] .blade-glow { opacity:0.4; }
```
**No mix-blend-mode** (compositing cost per leaf under animation; the gradient
at 0.4 is 90% of the effect). Nulls carry no glow — a dry fold does not
transmit light, and its matte stillness is the honest read.

**Dawn dew** (deterministic, living leaves only): archetypes emit up to 2 dew
positions on their upper edge using seeded t values (`t1 = 0.25 + (seed%13)/40`,
`t2 = 0.6 + (seed%7)/30` through the same Bezier-at-t formula); succulent
emits ONE larger bead (r=1.2) at the pad's low point (succulents pool, ferns
film); moss none. Painted as `<circle class="dew" fill="#fff" r="0.9|0.7">`
inside `.wind`.
```css
.dew { opacity:0; transition:opacity 3s ease; }
body[data-phase="dawn"] .dew { opacity:0.85; }
```
No keyframes — dew sits still, which is what dew does. (The optional glint
wobble is cut: motion budget is spent.)

**Cut from the painter lens:** winter rime (a per-leaf always-present stroke
for a rarely-active season — revisit if a winter ships), crossing-blade
contact shadows (painter's own first cut; the layered faces + paint order
already imply depth), per-leaf gradient overlays (superseded by layered
faces).

---

## 7. The motion — one wind, one lean, one breath

**Wind field** (keyframe name `sway` is KEPT — only the body changes; grep
tests first to confirm no coupling, expected none):
```css
@property --windamp { syntax:'<number>'; inherits:true; initial-value:1; }
body { --windamp:1; transition:--windamp 20s linear; }
body[data-phase="dawn"] { --windamp:0.7; }
body[data-phase="dusk"] { --windamp:0.5; }
body[data-phase="night"] { --windamp:0.15; }

#plant { transform-origin:400px 344px;
         animation: sway 47s ease-in-out infinite;
         rotate: calc(var(--lean, 0) * 1deg);
         transition: rotate 240s linear; }
@keyframes sway {
  0%  { transform: rotate(calc(var(--windamp,1) * -0.5deg)); }
  12% { transform: rotate(calc(var(--windamp,1) *  0.8deg)); }
  24% { transform: rotate(calc(var(--windamp,1) * -0.6deg)); }
  38% { transform: rotate(calc(var(--windamp,1) *  0.7deg)); }
  50% { transform: rotate(calc(var(--windamp,1) * -0.4deg)); }
  62% { transform: rotate(calc(var(--windamp,1) *  1.6deg)); }  /* the gust */
  74% { transform: rotate(calc(var(--windamp,1) * -0.7deg)); }
  88% { transform: rotate(calc(var(--windamp,1) *  0.5deg)); }
  100%{ transform: rotate(calc(var(--windamp,1) * -0.5deg)); }
}
```
Existing hover-pause rules extend to the new lanes:
```css
.scene:hover #plant, .scene:focus-within #plant,
.scene:hover .leaf .wind, .scene:focus-within .leaf .wind,
.scene:hover #bud, .scene:hover #bud-tip .breath { animation-play-state:paused; }
```

**Leaf coupling — ONE animated lane per organ** (the seeded private flutter
lane is removed; its character folds into seeded amplitude): in milestoneLeaf,
on the `.wind` g:
```js
w.style.setProperty('--t', t.toFixed(3));
w.style.setProperty('--lamp', ((0.6 + t*0.9) * (0.92 + (seed%13)/80)).toFixed(3));
```
```css
.leaf .wind { transform-box:fill-box; transform-origin:0% 50%;
              animation: leaf-wind 47s ease-in-out infinite;
              animation-delay: calc(var(--t,0.5) * 1.2s - 47s); }  /* negative: no dead frames */
.leaf.null-leaf .wind { animation:none; }   /* a kept miss is at rest */
@keyframes leaf-wind {   /* same shape as sway, scaled per leaf */
  0%  { transform: rotate(calc(var(--windamp,1)*var(--lamp,1) * -0.5deg)); }
  … same nine stops, 1.6deg gust …
}
```
The gust visibly travels root→tip (delay = t·1.2s); tip leaves swing more
(--lamp grows with t) — a young plant stirs gently, a tall one dances more,
which is growth made visible without a single claim. Delete the old
`@keyframes flutter` and `--fdur` seeding. Remove `transform-box/origin` from
`.leaf` itself (it no longer transforms); keep `.leaf` in the opacity
transition list (line 256) and all cursor/selection rules.

**Phototropism** (in placeSun; zero DOM):
```js
var lean = day ? (x - 400) / 400 * 1.8 : 0;   // moon exerts no pull
sc.style.setProperty('--lean', lean.toFixed(2));
```
Boot sets `--lean` synchronously before first paint (script runs at parse,
verified boot order), so the page loads already in posture. Browsers without
the individual `rotate` property simply stand the plant vertical.

**The bud's own breath** (9.7s — shares no small common period with 47s):
new static `<g id="bud-tip" aria-hidden="true"></g>` between `#bud-halo` and
`#bud`. drawStalk fills it: outer attribute transform
`translate(tipX tipY) scale(S)` with `S = 0.6 + 0.4*openProg` (render-time
only — NEVER animate the swell; it is the feed's open.progress made legible),
containing `<g class="breath">` with two mirrored quadratic husks
(fill `shade(leafColor,−12)`, stroke `shade(leafColor,−30)` w0.8) clasping a
2px tip ellipse (`shade(leafColor,+20)`). Empty + hidden when nothing is open
(same gate as #bud opacity). `#bud` stays the focusable/hit element with all
current wiring.
```css
#bud, #bud-tip .breath { transform-box:fill-box; transform-origin:center;
                         animation: bud-breath 9.7s ease-in-out infinite; }
@keyframes bud-breath { 50% { transform: scale(1.07); } }
body[data-phase="night"] #bud-halo[data-on] { animation: bud-breathe 9.7s ease-in-out infinite; }
/* bud-breathe keyframe body unchanged; duration retimed 7s → 9.7s */
```
No breath on `#flower` — a finished ladder rests. Breath rhythm encodes
nothing (no speed-up on runner state — that would be a claim).

**Night calm:** at night `--windamp:0.15` — the room goes almost still;
living leaves and folded nulls become indistinguishable in dead air, and the
one thing still moving is the bud: the open experiment, which is exactly the
true state of the lab. Firefox @property-transition gaps degrade to a snap at
the phase boundary, hidden inside the existing palette hard-switch.

**Growth theater — the since-your-last-visit unfurl** (last slice; every part
guarded): localStorage key `windowsill:seen-closed-ids` = JSON array of closed
milestone ids, ALL access in try/catch (file:// and private-mode can throw →
"no history", no theater, no error). In drawStalk, ONLY when rendering a real
loaded feed (pass a flag from `render` — state not empty): diff current
closed ids against stored **by id membership, never status** (amber→green
promotion must not replay); for up to the **3 newest** additions, run a
one-shot WAAPI animation on that organ's `.wind`:
```js
try {
  el.animate(
    [{ scale:'0.05', rotate:(dir*-35)+'deg', opacity:0.2 },
     { scale:'1', rotate:'0deg', opacity:1 }],
    { duration:6000, easing:'cubic-bezier(0.22,0.9,0.3,1)', fill:'backwards', delay:600 });
} catch (e) { /* older engines: no theater, settled pose */ }
```
Individual properties compose with the CSS transform animation on the same
element; origin is already the attachment. Skip entirely when `reduce` is
true. First-ever visitors (no key): no theater (31 unfurls is fireworks, not
a windowsill) — just write the set. Write-back only after a successful feed
render. A null that closed since last visit unfurls too, into its folded grey
form — the miss arriving is also news and gets the same quiet ceremony.

---

## 8. Status treatment (consolidated)

| status | fill | layers | motion | extras |
|---|---|---|---|---|
| verified | `shade(SEASON_LEAF[season], (seed%17)−8)` | shadow/lit faces, rim, veins | wind + lag | glow at dawn/dusk, dew at dawn |
| review | `#d2aa67` base, same shade() ramps | identical to verified — light falls on all statuses equally; overlay opacities never exceed 0.55 so amber never drifts green | identical | identical (paint is never a claim ranking) |
| null | `#8a8f82` two-face fold (+8/−14) | crease + micro-crease, no rim | NONE (still even in wind) | no glow, no dew; painted LAST; opacity 0.78; creeper adds dead-runner overdraw |

Season tints only the verified green (existing SEASON_LEAF map, unchanged).
The phase palette tints everything via --sun/--spill exactly as the scene
already does.

---

## 9. A11y wiring (unchanged contract, restated for the new DOM)

- Outer `.leaf` g keeps: `tabindex="0"`, `role="button"`, `aria-label` (same
  text logic), `<title>`, `data-mid`, click/keydown via `makeLeafInteractive`
  — code untouched, it operates on the g it's handed.
- `circle.leaf-hit` r=22 world-space, recentered on the blade centroid.
- `.leaf:focus-visible, #bud:focus-visible` outline rule works as-is (targets
  the outer g). `.leaf.is-selected` drop-shadow works as-is.
- `#bud` wiring untouched; `#bud-tip` is `aria-hidden="true"` decoration.
- `<svg role="group">` untouched (test-asserted).
- Tab order = paint order (living height-sorted, nulls last). Every organ is
  self-labeled and the milestone rail provides ordered traversal; document
  this in a code comment at the sort.

---

## 10. Reduced motion

Extend the existing kill block (lines ~698–710) — everything else in this
design is static paint:
```css
@media (prefers-reduced-motion: reduce) {
  /* existing lines stay */
  #plant { animation:none; rotate:none; transition:none; }
  .leaf .wind, #bud, #bud-tip .breath { animation:none; }
}
```
- JS `reduce` flag (already read at boot) gates growth theater (skip).
- Dew/glow/rim/edge reveals are 3s **opacity transitions**, consistent with
  the page's existing phase cross-fades — they remain (same policy as the
  current palette). The night halo's steady 0.6 override is preserved.
- Frozen flutter degrades to perfect stillness at the attachment pose.

---

## 11. Degradations

- **No feed** (DEFAULT_MILESTONES=[]): count=0 → tapered ribbon nub + collar
  AO + core line render on the default fern spine (the bare seed stops
  looking like a wire); no organs, no theater, no localStorage writes (so the
  first real feed render diffs against genuine history, not a poisoned empty
  set).
- **Offline/file://**: everything is inline geometry + local CSS vars on the
  visitor's clock; two new defs are inline; localStorage throws are caught.
- **Unknown growth_form**: registry falls back to fern; fern's archetype is
  the default painter; `deepEqual` fallback test keeps passing because added
  keys ride the same builder.
- **Restored tab**: CSS animations and the 60s placeSun tick self-correct;
  the 240s lean transition resumes toward the current sun.

---

## 12. Garden mini-specimens

**Untouched.** `drawGarden` is frozen by the literal source-string tests
listed in §1, its 40px silhouettes are an index (not six more organisms), and
the animator's rule stands: no wind there. Moss's composite `stem` string is
preserved specifically so the garden moss card keeps its mat outline. The
hero/garden language stays linked through the shared GF geometry and status
colors. (If a future pass wants archetype silhouettes at specimen scale, it
must update the frozen test literals in the same change — out of scope now.)

---

## 13. What happens to existing code

- `milestoneLeaf`: name and a11y/interaction tail kept; geometry body
  replaced by the archetype instancer (§5). No legacy fallback branch — page
  and module version together (the visionary's fallback would be dead code).
- `drawStalk`: keeps name and flow; gains spine/ribbon/edges/mat writes, the
  paint-order sort, `#bud-tip` fill, and (slice 5) the theater diff. The
  string `GF.pageGrowthForm(milestones)` and `GF.build(formName` must remain
  verbatim (test-asserted).
- `@keyframes flutter` + `--fdur` seeding: deleted (grep tests first).
- `@keyframes sway`: body replaced, name kept, 11s → 47s.
- `#stem`: keeps id and d (now the spine); restyled to core-line in markup.
- growth-forms.js: additive only; inline block re-synced every time.

---

## 14. Don't-do list (merged, binding)

1. No decorative foliage untied to milestones — pinnae/tendrils/rootlets/
   tufts are legal ONLY inside exactly one organ per closed milestone; no
   berries, filler fronds, or mat interior stipple (dots read as data points
   that don't exist).
2. No Math.random anywhere in the plant — every length, angle, pinna count,
   tendril presence, dew position derives from `leafSeed(m.id)`, `count`, or
   the clock. Same plant every visit.
3. No per-leaf gradients, no filters inside animated groups, no
   mix-blend-mode on leaves, no feTurbulence "organic" noise — two shared
   defs total (#soilAO, #bladeBacklight).
4. No per-frame JS: no rAF wind, no scroll/pointer-reactive motion, no
   animated stem `d`. placeSun's minutes cadence + CSS do all the moving.
5. No softening the null: never smaller, never buried (nulls-last outranks
   every depth sort), never warmed toward the palette, never glowing, dewed,
   or swaying. A beautiful miss is fine; a camouflaged one is not.
6. No motion encoding lab state beyond spec: no faster wind on fresh runs, no
   drooping on stale feeds, no breath-rate change on runner_available, no
   animated bud swell, no synced bud rhythm (asynchrony is the point).
7. No breaking homogeneity: tipY() is law; expressiveness lives in path and
   organ shape only. One bud, one tip — no second growing point anywhere.
8. No renames of `#stem #leaves #bud #bud-halo #flower #soil`, no dropping
   `.leaf/.leaf-hit/.null-leaf`, no wrapper g around existing ids, no changes
   to the `{stem,nodes,tip}` return shape (grow it additively), no edits to
   the frozen drawGarden literals.
9. No wind on the garden minis; no unfurl replay on status change or first
   visit; never more than 3 queued unfurls.
10. Do not skip the inline-block re-sync after any growth-forms.js edit — the
    byte-for-byte test will catch you, but don't make it.

---

## 15. Guards to run per slice

- `node --test web/growth-forms.test.mjs`
- `python -m pytest tests/test_web_growth_forms.py tests/test_labhome.py -q`
  (fast web guards), full `python -m pytest` before landing.
- Manual: open `web/index.html` from file:// (bare-seed path) AND via
  localhost (reads `../pot.json` — real 31-milestone feed). Walk phases with
  `window.advanceTime(3600e3)` in the console; check `render_game_to_text()`
  shape unchanged. Force each form by temporarily editing a copy of pot.json's
  open milestone `growth_form` (all six). Toggle prefers-reduced-motion in
  devtools. Hover-pause, tab through leaves, open field notes from leaf, bud,
  rail. Verify no horizontal overflow of blades past the pot rim at count=31.

---

## 16. Judge amendments (binding — adversarial panel 2026-08-07)

Truth/a11y judge:
1. **Moss envelope**: tuft strokes 10–16px (len law × 0.5–0.7 internal factor), null tuft ≥12px as a folded-fan silhouette with two-face grey; crease stroke ≥1.5 so grey-on-mat clears 3:1. Verify with forced moss+null.
2. **Bud target**: `#bud-tip { pointer-events:none }`; add transparent r=22 bud-hit circle forwarding click to #bud; #bud stays the focusable element.
3. **Creeper rootlets**: gate on `t <= 2/total` (lowest 1–2 nodes), not `(BASE−y)<34` which never fires.
4. **Autumn amber/green**: review gets a season-independent secondary channel — double midrib (two parallel rib strokes, no crease) — hue alone may not carry the distinction.
5. **Signature threading**: `milestoneLeaf(node, m, leafColor, geo, i)`; fallback node gets `out:-Math.PI/2`; guard `if (!isFinite(node.out))` inside.
6. **Tip hit occlusion**: append each organ's leaf-hit circle into an always-on-top overlay group `#leaf-hits` in milestone order, wired to the same handlers; outer g keeps tabindex/aria. Manual check: at count=31 tap top 3 living leaves + newest null.

Calm/perf judge:
1. **No second `transition` on body** — never redeclare; `--windamp` gets NO transition at all (see next).
2. **No @property/transition on --windamp**: plain per-phase custom property, amplitude snaps at phase boundary (hidden in palette switch). Static var() only in keyframes.
3. **Dew cap**: beads only where `seed % 3 === 0`, opacity 0.6; succulent single pooled bead stays.
4. **Focus parity**: `.scene:focus-within` added to #bud + #bud-tip .breath pause rules.
5. **x≥0 archetype invariant**: no geometry crosses local x<0 (clamp tendril spiral; cordate lobes at x≥0); origin approximation accepted for ±1.6° wind; visually check WAAPI unfurl per form.
6. **--fdur scoped delete**: remove only .leaf flutter keyframes + milestoneLeaf's two --fdur lines; fireflies keep their --fdur.
7. **Honest numbers**: arc day-minimum ≈0.6; DOM worst case ≈430 nodes incl. wrappers/hit/title/dew.
