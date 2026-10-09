# Data sources

Where TESS data and the catalogs live, how to pull them, and the traps. Researched for the kit on 2026-10-09 against `benskamps/windowsill-lab` @ `2436d02`.

> **What the kit's runner already does about the traps below:** it keeps only cadences with `QUALITY == 0` (stricter than lightkurve's `"hard"` mask, so scattered-light and Planet Search Exclude cadences are gone), reads SPOC PDCSAP only, and its catalog gate checks ExoFOP's CTOI table alias-aware (n = 1 to 4) as well as the NASA archive's TOI and confirmed-planet tables. If you pull data yourself with lightkurve, use `quality_bitmask="hard"`.
Every URL below was fetched on 2026-10-09 unless the verification table at the end says otherwise.

Vocabulary rule, same as the lab: a signal you find is a **candidate**. "Validated" and "confirmed" are statuses other people's evidence earns. Nothing in this file, and nothing the kit produces, claims a planet.

---

## 0. The one-screen map

| You need | Go to | Pull with | Cost / limits | Biggest trap |
|---|---|---|---|---|
| Light curves, bright stars, best quality | **SPOC 2-min (and 20-s)** at MAST | `lightkurve.search_lightcurve(..., author="SPOC", exptime=120)` | free, no login | Only ~20k selected targets per sector; your star may not be one |
| Light curves, everyone else to Tmag 13.5 | **TESS-SPOC FFI** and **QLP** HLSPs at MAST | `author="TESS-SPOC"` / `author="QLP"` | free | Coarser cadence (30 → 10 → 3.33 min by year); different detrending per pipeline |
| Faint or crowded stars (to Tmag 16) | **TGLC**, **GSFC-ELEANOR-LITE** HLSPs | `author="TGLC"` / `author="GSFC-ELEANOR-LITE"` | free | Many sectors bulk-download only, not via API |
| Your own photometry from pixels | **TESScut** (SPOC FFI cutouts) | `lk.search_tesscut(...)` / `Tesscut.get_cutouts(...)` | max 10,000 px area; max 10 concurrent requests per user (503 above that) | You own the aperture and the scattered-light handling |
| Star size, brightness, neighbours | **TIC v8.2** via MAST | `Catalogs.query_object(..., catalog="TIC")` | ~500k-row server cap per query | Phantom entries (artifacts, joins, splits) bias dilution |
| Clean Gaia astrometry / binarity | **Gaia DR3** (ESA archive) | `astroquery.gaia.Gaia.launch_job(adql)` | **CC BY-NC 3.0 IGO** license | DR4 lands 2026-12-02; RUWE > ~1.4 means "maybe not single" |
| "Has someone already found this?" | **TOI** table (NASA Exoplanet Archive) + **CTOI** table (ExoFOP) | TAP `select ... from toi`; CTOI CSV | free; ExoFOP blocks robots on its HTML pages | CTOIs are not in NExScI; the lab lost three leads to this |
| Pipeline's own detections | **TCE** CSVs per sector | bulk CSV from MAST | free | A TCE is a threshold crossing, not a candidate |
| Practice with answers in the back | **Kepler DR25** KOI + TCE + simulated sets | TAP `q1_q17_dr25_koi`, `q1_q17_dr25_tce` | free | Kepler ≠ TESS (4″ vs 21″ pixels) |
| Ground follow-up | ExoFOP (TFOP), ExoClock, ETD/VarAstro, ESO, LCO | mostly web forms | accounts for upload | Uploading a CTOI now needs a peer-reviewed paper |

---

## 1. TESS at MAST: the light curves

MAST (STScI) is the official archive for TESS. Everything here is public with no login. As of 2026-10-09 the mission is in Year 9 (Sectors 108–121); the TCE bulk page lists single-sector files through **Sector 106** and multi-sector runs through **1–96**.

### 1a. SPOC 2-minute (and 20-second) light curves, the gold standard

