"""A05 lane-4 tests — the receipt is re-derivable or it is nothing.

The fixture runs the WHOLE pipeline (synthetic FITS on disk -> loader ->
prewhiten -> blind search -> stage-2 FAP -> disposition ladder -> receipt)
once per module, then every adversarial test hand-edits a JSON copy of that
receipt and asserts ``check_a05`` reacts the contract's way:

* broken/absent evidence -> ``None`` (unreadable, never negative),
* evidence that contradicts itself -> ``False`` (fabricated, never absent),
* the honest receipt -> ``True`` with a bitwise spot reproduction.

No network, no publisher cache: the FITS bytes are synthesized in tmp and
pinned by SHA-256 exactly like the real cache, so CI exercises the full
trust chain including the spot-reproduction gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from lab import a04, a05, checks

# Small-but-honest scale: 27 d baseline (real sector length) at 7.2-minute
# cadence, 300-period grid, B=64 permutations — the coarsest configuration
# the check's own floors (A05_MIN_B, uniformity n) accept.
DAYS, CADENCE, N_PERIODS, B = 27.0, 0.005, 300, 64
#: Planted short-period transit: ~30 events in the baseline gives the peak
#: the sharpness a coarse 300-period grid needs to clear SDE 8.
PLANT_PERIOD, PLANT_DEPTH = 0.9, 0.01
TICS = [str(n) for n in range(901, 911)]        # 901, 902 planted; rest quiet
PLANTED = ("901", "902")


# ------------------------------------------------------- synthetic FITS ------

def _card(key: str, value, comment: str = "") -> str:
    if isinstance(value, str):
        val = f"'{value}'".ljust(20)
    elif isinstance(value, bool):
        val = ("T" if value else "F").rjust(20)
    elif isinstance(value, float):
        val = f"{value:.10G}".rjust(20)
    else:
        val = str(value).rjust(20)
    return (f"{key:<8}= {val} / {comment}")[:80].ljust(80)


def _pad(block: bytes) -> bytes:
    rem = len(block) % 2880
    return block if rem == 0 else block + b" " * (2880 - rem)


def fits_bytes(t: np.ndarray, f: np.ndarray, crowdsap: float = 0.95) -> bytes:
    """A minimal SPOC-shaped light-curve FITS the lab's own reader accepts."""
    n = len(t)
    primary = (_card("SIMPLE", True) + _card("BITPIX", 8) +
               _card("NAXIS", 0) + "END".ljust(80)).encode("ascii")
    cols = [("TIME", "D"), ("PDCSAP_FLUX", "D"),
            ("PDCSAP_FLUX_ERR", "D"), ("QUALITY", "J")]
    dtype = np.dtype([(name, ">f8" if form == "D" else ">i4")
                      for name, form in cols])
    data = np.zeros(n, dtype=dtype)
    data["TIME"] = t
    data["PDCSAP_FLUX"] = f
    data["PDCSAP_FLUX_ERR"] = 3e-4
    hdr = (_card("XTENSION", "BINTABLE") + _card("BITPIX", 8) +
           _card("NAXIS", 2) + _card("NAXIS1", dtype.itemsize) +
           _card("NAXIS2", n) + _card("PCOUNT", 0) + _card("GCOUNT", 1) +
           _card("TFIELDS", len(cols)))
    for i, (name, form) in enumerate(cols, start=1):
        hdr += _card(f"TTYPE{i}", name) + _card(f"TFORM{i}", form)
    hdr += _card("CROWDSAP", float(crowdsap))
    hdr += "END".ljust(80)
    return _pad(primary) + _pad(hdr.encode("ascii")) + _pad(data.tobytes())


def _fname(tic: str) -> str:
    return f"tess2018234235059-s0002-{int(tic):016d}-0121-s_lc.fits"


