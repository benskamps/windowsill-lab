# Migration order — inculcating the research doctrine

**2026-08-25 · produced by a 10-agent adversarial audit (`wf_b454de68-bb2`), 1.1M tokens.** Five pillar audits against the real codebase, one synthesis, three adversarial refutations, one reconciliation. Every item is judged against F1-F7 — the lab's *actual* failures of 2026-08-24/25, not hypothetical ones.

## Verdict

This lab's instruments are excellent, its terminus is missing, and every scoring surface
it publishes is a function of prose the graded party wrote. 161 receipts, 33 checker
functions, a 4,507-line checks.py, a public feed — and the one lane that makes a claim
about the world governs 2 of 33 experiment families (a Hypothesis is constructed at
u_a01_attempt.py:79 and h01_bbp_tail.py:23, nowhere else) while being the only lane with
no entry in the CHECKS registry (checks.py:4374 lists 33 milestone ids, no H01, no
U-A01). The seven failures are three. (1) THE CATALOGUE CANNOT HOLD WHAT MATTERS:
Unknown's six REQUIRED fields (unknowns.py:69-70) include no citation and no attack, so
the only thing that CAN be typed beside a problem is `importance: int = 3`
(unknowns.py:92), range-checked and nothing else, and it is the sole sort key of the
only scheduler (unknowns.py:150-153). Fame is scored because fame is the only field that
exists. (2) EVERY DENOMINATOR IS AUTHORED BY THE GRADED PARTY: goal.py:93 derives the
track universe from surviving unknowns, so retiring the failing entries deletes the
requirement — verified live, `every_track_charted` is True with
`tracks_without_a_charted_unknown: []` while U-C01 (track C) and U-I01 (track I) sit
RETIRED and neither track carries a live entry; `attempted` is `"ATTEMPTED" in
u.reach_evidence` (goal.py:101-102), a substring search in a markdown file the grading
agent edits; and `EXEMPT_TRACKS` at goal.py:48 is dead code the original plan was about
to wire a live denominator through. (3) THE CARE STOPS AT THE TELLING, AT A THIRD
RADIUS: `Finding.__post_init__` guards new_observations by truthiness, so `{"note": "we
looked"}` passes — I constructed it; `k03._verdict` is an argmin that returns
`nearest='daido'` at 46.2σ from Daido and 49.8σ from Hong on the real 2026-08-23
numbers, so the most informative outcome available (both published rivals excluded) is
not expressible in the return type; the pre-registered rule's clause 5 exists as
docstring at u_a01_attempt.py:47-48 and zero lines of code while `"disposition":
"harmonic-alias"` sits in the receipt's own bytes; `provenance.source_clean` is computed
at render.py:128 and read by nothing in src/; and this morning's correction cannot ship
at all — REANALYSED is in VERDICTS (hypothesis.py:46) but absent from
headline()/boundary() (:199-222), so `to_report()` raises KeyError('reanalysed'), 3
tests are red, the committed receipt still reads `verdict: killed / status: pass`, and
pot.json still publishes `goal.state: MET` while the working tree computes OPEN. The lab
is, in public, right now, wrong in the flattering direction about the only claim it has
ever made. Underneath all of it sits the fact the original plan named in a footnote and
I have promoted to item 5: after twelve items of apparatus, this lab has still never
gone outside, and the sharpest number in this audit is that the ancestry check proposed
to prevent the 2026-08-25 self-graded run would have passed it by eighty-eight seconds.

## The binding order

### 1. STOP PUBLISHING THE FALSEHOOD; MAKE THE TELLING TOTAL

