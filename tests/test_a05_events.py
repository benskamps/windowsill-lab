"""Cross-sector single-event search: pairing, vetoes, placebo, injection grading."""
import numpy as np
import pytest

from lab import a05_events as ev

CAD = 10.0 / 1440                      # 10-min cadence keeps the scan fast


def sectors(starts, span=12.0, noise=6e-4, seed=2026):
    rng = np.random.default_rng(seed)
    t = np.concatenate([np.arange(s, s + span, CAD) for s in starts])
    return t, 1.0 + rng.normal(0, noise, t.size)


def plant(t, f, period, t0, depth=0.004, dur=3.0 / 24):
    return ev.inject(t, f, period, t0, depth, dur)


def test_segments_split_on_gaps():
    t = np.r_[np.arange(0, 2, 0.01), np.arange(5, 7, 0.01), np.arange(7.5, 8, 0.01)]
    lab = ev.segments(t)
    assert lab[0] == 0 and lab[250] == 1 and lab[-1] == 1   # 0.5 d gap is not a split
    assert int(lab.max()) == 1


def test_pure_noise_survives_nothing():
    t, f = sectors([0, 100, 230, 400])
    res = ev.search(t, f)
    assert res["n_survivors"] == 0 and res["s_max"] == 0.0


def test_three_single_events_recover_the_period_and_veto_its_aliases():
    # one event per sector; 24.2456 d; sectors chosen so each holds one epoch
    P, t0 = 24.2456, 6.0
    starts = [0, 6.0 + 4 * P - 6, 6.0 + 9 * P - 6, 6.0 + 15 * P - 6]
    t, f = sectors(starts)
    f = plant(t, f, P, t0)
    res = ev.search(t, f)
    assert res["best"]["period"] == pytest.approx(P, rel=0.005)
    assert res["best"]["n_events"] >= 3
    assert ev.recovered(res, P) == "exact"


def test_two_events_without_veto_coverage_keep_the_whole_alias_family():
    P, t0 = 30.0, 6.0
    t, f = sectors([0, t0 + 3 * P - 6])                 # epochs 0 and 3 only
    f = plant(t, f, P, t0)
    res = ev.search(t, f)
    periods = sorted(s["period"] for s in res["survivors"])
    # Δ = 90 d: 90, 45, 30, 22.5, 18, 15, 12.86, 11.25, 10 all survive —
    # nothing in the data distinguishes them, and the output must say so
    assert any(abs(p - 90.0) < 0.2 for p in periods)
    assert any(abs(p - 30.0) < 0.1 for p in periods)
    assert res["n_vetoed"] == 0


def test_a_covered_epoch_without_a_dip_vetoes_the_alias():
    P, t0 = 30.0, 6.0
    # a third sector covers t0 + 45 (where the P = 45 alias predicts a dip,
    # and P = 30 does not), so 45 d must die and 30 d must not
    t, f = sectors([0, t0 + 45 - 6, t0 + 3 * P - 6])
    f = plant(t, f, P, t0)
    res = ev.search(t, f)
    periods = [s["period"] for s in res["survivors"]]
    assert not any(abs(p - 45.0) < 0.2 for p in periods)
    assert any(abs(p - 30.0) < 0.1 for p in periods)
    assert res["n_vetoed"] > 0


def test_roll_keeps_each_segment_and_its_timestamps():
    t, f = sectors([0, 100])
    g = ev.roll_segments(t, f, np.random.default_rng(1))
    seg = ev.segments(t)
    for s in (0, 1):
        assert sorted(g[seg == s]) == sorted(f[seg == s])
    assert not np.array_equal(g, f)


def test_placebo_prices_a_real_signal_and_not_noise():
    P, t0 = 24.2456, 6.0
    starts = [0, 6.0 + 4 * P - 6, 6.0 + 9 * P - 6]
    t, f = sectors(starts)
    sig = ev.placebo(t, plant(t, f, P, t0), n_rolls=9, seed=5)
    assert sig["k_exceed"] == 0 and sig["fap"] == pytest.approx(0.1)
    quiet = ev.placebo(t, f, n_rolls=9, seed=5)
    assert quiet["s_max_observed"] == 0.0 and quiet["fap"] == 1.0


def test_recovered_grades_exact_alias_and_miss():
    res = {"survivors": [{"period": 12.0}]}
    assert ev.recovered(res, 24.0) == "alias"
    assert ev.recovered(res, 12.03) == "exact"
    assert ev.recovered(res, 17.0) is None
