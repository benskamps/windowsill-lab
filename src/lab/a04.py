"""A04 — a blind box-least-squares transit search across a TESS sector.

A01 recovered a planet the pipeline was *told about*: it searched a narrow window
around WASP-18 b's known period. A04 removes that: the search is handed a set of
light curves with no labels, no periods, and no hint about which ones host
anything, and has to surface the planets itself.

### What changes when the search goes blind

Three things A01 could take for granted stop being safe, and each is a real
design constraint rather than a tuning knob:

1. **The period is unknown**, so the grid spans 0.5-15 d instead of 0.85-1.05 d.
2. **Stellar variability swamps a 1 % transit.** A01's target is a bright star
   with an enormous signal; a general target needs the light curve detrended by a
   running median first, on a window several times the transit duration so it
   removes the star without eating the planet.
3. **Raw depth is not comparable across stars.** A01 ranked by box depth, which is
   fine for one known target and useless for a survey — a noisy or variable star
   wins on depth while hosting nothing. The blind ranker is the **SDE** (signal
   detection efficiency): how far the best period stands above the spread of that
   target's *own* periodogram. Dimensionless, self-normalising, comparable.

### The two controls, and why the threshold is measured rather than chosen

Finding known planets proves the search can detect a transit. It does not prove
the search only reports real ones, and it says nothing about what an SDE *means*.
So both directions are graded, and the detection threshold falls out of them
instead of being picked:

* **Positive (the class-6 gate).** Synthetic box transits of known period and
  depth are injected into a real light curve and must be recovered blind. Without
  this, a detection is a number with no demonstrated sensitivity behind it — the
  failure mode that produced A03's phantom chirp masses and K03's four wrong
  exponents.
* **Negative.** The same search runs on targets with no known planet. Their SDE
  distribution *is* the false-alarm floor. A threshold is only meaningful if it
  sits in a measured gap above that floor and below the recoveries.

Nothing from the exoplanet catalog enters the search. Published periods are read
only at grading time, to ask whether what the search found on its own is the
planet that is really there.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from dataclasses import dataclass, field

import numpy as np

from . import a01

#: Blind period grid. Wide enough for hot Jupiters through warm sub-Neptunes; a
#: single 27-day sector cannot support much beyond ~15 d (fewer than two transits).
P_LO, P_HI = 0.5, 15.0

#: A period is only confirmable if several transits fall inside the baseline.
#: A 27-day sector cannot support a 14-day period: you get under two events, no
#: odd-even test is possible, and the "detection" is unfalsifiable. The search
#: caps its grid at baseline/MIN_TRANSITS rather than trusting P_HI blindly.
MIN_TRANSITS = 3
N_PERIODS = 3000
BINS = 200

#: Detrending window. Must exceed the transit duration by several times or the
#: running median absorbs the signal it is meant to expose.
DETREND_WINDOW_DAYS = 0.5

#: Injections for the positive control: depth in fractional flux, period in days.
INJECTIONS = ((0.010, 3.7), (0.004, 2.3), (0.002, 5.1))
INJECT_DURATION_DAYS = 2.5 / 24

#: A recovery counts only if the blind period lands this close to the published one.
PERIOD_TOL_FRAC = 0.01

#: Detection threshold. NOT a free parameter — the run measures the false-alarm
#: floor and asserts this sits above it, refusing if the gap closes.
SDE_THRESHOLD = 8.0

#: Sector 2 hosts both recovery targets with SPOC light curves.
DEFAULT_SECTOR = 2

#: Known planets used ONLY at grading time. The search never sees these.
RECOVERY_TARGETS = {
    "100100827": {"name": "WASP-18 b", "period_days": 0.94145223},
    "201248411": {"name": "HIP 65 A b", "period_days": 0.98097340},
}


class A04Error(RuntimeError):
    pass


def detrend(t: np.ndarray, f: np.ndarray,
            window_days: float = DETREND_WINDOW_DAYS) -> tuple[np.ndarray, np.ndarray]:
    """Divide out a running median.

    Cadence is uniform, so this uses a fixed-width sliding window rather than a
    time-radius scan — the O(N²) form took minutes on a 19k-cadence sector.
    """
    order = np.argsort(t)
    t, f = t[order], f[order]
    if len(t) < 10:
        return t, f
    cadence = float(np.median(np.diff(t)))
    if not np.isfinite(cadence) or cadence <= 0:
        return t, f / np.median(f)
    width = max(11, int(round(window_days / cadence)) | 1)      # odd
    if width >= len(f):
        return t, f / np.median(f)
    pad = width // 2
    padded = np.r_[f[:pad][::-1], f, f[-pad:][::-1]]
    trend = np.median(np.lib.stride_tricks.sliding_window_view(padded, width), axis=-1)
    trend[trend <= 0] = 1.0
    return t, f / trend


def bls_power(t: np.ndarray, f: np.ndarray, period: float,
              bins: int = BINS, min_width: int = 3,
              max_frac: float = 0.15) -> tuple[float, float, float]:
    """Box power at one trial period — best ``depth·√n_in`` over box widths."""
    phase = np.mod(t, period) / period
    idx = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(idx, weights=f, minlength=bins)
    counts = np.bincount(idx, minlength=bins)
    total, n_total = sums.sum(), counts.sum()
    if n_total == 0:
        return 0.0, 0.0, 0.0
    # Doubled arrays so a box may straddle phase 0 — a transit at the wrap point
    # is not a special case, and missing it would bias the survey toward periods
    # whose alignment happens to be lucky.
    cs = np.r_[0.0, np.cumsum(np.r_[sums, sums])]
    cc = np.r_[0.0, np.cumsum(np.r_[counts, counts])]
    best = (0.0, 0.0, 0.0)
    for width in range(min_width, max(min_width + 1, int(bins * max_frac))):
        s_in = cs[width:width + bins] - cs[:bins]
        n_in = cc[width:width + bins] - cc[:bins]
        ok = n_in > 5
        if not ok.any():
            continue
        s_out, n_out = total - s_in, n_total - n_in
        with np.errstate(invalid="ignore", divide="ignore"):
            mu_in = np.where(ok, s_in / np.maximum(n_in, 1), 1.0)
            mu_out = np.where(ok & (n_out > 0), s_out / np.maximum(n_out, 1), 1.0)
            depth = mu_out - mu_in
            power = np.where(ok & (depth > 0), depth * np.sqrt(np.maximum(n_in, 0)), 0.0)
        j = int(np.argmax(power))
        if power[j] > best[0]:
            best = (float(power[j]), float(depth[j]), float(((j + width / 2) / bins) % 1.0))
    return best


#: An odd-even depth difference this many sigma apart means the true period is
#: 2P and the "transit" is alternating primary/secondary eclipses — an EB.
ODD_EVEN_SIGMA = 5.0
#: Standard error of a MEDIAN vs a mean on Gaussian noise: sqrt(pi/2). Every
#: depth below is read with `np.median`, so every error bar below has to pay
#: the median's efficiency cost instead of quietly reporting a mean's bar on a
#: median's number. A DIFFERENCE of two medians carries the factor on each
#: term, which is why the odd-even statistic ran sqrt(pi) = 1.77x hot until
#: 2026-08-21 (VET-F3) and the depth statistic sqrt(pi/2) = 1.25x hot — so the
#: nominal 5-sigma candidate-minting rung actually admitted true ~4-sigma
#: dips. `lab.a05_fold` fixed this for its own gates first and imports this
#: constant from here, so the repo has one convention and not two.
MEDIAN_SIGMA_FACTOR = float(np.sqrt(np.pi / 2.0))
VET_WINDOW_PHASE = 0.03


#: A best period this close to a grid edge is railed, not measured.
RAIL_TOL_FRAC = 0.002


def vet_candidate(t: np.ndarray, f: np.ndarray, det: Detection,
                  p_lo: float = P_LO, p_hi: float = P_HI) -> dict:
    """Astrophysical vetting of a detection — the step that separates a planet
    candidate from an eclipsing binary.

    A blind box search cannot tell a 1 % planet from a grazing or diluted EB at
    twice the period: fold an EB at P instead of 2P and its primary and secondary
    eclipses land on top of each other, looking like one transit. Two standard
    discriminators:

    * **odd-even depth.** Alternate epochs sample the two different eclipses, so
      an EB shows depths that differ; a planet's do not.
    * **secondary eclipse** at phase 0.5.

    This is why the survey's above-threshold hits are *vetted*, not counted. The
    first real run surfaced TIC 287328866 at SDE 9.0 and depth 1.38 %, absent
    from every TOI and confirmed-planet table — and odd-even separated it at
    11 sigma. Without this step it would have been reported as a candidate.
    """
    # Grid-edge railing first: a best period sitting ON a search bound means the
    # true period is probably OUTSIDE the range, and the fold is an alias. The
    # final run surfaced TIC 206502540 at P = 0.5000 d — exactly P_LO — with 52
    # "events" and a 20-sigma depth, which vetting would otherwise have called a
    # planet candidate in a public report.
    baseline = float(t.max() - t.min())
    hi_eff = min(p_hi, baseline / MIN_TRANSITS) if baseline > 0 else p_hi
    if (abs(det.period_days - p_lo) <= RAIL_TOL_FRAC * p_lo
            or abs(det.period_days - hi_eff) <= RAIL_TOL_FRAC * hi_eff):
        return {"verdict": "period-railed", "railed_at": det.period_days,
                "grid_lo": p_lo, "grid_hi": hi_eff}

    period, ph0 = det.period_days, det.phase
    phase = np.mod(t, period) / period
    epoch = np.floor((t - t[0]) / period).astype(int)
    in_transit = np.abs(((phase - ph0 + 0.5) % 1.0) - 0.5) < VET_WINDOW_PHASE
    out = ~in_transit
    if in_transit.sum() < 12 or out.sum() < 50:
        return {"verdict": "insufficient-coverage"}
    base = float(np.median(f[out]))
    noise = float(np.std(f[out]))
    odd, even = f[in_transit & (epoch % 2 == 1)], f[in_transit & (epoch % 2 == 0)]
    if len(odd) < 5 or len(even) < 5:
        return {"verdict": "insufficient-coverage"}
    d_odd, d_even = base - float(np.median(odd)), base - float(np.median(even))
    n_odd, n_even, n_out = len(odd), len(even), int(out.sum())

    def _median_se(*counts: int) -> float:
        """SE of a sum/difference of independent medians on Gaussian noise.

        Each term contributes (pi/2) * noise^2 / n. `base` is itself a median
        over the out-of-transit sample, so it is one of the terms — negligible
        when n_out is large, but it is not zero and it is not this function's
        job to decide that.
        """
        return float(MEDIAN_SIGMA_FACTOR * noise
                     * np.sqrt(sum(1.0 / max(n, 1) for n in counts)))

    # Difference of two medians: the factor lands on BOTH terms, so this bar
    # is sqrt(pi) wider than the mean's bar that used to stand here.
    sigma_diff = _median_se(n_odd, n_even)
    diff_sigma = abs(d_odd - d_even) / sigma_diff if sigma_diff > 0 else float("inf")

    sec = np.abs(((phase - ph0 - 0.5 + 0.5) % 1.0) - 0.5) < VET_WINDOW_PHASE
    d_sec = base - float(np.median(f[sec])) if sec.sum() > 5 else float("nan")
    # Signed, deliberately: a significant phase-locked BRIGHTENING is its own
    # verdict below, so this statistic must keep its sign.
    sigma_sec = _median_se(int(sec.sum()), n_out)
    sec_sigma = (d_sec / sigma_sec) if sec.sum() > 5 and sigma_sec > 0 else 0.0

    # "planet-candidate" has to be EARNED. A first pass blessed TIC 280095254 on
    # depths of ~1e-5 with the odd-epoch depth NEGATIVE — noise wearing a verdict.
    # Both parities must show a real, positive dip before anything is a candidate.
    # The candidate-minting statistic: the SHALLOWER parity's depth against
    # the baseline. Both are medians, so both pay the factor; the weaker
    # parity's own count sets the bar, not the pair's.
    sigma_depth = _median_se(min(n_odd, n_even), n_out)
    depth_sigma = min(d_odd, d_even) / sigma_depth if sigma_depth > 0 else 0.0
    n_events = int(np.unique(epoch[in_transit]).size)
    alias = _subharmonic_alias(t, f, period)
    if n_events < MIN_TRANSITS:
        verdict = "insufficient-coverage"
    elif alias is not None:
        # The 2026-08-14 discovery pilot's one uncatalogued "planet-candidate",
        # TIC 140940493 (SDE 8.7, P=0.6222 d, 900 ppm), was really a δ Scuti-type
        # pulsator at 8.04 cycles/day — P/5 of the detection. A periodic signal
        # BELOW the grid floor aliases onto a grid period and passes odd-even
        # (every cycle is identical), so the fold has to be interrogated: a true
        # transit at P loses its dip when folded at P/n (only every n-th fold
        # carries it), while a signal genuinely periodic at P/n keeps full depth.
        verdict = "harmonic-alias"
    elif diff_sigma >= ODD_EVEN_SIGMA:
        verdict = "eclipsing-binary-odd-even"
    elif sec_sigma >= ODD_EVEN_SIGMA:
        verdict = "eclipsing-binary-secondary"
    elif sec_sigma <= -ODD_EVEN_SIGMA:
        # Same target, second tell: the "secondary" was a 13-sigma BRIGHTENING.
        # A planet's occultation can only dim; significant phase-locked
        # brightening at 0.5 is ellipsoidal variation or pulsation. The gate
        # used to test only `sec_sigma >= +5` and let the sign slip through.
        verdict = "phased-brightening"
    elif depth_sigma < ODD_EVEN_SIGMA:
        verdict = "low-significance"
    else:
        verdict = "planet-candidate"
    out_row = {
        "verdict": verdict,
        "n_events": n_events,
        "depth_sigma": float(depth_sigma),
        "depth_odd": d_odd, "depth_even": d_even,
        "odd_even_sigma": float(diff_sigma),
        "secondary_depth": float(d_sec), "secondary_sigma": float(sec_sigma),
    }
    if alias is not None:
        out_row["alias_n"] = alias[0]
        out_row["alias_depth"] = alias[1]
    return out_row


#: A box fit at period/n must retain at least this fraction of the period-fit
#: depth to call the detection an alias of a shorter true period. The mean-based
#: BLS depth makes the discrimination exact in the clean limit: a true transit
#: at P contributes to only every n-th fold at P/n, so its box MEAN dilutes to
#: depth/n <= 0.5x, while a signal genuinely periodic at P/n keeps full depth.
ALIAS_DEPTH_FRAC = 0.7
ALIAS_MIN_SIGMA = 5.0


def _subharmonic_alias(t: np.ndarray, f: np.ndarray,
                       period: float) -> tuple[int, float] | None:
    """Is the detection at ``period`` really a signal at ``period/n``?

    Runs the same ``bls_power`` box fit at period/n for n in 2..6 and compares
    depths. Returns (n, depth_at_period_over_n) for the first n that keeps
    >= ALIAS_DEPTH_FRAC of the period-fit depth above a noise floor, else None.
    """
    _, depth_1, _ = bls_power(t, f, period)
    if depth_1 <= 0:
        return None
    cadence = float(np.median(np.diff(np.sort(t)))) if len(t) > 1 else 0.0
    # Smallest box the fit can select is 3/BINS of the fold; a depth must beat
    # ALIAS_MIN_SIGMA on that support to count as anything but noise.
    floor = ALIAS_MIN_SIGMA * float(np.std(f)) / max(
        np.sqrt(len(f) * 3.0 / BINS), 1.0)
    for n in (2, 3, 4, 5, 6):
        p = period / n
        if p <= 8 * cadence:            # fold too fine for the binned box fit
            continue
        _, depth_n, _ = bls_power(t, f, p)
        if depth_n >= ALIAS_DEPTH_FRAC * depth_1 and depth_n >= floor:
            return n, float(depth_n)
    return None


@dataclass
class Detection:
    period_days: float
    depth: float
    phase: float
    sde: float


def blind_search(t: np.ndarray, f: np.ndarray, p_lo: float = P_LO,
                 p_hi: float = P_HI, n_periods: int = N_PERIODS) -> Detection:
    """Uniform-in-FREQUENCY grid (uniform in period would over-sample long ones)."""
    if p_lo <= 0 or p_hi <= p_lo:
        raise A04Error("period range must satisfy 0 < p_lo < p_hi")
    baseline = float(t.max() - t.min())
    p_hi = min(p_hi, baseline / MIN_TRANSITS) if baseline > 0 else p_hi
    if p_hi <= p_lo:
        raise A04Error("baseline too short for the requested period range")
    freqs = np.linspace(1.0 / p_hi, 1.0 / p_lo, n_periods)
    periods = 1.0 / freqs
    power = np.empty(n_periods)
    depth = np.empty(n_periods)
    phase = np.empty(n_periods)
    for i, p in enumerate(periods):
        power[i], depth[i], phase[i] = bls_power(t, f, float(p))
    j = int(np.argmax(power))
    spread = float(power.std())
    sde = float((power[j] - np.median(power)) / spread) if spread > 0 else 0.0
    return Detection(float(periods[j]), float(depth[j]), float(phase[j]), sde)


def inject_box(t: np.ndarray, f: np.ndarray, period: float, depth: float,
               duration_days: float = INJECT_DURATION_DAYS,
               t0: float | None = None) -> np.ndarray:
    """Plant a synthetic box transit. Epoch is deliberately off-grid."""
    if t0 is None:
        t0 = t[0] + 0.37 * period
    ph = np.mod(t - t0 + 0.5 * period, period) - 0.5 * period
    out = f.copy()
    out[np.abs(ph) < duration_days / 2] *= (1.0 - depth)
    return out


def sector_targets(sector: int = DEFAULT_SECTOR, max_pages: int = 4,
                   pagesize: int = 500, deadline: float | None = None) -> list[str]:
    """Distinct TIC ids with SPOC time-series in ``sector``, paged and sorted.

    PAGE-CAPPED, and the caller must not read the result as "the sector". A real
    TESS sector holds thousands of 2-minute targets; ``max_pages x pagesize``
    bounds what one run enumerates so the survey stays a bounded job.
    """
    tics: list[str] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        rows = a01._mast("Mast.Caom.Filtered", {
            "columns": "obsid,target_name,sequence_number,provenance_name",
            "filters": [
                {"paramName": "obs_collection", "values": ["TESS"]},
                {"paramName": "dataproduct_type", "values": ["timeseries"]},
                {"paramName": "provenance_name", "values": ["SPOC"]},
                {"paramName": "sequence_number", "values": [sector]},
            ],
        }, deadline=deadline, pagesize=pagesize, page=page)
        if not rows:
            break
        for r in rows:
            name = str(r.get("target_name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                tics.append(name)
        if len(rows) < pagesize:
            break
    return sorted(tics)


def sample_targets(tics: list[str], n: int, seed: int = 2026) -> list[str]:
    """A deterministic sample, plus every recovery target present in the sector.

    Seeded by content hash rather than call order, so the same sector always
    yields the same sample regardless of how MAST paginated that day.
    """
    pool = [t for t in tics if t not in RECOVERY_TARGETS]
    # CONSISTENT HASHING, not a seed derived from the whole pool. The earlier
    # form hashed the sorted pool, so any change in what MAST returned that day
    # reshuffled the entire sample — two consecutive runs shared almost no
    # targets and the report's "deterministic sample" was false. Hashing each
    # TIC independently makes membership stable: adding or dropping pool members
    # leaves every other target's inclusion unchanged.
    def rank(tic: str) -> bytes:
        return hashlib.sha256(f"{seed}|{tic}".encode()).digest()
    chosen = sorted(pool, key=rank)[:min(n, len(pool))]
    # Recovery targets are added UNCONDITIONALLY, not gated on appearing in
    # `tics`. The sector listing is page-capped (see `sector_targets`), so it is
    # a slice of the sector rather than the sector: a first run sampled 24 of
    # 1994 enumerated targets and included ZERO known planets, leaving the survey
    # with nothing to validate against. `light_curve` returns None for a target
    # with no product in this sector, which drops any that genuinely are absent —
    # so this adds candidates, never fabricates them.
    return sorted(set(chosen) | set(RECOVERY_TARGETS))


def light_curve(tic: str, sector: int, cache_dir=None):
    """Detrended (t, flux) for one target, or None when the sector has no product."""
    cache_dir = cache_dir or a01.CACHE_DIR
    products = a01.discover_spoc_light_curves(tic, max_sectors=4)
    product = next((p for p in products if p.get("sector") == sector), None)
    if product is None:
        return None
    blob, _ = a01._download_product(product, cache_dir)
    t, f = a01._normalise(a01.read_tess_light_curve(blob))
    return detrend(t, f)


def _tap(query: str, deadline: float | None = None) -> list[dict]:
    """One NASA Exoplanet Archive TAP query, JSON rows. Reuses A01's HTTP path."""
    url = a01.NASA_TAP + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    return json.loads(a01._request(url, deadline=deadline))


