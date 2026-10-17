/*
 * Node test for the bench model in the measurement panel (web/hotplate.js,
 * drawn with the vendored web/iso-kit.js). No DOM — plain `node --test`, the
 * lane the other web suites run in.
 *
 *   node --test web/hotplate.test.mjs
 *
 * WHAT THIS FILE GUARDS. The hot plate is the one picture on the page that runs
 * in the visitor's browser instead of being read off a receipt, which makes it
 * the easiest place to slip a claim in sideways. So: the two things it takes
 * from the feeds (the end grain, the starting tray) must be the feeds' own and
 * nothing else; with no feed it must draw nothing it cannot back; its "exact"
 * readout must be the textbook value; and the page must ship the same code
 * these tests run, because the mirror copies only index.html.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const K = require("./iso-kit.js");
const H = require("./hotplate.js");

const read = (rel) => readFileSync(new URL(rel, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const PAGE = read("./index.html");
const FEED = JSON.parse(read("../pot.json"));
const PHYSICS = JSON.parse(read("../physics-latest.json"));

/* ── One file, two copies: the page ships what these tests run ───────────── */

function inlined(name) {
  const begin = `<!-- BEGIN ${name} (inlined; source of truth: web/${name}) -->`;
  const end = `<!-- END ${name} (inlined) -->`;
  assert.ok(PAGE.includes(begin), `${name} BEGIN marker missing from index.html`);
  assert.ok(PAGE.includes(end), `${name} END marker missing from index.html`);
  const inner = PAGE.split(begin)[1].split(end)[0];
  return inner.slice(inner.indexOf("<script>") + "<script>".length, inner.lastIndexOf("</script>")).trim();
}

for (const name of ["iso-kit.js", "hotplate.js"]) {
  test(`the page's inlined ${name} is web/${name}, byte for byte`, () => {
    assert.equal(inlined(name), read(`./${name}`).trim(),
      `index.html's inlined ${name} has drifted from web/${name}; edit the file, then re-sync the block`);
  });
}

test("the vendored kit keeps its licence and says what changed", () => {
  const kit = read("./iso-kit.js");
  assert.ok(kit.includes("Copyright (c) 2026 Ryan"), "the MIT copyright line left the vendored kit");
  assert.ok(kit.includes("Permission is hereby granted, free of charge"), "the MIT permission notice left the vendored kit");
  assert.ok(/github\.com\/wheresryan22\/anatomy/.test(kit), "the vendored kit no longer names its upstream");
});

/* ── The end grain is the report ledger, one ring per day ────────────────── */

// The hero's ring section and the hot plate's base draw the same ledger. If one
// ever counts days differently from the other, the page shows two histories.
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

test("the end grain and the hero's ring section count the same days", () => {
  const ledgerDays = new Function(lift("ledgerDays") + "\nreturn ledgerDays;")();
  const hero = ledgerDays(FEED.reports);
  const grain = H.ringDays(FEED.reports);
  assert.ok(grain.length > 1, "the committed feed carries no report days to grow rings from");
  assert.deepEqual(grain.map((d) => d.date), hero.map((d) => d.date));
  assert.deepEqual(grain.map((d) => d.n), hero.map((d) => d.n));
});

test("every ring is one report day, and a malformed date grows nothing", () => {
  const days = H.ringDays([
    { date: "2026-10-01" }, { date: "2026-10-01" }, { date: "2026-10-03" },
    { date: "yesterday" }, { date: 20261002 }, null, {},
  ]);
  assert.deepEqual(days, [{ date: "2026-10-01", n: 2 }, { date: "2026-10-03", n: 1 }]);
  assert.deepEqual(H.ringDays(undefined), []);
});

test("rings never cross: radii climb strictly and the newest lands on the rim", () => {
  const days = H.ringDays(FEED.reports);
  const radii = H.ringRadii(days, 18, 172);
  assert.equal(radii.length, days.length);
  radii.forEach((r, i) => assert.ok(i === 0 ? r > 18 : r > radii[i - 1], `ring ${i} does not sit outside ring ${i - 1}`));
  assert.ok(Math.abs(radii[radii.length - 1] - 172) < 1e-9, "the newest ring is not at the rim the figure clips to");
});

test("a busier day grows a wider ring, up to the cap", () => {
  const r = H.ringRadii([{ n: 1 }, { n: 4 }, { n: 8 }, { n: 40 }], 0, 100);
  const w = r.map((x, i) => x - (i ? r[i - 1] : 0));
  assert.ok(w[0] < w[1] && w[1] < w[2], "ring width no longer follows how busy the day was");
  assert.ok(Math.abs(w[2] - w[3]) < 1e-9, "one flood of reports is no longer capped");
});

