"""A05 vetting — prewhitening and blend gates for the survey-grade hunt.

A04's vetting interrogates the FOLD: odd-even depths, secondary eclipses,
grid-edge railing, and a harmonic-alias heuristic that asks whether a box fit at
P/n keeps the dip. That last gate exists because the 2026-08-14 pilot's one
uncatalogued "planet-candidate", TIC 140940493, was a δ Scuti-type pulsator at
8.04 cycles/day aliased onto the 5th subharmonic of its 0.6222 d detection. The
fold heuristic caught it — but only by inference from box depths. This module
replaces the inference with a **direct spectral measurement**: compute the
star's amplitude spectrum, extract its coherent pulsation frequencies by
prewhitening, and grade any detection commensurate with a measured pulsation as
'stellar-pulsation' with the frequency itself as evidence.

### Why an explicit sin/cos least-squares, not an FFT

TESS light curves have gaps (the downlink gap bisects every sector) and
quality-masked cadences, so the timestamps are not uniform. An FFT of the gappy
series convolves every real peak with the window function; a least-squares fit
of ``a·sin(2πνt) + b·cos(2πνt)`` on the TRUE timestamps is immune to that — it
is the Lomb-Scargle idea in its plainest form, and for near-uniform cadence the
two agree while the least-squares form stays honest through the gaps.

### Why prewhitening must not eat transits

A transit is periodic too: a box at period P carries a Fourier comb at k/P whose
low harmonics can tower over the noise floor of the amplitude spectrum. A naive
"subtract the biggest peak" loop would happily shave a planet's harmonics one by
one and hand the survey a shallower transit. The physical difference is SHAPE:
a coherent pulsation is a sinusoid *everywhere in the light curve*, while a
transit concentrates its power in the few percent of cadences that sit in the
dips. So every peak must EARN its subtraction through a robust re-fit: clip the
outlier cadences and fit again. A pulsation keeps its amplitude (clipping a
sinusoid's tails is harmless); a transit-comb peak collapses, because out of
transit there is nothing at that frequency to fit. Peaks that fail the retention
test stop the loop instead of being subtracted.

### Blend gates from data already on disk

The pixels never lie about WHERE the light went missing. Every SPOC light-curve
file already carries flux-weighted centroids (MOM_CENTR1/2), the pointing-model
corrections (POS_CORR1/2), and the aperture crowding metrics (CROWDSAP,
FLFRCSAP). A transit on the target does not move the centroid measurably; an
eclipse on a blended neighbour drags the in-transit centroid toward everything
that is NOT eclipsing. ``centroid_shift`` measures the in-minus-out centroid
per event with a bootstrap-over-events error, so slow pointing drifts cancel
locally and the error bar is set by how repeatable the shift is across events —
not by an assumed noise model. ``contamination`` divides the observed depth by
CROWDSAP to report what the depth would be if all aperture flux belonged to the
target; both depths are REPORTED, neither is graded, because the correction is
a catalog-model quantity, not a measurement this pipeline made.

No literature numbers enter any graded or reported field: pulsation frequencies
are measured from the flux, centroids and crowding come from the same FITS file
as the flux itself.
"""
from __future__ import annotations

import numpy as np

from . import a01, a04
from .a04 import Detection

#: Frequency band of the amplitude spectrum, cycles/day. The floor sits above
#: the transit-search band (P >= 0.5 d --> f <= 2 c/d and its first harmonics),
#: so orbital-scale power never enters the pulsation hunt; the ceiling is the
#: Nyquist frequency of 2-minute cadence (1 / (2 * 120 s) = 360 c/d).
F_LO_CPD = 4.0
F_HI_CPD = 360.0

#: Grid density: samples per Rayleigh resolution element (1/baseline). Two per
#: element resolves every peak the 27 d baseline can separate; the fine-scan
#: refinement below recovers the sub-grid frequency before subtraction.
OVERSAMPLE = 2

#: Near the Nyquist frequency of an (almost) uniform cadence the sin and cos
#: columns become degenerate and the 2x2 normal equations lose rank; a fitted
#: "amplitude" there is division by a vanishing determinant, not a measurement.
#: Grid points whose determinant falls below this fraction of its well-posed
#: value (N/2)^2 report zero amplitude instead of garbage. 1e-2 zeroes a
#: ~0.001 c/d sliver at Nyquist on perfectly uniform cadence (where a 3 ppm
#: noise amplitude was observed inflating to 80 ppm) and nothing elsewhere.
DET_MIN_FRAC = 1e-2

