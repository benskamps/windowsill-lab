/*
 * Node test for the page's own honesty layer (web/index.html). No DOM, no
 * framework — plain `node --test`, the lane pots.test.mjs, growth-forms.test.mjs
 * and centre-plant.test.mjs run in.
 *
 *   node --test web/honest-state.test.mjs
 *
 * WHAT THIS FILE GUARDS. The lab's rule is that a published number is a checked
 * claim, not a mood. The page is the surface where that rule is easiest to
 * break by accident: a counter drawn from one denominator beside a counter
 * drawn from another, a rail parked on a phase that finished, a card row that
 * hard-codes how many sciences exist. Each test below runs the page's own
 * function against the page's own committed feed, so it fails on behaviour
 * rather than on a spelling.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const PAGE = readFileSync(new URL("./index.html", import.meta.url), "utf8");
const FEED = JSON.parse(readFileSync(new URL("../pot.json", import.meta.url), "utf8"));

/* Lift a top-level `function name(...) { ... }` out of the page by brace
 * matching, so the test exercises the code that actually ships rather than a
 * copy of it. (Same helper as centre-plant.test.mjs, deliberately duplicated:
 * these files have no build step and no module system between them.) */
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

function evaluate(names, extra) {
  const body = names.map(lift).join("\n") + "\n" + (extra || "") +
    "\nreturn { " + names.map((n) => `${n}: ${n}`).join(", ") + " };";
  return new Function(body)();
}

/* ── The hunt strip: one denominator ─────────────────────────────────────── */

const { huntCounters } = evaluate(["huntCounters"]);

test("the strip's figures are all counts of the same events", () => {
  const hunt = FEED.hunt;
  assert.ok(hunt, "the committed feed carries no hunt block to check");
  const c = huntCounters(hunt);
  assert.equal(c.impostors + c.known + c.leads + c.unresolved, c.events,
    `the strip prints ${c.impostors}+${c.known}+${c.leads}+${c.unresolved} ` +
    `against ${c.events} events`);
});

test("NEGATIVE: the star count is a different number, and is kept out", () => {
  // The defect this file exists for. The strip printed `known_recovered` — 9
  // distinct stars across every run — in a row of event counts, so the visible
  // numbers summed to 119 against 113 events. If these two ever coincide the
  // assertion above passes for free, so say the gap out loud.
  const c = huntCounters(FEED.hunt);
  assert.notEqual(c.known, FEED.hunt.known_recovered,
    "the star count and the known-planet event count are the same number here; " +
    "this test can no longer tell one denominator from two");
  assert.equal(c.known, FEED.hunt.dispositions["known-planet"]);
});

test("the page's lead count agrees with the publisher's own counter", () => {
  // The page derives leads from the histogram so the arithmetic closes; the
  // publisher derives the same number from the receipts. Drift between them is
  // a producer/page disagreement, which is exactly what a feed contract is for.
  const c = huntCounters(FEED.hunt);
  assert.equal(c.leads, FEED.hunt.leads_awaiting_human_review);
});

test("a missing or empty hunt block counts to zero, not to NaN", () => {
  for (const empty of [null, undefined, {}, { dispositions: {} }]) {
    const c = huntCounters(empty);
    assert.deepEqual(c, { events: 0, impostors: 0, unresolved: 0, known: 0, leads: 0 });
  }
});

test("an unknown verdict lands in impostors and keeps the sum closed", () => {
  // The vocabulary is the receipt's, not the page's. A verdict the page has
  // never seen must still be counted somewhere, or the arithmetic silently
  // loses events.
  const c = huntCounters({
    above_threshold: 5,
    dispositions: { "harmonic-alias": 2, "low-significance": 1, "known-planet": 1,
                    "a-verdict-from-the-future": 1 },
  });
  assert.equal(c.impostors + c.known + c.leads + c.unresolved, c.events);
  assert.equal(c.impostors, 3);
});

test("the strip labels its two denominators apart", () => {
  assert.ok(PAGE.includes("<span>events on known planets</span>"),
    "the strip still calls an event count 'known planets re-found'");
  assert.ok(PAGE.includes('id="hunt-stars"'),
    "the distinct-star count has no line of its own");
});

/* ── The curriculum rail: a finished ladder says so ──────────────────────── */

const { curriculumFrontier } = evaluate(["curriculumStage", "curriculumFrontier"]);

test("the shipped feed has no phase left to point at", () => {
  const f = curriculumFrontier(FEED.milestones);
  assert.equal(f.complete, true,
    "M01-M18 are no longer all closed — the completed state is untested here");
  assert.equal(f.stage, 0, "a complete rail must not nominate a current phase");
});

test("the frontier line names the open milestone from the feed", () => {
  const f = curriculumFrontier(FEED.milestones);
  const open = FEED.milestones.find((m) => m.status === "open");
  assert.ok(open, "the feed carries no open milestone");
  assert.equal(f.moved_to.id, open.id);
  assert.ok(!/^M\d\d$/.test(f.moved_to.id),
    "the bench is back on the physics rail; the rail should be pointing at it");
});

