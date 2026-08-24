# evidence — the bytes a milestone was derived from

A receipt says what was measured. This directory holds **what it was measured
from**, so anyone who clones the repo can re-derive the number rather than
trusting the receipt that reports it.

`check_a02` looks here when the box's own cache is absent, which is the case on
every CI runner and every fresh clone. Both copies are pinned by SHA-256 in the
receipt, so a committed file that has drifted grades `False` rather than
quietly passing.

## Why this exists

A02 was promoted on 2026-08-24 and CI immediately failed it — not because the
science was wrong, but because the six TESS light curves it folded live on the
box that downloaded them. The estate had already met this shape twice (A05, A07)
and answered it with "cannot re-derive on this box is not evidence against the
run", which is true and was enough while neither was promoted. A02 was the first
green milestone whose check needed bytes nobody else had.

Ben's call: commit them. **11.6 MB buys independent verifiability of a promoted
result, and this lab's entire claim is that its numbers can be checked by
someone who does not trust it.**

## What does NOT belong here

Not every run's inputs. A05's hunts reference dozens of light curves per slice
and would put gigabytes in a public repo to no benefit, because A05's claim is a
*measured false-alarm rate*, not a re-derivable constant. The rule is narrow:

> **Evidence is committed when a PROMOTED milestone's checker cannot otherwise
> re-derive its headline number.** Everything else stays in the box-local cache
> and grades `needs-evidence` off-box, which is honest and costs nothing.

## Contents

* `a02/` — six TESS SPOC light curves (2 MB each) and six AAVSO VSX records
  (~5 KB each), one pair per star in the graded sample.
