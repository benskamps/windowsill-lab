# Assay — pinning U-K02's prior art, and correcting the public record

**Why this exists:** U-K02 is the catalogue's flagship `field` unknown and it is
public. It named two papers, said they contradict each other, and priced 3.1
GPU-hours against that contradiction. On 2026-09-03 six agents went to the
primary texts. One of the two papers does not contain the claim attributed to
it; the contradiction is one cell wide rather than wholesale; and the engine's
frequency distribution is neither paper's. **No number was measured and none is
claimed here.** This is a citation audit, and the citations were the defect.

**Assayer:** Claude (Opus), six parallel primary-source passes, cross-checked
against each other. **Date:** 2026-09-03. **Protocol:** `docs/assays/PROTOCOL.md`.
**Receipts:** `evidence/literature/` — one record per source, with the verbatim
sentence, its address inside the paper, the URL reached, and a SHA-256 over the
committed bytes. **Wall:** literature only; no simulation, no GPU.

---

## The short version

| Sub-claim, as U-K02 carried it | Verdict |
|---|---|
| "Daido, Prog. Theor. Phys. 75, 1460 (1986)" is a source for γ = 1/4, γ′ = 1 | **WRONG** — the pair is not in that paper |
| "Two published results directly contradict each other" | **OVERSTATED** — one cell is contested, not a literature |
| Daido's and Hong's γ, γ′ are exponents on χ = N·Var_t(r) | **CONFIRMED** at primary text, three independent chains |
| K03's ∂⟨r⟩/∂h can adjudicate that pair | **REFUTED** — different observable, different published value |
| "This engine's frequency set is that class term for term" | **NARROWED** — true of Daido's construction, not of Hong's |
| A regular-class γ_sus = 1 is established | **NOT ESTABLISHED** — asserted once, in the wrong section, with no derivation |

Nothing here settles U-K02. The entry stays open, its reach verdict is
untouched, and **only Ben retires an unknown or declares a literature question
settled.** What changed is that the entry now says true things.

---

## 1. Why this fires

PROTOCOL §7 says the searches are part of the receipt: *"'Hong et al. 2015' is
not a citation; 'Hong et al. 2015, Eq. (4.2)–(4.3), Fig. 6' is."* U-K02 met the
letter of that and failed its purpose. It carried journal, volume and page for
both sides — and one of those addresses points at a paper that says the
opposite of what it was cited for. A citation that is precise and wrong is worse
than a vague one, because precision is what stops a reader from checking.

PROTOCOL §3 says an exponent comparison is meaningless until the configuration
class is matched, and lists *the disorder distribution* as part of the class.
The 2026-08-02 assay matched the sampling **rule** term for term and did not
match the **distribution**. That gap is §4 below.

## 2. What was actually read

Eight sources, recorded individually in `evidence/literature/`. The `reached`
field on each says how far the reading went, and only `primary-full-text`
licenses citing an equation number.

| Source | Reached |
|---|---|
| Daido, *Prog. Theor. Phys.* **75**, 1460 (1986) | full text, four-page scan, page by page |
| Daido, *Prog. Theor. Phys.* **81**, 727 (1989) | full text, five-page scan, page by page |
| Daido, *J. Stat. Phys.* **60**, 753 (1990) | **abstract only** — Springer paywall |
| Hong, Chaté, Tang & Park, *PRE* **92**, 022122 (2015) | full text, arXiv PDF and ar5iv, agreeing throughout |
| Tang, *J. Stat. Mech.* (2011) P01034 | full text |
| Yoon, Sorbaro Sindaci, Goltsev & Mendes, *PRE* **91**, 032814 (2015) | full text |
| Park & Park, *PRE* **110**, 034216 (2024) | full text |
| Daido, *PRE* **91**, 012925 (2015) | **abstract only** — APS returns 403 |

## 3. The estimator audit — which susceptibility is χ

**PROTOCOL §4: is our number measuring what their number measures? No, and the
paper says so itself.**

Hong et al. define χ exactly once, in §III B Eq. (3.6):

> χ(K,N) ≡ N[⟨(Δ − ⟨Δ⟩)²⟩] = N[⟨Δ²⟩ − ⟨Δ⟩²]
>
> where ⟨·⟩ denotes time average in the steady state of a given sample and [·]
> sample average, respectively.

