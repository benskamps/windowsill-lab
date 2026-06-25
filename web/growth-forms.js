/*
 * growth-forms.js — pluggable growth forms for the windowsill, behind one
 * interface. The feed contract (src/lab/publish.py) derives a `growth_form`
 * for every milestone from its track (physics→fern, compute→vine,
 * astronomy→creeper, instrument→succulent, boinc→moss, misc→sprout). This
 * module turns that hint into *geometry* — where the stem goes and where each
 * closed milestone hangs on it — while keeping every other windowsill rule
 * identical: same clay pot, same palette, same light-follows-your-clock soul,
 * same node-per-milestone count. A wall of windowsills should still read as
 * one garden; only the form of the green thing changes.
 *
 * THE ONE INTERFACE every form implements:
 *
 *     form.build(ctx) -> {
 *       stem:  "M…"  (an SVG path string for #stem),
 *       nodes: [{ x, y, dir, t }],   // one per closed milestone, bottom→top
 *       tip:   { x, y },             // where the open bud / flower sits
 *     }
 *
 *   ctx = { count, total, openProg, base, rise }
 *     count    = number of closed (verified|null) milestones  → node count
 *     total    = ladder length (rungs across all tracks)       → growth scale
 *     openProg = 0..1 progress of the open experiment          → tip reach
 *     base     = soil-surface y (px)                           → shared origin
 *     rise     = full-ladder rise (px)                          → shared envelope
 *
 * HOMOGENEITY CONTRACT (what makes a wall of these read as one garden):
 *   - Every form roots at (CX, base) and reaches the SAME tip height for a
 *     given (count, total, openProg) — `tipY(ctx)` below. Forms differ in the
 *     PATH and in how nodes are arranged, never in how tall the plant is.
 *   - `nodes.length === count` for every form (one node per closed milestone).
 *   - The tip is the single growing point (one bud / one flower), always.
 *
 * Pure functions, no DOM — so this is the single source of truth the page
 * paints from AND the test imports. Works as a browser global (window.GrowthForms)
 * or an ES module (export at the bottom, ignored by the classic <script> load).
 */
