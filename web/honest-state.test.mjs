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

/* `core.autocrlf=true` checks index.html out with CRLF on Windows, so a
 * multi-line source assertion below would compare against "+\r\n" and fail on
 * this machine while passing on Loam. Line endings are a checkout artifact,
 * never the behaviour under test — normalise them once, here. */
const PAGE = readFileSync(new URL("./index.html", import.meta.url), "utf8")
  .replace(/\r\n/g, "\n");
const FEED = JSON.parse(readFileSync(new URL("../pot.json", import.meta.url), "utf8"));
/* The instrument panel's second feed. It stopped being optional on 2026-09-04:
 * the panel lost `hidden`, so every hardcoded value in it is now published copy
 * on a cold load and has to be checkable against the run it claims to be. */
const PHYSICS = JSON.parse(
  readFileSync(new URL("../physics-latest.json", import.meta.url), "utf8"));

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

/* ── The hero's cadence claim, and the exception it owes the reader ──── */

// The 2026-09-04 voice pass promoted "two computers, one turn every three
// hours, around the clock" out of the tail of a governance sentence and into a
// line of its own, near the top of the page. That fact was already under
// strain: windows-cuda's last turn is 2026-08-20 while linux-rocm keeps filing.
// Promoting a strained claim without promoting its exception would be the one
// honesty regression available in that rewrite — so the hero carries an element
// drawMachines() fills from turns.last_by_machine, and this is the test that
// says it may not be deleted while the claim stands.
test("the hero does not assert a cadence it cannot show", () => {
  const HERO = (() => {
    const open = PAGE.indexOf('<p class="sowhat-machines"');
    const close = PAGE.indexOf("</p>", open);
    return open === -1 || close === -1 ? "" : PAGE.slice(open, close);
  })();
  assert.notEqual(HERO, "", "the hero no longer states the machine cadence");
  assert.ok(/every three hours|three-hour schedule/.test(HERO),
    "the hero states a cadence this test can no longer find");
  assert.ok(PAGE.includes('id="sowhat-boxes"'),
    "the hero asserts a two-machine cadence with no element to render the exception");
  assert.ok(PAGE.includes("function drawMachines(state)"),
    "#sowhat-boxes is a static sentence again — nothing rewrites it from the feed");

  const last = FEED.turns.last_by_machine;
  assert.equal(Object.keys(last).length, 2,
    "the hero says two computers; the feed's turn ledger names " + Object.keys(last).length);

  // The static fallback is what a crawler and a JS-less reader see, so it may
  // not contradict the committed feed: if a box is outside eight declared
  // intervals, the shipped sentence has to say a box is quiet.
  const iv = FEED.turns.expected_interval_h;
  const stale = Object.entries(last).filter(([, at]) =>
    iv && (Date.now() - new Date(at).getTime()) / 3600000 > 8 * iv);
  const fallback = (PAGE.match(/id="sowhat-boxes">([^<]*)</) || [, ""])[1];
  if (stale.length) {
    assert.ok(/quiet since|has not taken a turn/.test(fallback),
      `${stale.map(([n]) => n).join(", ")} is outside the declared cadence, and the ` +
      `no-JS fallback still reads: "${fallback}"`);
  }
});

/* ── The zero is a result, not a centrepiece ─────────────────────── */

// Ben's ruling, 2026-09-04: "no more apologies for 0s." A zero that is a real
// result is stated plainly, once, at the size of the numbers beside it. The
// value itself is untouched and unraisable; only its billing changed.
test("planets discovered is stated once, at the scale of its neighbours", () => {
  assert.ok(PAGE.includes('<li class="hunt-zero"><b id="hunt-planets">0</b>'),
    "the zero left the strip");
  assert.equal(FEED.hunt.planets_discovered, 0);
  const zeroRule = PAGE.split(".hunt-zero b {")[1].split("}")[0];
  assert.ok(!/font-size/.test(zeroRule),
    "the zero is being sized apart from the counters beside it again");
  assert.ok(!/a zero kept on purpose/.test(PAGE),
    "the page is applauding an absence again");
  // ...and the caveat that gives the zero its meaning survives word for word.
  assert.ok(PAGE.includes("independent follow-up say so"),
    "the zero lost the rule that makes it mean anything");
});

/* ── The instrument panel may not out-claim its own resolution ───────── */

