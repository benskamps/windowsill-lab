# A05 hunt-receipt schema — the cross-lane contract (2026-08-14)

Committed home: `reports/hunts/hunt-<YYYY-MM-DD>-s<sector>.json`. One file per
completed hunt run. Every lane builds against this shape; `check_a05` owns the
constants that grade it and re-derives everything from the raw stored numbers.

```jsonc
{
  "experiment": "a05-survey-hunt",
  "schema": 1,
  "generated_at": "2026-08-14T17:00:00+00:00",   // UTC ISO
  "sector": 2,
  "slice_rule": "consistent-hash ranking, seed 2026, graded-run + prior-hunt targets excluded",
  "seed": 2026,                      // top-level: the run seed behind slice ranking + control draw
  "control_fraction": 0.10,          // top-level: pre-data fraction routed to the uniformity control
  "n_enumerated": 1994,
  "targets": [                       // one row per target ATTEMPTED
    {
      "tic": "140940493",
      "outcome": "searched",         // searched | skipped-no-product | error:<Type>
      "cache_sha256": "…",           // SHA-256 of the cached FITS bytes (searched only)
      "sde": 8.69,                   // observed, blind_search convention
      "period_days": 0.62217,
      "depth": 0.000898,
      "phase": 0.4775,
      "stage2": true,                // paid the bootstrap (above triage OR control subsample)
      "control_subsample": false,    // pre-data uniformity-control member (hash draw, NO SDE filter)
      "fap": {                       // present iff stage2
        "B": 256,
        "seed": 123456789,           // RNG seed for this target's permutations
        "schemes": {
          "iid":   { "raw_maxima": [/* B floats */], "fap_empirical": 0.0039 },
          "block": { "block_days": 0.75, "raw_maxima": [/* B floats */], "fap_empirical": 0.0117 }
        },
        "fap_graded": 0.0117,        // the MORE CONSERVATIVE of the two — the ONLY graded number
        "gumbel": {                  // reported-never-graded; may be null if calibration refused
          "mu": 5.1, "beta": 0.62,
          "bulk_calibration_pass": true,
          "fap_tail": 0.0021
        }
      },
      "disposition": "stellar-pulsation",  // machine disposition, code vocabulary verbatim;
                                           // above-threshold rows REQUIRE one; terminal
                                           // machine states include "lead-awaiting-human-review"
      "disposition_evidence": { "pulsation_cpd": 8.035 },   // gate-specific, optional
      "injections": [                // per-host ladder, Stage-2 + recovery hosts
        { "depth": 0.002, "period_days": 2.3, "epoch": 0, "sde": 4.9, "fap_injection_iid": null, "recovered": false }
      ],
      "d_min": { "2.3": 0.004, "3.7": 0.002, "5.1": 0.002 },  // per-period measured depth limit
      "known_planet": null,          // grading-time catalog identification, or name
      "published_period_days": null
    }
  ],
  "recoveries": [ /* same row shape; the designated + serendipitous knowns */ ],
  "sky_gates": {                     // did apply_sky_gates RUN? asked and answered
    "status": "ran",                 // "ran" | "not-wired" — an unrun gate is not a passed gate
    "neighbours_wired": true,        // was a neighbour resolver supplied to run_a05
    "catalog_wired": true,           // was a neighbour TOI/CTOI lookup supplied
    "rows_examined": 3,              // leads put to the gate
    "rows_refuted": 1,               // leads the gate took away
    "lookup_errors": 0,              // outages; each one makes the run INCOMPLETE
    "verdicts": { "blended-known-planet": 1 }
  },
  "uniformity": {                    // the calibration of the calibrator
    "n_control": 50,
    "p_values": [/* floats */],
    "ks_stat": 0.071,
    "pass": true
  },
  "placebo": {                       // epoch-scramble through the FULL ladder
    "n_scrambled": 25,
    "planet_candidates": 0,
    "pass": true
  },
  "floor_history": [                 // appended every run; makes the triage heuristic testable.
                                     // Sources are the COMMITTED receipt filenames (renamed from
                                     // the earlier shorthand constants), so every point is checkable.
    { "n": 22, "floor_max": 6.6, "source": "run-2026-08-08-2338-a04.json" },
    { "n": 153, "floor_max": 7.65, "source": "hunt-2026-08-14-s2-pilot-158.json" },
    { "n": 551, "floor_max": 7.875, "source": "hunt-2026-08-14-s2-pilot-570.json" }
  ],
  "triage": {                        // compute-bounding HEURISTIC — never graded, never "measured"
    "level": 7.9, "mu": 5.9, "beta": 0.54, "safety_margin": 1.0
  },
  "budget": { "per_target_share": 0.00025, "survey_sum_reported": 0.31 },  // sum is REPORTED only
  "counts": { "attempted": 500, "searched": 496, "skipped": 3, "errors": 1,
              "stage2": 41, "above_threshold": 9, "dispositioned": 9,
              "leads_awaiting_human_review": 0 },
  "wall_seconds": 5400.0,
  "provenance": { "machine": "win-cuda", "code_sha": "…", "python": "3.13" },
  "claim_boundary": "…"              // shipped verbatim into pot.json by the aggregator
}
```

