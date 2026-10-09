# Planet kit: communities and venues

*Where a newcomer with a transit candidate goes, what each place accepts, and how to avoid getting ignored or burned.*
Checked 2026-10-09. Venues change their rules: re-check anything marked ⚠️, and anything you're about to act on, from a normal browser.

**Verification key:** ✅ = fetched and read on 2026-10-09. ⚠️ = couldn't be fetched by the research agent (robots or proxy); the fact is second-hand and the source is named. Verify ⚠️ items from a normal browser before relying on them.

---

## 0. The one thing to know first

**ExoFOP no longer takes raw community candidates.** Since **2026-08-19**, the CTOI upload rule reads "community planet candidates must first be published in a peer-reviewed journal with online access before being uploaded", and uploads go through a "Published Candidate Upload Request" approval. ⚠️ ExoFOP blocks automated fetching, so this is second-hand from two independent reads of `exofop.ipac.caltech.edu/tess/candidate_help.php` on 2026-10-08: [windowsill-lab PR #160](https://github.com/benskamps/windowsill-lab/pull/160) ("since 2026-08-19 CTOIs must be published in a peer-reviewed journal first") and [klucilla/refute issue #18](https://github.com/klucilla/refute/issues/18). The same help page also says candidates "can also be presented in a Research Note of the AAS (RNAAS)", that "at least two of period, epoch and depth are required", and to "never assign a lowercase letter (b, c, ...) before the planet is confirmed in the refereed literature."

What this changes for the kit:
- The old path ("found a dip → post a CTOI on ExoFOP") is closed to newcomers. Paras Chopra's post still says he plans to "report to NASA's ExoFOP as Community TESS Objects of Interest" ✅ ([substack](https://invertedpassion.substack.com/p/vibe-astronomy-discovering-exoplanets)). He will hit this gate.
- The practical newcomer route is now **RNAAS (or another refereed outlet) → Published Candidate Upload Request → CTOI.** Whether RNAAS satisfies "peer-reviewed" is an open question: RNAAS itself says it is "not peer reviewed but moderated" ✅. The candidate-help page names RNAAS explicitly, so it looks like the intended route, but **confirm with exofop-support@ipac.caltech.edu before planning on it.** refute #18 lists the same email as its open question.
- No lowercase letters. Write "TIC 4206066.01" or "candidate", never "TIC 4206066 b". The memecoin's name ("…TIC 4206066 b") breaks this rule on its own.

---

## 1. The ladder at a glance

| Rung | Venue | What it's for | Newcomer can enter? | Verified |
|---|---|---|---|---|
| Learn | Astrobites, Exoplanet Watch (no-telescope path), AAVSO guide | Learn vetting and the vocabulary | Yes, free | ✅ |
| Practise on known planets | Exoplanet Watch, ExoClock, ETD/VarAstro, AAVSO Exoplanet DB | Real transit photometry with feedback, a track record | Yes | ✅ |
| Get eyes on a candidate | Planet Hunters TESS Talk | Volunteers and the PHT team discuss lightcurves | Yes, but it's their candidates' home, not yours | ✅ (research page); Talk ⚠️ |
| Publish a dated record | RNAAS; arXiv astro-ph.EP (needs endorsement) | A citable, moderated record of a candidate | RNAAS yes; arXiv needs endorsement | ✅ |
| Register the candidate | ExoFOP CTOI | Puts it on the professional follow-up radar | Only **after** refereed publication (since 2026-08-19) | ⚠️ |
| Coordinate follow-up | TFOP Working Group | Ground photometry, spectroscopy, imaging, RVs | Yes, by application, with evidence of past results | ✅ |
| Request telescope time | TESS DDT; TESS GI (Cycle 10) | Get TESS to watch a star | Anyone can ask; DDT ≥6 weeks before sector | ✅ |
| Talk about it publicly | HN, r/ClaudeAI, X, Substack | Share the method | Yes; reputational risk lives here | HN ✅; Reddit/X ⚠️ |

---

## 2. Venue by venue

### 2.1 ExoFOP-TESS and the CTOI path ⚠️

- **Who's there:** NExScI/IPAC run it; TFOP members, TESS team and follow-up observers read it. It is the single place where TOIs and CTOIs collect follow-up notes, files and dispositions. TFOP's own page says "TFOP-related follow-up data shall be submitted to ExoFOP-TESS at https://exofop.ipac.caltech.edu" ✅ ([tess.mit.edu/followup/exofop-tess](https://tess.mit.edu/followup/exofop-tess/)).
- **What it accepts now:** see §0. Peer-reviewed publication first, then an upload request. Minimum fields: two of period, epoch and depth, each with uncertainties; duration helps.
- **How to submit:** ExoFOP account → Published Candidate Upload Request → CTOI. ⚠️ Exact form names come from the second-hand reads above.
- **Why it matters even with the gate:** TFOP's publication policy (v21, 2026-07-12) ✅ says that a CTOI "submitted to ExoFOP more than two months prior to its posting by the TESS project" earns its contributors an invitation to "join as an author on any publication pertaining to that cTOI for the first time." Being early on ExoFOP is how a community finder gets real credit.
- **Gets you ignored:** missing uncertainties, a lowercase planet letter, a "planet" claim, a candidate that's already a TOI or a known EB (check the TOI list and the [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/) first ⚠️).
- **Read from a browser:** https://exofop.ipac.caltech.edu/tess/ and `…/tess/candidate_help.php`.

### 2.2 TESS Follow-up Observing Program (TFOP) ✅

- **Who's there:** the professional follow-up network in five sub-groups. SG1 handles seeing-limited photometry (Karen Collins), SG2 recon spectroscopy (Sam Quinn), SG3 high-resolution imaging (David Ciardi), SG4 precise RVs (Dave Latham) and SG5 space photometry (Diana Dragomir). Jessie Christiansen chairs ExoFOP-TESS. Its primary goal is to "measure masses for 50 transiting planets smaller than 4 Earth radii." ([overview](https://tess.mit.edu/followup/))
- **Who can join** ([apply page](https://tess.mit.edu/followup/apply-join-tfop/)): observers with suitable facilities, or **general members** without facilities, for example people "leading TESS-based science projects or publications". The application is freeform email and must state that you have read and will follow the [Charter](https://tess.mit.edu/wp-content/uploads/TFOPWG_Charter_v21_20260712.pdf) and the [Publication Policy](https://tess.mit.edu/wp-content/uploads/TFOPWG_Publication_Policy_v21_20260712.pdf). "Citizen scientist applicants should include 2-3 examples of observational results you have produced." SG1 prefers "pixel scales of 1 arcsec or less."
- **Etiquette (from the policy):** before publishing a validation or mass on a TOI, check TFOP tools for other groups and post a preliminary abstract to the TESS Wiki. Offer authorship to whoever supplied unpublished results. ExoFOP uploads are not refereed publications, but RNAAS notes count for TFOP results.
- **Realistic newcomer use:** you probably don't join on day one. Your candidate gets TFOP attention by being a CTOI on ExoFOP. Joining as a general member makes sense once you have a published candidate or a body of photometry.
- **Press:** NASA Goddard offers media coverage for TESS discoveries, requested "at least 6 weeks before submitting it to arXiv" ✅ ([policies page](https://tess.mit.edu/followup/data-submission-policies/)). This is the sanctioned publicity route. A viral thread is not.

### 2.3 Planet Hunters TESS (Zooniverse) ✅ / Talk ⚠️

- **Who's there:** the Zooniverse volunteer crowd plus the PH team (Nora Eisner's project; Oxford, Adler and Minnesota logos). Volunteers mark transits in TESS lightcurves; Talk is where candidates and eclipsing binaries get discussed. ([research page](https://www.zooniverse.org/projects/nora-dot-eisner/planet-hunters-tess/about/research))
- **What it accepts:** classifications and Talk discussion of *their* lightcurves. It is not an intake desk for candidates found by your own pipeline. The PHT team vets volunteer finds and has uploaded them to ExoFOP as CTOIs itself ✅ ([PHT blog, 2019](https://blog.planethunters.org/2019/05/20/exciting-new-planet-candidates/)).
- **Rule you must know:** anyone publishing results based on Talk information must cite Eisner et al., email the PH team about credit and, where results depend substantially on PH, authorship, and credit the contributing volunteers. "Agreement with this policy is necessary in order to use results from the platform." ✅
- **Best newcomer use:** classify for a few weeks. It's the cheapest way to train your eye on real TESS systematics (momentum dumps, scattered light, EBs). Ask on Talk whether a TIC you're looking at has been discussed. Never mine Talk for candidates and then publish them as your own.
- **Gets you ignored:** dropping links to your own project, announcing "I found a planet", ignoring the credit policy.

### 2.4 AAVSO Exoplanet Section and Exoplanet Database ✅

- **Who's there:** amateur photometrists with real telescopes, chaired by Dennis Conti. It publishes "A Practical Guide to Exoplanet Observing" (with an AstroImageJ tutorial), runs CHOICE courses, and holds quarterly online meetings coordinated by Google Group (join by emailing dennis@astrodennis.com). ([section page](https://www.aavso.org/exoplanet-section))
- **What it accepts:** transit observations of **known** planets into the AAVSO Exoplanet Database (AED). It also runs a TESS follow-up support program and an ephemeris-refresh target list (~68 planets, P < 3 d, V < 14, depth > 0.5%). Suggested kit: 8″+ aperture, mono CCD, at least one standard filter.
- **Newcomer use:** the best place to learn ground-based transit photometry properly. It doesn't vet archive-only candidates, and a 500 ppm TESS candidate is beyond small-telescope reach anyway.

### 2.5 NASA Exoplanet Watch (JPL) ✅

- **Who's there:** NASA citizen-science project, lead scientist Rob Zellem (JPL), with a volunteer Slack. ([overview](https://science.nasa.gov/citizen-science/exoplanet-watch/), [how to contribute](https://science.nasa.gov/citizen-science/exoplanet-watch/how-to-contribute/))
- **What it accepts:** transit light curves of known planets reduced with **EXOTIC** (runs in Google Colab), uploaded to the AAVSO database. "Observations included in scientific papers list the contributor as a co-author."
- **No telescope needed:** request free data from MicroObservatory, Las Cumbres and JPL telescopes through the data-checkout system. **This is the best first rung for a kit user with only a laptop.**

### 2.6 ExoClock (Ariel) ✅

- **Who's there:** the ARIEL Ephemerides Working Group, supporting ESA's Ariel mission, run by PULSAR in Thessaloniki. 800+ members. ([site](https://www.exoclock.space/), [contribute](https://www.exoclock.space/contribute))
- **What it accepts:** light curves of scheduled known planets. Register your telescope, follow your personal schedule, reduce with HOPS (recommended, not required), upload. A review team checks every upload, and an annual peer-reviewed paper ships with a data release.
- **Newcomer use:** structured, reviewed practice with publication outcomes. It is not a candidate venue.

### 2.7 TRESCA / ETD (Czech Astronomical Society) ✅

- **Who's there:** the Variable Star and Exoplanet Section of the Czech Astronomical Society. The old Exoplanet Transit Database (`var2.astro.cz/ETD`, which grew out of the TRESCA project) now redirects to **VarAstro**: "a portal for publication and sharing photometric observations of variable stars and exoplanetary transits." ([ETD page](https://var.astro.cz/en/Home/ETD), [section](https://sphe.astro.cz/en))
- **What it accepts:** transit photometry, uploaded to the **parent star** (WASP-43, not WASP-43 b) through [the upload form](https://var.astro.cz/en/Observations/New), then model-fitted in the portal. Free transit predictions are [here](https://var.astro.cz/en/Exoplanets/TransitsPredictions?init=1).
- **Note:** "TRESCA" as a separate live group did not turn up today. Treat it as the historical name behind ETD.

### 2.8 Unistellar / SETI Institute (UNITE) ✅

- **Who's there:** Unistellar smart-telescope owners and the SETI Institute (Tom Esposito, Lauren Sgro, Franck Marchis). UNITE is "Unistellar Network Investigating TESS Exoplanets", a NASA citizen-science project. ([UNITE](https://science.unistellar.com/exoplanets/unite/), [exoplanets](https://science.unistellar.com/exoplanets/))
- **What it accepts:** coordinated observations of TESS giant-planet targets with long or uncertain transits. Data from non-Unistellar telescopes can't be processed by the pipeline; for those, the page points people to Exoplanet Watch, TFOP and AAVSO.
- **Credit:** on the TOI-4465 b result, "All observers are co-authors on the scientific paper."
- **Newcomer use:** only if you own a Unistellar. Shows the good model: coordinated, credited, candidates called candidates.

### 2.9 TESS Science Support Center, GI and DDT ✅

- **TSSC (HEASARC):** helpdesk, tutorials, TESS-point (is my star observed?), data products. ([home](https://heasarc.gsfc.nasa.gov/docs/tess/), [helpdesk](https://heasarc.gsfc.nasa.gov/docs/tess/helpdesk.html), [tools](https://heasarc.gsfc.nasa.gov/docs/tess/data-analysis-tools.html))
- **GI program:** "Anyone is eligible to submit a TESS GI Program." Funding needs a US institution. The **Cycle 10** call is "expected to occur in Early 2027" (Sectors 122–134). Mini proposals are 2 pages, unfunded, dual-anonymous, with an Open Science and Data Management Plan. Proposals must use *new* TESS observations; archival-only work goes elsewhere. ([how to propose](https://heasarc.gsfc.nasa.gov/docs/tess/proposing-investigations.html))
- **DDT:** for targets "not covered in the GI target lists." Submit any time through the form at [tess.mit.edu/science/ddt](https://tess.mit.edu/science/ddt/), at least **6 weeks** before the target sector. Reviewed by the TESS PI, an expert and ops. No proprietary period. ([TSSC DDT page](https://heasarc.gsfc.nasa.gov/docs/tess/ddt.html)) Pavel's DDT 100 shows the route works for an unaffiliated person with a pre-registered prediction. **A DDT grant is observing time, not a verdict.** Say it that way.

### 2.10 Publication venues

| Venue | Accepts | Review | Newcomer notes | Verified |
|---|---|---|---|---|
| **RNAAS** (AAS) | "works in progress, comments and clarifications, null results, or timely reports of observations"; ≤1,500 words, one figure *or* table, abstract required | "not peer reviewed but moderated" (Lead Editor Chris Lintott, chris.lintott@aas.org); online "within days of acceptance" | The natural home for a single candidate, and the one ExoFOP's help page names. Fees not stated on the page. | ✅ [journals.aas.org/research-notes](https://journals.aas.org/research-notes/) |
| **arXiv astro-ph.EP** | Original, significant research | Moderated | **Endorsement required** for first-time submitters; an institutional email or claimed past papers can auto-endorse. **New rate limit from 2026-10-01:** two submissions per calendar month and three active at once, per submitter. Moderators name "thin," "salami" and "dense AI-written" papers as the problem. AI use is allowed if disclosed. | ✅ [endorsement](https://info.arxiv.org/help/endorsement.html), [rate-limit post](https://blog.arxiv.org/2026/10/01/updated-rate-limit-policy/) |
| **Zenodo** | Anything, with a DOI | None | Good for a dated, citable data and code snapshot (Pavel used it). A DOI is **not** publication and doesn't pass ExoFOP's gate. | ⚠️ blocked |
| **JOSS** | Research software papers | Open peer review | A route for the *kit/pipeline itself* (refute #18 plans JOSS first). It doesn't carry a candidate. | ⚠️ not fetched |
| AJ / MNRAS / A&A / PASP | Full papers | Refereed | The real bar for validation (FPP < 0.015 plus follow-up). Usually reached with professional co-authors. | – |

### 2.11 Astrobites and explainers ✅

- **Who's there:** grad-student writers summarising astro-ph daily for undergraduates. ([astrobites.org](https://astrobites.org/))
- **Accepts:** guest posts ([submit](https://astrobites.org/apply-to-write-for-astrobites/submit-a-guest-post/)), paper suggestions ([suggest](https://astrobites.org/about/suggest-a-paper-topic/)), undergrad research abstracts. A topic suggestion only works once there's a paper on arXiv.
- **Kit use:** the reading list. The [exoplanets tag](https://astrobites.org/tag/exoplanets/) explains vetting in plain words. A current example is the 2026-10-05 guest post "Your Planet Candidate Needs a Background Check", which is about Gaia astrometry, but its vetting logic (unresolved companions, imaging, second spectral lines) is the same problem TESS candidates have.

### 2.12 Where the viral crowd gathers

| Place | Who's there | Accepts | Etiquette / what gets you ignored | Verified |
|---|---|---|---|---|
| **Hacker News** | Builders and skeptics; the TIC 4206066 threads split "incredible" vs "noise fitting noise" | Links; **Show HN** only for "something you've made that other people can play with" | No blog-post Show HNs, no "quickly-generated one-offs; anybody can do that now", no unfinished work, no linkbait titles, never "solicit upvotes, comments, or submissions." A kit people can run qualifies; a candidate announcement doesn't. | ✅ [showhn](https://news.ycombinator.com/showhn.html), [guidelines](https://news.ycombinator.com/newsguidelines.html) |
| **r/ClaudeAI** | Claude users, where Pavel's post landed (~6.4K activity) | Show-and-tell | Expect "AI found a planet" framing in replies. Post the method, call it a candidate. | ⚠️ Reddit blocked |
| r/exoplanets, r/askastronomy | Enthusiasts, some pros | Questions, news | Ask for vetting help; don't announce. | ⚠️ |
| **X** | the TIC 4206066 thread, its amplifiers (@MTSlive, @andrewcurran_), memecoin launchers | Threads | The venue where "NASA approved" turns into "NASA confirmed" within a day. Nothing posted there counts as a record. | ⚠️ blocked |
| **eumemic/exoplanets** | One person (likely @dysmemic), ~36 candidates, no ExoFOP submission | – | Lots of candidates fast. Its own numbers say its injection recovery is about 60%. | ✅ (its README) |
| **Paras Chopra, "Vibe Astronomy"** | Substack readers | – | Good: "obviously tentative and unconfirmed", names the EB blend risk. Gap: plans a direct ExoFOP CTOI, which the 2026-08-19 gate blocks. | ✅ |
| **klucilla/refute** | A falsification framework, the closest in spirit to the windowsill lab | – | Its #18 lays out JOSS → methods paper → RNAAS per candidate → ExoFOP. It is the only crowd member that has read the new gate. Worth citing and possibly collaborating with. | ✅ |

---

## 3. Reputational traps, ranked

1. **Claiming before vetting.** "I found a planet" when the evidence is a candidate. Field vocabulary: *candidate*, *TOI/CTOI*, *validated* (statistical, FPP < 0.015 plus follow-up), *confirmed* (mass or independent evidence), *false positive*. Pavel's own FPP of 0.03–0.04 misses validation, and the headline still said "planet".
2. **Lowercase letters and names.** "b" only after refereed confirmation (ExoFOP help ⚠️). The IAU "acts as a single arbiter of the naming process", and commercial naming schemes "have no bearing on the official naming process" ✅ ([IAU 1301](https://iauarchive.eso.org/public_press/news/detail/iau1301/)).
3. **Memecoins and tokens.** At least 30 same-name tokens appeared within a day of the TIC 4206066 post. Anyone who goes public with a TIC number should expect one and should pre-empt it: put a plain "no coin, token, or sale is connected to this star" line on the page *before* posting (the windowsill TIC page does this). Never like, reply to or quote a token account; engagement reads as endorsement.
4. **"NASA approved" ≠ "NASA confirmed."** A DDT slot or an ExoFOP listing is observing attention, not a verdict.
5. **Skipping the known-object check.** Re-announcing a known TOI, a known EB or a Gaia binary is the fastest way to be ignored. Check the TOI list, ExoFOP, the NASA Exoplanet Archive and the Gaia RUWE before saying anything.
6. **Harvesting other people's work.** Planet Hunters Talk has a binding credit policy. TFOP expects authorship offers for unpublished data used.
7. **Flooding.** Dozens of thin candidates, or several AI-written arXiv papers, now run into arXiv's 2026-10-01 rate limit and moderators' "dense AI-written" flag. One well-vetted candidate beats 36.
8. **Publicity before the paper.** NASA Goddard wants 6 weeks' notice before arXiv for TESS press. Going viral first burns that route.

---

## 4. The recommended path for a kit user

[`JOURNEY.md`](JOURNEY.md) is the full walk-through; this is the community side of it.

1. **Learn (week 1):** Astrobites exoplanet tag; classify on Planet Hunters TESS; one Exoplanet Watch no-telescope light curve through EXOTIC.
2. **Search (kit pipeline):** commit a preregistration, run `python -m lab.planetkit run`, and read the verdict.
3. **Hold the language:** "candidate" everywhere, no letters, a no-token line on any public page.
4. **Ask first:** email exofop-support@ipac.caltech.edu with the candidate summary and ask whether an RNAAS clears the 2026-08-19 gate.
5. **Publish:** RNAAS (one candidate, ≤1,500 words, one figure); data and code snapshot with a DOI; arXiv only if you have endorsement and the work is substantial.
6. **Register:** Published Candidate Upload Request → CTOI on ExoFOP. Being there two months before any TESS-project posting earns an authorship invitation under the TFOP policy.
7. **Ask for photons:** a TESS DDT request ≥6 weeks before the next sector, if the star is due; otherwise the CTOI is the request to TFOP SG1–SG3.
8. **Then talk:** Show HN for the *kit*, or a write-up that links the RNAAS. Never a planet headline.

---

## 5. Not verified (check from a browser)

- ExoFOP `candidate_help.php` wording and the upload-request form (robots-blocked).
- Planet Hunters TESS Talk board structure (the Talk page returned only Zooniverse boilerplate).
- Reddit (r/ClaudeAI, r/exoplanets, r/askastronomy) and X: proxy- or robots-blocked.
- Zenodo and JOSS submission pages: blocked or not fetched.
- RNAAS fees: not stated on the AAS page; check at submission.
- Whether astro-ph endorsement is category-wide or per subject class (the arXiv page doesn't say).

## Sources fetched today (✅)

[TFOP overview](https://tess.mit.edu/followup/) · [Join TFOP](https://tess.mit.edu/followup/apply-join-tfop/) · [TFOP publication policy v21](https://tess.mit.edu/wp-content/uploads/TFOPWG_Publication_Policy_v21_20260712.pdf) · [TESS policies page](https://tess.mit.edu/followup/data-submission-policies/) · [ExoFOP-TESS at MIT](https://tess.mit.edu/followup/exofop-tess/) · [PHT research](https://www.zooniverse.org/projects/nora-dot-eisner/planet-hunters-tess/about/research) · [PHT blog 2019](https://blog.planethunters.org/2019/05/20/exciting-new-planet-candidates/) · [AAVSO exoplanet section](https://www.aavso.org/exoplanet-section) · [Exoplanet Watch](https://science.nasa.gov/citizen-science/exoplanet-watch/) · [Exoplanet Watch how-to](https://science.nasa.gov/citizen-science/exoplanet-watch/how-to-contribute/) · [ExoClock](https://www.exoclock.space/) · [ExoClock contribute](https://www.exoclock.space/contribute) · [VarAstro ETD](https://var.astro.cz/en/Home/ETD) · [Unistellar exoplanets](https://science.unistellar.com/exoplanets/) · [UNITE](https://science.unistellar.com/exoplanets/unite/) · [TSSC](https://heasarc.gsfc.nasa.gov/docs/tess/) · [TSSC DDT](https://heasarc.gsfc.nasa.gov/docs/tess/ddt.html) · [TSSC proposing](https://heasarc.gsfc.nasa.gov/docs/tess/proposing-investigations.html) · [RNAAS](https://journals.aas.org/research-notes/) · [arXiv endorsement](https://info.arxiv.org/help/endorsement.html) · [arXiv rate limit 2026-10-01](https://blog.arxiv.org/2026/10/01/updated-rate-limit-policy/) · [Astrobites](https://astrobites.org/) · [Show HN](https://news.ycombinator.com/showhn.html) · [HN guidelines](https://news.ycombinator.com/newsguidelines.html) · [IAU 1301](https://iauarchive.eso.org/public_press/news/detail/iau1301/) · [refute #18](https://github.com/klucilla/refute/issues/18) · [windowsill-lab #160](https://github.com/benskamps/windowsill-lab/pull/160) · [Vibe Astronomy](https://invertedpassion.substack.com/p/vibe-astronomy-discovering-exoplanets)