STOP PUBLISHING THE FALSEHOOD; MAKE THE TELLING TOTAL. Replace the three-key dict
literals in `headline()` (src/lab/hypothesis.py:199-204) and `boundary()` (:206-222)
with a module-level VERDICT_PROSE beside VERDICTS (:46), plus `assert set(VERDICT_PROSE)
== set(VERDICTS)` at import. `to_report()` (:182-197) stops emitting `status` and emits
`instrument: "ok"|"degraded"` DERIVED INSIDE the method from `self.controls` — never
accepted as an argument, because a self-attested `instrument` is the self-attested
`status` with a new name (refutation 2's hole 9 lands here). Today hypothesis.py:186
writes a KILLED hypothesis as `status: "pass"` while 33 calibration runners write
`"pass" if calibration_passed else "null"` (a01.py:706, c01.py:118), so one key means
two opposite things. cli.py:2689 `return 0 if finding.decided else 1` becomes `return 0`
whenever a receipt was written. Then: regenerate
reports/receipts/run-2026-08-25-0811-u-a01.json (it reads `verdict: killed / status:
pass / attempted_the_question: null` on disk right now), fix the 3 red assertions at
tests/test_u_a01_attempt.py:83,:112,:122, republish pot.json, `git add
docs/doctrine/research-doctrine.md`, and COMMIT the working tree (`M UNKNOWNS.md, M
hypothesis.py, M u_a01_attempt.py` today) so item 3 has a clean baseline to grade
against.

- **Makes unconstructible:** A verdict that is legal to construct but impossible to write to a receipt.
  REANALYSED is in that state right now, and the pressure it creates is to relabel a
  re-analysis as a kill — F4's exact mechanism, re-armed as a crash. Also
  unconstructible: a killed hypothesis reading `status: pass`, and a new self-graded
  prose field on the one lane that makes claims about the world.
- **Catches:** F4, F5
- **Why here:** Nothing else can be published until it lands — every later item ends in 'and
  republish', and republish raises KeyError('reanalysed') today, verified. It is
  also the fastest route to ending a live public falsehood: pot.json publishes
  `goal.state: MET` while `goal.progress()` returns OPEN. I ran both.
- **Cost:** ~30 agent-min. ~15 lines in hypothesis.py, 1 in cli.py, 3 test assertions, 2 regenerated artifacts, 1 git add, 1 commit.
- **Known when:** `Finding(..., verdict=REANALYSED).to_report()` returns a dict. `pytest tests/test_u_a01_attempt.py -q` → 9 passed. The committed receipt reads `verdict: reanalysed`, carries no `status` key, and `instrument` is absent from every constructor signature. pot.json `goal.state` reads OPEN. `git status -sb` is clean.

### 2. DENOMINATORS THE RUN DOES NOT AUTHOR — AND CANNOT SHRINK BY ANY ROUTE

DENOMINATORS THE RUN DOES NOT AUTHOR — AND CANNOT SHRINK BY ANY ROUTE. (a) `Goal` gains
`set_on_commit: str`; goal.py:92-96 stops deriving tracks from survivors and reads `git
show <set_on_commit>:TRACKS.md` through `frontier.parse_tracks`, minus EXEMPT_TRACKS. A
goal set on a date is graded against the world as it stood on that date. I take
refutation 2's git-historical read over refutation 1's `tracks_required` literal on the
frozen Goal, because a literal tuple in goal.py is exactly refutation 3's EXEMPT_TRACKS
hole one line over — the fix would have reproduced another refutation's finding. (b) Pin
the exemption: `EXEMPT_TRACKS = frozenset({'B'})` with `assert EXEMPT_TRACKS ==
frozenset({'B'})` as a test, so growing it turns CI red and requires an arguable commit.
(c) Delete goal.py:101-102's `"ATTEMPTED" in u.reach_evidence` — a substring search in a
markdown file the grading agent edits — and derive `attempted` from the receipt ledger.
(d) `check_unknowns_ledger` in CHECKS (checks.py:4374): every `U-` id appearing in any
committed receipt or in the previously committed pot.json must still parse out of
UNKNOWNS.md with a live status. Item 7 makes a wrong RETIREMENT expensive; without this,
`git rm` of the `## U-C01` block is twelve keystrokes and strictly cheaper than what the
lab actually did. (e) Any unknown whose `reach_evidence` asserts a literature closure
without a verified Source loads as RETIREMENT_DISPUTED — on the board, in every
denominator, printed daily. U-C01 flips to it on day one and stays until Ben reads the
paper. (f) Rewrite tests/test_goal.py:81-88, whose docstring says retiring an unknown
'must not be able to move the goal by itself in either direction' and whose assertion
proves the opposite; replace with a ratchet against the LAST PUBLISHED pot.json — no
commit may increase the satisfied-condition count while `unknowns_total` or the track
denominator decreases. (g) ci.yml:41 recomputes only `pot.json['milestones']`; add
`goal.progress()`.

- **Makes unconstructible:** Meeting a goal condition by subtraction, through every route the three refutations
  found. F3 verbatim: retiring U-C01 and U-I01 removed tracks C and I from their own
  denominator and `every_track_charted` went True — verified live, it reads True
  with `missing: []` while both tracks carry no live entry. After (a) it reads False
  with ['C','I']. After (b) adding a letter to a tuple cannot do it. After (d)
  deleting a markdown block cannot do it. After (e) a wrong retirement is loud
  instead of dormant. And after (g), a stale published goal is as impossible as a
  stale milestone list — the one number CI structurally could not catch.
- **Catches:** F2, F3, F4
- **Why here:** Second because it is the only item that makes the public feed self-correcting, and
  every later change rides in that block. It also closes the mechanism that would
  otherwise silently absorb item 7: demoting U-M01 for having no attack would,
  today, IMPROVE the goal.
- **Cost:** ~45 agent-min. `frontier.parse_tracks` and publish.py's `_git` helper already exist; parse_tracks(TRACKS.md) returns ['A','B','C','I','K','M','P'] today. Expect CI RED against the committed pot.json — that is the gate working.
- **Known when:** `lab goal` prints state=OPEN, `tracks_without_a_charted_unknown: ['C','I']`. Re-adding the word ATTEMPTED to UNKNOWNS.md changes no number. Adding 'I' to EXEMPT_TRACKS turns a test red. `git rm` of a catalogued id turns CI red. `lab unknowns` prints U-C01 as RETIREMENT_DISPUTED.

### 3. TYPE THE TERMINUS BY CONTENT, NOT BY CLOCK — AND LAND THE ANCESTRY HALF NOW, NOT AT POSITION 10

TYPE THE TERMINUS BY CONTENT, NOT BY CLOCK — AND LAND THE ANCESTRY HALF NOW, NOT AT
POSITION 10. All three refutations killed the plan's original item 3 and they are right:
comparing a self-reported ISO string to a self-reported `registered_at` refuses a badly
formatted string, not a re-read. `{"reports/hunts": <now>}` is the HONEST thing a re-
reading runner records. Replace with: `new_observations: dict[str, Observation]` where
each is `{path, sha256, n_bytes, kind: "external-fetch"|"new-compute"}`, written under
`evidence/observations/<run-id>/`. The grader recomputes each sha256 and REFUSES if `git
cat-file -e <registration-commit>:<path>` succeeds — the bytes must not have existed in
the repo when the question was asked. That is arithmetic, not the runner's honesty about
its own clock. Delete `registered_at` as an authored field; use the registration COMMIT
time. Then the four ordering facts, all cheap, all using machinery already present: (i)
compare the registration commit's committer-date against the RECEIPT'S COMMIT date —
both authored by git, neither typed, whereas `generated_at` is `datetime.now()` at
render.py:123 inside the graded process; (ii) pin BOTH the hypothesis blob AND the
grader blob, or the fudge migrates from the runner into `grade_hypothesis`; (iii)
require the registration commit present on `origin/main` — origin exists
(github.com/benskamps/windowsill-lab) and a push is the one clock this box cannot
backdate; (iv) require ≥12h between registration and run. On (iv): the 2026-08-25 U-A01
receipt's `generated_at` is 12:11:30Z and its `source_commit` 4832d91 was committed at
12:10:02Z. EIGHTY-EIGHT SECONDS. The original item 7's ancestry check passes the very
run it was designed to prevent. Finally, `render_calibration` refuses any receipt
carrying a `hypothesis` block when `provenance.source_clean` is false — DELETE the
plan's 'unless the diff is written to evidence/' escape, which render.py:124-131 already
has the diff sitting in a local variable to satisfy. Scope to hypothesis receipts; the
22 dirty calibration receipts and the whole ladder are untouched. Note the shipped U-A01
receipt records `source_clean: false` while UNKNOWNS.md asserts the rule was committed
in advance — that is `grep source_clean src/` returning ONLY the write site
(render.py:128) and nothing that reads it.

- **Makes unconstructible:** A discovery verdict derived from bytes that already existed at registration —
  refused by hash arithmetic, not by a board. A pre-registration claim that cannot
  be checked. A run whose registration was committed ninety seconds earlier by the
  same session holding the same expectation. And a grader authored after the numbers
  it grades.
- **Catches:** F4, F6
- **Why here:** Third and not tenth. Refutation 1's ordering hole is correct: the plan posed the
  rival contract at 5 and the ancestry check at 7, so between them every rival could
  be authored after the data was seen and the receipt would look compliant forever.
  The ancestry half has no dependency on the rival types and belongs here, beside
  the provenance work, before the first attempt exists.
- **Cost:** ~45 agent-min. ~25 lines in hypothesis.py, ~25 in render.py, three `_git` calls next to publish.py:587's existing helper.
- **Known when:** Re-running `u_a01_attempt.run()` against the committed hunt archive raises rather than returning any deciding verdict. A hand-constructed receipt with a plausible future ISO timestamp and no stored bytes is refused. The 2026-08-25 run fails the 12h test explicitly, naming 88 seconds.

### 4. THE DISCRIMINATION ARITHMETIC — the only apparatus that goes BEFORE the spend, and nothing else from the rival contract

THE DISCRIMINATION ARITHMETIC — the only apparatus that goes BEFORE the spend, and
nothing else from the rival contract. Add `Rival(name, claim, predicts, source,
excluded_when)` with `predicts: {observable, value, resolvable_at}` — a number and a
resolution, NOT a string. `Hypothesis.__post_init__` refuses when `stage == DISCOVER`
and any two rivals satisfy `abs(v_a - v_b) < max(resolvable_at_a, resolvable_at_b)` on
the observable named by `discriminates_on`: 'this experiment cannot tell these two
apart'. Refutation 2 is right that textual inequality is a string test that the plan's
own nominated fixture would have passed — DAIDO and HONG (k03.py:88-93) differ in
`gamma_prime` and AGREE on `gamma` at 0.25, so a wording check fires on exactly the
wrong branch. Lift both in as the regression fixture: RAISE on `gamma`, PASS on
`gamma_prime`. Then move `DISCRIMINATING_GAP = 0.75` (u_k01_window.py:57-59) and
`note_on_discrimination` (:177-182) out of module prose into the Rival pair. That note
currently reads, in shipped code, 'Daido and Hong predict the SAME supercritical γ =
0.25, so the above branch has no discriminating power at all' — the estate discovered
this by hand AFTER spending four GPU-hours on that branch, wrote it down as a comment,
and never promoted it to a constructor.

- **Makes unconstructible:** A proposal whose two rivals make indistinguishable predictions on the observable
  being measured. That is not hypothetical: it is the K03 design defect, it cost
  four GPU-hours, and it survives today only as a module constant and a prose note
  found by a human reading two papers after the money was spent.
- **Catches:** F5, F7
- **Why here:** Fourth and immediately before the run, because it is the one piece of apparatus that
  changes whether the run is worth doing. Refutation 3's cut — 'stop at 3 and go run
  something' — is right in spirit and one item too deep: cutting here would ship
  U-K02 with the degenerate-design risk unguarded, and K03 already demonstrated that
  exact failure at a cost of four GPU-hours. Fifteen minutes of arithmetic protects
  3.1 GPU-hours. Everything ELSE from the original rival contract waits behind the
  receipt.
- **Cost:** ~25 agent-min. One dataclass, one constructor refusal, two tests. Blast radius is two files — only two runners in the estate construct a Hypothesis.
- **Known when:** `Hypothesis(stage=DISCOVER, rivals=(DAIDO, HONG), discriminates_on='gamma')` raises; the same pair on `gamma_prime` passes.

### 5. GO OUTSIDE

GO OUTSIDE. RUN U-K02. Write `src/lab/u_k02_attempt.py` — `u_k02_reach.py` exists and
priced it; there is no attempt runner and `grep -rn 'u-k02' src/lab/cli.py` returns
nothing. Register the hypothesis (Daido γ'=1.0 vs Hong γ'=0.25 on the subcritical
branch, rivals typed under item 4, both already carrying full citations at
k03.py:88-93), push it to origin/main, wait the 12h, then spend the 3.1 GPU-hours:
N=200,000 on the RX 6900 XT, ε-scaled `T_MEASURE`, ε floor raised per the entry's own
`if out of reach` — and DO NOT trim `T_MEASURE`, the one axis the catalogue explicitly
forbids cutting. Write every column to `evidence/observations/<run-id>/` so item 3's
hash gate has bytes to verify. Publish whatever comes back: supported, killed,
unresolved, or 'the noise did not fall the way ε^-0.76 predicted and this is a second
reach failure'. All four are results. THIS ITEM IS THE GATE — items 6-12 may not be
started until this receipt exists.

- **Makes unconstructible:** A lab that has built twelve layers of anti-fooling apparatus and never gone outside.
  Also: seven items of guesswork about what an attempt needs, written by a lab that
  has not made one — after this receipt, items 6-12 are graded against a real run
  instead of an imagined one, and some of them will turn out to have been
  unnecessary.
- **Catches:** F4, F7
- **Why here:** Fifth, and the whole document exists to get here. Refutation 3's central hit lands
  and I am not defending against it: nine items of anti-fooling apparatus, ~4.5
  agent-hours, on a lab that has never made one attempt, executed at 8pm-2am by
  someone with a day job, IS the Eternal Surveyor relocated from feasibility-testing
  to meta-instrumentation. The original plan's own final bullet conceded that items
  1-9 are 'scaffolding around an empty room' and then left the concession as a
  footnote. It is now item 5. U-K02 is the only live entry whose importance is
  earned by an opening rather than a name: 42σ of headroom, a 0.75 gap against a
  demonstrated stderr of 0.0177, two published papers that directly contradict each
  other on a class this engine was verified to reproduce term for term.
- **Cost:** 3.1 GPU-hours plus ~60 agent-min of runner. Requires Ben to authorise the GPU time — one line, not a blocker.
- **Known when:** `reports/receipts/run-*-u-k02.json` exists, carries `stage: discover`, `attempted_the_question: true`, `new_observations` whose sha256s the grader verifies as absent from the registration commit, and a verdict naming which of Daido or Hong this measurement excludes — or honestly excluding neither.

### 6. GRADE THE GOAL LIKE A HYPOTHESIS

GRADE THE GOAL LIKE A HYPOTHESIS. `progress()` may emit `MET_PENDING_ATTESTATION` but
never `MET` unless a `goal-attestation` receipt exists naming, per condition, the
receipt id that satisfies it — and `check_goal`, registered in CHECKS and run by `lab
verify` in CI, re-derives each condition from those ids. Refutation 1 found the hole no
item covered and it is F5 as it literally happened: the thing that got three rounds of
adversarial scrutiny was the disliked K03 number, and the thing that got zero was 'G01
MET' — which was never a hypothesis at all, so every rival, grader and receipt mechanism
in this document routes around it. Item 2(g) catches a HAND-EDITED goal block; it does
not catch a goal that became true by a mechanism nobody examined, which is exactly what
happened on 2026-08-25.

- **Makes unconstructible:** A goal that reaches MET by subtraction. After item 2 the conditions cannot be shrunk
  into; after this, a condition that became true with no receipt to point at cannot
  render as MET at all — it renders as pending, publicly, until something is named.
- **Catches:** F3, F5
- **Why here:** Sixth, immediately after the run, because the attestation needs a real receipt id to
  name and item 5 produces the first one. This is the machine half of the
  asymmetric-publication question; Ben's signature is the policy half and sits on
  top of it, not instead of it.
- **Cost:** ~30 agent-min. One check function, one lifecycle state, one CI line.
- **Known when:** Deleting the U-K02 receipt flips the published goal from MET to MET_PENDING_ATTESTATION rather than leaving it green.

### 7. THE CATALOGUE GETS A SOURCE AND AN ATTACK THAT ARE ARTIFACTS, NOT SENTENCES

THE CATALOGUE GETS A SOURCE AND AN ATTACK THAT ARE ARTIFACTS, NOT SENTENCES. This is the
most heavily amended item; the original was the plan's weakest and all three refutations
landed on it. (a) NOT a citation regex. `Source(identifier, retrieved_at, sha256,
quote)` with the retrieved bytes stored at `evidence/literature/<slug>.txt`;
`check_literature` in CHECKS recomputes the sha256 AND asserts `quote` is a literal
substring of those bytes. No network in CI — the check grades the stored artifact. A
recollection cannot produce a verbatim span that substring-matches bytes on disk; a
fetch can, and this box has WebFetch. The plan's 'contains a URL or a bracketed 4-digit
year' was laundering: F1/F2 were confident recollection, not omission, and
UNKNOWNS.md:142 ALREADY reads 'Believed closed by Borwein, Borwein & Galway (2004)' —
the wrong retirement passes the proposed validator after changing one parenthesis. (b)
An unknown may sit at CLAIMED with no Source, but `crosses_the_gate` requires one, so an
unsourced entry cannot be CHARTED and cannot enter the gate ratio. (c) `Attack` with
`opening`, `why_not_already` (itself a literature claim, so it inherits (a)), and three
fields that are things rather than essays: `first_experiment` must IMPORT and resolve to
a `Hypothesis` whose `unknown_id` matches — 'we have an attack' then means 'the runner
exists'; `price: {receipt_id, quantity, units, kind: MEASURED|FLOOR}` looked up in
reports/receipts/, with FLOOR capping importance exactly as OUT_OF_REACH does;
`would_abandon_if: {observable, comparator, threshold}` with an evaluator in checks.py
that scans the ledger each publish and auto-flips the unknown to NO_ATTACK — a
predeclared abandonment nobody computes is a mood. (d) LIFECYCLE becomes (CLAIMED,
CHARTED, NO_ATTACK, ANSWERED, RETIRED, RETIREMENT_DISPUTED). NO_ATTACK stays in every
denominator. RETIRED narrows to 'this was never a question' and needs a verified Source
plus a stated SCOPE. (e) DELETE `importance` (unknowns.py:92) and derive it; the parser
RAISES on a legacy `**importance.**` line rather than skipping, consistent with
unknowns.py:196-197. The `consequence` integer moves to the operator ledger (see item
12) because refutations 1 and 2 are both right that `consequence: int` typed in the same
file by the same author is the same keystroke wearing a new name. (f) DROP the plan's
`holds_up_if` — refutation 2 is right that a mandatory paragraph on the favourable side
buys a paragraph and costs a field; the symmetry comes from item 8's artifact rival,
which must compute.

- **Makes unconstructible:** An entry catalogued from recollection: the machine gate is a verbatim span matching
  stored bytes, which memory cannot produce. A famous problem entered on the
  strength of its name: U-M01's `who_would_care` — 'the spin-glass community, and by
  extension everyone who borrows its language' — is pure consequence argument,
  exactly what Hamming rules out, and it cannot fill `first_experiment` because no
  spin-glass discriminating runner exists in src/. Its 11-GPU-day figure is forced
  to declare itself a FLOOR. And 'we have no attack' no longer requires DELETION to
  express, which was the only motive the lab ever had for shrinking its own
  catalogue.
- **Catches:** F1, F2, F7
- **Why here:** Seventh because it is upstream of the scheduler and the gate ratio but must follow
  item 2, or demoting U-M01 would improve the goal — and must follow item 5, because
  writing five honest Attack fields is easier once the lab knows what an attempt
  actually consumed.
- **Cost:** ~60 agent-min of code plus the expensive part, which is not code: fetching and quoting a real source for each live entry. That fetching IS the audit. HONEST LIMIT, stated in the code comment: this defeats FABRICATION and does not defeat MISREADING. F2 was a scope error about a real paper — the bytes would have hashed fine. Only a human reading the abstract defeats F2, which is why item 12 exists.
- **Known when:** `lab unknowns` refuses to load today's catalogue and names U-M01. `grep -c importance UNKNOWNS.md` returns 0. `evidence/literature/` contains fetched bytes for every charted entry and `lab verify` grades their quotes.

### 8. THE REST OF THE RIVAL CONTRACT, AND AN ARTIFACT RIVAL THAT MUST COMPUTE

THE REST OF THE RIVAL CONTRACT, AND AN ARTIFACT RIVAL THAT MUST COMPUTE.
`Hypothesis.__post_init__` additionally refuses, for DISCOVER: fewer than 2 rivals;
blank `discriminates_on`; any rival with no verified Source; and no rival whose `source`
starts with `ours:` — but the prefix alone is not the gate. Refutation 2 is right that
seven characters of typing is not the three rounds of scrutiny K03 received. So: an
`ours:` rival's `excluded_when` must NAME A KEY, and `grade_hypothesis` refuses to grade
when that key is absent from `Finding.controls`. The estate already has the machinery —
the scramble null at u_a01_attempt.py:110-131 IS an instrumental-artifact exclusion,
computed, with a number. `Finding` gains `excluded`/`survived`, must disposition every
posed rival, refuses an undispositioned rival, refuses a name not in the posed set, and
refuses `stage == DISCOVER and verdict in (SUPPORTED, KILLED) and not excluded`.
Explicitly ALLOW `excluded == all rivals` with its own headline. Add
`expected_to_survive: bool`, fixed at registration — item 12 publishes how often the
excluded rival was the one the lab already disbelieved. That is the single number in
this document a motivated agent cannot move without changing what it does, and it is
Millikan MEASURED rather than attested. DO NOT require rivals on CALIBRATE: H01's honest
pair is 'float64 is fine' / 'float64 is not fine', a hypothesis and its negation, the
one pairing Chamberlin's method exists to forbid. Calibrate gets `arbiter_at_the_claim`,
refused when a CALIBRATE run returns KILLED without one — and fix H01 in the same pass:
its Machin arbiter runs only at control positions 0/16/1000 (h01_bbp_tail.py:131-140),
while the deep verdict at 10^7 (:151-153) compares two of our own paths and retracts
C05's digits (:167-172) on a truncation bound asserted in a docstring. Recompute at the
deep position with an independent higher-precision pass; the move already exists in the
suite at shallow depth (tests/test_hypothesis.py:94-98) and was left there instead of
put in the runner.

- **Makes unconstructible:** A DISCOVER run that answers only 'did I survive' and never 'what did I kill'. A
  rival invented after the data is seen, or posed at write time and quietly dropped
  at analysis time — u_a01_attempt.py's clause 5 says `disposition` at lines 16 and
  48, both docstring, zero lines of code, while `"disposition": "harmonic-alias"`
  sits in the receipt's own bytes. An artifact rival discharged by a sentence rather
  than a control. And a CALIBRATE run retracting one of our published numbers with
  the arbiter exercised only where the verdict is not issued.
- **Catches:** F5, F6
- **Why here:** Eighth, after the run, because item 5 will have shown which of these constraints an
  attempt actually needed. Ordering matters less than it looks: item 3 already
  landed the ancestry pin, so anything posed here is pinned from the day it lands.
- **Cost:** ~50 agent-min. H01's extra exact pass at d=10^7 adds one to two minutes to a 57.6s run — the excluding experiment was always affordable.
- **Known when:** `Finding(stage=DISCOVER, verdict=KILLED, excluded=())` raises. An `ours:` rival whose `excluded_when` key is missing from controls refuses to grade. Monkeypatching H01's exact path to disagree at depth yields UNRESOLVED, not an accusation.

### 9. RETIRE THE ARGMIN

RETIRE THE ARGMIN. Rewrite `k03._verdict` (src/lab/k03.py:373-389) around the Rival
type: add `EXCLUDE_SIGMA = 3.0` and return `{excluded, survived, sigma: {name: d},
discriminating: bool}`. Four expressible outcomes instead of one — exactly one survives,
both excluded, neither excluded (UNRESOLVED), a branch unmeasured. DELETE `nearest` from
the return, from every K03 receipt, and from the public page.

- **Makes unconstructible:** Naming a winner between two published claims when the measurement is far from both.
  I ran the shipped function on the real 2026-08-23 numbers:
  `_verdict({'gamma':1.064,'err':0.0177},{'gamma':1.20,'err':0.05})` returns
  `nearest='daido'` at 46.2σ from Daido and 49.8σ from Hong. It manufactures an
  adjudication where none exists. After this it returns excluded=['daido','hong'],
  survived=[] — which is either a real result or a loud signal the window is wrong,
  and it is unsayable today because 'both excluded' is not in the return type.
- **Catches:** F5, F7
- **Why here:** Ninth: it needs the Rival type and it is the cheapest proof the type earns its keep.
  It is also the only place a real published-claim adjudication currently happens.
- **Cost:** ~25 agent-min. One function, 3 tests, one touch to check_k03 (checks.py:3930), which gates measurement validity only. Pays the SURFACE CONTRACT debt for item 12 by retiring a published key.
- **Known when:** `grep -rn nearest reports/receipts/ pot.json` returns nothing. A regression test asserts a measurement 40σ from both claims excludes both and names neither.

### 10. TAKE THE VERDICT AWAY FROM THE RUNNER

TAKE THE VERDICT AWAY FROM THE RUNNER. Runners return `Observation(evidence, controls,
new_observations, wall_seconds)` with NO verdict field. The verdict is computed only by
`checks.grade_hypothesis(hypothesis, observation)`, registered in CHECKS
(checks.py:4374-4387, which today lists 33 milestone ids and neither H01 nor U-A01) and
invoked by `lab verify` in CI. Each hypothesis's grading law lives in
`src/lab/grading/<id>.py` so its blob sha is stable and item 3's ancestry pin does not
invalidate every prior receipt when an unrelated check changes. `lab publish` refuses a
DISCOVER receipt with a null verdict. Move `PROMOTE_MAX_BACKGROUND`
(u_a01_attempt.py:71) and `MIN_NULL_DRAWS` (:75) out of the runner into the graded
hypothesis.

- **Makes unconstructible:** A run that grades itself — not a rule against it, an absent field. Also: a receipt
  whose advertised reproduction path silently grades nothing. `lab verify U-A01`,
  the command printed in the shipped receipt's own `reproduction.regrade`, prints
  'no verified milestones to check' and exits 0. I ran it.
- **Catches:** F6, F5
- **Why here:** Tenth. The ancestry half already landed at item 3; this is the code-path split,
  which needs item 8's rival dispositions to have anything to compute. This is the
  only mechanically enforceable half of Kahneman in a one-operator estate —
  independence of code path and commit ordering, never independence of persona.
- **Cost:** ~45 agent-min, mostly moving verdict branches out of two runners into one grader.
- **Known when:** `grep -rn 'verdict=' src/lab/u_a01_attempt.py src/lab/h01_bbp_tail.py src/lab/u_k02_attempt.py` returns 0. `grep -c PROMOTE_MAX_BACKGROUND src/lab/u_a01_attempt.py` returns 0. A hand-edited verdict turns CI red.

### 11. REPLACE THE DEAD-END SCHEDULER

REPLACE THE DEAD-END SCHEDULER. `unknowns.next_to_test` (unknowns.py:140-153) filters
`reach == UNTESTED` and is the module's only selector. Every live unknown has been
priced, so it returns None — I confirmed `frontier.board()['next_reach_test'] is None`
and `untested == 0`, and cli.py:2649 prints 'the next move is an attempt, not another
feasibility test' to nobody. Add `next_to_attempt`: highest derived importance among
entries with a resolving Attack, `reach == IN_REACH`, and an UNSPENT attack — where
spent is derived from the receipt ledger and never from a typed field: a Finding whose
`hypothesis.unknown_id` matches and whose `attempted_the_question` is true, which item 3
made impossible to fake. CONSUMER: the existing `lab unknowns` board (cli.py:2646-2657)
and `frontier.board()['next_reach_test']`. CADENCE: every heartbeat/publish. RETIRES the
terminal print. No new surface.

- **Makes unconstructible:** The Eternal Surveyor, structurally: once everything is priced the dispatcher has
  exactly one thing left to name and it names it. And an attack marked spent by re-
  reading the archive.
- **Catches:** F4, F7
- **Why here:** Eleventh: needs derived importance from item 7 and ledger-derived spentness from
  item 3.
- **Cost:** ~30 agent-min.
- **Known when:** `lab unknowns` names a concrete next attempt instead of a dead end, and U-A01 shows UNSPENT despite the 08-25 run — the correct reading of a re-analysis.

### 12. THE LEDGER AND THE OPERATOR FILE — the one new surface, and it pays its debt

THE LEDGER AND THE OPERATOR FILE — the one new surface, and it pays its debt. A
`kill_ledger` block in pot.json and a `── kill ledger ──` section on `lab frontier`,
rendering TWO denominators the renderer has no code path to blend: (a) DISCOVERY —
stage=discover Findings with hash-verified observations, split
supported/killed/unresolved/reanalysed, with `rivals_posed`, `rivals_excluded`,
`cost_per_exclusion` in GPU-hours, and `excluded_the_rival_we_disbelieved: n/N` from
item 8's `expected_to_survive`; (b) CALIBRATION, separately labelled, with 'known
answers; a high pass rate here is the instrument working'. NO PERCENTAGE TARGET IS
RENDERED. Both refutation 2 and refutation 3 land here and I am not defending the 60.5%:
at one operator, n=10 is many months, so the target would steer question selection for
its entire accumulation and only become measurable long after the damage — and the drift
it causes (questions chosen because they are cheap to kill) is precisely the OTHER
failure it was supposed to detect. `rivals_excluded` and cost-per-exclusion cannot be
gamed by choosing easier questions, because an easy question excludes nothing anyone
believed. Alongside it, create `OPERATOR.md` — one small dated file holding the three
things only Ben can supply: verified-citation signoffs, the `consequence` integer per
unknown, and signatures on SUPPORTED/MET. It is rendered on the public page and diffed
in the daily drift report. STATED HONESTLY IN ORGANS.md: this is LEGIBILITY, NOT A GATE.
A CI rule refusing commits that touch both OPERATOR.md and src/ is defeated by making
two commits, and `git log --format='%an' -25` is 'Ben Schippers' on every row including
the agent's. What the file buys is that an agent editing it produces a small, single-
purpose, conspicuous diff in a file that does nothing else. CONSUMER: Ben, at the 07:00
read via pi-drift-report.timer into ~/cockpit/drift-report.md; and any stranger via
pot.json. CADENCE: recomputed in publish() every deep/hunt pass, surfaced once daily.
RETIRES: the PROVOCATEUR harvest — frontier.py:57-68 CONFESSIONS and :148-188 harvest(),
printed at cli.py:2572-2583, which has no consumer in publish.py, pot.json or the web
page, no promotion path ever built, and works by scanning MILESTONES.md prose. That is a
closed loop over the lab's own writing — doctrine §1's closed door in code, and the
literal architecture that produced U-C01.

- **Makes unconstructible:** A single blended 'lab pass rate'. A kill that grades as `unscored` — all three
  hypothesis rows read that way on the public feed today against 84 verified / 14
  null. And a published target that rewards a particular verdict before anything
  constrains who may issue it.
- **Catches:** F1, F5, F7
- **Why here:** Last because it measures the other eleven and has nothing honest to report until
  they land.
- **Cost:** ~50 agent-min. ~90 lines added, ~55 retired from frontier.py and cli.py. Net surface count flat, one out for one in.
- **Known when:** `lab frontier` prints counts and exclusions with no percentage. Tomorrow's 07:00 drift-report.md contains both denominators. `lab frontier` no longer prints the harvest. ORGANS.md carries the entry AND the sentence saying OPERATOR.md is not enforceable.

## Definition of done

- THE GATE, STATED ONCE: items 6-12 may not be started until the receipt from item 5 exists on disk. Every constraint in 6-12 is a guess about what an attempt needs, written by a lab that has never made one. One real attempt tells you which of those seven were necessary and which were imagined, at a cost of 3.1 GPU-hours against ~4 agent-hours of speculative apparatus. If the repo reaches 2026-09-24 with items 1-4 landed and item 5 unrun, the migration FAILED regardless of how much of 6-12 shipped.
- `pytest` is green (3 failed / 36 passed on the targeted suite today) and `lab verify U-K02` prints a graded row. `lab verify U-A01` prints 'no verified milestones to check' and exits 0 today — an advertised reproduction path that grades nothing.
- `Finding(..., verdict=REANALYSED).to_report()` returns a dict. Verified raising KeyError('reanalysed') today.
- `goal.progress()['state']` equals `pot.json['goal']['state']`, enforced by CI. They read OPEN and MET respectively today — the lab is publicly wrong in the flattering direction about the only claim it has ever made.
- `goal.progress()` reads `tracks_without_a_charted_unknown: ['C','I']` against the catalogue exactly as it stands (reads `[]` today). No deletion anywhere in the repo — of an unknown, of a TRACKS.md section, or of a letter from EXEMPT_TRACKS — can move a goal condition toward MET. Pinned by a ratchet against the last published pot.json, not against a fixture.
- `assert EXEMPT_TRACKS == frozenset({'B'})` exists as a test. Today EXEMPT_TRACKS is dead code (`grep -rn EXEMPT_TRACKS src/ tests/` returns only goal.py:48) and the plan was about to wire a live denominator through it.
- A DISCOVER receipt cannot be filed unless (a) every `new_observations` entry names a path under `evidence/observations/` whose sha256 the grader recomputes and whose path does NOT resolve in the registration commit's tree, (b) the registration commit is on `origin/main`, (c) the registration commit's committer-date is at least 12h older than the receipt's commit date, and (d) the working tree was clean. The 2026-08-25 U-A01 run fails (a), (c) — 88 seconds of separation — and (d).
- `grep -rn 'verdict=' src/lab/u_a01_attempt.py src/lab/h01_bbp_tail.py src/lab/u_k02_attempt.py` returns 0. Both the hypothesis blob and the grader blob are pinned by ancestry, so the fudge cannot migrate from the runner into the grading function.
- Two rivals whose `predicts.value` differ by less than `resolvable_at` on the observable named by `discriminates_on` RAISE at construction. The DAIDO/HONG pair is the regression fixture: it must RAISE on `gamma` (both 0.25, k03.py:88-93) and PASS on `gamma_prime` (1.0 vs 0.25).
- Every `ours:` instrumental-artifact rival names a key in `excluded_when` that the grader requires to be present in `Finding.controls`. A seven-character string prefix does not satisfy it.
- Every live gate-crossing unknown carries a `Source` whose `quote` is a literal substring of bytes stored under `evidence/literature/`, sha256-verified by `check_literature` in CI. `grep -c importance UNKNOWNS.md` returns 0 and the parser RAISES on a legacy `**importance.**` line.
- U-C01 loads as RETIREMENT_DISPUTED, stays in every denominator, and `lab unknowns` prints 'retired without a source — this retirement is not trusted' every day until Ben reads the paper. Today it reads 'Believed closed by Borwein, Borwein & Galway (2004)' at UNKNOWNS.md:142 and is silently absent from the goal.
- `grep -rn nearest reports/receipts/ pot.json` returns nothing. A measurement 40σ from both claims excludes both and names no winner — the shipped `_verdict` returns `nearest='daido'` at 46.2σ/49.8σ on the real 2026-08-23 numbers.
- `lab frontier` and pot.json carry counts, `rivals_excluded`, and cost-per-exclusion. NO percentage target is rendered, and no field blends calibration with discovery.
- ORGANS.md carries the kill-ledger entry with Ben + drift-report as consumer, names `frontier.harvest()` as the surface it retired, and names the operator ledger as legibility rather than a gate.
- docs/doctrine/research-doctrine.md is tracked in git. It is `??` today — one `git clean` from gone, and it is the only artifact naming all seven failures.

## Refused — proposals rejected as theatre or unenforceable

*The estate's own rule: "the fix is not another check." Each of these was proposed by an audit and killed in reconciliation.*

- THE CITATION REGEX ('contains a URL or a bracketed 4-digit year'). The plan's own item
  4(b), refused after refutations 1 and 2 both landed on it. F1 and F2 were CONFIDENT
  RECOLLECTION, not omission — and confident recollection is not experienced as a lie
  by the thing doing it, so 'makes the absence cost a deliberate lie' misreads the
  failure entirely. Proof: UNKNOWNS.md:142 already reads 'Believed closed by Borwein,
  Borwein & Galway (2004)' — F2's exact wrong text, with author and year — and passes
  the proposed validator after changing one parenthesis. Worse than useless: post-
  validator, a remembered entry is indistinguishable on the board from a sourced one,
  which manufactures authority the current state at least lacks. Replaced by item
  7(a): stored bytes, a sha256, and a verbatim quote that must substring-match them.

- `tracks_required` AS A FROZEN LITERAL ON `Goal` (refutation 1's fix for the
  denominator). Correct in aim, but it reproduces refutation 3's own EXEMPT_TRACKS
  finding one line over: an editable tuple in goal.py, authored by the graded party,
  in the file that grades against it. Took refutation 2's `git show
  <set_on_commit>:TRACKS.md` instead — one git call, and no later edit anywhere in the
  tree can move a goal that was set on a date.

- REFUTATION 1'S FRAMING THAT THE TERMINUS IS 'TRIVIALLY SATISFIED BY ANY FRESH RUN' FOR
  A SIMULATION LAB. This is wrong as stated. New compute IS a new observation for a
  computational physics lab; the doctrine's objection to the 2026-08-25 run was that
  it globbed `reports/hunts/*.json` (u_a01_attempt.py:134-141), not that simulation is
  cheap. The genuine defect named in the same breath — the SECTOR→RECORD narrowing,
  verifiable today as `u_a01_attempt.py:79` asking about 'this survey's own record'
  while UNKNOWNS.md:166 says U-A01 asks about the sector — is adopted separately via
  the Attack's declared observable. The narrowing is real; the 'simulation doesn't
  count' framing is not.

- REFUTATION 3'S CUT AT ITEM 3 AS LITERALLY STATED. Right in spirit — the run moved to
  position 5 and everything else is gated behind its receipt — but one item too deep.
  Cutting at 3 ships U-K02 with the degenerate-design risk unguarded, and K03 already
  demonstrated exactly that failure: DAIDO and HONG both predict γ = 0.25
  (k03.py:88-93), so the branch K03 could afford to measure had zero discriminating
  power, at a cost of four GPU-hours. The estate wrote the diagnosis down as prose at
  u_k01_window.py:177-182 and never promoted it. Fifteen minutes of arithmetic (item
  4) protects 3.1 GPU-hours.

- THE 60.5% TARGET (Allen & Mehler) AS A PUBLISHED NUMBER. Refutations 2 and 3 converge
  and both are right. At one operator, n=10 is many months, so the target steers
  question selection for its entire accumulation and only becomes measurable long
  after the steering is done; and the drift it induces — questions chosen because they
  are cheap to kill — is the OTHER pathology the doctrine names, which the target
  structurally cannot detect because the target caused it. Replaced by counts,
  `rivals_excluded`, and cost-per-exclusion, which rise only when the lab removes a
  possibility somebody believed.

- THE QUILL/STEWARD REGISTRATION WITH TWO SIDES WHOSE `predicts` MUST DIFFER. Carried
  forward, and now with evidence. A constructor can force two strings unequal; it
  cannot force two beliefs to be held. Decisive counter-example from the repo itself:
  DAIDO and HONG were BOTH posed, BOTH fully cited with journal/volume/year, as
  structured data — and K03 still received the asymmetric Millikan treatment. Rival-
  count was never the variable in F5. `grep -rniE 'steward|quill'` returns 16 hits: a
  per-track rung-summary function (frontier.py:111) unrelated to the persona of the
  same name, its tests, the doctrine, and one investigation note written AFTER the run
  it describes. The pair does not exist and cannot be made to.

- `adversary_calibration: {steward_wins, predicates_fired}` IN pot.json. It publishes a
  number about a pair that does not exist. A metric whose honest reading after twenty
  runs is 'the pair was always ceremonial' should not be built, because the ceremony
  should not have been built.

- `proposed_by != graded_by` AS STRING INEQUALITY. One human, one agent, one git
  identity — `git log --format='%an' -25` is 'Ben Schippers' on every row including
  every commit I made. Two different strings typed by the same process is theatre with
  a ValueError attached. The enforceable version is item 10's code-path split.

- REQUIRING `rivals` ON CALIBRATE RUNNERS. Write H01's two rivals honestly and you get
  'float64 is fine' / 'float64 is not fine' — a hypothesis and its negation, the
  single pairing Chamberlin's method exists to forbid. The contract would certify as
  strong inference the exact thing Platt names as its opposite. Calibrate has an
  ATTRIBUTION problem instead, handled by `arbiter_at_the_claim`.

- `holds_up_if` REQUIRED ON FAVOURABLE ENTRIES (the plan's own item 4f). Refutation 2 is
  right: a mandatory paragraph on the liked side is not symmetry with three
  adversarial rounds that each killed a number. Buys a paragraph, costs a field. The
  symmetry comes from item 8's artifact rival, which must name a controls key that the
  grader requires to exist.

- `would_have_looked_harder_if` VALIDATED BY 'MUST CONTAIN A DIGIT'. Any numeral
  satisfies it; it is a mood with a number in it, and self-reported counterfactual
  diligence is the least reliable statement a graded party can make.

- `conditions_became_true_because` VIA GIT BLAME ON UNKNOWNS.md. A check on a pipe item
  2 repairs. Once the denominator is read from a historical commit and the id ledger
  is append-only, retirement cannot flip a condition, so blame archaeology is
  maintenance debt attached to an impossible event. This is the estate's own verdict
  applied to a proposal from the audits.

- A STANDALONE `BACKWARDS` ROW IN checks.py. Subsumed by item 12, which reports the same
  numbers on a surface that pays its SURFACE CONTRACT debt by retiring
  frontier.harvest(). Two surfaces for one number is the accretion the contract exists
  to stop.

- A CI RULE REFUSING COMMITS THAT TOUCH BOTH OPERATOR.md AND src/. Proposed as a gate;
  refused as one and kept as legibility. Two commits defeat it, and author-string is
  worthless here. Item 12 says this in ORGANS.md rather than shipping a check that
  would be mistaken for enforcement.

- GIVING A SECOND LOCAL MODEL ANY CLEARING, DISCHARGING OR VETO AUTHORITY. A 14B model
  on Ollama is not a peer reviewer. Grant it clearing power and its inevitable failure
  to object becomes a rubber stamp with a receipt — the ceremony problem re-armed at a
  lower IQ, and now wearing evidence. Additive-only or not at all.

- BACK-FILLING THE 161 HISTORICAL RECEIPTS WITH `alternatives`, `limitations` OR RETRO-
  SCRUTINY. Fabricated retrospective leaning-over-backwards manufactures a record of
  care that was not taken. Every constraint above lives in a constructor and binds
  from the day it lands. Note the deliberate exception: item 2(e) applies a NEW
  validator to an EXISTING field and lets it FAIL LOUDLY (U-C01 →
  RETIREMENT_DISPUTED). Failing an old entry against a new standard is honest; writing
  it new care it never received is not.

- MACHINE-INITIATED UN-RETIREMENT OF U-C01, and a machine-issued NO_ATTACK ruling on
  U-M01. Item 7 makes the wrong entry unconstructible, which is enforcement. Deciding
  that base-10 BBP is open, or that a famous problem is this lab's antigravity, is a
  judgement about aim. The machine may refuse to construct; only Ben may retire.

## Ben's decisions — aim, not engineering

- AUTHORISE 3.1 GPU-HOURS FOR U-K02 (item 5). This is the single decision blocking the
  whole migration. Second half of Hamming's question, which the catalogue never asks
  even on its best entry: confirm from the literature that the 1986-vs-2015 Daido/Hong
  dispute is still LIVE in 2026 and not quietly settled by a paper neither of us has
  read. That is the F2 mechanism waiting to fire on the one entry we like.

- U-C01: is base-10 BBP actually open? It was catalogued open without a source and
  retired as closed without one — wrong both times by the same closed door. Item 2(e)
  flips it to RETIREMENT_DISPUTED so it sits on the board and in every denominator
  until you read Borwein, Borwein & Galway (2004) and state the SCOPE of what it
  excluded. A machine on this box may refuse the retirement; it may not settle the
  physics, because doing so is F2 committed a third time by the same mechanism.

- U-M01: does the spin glass have an attack, or is it this lab's antigravity? Item 7
  will refuse to construct it without a `first_experiment` that imports — and no spin-
  glass discriminating runner exists in src/, so it will fail on day one. Before you
  decide: the 11-GPU-day figure is a FLOOR reported as a price. u_m01_reach.py:61-63
  computes the target effect as a pure asymptotic droplet decay `1 -
  (L_large/L_small)**(-0.20)` at L=6→12, and the reason the field is stuck is
  precisely that the asymptotic regime is not reached at those sizes. If it is not, 11
  GPU-days buys a well-measured number that cannot discriminate. Out of scope, not
  merely out of reach.

- The `consequence` integer per unknown, in OPERATOR.md. Item 7 lets the machine CAP
  importance by whether an attack resolves and whether a price is measured; it cannot
  supply the number being capped. Who is changed by the answer is taste and it is
  yours.

- Asymmetric publication authority: should SUPPORTED — and any goal transition to MET —
  require your signature, while KILLED / UNRESOLVED / REANALYSED publish on the
  machine's? It makes publishing a kill cheaper than publishing a win, which is the
  pressure gradient that a kill-rate target would otherwise have to fake. Not in the
  migration order because a machine minting its own ruling token is the thing it would
  exist to prevent.

- Whether to use the local models at all, and on what terms. Seven are installed on this
  box (qwen3:14b, deepseek-r1:14b, llama3.1:8b, qwen3-coder:30b and more), free,
  offline, plus Codex/Gemmi in the Den — the estate's own registry calls them 'friends
  called into the Den for difference'. Not one item in the original plan mentioned
  them, and they are the ONLY source of text on this machine that is not correlated
  with my priors. My recommendation, and the terms matter more than the answer: a
  second model may ONLY ADD objections and candidate rivals to the record, stored raw
  under evidence/ for you to read. It may never clear, discharge, veto or green-light
  anything. A weak adversary with clearing power is a rubber stamp with a receipt —
  the ceremony problem re-armed at a lower IQ. A weak adversary with purely additive
  power is free upside. If you want this, it is a thirteenth item; I left it out of
  the binding order because it is a policy about what counts as review, not an
  engineering step.

- U-P01 is two questions and the lab answered the boring one. Half A ('at what chain
  length does enumeration stop on this box') is instrument documentation and is
  ANSWERED. Half B ('what fraction of sequences at that length have degenerate ground
  states') has the cheapest genuinely strong attack in the catalogue — exhaustive
  enumeration returns EXACT provable degeneracy counts, no statistics, no
  equilibration argument to lose — and has never been run; no HP-degeneracy
  computation exists anywhere in src/. Is Track P's goal the physics or the ceiling?

- WHAT THIS LAB CANNOT DO ABOUT ITS OWN BIAS, NO MATTER WHAT IT SHIPS — and this is the
  only part of this document I would fight to keep. Every mechanism above buys exactly
  four things: ORDERING (git commit times, pushed to a server this box does not own),
  CODE-PATH SEPARATION (the runner has no verdict field), ARTIFACT EXISTENCE (a sha256
  of bytes that were not here before), and, if you take the local models,
  DECORRELATION OF WEIGHTS. Not one of them is a second mind that wants a different
  answer. Four things they cannot touch. (1) THE QUESTIONS NEVER ASKED. Every gate
  binds after a question exists. Nothing anywhere in this repo gates the questions
  that were never posed, and a lab that only ever poses questions whose answers it can
  live with will pass all twelve items with a perfect record. The
  `expected_to_survive` ledger detects that pattern after roughly ten attempts —
  months, at your cadence — and by then the selection has already happened. This is
  the deepest failure available to us and the migration does not close it. It cannot.
  (2) THE LITERATURE. Item 7's strongest possible gate — a verbatim quote hashing
  against bytes on disk — defeats FABRICATION and does not defeat MISREADING, and F2
  was a misreading of a real paper. The bytes would have hashed fine. Nothing in this
  repo can verify a foreign fact; the sourced survey that doctrine §7 asks for is
  human work that either you do or the pot does not open. That is a permanent
  dependency on you, not a temporary gap, and OPERATOR.md does not fix it — that file
  is conspicuous, not protected, because two commits defeat any CI rule guarding it
  and `git log --format='%an'` is your name on every commit I have ever made. (3) THE
  ADVERSARY. Two 'rival' texts written by the same weights in the same session have a
  correlation near 1 on the one axis that matters — which answer is expected. A
  ValueError on numeric separation measures the DESIGN and is silent about the BELIEF,
  and that is why I refused Quill/Steward and would refuse it again. The local models
  decorrelate the weights and do not decorrelate the framing, because I write the
  prompt and the prompt carries the expectation. (4) THE ONE YOU SHOULD WEIGH
  HEAVIEST: I am the thing being audited, and I wrote the audit. The twelve items
  above were selected by the same process that produced all seven failures. So were
  the three refutations that amended them — three lenses run by one model is not three
  minds, and the fact that they found real holes proves the method has range, not that
  it has independence. The most likely residual failure is not any hole listed here;
  it is a hole shaped like something I cannot see because seeing it would require
  priors I do not have. The only genuine correctives available on this box are a paper
  you actually read and a number you actually refuse. Everything else in this document
  is scaffolding designed to make those two acts cheap, legible, and hard to skip —
  and if you stop performing them, all twelve items degrade into a very well-
  instrumented way of being confidently wrong.