#: A peak must clear this multiple of the LOCAL spectrum level (the mean
#: amplitude in a window around the peak — Breger's classic SNR >= 4). Local,
#: not global: a δ Scuti forest raises its own neighbourhood and a global floor
#: would either drown real modes or bless noise elsewhere. Mean, not median:
#: noise amplitudes are Rayleigh-distributed with mean 1.25 sigma_a, so 4x the
#: mean is 5 sigma_a — above the ~4.4 sigma_a look-elsewhere extreme of a
#: 19k-frequency band, where 4x the (smaller) median was observed blessing the
#: tallest noise spike of a pure-noise spectrum as a "component".
PREWHITEN_SNR = 4.0

#: Half-width of the local-level window, cycles/day.
LOCAL_WINDOW_CPD = 5.0

#: Rayleigh elements excluded around the peak itself when estimating the local
#: level — the peak must not vouch for its own significance.
LOCAL_EXCLUDE_RAYLEIGH = 3.0

#: Maximum components extracted per star. Eight covers every multi-mode
#: pulsator the pilot met; an unbounded loop on a pathological star is a hang.
PREWHITEN_MAX_COMPONENTS = 8

#: Robust re-fit: cadences beyond this many MAD-sigma of the residual are
#: clipped before the fit that decides subtraction.
ROBUST_CLIP_SIGMA = 3.0
ROBUST_CLIP_ITERATIONS = 3

#: A peak is only subtracted if its robust amplitude retains this fraction of
#: the raw least-squares amplitude. A coherent sinusoid retains ~100 %; a
#: transit-comb peak collapses once the in-transit cadences are clipped,
#: because out of transit there is nothing at that frequency to fit.
ROBUST_RETENTION = 0.5

#: Fine-scan points across +/- one grid step around the argmax bin. Subtracting
#: at the raw grid frequency can leave tens of percent of the amplitude behind
#: (a half-bin error drifts ~pi/2 in phase over the baseline); the fine scan
#: pins the frequency to a small fraction of a Rayleigh element first.
FREQ_REFINE_POINTS = 25

#: A detection is 'stellar-pulsation' when its period matches n/f_pulsation for
#: n = 1..PULSATION_MAX_HARMONIC within this fractional tolerance. Six matches
#: the reach of A04's fold heuristic; the tolerance matches A04's recovery
#: tolerance so the two vocabularies agree about what "the same period" means.
PULSATION_MAX_HARMONIC = 6
PULSATION_PERIOD_TOL_FRAC = 0.01

#: Centroid gate: in-minus-out shift significance (2D, bootstrap-over-events)
#: above which the shift is judged REAL. Significance alone is not the verdict —
#: see CENTROID_MIN_OFFSET_PX.
CENTROID_SIGMA = 3.0

#: The verdict additionally requires the IMPLIED OFFSET of the eclipsed source,
#: ``shift / depth`` (pixels), to exceed this. A moment centroid shifts by
#: ``depth x (distance to the eclipsed star)``, so even a transit that really is
#: on the target moves the centroid by depth times the flux-weighted offset of
#: whatever else is in the aperture — WASP-18 itself shows a repeatable 1.4e-4 px
#: shift at 4.4 sigma that implies a source offset of just 0.014 px, i.e. the
#: target. A bare significance gate would call every bright, slightly-crowded
#: planet host a blend; requiring the implied source position to sit a half
#: pixel (10.5 arcsec) off target is what actually separates "the eclipse is on
#: a neighbour" from "the aperture contains neighbours".
CENTROID_MIN_OFFSET_PX = 0.5
CENTROID_BOOTSTRAP = 256
CENTROID_SEED = 20260814
#: Fewer events than this and the bootstrap has nothing to resample — the gate
#: reports None rather than a verdict on an unmeasurable quantity.
CENTROID_MIN_EVENTS = 3
#: Local out-of-transit comparison window, in units of the vetting phase window.
#: Comparing each event to its own neighbourhood cancels slow centroid drifts
#: that survive the POS_CORR pointing model.
CENTROID_OUT_WINDOW_FACTOR = 3.0

#: CROWDSAP below this adds a 'crowded' flag: less than 80 % of the aperture
#: flux belongs to the target, so the observed depth is diluted by more than a
#: quarter and the corrected depth is the number a follow-up should budget for.
CROWDSAP_MIN = 0.8


