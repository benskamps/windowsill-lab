# A dashboard for one run

After a run, turn the receipt into one page: the system, the star and the
candidate, side by side.

```bash
python -m lab.planetkit_dashboard receipt-TIC100100827-2026-10-09.json \
    --fits path/to/*s0002*_lc.fits --star my-star.json
```

It writes `receipt-....html` next to the receipt. The page is a single static
file with no scripts and nothing fetched from the internet, so it opens
offline and passes a strict content-security policy.

| Panel | Shows | Comes from |
|---|---|---|
| The system | the star, and the orbit drawn to scale in star radii | the receipt's period; the orbit size is worked out with Kepler's third law only when the star file gives a mass |
| The star | radius, CROWDSAP and centroid offset per sector, plus anything in the star file | the receipt and the light-curve headers |
| The candidate | each sector folded on its own period, the per-sector table, the verdict, and what you may and may not say | light curves you pass with `--fits` or `--csv`, or the fold plots the runner writes beside the receipt |

## The rules it keeps

- **It shows nothing the verdict doesn't.** The thing blocking the light is
  drawn only for `lead-awaiting-human-review` and `already-known`, and only
  as a dashed outline labelled "not measured". A refuted star shows why it
  was refuted, and a star with nothing above threshold gets no orbit.
- **It checks the receipt first.** A receipt that `check_receipt` refuses
  never becomes a page. The finished page is checked against the same claim
  pattern too. The "what you may not say" list is the only place those
  phrases appear.
- **The light curve has to be the one the receipt searched.** A `--fits` or
  `--csv` file whose SHA-256 differs from the receipt's is refused.
- **Worked-out numbers say so.** The orbit radius is labelled "worked out",
  with its inputs named.

## The star file

Optional JSON, any of these keys, copied as given and shown as "star file":

```json
{"name": "WASP-18", "r_star_sun": 1.23, "m_star_sun": 1.22, "teff_k": 6400,
 "tmag": 8.8, "distance_pc": 123.5, "ra_deg": 24.354, "dec_deg": -45.678,
 "source": "TIC v8 via ExoFOP, read 2026-10-09"}
```

Name your source. Any other key is refused.

## The worked example

The lab's own open lead, TIC 374861595, has a hand-built version of this
page drawn from its dossier: two orbit radii that disagree (the density
tension), the grazing path, a Gaia neighbour chart, and three sectors'
folds. This module is that page made general enough for any run.