- **What it is:** NASA Ames Science Processing Operations Center light curves for pre-selected targets (the CTL plus Guest Investigator programs). 2-min cadence since Sector 1; 20-s cadence for a smaller set since Cycle 3.
- **What you get:** `_lc.fits` with `TIME`, `SAP_FLUX`, `PDCSAP_FLUX` (systematics-corrected and deblended), `*_ERR`, `QUALITY`, plus header keywords `CROWDSAP` (fraction of aperture flux that is the target) and `FLFRCSAP` (fraction of target flux the aperture captured). Also target pixel files (`_tp.fits`), and DV reports and time series (`_dvr.pdf`, `_dvt.fits`) for stars where the pipeline raised a TCE.
- **Lab usage:** this is the lab's primary feed. `src/lab/a01.py` queries `Mast.Caom.Filtered` (TESS, `timeseries`, `provenance_name == "SPOC"`), lists products with `Mast.Caom.Products`, keeps `productSubGroupDescription == "LC"` / `*_lc.fits`, and reads `TIME/PDCSAP_FLUX/PDCSAP_FLUX_ERR/QUALITY` with a dependency-free FITS parser. `src/lab/a04.py` pages a whole sector the same way for the blind BLS search.
- **Citation:** Ricker et al. 2015 (TESS mission, JATIS 1, 014003); Jenkins et al. 2016 (SPOC, SPIE 9913). MAST's required TESS acknowledgement (fetched from archive.stsci.edu/publishing/mission-acknowledgements):
  > This paper includes data collected with the TESS mission, obtained from the MAST data archive at the Space Telescope Science Institute (STScI). Funding for US Institutions for the TESS mission is provided by the NASA Explorer Program. STScI is operated by the Association of Universities for Research in Astronomy, Inc., under NASA contract NAS5–26555.

### 1b. TESS-SPOC FFI light curves

- **What:** the SPOC pipeline run on full-frame images for up to ~160,000 targets per sector (10,000 per CCD). Selection: all 2-min targets, H ≤ 10, within 100 pc, and Tmag ≤ 13.5.
- **Cadence follows the FFIs:** 30 min (Sectors 1–26), 10 min (27–55), 200 s (56 on).
- **Products:** LC, TPF, CBVs; DV products for TCEs since Sector 36 (minimum searched duration 2 h for FFIs vs 0.5 h for 2-min). Multi-sector searches since Sector 56.
- **Known issue (MAST page):** Sectors 40–68 light curves lack CDPP values (pipeline bug).
- **Naming:** `hlsp_tess-spoc_tess_phot_<16-digit TIC>-s<NNNN>_tess_v1_lc.fits`.
- **Cite:** Caldwell et al. 2020, RNAAS 4, 201. DOI 10.17909/t9-wpz1-8s54. https://archive.stsci.edu/hlsp/tess-spoc

### 1c. QLP (MIT Quick-Look Pipeline)

- **What:** MIT's FFI light curves for every star to Tmag < 13.5; the pipeline the TESS Science Office uses to find most FFI TOIs.
- **Notes from the MAST page:** since Sector 94 QLP uses the TGLC (Gaia-prior PSF) method; Sectors 74–79 and 99–104 carry timestamp corrections (74–79 re-released as `v02`); TXT versions exist only for Sectors 1–26.
- **Naming:** `hlsp_qlp_tess_ffi_s<NNNN>-<16-digit TIC>_tess_v01_llc.fits`.
- **License:** CC BY 4.0. DOI 10.17909/t9-r086-e880.
- **Cite:** Huang et al. 2020a, 2020b (RNAAS); Kunimoto et al. 2021, 2022. Requested acknowledgement:
  > We acknowledge the use of TESS High Level Science Products (HLSP) produced by the Quick-Look Pipeline (QLP) at the TESS Science Office at MIT, which are publicly available from the Mikulski Archive for Space Telescopes (MAST). Funding for the TESS mission is provided by NASA's Science Mission directorate.

  https://archive.stsci.edu/hlsp/qlp

### 1d. TICA (quick-look calibrated FFIs)

