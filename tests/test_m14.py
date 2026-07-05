"""M14 random-bond Ising — the Nishimori-line engine, the runner, the check.

Three layers, matching the house style (cf. ``test_m13.py`` + ``test_m12.py``):

* **The engine** (``random_bond.py``) runs on CPU with tiny lattices: the ±J bonds are
  drawn at a tunable AF fraction ``p`` (the one change from M11's 50/50 draw), the energy
  estimator is the M11 one, and the load-bearing physics assertion is that ON the Nishimori
  line the disorder-averaged energy per spin reproduces the EXACT identity
  ``E/N = −2 tanh(1/T) = −2(1−2p)`` — a gauge-symmetry identity that holds at any L, which is
  why the lab can calibrate the frontier cheaply.
* **The runner** (``m14.py``) sweeps p up the Nishimori line, grades the energy at the
  largest L, and maps the ferro-order collapse toward the multicritical point.
* **The check** (``checks.check_m14``) *re-derives* the exact energy from each point's own
  temperature (a receipt) and owns its tolerance; the honest-null path is exercised too.
"""
import math

import pytest

from lab.random_bond import (
    RandomBondConfig, RandomBondResult, run,
    nishimori_temperature, nishimori_energy_per_spin,
)
from lab.m14 import run_m14, to_report, M14Result, _cross_below, _binder_crossing_p, ENERGY_TOL
from lab.checks import check_m14


# ─────────────────────────── the Nishimori-line closed forms ──────────────────────────────
def test_nishimori_temperature_inverts_the_line_condition():
    # tanh(1/T_NL) must equal 1 − 2p by construction of the Nishimori line.
    for p in (0.05, 0.1094, 0.2, 0.4):
        T = nishimori_temperature(p)
        assert math.tanh(1.0 / T) == pytest.approx(1.0 - 2.0 * p, abs=1e-9)


def test_nishimori_temperature_at_mnp_matches_benchmark():
    # p_c ≈ 0.1094 sits at T_c ≈ 0.9528 — the multicritical point on the line.
    assert nishimori_temperature(0.1094) == pytest.approx(0.9528, abs=2e-3)


def test_nishimori_temperature_rejects_out_of_range():
    for bad in (0.0, 0.5, 0.7, -0.1):
        with pytest.raises(ValueError):
            nishimori_temperature(bad)


def test_nishimori_energy_is_minus_two_tanh():
    T = nishimori_temperature(0.1)
    assert nishimori_energy_per_spin(T) == pytest.approx(-2.0 * math.tanh(1.0 / T))
    # On the line this also equals −2(1−2p).
    assert nishimori_energy_per_spin(T) == pytest.approx(-2.0 * (1.0 - 2.0 * 0.1), abs=1e-9)


# ───────────────────────────────── the engine: physics ────────────────────────────────────
def test_engine_smoke_and_json():
    cfg = RandomBondConfig(L=8, p=0.1, T=nishimori_temperature(0.1), n_realizations=8,
                           n_burnin=200, n_sweeps=600, sample_every=20, seed=1, device="cpu")
    r = run(cfg)
    assert isinstance(r, RandomBondResult)
    assert -2.001 <= r.energy <= 0.001          # energy/spin in [−2, 0] on the square lattice
    assert 0.0 <= r.abs_mag <= 1.0
    assert r.on_nishimori_line is True
    j = r.to_json()
    assert j["config"]["p"] == 0.1 and "energy" in j


def test_engine_reproduces_exact_nishimori_line_energy():
    """The load-bearing calibration: on the Nishimori line the disorder-averaged energy per
    spin matches the EXACT −2 tanh(1/T) identity — at tiny L, because it is a gauge-symmetry
    identity, not a finite-size-shifted critical temperature. A wrong bond draw or estimator
    would miss it by far more than the tolerance."""
    for p in (0.05, 0.10, 0.15):
        T = nishimori_temperature(p)
        cfg = RandomBondConfig(L=16, p=p, T=T, n_realizations=48, n_burnin=1500,
                               n_sweeps=5000, sample_every=20, seed=3, device="cpu")
        r = run(cfg)
        assert r.energy == pytest.approx(nishimori_energy_per_spin(T), abs=0.05)