There is no pinning field anywhere in that paper, and §IV reuses this χ without
redefining it, so the regular-class γ and γ′ are fluctuation exponents. Daido's
is the same family: his 1989 letter defines σ = lim √N⟨|Z − ⟨Z⟩|²⟩^(1/2) under a
long time average and is titled *"Intrinsic Fluctuation and Its Critical
Scaling"*; Hong et al.'s endnote [15] records his variant as
N[⟨|Z|²⟩ − |⟨Z⟩|²]; Tang (2011), writing independently, quotes it as
χ ≡ N(Δ² − Δ̄²) with *"the overline bar denotes time average"*. Three chains,
two of them read directly this round.

The field response is a **different object with a different symbol and a
different value**, and Hong et al. draw the line themselves, one paragraph after
their random-class conclusion:

> One should note that the dynamic fluctuations of the order parameter are not
> necessarily proportional to the susceptibility (response of the order parameter
> to an infinitesimal external field) in general nonequilibrium steady states due
> to probable violation of the fluctuation-dissipation theorem. It is almost
> trivial to derive the susceptibility exponents in the Kuramoto model, which
> turn out to be γ_sus = γ′_sus = 1 [16]. Yet this accordance with the dynamic
> fluctuation exponents in Eq. (3.15) may be merely coincidental.

So FDT is not assumed to hold, and the two exponents are not assumed to agree.
`src/lab/k03.py` measures ∂⟨r⟩/∂h. **A field-response measurement cannot confirm
or refute either side of the 1/4-versus-1 dispute, in either direction.** That
is not a precision problem and no amount of GPU time fixes it.

The corroboration that closes the "maybe they coincide anyway" escape is
structural: the fluctuation χ is sampling-class dependent — switch i.i.d. draws
to quantile sampling of the same g(ω) and Hong et al.'s value moves from 1 to
1/4 — while the response χ cannot move under that switch, because off-critically
it is a thermodynamic-limit functional of g alone. That is why Yoon et al.
(exact, complete graph), Terada & Yamaguchi (linear-response theory, any
coupling function), and Sakaguchi (1988) all get 1 with no sampling class
attached — those three were screened rather than pinned, so they corroborate
rather than carry. Two observables that respond differently to the same knob
are not one observable up to constants.

## 4. The configuration class — and the distribution nobody matched

**PROTOCOL §3, the gate the protocol turns on.** The 2026-08-02 assay matched
the *sampling rule*: `lorentzian_frequencies()` draws at the midpoint quantiles
`(i+½)/N`, which is Hong et al.'s Eq. (4.1) rule and Daido's 1986 construction

> Δ_j = γ × tan{(jπ/N) − (N+1)π/2N}

term for term. That much holds. But the class has a second axis and it was never
matched:

* **`kuramoto.py` is Lorentzian.** So is Daido — half-width γ = 10⁻³, verified in
  his own 1986 and 1989 text. Our engine sits on **Daido's** distribution.
* **Hong et al.'s regular-class exponents are Gaussian.** Every γ, γ′, β and ν̄
  in their §IV is measured on g(ω) = (1/√2π)e^(−ω²/2). Their *entire*
  regular-Lorentzian content is two sentences at the end of §IV A reporting
  ν̄ ≈ 5/4 for the **order parameter**, with no χ, no γ, no γ′ and no error bar.

So there is no published Hong γ′ on the distribution this engine runs. A
regular-Lorentzian γ measured here would be comparing against a cell that does
not exist in their paper — legitimate ground, and unpublished ground, but not
"reproducing" or "adjudicating" anybody.

**The named deviation, measured.** PROTOCOL §3 requires deviations to be named
as deviations. The tail clip at |ω| ≤ 40γ is one, and its size is exact rather
than approximate: the clipped fraction is

    2·arctan(1/40)/π = 0.0159122…

— **1.591 % of the population, independent of N** (verified numerically at
N = 2 000 / 20 000 / 200 000: 1.6000 %, 1.5900 %, 1.5910 %). Those oscillators
are not thinned or renormalized; they are parked exactly on ±40γ, two degenerate
frequencies carrying 1.6 % of the population between them. K_c is untouched
because g(0) is untouched, and the K02 assay's negative control showed the clip
does not carry β/ν̄ (0.04977 vs 0.04744 at clip 100γ, agreeing at 1.1σ). **None of
that is evidence about γ.** β/ν̄ is a first-moment exponent and γ is a
second-moment one, and no control has been run for the second moment.

