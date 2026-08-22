"""A05 fold gates — measure the eclipse before grading it.

Three seams opened on 2026-08-18, when TIC 287328866 walked through every gate
in the ladder and landed on the shelf as `lead-awaiting-human-review`. It was an
eclipsing binary at 2.0765 d, detected at its P/2 alias, and ExoFOP had carried
it as two community candidates since 2019
(`docs/investigations/2026-08-18-tic287328866-p2-alias-refutation.md`). Every
gate behaved exactly as written; the writing was the defect. This module fixes
two of the three (the third, the CTOI table, lives in
:func:`lab.a04.catalog_crosscheck` where the other catalog lookups already are)
— and, in the course of fixing them, retires the mechanism the refutation note
proposed for the first one. See Seam 1.

### Seam 1 — the odd/even split is a counting scheme, and the count can slip

The 2026-08-18 refutation attributed the miss to DILUTION: A04 measures a parity
depth as the median over a fixed ±0.03 phase window, and the note reasoned that
a window wider than the eclipse would drag the median toward baseline and shrink
the odd-minus-even difference the gate grades. That note compared the vet's
numbers (1.410 % / 1.496 %, measured on DETRENDED, prewhitened flux) against
depths measured on raw quality-masked PDCSAP (2.102 % / 1.661 %) and read the
gap as a 5x estimator dilution.

**Re-measured on matched flux, that is not what happened.** Running both
estimators on the same detrended series (see the module's tests and
`docs/investigations/2026-08-19-fold-gate-validation.md`), the fixed-window
medians and the duration-matched depths agree to about 1 % on this star: the
window was not eating the eclipse. Most of the 2.1 % -> 1.65 % difference is the
0.5 d running-median detrend, applied before the vet and not before the note's
hand fold. The dilution claim conflated two different flux series.

What the re-measurement DID find is a different defect in the same estimator.
A04 labels epochs ``floor((t - t[0]) / P)``, which puts the epoch boundary at
whatever phase the first cadence happens to occupy. On TIC 287328866 sector 3
(transit phase 0.895) the boundary lands close enough to the transit that the
two epoch conventions — A04's, and the transit-centred one
``lab.a05_vetting.centroid_shift`` already uses — disagree about the **sign** of
the odd-even difference: −0.00086 one way, +0.00104 the other. The photons
cannot care where the counting started, so that sign is a labelling artifact,
and any gate reading it is grading its own bookkeeping. :func:`odd_even_fold`
uses the centred convention; :func:`windowed_odd_even` keeps A04's, unchanged,
as the reference the two can be compared against.

Even centred, the parity split reached only 2.7σ on that sector while the
doubled fold reached 5.0σ. Splitting by counted epoch is simply a weaker way to
ask the question than splitting by phase, which is why Seam 2 carries the
verdict and this one is a supporting measurement.

### Seam 2 — the secondary test is vacuous at a P/2 alias

A04 looks for a secondary eclipse at phase 0.5 of the DETECTED period. When the
detection is the P/2 alias of a binary, both eclipses are already folded on top
of each other and there is no phase left for a secondary to appear at:
TIC 287328866 returned secondary_sigma = 0.48, which reads as "no secondary,
consistent with a planet" and means nothing at all. A near-zero secondary is
only evidence when the detected period is the true period — which is the
question being asked.

:func:`p2_fold` runs the discriminating test instead: fold at 2P and measure
both minima. A planet at P produces two dips of EQUAL depth there (alternate
transits, same star, same occulter). A binary at 2P produces two dips of
UNEQUAL depth (primary and secondary). Note carefully what is and is not
evidence: the 0.5 phase separation is *guaranteed by construction* — every
detection at P puts its events at two phases half a fold apart when folded at 2P
— so it is a consistency check on the arithmetic, never a finding. The evidence
is the depth difference, and only when both dips are individually significant.

### What these gates may NOT do

They may not move a disposition off `lead-awaiting-human-review` in the
direction of a planet. Every verdict here is a REFUTATION — a way for the
machine to take a candidate away from itself. The estimator is deliberately
built so that its failure mode is a lead that stays on the shelf, not a lead
that leaves it wrongly: both dips must clear MIN_ECLIPSE_SIGMA on their own
before a depth difference is allowed to mean anything, and a dip measured
against fewer than MIN_DIP_CADENCES cadences reports ``None`` rather than a
number.

Error bars here are white-noise bars: ``sigma_point / sqrt(n)`` from the local
MAD. Correlated stellar variability on the eclipse timescale would make the true
bar larger, so a marginal fire near the threshold is soft. This is the same
assumption every depth bar in A04 already makes; it is stated here rather than
inherited silently.
"""
from __future__ import annotations

