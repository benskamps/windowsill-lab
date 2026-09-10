# A05 survey audit — the running ledger

**Raised 2026-09-10** by an adversarial audit of all 76 committed hunt receipts,
commissioned because the operator had a hunch. Every finding below was VERIFIED
against the receipts' own evidence unless marked otherwise.

**The audit's own bottom line, kept verbatim so this file cannot soften it:**

> The receipts are honest. The arithmetic is honest. The published summary is
> three weeks stale on its headline number, and the statistical instrument that
> "closed" the discovery question is broken in a way that made closing it
> inevitable.

No fabricated numbers were found. Every count, FAP, Gumbel fit, control
membership and dossier hash re-derived from raw evidence. What follows are all
**logic errors** — correct computations over the wrong inputs, or gates nobody
calls.

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | pot.json advertised `leads_awaiting_human_review: 9` for three weeks after a human refuted six of them — one being HATS-16 b on a neighbour 0.71 px away. `hunt_block` never read `docs/shelf-rulings.json`; the page then *recomputed* the count from the dispositions histogram, so fixing one layer alone would not have reached a reader. | SEVERE | **FIXED** `5b89987` — four numbers published, both layers, agreement test added |
| 2 | `u_a01_attempt.empirical_fap` is non-monotone in SDE: the zero-exceedance bound `3/N` exceeds the one-exceedance estimate `1/N`, so SDE 8.60 is promotable and SDE 50 is refused. The kill verdict on the discovery question was arithmetically guaranteed before any data was seen, and it named SDE 8.048 "the strongest uncatalogued crossing" while SDE 10.14 sat in the same receipts. | SEVERE | **OPEN** — verdict needs retracting, `UNKNOWNS.md:168` corrected |
| 3 | TIC 49558810 (SDE 8.024) and TIC 287328866 (SDE 8.028) are exceeded **11 times** by pure-noise scrambles of their own sector's curves. Expected false alarms 0.254 = 2.5x the survey's own declared `PROMOTE_MAX_BACKGROUND`. Never leads by its own rule. The other seven are *unpriced*, not refuted — the bound cannot separate SDE 9 from SDE 50 (see #2). | SEVERE | **OPEN** — re-grade or retract |
| 4 | `sky_gates` is documented as making "an unrun gate is not a passed gate" machine-checkable. Nothing reads it — not `check_a05`, not `_hunt_refusal`. Absent entirely from **50 of 76** receipts. **6 of 9 lead stars** were minted with the neighbour/blend gate a documented no-op, one of them TIC 77044472. | HIGH | **OPEN** — give it a checker or delete the claim |
| 5 | Three receipts whose own uniformity control FAILED are published and counted. `check_a05` returns `None` for them ("every graded FAP is uninterpretable") but `_hunt_refusal`, the gate that actually runs at aggregation, accepts them. `hunt-2026-08-18-s2-1000.json` is one, and it is the **sole source** of lead TIC 77044472. Two more fail on budget over-share. | HIGH | **OPEN** — make `_hunt_refusal` refuse what `check_a05` refuses |
| 6 | TIC 144122210 is documented in `a04.py:180-186` as an eclipsing binary ("missed being auto-disposed an EB by 0.13 sigma"; re-measured ~8.9 sigma in a duration-matched window) and is still `lead-awaiting-human-review`. Systematic: `secondary_window_phase` first appears 2026-08-29, so **7 of 9 lead stars** had their secondary measured in a fixed window `a04.py` calls biased toward zero, landing hardest on short transits. | HIGH | **OPEN** — re-grade the pre-08-29 leads |
| 7 | The 2026-08-15 sector-2 pair shares **29 byte-identical target rows** including `cache_sha256` — one measurement filed twice by two boxes, neither declaring `supersedes` as the schema requires. Star-level counts dedupe correctly; `targets_searched` is a row sum by design (194 duplicate rows). | MEDIUM | **OPEN** — declare `supersedes`/`overlaps` |
| 8 | The public page renders `targets_searched` (a row sum) as "stars searched blind". At most 13,156 distinct stars against 13,350 published — **>=194 overstatement**. | MEDIUM | **OPEN** |
| 9 | TIC 212950885 passes physical admissibility only because the gate grades the **uncorrected** depth: `r_c` 1.735 R_Jup graded, 2.893 reported, `MAX_PLANET_R_SUN` 2.5. `crowdsap` 0.36, and its own flux budget names a neighbour holding 64% of the aperture at 0.887 px. The grading choice is defensible; the receipt does not say the lead's survival depends on it. | MEDIUM | **OPEN** |
| 10 | TIC 234518605's BLS box depth and folded vetting depth disagree by **22x** (survey median ratio 0.93, 4th-largest overall). Window dilution explains ~2x. Cause undetermined. Star is independently refuted. | LOW | **OPEN — cause unknown** |
| 11 | CTOI cross-check subfields first appear 2026-08-28; only **3 of 9** lead stars carry them, while **four of the six refutations cite a CTOI match** as the killing evidence. 82 of 195 above-threshold rows carry no `catalog` block at all. | MEDIUM | **OPEN** |
| 13 | **RETRACTED 2026-09-10, same day, by adversarial review.** I claimed the injection ladder was censored at both ends and that "64% of sensitivity values are bounds stored as point values". **The count was exact and the reading was wrong.** `d_min = min(recovered_depths) if recovered_depths else None` (`a05_sensitivity.py:244`), so a stored `0.010` means 0.002 and 0.004 were MISSED and 0.010 was RECOVERED — a bracket `0.004 < θ ≤ 0.010`, exactly as much a measurement as `0.004`. It is not censored. The genuinely right-censored cell is `None` (θ > 0.010, unbounded), which I filed as "correctly says cannot see" and excluded from my own 64%. **What survives:** the 56.6% floor is left-censored and under-claims sensitivity — but `null_statement` prints `>=` and `aggregate_sensitivity` takes a `max`, so an under-claim never wins and nobody's number is wrong because of it; and all 608 hosts with a `None` are flagged `insensitive` and excluded at `:257`. **The survey handles this correctly. The finding was mine, not the survey's.** | RETRACTED | **CLOSED** — no action; kept as the record of a wrong call |
| 12 | **Ours, not the audit's.** `docs/preregistrations/2026-09-10-u-a01-sector-96.md` justifies its SDE >= 8.0 threshold with "84,500 draws, maximum 8.049" — taken from `UNKNOWNS.md`. The live null is **325,000 draws with a sector-3 maximum of 8.6499**. The running sector-96 hunt inherits a threshold below the measured null maximum. | HIGH | **OPEN** — must be declared in the receipt, not silently re-baselined |

## Confirmed sound

Recorded because a clean finding is evidence too, and because an audit that
only lists faults cannot be used to judge coverage.

- `hunt_block` recomputed from the 76 receipts and diffed field-by-field against
  committed `pot.json`: **zero differences**. The pot is an honest function of
  its inputs.
- `planets_discovered` is hard-assigned from a literal after all aggregation; no
  data path can raise it, and `_hunt_refusal` refuses any row dispositioned
  `planet`. Zero such rows in 13,721.
- **1,810 of 1,810** stage-2 rows have `fap_graded == max(iid, block)`. The
  conservative rule genuinely selects, it does not default.
- 59/76 receipts pass `check_a05`'s full re-derivation — FAPs recomputed from
  stored raw maxima, Gumbel refit with the checker's own MLE, control membership
  re-derived from the declared seed hash.
- 9/9 lead dossiers SHA-256 verify byte-for-byte against their receipts. Zero
  orphans. The "missing tenth" is the duplicate row, not a missing file.
- Placebo control: 0 of 74 schema-1 receipts fail. The epoch-scramble ladder
  produced zero planet-candidates in every run.
- All 10 leads have `n_events >= 5`, within what a 27.4-day baseline permits at
  the claimed period. Odd-even and secondary tests ran on every one.
- `shelf.py` itself is sound — grades the star not the sector, dedupes, refuses
  to promote from the machine side, parks on named gaps. The machinery was
  right; only the publish path failed to consume it.
- Every receipt carries its own `null_caveat` verbatim: "every FAP here is
  anti-conservative by construction at some level." The repo declares its bias
  rather than hiding it.

## The shape

Every entry above is one of two things, and they are the same thing:

1. **A correct computation over half the record.** #1, #2, #6, #7, #8, #11.
2. **A check that exists and is never called.** #4, #5, and #1 again.

Neither is an arithmetic error. The system had the right answer somewhere in
every single case; the failure was always in the join.
