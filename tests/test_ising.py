import math

import numpy as np
import pytest
import torch

from lab.ising import RunConfig, run
from lab.ising_tri import TriRunConfig
from lab.ising_tri import run as run_tri
from lab.potts import PottsRunConfig
from lab.potts import run as run_potts
from lab.xy import XYRunConfig
from lab.xy import run as run_xy
from lab.heisenberg import HeisenbergRunConfig, _random_unit_vectors
from lab.heisenberg import run as run_heis
from lab.ising_afm import AFMRunConfig
from lab.ising_afm import run as run_afm


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


# ── M09: 2D Heisenberg engine (heisenberg) — O(3) unit vectors, Mermin–Wagner ──
def test_heisenberg_runconfig_defaults():
    cfg = HeisenbergRunConfig()
    assert cfg.L == 32
    assert cfg.updater == "metropolis"
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


def test_heisenberg_rejects_unknown_updater():
    cfg = HeisenbergRunConfig(L=8, n_temps=1, n_burnin=1, n_sweeps=2,
                              updater="banana", device="cpu")
    with pytest.raises(ValueError, match="unknown updater"):
        run_heis(cfg)


def test_heisenberg_uniform_sphere_sampling():
    """The proposal/init must sample UNIFORMLY on S² — not pole-biased.

    The classic O(3) bug is drawing (θ, φ) both uniform, which over-weights the
    poles and systematically corrupts every energy and correlation. Uniform-on-
    sphere requires z = cos θ uniform in [−1, 1], so over many samples ⟨z⟩ ≈ 0 AND
    ⟨|z|⟩ ≈ 0.5 (the giveaway: a θ-uniform pole bias pushes ⟨|z|⟩ well above 0.5).
    Every vector is also a genuine unit vector.
    """
    g = torch.Generator(device="cpu").manual_seed(0)
    V = _random_unit_vectors((100000,), g, torch.device("cpu"))
    norms = torch.linalg.vector_norm(V, dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)
    z = V[..., 2]
    assert abs(float(z.mean())) < 0.02, "mean z must be ~0 (no hemisphere bias)"
    # Uniform z → E|z| = 0.5; a θ-uniform pole bias would push this well above 0.5.
    assert abs(float(z.abs().mean()) - 0.5) < 0.02, "E|z| must be ~0.5 (no pole bias)"
    # x and y centred too (azimuthal symmetry).
    assert abs(float(V[..., 0].mean())) < 0.02 and abs(float(V[..., 1].mean())) < 0.02


def test_heisenberg_cpu_run_smoke():
    """A tiny CPU Heisenberg run produces sensible-shaped, physically valid output.

    The headline observable is ⟨|m|⟩, the Mermin–Wagner drift order parameter. We
    assert the shapes, that the energy per spin lives in its bond range [-2, 2]
    (O(3) dots ∈ [-1, 1], 0.5 de-double-counts the 2N bonds), that ⟨|m|⟩ ∈ [0, 1],
    that χ is a non-negative variance, and that the realized Metropolis acceptance
    is a sane fraction (the per-T-tuned δ keeping it off the 0/1 rails).
    """
    cfg = HeisenbergRunConfig(L=12, T_min=0.7, T_max=0.7, n_temps=1,
                              n_burnin=200, n_sweeps=400, sample_every=10,
                              over_relax=3, device="cpu")
    r = run_heis(cfg)
    assert r.T.shape == (1,)
    assert r.abs_mag.shape == (1,)
    assert r.abs_mag_err.shape == (1,) and (r.abs_mag_err >= 0).all()
    assert r.chi.shape == (1,) and (r.chi >= -1e-6).all()
    assert r.energy.shape == (1,)
    assert r.acceptance.shape == (1,)
    # Energy per spin e = -0.5·⟨S·Σ_4 nbr⟩ ∈ [-2, 2] (dots ∈ [-1,1], 0.5 de-double).
    assert (r.energy >= -2.0001).all() and (r.energy <= 2.0001).all()
    # ⟨|m|⟩ is a vector-magnetization fraction in [0, 1].
    assert (r.abs_mag >= -1e-6).all() and (r.abs_mag <= 1.0 + 1e-6).all()
    # Acceptance is a real fraction, comfortably off the 0/1 rails (δ is tuned).
    assert (r.acceptance > 0.05).all() and (r.acceptance < 0.99).all()