- **What:** MIT's fast calibrated FFIs (with WCS) that feed QLP, delivered per orbit since Sector 35 and per half-orbit since Sector 56. Images only, no light curves.
- **Use it when:** you need the newest sector before SPOC FFIs exist. Otherwise prefer SPOC FFIs.
- **Caveats on the page:** missing/lost cadences in many sectors (whole half-orbits in Sectors 77 and 78); a Sector 65 upset may spoil some Camera 4 CCD 4 frames. **TESScut stopped making TICA cutouts in August 2025** (astroquery docs); TICA FFIs are still downloadable from the HLSP page.
- **Cite:** Fausnaugh et al. 2020, RNAAS 4, 251. DOI 10.17909/t9-9j8c-7d30. https://archive.stsci.edu/hlsp/tica

### 1e. Deeper FFI products for faint and crowded stars

| Product | Depth | Coverage via API | Cite | DOI / license |
|---|---|---|---|---|
| **TGLC** (TESS-Gaia Light Curve) | to Tmag 16, PSF with Gaia DR3 priors, columns `cal_aper_flux`, `cal_psf_flux` | S1–26 via API; S1–55 by bulk script | Han & Brandt 2023, AJ 165, 71 | 10.17909/610m-9474, CC BY 4.0 |
| **GSFC-ELEANOR-LITE** | > 150 M light curves to 16 mag | S1–13 via API; S14–26 bulk only | Powell et al. 2022, RNAAS 6, 111 | 10.17909/j2yt-t417, CC BY 4.0 |
| CDIPS, PATHOS, TASOC, DIAMANTE | cluster / special-purpose sets | via `author=` in lightkurve | see each HLSP page | |

TGLC's own caveat: calibrated columns can be unreliable for stars fainter than ~15 Tmag near variable sources.

### 1f. TESScut (make your own light curve from pixels)

- **What:** time-series cutouts of SPOC FFIs around any position, returned as TPF-shaped files. Also tells you which sectors/camera/CCD saw a position.
- **Limits:** max cutout area 10,000 px (a 20×20 px cutout is ~10 MB per sector); **10 simultaneous requests per user, 503 above that** (astroquery docs). Default size 5 px.
- **Cite:** Brasseur et al. 2019 (Astrocut, ASCL ascl:1905.007). https://mast.stsci.edu/tesscut/

### 1g. Bulk and cloud

- **Bulk scripts** (curl shell scripts per sector for LC, TPF, DV, FFI; TCE CSVs): https://archive.stsci.edu/tess/bulk_downloads.html. TCE stats: `tess<date>-s<NNNN>-s<NNNN>_dvr-tcestats.csv`.
- **AWS Open Data:** bucket `s3://stpubdata/tess` (us-east-1), public domain, updated monthly, no account needed: `aws s3 ls --no-sign-request s3://stpubdata/tess/`. In astroquery: `Observations.enable_cloud_dataset()` then `download_products(..., cloud_only=True)`. Fastest path if you run in AWS us-east-1.

---

## 2. Pulling it in code

Signatures below were checked against the installed packages on 2026-10-09: **lightkurve 2.6.0**, **astroquery 0.4.11**, tess-point 0.9.5.post1, astrocut 1.4.0. The research container could not reach MAST from the shell (the network policy only allows package indexes), so the snippets were checked for API shape, not executed end to end. The lab's own runs of the same calls are the end-to-end evidence (`src/lab/a01.py`, `scripts/tic374861595_refit.py`).

```python
import lightkurve as lk

# 1. What exists for this star? Always look before you download.
sr = lk.search_lightcurve("TIC 374861595", mission="TESS")
print(sr)                                   # author, exptime, sector per row

# 2. The clean set: SPOC 2-min only, one product per sector.
spoc = lk.search_lightcurve("TIC 374861595", author="SPOC", exptime=120)
lcs = spoc.download_all(quality_bitmask="default")   # or "hard" / "hardest"
lc = lcs.stitch()                           # normalises each sector, then joins

# 3. No 2-min data? Fall back to FFI products.
ffi = lk.search_lightcurve("TIC 374861595", author=["TESS-SPOC", "QLP"])

# 4. Pixels yourself.
tc = lk.search_tesscut("TIC 374861595", sector=None)
tpf = tc[0].download(cutout_size=15)
```

