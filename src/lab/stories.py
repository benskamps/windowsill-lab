"""The story layer — durable plain-language copy for each milestone.

MILESTONES.md is the technical source of truth (it drives status, titles, and the
technical ``result`` string). This module is its plain-language companion: the
human-readable *story* of each experiment, written for total non-experts and kept
beside the curriculum so the public page never has to infer plain copy from
technical prose at render time.

Each entry is keyed by milestone id and may carry:

- ``short_label``    — 2-4 plain words naming the experiment.
- ``question_plain`` — the experiment's question in everyday, jargon-free language.
- ``why_it_matters`` — one sentence on why a curious person should care.
- ``result_plain``   — a plain statement of the outcome, including a kept miss's
                       own numbers (or ``None`` for open/pending milestones,
                       which have no result yet).

Tracks currently carrying entries: M=magnetism, K=coherence, C=computation,
A=astronomy, I=instrument, B=donated compute.

``publish.parse_milestones`` merges these onto each milestone record (without
overwriting the technical ``result``), so they flow into ``pot.json`` and the page.

Governing voice: *romance in the questions, rigor in the claims.* Every
``result_plain`` here was reviewed against the MILESTONES.md result it summarizes —
including the lab's honest negative results (M09, M11), whose correct answer is
"no", stated proudly.

Stdlib-only (a plain dict) so ``publish`` stays import-light and unit-testable.
"""
from __future__ import annotations

