# Find your own planet (honestly)

You saw the posts. Someone pointed Claude Code at NASA's TESS data, found a
repeating dip in a star's light, and a million people watched. Now you want to
try it. Good. The data are public, the tools are free, and an agent can write
the search for you in an afternoon.

This kit is what the windowsill lab learned doing exactly that, slowly and in
public, from August 2026 onward: 12,898 searches, 116 signals, nine known
planets re-found blind, seven leads, five of those killed by our own tests,
one still open, **zero planets claimed**. It gives you the same pipeline and the same rules,
cut down to one person and one star.

It will not let you say you found a planet. Nothing automated can, and every
step here is built around that.

## What you get

| Piece | What it does |
|---|---|
| [`JOURNEY.md`](JOURNEY.md) | **Start here.** The whole path, from learning what a transit is to sharing a result and coming back |
| [`PROTOCOL.md`](PROTOCOL.md) | The method, written down as ten rules, with where each one came from and an honest note on what is and isn't new |
| [`BEFORE-YOU-POST.md`](BEFORE-YOU-POST.md) | What you can truthfully say for each result, and the path from "signal" to "planet" (it is long) |
| [`PREREGISTRATION.md`](PREREGISTRATION.md) | The form you fill in and commit **before** you look at the data |
| [`skills/find-your-own-planet/`](skills/find-your-own-planet/SKILL.md) | A Claude Code skill that makes your agent follow the protocol |
| [`LEARN.md`](LEARN.md) | A five-rung learning ladder, from never having seen a light curve to knowing where results go |
| [`DATA.md`](DATA.md) | Where TESS data and the catalogs live, how to pull them, and the traps |
| [`PROCEDURES.md`](PROCEDURES.md) | How the professional field runs the same path, and where this kit stands against it |
| [`COMMUNITIES.md`](COMMUNITIES.md) | Every venue (ExoFOP, TFOP, Planet Hunters, AAVSO, journals) and what each asks of you |
| `python -m lab.planetkit` | The runner (`prereg`, `run`, `explain`, `ledger`, `doctor`): the lab's survey pipeline on one star, with its own placebo and a plain-English verdict |

## Quickstart

```bash
git clone https://github.com/benskamps/windowsill-lab && cd windowsill-lab
pip install numpy                      # the kit needs nothing else
export PYTHONPATH=src

# 1. Pick a star and the sectors you'll search. Write it down first.
#    Start with a star whose answer you already know: WASP-18 (TIC 100100827),
#    a confirmed hot Jupiter. The kit should end "already-known". If it
#    doesn't, fix your setup before you go looking for anything new.
python -m lab.planetkit prereg 100100827 --sectors 2 --out my-prereg.md
#    edit the question, then:
git add my-prereg.md && git commit -m "prereg: TIC 100100827 s2"

# 2. Run the ladder. --download fetches the declared sectors from MAST.
python -m lab.planetkit run --prereg my-prereg.md --download

# 3. Read what you're allowed to say.
python -m lab.planetkit explain receipt-TIC100100827-*.json

# 4. Every star you search joins your own survey. Keep the receipts.
python -m lab.planetkit ledger
```

Have SPOC files already? Use `--fits path/to/*.fits`. Only have a
`time,flux` table? Use `--csv` (one file per declared sector). In that case the
centroid and size gates can't run, and the receipt says so.

To give the rules to Claude Code, add the lab as a plugin marketplace and
install the kit from it:

```
/plugin marketplace add benskamps/windowsill-lab
/plugin install find-your-own-planet@windowsill-lab
```

On Claude Code 2.1.275 or later, one line does both:
`/plugin install find-your-own-planet --marketplace benskamps/windowsill-lab`.
Then ask Claude to "find a planet the windowsill way". The skill still runs
the code in this repo, so keep the clone.

A full run (B = 256 permutations, 3,000 trial periods, ten placebo scrambles)
takes about three minutes per sector on one core. `--quick` checks the plumbing in
seconds, and its receipts are marked so you won't post one by accident.

## What a result looks like

```
TIC 100000001: lead-awaiting-human-review

My search found a repeating dip that every automatic test failed to explain. It is a lead for a human to review, not a planet. It is in one sector only, so it is provisional: the next step is the same search on another sector.

  sector 20: SDE 9.5, P = 3.1791 d, word = lead-awaiting-human-review, placebo passed
  ! The preregistration was never committed, so nobody can tell it was written before the data were seen.

Do not say: I found a planet; I discovered a planet; NASA confirmed it; a new world
```

That is a real run of the kit at full size, on a **synthetic** star: a 0.4%
dip every 3.18 days planted in one simulated sector of 2-minute data with
0.1% noise. It took about three minutes on one CPU core. The star is fake
and the output is not.

Every star ends in exactly one of six words: `nothing-above-threshold`,
`refuted`, `already-known`, `lead-awaiting-human-review`, `incomplete`,
`control-failed`. Most stars, run honestly, end in the first three. That is the
search working.

## What the kit doesn't do (yet)

The runner is the lab's survey pipeline, and that pipeline stops short of
what the professional field does in a few places. They're listed here so
you don't mistake a gap for a pass. The full comparison, with sources, is
in [`PROCEDURES.md`](PROCEDURES.md#3--gap-table-windowsill-lab-against-the-field).

| Gap | What it means for your result |
|---|---|
| No statistical validation (TRICERATOPS) | Nothing here can move a small-planet lead past "candidate", even in principle |
| No difference imaging of its own | The centroid gate uses SPOC's flux-weighted centroids, which crowding can bias. CSV input has no centroid gate at all |
| Fixed 0.5-day running median detrend | The field's benchmark prefers a biweight at about 3x the transit duration. Transits longer than about 5.5 hours lose depth |
| BLS only, no TLS | TLS recovers more Earth-size signals at the same false-alarm rate |
| One sector searched at a time | Periods beyond about 9 days, and signals too shallow to show in one sector, are missed. Persistence is graded across sectors afterwards |
| SPOC 2-minute targets only | No FFI light curves, so most of the sky's faint stars are out of reach |

These are known, documented, and not quietly patched: changing the
pipeline changes every receipt the lab has published.

## Why bother with all this?

There are two reasons.

**Most dips aren't planets.** Of 116 signals the lab's search flagged, 36 were
two stars eclipsing each other, 16 were echoes of a different rhythm, and 14
were the star itself pulsing. A pipeline that skips those tests will hand you
those, labelled "candidate".

**The bar for being taken seriously moved.** Since 2026-08-19, ExoFOP (where
community candidates are filed) requires a peer-reviewed paper before an
upload. "Submit a CTOI" is no longer a form. That makes a dated, public,
falsifiable record the thing you actually need. A viral post doesn't count.

## Where this came from

The method is the windowsill lab's: the survey paper
([`docs/papers/2026-09-18-survey-methods-draft.md`](../docs/papers/2026-09-18-survey-methods-draft.md)),
the lead contract ([`docs/shelf-exit-contract.md`](../docs/shelf-exit-contract.md)),
and the A05 pipeline under `src/lab/`. The kit runs that code. It does not
reimplement it.
