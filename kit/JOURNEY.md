# The journey, start to finish

This page walks through the whole kit in order, from "I saw the posts" to
"someone else can check my work". Each step says what to do, which file
covers it, and when you're done.

| # | Step | Read | You're done when |
|---|---|---|---|
| 0 | Learn what a transit is | [`LEARN.md`](LEARN.md) | you can explain why a dip that repeats isn't automatically a planet |
| 1 | Set up | [`README.md`](README.md#quickstart) | `python -m lab.planetkit doctor` is all green, or you know which line isn't and why |
| 2 | Calibrate on a known star | [`README.md`](README.md#quickstart) | WASP-18 (TIC 100100827, sector 2) ends `already-known` |
| 3 | Pick your star | [`DATA.md`](DATA.md) | you have a TIC number, its sectors, and a reason |
| 4 | Preregister | [`PREREGISTRATION.md`](PREREGISTRATION.md) | the form is committed, before you've opened the light curve |
| 5 | Run the ladder | [`PROTOCOL.md`](PROTOCOL.md) | you have a receipt that passes `check_receipt` |
| 6 | Read the verdict | `python -m lab.planetkit explain` | you can say the status word and the one sentence that goes with it |
| 7 | Decide what's next | [`PROCEDURES.md`](PROCEDURES.md) | a lead gets a second sector, everything else gets written down |
| 8 | Share | [`BEFORE-YOU-POST.md`](BEFORE-YOU-POST.md) | your post uses only words from the table, and links the receipt and the commit |
| 9 | Find your people | [`COMMUNITIES.md`](COMMUNITIES.md) | you know which venue fits your result and what it asks of you |
| 10 | Come back | `python -m lab.planetkit ledger` | your ledger lists every star you've searched and what each one needs next |

## Notes on each step

**0. Learn.** You don't need a physics degree. You do need to know the three
things that most often look like a planet and aren't: two stars eclipsing
each other, an echo of some other rhythm in the data, and the star itself
pulsing. The lab's
search flagged 116 signals, and 66 of them were one of those.

**1. Set up.** `doctor` checks Python, numpy, the lab code, and whether MAST,
the NASA Exoplanet Archive and ExoFOP are reachable from your machine. Some
sandboxes and cloud agents can't reach them. If so, download the SPOC
`_lc.fits` files in a browser and use `--fits`.

**2. Calibrate.** Running a star whose answer is known first tells you the
setup works. If WASP-18 doesn't come back `already-known`, nothing you find
on another star means anything yet.

**3. Pick.** Any star TESS observed works. Good first picks are bright
(TESS magnitude under about 12), not crowded, and observed in two or more
sectors, so a lead can be checked in a second sector without a new
preregistration fight. Write down why you picked it. "It's the one from
the viral post" is a fine reason, as long as you say so.

**4. Preregister.** This is the step everyone skips and the one that makes
your result worth anything. The kit refuses to run without the form, and
warns on every receipt if the form wasn't committed before the run.

**5. Run.** About three minutes per sector at full size. The runner does the
blind search, the permutation null, the injection floor, the gates, the
catalog check and a placebo. You don't choose which of those to run.

**6. Read.** Every star ends in one of six words. Most honest runs end in
`nothing-above-threshold`, `refuted` or `already-known`. Those are results.
`incomplete` and `control-failed` mean the run says nothing.

**7. Next.** A `lead-awaiting-human-review` in one sector is provisional.
The next step is the same search, preregistered, on another sector. A lead
that persists goes to a human reviewer, and then to the ladder in
`BEFORE-YOU-POST.md`. Nothing in this kit promotes a lead for you.

**8. Share.** A refuted star, shared with its receipt, is more useful to
the field than a "candidate" with no receipt. Post the no-token line before
anything else.

**9. Community.** The venues that matter (ExoFOP, TFOP, Planet Hunters TESS,
AAVSO, Exoplanet Watch) each have their own rules. Since 2026-08-19, a
community candidate on ExoFOP needs a published paper first.

**10. Come back.** Every receipt you keep joins your own survey. The
ledger regrades each star across all your receipts, so a lead from one
sector turns persistent (or doesn't) when you search another. TESS goes
back to most of the sky every couple of years, so a provisional lead often
gets a new sector to check. Most stars end in `nothing-above-threshold`, and
each one still counts: the lab's own record is 12,898 searches and zero
planets claimed, and that denominator is the result.

## If you're an agent

Install the plugin (see [`README.md`](README.md#quickstart)) or read
[`skills/find-your-own-planet/`](skills/find-your-own-planet/SKILL.md), and follow it. It is this page, as hard rules.
