# windowsill-lab

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
```

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
- [**seed-in-a-pot**](https://github.com/benskamps/seed-in-a-pot) — a
  single seed on a windowsill, growing on real signals. Calmer DNA, real
  graphics.
- **windowsill-lab** (this) — same shape, but the patient observation is
  real physics instead of a fish or a sprout. Numbers, plots, theory.

One machine. One patient observation. Real signal. Accumulates over months.

## License

MIT
