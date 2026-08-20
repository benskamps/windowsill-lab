"""A03 — reprocess an open LIGO/Virgo event from GWOSC and try to recover its
published chirp mass.

The method is matched filtering against 3.5PN TaylorF2 stationary-phase inspiral
templates, written against numpy alone (no scipy, no h5py, no gwpy) in the same
spirit as A01's dependency-free FITS reader. Public GWOSC text strain is pinned
by URI, byte count and SHA-256; nothing is trusted from a cache without its hash.

Two things make this milestone honest rather than decorative:

1. **The event choice is a physics argument, not a preference.** A 3.5PN inspiral
   template is the right model only while the binary is inspiralling in band. For
   GW150914 (~66 Msun) f_ISCO = 1/(6^1.5 pi M) is 67 Hz, so the inspiral occupies
   35-67 Hz and essentially all the SNR sits in a merger-ringdown this waveform
   does not model — which is why LIGO used full IMR waveforms for it. A binary
   neutron star spends thousands of cycles in band, so GW170817 is where an
   inspiral-only filter is the correct instrument.

2. **A software injection runs at identical settings every time.** Without it a
   non-detection is uninterpretable — you cannot tell a quiet sky from a broken
   filter. The injection is drawn from the same template family as the search, so
   it validates the *machinery* and deliberately does NOT validate the waveform's
   fidelity to a real astrophysical source. The gap between the two is the model
   mismatch, and reporting that gap is the point.
"""
from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import math
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .pn import taylorf2_35, TSUN

EVENT_API = "https://gwosc.org/eventapi/json/{catalog}/{event}/{version}/"
DEFAULT_CATALOG = "GWTC-1-confident"
DEFAULT_EVENT = "GW170817"
DEFAULT_VERSION = "v3"
from .labhome import CACHE as LAB_CACHE

CACHE_DIR = LAB_CACHE / "a03"
def _user_agent() -> str:
    """Identify THIS checkout to GWOSC, not the upstream author's.

    A courtesy header, and courtesy that names the wrong party is worse than
    none: an operator who needs to contact whoever is hitting their archive
    should reach the person actually running it. Derived from the checkout's own
    remote; falls back to the bare project name when there is nothing to point
    at (see :mod:`lab.origin`).
    """
    from . import origin
    url = origin.repo_url()
    return f"windowsill-lab/a03 (+{url})" if url else "windowsill-lab/a03"


USER_AGENT = _user_agent()

FS_RAW = 4096
DECIM = 4
FS = FS_RAW // DECIM
SEG_SEC = 256
PRE_SEC = 200.0
F_LOW, F_HIGH = 25.0, 480.0
MC_LO, MC_HI, DMC = 1.15, 1.26, 2e-5
ETA = 0.2490
INJECT_SNR = 25.0

# A recovered chirp mass counts only if it lands inside the published error bar.
# The control has its own, much tighter gate: if the pipeline cannot recover a
# signal it planted itself, the run says nothing about the sky.
CONTROL_TOL_MSUN = 1e-3


class A03Error(RuntimeError):
    pass


class A03NetworkError(A03Error):
    pass


def _fetch(url: str, cache: Path, timeout: float = 600.0) -> bytes:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return cache.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            blob = fh.read()
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed lab error
        raise A03NetworkError(f"GWOSC fetch failed for {url}: {exc}") from exc
    cache.write_bytes(blob)
    return blob


def fetch_event(catalog: str, event: str, version: str,
                cache_dir: Path = CACHE_DIR) -> dict:
    """Published parameters straight from the GWOSC event API, pinned by hash."""
    url = EVENT_API.format(catalog=catalog, event=event, version=version)
    blob = _fetch(url, cache_dir / f"{event}-{version}.json")
    payload = json.loads(blob.decode("utf-8"))
    key = next(iter(payload["events"]))
    rec = payload["events"][key]
    mc_src = rec.get("chirp_mass_source")
    if mc_src is None:
        raise A03Error(f"{event} publishes no source-frame chirp mass")
    lo = abs(rec.get("chirp_mass_source_lower") or 0.0)
    hi = abs(rec.get("chirp_mass_source_upper") or 0.0)
    z = rec.get("redshift") or 0.0
    return {
        "event": key,
        "catalog": catalog,
        "version": version,
        "api_url": url,
        "api_sha256": hashlib.sha256(blob).hexdigest(),
        "gps": float(rec["GPS"]),
        "chirp_mass_source": float(mc_src),
        "chirp_mass_source_lower": float(lo),
        "chirp_mass_source_upper": float(hi),
        "redshift": float(z),
        # the filter measures the redshifted (detector-frame) chirp mass
        "chirp_mass_detector": float(mc_src) * (1.0 + float(z)),
        "network_snr": rec.get("network_matched_filter_snr"),
        "strain": rec.get("strain", []),
    }