test("an unfinished rail still marks exactly one phase current", () => {
  // The negative control: the old behaviour must survive for a lab whose
  // physics ladder is still climbing, or this change would strand every fork.
  const climbing = FEED.milestones.map((m) =>
    m.id === "M15" ? { ...m, status: "open" } : m);
  const f = curriculumFrontier(climbing);
  assert.equal(f.complete, false);
  assert.equal(f.stage, 4);
  const pending = curriculumFrontier(FEED.milestones.map((m) =>
    m.id === "M07" ? { ...m, status: "pending" } : m));
  assert.equal(pending.stage, 2, "a waiting rung sets the stage where it sits");
});

test("a feed with no physics rungs at all draws no rail state", () => {
  const f = curriculumFrontier(FEED.milestones.filter((m) => !/^M\d\d$/.test(m.id)));
  assert.deepEqual(f, { stage: 0, complete: false });
  assert.deepEqual(curriculumFrontier([]), { stage: 0, complete: false });
  assert.deepEqual(curriculumFrontier(null), { stage: 0, complete: false });
});

test("a complete rail with nowhere to move degrades to a sentence, not a crash", () => {
  const nothingOpen = FEED.milestones.map((m) =>
    m.status === "open" ? { ...m, status: "pending" } : m)
    .filter((m) => /^M\d\d$/.test(m.id));
  const f = curriculumFrontier(nothingOpen);
  assert.equal(f.complete, true);
  assert.equal(f.moved_to, null);
});

test("the rail carries a place to say where the frontier went", () => {
  assert.ok(PAGE.includes('id="phase-frontier"'));
  assert.ok(/aria-current/.test(PAGE), "the rail lost its step semantics entirely");
  assert.ok(!/data-curriculum-phase="4"[^\n]*aria-current/.test(PAGE),
    "phase 04 is hard-coded as the current step in the markup");
});

/* ── The conservatory: one card per track the feed can carry ─────────────── */

const SPECS = new Function(
  PAGE.slice(PAGE.indexOf("var GARDEN_SPECS = ["),
             PAGE.indexOf("];", PAGE.indexOf("var GARDEN_SPECS = [")) + 2) +
  "\nreturn GARDEN_SPECS;")();

test("every track in the feed has a card", () => {
  // The defect: GARDEN_SPECS hard-coded six tracks while the feed carried
  // seven, so P01 — a whole science — was on the record and off the shelf.
  const tracks = [...new Set(FEED.milestones.map((m) => m.track))];
  const carded = new Set(SPECS.map((s) => s.track));
  const missing = tracks.filter((t) => !carded.has(t));
  assert.deepEqual(missing, [], `no card for: ${missing.join(", ")}`);
});

test("the seventh card is the folding track, and it is not empty", () => {
  const misc = SPECS.find((s) => s.track === "misc");
  assert.ok(misc, "the misc card is gone again");
  assert.equal(misc.form, "sprout", "misc must reuse the default seedling");
  const rungs = FEED.milestones.filter((m) => m.track === "misc");
  assert.ok(rungs.length, "the misc card would stand over an empty track");
  assert.ok(rungs.every((m) => /^P\d\d$/.test(m.id)),
    "misc now holds a track that is not the folding one; the card's label lies");
});

test("the heading counts the cards instead of repeating a number", () => {
  assert.ok(PAGE.includes("countWord(GARDEN_SPECS.length) +\n" +
    "          ' instruments. One standard of proof.'"),
    "the conservatory heading is hand-written again");
  const { countWord } = new Function(
    PAGE.slice(PAGE.indexOf("var COUNT_WORDS = ["),
               PAGE.indexOf("}", PAGE.indexOf("function countWord(")) + 1) +
    "\nreturn { countWord: countWord };")();
  // ...and the no-JS fallback in the markup says the same thing the JS would.
  assert.ok(PAGE.includes('<h2 id="garden-title">' + countWord(SPECS.length) +
    " instruments. One standard of proof.</h2>"),
    "the static heading and the rendered heading disagree");
  assert.equal(countWord(99), "99", "an unnamed count must still be honest");
});

test("the sill and the conservatory draw the same row of pots", () => {
  // drawSillGarden and drawGarden both walk GARDEN_SPECS, so the static
  // sentence above the scene must count the same list. It has no JS behind it,
  // which is exactly why it needs a test.
  const { countWord } = new Function(
    PAGE.slice(PAGE.indexOf("var COUNT_WORDS = ["),
               PAGE.indexOf("}", PAGE.indexOf("function countWord(")) + 1) +
    "\nreturn { countWord: countWord };")();
  const word = countWord(SPECS.length).toLowerCase();
  assert.ok(PAGE.includes("Below: " + word + " pots on one windowsill"),
    `the so-what strip does not say "${word} pots" for ${SPECS.length} cards`);
});
