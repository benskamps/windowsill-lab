/*
 * pots.js — one pot per track, behind one interface. Companion to
 * growth-forms.js: that module answers "what shape does this science grow in?",
 * this one answers "what vessel is it growing in, and how hard has that vessel
 * been worked?"
 *
 * WHY A POT LAYER EXISTS. publish.GROWTH_FORMS maps SIX tracks onto FIVE forms —
 * `coherence` deliberately reuses the fern, because a coherence ladder IS a
 * convergence ladder and a seventh plant nobody asked for would misdescribe the
 * climb. So two tracks share one plant and nothing told them apart. The pot is
 * the honest answer: same plant, different vessel.
 *
 * THE TWO HALVES, kept strictly apart:
 *
 *   SILHOUETTE = identity. Authored, constant, per track. Profile, rim, feet,
 *   throwing ridges. It answers "which science is this?" and never moves.
 *
 *   MARKS = labour. Derived from pot.json on every render, nothing else.
 *   Glaze climbs the wall as the ladder is climbed and stops at the frontier,
 *   leaving raw clay above it. Scratches tally the runs. Chips and slip-filled
 *   repair seams record the misses, kept in daylight the way the folded grey
 *   leaves are. A pot nobody has run yet is bare — and still on the sill.
 *
 * If a detail cannot be re-derived from the feed it is not a mark and it does
 * not ship. No status hue ever touches a vessel: green/amber/grey belong to
 * leaves; pots are clay. No text, no counts, no machine marks on the sill.
 *
 * THE ONE INTERFACE:
 *
 *     POTS.marksFrom(stats) -> { glaze, matte, tally, patina, chips, seams,
 *                                damp, virgin, runs }
 *     POTS.build(track, marks, geom) -> pathSpec[]
 *
 *   pathSpec = { d } | { e:{cx,cy,rx,ry} }  plus optional
 *              { fill, stroke, sw, op, cls, cap }
 *   LOCAL COORDINATES: origin = the MOUTH CENTRE, +x right, +y down, final
 *   size. The page instances a pot with one translate — no scale transform.
 *
 *   geom = { mouth, depth }
 *     mouth = the shared mouth half-width at y=0 (hero 70, card mini ~26)
 *     depth = mouth → foot (hero 126)
 *
 * THE MOUTH AND THE FOOT ARE LAW. Every vessel spans exactly ±mouth at y=0 and
 * bottoms out at exactly `depth`, so the soil line, the root collar and every
 * growth form's root at CX land identically in all seven pots, and every pot
 * stands on the same board. One sill, one soil line; expressiveness lives
 * between them.
 *
 * Pure functions, no DOM, no randomness, no clock — geometry is a function of
 * (track, marks, geom) alone, so the same feed draws the same pot forever.
 * Browser global (window.Pots) or ES module, same as growth-forms.js.
 */
