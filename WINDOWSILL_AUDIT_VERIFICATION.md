# Windowsill Audit — Verification Record

**Date:** 2026-06-26 (overnight) · **Method:** 8 parallel code-verification agents + 1 ground-truth
agent, each grounding every claim in `WINDOWSILL_PUBLIC_EXPERIENCE_AUDIT.md` against the actual code
and the live feed (`pot.json`). This record is the fact-check that gates the implementation work.

## Bottom line

The audit is **high quality and honest** — every structural finding verified true (7/8 confirmed
outright, 1 partially-correct), and every "healthy / what works" claim independently confirmed. Two
calibration notes: the audit **over-rates severity** (its P0s are really P1s, its P1s really P2s —
nothing is broken or dangerous on this calm page), and one cited "defect" (archive deep-links) is
**intentional by design**.

## Ground truth (verified 2026-06-26)

- Canonical feed the page reads: **`pot.json`** (committed; `web/index.html` consumes it directly).
- **M12 open**, **11 of 31** milestones verified (M01–M11), `runs: 13`, `reports[]: 23`.
- **Python tests: 273/273 pass** (repo `.venv`, ~35s). **JS growth-form tests: 7/7 pass.**
- Ising critical point reproduced (M01: χ-peak T≈2.30 vs Onsager 2.2692, ~0.2%).
- **New finding (not in audit):** the feed lists **23 report rows but only 16 artifacts exist on
  disk** — the 7 oldest rows (2026-06-14…06-18) have `href: null` and no backing file. So
  "23 on record" overcounts the physically-clickable archive by 7.

## Findings ledger

| # | Finding | Verdict | Audit sev | Real sev | Effort | Key evidence |
|---|---------|---------|-----------|----------|--------|--------------|
| 1 | Nightly runs M01 Ising; curriculum at M12; no `lab next` scheduler | **confirmed** | P0 | P1 | medium | `setup.py:98,179` static `lab.cli run`; `cli.py:735` → base Ising; no scheduler in HELP |
| 2 | Growth-form variety can't surface (fern always wins) | **confirmed** | P0 | P1 | small | `growth-forms.js:149` tallies mode over **all** milestones; physics=18/31 wins always |
| 3 | Static explainer prose stale ("right now 2D Ising", "Four verified") | **confirmed** | P0 | P1 | small | `index.html:520,551,560-563`; live = 11 verified, M12 open. Legend chip is correct (feed-driven) |
| 4 | Report links: `href` vs `url` mismatch | **partially** | P1 | P2 | trivial | Feed emits `href` (`archive.py:255`); page reads `rep.url` (`index.html:1201`). Archive-index deep-link is **intentional** (`13bb932`), not a bug |
| 5 | `runs 13` vs `23 on record` — both labeled "runs" | **confirmed** | P1 | P2 | trivial | `runs`=distinct days (`publish.run_cadence`); archive=`reports[].length`=23 distinct runs |
| 6 | Leaves not tappable/keyboard (title-tooltip only) | **confirmed** | P1 | P1 | medium | `index.html:985` per-leaf data in `<title>`; plain `<g>`, no tabindex/role/handler/panel |
| 7 | Engineering achievement hidden (no pipeline/stack) | **confirmed** | P1 | P2 | small | `index.html:515-570` metaphor + one physics explainer; no PyTorch/CI/contract/pipeline on page |
| 8 | Per-milestone story layer doesn't exist (~0%) | **confirmed** | — | foundation | medium | Schema/records carry only `id/title/status/track/growth_form/result`; public copy string-split from technical prose at `publish.py:139` |

## Nuances worth carrying into the work

- **#1 is freshly worse, not stale:** the M04→M11 ladder (6/24-25) added milestones, widening the
  gap between the static nightly (M01) and the curriculum front. M01 isn't even a named command — it's
  the un-prefixed default `run`. Two honest product directions: (a) explain heartbeat-vs-expedition on
  the page, or (b) build a milestone-aware `lab next`. (a) is the fast comms fix; (b) is the deeper fix.
- **#2:** `creeper`→`vine` and `moss`→`succulent` are aliased in the JS registry, so only 3 shapes
  (fern/vine/succulent) are even reachable today. Fix = select hero form from the **open** milestone's
  track, not the mode.
- **#3:** only the explainer *prose* drifted; the live legend chip (`#m-growth`) already shows the
  correct `11 / 31 verified · M12 open`. The worst line ("Four verified") sits inside the collapsed
  "For the curious" details.
- **#4:** one-line fix — read `rep.href || rep.url`. Don't "fix" the archive-index deep-link; it's
  deliberate (dated renders are gitignored and would 404).
- **#8 is the keystone:** Passes 1–3 of the audit all want plain-language fields. The cleanest seam is
  the parse pipeline (`publish.parse_milestones`); the per-report hand-written `headline` is the nearest
  existing analog to the proposed `result_plain`.

## Implementation sequence (this is being executed as stacked PRs; nothing auto-merges)

1. **Truth & orientation** — `href||url`; relabel legend `runs`→`nights`; feed-drive the stale count.
2. **Story layer** — durable per-milestone plain-language fields, merged into `pot.json` at publish.
3. **Garden + curriculum** — hero form from the open track; "garden of sciences" preview; four-phase
   "you are here" journey; tappable/keyboard leaves with a field-note panel.
4. **Proof** — opt-in engineering pipeline + recruiter-legible line.
5. **`lab next` prototype** (gated for Ben's decision) — milestone-aware scheduler.

Open decisions surfaced for Ben (nod queue): the heartbeat-vs-`lab next` product direction (#1), and
the 23-vs-16 feed/disk archive gap (backfill artifacts, or count only what's clickable?).