> **Effect of the clip on γ: UNDETERMINED.** Not "small", not "harmless", not
> "preserved because K_c is preserved". Unmeasured. The engine's g(ω) is a
> Lorentzian with 1.6 % of its mass moved to two atoms, which is strictly
> neither Daido's g nor Hong's, and the negative control that would settle it
> (rerun a γ column at a different clip and show the exponent does not move) has
> not been run.

Park & Park 2024 sharpen why this matters more than it looks: within the
deterministic family, exponents are *"sensitive to the specifics of the sampling
method"*, and they show s = 0 and s = 1 differ in **two** of N frequencies and
land in different FSS classes. A clip is a far larger perturbation than that —
though it acts on the tails rather than at ω ≈ 0, which is where they show the
sensitivity lives. Which of those two facts dominates is exactly what is
undetermined.

## 5. σ versus χ — the factor of two nobody announces

Daido never writes 1/4 or 1. He writes, on σ = √(N·Var):

> σ(ε) ≅ f̃(0)√(ε_c/|b|)(ε_c − ε)^(−1/2) … **Therefore γ′ = 1/2 for ε < ε_c.**  (1989, Eq. 12)
>
> σ(ε) ∝ (ε − ε_c)^(−1/8) … **Namely, γ′ = 1/8 for ε > ε_c.**  (1989, Eq. 17)

Squared into χ units those are exactly 1 and 1/4, which is what the modern
literature quotes — silently. Two further traps ride along:

* **Daido labels both sides γ′.** He has no symbol γ for the supercritical
  exponent; in his papers γ is the Lorentzian half-width. Grepping his text for
  "γ = 1/4" finds a width, not an exponent.
* **The unit shift is unannounced.** Hong et al. and Yoon et al. both restate
  Daido in χ units without saying they squared him. The arithmetic is right and
  was checked end to end here — but a lab that fits σ and compares to "1/4" has
  made a factor-of-two error in the same family as the fluctuation/response one.

> **Standing requirement for any future K-track exponent fit: state whether the
> fit was on σ or on χ, in the receipt, next to the number.**

## 6. The framing correction — one cell, not a literature

U-K02 said the two papers *"directly contradict each other"* and are *"not
reconcilable"*. That reads the wrong sentence. Hong et al.'s famous

> This suggests strongly that γ = γ′ = 1, and **definitely excludes Daido's value
> γ = 1/4.**

is in §III B — the **random** class. In the regular class they say the opposite:

> Using ν̄ = 5/4, we find γ = 0.27(3), which is close to 1/4. **This value is
> consistent with Daido's theoretical result of γ = 1/4** [4].

and disagree on one side only:

> Our results are clearly different from … his theoretical prediction of γ′ = 1
> on the subcritical side, which cannot be accounted for by adopting a slightly
> different definition of χ by Daido [15].

The contested cell is **(regular, subcritical, fluctuation)**, and it is a
narrower and better question than the one the catalogue was carrying. The second
half of that quote also closes the definitional escape hatch: within the
fluctuation family this is a physics disagreement, not bookkeeping.

Two facts lower the prior that the asymmetry is real, and both belong on the
record before anyone spends a night on it. First, **Daido's own numerics were
symmetric**: 0.123 ± 0.003 above and 0.126 ± 0.009 below, on σ — that is
0.246(6) and 0.252(18) on χ, statistically indistinguishable from Hong et al.'s
0.24(2) and 0.25(1). He discarded the subcritical measurement in favour of his
perturbation theory because *"N = 1600 chosen in Ref. 5) was still too small."*
So the dispute is not theory versus theory; it is one perturbation theory
against everybody's numerics, Daido's included. Second, **Hong et al.'s
regular-class numbers are themselves contested**: Park & Park 2024 reran the
equally-spaced case at N up to 2¹⁸ and t up to 10⁹ and revised ν̄_c from 5/4 to
1.54(7), showing that the 5/4-compatible reading is exactly what you measure at
Hong's sizes before a late crossover. Hong's ν̄-independent estimates (0.24(2),
0.25(1)) survive that arithmetic — but they were taken at N = 6400, inside the
window Park & Park show to be pre-asymptotic.

## 7. What remains UNDETERMINED