import numpy as np

from . import a04
from .a04 import Detection

#: Bins across the measurement window when locating the dip's support. The
#: fold is binned only to FIND the eclipse; the depth itself is measured from
#: unbinned cadences inside the located support, so this number sets the
#: resolution of the duration estimate and nothing else.
DIP_BINS = 24

#: The dip's support runs outward from its deepest bin while the binned depth
#: stays above this fraction of the peak depth — a half-depth (FWHM) support.
#: Half, not a noise multiple: it is a property of the eclipse SHAPE, so it
#: does not drift with the star's noise level the way a sigma-based edge would.
DIP_FLOOR_FRAC = 0.5

#: Baseline and scatter come from an annulus around the dip: cadences between
#: one and this many measurement windows away. Local, so anything drifting
#: slower than one window cancels before it can become depth.
DIP_OUT_FACTOR = 3.0

#: A dip measured on fewer cadences than this is not measured. (12 matches
#: A04's in-transit minimum; below it the mean is a rumour.)
MIN_DIP_CADENCES = 12

#: Each dip must clear this on its own before any COMPARISON between two dips
#: is allowed to carry a verdict. Without it, two noise excursions of opposite
#: sign would "differ significantly" and refute a candidate for free.
MIN_ECLIPSE_SIGMA = 5.0

#: Depth difference significance at which the 2P fold calls the detection the
#: P/2 alias of a binary. Matches A04's ODD_EVEN_SIGMA: the two gates ask the
#: same physical question (do alternate eclipses differ?) and disagreeing about
#: the bar would mean the answer depended on which one happened to run.
P2_ALIAS_SIGMA = a04.ODD_EVEN_SIGMA

#: Measurement half-window, in phase, at whichever period is being folded.
#: Deliberately equal to A04's SEARCH window rather than smaller: this
#: estimator finds the eclipse's support inside the window instead of assuming
#: it fills it, so a generous window costs nothing and a stingy one silently
#: truncates a long eclipse. At the doubled period this is twice A04's window
#: in absolute time, which is the point — a 2 h eclipse on a 2 d binary does
#: not fit in A04's ±0.03 of the ALIAS period.
MEASURE_WINDOW_PHASE = a04.VET_WINDOW_PHASE

#: Standard error of a median vs a mean on Gaussian noise, sqrt(pi/2). The
#: aperture reads depths with a median (see :func:`depth_in_support`), so the
#: error bar has to pay the median's efficiency cost rather than quietly
#: reporting a mean's bar on a median's number. Defined in :mod:`lab.a04` and
#: re-exported here: this module fixed the math first, A04's vetting rung
#: carried the mean's bar until VET-F3, and one convention beats two.
MEDIAN_SIGMA_FACTOR = a04.MEDIAN_SIGMA_FACTOR

#: Hard ceiling on the half-window. The annulus reaches DIP_OUT_FACTOR windows
#: out, and in the doubled fold the OTHER eclipse sits at Δφ = 0.5; letting the
#: baseline annulus reach it would measure each eclipse's depth against the
#: other one. Half of that separation, with the factor divided out.
MAX_HALF_WINDOW = 0.25 / DIP_OUT_FACTOR


def _mad_sigma(x: np.ndarray) -> float:
    """Robust sigma from the median absolute deviation. Empty -> inf."""
    if len(x) == 0:
        return float("inf")
    med = float(np.median(x))
    return float(1.4826 * np.median(np.abs(x - med)))


