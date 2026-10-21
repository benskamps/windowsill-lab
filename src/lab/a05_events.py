"""Cross-sector single-event search — dips in different sectors, paired into periods.

The survey's period search (:func:`lab.a04.blind_search`) folds one sector and
needs ``MIN_TRANSITS = 3`` events in it, so anything slower than about nine days
is outside its definition. :mod:`lab.a05_mono` finds a single dip inside one
sector but cannot give it a period. This module is the missing join: find
transit-shaped events in every sector of one star, then ask which pairs of
events, years apart, are the same body coming round again.

Governed by ``docs/preregistrations/2026-10-20-a05-single-event-mode.md``. The
constants below are that file's, and changing one is an amendment, not a tune.

### The steps

1. :func:`find_events` — ``a05_mono.scan`` on each segment-bearing series;
   an event is a dip with SNR >= :data:`EVENT_SNR`.
2. :func:`pair_trials` — every pair of events in DIFFERENT orbit segments with
   compatible duration and depth gives trial periods ``Δ/n`` down to
   :data:`P_MIN`. Each is one member of an alias family.
3. Each trial is checked against every epoch it predicts inside the data
   (:func:`check_trial`): an epoch whose box excludes the pair's depth at
   :data:`VETO_SIGMA` kills the trial; otherwise the trial scores the combined
   SNR of all covered epochs.
4. :func:`search` returns the surviving trials, best first, and ``s_max``.

### The nulls

:func:`roll_segments` is the placebo: each orbit segment's flux is rolled
against its own timestamps, which keeps every dip, gap and systematic in that
segment and destroys only the cross-segment timing the pairing step measures.
:func:`invert` is the second null: brightenings paired by the same machinery.

Nothing here assigns a disposition, and nothing here can emit *planet*.
"""
from __future__ import annotations

import math

import numpy as np

from . import a05_mono

#: Event threshold. Below a05_mono.SNR_REPORT (9) because pairing supplies the
#: repetition a single event lacks; the pre-registration fixes it at 7.
EVENT_SNR = 7.0

#: Shortest trial period. Below this the per-sector BLS (3 events in ~27 d)
#: already sees the signal; this mode exists for what it cannot see.
P_MIN = 10.0

#: Orbit segments split on gaps longer than this (TESS downlinks are ~1 d;
#: sector boundaries are longer).
SEGMENT_GAP_DAYS = 1.0

#: Pairing compatibility: durations within this factor, depths within this
#: many combined sigma.
DUR_FACTOR = 2.0
DEPTH_SIGMA = 3.0

#: A covered epoch whose box depth + VETO_SIGMA·sigma falls short of the pair's
#: mean depth vetoes the trial: the data were there and the dip was not.
VETO_SIGMA = 3.0

#: A covered epoch counts as an event in support when its box SNR clears this.
SUPPORT_SNR = 3.0

#: Placebo size and seed (A05 convention for the empirical FAP).
N_ROLLS = 200
SEED = 2026

#: Box flanks out to this many half-widths, as in a05_mono and
#: a05_multisector.box_depth.
FLANK_FACTOR = 3.0


def segments(t: np.ndarray, gap: float = SEGMENT_GAP_DAYS) -> np.ndarray:
    """Segment label per cadence (t sorted): a new label after every gap."""
    t = np.asarray(t, float)
    lab = np.zeros(t.size, dtype=int)
    if t.size > 1:
        lab[1:] = np.cumsum(np.diff(t) > gap)
    return lab


def find_events(t: np.ndarray, f: np.ndarray, seg: np.ndarray,
                snr_min: float = EVENT_SNR) -> list[dict]:
    """Dips with SNR >= ``snr_min``, scanned one segment at a time so a dip
    can never borrow flank cadences from across a gap."""
    out: list[dict] = []
    for s in np.unique(seg):
        m = seg == s
        if m.sum() < a05_mono.MIN_IN + a05_mono.MIN_OUT:
            continue
        for h in a05_mono.scan(t[m], f[m]):
            if h["snr"] >= snr_min:
                h = dict(h)
                h["segment"] = int(s)
                h["sigma_depth"] = (h["depth"] / h["snr"]) if h["snr"] else None
                out.append(h)
    out.sort(key=lambda h: h["t_centre"])
    return out


