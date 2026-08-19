# Backlog

Where the windowsill is headed. Not commitments — a place to park ideas so they
don't get lost, and so the shape of the project stays legible. Roughly ordered
by how soon they matter.

## ⭐ North star — the frontier gate (declared 2026-08-02, Ben)

**The windowsill is "frontier" on the day one of its numbers survives BOTH its
own check gate AND a literature search that comes back empty.** Everything below
this line serves that crossing. Honest ladder position as of the declaration:
rung 0–1 (reproduce known physics) done across five tracks; rung 1.5 (falsify
your own conjecture with receipts) crossed 2026-08-02 by K02; rung 2 (a
certified-novel number) not attempted. The wall is not compute — it is
**certifying novelty**, and physics has no OEIS: the literature search IS the
gate, so it must be built with the same rigor as `checks.py`.

Goals, nearest first:

1. **K02 literature cross-check** — grade the measured r*-collapse (∝ N^−0.28)
   against published Kuramoto finite-size scaling (Hong–Chaté–Tang–Park 2015,
   Daido 1990, successors). Expected outcome: rediscovery (an honest label, and
   the first live test of the novelty-certification muscle). Small chance the
   estimator-specific exponent is unpublished — then this IS the crossing.
   Downstream either way: the /fireflies/ page's "peaks at r = 0.4" sentence
   gets the finite-size reframe.
2. **K03 — the Run 02 fork questions** (does a coverage-optimizing schedule beat
   ALOHA; does the desync end have its own optimal τ). Best odds in the estate:
   the framing is ours, the quantities plausibly sit behind soft walls nobody
   tabulated. Source: coherence-lab Run 02 report (RUN02-TAU.md).
3. **A novelty-certification protocol for physics** — the Erdős Check discipline
   transposed: pinned sources, adversarial search for prior art, a verdict
   vocabulary (rediscovered / extends / unpublished), and a receipt. Without
   this, no rung-2 claim is trustworthy; with it, the *method* is publishable
   even when every number turns out known.
4. **M12 valid rerun** (parity fix landed, GPU capped 240 W) — then spin-glass
   territory only via niche observables; the exponent-precision race belongs to
   Janus-class hardware and we do not pretend otherwise.

