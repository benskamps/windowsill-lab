# Novelty-certification protocol

The check gate (`checks.py`) asks whether a number is *right*. This asks whether
it is *ours*. A milestone crosses into frontier territory only when a number
survives both — its own check, and a literature search that comes back empty and
stays empty when someone else runs it.

Physics has no OEIS: there is no table to look a value up in, so the search *is*
the gate, and it has to be built with the same discipline as the checks — an
adversarial procedure, written down, with receipts a stranger can re-run.

Worked exemplar: [`2026-08-02-k02-literature-crosscheck.md`](2026-08-02-k02-literature-crosscheck.md).
Everything below is an abstraction of what that assay actually did. The Erdős
Check discipline it transposes lives in `~/projects/erdos-check/CLAUDE.md`.

---

## 1. When an assay fires

**Any measurement a milestone wants to claim beyond calibration.** If the check
gate compares the number against an exact known value (Onsager's T_c, `K_c = 2γ`,
KPZ's 1/3, the Nishimori identity), that is calibration and no assay is needed —
the literature *is* the gate already. The moment a milestone reports a number
with nothing exact behind it — a fitted exponent, a collapse, an optimum, a
threshold, a shape — an assay is owed before that number appears in a report
headline, on `brokenbranch.dev`, or in a `MILESTONES.md` entry phrased as a
finding. It fires per *number*, not per milestone: K02 carried three sub-claims
and each got its own verdict.

## 2. Stance

**Default hypothesis: rediscovery.** The assayer's job is to find the *strongest
published statement* of each element, not to protect the result. An assay that
returns "novel" without having tried hard to kill the claim has certified
nothing. K02's headline — *"K02's physics is right. K02's novelty is nil, and its
headline number is off"* — was the correct output of a good assay, not a bad day.

## 3. Match the configuration class before comparing anything

**This is the gate the whole protocol turns on. An exponent comparison is
meaningless until the configuration class is matched.**

The literature usually holds several values of "the same" exponent, differing by
setup details a non-specialist reads as incidental. K02's engine drew frequencies
at the deterministic midpoint quantiles `(i+½)/N` — the literature's *regular /
equally-spaced* sampling, whose published collapse exponent is 0.39(2), while the
*random* iid value a casual search surfaces first is 0.20. Grading against the
wrong class turns a clean rediscovery into a fake discovery, or the reverse.

So, before any number is compared, establish and write down:

- **the model and its parameters** — coupling form, boundary conditions,
  dimension, disorder distribution;
- **the sampling / disorder rule**, at the level of the actual line of code
  (K02: `omega = gamma * np.tan(np.pi * ((arange(n)+0.5)/n - 0.5))`, matched term
  for term to Hong et al. Eq. 4.1 and §IV A);
- **the estimator's exact definition** (see §4);
- **the regime** — the N or L window, and whether the published value is
  asymptotic or effective there. K02's ladder sat entirely below the crossover
  where the asymptotic 0.325 takes over, so the applicable published value was
  the pre-asymptotic 0.39(2). Getting this backwards manufactures a fake tension.

If no published work matches the configuration, say so explicitly — that is a
real finding, and it is the *only* honest route to UNPUBLISHED on an exponent.

Any deviation from the matched configuration gets named as a deviation, not
buried. K02's tail clip at `|ω| ≤ 40γ` preserves K_c exactly but collapses ~1.6%
of the population onto two degenerate frequencies; that is an uncontrolled
difference from the papers it would be graded against, and it earns a negative
control (rerun one rung at a different clip and show the number does not move).

## 4. Estimator audit

Ask, in one sentence: **is our number measuring what their number measures?**

Compare our estimator to the literature's estimator symbol by symbol. Two failure
modes, both real:

- **Same name, different quantity.** Check the definition, not the label.
- **A compound estimator inheriting its own misfit.** K02's headline −0.28 was
  not `r(K_c,N)` at all — it was `p/(p+q)` read off a free Beta fit whose R² was
  0.73–0.82 and whose parameters *tracked N*. Its N-dependence was a compound of
  the physics and the fit family's drift, and the drift was plausibly the bigger
  term. The literature-comparable measurement (fit `log⟨r⟩` at the exact known
  coupling against `log N`) was available from data already collected.

If a direct, literature-comparable estimator exists in the data we already have,
the assay says so and the direct number is what gets graded.

## 5. Error bars are mandatory

**No exponent or fitted number enters an assay comparison without an uncertainty.**

K02 shipped −0.28 with none. Against Hong's 0.39(2) that is ~5σ low, but with no
bar of its own the comparison is not symmetric, so the line is neither
"consistent with published" nor "in tension with published" — it is unreadable.
That was the single most consequential reporting gap in the assay, and it is the
named anti-pattern here.

State what the bar covers: a tight OLS statistical error on a straight log-log
line is not the uncertainty (M15 says this well), and the systematic band from
estimator and window choice usually dominates.

## 6. Verdict vocabulary

One verdict per sub-claim, with its citation or its empty searches.

| Verdict | Means | Requires |
|---|---|---|
| **REDISCOVERED** | Published, in a matched configuration | The *strongest* published statement — paper, section, equation. If the literature is sharper than us, say so and give their number. |
| **EXTENDS** | Published, but our result goes past it | The citation **and** the delta, stated as a quantity. The delta is the claim; the published part is not. |
| **UNPUBLISHED** | Nothing found | The searches that came back empty, verbatim, plus a sentence on *why* the absence is plausible. |

**The category (b) rule.** A statement derivable-in-one-line from a published
result is **not** a crossing, even when no paper states it. K02's "the χ peak
collapses in r-space; the fixed point is in K only" returned four empty searches
— and is one line from Hong et al. Eq. (4.3). The right reading of that negative
is that specialists do not reparametrize to the response variable, not that we
found something; it is unpublished the way "3 is not an even number" is
unpublished. So UNPUBLISHED splits, and the assay says which: **(a)** genuinely
absent and not derivable → candidate frontier claim; **(b)** absent but one line
from published work → real pedagogy for the lab, not a contribution to the field.

## 7. The searches are part of the receipt

An assay's negative result is only checkable if the search is.

- **Pinned citations**: title, authors, year, journal + arXiv id, and the
  *specific* equation, figure, or section carrying the claim. "Hong et al. 2015"
  is not a citation; "Hong et al. 2015, Eq. (4.2)–(4.3), Fig. 6" is.
- **Empty searches listed verbatim** — the exact query strings, so a reader can
  re-run them and either confirm the hole or fill it.
- **What was retrieved and rejected**: the papers that came back and did *not*
  contain the claim, one line each on why. A hole is more convincing when the
  surrounding corpus is named.
- **Numerical coincidences flagged**. K02's Run 01 `r* = 2/5` (a coherence value)
  and Hong's `β/ν̄ = 2/5` (a scaling exponent) are unrelated quantities landing on
  the same number; left unflagged, that collision manufactures a deep connection
  in the next writeup.

The assay lives in `docs/assays/YYYY-MM-DD-<milestone>-literature-crosscheck.md`
and is linked from the milestone's `MILESTONES.md` entry.

## 8. Outcome routing

- **REDISCOVERED** → the number is relabelled as **calibration against a
  published value**, and the `MILESTONES.md` entry cites the paper. This is a
  good outcome, not a demotion: "we reproduced a real result on a windowsill" is
  the lab's actual thesis, and citing it is strictly stronger than an unsourced
  near-miss. If our number disagrees with the published one, that disagreement is
  a defect to chase (§4), not a finding.
- **EXTENDS** → the delta is the claim, stated with its error bar, assay attached.
  The published portion is described as published, in the same sentence.
- **UNPUBLISHED (a)** → a candidate frontier claim. **It requires a second,
  independent assay pass before the word "frontier" appears anywhere public.**
  Independent means a different assayer working from the claim, not a re-read of
  this document — and if both passes are the same model family, they are
  correlated evidence and the assay says so.
- **UNPUBLISHED (b)** → written down as lab pedagogy; no novelty claim.

Until an assay exists, the safe public phrasing cites the literature's value
rather than ours. K02's `/fireflies/` reframe quotes the published N^−1/3 range,
not the unreplicated −0.28.

## 9. Free wins

An assay reads the literature carefully in our exact regime, which is the best
chance the lab gets to find its *next* experiment — note them. K02 surfaced a
live disagreement (Daido's `γ = 1/4`, `γ' = 1` against Hong et al.'s `γ = γ'`)
checkable with a one-line fit on data already on disk. That is a better next
milestone than another pass at the refuted form.
