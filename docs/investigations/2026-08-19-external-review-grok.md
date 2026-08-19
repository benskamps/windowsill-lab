# External review: Grok on the Windowsill Lab (2026-08-19)

**Source:** an unsolicited outside read by Grok (xAI), prompted by Ben from the
public surface only — `brokenbranch.dev/windowsill/experiments/` plus web search
(the model reported ~30 and ~47 pages of browsing across the two passes). It did
**not** read this repo, the receipts, `checks.py`, `BACKLOG.md`, or the assay
protocol. That matters twice over: it is a clean read of what a stranger can see,
and it is uninformed about everything we already decided.

Digest written by Claude. Sections: what it praised · what it criticised (graded
against what the project already knows) · what is genuinely new · the peer list ·
the artifact it produced.

---

## 1. What it praised — the public surface is landing

The read confirmed the ethos reaches a stranger without explanation:

- *"If it doesn't reproduce a known answer, it's a failed calibration, not a
  discovery"* — quoted back at us unprompted. The misses-stay-visible rule is
  legible from outside.
- Calibration-first sequencing (instrument earns trust before it explores) read
  as **"the correct scientific posture,"** and as the reason to believe the
  non-equilibrium wing at all.
- The hard claim ceiling — pipeline forbidden from ever emitting "planet,"
  highest state `lead — awaiting human review` — read as *"most pipelines
  overclaim; this one underclaims by design."*
- Home hardware framed as an **advantage**, not an apology: patient continuous
  runtime instead of contested cluster queues.

Nothing to action. Recorded because it is evidence the front door works — the
explainer / near-planets register did its job on a reader with no context.

---

## 2. What it criticised — graded

Grok volunteered six criticisms when pushed ("Can't all be positive right?").
Grading each against what this repo already declares:

| # | Critique | Grade |
|---|---|---|
| 1 | **Scale is small.** L=12 3-D glass, 64 disorder realizations, single-sector TESS subsets; FAP control unproven at survey scale. | **Known.** `BACKLOG.md` already concedes the exponent-precision race to Janus-class hardware and routes spin-glass work to *niche observables only*. The one part **not** answered: FAP control at scale — the noise floor rising with sample size is measured, but survey-scale behaviour is untested. |
| 2 | **Novelty is promised, not delivered.** Everything so far is re-derivation (Onsager, exponents, published periods, recovered planets). | **Known, and already the north star.** The frontier gate declared 2026-08-02 says exactly this, and names the wall more precisely than Grok does: the blocker is *certifying* novelty (physics has no OEIS), not producing a number. |
| 3 | **Extreme conservatism is a way of never shipping.** Nothing submitted to ExoFOP or the literature; permanent "awaiting human review" produces demonstrations and receipts, not usable claims. | **LIVE — the sharpest hit.** As of 2026-08-18 the ledger carries 6 leads pending a ruling, one refuted (TIC 287328866, P/2 alias), and **three vetting gates designed but not built**. The critique names the exact state we are in. See §3.1. |
| 4 | **Agent-written instrument = opacity.** Kernels, verification, provenance and UI are generated; subtle systematics could survive longer than in hand-audited code. Reproducibility of the *results* is high; reproducibility of the *code's correctness* is a different question. | **Partly answered, usefully reframed.** `checks.py`, negative controls and placebo runs test the *results*. Nothing tests the *auditor* — the verification code is agent-written too. Real gap; keep the framing. |
| 5 | **The human gate is the bottleneck.** One person deciding what earns a leaf rate-limits the lab; if the human slows, leaves stop while machines run. | **True and currently binding** — the 6-lead backlog is the proof. Constructive fix in §3.2. |
| 6 | **The charm can obscure the science.** Plant/windowsill metaphor and live demos are delightful but bury the methodological decision tree; results transparency ≫ methods transparency. | **Testable, partly stale.** The explainer register and the near-planets page came after the pages Grok read. Worth a targeted check: can a stranger get from a leaf to *why that number is trusted* in two clicks? |

Net: **four of six are already on the record here.** Two land — #3 (not shipping)
and #4 (nobody audits the auditor). #5 is the mechanism behind #3.

---

## 3. What is genuinely new

### 3.1 Shipping is now the binding constraint, not rigor

The project has spent a year building the right to make a claim and has not yet
made one. Grok's phrasing — *"That choice protects reputation, but it also limits
impact"* — is the honest version. The three designed-not-built vetting gates and
the 6 pending leads are the whole critique in one queue.

**Move:** decide, in advance and in writing, what a lead must clear to leave the
shelf, and where it goes when it does (ExoFOP is the named destination for the
sky track). Then let the gates run without a per-lead human turn. This is not
loosening the standard — it is writing the standard down, so that the standard
rather than Ben's calendar is what gates.

### 3.2 Frontier contracts (deployment)

Instead of the human reviewing every leaf: pre-declare a small set of contracts —
a specific open question, a success criterion, and a decisive-failure criterion —
then let the machines run until one or the other is met. The human's judgment
moves upstream (into writing the contract) instead of sitting in the loop.

Same shape as the estate's night-shift contract ("a clock, not a scope"), applied
to science instead of engineering. Converts critique #5 from a bottleneck into a
design.

### 3.3 Information per wall-clock hour, not FLOPs

Named levers under the no-new-hardware constraint: **population annealing,
parallel-tempering variants, Wang–Landau / flat-histogram sampling**, adaptive
schedules, variance reduction.