test("the figure draws exactly one ring per report day", () => {
  const days = H.ringDays(FEED.reports);
  const { svg } = H.build(K, { days });
  const grain = svg.split('<g data-part="grain">')[1].split("</g>")[0];
  assert.equal((grain.match(/<path /g) || []).length, days.length);
  assert.equal((grain.match(/grain-newest/g) || []).length, 1, "the newest ring is not singled out exactly once");
});

test("NEGATIVE: with no feed the wood is bare, not a made-up history", () => {
  const { svg } = H.build(K, {});
  const grain = svg.split('<g data-part="grain">')[1].split("</g>")[0];
  assert.equal(grain, "", "the hot plate drew rings without a report ledger");
});

/* ── The tray starts from the run's own frame ───────────────────────────── */

test("the starting tray is a sample of the committed frame, site for site", () => {
  const m = PHYSICS.m01;
  const key = Object.keys(m.snapshots).sort((a, b) => Math.abs(a - H.TC) - Math.abs(b - H.TC))[0];
  const s = H.trayFromSnapshot(m.snapshots[key], m.snapshot_L);
  assert.ok(s, "the committed frame did not decode");
  assert.equal(s.length, H.N * H.N);
  const raw = Buffer.from(m.snapshots[key], "base64");
  const stride = Math.floor(m.snapshot_L / H.N);
  for (let j = 0; j < H.N; j++) for (let i = 0; i < H.N; i++) {
    const idx = j * stride * m.snapshot_L + i * stride;
    const bit = (raw[idx >> 3] >> (7 - (idx & 7))) & 1;
    assert.equal(s[j * H.N + i], bit ? 1 : -1, `tile ${i},${j} is not the frame's magnet`);
  }
});

test("the page hands the bench model the panel's own middle frame", () => {
  assert.ok(PAGE.includes("window.hotplateStart(m.snapshots['' + crit], m.snapshot_L, crit)"),
    "the hot plate no longer starts from the frame the triptych calls nearest to T_c");
  assert.ok(PAGE.includes("window.hotplateReports(state.empty ? [] : state.reports)"),
    "the hot plate no longer grows its rings from the feed the pot render read");
});

test("NEGATIVE: anything that is not a frame starts nothing", () => {
  assert.equal(H.trayFromSnapshot(undefined, 128), null);
  assert.equal(H.trayFromSnapshot("AAAA", 128), null, "a frame too short for its own size decoded");
  assert.equal(H.trayFromSnapshot("not base64 !!", 128), null);
  assert.equal(H.trayFromSnapshot(PHYSICS.m01.snapshots["2.3"], 8), null, "a frame smaller than the tray decoded");
});

/* ── The readout's "exact" is the textbook value ────────────────────────── */

test("the knob's mark is Onsager's T_c, the same number the panel publishes", () => {
  assert.equal(H.TC.toFixed(3), PHYSICS.onsager_tc.toFixed(3));
  assert.ok(Math.abs(H.TC - 2 / Math.log(1 + Math.SQRT2)) < 1e-12);
});

test("exact |m| is Yang's 1952 formula, and zero from the tipping point up", () => {
  const yang = (T) => Math.pow(1 - Math.pow(Math.sinh(2 / T), -4), 1 / 8);
  for (const T of [1.0, 1.5, 2.0, 2.2, 2.26]) assert.ok(Math.abs(H.exactM(T) - yang(T)) < 1e-12, `exact |m| is wrong at T=${T}`);
  assert.equal(H.exactM(H.TC), 0);
  assert.equal(H.exactM(2.5), 0);
  assert.equal(H.exactM(3.5), 0);
  let prev = 1;
  for (let T = 1.5; T < H.TC; T += 0.01) {
    assert.ok(H.exactM(T) <= prev, `exact |m| rises with temperature at T=${T.toFixed(2)}`);
    prev = H.exactM(T);
  }
});

/* ── The caption claims only what the bench model can show ──────────────── */

test("the caption says it is not a receipt, and quotes no measured number", () => {
  const open = PAGE.indexOf('<figure class="hotplate iso" id="hotplate">');
  const close = PAGE.indexOf("</figure>", open);
  assert.ok(open !== -1 && close !== -1, "the bench model left the page");
  const fig = PAGE.slice(open, close).replace(/\s+/g, " ");
  assert.ok(/rather than read from a receipt/.test(fig), "the bench model no longer says it is not a receipt");
  // The run's measured peak and wall clock live in wired spans in the panel;
  // a copy typed into this caption would go stale against the next run.
  assert.ok(!fig.includes(PHYSICS.m01.chi_peak_t.toFixed(2)), "the caption types in the run's measured peak");
  assert.ok(!fig.includes(String(PHYSICS.m01.config.L) + " ×"), "the caption types in the run's lattice size");
});