`author=` values lightkurve 2.6.0 understands: `SPOC`, `TESS-SPOC`, `QLP`, `TASOC`, `TGLC`, `GSFC-ELEANOR-LITE`, `CDIPS`, `PATHOS`, `Kepler`, `K2`, `K2SFF`, `EVEREST`, `TESScut`.

```python
from astroquery.mast import Catalogs, Tesscut, Observations

# TIC row for one star
tic = Catalogs.query_criteria(catalog="TIC", ID=374861595)
# Everything within 2 arcmin (≈ 6 TESS pixels): your contamination suspects
nbrs = Catalogs.query_object("TIC 374861595", radius=0.033, catalog="TIC")
# Which sectors saw it
Tesscut.get_sectors(objectname="TIC 374861595")
```

```python
# Raw MAST API, the way the lab does it (no third-party deps)
# POST https://mast.stsci.edu/api/v0/invoke  with form field request=<json>
{"service": "Mast.Catalogs.Filtered.Tic",
 "params": {"columns": "ID,ra,dec,Tmag,rad",
            "filters": [{"paramName": "ID", "values": ["374861595"]}]},
 "format": "json", "pagesize": 500, "page": 1}
# neighbours: "Mast.Catalogs.Filtered.Tic.Position" with ra, dec, radius (deg)
# light curves: "Mast.Caom.Filtered" then "Mast.Caom.Products"
# download:     https://mast.stsci.edu/api/v0.1/Download/file?uri=<dataURI>
```

```python
# Has anyone already got it? (NASA Exoplanet Archive TAP, CSV/JSON out)
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
toi = NasaExoplanetArchive.query_criteria(table="toi",
        select="toi,tid,tfopwg_disp,pl_orbper,pl_trandep", where="tid=374861595")
# or plain HTTP:
# https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+toi,tfopwg_disp+from+toi+where+tid=374861595&format=csv
```

```python
# Gaia DR3 by source_id (the TIC carries the Gaia DR2 id; DR2→DR3 is via gaiadr3.dr2_neighbourhood)
from astroquery.gaia import Gaia
job = Gaia.launch_job("""
  SELECT source_id, ruwe, phot_g_mean_mag, bp_rp, parallax, parallax_error,
         teff_gspphot, radius_flame, non_single_star, ipd_frac_multi_peak
  FROM gaiadr3.gaia_source WHERE source_id = 4756470194913503104""")
job.get_results()
```

**Rate limits in practice.** None of MAST, NExScI or the Gaia archive publishes a hard request quota on the pages fetched. The real limits are: TESScut 10 concurrent per user; MAST queries die above ~500,000 rows ("Connection reset by peer"), so narrow the radius or add filters; astroquery's MAST default timeout is 600 s. The lab's own client retries 408/429/5xx twice with exponential backoff and enforces a wall-clock deadline per target (`a01._request`); copy that pattern. Cache everything: the lab keeps FITS under `~/.lab/cache/` and the CTOI CSV with its fetch time.

---

## 3. Stellar context: TIC, CTL, Gaia

### TIC v8.2 and the CTL

- **TIC:** ~1.7 billion point sources plus ~100 million extended sources, built on Gaia DR2 + 2MASS and others. TIC IDs are never deleted or reassigned between versions. Fields that matter for a transit search: `Tmag`, `Teff`, `rad`, `mass`, `logg`, `d`, `contratio`, `GAIA` (DR2 id), plus the disposition/duplicate flags.
- **CTL:** ~9.5 million stars ranked for transit detectability (CTL v8.01); it drives 2-min target selection.
- **Bulk:** CSVs in 2° declination strips (0.02–10.7 GB each) and the CTL (~497 MB) at https://archive.stsci.edu/tess/tic_ctl.html. (That page still labels columns "v8.1" while links point at `tic_v82`; treat v8.2 as current.)
- **Trap, phantoms (Paegert et al. 2021, arXiv:2108.04778):** *artifacts* (spurious 2MASS sources on diffraction spikes), *joins* (one star listed twice), *splits* (one bright entry that is really several Gaia stars). v8.2 flagged ~850k artifacts, ~3.18 M joins and ~7.95 M splits. Before Sector 14 reprocessing about 1 % of 2-min targets had flux ratios off by > 0.3. Tools: `tic_inspect`, `tic_contam` (github.com/mpaegert/tic_inspect).
- **Cite:** Stassun et al. 2018, 2019 (AJ); Paegert et al. 2021.

