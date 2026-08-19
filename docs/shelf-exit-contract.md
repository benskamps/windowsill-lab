# The shelf-exit contract — how a lead stops being a lead

**Status: proposed 2026-08-19. §4 thresholds and §6 destination are Ben's ruling
and are marked. Everything else is mechanism and is already built or buildable.**

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

**⚠ Ben's ruling. The mechanism below is proposed; the numbers are his.**

A lead is promotable when all of the following hold, each of them a number
already measured by the pipeline:

- **Persistence.** Detected independently in ≥ 2 sectors at consistent period
  and depth. *(Proposed: period agreement within `PERIOD_TOL_FRAC`, depths
  consistent within 3σ.)*
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

**⚠ Ben's ruling, and the one with the most on it.**

Today: nowhere. A promoted lead would sit in this repo. The lab's stated goal is
*"a measurement nobody has made yet, given away free"*, and a candidate that
never reaches the community has not been given away.

The obvious destination for the sky track is **ExoFOP as a CTOI** — the same
table §2.4 now reads. Submitting is what the table is for, it costs nothing but
an account, and a CTOI is explicitly a *candidate*, which is exactly the claim
level the pipeline's vocabulary tops out at. It requires no change to the
"never say planet" rule.

Open questions that are genuinely Ben's:

- Submit as CTOIs, or hold everything until something clears a higher internal
  bar? Submitting is reversible and low-claim; holding is the current default by
  omission rather than by decision.
- Does a promoted lead get its own page on the register, or only a row?
- Does the lab publish its **parked** and **refuted** leads too? (Consistent with
  the misses-stay-visible rule, this should be yes — and it is the part that
  makes the register unusual.)

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
| 3 | per-sector evidence combined | `combine_p2_folds` built; general version **not built** |
| 4 | promotion criteria | **proposed**, awaiting ruling |
| 4 | companion-radius admissibility gate | **built** 2026-08-19 (`lab.a05_physical`), wired into `a05.process_target` |
| 5 | `first_seen` + the clock | **not built** |
| 6 | destination | **awaiting ruling** |
