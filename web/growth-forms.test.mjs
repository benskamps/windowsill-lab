/*
 * Node test for the growth-form registry (web/growth-forms.js). No DOM, no test
 * framework — plain `node --test` so it runs anywhere Node 18+ exists. CI is
 * Python-only today; this is the local/agent gate that the manager runs.
 *
 *   node --test web/growth-forms.test.mjs
 *
 * Proves: every form builds valid geometry behind one interface, the three
 * shipped forms are visually DISTINCT, they're HOMOGENEOUS (same root, same tip
 * height, one node per closed milestone), and the feed's `growth_form` selects
 * the right form (with a clean fallback).
 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const GF = require("./growth-forms.js");

const CTX = { count: 6, total: 31, openProg: 0.3, base: 344, rise: 154 };
const SHIPPED = ["fern", "vine", "succulent"]; // the original 3 forms the BACKLOG asked for
// The remaining three contract forms (astronomy/boinc/misc tracks). Each used to
// alias one of the SHIPPED forms; now each has its own distinct build().
const NEW_FORMS = ["creeper", "moss", "sprout"];
const ALIAS_OF = { creeper: "vine", moss: "succulent", sprout: "fern" };
const ALL_FORMS = [...SHIPPED, ...NEW_FORMS]; // mirrors src/lab/publish.py GROWTH_FORMS

function validPath(d) {
  // an SVG path that starts with a moveto and carries finite coordinates only
  if (typeof d !== "string" || !/^M/.test(d)) return false;
  const nums = d.match(/-?\d+(\.\d+)?/g) || [];
  return nums.length >= 2 && nums.every((n) => Number.isFinite(parseFloat(n)));
}

test("every shipped form implements the one interface", () => {
  for (const name of SHIPPED) {
    const g = GF.build(name, CTX);
    assert.ok(validPath(g.stem), `${name}: stem must be a valid SVG path`);
    assert.ok(Array.isArray(g.nodes), `${name}: nodes must be an array`);
    assert.ok(g.tip && Number.isFinite(g.tip.x) && Number.isFinite(g.tip.y),
      `${name}: tip must be a finite point`);
    for (const n of g.nodes) {
      assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y), `${name}: finite node coords`);
      assert.ok(n.dir === 1 || n.dir === -1, `${name}: node.dir is a side`);
    }
  }
});

test("one node per closed milestone, for every form (homogeneity)", () => {
  for (const name of SHIPPED) {
    for (const count of [0, 1, 6, 20]) {
      const g = GF.build(name, { ...CTX, count });
      assert.equal(g.nodes.length, count, `${name}: nodes==count at count=${count}`);
    }
  }
});

test("all forms root at the pot center and reach the SAME tip height (homogeneity)", () => {
  const heights = SHIPPED.map((name) => GF.build(name, CTX).tip.y);
  const first = heights[0];
  for (let i = 1; i < heights.length; i++) {
    assert.ok(Math.abs(heights[i] - first) < 1e-6,
      `${SHIPPED[i]} tip height must match ${SHIPPED[0]} (got ${heights[i]} vs ${first})`);
  }
  // and the tip x is the shared center for all forms
  for (const name of SHIPPED) {
    assert.equal(GF.build(name, CTX).tip.x, GF.CX, `${name}: tip centered on the pot`);
  }
});

test("the three shipped forms are visually DISTINCT", () => {
  const stems = SHIPPED.map((name) => GF.build(name, CTX).stem);
  const uniq = new Set(stems);
  assert.equal(uniq.size, SHIPPED.length, "each form must draw a different stem path");

  // node layouts differ too: fern is on-axis (x≈center), succulent spreads wide
  const fernNodes = GF.build("fern", CTX).nodes;
  const succNodes = GF.build("succulent", CTX).nodes;
  const fernSpread = Math.max(...fernNodes.map((n) => Math.abs(n.x - GF.CX)));
  const succSpread = Math.max(...succNodes.map((n) => Math.abs(n.x - GF.CX)));
  assert.ok(fernSpread < 1, "fern nodes ride the central stem");
  assert.ok(succSpread > fernSpread + 5, "succulent fans its nodes out into a rosette");
});

// Signature of a form's node layout — the (x, y) of every node — so two forms
// can be compared for "different node arrangement" independent of stem path.
function nodeSig(form, ctx = CTX) {
  return JSON.stringify(GF.build(form, ctx).nodes.map((n) => [n.x, n.y]));
}

test("creeper/moss/sprout are HOMOGENEOUS: root at pot center, same tip height as fern", () => {
  const fernTip = GF.build("fern", CTX).tip;
  for (const name of NEW_FORMS) {
    const g = GF.build(name, CTX);
    assert.ok(validPath(g.stem), `${name}: stem must be a valid SVG path`);
    // roots at the pot center: the path begins with the moveto to (CX, base)
    assert.ok(g.stem.startsWith("M" + GF.CX + " "), `${name}: stem roots at the pot center x`);
    assert.equal(g.tip.x, GF.CX, `${name}: tip centered on the pot`);
    assert.ok(Math.abs(g.tip.y - fernTip.y) < 1e-6,
      `${name}: tip height must match fern (got ${g.tip.y} vs ${fernTip.y})`);
  }
});

test("creeper/moss/sprout keep one node per closed milestone, finite + sided", () => {
  for (const name of NEW_FORMS) {
    for (const count of [0, 1, 6, 20]) {
      const g = GF.build(name, { ...CTX, count });
      assert.equal(g.nodes.length, count, `${name}: nodes==count at count=${count}`);
      for (const n of g.nodes) {
        assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y), `${name}: finite node coords`);
        assert.ok(n.dir === 1 || n.dir === -1, `${name}: node.dir is a side`);
      }
    }
  }
});

test("creeper/moss/sprout are DISTINCT from the forms they used to alias", () => {
  // Each was a comment-level alias (creeper→vine, moss→succulent, sprout→fern).
  // Now each must draw a different stem AND lay its nodes out differently.
  for (const name of NEW_FORMS) {
    const alias = ALIAS_OF[name];
    assert.notEqual(GF.build(name, CTX).stem, GF.build(alias, CTX).stem,
      `${name} must not reuse ${alias}'s stem path`);
    assert.notEqual(nodeSig(name), nodeSig(alias),
      `${name} must arrange its nodes differently than ${alias}`);
  }
});

test("all six contract forms draw mutually distinct stems", () => {
  // mirrors src/lab/publish.py GROWTH_FORMS — none of the six should collide.
  const stems = ALL_FORMS.map((name) => GF.build(name, CTX).stem);
  assert.equal(new Set(stems).size, ALL_FORMS.length,
    "every one of the six growth forms must draw a unique stem");
});

test("growth_form selection: the OPEN milestone's track is the hero form", () => {
  // The open milestone wins even when another track dominates by count — this is
  // the fix for "fern always wins" (physics dominates the curriculum forever).
  const ms = [
    { id: "M01", growth_form: "fern", status: "verified" },
    { id: "M02", growth_form: "fern", status: "verified" },
    { id: "A01", growth_form: "creeper", status: "open" },
  ];
  assert.equal(GF.pageGrowthForm(ms), "creeper"); // not fern, despite the physics majority

  // The real curriculum today (physics-heavy, M12 physics open) → fern, correctly.
  const real = [
    { id: "M11", growth_form: "fern", status: "verified" },
    { id: "M12", growth_form: "fern", status: "open" },
    { id: "C01", growth_form: "vine", status: "pending" },
    { id: "A01", growth_form: "creeper", status: "pending" },
  ];
  assert.equal(GF.pageGrowthForm(real), "fern");
});

test("growth_form selection: falls back to the most common form when nothing is open", () => {
  // No open milestone and no status → the legacy mode-wins fallback still holds.
  const physics = [{ growth_form: "fern" }, { growth_form: "fern" }, { growth_form: "vine" }];
  assert.equal(GF.pageGrowthForm(physics), "fern");
  const compute = [{ growth_form: "vine" }, { growth_form: "vine" }, { growth_form: "fern" }];
  assert.equal(GF.pageGrowthForm(compute), "vine");
});

test("selection falls back cleanly on empty / unknown / absent forms", () => {
  assert.equal(GF.pageGrowthForm([]), GF.DEFAULT_FORM);
  assert.equal(GF.pageGrowthForm(null), GF.DEFAULT_FORM);
  assert.equal(GF.pageGrowthForm([{ growth_form: "tumbleweed" }]), GF.DEFAULT_FORM);
  assert.equal(GF.pageGrowthForm([{ title: "no form field" }]), GF.DEFAULT_FORM);
  // build() degrades an unknown form to the default rather than throwing
  assert.deepEqual(GF.build("tumbleweed", CTX), GF.build(GF.DEFAULT_FORM, CTX));
});

test("the full contract enum maps to a known builder (no producer/consumer drift)", () => {
  // mirrors src/lab/publish.py GROWTH_FORMS values
  for (const form of ["fern", "vine", "creeper", "succulent", "moss", "sprout"]) {
    const g = GF.build(form, CTX);
    assert.ok(validPath(g.stem), `feed form "${form}" must render`);
  }
});
