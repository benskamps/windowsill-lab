# Research doctrine — what Steward and Quill are for

**2026-08-25 · sourced, not remembered.** Every claim below carries a citation,
because the lab spent a day discovering that its own catalogue of "unknowns"
was assembled from a machine's recollection and was wrong twice about the same
entry.

---

## 0 · The failure this document exists to correct

The pipeline built on 2026-08-24 went: *look at our instruments → ask what they
could almost do → call that an unknown → build a runner → publish a verdict.*

It is inverted. It can only ever discover things about itself, and it did:
`U-C01` was half-remembered, `U-I01` was "we own a computer, computers have
cameras", `U-M01` was a famous name with no way in, and the one "attempt" that
closed a discovery goal consumed **zero new observations**.

The correct order is Ben's, and it has three blanks:

> *"In the field represented by this pot, we have the following unanswered
> questions ___. I will break ground by ___. My experiments will be ___."*

**SURVEY → ATTACK → EXPERIMENT.** Only the third was built.

---

## 1 · Problem selection — the part that is harder than the answers

Hamming's definition is the one that matters, and it is not about stakes:

> *"By important I mean guaranteed a Nobel Prize and any sum of money you want
> to mention. We didn't work on (1) time travel, (2) teleportation, and (3)
> antigravity. They are not important problems because we do not have an
> attack."*
> *"It's not the consequence that makes a problem important, it is that you
> have a reasonable attack."*

**This kills the way the catalogue scored importance.** `U-M01` — is the 3D
spin glass RSB or droplet — is a genuinely famous problem and, at 0.3σ with an
11-GPU-day price and the discriminating observable not even serialised, it is
this lab's *antigravity*. Importance 4 was a rating of the problem's fame, not
of our opening.

And "reach" is not "attack". Reach asks *can the instrument touch it*. Attack
asks *why would we get somewhere a field of specialists has not*. The catalogue
measured reach on every entry and attack on none.

Two more of Hamming's, both operational:

> *"The average scientist, so far as I can make out, spends almost all his time
> working on problems which he believes will not be important and he also
> doesn't believe that they will lead to important problems."*

> *"He who works with the door open gets all kinds of interruptions, but he also
> occasionally gets clues as to what the world is and what might be
> important."*

An agentic lab reading only its own `reports/` is a **closed door**. That is
not a metaphor here; it is the literal architecture that produced U-C01.

---

## 2 · Method — strong inference, and why it is not what we were doing

Platt's diagnosis of why some fields move and others crawl, and his four steps:

> *"Devising alternative hypotheses; Devising a crucial experiment (or several
> of them), with alternative possible outcomes, each of which will, as nearly as
> possible, exclude one or more of the hypotheses; Carrying out the experiment
> so as to get a clean result; Recycling the procedure…"*

**`alternative hypotheses` is plural and our contract holds exactly one.** Every
runner in this estate poses a single hypothesis and asks whether it survives.
That is not strong inference — it is confirmation with a kill switch attached.
Chamberlin's point, which Platt carries:

> *"The method of multiple working hypotheses… distributes the effort and
> divides the affections. Each hypothesis suggests its own criteria, its own
> method of proof."*

*Divides the affections* is the mechanism. A researcher with one hypothesis is
its advocate; a researcher with three is an adjudicator.

Platt's touchstone question, to be asked of every proposal:

> *"But sir, what experiment could **dis**prove your hypothesis?"* — and its
> twin — *"But sir, what hypothesis does your experiment **dis**prove?"*

The second is the one this lab keeps failing. Our runners can say what would
refute *themselves*. Almost none can name a rival they would exclude.

### Platt's pathologies — the "what not to do" list, verbatim

> *The Frozen Method · The Eternal Surveyor · The Never Finished · The Great Man
> With a Single Hypothesis · The Little Club of Dependents · The Vendetta · The
> All-Encompassing Theory Which Can Never Be Falsified*

Two are already ours. **The Eternal Surveyor** is what a feasibility-test
factory becomes when pricing is cheaper than attempting — five of seven
catalogue entries were priced and none attempted. **The Great Man With a Single
Hypothesis** is the shape of `lab.hypothesis.Hypothesis` itself.

---

## 3 · Integrity — the standard is higher than honesty

Feynman, and the sentence that should sit above this whole estate:

> *"The first principle is that you must not fool yourself—and you are the
> easiest person to fool."*

> *"If you're doing an experiment, you should report everything that you think
> might make it invalid—not only what you think is right about it: other causes
> that could possibly explain your results; and things you thought of that
> you've eliminated by some other experiment, and how they worked."*

> *"The thing I'm talking about is not just a matter of not being dishonest,
> it's a matter of scientific integrity, which is another level."*

And the Millikan oil-drop story, which describes this lab on 2026-08-25 exactly:

> *"When they got a number that was too high above Millikan's, they thought
> something must be wrong—and they would look for and find a reason why
> something might be wrong. When they got a number closer to Millikan's value
> they didn't look so hard."*

**Today the K03 result was disliked and got three rounds of adversarial
scrutiny — window artifact, critical slowing down, saturation bias, each one
killing a number. The G01 "MET" was liked and got none.** Same lab, same day,
same person. The asymmetry was not dishonesty; it was Millikan.

---

## 4 · Calibration — the number that says whether we are testing or confirming

Registered Reports move peer review to *before* the results exist: a protocol is
accepted on its question and method alone, and publication does not depend on
the answer. The effect on what gets found is the most useful statistic in
metascience:

