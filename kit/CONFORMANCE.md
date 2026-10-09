# Does the kit follow its own rules?

This checks the runner (`src/lab/planetkit.py`) against two things: the
lab's ten rules in [`PROTOCOL.md`](PROTOCOL.md), and the professional path
in [`PROCEDURES.md`](PROCEDURES.md). Every row says where in the code the
rule is enforced, or that the kit departs from it on purpose and why.
Checked 2026-10-09 against the code in this commit.

## Against the lab's ten rules

| Rule | Kit | Where, or why not |
|---|---|---|
| 1. Write the question first, and date it publicly | **Enforced, with one soft edge.** No run without a preregistration, and the star and sectors must match it. An *uncommitted* form is allowed, but every receipt and verdict then says so | `read_prereg`, `git_provenance`, `plain_verdict`. Soft on purpose: a newcomer's calibration run on WASP-18 shouldn't need a GitHub account |
| 2. One threshold for every star | **Enforced.** A form that sets any SDE other than 8.0 is refused | `read_prereg` |
| 3. Every signal gets its own null, two schemes, the worse one counts | **Enforced** at B = 256 by default. `--quick` uses 64, and its receipts are marked so they can't be posted or counted in a ledger | `a05.process_target`, `QUICK`, `ledger` |
| 4. Measure what this star could have shown | **Enforced.** Every "nothing found" sentence quotes the star's own depth floor | `a05_sensitivity.null_statement` via `plain_verdict` |
| 5. A placebo through the whole ladder | **Enforced, one simplification.** Ten scrambles of the star's own photons; any candidate voids the run. The placebo scrambles don't get their own permutation null (the survey's do), because the pass rule is "zero candidates" and doesn't need one | `search_sector`, receipt `parameters.placebo_fap: false` |
| 6. A fixed ladder, every rung recorded | **Enforced.** A rung that couldn't run (offline catalog, CSV input with no centroids, a catalog outage) is recorded as not run, and the star can't become a lead | `resolve`, `star_status` (`incomplete`), `a05.resolve_catalog` |
| 7. A closed vocabulary with no word for "planet" | **Enforced.** Words come from `lab.a05_vocab`. A receipt with an unknown word, `planets_claimed` other than 0, or a claim phrase is refused | `check_receipt`, `_CLAIM` |
| 8. Refuse, don't repair | **Enforced.** A failed placebo makes the star `control-failed`; nothing retries or retunes | `star_status` |
| 9. A lead belongs to a star, not a sector | **Enforced.** One sector is marked provisional; the ledger regrades a star across all your receipts | `star_status`, `ledger` |
| 10. Every number in a write-up comes from the receipts | **Partly.** `explain` and the ledger print only receipt values, and the skill tells an agent to quote the verdict verbatim. The kit can't check a post you write yourself | `explain`, `ledger_text`, skill rule 5 |

## Against the field's path

What the kit does the way the field does: quality-flag masking (stricter than
lightkurve's `"hard"` mask: only `QUALITY == 0` cadences), PDCSAP light
curves, a fixed detection threshold, a per-target noise null, a
scrambled-data placebo, injection and recovery, odd/even, secondary eclipse,
the P/2 alias, pulsation, transit shape, the density check, the size check,
crowding, a flux-weighted centroid shift, and the catalog check
(TOIs, confirmed planets, and ExoFOP community candidates, alias-aware, with
the table's age recorded).

Where it departs, knowingly:

| The field does | The kit does | Why |
|---|---|---|
| 3 to 5 independent human vetters | one human, you | a one-person kit. The kit stops at "lead awaiting human review" so the human step stays explicit |
| statistical validation (TRICERATOPS) | none | needs follow-up data a newcomer doesn't have. The kit can't take a lead past "candidate", and says so |
| difference-image centroids | flux-weighted centroids from the SPOC file | no pixel data in the kit's path. Crowding can bias them, and CSV input has no centroid gate at all |
| biweight detrending at about 3x the transit duration | a fixed 0.5-day running median | the lab's survey uses it, and changing it would change every published receipt. Long transits (over about 5.5 h) lose depth |
| TLS alongside BLS | BLS only | same reason |
| stitched multi-sector searches | one sector at a time, graded across sectors after | same reason. Periods over about 9 days are missed |
| FFI light curves for faint stars | SPOC 2-minute targets only | same reason |

None of these is hidden: the same list is in the kit README under "What the
kit doesn't do (yet)". Each departure narrows what a result can say; none of
them lets the kit say more than the field would.
