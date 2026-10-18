/*
 * hotplate.js — the bench model in the measurement panel. A tray of 16 × 16
 * magnet tiles sits on a hot plate; the knob sets the plate's temperature, every
 * tile flips by the Metropolis rule at that temperature, and a dial gauge reads
 * |m|, the share of tiles that agree. It is drawn with the vendored IsoKit
 * (web/iso-kit.js) and it RUNS: the gauge is never scripted.
 *
 * What it is NOT: a receipt. The panel around it holds the run's own numbers;
 * this is the same rule on a sheet small enough to watch, running in the
 * visitor's browser. Two things on it come from the feeds, and only these:
 *
 *   - the tray starts from a 16 × 16 sample of the same saved lattice frame
 *     the panel shows in the middle of its three (the run's nearest to the
 *     tipping point, physics-latest.json), or from a fixed seeded scatter,
 *     labelled as such, when no frame reached the page;
 *   - the base plate is a slice of tree with one ring per day the lab filed a
 *     report (pot.json), widest where the day was busiest, the newest in amber,
 *     the same ledger the hero's ring section draws. With no feed the wood is
 *     bare; it never invents a history.
 *
 * Pure helpers (exactM, ringDays, ringRadii, trayFromSnapshot) are
 * exported for web/hotplate.test.mjs; build() returns the figure's SVG string;
 * mount() puts it on the page and runs it.
 */