def _nearest_period_row(rows: list[dict], period_days: float | None,
                        key: str = "pl_orbper") -> dict:
    """The catalog row whose period sits nearest the DETECTED one.

    Multi-planet systems return several unordered rows; picking ``rows[0]``
    once misnamed TOI-125 b as c. When the detection carries a period, the row
    with the nearest ``pl_orbper`` is the one the search actually re-found;
    rows without a usable period (or a call without one) fall back to
    ``rows[0]`` — the old behaviour, now the exception rather than the rule.
    """
    if period_days is None:
        return rows[0]
    keyed = [r for r in rows if isinstance(r.get(key), (int, float))
             and not isinstance(r.get(key), bool)]
    if not keyed:
        return rows[0]
    return min(keyed, key=lambda r: abs(float(r[key]) - float(period_days)))


def catalog_crosscheck(tic: str, deadline: float | None = None,
                       detected_period_days: float | None = None) -> dict:
    """Is this candidate already a known planet or TOI? Asked AFTER the search.

    A blind search that surfaces a real transit will mostly surface things other
    people already found — sector 2 has been worked over by SPOC and QLP for
    years. The first graded run proved the point: the one target vetting called
    a "planet-candidate", TIC 211438925, is **WASP-20 b** (TOI 194.01,
    disposition KP), recovered at P = 4.901 d against a published 4.89962 d.

    That is a genuine third blind recovery and a validation of the vetting step —
    but only if the report SAYS so. Without this lookup a future reader meets an
    unannotated "planet-candidate" in a public artifact and has every reason to
    read it as a discovery. Run at report time, never during the search.

    ``detected_period_days`` selects among multi-planet rows: the TOI/ps row
    whose published period lands nearest the detection is the signal actually
    re-found (see :func:`_nearest_period_row`).
    """
    out = {"tic": tic, "known_toi": None, "known_planet": None,
           "published_period_days": None, "disposition": None,
           "known_ctoi": None, "ctoi_alias_n": None, "n_ctoi": 0}
    try:
        rows = _tap(f"select toi,pl_orbper,tfopwg_disp from toi where tid={int(tic)}",
                    deadline)
        if rows:
            row = _nearest_period_row(rows, detected_period_days)
            out["known_toi"] = row.get("toi")
            out["disposition"] = row.get("tfopwg_disp")
            out["published_period_days"] = row.get("pl_orbper")
    except Exception:  # noqa: BLE001 — a lookup outage must not sink the survey
        out["lookup_error"] = True
    try:
        rows = _tap(f"select pl_name,pl_orbper from ps where tic_id='TIC {int(tic)}'",
                    deadline)
        if rows:
            row = _nearest_period_row(rows, detected_period_days)
            out["known_planet"] = row.get("pl_name")
            out["published_period_days"] = (out["published_period_days"]
                                            or row.get("pl_orbper"))
    except Exception:  # noqa: BLE001
        out["lookup_error"] = True
    # ExoFOP's COMMUNITY candidates — the third table, and the one that was
    # missing. Neither the TOI list nor the confirmed-planet list carries a
    # CTOI, so a star filed by an outside analyst and never promoted came back
    # from this function as "unknown to every catalog" — which is how
    # TIC 287328866, on ExoFOP since 2019 as two CTOIs, became a lead.
    # Alias-aware: the 2019 filings are at 2.06/2.08 d and the hunt found the
    # 1.038 d P/2 alias, so a direct period match would still have missed it.
    try:
        from . import exofop
        ct = exofop.ctoi_crosscheck(tic, detected_period_days=detected_period_days,
                                    deadline=deadline)
        out["known_ctoi"] = ct["known_ctoi"]
        out["ctoi_alias_n"] = ct["ctoi_alias_n"]
        out["n_ctoi"] = ct["n_ctoi"]
        out["ctoi_period_days"] = ct["ctoi_period_days"]
        out["ctoi_table_age_days"] = ct["table_age_days"]
        if ct.get("lookup_error"):
            out["lookup_error"] = True
    except Exception:  # noqa: BLE001
        out["lookup_error"] = True
    return out