class _Boxer:
    """Fast box depth on a time-sorted series, identical in definition to
    :func:`lab.a05_multisector.box_depth` (mean in, median flank baseline,
    MAD flank scatter, error sqrt(1/n_in + (pi/2)/n_out)), but with the windows
    found by binary search instead of a full-array scan."""

    def __init__(self, t: np.ndarray, f: np.ndarray):
        o = np.argsort(t, kind="stable")
        self.t = np.asarray(t, float)[o]
        self.f = np.asarray(f, float)[o]
        self.lo, self.hi = float(self.t[0]), float(self.t[-1])

    def depth(self, tc: float, dur: float) -> tuple | None:
        half = 0.5 * dur
        a = np.searchsorted(self.t, tc - FLANK_FACTOR * half, "left")
        b = np.searchsorted(self.t, tc + FLANK_FACTOR * half, "right")
        if b - a < 13:
            return None
        tt = self.t[a:b]
        ff = self.f[a:b]
        d = np.abs(tt - tc)
        inb = d <= half
        n_in = int(inb.sum())
        n_out = int(tt.size - n_in)
        if n_in < 3 or n_out < 10:
            return None
        fo = ff[~inb]
        base = float(np.median(fo))
        s = float(1.4826 * np.median(np.abs(fo - base)))
        dep = base - float(np.mean(ff[inb]))
        err = s * math.sqrt(1.0 / n_in + (math.pi / 2) / n_out)
        if not err > 0:
            return None
        return dep, err


def check_trial(boxer: _Boxer, t_ref: float, period: float, dur: float,
                depth: float) -> dict:
    """Every epoch of ``t_ref + k·period`` inside the data, measured.

    Stops at the first veto (most aliases die on their first covered epoch).
    """
    k0 = int(math.ceil((boxer.lo - t_ref) / period))
    k1 = int(math.floor((boxer.hi - t_ref) / period))
    covered = []
    for k in range(k0, k1 + 1):
        tc = t_ref + k * period
        r = boxer.depth(tc, dur)
        if r is None:
            continue
        dep, err = r
        if dep + VETO_SIGMA * err < depth:
            return {"vetoed": True, "veto_epoch": k, "veto_t": tc,
                    "veto_depth": dep, "veto_sigma": err}
        covered.append((k, tc, dep, err))
    snr = np.array([max(c[2] / c[3], 0.0) for c in covered]) if covered else np.zeros(0)
    return {"vetoed": False,
            "score": float(math.sqrt(float(np.sum(snr ** 2)))),
            "n_covered": len(covered),
            "n_events": int(np.sum(snr >= SUPPORT_SNR)),
            "epochs": [{"k": c[0], "t": c[1], "depth": c[2], "sigma": c[3]}
                       for c in covered]}


def pair_trials(events: list[dict], p_min: float = P_MIN) -> list[dict]:
    """Every (pair, n) trial period, before any data check."""
    trials = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if a["segment"] == b["segment"]:
                continue
            da, db = a["duration_hours"], b["duration_hours"]
            if max(da, db) / min(da, db) > DUR_FACTOR:
                continue
            sa, sb = a.get("sigma_depth") or 0.0, b.get("sigma_depth") or 0.0
            if abs(a["depth"] - b["depth"]) > DEPTH_SIGMA * math.hypot(sa, sb):
                continue
            delta = b["t_centre"] - a["t_centre"]
            n_max = int(math.floor(delta / p_min))
            dur = 0.5 * (da + db) / 24.0
            dep = 0.5 * (a["depth"] + b["depth"])
            for n in range(1, n_max + 1):
                trials.append({"pair": (i, j), "n": n, "period": delta / n,
                               "t_ref": a["t_centre"], "duration_days": dur,
                               "depth": dep})
    return trials


