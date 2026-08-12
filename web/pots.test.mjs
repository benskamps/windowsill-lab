/*
 * Node test for the pot registry (web/pots.js). No DOM, no framework — plain
 * `node --test`, the same lane growth-forms.test.mjs runs in.
 *
 *   node --test web/pots.test.mjs
 *
 * Proves the three things a pot layer can get wrong: that the vessels are
 * actually DISTINGUISHABLE (the whole point — two tracks share the fern), that
 * the MOUTH AND FOOT ARE LAW (one soil line, one board, seven pots), and that
 * every mark is DERIVED — pure, deterministic, and monotone in the feed number
 * it claims to report. Negative controls first: a bare pot must be bare, and a
 * pot must never gain a mark it has no data for.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const POTS = require("./pots.js");

const TRACKS = ["physics", "coherence", "compute", "astronomy", "instrument", "boinc", "misc"];
const GEOM = { mouth: 70, depth: 126 };
const WORKED = POTS.marksFrom({
  closed: 12, total: 18, reviews: 1, nulls: 2, runs: 111, nullRuns: 2,
  lastAtMs: 1000, nowMs: 1000 + 3600e3, intervalH: 3
});
const BARE = POTS.marksFrom({ closed: 0, total: 2, runs: 0 });

function nums(spec) {
  if (spec.e) return [spec.e.cx, spec.e.cy, spec.e.rx, spec.e.ry];
  return (String(spec.d).match(/-?\d+(\.\d+)?/g) || []).map(Number);
}
function allSpecs(track, marks, geom) {
  return POTS.build(track, marks || WORKED, geom || GEOM);
}
function bbox(specs) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const s of specs) {
    if (s.e) {
      minX = Math.min(minX, s.e.cx - s.e.rx); maxX = Math.max(maxX, s.e.cx + s.e.rx);
      minY = Math.min(minY, s.e.cy - s.e.ry); maxY = Math.max(maxY, s.e.cy + s.e.ry);
      continue;
    }
    const pts = String(s.d).match(/-?\d+(\.\d+)?\s+-?\d+(\.\d+)?/g) || [];
    for (const p of pts) {
      const [x, y] = p.split(/\s+/).map(Number);
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
  }
  return { minX, maxX, minY, maxY };
}
function has(specs, cls) {
  return specs.some((s) => typeof s.cls === "string" && s.cls.split(/\s+/).includes(cls));
}
function count(specs, cls) {
  return specs.filter((s) => typeof s.cls === "string" && s.cls.split(/\s+/).includes(cls)).length;
}

// ── The interface ─────────────────────────────────────────────────────────────

test("every track in the feed's taxonomy has a vessel", () => {
  // mirrors src/lab/publish.py TRACKS + the misc/unknown default
  for (const t of TRACKS) assert.ok(POTS.VESSELS[t], `no vessel for track ${t}`);
  assert.equal(POTS.DEFAULT_TRACK, "misc");
});

test("every spec is a drawable path or ellipse with finite numbers", () => {
  for (const t of TRACKS) {
    const specs = allSpecs(t);
    assert.ok(specs.length > 6, `${t} drew almost nothing`);
    for (const s of specs) {
      assert.ok(s.d || s.e, `${t}: spec is neither path nor ellipse`);
      if (s.d) assert.match(s.d, /^M/, `${t}: path does not start with a moveto`);
      for (const n of nums(s)) assert.ok(Number.isFinite(n), `${t}: non-finite coordinate`);
    }
  }
});

test("an unknown track falls back to the default vessel, exactly", () => {
  assert.deepEqual(
    JSON.stringify(POTS.build("no-such-science", WORKED, GEOM)),
    JSON.stringify(POTS.build(POTS.DEFAULT_TRACK, WORKED, GEOM))
  );
});

// ── The mouth and the foot are law ────────────────────────────────────────────

test("every vessel spans exactly the shared mouth at y=0", () => {
  for (const t of TRACKS) {
    const box = bbox(allSpecs(t).filter((s) => (s.cls || "").indexOf("pot-rim") === 0));
    assert.ok(Math.abs(box.minY) < 0.01, `${t}: rim does not start at the mouth line`);
    // the rim may roll OUTSIDE the mouth, but it must reach the mouth exactly
    assert.ok(box.minX <= -GEOM.mouth + 0.01 && box.maxX >= GEOM.mouth - 0.01,
      `${t}: rim does not reach ±mouth`);
  }
});

test("every vessel stands on the same board", () => {
  for (const t of TRACKS) {
    const box = bbox(allSpecs(t));
    assert.ok(Math.abs(box.maxY - GEOM.depth) < 0.01, `${t}: foot is at ${box.maxY}, not ${GEOM.depth}`);
    assert.ok(box.minY >= -0.01, `${t}: geometry rises above the mouth line`);
  }
});

test("no vessel overhangs the sill absurdly", () => {
  for (const t of TRACKS) {
    const box = bbox(allSpecs(t));
    assert.ok(box.maxX <= GEOM.mouth * 1.2 && box.minX >= -GEOM.mouth * 1.2,
      `${t}: vessel is wider than 1.2x the mouth`);
  }
});

// ── Distinguishable — the reason the layer exists ─────────────────────────────

test("the six track vessels are pairwise distinct silhouettes", () => {
  const walls = new Map();
  for (const t of TRACKS) {
    const w = allSpecs(t, BARE).filter((s) => s.cls === "pot-wall")[0];
    assert.ok(w, `${t} has no wall`);
    for (const [other, d] of walls) {
      assert.notEqual(w.d, d, `${t} and ${other} draw the same wall`);
    }
    walls.set(t, w.d);
  }
});

test("physics and coherence share a growth form but never a vessel", () => {
  // publish.GROWTH_FORMS maps both onto `fern`; the pot is the only thing that
  // tells the two ferns apart, so this is the load-bearing assertion.
  const a = JSON.stringify(allSpecs("physics", BARE));
  const b = JSON.stringify(allSpecs("coherence", BARE));
  assert.notEqual(a, b);
});

// ── Purity and determinism ────────────────────────────────────────────────────

test("build is pure: the same inputs draw the same pot, twice", () => {
  for (const t of TRACKS) {
    assert.equal(JSON.stringify(allSpecs(t)), JSON.stringify(allSpecs(t)));
  }
});

test("the module contains no randomness and no clock", () => {
  const src = require("node:fs").readFileSync(new URL("./pots.js", import.meta.url), "utf8");
  assert.ok(!/Math\.random/.test(src), "Math.random in the pot layer");
  assert.ok(!/new Date|Date\.now/.test(src), "a clock inside the pot geometry");
});

test("a pot scales as one piece — a card mini is the same pot, smaller", () => {
  const big = bbox(allSpecs("astronomy", WORKED, { mouth: 70, depth: 126 }));
  const small = bbox(allSpecs("astronomy", WORKED, { mouth: 26, depth: 46 }));
  assert.ok(Math.abs(small.maxY - 46) < 0.01);
  assert.ok(Math.abs(small.maxX / small.minX - big.maxX / big.minX) < 0.05);
});

// ── The marks: every one derived, negative controls first ─────────────────────

test("NEGATIVE: a track with no runs draws a bare pot", () => {
  assert.equal(BARE.virgin, true);
  assert.equal(BARE.tally, 0);
  assert.equal(BARE.chips, 0);
  assert.equal(BARE.seams, 0);
  assert.equal(BARE.damp, 0);
  const specs = allSpecs("boinc", BARE);
  for (const cls of ["pot-glaze", "pot-glaze-line", "pot-matte", "pot-tally",
                     "pot-chip", "pot-seam", "pot-patina", "pot-damp", "dew"]) {
    assert.equal(has(specs, cls), false, `a pot with no data drew a ${cls}`);
  }
  // ...and it is still a pot: wall, rim, feet all present
  assert.ok(has(specs, "pot-wall") && has(specs, "pot-rim"));
});

test("NEGATIVE: a feed with no timestamp never fakes a fresh watering", () => {
  const m = POTS.marksFrom({ closed: 1, total: 4, runs: 3 });
  assert.equal(m.damp, 0);
  assert.equal(has(allSpecs("compute", m), "pot-damp"), false);
});

test("NEGATIVE: resting is not distress — a long-quiet track just reads dry", () => {
  const quiet = POTS.marksFrom({
    closed: 4, total: 4, runs: 10, lastAtMs: 0, nowMs: 400 * 3600e3, intervalH: 3
  });
  assert.equal(quiet.damp, 0);
  // and nothing else about the pot changed: same glaze, same tally as a fresh one
  const fresh = POTS.marksFrom({
    closed: 4, total: 4, runs: 10, lastAtMs: 0, nowMs: 1 * 3600e3, intervalH: 3
  });
  assert.equal(quiet.glaze, fresh.glaze);
  assert.equal(quiet.tally, fresh.tally);
  assert.ok(fresh.damp > 0.8);
});

test("glaze is the ladder climbed, and stops at the frontier", () => {
  assert.equal(POTS.marksFrom({ closed: 0, total: 4, runs: 2 }).glaze, 0);
  assert.equal(POTS.marksFrom({ closed: 2, total: 4, runs: 2 }).glaze, 0.5);
  assert.equal(POTS.marksFrom({ closed: 4, total: 4, runs: 2 }).glaze, 1);
  // the glazed band never covers the whole wall unless the ladder is finished
  const half = allSpecs("physics", POTS.marksFrom({ closed: 2, total: 4, runs: 2 }));
  const done = allSpecs("physics", POTS.marksFrom({ closed: 4, total: 4, runs: 2 }));
  const top = (specs) => bbox(specs.filter((s) => s.cls === "pot-glaze")).minY;
  assert.ok(top(half) > top(done), "a half-climbed ladder glazed higher than a finished one");
});

test("the unfired band appears only while a human read is owed", () => {
  const noReview = POTS.marksFrom({ closed: 2, total: 4, runs: 5 });
  const review = POTS.marksFrom({ closed: 2, total: 4, runs: 5, reviews: 1 });
  assert.equal(noReview.matte, false);
  assert.equal(review.matte, true);
  assert.equal(has(allSpecs("physics", noReview), "pot-matte"), false);
  assert.equal(has(allSpecs("physics", review), "pot-matte"), true);
});

test("scratches and patina grow with the runs, monotonically", () => {
  let lastT = -1, lastP = -1;
  for (const runs of [0, 1, 4, 9, 25, 64, 111, 400]) {
    const m = POTS.marksFrom({ closed: 1, total: 4, runs });
    assert.ok(m.tally >= lastT, `tally went backwards at ${runs} runs`);
    assert.ok(m.patina >= lastP, `patina went backwards at ${runs} runs`);
    lastT = m.tally; lastP = m.patina;
  }
  assert.equal(POTS.marksFrom({ closed: 1, total: 4, runs: 111 }).tally, 11);
  assert.ok(POTS.marksFrom({ closed: 1, total: 4, runs: 1e6 }).tally <= 12, "tally must stay legible");
  assert.ok(POTS.marksFrom({ closed: 1, total: 4, runs: 1e6 }).patina < 1);
});

test("scratches are struck in gates of five", () => {
  // 11 runs of labour → 3 groups (5,5,1) → 4+1 + 4+1 + 1 = 11 marks
  const specs = allSpecs("physics", POTS.marksFrom({ closed: 1, total: 4, runs: 121 }));
  assert.equal(POTS.marksFrom({ closed: 1, total: 4, runs: 121 }).tally, 11);
  assert.equal(count(specs, "pot-tally"), 11);
});

test("misses are kept in daylight: one chip per null run, one seam per null kept", () => {
  const m = POTS.marksFrom({ closed: 6, total: 8, runs: 20, nulls: 2, nullRuns: 3 });
  assert.equal(m.chips, 3);
  assert.equal(m.seams, 2);
  const specs = allSpecs("physics", m);
  assert.equal(count(specs, "pot-chip"), 3);
  // each seam is one slip line plus two staples
  assert.equal(count(specs, "pot-seam"), 6);
  // the seam is house clay slip, never gold — a boundary is not a prize
  for (const s of specs.filter((x) => x.cls === "pot-seam")) {
    assert.equal(s.stroke, "#e2b492");
  }
});

test("a flood of nulls stays legible instead of shredding the pot", () => {
  const m = POTS.marksFrom({ closed: 9, total: 9, runs: 60, nulls: 40, nullRuns: 40 });
  assert.equal(m.chips, 4);
  assert.equal(m.seams, 4);
});

test("no vessel ever carries a status hue", () => {
  // green/amber/grey belong to leaves; a pot must never rank or claim.
  const banned = ["#7fae6b", "#d2aa67", "#8a8f82", "var(--leaf)", "var(--review)", "var(--null)"];
  for (const t of TRACKS) {
    for (const s of allSpecs(t)) {
      for (const b of banned) {
        assert.notEqual(s.fill, b, `${t}: status hue on a vessel`);
        assert.notEqual(s.stroke, b, `${t}: status hue on a vessel`);
      }
    }
  }
});

test("both glints ship, one per side, so the sundial can pick", () => {
  for (const t of TRACKS) {
    const specs = allSpecs(t);
    assert.equal(count(specs, "l"), 1);
    assert.equal(count(specs, "r"), 1);
    assert.equal(count(specs, "pot-glint"), 2);
  }
});
