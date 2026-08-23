"""A02 — recover a known variable star's period from TESS photometry, blind.

The claim is RECOVERY, in A04's sense: the search is never told what it is
looking for. A predeclared list of *names* goes in; for each one the pipeline
resolves coordinates, finds the star's TESS SPOC photometry, and measures the
dominant frequency from the light curve alone. The catalogued period is read
**only at grading time**, from AAVSO's Variable Star Index — which is also this
milestone's venue, so the instrument is graded against the community it reports
to.

Why the sample is names and not TIC ids: a TIC id is already an answer to the
question "which star is this?", and half of A05's refutations were that question
answered wrongly. Starting from the name and resolving forward means the
resolution step is part of what gets graded.

WHAT IS GRADED
    Per target, the blind period against VSX's, with the bar derived rather
    than chosen: one Rayleigh resolution element, ``δP = P²/T_baseline`` — the
    smallest period difference a baseline of that length can distinguish at
    all. A run that beats its own resolution by an order of magnitude is
    reporting that fact, not being graded on it.

    Plus a control per target: the same flux, shuffled against the same
    timestamps. It destroys the coherence and keeps the noise, so its strongest
    peak measures what this cadence pattern produces from nothing. A real
    detection has to stand above it by a declared margin.

WHAT IS NOT CLAIMED
    Not a discovery of anything, not a new period for any star, and not the
    AAVSO half of A02 — registering an observer code and submitting a validated
    observation is an account action a human takes, and it stays open.

    Amplitudes are reported, never graded: SPOC's PDCSAP is corrected for
    crowding and systematics in ways that are appropriate for transits and only
    approximately right for a high-amplitude pulsator.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import a01, a05, a05_vetting
from .labhome import LAB_HOME

CACHE_DIR = LAB_HOME / "cache" / "a02"

#: The sample, declared as NAMES before any period was looked at. Four pulsator
#: classes so the recovery is not a property of one light-curve shape:
#: an RR Lyrae (with Blazhko modulation, deliberately — see BLAZHKO below), a
#: β Cephei, and four SX Phoenicis / high-amplitude δ Scuti stars whose periods
#: run down to 79 minutes.
TARGETS: tuple[str, ...] = (
    "RR Lyr",     # RRAB/BL  — the archetype, and the hardest case here
    "beta Cep",   # BCEP     — the class prototype
    "XX Cyg",     # SXPHE
    "AI Vel",     # HADS(B)
    "SX Phe",     # SXPHE(B) — the class prototype
    "AE UMa",     # SXPHE(B)
)

#: Search band in cycles/day. Wide enough to hold everything from a 20-day
#: binary to a 12-minute pulsation, and deliberately NOT tuned to the sample:
#: every target's answer sits far inside it, and the band was fixed before any
#: spectrum was computed.
F_LO_CPD = 0.05
F_HI_CPD = 120.0

#: Oversampling of the frequency grid relative to 1/T. The peak is refined
#: below the grid by parabolic interpolation, so this only has to be fine
#: enough that the three points around the maximum are on the peak.
OVERSAMPLE = 10

#: A detection must stand this far above its own shuffled control's strongest
#: peak. Declared before measurement; the achieved margins are reported.
CONTROL_MARGIN = 3.0

#: Frequencies within this fraction of the peak are excluded when measuring the
#: local noise floor, so a broad peak does not inflate its own baseline.
FLOOR_EXCLUSION = 0.02

#: Blazhko stars amplitude- and phase-modulate over tens to hundreds of days,
#: so a single 27-day sector measures that sector's period, not the mean the
#: catalogue publishes. RR Lyr is in the sample ON PURPOSE — a pipeline that
#: only recovers clean sinusoids has not been tested — and its residual is
#: expected to be the largest of the six.
BLAZHKO_TYPES = ("BL",)

VSX_API = "https://www.aavso.org/vsx/index.php"
_UA = "windowsill-lab/A02 (research; github.com/benskamps/windowsill-lab)"


# ── catalogue side (read at grading time only) ───────────────────────────────

def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def fetch_vsx(ident: str, cache_dir: Path = CACHE_DIR,
              timeout: float = 45.0) -> tuple[dict, dict]:
    """VSX's record for ``ident``, plus provenance pinning the exact bytes.

    Cached: a rerun re-derives from the same response rather than whatever the
    catalogue says today, so ``check_a02`` can grade offline and a period
    revised upstream shows up as a deliberate re-fetch instead of a silent
    change under a published number.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = ident.replace(" ", "_").replace("/", "-")
    path = cache_dir / f"vsx-{safe}.json"
    if path.exists():
        blob = path.read_bytes()
    else:
        url = VSX_API + "?" + urllib.parse.urlencode(
            {"view": "api.object", "ident": ident, "format": "json"})
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read()
        path.write_bytes(blob)
    record = (json.loads(blob.decode("utf-8")) or {}).get("VSXObject") or {}
    prov = {"source": "AAVSO VSX api.object", "ident": ident,
            "cache_file": path.name, "sha256": _sha256(blob)}
    return record, prov


