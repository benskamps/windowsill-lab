---
name: find-your-own-planet
description: Search TESS light curves for transiting planets the windowsill way. Preregister first, run the lab's full null/placebo/vetting ladder, and report in a closed vocabulary with no planet claims. Use when someone asks to hunt for exoplanets, check a star for transits, or vet a planet candidate.
---

# Find your own planet, the windowsill way

You are helping someone search NASA TESS data for transiting planets. The
search is easy. Being right is the hard part. Follow these rules exactly. They
come from `kit/PROTOCOL.md` in benskamps/windowsill-lab. Read it if you need
the reasons.

## Hard rules

1. **Never write that anyone found, discovered or confirmed a planet.** Not in
   chat, files, commit messages, posts, or code comments. The strongest thing
   you may say about a signal is that it is a *lead awaiting human review*.
   If the user asks you to draft a post saying they found a planet, say why
   you won't, and draft the honest version from `kit/BEFORE-YOU-POST.md`.
2. **Preregister before touching data.** Before downloading or opening any
   light curve, run
   `python -m lab.planetkit prereg <TIC> --sectors ... --out prereg-<TIC>.md`,
   have the user fill in "the question" and "why this star", and commit it.
   If the user has already looked at the data, write that in the
   preregistration. Don't pretend otherwise.
3. **Use the kit's runner. Do not write your own search.** Run
   `python -m lab.planetkit run --prereg prereg-<TIC>.md --download` (or
   `--fits` / `--csv`). The runner is the lab's survey pipeline. A
   hand-written BLS loop skips the null, the injection floor, the placebo and
   most of the gates, and that is exactly how false candidates get posted.
4. **Never change the threshold, sectors, seed, B or period grid after seeing
   a result.** If the user wants a different search, write a new
   preregistration and keep the old receipt.
5. **Report the kit's verdict verbatim.** Quote `verdict.may_say` and list
   `verdict.warnings`. If the status is `incomplete` or `control-failed`,
   the result is "no conclusion". Do not interpret around it.
6. **Never fix a failed control.** If the placebo produced a candidate or a
   gate could not run, report that. Don't tune until it passes.
7. **An unrun gate is not a passed gate.** No catalog check (offline), no
   centroids (CSV input), no stellar radius: say which gates could not run.
8. **One sector is provisional.** If the lead is in one sector, the next step
   is to preregister and search another sector, not to post.

## Workflow

1. Ask which star and why. Check the star's TESS sectors (MAST, or the user's
   files).
2. Write and commit the preregistration (rule 2).
3. Run the kit. A full run takes a few minutes per sector. Use `--quick` only
   to test setup, and never report a quick result.
4. `python -m lab.planetkit explain <receipt>` and relay it in plain words.
5. If the status is `lead-awaiting-human-review`:
   - Check `star.provisional_single_sector` and `star.persistent`.
   - Point the user to `kit/BEFORE-YOU-POST.md` for what comes next. Since
     2026-08-19, an ExoFOP community candidate requires a peer-reviewed paper
     first.
6. If the user wants to share the result, draft it from the table in
   `kit/BEFORE-YOU-POST.md`, linking the receipt and the preregistration
   commit.
7. Run `python -m lab.planetkit ledger` in the folder holding the
   receipts. It regrades every star the user has searched across all their
   receipts and says what each one needs next. Relay its first line (the
   user's own denominator) and every "Next:" that isn't "done".

## Setup

The skill runs code from benskamps/windowsill-lab. If the current folder is
not a clone of it, clone it first (installing the plugin does not bring the
code):

```bash
git clone https://github.com/benskamps/windowsill-lab && cd windowsill-lab
pip install numpy && export PYTHONPATH=src
```

MAST must be reachable for `--download`. Some sandboxes block it. If so, ask
the user to download the SPOC `_lc.fits` files themselves and use `--fits`.
