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

- [x] **Wolff single-cluster updates** (z ≈ 0.25 — essentially no critical
      slowing). Grow a cluster by adding aligned neighbours with probability
      p = 1 − exp(−2β), flip it whole. GPU-friendly as an iterative
      frontier-expansion (parallel BFS) across the batched lattices. This is the
      correct instrument for criticality and unlocks clean FSS to L ≥ 512 and
      sharp exponents for M03/M04. Keep Metropolis as the default for
      off-critical sweeps; pick the updater by regime.
      (done 2026-06-16 — `wolff.py` landed with M03 (#13): batched parallel-BFS
      frontier expansion over frozen bond fields, each undirected bond activated
      exactly once. Validated against Metropolis on ⟨|m|⟩ and energy below and
      above T_c plus Onsager sanity (`test_wolff.py`), and AT criticality via
      the M02 wiring tests (`test_fss_updater.py`). Regime/flag selection landed
      2026-07-05 (#47): `run_fss(updater='wolff'|'metropolis')`, Wolff the
      default in the critical window, Metropolis still selectable off-critical.
      The 3D generalisation `wolff3d.py` landed 2026-06-27 (#32).)
- [ ] Once Wolff lands, re-run M02 to L = 512/1024 and tighten the measured γ/ν.
      (Wolff has landed and `run_fss` defaults to it — this re-run is now the
      live next step; nothing blocks it but GPU time.)
- [ ] **Sharpen M06's 3D T_c via an L-extrapolation.** The Phase-2 M06 run lands
      the χ-peak at T_c(L=12) = 4.504 (0.17% from the MC benchmark 4.5115), but a
      single small lattice carries an O(L^−1/ν) finite-size shift in its
      pseudo-critical peak. Sweep several L (8, 10, 12, 16…) and extrapolate
      T_c(L) → T_c(∞) to turn a calibration pass into a precision number. The 3D
      checkerboard engine (`ising3d.py`) already batches over temperatures; the
      3D Wolff updater (`wolff3d.py`, #32) lets this reach L ≥ 24 without
      critical slowing.
- [ ] **Sharpen K02's r\*(N) collapse — the raw argmax doesn't resolve it.** K02
      excludes Run 01's r\* = 2/5 at every rung (≥2.5σ) and shows the collapse
      cleanly through the *fitted* interior maximum (monotone 5/5, ∝ N^−0.28,
      R² = 0.985), but the family-free **argmax** does not separate the ladder's
      two ends against its own honest floor (|Δ| = 0.069 inside a combined
      ±0.115). The floor is not statistics — it is the parameterization:
      `r(K) = √(1−K_c/K)` has infinite slope at K_c⁺, exactly where χ peaks, so a
      peak index that wanders two or three grid steps drags r\* a long way, and
      the N=500 rung's five initial conditions came back bimodal (0.05 / 0.20).
      Three levers, cheapest first: (a) more initial conditions per rung — the
      median already rejects a single excursion, and 9–15 seeds would shrink the
      index jitter directly; (b) a longer measurement window, since χ = N·Var_t(r)
      is under-sampled near K_c where the correlation time grows; (c) a wider
      lever arm in N (8000, 16000) — still CPU-scale at O(N) per step. The
      shipped run is ~21 min; (a)+(c) is a few hours, i.e. a hand-run, not a
      nightly (K02 is deliberately out of `curriculum.ROTATION` for this reason).
- [ ] **Test the χ(r) shape law in Run 01's OWN regime (noisy Kuramoto).** K02
      ran the *deterministic* engine K01 calibrated — fixed-step RK4, no
      stochastic forcing — while Run 01's `a·r²(1−r)³` fit came from a **noisy**
      system (D = 0.20) at N = 24. K02's mechanism (χ peaks at a fixed point in
      **K**, so r\* inherits the finite-size scaling of r at criticality and
      cannot be N-independent) is regime-independent, but the specific measured
      exponents are engine-specific and the refutation would be stronger if it
      also landed in the regime the form was fitted in. Adding an optional noise
      term means an Euler–Maruyama path beside the RK4 one (RK4 is not valid for
      an SDE) — a real engine change, deliberately not smuggled into K02.

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

**Open (2026-08-02):** the K (coherence) track landed without its own form — it
reuses the physics `fern`, because a coherence sweep is the same shape of climb
as a magnetism sweep and shipping a seventh plant nobody asked for is not what
K01 was for. If the track grows past K01, give it a form that reads as *many
things falling into step* (a cluster converging on one line) and add it to
`web/growth-forms.js` + the `growth_form` enum in `schema/pot.schema.json`.
Until then `publish.GROWTH_FORMS["coherence"] = "fern"` is the deliberate
placeholder, not an oversight.

- [x] Define a `growth_form` (or derive it from `track`) in the feed contract.
      (done 2026-06-23 — `publish.GROWTH_FORMS` + `growth_form_for(track)`; every
      milestone is stamped, schema enum added.)
- [x] Refactor `web/index.html`'s render into pluggable forms behind one
      interface; ship 2–3 forms; prove they're visually homogeneous side by side.
      (done 2026-06-24 — `web/growth-forms.js`: a registry where each form is
      `build(ctx) -> {stem, nodes, tip}`. Shipped **fern** (physics/default),
      **vine** (compute, a coiling climb), **succulent** (instrument, a compact
      rosette). Homogeneity is enforced by the interface — every form roots at the
      pot center and reaches the *same* tip height for a given progress; only the
      path and node layout change. Inlined into `index.html` for the single-file
      mirror, kept in sync by `tests/test_web_growth_forms.py`; behaviour proved by
      `web/growth-forms.test.mjs` (`node --test`).)

## Lineage — origination points (backlogged, not rebuilt)

The windowsill didn't appear from nowhere. Record the ancestors so the idea's
provenance stays on the books the way its data does. These are **kept as
origins**, not active work:

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
- [x] Keep `brokenbranch.dev/windowsill` in sync with `web/index.html` from a
      single source of truth.
      (done — `web/index.html` is mirrored verbatim into the
      brokenbranchdevwebsite repo, and this repo's CI gates the file with the
      same `html-validate` config the downstream site enforces, so the mirror
      can never push HTML the site rejects; see `.github/workflows/ci.yml`.)
