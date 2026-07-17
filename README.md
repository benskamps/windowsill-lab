# windowsill-lab

> 🌲 Part of the [Broken Branch labs](https://www.brokenbranch.dev/labs/) — one human and a cluster of AI agents shipping strange software in public. This is one experiment among many; the front door lists them all.

A patient scientific instrument that lives in your machine: numerical physics,
trusted computation, open-archive astronomy, and the hardware itself as a sensor.

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
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell (use this instead of the line above)
# .\.venv\Scripts\Activate.ps1

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
installs a nightly job — Windows Task Scheduler on Windows, a systemd **user**
timer where available, or a cron line otherwise — that runs the next available
curriculum experiment (and an M01 heartbeat when the frontier has no runner),
refreshes `pot.json`, and pushes it. Inspect first with `lab setup --check`, or
see the plan with `lab setup --dry-run`; a dry run never writes or schedules
anything. No accounts, no service to sign into — publishing is your own
`git push`. The default Windows task runs while you are logged in, wakes a
sleeping machine, and retries a failed launch twice.

The report lives at `~/.lab/YYYY-MM-DD.html` (one per day) with a
`~/.lab/latest.html` pointer for convenience. Raw measurements are also
dumped as JSON next to each report so future-you (or any other tool) can
re-analyze without re-running.

## The phases

| Phase | What | Why |
|---|---|---|
| **1. Verify** | 2D Ising critical exponents on a square lattice. | Calibrates the lab against Onsager's exact 1944 result. The known answer makes a strong regression target; the ±0.1 gate catches a broken instrument but is not a precision proof of the whole codebase. |
| **2. Map known territory** | 3D Ising · Potts (q=3,4,5) · XY · Heisenberg models. | Phase diagrams in textbooks. Your numbers should match. Builds the rendering + measurement stack across more systems. |
| **3. Push the edge** | Spin glasses (Edwards-Anderson), frustrated lattices, quenched disorder. | Numbers from this corner are *worse-known* — many papers are from the 90s on clusters that a modern GPU dwarfs. Quietly verify or improve. |
| **4. Genuinely open** | Non-equilibrium phase transitions · aging dynamics · KPZ universality on weird geometries. | Active research areas where one home GPU patiently sweeping a parameter for months has a real chance at a plot nobody has. |

See [MILESTONES.md](MILESTONES.md) for the concrete next-step list.

## Four plants

The public windowsill renders each kind of work as a different but related plant.
Their first calibration commands are now runnable end to end:

```bash
lab m16                         # physics fern: 3D spin-glass aging
lab c01                         # compute vine: OEIS bytes + Lucas–Lehmer
lab a01                         # astronomy creeper: TESS / WASP-18 b
lab i01 --frames dark-stack.npy # instrument succulent: real capped-CMOS frames
```

`lab i01` without real frames deliberately writes a grey hardware-null report.
Synthetic fixtures test the classifier but can never masquerade as a sensor run.
The three successful calibrations remain amber until a human promotes them; a
machine pass alone never awards a green leaf.

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
four-plant garden grows on this lab's *passive citizen science*: each **verified**
milestone hardens into a node on its track's stem (a green leaf), a **failed
calibration** is a folded grey leaf (an honest null, kept on the books), the
patient overnight **runs** water the soil, and CPU heat sets the season.
Machine-checked measurements waiting for human review stay amber; only a human
promotion turns them green.

```bash
lab publish                 # write the committed pot.json (the live feed)
lab verify [IDs]            # re-derive verified milestones from their reports
lab verify --rerun-smoke    # + prove the engine reproduces itself (determinism gate)
lab scoreboard              # render the calibration scoreboard (measured vs theory)
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

**The instrument reproduces itself.** `lab verify` only regrades *saved* JSON —
it never re-runs the engine. `lab verify --rerun-smoke` closes that gap: it
re-runs a tiny pinned CPU config (`L=16`, `seed=42`, a handful of temperatures)
twice and proves the two runs are byte-for-byte identical (SHA-256), then checks
them against a committed golden artifact
([`tests/golden/determinism-l16-seed42.json`](tests/golden/determinism-l16-seed42.json)).
Self-determinism is enforced hard on every platform; the golden is bit-exact on
the platform that blessed it and graded within a tight, check-owned tolerance
across torch builds. CI runs this too, so a silently nondeterministic instrument
reds the build instead of shipping green.

**Controls, not prose.** `lab controls` runs two re-derivable probes and grades
them with `checks.check_controls`. A **positive** control: single-spin Metropolis
and single-cluster Wolff — two independent correct algorithms — must agree on
⟨|m|⟩ and energy at the same temperatures (they land within ~0.03 on a tiny CPU
lattice). A **negative** control: with the coupling switched off (`J=0`, free
spins) the *same* susceptibility estimator and peak-finder M01 uses must show a
**flat** χ with no prominent peak — the control's job is to *fail* the "there's a
T_c peak" gate, proving M01's peak is physics, not an artifact the pipeline
manufactures from noise. (CPU-toy scale; a GPU-scale control battery — e.g. a
bond-reshuffled spin glass that loses its aging signal — is a documented
follow-up.)

**One picture of everything vs theory.** `lab scoreboard` renders a single
house-style "money plot" — every verified milestone's measured value against its
exact/benchmark theory (Onsager `T_c`, γ/ν=7/4, β/ν=1/8, the Potts `T_c` ladder,
the XY universal-jump crossing, Wannier's residual entropy, the Nishimori-line
energy, the Allen–Cahn coarsening exponent), each in units of that milestone's own
check tolerance, with a shaded band at `|z| ≤ 1`. It reads the same committed
reports and the same benchmark constants `lab verify` grades against, and is
embedded at the top of the [archive index](reports/index.html).

**Receipts.** Every snapshot carries `provenance` — the code SHA (`-dirty` when
the tree has uncommitted changes), a sanitized environment string, and the
versions of `torch`/`numpy`/`matplotlib` a result depended on. Every run also
publishes a compact `reports/receipts/run-*.json` record: all checker inputs and
provenance remain, heavy visual snapshots are omitted explicitly, and both the
source report and each omission are SHA-256 pinned. Full reports remain local;
the newest full render is published as `reports/latest.html`.

## A portable result

[`release/m14-nishimori-v1`](release/m14-nishimori-v1/) and its
[`portable ZIP`](release/m14-nishimori-v1/m14-nishimori-v1.zip) package one deliberately
narrow claim as an offline verification release. Its standard-library checker
regrades eight persisted `L=24` aggregate energy measurements against the exact
Nishimori-line identity, checks every byte against a manifest, and rejects
undeclared or modified files. The deterministic ZIP can be extracted and checked
without this repository or a network connection; its external digest is pinned
in [`release/m14-nishimori-v1.sha256`](release/m14-nishimori-v1.sha256):

```bash
python verify_release.py receipt.json --strict
```

The boundary is as important as the pass: this is saved-data statistical
agreement, not a Monte Carlo rerun, a proof of the identity, a precise location
of the multicritical point, or a novelty claim. The original M14 report did not
record run-start provenance, so the release says that plainly instead of
reconstructing a cleaner story after the fact.

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
