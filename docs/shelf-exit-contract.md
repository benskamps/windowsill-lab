# The shelf-exit contract — how a lead stops being a lead

**Status: RULED 2026-08-19 by Ben. The three open questions are answered below
and marked ✅. What remains open is build work, not policy.**

The rulings, in one place:

| # | Question | Ruling |
|---|---|---|
| §4 | Does a lead need ≥2 sectors to be promotable? | **Yes, ≥2 sectors required.** |
| §6 | Where does a promoted lead go? | **ExoFOP, as a CTOI.** |
| — | M11 and parallel tempering | **Re-run tempered, keep both ladders.** |

**Update, same day:** with the new gates in place, five of the six leads on the
shelf were refuted and one survives
(`docs/investigations/2026-08-19-fold-gate-validation.md` §6.5). The queue this
contract was written to unblock is now one row long — which does not make the
contract less needed, because the entry condition that produced six leads is
still running and the exit condition still does not exist.

The machine has one terminal state it can reach on its own for a signal it
cannot explain: `lead-awaiting-human-review`. Nothing in the pipeline can move a
row out of it. That was the correct design — a machine that can promote its own
candidates will eventually promote a bad one — but it has a consequence nobody
wrote down: **the shelf only ever grows.** Seven lead rows across the receipts
as of 2026-08-19, the oldest from 08-15, none ruled on. A queue with an entry
condition and no exit condition is not a standard; it is a slow stop.

An outside read of the lab on 2026-08-19 put it plainly: *"That choice protects
reputation, but it also limits impact."* The fix is not to lower the bar. It is
to write the bar down, so that the standard gates instead of the calendar.

---

## 1. The principle

**The machine may refute. Only a human may promote. Neither may leave a lead
unruled indefinitely.**

Three exits, not one:

| Exit | Who | What it means |
|---|---|---|
| **Refuted** | machine | A gate found a specific astrophysical or instrumental explanation. Named verdict, evidence attached. |
| **Not novel** | machine | Somebody already filed this signal (TOI, confirmed planet, CTOI). Not a claim about what it is. |
| **Promoted** | human | Survived every gate, carries a complete dossier, and Ben has looked at it. |

Plus one holding state with a clock on it, §5.

## 2. Entry condition — what makes a row a lead in the first place

A row reaches `lead-awaiting-human-review` only after **every** gate below has
run and returned nothing. A row that reaches it because a gate *failed to run*
is a bug, and `pending_catalog` already exists to keep those rows out (a catalog
outage mints no lead — `lab.a05.resolve_catalog`). This contract extends that
rule to every gate: **an unrun gate is not a passed gate.**

Mandatory before a lead may be minted:

1. `extended_vet` — pulsation spectrum, odd/even, secondary, railing, harmonic alias
2. `fold_gate` — doubled-period fold + duration-matched odd/even *(new, 2026-08-19)*
3. `centroid_shift` + `contamination` — blend gates, or an explicit "no centroid data"
3b. `companion_radius` — is the occulting body small enough to be a planet, or an
    explicit "no stellar radius" *(new, 2026-08-19)*
4. `catalog_crosscheck` — TOI, confirmed-planet, **and CTOI** tables *(CTOI new, 2026-08-19)*
5. FAP from the star's own noise, both shuffling schemes, at full B
6. Injection sensitivity for the host (`d_min`)

Each returns a verdict or an explicit reason it could not. The lead's dossier
carries all six.

## 3. The multi-sector rule *(new, and the one that changes the most)*

**A lead is a property of a star, not of a sector.** Grading one sector at a
time is how TIC 287328866 got shelved: six of its eight sectors read the
doubled-fold difference below 5σ in isolation while the combination reads 9.43σ
(`docs/investigations/2026-08-19-fold-gate-validation.md` §5).

Before a row is minted as a lead, every archival sector for that TIC must be
pulled and the gates run per sector, with the evidence combined. A single-sector
lead is provisional at best, and the receipt must say which it is.

This is the largest open build in the sky track. `combine_p2_folds` is the first
instance; the general version — carry a star's per-sector evidence forward and
grade the star — is not built yet.

## 4. Exit condition — what a lead must clear to be promoted

**✅ RULED 2026-08-19.** A lead is promotable when all of the following hold,
each of them a number already measured by the pipeline:

- **Persistence — ✅ ≥ 2 sectors required.** Detected independently in ≥ 2 sectors
  at consistent period and depth (period agreement within `PERIOD_TOL_FRAC`,
  depths consistent within 3σ).

  **What this costs, recorded because it is a real cost.** This is the only
  criterion here that can reject something true: a genuine planet observed in
  exactly one sector — a long period, a star with a single visit — fails it
  permanently, however clean it is. The pipeline is therefore *structurally
  blind to single-sector planets*, by choice, because a single-sector candidate
  has no independent confirmation available and this instrument has no way to
  go and get one. Any future occurrence-rate statement must say so; a
  completeness figure that ignores this is wrong.
- **Significance.** Combined FAP below the declared α in both shuffling schemes.
  *(Proposed: the existing `FAP_ALPHA` = 0.01, applied to the combined evidence
  rather than per sector.)*
- **Every gate silent, on every sector.** Not "silent on the sector it was found
  in".
- **Uncatalogued.** No TOI, no confirmed planet, no CTOI at the period or any
  alias to n = 4.
