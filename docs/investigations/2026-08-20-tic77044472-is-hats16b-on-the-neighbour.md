# TIC 77044472 — the last lead is HATS-16 b, on the star next door

**2026-08-20. Verdict: REFUTED as a candidate on this target — and simultaneously
the pipeline's first blind recovery of a real planet it was never told about.
The shelf is now empty, 6 of 6.**

TIC 77044472 was the one survivor of the 2026-08-19 shelf sweep: the five others
died as `eclipsing-binary-p2-alias`, this one had no verdict. It had no verdict
because the gate that would have killed it does not exist yet.

The signal is real. The planet is real. It is not orbiting TIC 77044472.

---

## 1. What the detection actually is

| | |
|---|---|
| Blind detection, TIC 77044472 sector 2 | P = **2.685728751 d**, SDE 10.14, FAP 3.9 × 10⁻³ |
| **TOI 228.01 = HATS-16 b**, TIC 77044471 | P = **2.686506386 d** ± 3.0 × 10⁻⁶, TFOPWG **KP** |
| Offset | 0.0007776 d = **67 s = 0.029 %** |

67 seconds is inside single-sector BLS resolution (~10 transits across a 27-day
baseline), so this is a period match, not a near-miss.

TIC 77044471 sits **15.01 arcsec = 0.71 TESS pixels** from TIC 77044472 and is
**2.55 mag brighter** (T = 13.257 vs 15.807) — **10.5× the flux**. TESS cannot
separate them. The SPOC aperture reports `CROWDSAP` = 0.1389 (s2) / 0.1193 (s69):
**86–88 % of the aperture flux is not the target**, and essentially all of that
excess is this one star.

Sectors agree: TOI 228.01 is listed in sectors 2, 29, 69; the detection is in
sector 2 and the shelf sweep's second epoch is sector 69.

## 2. The physics narrows the on-target hypothesis but does NOT exclude it

**Corrected 2026-08-20, later the same day.** The first version of this section
claimed the duration alone ruled the target out. It did not, and the error was
mine: the duration/density relation was written in the small-planet limit.

**Duration bounds the host's density.** For a companion of radius ratio ``k``::

    T14 = (P/pi) * sqrt((1+k)^2 - b^2) / (a/R*)

At ``b = 0`` this gives the largest ``a/R*`` the observed duration allows, and
``rho* = 3pi/(G P^2) (a/R*)^3`` inherits that maximum — any real impact
parameter makes the host *less* dense. That much held.

What did not hold was dropping the ``(1+k)``. This is a 6 % eclipse, so
``k ~ 0.24`` and the term enters cubed: a factor of 1.9 in density. Measured
values, with ``T14/P = 0.0375`` and the fitted ``k = 0.243``:

| | rho*_max (g/cm3) | lightest allowed host |
|---|---|---|
| as first written (k = 0) | 1.60 | ~G8V, R* >~ 0.95 |
| **correct (k = 0.243)** | **3.08** | **~K5V, R* >~ 0.72** |

At ``R* = 0.72 R_sun`` the implied companion is **1.7 R_Jup** — large, but
planetary, and well inside ``a05_physical.MAX_PLANET_R_SUN``. So the claim
that there was "no M-dwarf escape hatch" and that the companion had to be
stellar was wrong. A K-dwarf host would have been perfectly consistent with the
light curve.

The error was caught by the control, not by inspection: WASP-18 b has a
published host density of 0.873 g/cm3, and the k=0 formula returns a "ceiling"
of 0.803 — below the truth, so not a ceiling at all. That test now lives in
``tests/test_a05_shape.py::test_dropping_k_breaks_the_ceiling``.

**What this means for the verdict:** nothing. The refutation was never the
density argument — it is the catalogue match in section 1, which is exact and
untouched. But the density gate must not be credited with a kill it did not
make, and section 5's claim about what the instrument achieved stands only on
the period match and the blend arithmetic.

## 3. The blend hypothesis predicted the answer before it was looked up

Taking the eclipse to sit on TIC 77044471 (R\* = 1.183 R☉, catalogued), with the
neighbour holding a fraction *g* ≈ 0.86 of aperture flux and the measured
detrended SAP depth of 0.864 %:

| quantity | predicted | published (HATS-16 b) | error |
|---|---|---|---|
| host radius (R☉) | 1.183 | 1.183 | 0.0 % |
| host density (g/cm³) | 0.89 | 0.895 | **0.5 %** |
| companion radius (R_Jup) | 1.18 | 1.253 | **5.8 %** |
| T₁₄ (h) | 2.42 | 2.657 | 8.9 % |
| depth on host (%) | 1.00 | 1.214 | 17.3 % |

The depth residual is the *g* ≈ 0.86 estimate; inverting the published depth gives
g = 0.71, consistent with a star 0.71 px off the aperture centre.

## 4. Two gate defects this exposes

