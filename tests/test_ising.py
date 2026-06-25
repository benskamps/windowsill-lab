import pytest
import torch

from lab.ising import RunConfig, run
from lab.ising_tri import TriRunConfig
from lab.ising_tri import run as run_tri


CUDA_AVAILABLE = torch.cuda.is_available()


def test_runconfig_defaults():
    cfg = RunConfig()
    assert cfg.L == 128
    assert cfg.n_temps == 21
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


@pytest.mark.skipif(not CUDA_AVAILABLE, reason="GPU not available")
def test_tiny_gpu_run_smoke():
    """Smoke test: a tiny run produces sensible-shaped outputs without crashing."""
    cfg = RunConfig(L=16, n_temps=5, n_burnin=20, n_sweeps=40, sample_every=10, device="cuda")
    r = run(cfg)
    assert r.T.shape == (5,)
    assert r.abs_mag.shape == (5,)
    assert r.chi.shape == (5,)
    assert r.energy.shape == (5,)
    assert r.chi_abs.shape == (5,)
    assert r.specific_heat.shape == (5,)
    # Magnetization should be in [0, 1]
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1).all()
    # |m|-susceptibility is a variance → non-negative
    assert (r.chi_abs >= 0).all()
    # Specific heat is a variance (·N/T²) → non-negative (M04 observable)
    assert (r.specific_heat >= 0).all()
    # Three snapshots saved
    assert len(r.snapshots) == 3


def test_cpu_run_smoke():
    """Same smoke test on CPU so we always have one ground-truth path."""
    cfg = RunConfig(L=12, n_temps=3, n_burnin=10, n_sweeps=20, sample_every=5, device="cpu")
    r = run(cfg)
    assert r.T.shape == (3,)
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1).all()
    assert r.chi_abs.shape == (3,) and (r.chi_abs >= 0).all()
    assert r.specific_heat.shape == (3,) and (r.specific_heat >= 0).all()


# ── M05: triangular-lattice engine (ising_tri) ───────────────────────────────
def test_tri_runconfig_defaults():
    cfg = TriRunConfig()
    assert cfg.L == 129 and cfg.L % 3 == 0   # multiple of 3 for the 3-colour seam
    assert cfg.n_temps == 25
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


def test_tri_cpu_run_smoke():
    """A tiny CPU triangular run produces sensible-shaped, physically valid output."""
    cfg = TriRunConfig(L=12, n_temps=4, T_min=2.0, T_max=6.0,
                       n_burnin=20, n_sweeps=40, sample_every=5, device="cpu")
    r = run_tri(cfg)
    assert r.T.shape == (4,)
    assert r.abs_mag.shape == (4,)
    assert r.chi.shape == (4,)
    assert r.chi_abs.shape == (4,)
    assert r.energy.shape == (4,)
    assert r.specific_heat.shape == (4,)
    # Magnetization in [0, 1].
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1).all()
    # |m|-susceptibility and specific heat are variances → non-negative.
    assert (r.chi_abs >= 0).all()
    assert (r.specific_heat >= 0).all()
    # Six bonds per site, energy per spin = -0.5·⟨s·Σ_6 nbr⟩ → in [-3, 3];
    # a cold lattice approaches the ground-state -3 (fully aligned).
    assert (r.energy >= -3.0001).all() and (r.energy <= 3.0001).all()
    # Three snapshots saved (cold / mid / hot).
    assert len(r.snapshots) == 3


def test_tri_requires_multiple_of_three():
    """The 3-colour update only wraps cleanly when 3 | L; other L must raise."""
    cfg = TriRunConfig(L=16, n_temps=2, n_burnin=1, n_sweeps=2, device="cpu")
    with pytest.raises(ValueError, match="multiple of 3"):
        run_tri(cfg)


@pytest.mark.skipif(not CUDA_AVAILABLE, reason="GPU not available")
def test_tri_tiny_gpu_run_smoke():
    """Smoke test: a tiny triangular GPU run produces sensible-shaped outputs."""
    cfg = TriRunConfig(L=15, n_temps=5, T_min=3.0, T_max=4.5,
                       n_burnin=20, n_sweeps=40, sample_every=10, device="cuda")
    r = run_tri(cfg)
    assert r.T.shape == (5,)
    assert r.chi_abs.shape == (5,) and (r.chi_abs >= 0).all()
    assert r.specific_heat.shape == (5,) and (r.specific_heat >= 0).all()
    assert (r.abs_mag >= 0).all() and (r.abs_mag <= 1).all()
