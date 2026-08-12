/*
 * Node test for the CENTRE plant's data set (web/index.html). No DOM, no
 * framework — plain `node --test`, the lane pots.test.mjs and
 * growth-forms.test.mjs run in.
 *
 *   node --test web/centre-plant.test.mjs
 *
 * THE DEFECT THIS LOCKS OUT. Until 2026-08-12 the full-size plant at the centre
 * of the sill was built from the WHOLE lab's milestone ledger — every science's
 * leaves on one stem — while standing in the bench track's pot. Ben, looking at
 * the live shelf beside the six conservatory cards: it "still seems to be 'all
 * of the leafs in one' and it doesn't match the 6 images." On the 2026-08-12
 * feed that was 25 leaves over a 34-rung ladder, in a coherence pot whose own
 * card is a sparse young fern with two.
 *
 * So the centre must be ONE track's plant: its own closed milestones over its
 * own ladder length, exactly as a flank (`sillPlant`) and a conservatory card
 * (`drawGarden`) are parameterized. The page's derivation is `benchLadder`,
 * which this test lifts out of index.html and RUNS against the committed feed —
 * so it fails on behaviour, not on a spelling. The negative control is the
 * whole-lab count: the test is only meaningful because 2 !== 25, and it asserts
 * that gap directly.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const GF = require("./growth-forms.js");

const PAGE = readFileSync(new URL("./index.html", import.meta.url), "utf8");
const FEED = JSON.parse(readFileSync(new URL("../pot.json", import.meta.url), "utf8"));
const MILESTONES = FEED.milestones;

/* Lift a top-level `function name(...) { ... }` out of the page by brace
 * matching, so the test exercises the code that actually ships rather than a
 * copy of it. Anything that changes the function's behaviour changes this. */
function lift(name) {
  const start = PAGE.indexOf("function " + name + "(");
  assert.notEqual(start, -1, `index.html no longer defines ${name}()`);
  let depth = 0, i = PAGE.indexOf("{", start);
  const open = i;
  for (; i < PAGE.length; i++) {
    if (PAGE[i] === "{") depth++;
    else if (PAGE[i] === "}" && --depth === 0) break;
  }
  assert.ok(i > open, `could not brace-match ${name}()`);
  return PAGE.slice(start, i + 1);
}

/* `new Function` over the repo's own committed index.html — a test reading a
 * tracked file in its own checkout, never network or user input. It is the
 * point of the exercise: the shipped source is the thing under test. */
const evaluate = new Function(
  lift("isClosed") + "\n" + lift("benchLadder") +
  "\nreturn { isClosed: isClosed, benchLadder: benchLadder };"
)();
const { isClosed, benchLadder } = evaluate;

/* The bench track is the open experiment's track — the same rule pageTrack()
 * and GF.pageGrowthForm() use, so the pot, the plant and the form always agree
 * about which science is on the bench. */
const OPEN = MILESTONES.find((m) => m.status === "open");
const BENCH = OPEN ? OPEN.track : null;

test("the feed still poses the question this test answers", () => {
  assert.ok(OPEN, "no open milestone in the feed — the centre has no bench track");
  const wholeLadder = MILESTONES.length;
  const wholeClosed = MILESTONES.filter(isClosed).length;
  const benchLadderLen = MILESTONES.filter((m) => m.track === BENCH).length;
  const benchClosed = MILESTONES.filter((m) => m.track === BENCH && isClosed(m)).length;
  // The negative control. If these ever coincide, every assertion below passes
  // for free and this file stops guarding anything — so say so out loud.
  assert.notEqual(benchClosed, wholeClosed,
    `the bench track holds every closed milestone in the lab (${benchClosed}); ` +
    "this suite cannot tell a per-track plant from a whole-lab one");
  assert.ok(benchLadderLen < wholeLadder);
});

test("the centre plant grows only the bench track's ladder", () => {
  const bench = benchLadder(MILESTONES, BENCH, MILESTONES.length);
  assert.equal(bench.whole, false);
  assert.equal(bench.total, MILESTONES.filter((m) => m.track === BENCH).length);
  assert.ok(bench.milestones.every((m) => m.track === BENCH),
    "a milestone from another science reached the centre plant");
  // ...and it is the WHOLE of that track, not a slice of it
  assert.equal(bench.milestones.length, bench.total);
});

