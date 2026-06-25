import pytest
import torch

from lab.ising import RunConfig, run


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
