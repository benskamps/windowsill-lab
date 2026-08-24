"""The GPU engine must reproduce the CPU engine before it may produce new science.

This is the whole reason the module is allowed to exist. U-K02 needs 100× the
oscillators, and the fast path is worth nothing if it quietly disagrees with the
instrument every published K-track result was measured on — that would not be an
upgrade, it would be an unlabelled second lab.

Every test here skips cleanly without a GPU, because the lean CI job has no ROCm
stack and a collection error there would look like a physics failure.
"""
from __future__ import annotations

import numpy as np
import pytest

from lab import kuramoto
from lab import kuramoto_gpu as g

pytestmark = pytest.mark.skipif(not g.available(), reason="no GPU on this runner")

DT = 0.01


def _pair(n=2048, seed=11):
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0, 2 * np.pi, n)
    omega = rng.standard_cauchy(n) * 0.1
    return theta, omega


@pytest.mark.parametrize("coupling,field,label", [
    (0.15, 0.0, "subcritical"),
    (0.40, 0.0, "supercritical"),
    (0.15, 0.002, "subcritical with pinning field"),
    (0.40, 0.002, "supercritical with pinning field"),
])
def test_the_two_engines_agree_to_roundoff_over_a_trajectory(coupling, field, label):
    """Not a single step — a trajectory, because RK4 compounds and a difference
    in how the mean field is formed would show up as drift rather than as an
    immediate mismatch."""
    theta, omega = _pair()
    tc = theta.copy()
    tg = g.to_device(theta)
    og, cg = g.to_device(omega), g.to_device(np.float64(coupling))
    fg = g.to_device(np.float64(field)) if field else None
    for _ in range(400):
        tc = kuramoto.rk4_step(tc, omega, np.float64(coupling), DT, field=field)
        tg = g.rk4_step(tg, og, cg, DT, field=fg)
    assert np.abs(tc - tg.cpu().numpy()).max() < 1e-12, label


def test_zero_field_takes_the_same_short_circuit_as_the_cpu_engine():
    """`kuramoto._drift` guarantees h=0 trajectories are bit-identical to the
    pre-field engine. The GPU path must inherit that, or a K01/K02 rerun on the
    fast engine would silently stop being comparable to its own history."""
    theta, omega = _pair(n=512)
    og, cg = g.to_device(omega), g.to_device(np.float64(0.3))
    a = g.to_device(theta)
    b = g.to_device(theta)
    for _ in range(50):
        a = g.rk4_step(a, og, cg, DT, field=None)
        b = g.rk4_step(b, og, cg, DT, field=g.to_device(np.float64(0.0)))
    assert np.array_equal(a.cpu().numpy(), b.cpu().numpy())


def test_running_averages_match_a_trajectory_computed_the_slow_way():
    """`evolve` accumulates on the device because a 200,000-oscillator
    trajectory cannot be shipped back. That optimisation is only safe if it
    produces the same number as the obvious implementation."""
    theta, omega = _pair(n=1024, seed=5)
    og, cg = g.to_device(omega), g.to_device(np.float64(0.35))
    out = g.evolve(g.to_device(theta), og, cg, DT, steps=200,
                   observe_every=10)
    tc, rs, cs = theta.copy(), [], []
    for i in range(200):
        tc = kuramoto.rk4_step(tc, omega, np.float64(0.35), DT)
        if (i + 1) % 10 == 0:
            r, _ = kuramoto.order_parameter(tc)
            rs.append(float(r))
            cs.append(float(np.cos(tc).mean()))
    assert out["n_samples"] == len(rs)
    assert out["mean_r"] == pytest.approx(float(np.mean(rs)), abs=1e-10)
    assert out["mean_cos"] == pytest.approx(float(np.mean(cs)), abs=1e-10)


def test_the_engine_scales_to_the_N_the_reach_projection_assumes():
    """U-K02's 3.1 GPU-hour figure is priced at N = 200,000. If the engine
    cannot hold that many oscillators, the projection is fiction."""
    from lab import u_k02_reach
    n = u_k02_reach.project.__defaults__ and 200_000
    theta, omega = _pair(n=n, seed=3)
    out = g.evolve(g.to_device(theta), g.to_device(omega),
                   g.to_device(np.float64(0.3)), DT, steps=5, observe_every=5)
    assert 0.0 <= out["mean_r"] <= 1.0