def measure_dip(t: np.ndarray, f: np.ndarray, period: float,
                center_phase: float, half_window: float,
                bins: int = DIP_BINS) -> dict:
    """Depth of the dip at ``center_phase``, measured over its OWN support.

    Steps: take the cadences within ``half_window`` of the fold phase; take the
    local annulus (1 to DIP_OUT_FACTOR windows out) as baseline and scatter;
    bin the in-window cadences and find the deepest bin; grow a contiguous
    support outward while the binned depth holds above DIP_FLOOR_FRAC of the
    peak; then measure the depth as ``baseline - mean(flux)`` over the *unbinned*
    cadences inside that support.

    Returns depth, its white-noise sigma, the significance, the measured
    duration in phase units, and the cadence counts — plus ``edge_limited`` when
    the support ran into the window edge, which means the duration (and hence
    the depth) is a lower bound on the eclipse, not a measurement of it.

    ``depth`` is signed: a bump returns a negative depth rather than zero, so a
    caller can tell "nothing there" from "the opposite of an eclipse".
    """
    out: dict = {"depth": None, "sigma": None, "depth_sigma": None,
                 "duration_phase": None, "n_in": 0, "n_out": 0,
                 "edge_limited": False, "reason": None}
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    if period <= 0 or half_window <= 0:
        out["reason"] = "bad-window"
        return out
    ph = np.mod(t, period) / period
    d = ((ph - center_phase + 0.5) % 1.0) - 0.5          # signed distance, no wrap
    in_win = np.abs(d) <= half_window
    annulus = (np.abs(d) > half_window) & (np.abs(d) <= DIP_OUT_FACTOR * half_window)
    out["n_out"] = int(annulus.sum())
    if in_win.sum() < MIN_DIP_CADENCES or annulus.sum() < MIN_DIP_CADENCES:
        out["reason"] = "insufficient-cadences"
        return out

    baseline = float(np.median(f[annulus]))
    sigma_pt = _mad_sigma(f[annulus] - baseline)
    if not np.isfinite(sigma_pt) or sigma_pt <= 0:
        out["reason"] = "degenerate-scatter"
        return out

    # Bin only to locate the support. Empty bins are impassable: the support
    # must be contiguous in DATA, so a gap ends it rather than being crossed.
    edges = np.linspace(-half_window, half_window, bins + 1)
    idx = np.clip(np.digitize(d[in_win], edges) - 1, 0, bins - 1)
    fin = f[in_win]
    depth_bin = np.full(bins, np.nan)
    for b in range(bins):
        sel = idx == b
        if sel.sum() >= 3:
            depth_bin[b] = baseline - float(np.median(fin[sel]))
    if not np.isfinite(depth_bin).any():
        out["reason"] = "empty-fold"
        return out

    # Grow the support from the CENTER bin — the phase the ephemeris predicts —
    # not from the deepest bin in the window. Free-floating the start would let
    # the estimator select the most favourable noise excursion out of `bins`
    # tries, which biases every depth upward and would let pure noise clear
    # MIN_ECLIPSE_SIGMA. The deepest bin is still reported, as a diagnostic:
    # far from centre means the ephemeris and the flux disagree.
    center = bins // 2
    out["peak_offset_bins"] = int(np.nanargmax(depth_bin) - center)
    if not np.isfinite(depth_bin[center]):
        out["reason"] = "empty-centre-bin"
        return out

    def _grow(floor: float) -> tuple[int, int]:
        lo = hi = center
        while lo - 1 >= 0 and np.isfinite(depth_bin[lo - 1]) and depth_bin[lo - 1] >= floor:
            lo -= 1
        while hi + 1 < bins and np.isfinite(depth_bin[hi + 1]) and depth_bin[hi + 1] >= floor:
            hi += 1
        return lo, hi

    # The eclipse's own peak depth is the deepest bin CONNECTED to the centre,
    # not the deepest bin in the window: the half-depth edge has to be measured
    # against this eclipse, and the centre bin may sit on the ingress.
    lo0, hi0 = _grow(0.0)
    peak_depth = float(np.nanmax(depth_bin[lo0:hi0 + 1]))
    if peak_depth <= 0:
        # No dip at all here. Report the window mean so the caller still gets a
        # signed number (and can see a bump), but mark the support undefined.
        depth = baseline - float(np.mean(fin))
        n_in = int(in_win.sum())
        sigma = sigma_pt / np.sqrt(n_in)
        out.update({"depth": float(depth), "sigma": float(sigma),
                    "depth_sigma": float(depth / sigma), "n_in": n_in,
                    "duration_phase": float(2 * half_window),
                    "reason": "no-dip"})
        return out

    lo, hi = _grow(DIP_FLOOR_FRAC * peak_depth)
    out["edge_limited"] = bool(lo == 0 or hi == bins - 1)

    support = (d >= edges[lo]) & (d <= edges[hi + 1])
    n_in = int(support.sum())
    if n_in < MIN_DIP_CADENCES:
        out["reason"] = "support-too-thin"
        return out
    depth = baseline - float(np.mean(f[support]))
    sigma = sigma_pt / np.sqrt(n_in)
    out.update({"depth": float(depth), "sigma": float(sigma),
                "depth_sigma": float(depth / sigma), "n_in": n_in,
                "duration_phase": float(edges[hi + 1] - edges[lo])})
    return out


