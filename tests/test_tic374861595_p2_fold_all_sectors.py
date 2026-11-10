"""Gates on ``scripts/tic374861595_p2_fold_all_sectors.py``.

That script reports measurements on one star, and nothing in this repo knows what the right
answer for that star is. So each estimator it adds is handed a light curve whose answer is
known, and has to return it. The lab's own fold gates are not re-tested here; they have
``tests/test_a05_fold.py``.

Each test names what would make it fail, and each was seen to fail on 2026-11-10 before it
was allowed to pass:

* ``linear_drift`` first reported the period offset with the wrong sign. The drift test
  failed on it (expected 3.8778 d, got 3.8700 d) and the function was corrected.
* Swapping the ``atan2`` arguments in ``sinusoid_fit`` fails the phase test (0.300 reads 0.950).
* Flipping the parity index in ``event_depths`` (``(n + 1) % 2``) fails the alternation test
  (+0.006 reads -0.006).
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "tic374861595_p2_fold_all_sectors.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("p2_fold_all_sectors", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sector(mod, start, *, days=27.0, cadence_min=10.0, period, phase_max, amp=0.01,
            noise=0.002, seed=0):
    """One synthetic sector: two orbits with a gap, a quadratic drift, and one sinusoid."""
    rng = np.random.default_rng(seed)
    t = np.arange(start, start + days, cadence_min / 1440.0)
    t = t[(t < start + 12.5) | (t > start + 14.0)]
    theta = (t - mod.T0_BTJD) / period
    drift = 0.004 * ((t - start) / days) ** 2 - 0.002 * (t - start) / days
    f = 1.0 + drift + amp * np.cos(2.0 * math.pi * (theta - phase_max)) + rng.normal(0.0, noise, len(t))
    return t, f


def test_sinusoid_fit_recovers_an_injected_phase_through_a_drift_and_a_gap(mod):
    """Fails if the phase convention is wrong, or if the trend terms swallow the signal."""
    two_p = 2.0 * mod.P_DAYS
    t, f = _sector(mod, mod.T0_BTJD + 400.0, period=two_p, phase_max=0.300, amp=0.012)
    t, f, seg = mod.mask_dips(t, f)
    fit = mod.sinusoid_fit(t, f, seg, two_p)
    assert fit["amplitude"] == pytest.approx(0.012, rel=0.08)
    assert abs(((fit["phase_of_max_cycles"] - 0.300 + 0.5) % 1.0) - 0.5) < 0.01
    assert fit["amplitude_snr"] > 20


def test_locked_phases_line_up_at_the_true_period_and_scatter_at_a_wrong_one(mod):
    """The coherence test has to be able to fail: at a period 1 % off, the same light curves
    must NOT line up. If R stayed high there, a held phase would mean nothing."""
    two_p = 2.0 * mod.P_DAYS
    right, wrong = [], []
    for k in range(12):
        t, f = _sector(mod, mod.T0_BTJD + 100.0 + 160.0 * k, period=two_p, phase_max=0.55,
                       seed=k)
        t, f, seg = mod.mask_dips(t, f)
        right.append(mod.sinusoid_fit(t, f, seg, two_p)["phase_of_max_cycles"])
        wrong.append(mod.sinusoid_fit(t, f, seg, two_p * 1.01)["phase_of_max_cycles"])
    assert mod.rayleigh(right)["R"] > 0.95
    assert mod.rayleigh(right)["p"] < 1e-4
    assert mod.rayleigh(wrong)["R"] < 0.6


def test_linear_drift_gives_a_longer_period_when_maxima_arrive_later(mod):
    """A modulation slower than 2P reaches maximum later each cycle, so its phase on the 2P
    clock CLIMBS, and the implied period is LONGER than 2P. The sign is the whole test."""
    two_p = 2.0 * mod.P_DAYS
    eps = 0.001
    cycles = [float(c) for c in range(0, 260, 16)]
    phases = [0.30 + eps * c for c in cycles]
    drift = mod.linear_drift(cycles, phases)
    assert drift["slope_cycles_per_cycle"] == pytest.approx(eps, rel=1e-6)
    assert drift["implied_period_days"] == pytest.approx(two_p * (1.0 + eps), rel=1e-9)
    assert drift["implied_period_days"] > two_p


def _dips(mod, depth_even, depth_odd, *, noise=0.003, seed=1):
    rng = np.random.default_rng(seed)
    start = mod.T0_BTJD + 800.0
    t = np.arange(start, start + 27.0, 2.0 / 1440.0)
    f = 1.0 + rng.normal(0.0, noise, len(t))
    n = np.round((t - mod.T0_BTJD) / mod.P_DAYS).astype(int)
    in_dip = np.abs((t - (mod.T0_BTJD + n * mod.P_DAYS)) * 24.0) < 1.07
    f[in_dip & (n % 2 == 0)] -= depth_even
    f[in_dip & (n % 2 == 1)] -= depth_odd
    return t, f


def test_event_depths_sees_an_alternation_and_not_an_equal_pair(mod):
    """Fails if the parity split is mislabelled, or if the estimator invents a difference."""
    unequal = mod.event_depths(*_dips(mod, 0.090, 0.096))
    assert unequal["difference_odd_minus_even"] == pytest.approx(0.006, abs=0.0015)
    assert unequal["difference_odd_minus_even"] / unequal["sigma"] > 4.0
    equal = mod.event_depths(*_dips(mod, 0.093, 0.093))
    assert abs(equal["difference_odd_minus_even"] / equal["sigma"]) < 3.0


def test_weighted_widens_its_bar_when_sectors_scatter_more_than_their_bars(mod):
    """The formal bar is a white-noise bar. When the sectors disagree by more than it allows,
    the reported significance has to drop, and by about the right factor."""
    rng = np.random.default_rng(3)
    sig = [0.001] * 40
    honest = mod.weighted(list(0.004 + rng.normal(0.0, 0.001, 40)), sig)
    noisy = mod.weighted(list(0.004 + rng.normal(0.0, 0.003, 40)), sig)
    assert honest["bar_inflation"] < 1.4
    assert 2.2 < noisy["bar_inflation"] < 3.8
    assert noisy["sigmas_after_inflation"] < noisy["sigmas_formal"] / 2.0