def test_heisenberg_low_T_aligned_high_T_floppy():
    """The core physics: a cold O(3) lattice aligns (low E, high |m|), a hot one melts.

    This calibrates the ΔE sign and the dot-product energy — a sign error leaves
    the lattice stuck disordered at all T. A wide T window with a cold and a hot
    point pins both ends. CPU so it always runs (no GPU dependency).
    """
    cfg = HeisenbergRunConfig(L=12, T_min=0.2, T_max=3.0, n_temps=4,
                              n_burnin=400, n_sweeps=700, sample_every=10,
                              over_relax=3, device="cpu")
    r = run_heis(cfg)
    # Coldest: nearly aligned — energy approaches the ground state -2, |m| high.
    assert r.energy[0] < -1.5, f"cold lattice should align (E→-2), got {r.energy[0]:.3f}"
    assert r.abs_mag[0] > 0.6, f"cold lattice should magnetize, got |m|={r.abs_mag[0]:.3f}"
    # Hottest: floppy — energy well above the ground state, |m| small.
    assert r.energy[-1] > r.energy[0]
    assert r.abs_mag[-1] < r.abs_mag[0]


def test_heisenberg_mermin_wagner_drift():
    """The Mermin–Wagner signature: ⟨|m|⟩ DECREASES as L grows at a fixed T.

    This is the whole point of M09 — there is no finite-T order, so the per-spin
    magnetization drifts toward 0 with system size. A single L would fake a finite
    ⟨|m|⟩; the drift across L is what verifies the *absence*. Small lattices + short
    runs on CPU keep it a fast but unambiguous monotone check (the engine halves
    |m| per doubling of L on the GPU at these settings; even short CPU runs keep
    the inequalities clear).
    """
    mags = []
    for L in (8, 16, 24):
        cfg = HeisenbergRunConfig(L=L, T_min=0.7, T_max=0.7, n_temps=1,
                                  n_burnin=400, n_sweeps=700, sample_every=10,
                                  over_relax=3, seed=42, device="cpu")
        mags.append(float(run_heis(cfg).abs_mag[0]))
    assert mags[0] > mags[1] > mags[2], (
        f"⟨|m|⟩ must drift down with L (Mermin–Wagner), got {mags}"
    )


def test_heisenberg_metropolis_and_wolff_both_run():
    """Both updaters run and align a cold lattice (low E) — the embedded-Wolff
    reflection (across the plane ⊥ the random axis, flipping ε) must order, not heat.

    M09 drives Metropolis-plus-over-relaxation; the embedded-cluster Wolff path is
    the alternative for the low-T (large-ξ) points. This exercises both on CPU and
    checks they each drive a cold lattice toward alignment (E < -1) — a Wolff that
    reflected through the axis instead of across the ⊥ plane would fail to order.
    """
    for updater in ("metropolis", "wolff"):
        cfg = HeisenbergRunConfig(L=12, T_min=0.3, T_max=0.3, n_temps=1,
                                  n_burnin=300, n_sweeps=500, sample_every=10,
                                  over_relax=3, updater=updater, device="cpu")
        r = run_heis(cfg)
        assert r.energy.shape == (1,)
        assert r.energy[0] < -1.0, \
            f"{updater}: cold lattice should align (E<-1), got E={r.energy[0]:.3f}"


# ── M10: antiferromagnetic Ising engine (ising_afm) — staggered order, J=-1 ───
def test_afm_runconfig_defaults():
    cfg = AFMRunConfig()
    assert cfg.L == 128
    assert cfg.J == -1.0          # antiferromagnetic by default
    assert cfg.n_temps == 25
    assert cfg.n_samples() == cfg.n_sweeps // cfg.sample_every


def test_afm_cpu_run_smoke():
    """A tiny CPU AFM run produces sensible-shaped, physically valid output.

    The headline observable is the STAGGERED magnetization m_s — near 1 when the
    Néel state orders, near 0 disordered — while the UNIFORM ⟨|m|⟩ stays ≈0 (the
    AFM carries no net moment). Shapes, m_s/⟨|m|⟩ ∈ [0,1], non-negative variances,
    and the energy range [-2, 0] are all asserted.
    """
    cfg = AFMRunConfig(L=16, n_temps=4, T_min=1.8, T_max=2.8,
                       n_burnin=40, n_sweeps=120, sample_every=5, device="cpu")
    r = run_afm(cfg)
    assert r.T.shape == (4,)
    assert r.stag_mag.shape == (4,)
    assert r.stag_mag_err.shape == (4,) and (r.stag_mag_err >= 0).all()
    assert r.chi_staggered.shape == (4,) and (r.chi_staggered >= -1e-6).all()
    assert r.abs_mag.shape == (4,)
    assert r.energy.shape == (4,) and r.specific_heat.shape == (4,)
    # Staggered and uniform magnetizations are per-spin fractions in [0, 1].
    assert (r.stag_mag >= -1e-6).all() and (r.stag_mag <= 1.0 + 1e-6).all()
    assert (r.abs_mag >= -1e-6).all() and (r.abs_mag <= 1.0 + 1e-6).all()
    assert (r.specific_heat >= -1e-6).all()
    # Energy per spin e = +0.5·⟨Σ_4 s·s⟩ with J=-1 → Néel ground state at -2 ≤ e ≤ 0.
    assert (r.energy >= -2.0001).all() and (r.energy <= 1e-6).all()
    assert len(r.snapshots) == 3