// The 2026-09-04 voice pass rewrote the chi caption from a hedge ("on a sheet
// this size the peak is expected to land a little above it") into three
// hardcoded numbers: "steps in 0.1 and peaks at 2.30 — one grid step up, which
// is where a finite 128×128 sheet is supposed to put it." Two things were wrong
// with that. It sat beside a feed-driven #ip-chi-peak, so a new grid or lattice
// would leave prose contradicting the curve above it — and in the guard-failed
// state, where #ip-h2-peak withdraws the number entirely ("no qualified peak"),
// the caption went on naming 2.30 anyway. The numbers are wired now; this test
// says they may not be typed back in.
test("the chi caption reads its numbers from the run, not from memory", () => {
  const CAP = (() => {
    const open = PAGE.indexOf('<figure class="plot-fig" id="plot-chi"');
    const close = PAGE.indexOf("</figure>", open);
    return open === -1 || close === -1 ? "" : PAGE.slice(open, close);
  })();
  assert.notEqual(CAP, "", "the chi figure lost its id");
  for (const id of ["ip-chi-peak", "ip-chi-exact", "ip-chi-step", "ip-chi-l"]) {
    assert.ok(CAP.includes(`id="${id}"`),
      `the chi caption no longer carries #${id} — a number went back to being typed`);
    assert.ok(PAGE.includes(`setText('${id}'`) || PAGE.includes(`setHTML('${id}'`),
      `#${id} is in the caption but nothing writes it from the feed`);
  }
  // Prose outside those wired elements must carry no bare decimal: that is how
  // a stale 2.30 gets back in beside a peak the guard has withdrawn. Strip the
  // wired elements WITH their fallback contents first -- those are placeholders
  // the feed overwrites, not claims.
  const prose = CAP
    .replace(/<(?:b|span) id="ip-chi-[^"]*"[^>]*>[^<]*<\/(?:b|span)>/g, " ")
    .replace(/<[^>]*>/g, " ");
  const stray = prose.match(/\b\d+\.\d+\b/g) || [];
  assert.deepEqual(stray, [],
    `the chi caption states ${stray.join(", ")} in prose instead of reading it from the run`);
});

// The peak of C(T) and the peak of chi(T) do NOT coincide on a finite lattice —
// they carry different finite-size shifts. The pre-rewrite caption said "has to
// peak near"; the rewrite promoted that hedge to "has to peak at the same
// temperature", which is both false and a direct contradiction of the chi
// caption two figures up, whose whole subject is that peaks move.
test("no figure claims two measurements peak at the same temperature", () => {
  assert.ok(PAGE.includes('id="plot-heat"'), "the specific-heat figure moved");
  // One line, whitespace-folded: an earlier version of this test sliced the
  // plot block and stopped short of the heat figcaption, so it passed on the
  // exact sentence it was written to catch.
  const flat = PAGE.replace(/\s+/g, " ");
  const claim = flat.match(/peaks? at the same temperature/);
  assert.equal(claim, null,
    "a caption claims two different measurements peak AT the same temperature; " +
    "on a finite lattice the chi and C peaks carry different finite-size shifts, " +
    "and the chi caption two figures up exists to say peaks move");
});

/* ── The cadence claim outside the hero ───────────────────────── */

// Every place the page states the interval — the hero included — may claim only
// the SCHEDULE the feed declares (turns.expected_interval_h), never a delivered
// rate. Three hours between turns is eight a day. The feed last carried eight in
// a day on 2026-08-13, with both boxes running; since windows-cuda went quiet on
// 2026-08-20 it has carried about four, with whole days at zero. Naming the quiet
// box (drawMachines) explains the shortfall — it does not license asserting the
// rate anyway, so the wording stays on the schedule everywhere.
test("no line on the page asserts a delivered cadence", () => {
  // "one/a turn every three hours" asserts a rate; "on a three-hour schedule"
  // and "a turn scheduled every three hours" assert the schedule.
  const asserted = PAGE.match(/\b(?:a|one) turn every (?:two|three|four|six) hours/g) || [];
  assert.deepEqual(asserted, [],
    `"${asserted.join('; ')}" states a delivered rate; the feed declares a schedule ` +
    `and delivers about half of it while one box is quiet`);
  assert.equal(FEED.turns.expected_interval_h, 3,
    "the page says three hours; the feed declares " + FEED.turns.expected_interval_h);

  // And the arithmetic that makes the distinction load-bearing: if the feed ever
  // does deliver its declared rate again, this test is the place to relax.
  const perDay = {};
  for (const r of FEED.reports || []) {
    const day = String(r.at || r.date || "").slice(0, 10);
    if (!day) continue;
    perDay[day] = (perDay[day] || 0) + (r.group_count >= 2 ? r.group_count : 1);
  }
  const recent = Object.keys(perDay).sort().slice(-7);
  const delivered = recent.reduce((a, d) => a + perDay[d], 0) / (recent.length || 1);
  const scheduled = 24 / FEED.turns.expected_interval_h;
  assert.ok(delivered < scheduled,
    `the feed now delivers ${delivered.toFixed(1)} turns a day against a scheduled ` +
    `${scheduled} — the schedule/rate hedge above may be relaxed to a plain rate`);
});