def test_engine_p_zero_limit_is_the_clean_ferromagnet():
    """At p→0 the random-bond model is the clean ferromagnet: on the (cold) Nishimori line
    it is deep in the ordered phase, so ⟨|m|⟩ is large. A tiny p keeps that order."""
    p = 0.01
    cfg = RandomBondConfig(L=16, p=p, T=nishimori_temperature(p), n_realizations=16,
                           n_burnin=1000, n_sweeps=3000, sample_every=20, seed=5, device="cpu")
    r = run(cfg)
    # Strongly ordered: |m| sits well above the disordered regime (~0.2-0.4 at p≳0.15).
    # A tiny lattice + short sweep at this cold T doesn't fully saturate to 1, so the
    # bar is a clear-order threshold, not saturation.
    assert r.abs_mag > 0.6                       # strongly ferromagnetic at small p


def test_engine_determinism():
    cfg = RandomBondConfig(L=8, p=0.1094, T=0.9528, n_realizations=8, n_burnin=100,
                           n_sweeps=400, sample_every=20, seed=9, device="cpu")
    r1, r2 = run(cfg), run(cfg)
    assert r1.energy == r2.energy and r1.abs_mag == r2.abs_mag


# ─────────────────────────────── runner reducers (stdlib) ──────────────────────────────────
def test_cross_below_interpolates_the_half_crossing():
    ps = [0.05, 0.10, 0.15, 0.20]
    ms = [0.90, 0.70, 0.30, 0.10]                # crosses 0.5 between 0.10 and 0.15
    ph = _cross_below(ps, ms, 0.5)
    assert 0.10 < ph < 0.15


def test_cross_below_returns_none_without_a_crossing():
    assert _cross_below([0.05, 0.1], [0.9, 0.8], 0.5) is None


def test_binder_crossing_none_when_curves_do_not_cross():
    # The honest reachable-scale outcome: U_large stays below U_small (no + → − of the diff).
    ps = [0.06, 0.08, 0.10, 0.12]
    u_small = [0.66, 0.65, 0.64, 0.60]
    u_large = [0.62, 0.59, 0.59, 0.54]
    assert _binder_crossing_p(ps, u_small, u_large) is None


def test_binder_crossing_found_when_they_cross():
    ps = [0.06, 0.10, 0.14]
    u_small = [0.60, 0.55, 0.50]
    u_large = [0.66, 0.55, 0.40]                 # diff runs + → − across the middle
    ph = _binder_crossing_p(ps, u_small, u_large)
    assert ph is not None and 0.06 <= ph <= 0.14


# ──────────────────────────────── runner + report + check ──────────────────────────────────
def test_run_m14_tiny_resolves_the_exact_energy():
    """The full runner over a small real sweep returns a check-ready result whose gate-L
    energy reproduces the exact Nishimori-line identity — a genuine physics assertion."""
    calls = []
    result = run_m14(p_values=(0.05, 0.10, 0.1094, 0.15), L_values=(8, 12),
                     n_realizations=24, n_sweeps=4000, n_burnin=1500, seed=3, device="cpu",
                     progress=lambda L, p, r: calls.append((L, p)))
    assert isinstance(result, M14Result)
    assert len(calls) == 8                        # 2 L × 4 p
    assert result.gate_L == 12
    assert len(result.calibration_points) == 4
    assert result.on_nishimori_line is True
    assert result.max_energy_dev <= ENERGY_TOL
    assert result.energy_resolved is True


