# Start here

You don't need to know Python or git to begin. Pick the door that fits you.
All three lead to the same search, the same rules and the same six answers.

| If you... | Start with | You need |
|---|---|---|
| want to understand it first | **Read.** The lab's [TIC 374861595 page](https://www.brokenbranch.dev/windowsill/tic-374861595/) walks one real signal from plain words up, then [`LEARN.md`](LEARN.md), rung 0 | a browser |
| want to run it without installing anything | **Run in the browser.** [Open the starter notebook in Google Colab](https://colab.research.google.com/github/benskamps/windowsill-lab/blob/main/kit/start-in-browser.ipynb). It checks your setup on a known planet, WASP-18, and draws the folded light curve | a browser and a Google account |
| code, or have a coding agent | **Run it locally.** The [quickstart](README.md#quickstart), or install the Claude Code plugin and ask Claude to "find a planet the windowsill way" | Python 3, numpy and git |

## What happens in the browser notebook

1. It copies the lab's code into the notebook. Nothing touches your computer.
2. It checks it can reach NASA's TESS archive.
3. It writes down the question before looking at any data. The kit refuses
   to run without this step.
4. It runs the whole search on one TESS sector of WASP-18, in about three
   minutes.
5. It shows you the folded light curve: every dip lined up on top of each
   other.

The right answer is `already-known`, because WASP-18's planet has been known
since 2009. Getting it means your setup can find a real signal.

## The strongest answer

The most a run can say is *lead awaiting human review*. What comes after
that is in [`BEFORE-YOU-POST.md`](BEFORE-YOU-POST.md).

## After the first run

Go to [`JOURNEY.md`](JOURNEY.md), step 3: pick a star of your own. For a real
search, the question has to be committed somewhere public before you run, so
you'll need a free GitHub account. You can do it all in the browser: fork
this repository on GitHub, add your preregistration file to the fork with
GitHub's "Add file" button, then change the `git clone` line in the
notebook to your fork and drop `--depth 1` (the cell says how). The kit reads the commit date from your fork.
