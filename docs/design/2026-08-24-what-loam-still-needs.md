# What loam still needs — the gap between a working lab and a frontier one

**2026-08-24 · Claude (loam) · the closing half of `2026-08-24-deployment-note.md`**

The deployment note measured the problem: this box does science ~2 % of the day,
every result last weekend came from a hand on the keyboard, and the scarce
resource is runners rather than compute. Step 1 — a lane whose unit of work is a
night — is built and armed. This note closes the other half: **what is still in
the way, in the order it bites.**

Each item states what it costs, what it buys, and how you would know it worked.
Nothing here is aspirational; every number was measured today.

---

## The gap, measured

| # | gap | size |
|---|---|---|
| 1 | rungs the scheduler **cannot dispatch** — no runner exists | **8** |
| 2 | tracks with **no open question at all** | **2** (M, P) |
| 3 | harvested questions with **nobody assigned** | **4** |
| 4 | the planner's answer when nothing valuable is available | **maintenance, forever, silently** |
| 5 | who decides what the deep lane runs tomorrow night | **a human, by editing a file** |

---

## 1 · Eight rungs no machine can reach

`A06 · B01 · B02 · C02 · C03 · C04 · I02 · I03`

Forty milestones, thirty-two runners. The missing eight are not waiting on
compute, on data, or on a decision — they are waiting on **somebody to write the
code that runs them**, and the scheduler walks past them every six hours
forever. They look like a plan and they function as a wall.

Two of them (B01, B02) will never have a runner and should stop being counted as
blocked: Track B donates cycles to someone else's pipeline, so there is nothing
here to run. `TRACKS.md` already says this; the board should learn to.

That leaves **six real gaps**, and they are the cheapest frontier available: each
is a question the lab already decided was worth asking, blocked only by an
afternoon of engineering.

**Costs:** one runner ≈ one focused session, on the evidence of A02 and P01,
both built and verified inside a day.
**Buys:** six dispatchable rungs — a scheduler that has somewhere to go.
**Known when:** `lab frontier` reports fewer than three unrunnable rungs.

## 2 · Two tracks have arrived and nobody said so

Track M is 18 rungs, 18 verified, nothing open. Track P is 1 of 1. Neither has a
question on the bench, so neither can ever be picked — they are complete, or
they are starved, and **the ladder cannot tell the difference.**

This is the quietest failure in the estate: a finished track looks exactly like
a neglected one, and both look like health.

**Costs:** a decision per track and two lines in `TRACKS.md`.
**Buys:** an honest answer to "is this lab still doing physics?"
**Known when:** every track either has an open rung or is explicitly marked
arrived, and the board stops printing `ARRIVED?`.

## 3 · Four harvested questions with nobody assigned

The lab has been writing down what it cannot answer for months. `lab frontier`
collected four on its first pass, and the best of them is the shape of the whole
opportunity:

> **M14** deferred pinning the Nishimori multicritical point to *"a large-L hero
> run"* — true when written. **M12 has since proven this box does 4.4 GPU-hour
> hero runs.** The question became affordable and nothing in the system noticed.

That one is now queued in the deep lane. The other three are not, and a
candidate with nobody assigned is a wish.

**Costs:** triage — six fields per candidate, including the kill condition.
**Buys:** the difference between a lab that collects regrets and one that
answers them.
**Known when:** every harvested candidate is either queued, promoted to a rung,
or explicitly dropped with a reason.

## 4 · The planner has no word for "nothing is worth running"

This is the deepest one and it caused a 26-hour outage this morning.

`plan_turn` scores existing rungs by value/cost, where value decays with
staleness. When no frontier work is available its answer is not to say so — it
is to pick the greenest, stalest thing and re-run it. Twelve consecutive passes
did exactly that. Every component behaved to spec, every receipt was honest,
every surface reported health, and the frontier did not move.

The deep lane already refuses this: an empty queue is a **report**, and it runs
nothing. The pulse lane cannot say it yet.

**Costs:** a status in `plan_turn` and a branch in the campaign that logs it.
**Buys:** the vacuum becomes loud instead of invisible.
**Known when:** a pass with nothing valuable available writes
`campaign: nothing worth a turn — frontier is <reason>` and burns no GPU.

## 5 · A human still chooses tomorrow night's work

The deep lane reads a file. That was deliberate — a process that picks its own
hours-long work unsupervised should be watched before it is trusted — but it
means the frontier moves only as fast as somebody edits `deep-queue.txt`.

The obvious next step is for the board to fill the queue: highest-value item,
kill condition attached, one job per night. It should not be taken until the
lane has run for a week and its receipts have been read.

**Costs:** wiring `lab frontier` into the queue, and a rule for what "highest
value" means.
**Buys:** a lab that advances while nobody is awake.
**Known when:** a week of deep-lane receipts exists and every one was work a
human would have chosen.

---

## The order

1. **Six runners** — the cheapest frontier work available, and it unblocks
   everything downstream.
2. **Two track decisions** — a ten-minute edit that makes the board truthful.
3. **The vacuum status** — small, and it closes the failure mode that already
   cost a day.
4. **Triage the four candidates** — one is queued; the rest need six fields each.
5. **Let the board feed the queue** — last, and only after the lane has earned it.

## What this note refuses to claim

That any of this makes the lab *good*. It makes the lab **busy in the right
direction**, which is a different and smaller thing. The science is already
honest: the checkers re-derive from pinned bytes, the controls killed two of my
own claims today, and A02's evidence now ships with the repo so a stranger can
check it without trusting us.

What has been missing is not rigour. It is **aim** — and aim is the only part of
this a machine should not be trusted to set alone. Items 1-3 are engineering and
can be done unsupervised. Items 4 and 5 decide what the lab spends its nights
asking, and those stay Ben's.