@dataclass
class A04Result:
    sector: int
    searched: list[dict] = field(default_factory=list)
    injections: list[dict] = field(default_factory=list)
    recoveries: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    false_alarm_sde: list[float] = field(default_factory=list)
    threshold: float = SDE_THRESHOLD
    control_passed: bool = False
    floor_clear: bool = False
    candidates_vetted: bool = False
    recovered_any: bool = False
    calibration_passed: bool = False
    wall_seconds: float = 0.0


def run_a04(sector: int = DEFAULT_SECTOR, n_targets: int = 24,
            seed: int = 2026, cache_dir=None, progress=None,
            phase=None) -> A04Result:
    t_start = time.time()
    result = A04Result(sector=sector)

    if phase:
        phase("enumerate", {"sector": sector})
    tics = sector_targets(sector)
    targets = sample_targets(tics, n_targets, seed)
    if phase:
        phase("sample", {"sector_size": len(tics), "sampled": len(targets)})

    curves: dict[str, tuple] = {}
    for tic in targets:
        try:
            tf = light_curve(tic, sector, cache_dir)
        except Exception:  # noqa: BLE001 — one bad target must not sink a survey
            tf = None
        if tf is None:
            continue
        curves[tic] = tf
        det = blind_search(*tf)
        known = RECOVERY_TARGETS.get(tic)
        row = {
            "tic": tic, "period_days": det.period_days, "depth": det.depth,
            "phase": det.phase, "sde": det.sde,
            "known_planet": known["name"] if known else None,
        }
        if known:
            row["published_period_days"] = known["period_days"]
            row["period_error_frac"] = abs(det.period_days / known["period_days"] - 1.0)
            row["recovered"] = bool(row["period_error_frac"] <= PERIOD_TOL_FRAC
                                    and det.sde >= SDE_THRESHOLD)
            result.recoveries.append(row)
        elif det.sde >= SDE_THRESHOLD:
            # Above threshold and not a known planet: a CANDIDATE, which must be
            # vetted rather than counted as either a planet or a false alarm.
            row["vetting"] = vet_candidate(*tf, det)
            row["catalog"] = catalog_crosscheck(
                tic, detected_period_days=det.period_days)
            result.candidates.append(row)
        else:
            result.false_alarm_sde.append(det.sde)
        result.searched.append(row)
        if progress:
            progress(tic, det, known)

    # Positive control — the class-6 gate.
    if phase:
        phase("injection", {})
    host = next((tic for tic in curves if tic not in RECOVERY_TARGETS), None)
    if host is not None:
        t, f = curves[host]
        for depth, period in INJECTIONS:
            det = blind_search(t, inject_box(t, f, period, depth))
            err = abs(det.period_days / period - 1.0)
            result.injections.append({
                "host_tic": host, "injected_period_days": period,
                "injected_depth": depth, "recovered_period_days": det.period_days,
                "recovered_depth": det.depth, "sde": det.sde,
                "period_error_frac": err,
                "recovered": bool(err <= PERIOD_TOL_FRAC and det.sde >= SDE_THRESHOLD),
            })

    floor = np.array(result.false_alarm_sde) if result.false_alarm_sde else np.array([])
    result.control_passed = bool(result.injections
                                 and all(i["recovered"] for i in result.injections))
    result.floor_clear = bool(floor.size >= 3 and floor.max() < SDE_THRESHOLD)
    result.candidates_vetted = all(
        c.get("vetting", {}).get("verdict") not in (None, "insufficient-coverage")
        for c in result.candidates)
    result.recovered_any = bool(result.recoveries
                                and all(r["recovered"] for r in result.recoveries))
    result.calibration_passed = bool(
        result.control_passed and result.floor_clear and result.recovered_any
        and result.candidates_vetted)
    result.wall_seconds = time.time() - t_start
    return result


