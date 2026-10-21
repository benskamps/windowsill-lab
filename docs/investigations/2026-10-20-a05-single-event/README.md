# Cross-sector single-event search: first rung results

**Consumer:** Ben and the thread session, once, to decide whether a survey pre-registration comes next. One-off; retires nothing.
**Pre-registration:** `docs/preregistrations/2026-10-20-a05-single-event-mode.md`
(commit 4337a3c, before the prototype touched a real light curve).
**Code:** `src/lab/a05_events.py`, `src/lab/a05_multisector.py`,
`scripts/a05_events_control.py`. **Receipts:** `toi1231-control.json` (the
pre-registered run, 200 rolls, 60 injections) and `toi1231-control-quick.json`
(20-roll shake-out, kept for the record). **No survey was run.**

## Positive control: TOI-1231 b (TIC 447061717): passes

- **Data.** SPOC 2-min sectors 9, 10, 36, 63, 90, 99. **S37 was refused by the
  reader** (too few quality-zero cadences) and is recorded as unusable, not
  hidden. The published ephemeris puts 5 events in the usable data, one per
  sector.
- **Blind search** (no period prior): 5 events at SNR 29–37, 862 trials, 767
  vetoed, 95 survivors. The top survivor is **24.2455 d** (published
  24.245586 d), scoring 57.6 with all 5 events. The next family (727 d and its
  subharmonics) scores 44.7 on 3 events. Verdict: **exact**.
- **Placebo** (200 segment rolls, seed 2026): null max 49.4, median 40.2,
  0 of 200 ≥ 57.6, so **FAP = 1/201**. That passes the pre-registered line.
  The margin is the honest number to watch: the rolls keep all five real, deep
  dips, so chance alignments between real dips score about 40 on every roll.
  The null is *not* noise-level. It is "real dips, wrong timing", which is the
  right null for this question and a demanding one.
- **Inverted null** (brightenings paired): 0 events, S_max 0.
- **Masked placebo** (known transits removed): 0 events observed and 0 in every
  roll, so it **passes, but is uninformative**. On a quiet Tmag 10.3 star,
  noise never makes an SNR ≥ 7 event, so this check could not have failed here.
  It needs a noisier or more active star to have teeth. That is a gap for the
  next rung, stated rather than counted as a pass.

## Injection ladder (60 injections into the masked series)

| depth | detectable (≥ 2 events in data) | exact survives | top-ranked exact | alias only | missed |
|---|---|---|---|---|---|
| 4000 ppm | 14 | 13 | 10 | 0 | 1 |
| 2000 ppm | 14 | 9 | 7 | 3 | 2 |
| 1000 ppm | 14 | 1 | — | 0 | 13 |
| 500 ppm | 14 | 0 | — | 0 | 14 |

(4 of 60 injections had fewer than 2 events in data and are not counted.) On
this star the rung's floor sits between 1,000 and 2,000 ppm for 3-h events.
That floor is set by the event threshold SNR ≥ 7: a 1,000 ppm single event here
is SNR ≈ 6. When the true period survives it is usually, but not always,
top-ranked (10/13 at 4,000 ppm). In the other cases a long alias family that
the coverage cannot veto outranks it, and the output reports the whole family.

## What failed or needed fixing on the way

1. **The veto vetoed every true alias.** The pair's reference depth came from
   the scan (median in-box, at its best duration), while the epochs were checked
   with a mean box at the pair's duration. The events vetoed themselves.
   `tests/test_a05_events.py` caught it before any real light curve was
   searched. The fix measures both with the same box. A mutation check (veto
   disabled) turns the veto test red.
2. The first control run crashed on S37 (unusable file). The sector is now
   recorded and skipped.

## Not done, by design

No survey. No trial-factor pricing across stars. A noisier control star for
the masked placebo is the obvious next item before any survey
pre-registration.