Stated plainly, because the point of this assay is that the entry stopped
saying true things once and should not do it again.

1. **Nobody reached Daido, *J. Stat. Phys.* 60, 753 (1990).** Springer paywall.
   It is the canonical citation for the 1/4-and-1 pair. The 1989 letter carries
   the same pair in σ units and the 1990 abstract calls the diverging object
   *"the intensity … of fluctuations"*, so the pair itself is verified at primary
   text — but **what that paper defines, and in which units, is not**, and no
   equation number from it may be cited on this chain. `evidence/literature/
   daido-1990-jsp60-753.json` records the hole rather than papering it.
2. **γ_sus = 1 has never been established for the regular class.** Hong et al.
   assert it in one sentence, inside their **random**-class section, with no
   derivation, no error bar and no class label, citing a Daido paper (*PRE* 91,
   012925 (2015)) that this pass reached only in abstract. The argument that a
   thermodynamic-limit response must be class-independent is an inference, not a
   quoted result. Nobody has measured ∂⟨r⟩/∂h on a regular-sampled finite-N
   ensemble at all.
3. **The clip's effect on γ.** §4. Unmeasured, and the control is cheap.
4. **The regular-Lorentzian γ and γ′ are unpublished outright.** Hong et al.
   report only ν̄ there; Park & Park deliberately avoided the Lorentzian and
   declined to measure γ at all, in writing, twice — *"a detailed discussion for
   γ will be reported elsewhere"* — and the follow-up has not appeared.

## 8. Routing

- **U-K02's wording is corrected, not deleted.** Its history stays in the entry,
  because the correction is the more useful artifact than a clean-looking entry
  would have been. Its `status`, `reach` and `reach evidence` are untouched.
- **The entry is NOT settled, NOT attempted and NOT retired.** A literature pass
  narrows a question; it does not answer it, and it is not this assay's or any
  agent's call to close one. **That is Ben's ruling to make.**
- **`src/lab/k03.py` was corrected inside this same branch** by the rivals lane,
  after this section was written. Its module docstring and its `DAIDO` record now
  cite Prog. Theor. Phys. **81**, 727 (1989); `tests/test_rivals.py` asserts that
  "75, 1460" stays out of `DAIDO["source"]`; and the ∂⟨r⟩/∂h wording is gone from
  that module. **What remains is `src/lab/kuramoto.py`**, whose `_drift` docstring
  still calls the linear-response susceptibility ∂⟨r⟩/∂h *"the quantity Daido and
  Hong disagree about"* — which the pinned Hong record contradicts: both sides'
  γ/γ′ are fluctuation exponents on χ = N·Var_t(r), and Hong et al. give the field
  response a different symbol AND value in the same paragraph. That module is
  outside this pass's lane and is reported rather than edited. Files are named
  without line numbers so a later edit cannot rot this bullet again.
- **Public phrasing**, until the above lands: cite Prog. Theor. Phys. **81**, 727
  (1989) for the asymmetry and J. Stat. Phys. **60**, 753 (1990) as the long
  version nobody here has read. Never cite Prog. Theor. Phys. 75, 1460 (1986)
  for it.

## 9. Free wins

PROTOCOL §9: a careful read of the literature in our exact regime is the best
chance the lab gets to find its next experiment. Three came out of this one, in
descending order of what they cost.

1. **The cheapest is the clip control, and it is owed anyway.** One γ column
   rerun at clip 100γ with dt reduced to keep the fastest drifter resolved,
   exactly as K02's β/ν̄ control was run. It converts §4's UNDETERMINED into a
   number, and it is minutes, not GPU-hours.
2. **The regular-Lorentzian γ is genuinely unpublished.** Not UNPUBLISHED (b) —
   it is not one line from anything, because Hong et al. never computed χ on that
   distribution and Park & Park avoided it. Whether that is worth measuring is a
   separate question from whether it would be new, and the answer to the second
   is yes.
3. **The regular-class FDT check is unclaimed.** Hong et al.'s own numbers imply
   a violation in the regular class — fluctuation γ = 1/4 against response
   γ_sus = 1 — and nobody has checked it. This box can measure both observables
   on the same ensemble, which is the whole test. It is adjacent to U-K02 rather
   than inside it, and it is a better use of an instrument that already has a
   pinning field than re-measuring a pair it cannot adjudicate.