### Gaia DR3

- **What it adds over the TIC:** better parallaxes and photometry, `ruwe` (astrometric excess noise; > ~1.4 suggests an unresolved companion, Lindegren et al. 2021), `non_single_star`, `ipd_frac_multi_peak` (doubled image), FLAME radii, and neighbours down to G ≈ 21 at 0.4″ resolution, which TESS's 21″ pixels cannot separate.
- **Schedule (cosmos.esa.int/web/gaia/release):** DR3 13 June 2022, FPR 10 October 2023, **DR4 scheduled 2 December 2026** (66 months of data, including epoch photometry and astrometry), DR5 not before end of 2030. The kit should note that DR4 will change neighbour lists and RUWE for many stars.
- **License:** **CC BY-NC 3.0 IGO** (cosmos.esa.int/web/gaia-users/license). Non-commercial; fine for the kit, worth stating.
- **Cite:** Gaia Collaboration, Prusti et al. 2016 (A&A 595, A1); Gaia Collaboration, Vallenari et al. 2023, DOI 10.1051/0004-6361/202243940. ESA asks for a per-release acknowledgement; the DR3 credit page was in maintenance when fetched (see §7).
- **Access:** TAP at `https://gea.esac.esa.int/tap-server/tap` (ADQL), astroquery `Gaia`, bulk at http://cdn.gea.esac.esa.int/Gaia/. VizieR mirrors DR3 as I/355.

---

## 4. "Is this already known?" TOI, CTOI, TCE, confirmed planets

| Table | Where | What a match means | Live count (2026-10-09) |
|---|---|---|---|
| **TOI** | NExScI TAP `toi` (mirror of the TESS Science Office list); ExoFOP-TESS is the TFOP working copy | TSO vetted it; check `tfopwg_disp` | **8,148 rows**, last `rowupdate` 2026-10-01: PC 4,824 · FP 1,314 · CP 814 · KP 606 · APC 488 · FA 100 · blank 2 |
| **CTOI** | ExoFOP only: `https://exofop.ipac.caltech.edu/tess/download_ctoi.php?output=csv` | someone in the community filed it | not fetchable from the research container; lab cache had 5,137 rows on 2026-09-14 |
| **TCE** | MAST bulk CSVs per sector and sector range | the pipeline crossed 7.1σ; nothing more | S1–S106 single-sector files |
| **Confirmed planets** | NExScI TAP `ps` / `pscomppars` | published planet | **6,445** rows in `pscomppars` |

**TFOPWG disposition codes, verbatim from NExScI:** PC "planetary candidate", APC "ambiguous planetary candidate", CP "confirmed planet", KP "known planet", FP "false positive", FA "false alarm". The kit should keep these exactly.

**Traps the lab hit, with receipts:**