> Allen & Mehler examined 296 a priori hypotheses across 113 Stage-2 Registered
> Reports: **60.5% were not supported**, against an estimated **5–20%** null
> findings in the traditional literature.

**So a healthy hypothesis engine kills roughly six in ten.** That is a hard,
external, non-negotiable calibration target — and it replaces the "20-40%" this
lab guessed at yesterday with a sourced number.

A kill rate far below it means the questions are too safe or the grading is too
kind. A kill rate near 100% means the questions are unserious.

Ioannidis supplies the mechanism to guard against:

> Findings are less likely to be true the smaller the studies, the smaller the
> effects, the greater the number and lesser the selection of tested
> relationships, and **the greater the flexibility in designs, definitions,
> outcomes, and analytical models**.

Flexibility is the axis an agentic lab maxes out by default. On 2026-08-25 one
agent wrote the question, the kill condition, the threshold, the runner, the
analysis and the verdict. That is total flexibility, and Ioannidis's corollary
applies with full force regardless of how careful each individual step was.

---

## 5 · Structure — what the institutions actually did

The MRC Laboratory of Molecular Biology has produced **12 Nobel Prizes shared
among 16 people**. Its recipe, from Perutz:

> pick good people, help them get what they need, and otherwise let them follow
> their own interests.

Structurally: **no director until 1979** — Perutz never used the title — **no
departments, no doors, no locked cabinets, no secrets among scientists**, no
personal assistants screening visitors, paperwork kept to a minimum, and
researchers encouraged toward *risky, hard-to-solve* problems.

The transferable part is not the flatness. It is that **the structure removes
every place a result could be hidden or a question could be quietly narrowed**,
and it pushes taste toward hard problems rather than safe ones.

---

## 6 · Adversarial collaboration — the answer to "who can falsify this if not me?"

Kahneman's protocol, and the reason Steward and Quill exist:

> The two disputing researchers team up with a neutral arbiter and agree on a
> procedure for an experiment that would distinguish between their hypotheses.
> **They discuss ahead of time what results each expects, and what sorts of
> results would lead them to change their minds.**

> *"Because adversarial collaborations restrict scholars' abilities to rig
> methods in favor of their own hypothesis and to dismiss unexpected results,
> adversarial collaborations are likely to advance debates faster and generate
> more reliable knowledge than traditional approaches."*

> Each collaborator serves as a check on their adversary to confirm that the
> hypotheses are falsifiable, the tests are fair, and the interpretations
> accurately characterize the findings.

**This is the correction to how the pair has been run.** Steward and Quill have
been a friendly PM and a friendly researcher, agreeing with each other and with
me. That is a Little Club of Dependents. They must be **adversaries by
construction**: Quill proposes and advocates; Steward's job is to kill it; both
must state *in advance* what result would change their mind; and neither may
grade their own run.

---

## 7 · What this changes, concretely

| # | change | source |
|---|---|---|
| 1 | A pot opens with a **sourced survey** of what the field does not know. No entry without a citation. | Hamming's open door; U-C01's two errors |
| 2 | Every unknown declares an **ATTACK** — why *we* have a way in — distinct from reach. No attack ⇒ it is our antigravity, and it is not important. | Hamming |
| 3 | A proposal carries **≥2 rival hypotheses** and an experiment that **excludes** at least one. Answering "what would refute me" is not enough; it must answer "what does my experiment disprove". | Platt, Chamberlin |
| 4 | Quill and Steward **pre-commit their expectations** — what each predicts and what would change their mind — before the run. | Kahneman |
| 5 | **Nobody grades their own run.** | Kahneman, LMB's no-locked-cabinets |
| 6 | The board tracks **kill rate against 60%**, not just count. Below it we are confirming. | Allen & Mehler via Registered Reports |
| 7 | Every receipt carries a **"leaning over backwards"** section: everything that might make this wrong, including what we looked for and eliminated. | Feynman |
| 8 | Flexibility is logged as a **risk factor**: when one agent wrote the question, method and verdict, the receipt says so. | Ioannidis |

---

## Sources

- Platt, J.R. "Strong Inference." *Science* 146:347 (1964).
  <https://www2.cs.duke.edu/courses/fall04/cps296.2/science_platt.html>
- Hamming, R.W. "You and Your Research" (1986).
  <https://www.cs.virginia.edu/~robins/YouAndYourResearch.html>
- Feynman, R.P. "Cargo Cult Science," Caltech commencement (1974).
  <https://calteches.library.caltech.edu/51/2/CargoCult.htm>
- Ioannidis, J.P.A. "Why Most Published Research Findings Are False." *PLoS Med* (2005).
  <https://en.wikipedia.org/wiki/Why_Most_Published_Research_Findings_Are_False>
- Registered Reports; Allen & Mehler null-rate comparison.
  <https://en.wikipedia.org/wiki/Registered_report> ·
  <https://www.nature.com/articles/s41562-021-01142-4>
- Kahneman, D. "Adversarial Collaboration." Edge.
  <https://www.edge.org/adversarial-collaboration-daniel-kahneman> ·
  <https://en.wikipedia.org/wiki/Adversarial_collaboration>
- MRC LMB Nobel record and Perutz's management.
  <https://mrclmb.ac.uk/achievements/awards-and-prizes/nobel-prizes/> ·
  <https://www.science.org/content/article/nobel-prize-winning-culture>
