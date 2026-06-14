# Backlog

Where the windowsill is headed. Not commitments — a place to park ideas so they
don't get lost, and so the shape of the project stays legible. Roughly ordered
by how soon they matter.

## Growth forms — different plants for different experiments

Today every experiment grows the same seedling. The aim: a small **family** of
growth forms so the *kind* of science is legible at a glance — a physics
convergence sweep, a long astronomy time-series, an instrument calibration, and
a distributed-compute (BOINC-style) contribution shouldn't all look identical.

The one hard constraint: **homogeneous.** Same clay pot, same palette, same
light-follows-your-clock soul, same `pot.json` contract — only the *form* of the
green thing changes (vine, fern, succulent, moss…). A growth form is a render
strategy, not a new page. Pick the form from a milestone's `track`, keep every
other rule identical, and a wall of windowsills should still read as one garden.

- [ ] Define a `growth_form` (or derive it from `track`) in the feed contract.
- [ ] Refactor `web/index.html`'s render into pluggable forms behind one
      interface; ship 2–3 forms; prove they're visually homogeneous side by side.

## Lineage — origination points (backlogged, not rebuilt)

The windowsill didn't appear from nowhere. Record the ancestors so the idea's
provenance is as honest as its data. These are **kept as origins**, not active
work:

- [ ] **The ASCII prototype** — the original text-only seed. The origination
      point of the whole "calm, living, honest" idea. Preserve it as a documented
      starting point / `git` artifact; do not modernize it.
- [ ] **The aquarium (fish tank)** — the louder sibling that the windowsill is
      explicitly "the calmer sibling of." Same lineage, different temperament.
      Note the relationship; keep it as an origin, not a thing to fold in.

## Consolidation — one repo, two surfaces

Make a single `git pull` give you everything: the engine, the feed, and the
page. (In progress — the page now lives in [`web/`](web/).)

- [x] Bring the canonical seed-in-the-pot page into this repo (`web/index.html`).
- [ ] Keep `brokenbranch.dev/windowsill` in sync with `web/index.html` from a
      single source of truth (mechanism TBD: CI mirror / submodule / sync script).
