# Windowsill Public Experience Audit

**Date:** 2026-06-26  
**Surfaces reviewed:** [Brokenbranch Lab](https://www.brokenbranch.dev/labs/) · [Windowsill](https://www.brokenbranch.dev/windowsill/) · `windowsill-lab` repository  
**Audiences considered:** curious passerby, non-technical visitor, recruiter/hiring manager, technical reviewer

## Executive summary

Windowsill is a strong concept with an unusually coherent ethic: a home computer performs patient scientific work, verifies itself against known results, keeps failed attempts visible, and translates progress into the growth of a plant.

The public experience does not yet communicate that idea quickly enough. A first-time visitor sees an attractive ambient plant and a dense physics receipt, but must reverse-engineer whether the project is an art toy, a simulation, an autonomous agent, or a research instrument. The engineering system and scientific breadth are both substantially more impressive than the page makes them appear.

The central problem is not visual polish. It is orientation and state modeling:

1. The nightly M01 calibration heartbeat and the current milestone expedition are presented as one activity.
2. The page explains the original M01 experiment while the curriculum is currently on M12.
3. The renderer's growth-form selection permanently favors the physics fern, preventing the advertised scientific variety from appearing.
4. Current-state facts are embedded in static prose and have already drifted out of date.
5. The strongest proof of engineering quality is largely absent from the public page.

The recommended redesign preserves the quiet window, plant, clay pot, changing light, and honest record. It adds a clear promise, a current question, a visible curriculum, plain-language results, tappable leaves, and a preview of the different scientific tracks.

## What a visitor should understand

### Within three seconds

- This is a home computer doing real scientific simulations.
- The plant grows from checked results.
- Something specific is being investigated now.

### Within thirty seconds

- The lab begins with known physics to establish trust.
- It advances through four physics phases toward open questions.
- Separate tracks will cover number theory, astronomy, hardware sensing, and donated computation.
- Failed calibrations remain visible rather than being discarded.

### Within three minutes

- How the simulation, verification, report, feed, and visualization pipeline works.
- What the latest result means in ordinary language.
- What evidence supports the claim.
- How to inspect the report, archive, provenance, tests, and source.

## Current visitor experience

### What works

- The central scene is memorable and aesthetically coherent.
- The day/night behavior gives the project a genuine sense of presence.
- The clay pot, changing soil, plant growth, and weather metaphor belong to one visual world.
- “A failed calibration, not a discovery” is an excellent governing principle.
- The live feed is real: 11 of 31 milestones are verified, M12 is open, and 23 reports are present in the archive.
- The underlying project is healthy: the local audit reproduced the Ising critical point, all 11 published milestone checks passed, 273 Python tests passed, and seven growth-form tests passed.

### What fails for a new visitor

- The category is unclear. “Windowsill” is a mood and a metaphor, not an explanation.
- The essential “What am I looking at?” answer appears after the main visual and telemetry.
- The current milestone is represented only as the cryptic label `M12 open`.
- The visible result is M01, while the growing tip is supposedly M12.
- Identical leaves communicate completion count but not intellectual variety.
- Technical notation appears before a plain-language claim.
- The visitor receives no visible roadmap showing when the science changes.
- A recruiter cannot easily see the breadth of the built system.

## Structural findings

### P0 — The page conflates two clocks

The installed nightly task runs ordinary `lab run`, which dispatches the original two-dimensional Ising simulation. New milestone models are launched through separate commands such as `lab m08`, `lab m11`, and so on.

Relevant implementation:

- [`src/lab/setup.py`](src/lab/setup.py) generates the nightly script and invokes `python -m lab.cli run`.
- [`src/lab/cli.py`](src/lab/cli.py) maps `run` to the base Ising engine, while each milestone has a separate command.

The live page therefore shows two truthful but apparently contradictory states:

- “Last night” reports M01.
- The curriculum says M12 is open.

These should be explicitly modeled as:

- **Heartbeat:** the nightly calibration that demonstrates the instrument still reproduces a trusted result.
- **Current expedition:** the harder milestone presently under development or investigation.

There are two viable product directions:

1. Preserve the two-loop behavior and explain it honestly on the page.
2. Create a milestone-aware `lab next` scheduler that runs the active curriculum experiment and advances state after verification.

The first is a fast communication fix. The second realizes the stronger autonomous-curriculum promise but requires meaningful engineering work.

### P0 — Growth-form variety cannot surface

[`web/growth-forms.js`](web/growth-forms.js) selects the page's plant form by tallying the `growth_form` of every milestone and choosing the most common.

Current curriculum distribution:

| Track | Growth form | Milestones |
|---|---|---:|
| Physics | Fern | 18 |
| Compute | Vine | 4 |
| Astronomy | Creeper | 4 |
| Instrument | Succulent | 3 |
| BOINC | Moss | 2 |

Because the full milestone list remains present as statuses change, fern always wins. The public page is effectively locked to the physics form.

Recommended behavior:

- Select the hero plant from the open milestone's track.
- Preserve phase progress separately from morphology.
- Preview all future forms in a small labeled “garden of sciences” so variety is visible before those tracks become active.

### P0 — Static copy is already stale

[`web/index.html`](web/index.html) contains hand-authored claims that the lab is “right now” studying the original Ising model and that four milestones have been verified. The live state is M12 with eleven verified milestones.

All time-sensitive public copy should be feed-driven:

- Current milestone
- Current phase
- Plain-language question
- Plain-language result
- Verified count
- Distance to the next phase
- Active track and growth form

Static copy should describe only durable principles.

### P1 — Report links do not fulfill their promise

The report producer emits `latest_report.href`, while the page checks `latest_report.url`. As a result, “full report” retains its default link to the GitHub repository instead of using the feed's report target.

The archive's per-row report links also point to the archive index rather than distinct run reports. This behavior is documented internally, but it conflicts with the user-facing “report” label.

Recommended fixes:

- Accept `rep.href || rep.url` in the consumer during migration.
- Align the schema and producer on one canonical property.
- Use “view in archive” when the destination is the archive index.
- Restore genuine per-run deep links where storage policy permits.

### P1 — Public metrics appear contradictory

The page shows `runs 13` while the archive announces `23 on record`. The likely distinction is nightly heartbeat runs versus all recorded milestone reports, but both are presented as runs.

Recommended labels:

- `13 nightly heartbeats`
- `23 total reports`
- `11 verified milestones`

### P1 — Leaves are not useful public interactions

Milestone meaning currently lives in SVG `<title>` tooltips. These are subtle on desktop and functionally undiscoverable on touch devices. The visual carries extensive result data without a usable interaction model.

Recommended interaction:

- Make each leaf keyboard-focusable and tappable.
- Open an adjacent or bottom-sheet field note.
- Lead with a one-sentence plain-language result.
- Offer a secondary “show the receipt” disclosure for technical numbers.
- Mark phase boundaries on the stem so model changes are visible.

### P1 — The engineering achievement is hidden

A technical reviewer or recruiter should be able to see the complete system at a glance:

`schedule → simulate → verify → render report → publish feed → grow plant`

The current page foregrounds the metaphor and one physics explanation but not the architecture. This causes the work to look smaller than it is.

Recommended proof statement:

> Built end-to-end: PyTorch GPU simulations, deterministic checks against known theory, automated nightly scheduling, provenance-stamped reports, a versioned JSON contract, CI verification, and a live SVG driven by the results.

### P2 — The Lab front door is visually under-leveraged

The Lab index has a distinctive editorial identity, but the mobile page is very long and the project entries rely heavily on prose. Windowsill's live scene and the aquarium are much stronger evidence than their descriptions.

Recommended direction:

- Feature the machine residents as large editorial visual rows rather than text-heavy cards.
- Embed a live or captured crop of the Windowsill and aquarium surfaces.
- Keep the excellent shelf organization, but give each shelf one dominant visual specimen.
- Add a short “what this demonstrates” line for recruiters without turning the page into a conventional portfolio grid.

## Recommended positioning

### Category

**A patient home science machine**

This is clearer and more distinctive than “numerical-physics instrument” for a general audience. Technical language can follow after orientation.

### Core promise

> A home GPU runs science while everyone sleeps. It starts by reproducing famous results; as the instrument earns trust, the lab moves toward harder questions. Every result stays on the record—even the misses.

### Governing idea

> Romance in the questions. Rigor in the claims.

This line already exists in the page's hidden copy and deserves a more visible role.

## Proposed first viewport

### Kicker

`WINDOWSILL LAB · A PATIENT HOME SCIENCE MACHINE`

### Headline

**A home GPU runs science while everyone sleeps.**

### Supporting copy

It begins by reproducing famous physics. As the instrument earns trust, the curriculum moves into spin glasses, astronomy, number theory, hardware sensing, and questions without known answers.

### Current expedition

**NOW GROWING · PHASE 3 — PUSH THE EDGE**  
Can a three-dimensional spin glass freeze at a real temperature?  
M12 · preparing · 11 of 31 results verified

### Nightly heartbeat

**LAST NIGHT'S HEARTBEAT · PASSED**  
The machine re-found a 1944 exact result within 1.4%.

### Primary actions

- See the current question
- Explore the curriculum

The full report and source should remain available but should not be the only meaningful destinations.

## Proposed information architecture

### 1. Hero — identify and orient

One composition: the plant, the promise, the current question, and the distinction between heartbeat and expedition.

### 2. The journey — show when the science changes

| Phase | Public label | Purpose | Current state |
|---|---|---|---|
| 1 | Verify the instrument | Reproduce famous exact results | Complete |
| 2 | Map known territory | Test different models and geometries | Complete |
| 3 | Push the edge | Spin glasses, frustration, disorder | Active |
| 4 | Ask open questions | Non-equilibrium behavior, aging, KPZ | Ahead |

Display a clear “you are here” marker and a dynamic distance to the next phase.

### 3. Latest field note — explain before proving

Example for M11:

> **A two-dimensional spin glass never truly freezes at a nonzero temperature.**  
> The simulation reproduced that expected absence: glass-like structure strengthened steadily as the system approached absolute zero.

Under “show the receipt”:

> Across 16 temperatures and 64 disorder realizations, ⟨q²⟩ increased from 0.011 to 0.306 as T fell from 2.0 to 0.6.

### 4. One machine, many sciences — make breadth visible

Show the five growth forms together:

- Fern — statistical physics
- Vine — number theory and compute
- Creeper — astronomy time series
- Succulent — hardware instrumentation
- Moss — distributed computation

These can be small silhouettes or specimens rather than five competing hero illustrations.

### 5. How the system works — expose the engineering

`nightly schedule → GPU experiment → verification gate → report and provenance → public feed → plant growth`

Each step needs one sentence at most.

### 6. The honest record — prove the ethos

Surface three examples:

- A verified result
- An expected negative result, such as M09
- A failed calibration retained in the archive

This demonstrates scientific judgment more convincingly than a general promise.

### 7. Archive and source — deepen

Provide clear destinations:

- Read the latest field note
- Browse all reports
- Inspect the methodology and source
- Reproduce the experiment locally

## Suggested public content model

Technical milestone titles and long result strings are not sufficient public copy. Add a small durable story layer for each milestone:

```json
{
  "id": "M12",
  "phase": 3,
  "track": "physics",
  "growth_form": "fern",
  "status": "open",
  "short_label": "3D spin glass",
  "question_plain": "Can a disordered magnet freeze at a real temperature?",
  "why_it_matters": "Three-dimensional spin glasses show collective order that their two-dimensional cousins cannot sustain.",
  "result_plain": null,
  "result_technical": null
}
```

This content should be maintained beside the curriculum rather than inferred from long technical prose at render time.

## Interaction direction

Use motion to clarify state rather than decorate it:

1. **Arrival:** night light settles, then the current bud softly brightens as the current question appears.
2. **Curriculum:** scrolling advances a restrained phase marker along the stem.
3. **Leaf detail:** selecting a leaf opens a field note and subtly emphasizes its chapter.
4. **Track preview:** hovering or tapping a future track gently morphs a specimen between fern, vine, creeper, succulent, and moss.

Avoid adding dashboard cards, animated charts, excessive badges, or multiple competing accent colors. The page's restraint is an asset.

## Implementation sequence

### Pass 1 — Truth and orientation

- Rewrite the hero around identity and the current question.
- Separate heartbeat from current expedition.
- Drive current-state copy from feed data.
- Fix `href` versus `url` report handling.
- Clarify heartbeat and total-report counts.
- Update or remove all stale embedded milestone counts.

### Pass 2 — Visible curriculum

- Add the four-phase journey and “you are here.”
- Add plain-language current and latest-result fields.
- Make leaves tappable and keyboard accessible.
- Add phase boundaries or chapter markers to the plant.

### Pass 3 — Public variety

- Select hero form from the active track.
- Add the labeled future garden.
- Give each track an appropriate plain-language introduction.

### Pass 4 — Portfolio and proof

- Add the compact engineering pipeline.
- Improve individual report destinations.
- Feature large visual specimens on the Lab front door.
- Add a recruiter-friendly summary without compromising the project's voice.

### Larger product decision

Decide whether Windowsill is:

1. A nightly calibration heartbeat plus separately initiated expeditions, or
2. An autonomous curriculum that chooses and advances the active experiment.

Both are credible. The public story must match the actual behavior.

## Success criteria

After the redesign, an unbriefed visitor should be able to answer:

- What is this? — A home computer running and recording scientific experiments.
- What is it doing now? — Investigating the three-dimensional spin-glass transition.
- Why begin with old physics? — To prove the instrument is trustworthy.
- How does the plant relate? — Each checked milestone becomes visible growth.
- What changes later? — The curriculum moves from known physics to open questions and other scientific tracks.
- Why is this technically impressive? — It is a complete automated simulation, verification, reporting, provenance, publishing, and visualization pipeline.
- Where can I verify the claim? — In a specific report, the archive, or the source.

## Preserve these qualities

- The calm pace
- The changing light and weather
- The clay pot and singular visual focus
- The language of patient computation
- The visible failed calibrations
- The absence of account creation, gamification pressure, or notification mechanics
- The willingness to report negative scientific results
- The sense that the software lives quietly rather than demanding attention

The redesign should make Windowsill easier to understand, not more conventional.