- **Physically admissible.** Implied companion radius from the depth and the TIC
  stellar radius is sub-stellar. TIC 287328866 failed this by a mile and nothing
  in the pipeline asked. *(Built 2026-08-19: `lab.a05_physical`, graded on the
  UNcorrected depth so a crowding model cannot refute a candidate on its own.
  Two caveats travel with it: the radius runs ~7 % high because the depth is a
  box fit on a limb-darkened transit, and a star with no RADIUS keyword cannot be
  graded at all — TIC 77044472, the one lead still standing, is exactly that
  case.)*

A lead failing any of these is not refuted — it is **parked**, with the failing
criterion named.

## 5. The clock — no lead sits unruled

Every lead carries `first_seen`. Two deadlines, both proposed:

- **14 days** — the lead appears in the morning surface with its dossier link
  and the one question it needs answered. Not a nag; a queue that is visible is
  a queue that gets worked.
- **60 days** — auto-parked as `stale-unruled`, with the reason recorded as
  "no human ruling within the contract window". It stays in the register and
  stays linkable. **Parking is not refutation and must never be reported as
  one** — a parked lead is the lab admitting a bandwidth limit, which is an
  honest thing to publish and a dishonest thing to disguise.

The point of the clock is not urgency. It is that the shelf's contents stay a
known quantity rather than an accumulating silence.

## 6. Where a promoted lead goes

**✅ RULED 2026-08-19: ExoFOP, as a CTOI.**

Decided while nothing was queued, which was the point — the worst moment to
choose a destination is while holding a candidate you are excited about.

Why this is the right ceiling rather than a compromise:

- **A CTOI is explicitly a *candidate*,** which is exactly where this pipeline's
  vocabulary tops out. Filing one requires no change to the "never say planet"
  rule; it files at precisely the claim level the machine already refuses to
  exceed.
- **It is the table the pipeline now reads.** Three of the six refutations on
  2026-08-19 came out of it. Submitting is what it is for, and a lab that takes
  from a community table and never gives to it is a free rider.
- **It is reversible and low-stakes.** CTOIs are updated and withdrawn routinely;
  being wrong in public and then filing the refutation is the normal life of that
  table, and it is also how this register already behaves.

**Consequences that follow, and are now binding:**

- A submitted CTOI is a public artifact with Ben's name on it. The gates that
  refuted five of six leads are the filter standing between the machine and that
  artifact, so **weakening a gate is now a decision with an external blast
  radius**, not an internal one.
- **Refutations get filed too.** If the lab submits candidates it must also
  submit — or at minimum publish — the ones it later kills, including its own.
  Asymmetric submission is how a table fills with junk.
- The register publishes **parked and refuted leads alongside promoted ones**.
  This follows from the misses-stay-visible rule, and it is the part that makes
  the register unusual: most pipelines publish only what survived.

**Still open, but build questions rather than policy:** whether a promoted lead
gets its own page or only a row, and the mechanics of submission (ExoFOP account,
the upload format, who presses the button — Ben, since it is his name).

## 7. What this contract does not do

It does not lower any threshold. Every number in §4 is one the pipeline already
computes, and two new gates (§2.2, §2.4) make it *harder* to become a lead than
it was yesterday — which is the point. The 2026-08-19 gate build refuted leads
that the previous ladder minted; a stricter entry condition is the main reason
the shelf should shrink.

It also does not make the machine braver. Nothing here lets a gate promote a
candidate, and every new gate emits refutations only.

## 8. Status of each piece

| § | Piece | State |
|---|---|---|
| 2.2 | `fold_gate` in the mandatory list | **built** 2026-08-19, wired into `a05.process_target` |
| 2.4 | CTOI in `catalog_crosscheck` | **built** 2026-08-19 (`lab.exofop`) |
| 3 | per-sector evidence combined | **machinery built** 2026-08-22 (`lab.a05_star`, PR #119, adversarially reviewed — one refutation found and repaired: same-sector duplicate receipts must dedupe, never combine as independent looks): star-level dossier + combined 2P verdict wired into `lab shelf`, with every uncombinable sector named. **Starved for data until the pipeline persists signed fold evidence in receipts** — today zero committed receipts carry `signed_difference`, so the gate is live but idle; the remaining §3 work is at mint time (pull all archival sectors, persist `p2_fold`), not in the grader. Also new: the uniformity floor — a lead from a receipt whose own uniformity control failed (or is too small to grade, n < 5) parks as "FAP uninterpretable". |
| 4 | promotion criteria | **enforced** 2026-08-22 (`lab.shelf`, `lab shelf` CLI): a pure derivation of the committed receipts grades every lead — promotable / parked with the failing criterion named. Two criteria grade as *ungradeable-therefore-parked* until the pipeline measures what they need: depth consistency (no `depth_err` in receipts) and, for pre-08-19 receipts, physical admissibility. Significance is graded per sector in both schemes; the combined-evidence version waits on §3's general machinery, deliberately — per-sector-independent can only under-promote. |
| 4 | companion-radius admissibility gate | **built** 2026-08-19 (`lab.a05_physical`), wired into `a05.process_target` |
| 5 | `first_seen` + the clock | **built** 2026-08-22 (`lab.shelf`): `first_seen` = earliest lead receipt; 14 days → `surfaced` with the one question it needs; 60 days → `stale-unruled`, recorded as a bandwidth admission, never a refutation. |
| 5 | rulings ledger | **built** 2026-08-22: `docs/shelf-rulings.json` — the only path to `promoted`, human-written, vocabulary enforced (`promoted` / `refuted` / `not-novel`; anything else refuses the whole file). Seeded with the six historical refutations (08-19 sweep §6.5 + the 08-20 HATS-16 b sky-gate finding), each citing its investigation. |
| 6 | destination | **ruled** 2026-08-19 — ExoFOP as CTOI; submission path not built (Ben's account, Ben's button) |
