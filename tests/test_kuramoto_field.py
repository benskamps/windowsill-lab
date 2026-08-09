"""The external field is opt-in, and h=0 leaves K01/K02 bit-identical.

`kuramoto.py` is a shared engine under two GREEN milestones. K03 needed a
pinning field on it, because the fluctuation estimator K01/K02 use cannot answer
the Daido-vs-Hong question: below K_c the system is incoherent, r sits on the
1/√N floor, and N·Var(r) saturates at the Rayleigh value 1 − π/4 ≈ 0.215
(measured flat to 1.3× across a 25× range in |K−K_c|/K_c).

Adding a term to a green engine is only safe if "unchanged when off" is a
*checked* property rather than a claim, so these assert **bit-identity**, not
closeness — the same standard `lab verify --rerun-smoke` holds the engine to.
"""
from __future__ import annotations

import numpy as np
import pytest

from lab import kuramoto


def _state(n=64, n_k=3, seed=5):
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0.0, 2.0 * np.pi, size=(n_k, n))
    omega = kuramoto.lorentzian_frequencies(n, kuramoto.GAMMA)
    coupling = np.array([0.6, 1.0, 1.4])[:, None]
    return theta, omega, coupling


def test_drift_is_bit_identical_when_the_field_is_off():
    theta, omega, coupling = _state()
    without = kuramoto._drift(theta, omega, coupling)
    explicit_zero = kuramoto._drift(theta, omega, coupling, 0.0)
    assert np.array_equal(without, explicit_zero)
    assert without.tobytes() == explicit_zero.tobytes()


def test_rk4_step_is_bit_identical_when_the_field_is_off():
    theta, omega, coupling = _state()
    a = kuramoto.rk4_step(theta, omega, coupling, kuramoto.DT)
    b = kuramoto.rk4_step(theta, omega, coupling, kuramoto.DT, 0.0)
    assert a.tobytes() == b.tobytes()


def test_a_whole_trajectory_is_bit_identical_when_the_field_is_off():
    """The property that actually protects K01/K02: many steps, not one."""
    theta, omega, coupling = _state()
    a, b = theta.copy(), theta.copy()
    for _ in range(200):
        a = kuramoto.rk4_step(a, omega, coupling, kuramoto.DT)
        b = kuramoto.rk4_step(b, omega, coupling, kuramoto.DT, field=0.0)
    assert a.tobytes() == b.tobytes()


def test_a_field_actually_changes_the_dynamics():
    """Otherwise 'unchanged when off' would be trivially true and useless."""
    theta, omega, coupling = _state()
    off = kuramoto.rk4_step(theta, omega, coupling, kuramoto.DT)
    on = kuramoto.rk4_step(theta, omega, coupling, kuramoto.DT, field=0.05)
    assert not np.allclose(off, on)


def test_the_field_pins_toward_its_own_axis():
    """h·sin(Θ−θ) with Θ=0 must pull phases toward 0, not push them away.

    A sign slip here would invert the response and hand K03 a negative
    susceptibility — the same shape as the bug that made this milestone need a
    new estimator in the first place.
    """
    n = 4096
    omega = np.zeros(n)                      # no natural drift: field only
    coupling = np.zeros((1, 1))              # no coupling: field only
    rng = np.random.default_rng(3)
    theta = rng.uniform(0.0, 2.0 * np.pi, size=(1, n))
    r0 = kuramoto.order_parameter(theta)[0][0]
    for _ in range(400):
        theta = kuramoto.rk4_step(theta, omega, coupling, kuramoto.DT, field=0.5)
    r1, psi1 = (v[0] for v in kuramoto.order_parameter(theta))
    assert r1 > r0                            # the crowd gathers
    assert abs(np.arctan2(np.sin(psi1), np.cos(psi1))) < 0.15   # ...at Θ = 0


def test_incoherent_floor_is_what_it_is_predicted_to_be():
    """Records WHY K03 needed a field: N·Var(r) below K_c is the Rayleigh floor.

    A Rayleigh-distributed r with ⟨r²⟩ = 1/N gives N·Var(r) → 1 − π/4. That is a
    constant, so the fluctuation estimator carries no subcritical exponent.
    """
    rng = np.random.default_rng(17)
    n = 4000
    # incoherent phases: r is the random-walk centroid of N scattered phases
    samples = np.array([
        kuramoto.order_parameter(rng.uniform(0, 2 * np.pi, size=(1, n)))[0][0]
        for _ in range(4000)
    ])
    assert n * samples.var() == pytest.approx(1.0 - np.pi / 4, abs=0.03)
    assert samples.mean() == pytest.approx(np.sqrt(np.pi / 4 / n), rel=0.05)
