"""Four-plant calibration engines: physics, compute, astronomy, instrument."""
import hashlib
import struct

import numpy as np

from lab import a01, c01, checks, i01, m16
from lab.archive import classify_run


def test_m16_metrics_prefer_the_age_scaled_clock_and_check_rederives():
    tws = [16, 32, 64, 128]
    dts = [8, 16, 32, 64, 128, 256]
    # Exact synthetic aging law C = exp[-sqrt(dt/tw)].
    rows = {str(tw): [float(np.exp(-np.sqrt(dt / tw))) for dt in dts] for tw in tws}
    metrics = m16.aging_metrics(tws, dts, rows)
    assert metrics["collapse_ratio"] < 0.1
    assert metrics["fixed_lag_separation"] > 0.2
    report = {
        "experiment": "M16-spin-glass-aging", "waiting_times": tws,
        "delta_times": dts, "correlations": rows,
    }
    ok, detail = checks.check_m16(report)
    assert ok, detail


def test_c01_generates_exact_oeis_bytes_and_retests_mersenne(monkeypatch):
    expected = c01.fibonacci_bfile_segment(12)
    assert expected.startswith(b"0 0\n1 1\n2 1\n")
    assert c01.lucas_lehmer(31) == (True, 0)
    assert c01.lucas_lehmer(11)[0] is False  # 2^11-1 = 23*89
    monkeypatch.setattr(c01, "_download", lambda *_args, **_kwargs: expected + b"12 144\n")
    result = c01.run_c01(n_terms=12)
    report = c01.to_report(result)
    ok, detail = checks.check_c01(report)
    assert result.calibration_passed and ok, detail


def _card(key, value=None):
    if value is None:
        text = key
    elif isinstance(value, str):
        text = f"{key:<8}= '{value}'"
    elif isinstance(value, bool):
        text = f"{key:<8}= {'T' if value else 'F':>20}"
    else:
        text = f"{key:<8}= {value:>20}"
    return text.ljust(80).encode("ascii")


def _hdu(cards, data=b""):
    header = b"".join([*cards, _card("END")])
    header += b" " * ((-len(header)) % 2880)
    data += b"\0" * ((-len(data)) % 2880)
    return header + data


def test_a01_dependency_free_fits_reader_and_ephemeris():
    rows = [
        struct.pack(">dffi", 100.0 + i, 1000.0 - i, 2.0, 0 if i != 2 else 1)
        for i in range(4)
    ]
    blob = _hdu([
        _card("SIMPLE", True), _card("BITPIX", 8), _card("NAXIS", 0),
        _card("EXTEND", True),
    ]) + _hdu([
        _card("XTENSION", "BINTABLE"), _card("BITPIX", 8), _card("NAXIS", 2),
        _card("NAXIS1", 20), _card("NAXIS2", 4), _card("PCOUNT", 0),
        _card("GCOUNT", 1), _card("TFIELDS", 4),
        _card("TTYPE1", "TIME"), _card("TFORM1", "1D"),
        _card("TTYPE2", "PDCSAP_FLUX"), _card("TFORM2", "1E"),
        _card("TTYPE3", "PDCSAP_FLUX_ERR"), _card("TFORM3", "1E"),
        _card("TTYPE4", "QUALITY"), _card("TFORM4", "1J"),
    ], b"".join(rows))
    curve = a01.read_tess_light_curve(blob)
    assert curve["TIME"].tolist() == [100.0, 101.0, 102.0, 103.0]
    assert curve["QUALITY"].tolist() == [0, 0, 1, 0]

    epochs = list(range(-10, 11))
    period = 0.94145223
    times = [1500.25 + n * period for n in epochs]
    fit = a01.fit_ephemeris(times, epochs)
    assert abs(fit["period_days"] - period) < 1e-12


def test_a01_check_refits_saved_transits_instead_of_echoing_cached_period():
    p, depth = 0.94145223, 0.01041
    epochs = list(range(12))
    report = {
        "experiment": "A01-tess-hot-jupiter-calibration",
        "transit_times": [1000 + p * n for n in epochs],
        "transit_epochs": epochs,
        "transit_depths": [depth] * len(epochs),
        "kept_transits": [True] * len(epochs),
        "period_days": 123.0,
        "products": [{"sha256": hashlib.sha256(b"fits").hexdigest()}],
        "benchmark": {"period_days": p, "period_err_days": 2.4e-7,
                      "depth_fraction": depth, "depth_err_fraction": 0.00022},
    }
    ok, detail = checks.check_a01(report)
    assert ok, detail


def test_i01_separates_persistent_hot_pixels_from_transient_track():
    rng = np.random.default_rng(42)
    stack = rng.normal(100.0, 1.0, size=(24, 48, 48))
    stack[:, 5, 7] += 35.0
    stack[:, 31, 40] += 45.0
    for k in range(10):
        stack[9, 15 + k, 10 + k] += 30.0
    analysis = i01.classify_dark_stack(stack)
    assert analysis["hot_pixel_count"] >= 2
    assert analysis["track_candidate_count"] >= 1


def test_i01_without_real_frames_is_an_explicit_null(monkeypatch):
    monkeypatch.delenv("WINDOWSILL_I01_FRAMES", raising=False)
    report = i01.to_report(i01.run_i01())
    ok, detail = checks.check_i01(report)
    assert report["status"] == "null"
    assert ok is False and "hardware-null" in detail
    row = classify_run(report)
    assert row["kind"] == "instrument"
    assert row["verdict"] == "null"
    assert "hardware unavailable" in row["numbers"]
