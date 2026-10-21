"""Multi-sector plumbing: the reader, the long-baseline BLS, one-event timing."""
import struct

import numpy as np
import pytest

from lab import a05_multisector as ms


def _card(key, value=None):
    if value is None:
        s = f"{key:<8}"
    elif isinstance(value, str):
        s = f"{key:<8}= '{value}'"
    elif isinstance(value, bool):
        s = f"{key:<8}= {'T' if value else 'F':>20}"
    else:
        s = f"{key:<8}= {value:>20}"
    return s.ljust(80).encode("ascii")


def _block(cards):
    raw = b"".join(cards) + _card("END")
    return raw + b" " * ((-len(raw)) % 2880)


def fake_qlp(t, flux, quality):
    """A minimal QLP-shaped FITS: TIME (D), KSPSAP_FLUX (E), QUALITY (J)."""
    primary = _block([_card("SIMPLE", True), _card("BITPIX", 8), _card("NAXIS", 0),
                      _card("TESSMAG", 11.7)])
    n = len(t)
    table = _block([_card("XTENSION", "BINTABLE"), _card("BITPIX", 8), _card("NAXIS", 2),
                    _card("NAXIS1", 16), _card("NAXIS2", n), _card("PCOUNT", 0),
                    _card("GCOUNT", 1), _card("TFIELDS", 3),
                    _card("TTYPE1", "TIME"), _card("TFORM1", "D"),
                    _card("TTYPE2", "KSPSAP_FLUX"), _card("TFORM2", "E"),
                    _card("TTYPE3", "QUALITY"), _card("TFORM3", "J")])
    data = b"".join(struct.pack(">dfi", a, b, int(c)) for a, b, c in zip(t, flux, quality))
    data += b"\0" * ((-len(data)) % 2880)
    return primary + table + data


def test_reader_reads_a_qlp_file_without_pdcsap():
    t = np.arange(2000.0, 2010.0, 200 / 86400)
    f = 1000.0 + np.random.default_rng(1).normal(0, 1, t.size)
    q = np.zeros(t.size, int)
    q[:50] = 4096
    c = ms.curve_from_product(fake_qlp(t, f, q), "QLP")
    assert c["n_cadences"] == t.size - 50                 # quality mask applied
    assert c["provenance"] == "QLP" and c["crowdsap"] is None
    assert c["tessmag"] == pytest.approx(11.7)
    assert np.median(c["f_raw"]) == pytest.approx(1.0, abs=1e-6)
    assert c["cadence_days"] == pytest.approx(200 / 86400, rel=1e-3)


def test_reader_refuses_a_file_without_the_named_flux_column():
    t = np.arange(2000.0, 2001.0, 200 / 86400)
    blob = fake_qlp(t, np.ones(t.size), np.zeros(t.size))
    with pytest.raises(ValueError, match="PDCSAP_FLUX"):
        ms.curve_from_product(blob, "SPOC")


def test_frequency_grid_drift_is_bounded():
    f = ms.frequency_grid(1.0, 40.0, 2000.0, 1.0 / 24)
    assert f[0] == pytest.approx(1 / 40) and f[-1] >= 1.0
    # time drift across the baseline between adjacent trials <= quarter box
    drift = np.diff(f) * 2000.0 / f[:-1]
    assert drift.max() <= 0.25 / 24 * 1.0001


def two_sectors(P=18.15219, t0=5.3, depth=0.0032, dur=0.1, noise=0.0015, seed=7):
    rng = np.random.default_rng(seed)
    t = np.concatenate([np.arange(0, 27, 10 / 1440), np.arange(110, 137, 10 / 1440)])
    f = 1 + rng.normal(0, noise, t.size)
    x = ((t - t0 + P / 2) % P) - P / 2
    f[np.abs(x) < dur / 2] -= depth
    return t, f


def test_stitched_bls_recovers_a_period_the_survey_cannot():
    t, f = two_sectors()
    bls = ms.bls_stitched(t, f, p_lo=10.0, p_hi=30.0, durations_hours=(2.0, 2.5))
    top = ms.top_peaks(bls, 3)[0]
    assert top["period_days"] == pytest.approx(18.15219, abs=0.01)
    assert top["depth"] == pytest.approx(0.0032, rel=0.35)


def test_stitched_bls_finds_nothing_special_in_noise():
    rng = np.random.default_rng(3)
    t = np.concatenate([np.arange(0, 27, 10 / 1440), np.arange(110, 137, 10 / 1440)])
    f = 1 + rng.normal(0, 0.0015, t.size)
    bls = ms.bls_stitched(t, f, p_lo=10.0, p_hi=30.0, durations_hours=(2.0,))
    assert ms.top_peaks(bls, 1)[0]["snr"] < 7.0


def test_event_time_recovers_a_planted_mid_time():
    t, f = two_sectors(noise=0.001)
    et = ms.event_time(t, f, 5.3 + 0.01, 0.1)
    assert (et["t_mid"] - 5.3) * 1440 == pytest.approx(0.0, abs=4.0)
    assert not et["edge"]


def test_box_depth_reports_no_coverage_rather_than_zero():
    t, f = two_sectors()
    r = ms.box_depth(t, f, 60.0, 0.1)                     # inside the gap
    assert r["depth"] is None and r["reason"] == "no-coverage"


def _centroids(t, centres, dur, shift):
    rng = np.random.default_rng(11)
    cx = 500 + rng.normal(0, 0.002, t.size)
    cy = 400 + rng.normal(0, 0.002, t.size)
    for tc in centres:
        cx[np.abs(t - tc) < dur / 2] += shift
    return cx, cy


def test_matched_centroid_fires_on_a_shift_pointing_off_target():
    t, _ = two_sectors()
    centres = [5.3 + n * 18.15219 for n in (0, 1, 6, 7)]
    cx, cy = _centroids(t, centres, 0.1, 0.01)
    r = ms.centroid_shift_matched(t, cx, cy, centres, 0.1, depth=0.0032)
    assert r["n_events"] == 4
    assert r["verdict"] == "centroid-shift"               # 0.01 / 0.0032 = 3 px


def test_matched_centroid_is_quiet_without_a_shift_and_honest_without_data():
    t, _ = two_sectors()
    centres = [5.3 + n * 18.15219 for n in (0, 1, 6, 7)]
    cx, cy = _centroids(t, centres, 0.1, 0.0)
    assert ms.centroid_shift_matched(t, cx, cy, centres, 0.1, 0.0032)["verdict"] is None
    r = ms.centroid_shift_matched(t, None, None, centres, 0.1, 0.0032)
    assert r["reason"] == "no-centroid-data"