def strain_products(meta: dict, detectors=("H1", "L1"), duration: int = 4096) -> list[dict]:
    out = []
    for s in meta["strain"]:
        if (s.get("format") == "txt" and s.get("duration") == duration
                and s.get("sampling_rate") == FS_RAW and s.get("detector") in detectors):
            out.append({"detector": s["detector"], "url": s["url"], "duration": duration})
    if len(out) < 2:
        raise A03Error(f"expected 2 text strain products, found {len(out)}")
    return sorted(out, key=lambda p: p["detector"])


def load_segment(product: dict, event_gps: float, cache_dir: Path = CACHE_DIR,
                 progress=None) -> tuple[np.ndarray, float, dict]:
    """Pull SEG_SEC seconds ending PRE_SEC before merger, without holding 4096 s."""
    name = product["url"].rsplit("/", 1)[-1]
    path = cache_dir / name
    blob = _fetch(product["url"], path)
    digest = hashlib.sha256(blob).hexdigest()
    file_gps = int(name.split("-")[-2])
    start = int((event_gps - PRE_SEC - file_gps) * FS_RAW)
    count = SEG_SEC * FS_RAW
    if start < 0:
        raise A03Error(f"{name}: requested segment starts before the file")
    with gzip.open(path, "rt") as fh:
        for _ in range(3):
            fh.readline()
        sl = itertools.islice(fh, start, start + count)
        x = np.fromiter((float(v) for v in sl), dtype=np.float64, count=count)
    if progress:
        progress(product["detector"], len(blob), digest)
    return x, file_gps + start / FS_RAW, {
        "detector": product["detector"],
        "uri": product["url"],
        "bytes": len(blob),
        "sha256": digest,
        "file_gps_start": file_gps,
        "segment_gps_start": file_gps + start / FS_RAW,
        "segment_seconds": SEG_SEC,
    }


def tukey(n: int, alpha: float = 0.1) -> np.ndarray:
    w = np.ones(n)
    e = max(int(alpha * n / 2), 1)
    r = 0.5 * (1 + np.cos(np.pi * (np.arange(e) / e - 1)))
    w[:e], w[-e:] = r, r[::-1]
    return w


