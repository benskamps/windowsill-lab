# Learn: from zero to contributor

Part of the find-your-own-planet kit. Where the kit's own tools fit on this ladder:

- **Rung 2:** the kit's calibration run, WASP-18 (TIC 100100827) ending `already-known`, is the "fold a known planet" check done by the lab's pipeline. See [`README.md`](README.md#quickstart).
- **Rung 3:** the kit's runner *is* the standard vetting battery, plus a null and a placebo. Run it on your preregistered star ([`JOURNEY.md`](JOURNEY.md), steps 3 to 6).
- **Rung 4:** [`BEFORE-YOU-POST.md`](BEFORE-YOU-POST.md) and [`COMMUNITIES.md`](COMMUNITIES.md).

Written 2026-10-09. Every link below was opened on that date from a cloud sandbox unless it is marked **unverified**. That sandbox could not reach X, Reddit, Zenodo or ExoFOP, and a few NASA tool pages refuse automated fetches; those are listed at the end.

---

## How to use this

Five rungs. Each one has **do this first** (a thing to look at or run), then **read this** (the explanation), then **you're ready for the next rung when** (a check you can answer out loud).

| Rung | Level | You start as | You leave able to | Time |
|---|---|---|---|---|
| 0 | zero | someone who has never seen a light curve | say what a transit is and why one dip means nothing | an evening |
| 1 | beginner | someone who gets the idea | read a phase fold and the four numbers that describe a dip | a weekend |
| 2 | intermediate | someone with Python | download TESS data, run a period search, fold a known planet | 2 to 4 weekends |
| 3 | practitioner | someone with a signal | run the standard vetting tests and say what a signal is not | a month, on and off |
| 4 | contributor | someone with a vetted lead | know where results go, what the labels mean, and when to stop | ongoing |

The lab already has a from-zero layer. This ladder sends you through it rather than repeating it:

- **TIC 374861595, "Start from zero"**: www.brokenbranch.dev/windowsill/tic-374861595/ — a real open lead explained from plain words up to the working file.
- **The paper's reader's guide**: www.brokenbranch.dev/windowsill/paper/ — the survey in one breath, the numbers as a story, and a plain-language word list (transit, BLS, SDE, placebo, injection, eclipsing binary, harmonic alias, SPOC, TOI).
- **The experiment rooms**: A01 (fold a known planet), A04 (search stars nobody pointed you at), A05 (every candidate's odds of being nothing), at www.brokenbranch.dev/windowsill/experiments/.
- **Calibrate Before You Search**: www.brokenbranch.dev/learn/calibrate-before-you-search/ — the five habits, written so they carry over to A/B tests and model evals.

(The site pages above were read from the site repo, not fetched live: the sandbox's proxy blocked brokenbranch.dev.)

---

## Rung 0 · zero: a star gets a little darker

**Do this first.**
1. Watch NASA's transit animation, a planet crossing next to its light curve. [Exoplanet Transit Animations, NASA SVS](https://svs.gsfc.nasa.gov/13022/) — video files, a minute or two.
2. Read the lab's [TIC 374861595 page](https://www.brokenbranch.dev/windowsill/tic-374861595/) down to "And there is no coin". Ten minutes. It is the whole method in one real example.
3. Read [xkcd 882, "Significant"](https://xkcd.com/882/). One minute. It is the most important idea on this ladder, drawn as jelly beans.

**Read this.**

| Item | Format | Time | What it teaches | Why it's here |
|---|---|---|---|---|
| [What's a transit? (NASA)](https://science.nasa.gov/exoplanets/whats-a-transit/) | short article + animation | 2 min | a planet blocks light, the dip gives size and orbit | the official one-paragraph version |
| [Rubin planetarium video: Exoplanet Transits (NOIRLab)](https://noirlab.edu/public/videos/rubin-exoplanet-transits) | video | 3 min | depth gives size, spacing gives period; a small star makes a deeper dip | the depth-vs-star-size point matters later for red dwarfs like TIC 374861595 |
| [How We Find and Characterize (NASA)](https://science.nasa.gov/exoplanets/how-we-find-and-characterize/) | article + videos | 5 min | transits vs radial velocity, microlensing, imaging | so you know transits only give size, not mass |
| [Exoplanet detection methods (ESA)](https://www.esa.int/ESA_Multimedia/Images/2019/12/Exoplanet_detection_methods) | infographic | 2 min | all methods on one page | a picture to come back to |
| [TESS mission page (NASA)](https://science.nasa.gov/mission/tess/) | mission page | 3 min | what the satellite does | where the data comes from |
| [How Will TESS Look for Exoplanets? (NASA)](https://science.nasa.gov/missions/tess/how-will-tess-look-for-exoplanets/) | article + video | 5 min | pixels become brightness measurements | the step people skip; embedded video unverified (YouTube rate-limited the check) |
| [10 Steps to Confirm a Planet (NASA)](https://science.nasa.gov/universe/exoplanets/10-steps-to-confirm-a-planet-around-another-star/) | article | 7 min | the road from a dip to a confirmed planet; step 4 is false positives | shows how far a dip is from a planet |
| [The Little Book of Exoplanets, Joshua Winn (Princeton, 2023)](https://press.princeton.edu/node/47797) | book, paid ($22.95) | a few evenings | the whole field for a general reader, by the author of the standard transit chapter | the one book to buy at this rung |

**You're ready for Rung 1 when** you can say, without looking: why a planet makes a dip, why the dip has to repeat, and why NASA's software flagging something 259 times is still not a planet.

---

## Rung 1 · beginner: reading a dip

**Do this first.**
1. Open [A01: Finding a planet you were told was there](https://www.brokenbranch.dev/windowsill/experiments/a01/). It folds WASP-18 b: a 1% dip every 0.94145 days, timed over 177 transits, landing 11 ms from the published period. Read until you can explain folding to someone else.
2. Work through Andrew Vanderburg's [Transit Light Curve Tutorial](https://lweb.cfa.harvard.edu/~avanderb/tutorial/tutorial.html) (Harvard–Smithsonian CfA), especially [part 2](https://lweb.cfa.harvard.edu/~avanderb/tutorial/tutorial2.html), which reads a real Kepler light curve of HAT-P-7 b: depth, period, secondary eclipse, limb darkening. Free, illustrated, about an hour across pages.
3. Try [Planet Hunters TESS](https://www.zooniverse.org/projects/nora-dot-eisner/planet-hunters-tess) for 20 minutes: mark dips in real TESS light curves by eye. The project looked live on 2026-10-09 (NASA's listing, updated 2026-04-01, still says "Get started") but the page did not state its status, so check before relying on it. You will learn fast how much of a light curve is not a planet.

**The numbers a newcomer must grasp.** Examples first, then the rule.

| Number | Example | Rule of thumb | Trap |
|---|---|---|---|
| **Depth** | Jupiter across the Sun dims it about 1%. Earth across the Sun: about 0.008% (84 parts per million). | depth ≈ (planet radius / star radius)². Same planet, smaller star, deeper dip. | A grazing transit (clipping the edge, like TIC 374861595) is shallower and V-shaped, so depth underestimates size. Light from a neighbour star dilutes the dip and also hides size. |
| **Period** | WASP-18 b: 0.94 days. TIC 374861595: 1.94 days. | the time between dips. Needs at least two, really three or more. | The search can lock onto half or double the true period (a harmonic alias). An eclipsing binary at half its real period looks like one planet. |
| **Duration** | A hot Jupiter: 1–3 hours. Earth seen from afar: about 13 hours. | set by the star's size and the orbit's speed. A too-long or too-short duration for the star is a warning. | A box-shaped search guesses durations from a grid; a wrong guess blurs the depth. |
| **Shape** | flat bottom = whole planet in front of the star. V = grazing, or two stars. | U-shaped with a flat floor is what a planet usually looks like. | V-shapes are where eclipsing binaries hide. |
| **SNR (signal-to-noise)** | A 1% dip on a star that scatters 0.1% per point, with 100 points in transit: SNR ≈ (1 / 0.1) × √100 = 100. | SNR ≈ (depth / scatter) × √(points in transit). NASA's TESS pipeline flags a signal around 7.1σ. | SNR says the dip is probably not random scatter. It says nothing about whether it is a planet. |
| **False alarms** | The lab's survey: 3,000 trial periods per star, 12,898 searches, expected about one pure-noise crossing above its bar. | the more places you look, the more flukes you find. Price the noise before trusting a hit. | Comparing your peak against noise at the same period ignores the 2,999 other tries. This is the look-elsewhere effect (see xkcd 882 above). |
| **One dip** | A cosmic ray, a spacecraft momentum dump, scattered light from Earth, a flare's recovery. | one dip is an event, not a signal. | People post single dips as discoveries. Don't. |

**Read this.**

| Item | Format | Time | What it teaches | Why it's here |
|---|---|---|---|---|
| The paper's [reader's guide](https://www.brokenbranch.dev/windowsill/paper/) | web page | 15 min | the survey's numbers and a word list | the lab's own vocabulary, already in plain language |
| [A04: Finding planets nobody pointed you at](https://www.brokenbranch.dev/windowsill/experiments/a04/) | lab explainer | 20 min | blind search: no hints, wide period range, a measured gap between junk (6.6) and the bar (8.0) | the jump from "fold what you were told" to "search" |
| [Calibrate Before You Search](https://www.brokenbranch.dev/learn/calibrate-before-you-search/) | method | 9 min | price the noise, plant fakes, feed it nothing | the habits before the tools |
| [Look-elsewhere effect (The Decision Lab)](https://thedecisionlab.com/biases/look-elsewhere-effect) | article | 15 min | multiple comparisons in plain language, with the Higgs boson | the false-alarm row above, longer |
| [TESS Observations / sectors (TESS Science Support Center)](https://heasarc.gsfc.nasa.gov/docs/tess/sector.html) | reference table | 5 min | a sector is ~27.4 days, two spacecraft orbits; dates and pointings | you'll see "sector" everywhere next |
| [TESS FAQ](https://heasarc.gsfc.nasa.gov/docs/tess/faq.html) and [What is TESS?](https://heasarc.gsfc.nasa.gov/docs/tess/what-is-tess.html) | reference | 10 min | cadences, cameras, data releases | the operating manual, short version |
| [NASA exoplanet glossary](https://science.nasa.gov/exoplanets/glossary/) | reference | 5 min | ~24 core terms | for words the paper guide doesn't cover |
| [Half of Kepler's giant candidates are false positives (Space.com, 2015)](https://www.space.com/31320-kepler-giant-exoplanets-false-positives.html) | news | 4 min | about half of Kepler's giant-planet candidates were other stars | the base rate a newcomer should carry around |

**You're ready for Rung 2 when** you can look at a folded light curve and say its period, depth, duration and shape, and name two things that make a fake dip.

---

## Rung 2 · intermediate: the tools track

Needs Python and a free afternoon to install things. The kit's starter pipeline runs on these.

**Do this first.** Recover a known planet before you search for anything. In order:

| Step | Notebook | What you do |
|---|---|---|
| 1 | [What are LightCurve objects? (Lightkurve)](https://lightkurve.github.io/lightkurve/tutorials/1-getting-started/what-are-lightcurve-objects.html) | make a light curve, then flatten, fold and bin it |
| 2 | [Searching & downloading Kepler, K2, and TESS data](https://lightkurve.github.io/lightkurve/tutorials/1-getting-started/searching-for-data-products.html) | pull real TESS data for a named star |
| 3 | [How to recover the first TESS planet candidate](https://lightkurve.github.io/lightkurve/tutorials/3-science-examples/exoplanets-recover-first-tess-candidate.html) | clean a TESS light curve and fold Pi Mensae c |
| 4 | [Identifying transiting exoplanet signals in a light curve](https://lightkurve.github.io/lightkurve/tutorials/3-science-examples/exoplanets-identifying-transiting-planet-signals.html) | run BLS, get period/epoch/duration, mask the transit and search again |
| 5 | [How to recover a known planet in Kepler data](https://lightkurve.github.io/lightkurve/tutorials/3-science-examples/exoplanets-recover-a-known-planet.html) | Kepler-10 from pixels to detection |
| 6 | [What are Periodogram objects?](https://lightkurve.github.io/lightkurve/tutorials/1-getting-started/what-are-periodogram-objects.html) | find an eclipsing binary's period: the first false positive you'll meet |

This is A01 done with your own hands. If your period for a known planet doesn't match the published one, stop and find out why before going on. That is the lab's one rule: no calibration, no claim.

**Then the search algorithms.**

| Item | Level | Format | Time | What it teaches | Why it's here |
|---|---|---|---|---|---|
| [Astropy Box Least Squares](https://docs.astropy.org/en/stable/timeseries/bls.html) | intermediate | docs + code | 1 h | the BLS periodogram the lab and most beginners use | the search engine, documented |
| [Kovács, Zucker & Mazeh 2002, "A box-fitting algorithm in the search for periodic transits"](https://arxiv.org/abs/astro-ph/0206099) | practitioner | paper (free) | 2 h | the original BLS | read once you've run it, not before |
| [Transit Least Squares docs](https://transitleastsquares.readthedocs.io/en/latest/) | intermediate | docs | 1 h | a transit-shaped search, better for small planets | the next tool after BLS |
| [TLS tutorials (GitHub)](https://github.com/hippke/tls/tree/master/tutorials) | intermediate | 11 notebooks | a weekend | 01 quick start; 02 K2-3 b; 05 the grazing planet WASP-75; 06 TLS vs BLS; 09 optimal period grids; 11 a planet from TESS | notebook 05 is the grazing-geometry lesson TIC 374861595 needs |
| [Hippke & Heller 2019, the TLS paper](https://arxiv.org/abs/1901.02015) | practitioner | paper (free) | 2 h | why a transit shape beats a box | |
| [MAST TESS notebooks](https://spacetelescope.github.io/mast_notebooks/intro.html) | beginner → intermediate | notebooks | an hour each | under `/notebooks/TESS/`: read a light curve file (`beginner_how_to_use_lc`), a target pixel file (`beginner_how_to_use_tp`), a full-frame image (`beginner_how_to_use_ffi`), cut out FFIs with TESScut (`beginner_tesscut_astroquery`), search the TESS Input Catalog (`beginner_tic_search_hd209458`) | the archive's own way to get data, for when Lightkurve hides too much |
| [TESS Data Analysis Tools (TSSC)](https://heasarc.gsfc.nasa.gov/docs/tess/data-analysis-tools.html) | all | directory | 10 min | the community tool list: Lightkurve, wotan, eleanor, TESScut, tess-point, batman, exoplanet, juliet, DAVE, VESPA, TRICERATOPS, LATTE | the map of what exists |
| [Instrumental noise #1: data gaps and quality flags (Lightkurve)](https://lightkurve.github.io/lightkurve/tutorials/2-creating-light-curves/2-2-kepler-noise-1-data-gaps-and-quality-flags.html) | intermediate | notebook | 1 h | quality flags, gaps, one-point glitches | Kepler/K2 examples, not TESS, but the habit transfers |
| [TESS Archive Manual (MAST)](https://outerspace.stsci.edu/spaces/TESS/pages/14562808/TESS+Archive+Manual) and [TESS data products table](https://archive.stsci.edu/tess/all_products.html) | intermediate | reference | browse | file names, product types, where things are | for when a file name confuses you |
| [tessworkshop_tutorials (STScI, 2019)](https://github.com/spacetelescope/tessworkshop_tutorials) | intermediate | notebooks | varies | BLS, eleanor, exoplanet, lightkurve, starry, TESScut | old (last pushed 2019); some cells will break; still the cleanest BLS walk-through set |

**Courses and texts for this rung.**

| Item | Level | Format | Time | Cost | Why it's here |
|---|---|---|---|---|---|
| [Winn, "Transits and Occultations" (arXiv 1001.2010)](https://arxiv.org/abs/1001.2010) | intermediate | review chapter, free | 2–3 evenings | free | the standard transit-geometry reference; the chapter from Seager (ed.) *Exoplanets*. Every equation you need for depth, duration and impact parameter |
| [Seager & Mallén-Ornelas 2003](https://arxiv.org/abs/astro-ph/0206228) | intermediate | paper, free | 2 h | free | how depth, duration and shape pin down the star and planet; the maths behind "this duration is wrong for this star" |
| [The Diversity of Exoplanets (Coursera, Univ. of Geneva)](https://www.coursera.org/learn/exoplanets) | intermediate | MOOC, 7 modules | ~20 h | free to enrol, paid certificate | taught by Udry, Mayor and Queloz, who found the first planet around a sun-like star |
| [HarvardX: Super-Earths and Life (edX)](https://www.edx.org/learn/astronomy/harvard-university-super-earths-and-life) | beginner → intermediate | MOOC, self-paced | 7 weeks × 5–8 h | free to audit, $149 certificate | Sasselov; the "why bother" course |
| [Astrobiology: Exploring Other Worlds (Coursera, Univ. of Arizona)](https://www.coursera.org/learn/astrobiology-exploring-other-worlds) | beginner | MOOC | ~25 h | free to enrol | gentler; has an exoplanets module |
| ANUx "Astrophysics: Exploring Exoplanets" (edX, Paul Francis and Brian Schmidt) — [Class Central entry](https://classcentral.com/mooc/1635/edx-anu-astro2x-exoplanets) | beginner → intermediate | MOOC | self-paced | free access | the edX page itself is **unverified** (failed to load); listed via Class Central only |
| [MIT OCW 12.425, Extrasolar Planets (Seager, Fall 2007)](https://ocw.mit.edu/courses/12-425-extrasolar-planets-physics-and-detection-techniques-fall-2007/) | intermediate | lecture notes, problem sets | a semester, or pick lectures | free | the closest thing to a free textbook; problem sets to check yourself |
| [Sagan Summer Workshop 2012: Working with Exoplanet Light Curves](https://nexsci.caltech.edu/workshop/2012/) | intermediate | talk PDFs, videos, hands-on | pick sessions | free | light-curve modelling, transit timing, Kepler data, taught by the people who did it |
| [Astrobites](https://astrobites.org/) and [Astrobites guides](https://astrobites.org/guides/) | intermediate | daily paper summaries | 5 min each | free | grad students explaining papers to undergrads; no transit guide, but [Beyond Chi-Squared: correlated noise](https://astrobites.org/2014/07/01/beyond-chi-squared-an-introduction-to-correlated-noise/) is the one to read here |

**You're ready for Rung 3 when** you've recovered two known planets yourself, within error bars of the published periods, and one of them was on TESS data you downloaded.

---

## Rung 3 · practitioner: saying what a signal is not

This is the hard half. Finding a dip is easy. The work is killing it, and writing down what survived.

**Do this first.**
1. Read the paper's §5, the refutation record: seven leads, five killed by the lab's own later checks. Then §4, calibration (nine known planets found blind, zero hits from 1,850 scrambled fakes). Links from the [reader's guide](https://www.brokenbranch.dev/windowsill/paper/).
2. Read [A05: Every candidate carries its own odds of being nothing](https://www.brokenbranch.dev/windowsill/experiments/a05/) — 256 shuffles per candidate, 0 of 25 placebos survived.
3. Download one real NASA vetting report and annotate it: [MAST notebook: Retrieve TESS Data Validation Products](https://spacetelescope.github.io/mast_notebooks/notebooks/TESS/beginner_astroquery_dv/beginner_astroquery_dv.html), then compare against [a sample DV report for TESS ID 300871545](https://ntrs.nasa.gov/api/citations/20190032046/downloads/20190032046.pdf). Every page of that PDF is a test you're about to learn.

**The checks, as questions.**

| Question | Test | Where to learn it |
|---|---|---|
| Is it on this star or a neighbour? | centroid shift, difference image, pixel-by-pixel look | [Verifying the location of a periodic signal (Lightkurve)](https://lightkurve.github.io/lightkurve/tutorials/3-science-examples/periodograms-verifying-the-location-of-a-signal.html) |
| Is it two stars eclipsing at half the period? | odd vs even depths | [Twicken et al. 2018, Kepler Data Validation I](https://arxiv.org/abs/1803.04526) (explains every DV test; TESS's pipeline is built on it) |
| Is there a second, shallower dip half an orbit later? | secondary eclipse search | Twicken 2018; Vanderburg tutorial part 2 (HAT-P-7 b's secondary) |
| Is the shape right for a planet on this star? | duration vs stellar density; U vs V | Seager & Mallén-Ornelas 2003; TLS notebook 05 (grazing) |
| Is the period real or an alias? | fold at ½× and 2×; harmonic check | lab paper glossary "harmonic alias"; TLS notebook 09 |
| How likely is noise alone? | shuffle the data, rerun, compare peaks | A05; Calibrate Before You Search |
| Could the search see a dip this size here at all? | inject fakes, see what fraction come back | Calibrate Before You Search; paper §4 |
| Given everything, how probable is a false positive? | false-positive probability (FPP) | TRICERATOPS below |

**Tools and papers for this rung.**

| Item | Level | Format | Time | What it teaches | Why it's here |
|---|---|---|---|---|---|
| [TRICERATOPS docs](https://triceratops.readthedocs.io/en/latest/) with [TESS example](https://triceratops.readthedocs.io/en/latest/tutorials/example.html) and [Kepler example](https://triceratops.readthedocs.io/en/latest/tutorials/kepler_example.html) | practitioner | docs + notebooks | a weekend | Bayesian FPP for TESS candidates, single- and multi-sector | the standard TESS tool for "how likely is this a false positive" |
| [Giacalone et al. 2021, TRICERATOPS paper](https://arxiv.org/abs/2002.00691) | practitioner | paper | 2 h | 384 TOIs vetted, 12 validated | read the thresholds: an FPP number alone validates nothing. This is the trap in the viral TIC 4206066 post (FPP 0.03–0.04 is above the cut that paper uses) |
| [Morton 2012, vespa](https://arxiv.org/abs/1206.1568) | practitioner | paper | 2 h | the original automated validation | where FPP came from |
| [Lissauer et al. 2012, "Almost all of Kepler's multiple planet candidates are planets"](https://arxiv.org/abs/1201.5424) | practitioner | paper | 1 h | why multi-planet systems are rarely false | a base-rate argument worth having |
| [LATTE](https://github.com/noraeisner/LATTE) (`pip install tessLATTE`) | practitioner | interactive tool | an afternoon | the Planet Hunters TESS vetting diagnostics, one target at a time | the human-scale vetting bench. The `PlanetHunters/LATTE` address does not resolve; use `noraeisner/LATTE` |
| [LEO-Vetter](https://github.com/mkunimoto/LEO-Vetter) and [Kunimoto et al. 2025 (arXiv 2509.10619)](https://arxiv.org/abs/2509.10619) | practitioner | code + paper | a weekend | automated pass/fail vetting for TESS; ~20k M-dwarf detections cut to 172 candidates | what a robot vetter throws away, measured |
| [Thompson et al. 2018, Kepler DR25 Robovetter](https://arxiv.org/abs/1710.06758) and [Coughlin et al. 2016](https://arxiv.org/abs/1512.06149) | practitioner | papers | 3 h | completeness and reliability, measured with injections and inversions | the grown-up version of the lab's placebo and injection tests |
| [Guerrero et al. 2021, the TOI catalog](https://arxiv.org/abs/2103.12538) | intermediate → practitioner | paper | 2 h | how TESS candidates are vetted and labelled | the vocabulary you'll be judged in |
| [SHERLOCK](https://github.com/franpoz/SHERLOCK) | practitioner | end-to-end pipeline | varies | search, vet, fit in one package | a reference to compare the kit's pipeline against |
| [Sagan Summer Workshop 2018: "Did I Really Just Find an Exoplanet?"](https://nexsci.caltech.edu/workshop/2018/) ([hands-on sessions](https://nexsci.caltech.edu/workshop/2018/hos.shtml)) | practitioner | handouts, videos, hands-on | a week, or pick sessions | validation and follow-up: VESPA tutorial, EXOFASTv2 fitting, TESS validation handout | the whole rung as a workshop, free. 2016 ["Is There a Planet in My Data?"](https://nexsci.caltech.edu/workshop/2016/) covers the statistics side |
| [exoplanet](https://docs.exoplanet.codes/en/latest/) and [juliet](https://juliet.readthedocs.io/en/latest/) | practitioner | fitting libraries | weekends | probabilistic transit fits with honest error bars | for when you need a radius with uncertainties, not a BLS guess |
| [The Exoplanet Handbook, Perryman, 2nd ed. (Cambridge, 2018)](https://www.cambridge.org/core/product/750759E015FDCF469D141F0046198519) | practitioner | reference book, 952 pp, paid | dip in | everything, with references | the shelf book |
| [Exoplanets, ed. Seager (U. Arizona Press, 2011)](https://uapress.arizona.edu/book/exoplanets) | practitioner | graduate text, 544 pp, $40 | dip in | the field by chapter; many chapters free on arXiv (Winn's is one) | |
| Haswell, *Transiting Exoplanets* (Cambridge, 2010), ISBN 9780521139380 | intermediate | undergraduate text, paid | weeks | the only textbook built around transits | publisher page **unverified** (returned errors twice); ISBN confirmed by search |

**You're ready for Rung 4 when** you can take a signal and write one paragraph that says what it is not, test by test, with the numbers, and the one thing you could not rule out.

---

## Rung 4 · contributor: where results go, and the words to use

**Labels.** The field has a fixed vocabulary for where a signal stands. Use it as written. Never say "planet" for anything the field hasn't confirmed.

| Label | Meaning |
|---|---|
| TCE | Threshold Crossing Event: NASA's pipeline saw a repeating dip above its bar. Most are not planets. |
| TOI | TESS Object of Interest: the TESS team's own follow-up list. [TOI releases](https://tess.mit.edu/toi-releases/) warn they include false positives. |
| CTOI | Community TOI: a candidate proposed from outside the team, through ExoFOP. |
| PC / APC | planet candidate / ambiguous planet candidate. |
| FP / FA | false positive (astrophysical, e.g. an eclipsing binary) / false alarm (instrumental or noise). |
| KP / CP | known planet / confirmed planet. Confirmation usually means a mass measurement or statistical validation that passes published thresholds. |
| the lab's own | a closed 18-term vocabulary with no word for "planet"; the furthest a machine goes is *lead awaiting human review*. TIC 374861595 is an **open lead**. |

TFOP working-group dispositions as listed on ExoFOP are **unverified from here** (ExoFOP is blocked from the sandbox); the PC/APC/FP/FA/KP/CP set above is the one the TOI catalog paper uses.

**Where things go.**

| Venue | What it's for | Link | Note |
|---|---|---|---|
| ExoFOP-TESS | where CTOIs are filed and follow-up notes live | exofop.ipac.caltech.edu/tess/ | **unverified** (blocked from the sandbox) |
| TESS Follow-up Observing Program | five subgroups; SG1 does ground photometry to rule out nearby eclipsing binaries | [TSSC TFOP page](https://heasarc.gsfc.nasa.gov/docs/tess/tfop.html), [MIT follow-up page](https://tess.mit.edu/followup/) | neither page says whether amateurs can join |
| NASA Exoplanet Archive | confirmed planets and the TOI table | [home](https://exoplanetarchive.ipac.caltech.edu/), [counts](https://exoplanetarchive.ipac.caltech.edu/docs/counts_detail.html), [video demos](https://exoplanetarchive.ipac.caltech.edu/docs/videos.html), [tips](https://exoplanetarchive.ipac.caltech.edu/docs/tip_archive.html) | the TOI table, periodogram service and transit service pages are **unverified** (they refuse automated fetches) |
| NASA Exoplanet Watch | observe transits of known planets with a small or remote telescope, reduce with EXOTIC, submit to AAVSO | [hub](https://science.nasa.gov/citizen-science/exoplanet-watch/), [how to contribute](https://science.nasa.gov/citizen-science/exoplanet-watch/how-to-contribute/) | active (updated 2026-09-27). The old exoplanets.nasa.gov link now redirects elsewhere; use these |
| AAVSO Exoplanet Section | amateur transit photometry | [exoplanet photometry](https://aavso.org/exoplanet-photometry/), [section](https://www.aavso.org/exoplanet-section) | |
| Planet Hunters TESS | volunteer dip-marking | [project](https://www.zooniverse.org/projects/nora-dot-eisner/planet-hunters-tess), [education](https://www.zooniverse.org/projects/nora-dot-eisner/planet-hunters-tess/about/education) | status not stated; check |
| Zenodo | a citable DOI for a dataset or report | zenodo.org | **unverified** (blocked) |

Context for the count, 2026-10-08 per the Archive's counts page: 6,445 confirmed planets; 8,148 TESS project candidates, 4,823 of them still awaiting a disposition; 1,008 TESS planets confirmed. A new candidate joins a queue of thousands. That's why the paragraph that says what it is not matters more than the claim.

**When to stop.** A single-telescope photometry search can't measure mass. If the open question is mass (as it is for TIC 374861595: giant planet or brown dwarf), the next step is radial-velocity time on a large telescope, which a home lab doesn't have. Write that down, file what you have, and say "open lead".

---

## Glossary: words not already in the paper's guide

The paper's reader's guide already covers: transit, light curve, TESS, sector, TIC, BLS, SDE, threshold crossing, disposition, closed vocabulary, recovery, placebo, injection, lead, refutation, eclipsing binary, harmonic alias, SPOC, TOI, CTOI, ExoFOP. These are the extra ones a newcomer hits on this ladder.

| Word | Plain meaning |
|---|---|
| phase fold | cut the record into lengths of one guessed period and stack them, so every dip lands on top of the others |
| epoch (T₀) | the time of one reference mid-transit; with the period it predicts every future dip |
| cadence | how often a brightness measurement is taken (TESS: 2 minutes for chosen stars; the full-frame images less often) |
| FFI | full-frame image: TESS's whole-camera picture, which holds stars nobody chose in advance |
| TPF | target pixel file: the small stack of pixels around one star, over time |
| aperture | the pixels you add up to get a star's brightness; a bad one lets a neighbour in |
| contamination / dilution | light from other stars in your aperture, which makes dips look shallower |
| detrending / flattening | removing slow wiggles (star spots, spacecraft drift) so dips stand out; done badly, it eats dips |
| quality flag | a marker on a data point the pipeline doesn't trust |
| momentum dump | a thruster firing on the spacecraft; it makes fake features at known times |
| scattered light | Earth or Moon light in the camera, usually near the ends of each orbit |
| impact parameter (b) | how far from the star's centre the planet crosses: 0 is dead centre, near 1 is grazing |
| grazing | the object only clips the star's edge; V-shaped, shallow, size hard to pin down |
| limb darkening | stars are dimmer at the edge, which rounds the bottom of a dip |
| secondary eclipse | the small dip when the companion goes behind the star; a deep one means the companion glows, so it's probably a star |
| odd/even test | compare alternate dips; different depths mean two stars at double the period |
| centroid shift | the star's light centre moving during a dip, meaning the dip is on a neighbour |
| TCE | threshold crossing event: anything NASA's pipeline flagged |
| DV report | data validation report: NASA's per-signal vetting PDF |
| FPP | false-positive probability: the odds, under a model, that a signal isn't a planet |
| statistical validation | calling a candidate a planet because its FPP is below a published threshold, without a mass |
| radial velocity (RV) | measuring the star's wobble to get the companion's mass |
| brown dwarf | an object between a planet and a star in mass; looks like a giant planet in a transit |
| look-elsewhere effect | search enough places and something will look significant by chance |
| completeness / reliability | what fraction of real signals you catch / what fraction of your catches are real |
| injection-recovery | plant fake dips, count how many come back; measures completeness |
| M dwarf / red dwarf | small cool star; dips are deeper there, and most nearby stars are one |

---

## Verification log

Checked 2026-10-09 with a web-fetch tool from a cloud sandbox. Things a reader should know:

**Corrected while checking.**
- BLS paper is astro-ph/**0206099** (astro-ph/0202297 is an unrelated Seyfert galaxy paper).
- LATTE lives at github.com/**noraeisner**/LATTE (PyPI `tessLATTE` points there).
- LEO-Vetter's canonical repo name is `mkunimoto/LEO-Vetter`.
- MIT OCW 12.425 is the **Fall 2007** edition.
- The Geneva Coursera course is titled **The Diversity of Exoplanets**. *Super-Earths and Life* is on **edX**, not Coursera.
- Seager (ed.) *Exoplanets* was published January **2011**.

**Retired or not found.**
- Las Cumbres Observatory's *Agent Exoplanet* is a legacy site, no longer active. Left off.
- NASA's standalone "Ways to find a planet" interactive was not found; *Eyes on Exoplanets* ([info](https://science.nasa.gov/exoplanets/eyes-on-exoplanets-web/)) replaces it as the interactive.
- No free Snellen lecture notes found; MIT OCW 12.425 stands in.
- No Astrobites guide covers transits specifically.

**Unverified (could not open from here; check in a browser).**
- ExoFOP-TESS, Zenodo, X, Reddit (blocked from the sandbox).
- NASA Exoplanet Archive TOI table, periodogram and transit-service pages (refuse automated fetches; linked from the Archive's own tools page).
- Haswell's Cambridge page; the ANUx edX course page.
- The STScI Science Data Products Description PDF (linked from the MAST products table).
- Embedded NASA YouTube videos (rate-limited).
- brokenbranch.dev pages were read from the site repo, not fetched live.

**Not opened, only linked from a verified page:** SHERLOCK docs and tutorial repo; exo.MAST; the Exoplanet Watch subpages beyond "how to contribute"; the Join TFOP page.