(function (root) {
  "use strict";

  function fmt(n) { return Math.round(n * 100) / 100; }
  function clamp01(k) { return Math.max(0, Math.min(1, k)); }
  function lerp(a, b, t) { return a + (b - a) * t; }

  // A closed wall polygon between two depths, walking the vessel's own profile
  // down the left side and back up the right. Every mark that has to hug the
  // pot (glaze, damp ring) is cut from the same profile, so nothing floats.
  function wall(outer, y0, y1, steps) {
    var d = "M" + fmt(-outer(y0)) + " " + fmt(y0), i, y;
    for (i = 1; i <= steps; i++) { y = lerp(y0, y1, i / steps); d += " L" + fmt(-outer(y)) + " " + fmt(y); }
    for (i = steps; i >= 0; i--) { y = lerp(y0, y1, i / steps); d += " L" + fmt(outer(y)) + " " + fmt(y); }
    return d + " Z";
  }
  function band(x0, y0, x1, y1) {
    return "M" + fmt(x0) + " " + fmt(y0) + " L" + fmt(x1) + " " + fmt(y0) +
           " L" + fmt(x1) + " " + fmt(y1) + " L" + fmt(x0) + " " + fmt(y1) + " Z";
  }
  function line(x0, y0, x1, y1) {
    return "M" + fmt(x0) + " " + fmt(y0) + " L" + fmt(x1) + " " + fmt(y1);
  }

  // ── The seven vessels ─────────────────────────────────────────────────────
  // Each returns { rimH, outer(y), rim:[], ridges:[], feet:[] }. All widths are
  // written as fractions of `mouth` so a card mini is the same pot, smaller.

  // PHYSICS — the ladder pot. The classic thrown terracotta the windowsill has
  // always had: broad flared rim, a gently bellied wall, three throwing ridges.
  // Physics is the calibration spine, so its vessel is continuity, not novelty.
  function physics(M, D) {
    var rimH = 0.175 * D;
    function outer(y) {
      var u = clamp01((y - rimH) / (D - rimH));
      return M * (0.814 - 0.157 * u + 0.029 * Math.sin(Math.PI * u));
    }
    var ridges = [0.18, 0.42, 0.66].map(function (u) {
      var y = rimH + (D - rimH) * u, h = outer(y) * 0.97;
      return { d: line(-h, y, h, y), stroke: "#7e4528", sw: 0.9 * (M / 70), op: 0.28, cls: "pot-ridge" };
    });
    return {
      rimH: rimH, outer: outer, ridges: ridges, feet: [],
      rim: [
        { d: "M" + fmt(-M) + " 0 L" + fmt(M) + " 0 L" + fmt(0.886 * M) + " " + fmt(rimH) +
             " L" + fmt(-0.886 * M) + " " + fmt(rimH) + " Z", fill: "#c8784f", cls: "pot-rim" },
        { d: band(-M, 0, M, 0.031 * D), fill: "#e29a70", cls: "pot-rim-lit" }
      ]
    };
  }

  // COHERENCE — the coupled pot. A pinched waist between two lobes, a rolled
  // bead rim, a flared ring foot: two oscillators finding each other. It shares
  // the fern with physics, so the waist is what tells them apart at a glance.
  function coherence(M, D) {
    var rimH = 0.119 * D;
    function outer(y) {
      var u = clamp01((y - rimH) / (D - rimH));
      return M * (0.80 - 0.20 * Math.sin(Math.PI * u));
    }
    return {
      rimH: rimH, outer: outer, ridges: [],
      rim: [
        { d: "M" + fmt(-M) + " 0 L" + fmt(M) + " 0 C" + fmt(1.057 * M) + " " + fmt(0.42 * rimH) +
             " " + fmt(1.057 * M) + " " + fmt(0.74 * rimH) + " " + fmt(0.83 * M) + " " + fmt(rimH) +
             " L" + fmt(-0.83 * M) + " " + fmt(rimH) + " C" + fmt(-1.057 * M) + " " + fmt(0.74 * rimH) +
             " " + fmt(-1.057 * M) + " " + fmt(0.42 * rimH) + " " + fmt(-M) + " 0 Z",
          fill: "#c8784f", cls: "pot-rim" },
        { d: band(-M, 0, M, 0.028 * D), fill: "#e29a70", cls: "pot-rim-lit" }
      ],
      feet: [
        { d: "M" + fmt(-0.83 * M) + " " + fmt(D - 0.075 * D) + " L" + fmt(0.83 * M) + " " + fmt(D - 0.075 * D) +
             " L" + fmt(0.80 * M) + " " + fmt(D) + " L" + fmt(-0.80 * M) + " " + fmt(D) + " Z",
          fill: "#a85a37", cls: "pot-foot" }
      ]
    };
  }

  // COMPUTE — the stepped pot. Five discrete faceted steps down the wall, a
  // squared rim, four block feet. Exact arithmetic has no smooth interior: a
  // staircase, not a curve.
  function compute(M, D) {
    var rimH = 0.143 * D;
    function outer(y) {
      var u = clamp01((y - rimH) / (D - rimH));
      var step = Math.min(4, Math.floor(u * 5));
      return M * (0.857 - 0.049 * step);
    }
    var feet = [-0.52, -0.17, 0.17, 0.52].map(function (f) {
      return { d: band(M * f - 0.055 * M, D - 0.055 * D, M * f + 0.055 * M, D),
               fill: "#a85a37", cls: "pot-foot" };
    });
    return {
      rimH: rimH, outer: outer, ridges: [], feet: feet,
      rim: [
        { d: band(-1.03 * M, 0, 1.03 * M, rimH), fill: "#c8784f", cls: "pot-rim" },
        { d: band(-1.03 * M, 0, 1.03 * M, 0.032 * D), fill: "#e29a70", cls: "pot-rim-lit" }
      ]
    };
  }

  // ASTRONOMY — the collecting dish. A wide shallow bowl on a narrow stem and a
  // flared base: a dish that gathers light over a long baseline. Widest rim on
  // the sill.
  function astronomy(M, D) {
    var rimH = 0.095 * D, bowl = 0.44 * D, stemEnd = 0.80 * D;
    var stemHalf = M * 1.057 * Math.cos(1.33);
    function outer(y) {
      if (y <= bowl) {
        var k = clamp01((y - rimH) / (bowl - rimH));
        return M * 1.057 * Math.cos(k * 1.33);
      }
      if (y <= stemEnd) return stemHalf;
      var j = clamp01((y - stemEnd) / (D - stemEnd));
      return stemHalf + (0.70 * M - stemHalf) * j * j;
    }
    return {
      rimH: rimH, outer: outer, ridges: [], feet: [],
      rim: [
        { d: "M" + fmt(-M) + " 0 L" + fmt(M) + " 0 C" + fmt(1.114 * M) + " " + fmt(0.45 * rimH) +
             " " + fmt(1.114 * M) + " " + fmt(0.8 * rimH) + " " + fmt(1.057 * M) + " " + fmt(rimH) +
             " L" + fmt(-1.057 * M) + " " + fmt(rimH) + " C" + fmt(-1.114 * M) + " " + fmt(0.8 * rimH) +
             " " + fmt(-1.114 * M) + " " + fmt(0.45 * rimH) + " " + fmt(-M) + " 0 Z",
          fill: "#c8784f", cls: "pot-rim" },
        { d: band(-M, 0, M, 0.024 * D), fill: "#e29a70", cls: "pot-rim-lit" }
      ]
    };
  }

  // INSTRUMENT — the bench crucible. Straight machined walls under a heavy
  // double-banded collar, on three tripod feet: lab glassware rendered in clay.
  function instrument(M, D) {
    var rimH = 0.159 * D;
    function outer(y) {
      var u = clamp01((y - rimH) / (D - rimH));
      return M * (0.743 - 0.043 * u);
    }
    var feet = [-0.60, 0, 0.60].map(function (f) {
      return { d: band(M * f - 0.07 * M, D - 0.05 * D, M * f + 0.07 * M, D),
               fill: "#a85a37", cls: "pot-foot" };
    });
    return {
      rimH: rimH, outer: outer, ridges: [], feet: feet,
      rim: [
        { d: band(-M, 0, M, 0.055 * D), fill: "#c8784f", cls: "pot-rim" },
        { d: band(-0.9 * M, 0.055 * D, 0.9 * M, rimH), fill: "#b96a44", cls: "pot-rim" },
        { d: band(-M, 0, M, 0.026 * D), fill: "#e29a70", cls: "pot-rim-lit" }
      ]
    };
  }

  // BOINC — the seed pan. A strongly flaring pan on a broad foot ring pierced
  // by small drain slots: many little contributors draining into one tray.
  function boinc(M, D) {
    var rimH = 0.111 * D;
    function outer(y) {
      var u = clamp01((y - rimH) / (D - rimH));
      return M * (0.943 - 0.371 * u);
    }
    var feet = [{ d: band(-0.62 * M, D - 0.072 * D, 0.62 * M, D), fill: "#a85a37", cls: "pot-foot" }];
    for (var i = 0; i < 7; i++) {
      var x = (-0.48 + 0.16 * i) * M;
      feet.push({ d: band(x - 0.026 * M, D - 0.055 * D, x + 0.026 * M, D - 0.016 * D),
                  fill: "#4a2415", op: 0.7, cls: "pot-drain" });
    }
    return {
      rimH: rimH, outer: outer, ridges: [], feet: feet,
      rim: [
        { d: "M" + fmt(-1.029 * M) + " 0 L" + fmt(1.029 * M) + " 0 L" + fmt(0.971 * M) + " " + fmt(rimH) +
             " L" + fmt(-0.971 * M) + " " + fmt(rimH) + " Z", fill: "#c8784f", cls: "pot-rim" },
        { d: band(-1.029 * M, 0, 1.029 * M, 0.026 * D), fill: "#e29a70", cls: "pot-rim-lit" }
      ]
    };
  }

  // MISC — the nursery pot. A plain thin-rimmed taper: the homogeneous default,
  // exactly as `sprout` is for growth forms.
  function misc(M, D) {
    var rimH = 0.095 * D;
    function outer(y) {
      var u = clamp01((y - rimH) / (D - rimH));
      return M * (0.829 - 0.20 * u);
    }
    return {
      rimH: rimH, outer: outer, ridges: [], feet: [],
      rim: [
        { d: "M" + fmt(-M) + " 0 L" + fmt(M) + " 0 L" + fmt(0.914 * M) + " " + fmt(rimH) +
             " L" + fmt(-0.914 * M) + " " + fmt(rimH) + " Z", fill: "#c8784f", cls: "pot-rim" },
        { d: band(-M, 0, M, 0.022 * D), fill: "#e29a70", cls: "pot-rim-lit" }
      ]
    };
  }

  var VESSELS = {
    physics: physics,
    coherence: coherence,
    compute: compute,
    astronomy: astronomy,
    instrument: instrument,
    boinc: boinc,
    misc: misc
  };
  var DEFAULT_TRACK = "misc";

  // ── Marks: the ONLY place feed numbers become pot character ────────────────
  // stats = { closed, total, reviews, nulls, runs, nullRuns, lastAtMs, nowMs,
  //           intervalH }.  Every field is optional and degrades to "unworked".
  function marksFrom(stats) {
    var s = stats || {};
    var total = Math.max(1, Number(s.total) || 0);
    var closed = Math.max(0, Number(s.closed) || 0);
    var runs = Math.max(0, Number(s.runs) || 0);
    var interval = Number(s.intervalH) > 0 ? Number(s.intervalH) : 16;
    // `0` is a real epoch instant, so these are null-checks, not truthiness
    // checks: a feed whose timestamp is the epoch must not read as "no data".
    var hours = (s.lastAtMs != null && s.nowMs != null)
      ? (Number(s.nowMs) - Number(s.lastAtMs)) / 3600000 : null;
    if (hours != null && !isFinite(hours)) hours = null;
    return {
      // the glaze climbs as the ladder is climbed; raw clay above it IS the frontier
      glaze: clamp01(closed / total),
      // a checker passed, a human read is still owed: the top band goes unfired
      matte: (Number(s.reviews) || 0) > 0,
      // one scratch per root-run: a 111-run pot is scratched, not shredded
      tally: Math.min(12, Math.round(Math.sqrt(runs))),
      // wear that never quite saturates
      patina: 0.97 * (1 - Math.exp(-runs / 25)),
      chips: Math.min(4, Math.max(0, Number(s.nullRuns) || 0)),
      seams: Math.min(4, Math.max(0, Number(s.nulls) || 0)),
      // tended vs resting. Resting is NEVER distress — a track the rotation did
      // not schedule and a track whose turn failed both simply read dry.
      damp: hours == null ? 0 : clamp01(1 - hours / (2 * interval)),
      virgin: runs === 0,
      runs: runs
    };
  }

  // Deterministic lattice — golden-ratio strides, never a random draw, so the
  // same feed speckles the same pot on every visit and every machine.
  function latticeU(i) { return (i * 0.6180339887) % 1; }

  // Chips bite the rim's LOWER edge, out toward the shoulder. The top edge is
  // the mouth, and the page paints the pot's dark interior over it — a chip
  // drawn up there would be an honest mark nobody could see.
  // Each chip is its own lopsided bite — same fixed table every time, but no
  // two the same size, so four misses read as damage and not as decoration.
  var CHIP_X = [-0.79, 0.62, -0.44, 0.87];
  var CHIP_W = [4.6, 2.9, 3.8, 2.4];
  var CHIP_H = [5.4, 2.8, 4.2, 3.4];
  var CHIP_SKEW = [0.34, -0.42, -0.2, 0.5];
  var SEAM_U = [0.30, 0.55, 0.42, 0.68];

  function build(track, marks, geom) {
    var g = geom || {};
    var M = Number(g.mouth) > 0 ? Number(g.mouth) : 70;
    var D = Number(g.depth) > 0 ? Number(g.depth) : 126;
    var k = M / 70;                                  // one scale for every mark
    var v = (VESSELS[track] || VESSELS[DEFAULT_TRACK])(M, D);
    var m = marks || marksFrom({});
    var out = [];
    var bodyTop = v.rimH - 1 * k, i, y, h;

    // 1. the wall itself
    var wallD = wall(v.outer, bodyTop, D, 64);
    out.push({ d: wallD, fill: "url(#clayGrad)", cls: "pot-wall" });
    out.push({ d: wallD, fill: "url(#clayGradV)", cls: "pot-wall-shade" });

    // 2. glaze — climbs to the frontier, stops, leaves raw clay above
    if (!m.virgin && m.glaze > 0) {
      var yg = D - (D - v.rimH) * clamp01(m.glaze);
      out.push({ d: wall(v.outer, yg, D, 40), fill: "#8a4d2c", op: 0.4, cls: "pot-glaze" });
      h = v.outer(yg);
      out.push({ d: line(-h, yg, h, yg), stroke: "#f0c39a", sw: 1.1 * k, op: 0.5, cls: "pot-glaze-line" });
      // a human read is owed: the top band is left unfired, matte, no shine
      if (m.matte) {
        out.push({ d: wall(v.outer, yg, Math.min(D, yg + 9 * k), 8),
                   fill: "#6a4331", op: 0.5, cls: "pot-matte" });
      }
    }

    // 3. patina — wear, continuous, never saturating
    var speckles = Math.round(clamp01(m.patina) * 9);
    for (i = 0; i < speckles; i++) {
      y = v.rimH + (D - v.rimH) * (0.12 + 0.80 * latticeU(i * 3 + 1));
      var side = (i % 2) ? 1 : -1;
      out.push({ e: { cx: fmt(side * v.outer(y) * (0.22 + 0.56 * latticeU(i * 5 + 2))), cy: fmt(y),
                      rx: fmt(3.0 * k), ry: fmt(1.5 * k) },
                 fill: "#5e3018", op: 0.16, cls: "pot-patina" });
    }

    // 4. repair seams — a miss kept on the permanent record, mended in daylight
    //    with the house's own clay slip. Never gold; a boundary is not a prize.
    for (i = 0; i < m.seams; i++) {
      y = v.rimH + (D - v.rimH) * SEAM_U[i % SEAM_U.length];
      h = v.outer(y);
      out.push({ d: "M" + fmt(-h * 0.78) + " " + fmt(y - 3 * k) +
                    " Q0 " + fmt(y + 3.5 * k) + " " + fmt(h * 0.62) + " " + fmt(y - 1.5 * k),
                 stroke: "#e2b492", sw: 1.2 * k, op: 0.72, cls: "pot-seam" });
      out.push({ d: line(-h * 0.42, y - 2 * k, -h * 0.42, y + 3 * k),
                 stroke: "#e2b492", sw: 1 * k, op: 0.6, cls: "pot-seam" });
      out.push({ d: line(h * 0.26, y - 1 * k, h * 0.26, y + 4 * k),
                 stroke: "#e2b492", sw: 1 * k, op: 0.6, cls: "pot-seam" });
    }

    // 5. tally scratches — the labour, incised in gates of five
    if (m.tally > 0) {
      var yT = v.rimH + (D - v.rimH) * 0.80;
      var gates = Math.floor(m.tally / 5), rem = m.tally % 5;
      var groups = [], gi;
      for (gi = 0; gi < gates; gi++) groups.push(5);
      if (rem) groups.push(rem);
      var pitch = 3.2 * k, gapW = 5 * k, tall = 7 * k;
      var widths = groups.map(function (n) { return (Math.min(n, 4) - 1) * pitch + (n === 5 ? 2 * k : 0); });
      var totalW = widths.reduce(function (a, b) { return a + b; }, 0) + gapW * (groups.length - 1);
      var cursor = -totalW / 2;
      groups.forEach(function (n, gj) {
        var upright = Math.min(n, 4), j;
        for (j = 0; j < upright; j++) {
          out.push({ d: line(cursor + j * pitch, yT - tall / 2, cursor + j * pitch, yT + tall / 2),
                     stroke: "#6b3a20", sw: 0.9 * k, op: 0.5, cls: "pot-tally" });
        }
        if (n === 5) {
          out.push({ d: line(cursor - 1.4 * k, yT + tall / 2, cursor + (upright - 1) * pitch + 1.4 * k, yT - tall / 2),
                     stroke: "#6b3a20", sw: 0.9 * k, op: 0.5, cls: "pot-tally" });
        }
        cursor += widths[gj] + gapW;
      });
    }

    // 6. the damp ring — tended this turn, drying toward resting
    if (m.damp > 0) {
      out.push({ d: wall(v.outer, D - 0.14 * (D - v.rimH), D, 12),
                 fill: "#2a1710", op: fmt(clamp01(m.damp) * 0.45), cls: "pot-damp" });
    }

    // 7. rim, then the chips bitten out of it — one per miss actually run
    v.rim.forEach(function (spec) { out.push(spec); });
    for (i = 0; i < m.chips; i++) {
      var ci = i % CHIP_X.length;
      var cx = CHIP_X[ci] * M, cw = CHIP_W[ci] * k, ch = CHIP_H[ci] * k;
      var cy = v.rimH, apex = cx + CHIP_SKEW[ci] * cw;
      out.push({ d: "M" + fmt(cx - cw) + " " + fmt(cy) + " L" + fmt(cx + cw) + " " + fmt(cy) +
                    " L" + fmt(apex) + " " + fmt(cy - ch) + " Z", fill: "#5c2f1a", cls: "pot-chip" });
      // the pale face of a fresh break: unweathered clay, lighter than the wall
      out.push({ d: line(cx - cw, cy, apex, cy - ch),
                 stroke: "#e8b58c", sw: 0.8 * k, op: 0.5, cls: "pot-chip-break" });
    }

    // 8. authored identity detail, then feet
    v.ridges.forEach(function (spec) { out.push(spec); });
    v.feet.forEach(function (spec) { out.push(spec); });

    // 9. the light the scene already has: one glint per side, and the sundial's
    //    data-sunside picks which one is lit. No new animation lane.
    [-1, 1].forEach(function (s) {
      var y0 = v.rimH + (D - v.rimH) * 0.14, y1 = v.rimH + (D - v.rimH) * 0.66;
      var ym = (y0 + y1) / 2;
      out.push({ d: "M" + fmt(s * v.outer(y0) * 0.86) + " " + fmt(y0) +
                    " Q" + fmt(s * v.outer(ym) * 0.99) + " " + fmt(ym) +
                    " " + fmt(s * v.outer(y1) * 0.80) + " " + fmt(y1),
                 stroke: "#ffd9b0", sw: 3.2 * k, op: 1, cap: "round",
                 cls: "pot-glint " + (s < 0 ? "l" : "r") });
    });

    // 10. dawn condensation on the glazed band — the leaves' own .dew rule
    if (!m.virgin && m.glaze > 0) {
      var yd = D - (D - v.rimH) * clamp01(m.glaze);
      [-0.45, 0.12, 0.58].forEach(function (f, di) {
        out.push({ e: { cx: fmt(f * v.outer(yd + 4 * k)), cy: fmt(yd + (3 + di) * k),
                        rx: fmt(0.9 * k), ry: fmt(0.9 * k) },
                   fill: "#fff", cls: "dew" });
      });
    }

    return out;
  }

  var api = {
    VESSELS: VESSELS,
    DEFAULT_TRACK: DEFAULT_TRACK,
    build: build,
    marksFrom: marksFrom,
    _wall: wall,
    _latticeU: latticeU
  };

  if (root) root.Pots = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));
