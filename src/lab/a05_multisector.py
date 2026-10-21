"""One star, every sector — the plumbing a single-sector survey never needed.

A05 searches one sector at a time, and :func:`lab.a05.load_curve` reads one
SPOC 2-minute product at a time, so everything downstream assumes a single
contiguous ~27-day series. A signal with an 18-day period puts at most two
events in one sector and often one, and the events that pin its period are
years apart. Checking such a signal — someone else's or our own — needs four
things this module provides and nothing else does:

1. :func:`discover_products` lists every light-curve product MAST holds for a
   TIC across the pipelines a caller admits (SPOC 2-min, TESS-SPOC FFI, QLP),
   not just SPOC, because a target observed only in full-frame images in its
   later sectors has no SPOC 2-min product there at all.
2. :func:`read_columns` reads any TESS light-curve BINTABLE with the same
   dependency-free walk as :func:`lab.a01.read_tess_light_curve`, without
   demanding ``PDCSAP_FLUX`` (QLP files carry ``KSPSAP_FLUX`` instead).
3. :func:`bls_stitched` is BLS over a multi-year baseline. The single-sector
   grid (:func:`lab.a04.blind_search`: 3,000 frequencies, 200 phase bins) is
   wrong in two ways at that baseline: the frequency step has to shrink with
   the baseline or a real period falls between grid points, and the phase bins
   have to be sized to the transit in TIME, not to a fixed fraction of the
   period, or a 2-hour dip at 40 days is smeared across a 5-hour bin.
4. :func:`event_time`, :func:`box_depth` and :func:`centroid_shift_matched`
   measure one event at a time, in absolute time, with windows sized to the
   transit duration. The A05 gates size their windows in PHASE
   (``a04.VET_WINDOW_PHASE = 0.03``), which is right for a 3-day period and
   ±13 hours at 18 days: a 2.4-hour dip is then a minority of its own window.

Nothing here assigns a disposition. Callers use the existing gates and
vocabulary; this module only makes them measurable at long period.
"""
from __future__ import annotations

import hashlib
import math
import re

import numpy as np

from . import a01, a04

#: Pipelines this module knows how to read, and the flux column each carries.
#: SPOC and TESS-SPOC carry PDCSAP (crowding-corrected); QLP carries its own
#: detrended KSPSAP and no crowding keyword.
FLUX_COLUMN = {"SPOC": "PDCSAP_FLUX", "TESS-SPOC": "PDCSAP_FLUX",
               "QLP": "KSPSAP_FLUX"}

#: Seconds per day, for exposure times reported in seconds.
DAY_S = 86400.0


def discover_products(tic: str, provenances=("SPOC", "TESS-SPOC", "QLP"),
                      deadline: float | None = None) -> list[dict]:
    """Every light-curve FITS product MAST lists for ``tic``, one per
    (provenance, sector), sorted by sector then provenance.

    SPOC lives in the ``TESS`` collection and the FFI pipelines in ``HLSP``;
    both are queried by target name. A SPOC observation can carry both a 2-min
    and a 20-s product; only the 2-min ``_lc.fits`` is kept, as in A01.
    """
    tic = str(int(str(tic)))
    obs = a01._mast("Mast.Caom.Filtered", {
        "columns": "obsid,obs_collection,provenance_name,sequence_number,t_exptime",
        "filters": [{"paramName": "target_name", "values": [tic]},
                    {"paramName": "dataproduct_type", "values": ["timeseries"]}],
    }, deadline=deadline)
    want = {p.upper() for p in provenances}
    out: dict[tuple[str, int], dict] = {}
    for o in sorted(obs, key=lambda r: (int(r.get("sequence_number") or 0),
                                        str(r.get("provenance_name")),
                                        str(r.get("obsid")))):
        prov = str(o.get("provenance_name") or "").upper()
        if prov not in want:
            continue
        sector = int(o.get("sequence_number") or 0)
        if sector <= 0 or (prov, sector) in out:
            continue
        rows = a01._mast("Mast.Caom.Products", {"obsid": str(o["obsid"])},
                         deadline=deadline)
        for row in sorted(rows, key=lambda r: str(r.get("productFilename", ""))):
            name = str(row.get("productFilename", ""))
            uri = str(row.get("dataURI") or "").strip()
            low = name.lower()
            if not uri or not low.endswith(".fits"):
                continue
            if prov == "SPOC":
                ok = low.endswith("_lc.fits") and "fast" not in low
            else:
                ok = low.endswith("lc.fits")        # _lc.fits / _llc.fits
            if not ok:
                continue
            out[(prov, sector)] = {
                "tic": tic, "sector": sector, "provenance": prov,
                "filename": name, "uri": uri,
                "size": int(row.get("size") or 0),
                "exptime_s": float(o.get("t_exptime") or 0.0)}
            break
    return sorted(out.values(), key=lambda p: (p["sector"], p["provenance"]))


