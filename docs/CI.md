# CI: what runs, when, and why

Three workflows live in `.github/workflows/`. This page says when each job
runs, how to force a run, and why the slow job runs on every change.

This repository is public, so GitHub-hosted minutes are free here. What CI
costs is waiting time and noise, not money.

## What runs when

| Workflow | Job | Push to `main` | Pull request | Manual |
|---|---|---|---|---|
| CI | `pipeline`: publish/verify/contract tests, `lab verify`, pot.json sync, ~20 s | yes | yes, drafts too | yes |
| CI | `web`: node suites + html-validate, ~15 s | yes | yes, drafts too | yes |
| CI | `physics`: the **whole** pytest suite + `lab verify --rerun-smoke`, about 15-30 min | yes | yes, drafts too | yes |
| CI | `alarm`: opens or updates the "main is red" issue | on failure | never | never |
| feed freshness | `freshness` | every 6 h (cron) | | yes |
| Planet kit plugin | `validate` (+ `release` on manual runs) | if `kit/`, `.claude-plugin/` or the workflow changed | same paths | yes |

A newer push to the same PR cancels the older run. Pushes to `main` are never
cancelled; each one gets its own verdict.

**Drafts run CI on purpose.** PRs here are opened as drafts and marked ready
seconds before merge. That makes the draft run the only pre-merge verdict.
Between 2026-09-18 and 2026-10-18 the one failing PR run (a `physics` failure
on #166) was on a draft, and every merged PR was merged after a green run on
its final commit.

## Why `physics` runs on every change

`physics` is not physics. It is the whole suite plus the determinism gate,
and the suite reads most of what changes in this repo. On 2026-10-18 the full
suite and `lab verify --rerun-smoke` were run under `strace -f`, with each
file access pinned on the test that made it:

- **It guards the page.** Seven test files read `web/index.html`
  (`test_hunt_block`, `test_publish`, `test_serialization_pin`,
  `test_shelf_fallback`, `test_turns`, `test_web_growth_forms`,
  `test_web_pots`); the last two also read `web/growth-forms.js` and
  `web/pots.js`. A web PR that edits the page is tested by this job.
- **It guards the data.** Receipts, `pot.json`, `MILESTONES.md`, `TRACKS.md`,
  `UNKNOWNS.md`, `evidence/`, `schema/`, `release/`, `docs/papers/`,
  `docs/survey/` and `scripts/` are read by tests or by `lab verify`. Every
  campaign pass rewrites `pot.json` and adds a receipt.

Of the 89 CI runs between 2026-09-18 and 2026-10-18, 9 changed only files
under `web/`, and all 9 changed `web/index.html`. A filter that never skips
`physics` when one of its inputs changes would have skipped none of them. The
rest of `web/` (the node test files, `hotplate.js`, `iso-kit.js`, `README.md`)
is never touched by the job, but no run changed only those files, and a gate
job would sit in front of `physics` on every run. So there is no filter. If the
suite stops reading the page, or most web work moves out of `index.html`, run
the trace again and revisit.

**Where the time goes.** In the 2026-10-18 push run, six files took about 70%
of the 16 minutes: `test_selftest` 219 s, `test_render` 132 s,
`test_a05_receipts` 120 s, `test_serialization_pin` 93 s, `test_archive` 60 s,
`test_planetkit` 60 s. The torch engine tests took 24 s between them. Making
those six files faster is test work, not workflow work, and it is the change
that would shorten the wait.

## Forcing a run

Actions -> **CI** -> **Run workflow**, then pick a branch. A manual run runs
every job, with or without a PR. From a terminal:

```sh
gh workflow run ci.yml --ref <branch>
```

## The feed-freshness watchdog

`freshness.yml` is the outside check that the campaign scheduler is alive. It
runs every 6 h against a 13 h staleness threshold, so a dead campaign pages
within about 19 h at worst. Every 12 h would page within about 25 h, still
inside the 29 h outage it was built for. Nothing in the file says 6 h is more
than it needs, so the cadence is unchanged; that is Ben's call.

## Self-hosted runners

None, on purpose: this repo is public, so any fork's pull request could run
its own code on a self-hosted runner, and that runner would be Ben's home box.
