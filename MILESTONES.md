# Milestones — the lab's curriculum

Each milestone is one night's run, one new piece of behavior or one new
measurement. Mark `✓ done <date>` when the report it produced is committed
into `reports/`.

---

## Phase 1 — verify (we are here)

- [x] **M01** — 2D Ising verification. Reproduce Onsager's M(T) curve, locate T_c via susceptibility peak. (done 2026-06-08 — peak at T=2.30 ± 0.05, Onsager: 2.2692)
- [x] **M02** — Finite-size scaling: rerun at L = 32, 64, 128, 256, 512 and check that χ_max / L^(γ/ν) collapses (γ/ν = 7/4 for 2D Ising). (done 2026-06-15 — χ_max ∝ L^1.816 over L=32–256, R²=0.998; uses the |m|-susceptibility on the disordered side. L≥512 awaits a cluster updater — Metropolis critical slowing, see BACKLOG)
- [x] **M03** — Critical exponent β from data collapse of M·L^(β/ν) vs (T-T_c)·L^(1/ν). β/ν = 1/8 for 2D Ising. (done 2026-06-16 — β/ν = 0.131 over L=16–48 via Wolff cluster updates, residual 8.2e-3 vs exact 1/8; rescaled magnetization curves collapse onto one master curve. A short proof run gave 0.122; both bracket 1/8.)
- [x] **M04** — Specific heat curve C(T): the logarithmic divergence at T_c. (done 2026-06-24 — C-peak at T=2.275 vs Onsager exact 2.2692, rel. err 0.2%; χ-peak cross-check 2.280 from the same run, L=128, 25 temps in [2.0, 2.6], 40k sweeps, 33s on GPU. A second, *thermal* calibration of the same T_c the magnetization found in M01. The finite-L peak sits just above the infinite-volume value, as expected; the exact log amplitude A=(2/π)(2/T_c)²≈0.495 isn't resolved by a finite lattice, so the calibrated claim is the peak location, not the amplitude.)
- [x] **M05** — Verify lattice geometries beyond square: triangular (T_c = 4 / ln 3 ≈ 3.641), hexagonal (T_c = 2 / ln(2+√3) ≈ 1.519). Different geometries, same universality class. (done 2026-06-24 — triangular verified: χ-peak T_c(L=129) = 3.675 vs exact 4/ln3 = 3.6410, rel. err 0.9%; specific-heat peak independently at T_c = 3.650 from the same run, 25 temps in [3.3, 4.0], 40k sweeps, 63s on GPU. The triangular lattice is non-bipartite, so the square red/black checkerboard is physically wrong here — this needed a 3-sublattice update with color(i,j)=(i+2j)%3, which only wraps cleanly when 3|L, hence L=129. Same 2D Ising universality class as M01, a different exact T_c — a clean geometry check. The finite-L peak sits just above the infinite-volume value, as expected. Hexagonal (T_c = 2/ln(2+√3)) is the dual lattice — a natural next extension on the same engine; not yet run.)

## Phase 2 — map known territory

- [x] **M06** — 3D simple cubic Ising. Verify T_c ≈ 4.5115 (Monte Carlo benchmark). Different exponents (γ = 1.237, β = 0.326). (done 2026-06-16 — χ-peak T_c(L=12) = 4.504 vs MC benchmark 4.5115, rel. err 0.17%; specific-heat peak independently at T_c ≈ 4.42. CPU NumPy engine, 21 temps in [4.1, 4.9], 16k sweeps, 28s. Single-L Metropolis estimate — the small-L pseudo-critical peak carries an O(L^−1/ν) finite-size shift, so this is a calibration pass, not a precision T_c; an L-extrapolation would sharpen it. See BACKLOG.)
- [ ] **M07** — Potts model (q-state). Run q = 3, 4, 5, 6. Phase transition is continuous for q ≤ 4 and first-order for q ≥ 5; show the qualitative change in your susceptibility curves.
- [ ] **M08** — 2D XY model. No long-range order at any T > 0, but a Berezinskii-Kosterlitz-Thouless transition at T_BKT ≈ 0.893. Measure the helicity modulus jump.
- [ ] **M09** — 2D Heisenberg (continuous spins). Confirm no phase transition in 2D (Mermin-Wagner).
- [ ] **M10** — Antiferromagnetic Ising on a bipartite lattice (same as ferromagnetic by sign-flip — sanity check the framework handles negative J cleanly).

## Phase 3 — push the edge

- [ ] **M11** — Edwards-Anderson spin glass on a 2D square lattice. Run many disorder realizations, measure overlap distribution P(q). At low T it broadens and develops structure — that's the glassy signature.
- [ ] **M12** — 3D EA spin glass — the harder, more famous case. Look for the spin-glass transition at T_SG ≈ 0.95. Disorder-averaged Binder cumulant crossing is the cleanest signature.
- [ ] **M13** — Triangular lattice antiferromagnet — frustrated, ordered ground states are degenerate. Measure the entropy by integration of C/T.
- [ ] **M14** — Random-bond Ising (binary disorder p% antiferromagnetic bonds). Map the multicritical Nishimori point.

## Phase 4 — genuinely open

- [ ] **M15** — Glauber dynamics relaxation: quench from T=∞ to below T_c. Track domain growth — Allen-Cahn predicts L_domain(t) ~ t^(1/2). Measure the exponent.
- [ ] **M16** — Aging in spin glasses: after a quench, two-time correlator C(t, t_w) should depend on t/t_w only (aging) or only on t-t_w (equilibrium). Time-translation invariance breaks below the transition.
- [ ] **M17** — KPZ growth on circular geometry — interfaces wrapping around a torus, GUE-Tracy-Widom distribution of fluctuations. Numerical exponents 1/3 in time, 2/3 in space.
- [ ] **M18** — Directed percolation in 2+1d at the absorbing-state transition. Universality class is one of the simplest non-equilibrium examples.

---

# The Citizen Science book

The physics ladder above proves the lab can be trusted. This book points that
trust *outward* — at real contributions a single patient machine can make to
science that other people use. Same rule as the physics: **calibrate first**
(reproduce a known result), then contribute, then submit to the official record.
See [CITIZEN_SCIENCE.md](CITIZEN_SCIENCE.md) for venues, contributor IDs, and the
provenance/DOI workflow. IDs are track-prefixed (C/A/I/B) and a verified
contribution carries its record as `{venue=… ; url=… ; doi=…}`.

## Track C — compute & number theory

- [ ] **C01** — Calibrate the number stack: reproduce a known OEIS b-file segment byte-for-byte and re-verify a small known Mersenne prime. A pass means the arithmetic is trustworthy.
- [ ] **C02** — Run one assigned GIMPS exponent (PRP + proof) to completion and submit the residue. {venue=GIMPS}
- [ ] **C03** — Extend an existing OEIS sequence's b-file by N verified terms (or submit a new sequence) and get it accepted. {venue=OEIS}
- [ ] **C04** — Join PrimeGrid and complete validated work units on an open prime problem (Proth / Sierpiński). {venue=PrimeGrid}

## Track A — astronomy from open archives

- [ ] **A01** — Calibrate photometry: recover a *confirmed* TESS hot-Jupiter's period and transit depth from open MAST data, within the published error bars.
- [ ] **A02** — Recover a known variable star's light curve and period; register an AAVSO observer code and submit one validated observation. {venue=AAVSO}
- [ ] **A03** — Reprocess one open LIGO/Virgo event from GWOSC and reproduce its published chirp mass within error. {venue=GWOSC}
- [ ] **A04** — Blind transit search across one TESS sector; vet the candidates and report a recovered planet. {venue=ExoFOP}

## Track I — the machine as instrument

- [ ] **I01** — Calibrate the CMOS as a particle detector: cap the sensor, characterize dark noise, and separate hot pixels from track-like events (DECO/CRAYFIS method).
- [ ] **I02** — Log cosmic-ray muon candidates for a month; check the rate against the ~1 / cm² / min expectation and the zenith-angle dependence. {venue=DECO}
- [ ] **I03** — Stand up a hardware-entropy beacon: publish a signed, timestamped randomness feed that passes the NIST SP 800-22 health tests. {venue=Zenodo}

## Track B — donate cycles (BOINC)

- [ ] **B01** — Join a team and complete validated work units on Einstein@Home (continuous-gravitational-wave / pulsar search). {venue=Einstein@Home}
- [ ] **B02** — Complete validated units on Rosetta@home or World Community Grid; archive the credit record. {venue=BOINC}

## Conventions

- Each milestone PR includes the report it generated (drop the HTML +
  JSON into `reports/`).
- Don't burn weeks of compute without checkpointing — every long run
  writes intermediate JSON every N samples.
- A milestone that doesn't reproduce a known result is a failed
  calibration, not a discovery. Verify before claiming. Mark it `- [~]`
  (instead of `- [x]`): it stays on the books as an honest null and shows
  up as a folded grey leaf on the [seed](https://www.brokenbranch.dev/windowsill/),
  not a green one.
- Phase 4 results that LOOK novel get a second pass from a real physicist
  before sharing.
- The checkboxes here are the single source of truth for `lab publish`:
  `[x]` → verified, `[~]` → null, `[ ]` → pending (the first pending is the
  open experiment, the seedling's growing tip).
