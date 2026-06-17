# Backlog

Where the windowsill is headed. Not commitments — a place to park ideas so they
don't get lost, and so the shape of the project stays legible. Roughly ordered
by how soon they matter.

## Instrument — a cluster algorithm (the next big unlock)

M02 (finite-size scaling) landed cleanly over L = 32–256 but **stops there**: the
single-spin Metropolis updater suffers critical slowing down (dynamic exponent
z ≈ 2.17), so the largest lattices can't develop their full critical fluctuation
spectrum in a tractable number of sweeps — χ_max gets under-measured and the
slope sags. This caps every critical-point milestone (M02 finite-size scaling,
M03 β/ν, M04 specific heat, and the spin-glass runs M11+) at modest L.

- [ ] **Wolff single-cluster updates** (z ≈ 0.25 — essentially no critical
      slowing). Grow a cluster by adding aligned neighbours with probability
      p = 1 − exp(−2β), flip it whole. GPU-friendly as an iterative
      frontier-expansion (parallel BFS) across the batched lattices. This is the
      correct instrument for criticality and unlocks clean FSS to L ≥ 512 and
      sharp exponents for M03/M04. Keep Metropolis as the default for
      off-critical sweeps; pick the updater by regime.
- [ ] Once Wolff lands, re-run M02 to L = 512/1024 and tighten the measured γ/ν.
- [ ] **Sharpen M06's 3D T_c via an L-extrapolation.** The Phase-2 M06 run lands
      the χ-peak at T_c(L=12) = 4.504 (0.17% from the MC benchmark 4.5115), but a
      single small lattice carries an O(L^−1/ν) finite-size shift in its
      pseudo-critical peak. Sweep several L (8, 10, 12, 16…) and extrapolate
      T_c(L) → T_c(∞) to turn a calibration pass into a precision number. The 3D
      checkerboard engine (`ising3d.py`) already batches over temperatures; a 3D
      Wolff updater (once the 2D one is generalized) would let this reach L ≥ 24
      without critical slowing.

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