def resolve_tess(ra_deg: float, dec_deg: float, radius_deg: float = 0.02,
                 deadline: float | None = None) -> dict:
    """The TESS SPOC timeseries at this position: TIC id and sectors.

    A cone rather than a name lookup, because MAST indexes TESS observations by
    TIC and the question "which TIC is this star" is exactly the one A05 got
    wrong on TIC 77044472. A cone that lands on two TICs is reported as
    ambiguous and refused, never silently resolved to the first row.
    """
    rows = a01._mast("Mast.Caom.Filtered.Position", {
        "columns": "target_name,sequence_number,provenance_name",
        "filters": [
            {"paramName": "obs_collection", "values": ["TESS"]},
            {"paramName": "dataproduct_type", "values": ["timeseries"]},
            {"paramName": "provenance_name", "values": ["SPOC"]},
        ],
        "position": f"{ra_deg}, {dec_deg}, {radius_deg}",
    }, deadline=deadline)
    tics: dict[str, set] = {}
    for row in rows:
        tic = str(row.get("target_name") or "").strip()
        sector = row.get("sequence_number")
        if not tic:
            continue
        tics.setdefault(tic, set())
        if isinstance(sector, int) and sector > 0:
            tics[tic].add(sector)
    if not tics:
        return {"tic": None, "sectors": [], "reason": "no SPOC timeseries within the cone"}
    if len(tics) > 1:
        return {"tic": None, "sectors": [],
                "reason": f"ambiguous: {len(tics)} TICs in the cone ({', '.join(sorted(tics))})"}
    tic, sectors = next(iter(tics.items()))
    return {"tic": tic, "sectors": sorted(sectors), "reason": None}


# ── measurement side (blind) ─────────────────────────────────────────────────

def refine_peak(freqs: np.ndarray, amps: np.ndarray, k: int) -> float:
    """Sub-grid frequency of the peak at index ``k`` by parabolic interpolation.

    Three points around a maximum determine a parabola, and its vertex is a far
    better estimate than the grid point itself: on a 27-day baseline the grid
    step alone caps the period at ~1e-3 relative, which is the resolution of the
    GRID and not of the DATA. Falls back to the grid point at an edge.
    """
    if k <= 0 or k >= len(amps) - 1:
        return float(freqs[k])
    y0, y1, y2 = float(amps[k - 1]), float(amps[k]), float(amps[k + 1])
    denom = y0 - 2.0 * y1 + y2
    if denom == 0.0:
        return float(freqs[k])
    delta = 0.5 * (y0 - y2) / denom
    if not (-1.0 < delta < 1.0):
        return float(freqs[k])
    step = float(freqs[1] - freqs[0])
    return float(freqs[k]) + delta * step


def measure(t: np.ndarray, flux: np.ndarray, *, seed: int,
            f_lo: float = F_LO_CPD, f_hi: float = F_HI_CPD,
            oversample: int = OVERSAMPLE) -> dict:
    """Dominant frequency, its strength, and the shuffled control — one target.

    The control shuffles the flux against the same timestamps with a seeded
    permutation: identical values, identical sampling, coherence destroyed. Its
    strongest peak is what this cadence pattern manufactures from noise alone.
    """
    t = np.asarray(t, dtype=float)
    flux = np.asarray(flux, dtype=float)
    freqs, amps = a05_vetting.amplitude_spectrum(
        t, flux, f_lo=f_lo, f_hi=f_hi, oversample=oversample)
    k = int(np.argmax(amps))
    nu = refine_peak(freqs, amps, k)
    peak_amp = float(amps[k])

    # Local floor: everything outside a small exclusion around the peak.
    away = np.abs(freqs - freqs[k]) > FLOOR_EXCLUSION * max(freqs[k], 1e-9)
    floor = float(np.median(amps[away])) if away.any() else float("nan")

    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(flux)
    _cf, camps = a05_vetting.amplitude_spectrum(
        t, shuffled, f_lo=f_lo, f_hi=f_hi, oversample=oversample)
    control_amp = float(np.max(camps))

    return {
        "frequency_cpd": nu,
        "period_days": float(1.0 / nu) if nu > 0 else float("nan"),
        "grid_frequency_cpd": float(freqs[k]),
        "peak_amplitude": peak_amp,
        "noise_floor": floor,
        "peak_over_floor": peak_amp / floor if floor and floor > 0 else float("nan"),
        "control_peak_amplitude": control_amp,
        "control_margin": peak_amp / control_amp if control_amp > 0 else float("nan"),
        "control_seed": int(seed),
        "baseline_days": float(t.max() - t.min()),
        "cadences": int(len(t)),
        "band_cpd": [float(f_lo), float(f_hi)],
    }


def rayleigh_period_resolution(period_days: float, baseline_days: float) -> float:
    """δP = P²/T — the smallest period difference this baseline can resolve."""
    if baseline_days <= 0:
        return float("nan")
    return float(period_days * period_days / baseline_days)


