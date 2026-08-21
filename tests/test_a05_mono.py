"""Single-transit detector — the population BLS cannot see by construction."""
import numpy as np
import pytest

from lab import a05_mono


def clean(n=19440, span=27.0, noise=3e-4, seed=20260820):
    t = np.arange(0.0, span, span / n)
    return t, 1.0 + np.random.default_rng(seed).normal(0, noise, t.size)


def test_pure_noise_yields_nothing():
    t, f = clean()
    res = a05_mono.search_single(t, f)
    assert res["candidates"] == []
    assert res["snr_max_brightening"] < a05_mono.SNR_REPORT


def test_recovers_a_planted_single_transit():
    t, f = clean()
    f[np.abs(t - 12.0) <= 2.0 / 24] -= 0.003
    res = a05_mono.search_single(t, f)
    assert len(res["candidates"]) == 1
    c = res["candidates"][0]
    assert c["t_centre"] == pytest.approx(12.0, abs=0.2)
    assert c["depth"] == pytest.approx(0.003, rel=0.3)
    assert c["snr"] > a05_mono.SNR_REPORT
    assert c["snr_over_null"] > 2.0


def test_brightening_null_is_reported():
    t, f = clean()
    f[np.abs(t - 12.0) <= 2.0 / 24] -= 0.003
    res = a05_mono.search_single(t, f)
    # the null is drawn from the same star and must be finite and modest
    assert 0.0 < res["snr_max_brightening"] < res["candidates"][0]["snr"]


def test_a_periodic_signal_is_not_a_monotransit():
    t, f = clean()
    P, ph0 = 2.6857, 0.375
    ph = np.mod(t, P) / P
    f[np.abs(((ph - ph0 + 0.5) % 1.0) - 0.5) < 0.019] -= 0.006
    res = a05_mono.search_single(t, f, known_period_days=P, known_phase=ph0)
    assert res["candidates"] == []
    assert len(res.get("periodic_events", [])) > 1


def test_events_at_the_series_edge_are_refused():
    t, f = clean()
    f[t <= 0.2] -= 0.01                      # truncated dip, no egress
    res = a05_mono.search_single(t, f)
    assert all(c["t_centre"] > 0.3 for c in res["candidates"])


def test_a_flat_series_is_handled():
    t = np.linspace(0, 27, 5000)
    res = a05_mono.search_single(t, np.ones_like(t))
    assert res["candidates"] == []