def _synth(seed: int, depth: float = 0.0, days: float = DAYS,
           cadence: float = CADENCE) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence)
    f = 1.0 + rng.normal(0.0, 3e-4, len(t))
    if depth:
        f = a04.inject_box(t, f, PLANT_PERIOD, depth, duration_days=2.5 / 24)
    return t, f


def _write_cache(cache: Path, tics, days: float = DAYS,
                 cadence: float = CADENCE) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for tic in tics:
        depth = PLANT_DEPTH if tic in PLANTED else 0.0
        t, f = _synth(int(tic), depth=depth, days=days, cadence=cadence)
        (cache / _fname(tic)).write_bytes(fits_bytes(t, f))


def _loader(cache: Path):
    def load(tic: str) -> dict:
        curve = a05.curve_from_blob((cache / _fname(tic)).read_bytes())
        curve["cache_file"] = _fname(tic)
        return curve
    return load


def _catalog(tic: str) -> dict:
    """Offline stand-in for the TAP cross-check. TIC 902 replays the field
    fact that motivated the toi-known-fp rule: vetting says planet-candidate,
    the TOI table says TFOPWG disposition FP (the TOI 189.01 case)."""
    if tic == "902":
        return {"tic": tic, "known_toi": "189.01", "known_planet": None,
                "published_period_days": 0.9015, "disposition": "FP"}
    return {"tic": tic, "known_toi": None, "known_planet": None,
            "published_period_days": None, "disposition": None}


# ------------------------------------------------------------- the fixture --

@pytest.fixture(scope="module")
def hunt(tmp_path_factory):
    cache = tmp_path_factory.mktemp("a01-cache")
    _write_cache(cache, TICS)
    result = a05.run_a05(
        sector=2, targets=TICS, curve_loader=_loader(cache),
        catalog=_catalog, B=B, n_periods=N_PERIODS,
        control_fraction=1.0,          # every target predeclared into the
        n_placebo=2,                   # uniformity control ensemble
        prewhiten_kwargs={"f_hi": 45.0},
        soft_budget_seconds=1200.0, per_target_share=0.2,
        hunt_id="hunt-test-s2")
    report = a05.to_report(result)
    return {"result": result, "report": report, "cache": cache}


def _mut(report: dict) -> dict:
    """A deep JSON copy to hand-edit — also proves the receipt serializes."""
    return json.loads(json.dumps(report))


def _stage2_rows(report: dict) -> list[dict]:
    return [r for r in report["targets"]
            if r.get("outcome") == "searched" and r.get("stage2")]


# ------------------------------------------------- (1) honest end to end -----

def test_e2e_receipt_passes_check_a05(hunt):
    ok, detail = checks.check_a05(hunt["report"], cache_dir=hunt["cache"])
    assert ok is True, detail
    assert "spot" in detail


def test_e2e_receipt_shape(hunt):
    report = hunt["report"]
    counts = report["counts"]
    assert counts["attempted"] == len(TICS)
    assert counts["searched"] == len(TICS)
    assert counts["above_threshold"] == 2          # the two planted transits
    assert counts["dispositioned"] == 2
    assert counts["leads_awaiting_human_review"] == 1
    lead = next(r for r in report["targets"] if r["tic"] == "901")
    assert lead["disposition"] == "lead-awaiting-human-review"
    for panel in ("fold_p", "fold_half_p", "fold_2p", "odd_even",
                  "secondary", "self_injection", "amplitude_spectrum"):
        assert panel in lead["dossier"], panel
    assert hunt["result"].dossiers["901"].startswith("<!doctype html>")
    # floor history: both prior points survive, this run appended its own.
    sources = [h["source"] for h in report["floor_history"]]
    assert sources[:2] == ["run-2026-08-08-2338-a04", "hunt-2026-08-14-s2"]
    assert sources[-1] == "hunt-test-s2"
    # graded FAP is the conservative max, per row.
    for r in _stage2_rows(report):
        schemes = r["fap"]["schemes"]
        assert r["fap"]["fap_graded"] == max(
            schemes["iid"]["fap_empirical"], schemes["block"]["fap_empirical"])


