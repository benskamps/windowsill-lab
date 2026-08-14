# The plant bible — painterly repaint reference (phase 1)

Art direction for the windowsill's painterly repaint, painted in the den
(Nano Banana, 2026-08-14 session; originals at
`personal-infra/den/artifacts/plant-bible-*.jpg` / `backdrop-*.jpg`).
Committed here shrunk to 512px-wide JPEG q80 (~350 KB total) as the
reference the repaint PRs are reviewed against.

The target look, read off these ten frames:

- **Leaves** as soft luminous gradient blades — a pale core that reads as
  light from within, falling to a deeper rim.
- **Pots** in worn-glaze terracotta.
- **Palette**: warm lamp-lit room against a cosmic night window
  (warm-vs-cosmic).

| file | subject |
|---|---|
| `plant-bible-{fern,vine,creeper,succulent,moss,sprout}.jpg` | one portrait per growth-form archetype |
| `backdrop-{dawn,day,dusk,night}.jpg` | the window's four phases — **reference only in phase 1**; wiring backdrops into the live page is phase 2, gated on Ben |

What phase 1 ships against this reference: per-archetype luminous-core
gradients (`GrowthForms.SKINS`), a group-level outer-glow filter, seeded
irregular blade edges, and the data-lit lumen (verified leaves glow by run
recency through the planner's own log2(1+days/7) staleness shape). The
growth GRAMMAR — root+tip homogeneity, node frames, spine/mat — is
untouched per the 2026-08-07 spec §16.