(function (root) {
  "use strict";

  var N = 16;
  var TC = 2 / Math.log(1 + Math.SQRT2); // Onsager, 1944: 2.269185…
  var T_MIN = 1.5, T_MAX = 3.5;
  var SWEEP = Math.PI * 1.5; // 270° of travel on knob and gauge
  var SWEEPS_PER_SECOND = 9; // slow enough to watch tiles flip

  function angleOfT(T) { return -SWEEP / 2 + ((T - T_MIN) / (T_MAX - T_MIN)) * SWEEP; }
  function angleOfM(m) { return -SWEEP / 2 + m * SWEEP; }

  // Yang (1952): the exact spontaneous magnetization of the infinite sheet.
  // Zero at and above the tipping point.
  function exactM(T) {
    if (!(T > 0) || T >= TC) return 0;
    var b = 1 - Math.pow(Math.sinh(2 / T), -4);
    return b <= 0 ? 0 : Math.pow(b, 0.125);
  }

  // One entry per calendar day that carries at least one report, oldest first.
  // Same date rule as the hero's ledgerDays(): a malformed date is skipped.
  function ringDays(reports) {
    var by = {};
    (Array.isArray(reports) ? reports : []).forEach(function (r) {
      if (!r || typeof r.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(r.date)) return;
      by[r.date] = (by[r.date] || 0) + 1;
    });
    return Object.keys(by).sort().map(function (d) { return { date: d, n: by[d] }; });
  }

  // The outer radius of every ring, pith outward: each ring is as wide as its
  // day was busy (capped, so one flood of reports cannot swallow the plate),
  // and the trunk is scaled so the newest ring lands exactly at r1.
  function ringRadii(days, r0, r1) {
    var widths = days.map(function (d) { return 1.6 + 0.7 * Math.min(d.n, 8); });
    var total = widths.reduce(function (a, b) { return a + b; }, 0);
    var grow = total ? (r1 - r0) / total : 0, r = r0;
    return widths.map(function (w) { r += w * grow; return r; });
  }

  // A bit-packed L × L frame (1 = up, most significant bit first), sampled on
  // an N × N grid. Returns null for anything that is not such a frame.
  function trayFromSnapshot(b64, L) {
    if (typeof b64 !== "string" || !(L >= N) || typeof atob !== "function") return null;
    var raw;
    try { raw = atob(b64); } catch (e) { return null; }
    if (raw.length * 8 < L * L) return null;
    var stride = Math.floor(L / N), s = new Int8Array(N * N);
    for (var j = 0; j < N; j++) for (var i = 0; i < N; i++) {
      var idx = (j * stride) * L + i * stride;
      s[j * N + i] = (raw.charCodeAt(idx >> 3) >> (7 - (idx & 7))) & 1 ? 1 : -1;
    }
    return s;
  }

  // A fixed scatter for when no frame reached the page: the same on every load.
  function seededTray() {
    var x = 20261017, s = new Int8Array(N * N);
    for (var i = 0; i < N * N; i++) {
      x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
      s[i] = ((x >>> 0) % 100) < 62 ? 1 : -1;
    }
    return s;
  }

  // ── The world (1 unit ≈ 1 px of the bench model) ─────────────────────────
  var WIDTH = 640, HEIGHT = 440;
  var PLATE = { x: -160, y: -86, w: 306, d: 172, r: 9 };
  var PLATE_H = 12, FOOT_H = 5;
  var HEAT = { x: -146, y: -74, w: 160, d: 148, r: 5 };
  var HEAT_H = 16;
  var TRAY = { x: -138, y: -66, w: 144, d: 132, r: 3 };
  var TRAY_Z = HEAT_H, TRAY_FLOOR = 2, RIM = 5;
  var PITCH = 7.6, TILE = 6.2;
  var GRID = { x: TRAY.x + (TRAY.w - N * PITCH) / 2, y: TRAY.y + (TRAY.d - N * PITCH) / 2 };
  var UP_H = 4.2, DN_H = 0.9;
  var KNOB = [92, 46], KNOB_R = 12, KNOB_H = 9;
  var SCALE_R = 22;
  var GAUGE = [104, -38], GAUGE_R = 26, GAUGE_Z = 74, GAUGE_H = 9;
  var GAUGE_TOP = GAUGE_Z + GAUGE_H;
  var PITH = [-24, 6];

  function projection(k) {
    return k.fitProjection(
      k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0).concat([
        [GAUGE[0], GAUGE[1] - GAUGE_R, GAUGE_TOP + 4],
        [GAUGE[0] + GAUGE_R, GAUGE[1], GAUGE_TOP],
      ]),
      WIDTH, HEIGHT, { pad: 26, azimuth: 38 });
  }

  function pointerAt(k, P, T) {
    var a = angleOfT(T);
    return k.lineOnTop(KNOB, [KNOB[0] + Math.sin(a) * (KNOB_R - 4), KNOB[1] - Math.cos(a) * (KNOB_R - 4)], KNOB_H + 0.1, P);
  }
  function needleAt(k, P, m) {
    var a = angleOfM(m);
    return k.lineOnTop(
      [GAUGE[0] - Math.sin(a) * 4, GAUGE[1] + Math.cos(a) * 4],
      [GAUGE[0] + Math.sin(a) * (GAUGE_R - 2.4), GAUGE[1] - Math.cos(a) * (GAUGE_R - 2.4)],
      GAUGE_TOP + 0.2, P);
  }

  // The end grain: one ring per report day, every ring sharing one wobble
  // scaled by its radius (so rings never cross), each clipped to the plate's
  // groove so its ends land on that line.
  function grainSvg(k, P, days) {
    if (!days.length) return "";
    var box = k.insetPlan(PLATE, 5);
    var lo = [box.x + box.r, box.y + box.r], hi = [box.x + box.w - box.r, box.y + box.d - box.r];
    var inside = function (p) {
      var cx = Math.min(hi[0], Math.max(lo[0], p[0])), cy = Math.min(hi[1], Math.max(lo[1], p[1]));
      return Math.hypot(p[0] - cx, p[1] - cy) <= box.r;
    };
    var wob = function (t) { return 1 + 0.035 * Math.sin(3 * t + 0.7) + 0.02 * Math.sin(5 * t + 2.1) + 0.012 * Math.sin(9 * t + 0.3); };
    var radii = ringRadii(days, 18, 172);
    var TAU = Math.PI * 2, steps = 240;
    var out = [];
    radii.forEach(function (R, i) {
      var drift = i * 0.18;
      var pt = function (t) { return [PITH[0] + drift + R * wob(t) * Math.cos(t), PITH[1] + R * 0.86 * wob(t) * Math.sin(t)]; };
      var edge = function (a, b) {
        for (var n = 0; n < 24; n++) { var m = (a + b) / 2; if (inside(pt(m)) === inside(pt(a))) a = m; else b = m; }
        return pt((a + b) / 2);
      };
      var t0 = 0;
      while (inside(pt(t0)) && t0 < TAU) t0 += TAU / steps; // start outside so a run never wraps
      var runs = [], run = null;
      for (var s = 0; s <= steps; s++) {
        var a = t0 + (s - 1) * TAU / steps, t = t0 + s * TAU / steps;
        var p = pt(t), inNow = inside(p);
        if (inNow && !run) run = s === 0 ? [p] : [edge(a, t), p];
        else if (inNow) run.push(p);
        else if (run) { run.push(edge(a, t)); runs.push(run); run = null; }
      }
      if (run) runs.push(run);
      var d = runs.map(function (pts) {
        return "M" + pts.map(function (q) { return k.iso([q[0], q[1], 0], P).map(function (v) { return v.toFixed(1); }).join(" "); }).join("L");
      }).join("");
      var newest = i === radii.length - 1;
      out.push(k.lineSvg(d, { tone: newest ? "mid" : i % 5 === 4 ? "lo" : "faint", className: newest ? "grain-newest" : undefined }));
    });
    return out.join("");
  }

  function build(k, opts) {
    opts = opts || {};
    var P = projection(k);
    var at = function (p) { return k.iso(p, P); };
    var S = function (paths, style) { return k.solidSvg(paths, style); };
    var L = function (d, style) { return k.lineSvg(d, style); };
    var D = function (pts, style) { return k.dotsSvg(pts, style); };
    var depth = function (p) { return k.depthOf([p[0], p[1], p[2] || 0], P); };
    var byDepth = function (pts) { return pts.slice().sort(function (a, b) { return depth(a) - depth(b); }); };
    var s0 = opts.start || seededTray();
    var T0 = opts.T0 || 2.27;

    // Base plate: feet, plate, end grain, groove, screws, ruler strip, label plate.
    function plate() {
      var out = ['<path class="iso-halo" d="' + k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P) + '"/>'];
      byDepth(k.corners(PLATE, 22)).forEach(function (c) {
        out.push(S(k.cylinder(c[0], c[1], 7.5, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
        out.push(S(k.cylinder(c[0], c[1], 5.6, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
      });
      out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid" }));
      out.push('<g data-part="grain">' + grainSvg(k, P, opts.days || []) + "</g>");
      out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
      var screws = k.corners(PLATE, 11);
      out.push(L(screws.map(function (c) { return k.ring(c[0], c[1], 2.3, 0, P, 16); }).join(""), { tone: "lo" }));
      out.push(D(screws.map(function (c) { return at([c[0], c[1], 0]); }), { size: 0.5 }));
      // A ruler strip along the front edge: one tick per tile, a major every four.
      var strip = { x: GRID.x - 3, y: PLATE.y + PLATE.d - 13, w: N * PITCH + 6, d: 6, r: 1 };
      out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
      var ticks = k.topTicks(GRID.x + PITCH / 2, GRID.x + PITCH * (N - 0.5) + 0.01, PITCH, 4, strip.y + 0.6, 0.6, [1.8, 3.4], P);
      out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
      out.push(D([at([strip.x + 1.6, strip.y + 3, 0.6]), at([strip.x + strip.w - 1.6, strip.y + 3, 0.6])], { size: 0.4 }));
      // A label plate with two rule lines and one engraved line.
      var label = { x: 6, y: PLATE.y + PLATE.d - 30, w: 40, d: 18, r: 1.5 };
      out.push(S(k.slabOf(label, 0, 0.8, P, 3, 0.3), { tone: "lo", crease: "none" }));
      out.push(k.faceTextSvg(k.topMatrix([label.x + 4, label.y + 6.2], 0.8, P, "x"), "ISING · J=1", { size: 3, tone: "mid" }));
      [10, 13].forEach(function (yy) {
        out.push(L(k.lineOnTop([label.x + 4, label.y + yy], [label.x + label.w - (yy === 13 ? 14 : 4), label.y + yy], 0.8, P), { tone: "faint", free: "both" }));
      });
      out.push(D([[label.x + 2, label.y + 2], [label.x + label.w - 2, label.y + 2], [label.x + 2, label.y + label.d - 2], [label.x + label.w - 2, label.y + label.d - 2]]
        .map(function (c) { return at([c[0], c[1], 0.8]); }), { size: 0.35 }));
      return out.join("");
    }

    // The hot plate: body, vent slots on the front, a terminal block, corner screws.
    function heater() {
      var out = ['<path class="iso-halo" d="' + k.haloOf(k.insetPlan(HEAT, 2), 0, 0.1, P) + '" style="filter:blur(3px)"/>'];
      out.push(S(k.slabOf(HEAT, 0, 3, P, 6, 0.6), { tone: "mid" }));
      out.push(S(k.slabOf(k.insetPlan(HEAT, 1.2), 3, HEAT_H - 3, P, 6, 0.8), { tone: "mid" }));
      var fy = HEAT.y + HEAT.d - 1.2;
      for (var i = 0; i < 9; i++) {
        var x = HEAT.x + 22 + i * 13;
        out.push(L("M" + at([x, fy, 6]).join(" ") + "L" + at([x + 8, fy, 6]).join(" ") + "M" + at([x, fy, 10]).join(" ") + "L" + at([x + 8, fy, 10]).join(" "), { tone: "lo" }));
        out.push(L("M" + at([x, fy, 6]).join(" ") + "L" + at([x, fy, 10]).join(" ") + "M" + at([x + 8, fy, 6]).join(" ") + "L" + at([x + 8, fy, 10]).join(" "), { tone: "lo" }));
      }
      var term = { x: HEAT.x + HEAT.w - 0.5, y: 30, w: 6, d: 14, r: 1 };
      out.push(S(k.slabOf(term, 4, 8, P, 3, 0.4), { tone: "mid" }));
      out.push(D([at([term.x + 6, 34, 8]), at([term.x + 6, 40, 8])], { size: 0.5 }));
      out.push(D(k.corners(HEAT, 5).map(function (c) { return at([c[0], c[1], HEAT_H]); }), { size: 0.45 }));
      return out.join("");
    }

    // The tray: floor and the back and left walls before the tiles, the front
    // and right walls after them.
    function trayBack() {
      var z = TRAY_Z + TRAY_FLOOR;
      var out = [S(k.slabOf(TRAY, TRAY_Z, TRAY_FLOOR, P, 4, 0.4), { tone: "mid" })];
      out.push(S(k.slabOf({ x: TRAY.x, y: TRAY.y, w: TRAY.w, d: 3, r: 1 }, z, RIM, P, 3, 0.3), { tone: "mid" }));
      out.push(S(k.slabOf({ x: TRAY.x, y: TRAY.y, w: 3, d: TRAY.d, r: 1 }, z, RIM, P, 3, 0.3), { tone: "mid" }));
      for (var i = 1; i < N; i++) {
        var gx = GRID.x + i * PITCH;
        out.push(L(k.lineOnTop([gx, GRID.y], [gx, GRID.y + N * PITCH], z, P), { tone: "faint" }));
      }
      return out.join("");
    }
    function trayFront() {
      var z = TRAY_Z + TRAY_FLOOR;
      return [
        S(k.slabOf({ x: TRAY.x + TRAY.w - 3, y: TRAY.y, w: 3, d: TRAY.d, r: 1 }, z, RIM, P, 3, 0.3), { tone: "mid" }),
        S(k.slabOf({ x: TRAY.x, y: TRAY.y + TRAY.d - 3, w: TRAY.w, d: 3, r: 1 }, z, RIM, P, 3, 0.3), { tone: "mid" }),
        D(k.corners(TRAY, 1.5).map(function (c) { return at([c[0], c[1], z + RIM]); }), { size: 0.4 }),
      ].join("");
    }

    // The tiles: each holds both poses, and the page flips data-up.
    function tiles() {
      var z = TRAY_Z + TRAY_FLOOR, cells = [];
      for (var j = 0; j < N; j++) for (var i = 0; i < N; i++) cells.push([i, j]);
      cells.sort(function (a, b) {
        return depth([GRID.x + a[0] * PITCH, GRID.y + a[1] * PITCH, 0]) - depth([GRID.x + b[0] * PITCH, GRID.y + b[1] * PITCH, 0]);
      });
      return cells.map(function (c) {
        var i = c[0], j = c[1];
        var plan = { x: GRID.x + i * PITCH + (PITCH - TILE) / 2, y: GRID.y + j * PITCH + (PITCH - TILE) / 2, w: TILE, d: TILE, r: 0.8 };
        var up = S(k.slabOf(plan, z, UP_H, P, 2, 0.35), { tone: "hi", crease: "lo", lit: true, className: "u" });
        var dn = S(k.slabOf(plan, z, DN_H, P, 2), { tone: "lo", crease: "none", className: "d" });
        return '<g class="sp" data-i="' + (j * N + i) + '" data-up="' + (s0[j * N + i] > 0 ? 1 : 0) + '">' + up + dn + "</g>";
      }).join("");
    }

    // The knob: skirt, scale ring with ticks, the tipping-point mark, knurled cap.
    function knob() {
      var x = KNOB[0], y = KNOB[1], out = [];
      out.push(S(k.cylinder(x, y, SCALE_R + 3, 0, 1.2, P, 56, 0.3), { tone: "lo" }));
      var t = k.radialTicks(x, y, SCALE_R + 3, 20, 5, 1.2, [1.8, 3.6], P, -SWEEP / 2, SWEEP);
      out.push(L(t.minor, { tone: "lo" }), L(t.major, { tone: "mid" }));
      var a = angleOfT(TC);
      var tip = [x + Math.sin(a) * (SCALE_R + 3), y - Math.cos(a) * (SCALE_R + 3)];
      out.push(L(k.lineOnTop([x + Math.sin(a) * KNOB_R, y - Math.cos(a) * KNOB_R], tip, 1.2, P), { tone: "hi", className: "tc-mark" }));
      out.push('<g class="tc-mark">' + D([at([tip[0], tip[1], 1.2])], { size: 0.6, tone: "hi" }) + "</g>");
      out.push(S(k.cylinder(x, y, KNOB_R, 1.2, 2.4, P, 48, 0.3), { tone: "mid" }));
      out.push(S(k.cylinder(x, y, KNOB_R - 1.6, 3.6, KNOB_H - 3.6, P, 48, 0.6), { tone: "mid" }));
      out.push(L(k.knurl(x, y, KNOB_R - 1.6, 3.6, KNOB_H, 60, P), { tone: "lo" }));
      out.push(L(k.ring(x, y, KNOB_R - 4, KNOB_H, P, 40), { tone: "faint" }));
      out.push(k.faceTextSvg(k.topMatrix([x - 14, y + SCALE_R + 8], 0, P, "x"), String(T_MIN), { size: 3, tone: "lo", anchor: "middle" }));
      out.push(k.faceTextSvg(k.topMatrix([x + 15, y + SCALE_R + 8], 0, P, "x"), String(T_MAX), { size: 3, tone: "lo", anchor: "middle" }));
      return out.join("");
    }

    // The gauge: foot, post, collar, dial body, scale.
    function gauge() {
      var x = GAUGE[0], y = GAUGE[1], out = [];
      out.push(S(k.cylinder(x, y + GAUGE_R + 8, 9, 0, 3, P, 36, 0.4), { tone: "mid" }));
      out.push(S(k.cylinder(x, y + GAUGE_R + 8, 3.4, 3, GAUGE_Z - 12, P, 24), { tone: "mid", crease: "none" }));
      out.push(L([22, 42].map(function (zz) { return k.sideArc(x, y + GAUGE_R + 8, 3.4, zz, P, 14); }).join(""), { tone: "faint" }));
      out.push(S(k.slabOf({ x: x - 6, y: y + GAUGE_R - 2, w: 12, d: 16, r: 2 }, GAUGE_Z - 10, 9, P, 4, 0.5), { tone: "mid" }));
      out.push(D([at([x - 3, y + GAUGE_R + 12, GAUGE_Z - 1]), at([x + 3, y + GAUGE_R + 12, GAUGE_Z - 1])], { size: 0.45 }));
      out.push(S(k.cylinder(x, y, GAUGE_R, GAUGE_Z, GAUGE_H, P, 72, 0.8), { tone: "hi", crease: "lo" }));
      out.push(L(k.knurl(x, y, GAUGE_R, GAUGE_TOP - 3.4, GAUGE_TOP, 96, P, 0.3), { tone: "lo" }));
      out.push(L(k.ring(x, y, GAUGE_R - 2.4, GAUGE_TOP, P, 72), { tone: "lo" }));
      var t = k.radialTicks(x, y, GAUGE_R - 3.4, 20, 5, GAUGE_TOP, [1.4, 3.2], P, -SWEEP / 2, SWEEP);
      out.push(L(t.minor, { tone: "lo" }), L(t.major, { tone: "mid" }));
      out.push(k.faceTextSvg(k.topMatrix([x, y + 11], GAUGE_TOP, P, "x"), "|m|", { size: 4, tone: "lo", anchor: "middle" }));
      out.push(k.faceTextSvg(k.topMatrix([x - 15, y + 17], GAUGE_TOP, P, "x"), "0", { size: 3, tone: "lo", anchor: "middle" }));
      out.push(k.faceTextSvg(k.topMatrix([x + 15, y + 17], GAUGE_TOP, P, "x"), "1", { size: 3, tone: "lo", anchor: "middle" }));
      out.push(L(k.ring(x, y, 1.8, GAUGE_TOP, P, 16), { tone: "mid" }));
      return out.join("");
    }

    // The cables: knob to the heater's terminal; the tray's probe to the gauge.
    function cables() {
      return [
        k.wireSvg(at([KNOB[0] - SCALE_R - 3, KNOB[1] - 4, 0.6]), at([HEAT.x + HEAT.w + 5.5, 40, 8]),
          { via: [at([KNOB[0] - 40, KNOB[1] - 4, 0.3]), at([HEAT.x + HEAT.w + 12, 40, 0.3])], tone: "mid" }),
        k.wireSvg(at([TRAY.x + TRAY.w, TRAY.y + 20, TRAY_Z + TRAY_FLOOR + 3]), at([GAUGE[0] - 6, GAUGE[1] + GAUGE_R + 6, GAUGE_Z - 6]),
          { via: [at([TRAY.x + TRAY.w + 14, TRAY.y + 20, TRAY_Z + 4]), at([GAUGE[0] - 16, GAUGE[1] + GAUGE_R + 6, GAUGE_Z - 6])], tone: "lo", dotted: true }),
      ].join("");
    }

    var svg = k.figureSvg({
      width: WIDTH, height: HEIGHT,
      label: "A bench model of the magnet experiment. A tray of 16 by 16 small magnet tiles sits on a hot plate. " +
        "Tiles pointing up stand raised and lit; tiles pointing down lie flat. A knob in front sets the temperature " +
        "from " + T_MIN + " to " + T_MAX + ", with a mark at the exact tipping point 2.269. A dial gauge on a post reads " +
        "the share of tiles that agree. The base is a slice of wood with one ring per day the lab filed a report.",
      body: [
        plate(), heater(), trayBack(),
        '<g data-part="tiles">' + tiles() + "</g>",
        trayFront(), cables(), gauge(),
        '<path data-part="needle" class="iso-line" data-tone="hi" data-free="start" d="' + needleAt(k, P, 0.5) + '" style="stroke-width:1.2"/>',
        knob(),
        '<path data-part="pointer" class="iso-line" data-tone="hi" data-free="start" d="' + pointerAt(k, P, T0) + '" style="stroke-width:1.4"/>',
      ],
    });
    return { svg: svg, P: P, s0: s0, T0: T0 };
  }

  // Put the figure on the page and run it. `stage` is the .iso-stage element;
  // `readout` the corner that prints T, agree and exact. Returns a handle the
  // page feeds as the two feeds land, in either order.
  function mount(stage, readout, k, opts) {
    opts = opts || {};
    var built = build(k, opts);
    var P = built.P;
    stage.innerHTML = built.svg;
    var svg = stage.querySelector("svg");
    var pointer = svg.querySelector('[data-part="pointer"]');
    var needle = svg.querySelector('[data-part="needle"]');
    var grain = svg.querySelector('[data-part="grain"]');
    var tiles = Array.prototype.slice.call(svg.querySelectorAll(".sp"))
      .sort(function (a, b) { return a.dataset.i - b.dataset.i; });
    var s = new Int8Array(built.s0);
    var still = root.matchMedia ? root.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
    var clamp = function (v, lo, hi) { return Math.min(hi, Math.max(lo, v)); };
    var T = built.T0, target = T, shown = T, mAvg = 0, needleM = 0.5;
    var frame = 0, last = 0, clock = 0, acc = 0, touring = true, visible = false, idle = 0;

    function paintTiles() { for (var i = 0; i < N * N; i++) tiles[i].dataset.up = s[i] > 0 ? 1 : 0; }

    // One Metropolis sweep, random-site order, periodic edges, J = 1.
    function sweep() {
      for (var n = 0; n < N * N; n++) {
        var i = (Math.random() * N * N) | 0, x = i % N, y = (i / N) | 0;
        var nb = s[y * N + (x + 1) % N] + s[y * N + (x + N - 1) % N] + s[((y + 1) % N) * N + x] + s[((y + N - 1) % N) * N + x];
        var dE = 2 * s[i] * nb;
        if (dE <= 0 || Math.random() < Math.exp(-dE / T)) { s[i] = -s[i]; tiles[i].dataset.up = s[i] > 0 ? 1 : 0; }
      }
      var sum = 0;
      for (var j = 0; j < N * N; j++) sum += s[j];
      var m = Math.abs(sum) / (N * N);
      mAvg = mAvg ? mAvg * 0.85 + m * 0.15 : m;
    }
    // The idle tour: cold, through the mark, hot, and back.
    var tour = [1.7, 2.1, 2.27, 2.5, 3.2, 2.27];
    function tourAt(t) { return tour[Math.floor(t / 4.2) % tour.length]; }
    function draw() {
      pointer.setAttribute("d", pointerAt(k, P, shown));
      needle.setAttribute("d", needleAt(k, P, needleM));
      var text = "T " + T.toFixed(2) + " · agree " + mAvg.toFixed(2) + " · exact " + exactM(T).toFixed(2);
      if (readout && readout.textContent !== text) readout.textContent = text;
      stage.setAttribute("aria-valuenow", T.toFixed(2));
      stage.setAttribute("aria-valuetext", text);
    }
    function tick(now) {
      var dt = last ? Math.min((now - last) / 1000, 1 / 20) : 1 / 60;
      last = now;
      if (touring) { clock += dt; target = tourAt(clock); }
      T = target;
      shown += (T - shown) * (1 - Math.exp(-dt / 0.18));
      acc += dt * SWEEPS_PER_SECOND;
      while (acc >= 1) { sweep(); acc -= 1; }
      needleM += (mAvg - needleM) * (1 - Math.exp(-dt / 0.35));
      draw();
      frame = visible ? requestAnimationFrame(tick) : 0;
    }
    function run() { if (!frame && visible && !still.matches) { last = 0; frame = requestAnimationFrame(tick); } }
    function settleStill() { for (var i = 0; i < 300; i++) sweep(); needleM = mAvg; shown = T; draw(); }
    function steer(next) {
      touring = false;
      target = clamp(Math.round(next * 100) / 100, T_MIN, T_MAX);
      clearTimeout(idle);
      idle = setTimeout(function () { touring = !still.matches; clock = 0; run(); }, 9000);
      if (still.matches) { T = target; mAvg = 0; settleStill(); } else run();
    }
    if (typeof IntersectionObserver === "function") {
      new IntersectionObserver(function (es) {
        visible = es[es.length - 1].isIntersecting;
        if (visible) run(); else frame = 0;
      }, { rootMargin: "80px 0px" }).observe(stage);
    } else { visible = true; run(); }
    stage.addEventListener("pointermove", function (e) {
      var box = svg.getBoundingClientRect();
      steer(T_MIN + clamp((e.clientX - box.left) / box.width, 0, 1) * (T_MAX - T_MIN));
    });
    stage.addEventListener("keydown", function (e) {
      var to = null;
      if (e.key === "ArrowRight" || e.key === "ArrowUp") to = target + 0.05;
      if (e.key === "ArrowLeft" || e.key === "ArrowDown") to = target - 0.05;
      if (e.key === "Home") to = T_MIN;
      if (e.key === "End") to = T_MAX;
      if (e.key === "t" || e.key === "T") to = TC;
      if (to === null) return;
      e.preventDefault();
      steer(to);
    });
    if (still.matches) { touring = false; settleStill(); } else draw();

    return {
      // pot.json landed: grow the end grain from its report ledger.
      setReports: function (reports) {
        var days = ringDays(reports);
        if (grain) grain.innerHTML = grainSvg(k, P, days);
        return days;
      },
      // physics-latest.json landed: restart the tray from the run's own frame.
      setStart: function (start) {
        if (!start) return false;
        s = new Int8Array(start); mAvg = 0; paintTiles();
        if (still.matches) settleStill();
        return true;
      },
    };
  }

  var api = {
    N: N, TC: TC, T_MIN: T_MIN, T_MAX: T_MAX,
    exactM: exactM,
    angleOfT: angleOfT,
    angleOfM: angleOfM,
    ringDays: ringDays,
    ringRadii: ringRadii,
    trayFromSnapshot: trayFromSnapshot,
    seededTray: seededTray,
    build: build,
    mount: mount,
  };

  // Browser: attach as a global the classic <script> can read.
  if (root) root.Hotplate = api;
  // CommonJS: harmless under a classic <script> load, importable by the test.
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));