def _toy_m14_result(resolved=True):
    """A hand-built result so ``to_report`` shape / null tests don't depend on a Monte-Carlo
    run landing on either side of tolerance."""
    ps = [0.05, 0.10, 0.1094, 0.15]
    Ts = [nishimori_temperature(p) for p in ps]
    exact = [nishimori_energy_per_spin(T) for T in Ts]
    meas = list(exact) if resolved else [e + 0.3 for e in exact]
    pts = [{"p": ps[i], "T": Ts[i], "energy": meas[i], "energy_err": 0.005,
            "energy_exact": exact[i], "abs_dev": abs(meas[i] - exact[i])} for i in range(4)]
    return M14Result(
        p_values=ps, T_values=Ts, L_values=[8, 12], gate_L=12,
        energy_by_L={"8": meas, "12": meas}, energy_err_by_L={"8": [0.005] * 4, "12": [0.005] * 4},
        abs_mag_by_L={"8": [0.95, 0.85, 0.80, 0.55], "12": [0.96, 0.88, 0.70, 0.45]},
        binder_by_L={"8": [0.66, 0.64, 0.63, 0.55], "12": [0.62, 0.59, 0.57, 0.48]},
        energy_exact=exact, calibration_points=pts,
        max_energy_dev=max(pt["abs_dev"] for pt in pts),
        energy_resolved=resolved, on_nishimori_line=True,
        mnp_order_p_half=0.12, binder_crossing_p=None,
        p_c_benchmark=0.1094, t_c_benchmark=0.9528, n_realizations=24,
        wall_seconds=10.0, config={"model": "random-bond-ising-2d"},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_m14_result(resolved=True))
    assert rep["experiment"] == "M14-random-bond-nishimori"
    assert len(rep["calibration_points"]) == 4
    assert rep["p_c_benchmark"] == 0.1094
    assert "status" not in rep                     # resolved → not a null
    assert "nishimori" in rep["headline"].lower()


def test_to_report_unresolved_is_honest_null():
    rep = to_report(_toy_m14_result(resolved=False))
    assert rep["energy_resolved"] is False
    assert rep["status"] == "null"                 # honest failed-calibration grey leaf
    assert "calibration null" in rep["headline"]


def test_check_m14_reads_a_real_engine_curve_end_to_end():
    """End-to-end receipt on genuine Monte-Carlo data: the engine's energy → report → check,
    where the check re-derives −2 tanh(1/T) itself. Corrupting the stored energies at a point
    the check re-grades must flip the grade; corrupting a non-graded field must not."""
    result = run_m14(p_values=(0.05, 0.10, 0.1094, 0.15), L_values=(8, 12),
                     n_realizations=24, n_sweeps=4000, n_burnin=1500, seed=3, device="cpu")
    rep = to_report(result)
    assert check_m14(rep)[0] is True               # real curve sits on the exact identity
    # A lie in a NON-graded field (the reported exact) must not change the receipt.
    rep["energy_exact"] = [0.0, 0.0, 0.0, 0.0]
    assert check_m14(rep)[0] is True
    # But breaking the measured energies away from the identity must fail.
    for pt in rep["calibration_points"]:
        pt["energy"] = pt["energy"] + 0.5
    assert check_m14(rep)[0] is False


def test_check_m14_rejects_off_line_points():
    """A point that is NOT on the Nishimori line has no exact-energy identity to test, so the
    check flags it rather than mis-grading — the run can't smuggle an off-line point in."""
    rep = to_report(_toy_m14_result(resolved=True))
    # Move one point off the line (T no longer satisfies tanh(1/T)=1−2p) but keep its energy.
    rep["calibration_points"][0]["T"] = rep["calibration_points"][0]["T"] * 1.5
    ok, detail = check_m14(rep)
    assert ok is False
    assert "off the nishimori line" in detail.lower()


def test_check_m14_not_applicable_to_other_reports():
    assert check_m14({"experiment": "M13-triangular-afm"})[0] is None
    assert check_m14({"experiment": "M01-ising-verification"})[0] is None