def depth_in_support(t: np.ndarray, f: np.ndarray, period: float,
                     center_phase: float, half_support: float,
                     half_window: float) -> dict:
    """Depth over a GIVEN support — no locating, no choosing.

    Split out from :func:`measure_dip` because two dips being compared must be
    measured through the same aperture. Letting each one find its own support
    means the difference between them mixes a depth difference with a support
    difference, and on a planet whose fitted period is a little off the true one
    the supports genuinely differ (the fold smears, and the two halves of the
    doubled fold smear differently). That path produced a false
    `eclipsing-binary-p2-alias` on a planted synthetic transit before this
    function existed — the exact failure this whole module is built to avoid.
    """
    out: dict = {"depth": None, "sigma": None, "depth_sigma": None,
                 "duration_phase": float(2 * half_support), "n_in": 0,
                 "n_out": 0, "reason": None}
    ph = np.mod(np.asarray(t, dtype=float), period) / period
    d = ((ph - center_phase + 0.5) % 1.0) - 0.5
    f = np.asarray(f, dtype=float)
    support = np.abs(d) <= half_support
    annulus = (np.abs(d) > half_window) & (np.abs(d) <= DIP_OUT_FACTOR * half_window)
    out["n_in"], out["n_out"] = int(support.sum()), int(annulus.sum())
    if support.sum() < MIN_DIP_CADENCES or annulus.sum() < MIN_DIP_CADENCES:
        out["reason"] = "insufficient-cadences"
        return out
    baseline = float(np.median(f[annulus]))
    sigma_pt = _mad_sigma(f[annulus] - baseline)
    if not np.isfinite(sigma_pt) or sigma_pt <= 0:
        out["reason"] = "degenerate-scatter"
        return out
    # MEDIAN through the aperture, not mean. A cadence either falls inside an
    # eclipse or does not, and the two halves of a doubled fold do not sample
    # the ingress/egress cadences identically — one may catch 57 in-eclipse
    # cadences per event where the other catches 58. Through a mean, that
    # one-cadence asymmetry is a real depth difference of order depth/57, which
    # on a 2 % planted transit measured 5.4σ and fired this gate on a PLANET.
    # The median is blind to a handful of edge cadences and returned 1.9σ on
    # the same curve while recovering the injected depth to 0.1 %.
    #
    # Note what this does NOT say: A04's estimator was never wrong for being a
    # median. It was wrong for taking that median over a window sized for
    # searching. The aperture is the fix; the median is how it is read.
    depth = baseline - float(np.median(f[support]))
    # Asymptotic efficiency of the median on Gaussian noise: sqrt(pi/2).
    sigma = MEDIAN_SIGMA_FACTOR * sigma_pt / np.sqrt(int(support.sum()))
    out.update({"depth": float(depth), "sigma": float(sigma),
                "depth_sigma": float(depth / sigma)})
    return out


