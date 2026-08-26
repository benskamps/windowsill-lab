# The pots — eight hunting grounds, one shape

**2026-08-25.** Every pot below is an instance of a single observation:

> **The expensive cognitive step is already done and published. The cheap
> mechanical follow-through was never worth anyone's time.**

We are not smarter than the people who wrote these papers. We are the only ones
with no career reason to look away from the parts their incentives don't reward.

## The rules every pot inherits

Learned the hard way on 2026-08-24/25, at a cost of four wrong turns:

1. **Gate order is inverted.** Test *would anyone use it* FIRST (hours), then
   *does it already exist* (minutes), then *can we compute it* (expensive). Going
   1→2→3 is how a night gets spent on a table nobody wants — verified, once.
2. **Two-sided filter.** A candidate needs *the constraint moved* **and**
   *somebody reads the answer*. One without the other is a hobby.
3. **No negative-literature claims.** Every pot below is built on a POSITIVE,
   checkable statement someone else wrote down. "Nobody has done X" is the
   operation this lab is demonstrably worst at — it got U-C01 wrong twice.
4. **Never fight active specialists on their own ground.** Cost: four GPU-hours
   and three instrument defects, to lose a comparison that turned out to be
   measuring a different quantity than the papers it was compared against.
5. **The cheap check always precedes the spend.** Four for four today.

---

## P-CONFESSION · stated constraints
**The cheat.** The author hit the wall, knew the field, and wrote down where the
wall was and why. We only check whether it expired.
**Tell.** `prohibitiv*` · `computationally (expensive|demanding)` · `limited to`
· `CPU/core/GPU hours` · `due to computational cost`
**Measured 2026-08-25.** 51 papers, full text: **59% carry a pattern, ~1 in 3
genuine, 10% with an extractable number.** Precision is the work, supply is not.
**Kills it.** A constraint stated in 2016 may have been resolved in 2019 by
someone else — and the text cannot tell us. Every candidate needs a
did-anyone-already check, which is the expensive one.
**Status.** Density passed. Untested: does repricing produce anything usable.

## P-REFEREE · open peer review objections
**The cheat.** Strictly more than a confession. A referee says *"the authors
should have checked Y"*; the authors reply *"beyond the scope of this work."*
That is an expert-identified gap, an expert-endorsed method, and a documented
admission nobody did it — all three published.
**Tell.** Venues that publish review files (eLife, PeerJ, F1000, Nature Comms
opt-in). The reply phrase `beyond the scope`.
**Kills it.** Whether review files are machine-fetchable at volume. If they are
locked behind per-article HTML with no API, the supply is unreachable.
**Why it may be the best.** The gap has already survived a second expert's
judgment that it mattered. Nothing else here has that.

## P-CONCLUSION · future-work mining
**The cheat.** The last paragraph of every paper is **a curated to-do list
written by the person who knows most about the problem** — and it is the most
systematically skipped section in science.
**Tell.** `future work` · `it would be interesting to` · `remains to be` ·
`we have not addressed` · `a natural extension`
**Kills it.** Yield of *actionable* items. "Future work" is often ritual filler
appended to satisfy a reviewer. If under ~5% name something specific and
bounded, the section is decoration and the pot is empty.
**MEASURED 2026-08-25 — FAILED.** Same 51 papers, same method: **29% carry a
future-work statement, only 2% name anything specific** — five times worse than
P-CONFESSION. I predicted this would be the best pot on the list.