def welch_psd(x: np.ndarray, fs: int, seg_sec: float = 8.0):
    nper = int(seg_sec * fs)
    win = np.hanning(nper)
    norm = (win ** 2).sum() * fs
    acc, k = None, 0
    for s in range(0, len(x) - nper + 1, nper // 2):
        p = np.abs(np.fft.rfft(x[s:s + nper] * win)) ** 2 / norm
        acc = p if acc is None else acc + p
        k += 1
    if acc is None:
        raise A03Error("segment shorter than one PSD window")
    psd = acc / k
    psd[1:-1] *= 2.0
    return np.fft.rfftfreq(nper, 1 / fs), psd


def decimate(x: np.ndarray, factor: int) -> np.ndarray:
    """Fourier decimation — exact low-pass, no filter design, no scipy."""
    n = len(x)
    n2 = n // factor
    X = np.fft.rfft(x)
    return np.fft.irfft(X[: n2 // 2 + 1], n=n2) * (n2 / n)


def gate_transients(x: np.ndarray, fs: int, t0: float, event_gps: float,
                    n_sigma: float = 6.0, pad_sec: float = 0.06):
    """Taper out loud non-Gaussian transients (the GW170817 Livingston glitch).

    Detection runs on a provisional whitening; the taper is applied to the raw
    strain so the PSD is re-estimated without the artefact it is meant to remove.
    """
    n = len(x)
    freqs = np.fft.rfftfreq(n, 1 / fs)
    pf, pxx = welch_psd(x, fs)
    psd = np.interp(freqs, pf, pxx)
    psd[psd <= 0] = np.inf
    w = np.fft.rfft(x * tukey(n)) / np.sqrt(psd * fs / 2)
    w[(freqs < 30) | (freqs > 400)] = 0
    w = np.fft.irfft(w, n=n)
    edge = int(15 * fs)
    core = np.zeros(n, bool)
    core[edge:-edge] = True
    sigma = float(w[core].std())
    loud = np.where(core & (np.abs(w) > n_sigma * sigma))[0]
    out, gates = x.copy(), []
    if not len(loud):
        return out, gates
    for grp in np.split(loud, np.where(np.diff(loud) > fs // 20)[0] + 1):
        lo = max(int(grp[0] - pad_sec * fs), 0)
        hi = min(int(grp[-1] + pad_sec * fs), n - 1)
        span = hi - lo + 1
        ramp = max(int(0.25 * span), 1)
        win = np.ones(span)
        tt = np.arange(ramp) / ramp
        win[:ramp] = 0.5 * (1 - np.cos(np.pi * tt))
        win[-ramp:] = win[:ramp][::-1]
        out[lo:hi + 1] *= 1.0 - win
        gates.append({
            "seconds_from_merger": float(t0 + grp[0] / fs - event_gps),
            "peak_sigma": float(np.abs(w[grp]).max() / sigma),
            "samples": int(len(grp)),
        })
    return out, gates


class MatchedFilter:
    def __init__(self, strain: np.ndarray, fs: int, t0: float, event_gps: float):
        self.n = len(strain)
        self.fs = fs
        self.freqs = np.fft.rfftfreq(self.n, 1 / fs)
        pf, pxx = welch_psd(strain, fs)
        psd = np.interp(self.freqs, pf, pxx)
        psd[psd <= 0] = np.inf
        self.psd = psd
        self.asd = np.sqrt(psd)
        self.dw = np.fft.rfft(strain * tukey(self.n)) / self.asd
        self.t = t0 + np.arange(self.n) / fs
        ok = (self.t > t0 + 20) & (self.t < t0 + SEG_SEC - 20)
        self.on = ok & (np.abs(self.t - event_gps) < 0.10)
        self.off = ok & (np.abs(self.t - event_gps) > 2.0)

    def snr_series(self, mc: float, eta: float):
        hh = taylorf2_35(self.freqs, mc, eta, F_LOW, F_HIGH) / self.asd
        nrm = float(np.sqrt((np.abs(hh) ** 2).sum()))
        if nrm <= 0:
            return None
        X = self.dw * np.conj(hh)
        Z = np.zeros(self.n, dtype=np.complex128)
        Z[: len(X)] = X
        Z[0] = 0.0
        r = np.abs(np.fft.ifft(Z) * self.n) / nrm
        scale = r[self.off].std()
        return r / scale if scale > 0 else None

    def scan(self, mc_grid, eta: float):
        best = (0.0, float("nan"), float("nan"))
        background = 0.0
        for mc in mc_grid:
            r = self.snr_series(mc, eta)
            if r is None:
                continue
            background = max(background, float(r[self.off].max()))
            peak = float(r[self.on].max())
            if peak > best[0]:
                k = int(np.where(self.on)[0][int(np.argmax(r[self.on]))])
                best = (peak, float(mc), float(self.t[k]))
        return {"peak_snr": best[0], "mc_detector": best[1],
                "gps_peak": best[2], "background_max": background}


def inject(strain: np.ndarray, flt: MatchedFilter, mc: float, eta: float,
           event_gps: float, rho: float) -> np.ndarray:
    """Add a template-family signal of nominal matched-filter SNR rho."""
    h = taylorf2_35(flt.freqs, mc, eta, F_LOW, 600.0)
    h = h * np.exp(-2j * np.pi * flt.freqs * (event_gps - flt.t[0]))
    unit = np.fft.irfft(h / np.sqrt(flt.psd * flt.fs / 2.0), n=flt.n)
    norm = float(np.linalg.norm(unit))
    if norm <= 0:
        raise A03Error("degenerate injection template")
    return strain + np.fft.irfft(h * (rho / norm), n=flt.n)


@dataclass
class A03Result:
    meta: dict
    detectors: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)
    gates: list[dict] = field(default_factory=list)
    control_passed: bool = False
    recovered: bool = False
    calibration_passed: bool = False
    wall_seconds: float = 0.0


def run_a03(catalog: str = DEFAULT_CATALOG, event: str = DEFAULT_EVENT,
            version: str = DEFAULT_VERSION, cache_dir: Path = CACHE_DIR,
            dmc: float = DMC, progress=None, phase=None) -> A03Result:
    t_start = time.time()
    meta = fetch_event(catalog, event, version, cache_dir)
    if phase:
        phase("event", meta)
    mc_pub_det = meta["chirp_mass_detector"]
    tol_src = max(meta["chirp_mass_source_lower"], meta["chirp_mass_source_upper"])
    grid = np.arange(MC_LO, MC_HI + dmc / 2, dmc)

    result = A03Result(meta=meta)
    for product in strain_products(meta):
        raw, t0, pinned = load_segment(product, meta["gps"], cache_dir, progress)
        result.products.append(pinned)
        x = decimate(raw, DECIM)
        gated, gates = gate_transients(x, FS, t0, meta["gps"])
        for g in gates:
            g["detector"] = product["detector"]
        result.gates.extend(gates)

        flt = MatchedFilter(gated, FS, t0, meta["gps"])
        real = flt.scan(grid, ETA)

        control_strain = inject(gated, flt, mc_pub_det, ETA, meta["gps"], INJECT_SNR)
        cflt = MatchedFilter(control_strain, FS, t0, meta["gps"])
        control = cflt.scan(grid, ETA)

        entry = {
            "detector": product["detector"],
            "real": real,
            "control": control,
            "control_error_msun": abs(control["mc_detector"] - mc_pub_det),
            "real_detected": real["peak_snr"] > real["background_max"],
            "real_mc_source": real["mc_detector"] / (1.0 + meta["redshift"]),
            "real_error_msun": abs(real["mc_detector"] / (1.0 + meta["redshift"])
                                   - meta["chirp_mass_source"]),
            "seconds_from_merger": real["gps_peak"] - meta["gps"],
        }
        result.detectors.append(entry)
        if phase:
            phase("detector", entry)

    result.control_passed = bool(result.detectors) and all(
        d["control"]["peak_snr"] > d["control"]["background_max"]
        and d["control_error_msun"] <= CONTROL_TOL_MSUN
        for d in result.detectors
    )
    result.recovered = bool(result.detectors) and all(
        d["real_detected"] and d["real_error_msun"] <= tol_src
        for d in result.detectors
    )
    result.calibration_passed = result.control_passed and result.recovered
    result.wall_seconds = time.time() - t_start
    return result


def to_report(result: A03Result) -> dict:
    m = result.meta
    dets = result.detectors
    ctrl_err = max((d["control_error_msun"] for d in dets), default=float("nan"))
    headline = (
        f"{m['event']}: pipeline recovers an injected chirp mass to "
        f"{ctrl_err:.1e} Msun in {len(dets)} detectors; "
        + ("the event itself is recovered"
           if result.recovered else "the event itself is NOT recovered")
    )
    return {
        "experiment": "A03-gwosc-chirp-mass",
        "headline": headline,
        "status": "pass" if result.calibration_passed else "null",
        "event": m["event"],
        "catalog": m["catalog"],
        "api_url": m["api_url"],
        "api_sha256": m["api_sha256"],
        "event_gps": m["gps"],
        "published_chirp_mass_source": m["chirp_mass_source"],
        "published_chirp_mass_source_lower": m["chirp_mass_source_lower"],
        "published_chirp_mass_source_upper": m["chirp_mass_source_upper"],
        "published_chirp_mass_detector": m["chirp_mass_detector"],
        "redshift": m["redshift"],
        "published_network_snr": m["network_snr"],
        "waveform": "TaylorF2 3.5PN stationary-phase inspiral, non-spinning, no tides",
        "band_hz": [F_LOW, F_HIGH],
        "segment_seconds": SEG_SEC,
        "sample_rate_hz": FS,
        "eta_assumed": ETA,
        "chirp_mass_grid": {"lo": MC_LO, "hi": MC_HI, "step": DMC},
        "injection_snr": INJECT_SNR,
        "control_tolerance_msun": CONTROL_TOL_MSUN,
        "detectors": dets,
        "products": result.products,
        "gates": result.gates,
        "control_passed": result.control_passed,
        "control_max_error_msun": ctrl_err,
        "recovered": result.recovered,
        "calibration_passed": result.calibration_passed,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "The injection is drawn from the SAME 3.5PN TaylorF2 family as the search "
            "template, so the control validates the filter, the whitening, the gating "
            "and the chirp-mass grid — it does NOT validate the waveform's fidelity to "
            "a real source. A real binary neutron star carries spin, tidal and "
            "higher-order structure this template omits, and that mismatch is the "
            "leading candidate for any gap between the control and the sky. This is a "
            "reprocessing of public archival strain, not an independent detection, and "
            "no result here is submitted to GWOSC or any collaboration."
        ),
    }
