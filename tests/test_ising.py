import math

import pytest
import torch

from lab.ising import RunConfig, run
from lab.ising_tri import TriRunConfig
from lab.ising_tri import run as run_tri
from lab.potts import PottsRunConfig
from lab.potts import run as run_potts
from lab.xy import XYRunConfig
from lab.xy import run as run_xy


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


# ── M07: q-state Potts engine (potts) ────────────────────────────────────────
def test_potts_runconfig_defaults():
    cfg = PottsRunConfig()
    assert cfg.q == 3 and cfg.L == 128
    assert cfg.n_temps == 25
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


def test_potts_requires_q_at_least_two():
    """q < 2 is not a Potts model (q=2 is the Ising floor); the engine must raise."""
    cfg = PottsRunConfig(q=1, L=8, n_temps=2, n_burnin=1, n_sweeps=2, device="cpu")
    with pytest.raises(ValueError, match="q must be"):
        run_potts(cfg)


def test_potts_cpu_run_smoke():
    """A tiny CPU Potts run produces sensible-shaped, physically valid output."""
    cfg = PottsRunConfig(q=3, L=12, n_temps=4, T_min=0.5, T_max=1.5,
                         n_burnin=20, n_sweeps=40, sample_every=5, device="cpu")
    r = run_potts(cfg)
    assert r.T.shape == (4,)
    assert r.order.shape == (4,)
    assert r.chi.shape == (4,)
    assert r.energy.shape == (4,)
    assert r.specific_heat.shape == (4,)
    # The Potts order parameter m = (q·ρ_max−1)/(q−1) lives in [0, 1].
    assert (r.order >= -1e-6).all() and (r.order <= 1.0 + 1e-6).all()
    # Susceptibility and specific heat are variances → non-negative.
    assert (r.chi >= 0).all()
    assert (r.specific_heat >= 0).all()
    # Energy per spin e = -0.5·⟨Σ_4 δ⟩ ∈ [-2, 0] (2N bonds, 0.5 de-double-counts).
    assert (r.energy >= -2.0001).all() and (r.energy <= 1e-6).all()
    # Three snapshots saved (cold / mid / hot).
    assert len(r.snapshots) == 3


def test_potts_low_T_orders_high_T_disorders():
    """The core physics: a cold q=3 Potts lattice orders (m→1), a hot one melts.

    This is the calibration the agreement-count must get right — a sign or
    bool-overflow bug in ΔE leaves the lattice stuck disordered at all T (m≈0),
    which this catches. CPU so it always runs (no GPU dependency).
    """
    q = 3
    tc = 1.0 / math.log(1.0 + math.sqrt(q))
    cfg = PottsRunConfig(q=q, L=24, T_min=0.4 * tc, T_max=1.8 * tc, n_temps=6,
                         n_burnin=400, n_sweeps=600, sample_every=10, device="cpu")
    r = run_potts(cfg)
    # Coldest temperature: nearly fully ordered (one flavour dominates).
    assert r.order[0] > 0.8, f"cold lattice should order, got m={r.order[0]:.3f}"
    # Hottest temperature: essentially disordered (flavours equipartitioned).
    assert r.order[-1] < 0.3, f"hot lattice should disorder, got m={r.order[-1]:.3f}"
    # Cold energy approaches the ordered ground state -2; hot is well above it.
    assert r.energy[0] < -1.5, f"cold energy should near -2, got {r.energy[0]:.3f}"
    assert r.energy[-1] > r.energy[0]


def test_potts_metropolis_path_runs():
    """The kept single-spin Metropolis updater path is still valid (off-critical).

    M07 drives the Wolff cluster updater; the Metropolis path is the independent
    cross-check engine. This exercises it on CPU and checks the same physical
    invariants (shapes, m∈[0,1], non-negative variances).
    """
    cfg = PottsRunConfig(q=3, L=12, n_temps=3, T_min=0.5, T_max=1.5,
                         n_burnin=20, n_sweeps=40, sample_every=5,
                         updater="metropolis", device="cpu")
    r = run_potts(cfg)
    assert r.order.shape == (3,)
    assert (r.order >= -1e-6).all() and (r.order <= 1.0 + 1e-6).all()
    assert (r.chi >= 0).all() and (r.specific_heat >= 0).all()


def test_potts_rejects_unknown_updater():
    cfg = PottsRunConfig(q=3, L=8, n_temps=2, n_burnin=1, n_sweeps=2,
                         updater="banana", device="cpu")
    with pytest.raises(ValueError, match="unknown updater"):
        run_potts(cfg)


@pytest.mark.skipif(not CUDA_AVAILABLE, reason="GPU not available")
def test_potts_tiny_gpu_run_smoke():
    """Smoke test: a tiny q=4 Potts GPU run produces sensible-shaped outputs."""
    cfg = PottsRunConfig(q=4, L=16, n_temps=5, T_min=0.6, T_max=1.3,
                         n_burnin=20, n_sweeps=40, sample_every=10, device="cuda")
    r = run_potts(cfg)
    assert r.T.shape == (5,)
    assert r.order.shape == (5,)
    assert (r.order >= -1e-6).all() and (r.order <= 1.0 + 1e-6).all()
    assert r.chi.shape == (5,) and (r.chi >= 0).all()
    assert r.specific_heat.shape == (5,) and (r.specific_heat >= 0).all()