(function (root) {
  "use strict";

  var CX = 400; // the pot's center x — every form's root, shared

  // Eased tip fraction: a long curriculum (dozens of rungs) still reads as real
  // growth early on instead of a dead sprout stuck near the soil. Identical
  // across forms so heights stay homogeneous.
  function ease(k) { return Math.pow(Math.max(0, Math.min(1, k)), 0.62); }
  function clamp01(k) { return Math.max(0, Math.min(1, k)); }

  function tipFrac(ctx) {
    return Math.min(1, (ctx.count + clamp01(ctx.openProg)) / Math.max(1, ctx.total));
  }
  // The shared height envelope: where the growing tip lands for this much
  // progress. Every form MUST honor this so side-by-side windowsills agree on
  // "how far up the ladder" without agreeing on the shape of the climb.
  function tipY(ctx) {
    return ctx.base - 22 - ctx.rise * ease(tipFrac(ctx));
  }
  // Per-node height along the shared envelope (node i of `count`, bottom→top).
  function nodeY(ctx, i) {
    return ctx.base - 22 - ctx.rise * ease((i + 1) / Math.max(1, ctx.total));
  }

  function fmt(n) { return Math.round(n * 100) / 100; }

  // ── FERN — the core physics convergence ladder ──────────────────────────
  // A single upright stem; fronds (nodes) alternate side to side as it climbs.
  // The default, homogeneous seedling shape. (sprout shares this builder.)
  function fern(ctx) {
    var top = tipY(ctx);
    var midx = CX + Math.sin(tipFrac(ctx) * 3) * 5;
    var stem = "M" + CX + " " + ctx.base +
      " C" + fmt(midx) + " " + fmt((ctx.base + top) / 2) +
      " " + fmt(800 - midx) + " " + fmt(top + 24) +
      " " + CX + " " + fmt(top);
    var nodes = [];
    for (var i = 0; i < ctx.count; i++) {
      nodes.push({ x: CX, y: nodeY(ctx, i), dir: (i % 2) ? 1 : -1, t: (i + 1) / Math.max(1, ctx.total) });
    }
    return { stem: stem, nodes: nodes, tip: { x: CX, y: top } };
  }

  // ── VINE — climbing integer sequences (compute / OEIS extensions) ────────
  // The stem coils as it climbs; nodes sit on the OUTSIDE of each coil, so the
  // plant reads as a spiral reaching upward rather than a straight stalk. Same
  // root, same tip height — only the path winds.
  function vine(ctx) {
    var top = tipY(ctx);
    var turns = 1.6;                 // how many half-coils over the full reach
    var amp = 26;                    // coil width (px), constant so it stays tidy
    var segs = 18;
    var d = "M" + CX + " " + ctx.base;
    for (var s = 1; s <= segs; s++) {
      var f = s / segs;
      var y = ctx.base + (top - ctx.base) * f;
      var x = CX + Math.sin(f * Math.PI * turns) * amp * (1 - f * 0.35);
      d += " L" + fmt(x) + " " + fmt(y);
    }
    var nodes = [];
    for (var i = 0; i < ctx.count; i++) {
      var fi = (i + 1) / Math.max(1, ctx.total);
      var ny = nodeY(ctx, i);
      // place the node on the stem at its height, pushed to the outside of the coil
      var phase = Math.sin(((ny - ctx.base) / (top - ctx.base || 1)) * Math.PI * turns);
      var nx = CX + phase * amp * 0.9;
      nodes.push({ x: fmt(nx), y: ny, dir: phase >= 0 ? 1 : -1, t: fi });
    }
    return { stem: d, nodes: nodes, tip: { x: CX, y: top } };
  }

  // ── SUCCULENT — an instrument calibration: compact, slow, precise ────────
  // Barely any stem; the milestones are a tight rosette radiating from a low
  // center, like a calibration target. Compactness IS the signal (a calibration
  // is small and dense, not a tall climb), but it still honors the shared tip
  // height so a finished calibration flowers at the same place a fern does.
  function succulent(ctx) {
    var top = tipY(ctx);
    var cy = ctx.base - 20;                 // rosette sits just above the soil
    var stem = "M" + CX + " " + ctx.base + " L" + CX + " " + fmt(cy) +
               " L" + CX + " " + fmt(top);  // a short, mostly-vertical spine to the tip
    var nodes = [];
    var R = 16 + Math.min(ctx.count, 12) * 1.6;   // rosette grows gently with count
    for (var i = 0; i < ctx.count; i++) {
      // golden-angle phyllotaxis so leaves never overlap, growing outward
      var ang = i * 2.399963;                      // ~137.5°
      var r = R * Math.sqrt((i + 1) / Math.max(1, ctx.count));
      var nx = CX + Math.cos(ang) * r;
      var ny = cy - Math.sin(ang) * r * 0.5;       // squashed vertically (a flat rosette)
      nodes.push({ x: fmt(nx), y: fmt(ny), dir: Math.cos(ang) >= 0 ? 1 : -1, t: (i + 1) / Math.max(1, ctx.total) });
    }
    return { stem: stem, nodes: nodes, tip: { x: CX, y: top } };
  }

  // The registry — the single interface. `growth_form` from the feed maps here;
  // unknown forms degrade to the homogeneous default (fern/sprout).
  var FORMS = {
    fern: fern,
    sprout: fern,        // the homogeneous default seedling is fern-shaped
    vine: vine,
    creeper: vine,       // a trailing time-series reuses the climbing path for now
    moss: succulent,     // a mat-former: compact, like the rosette
    succulent: succulent,
  };
  var DEFAULT_FORM = "fern";

  // Pick the PAGE's growth form from its milestones. A windowsill shows one
  // plant, so we pick the form of the dominant track among closed+open
  // milestones (most common growth_form wins; ties → first seen). This keeps
  // the page coherent while honoring whatever the feed stamped.
  function pageGrowthForm(milestones) {
    if (!Array.isArray(milestones) || !milestones.length) return DEFAULT_FORM;
    var tally = {}, order = [];
    milestones.forEach(function (m) {
      var gf = m && typeof m.growth_form === "string" ? m.growth_form : null;
      if (!gf || !FORMS[gf]) return;
      if (tally[gf] == null) { tally[gf] = 0; order.push(gf); }
      tally[gf]++;
    });
    if (!order.length) return DEFAULT_FORM;
    var best = order[0];
    order.forEach(function (gf) { if (tally[gf] > tally[best]) best = gf; });
    return best;
  }

  // build(formName, ctx) — the one call the page makes. Falls back cleanly.
  function build(formName, ctx) {
    var f = FORMS[formName] || FORMS[DEFAULT_FORM];
    return f(ctx);
  }

  var api = {
    FORMS: FORMS,
    DEFAULT_FORM: DEFAULT_FORM,
    build: build,
    pageGrowthForm: pageGrowthForm,
    // exposed for tests / advanced callers
    _tipY: tipY,
    _nodeY: nodeY,
    _tipFrac: tipFrac,
    CX: CX,
  };

  // Browser: attach as a global the classic <script> can read.
  if (root) root.GrowthForms = api;
  // ES module: harmless under a classic <script> load, importable by the test.
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));
