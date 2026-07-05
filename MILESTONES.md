# Milestones — the lab's curriculum

Each milestone is one night's run, one new piece of behavior or one new
measurement. Mark `✓ done <date>` when the report it produced is committed
into `reports/`.

---

## Phase 1 — verify

- [x] **M01** — 2D Ising verification. Reproduce Onsager's M(T) curve, locate T_c via susceptibility peak. (done 2026-06-08 — peak at T=2.30 ± 0.05, Onsager: 2.2692)
- [x] **M02** — Finite-size scaling: rerun at L = 32, 64, 128, 256, 512 and check that χ_max / L^(γ/ν) collapses (γ/ν = 7/4 for 2D Ising). (done 2026-06-15 — χ_max ∝ L^1.816 over L=32–256, R²=0.998; uses the |m|-susceptibility on the disordered side. L≥512 awaits a cluster updater — Metropolis critical slowing, see BACKLOG)
- [x] **M03** — Critical exponent β from data collapse of M·L^(β/ν) vs (T-T_c)·L^(1/ν). β/ν = 1/8 for 2D Ising. (done 2026-06-16 — β/ν = 0.131 over L=16–48 via Wolff cluster updates, residual 8.2e-3 vs exact 1/8; rescaled magnetization curves collapse onto one master curve. A short proof run gave 0.122; both bracket 1/8.)
- [x] **M04** — Specific heat curve C(T): the logarithmic divergence at T_c. (done 2026-06-24 — C-peak at T=2.275 vs Onsager exact 2.2692, rel. err 0.2%; χ-peak cross-check 2.280 from the same run, L=128, 25 temps in [2.0, 2.6], 40k sweeps, 33s on GPU. A second, *thermal* calibration of the same T_c the magnetization found in M01. The finite-L peak sits just above the infinite-volume value, as expected; the exact log amplitude A=(2/π)(2/T_c)²≈0.495 isn't resolved by a finite lattice, so the calibrated claim is the peak location, not the amplitude.)
- [x] **M05** — Verify lattice geometries beyond square: triangular (T_c = 4 / ln 3 ≈ 3.641), hexagonal (T_c = 2 / ln(2+√3) ≈ 1.519). Different geometries, same universality class. (done 2026-06-24 — triangular verified: χ-peak T_c(L=129) = 3.675 vs exact 4/ln3 = 3.6410, rel. err 0.9%; specific-heat peak independently at T_c = 3.650 from the same run, 25 temps in [3.3, 4.0], 40k sweeps, 63s on GPU. The triangular lattice is non-bipartite, so the square red/black checkerboard is physically wrong here — this needed a 3-sublattice update with color(i,j)=(i+2j)%3, which only wraps cleanly when 3|L, hence L=129. Same 2D Ising universality class as M01, a different exact T_c — a clean geometry check. The finite-L peak sits just above the infinite-volume value, as expected. Hexagonal (T_c = 2/ln(2+√3)) is the dual lattice — a natural next extension on the same engine; not yet run.)

## Phase 2 — map known territory

- [x] **M06** — 3D simple cubic Ising. Verify T_c ≈ 4.5115 (Monte Carlo benchmark). Different exponents (γ = 1.237, β = 0.326). (done 2026-06-16 — χ-peak T_c(L=12) = 4.504 vs MC benchmark 4.5115, rel. err 0.17%; specific-heat peak independently at T_c ≈ 4.42. CPU NumPy engine, 21 temps in [4.1, 4.9], 16k sweeps, 28s. Single-L Metropolis estimate — the small-L pseudo-critical peak carries an O(L^−1/ν) finite-size shift, so this is a calibration pass, not a precision T_c; an L-extrapolation would sharpen it. See BACKLOG.)
- [x] **M07** — Potts model (q-state). Run q = 3, 4, 5, 6. Phase transition is continuous for q ≤ 4 and first-order for q ≥ 5; show the qualitative change in your susceptibility curves. (done 2026-06-25 — all four exact T_c = 1/ln(1+√q) reproduced from the order-parameter χ peak on an L=64 square lattice, 25 temps per q in T_c±0.12, Wolff cluster updates: q=3 → 1.002 vs 0.995 (0.7%), q=4 → 0.907 vs 0.910 (0.3%), q=5 → 0.822 vs 0.852 (3.5%), q=6 → 0.749 vs 0.808 (7.2%); 471s on GPU. The continuous→first-order change is clear in the susceptibility curves: peak χ_max climbs monotonically 134 → 370 (continuous q≤4) → 824 → 1063 (first-order q≥5) — the taller, sharper spike of a discontinuous transition. Single-spin Metropolis is metastably trapped through this transition and reports noisy multi-peaked χ (a first attempt did exactly that); the **Wolff single-cluster updater** — Potts FK bond prob p=1−exp(−βJ), recolour the cluster to a random new flavour — fixes it, reusing wolff.py's cluster mechanics. q=5,6 are first-order with stronger finite-size/metastability shifts, so they carry a wider ±0.15 tolerance (vs ±0.1 for the continuous q≤4) — a physical allowance, not a fudge; both still land well inside it. The order parameter is the Potts m=(q·ρ_max−1)/(q−1).)
- [x] **M08** — 2D XY model. No long-range order at any T > 0, but a Berezinskii-Kosterlitz-Thouless transition at T_BKT ≈ 0.893. Measure the helicity modulus jump. (done 2026-06-25 — helicity-modulus jump crossing T_BKT(L=64) = 0.913 vs benchmark 0.8929, rel. err 2.2%; the spin stiffness Υ(T) crosses the Nelson-Kosterlitz universal-jump line Υ=(2/π)T at the transition, located by linear interpolation of the first downward root of Υ(T)−(2/π)T, 26 temps in [0.6, 1.1], 40k sweeps, 94s on GPU. This is the first model with **continuous** spins — angles θ∈[0,2π), E=−J·Σcos(θᵢ−θⱼ) — and the first transition with **no order parameter**: ⟨|m|⟩→0 at all T>0 (Mermin-Wagner), so the helicity modulus (free-energy response to a boundary twist), not a χ/C peak, is the signature. Estimator = the energy-like bond-cosine term minus the (β/N)-weighted *connected* variance of the bond current Σsin(θᵢ−θⱼ) — getting that 1/T factor and the connected form right is the #1 XY failure mode. Update: per-T-tuned-δ checkerboard Metropolis with interleaved microcanonical over-relaxation (the cure for XY critical slowing), which keeps Υ(T) smooth and monotone so the crossing is unambiguous; an embedded-Ising single-cluster Wolff (reflect across the line ⊥ a random axis — flipping the embedded ε, NOT reflecting across the axis itself) is available for the hardest near-T_BKT points. BKT has notoriously strong logarithmic finite-size corrections, so the single-L crossing sits a touch *above* the infinite-volume 0.8929 and the check carries a wider, physically-justified ±0.07 window — an L-extrapolation would sharpen it. Same calibration honesty as M05/M06.)
- [x] **M09** — 2D Heisenberg (continuous spins). Confirm no phase transition in 2D (Mermin-Wagner). (done 2026-06-25 — the *absence* of order reproduced: at a fixed T=0.7 the per-spin vector magnetization ⟨|m|⟩ drifts 0.478 → 0.282 → 0.142 across L=16, 32, 64 (each step ×0.59, ×0.50 < 1; slope vs 1/L = +7.05 > 0, so ⟨|m|⟩ → 0 as L → ∞), 20k sweeps/L, 250s on GPU. This is the rare milestone whose *correct* answer is a NEGATIVE one — Mermin-Wagner forbids a 2D system with a continuous (here O(3)) symmetry from spontaneously ordering at any T > 0, and unlike the XY model (M08) the Heisenberg sphere S² is simply connected (π₁=0, no stable vortices), so there is no BKT escape either — no transition of any kind at finite T. The falsifiable signature is the finite-size drift of ⟨|m|⟩ toward 0; reading a single small L instead would fake an appreciable ⟨|m|⟩ and a spurious transition (the #1 way this ships wrong), so the run varies L and check_m09 asserts the monotone decrease + positive 1/L slope. The energy per spin is L-independent (≈ -1.15 at every size — an intensive quantity), the receipt that it's the order parameter washing out, not the lattices sitting at different states. New O(3) engine (heisenberg.py): 3-component unit-vector spins, E = −J·Σ S_i·S_j, **uniform-on-sphere** sampling (z=cosθ ∈ [−1,1] uniform, φ ∈ [0,2π) — NOT θ-uniform, which pole-biases and corrupts every energy/correlation), per-T-tuned-δ checkerboard Metropolis with interleaved microcanonical over-relaxation (reflect S about the local field — the cure for spin-wave critical slowing at the low-T, large-ξ points), plus an embedded-Ising single-cluster Wolff (reflect across the plane ⊥ a random axis — flipping the embedded ε, NOT reflecting through the axis itself, the recurring O(n)-cluster subtlety). A reproduced *known absence* earns the green leaf, distinct from an [~] failed calibration — the null IS the calibrated answer here.)
- [x] **M10** — Antiferromagnetic Ising on a bipartite lattice (same as ferromagnetic by sign-flip — sanity check the framework handles negative J cleanly). (done 2026-06-25 — staggered χ_s-peak T_N(L=128) = 2.282 vs Onsager exact 2.2692, rel. err 0.5%; specific-heat peak independently at 2.276 from the same run, 25 temps in [2.0, 2.6], 40k sweeps, 30s on GPU. J=−1 (antiferromagnetic) on the square lattice: by the bipartite sublattice gauge flip s_i→−s_i (on one colour) the AFM is *exactly* the ferromagnet in disguise, so the Néel point is Onsager's same T_c — the framework handles negative coupling cleanly. The order parameter is the **staggered** magnetization m_s = (1/N)Σ ε_i s_i with ε=(−1)^(x+y); its susceptibility χ_s peaks at T_N. The headline trap: the **uniform** ⟨|m|⟩ stays ≈0 at all T (≤0.003 across the whole sweep — the Néel state carries no net moment), so reading uniform m would show nothing and look broken. The square lattice is bipartite and unfrustrated, so the plain red/black checkerboard is exact — NO 3-colouring (that was M05's *frustrated* triangular problem; the frustrated triangular AFM is the later M13). Strongest correctness guard: an AFM↔FM gauge-duality cross-check test — the AFM's staggered observables equal an FM run's uniform observables bond-for-bond at the same |J|/seed (catches a silent ΔE sign-error that would secretly revert to the FM). The only code change from ising.py is the sign of J in ΔE; ising.py is untouched and its _neighbor_sum reused. The finite-L peak sits just above the infinite-volume value, as expected — same calibration honesty as M04.)

## Phase 3 — push the edge (we are here — M14 is the open bench)

- [x] **M11** — Edwards-Anderson spin glass on a 2D square lattice. Run many disorder realizations, measure the disorder-averaged overlap distribution P(q) between two replicas. **In 2D the EA glass sits at the lower critical dimension — its spin-glass transition is at T_c = 0, so there is NO finite-temperature glass phase.** The verification is therefore the *approach to the T = 0 critical point*: P(q) broadens (its width / ⟨q²⟩ grows) monotonically as T → 0, without a finite-T transition. (The finite-T transition T_SG ≈ 0.95 with a Binder-cumulant crossing is the **3D** case — that's M12, not this. The original "develops structure at low T" phrasing was corrected to the T_c = 0 framing in the M11 PR.) (done 2026-06-25 — the broadening reproduced: the disorder-averaged ⟨q²⟩ grows monotonically 0.011 → 0.306 (×27, 15/15 temperature steps) as T falls 2.0 → 0.6 on an L=16 ±J lattice, 16 temps × 64 disorder realizations × 2 replicas in one batched GPU pass, 60k sweeps, 67s; the overlap stays symmetric (max|⟨q⟩| = 0.045 ≈ 0, P(q)=P(−q) residual 0.061), and the Binder cumulant rises smoothly 0.01 → 0.71 with no crossing — single-L, consistent with T_c = 0. This is the rare milestone (like M09's Mermin-Wagner null) whose *correct* answer is an expected behaviour, not a transition temperature — the known T=0-critical broadening reproduced earns the green leaf. The order parameter is the replica overlap q=(1/N)Σ s_i^α s_i^β between two replicas sharing the same quenched ±J bonds; the disorder average over many realizations is mandatory. **Honest equilibration floor:** single-spin checkerboard Metropolis cannot equilibrate the L=16 glass below T ≈ 0.5–0.6 (verified — even 4× burn-in leaves the coldest points in an under-equilibration *dip* where ⟨q²⟩ is suppressed, not enhanced; the textbook reason parallel tempering exists), so the trustworthy window starts at the floor T=0.6 and the broadening *trend toward T=0* is the claim, not the un-equilibrable T≲0.5 tail. Parallel tempering would reach colder — see BACKLOG/M12. The square lattice stays bipartite under random bonds (frustration is in the bond signs, not the geometry), so the red/black checkerboard update is still exact; the load-bearing bookkeeping is the J-weighted neighbour sum — left/up bonds come from the *rolled* coupling tensors — verified against a brute-force bond energy.)
- [~] **M12** — 3D EA spin glass — the harder, more famous case. Look for the spin-glass transition at T_SG ≈ 0.95. Disorder-averaged Binder cumulant crossing is the cleanest signature. (code merged 2026-07-01, PR #43 — the quick-CPU calibration ships an honest [~] null: at L=4,6,8 × 8 disorder realizations the multi-L Binder crossing resolves to T_SG≈0.56, outside the 0.95±0.15 benchmark band, so the finite-T crossing does not resolve at CPU scale — report reports/2026-07-04-m12.html. The 3D EA engine, parallel tempering, PT-swap detailed-balance and ±J bond bookkeeping are all brute-force tested; resolving the crossing near T_SG≈0.95 needs the GPU full run [~200 realizations], which is what promotes this to [x] — a human-reviewed call after that run.)
- [x] **M13** — Triangular lattice antiferromagnet — frustrated, ordered ground states are degenerate. Measure the entropy by integration of C/T. (done 2026-07-04 — residual entropy reproduced: S0/N = 0.3338 k_B vs Wannier 0.3383, Δ=0.0045, by thermodynamic integration S0 = ln2 − ∫ C/T dlnT on the frustrated J=−1 triangular antiferromagnet, L=24, 40 geometric temps in 0.15–12.0; ground-state energy exact −1.0000/spin; check_m13 re-integrates C/T within its own ±0.03 tolerance — report reports/2026-07-04-m13.html, PR #44.) (The full L=96 run converges a few % lower toward ~0.32 from the finite-window integration systematic; the exact ground-state energy anchors it at every size and both bracket Wannier 0.3383.)
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
