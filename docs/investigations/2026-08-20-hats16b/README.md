# Reproduce: TIC 77044472 is HATS-16 b on the neighbour

Findings doc: `../2026-08-20-tic77044472-is-hats16b-on-the-neighbour.md`

| script | proves |
|---|---|
| `sap_vs_pdcsap_ratio.py` | PDCSAP is already crowding-corrected → `depth/CROWDSAP` is a double correction. Controls span CROWDSAP 0.12–0.999; the 287328866 point (0.806) pins the prediction to 0.2%. **Detrend both series** — raw SAP on a T=15.8 star is trend-dominated and fakes a 6σ anomaly. |
| `neighbour_crosscheck.py` | The 15.01″ neighbour TIC 77044471 is TOI 228.01 = HATS-16 b, KP, P matching the blind detection to 67 s. |

Needs the a01 cache populated for the TICs referenced (they were, as of 2026-08-20)
and, for the crosscheck, network access to ExoFOP + MAST (`pip install astropy astroquery`).
