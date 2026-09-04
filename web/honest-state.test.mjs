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

/* ── Two run totals, both true, defined where they are printed ───────────── */

const { runsOnRecord } = evaluate(["runsOnRecord"]);

test("the archive's total expands every collapsed streak", () => {
  const rows = FEED.reports || [];
  assert.ok(rows.length, "the committed feed carries no run ledger");
  const collapsed = rows.filter((r) => r.group_count >= 2);
  assert.ok(collapsed.length, "no streak is collapsed; this total cannot drift here");
  assert.ok(runsOnRecord(rows) > rows.length,
    "the total is counting rows, which undercounts the record");
  assert.equal(runsOnRecord([]), 0);
  assert.equal(runsOnRecord(null), 0);
  assert.equal(runsOnRecord([{}, { group_count: 1 }, { group_count: 4 }]), 6);
});

test("turns are a subset of runs, and the page says which is which", () => {
  // Two numbers a page apart, 192 against 195, with no definition on either.
  // They count different things: a run is a report the lab kept, a turn is a
  // scheduled pass that filed a receipt, and every turn leaves a run behind.
  const runs = runsOnRecord(FEED.reports);
  const turns = FEED.turns && FEED.turns.count;
  assert.equal(typeof turns, "number");
  assert.ok(turns <= runs, `${turns} turns against ${runs} runs on record`);
  assert.ok(PAGE.includes("'every run · ' + totalRuns + ' runs on record'"),
    "the archive summary no longer names what it counts");
  assert.ok(PAGE.includes("On record counts runs: every report the lab kept."),
    "the two totals are published with no definition between them");
  assert.ok(PAGE.includes("one turn = one scheduled pass that filed a receipt"),
    "the turns counter no longer defines a turn");
});

test("NEGATIVE: the two totals are genuinely different numbers", () => {
  // If they ever coincide, the test above passes for free and the reconciling
  // sentence is describing a distinction the feed no longer shows.
  assert.notEqual(FEED.turns.count, runsOnRecord(FEED.reports),
    "turns and runs now agree; the page's reconciliation may be stale");
});

/* ── The standing commitment: published, and now visible ─────────────────── */

const { commitmentLines } = evaluate(["commitmentLines"]);

test("the block states the feed's goal in the feed's own words", () => {
  const lines = commitmentLines(FEED.goal, FEED.objections);
  assert.equal(lines.statement, FEED.goal.statement,
    "the page paraphrases the goal instead of quoting it");
});

test("the clock, the attempt and the open doubts all reach the page", () => {
  const lines = commitmentLines(FEED.goal, FEED.objections);
  const said = lines.state.join(" · ");

  // The clock has THREE phrasings, not one: commitmentLines() emits "due today"
  // at zero and "N days past the deadline" below it. A regex built as
  // `${days_remaining} days left` is therefore a dated landmine — it goes red
  // on 2026-09-24 and stays red, on a day nobody is looking at this file, for a
  // reason that has nothing to do with the lab being wrong. Assert the shape
  // instead, and that whichever branch fired carries the feed's own number.
  assert.match(said,
    /(^|· )(\d+ days? left|due today|\d+ days? past the deadline)( ·|$)/,
    `the goal's clock did not reach the page: ${said}`);
  const d = Math.round(FEED.goal.days_remaining);
  if (d !== 0) {
    assert.ok(said.includes(String(Math.abs(d))),
      `the clock line does not carry the feed's own ${d}`);
  }

  // CONSISTENCY, not a snapshot. The line this replaced hard-asserted
  // `a_field_unknown_attempted === false`: simultaneously the only assertion
  // anywhere that the goal's boolean is real, and a test that would go red the
  // day a genuine attempt landed — that is, on the one morning the lab most
  // needs its tests to be about the lab. What must hold in BOTH worlds is that
  // the flag, the list it summarises and the sentence on the page agree.
  const attempted = Array.isArray(FEED.goal.attempted) ? FEED.goal.attempted : [];
  assert.equal(FEED.goal.conditions.a_field_unknown_attempted, attempted.length > 0,
    "the goal's flag and its own attempted list disagree: " +
    `${FEED.goal.conditions.a_field_unknown_attempted} against ` +
    `${attempted.length} entr${attempted.length === 1 ? "y" : "ies"}`);
  assert.match(said, attempted.length ? /a field unknown has been attempted/
                                      : /no field unknown attempted yet/);

  // And the flag has to stand on receipts the feed NAMES. Since 2026-09-03
  // `attempted` is joined out of reports/receipts/ rather than found by a
  // substring search in UNKNOWNS.md, so an attempt with nothing a reader can
  // open is the grader having been talked into it a second time.
  // (`attempt_receipts` arrives with the next publish; while the feed claims no
  // attempt this binds vacuously, which is the honest state of that feed.)
  if (attempted.length) {
    assert.ok(Array.isArray(FEED.goal.attempt_receipts)
      && FEED.goal.attempt_receipts.length > 0,
      "the feed claims an attempt but names no receipt a reader could check");
  }

  assert.match(said, new RegExp(
    `\\b${FEED.objections.open} of ${FEED.objections.total} objections still open\\b`));
});