# ------------------------------------- (2) every broken control reads None ---

def test_stripped_maxima_is_none_not_false(hunt):
    bad = _mut(hunt["report"])
    del _stage2_rows(bad)[2]["fap"]["schemes"]["iid"]["raw_maxima"]
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is None and "maxima" in detail


def test_corrupt_cache_sha_is_none_not_false(hunt):
    bad = _mut(hunt["report"])
    for r in bad["targets"]:
        if r.get("cache_sha256"):
            r["cache_sha256"] = "0" * 64
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is None and "sha256 mismatch" in detail


def test_undispositioned_hit_is_none_not_false(hunt):
    bad = _mut(hunt["report"])
    row = next(r for r in bad["targets"] if r["tic"] == "901")
    row["disposition"] = None
    bad["counts"]["dispositioned"] -= 1
    bad["counts"]["leads_awaiting_human_review"] -= 1
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is None and "no machine disposition" in detail


def test_missing_injections_is_none_not_false(hunt):
    bad = _mut(hunt["report"])
    _stage2_rows(bad)[4]["injections"] = None
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is None and "injection" in detail


def test_missing_placebo_rows_is_none(hunt):
    bad = _mut(hunt["report"])
    bad["placebo"].pop("rows")
    ok, _ = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is None


def test_dropped_prior_floor_point_is_none(hunt):
    bad = _mut(hunt["report"])
    bad["floor_history"] = bad["floor_history"][1:]
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is None and "floor_history" in detail


# ------------------------------------------- (3) fabrication is False --------

def test_fabricated_null_maximum_is_caught(hunt):
    """Edit one stored null max so it crosses the observed SDE (the planted
    row: every honest maximum sits below its SDE 9): k changes, the stored
    fap no longer recomputes, and the receipt reads fabricated."""
    bad = _mut(hunt["report"])
    row = next(r for r in _stage2_rows(bad) if r["tic"] == "901")
    row["fap"]["schemes"]["iid"]["raw_maxima"][0] = float(row["sde"]) + 5.0
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "does not recompute" in detail


def test_fabricated_fap_is_caught(hunt):
    bad = _mut(hunt["report"])
    row = _stage2_rows(bad)[5]
    row["fap"]["schemes"]["block"]["fap_empirical"] *= 0.5
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "does not recompute" in detail


def test_fabricated_graded_fap_is_caught(hunt):
    bad = _mut(hunt["report"])
    _stage2_rows(bad)[6]["fap"]["fap_graded"] = 1e-4
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "conservative max" in detail


def test_fabricated_gumbel_is_caught(hunt):
    bad = _mut(hunt["report"])
    row = next((r for r in _stage2_rows(bad) if r["fap"].get("gumbel")), None)
    assert row is not None, "fixture produced no calibrated gumbel block"
    row["fap"]["gumbel"]["mu"] *= 1.5
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "refit" in detail


def test_edited_uniformity_ensemble_is_caught(hunt):
    bad = _mut(hunt["report"])
    n = bad["uniformity"]["n_control"]
    bad["uniformity"]["p_values"] = [0.5] * n
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "control rows" in detail


def test_placebo_summary_contradicting_rows_is_caught(hunt):
    bad = _mut(hunt["report"])
    bad["placebo"]["planet_candidates"] = 1
    bad["placebo"]["pass"] = False
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "placebo" in detail.lower()


def test_out_of_vocabulary_disposition_is_false(hunt):
    """The machine cannot emit 'planet' — a receipt that says it is not
    merely malformed, it violates contract rule 3 affirmatively."""
    bad = _mut(hunt["report"])
    next(r for r in bad["targets"] if r["tic"] == "903")["disposition"] = "planet"
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "vocabulary" in detail


# --------------------------------------------- (4) spot reproduction ---------