- **CTOIs are invisible to NExScI.** TIC 287328866 was filed in 2019 as two CTOIs at ~2.07 d (an eclipsing binary's primary and secondary filed separately); the 2026-08-18 hunt re-found it at the P/2 alias and the TOI/PS crosscheck said "unknown". Fix in `src/lab/exofop.py`: fetch the whole CTOI CSV (~1.4 MB), cache it with its age, refresh past 14 days, and match aliases at n = 1, 2, 3, 4 in both directions with 1 % tolerance.
- **A negative from a stale table is weak.** Always report the table's fetch time alongside "no match".
- **TOIs are preliminary.** The TOI releases page warns they are "based on preliminary data and likely to contain false positives."
- **Uploading a CTOI now needs a paper.** ExoFOP changed policy on 2026-08-19: "Candidates must be published in a peer-reviewed journal that offers online access before being uploaded to ExoFOP", with an approval request and a required paper URL. That is the lab's human transcription from `candidate_help.php` on 2026-09-14 (`docs/submissions/TIC374861595-CTOI.md` §0.1). ExoFOP disallows automated fetching, so it is **unverified from here**; re-read the live page before telling newcomers. RNAAS does not qualify (non-peer-reviewed by the AAS's own description).
- **Cite:** Guerrero et al. 2021, ApJS 254, 39 (TOI catalog, DOI 10.3847/1538-4365/abefe1). NExScI acknowledgement:
  > This research has made use of the NASA Exoplanet Archive, which is operated by the California Institute of Technology, under contract with the National Aeronautics and Space Administration under the Exoplanet Exploration Program.

  For ExoFOP use the AAS facility keyword `\facility{ExoFOP}`.

---

## 5. Kepler and K2: the training ground

Why start here: Kepler's answers are published, its pixels are 4″ (vs TESS's 21″), and the DR25 team released the simulated data that let you measure your own completeness and reliability.

- **Kepler (2009-05-02 to 2013-05-11):** 17 quarters, long cadence (~30 min) and short cadence (~1 min). Products `_llc.fits`, `_slc.fits`, TPFs, FFIs, DV time series. https://archive.stsci.edu/missions-and-data/kepler
- **DR25 KOI catalog (Thompson et al. 2018, ApJS 235, 38, arXiv:1710.06758):** 8,054 KOIs, 4,034 planet candidates, fully automated Robovetter. Completeness > 85 % and reliability > 98 % below 100 d; at 200–500 d low-SNR around FGK dwarfs, 76.7 % and 50.5 %. That last number is the lesson for newcomers: long-period, low-SNR "finds" are coin flips even for the best vetting machine ever built.
- **TAP tables:** `cumulative`, `q1_q17_dr25_koi`, `q1_q17_dr25_sup_koi`, `q1_q17_dr25_tce`, `q1_q17_dr25_ks` (stellar), `keplernames`; plus Certified False Positive and FPP tables, and the "Kepler Simulated Data" page (injections, inversions, scrambles) for measuring your own pipeline.
- **K2 (2014-02-04 to 2018-09-26):** ~80-day campaigns along the ecliptic, no official planet search. Pointing drift every ~6 h from thruster firings: use the K2SFF or EVEREST HLSPs (`author="K2SFF"` / `"EVEREST"`), not raw SAP. NExScI `k2pandc` has the planets and candidates.
- **Cloud:** `s3://stpubdata/kepler` (registry.opendata.aws/kepler).
- **Cite:** Borucki et al. 2010 (Kepler), Howell et al. 2014 (K2), Thompson et al. 2018. MAST Kepler acknowledgement:
  > This paper includes data collected by the Kepler mission and obtained from the MAST data archive at the Space Telescope Science Institute (STScI). Funding to US Institutions for the Kepler mission was provided by the NASA Science Mission Directorate. STScI is operated by the Association of Universities for Research in Astronomy, Inc., under NASA contract NAS5–26555.

A suggested graduation path for the kit: (1) recover a hot Jupiter from SPOC 2-min data (the lab's A01 does WASP-18 b, TIC 100100827); (2) blind-search one Kepler quarter and grade against DR25; (3) inject and recover synthetic transits to get your own detection threshold (the lab's A04 positive/negative controls); (4) only then search unlabelled TESS stars.

---

## 6. Ground follow-up archives