# ------------------------------------------------------------------ spectrum ---

def amplitude_spectrum(t: np.ndarray, f: np.ndarray,
                       f_lo: float = F_LO_CPD, f_hi: float = F_HI_CPD,
                       oversample: int = OVERSAMPLE) -> tuple[np.ndarray, np.ndarray]:
    """Sinusoid amplitude vs frequency by explicit least squares on true times.

    At each trial frequency the model ``a·sin(2πνt) + b·cos(2πνt)`` is fit to
    the mean-subtracted flux and the reported amplitude is ``√(a²+b²)`` — the
    physical semi-amplitude a pulsation of that frequency would need to produce
    the data. The 2x2 normal equations are assembled for the whole grid at once
    from two complex sums,

        Σ E·y  with E = exp(2πiνt)   (the data-side moments), and
        Σ E²                          (the design-side moments),

    because ``Σcos² = (N + Re ΣE²)/2``, ``Σsin² = (N − Re ΣE²)/2`` and
    ``Σ sin·cos = Im ΣE² / 2``.

    Materialising ``E`` for the whole grid is O(K·N) transcendentals — ~10 s on
    a 19k-cadence sector. Instead the grid index is factored ``k = q·B + r``, so
    ``E(ν_k) = base · (w^B)^q · w^r`` with ``w = exp(2πi·δν·t)``: two small
    cumulative-product tables (B and K/B rows) replace every per-frequency
    exponential, and both moment sums become ONE complex matrix product each —
    ``Σ_j A_j W2[q]_j W1[r]_j = ((W2·A) @ W1ᵀ)[q,r]`` — which BLAS executes in
    a fraction of a second. Same normal equations, exact same numbers.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(f, dtype=float)
    if len(t) != len(y) or len(t) < 16:
        raise ValueError("amplitude_spectrum needs matched arrays of >=16 cadences")
    if not (0 < f_lo < f_hi):
        raise ValueError("frequency band must satisfy 0 < f_lo < f_hi")
    y = y - float(np.mean(y))
    tt = t - float(t.min())
    baseline = float(tt.max())
    if baseline <= 0:
        raise ValueError("zero baseline")
    step = 1.0 / baseline / max(int(oversample), 1)
    freqs = np.arange(f_lo, f_hi + 0.5 * step, step)
    k_total = len(freqs)
    n = float(len(tt))

    b_cols = max(1, int(np.ceil(np.sqrt(k_total))))
    q_rows = int(np.ceil(k_total / b_cols))
    w = np.exp(2j * np.pi * step * tt)                       # one grid step
    w1 = np.cumprod(np.broadcast_to(w, (b_cols, len(tt))), axis=0)
    w1 = np.vstack([np.ones_like(w)[None, :], w1[:-1]])      # w^0 .. w^(B-1)
    wb = w1[-1] * w                                          # w^B
    w2 = np.cumprod(np.broadcast_to(wb, (q_rows, len(tt))), axis=0)
    w2 = np.vstack([np.ones_like(w)[None, :], w2[:-1]])      # (w^B)^0 .. ^(Q-1)
    base = np.exp(2j * np.pi * float(freqs[0]) * tt)

    ey = ((w2 * (base * y)[None, :]) @ w1.T).ravel()[:k_total]      # Σ E y
    base2, w1sq, w2sq = base * base, w1 * w1, w2 * w2
    e2 = ((w2sq * base2[None, :]) @ w1sq.T).ravel()[:k_total]       # Σ E²

    sss = 0.5 * (n - e2.real)
    scc = 0.5 * (n + e2.real)
    ssc = 0.5 * e2.imag
    ssy = ey.imag
    scy = ey.real
    det = sss * scc - ssc * ssc
    ok = det > DET_MIN_FRAC * (0.5 * n) ** 2
    det = np.where(ok, det, 1.0)
    a = (scc * ssy - ssc * scy) / det
    b = (sss * scy - ssc * ssy) / det
    return freqs, np.where(ok, np.hypot(a, b), 0.0)


def _fit_sinusoid(t: np.ndarray, y: np.ndarray, nu: float) -> tuple[float, float, float]:
    """Least-squares (a, b, c) of a·sin + b·cos + c at fixed frequency ``nu``."""
    w = 2 * np.pi * nu * t
    design = np.column_stack([np.sin(w), np.cos(w), np.ones(len(t))])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(coef[0]), float(coef[1]), float(coef[2])


def _robust_sinusoid(t: np.ndarray, y: np.ndarray, nu: float) -> tuple[float, float, float]:
    """The fit that decides subtraction: iteratively clip outlier cadences.

    A transit dip is a gross outlier against a sinusoid model (a 1 % dip vs
    ~0.03 % noise is >30 MAD-sigma), so the clip removes in-transit cadences and
    the re-fit measures only what the star does everywhere else. A genuine
    pulsation loses almost nothing to the clip and keeps its amplitude.
    """
    keep = np.ones(len(t), dtype=bool)
    a = b = c = 0.0
    for _ in range(ROBUST_CLIP_ITERATIONS):
        a, b, c = _fit_sinusoid(t[keep], y[keep], nu)
        w = 2 * np.pi * nu * t
        resid = y - (a * np.sin(w) + b * np.cos(w) + c)
        med = float(np.median(resid[keep]))
        mad = float(np.median(np.abs(resid[keep] - med)))
        sigma = max(1.4826 * mad, 1e-12)
        keep = np.abs(resid - med) <= ROBUST_CLIP_SIGMA * sigma
        if keep.sum() < 16:
            break
    return a, b, c


def _refine_frequency(t: np.ndarray, y: np.ndarray, nu: float,
                      step: float) -> float:
    """Two-stage fine least-squares scan around the argmax bin.

    Subtracting at the raw grid frequency is not good enough: a half-bin error
    drifts ~pi/2 in phase across the baseline and leaves tens of percent of the
    amplitude behind as a spurious neighbouring "component". Two zoom stages
    pin the frequency to ~1e-4 of a cycle/day, below the leakage noise floor.
    """
    best_nu = float(nu)
    half_width = float(step)
    for _ in range(2):
        grid = np.linspace(best_nu - half_width, best_nu + half_width,
                           FREQ_REFINE_POINTS)
        best_amp = -1.0
        for trial in grid:
            if trial <= 0:
                continue
            a, b, _ = _fit_sinusoid(t, y, float(trial))
            amp = float(np.hypot(a, b))
            if amp > best_amp:
                best_nu, best_amp = float(trial), amp
        half_width = 2.0 * half_width / (FREQ_REFINE_POINTS - 1)
    return best_nu


def prewhiten(t: np.ndarray, f: np.ndarray,
              max_components: int = PREWHITEN_MAX_COMPONENTS,
              f_lo: float = F_LO_CPD, f_hi: float = F_HI_CPD,
              ) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Extract coherent pulsation components; return (whitened flux, components).

    Loop: amplitude spectrum -> strongest peak -> does it clear PREWHITEN_SNR of
    the LOCAL spectrum level? -> refine its frequency below the grid -> robust
    fit -> does the clipped fit retain ROBUST_RETENTION of the raw amplitude?
    Only then is the sinusoid subtracted (evaluated on ALL cadences — a real
    pulsation continues through the transits) and recorded as ``(freq_cpd,
    amplitude)``. A peak failing either test ends the loop: whatever tops the
    spectrum at that point is not a coherent sinusoid, and subtracting
    non-sinusoids is how a prewhitener eats planets.
    """
    t = np.asarray(t, dtype=float)
    resid = np.asarray(f, dtype=float).copy()
    baseline = float(t.max() - t.min())
    if baseline <= 0:
        return resid, []
    rayleigh = 1.0 / baseline
    components: list[tuple[float, float]] = []
    for _ in range(max_components):
        freqs, amps = amplitude_spectrum(t, resid, f_lo=f_lo, f_hi=f_hi)
        j = int(np.argmax(amps))
        peak_nu, peak_amp = float(freqs[j]), float(amps[j])
        near = np.abs(freqs - peak_nu) <= LOCAL_WINDOW_CPD
        near &= np.abs(freqs - peak_nu) > LOCAL_EXCLUDE_RAYLEIGH * rayleigh
        local = float(np.mean(amps[near])) if near.any() else float(np.mean(amps))
        if local <= 0 or peak_amp < PREWHITEN_SNR * local:
            break
        step = float(freqs[1] - freqs[0]) if len(freqs) > 1 else rayleigh
        nu = _refine_frequency(t, resid, peak_nu, step)
        a_raw, b_raw, _ = _fit_sinusoid(t, resid, nu)
        amp_raw = float(np.hypot(a_raw, b_raw))
        a, b, _ = _robust_sinusoid(t, resid, nu)
        amp_rob = float(np.hypot(a, b))
        if amp_raw <= 0 or amp_rob < ROBUST_RETENTION * amp_raw:
            break
        w = 2 * np.pi * nu * t
        resid = resid - (a * np.sin(w) + b * np.cos(w))
        components.append((float(nu), amp_rob))
    return resid, components