def to_report(r: A04Result) -> dict:
    floor = np.array(r.false_alarm_sde) if r.false_alarm_sde else np.array([0.0])
    rec = [x for x in r.recoveries if x.get("recovered")]
    return {
        "experiment": "A04-blind-transit-search",
        "headline": (
            f"blind search of {len(r.searched)} sector-{r.sector} targets: "
            f"{len(rec)}/{len(r.recoveries)} known planets recovered without being "
            f"told where; {sum(i['recovered'] for i in r.injections)}/"
            f"{len(r.injections)} injections recovered; {len(r.candidates)} "
            f"candidate(s) vetted; noise floor max SDE {float(floor.max()):.1f} "
            f"vs threshold {r.threshold}"
        ),
        "status": "pass" if r.calibration_passed else "null",
        "sector": r.sector,
        "targets_searched": len(r.searched),
        "enumeration_note": "page-capped; a real sector holds thousands of 2-minute targets",
        "period_grid": {"lo_days": P_LO, "hi_days": P_HI, "n": N_PERIODS},
        "detrend_window_days": DETREND_WINDOW_DAYS,
        "sde_threshold": r.threshold,
        "period_tolerance_frac": PERIOD_TOL_FRAC,
        "searched": r.searched,
        "recoveries": r.recoveries,
        "candidates": r.candidates,
        "injections": r.injections,
        "false_alarm_sde": r.false_alarm_sde,
        "false_alarm_max": float(floor.max()),
        "false_alarm_median": float(np.median(floor)),
        "control_passed": r.control_passed,
        "floor_clear": r.floor_clear,
        "candidates_vetted": r.candidates_vetted,
        "recovered_any": r.recovered_any,
        "calibration_passed": r.calibration_passed,
        "wall_seconds": r.wall_seconds,
        "claim_boundary": (
            "A SAMPLE of one sector, not the whole sector: a full TESS sector holds "
            "thousands of 2-minute targets and this run searches a deterministic "
            "subset, so no completeness or occurrence-rate statement is implied. "
            "The graded claim is RECOVERY of already-confirmed planets by a search "
            "that was not told about them, plus a measured false-alarm floor — it "
            "is not a discovery, and nothing here is submitted to ExoFOP. Depths "
            "are reported, not graded: the running-median detrend biases them low "
            "for long transits, which the injections quantify. Published periods "
            "are read only at grading time and never enter the search."
        ),
    }
