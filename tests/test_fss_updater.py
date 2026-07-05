"""M02 finite-size scaling — the Wolff/Metropolis updater wiring.

``run_fss`` gained an ``updater`` switch so M02 can sample with the Wolff cluster
algorithm (z ≈ 0.25) instead of single-spin Metropolis (z ≈ 2.17) and thereby
reach L ≥ 512 without critical slowing down (see BACKLOG's cluster-algorithm
section). These tests prove:

1. the wolff branch is wired end-to-end and records ``config['updater']``;
2. the metropolis branch still works and is selectable;
3. an unknown updater fails loudly rather than silently mis-sampling;
4. the two updaters agree on the physics (⟨|m|⟩ and energy) *inside M02's
   critical window* — the exact regime M02 samples. (Low-/high-T agreement is
   already covered by ``test_wolff.py``; this pins agreement AT criticality,
   which is where the whole updater swap has to be trustworthy.)

Everything runs on ``device='cpu'`` with tiny lattices and short runs so the
module finishes in a few seconds with no GPU dependency, honoring the
GPU-SAFETY CONTRACT documented on ``run_fss`` / ``run_m03``.
"""
import numpy as np
import pytest

from lab.fss import run_fss, DEFAULT_L
from lab.ising import RunConfig, run
from lab.wolff import WolffConfig, wolff_run


# --------------------------------------------------------------------------- #
# wiring: the wolff branch runs end-to-end and records the choice
# --------------------------------------------------------------------------- #
def test_run_fss_wolff_smoke_cpu():
    """A tiny CPU ``run_fss(updater='wolff')`` produces a sane FSS result."""
    res = run_fss(
        L_values=(8, 12), T_min=2.24, T_max=2.34, n_temps=4,
        n_sweeps=120, n_burnin=40, seed=7, device="cpu", updater="wolff",
    )
    assert len(res.curves) == 2
    for c in res.curves:
        assert len(c.T) == 4 and len(c.chi) == 4
        assert c.chi_max > 0.0                      # χ_abs peak is positive
        assert 2.24 <= c.T_peak <= 2.34             # peak sits inside the window
    assert res.config["updater"] == "wolff"
    assert np.isfinite(res.slope)                   # log-log fit produced a number


def test_run_fss_metropolis_still_selectable():
    """The metropolis branch is unchanged and selectable via the flag."""
    res = run_fss(
        L_values=(8, 12), T_min=2.24, T_max=2.34, n_temps=4,
        n_sweeps=400, n_burnin=100, seed=7, device="cpu", updater="metropolis",
    )
    assert len(res.curves) == 2
    assert res.config["updater"] == "metropolis"
    assert all(c.chi_max > 0.0 for c in res.curves)
    assert np.isfinite(res.slope)


def test_run_fss_rejects_unknown_updater():
    """An unknown updater raises rather than silently mis-sampling."""
    with pytest.raises(ValueError, match="unknown updater"):
        run_fss(
            L_values=(8,), n_temps=3, n_sweeps=20, n_burnin=5,
            device="cpu", updater="glauber",
        )


def test_default_updater_is_wolff():
    """The FSS default is the cluster algorithm — the criticality instrument."""
    import inspect
    sig = inspect.signature(run_fss)
    assert sig.parameters["updater"].default == "wolff"


# --------------------------------------------------------------------------- #
# physics: Wolff and Metropolis agree AT criticality (M02's actual regime)
# --------------------------------------------------------------------------- #
def _wolff_TL(T_min, T_max, n_temps, L):
    cfg = WolffConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_burnin=200, n_updates=1000, sample_every=2, seed=42, device="cpu",
    )
    return wolff_run(cfg)


def _metro_TL(T_min, T_max, n_temps, L):
    cfg = RunConfig(
        L=L, T_min=T_min, T_max=T_max, n_temps=n_temps,
        n_burnin=1500, n_sweeps=4000, sample_every=4, seed=42, device="cpu",
    )
    return run(cfg)


def test_wolff_metropolis_agree_in_m02_window():
    """⟨|m|⟩ and energy agree across the two updaters inside M02's T-window.

    Two temperatures straddling T_c ≈ 2.269 on L=16. This is the same
    detailed-balance cross-check ``test_wolff.py`` runs at low/high T, but pinned
    to the critical window M02 actually sweeps — the regime where swapping the
    updater must not change the sampled distribution. Tolerances match the loose,
    short-run bounds used in ``test_wolff.py`` (a few×σ on a tiny sample).
    """
    T_min, T_max, n_temps, L = 2.20, 2.34, 2, 16
    w = _wolff_TL(T_min, T_max, n_temps, L)
    m = _metro_TL(T_min, T_max, n_temps, L)

    assert np.array_equal(w.T, m.T)
    for i in range(n_temps):
        assert abs(w.abs_mag[i] - m.abs_mag[i]) < 0.15, (i, w.abs_mag[i], m.abs_mag[i])
        assert abs(w.energy[i] - m.energy[i]) < 0.15, (i, w.energy[i], m.energy[i])
        # physical bounds: energy per spin in [-2, 0], |m| in [0, 1]
        assert -2.0 <= w.energy[i] <= 0.0
        assert 0.0 <= w.abs_mag[i] <= 1.0 + 1e-6


def test_default_L_documents_cluster_extension():
    """DEFAULT_L is the historical Metropolis-safe tuple; Wolff lifts the cap."""
    assert DEFAULT_L == (32, 64, 128, 256)