Supporting invariant: the bench stays trustworthy — armed rotation on both
boxes, receipts immutable (#83), one turn per box (#84), and every claim graded
by a check before it is spoken.

## From outside — the 2026-08-19 external review (worked, same day)

Grok read the public surface cold (no repo, no receipts) and returned six
criticisms; four were already on this page. The two that landed were worked the
same day, and every item it proposed was routed through the novelty-certification
protocol before any of it was built up into a claim. Digest:
`docs/investigations/2026-08-19-external-review-grok.md`.

**Shipped 2026-08-19** (all REDISCOVERED — standard practice adopted, prior art
pinned in `docs/assays/2026-08-19-fold-gates-and-tempering-prior-art.md`):

- [x] **Four sky-track gates.** Doubled-period fold (`lab.a05_fold.p2_fold`),
      duration-matched depths, CTOI catalog crosscheck (`lab.exofop`), and a
      companion-radius admissibility gate (`lab.a05_physical`) — the cheapest
      question in the ladder and the one nobody was asking. Plus multi-sector
      evidence combination, which turned out to be the largest of the four seams.
      Validation, with two false-positive mechanisms found by negative controls
      on planted planets: `docs/investigations/2026-08-19-fold-gate-validation.md`.
- [x] **Parallel tempering** (`lab.tempering`, `spin_glass.swap_every`). Lifts
      M11's documented equilibration floor from T ≈ 0.6 to at least 0.30 at the
      same wall-clock (75.7 s vs 78.3 s), with a 4x-sweeps control that fails as
      the module's own docstring predicted.
      `docs/investigations/2026-08-19-parallel-tempering-lifts-the-floor.md`.
- [x] **Audit the auditor** (`lab.mutation`). Corrupts every number in a report a
      check passes and asks whether the verdict moves. Found 31 fields across
      M03/M07/M14 that were **graded when present and ignored when absent** — a
      report that lost a field in serialisation kept its leaf. Fixed; the
      property is now a test over every check with a passing report on disk.

**Open, ranked:**

1. **Grade the star, not the sector — the top sky-track item.** TIC 287328866
   reads the doubled-fold difference below 5 sigma in six of its eight sectors
   and 9.4 sigma combined. Every gate in the ladder currently sees one sector at
   a time, so a star observed eight times gets eight weak looks instead of one
   strong one. `combine_p2_folds` is the first instance; the general version —
   carry a star's per-sector evidence forward and grade the star — is a pipeline
   change, not a gate.
2. **The shelf-exit rule.** `docs/shelf-exit-contract.md` is written and its
   mechanism is built; §4 thresholds and §6 destination (ExoFOP as CTOIs) need
   Ben's ruling. Until then the machine can refute a lead but nothing can promote
   one, which is the state the outside read correctly called "a way of never
   shipping".
3. **Limb-darkened depths instead of box depths.** The admissibility gate
   reproduces WASP-18 b's radius 7 % high, and the box-fit mean depth is why. A
   real upgrade (fit a transit model), not a coefficient — and it improves every
   depth the pipeline reports, not just this gate.
4. **Houdayer isoenergetic cluster moves** — the next sampler rung past plain
   tempering for +-J glasses, named and implemented by `peapods`
   (arXiv 2602.19045). Read Wang-Machta-Katzgraber (Phys. Rev. E 92, 013303)
   BEFORE spending a sprint on population annealing: they compare it against
   parallel tempering directly, so that answer can be read rather than measured.
5. **Reproduce a published Hurst measurement** — the free win from the assay
   below. de Freitas et al. 2019 (MNRAS 488, 3274) publish the global Hurst
   exponent for 662 named Kepler stars. Pull the same stars, compute H, compare:
   an external benchmark on real data for a sky-track instrument, needing no
   unpublished idea to be worth doing.
6. **Close the assay pinning gap.** Both 2026-08-19 assays pin citations at
   abstract level, not equation level, which PROTOCOL section 7 requires. Four
   papers to read.

**Retired by the assay, not by a build:** the "non-equilibrium diagnostics on
stellar residuals" greenfield. The umbrella claim is REFUTED (a 662-star Kepler
multifractal study), the diagnostic advertised as most novel — KPZ roughness — is
a **renaming** of the Hurst exponent for a 1-D signal, and the two genuinely
unpublished diagnostics need an observable photometry does not deliver. Full
verdicts: `docs/assays/2026-08-19-noneq-diagnostics-stellar-photometry.md`. The
general lesson belongs in PROTOCOL section 3: *"diagnostic X from field A has
never been applied to field B" deserves the question "is X a renaming of
something B already does?" before it deserves a backlog slot.*

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
      excludes Run 01's r\* = 2/5 at every rung (≥2.5σ), and the *collapse itself*
      is now established the right way — by the direct r(K_c,N) calibration,
      N^−0.401(17) against the published 0.39(2). But the family-free **argmax on
      the r-axis** still does not separate the ladder's two ends against its own
      honest floor (|Δ| = 0.069 inside a combined ±0.115), so the χ(r) reading of
      the same physics remains under-resolved. (The Beta fit's p/(p+q) trend is
      **not** the fix — the 2026-08-02 assay demoted it as a misfit artifact; see
      MILESTONES K02.) The floor is not statistics — it is the parameterization:
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
- [ ] **Measure the fluctuation exponent γ — a live disagreement in the literature,
      on data K02 already collects.** The 2026-08-02 assay's §4.3 flagged this as a
      better K03 than another pass at the Beta form. Hong et al. 2015 report
      `γ ≃ γ' ≃ 1/4` for the **regular** frequency set (K02's case) with hyperscaling
      `γ = ν̄ − 2β` obeyed, against `≃ 1` and violated for the random set. Daido's
      perturbation theory (Prog. Theor. Phys. **75**, 1460 (1986); J. Stat. Phys.
      **60**, 753 (1990)) predicted an *asymmetric* `γ = 1/4` above and `γ' = 1`
      below — which Hong et al. contradict. That is a genuine open disagreement, in
      exactly K02's regime, and `χ_c(K_c) ~ N^(γ/ν̄_c)` is a one-line fit on the
      per-rung χ this milestone already measures at K_c. Now that K02's β/ν̄_c
      reproduces the published 0.39(2), the instrument has earned the right to be
      pointed at it.
- [ ] **Extend the K02 ladder past the pre-asymptotic window.** K02's β/ν̄_c =
      0.401(17) agrees with Hong et al.'s 0.39(2) but the ladder stops at
      N = 4000 = 2¹². Park & Park 2024 Eq. (20) put the true asymptote at 0.325(15),
      reached only for N ≳ 2¹⁵ ≈ 32768, and call the late crossover *"exceedingly
      challenging"*. Watching the effective exponent bend from 0.39 toward 0.325
      would be a far stronger statement than either endpoint alone — and it is pure
      CPU time (the measurement is O(N) per step at a single coupling), not new code.
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
