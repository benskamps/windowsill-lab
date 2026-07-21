"""M06 3D-Ising — the Wolff/Metropolis updater wiring.

``run_m06`` (and the ``run_m06_l_extrapolation`` driver that calls it) gained an
``updater`` switch so the 3D benchmark and its L-extrapolation can sample with the
Wolff single-cluster algorithm (z ≈ 0.3) instead of single-spin Metropolis
(z ≈ 2 near criticality) — the instrument BACKLOG points the extrapolation at so
larger L become tractable without critical slowing down. Until now
``wolff3d.wolff_run`` was fully built and tested but *unreachable* from any
milestone driver; this closes that gap, mirroring ``run_fss(updater=...)`` (M02).

These tests prove:

1. the wolff branch is wired end-to-end through ``run_m06`` and records
   ``config['updater']``;
2. the metropolis branch is unchanged, is the default, and is selectable;
3. an unknown updater fails loudly rather than silently mis-sampling;
4. the two updaters agree on the χ-peak location (T_c estimate) *inside M06's
   critical window* — the exact regime the milestone samples;
5. the switch threads through ``run_m06_l_extrapolation`` and is recorded there too.

Everything runs on ``device='cpu'`` with tiny lattices and short runs so the
module finishes in a few seconds with no GPU dependency, honoring the
device-safety reasoning documented on ``run_m06`` / ``ising3d``.
"""
import inspect

import numpy as np
import pytest

from lab.m06 import TC_3D, run_m06, run_m06_l_extrapolation


# --------------------------------------------------------------------------- #
# wiring: the wolff branch runs end-to-end and records the choice
# --------------------------------------------------------------------------- #
def test_run_m06_wolff_smoke_cpu():
    """A tiny CPU ``run_m06(updater='wolff')`` produces a sane single-L result."""
    r = run_m06(
        L=6, T_min=4.2, T_max=4.9, n_temps=5,
        n_sweeps=200, n_burnin=60, seed=7, updater="wolff", device="cpu",
    )
    assert len(r.T) == 5 and len(r.chi) == 5
    assert r.config["updater"] == "wolff"
    assert r.config["device"] == "cpu"
    assert min(r.T) <= r.tc_chi <= max(r.T)          # peak sits inside the window
    assert np.isfinite(r.tc_chi_refined)
    assert all(c >= -1e-9 for c in r.chi)            # |m|-susceptibility is non-negative
    assert all(s >= -1e-9 for s in r.specific_heat)  # variance observable ≥ 0


def test_run_m06_metropolis_still_selectable():
    """The metropolis branch is unchanged and selectable via the flag."""
    r = run_m06(
        L=6, T_min=4.2, T_max=4.9, n_temps=5,
        n_sweeps=400, n_burnin=200, seed=7, updater="metropolis",
    )
    assert r.config["updater"] == "metropolis"
    assert len(r.chi) == 5
    assert np.isfinite(r.tc_chi_refined)


def test_run_m06_rejects_unknown_updater():
    """An unknown updater raises rather than silently mis-sampling."""
    with pytest.raises(ValueError, match="unknown updater"):
        run_m06(
            L=6, n_temps=3, n_sweeps=20, n_burnin=5, updater="glauber",
        )


def test_default_updater_is_metropolis():
    """M06's default stays the verified checkerboard engine (non-breaking).

    Unlike M02 (which defaults to Wolff), the single-L M06 milestone and its
    golden reports were calibrated on the Metropolis engine, so the default must
    reproduce them exactly. Wolff is the opt-in instrument for the larger-L
    L-extrapolation.
    """
    assert inspect.signature(run_m06).parameters["updater"].default == "metropolis"
    assert (
        inspect.signature(run_m06_l_extrapolation).parameters["updater"].default
        == "metropolis"
    )


# --------------------------------------------------------------------------- #
# physics: Wolff and Metropolis agree on the χ-peak in M06's critical window
# --------------------------------------------------------------------------- #
def test_wolff_metropolis_agree_on_tc_in_m06_window():
    """The χ-peak T_c estimate agrees across updaters inside M06's window.

    Both engines sample the same Boltzmann distribution, so the pseudo-critical
    peak they report on the *same* small lattice must coincide to within the grid
    spacing plus short-run noise. A cluster-construction bug (wrong p, double-
    counted bonds, mid-flood resampling) would shift the Wolff peak away from the
    Metropolis one that already lands the 3D benchmark T_c ≈ 4.5115.

    Small L=6 with a coarse 5-point window straddling 4.5115: the discrete argmax
    can differ by at most one grid step (ΔT = 0.175 here); we allow a bit more for
    the short-run fluctuation, and separately assert both land in the physical
    neighbourhood of the benchmark rather than at a window edge.
    """
    kw = dict(L=6, T_min=4.15, T_max=4.85, n_temps=5, seed=123)
    w = run_m06(n_sweeps=800, n_burnin=200, updater="wolff", device="cpu", **kw)
    m = run_m06(n_sweeps=1500, n_burnin=800, updater="metropolis", **kw)

    # Same temperature grid — compared with a tolerance because the Wolff (torch)
    # engine builds its linspace in float32 and the Metropolis (numpy) engine in
    # float64, so the shared grid differs only at the ~1e-6 rounding level.
    assert np.allclose(np.asarray(w.T), np.asarray(m.T), atol=1e-5)
    grid_step = w.T[1] - w.T[0]
    # χ-peak locations agree within ~one grid step + short-run slack.
    assert abs(w.tc_chi - m.tc_chi) <= 1.5 * grid_step, (w.tc_chi, m.tc_chi)
    # Both estimates sit in the physical neighbourhood of the benchmark (a sign or
    # observable-selection error would push the peak to a window edge).
    for tc in (w.tc_chi, m.tc_chi):
        assert abs(tc - TC_3D) < 0.5, tc


# --------------------------------------------------------------------------- #
# wiring: the switch threads through the L-extrapolation driver
# --------------------------------------------------------------------------- #
def test_l_extrapolation_forwards_and_records_updater():
    """``run_m06_l_extrapolation(updater='wolff')`` runs and records the choice.

    Two tiny lattices, short Wolff runs — this is a wiring/provenance test, not a
    precision-T_c claim (the fit needs ≥3 L and a real sweep budget for a sharp
    intercept). It proves the updater reaches every per-L run and lands in config.
    """
    res = run_m06_l_extrapolation(
        Ls=(6, 8), T_min=4.3, T_max=4.75, n_temps=4,
        n_sweeps=150, n_burnin=50, seed=11, updater="wolff", device="cpu",
    )
    assert res.config["updater"] == "wolff"
    assert res.config["device"] == "cpu"
    assert res.Ls == [6, 8]
    assert len(res.tc_of_L) == 2
    assert np.isfinite(res.tc_inf)
    # every per-L record carries a refined T_c
    assert all("tc_chi_refined" in rec for rec in res.per_L)
