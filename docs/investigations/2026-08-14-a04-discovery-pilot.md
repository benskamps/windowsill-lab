# A04 discovery pilot — the first hunt, and what it caught (2026-08-14)

**Question.** A04 was promoted this morning on a narrow claim: the blind search
recovers confirmed planets it was never told about, with a measured false-alarm
floor. This pilot is the rung that calibration was *for* — point the same
instrument at stars nobody designated and see whether anything survives vetting
that the catalog does not already know.

**Protocol.** `scripts/a04_hunt.py`: the next 150 targets in A04's own
consistent-hash ranking (seed 2026), sector 2, with the graded run's 26 targets
and both designated recovery targets excluded — the sample stays predeclared,
not cherry-picked. Same grid (0.5 d – baseline/3), same detrend, same SDE ≥ 8
threshold, same vetting ladder. Injection control re-run on this slice's own
host; catalog cross-check (TOI + confirmed-planet TAP) at report time only.
Per-target JSONL checkpointing; three session interruptions cost nothing.

**Result: no new planet — one impostor unmasked, and the instrument came out
stronger.** 158 targets searched blind in 18 wall-minutes (warm cache).

| TIC | SDE | P (d) | depth | verdict | catalog |
|---|---|---|---|---|---|
| 358460464 | 9.2 | 0.6043 | 189 ppm | eclipsing-binary-secondary | — |
| 89543393 | 8.3 | 0.9416 | 15.6 % | eclipsing-binary-secondary | — |
| **140940493** | **8.7** | **0.6222** | **898 ppm** | **planet-candidate** → refuted | **none** |
| 160085375 | 8.0 | 1.4030 | 23.3 % | eclipsing-binary-secondary | — |
| 306470921 | 8.1 | 0.5286 | 917 ppm | eclipsing-binary-secondary | — |

Noise floor: max SDE 7.65 over 153 sub-threshold targets. Injections on this
slice's host (TIC 259847258): 1.0 % and 0.4 % recovered; **0.2 % missed
(SDE 4.9)** — sensitivity is host-dependent and the graded run's 0.2 %
recovery does not generalise to noisier stars.

## The candidate, and its refutation

TIC 140940493 cleared every gate the graded run shipped with: planet-sized
depth (898 ppm), 42 events, odd-even consistent at 1.7σ, no secondary
*dimming*, not railed, and **absent from both the TOI and confirmed-planet
tables**. For about forty minutes it was exactly the artifact this pilot
exists to surface.

Follow-up killed it three ways, each independent:

1. **The fold at P shows five equally spaced dips**, not one — the signature
   of a signal at P/5, not P.
2. **A sine-fit amplitude spectrum peaks at 8.035 cycles/day (P = 2.99 h,
   ~660 ppm)** — exactly the P/5 prediction (8.0363 c/d). A 3-hour period is
   below the contact-binary minimum: this is a **δ Scuti-type pulsator**, and
   the BLS grid (floor 0.5 d) latched onto its 5th harmonic.
3. **The "secondary" is a 13σ phase-locked brightening** — impossible for an
   occultation, natural for continuous oscillation.

The detection also survived every detrend window from 0.25 d to 1.5 d
(SDE 8.7–8.8 throughout), ruling out the other suspect — interaction between
the 0.5 d running median and the 0.62 d period. The signal is real; its
interpretation was wrong. Direction of miss: the *vetting layer*, again — the
same layer that produced all five of A04's graded defects. The search itself
has still never been wrong.

## Two vetting holes, both fixed the A04 way (a test named for the target)

1. **`harmonic-alias`** — `vet_candidate` now runs the same BLS box fit at
   P/n (n = 2…6). A true transit at P occupies only every n-th fold at P/n, so
   its box *mean* dilutes to ≤ depth/n; a signal genuinely periodic at P/n
   keeps full depth. Keeping ≥ 0.7× the P-fit depth above a 5σ floor is called
   an alias. (First implementation used binned *medians* and over-fired on
   50/50 mixtures — the existing EB fixtures caught it; means are exact here.)
2. **`phased-brightening`** — the secondary test used to check only
   `sec_sigma >= +5`; a −13σ brightening sailed through. Significant
   phase-locked brightening at 0.5 now disqualifies.

Both verified against the real cached light curve: the hunt's own detection of
TIC 140940493 now grades `harmonic-alias (n=5)`. A regression test pins that a
clean injected transit still reaches `planet-candidate` through the new gates.

## Instrument notes for the next hunt

- **The floor scales with sample size.** Max sub-threshold SDE was 6.6 over 22
  targets in the graded run, 7.65 over 153 here — plain order statistics. At
  thousand-target scale, SDE 8 will produce false alarms; a survey-grade
  threshold needs to grow with log(sample), or the vetting ladder carries the
  load (here, it did).
- **TIC 89543393 sits at P = 0.9416 d — within 0.02 % of WASP-18 b's period —
  yet is a 15.6 %-deep EB.** A coincidence worth remembering: period agreement
  alone identifies nothing.
- **0.2 % injections are not universally recoverable.** Depth sensitivity must
  be measured per host, not quoted per instrument.
- Sector 2's 2-minute SPOC targets are heavily worked territory; an
  uncatalogued *real* planet here was always a lottery ticket. The loop —
  search → vet → cross-check → follow-up → refute-or-escalate — is now proven
  end to end, which is what a first hunt is for. Next apertures: more of this
  sector (only ~180 of ~1,994 enumerated targets searched), then a recent
  sector where the community has had less time.

**Artifacts:** `2026-08-14-a04-discovery-pilot-summary.json` (this directory),
per-target checkpoints at `~/.lab/cache/a04-hunt-2026-08-14-s2.jsonl`
(publisher-local, deliberately uncommitted), hardened gates + tests in
`src/lab/a04.py` / `tests/test_a04_maturity.py`.