### Defect A — the known-planet crosscheck never looks at the neighbours

`disposition_evidence.catalog` for TIC 77044472 reads
`known_toi: null, known_planet: null, n_ctoi: 0`. All true, and all irrelevant:
the crosscheck queries **the target TIC only**. A blended planet is by
construction filed under a *different* TIC. Querying TIC 77044471 returns
TOI 228.01 / KP immediately.

**Fix:** before promoting to lead, query every catalogued neighbour whose flux
could enter the aperture (the CROWDSAP budget already says how much foreign flux
is present) against the TOI and CTOI tables, with the existing alias-aware period
matcher. This is the fourth seam, alongside the three from 2026-08-18 —
odd/even dilution, P/2-vacuous secondary, no-CTOI crosscheck — and it is the one
that would have emptied the shelf without a single new photometric measurement.

### Defect B — CROWDSAP is applied twice, on flux that already has it

`a05_vetting.contamination` and `a05_physical.companion_radius` compute
`depth / CROWDSAP`. The pipeline reads **PDCSAP_FLUX** (`a01.py:378`,
`a05_vetting.py:382`), and SPOC's PDC has *already* removed the contaminating
flux using CROWDSAP. The second division is a double correction.

Measured directly — same eclipse, same cadences, SAP vs PDCSAP, both detrended:

| target | CROWDSAP | δ_PDC/δ_SAP | 1/CROWDSAP | |
|---|---|---|---|---|
| 100100827 (WASP-18) s2 | 0.9872 | 1.010 | 1.013 | ✓ |
| 100100827 s3 | 0.9886 | 1.001 | 1.012 | ✓ |
| 234518605 | 0.9550 | 0.981 | 1.047 | ✓ |
| 272357134 | 0.9982 | 0.989 | 1.002 | ✓ |
| 49558810 | 0.9943 | 0.979 | 1.006 | ✓ |
| **287328866** | **0.8058** | **1.239** | **1.241** | **✓ 0.2 %** |
| 369603748 | 0.9688 | 1.037 | 1.032 | ✓ |
| **77044472 s2** | 0.1389 | **6.79 ± 0.78** | 7.20 | ✓ 0.5σ |
| **77044472 s69** | 0.1193 | **7.85 ± 0.71** | 8.38 | ✓ 0.8σ |

The ratio tracks 1/CROWDSAP across the whole range — 287328866 at CROWDSAP 0.806
pins it to 0.2 %. **PDCSAP depth already is the deblended depth.** So the
`depth_corrected = 0.4419` carried in TIC 77044472's dossier is an artifact, not
a 44 % eclipse, and every `r_companion_corrected_*` on a crowded target is
inflated by 1/√CROWDSAP.

This is a different mechanism from the dilution claim retired on 2026-08-19 —
that one was about the parity-depth window; this one is about the flux series.
Both are the same failure shape: a correction applied to data that already had it.

**Fix:** delete the correction, or gate it on actually reading SAP_FLUX. Keep
CROWDSAP as a *flag* (a target at 0.12 deserves a neighbour sweep, which is
Defect A) rather than as a multiplier.

### A null worth recording

The duration/density check does **not** refute this candidate — see the
correction in section 2. Once ``(1+k)`` is carried, ρ\*ₘₐₓ = 3.08 g/cm³ leaves a
K-dwarf host standing and a ~1.7 R_Jup companion with it. The gate narrows the
host; it does not close the case. Recorded so it is not credited with more than
it did.

### A wrong turn, recorded

An earlier pass read the raw (undetrended) SAP/PDC ratio — 4.30 ± 0.68 vs a
predicted 8.38, apparently 6σ — as a blend signature. It was not: SAP on a
T = 15.8 star is trend-dominated, and detrending both series identically moved
the ratio to 7.85 ± 0.71 (0.8σ). The algebra also does not support the original
reading — PDC subtracts a constant and divides by a constant, so the ratio is
1/CROWDSAP no matter which star eclipses. The claim was wrong twice over.

## 5. What this is worth

The lab, blind, with no catalog hint, on a star contributing 12 % of its own
aperture flux, recovered a published hot Jupiter to **67 seconds in period** and
— once the blend was assumed — its radius to **5.8 %** and its host's density to
**0.5 %**.

That is a working instrument with a filing error, which is a much better problem
than a broken instrument. The correct disposition for TIC 77044472 is
`blended-known-planet`, a state that does not exist yet and should:
`known-planet` means *this star's* planet was recovered, and that is not what
happened.

**Shelf status: 0 leads standing, 6 of 6 dispositioned. 0 planets claimed.**

---

*Reproduce: `docs/investigations/2026-08-20-hats16b/` — the SAP-vs-PDCSAP ratio
harness, the density calculation, and the neighbour query. Controls are in the
table above and are the point: a measurement that only ran on the target of
interest would prove nothing.*
