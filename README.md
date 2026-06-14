# windowsill-lab

> 🌲 Part of the [Brokenbranch Lab](https://www.brokenbranch.dev/lab/) — one human and a cluster of AI agents shipping strange software in public. This is one experiment among many; the front door lists them all.

A patient numerical-physics instrument that lives in your machine.

> Tonight I ran 2D Ising on a 128×128 lattice across 21 temperatures in
> [1.50, 3.50], 40,000 measurement sweeps each. The susceptibility peaked at
> T ≈ 2.300 ± 0.050; Onsager says T_c = 2.2692. Wall time on the GPU: 11.4s.

That's a report you'd open with morning coffee. Phase 1 — verification —
reproduces the most famous exact result in statistical mechanics. Later
phases sweep less-mapped territory.

## Why

Your home GPU has time most academic clusters don't. A 16GB AMD card running
quietly for months can map a phase diagram nobody has bothered to map at
that resolution because it's not glamorous enough to apply for cluster hours
on. The point isn't more flops — it's **patient flops**.

Each night the lab runs one numerical experiment, produces a one-page report
with plots, fits constants, dumps the raw measurements as JSON. Over a year
you accumulate an actual notebook of physics observations from your own
machine.

## Quickstart

```bash
git clone https://github.com/benskamps/windowsill-lab
cd windowsill-lab
python -m venv .venv && source .venv/bin/activate

# PyTorch with ROCm support (adjust the channel if you're on CUDA)
pip install --pre torch --index-url https://download.pytorch.org/whl/nightly/rocm6.4
pip install -e .

lab run     # run today's experiment (Phase 1: Ising)
lab         # open the latest report in your browser
lab web     # open your seed-in-the-pot page locally (web/index.html)
lab setup   # install the nightly job so the windowsill grows on its own
```

One repo, everything in it: the **engine** (`src/`), the published **feed**
(`pot.json`), and the **page** people see (`web/` — see [`web/README.md`](web/README.md)).
`brokenbranch.dev/windowsill` is the hosted surface; this repo is the one you
pull, fork, and customize. Where it's headed lives in [`BACKLOG.md`](BACKLOG.md).

`lab setup` runs a pre-flight (Python, git remote, compute device) and then
installs a nightly job — a systemd **user** timer where available, a cron line
otherwise — that runs the experiment, refreshes `pot.json`, and pushes it. After
that the seed breathes without you. Inspect first with `lab setup --check`, or
see the plan with `lab setup --dry-run`. No accounts, no service to sign into —
publishing is your own `git push`.

The report lives at `~/.lab/YYYY-MM-DD.html` (one per day) with a
`~/.lab/latest.html` pointer for convenience. Raw measurements are also
dumped as JSON next to each report so future-you (or any other tool) can
re-analyze without re-running.

## The phases

| Phase | What | Why |
|---|---|---|
| **1. Verify** | 2D Ising critical exponents on a square lattice. | Calibrates the lab against Onsager's exact 1944 result. You know the code is correct because the answer is known to six decimal places. |
| **2. Map known territory** | 3D Ising · Potts (q=3,4,5) · XY · Heisenberg models. | Phase diagrams in textbooks. Your numbers should match. Builds the rendering + measurement stack across more systems. |
| **3. Push the edge** | Spin glasses (Edwards-Anderson), frustrated lattices, quenched disorder. | Numbers from this corner are *worse-known* — many papers are from the 90s on clusters that a modern GPU dwarfs. Quietly verify or improve. |
| **4. Genuinely open** | Non-equilibrium phase transitions · aging dynamics · KPZ universality on weird geometries. | Active research areas where one home GPU patiently sweeping a parameter for months has a real chance at a plot nobody has. |

See [MILESTONES.md](MILESTONES.md) for the concrete next-step list.

## The Citizen Science book

The four phases above are physics — they prove the lab can be trusted. Once
trusted, the same patient machine can point *outward* at real contributions:
number theory (GIMPS, OEIS, PrimeGrid), astronomy from open archives (AAVSO,
TESS/ExoFOP, GWOSC), the hardware itself as a particle detector (DECO/CRAYFIS),
and donated cycles (BOINC). Same rule throughout — **calibrate against a known
result first**, then contribute, then submit to the official record. Verified
contributions carry their record (`venue` / `url` / `doi`) and every published
snapshot ships a `provenance` block (code SHA + environment) so any number can be
traced and re-run. See [CITIZEN_SCIENCE.md](CITIZEN_SCIENCE.md).

## Feeding the seed

The lab feeds the **windowsill** — its calm, public face (the page now ships
from [`web/`](web/) in this repo). At
[brokenbranch.dev/windowsill/](https://www.brokenbranch.dev/windowsill/) a
single seedling grows on this lab's *passive citizen science*: each **verified**
milestone hardens into a node on the stem (a green leaf), a **failed
calibration** is a folded grey leaf (an honest null, kept on the books), the
patient overnight **runs** water the soil, and CPU heat sets the season.

```bash
lab publish                 # write the committed pot.json (the live feed)
lab verify [IDs]            # re-derive verified milestones from their reports
```

The snapshot is built by parsing `MILESTONES.md` (the single source of truth) plus
the run cadence in `reports/`/`~/.lab`, and the CPU temperature. It's deliberately
sanitized — milestone ids, titles, results, run counts, and temperature only; no
private data. A `lab run` refreshes it automatically, so the seed grows as the
science does.

**Live feed, no secrets.** `pot.json` is committed at the repo root; the
windowsill page reads it straight from GitHub raw through the site's edge cache.
A nightly run commits and pushes it. (`--gist <id>` / `POT_GIST_ID` remain an
optional legacy push target.) The shape is pinned by
[`schema/pot.schema.json`](schema/pot.schema.json) and carries a `schema_version`
so producer and page can't silently drift.

**Verified means checked.** `lab verify` re-derives each verified milestone's
headline number from the run report it shipped (e.g. M01's susceptibility peak
vs Onsager's exact `T_c`) and fails if it doesn't reproduce. CI runs it, so a
milestone can't wear a green leaf on the honor system.

**Receipts.** Every snapshot carries `provenance` — the code SHA (`-dirty` when
the tree has uncommitted changes), a sanitized environment string, and the
versions of `torch`/`numpy`/`matplotlib` a result depended on.

## Hardware notes

Built and tested on AMD RX 6900 XT (gfx1030) running ROCm 7 / PyTorch
nightly rocm6.4. The default 128² × 21 temperatures × 48k total sweeps run
completes in ~12 seconds. Larger lattices scale roughly with L², larger
temperature sweeps scale linearly.

If you have a CUDA card, swap the torch install for the standard CUDA
channel — everything else is provider-agnostic PyTorch.

## The family

Sibling toys built on the same DNA:

- [**fish-tank**](https://github.com/benskamps/fish-tank) — a terminal
  aquarium fed by real CPU heat and git activity. Aliveness from your
  machine's pulse.
- **windowsill-lab** (this) — same shape, but the patient observation is
  real physics instead of a fish. Numbers, plots, theory. Its calm public
  face is the **windowsill** page in [`web/`](web/)
  ([brokenbranch.dev/windowsill/](https://www.brokenbranch.dev/windowsill/));
  the original seed-in-a-pot desktop-toy repo is
  [archived](https://github.com/benskamps/seed-in-a-pot).

One machine. One patient observation. Real signal. Accumulates over months.

## License

MIT