test("NEGATIVE: the whole-lab plant is gone — leaf count is the track's, not the ledger's", () => {
  const bench = benchLadder(MILESTONES, BENCH, MILESTONES.length);
  const leaves = bench.milestones.filter(isClosed).length;
  const wholeLab = MILESTONES.filter(isClosed).length;
  assert.notEqual(leaves, wholeLab, "the centre is still every science in one");
  assert.equal(leaves, MILESTONES.filter((m) => m.track === BENCH && isClosed(m)).length);

  // One node per closed milestone is the growth-form homogeneity contract, so
  // the leaf count on the rendered plant IS this number — assert it through the
  // registry rather than trusting the claim.
  const geo = GF.build("fern", {
    count: leaves, total: bench.total,
    openProg: 0.32, base: 344, rise: 154
  });
  assert.equal(geo.nodes.length, leaves);
  assert.notEqual(geo.nodes.length, wholeLab);
});

test("the centre and its conservatory card are the same measurement", () => {
  // A card derives `closed` and `total` for its track with exactly this rule
  // (drawGarden: filter by track, isClosed, total = track.length || expected).
  // The centre must land on the same two numbers, or the sill contradicts the
  // row of cards under it — which is the whole complaint.
  const bench = benchLadder(MILESTONES, BENCH, MILESTONES.length);
  const cardTrack = MILESTONES.filter((m) => m.track === BENCH);
  assert.deepEqual(bench.milestones, cardTrack);
  assert.equal(bench.total, cardTrack.length);
  assert.equal(bench.milestones.filter(isClosed).length, cardTrack.filter(isClosed).length);
});

test("every track can take the bench without the centre borrowing another's leaves", () => {
  const tracks = [...new Set(MILESTONES.map((m) => m.track))];
  assert.ok(tracks.length > 1);
  for (const track of tracks) {
    const bench = benchLadder(MILESTONES, track, MILESTONES.length);
    assert.equal(bench.total, MILESTONES.filter((m) => m.track === track).length, track);
    assert.ok(bench.milestones.every((m) => m.track === track), track);
    // the rungs it has not reached are real and non-negative: leaves + open +
    // unreached === the ladder, which is what makes the dashed future honest
    const closed = bench.milestones.filter(isClosed).length;
    const open = bench.milestones.some((m) => m.status === "open") ? 1 : 0;
    assert.ok(bench.total - closed - open >= 0, `${track} reached past its own ladder`);
  }
});

test("a feed with no tracks keeps the whole-ledger plant", () => {
  // Degradation, not a crash: when nothing carries a track there is only one
  // ladder to draw, so the centre falls back to the ledger and says so.
  const untracked = MILESTONES.map((m) => ({ ...m, track: undefined }));
  const bench = benchLadder(untracked, "coherence", 31);
  assert.equal(bench.whole, true);
  assert.equal(bench.total, 31);
  assert.equal(bench.milestones.length, untracked.length);
  // ...and an empty feed does not throw
  assert.equal(benchLadder([], "coherence", 31).total, 31);
  assert.equal(benchLadder(null, "coherence", 31).milestones.length, 0);
});

test("render() hands the centre the bench ladder, never the lab's", () => {
  // The wiring, guarded at the one call site. The old line — drawStalk with the
  // page-wide `milestones` and `total` — must not come back.
  const render = lift("render");
  assert.ok(render.includes("var bench = benchLadder(milestones, heroTrack, total);"));
  assert.ok(render.includes("drawStalk(bench.milestones, bench.total, season,"));
  assert.ok(!/drawStalk\(milestones,/.test(render),
    "the centre plant is being built from the whole ledger again");
  // The whole-lab closed set still reaches drawStalk, but only as the theater's
  // memory — a visitor's seen-set is not foliage.
  assert.ok(PAGE.includes("rememberClosedIds(Array.isArray(ledgerClosed) ? ledgerClosed : closed);"));
  // ...and the harness reports the plant as one track's ladder.
  assert.ok(PAGE.includes("growth_form: GF.pageGrowthForm(bench.milestones)"));
  assert.ok(PAGE.includes("leaves: benchClosed.length"));
});