def test_afm_staggered_orders_uniform_does_not():
    """The core AFM physics + the headline trap, in one test.

    A cold antiferromagnet Néel-orders: the STAGGERED |m_s| → ~1, while the UNIFORM
    ⟨|m|⟩ stays ≈0 at EVERY temperature (the ground state carries no net moment).
    Reading uniform m would show nothing and look broken — so we assert the
    staggered order parameter does the work and the uniform one never does. A wide
    T window with a cold and a hot point pins both ends. CPU so it always runs.
    """
    tc = 2.0 / math.log(1.0 + math.sqrt(2.0))
    cfg = AFMRunConfig(L=24, T_min=0.5 * tc, T_max=1.5 * tc, n_temps=6,
                       n_burnin=500, n_sweeps=900, sample_every=10, device="cpu")
    r = run_afm(cfg)
    # Coldest: the staggered (Néel) order parameter is high.
    assert r.stag_mag[0] > 0.8, f"cold AFM should Néel-order, got |m_s|={r.stag_mag[0]:.3f}"
    # Hottest: staggered order melts.
    assert r.stag_mag[-1] < 0.3, f"hot AFM should disorder, got |m_s|={r.stag_mag[-1]:.3f}"
    # THE trap: the uniform magnetization stays ≈0 at ALL T — including the cold,
    # ordered end. (A silent sign-flip to the FM would make this large at low T.)
    assert (r.abs_mag < 0.15).all(), \
        f"uniform ⟨|m|⟩ must stay ≈0 for the AFM, got {r.abs_mag}"
    # Cold energy approaches the Néel ground state -2.
    assert r.energy[0] < -1.5, f"cold AFM energy should near -2, got {r.energy[0]:.3f}"


def test_afm_fm_gauge_duality():
    """The strongest correctness guard: AFM-staggered == FM-uniform at the same |J|.

    On a bipartite lattice the sublattice gauge flip turns the antiferromagnet
    EXACTLY into the ferromagnet, so the AFM's staggered observables must equal an
    FM run's uniform observables at the same parameters and seed. With identical
    RNG streams the two even track configuration-by-configuration under the gauge
    map, so they agree to well within Monte-Carlo noise. This catches a silent sign
    error in ΔE that would secretly revert the model to the FM (which would still
    peak at 2.2692, but on the wrong observable). CPU so it always runs.
    """
    common = dict(L=24, T_min=2.0, T_max=2.6, n_temps=7, n_burnin=600,
                  n_sweeps=1000, sample_every=10, seed=7, device="cpu")
    r_afm = run_afm(AFMRunConfig(J=-1.0, **common))
    r_fm = run(RunConfig(**common))   # the untouched FM engine: uniform |m|, chi_abs
    # Staggered AFM order parameter ≈ uniform FM order parameter, bond-for-bond.
    dm = float(np.abs(np.asarray(r_afm.stag_mag) - np.asarray(r_fm.abs_mag)).max())
    de = float(np.abs(np.asarray(r_afm.energy) - np.asarray(r_fm.energy)).max())
    assert dm < 0.05, f"AFM staggered |m_s| must match FM uniform |m| (duality), max Δ={dm:.4f}"
    assert de < 0.05, f"AFM energy must match FM energy (duality), max Δ={de:.4f}"


@pytest.mark.skipif(not CUDA_AVAILABLE, reason="GPU not available")
def test_afm_tiny_gpu_run_smoke():
    """Smoke test: a tiny AFM GPU run produces sensible-shaped outputs."""
    cfg = AFMRunConfig(L=16, n_temps=5, T_min=2.0, T_max=2.6,
                       n_burnin=20, n_sweeps=40, sample_every=10, device="cuda")
    r = run_afm(cfg)
    assert r.T.shape == (5,)
    assert r.stag_mag.shape == (5,) and (r.stag_mag <= 1.0 + 1e-6).all()
    assert r.chi_staggered.shape == (5,) and (r.chi_staggered >= -1e-6).all()
    assert r.abs_mag.shape == (5,) and (r.abs_mag <= 1.0 + 1e-6).all()
    assert r.energy.shape == (5,) and (r.energy >= -2.0001).all()


@pytest.mark.skipif(not CUDA_AVAILABLE, reason="GPU not available")
def test_heisenberg_tiny_gpu_run_smoke():
    """Smoke test: a tiny Heisenberg GPU run produces sensible-shaped outputs."""
    cfg = HeisenbergRunConfig(L=16, T_min=0.5, T_max=1.0, n_temps=3,
                              n_burnin=20, n_sweeps=40, sample_every=10, device="cuda")
    r = run_heis(cfg)
    assert r.T.shape == (3,)
    assert r.abs_mag.shape == (3,) and (r.abs_mag <= 1.0 + 1e-6).all()
    assert r.energy.shape == (3,) and (r.energy >= -2.0001).all()
    assert r.chi.shape == (3,) and (r.chi >= -1e-6).all()