# ------------------------------------------------------------------- vetting ---

def extended_vet(t: np.ndarray, f: np.ndarray, det: Detection,
                 components=(), p_lo: float = a04.P_LO,
                 p_hi: float = a04.P_HI) -> dict:
    """A04's vetting, upgraded with the measured pulsation spectrum.

    Any detection whose period sits within PULSATION_PERIOD_TOL_FRAC of
    ``n / f_pulsation`` for n = 1..PULSATION_MAX_HARMONIC of a recorded
    component auto-grades 'stellar-pulsation' with the measured frequency as
    evidence. This GENERALISES A04's harmonic-alias fold heuristic: the fold
    test infers a subharmonic from box depths; this states the pulsation
    frequency the star actually has, so the disposition carries a number a
    reader can verify against the amplitude spectrum. Anything not commensurate
    with a component falls through to :func:`lab.a04.vet_candidate` unchanged —
    ``f`` should therefore be the PREWHITENED flux, so the fold-based gates run
    on a light curve whose coherent oscillations are already removed.

    TIC-specific knowledge never enters: the gate compares the detection only
    against frequencies measured from this star's own flux.
    """
    for nu, amp in components:
        if nu <= 0:
            continue
        for n_harm in range(1, PULSATION_MAX_HARMONIC + 1):
            p_puls = n_harm / nu
            if abs(det.period_days / p_puls - 1.0) <= PULSATION_PERIOD_TOL_FRAC:
                return {
                    "verdict": "stellar-pulsation",
                    "pulsation_cpd": float(nu),
                    "pulsation_amplitude": float(amp),
                    "harmonic_n": int(n_harm),
                    "pulsation_period_days": float(p_puls),
                }
    return a04.vet_candidate(t, f, det, p_lo, p_hi)