def read_columns(blob: bytes) -> tuple[dict, dict, dict]:
    """``(columns, extension-1 header, primary header)`` from a light-curve FITS.

    The same walk as :func:`lab.a01.read_tess_light_curve`, returning every
    numeric column rather than insisting on SPOC's four.
    """
    primary, cursor = a01._header(blob, 0)
    n_axis = int(primary.get("NAXIS", 0))
    size = 0
    if n_axis:
        size = abs(int(primary.get("BITPIX", 8))) // 8
        for i in range(1, n_axis + 1):
            size *= int(primary.get(f"NAXIS{i}", 0))
        size = size * int(primary.get("GCOUNT", 1)) + int(primary.get("PCOUNT", 0))
    cursor += ((size + 2879) // 2880) * 2880
    table, data_offset = a01._header(blob, cursor)
    if table.get("XTENSION") != "BINTABLE":
        raise ValueError("light curve extension 1 is not a BINTABLE")
    names, formats, offsets = [], [], []
    byte_offset = 0
    for i in range(1, int(table["TFIELDS"]) + 1):
        name = str(table.get(f"TTYPE{i}", f"FIELD{i}")).strip()
        form = str(table[f"TFORM{i}"]).strip()
        m = re.fullmatch(r"(\d*)([A-Z])", form)
        if not m:
            raise ValueError(f"unsupported FITS TFORM {form!r}")
        count, code = int(m.group(1) or 1), m.group(2)
        width = math.ceil(count / 8) if code == "X" else count * a01._WIDTH[code]
        if code in a01._DTYPE and code not in ("A", "L") and count == 1:
            names.append(name)
            formats.append(np.dtype(a01._DTYPE[code]))
            offsets.append(byte_offset)
        byte_offset += width
    dtype = np.dtype({"names": names, "formats": formats, "offsets": offsets,
                      "itemsize": int(table["NAXIS1"])})
    rows = np.ndarray((int(table["NAXIS2"]),), dtype=dtype, buffer=blob,
                      offset=data_offset)
    cols = {n: np.asarray(rows[n]).astype(float) for n in names}
    return cols, table, primary


def _num(header: dict, key: str):
    v = header.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def curve_from_product(blob: bytes, provenance: str) -> dict:
    """One FITS byte string -> time-sorted, quality-masked, normalised,
    detrended series plus the ancillary numbers the gates read.

    Same order of operations as :func:`lab.a05.curve_from_blob`: quality mask,
    per-file median normalisation, centroids minus pointing model where both
    exist, then :func:`lab.a04.detrend`. ``f_raw`` keeps the normalised but
    undetrended flux for depth checks that must not inherit the detrend's bias.
    """
    prov = provenance.upper()
    cols, table, primary = read_columns(blob)
    flux_col = FLUX_COLUMN[prov]
    if flux_col not in cols:
        raise ValueError(f"{prov} product has no {flux_col} column")
    t = cols["TIME"]
    f = cols[flux_col]
    q = cols.get("QUALITY")
    good = np.isfinite(t) & np.isfinite(f) & (f > 0)
    if q is not None:
        good &= (q == 0)
    if good.sum() < 100:
        raise ValueError("too few quality-zero cadences")
    order = np.argsort(t[good], kind="stable")

    def pick(name):
        c = cols.get(name)
        return None if c is None else c[good][order]

    t = t[good][order]
    f = f[good][order]
    f = f / np.median(f)
    cx, cy = pick("MOM_CENTR1"), pick("MOM_CENTR2")
    px, py = pick("POS_CORR1"), pick("POS_CORR2")
    if cx is not None and px is not None:
        cx = cx - px
    if cy is not None and py is not None:
        cy = cy - py
    td, fd = a04.detrend(t, f)
    if not np.array_equal(td, t):
        raise ValueError("detrend reordered cadences")
    cadence = float(np.median(np.diff(t))) if t.size > 1 else float("nan")
    return {"t": t, "f": fd, "f_raw": f, "cx": cx, "cy": cy,
            "provenance": prov, "cadence_days": cadence,
            "crowdsap": _num(table, "CROWDSAP"),
            "flfrcsap": _num(table, "FLFRCSAP"),
            "r_star_sun": _num(primary, "RADIUS"),
            "teff_k": _num(primary, "TEFF"),
            "tessmag": _num(primary, "TESSMAG"),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "n_cadences": int(t.size)}


def load_product(product: dict, cache_dir=None) -> tuple[dict, dict]:
    """Download (or read from the A01 cache) one product; return
    ``(curve, receipt_row)``. The receipt row pins the bytes by SHA-256."""
    blob, meta = a01._download_product(product, cache_dir or a01.CACHE_DIR)
    curve = curve_from_product(blob, product["provenance"])
    row = {k: meta.get(k) for k in ("sector", "provenance", "filename", "uri",
                                    "bytes", "sha256", "download_url")}
    row.update({"n_cadences": curve["n_cadences"],
                "cadence_min": round(curve["cadence_days"] * 1440.0, 3),
                "t_start": float(curve["t"][0]), "t_end": float(curve["t"][-1]),
                "crowdsap": curve["crowdsap"]})
    return curve, row


# ---------------------------------------------------------- stitched BLS --

def bin_series(t: np.ndarray, f: np.ndarray, width_days: float) -> tuple:
    """Mean-bin onto a fixed grid; returns ``(t, f, n)`` for non-empty bins.
    Mixing 2-min and 10-min cadences then costs nothing in the BLS."""
    t = np.asarray(t, float)
    f = np.asarray(f, float)
    k = np.floor((t - t.min()) / width_days).astype(np.int64)
    uniq, inv, n = np.unique(k, return_inverse=True, return_counts=True)
    ts = np.bincount(inv, weights=t) / n
    fs = np.bincount(inv, weights=f) / n
    return ts, fs, n.astype(float)


def frequency_grid(p_lo: float, p_hi: float, baseline_days: float,
                   min_duration_days: float, drift_frac: float = 0.25) -> np.ndarray:
    """Frequencies such that adjacent trials drift by at most ``drift_frac``
    of the shortest box across the whole baseline.

    At frequency f the time error at the far end of the baseline from a step
    Δf is ``Δf · T · P``, so ``Δf = drift_frac · D · f / T`` — a geometric grid.
    """
    f_lo, f_hi = 1.0 / p_hi, 1.0 / p_lo
    ratio = 1.0 + drift_frac * min_duration_days / baseline_days
    n = int(math.ceil(math.log(f_hi / f_lo) / math.log(ratio))) + 1
    return f_lo * ratio ** np.arange(n)


def bls_stitched(t: np.ndarray, f: np.ndarray, w: np.ndarray | None = None, *,
                 p_lo: float = 1.0, p_hi: float = 40.0,
                 durations_hours=(1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
                 drift_frac: float = 0.25) -> dict:
    """BLS over an arbitrary multi-sector series.

    The statistic is the box depth over its white-noise error,
    ``(mean_out - mean_in) / (sigma / sqrt(n_in))`` with ``n_in`` the number of
    ORIGINAL cadences in the box (``w`` carries per-point counts when the input
    is binned). Phase bins are a fixed width in TIME — a quarter of the
    shortest duration — so a box means the same thing at every period.

    Returns the period grid, the per-period best SNR, depth, duration and
    epoch, and SDE = (power - median) / std over the grid.
    """
    t = np.asarray(t, float)
    f = np.asarray(f, float)
    w = np.ones_like(t) if w is None else np.asarray(w, float)
    durs = np.asarray(durations_hours, float) / 24.0
    base = float(t.max() - t.min())
    freqs = frequency_grid(p_lo, p_hi, base, float(durs.min()), drift_frac)
    bin_w = float(durs.min()) / 4.0
    mean = float(np.sum(w * f) / np.sum(w))
    resid = f - mean
    # Per-ORIGINAL-cadence scatter: a bin mean of n cadences has variance
    # s²/n, so resid·√n is on the per-cadence scale whatever the binning.
    sig = float(1.4826 * np.median(np.abs(resid * np.sqrt(w))))
    if not sig > 0:
        sig = float(np.std(resid * np.sqrt(w))) or 1.0
    wf = w * resid
    power = np.zeros(freqs.size)
    depth = np.zeros(freqs.size)
    best_d = np.zeros(freqs.size)
    epoch = np.zeros(freqs.size)
    t0 = float(t.min())
    for i, fr in enumerate(freqs):
        P = 1.0 / fr
        nb = max(8, int(math.ceil(P / bin_w)))
        ph = ((t - t0) * fr) % 1.0
        idx = np.minimum((ph * nb).astype(np.int64), nb - 1)
        s = np.bincount(idx, weights=wf, minlength=nb)
        c = np.bincount(idx, weights=w, minlength=nb)
        cs = np.r_[0.0, np.cumsum(np.r_[s, s])]
        cc = np.r_[0.0, np.cumsum(np.r_[c, c])]
        best = (0.0, 0.0, 0.0, 0.0)
        for d in durs:
            k = max(1, int(round(d / (P / nb))))
            if k >= nb // 2:
                continue
            sin = cs[k:k + nb] - cs[:nb]
            cin = cc[k:k + nb] - cc[:nb]
            ok = cin >= 3
            if not ok.any():
                continue
            # residuals sum to zero, so mean_out - mean_in = -sin/cin * N/(N-cin)
            tot = cc[nb]
            dep = np.where(ok, -sin / np.maximum(cin, 1e-9) * tot /
                           np.maximum(tot - cin, 1e-9), 0.0)
            snr = dep * np.sqrt(np.maximum(cin, 0)) / sig
            j = int(np.argmax(snr))
            if snr[j] > best[0]:
                best = (float(snr[j]), float(dep[j]), float(d),
                        t0 + P * ((j + 0.5 * k) / nb))
        power[i], depth[i], best_d[i], epoch[i] = best
    spread = float(power.std())
    sde = (power - np.median(power)) / spread if spread > 0 else power * 0
    return {"freqs": freqs, "periods": 1.0 / freqs, "power": power,
            "sde": sde, "depth": depth, "duration_days": best_d,
            "epoch": epoch, "sigma_cadence": sig, "n_trials": int(freqs.size),
            "baseline_days": base}


def top_peaks(bls: dict, n: int = 5, min_sep_frac: float = 0.01) -> list[dict]:
    """The ``n`` highest SDE peaks, each at least ``min_sep_frac`` apart in
    period from every higher one."""
    order = np.argsort(-bls["sde"])
    out: list[dict] = []
    for j in order:
        P = float(bls["periods"][j])
        if any(abs(P - o["period_days"]) / o["period_days"] < min_sep_frac for o in out):
            continue
        out.append({"period_days": P, "sde": float(bls["sde"][j]),
                    "snr": float(bls["power"][j]), "depth": float(bls["depth"][j]),
                    "duration_hours": float(bls["duration_days"][j] * 24.0),
                    "epoch_btjd": float(bls["epoch"][j])})
        if len(out) >= n:
            break
    return out


def peak_near(bls: dict, period: float, tol_frac: float = 0.002) -> dict | None:
    """Best SDE within ``tol_frac`` of ``period`` and its rank in the grid."""
    P = bls["periods"]
    sel = np.abs(P - period) / period < tol_frac
    if not sel.any():
        return None
    j = int(np.flatnonzero(sel)[np.argmax(bls["sde"][sel])])
    rank = int(np.sum(bls["sde"] > bls["sde"][j])) + 1
    # rank among distinct peaks: count higher peaks separated by > tol
    return {"period_days": float(P[j]), "sde": float(bls["sde"][j]),
            "snr": float(bls["power"][j]), "grid_rank": rank,
            "depth": float(bls["depth"][j])}


# ------------------------------------------------------------- one event --

def _local(t, f, tc, half, out_factor=3.0):
    d = np.abs(t - tc)
    inb = d <= half
    out = (d > half) & (d <= out_factor * half)
    return inb, out


def box_depth(t: np.ndarray, f: np.ndarray, tc: float, duration_days: float,
              out_factor: float = 3.0) -> dict:
    """Depth of a box of ``duration_days`` centred on ``tc`` against the local
    flanks out to ``out_factor`` half-widths. Error from the flank scatter.
    ``n_in`` < 3 or ``n_out`` < 10 is reported as no measurement."""
    t = np.asarray(t, float)
    f = np.asarray(f, float)
    half = 0.5 * duration_days
    inb, out = _local(t, f, tc, half, out_factor)
    n_in, n_out = int(inb.sum()), int(out.sum())
    res = {"t_centre": float(tc), "n_in": n_in, "n_out": n_out,
           "depth": None, "sigma": None, "snr": None}
    if n_in < 3 or n_out < 10:
        res["reason"] = "no-coverage"
        return res
    base = float(np.median(f[out]))
    s = float(1.4826 * np.median(np.abs(f[out] - base)))
    dep = base - float(np.mean(f[inb]))
    err = s * math.sqrt(1.0 / n_in + (math.pi / 2) / n_out)
    res.update({"depth": dep, "sigma": err,
                "snr": dep / err if err > 0 else None, "point_sigma": s})
    return res


def event_time(t: np.ndarray, f: np.ndarray, tc_guess: float,
               duration_days: float, search_half_days: float = 3.0 / 24,
               step_days: float = 1.0 / 1440) -> dict:
    """Mid-time of one event by a box χ² scan.

    At each trial centre the box depth is the least-squares value given the
    local flank baseline; χ² uses the flank point scatter. The 1σ interval is
    where χ² rises by 1 above its minimum — an honest single-event error only
    if the noise is white over a transit duration, which is stated, not tested.
    """
    t = np.asarray(t, float)
    f = np.asarray(f, float)
    half = 0.5 * duration_days
    win = np.abs(t - tc_guess) <= search_half_days + 3 * half
    tt, ff = t[win], f[win]
    out = {"t_guess": float(tc_guess), "t_mid": None, "sigma_days": None}
    if tt.size < 20:
        out["reason"] = "no-coverage"
        return out
    trials = np.arange(tc_guess - search_half_days,
                       tc_guess + search_half_days + 0.5 * step_days, step_days)
    sd = float(1.4826 * np.median(np.abs(ff - np.median(ff))))
    if not sd > 0:
        out["reason"] = "degenerate-scatter"
        return out
    chi = np.full(trials.size, np.inf)
    deps = np.zeros(trials.size)
    for i, tc in enumerate(trials):
        inb, flank = _local(tt, ff, tc, half)
        if inb.sum() < 3 or flank.sum() < 10:
            continue
        base = float(np.median(ff[flank]))
        dep = base - float(np.mean(ff[inb]))
        model = np.where(inb, base - dep, base)
        use = inb | flank
        chi[i] = float(np.sum(((ff[use] - model[use]) / sd) ** 2)
                       - np.sum(((ff[use] - base) / sd) ** 2))
        deps[i] = dep
    if not np.isfinite(chi).any():
        out["reason"] = "no-coverage"
        return out
    j = int(np.argmin(chi))
    within = np.flatnonzero(chi <= chi[j] + 1.0)
    lo, hi = trials[within.min()], trials[within.max()]
    out.update({"t_mid": float(trials[j]), "depth": float(deps[j]),
                "delta_chi2": float(-chi[j]),
                "sigma_days": float(max(0.5 * (hi - lo), step_days)),
                "edge": bool(j in (0, trials.size - 1))})
    return out


def centroid_shift_matched(t: np.ndarray, cx, cy, centres, duration_days: float,
                           depth: float, n_boot: int = 256,
                           seed: int = 20260814) -> dict:
    """:func:`lab.a05_vetting.centroid_shift` with windows in TIME.

    In-transit: ``|t - tc| < T14/2``. Local out-of-transit:
    ``T14/2 < |t - tc| < 3·T14/2``. Same per-event differencing, the same
    bootstrap over whole events, the same verdict constants
    (``CENTROID_SIGMA``, ``CENTROID_MIN_OFFSET_PX``, ``CENTROID_MIN_EVENTS``).
    """
    from . import a05_vetting as v
    out = {"verdict": None, "n_events": 0, "dx": None, "dy": None,
           "shift": None, "shift_sigma": None, "implied_offset_px": None}
    if cx is None or cy is None:
        out["reason"] = "no-centroid-data"
        return out
    t = np.asarray(t, float)
    cx = np.asarray(cx, float)
    cy = np.asarray(cy, float)
    fin = np.isfinite(cx) & np.isfinite(cy)
    half = 0.5 * duration_days
    dxs, dys = [], []
    for tc in centres:
        inb, flank = _local(t, None, tc, half)
        a, b = inb & fin, flank & fin
        if a.sum() < 5 or b.sum() < 5:
            continue
        dxs.append(float(np.mean(cx[a]) - np.mean(cx[b])))
        dys.append(float(np.mean(cy[a]) - np.mean(cy[b])))
    n = len(dxs)
    out["n_events"] = n
    out["per_event"] = [{"dx": x, "dy": y} for x, y in zip(dxs, dys)]
    if n < v.CENTROID_MIN_EVENTS:
        out["reason"] = "insufficient-events"
        return out
    dx_a, dy_a = np.asarray(dxs), np.asarray(dys)
    dx, dy = float(dx_a.mean()), float(dy_a.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    sx = float(np.std(dx_a[idx].mean(axis=1), ddof=1))
    sy = float(np.std(dy_a[idx].mean(axis=1), ddof=1))
    sig = float(np.hypot(dx / sx if sx > 0 else 0.0, dy / sy if sy > 0 else 0.0))
    shift = float(np.hypot(dx, dy))
    implied = shift / depth if depth > 0 else float("inf")
    out.update({"dx": dx, "dy": dy, "sigma_x": sx, "sigma_y": sy,
                "shift": shift, "shift_sigma": sig,
                "implied_offset_px": float(implied)})
    if sig > v.CENTROID_SIGMA and implied > v.CENTROID_MIN_OFFSET_PX:
        out["verdict"] = "centroid-shift"
    return out
