# `web/` — the seed-in-the-pot page

This is the **canonical** seed-in-the-pot web surface: one portable
`index.html` with no build step that grows a clay pot from this
lab's real science. Human-promoted milestones harden into green nodes,
machine-checked measurements awaiting review stay amber, and a failed
calibration folds into an honest grey leaf. Overnight runs water the soil and
CPU heat sets the season. The light follows the visitor's own clock, so it stays
alive even when the feed is quiet.

It reads the live feed — the `pot.json` this repo publishes (`lab publish`) — so
the page and the engine ship and version together. Pull this one repo and you
have both.

## Two surfaces, one source

| Surface | Where | How |
|---|---|---|
| **Hosted** | `brokenbranch.dev/windowsill` | mirrors this file and its schema; the page reads this repo's raw `pot.json` |
| **Downloadable** | this repo | `lab web` opens it locally and reads the same canonical feed; fork it and point it at your own feed |

This file and `schema/pot.schema.json` are the sources of truth; the hosted
copies are mirrored together.

## Run it locally

```bash
lab web          # opens web/index.html in your browser
```

By default the page fetches the published feed from this repo using the single
`data-feed-url` value on the root `<html>` element. The visible `snapshot.json`
link is derived from that same value, so the readout and download cannot drift.
To grow it from **your** fork, point `data-feed-url` at your fork's raw
`pot.json`. Every
field in `pot.json` is optional. With no feed the page renders a procedural seed
and explicitly labels itself a local scene; it never resurrects an old
curriculum snapshot as if it were current.

The page uses Google Fonts when online and falls back to system serif/monospace
fonts otherwise. The Broken Branch guided walk is loaded only on the hosted
domain; local use has no missing companion-script or favicon requests.

See [`../schema/pot.schema.json`](../schema/pot.schema.json) for the feed
contract and [`../BACKLOG.md`](../BACKLOG.md) for where this is headed (notably:
different **growth forms** for different experiment types).