def test_spot_reproduction_fails_wrong_seed(hunt):
    """The stored seed pins the null. Rewriting it (all rows, so whichever
    row the content hash picks is affected) must break the replay."""
    bad = _mut(hunt["report"])
    for r in _stage2_rows(bad):
        r["fap"]["seed"] = int(r["fap"]["seed"]) + 1
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "spot reproduction FAILED" in detail


def test_spot_reproduction_none_when_cache_absent(hunt, tmp_path):
    ok, detail = checks.check_a05(hunt["report"], cache_dir=tmp_path)
    assert ok is None and "missing" in detail


# ------------------------------------------- (5) count reconciliation --------

def test_dropped_row_is_caught_by_count_reconciliation(hunt):
    bad = _mut(hunt["report"])
    bad["targets"] = [r for r in bad["targets"] if r["tic"] != "908"]
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is None and "reconcile" in detail


# --------------------------------------------- (6) the TOI 189.01 lesson -----

def test_toi189_fp_is_not_a_recovery(hunt):
    """TIC 902 replays TIC 278866211: SDE 10.3-class detection, vetting says
    planet-candidate, catalog says TOI with TFOPWG disposition FP. The
    machine word is toi-known-fp — never a recovery, never a lead."""
    report = hunt["report"]
    row = next(r for r in report["targets"] if r["tic"] == "902")
    assert row["sde"] >= a04.SDE_THRESHOLD
    assert row["disposition"] == "toi-known-fp"
    assert row["disposition_evidence"]["vet"]["verdict"] == "planet-candidate"
    assert "902" not in {r["tic"] for r in report["recoveries"]}
    leads = [r for r in report["targets"]
             if r.get("disposition") == "lead-awaiting-human-review"]
    assert [r["tic"] for r in leads] == ["901"]
    # And a receipt that promotes the refuted TOI anyway is fabricated.
    bad = _mut(report)
    bad_row = next(r for r in bad["targets"] if r["tic"] == "902")
    bad_row["disposition"] = "recovery-or-known"
    bad["recoveries"].append(bad_row)
    ok, detail = checks.check_a05(bad, cache_dir=hunt["cache"])
    assert ok is False and "toi-known-fp" in detail


# ------------------------------------------------- (7) runner resumability ---

RESUME_TICS = ["911", "912", "913"]


def _resume_run(cache: Path, done_rows=None, max_new=None, sink=None):
    return a05.run_a05(
        sector=2, targets=RESUME_TICS, curve_loader=_loader(cache),
        catalog=_catalog, B=32, n_periods=150, control_fraction=1.0,
        n_placebo=2, prewhiten_kwargs={"f_hi": 45.0},
        soft_budget_seconds=600.0, per_target_share=0.5,
        done_rows=done_rows, max_new_targets=max_new,
        on_row=sink, hunt_id="hunt-resume-s2")


def _strip_volatile(obj):
    """Remove the clocks — everything else must be bit-identical."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in ("generated_at", "wall_seconds",
                             "survey_sum_reported")}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def test_killed_and_resumed_run_writes_the_same_receipt(tmp_path):
    cache = tmp_path / "cache"
    _write_cache(cache, RESUME_TICS, days=13.5, cadence=0.01)
    # First sitting: the "kill" — a clean budget stop after 2 of 3 targets,
    # each completed row checkpointed through the JSONL seam.
    lines: list[str] = []
    partial = _resume_run(cache, max_new=2, sink=lambda r: lines.append(json.dumps(r)))
    assert not partial.complete and len(lines) == 2
    with pytest.raises(a05.A05Error):
        a05.to_report(partial)          # an incomplete slice is not a survey
    # Second sitting: resume from the checkpoint, run to completion.
    done = [json.loads(line) for line in lines]
    resumed = _resume_run(cache, done_rows=done)
    assert resumed.complete
    # The uninterrupted control run.
    fresh = _resume_run(cache)
    assert fresh.complete
    rep_resumed = _strip_volatile(a05.to_report(resumed))
    rep_fresh = _strip_volatile(a05.to_report(fresh))
    assert rep_resumed == rep_fresh