def p2_fold(t: np.ndarray, f: np.ndarray, det: Detection,
            half_window: float | None = None) -> dict:
    """Fold at 2P and compare the two eclipses through ONE aperture.

    A detection at period P places its events at fold phases ``det.phase/2`` and
    ``det.phase/2 + 0.5`` when folded at 2P. The support is located ONCE, on the
    fold at the detected period where every event stacks (best signal, and
    symmetric between the two groups by construction); both eclipses are then
    measured through that same support at 2P. The verdict is
    `eclipsing-binary-p2-alias` when both are individually significant AND their
    depths differ by P2_ALIAS_SIGMA.

    The deeper dip is reported as A regardless of which phase it sits at, so
    ``depth_ratio >= 1`` always and the row reads the same way for every star.

    What is NOT evidence: the 0.5 phase separation is guaranteed by the
    arithmetic above, so it is a consistency check, never a finding.
    """
    p_det = float(det.period_days)
    p2 = 2.0 * p_det
    c_a = (float(det.phase) / 2.0) % 1.0
    c_b = (c_a + 0.5) % 1.0

    # One support, located on the stacked fold at the DETECTED period — on the
    # stack rather than on either eclipse, so neither gets to choose the
    # aperture it is judged in.
    #
    # The window ESCALATES until the support fits inside it. A16-hour eclipse
    # on a 1 d alias occupies more phase than A04's ±0.03 search window, and a
    # support pinned at the window edge is a lower bound on the eclipse, not a
    # measurement of it: measuring both eclipses through a clipped aperture
    # would compare two unknown fractions. Escalating is not loosening — the
    # aperture is still identical for both eclipses; only its size is now set
    # by the star instead of by a constant.
    stacked = None
    hw = float(half_window) if half_window is not None else None
    ladder = ([hw] if hw is not None
              else [MEASURE_WINDOW_PHASE * k for k in (1.0, 1.5, 2.0, 2.7, 3.5)])
    for trial in ladder:
        trial = min(float(trial), 2.0 * MAX_HALF_WINDOW)
        got = measure_dip(t, f, p_det, float(det.phase), trial)
        stacked, hw = got, trial
        if got["depth"] is not None and not got.get("edge_limited"):
            break
    out = {"verdict": None, "period_2p_days": float(p2),
           "support": stacked, "support_half_window_phase": float(hw),
           "phase_separation": 0.5,
           "depth_difference": None, "difference_sigma": None,
           "depth_ratio": None, "both_eclipses_significant": False}
    if stacked["depth"] is None or stacked["duration_phase"] is None:
        out["reason"] = stacked.get("reason") or "no-support"
        return out
    if stacked.get("edge_limited"):
        # Still clipped at the widest aperture the doubled fold allows: the
        # eclipse is too long for its own period to be measured this way.
        out["reason"] = "support-edge-limited"
        return out
    # Phase units halve when the period doubles: a given time offset is half as
    # much phase at 2P as it is at P.
    half_support = 0.5 * float(stacked["duration_phase"]) / 2.0
    hw_2p = hw / 2.0
    dip_1 = depth_in_support(t, f, p2, c_a, half_support, hw_2p)
    dip_2 = depth_in_support(t, f, p2, c_b, half_support, hw_2p)

    def _depth(dip):
        return dip["depth"] if dip["depth"] is not None else -np.inf

    a, b = (dip_1, dip_2) if _depth(dip_1) >= _depth(dip_2) else (dip_2, dip_1)
    out["eclipse_a"], out["eclipse_b"] = a, b
    out["phase_a"], out["phase_b"] = float(c_a), float(c_b)
    if a["depth"] is None or b["depth"] is None:
        out["reason"] = a.get("reason") or b.get("reason") or "unmeasurable"
        return out
    diff = float(a["depth"] - b["depth"])
    sigma = float(np.hypot(a["sigma"], b["sigma"]))
    out["depth_difference"] = diff
    out["difference_sigma"] = float(diff / sigma) if sigma > 0 else float("inf")
    # The sort above makes `depth_difference` a MAGNITUDE: A is the deeper dip
    # by construction, so it is never negative and a "sign" taken from it
    # carries no information at all. `combine_p2_folds` used to test exactly
    # that non-sign across sectors, which is why its guard could never fail and
    # why combining |noise| grew like sqrt(k) (VET-F2). The quantity that DOES
    # carry information is anchored to the fold PHASE rather than to the sort:
    # which of the two fixed eclipse slots was the deeper one. A real
    # primary/secondary alternation puts the same slot on top in every sector;
    # noise does not.
    out["signed_difference"] = float(dip_1["depth"] - dip_2["depth"])
    out["deeper_phase"] = float(c_a if out["signed_difference"] >= 0 else c_b)
    out["depth_ratio"] = (float(a["depth"] / b["depth"])
                          if b["depth"] not in (None, 0) else None)
    both_real = (a["depth_sigma"] >= MIN_ECLIPSE_SIGMA
                 and b["depth_sigma"] >= MIN_ECLIPSE_SIGMA)
    out["both_eclipses_significant"] = bool(both_real)
    if both_real and out["difference_sigma"] >= P2_ALIAS_SIGMA:
        out["verdict"] = "eclipsing-binary-p2-alias"
    return out