Contract rules (binding on all lanes):

1. **Graded vs reported.** `fap_graded` (per-target, more-conservative scheme,
   empirical bound `(1+k)/(B+1)`) is the only graded statistic. Gumbel tail and
   the survey-level sum are reported-never-graded; a failed bulk calibration
   nulls the gumbel block entirely.
2. **Counts reconcile or the receipt is unreadable**: `attempted = searched +
   skipped + errors`; every above-threshold row carries a machine disposition;
   `check_a05` re-derives counts from rows, never trusts `counts`.
3. **Machine terminal state is `lead-awaiting-human-review`** — no machine
   path may emit `planet`, and `planets_discovered` cannot be raised by code.
4. **Raw maxima stay in the receipt** (both schemes) so `check_a05` can refit
   and recompute without trust. Cached FITS are pinned by SHA-256 for spot
   reproduction within a checks-owned numerical tolerance (seed-pinned, not
   bit-for-bit across platforms).
5. **Schema 0 (pre-A05 pilots) and `supersedes`.** The two 2026-08-14 pilot
   receipts carry `"schema": 0` and an explicit pilot marker: they predate the
   FAP engine, so only hit rows and floor stats are recorded and the aggregator
   accepts them for counters it can honestly derive, labeling provenance
   "pilot (pre-A05 statistics)". A receipt whose target set extends an earlier
   one (shared checkpoint file) declares `"supersedes": "<receipt filename>"`;
   the aggregator excludes superseded receipts from counters (naming them in
   `hunt.superseded`) so cumulative runs cannot double-count. Only an accepted
   receipt may supersede.
**The `sky_gates` block exists because absence is not evidence.** A receipt
with no sky verdict on any row is ambiguous between "the gate ran and cleared
every lead" and "the gate was never wired" — and from 2026-08-20 until the
2026-08-21 gauntlet it silently meant the second: `scripts/a05_hunt.py` called
`run_a05` without `neighbours`, so `apply_sky_gates` was a no-op in the one
place production leads are minted. The block states the answer either way, so
the shelf-exit contract's "an unrun gate is not a passed gate" is a
machine-checkable claim rather than a hope. A `lookup_errors` count above zero
means some lead could not be asked the question; those rows go
`pending_catalog` and the run is not allowed to become a receipt at all.

6. **The uniformity control is chosen pre-data, on purpose.** Control
   membership is a deterministic hash of `(seed, tic)` with **no SDE filter**
   (the top-level `seed` and `control_fraction` fields pin the draw), so a
   control member can legitimately host a real astrophysical signal and drag
   the KS statistic. That is accepted behavior, not a defect: filtering
   controls by outcome would bias the very calibration the control exists to
   test. A KS degraded by a genuine signal is investigated, not excluded.
7. **The triage line is a heuristic with its first real test datum.** The
   two-point line fit to (22, 6.6) and (153, 7.65) predicted the n=551 floor
   about **0.47 SDE high** against the measured (551, 7.875) — conservative in
   the safe direction, but a miss. It stays a compute-bounding heuristic,
   never graded and never "measured"; `floor_history` exists precisely so
   every run retests it against a committed receipt.
8. **Known-planet boundary.** A confirmed known planet whose flux genuinely
   shows a secondary — WASP-18 b, with a real 399 ppm occultation — is
   dispositioned `known-planet`, with the physics verdict preserved as
   `disposition_evidence.initial_verdict`. Catalog identity outranks a bare
   secondary verdict **only for confirmed planets** (TFOPWG KP / CP); for
   anything else the physics verdict stands.
9. **Module map:** Lane 1 `src/lab/a05_stats.py`, Lane 2
   `src/lab/a05_vetting.py` (+ minimal `a01.py` reader extension), Lane 3
   `src/lab/a05_sensitivity.py`, Lane 4 `src/lab/a05.py` (orchestrator) +
   `checks.py` + `scripts/a05_hunt.py`, Lane 5 `publish.py` + `web/index.html`
   + `MILESTONES.md`. No lane edits another lane's module.