| Source | What it is | Public data | Reachable from the research container |
|---|---|---|---|
| **ExoFOP-TESS** | TFOP's shared workspace: TOI/CTOI tables, target pages, uploaded follow-up (SG1 photometry, SG2 recon spectra, SG3 high-res imaging, SG4 RVs, SG5 space) | target pages and tables public; uploads need an account | **No** (robots disallowed, shell egress denied). the lab fetches the CTOI/TOI CSVs from a home machine |
| **TFOP** (tess.mit.edu/followup) | the working group behind ExoFOP, five sub-groups; join via application | through ExoFOP | yes |
| **ExoClock** | ephemeris upkeep for ESA's Ariel targets; > 800 amateur and professional observers | ephemerides, observations, literature mid-times, annual data releases with papers | yes |
| **ETD / VarAstro** | Czech amateur transit-timing database (moved from var2.astro.cz/ETD to var.astro.cz/en/Home/ETD); transit predictions incl. a PLATO citizen project | per-planet O–C, depth, duration plots; data-usage page | yes |
| **NASA Exoplanet Watch** | amateur transit program with the EXOTIC reduction software | results feed the archive | **No** (old URL now redirects to science.nasa.gov/exoplanets; the sub-page errored) |
| **ESO Science Archive** | raw + processed La Silla/Paranal data (HARPS Phase 3 products etc.) | public after a ~1-year proprietary period; browsing and download without login | yes |
| **LCO Science Archive** | Las Cumbres network data (heavily used by TFOP SG1) | public after proprietary period | page is JS-only; content not verified |
| **NExScI time series** | `keltimeseries`, `superwasptimeseries`, `ukirttimeseries` TAP tables | public | yes |
| **SIMBAD / VizieR** (CDS) | identifiers, literature, catalog mirrors (Gaia I/355, TIC IV/39) | public | **No** from shell (proxy 403); WebFetch blocked by robots. the lab's code uses SIMBAD TAP from a home machine |
| **Planet Hunters TESS** (Zooniverse) | volunteer light-curve inspection since 2018-12-06 | discoveries published by the team | page loads, stats rendered as zero; active status not confirmed |

---

## 7. Traps checklist (for the kit's protocol)

1. **Quality flags.** lightkurve's `"default"` bitmask (17087) does **not** drop bit 2048/4096 (stray light) or 8192 (Planet Search Exclude). Scattered-light cadences survive by default. Use `"hard"` (24319) for searching, then check any detection against the default set.
2. **Scattered light.** Earth/Moon glow covers ~10–15 % of the field, at 2–6× sky; it ramps near orbit start/end. Dips that sit at the edges of an orbit are suspect until shown otherwise.
3. **Gaps.** Every sector is split by a downlink gap; momentum dumps leave flagged cadences. A "period" equal to a gap spacing or orbit length is the instrument.
4. **Crowding.** 21″ pixels. Check `CROWDSAP` (the lab flags < 0.8 as crowded, `a05_vetting.CROWDSAP_MIN`) and list TIC + Gaia neighbours within ~6 px. The lab measured that PDCSAP depth ratio tracks 1/CROWDSAP from 0.12 to 0.999, so PDCSAP is already deblended; don't correct twice (`a05_sky.py` docstring).
5. **Duplicates.** One star can have SPOC 2-min, 20-s, TESS-SPOC, QLP, TGLC and ELEANOR curves for the same sector. Pick one author per sector and say which; never stitch two pipelines' versions of the same sector together.
6. **Pipeline disagreement.** Depths differ by pipeline and by fitting model. The lab's TIC 374861595 page explains an 8.41 % trapezoid depth vs a 10.46 % SPOC DV depth from the same data.
7. **Aliases.** Search hits at P/2 and 2P of eclipsing binaries are routine. Match catalogues alias-aware (n = 1..4).
8. **Timestamps.** QLP Sectors 74–79 and 99–104 had timestamp corrections; use the latest version files.
9. **Version drift.** TIC 8.1 vs 8.2 labels; Gaia DR4 on 2026-12-02; TOI table updates weekly-ish. Record the version and fetch date of every table you used.
10. **Licensing.** QLP/TGLC/ELEANOR are CC BY 4.0, AWS TESS is public domain with attribution for papers, Gaia is CC BY-NC 3.0 IGO.

---

## 8. Verification log (fetched 2026-10-09)

Shell egress from the research container reaches only package indexes (PyPI etc.); archive hosts return proxy 403. Pages were fetched with the web-fetch tool instead.