def odd_even_fold(t: np.ndarray, f: np.ndarray, det: Detection,
                  half_window: float = MEASURE_WINDOW_PHASE) -> dict:
    """A04's odd-even test, re-measured over each parity's own dip support.

    Same question, same threshold, better estimator. Alternate epochs are split
    first and each parity's dip is then measured independently, so neither
    borrows the other's support. ``dilution`` reports how much the fixed-window
    median under-measured the difference — the diagnostic that made the seam
    visible in the first place, kept as evidence rather than thrown away.
    """
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    period = float(det.period_days)
    # TRANSIT-CENTRED epoch, not A04's ``floor((t - t[0]) / P)``. A04's form
    # puts the epoch boundary at whatever phase the first cadence happens to
    # land on; when that phase falls inside the transit window the SAME eclipse
    # is split across both parities and the alternation it is trying to measure
    # is averaged away. TIC 287328866 sector 3 (phase 0.895) is the live
    # example: the two epoch conventions disagree about the SIGN of the
    # odd-even difference, which is proof it was a labelling artifact — the
    # photons cannot care where the counting started. This is the same centred
    # form ``lab.a05_vetting.centroid_shift`` already uses, for the same reason.
    epoch = np.floor(t / period - float(det.phase) + 0.5).astype(int)
    odd, even = epoch % 2 == 1, epoch % 2 == 0
    dip_odd = measure_dip(t[odd], f[odd], period, float(det.phase), half_window)
    dip_even = measure_dip(t[even], f[even], period, float(det.phase), half_window)
    out = {"verdict": None, "depth_odd": dip_odd, "depth_even": dip_even,
           "difference": None, "difference_sigma": None, "dilution": None}
    if dip_odd["depth"] is None or dip_even["depth"] is None:
        out["reason"] = dip_odd.get("reason") or dip_even.get("reason")
        return out
    diff = float(dip_odd["depth"] - dip_even["depth"])
    sigma = float(np.hypot(dip_odd["sigma"], dip_even["sigma"]))
    out["difference"] = diff
    out["difference_sigma"] = float(abs(diff) / sigma) if sigma > 0 else float("inf")
    both_real = (dip_odd["depth_sigma"] >= MIN_ECLIPSE_SIGMA
                 and dip_even["depth_sigma"] >= MIN_ECLIPSE_SIGMA)
    out["both_eclipses_significant"] = bool(both_real)
    if both_real and out["difference_sigma"] >= a04.ODD_EVEN_SIGMA:
        out["verdict"] = "eclipsing-binary-odd-even"
    return out


def windowed_odd_even(t: np.ndarray, f: np.ndarray, det: Detection) -> dict:
    """A04's fixed-window median depths, reproduced here for the comparison.

    Not a gate — the reference measurement, so ``dilution`` in
    :func:`fold_gate` is a number computed in one place from one fold rather
    than two subsystems that might drift apart.
    """
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    period, ph0 = float(det.period_days), float(det.phase)
    phase = np.mod(t, period) / period
    epoch = np.floor((t - t[0]) / period).astype(int)
    in_tr = np.abs(((phase - ph0 + 0.5) % 1.0) - 0.5) < a04.VET_WINDOW_PHASE
    out_tr = ~in_tr
    if in_tr.sum() < MIN_DIP_CADENCES or out_tr.sum() < 50:
        return {"depth_odd": None, "depth_even": None, "difference": None}
    base = float(np.median(f[out_tr]))
    odd = f[in_tr & (epoch % 2 == 1)]
    even = f[in_tr & (epoch % 2 == 0)]
    if len(odd) < 5 or len(even) < 5:
        return {"depth_odd": None, "depth_even": None, "difference": None}
    d_odd = base - float(np.median(odd))
    d_even = base - float(np.median(even))
    return {"depth_odd": d_odd, "depth_even": d_even,
            "difference": float(d_odd - d_even)}


def fold_gate(t: np.ndarray, f: np.ndarray, det: Detection) -> dict:
    """Both fold gates, one verdict, full evidence.

    Order matters: the P/2 alias is checked FIRST, because when it fires the
    odd-even difference at the detected period is a *consequence* of the same
    geometry and reporting both as independent findings would double-count one
    piece of evidence. The odd-even re-measurement is still computed and
    reported either way — it is the number that shows the estimator working.

    Returns ``verdict: None`` when neither fires, which means only that these
    two gates found nothing: it is not a promotion, and nothing downstream may
    read it as one.
    """
    p2 = p2_fold(t, f, det)
    oe = odd_even_fold(t, f, det)
    ref = windowed_odd_even(t, f, det)
    dilution = None
    if (ref.get("difference") not in (None, 0)
            and oe.get("difference") is not None):
        dilution = float(oe["difference"] / ref["difference"])
    verdict = p2.get("verdict") or oe.get("verdict")
    return {"verdict": verdict, "p2_fold": p2, "odd_even_fold": oe,
            "windowed_reference": ref, "dilution": dilution}