/* ── The panel is no longer `hidden`, so its fallbacks are published copy ── */

// Until 2026-09-04 the instrument panel carried `hidden` and painted only after
// physics-latest.json landed, so its hardcoded values were never read by anyone.
// The voice pass un-hid it — correctly, it is the page's argument — and in doing
// so promoted every one of those placeholders to first-screen copy that a no-JS
// reader, a crawler and a failed fetch all see as a stated measurement. They are
// only honest while they are the last published run; nothing else checks that.
test("the panel's no-feed fallbacks are the committed run, not a memory of one", () => {
  const M01 = PHYSICS.m01;
  const shown = (id) => {
    const m = PAGE.match(new RegExp(`id="${id}"[^>]*>([^<]*)<`));
    assert.ok(m, `#${id} left the page — the panel lost a wired number`);
    // The page writes × as a literal in one fallback and as &times; in another;
    // render() writes the literal everywhere. Entities are an encoding, not a
    // claim, so normalise the handful this panel actually uses.
    return m[1]
      .replace(/&times;/g, "×").replace(/&minus;/g, "−")
      .replace(/&nbsp;/g, " ").replace(/&asymp;/g, "≈")
      .replace(/\s+/g, " ").trim();
  };

  assert.equal(shown("ip-h2-exact"), PHYSICS.onsager_tc.toFixed(3),
    "the headline's exact T_c disagrees with the feed's onsager_tc");
  assert.equal(shown("ip-chi-exact"), PHYSICS.onsager_tc.toFixed(3),
    "the chi caption's exact T_c disagrees with the feed's onsager_tc");

  // The measured peak. Only assert it when the run's own guard qualified the
  // whole sweep; a degraded run is render()'s problem, not the fallback's.
  if (M01.quality_status === "ok" && (M01.excluded_indices || []).length === 0) {
    assert.equal(shown("ip-h2-peak"), M01.chi_peak_t.toFixed(2),
      "the headline states a measured peak the committed run did not produce");
  }

  const spec = [
    `${M01.config.L}×${M01.config.L} magnets`,
    `${M01.T.length} temperatures from ${M01.T[0]} to ${M01.T[M01.T.length - 1]}`,
    `${M01.wall_seconds.toFixed(1)} seconds on a consumer GPU`,
  ].join(", ");
  assert.equal(shown("ip-h2-spec"), spec,
    "the panel's spec line no longer describes the committed run");

  assert.equal(shown("ip-chi-l"), `${M01.config.L}×${M01.config.L}`);
  assert.equal(shown("ip-chi-step"),
    String(Math.round((M01.T[1] - M01.T[0]) * 1000) / 1000),
    "the chi caption states a grid step the committed sweep does not use");
  assert.equal(shown("ip-mag-err"),
    Math.max(...M01.abs_mag_err.map(Number)).toFixed(3),
    "the magnetization caption states an uncertainty the committed run does not carry");

  // And the reader has to be told which state they are in: `hidden` used to say
  // "no data, no claim"; data-state="waiting" is what says it now.
  assert.ok(/id="instrument-panel"[^>]*data-state="waiting"/.test(PAGE),
    "the panel ships un-hidden with no waiting state — a cold load reads its " +
    "fallback numbers as a live measurement");
  assert.ok(/\[data-state="waiting"\][^{]*#instrument-panel-title::after/.test(PAGE),
    "the waiting state no longer marks the headline, which is where the " +
    "measured number is");
  assert.ok(PAGE.includes('panel.removeAttribute(\'data-state\')'),
    "nothing clears the waiting state when the panel actually paints");
});
