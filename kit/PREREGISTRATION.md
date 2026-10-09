# Preregistration: TIC ________

Written ____-__-__, before any light curve for this star was opened.
Commit this file before you run the kit. The receipt records the commit.

`python -m lab.planetkit prereg <TIC> --sectors <s1> <s2> --out my-prereg.md`
writes this template with your numbers in it.

## The question

Does TIC ________ show a repeating transit-like signal in sectors ____ that
survives the full ladder?

## Fixed before looking

```json
{
  "tic": "0",
  "sectors": [0],
  "seed": 2026,
  "B": 256,
  "n_periods": 3000,
  "n_placebo": 10
}
```

The detection threshold is SDE 8.0, the same for every star. The kit refuses a
preregistration that sets a different one.

## Why this star

(One or two lines. "It was in the news" is an honest answer, so write it
down. Selection is part of the record.)

## What each answer will mean

- **nothing-above-threshold**: I will say the search found nothing, and
  quote the depth it could have found on this star.
- **refuted**: I will say what explained the signal, in the kit's words.
- **already-known**: I will say I recovered a known signal.
- **lead-awaiting-human-review**: I will say I found a signal the tests
  could not explain. I will not say I found a planet.
- **incomplete / control-failed**: I will say the run did not finish, and
  why, and post nothing else.

## What I will not do

- Change the sectors, seed, B or period grid after seeing a result.
- Re-run until I get an answer I like. If I re-run, I write a new
  preregistration and keep both receipts.