def combine_p2_folds(folds, min_sectors: int = 2) -> dict:
    """Inverse-variance combination of the same star's 2P depth difference.

    The hunt grades one sector at a time and never looks at a star twice, which
    means a signal that is 3σ in each of four sectors is graded four times as
    "not significant" instead of once as 6σ. TIC 287328866 is the live case:
    the doubled fold reads +0.00258 ± 0.00041 (6.3σ) in sector 2 and
    +0.00164 ± 0.00047 (3.5σ) in sector 3. Sector 3 alone does not clear the
    bar. The two together are not close to the bar.

    Combines only the DIFFERENCE, not the depths: eclipse depth is a property of
    the star and the aperture (so it is comparable across sectors), but the
    aperture is re-located per sector and the crowding differs, whereas the
    difference is the quantity the verdict actually rests on.

    It combines ``signed_difference`` — the PHASE-anchored quantity — and not
    ``depth_difference``, which ``p2_fold`` sorts so that the deeper eclipse is
    always A and the number is therefore always positive. Combining that
    magnitude was wrong twice over (VET-F2): ``sign_consistent`` tested a sign
    that could not vary, so the guard could never fail; and averaging k
    folded-normal ``|noise|`` draws biases the mean by about
    ``0.8 * sigma``, so the combined significance grew like ``sqrt(k)`` out of
    nothing. Measured on a REAL PLANET — equal depths at both 2P slots, the
    difference pure noise — that reached 5.89 sigma at k=40 and fired this
    verdict. CVZ targets have that many sectors, so the gate built to refute
    eclipsing binaries would have refuted a planet, with a 40-sector receipt
    behind it.

    With the signed quantity the noise is zero-mean, the combination is
    unbiased at any k, and ``sign_consistent`` becomes a real test: a real
    primary/secondary alternation puts the same eclipse slot on top in every
    sector; noise splits. Note the failure direction — if a sector's detection
    lands on the other epoch parity, its slots swap and the sign flips, which
    makes ``sign_consistent`` False and REFUSES to refute. That is the safe
    way round for a gate whose job is to kill candidates.

    ``min_sectors`` exists so a single-sector call cannot quietly become a
    "combined" result with a different threshold than the per-sector one.
    """
    usable = [d for d in folds
              if d and d.get("difference_sigma") is not None
              and d.get("both_eclipses_significant")
              # An unsigned row cannot be combined: that is the vacuous path,
              # and it is refused rather than silently re-entered.
              and d.get("signed_difference") is not None
              and d.get("eclipse_a", {}).get("sigma")]
    out = {"verdict": None, "n_sectors": len(usable),
           "difference": None, "sigma": None, "difference_sigma": None,
           "sign_consistent": None, "per_sector_sigma": [
               float(d["difference_sigma"]) for d in usable],
           "deeper_phases": [d.get("deeper_phase") for d in usable]}
    if len(usable) < min_sectors:
        out["reason"] = "insufficient-sectors"
        return out
    diffs = np.array([float(d["signed_difference"]) for d in usable])
    sigmas = np.array([float(np.hypot(d["eclipse_a"]["sigma"],
                                      d["eclipse_b"]["sigma"])) for d in usable])
    if np.any(sigmas <= 0):
        out["reason"] = "degenerate-sigma"
        return out
    w = 1.0 / sigmas ** 2
    combined = float(np.sum(w * diffs) / np.sum(w))
    sigma = float(1.0 / np.sqrt(np.sum(w)))
    out["difference"] = combined
    out["sigma"] = sigma
    out["difference_sigma"] = float(combined / sigma)
    out["sign_consistent"] = bool(np.all(diffs > 0) or np.all(diffs < 0))
    # The magnitude decides, the sign gates: a consistent alternation is
    # evidence whichever slot is on top, but an inconsistent one is noise.
    if (out["sign_consistent"]
            and abs(out["difference_sigma"]) >= P2_ALIAS_SIGMA):
        out["verdict"] = "eclipsing-binary-p2-alias"
    return out
