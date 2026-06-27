# Decision: the nightly heartbeat vs. an autonomous `lab next` scheduler

**Status:** open — needs Ben's call. **Raised by:** the public-experience audit (P0, "the page conflates two clocks"), verified against the code 2026-06-26.

## The finding (verified)

The installed nightly task statically runs `python -m lab.cli run`, which dispatches the **base 2D Ising engine** — i.e. M01, the original calibration. (`setup.py` generates that command; `cli.py` maps `run` → `ising.run`. M01 isn't even a named command; it's the un-prefixed default.) Every later milestone (M02…M11) is its own hand-written subcommand (`lab m04`, `lab m11`, …). There is **no** milestone-aware scheduler.

So the nightly re-runs M01 forever, while the curriculum front has climbed to **M12**. The page truthfully showed both — "last night: M01 Ising" and "M12 open" — which read as a contradiction. The M04→M11 ladder (2026-06-24/25) widened the gap.

## What's already shipped (direction 1, the page-level fix)

This was the fast, safe half and it's landed in the web PRs:

- A one-sentence framing: the nightly re-check **is the lab's heartbeat** — it re-proves the instrument can still find a trusted answer — while the curriculum's frontier climbs ahead of it. (`fix(web): tell the truth`.)
- A **"now growing"** expedition line that names the actual open milestone's question, distinct from the heartbeat. (`feat(web): field notes + expedition line`.)

This makes the page *honest* about the two clocks. It does **not** make the nightly advance the curriculum — that's direction 2.

## The decision

**Direction 1 — keep the heartbeat; advance the curriculum by hand.**
The nightly stays a fixed M01 calibration ("is the instrument still true?"). New milestones are launched deliberately by you (`lab m12`, …) when you've written each one. The page already explains this honestly.
- *Pros:* zero new moving parts in the unattended job; the heartbeat is a genuinely valuable signal (it catches instrument regressions every night); matches how the lab actually works today.
- *Cons:* the "autonomous curriculum that advances itself" promise stays aspirational; milestone cadence is gated on you.

**Direction 2 — build `lab next`, a milestone-aware scheduler.**
The nightly runs the *open* milestone's experiment and, on a verified pass, advances state so tomorrow targets the next one.

A concrete, low-magic design:

1. **A runner registry** — `RUNNERS = {"M04": m04.run, …, "M11": m11.run}` (one entry per milestone that has an engine). This formalizes the mapping the bespoke subcommands already encode.
2. **`lab next`** — read `MILESTONES.md`, find the open milestone (the existing `parse_milestones` already computes it), and:
   - if its id is in `RUNNERS`, run it;
   - else fall back to the **heartbeat** (`run`) and log "no runner for `<id>` yet — heartbeat instead." This is the key reality check: **M12 has no runner yet**, so `lab next` would run the heartbeat until M12's code lands. Direction 2 does not remove the heartbeat; it *prefers the frontier when one exists.* (Note: a concurrent session's **PR #32** adds the 3D-Wolff single-cluster updater the 3D spin glass will need to equilibrate — a building block *toward* M12's engine, not the milestone runner itself.)
3. **Advance-on-verify** — only the verification gate (`checks.py`) may mark a milestone `[x]`. `lab next` never edits `MILESTONES.md` on its own beyond what a verified report already authorizes; promotion stays human-reviewed via the PR that adds the report. (Auto-editing the source of truth from an unattended job is the main risk to avoid.)
4. **`lab next --dry-run`** — print what it *would* run, so the behavior is inspectable before it's wired into the scheduler.
5. **Swap the nightly** — `setup.py` generates `lab next` instead of `lab run` (one line), once you're happy with `--dry-run`.

- *Pros:* realizes the autonomous-curriculum story; the page's "now growing" line becomes literally what ran last night.
- *Cons:* it changes the **unattended** nightly job, so correctness matters more (a bad dispatch runs every night with no one watching); needs each milestone to expose a uniform `run()` entry; the verify→advance loop needs care so a flaky run can't silently strand or mis-advance the curriculum.

## Recommendation

**Ship direction 1 now (done), build direction 2 as an opt-in `lab next` behind `--dry-run`, and only swap the nightly once you've watched a few dry runs.** The heartbeat is too useful to delete — keep it as the explicit fallback inside `lab next`. The honest framing already on the page is correct under *either* choice, so there's no rush; this is a "which lab do you want" decision, not a bug to patch.

Effort for direction 2: ~half a focused session for the registry + `lab next` + `--dry-run` + tests; the `setup.py` swap is one line whenever you're ready. I did **not** build it tonight because rewiring the unattended scheduler is exactly the kind of change AUTONOMY.md says to surface rather than decide alone.

## Your call

- [ ] **Direction 1** — heartbeat only; I advance milestones by hand. (No further work; page is already honest.)
- [ ] **Direction 2** — build `lab next` (registry + dry-run + tests), keep the heartbeat as fallback, swap the nightly after dry-run review.