# milestone id -> {short_label, question_plain, why_it_matters, result_plain}
STORIES: dict[str, dict[str, str | None]] = {
    # ── Phase 1 — verify the instrument ──────────────────────────────────────
    "M01": {
        "short_label": "Flat grid of magnets",
        "question_plain": "If you heat a sheet of tiny magnets, is there an exact temperature where they suddenly stop agreeing with each other?",
        "why_it_matters": "It is the simplest place in physics where a whole system flips from order to chaos at one sharp tipping point, and it tests whether the lab's instrument can find that point at all.",
        "result_plain": "Yes — the lab found the tipping point at a temperature of about 2.30, right on top of the exact textbook answer of 2.2692.",
    },
    "M02": {
        "short_label": "Bigger and bigger grids",
        "question_plain": "When you make the grid of magnets bigger and bigger, does the way it behaves near the tipping point follow one clean, predictable rule?",
        "why_it_matters": "If the same hidden pattern shows up at every size, it means the behavior at the tipping point is universal, not an accident of one particular grid.",
        "result_plain": "Yes — across grids from 32 up to 256 on a side, the sharpness of the change grew in lockstep with grid size as a clean power law, close to the exact textbook prediction.",
    },
    "M03": {
        "short_label": "How order fades",
        "question_plain": "As the magnets approach the tipping point, exactly how fast does their shared order melt away?",
        "why_it_matters": "The precise speed at which order disappears is a fingerprint shared by many different materials, so measuring it confirms the lab is reading the deep, universal physics.",
        "result_plain": "The lab measured that fading-rate fingerprint and landed right on the exact textbook value of one-eighth, with all the size curves folding neatly onto a single shared curve.",
    },
    "M04": {
        "short_label": "Heat near the tipping point",
        "question_plain": "Right at the tipping point, does the sheet of magnets suddenly drink up an enormous gulp of heat?",
        "why_it_matters": "Measuring the heat-hungry spike is a completely separate way to pinpoint the tipping temperature, so agreeing with the magnetism measurement proves the lab isn't fooling itself.",
        "result_plain": "Yes — the heat-hunger spiked at a temperature of about 2.275, matching the exact textbook tipping point of 2.2692 to within a fraction of a percent and confirming the answer the magnetism gave earlier.",
    },
    "M05": {
        "short_label": "Different-shaped grids",
        "question_plain": "If you rearrange the same tiny magnets onto a differently shaped grid, does the tipping point move to a new temperature but still follow the same deep rules?",
        "why_it_matters": "Showing that the shape of the grid changes the exact tipping temperature yet not the underlying behavior is a clean demonstration of one of physics' most beautiful ideas: that wildly different systems can obey the very same deep rules.",
        "result_plain": "Yes — twice over. On a triangular grid, where each magnet touches six others, the lab found the tipping point at about 3.675, close to its own exact answer of 3.641. On a honeycomb grid, where each magnet touches only three, it found about 1.532 against an exact 1.519. Both are far from the square grid's 2.269, and they line up in exactly the order you'd guess: the fewer neighbors holding a magnet in line, the less heat it takes to break the order. Three shapes, three different tipping points, same deep behavior underneath.",
    },
    # ── Phase 2 — map known territory ────────────────────────────────────────
    "M06": {
        "short_label": "3D Ising magnet",
        "question_plain": "If we stack the tiny magnets into a solid block instead of a flat sheet, does it still freeze into order, and at what temperature?",
        "why_it_matters": "Real magnets are three-dimensional, so this checks the lab against the world we actually live in, where adding a dimension changes everything.",
        "result_plain": "Yes — the block of tiny magnets locked into order right where the known answer says it should, near a temperature of about 4.5.",
    },
    "M07": {
        "short_label": "Potts colors",
        "question_plain": "If each tiny magnet can point in more than two directions, is there a tipping point where the way it freezes changes from gentle to sudden?",
        "why_it_matters": "It shows that a small change in the rules — how many choices each magnet has — can flip a smooth gradual change into an abrupt all-at-once one.",
        "result_plain": "Yes — with up to four choices the freezing came on gradually, but with five or more it snapped on all at once, and the lab pinpointed each transition temperature along the way.",
    },
    "M08": {
        "short_label": "XY whirlpools",
        "question_plain": "Can a flat sheet of magnets that can spin in any direction still have a special temperature, even when it never truly freezes into a single direction?",
        "why_it_matters": "It reveals a subtler kind of order, built from tiny whirlpools rather than everything pointing the same way, that won a Nobel Prize.",
        "result_plain": "Yes — even though the sheet never settles into one direction, the lab found the special temperature where its stiffness suddenly gives way, close to the known value of about 0.89.",
    },
    "M09": {
        "short_label": "No order in flatland",
        "question_plain": "If the tiny magnets can point anywhere in three-dimensional space but live on a flat sheet, can they ever all line up?",
        "why_it_matters": "The honest, surprising answer — no, never — is one of the deepest rules in physics, and confirming an absence is harder than finding a signal.",
        "result_plain": "No, and that is the correct answer: as the sheet was made larger the magnetism faded steadily toward nothing, exactly as the famous no-ordering rule predicts.",
    },
    "M10": {
        "short_label": "Anti-aligned magnet",
        "question_plain": "If we flip the rule so neighboring magnets want to point opposite ways instead of the same way, does the lab still handle it cleanly?",
        "why_it_matters": "Many real materials are built from opposites pulling against each other, so this proves the lab can handle that mirror-image world too.",
        "result_plain": "Yes — the alternating up-down pattern froze in at the same temperature its same-direction cousin does, confirming the lab handles the flipped rule correctly.",
    },
    # ── Phase 3 — push the edge ──────────────────────────────────────────────
    "M11": {
        "short_label": "2D spin glass",
        "question_plain": "If you tangle a magnet so its tiny parts pull in random, conflicting directions, can it ever freeze into a locked pattern at a real, above-zero temperature?",
        "why_it_matters": "It tells us whether messy, frustrated materials behave like ordinary magnets or live by stranger rules, and it shows the lab can honestly report a 'no' as proudly as a 'yes'.",
        "result_plain": "In flat, two-dimensional form it never truly freezes at any real temperature: the disorder keeps spreading wider and wider as the lab cools toward absolute zero, with no single moment of locking-in.",
    },
    "M12": {
        "short_label": "3D spin glass",
        "question_plain": "Give that same tangled, conflicting magnet a third dimension to live in — does the extra room finally let it freeze into a glassy, locked-up state at a real temperature?",
        "why_it_matters": "This is the famous case behind real glassy materials, and finding the freezing point would prove the lab can reach the genuinely hard problems, not just the textbook ones.",
        "result_plain": "Not yet — and both times the reason was found here, in the lab's own setup. The first attempt was too small to see anything. The second looked like a real answer until an audit turned up two faults: the simulation runs copies of the material at a ladder of temperatures and trades neighbours between rungs, and one whole set of those pairs was never tried even once, so the ladder broke into isolated couples instead of one connected chain; and the textbook number it was being graded against had been measured for a different kind of randomness than the one being simulated. Both faults are fixed in the code; the experiment is owed a rerun. Until then this stays grey.",
    },
    "M13": {
        "short_label": "Frustrated triangles",
        "question_plain": "When you arrange tiny magnets on triangles so they can never all satisfy each other, the material has many equally-good resting states — how much built-in disorder does that leave behind?",
        "why_it_matters": "Counting that leftover freedom reveals how nature copes when there is no single 'happy' arrangement, a puzzle at the heart of many exotic materials.",
        "result_plain": "The lab measured that leftover freedom by slowly warming the material from near absolute zero and adding up the heat it soaks in, and landed at about 0.334 — right on top of the exact textbook value of 0.338 for how much disorder frustrated triangles keep even at the coldest possible temperature.",
    },
    "M14": {
        "short_label": "Mixed-bond magnet",
        "question_plain": "If you sprinkle a magnet with a chosen fraction of contrary bonds that want their neighbours to disagree, is there a special recipe where order and disorder meet at a single magic point?",
        "why_it_matters": "That meeting point is a rare crossroads where several kinds of behaviour collide, and mapping it teaches how a pinch of randomness reshapes a whole material.",
        "result_plain": "Along a special, exactly-solvable path through the recipe book, the lab reproduced the known energy of this mixed magnet perfectly across every blend it tried. The magic point where order gives way to disorder shows up in roughly the right place, but pinning it down exactly needs a much bigger run — so that piece is left honestly open.",
    },
    # ── Phase 4 — genuinely open ─────────────────────────────────────────────
    "M15": {
        "short_label": "Domains growing",
        "question_plain": "Cool a hot, scrambled magnet in an instant and watch patches of agreement start to spread — how fast do those patches grow as time ticks on?",
        "why_it_matters": "The same coarsening rhythm governs everything from cooling alloys to separating oil and water, so measuring its pace connects a toy magnet to the everyday physics of things settling down.",
        "result_plain": "The patches grew with a measured power of 0.47 to 0.49, against the predicted one-half. The spread is the real uncertainty: the growth law is approached from below, so a young pattern reads slightly low, and the number drifts up to 0.494 late in the run. Measured across 48 separate quenches on a 512-wide grid.",
    },
    "M16": {
        "short_label": "Aging memory",
        "question_plain": "After a tangled magnet is suddenly chilled, does it keep changing in a way that depends on how long ago it was chilled — in other words, does it carry a memory of its own age?",
        "why_it_matters": "This 'getting older' behaviour is how real glasses and disordered solids quietly evolve for years, and catching it would show the lab can study things that never fully settle.",
        "result_plain": "The older the magnet, the more strongly it held onto its past. Compared at a fixed delay, correlation with its own history rose from 0.714 to 0.818 as the magnet aged. Its four separate histories line up when time is measured relative to age rather than absolutely — scattering only a quarter as much that way. Time has stopped meaning the same thing to it at every moment, which is what aging is.",
    },
    "M17": {
        "short_label": "Roughening surface",
        "question_plain": "When a surface grows by piling up randomly — like a coffee stain creeping outward or a flame front advancing — do its bumps and wrinkles follow a hidden universal law?",
        "why_it_matters": "A startling range of growing, spreading things share one mathematical fingerprint, and reproducing it would tie the windowsill lab to one of the deepest patterns in non-equilibrium physics.",
        "result_plain": "Yes — the surface roughened as time to the power 0.313 against the predicted 1/3, and to make sure that wasn't the ruler's doing, the same ruler measured two simpler growth rules and each landed on its own different known answer (0.235 vs exact 1/4; 0.500 vs exact 1/2, tracked to 0.6%). Even the lopsidedness of the wrinkles leaned the way the deep theory says it should, for both shapes of growth.",
    },
    "M18": {
        "short_label": "Spreading or dying",
        "question_plain": "If an activity can either spread to its neighbours or fizzle out for good, is there a knife's-edge setting where it just barely survives forever?",
        "why_it_matters": "This simplest model of epidemics, forest fires, and chain reactions captures the universal tipping point between extinction and survival, a pattern that shows up far beyond physics.",
        "result_plain": "Yes, within the resolution this machine can support. The lab ran just below and just above the knife edge, then kept the answer as the range between them instead of tuning one run until it looked exact. That range contains the published value for this kind of spreading process and rules out the simpler large-system approximation. A second full run on a different GPU landed on the same conclusion. Three controls ran alongside: activity far below the edge died in a clearly different way, activity far above it levelled off, and a completely empty grid never switched itself back on. This is a bounded consistency check, not a precision measurement or proof that every feature of the model belongs to the same family.",
    },
    # ── Track K — coherence: when do independent rhythms agree? ──────────────
    "K01": {
        "short_label": "Clocks finding a beat",
        "question_plain": "If you fill a room with clocks that all tick at slightly different speeds, and let each one nudge the others, how hard do they have to pull before they suddenly all tick together?",
        "why_it_matters": "The same tipping point governs fireflies flashing in unison, heart cells beating as one, and power grids staying in step — and there is an exact answer to check the lab against.",
        "result_plain": "The clocks snapped into step at a nudging strength of 1.0007, against the exact answer of 1. The harder test: above that point, theory predicts the whole curve of how much they agree, and the lab reproduced seven points on it to within two ten-thousandths with nothing fitted. With no nudging at all the clocks read 0.0203 together, which is just the accidental agreement of 2000 random things, so the effect is not an artefact of the setup.",
    },
    # The earlier entry here asked about the *cost* of coordination — a different
    # question from the one MILESTONES.md K02 actually poses, which is whether a
    # fitted shape law survives a change in crowd size. Rewritten to match.
    "K02": {
        "short_label": "Twitchiest in between",
        "question_plain": "A room of clocks is at its twitchiest somewhere between total disagreement and perfect lockstep — but is the exact spot where that happens a real law, or just a side effect of how many clocks were in the room?",
        "why_it_matters": "An earlier experiment in this lab fitted a tidy formula putting that sweet spot at 40% agreement; if the number is really just counting the crowd, then anyone building on the formula would be quietly wrong at every other size. Checking it also gives the lab a chance to measure a number physicists already published — the honest way to find out whether a windowsill instrument can be trusted.",
        "result_plain": "The twitchiest point does sit somewhere in the middle, at every crowd size from 250 clocks up to 4000. But it is not at 40% agreement, and it slides lower as the crowd grows — so this lab's earlier 40% was measuring the size of the room, not a law, and that claim is withdrawn. Measuring the slide directly: agreement falls as the crowd size to the power 0.401, give or take 0.017, against the 0.39 published for this exact setup in 2015. The two agree well within their error bars.",
    },
    "K03": {
        # Retargeted 2026-08-02 (MILESTONES.md K03) from the scheduled-coverage
        # / ALOHA question, which is unscheduled rather than abandoned. This
        # story rode the retired target until 2026-08-11 — and it is the copy on
        # the "on the bench" button, the most forward-looking thing a stranger
        # reads, so a stale entry here advertises an experiment the lab decided
        # not to run.
        "short_label": "Two answers, one question",
        "question_plain": "Right at the edge where a crowd of clocks falls into step, does the crowd react just as sharply coming from below the edge as from above — or is the edge lopsided?",
        "why_it_matters": "Two sets of physicists have published opposite answers to this about the exact system this lab already runs, and nobody has settled it. It is the first question on the page where the lab is not checking a known answer but trying to break a tie.",
        "result_plain": None,
    },
    # ── Track C — compute & number theory ────────────────────────────────────
    "C01": {
        "short_label": "Trust the arithmetic",
        "question_plain": "Before we hunt for new numbers, can we prove our machine even does math we can trust?",
        "why_it_matters": "Every later number-hunting result is worthless unless the basic arithmetic is provably correct first.",
        "result_plain": "A check of the arithmetic itself, not a finding. The machine rebuilt the first 40 Fibonacci numbers and matched the official catalogue byte for byte, then re-ran a known primality test on 2 to the 31st minus 1 and got the expected remainder of zero. This exists so the number-handling can be trusted before it is pointed at anything unknown.",
    },
    "C02": {
        "short_label": "Hunt a giant prime",
        "question_plain": "Can one home computer take a turn at the worldwide search for enormous prime numbers?",
        "why_it_matters": "It puts a windowsill machine into a real global hunt where home volunteers have actually discovered record-breaking primes.",
        "result_plain": None,
    },
    "C03": {
        "short_label": "Grow a number list",
        "question_plain": "Can we add new, checked terms to a famous catalog of number sequences and have them officially accepted?",
        "why_it_matters": "It turns idle computing time into a permanent, credited addition to a reference mathematicians actually use.",
        "result_plain": None,
    },
    "C04": {
        "short_label": "Join the prime grid",
        "question_plain": "Can our machine pull a fair share of work in a shared, worldwide search for special primes?",
        "why_it_matters": "It contributes verified work to open mathematical problems that no single computer could finish alone.",
        "result_plain": None,
    },
    "C05": {
        "short_label": "Teleport into π",
        "question_plain": "Can we read a digit from deep inside π without computing any of the digits before it — and prove the trick against an old-fashioned full expansion?",
        "why_it_matters": "Two completely different centuries of mathematics — a 1706 arctan formula and a 1997 digit-extraction identity — must agree byte for byte, or our arithmetic cannot be trusted anywhere else.",
        "result_plain": None,
    },
    # ── Track A — astronomy from open archives ───────────────────────────────
    "A01": {
        "short_label": "Weigh starlight",
        "question_plain": "From free telescope data, can we catch a known planet dimming its star and measure its year correctly?",
        "why_it_matters": "It proves our analysis of real survey data lands inside the numbers professional astronomers already published.",
        "result_plain": "From eight public telescope visits spanning seven years, the lab timed 177 crossings and measured the planet's year at 0.94145236 days, against the published 0.94145223. That is a difference of about 11 milliseconds. The star dims by 1.022% as the planet passes, against a published 1.041%. Both sit inside the published error bars. The catalogue value was never used in the fit.",
    },
    "A02": {
        "short_label": "Track a pulsing star",
        "question_plain": "Can we follow a star that brightens and dims, time its rhythm, and add a real observation to the amateur record?",
        "why_it_matters": "It earns a place in the standard amateur variable-star database that researchers draw on for long-term star behavior.",
        "result_plain": None,
    },
    "A03": {
        "short_label": "Reweigh a neutron-star collision",
        "question_plain": "From open gravitational-wave data, can we re-measure the mass of a collision that shook spacetime and match the official answer?",
        "why_it_matters": "It shows a home machine can independently re-derive a landmark physics result from the same public data the discoverers used.",
        "result_plain": "No. And the interesting part is how carefully it failed. The lab first fed its own pipeline a fake collision planted in the real detector data, and the pipeline found it and weighed it about twenty-four times more precisely than the published error bar — so the control passed. Pointed at the real 2017 neutron-star collision, it found nothing strong enough to call a detection, and said so rather than fitting the answer it already knew. On the way past it did find something real it was not looking for: a known instrumental glitch in the Livingston detector at 209 sigma, 1.06 seconds before the collision. Reproducing the published mass needs better wave physics, not more computer time.",
    },
    "A04": {
        "short_label": "Search for a planet",
        "question_plain": "Can a blind search of a small, predeclared sample from one telescope survey recover real planets without being told where to look?",
        "why_it_matters": "It tests whether the search and vetting can find real signals without leaking the catalogue answer into the hunt — the calibration needed before any genuinely new candidate could be trusted.",
        "result_plain": "Yes — three times, with the labels taken away. The earlier planet-weighing run was told where to look; this one searched 26 stars with no planet names or periods. The two planets it was graded on came back first and second in its own ranking. It also flagged a third star nobody had asked about, put it through the same checks, and only afterwards identified it as another already-known planet. During the debugging runs it rejected deep, convincing signals that were alternating eclipses or artifacts at the edge of the search range. The cutoff was measured rather than chosen: fake transits at three depths all cleared it, while twenty-two quieter stars stayed below it. The claim is narrow: a blind sample recovered known planets and measured its own noise floor. It is not a discovery, a survey of the whole sector, or a submission for follow-up.",
    },
    "A07": {
        "short_label": "Jupiter's clockwork",
        "question_plain": "If you watch Jupiter's four big moons for four months, do they keep the exact mathematical rhythm Kepler and Laplace wrote down centuries ago?",
        "why_it_matters": "Three of the moons are locked in a gravitational waltz so precise it has held for billions of years — recovering it from public ephemerides proves this lab can measure celestial clockwork end to end.",
        "result_plain": "Yes — all four moons land on Kepler's line, Jupiter's mass falls out of the fit, and Io, Europa and Ganymede keep the Laplace rhythm while Callisto, the outsider, proves the rhythm is real by breaking it.",
    },
    "A05": {
        "short_label": "Pricing false alarms",
        "question_plain": "When the planet-hunt flags a dip in a star's light, can the lab measure — for that exact star — how often pure chance would fake a dip just as convincing, and how small a dip that star could even show?",
        "why_it_matters": "A hunt that cannot price its own false alarms will eventually announce noise. In one day of pilot runs a signal held 'planet candidate' for forty minutes before being unmasked as a pulsing star, and another matched a catalog entry the community had already refuted — so every flagged signal needs its own measured odds, and the machine's strongest verdict stays 'a lead awaiting human review', never 'a planet'.",
        "result_plain": "The hunt is running and its totals move every few hours, so the live counts sit on the windowsill page rather than in this sentence. The shape of the result is steady: most dips that clear the threshold get explained away by the machine's own checks — eclipsing pairs, pulsing stars, aliases of a known rhythm, and a handful of already-known planets recovered along the way. A few are not explained away, and those are held as leads awaiting human review: priced, but not judged. No person has looked at them yet, and until someone does the lab will not call them planets, candidates, or anything stronger than a lead.",
    },
    "A06": {
        "short_label": "A fresher sky",
        "question_plain": "With the statistics proven, can the same search run on a newer patch of sky — one the community has had less time to comb — with every test for killing a false signal committed in advance?",
        "why_it_matters": "Declaring the refutation tests before touching the data is what keeps an exciting blip from bending the rules that judge it.",
        "result_plain": None,
    },
    # ── Track I — the machine as instrument ──────────────────────────────────
    "I01": {
        "short_label": "Camera as detector",
        "question_plain": "Can an ordinary computer camera, with its lens capped in the dark, actually feel particles passing through it?",
        "why_it_matters": "It turns a piece of everyday hardware into a real physics instrument, the first step to detecting things you cannot see.",
        "result_plain": "No real camera frames were available on this machine today, so the lab recorded a grey hardware boundary and made no particle claim. The real-frame analyzer is ready for a capped sensor instead of pretending test data came from the sky.",
    },
    "I02": {
        "short_label": "Counting cosmic rays",
        "question_plain": "If the camera watches in the dark for a whole month, can it count the tiny sparks left by particles raining down from space?",
        "why_it_matters": "It lets a single machine on a windowsill measure the steady drizzle of cosmic rays that passes through all of us every minute.",
        "result_plain": None,
    },
    "I03": {
        "short_label": "Randomness beacon",
        "question_plain": "Can the machine bottle pure, unpredictable randomness from its own hardware and publish it as a trustworthy, time-stamped feed?",
        "why_it_matters": "Genuinely unguessable numbers are the bedrock of secure communication, and a published feed lets anyone use and check them.",
        "result_plain": None,
    },
    # ── Track B — donate cycles (BOINC) ──────────────────────────────────────
    "B01": {
        "short_label": "Hunting gravity waves",
        "question_plain": "Can this machine donate its spare hours to a worldwide hunt for the faint hum of spinning dead stars?",
        "why_it_matters": "Pooling idle home computers is how volunteers help search for ripples in spacetime that no single lab could find alone.",
        "result_plain": None,
    },
    "B02": {
        "short_label": "Folding proteins",
        "question_plain": "Can the machine give its idle time to help work out the shapes of proteins that drive disease and medicine?",
        "why_it_matters": "Volunteer computing on problems like protein folding has fed real research a single household machine could never tackle by itself.",
        "result_plain": None,
    },
}