def search(t: np.ndarray, f: np.ndarray, *, p_min: float = P_MIN,
           events: list[dict] | None = None, keep: int = 20) -> dict:
    """The whole rung on one stitched series. ``t`` need not be sorted."""
    o = np.argsort(t, kind="stable")
    t = np.asarray(t, float)[o]
    f = np.asarray(f, float)[o]
    seg = segments(t)
    if events is None:
        events = find_events(t, f, seg)
    boxer = _Boxer(t, f)
    survivors: list[dict] = []
    n_trials = n_vetoed = 0
    seen: set = set()
    for tr in pair_trials(events, p_min):
        # one alias family member checked once even if several pairs propose it
        key = (round(math.log(tr["period"]) * 2000),
               round(((tr["t_ref"] % tr["period"]) / tr["period"]) * 200) % 200)
        if key in seen:
            continue
        seen.add(key)
        n_trials += 1
        res = check_trial(boxer, tr["t_ref"], tr["period"], tr["duration_days"],
                          tr["depth"])
        if res["vetoed"]:
            n_vetoed += 1
            continue
        if res["n_events"] < 2:
            continue
        survivors.append({**tr, **res})
    survivors.sort(key=lambda r: -r["score"])
    return {"events": events, "n_events": len(events),
            "n_segments": int(seg.max() + 1) if seg.size else 0,
            "n_trials": n_trials, "n_vetoed": n_vetoed,
            "n_survivors": len(survivors),
            "s_max": survivors[0]["score"] if survivors else 0.0,
            "best": survivors[0] if survivors else None,
            "survivors": survivors[:keep]}


# --------------------------------------------------------------- nulls --

def roll_segments(t: np.ndarray, f: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Placebo: each orbit segment's flux rolled by an independent random
    offset against its own (unchanged) timestamps. ``t`` must be sorted."""
    seg = segments(t)
    out = np.empty_like(np.asarray(f, float))
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s)
        out[idx] = np.roll(np.asarray(f, float)[idx], int(rng.integers(0, idx.size)))
    return out


def invert(f: np.ndarray) -> np.ndarray:
    """Second null: brightenings become dips; the same machinery pairs them."""
    return 2.0 - np.asarray(f, float)


def placebo(t: np.ndarray, f: np.ndarray, n_rolls: int = N_ROLLS,
            seed: int = SEED, p_min: float = P_MIN) -> dict:
    """S_max under ``n_rolls`` segment rolls, and the observed S_max's
    empirical FAP ``(1 + k) / (B + 1)``."""
    o = np.argsort(t, kind="stable")
    t = np.asarray(t, float)[o]
    f = np.asarray(f, float)[o]
    obs = search(t, f, p_min=p_min)["s_max"]
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_rolls):
        null.append(search(t, roll_segments(t, f, rng), p_min=p_min)["s_max"])
    null_a = np.asarray(null)
    k = int(np.sum(null_a >= obs))
    return {"s_max_observed": float(obs), "null": null_a.tolist(),
            "null_max": float(null_a.max()) if null_a.size else None,
            "null_median": float(np.median(null_a)) if null_a.size else None,
            "null_q025": float(np.quantile(null_a, 0.025)) if null_a.size else None,
            "null_q975": float(np.quantile(null_a, 0.975)) if null_a.size else None,
            "k_exceed": k, "n_rolls": n_rolls,
            "fap": (1 + k) / (n_rolls + 1)}


def inject(t: np.ndarray, f: np.ndarray, period: float, t0: float,
           depth: float, duration_days: float) -> np.ndarray:
    """Box transit, multiplicative, at ``t0 + k·period``."""
    x = ((np.asarray(t, float) - t0 + 0.5 * period) % period) - 0.5 * period
    out = np.asarray(f, float).copy()
    out[np.abs(x) < 0.5 * duration_days] *= (1.0 - depth)
    return out


def recovered(result: dict, period: float, tol: float = 0.005,
              max_alias: int = 3) -> str | None:
    """``"exact"``, ``"alias"`` or ``None`` for an injected ``period``."""
    kinds = []
    for s in result.get("survivors", []):
        p = s["period"]
        if abs(p - period) / period <= tol:
            return "exact"
        for n in range(2, max_alias + 1):
            if (abs(p - period / n) / (period / n) <= tol
                    or abs(p - period * n) / (period * n) <= tol):
                kinds.append("alias")
    return "alias" if kinds else None