def harmonic_relation(measured_p: float, published_p: float) -> str | None:
    """``None`` when the measurement is the published period itself.

    An amplitude spectrum peaks where the POWER is, which for an eclipsing
    binary is twice the orbital frequency and for a strongly non-sinusoidal
    pulsator can be a harmonic. Naming the ratio is the difference between a
    recovery and a near-miss dressed as one.
    """
    if not (measured_p > 0 and published_p > 0):
        return None
    for num, den, label in ((1, 2, "P/2 — the first harmonic"),
                            (2, 1, "2P — the subharmonic"),
                            (1, 3, "P/3"), (3, 1, "3P")):
        target = published_p * num / den
        if abs(measured_p - target) / target < 0.01:
            return label
    return None


# ── the run ──────────────────────────────────────────────────────────────────

@dataclass
class A02Result:
    targets: list[dict] = field(default_factory=list)
    generated_at: str = ""

    @property
    def graded(self) -> list[dict]:
        return [row for row in self.targets if row.get("outcome") == "measured"]

    @property
    def passed(self) -> bool:
        rows = self.graded
        return bool(rows) and all(row["within_resolution"] and row["control_clear"]
                                  for row in rows)


def run_a02(targets: tuple[str, ...] = TARGETS, cache_dir: Path = CACHE_DIR,
            deadline: float | None = None, on_row=None) -> A02Result:
    """Resolve, measure blind, then grade against VSX. One sector per target.

    The sector is the LOWEST available, fixed by rule rather than chosen after
    seeing results — picking the sector that grades best would make the sample
    a selection instead of a measurement.
    """
    result = A02Result(generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    for index, ident in enumerate(targets):
        row: dict = {"ident": ident}
        try:
            record, prov = fetch_vsx(ident, cache_dir=cache_dir)
            row["vsx"] = {
                "name": record.get("Name"), "auid": record.get("AUID"),
                "type": record.get("VariabilityType"),
                "period_days": float(record["Period"]) if record.get("Period") else None,
                "provenance": prov,
            }
            ra, dec = record.get("RA2000"), record.get("Declination2000")
            if row["vsx"]["period_days"] is None or ra is None or dec is None:
                row["outcome"] = "skipped-no-catalogue-period"
                result.targets.append(row)
                continue
            found = resolve_tess(float(ra), float(dec), deadline=deadline)
            row["tic"], row["sectors"] = found["tic"], found["sectors"]
            if found["tic"] is None or not found["sectors"]:
                row["outcome"] = "skipped-no-tess-photometry"
                row["reason"] = found["reason"]
                result.targets.append(row)
                continue
            sector = found["sectors"][0]
            row["sector"] = sector
            curve = a05.load_curve(row["tic"], sector)
            if curve is None:
                row["outcome"] = "skipped-no-product"
                result.targets.append(row)
                continue
            row["photometry"] = {"cache_file": curve.get("cache_file"),
                                 "sha256": curve.get("sha256")}
            meas = measure(curve["t"], curve["f"], seed=1000 + index)
            row.update(meas)

            published = row["vsx"]["period_days"]
            row["published_period_days"] = published
            row["abs_error_days"] = abs(meas["period_days"] - published)
            row["rel_error"] = row["abs_error_days"] / published
            row["resolution_days"] = rayleigh_period_resolution(
                published, meas["baseline_days"])
            row["within_resolution"] = bool(
                row["abs_error_days"] <= row["resolution_days"])
            row["resolution_beat_factor"] = (
                row["resolution_days"] / row["abs_error_days"]
                if row["abs_error_days"] > 0 else float("inf"))
            row["harmonic"] = harmonic_relation(meas["period_days"], published)
            row["control_clear"] = bool(meas["control_margin"] >= CONTROL_MARGIN)
            row["blazhko"] = any(tag in (row["vsx"]["type"] or "")
                                 for tag in BLAZHKO_TYPES)
            row["outcome"] = "measured"
        except Exception as exc:  # noqa: BLE001 — one star never sinks the run
            row["outcome"] = f"error:{type(exc).__name__}"
            row["error"] = str(exc)[:200]
        result.targets.append(row)
        if on_row:
            on_row(row)
    return result


def to_report(result: A02Result) -> dict:
    graded = result.graded
    return {
        "milestone": "A02",
        "experiment": "A02-variable-star-recovery",
        "schema": 1,
        # The permanent-report slug is derived from an UPPERCASE milestone
        # prefix on `experiment` (publish._slug_for). Tagged lowercase, this
        # receipt landed in the generic "run" bucket on its first real run —
        # which would also have entered the planner's ledger as a milestone
        # called "run", since that ledger keys on the same slug.

        "generated_at": result.generated_at,
        "band_cpd": [F_LO_CPD, F_HI_CPD],
        "control_margin_required": CONTROL_MARGIN,
        "counts": {
            "declared": len(result.targets),
            "measured": len(graded),
            "within_resolution": sum(1 for r in graded if r["within_resolution"]),
            "control_clear": sum(1 for r in graded if r["control_clear"]),
        },
        "targets": result.targets,
    }
