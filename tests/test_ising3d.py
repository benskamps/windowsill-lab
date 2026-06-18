"""3D simple-cubic Ising engine — pure NumPy, CPU, fast smoke + physics sanity.

The engine is small and CPU-only (no torch / no GPU), so unlike the 2D kernel we
can afford to run tiny *real* Monte-Carlo sweeps in the test suite. These stay
under a second: a few-thousand-spin lattice for a handful of sweeps.
"""
import numpy as np
import pytest

from lab.ising3d import (
    Run3DConfig, Run3DResult, run, _checkerboard_masks, _neighbor_sum,
)


def test_runconfig_defaults_and_sample_count():
    cfg = Run3DConfig()
    assert cfg.L == 10
    assert cfg.n_temps == 21
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


def test_checkerboard_partitions_the_lattice():
    even, odd = _checkerboard_masks(4)
    # The two colours partition every site exactly once.
    assert even.shape == (4, 4, 4)
    assert np.logical_xor(even, odd).all()
    assert (even.sum() + odd.sum()) == 4 ** 3
    # On a simple cubic lattice the two colours are equal halves.
    assert even.sum() == odd.sum() == 4 ** 3 // 2


def test_neighbor_sum_is_six_for_uniform_lattice():
    # A fully aligned lattice: every site sees 6 aligned neighbours.
    spins = np.ones((2, 4, 4, 4), dtype=np.int8)
    nbr = _neighbor_sum(spins)
    assert nbr.shape == (2, 4, 4, 4)
    assert (nbr == 6).all()
    # Flip all spins → every neighbour sum is −6 (periodic, still six neighbours).
    assert (_neighbor_sum(-spins) == -6).all()


def test_odd_L_is_rejected():
    with pytest.raises(ValueError):
        run(Run3DConfig(L=5, n_temps=2, n_burnin=1, n_sweeps=2))


def test_tiny_cpu_run_smoke():
    """A tiny real sweep produces sensibly-shaped, physical outputs."""
    cfg = Run3DConfig(L=4, T_min=4.0, T_max=5.0, n_temps=4,
                      n_burnin=20, n_sweeps=40, sample_every=5, seed=1)
    r = run(cfg)
    assert isinstance(r, Run3DResult)
    assert r.T.shape == (4,)
    for arr in (r.abs_mag, r.chi, r.energy, r.specific_heat, r.abs_mag_err):
        assert arr.shape == (4,)
    # |m| ∈ [0, 1]; susceptibility & specific heat are variances → non-negative.
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1).all()
    assert (r.chi >= 0).all()
    assert (r.specific_heat >= 0).all()
    # Energy per spin on a 6-coordinated lattice lives in [−3, 3].
    assert (r.energy >= -3.001).all() and (r.energy <= 3.001).all()
    assert r.wall_seconds >= 0.0


def test_low_T_orders_high_T_disorders():
    """Physics sanity: well below T_c the lattice orders (|m|≈1); well above it melts.

    The 3D benchmark is T_c ≈ 4.5115, so T=2.5 is deep in the ordered phase and
    T=8.0 deep in the disordered one. With a short burn-in the contrast is already
    unmistakable, which is enough to prove the Boltzmann weight points the right
    way (a sign error would invert this).
    """
    cfg = Run3DConfig(L=6, T_min=2.5, T_max=8.0, n_temps=2,
                      n_burnin=400, n_sweeps=400, sample_every=10, seed=7)
    r = run(cfg)
    m_cold, m_hot = r.abs_mag[0], r.abs_mag[1]
    assert m_cold > 0.8, f"expected order at low T, got |m|={m_cold:.3f}"
    assert m_hot < 0.4, f"expected disorder at high T, got |m|={m_hot:.3f}"
    assert m_cold > m_hot
