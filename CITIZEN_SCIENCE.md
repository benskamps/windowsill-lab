# The Citizen Science book

> One machine, patient flops, real signal — pointed *outward*. This is the
> reference for the contribution tracks in [MILESTONES.md](MILESTONES.md): what
> each one is, where the result goes, and how we make it credible enough that
> strangers can trust and re-use it.

Every contribution grows a leaf on the seed at
[brokenbranch.dev/windowsill/](https://www.brokenbranch.dev/windowsill/) — and a
verified leaf can link straight to its official record.

## The one rule: calibrate first

A home result is only believable if the instrument first reproduces a *known*
answer. So every track opens with a calibration milestone (`*01`) that recovers a
published value within its error bars. No calibration, no claim — a result that
doesn't reproduce a known result is **a failed calibration, not a discovery**,
and it stays on the books as an honest null (`[~]`, a folded grey leaf).

## The tracks

| Track | Prefix | What a home machine actually does | Where it goes |
|---|---|---|---|
| **Compute & number theory** | `C` | GPU/CPU number crunching: primality, sequences | GIMPS · PrimeGrid · OEIS |
| **Astronomy (open archives)** | `A` | Download + analyze open survey data | AAVSO · MPC · ExoFOP · GWOSC |
| **Machine as instrument** | `I` | The hardware itself becomes a sensor | DECO/CRAYFIS · Zenodo |
| **Donate cycles (BOINC)** | `B` | Validated volunteer compute | Einstein@Home · Rosetta · WCG |

## The venues (and the IDs that make it count)

Credibility comes from publishing to recognized homes with a real contributor
identity, under an open license:

- **GIMPS** — account + assigned exponents; discoverers get formal credit.
- **OEIS** — author credit on accepted sequences / b-file extensions.
- **PrimeGrid / BOINC** — account + team; some projects (Einstein@Home) name
  volunteers on discovery papers.
- **AAVSO** — apply for an **observer code**; the standard amateur variable-star
  database.
- **Minor Planet Center** — an **observatory code** for asteroid astrometry.
- **ExoFOP / GWOSC** — open exoplanet follow-up and gravitational-wave data.
- **Zenodo** — a citable **DOI** for any dataset, beacon, or report.

## Provenance — receipts over vibes

Every published snapshot (`pot.json`) carries a `provenance` block:

```json
"provenance": {
  "code_sha": "9993026",                      // "-dirty" if the tree was uncommitted
  "env": "python 3.11.15 · linux",
  "deps": { "torch": "2.4.0", "numpy": "2.1.0", "matplotlib": "3.9.0" }
}
```

so any number can be traced to the exact code and environment that produced it,
and re-run. No host or user data is included. And `lab verify` re-derives each
verified milestone's headline number from its committed report — a green leaf is
a checked claim, not an honor-system tick.

## Linking a contribution to its record

When a milestone is verified, tag its line in `MILESTONES.md` with the official
record so the seed's leaf can point at it:

```
- [x] **C03** — Extend OEIS A000123 by 2,000 terms. (done 2026-08-01 — accepted) {venue=OEIS; url=https://oeis.org/A000123; doi=10.5281/zenodo.123456}
```

`venue`, `url`, and `doi` are optional and flow through to the snapshot untouched
(a verified milestone with a `url` becomes a leaf that links to its record).

**Picking the active experiment.** The lab runs one experiment at a time. Mark
the current one with `[>]` instead of `[ ]` and it becomes the open bud on any
track — otherwise the first pending milestone is promoted automatically. Add
`{progress=0.4}` to show how far along it is.

## Minting a DOI (GitHub → Zenodo)

1. Sign in to **zenodo.org** with GitHub and flip the switch on the
   `windowsill-lab` repo.
2. Cut a GitHub **release** (e.g. tag a month of `reports/`).
3. Zenodo archives the release and mints a DOI automatically.
4. Drop that DOI into the milestone's `{doi=…}` tag.

## Status, in public

This is a scaffold — the tracks are written, none of the contribution milestones
are claimed yet. As with the physics ladder: verify before claiming, publish the
nulls too, and let it accumulate over months.