# ── M08: 2D XY engine (xy) — continuous angles, helicity modulus ──────────────
def test_xy_runconfig_defaults():
    cfg = XYRunConfig()
    assert cfg.L == 64
    assert cfg.n_temps == 25
    assert cfg.updater == "metropolis"
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


def test_xy_rejects_unknown_updater():
    cfg = XYRunConfig(L=8, n_temps=2, n_burnin=1, n_sweeps=2,
                      updater="banana", device="cpu")
    with pytest.raises(ValueError, match="unknown updater"):
        run_xy(cfg)


def test_xy_cpu_run_smoke():
    """A tiny CPU XY run produces sensible-shaped, physically valid output.

    The headline observable is the helicity modulus Υ — finite below T_BKT,
    dropping toward zero above. We assert the shapes, that the energy per spin
    lives in its bond range [-2, 0], that ⟨|m|⟩ ∈ [0, 1], and that the realized
    Metropolis acceptance is a sane fraction (the per-T-tuned δ keeping it off 0/1).
    """
    cfg = XYRunConfig(L=16, n_temps=4, T_min=0.4, T_max=1.4,
                      n_burnin=40, n_sweeps=120, sample_every=10, device="cpu")
    r = run_xy(cfg)
    assert r.T.shape == (4,)
    assert r.helicity_modulus.shape == (4,)
    assert r.helicity_err.shape == (4,) and (r.helicity_err >= 0).all()
    assert r.energy.shape == (4,)
    assert r.abs_mag.shape == (4,)
    assert r.acceptance.shape == (4,)
    # Energy per spin e = -0.5·⟨Σ_4 cos⟩ ∈ [-2, 0] (2N bonds, 0.5 de-double-counts).
    assert (r.energy >= -2.0001).all() and (r.energy <= 1e-6).all()
    # ⟨|m|⟩ is a vector-magnetization fraction in [0, 1].
    assert (r.abs_mag >= -1e-6).all() and (r.abs_mag <= 1.0 + 1e-6).all()
    # Acceptance is a real fraction, comfortably off the 0/1 rails (δ is tuned).
    assert (r.acceptance > 0.05).all() and (r.acceptance < 0.99).all()
    # Three snapshots saved (cold / mid / hot).
    assert len(r.snapshots) == 3


def test_xy_low_T_stiff_high_T_floppy():
    """The core BKT physics: Υ → J=1 as T→0 (stiff), Υ → 0 at high T (floppy).

    This is the calibration the helicity estimator must get right — a sign error
    or a dropped 1/T on the fluctuation term breaks the limits (a common XY bug
    leaves Υ negative or frozen-high). A wide T window with a cold and a hot point
    pins both ends. CPU so it always runs (no GPU dependency).
    """
    cfg = XYRunConfig(L=16, n_temps=6, T_min=0.2, T_max=2.0,
                      n_burnin=300, n_sweeps=900, sample_every=10, device="cpu")
    r = run_xy(cfg)
    # Coldest: nearly fully stiff — Υ approaches J = 1 (allow finite-L/run slack).
    assert r.helicity_modulus[0] > 0.8, \
        f"cold lattice should be stiff (Υ→1), got Υ={r.helicity_modulus[0]:.3f}"
    # Hottest: essentially floppy — Υ near 0 (small magnitude, either sign).
    assert abs(r.helicity_modulus[-1]) < 0.2, \
        f"hot lattice should be floppy (Υ→0), got Υ={r.helicity_modulus[-1]:.3f}"
    # Stiffness decreases overall from cold to hot.
    assert r.helicity_modulus[0] > r.helicity_modulus[-1]


def test_xy_metropolis_and_wolff_both_run():
    """Both updaters run and produce a finite, non-negative cold-stiffness Υ.

    M08 drives Metropolis-plus-over-relaxation; the embedded-cluster Wolff path is
    the alternative for the hardest near-T_BKT points. This exercises both on CPU
    and checks they each give a stiff cold lattice (Υ>0) — the Wolff reflection
    move and the Metropolis move must agree on the basic physics.
    """
    for updater in ("metropolis", "wolff"):
        cfg = XYRunConfig(L=12, n_temps=3, T_min=0.3, T_max=1.2,
                          n_burnin=200, n_sweeps=400, sample_every=10,
                          updater=updater, device="cpu")
        r = run_xy(cfg)
        assert r.helicity_modulus.shape == (3,)
        assert r.helicity_modulus[0] > 0.5, \
            f"{updater}: cold lattice should be stiff, got Υ={r.helicity_modulus[0]:.3f}"


@pytest.mark.skipif(not CUDA_AVAILABLE, reason="GPU not available")
def test_xy_tiny_gpu_run_smoke():
    """Smoke test: a tiny XY GPU run produces sensible-shaped outputs."""
    cfg = XYRunConfig(L=16, n_temps=5, T_min=0.6, T_max=1.1,
                      n_burnin=20, n_sweeps=40, sample_every=10, device="cuda")
    r = run_xy(cfg)
    assert r.T.shape == (5,)
    assert r.helicity_modulus.shape == (5,)
    assert r.energy.shape == (5,) and (r.energy >= -2.0001).all()
    assert r.abs_mag.shape == (5,) and (r.abs_mag <= 1.0 + 1e-6).all()