This is the Wolff move one rung up. Wolff landed 2026-06-16 for exactly this
reason — single-spin Metropolis burns wall-clock on critical slowing down. The
same argument says the *next* unlock is a better sampler, not a bigger lattice.
Ranks above "re-run M02 at L = 512" in expected information per GPU-hour.

### 3.4 Decisive nulls as shippable output

*"A clean, fully documented negative result that closes a question is often
faster and more valuable than an incremental positive."* Convergent with an item
already in `BACKLOG.md`: the **γ / γ′ disagreement** (Daido's asymmetric
γ = 1/4 above, γ′ = 1 below vs Hong et al. 2015's γ ≃ γ′ ≃ 1/4 with hyperscaling
obeyed) sits in K02's exact regime and is a one-line fit on χ data K02 already
collects. An outside reader independently landed on the category this item
belongs to. **Promote it.**

### 3.5 The greenfield claim — non-equilibrium toolkit → stellar light curves

Grok's "biggest impact possibility": treat stellar variability and post-detrend
residuals as a **non-equilibrium process** — aging / rejuvenation protocols,
multi-time correlation functions, KPZ-style roughness exponents, absorbing-state
(directed-percolation) diagnostics, mutual-information memory measures, rare-event
statistics — instead of the field's default stationary GPs, Fourier and AR models.
The pitch: uniquely exploits *both* wings living under one roof, needs no new
hardware, and a diagnostic that separates transits from activity more cleanly
would be adopted by surveys far larger than this one (PLATO, Roman).

**Caveat, and it is the important part:** "essentially open" is Grok's assertion,
not a verified result. Adjacent prior art almost certainly exists — DFA / Hurst
exponents, multifractal analysis and structure functions are established in
time-domain astronomy. The claim is therefore a **candidate for the
novelty-certification protocol** (BACKLOG goal #3), not a free lunch. Which makes
it a good first customer: a real cross-domain idea whose novelty is genuinely
unknown — exactly the thing the protocol exists to grade.

---

## 4. Peers — the first outside scan

No document in this repo names peers. Grok's list, **unverified — treat as leads,
not citations**:

- **Statistical physics / non-eq:** Janus Collaboration (the heavyweight for
  long-timescale spin-glass dynamics — real, and already the named benchmark in
  `BACKLOG.md`); plus `peapods` (Rust MC for Ising / spin glass), QISG (GPU
  quantum Ising spin glass), BatchTNMC (GPU tensor-network MC for 2-D spin
  glasses).
- **Agentic scientific discovery (2025–26):** PhyNex, SciExplorer, AgenticSciML,
  QUASAR. Closer in spirit; typically higher autonomy, bigger compute, no patient
  human-gated home instrument.
- **Open TESS re-analysis:** LEO-Vetter, COUNTESS, `eleanor` derivatives, various
  Zenodo-released complete analysis packages.

Grok's verdict: peers exist on each **individual** axis; nobody occupies the
intersection (permanent small hardware + AI-maintained instrument + dual tracks +
visible nulls + live public provenance). *"The closest peers are still working in
parallel rather than head-to-head."*

**Action:** verify the four unfamiliar names before any of them appears in public
copy. Janus, `eleanor` and LEO-Vetter are safe anchors; the rest are not yet.

---

## 5. The artifact — a rewritten post

Grok's own final rewrite after the critical pass, kept verbatim as a copy
reference (it moved from a celebratory frame to a "chapter one" frame on its own):

> **Windowsill Lab keeps receipts.**
>
> Two home machines. AI agents write and maintain the instrument. A human decides
> what earns a leaf. Misses stay on the shelf next to the wins.
>
> **Non-equilibrium wing (live in browser)** — A spin glass that ages and
> remembers. Surfaces that roughen with the KPZ exponent. Activity balanced on
> the edge between spreading and dying. Systems that refuse equilibrium. Clean
> numbers, published controls, finite lattices, finite times — all visible.
>
> **Sky track** — Public TESS light curves only. Folding recovers known periods
> to milliseconds. Blind search finds the planted planets and one more. Every
> candidate now carries its own false-alarm probability from its own noise. The
> pipeline is forbidden from ever saying "planet." Highest state: lead awaiting
> human review.
>
> This is still mostly careful calibration and recovery of known ground. The
> novel measurement remains ahead. What is already here is the scaffolding:
> patient hardware, agent-maintained code, radical honesty about nulls, and an
> instrument that has to prove itself before it is allowed to claim anything.
>
> A measurement nobody has made yet, given away free — when it arrives.
>
> https://www.brokenbranch.dev/windowsill/experiments/

Fact-check before posting: "blind search finds the planted planets and one more"
(A04 — accurate, the extra was WASP-20 b) and "recovers known periods to
milliseconds" (A01 — ~11 ms). Both hold as of 2026-08-19.

---

## 6. Carried into the backlog

- Promote the **γ / γ′ disagreement** item (§3.4) — closing a contested claim is
  a shippable frontier result, independently identified from outside.
- New item: **non-equilibrium diagnostics on stellar residuals** (§3.5), routed
  through the novelty-certification protocol rather than assumed novel.
- New item: **audit the auditor** (§2 #4) — `checks.py` grades results; nothing
  grades `checks.py`.
- New item: **better sampler before bigger lattice** (§3.3).
- Open question for Ben, not a backlog item: **the shelf-exit rule** (§3.1).
