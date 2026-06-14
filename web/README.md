# `web/` — the seed-in-the-pot page

This is the **canonical** seed-in-the-pot web surface: one self-contained
`index.html` (no build step, no dependencies) that grows a clay pot from this
lab's real science. Verified milestones harden into nodes on the stem, a failed
calibration folds into an honest grey leaf, overnight runs water the soil, and
CPU heat sets the season. The light follows the visitor's own clock, so it stays
alive even when the feed is quiet.

It reads the live feed — the `pot.json` this repo publishes (`lab publish`) — so
the page and the engine ship and version together. Pull this one repo and you
have both.

## Two surfaces, one source

| Surface | Where | How |
|---|---|---|
| **Hosted** | `brokenbranch.dev/windowsill` | mirrors this file; its serverless proxy serves this repo's `pot.json` |
| **Downloadable** | this repo | `lab web` opens it locally; fork it and point it at your own feed |

This file is the source of truth; the hosted copy is a mirror of it.

## Run it locally

```bash
lab web          # opens web/index.html in your browser
```

By default the page fetches the published feed from this repo. To grow it from
**your** fork, point it at your fork's raw `pot.json` (set `POT_RAW` on the
proxy that serves it, or edit the fetch URL near the top of `index.html`). Every
field in `pot.json` is optional — with an empty feed the page still renders the
honest default curriculum and stays fully alive.

See [`../schema/pot.schema.json`](../schema/pot.schema.json) for the feed
contract and [`../BACKLOG.md`](../BACKLOG.md) for where this is headed (notably:
different **growth forms** for different experiment types).