test("an attempted goal says so, and a passed deadline is not hidden", () => {
  const done = commitmentLines(
    { statement: "s", days_remaining: -3, conditions: { a_field_unknown_attempted: true } },
    { open: 1, total: 1 });
  assert.deepEqual(done.state,
    ["3 days past the deadline", "a field unknown has been attempted",
     "1 of 1 objection still open"]);
  assert.deepEqual(commitmentLines({ days_remaining: 0 }, null).state, ["due today"]);
  assert.deepEqual(commitmentLines({ days_remaining: 1 }, null).state, ["1 day left"]);
});

test("the attempt falls back to the attempted list when no condition is set", () => {
  assert.deepEqual(commitmentLines({ attempted: [] }, null).state,
    ["no field unknown attempted yet"]);
  assert.deepEqual(commitmentLines({ attempted: ["U-K01"] }, null).state,
    ["a field unknown has been attempted"]);
});

test("a feed without these fields renders nothing at all", () => {
  for (const empty of [[null, null], [undefined, undefined], [{}, {}]]) {
    const lines = commitmentLines(empty[0], empty[1]);
    assert.equal(lines.statement, null);
    assert.deepEqual(lines.state, []);
  }
  assert.ok(PAGE.includes('<section class="commitment" id="commitment" hidden'),
    "the block must start hidden, so an older feed shows nothing");
});

/* ── The shelf hero: a door that does not oversell the rooms ─────────────── */

// The shelf's counters are the lab's CLOSED LEDGER (verified + review + null),
// which is not the shelf page's room count: on 2026-09-02 that was 27 captured
// runs, 24 with rooms, against 28 closed milestones. The block's own comment
// has said so since the room audit — but the comment sat directly above a
// kicker reading "every run, a room of its own", which is the exact universal
// the audit removed from the sentence below it. A comment cannot hold a claim
// down; this test can.
const SHELF_HERO = (() => {
  const open = PAGE.indexOf('<a class="shelf-hero"');
  const close = PAGE.indexOf("</a>", open);
  return open === -1 || close === -1 ? "" : PAGE.slice(open, close);
})();

test("the shelf hero promises a room for most runs, never for every one", () => {
  assert.notEqual(SHELF_HERO, "", "the page no longer has a .shelf-hero block");
  const universal = SHELF_HERO.match(/\bevery (?:run|one|experiment)\b/i);
  assert.equal(universal, null,
    `the shelf hero claims a room for ${universal && universal[0]} — the shelf page's own total is lower`);
  assert.ok(/\bmost\b/.test(SHELF_HERO),
    "the shelf hero no longer hedges its room count at all");
});

test("the shelf counters are the closed ledger, and say so in that order", () => {
  const closed = FEED.milestones.filter((m) => ["verified", "review", "null"].includes(m.status));
  const byStatus = (s) => FEED.milestones.filter((m) => m.status === s).length;
  const shown = (id) => {
    const m = SHELF_HERO.match(new RegExp(`id="${id}"[^>]*>(\\d+)<`));
    return m ? Number(m[1]) : null;
  };
  assert.equal(shown("shelf-total"), closed.length,
    "the shelf total is not the count of closed milestones in the feed");
  assert.equal(shown("shelf-moss-count"), byStatus("verified"));
  assert.equal(shown("shelf-amber-count"), byStatus("review"));
  assert.equal(shown("shelf-clay-count"), byStatus("null"));
  assert.equal(shown("shelf-moss-count") + shown("shelf-amber-count") + shown("shelf-clay-count"),
    shown("shelf-total"), "the three dot counters do not sum to the shelf total");
});
