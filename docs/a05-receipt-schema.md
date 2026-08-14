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
      "control_subsample": false,    // deterministically chosen sub-triage uniformity member
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
        { "depth": 0.002, "period_days": 2.3, "epoch": 0, "sde": 4.9, "fap_graded": null, "recovered": false }
      ],
      "d_min": { "2.3": 0.004, "3.7": 0.002, "5.1": 0.002 },  // per-period measured depth limit
      "known_planet": null,          // grading-time catalog identification, or name
      "published_period_days": null
    }
  ],
  "recoveries": [ /* same row shape; the designated + serendipitous knowns */ ],
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
  "floor_history": [                 // appended every run; makes the triage heuristic testable
    { "n": 22, "floor_max": 6.6, "source": "run-2026-08-08-2338-a04" },
    { "n": 153, "floor_max": 7.65, "source": "hunt-2026-08-14-s2" }
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
5. **Module map:** Lane 1 `src/lab/a05_stats.py`, Lane 2
   `src/lab/a05_vetting.py` (+ minimal `a01.py` reader extension), Lane 3
   `src/lab/a05_sensitivity.py`, Lane 4 `src/lab/a05.py` (orchestrator) +
   `checks.py` + `scripts/a05_hunt.py`, Lane 5 `publish.py` + `web/index.html`
   + `MILESTONES.md`. No lane edits another lane's module.