# --------------------------------------------------------------- blend gates ---

def normalise_with_ancillary(curve: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """A01's quality mask, applied identically to flux AND centroids.

    Returns ``(t, normalised flux, aux)`` where ``aux`` carries the masked
    ancillary columns, the crowding keywords, and convenience ``cx``/``cy``
    centroids with the POS_CORR pointing model subtracted when it is present —
    the pointing model is exactly the slow drift the centroid gate must not
    mistake for astrophysics. Missing columns and keywords stay ``None``.
    """
    t_all = curve["TIME"]
    f_all = curve["PDCSAP_FLUX"]
    q = curve["QUALITY"]
    good = (q == 0) & np.isfinite(t_all) & np.isfinite(f_all) & (f_all > 0)
    t, f = t_all[good], f_all[good]
    if len(t) < 100:
        raise ValueError("too few quality-zero cadences")
    aux: dict = {}
    for name in a01.ANCILLARY_COLUMNS:
        col = curve.get(name)
        aux[name] = np.asarray(col, dtype=float)[good] if col is not None else None
    for key in a01.ANCILLARY_KEYWORDS:
        aux[key] = curve.get(key)
    for axis, mom, pos in (("cx", "MOM_CENTR1", "POS_CORR1"),
                           ("cy", "MOM_CENTR2", "POS_CORR2")):
        if aux[mom] is None:
            aux[axis] = None
        elif aux[pos] is not None:
            aux[axis] = aux[mom] - aux[pos]
        else:
            aux[axis] = aux[mom]
    return t, f / np.median(f), aux


def centroid_shift(t: np.ndarray, cx, cy, det: Detection,
                   n_boot: int = CENTROID_BOOTSTRAP,
                   seed: int = CENTROID_SEED) -> dict:
    """In-transit minus out-of-transit centroid, with a bootstrap-over-events error.

    Per event, the in-transit centroid is compared to the out-of-transit
    centroid of the SAME event's neighbourhood (within CENTROID_OUT_WINDOW_FACTOR
    vetting windows), so anything drifting slower than one orbit — differential
    velocity aberration, focus changes, residual pointing model — cancels before
    it can masquerade as a shift. The error bar comes from resampling whole
    events with replacement: it measures how repeatable the shift is across
    independent transits, which is the only sense in which a shift is evidence.

    The verdict needs BOTH tests. The 2D significance ``√((dx/σx)² + (dy/σy)²)``
    above CENTROID_SIGMA establishes the shift is real; the implied offset of
    the eclipsed source, ``shift / depth``, above CENTROID_MIN_OFFSET_PX
    establishes it points at a NEIGHBOUR rather than at the target's own
    slightly-contaminated aperture (see the constant's comment — WASP-18's real
    on-target transit is 4.4 sigma significant and 0.014 px implied-offset).
    Only then is the row 'centroid-shift': the lost light was not centred on
    the target.

    ``cx``/``cy`` of ``None`` (columns absent from the file) disables the gate
    — verdict ``None`` with a reason, never a judgement without data.
    """
    out = {"verdict": None, "n_events": 0, "dx": None, "dy": None,
           "shift": None, "shift_sigma": None, "implied_offset_px": None}
    if cx is None or cy is None:
        out["reason"] = "no-centroid-data"
        return out
    t = np.asarray(t, dtype=float)
    cx = np.asarray(cx, dtype=float)
    cy = np.asarray(cy, dtype=float)
    period, ph0 = det.period_days, det.phase
    phase = np.mod(t, period) / period
    dist = np.abs(((phase - ph0 + 0.5) % 1.0) - 0.5)
    in_tr = dist < a04.VET_WINDOW_PHASE
    near_out = (~in_tr) & (dist < CENTROID_OUT_WINDOW_FACTOR * a04.VET_WINDOW_PHASE)
    # Event index centred on the transit: cadences within half a period of one
    # predicted centre share an integer, so no event straddles a boundary.
    epoch = np.floor(t / period - ph0 + 0.5).astype(int)
    finite = np.isfinite(cx) & np.isfinite(cy)

    dxs, dys = [], []
    for e in np.unique(epoch[in_tr]):
        sel_in = in_tr & (epoch == e) & finite
        sel_out = near_out & (epoch == e) & finite
        if sel_in.sum() < 5 or sel_out.sum() < 5:
            continue
        dxs.append(float(np.mean(cx[sel_in]) - np.mean(cx[sel_out])))
        dys.append(float(np.mean(cy[sel_in]) - np.mean(cy[sel_out])))
    n_events = len(dxs)
    out["n_events"] = n_events
    if n_events < CENTROID_MIN_EVENTS:
        out["reason"] = "insufficient-events"
        return out
    dx_arr, dy_arr = np.asarray(dxs), np.asarray(dys)
    dx, dy = float(np.mean(dx_arr)), float(np.mean(dy_arr))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_events, size=(n_boot, n_events))
    bx = dx_arr[idx].mean(axis=1)
    by = dy_arr[idx].mean(axis=1)
    sx = float(np.std(bx, ddof=1))
    sy = float(np.std(by, ddof=1))
    sig = float(np.hypot(dx / sx if sx > 0 else 0.0,
                         dy / sy if sy > 0 else 0.0))
    shift = float(np.hypot(dx, dy))
    implied = shift / det.depth if det.depth > 0 else float("inf")
    out.update({"dx": dx, "dy": dy, "sigma_x": sx, "sigma_y": sy,
                "shift": shift, "shift_sigma": sig,
                "implied_offset_px": float(implied)})
    if sig > CENTROID_SIGMA and implied > CENTROID_MIN_OFFSET_PX:
        out["verdict"] = "centroid-shift"
    return out


def contamination(depth_observed: float, crowdsap) -> dict:
    """Crowding bookkeeping: what would the depth be on the target alone?

    CROWDSAP is the fraction of aperture flux belonging to the target, so an
    eclipse diluted by neighbours has true depth ``depth / CROWDSAP`` if — and
    only if — the target is the eclipsing star. Both depths are REPORTED and
    neither is graded: the correction assumes exactly the thing the centroid
    gate exists to test. CROWDSAP below CROWDSAP_MIN adds a 'crowded' flag so a
    reader knows a quarter or more of the light is not the target's. A missing
    keyword degrades to ``None`` and no flag fires.
    """
    out = {"depth_observed": float(depth_observed),
           "crowdsap": None, "depth_corrected": None, "crowded": False}
    if crowdsap is None:
        return out
    crowdsap = float(crowdsap)
    if not (0.0 < crowdsap <= 1.0):
        return out
    out["crowdsap"] = crowdsap
    out["depth_corrected"] = float(depth_observed) / crowdsap
    out["crowded"] = bool(crowdsap < CROWDSAP_MIN)
    return out