**Why, and it is the useful part:** *"future work" is usually the authors' own
next paper.* One sample reads *"we intend to compute the structure constants
using a similar approach as in ref. [36]"* — that is not territory being
released, it is territory being **claimed**. A confession is an admission of
defeat; a future-work statement is a flag planted. The rest were scope notes
(*"we shall not discuss"*) or filler (*"useful as a benchmark for future
investigations"*).

**Kept on the list, marked failed, with the reason.** A pot measured and dead is
worth more than the six below it that are merely untested.

## P-ASSUMPTION · "we assume X for simplicity"
**The cheat.** The author flagging what they know is wrong with their own model.
Removing it is a **fully-defined project with a built-in comparison** — their
number against ours. Fully-defined projects are the scarce good, not compute.
**Tell.** `for simplicity we` · `we assume` · `neglecting` · `to leading order`
· `in the limit of`
**Kills it.** Most such assumptions are load-bearing for tractability, not
laziness — removing them is the hard research problem, not a follow-through.
Needs a filter for *cheaply removable*.

## P-ORPHAN · datasets and code nobody used
**The cheat.** Somebody spent three years and a grant collecting it. **The
expensive half is done and paid for.** Same for released code with zero forks:
the implementation exists and was never independently run.
**Tell.** Zenodo/Dryad/figshare DOIs with zero citing works; paper-linked GitHub
repos with 0 forks and 0 issues.
**Kills it.** Orphaned usually means *uninteresting*, not *overlooked* — this is
the fame-scoring error wearing new clothes. Needs the "who reads the answer"
half of the two-sided filter more than any other pot.

## P-DISCREPANCY · published numbers that disagree, flagged by a third party
**Found inside P-CONCLUSION's failure**, which is the only thing that pot
produced. One sample read:

> *"the discrepancy between **ν = 0.689(5)** and **ν = 0.7112(5)** observed in
> [1,14] **remains to be understood**"*

**The cheat.** Two published values, with error bars, that disagree — and a
THIRD party who is neither author has already established the disagreement is
real and stated that it is unresolved. We do not have to notice it, adjudicate
whether it is genuine, or trust our own reading.

**Why it survives the rule that killed Daido-vs-Hong.** That cost four GPU-hours
because I could not tell a *dynamic-fluctuation* susceptibility from a
*linear-response* one — a CONCEPTUAL contradiction, which needs domain fluency
we do not have. A NUMERICAL discrepancy between two stated values is arithmetic,
and somebody else already did the conceptual work of confirming the two numbers
are comparable.

**Tell.** `discrepancy between` · `in disagreement with` · `differs from the
value reported` · `remains to be understood` — **with two numbers inside the
window.**

**Kills it.** Whether the flagging third party is usually just wrong, and whether
the disagreement was resolved after the flagging paper was written. Untested.

## P-BOUND · verification bounds on conjectures
**The cheat.** `"verified for all N up to 10^12"` — dated, numbered,
hardware-limited. **A stale edge that arrives pre-formatted with its own number.**
**Tell.** `verified (up to|for all)` · `exhaustive search up to` · `no
counterexample below`
**Kills it.** These are the most-watched records in their spaces and
distributed-computing projects already grind them. Only viable on an OBSCURE
bound nobody is chasing — which collides directly with "does anyone care."

## P-ERRATUM · corrections nobody propagated
**The cheat.** A correction is published; papers keep citing the original number
afterwards. Mechanically findable: erratum date versus citation date.
**Tell.** OpenAlex `is_retracted`, erratum-type works, and their citation
timelines.
**Kills it — and this one is not technical.** This is auditing other people's
published work. Done carelessly it makes us the group nobody collaborates with.
**Binding rule if we ever run it: findings go to the authors first, framed as
"we may be wrong," never as a public gotcha.**

## P-DRIFT · version drift
**The cheat.** A library changed behaviour at v2.0; every result computed with
v1.x may no longer reproduce. Detectable from dependency pins in released code.
Nobody checks, because nobody re-runs.
**Tell.** `requirements.txt` / `environment.yml` in paper-linked repos, pinned
below a known breaking release.
**Kills it.** Requires the code to actually run, which is the historical failure
point of reproduction attempts. B measured 89% of *papers* fetchable; nothing
measured what fraction of *code* executes.

---

## Order of attack

By cheapest decisive gate, not by attractiveness:

1. ~~**P-CONCLUSION**~~ — **run 2026-08-25, failed at 2%.** See above.
2. **P-DISCREPANCY** — same grep, same corpus, one hour. Came out of the failure
   above and is the most promising thing on this page.
3. **P-REFEREE** — one API probe answers whether the supply is reachable at all.
4. **P-ASSUMPTION** — same corpus again; the question is filterability.
5. **P-ORPHAN** — needs the who-reads-it gate before any tooling.
6. **P-DRIFT / P-ERRATUM / P-BOUND** — last, each for its own reason above.

## The scoreboard for the day these were written

Five predictions tested, **four killed** — an 80% kill rate against the 60.5%
that Registered Reports report for a priori hypotheses. Wrong about: the HP
table being wanted, the attribution graph being usable, paper inputs being
unreachable, and P-CONCLUSION being the best pot. Right about: confession
density.

Every kill cost under an hour and produced a number. Both survivors —
P-CONFESSION and P-DISCREPANCY — came out of failures rather than from planning.

**None of these needs infrastructure to test.** Every gate is a search, a fetch
and a grep, which is exactly how all four of today's gates were answered.