| URL | Result |
|---|---|
| archive.stsci.edu/hlsp/qlp | ✓ content |
| archive.stsci.edu/hlsp/tess-spoc | ✓ content |
| archive.stsci.edu/hlsp/tica | ✓ content |
| archive.stsci.edu/hlsp/tglc | ✓ content |
| archive.stsci.edu/hlsp/gsfc-eleanor-lite | ✓ content |
| archive.stsci.edu/missions-and-data/tess | ✓ content |
| archive.stsci.edu/missions-and-data/kepler | ✓ content |
| archive.stsci.edu/missions-and-data/k2 | ✓ content |
| archive.stsci.edu/tess/tic_ctl.html | ✓ content |
| archive.stsci.edu/publishing/mission-acknowledgements | ✓ content (acknowledgements quoted) |
| archive.stsci.edu/tess/bulk_downloads/bulk_downloads_tce.html | ✓ content (S1–S106) |
| archive.stsci.edu/tess/bulk_downloads.html, …/bulk_downloads_ffi-tp-lc-dv.html | reached, script list not rendered by fetcher |
| mast.stsci.edu/tesscut/ | ✓ content |
| mast.stsci.edu/api/v0/ | ✓ partial (500k-row note) |
| astroquery.readthedocs.io …/mast/mast.html, …/mast/mast_cut.html | ✓ content |
| outerspace.stsci.edu/display/TESS/TESS+Archive+Manual | reached, intro only |
| heasarc.gsfc.nasa.gov/docs/tess/data-access.html, …/observing-technical.html | ✓ content |
| heasarc.gsfc.nasa.gov/cgi-bin/tess/webtess/wtv.py | ✗ robots disallowed |
| tess.mit.edu/observations/, /toi-releases/, /followup/ | ✓ content |
| exoplanetarchive.ipac.caltech.edu TAP `toi`, `pscomppars` | ✓ live queries (counts above) |
| exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html, API_TOI_columns.html, acknowledge.html, KeplerMission.html | ✓ content |
| exofop.ipac.caltech.edu/tess/ (and CTOI CSV, candidate_help.php) | ✗ robots disallowed / proxy 403 |
| gea.esac.esa.int/tap-server (live ADQL) | ✗ robots disallowed |
| gea.esac.esa.int/archive/documentation/GDR3/…/sec_credit_and_citation_instructions/ | reached, archive maintenance notice |
| cosmos.esa.int/web/gaia/release, /web/gaia-users/license, /web/gaia-users/credits | ✓ content |
| arxiv.org/abs/2208.00211, 2108.04778, 2103.12538, 1710.06758 | ✓ content |
| lightkurve.github.io/lightkurve/, …/about/citing.html | ✓ content |
| github.com/tessgi/tess-point | ✓ content |
| registry.opendata.aws/tess/ | ✓ content |
| www.exoclock.space | ✓ content |
| var2.astro.cz/ETD → var.astro.cz/en/Home/ETD | ✓ content after redirect |
| exoplanets.nasa.gov/exoplanet-watch/ → science.nasa.gov | ✗ redirect target errored |
| archive.eso.org | ✓ content |
| archive.lco.global | reached, JS-only page |
| simbad.u-strasbg.fr | ✗ robots disallowed |
| zooniverse.org Planet Hunters TESS | reached, stats showed zero |
| x.com, reddit.com, zenodo.org | ✗ not reachable from the research container |
| pypi.org lightkurve / astroquery / tess-point / astrocut | ✓ installed and introspected |

Facts in this file not taken from a fetched page: Ricker 2015, Jenkins 2016, Stassun 2018/2019, Borucki 2010, Howell 2014, Lindegren 2021 RUWE threshold, Prusti 2016, Brasseur 2019 ASCL id, the 7.1σ TCE threshold, K2 ~6 h thruster cadence, FFI cadence by year (consistent with the TESS-SPOC and QLP pages but not stated in one place). They are standard references; confirm the bibcodes when the kit writes its bibliography.
