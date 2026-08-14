"""A05 lane 3 — per-host sensitivity, the epoch-scramble placebo, the dossier.

The pilot's defect sits at the top of this file: a survey-wide binary control
turned one host's unlucky photometry into ``control_passed: false`` on a
healthy hunt. The repair is per-host sensitivity — a miss is a MEASUREMENT
that weakens that host's d_min, never a verdict on the pipeline.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lab import a01, a04, a05_sensitivity as a05s

CACHE = Path.home() / ".lab" / "cache" / "a01"


def _cached(tic: str) -> Path:
    return CACHE / f"tess2018234235059-s0002-{int(tic):016d}-0121-s_lc.fits"


def _load(tic: str) -> tuple[np.ndarray, np.ndarray]:
    t, f = a01._normalise(a01.read_tess_light_curve(_cached(tic).read_bytes()))
    return a04.detrend(t, f)


def _flat(days=27.0, cadence=2.0 / 1440, noise=1e-4, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence)
    return t, 1.0 + rng.normal(0.0, noise, size=len(t))


# ------------------------------------------------------- per-host d_min ---

@pytest.mark.skipif(not _cached("259847258").exists(),
                    reason="publisher-local cache")
def test_tic259847258_reports_dmin_miss():
    """The target this lane is named for: on its real photometry the 0.2 %
    injection at 5.1 d is NOT recovered, so d_min at 5.1 d must weaken to
    reflect it — while the host stays counted, because 1.0 % recovers at every
    period. The pilot's binary control called this exact situation a pipeline
    failure; the per-host ladder calls it what it is: a measurement."""
    t, f = _load("259847258")
    rows = a05s.injection_grid(t, f)
    host = a05s.host_sensitivity(rows)
    deep = [r for r in rows
            if r["depth"] == 0.002 and r["period_days"] == 5.1]
    assert deep and not all(r["recovered"] for r in deep)
    assert host["d_min"]["5.1"] is not None
    assert host["d_min"]["5.1"] > 0.002
    assert host["insensitive"] is False           # 1.0 % recovers everywhere
    stmt = a05s.null_statement(host)
    assert "no candidate at FAP <=" in stmt
    assert "sensitive to depth >=" in stmt


def test_quiet_host_recovers_the_full_ladder():
    """A clean, quiet host must measure d_min = 0.2 % at every ladder period —
    otherwise the ladder itself is eating sensitivity and every per-host limit
    is biased pessimistic. Runs at the pipeline's real grid density — a
    thinned grid depressed the 5.1 d SDE from 9.3 to 8.0 and manufactured a
    miss."""
    t, f = _flat(noise=1e-4, seed=2)
    rows = a05s.injection_grid(t, f)
    assert all(r["recovered"] for r in rows)
    host = a05s.host_sensitivity(rows)
    assert host["insensitive"] is False
    for p in a05s.PERIODS:
        assert host["d_min"][f"{p}"] == pytest.approx(min(a05s.DEPTHS))


def test_noisy_host_is_flagged_insensitive_and_excluded():
    """Photometry that cannot see a 1 % transit supports no null statement.
    The host is flagged, refused a statement, and excluded from aggregates —
    the OPPOSITE failure mode of averaging blind hosts into a survey claim."""
    t, f = _flat(noise=0.05, seed=3)
    ladder = tuple((a05s.INSENSITIVE_DEPTH, p) for p in a05s.PERIODS)
    rows = a05s.injection_grid(t, f, ladder=ladder, n_periods=600)
    host = a05s.host_sensitivity(rows)
    host["tic"] = "noisy"
    assert host["insensitive"] is True
    assert "no null statement" in a05s.null_statement(host)

    quiet = {"tic": "quiet", "insensitive": False,
             "d_min": {f"{p}": 0.002 for p in a05s.PERIODS}}
    agg = a05s.aggregate_sensitivity([quiet, host])
    assert agg["n_hosts"] == 2
    assert agg["n_sensitive"] == 1
    assert agg["excluded"] == ["noisy"]
    for p in a05s.PERIODS:                 # aggregate reflects ONLY the quiet host
        assert agg["d_min_worst"][f"{p}"] == 0.002


# ------------------------------------------------------------- placebo ---

def test_epoch_scramble_preserves_cadence_and_flux_multiset():
    t, f = _flat(days=2.0, seed=4)
    ts, fs = a05s.epoch_scramble(t, f, seed=7)
    assert np.array_equal(ts, t)                       # times untouched
    assert np.array_equal(np.sort(fs), np.sort(f))     # same values, new order
    assert not np.array_equal(fs, f)                   # coherence destroyed


@pytest.mark.skipif(not _cached("358460464").exists(),
                    reason="publisher-local cache")
def test_scrambled_eb_yields_zero_planet_candidates():
    """TIC 358460464 is a real eclipsing binary — unscrambled it clears the
    SDE threshold. Permuting its flux against its own cadence times must leave
    the FULL ladder (search + vetting) with nothing: any planet-candidate
    surfaced from a phase-incoherent sky is a manufactured discovery."""
    t, f = _load("358460464")
    assert a04.blind_search(t, f).sde >= a04.SDE_THRESHOLD    # the real signal
    out = a05s.scramble_placebo([("358460464", t, f)])
    assert out["n_scrambled"] == 1
    assert out["planet_candidates"] == 0
    assert out["pass"] is True


# ------------------------------------------------------------- dossier ---

def test_dossier_carries_every_panel_and_stays_machine_terminal():
    t, f = _flat(noise=3e-4, seed=5)
    fi = a04.inject_box(t, f, period=3.1, depth=0.01, duration_days=2.5 / 24)
    det = a04.blind_search(t, fi, n_periods=600)
    assert det.sde >= a04.SDE_THRESHOLD          # a genuine surviving lead
    panels, html = a05s.dossier(t, fi, det)

    for key in a05s.DOSSIER_REQUIRED_PANELS:
        assert key in panels, key
    assert panels["status"] == "lead-awaiting-human-review"
    assert all(r["recovered"] for r in panels["self_injection"])
    assert len(panels["fold_p"]["flux"]) == a05s.FOLD_BINS
    assert panels["fold_half_p"]["period_days"] == pytest.approx(
        det.period_days / 2)

    # Self-contained: renders on an air-gapped machine in ten years.
    low = html.lower()
    for needle in ("http://", "https://", "file://", "src=", "href=", "@import"):
        assert needle not in low, needle
    assert "lead-awaiting-human-review" in html
    assert "<svg" in html and "polyline" in html
