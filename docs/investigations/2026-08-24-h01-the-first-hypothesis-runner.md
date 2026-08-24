# H01 — the first runner written as a question

**2026-08-24 · Steward (PM) + Quill (lead researcher) · track C**

The new pot's rule is that a runner *is* a hypothesis. This is the first one
built under it, and it is deliberately small: the point of a first runner is to
prove the shape, not to be impressive.

## What was asked

> Does C05's deep BBP window at hex position 10^7 survive an independent
> exact-integer computation, or has float64's tail already corrupted digits the
> lab is reporting?

Quill picked it off C05's own docstring, which names the float tail as its
precision boundary — *"the known precision limit … and if that ever stops being
true"* — and then never checks. Two things made it the right first target:

1. **C05 grades its deep window by overlap with an adjacent window.** Both are
   float computations. Two instances of the same method agreeing with each other
   is not independence, and the lab was calling it verification.
2. **`reports/receipts/` held no C05 receipt at all.** The runner had existed for
   weeks and had never been executed. Nobody noticed because nothing in the
   estate distinguishes "ran and passed" from "never ran".

Steward accepted it on one condition, stated before any code: *only because it
can die.* The kill condition was written first and names what gets given up —

> Any disagreement inside the reported window kills the claim: C05's deep digits
> are retracted, and the position of the first failing digit becomes the
> measured result.

Quill also had to state, in advance, how it might be nothing: an 8-hex window is
~32 bits, comfortably inside float64's ~52-bit mantissa, so **agreement was
always the likely outcome**. It was worth four hours anyway, because that
untested sentence sits exactly where Track C's own goal — *verifiable by a
second, independent method* — was quietly failing.

## What was done

`exact_bbp_window` recomputes the same window in scaled-integer arithmetic at
192 bits. Every division is floored, so each term loses at most one unit and
never gains; with d+1 head terms and ~P/4 tail terms the total truncation error
is bounded by (d + P/4 + 2)·2⁻ᴾ ≈ 10⁻⁵¹ at d = 10⁷ — forty orders of magnitude
below the last digit reported.

**Controls ran first, and the ordering is the entire safety argument.** At
shallow positions the exact path is checked against π computed by Machin's
arctan formula, which shares no code with BBP. An exact implementation that has
not been shown to agree with a known answer *somewhere* cannot be used to accuse
the float path *anywhere*. If the controls fail, the run returns `unresolved`
and concludes nothing — there is a test that monkeypatches the exact path to
garbage and asserts it refuses to judge rather than issuing a false retraction.

## Result — SUPPORTED

| position | Machin | exact | float |
|---|---|---|---|
| 0 | `243F6A88` | `243F6A88` | `243F6A88` |
| 16 | `13198A2E` | `13198A2E` | `13198A2E` |
| 1000 | `49F1C09B` | `49F1C09B` | `49F1C09B` |
| **10,000,000** | — | **`7AF5863E`** | **`7AF5863E`** |

58 seconds, no GPU. The float tail has not corrupted the reported window.

C05's caveat narrows from *unverified* to **verified to this depth by exact
arithmetic**, and the deep window now has a receipt from a genuinely independent
method rather than from a second copy of itself.

## What this does not claim

- **Not proof that float64 is safe at greater depth.** One depth was audited.
  The head-term count grows linearly with d, so the float error grows too; the
  honest statement is "verified at 10⁷", full stop.
- **Not a claim that the digits are correct in some absolute sense** — only that
  two independent methods, one of them exact with a proven bound, agree.
- **The likely-boring outcome happened.** That is what the predeclared
  `why_this_might_be_nothing` field is for: a supported hypothesis that was
  always likely to be supported is a small result, and calling it a large one
  would be the first crack in the pot.

## What the runner leaves behind

The shape, which is the actual deliverable:

- `lab.hypothesis.Hypothesis` — six required fields, and it **raises on
  construction** if any is missing. A question that cannot say what would refute
  it is not constructible here. The six are pinned by test to the six
  `lab frontier` already demands of proposals, so the board's schema is now
  executable rather than advisory.
- Three verdicts, with `killed` a first-class **success**: the receipt's
  `status: pass` means *the experiment decided*, not *the audited claim
  survived*, and `claim_boundary` says which happened every time. A lane that
  filed self-correction as a job failure would stop doing it, so `lab h01`
  exits 0 on a kill.

Three failures in a single day motivated that refusal, and none of them are
constructible under it: M14's runner with no test on its order parameter, A05's
uniformity control that ran ten days while structurally unable to fail, and
C05 — which this note just executed for the first time.
