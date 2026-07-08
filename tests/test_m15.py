"""M15 Glauber-dynamics domain growth — the engine, the exponent fit, the check.

Three layers, matching the house style (cf. ``test_m13.py`` / ``test_m14.py``):

* **The engine** (``glauber.py``) is pinned against *hand-computable* cases before it is ever
  pointed at a coarsening run: the heat-bath transition probability is brute-forced against its
  closed form ``σ(2βh)`` for every reachable field ``h``, the equal-time correlation is checked
  on lattices whose ``G(r)`` is exact by construction (uniform, periodic stripes), and the
  half-height domain-length estimator is checked on those same known curves.
* **The exponent fit** (``m15.fit_growth_exponent``) recovers a *known* slope from a synthetic
  perfect power law and honours the scaling window.
* **The runner + report + check** (``m15.py`` / ``checks.check_m15``) are exercised for a real
  (tiny) quench that coarsens, report shape + the honest-null path, and that the check
  *re-derives* the exponent from the report arrays (a receipt) — corrupting the stored exponent
  must not change the grade.
"""
import math

import numpy as np
import pytest
import torch

from lab.glauber import (
    QuenchConfig, QuenchResult, run,
    heatbath_prob_up, equal_time_correlation, domain_length_from_G,
    _energy_per_spin, _log_spaced_times,
)
from lab.m15 import (
    run_m15, to_report, M15Result, fit_growth_exponent,
    ALLEN_CAHN_EXPONENT, EXPONENT_TOL,
)
from lab.checks import check_m15


# ────────────────────────── the engine: heat-bath probability (brute force) ───────────────
def test_heatbath_prob_matches_closed_form_for_every_field():
    """Glauber/heat-bath P(s→+1) = σ(2βh) must equal 1/(1+e^{−2βh}) for every reachable integer
    field h ∈ {−4,−2,0,2,4} (four neighbours, ±1) at several temperatures — the defining rule,
    brute-forced against its closed form."""
    for h in (-4, -2, 0, 2, 4):
        for beta in (0.2, 0.5, 1.0 / 1.5, 1.3):
            p = float(heatbath_prob_up(torch.tensor([[float(h)]]), beta))
            exact = 1.0 / (1.0 + math.exp(-2.0 * beta * h))
            assert p == pytest.approx(exact, abs=1e-6), (h, beta, p, exact)


def test_heatbath_prob_is_symmetric_and_half_at_zero_field():
    # No local bias ⇒ a coin flip; ±h are mirror images summing to 1 (spin-inversion symmetry).
    beta = 0.7
    assert float(heatbath_prob_up(torch.tensor([[0.0]]), beta)) == pytest.approx(0.5)
    up_pos = float(heatbath_prob_up(torch.tensor([[2.0]]), beta))
    up_neg = float(heatbath_prob_up(torch.tensor([[-2.0]]), beta))
    assert up_pos + up_neg == pytest.approx(1.0, abs=1e-6)
    assert up_pos > 0.5 > up_neg


# ────────────────────────── the engine: correlation + domain length ───────────────────────
def test_uniform_lattice_correlation_is_all_ones():
    """A fully ordered lattice has G(r)=1 at every separation — no domain wall anywhere, so the
    half-height estimator saturates at the measured range (r_max = L//2)."""
    s = torch.ones((3, 16, 16), dtype=torch.int8)
    G = equal_time_correlation(s).numpy()
    assert np.allclose(G, 1.0, atol=1e-6)
    assert domain_length_from_G(G, threshold=0.5) == pytest.approx(16 // 2)


def test_periodic_stripe_correlation_is_exact():
    """Vertical stripes of period 4 (pattern +,+,−,−) have an EXACT axis-averaged correlation:
    constant (=1) along the stripe axis, and (1,0,−1,0,…) along the modulated axis, so the
    average is G=[1, ½, 0, ½, 1, …]. A closed-form target for both the FFT correlation and the
    half-height length (first drop through ½ is at r=1)."""
    row = torch.tensor([1, 1, -1, -1]).repeat(4)          # length 16, period 4
    s = row.view(1, 1, 16).expand(2, 16, 16).contiguous().to(torch.int8)
    G = equal_time_correlation(s).numpy()
    assert G[0] == pytest.approx(1.0)
    assert G[1] == pytest.approx(0.5, abs=1e-6)
    assert G[2] == pytest.approx(0.0, abs=1e-6)
    assert G[4] == pytest.approx(1.0, abs=1e-6)
    assert domain_length_from_G(G, threshold=0.5) == pytest.approx(1.0, abs=1e-6)


def test_domain_length_never_below_threshold_saturates():
    # A curve that never drops through the threshold returns the last r (a saturation flag the
    # scaling-window fit excludes), not a spurious small value.
    G = [1.0, 0.99, 0.98, 0.97]
    assert domain_length_from_G(G, threshold=0.5) == pytest.approx(3.0)


def test_energy_per_spin_on_known_configs():
    """Ising energy per spin: a fully aligned lattice sits at the ground state −2 (all four
    bonds satisfied); a perfect checkerboard sits at +2 (all four frustrated)."""
    up = torch.ones((1, 8, 8), dtype=torch.int8)
    assert float(_energy_per_spin(up)[0]) == pytest.approx(-2.0)
    ix = torch.arange(8).view(8, 1)
    iy = torch.arange(8).view(1, 8)
    checker = (((ix + iy) % 2) * 2 - 1).view(1, 8, 8).to(torch.int8)
    assert float(_energy_per_spin(checker)[0]) == pytest.approx(2.0)


def test_log_spaced_times_are_unique_and_bounded():
    ts = _log_spaced_times(1, 4000, 44)
    assert ts[0] == 1 and ts[-1] == 4000
    assert ts == sorted(ts)
    assert len(ts) == len(set(ts))                        # strictly increasing (no dupes)


# ────────────────────────────── the exponent fit ─────────────────────────────────────────
def test_fit_recovers_known_power_law_slope():
    """A synthetic perfect power law L = 1.3·t^0.5 must fit back to slope 0.5 with R²=1 inside
    the scaling window — the fit's own calibration before it touches Monte-Carlo noise."""
    t = np.array(_log_spaced_times(1, 4000, 44), dtype=float)
    L = 1.3 * t ** 0.5
    fit = fit_growth_exponent(t, L, L_box=512)
    assert fit is not None
    assert fit.exponent == pytest.approx(0.5, abs=1e-6)
    assert fit.r2 == pytest.approx(1.0, abs=1e-9)
    # The window excludes the finite-size-saturation ceiling: no fitted L exceeds sat_frac·L.
    assert fit.L_hi <= 0.20 * 512 + 1e-9


def test_fit_returns_none_without_a_window():
    # A flat/tiny L(t) that never enters [L_min_fit, sat_frac·L] yields no fittable window.
    t = np.array([1, 2, 3, 4, 5], dtype=float)
    L = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
    assert fit_growth_exponent(t, L, L_box=512) is None


# ─────────────────────────────── the runner (real tiny quench) ────────────────────────────
def test_glauber_run_smoke_and_json():
    cfg = QuenchConfig(L=48, T=1.5, n_seeds=4, t_max=200, n_times=20,
                       eq_burnin=200, eq_sample=200, seed=2, device="cpu")
    r = run(cfg)
    assert isinstance(r, QuenchResult)
    assert len(r.times) == len(r.L_corr) == len(r.energy)
    assert r.times[0] < r.times[-1]
    # Coarsening: the correlation length at the end exceeds the start (domains grew).
    assert r.L_corr[-1] > r.L_corr[0]
    # The reference equilibrium energy at T<T_c sits near (just above) the ground state −2.
    assert -2.001 < r.e_eq < -1.5
    j = r.to_json()
    assert j["config"]["dynamics"] if "dynamics" in j["config"] else True
    assert len(j["times"]) == len(j["L_corr"])


def test_run_m15_measures_a_positive_growth_exponent():
    """A real (tiny, CPU) quench coarsens: the correlation length grows as a clean-ish power
    law with a positive exponent in the physical ballpark. Small-scale finite-size noise keeps
    this a broad-band assertion — the precise Allen-Cahn number is the production run's job — but
    it is a genuine physics check, not just shape."""
    calls = []
    result = run_m15(L=64, T=1.5, n_seeds=6, t_max=400, n_times=26,
                     eq_burnin=300, eq_sample=300, seed=1, device="cpu",
                     progress=lambda r: calls.append(r))
    assert isinstance(result, M15Result)
    assert len(calls) == 1
    assert 0.30 < result.exponent < 0.80          # a real coarsening slope, not 0 or 1
    assert result.r2 > 0.9                         # a clean power law
    assert result.corr_fit.n_points >= 5
    assert result.energy_fit is not None


# ──────────────────────────────── report + check (receipt) ────────────────────────────────
def _synthetic_report(n=0.485, L_box=512, noise=0.0, seed=0):
    """A report with a clean synthetic L(t)=A·t^n so the check tests don't ride on a Monte-Carlo
    run landing on either side of the tolerance. Carries the window rule the check re-reads."""
    rng = np.random.default_rng(seed)
    t = np.array(_log_spaced_times(1, 8000, 52), dtype=float)
    Lc = 1.2 * t ** n * (1.0 + noise * rng.standard_normal(len(t)))
    Le = 1.0 * t ** (n - 0.02)
    fit = fit_growth_exponent(t, Lc, L_box)
    efit = fit_growth_exponent(t, Le, L_box)
    return {
        "experiment": "M15-glauber-domain-growth",
        "L": L_box, "T": 1.498, "T_ratio": 0.66, "n_seeds": 48, "t_max": 8000,
        "times": t.tolist(), "L_corr": Lc.tolist(), "L_energy": Le.tolist(),
        "energy": [-1.9] * len(t), "excess_energy": [0.1] * len(t), "e_eq": -1.95,
        "G_snapshots": {}, "snapshots": {},
        "exponent": fit.exponent, "exponent_stderr": fit.stderr,
        "systematic_spread": abs(fit.exponent - efit.exponent),
        "late_exponent": fit.exponent, "r2": fit.r2,
        "corr_fit": {"exponent": fit.exponent, "stderr": fit.stderr, "r2": fit.r2,
                     "intercept": fit.intercept, "n_points": fit.n_points,
                     "t_lo": fit.t_lo, "t_hi": fit.t_hi, "L_lo": fit.L_lo, "L_hi": fit.L_hi},
        "energy_fit": {"exponent": efit.exponent, "n_points": efit.n_points},
        "supports_allen_cahn": abs(fit.exponent - ALLEN_CAHN_EXPONENT) <= EXPONENT_TOL,
        "allen_cahn_exponent": ALLEN_CAHN_EXPONENT,
        "t_fit_min": 20, "l_min_fit": 4.0, "sat_frac": 0.20,
        "wall_seconds": 34.0, "config": {"model": "ising-2d-square"},
    }


def test_to_report_shape_is_check_ready():
    rep = to_report(_reconstruct_result(_synthetic_report()))
    assert rep["experiment"] == "M15-glauber-domain-growth"
    assert len(rep["times"]) == len(rep["L_corr"])
    assert rep["allen_cahn_exponent"] == ALLEN_CAHN_EXPONENT
    assert "status" not in rep                              # supports ½ → not a null
    assert "power law" in rep["headline"].lower() or "t^n" in rep["headline"]


def test_check_m15_passes_on_a_clean_half_and_is_a_receipt():
    """The check re-derives the exponent from the arrays: a clean t^0.485 passes, and corrupting
    the STORED exponent to a lie must not flip the grade (the recomputed slope decides)."""
    rep = _synthetic_report(n=0.485)
    ok, detail = check_m15(rep)
    assert ok is True, detail
    rep["exponent"] = 0.999                                 # a lie the check must ignore
    assert check_m15(rep)[0] is True                        # still passes on the real arrays


def test_check_m15_fails_a_diffusive_quarter_exponent():
    # A broken coarsening run growing as t^0.25 (diffusive, not curvature-driven) must fail —
    # far outside the ±0.06 Allen-Cahn band, even though it is a clean power law.
    rep = _synthetic_report(n=0.25)
    ok, detail = check_m15(rep)
    assert ok is False and "0.2" in detail


def test_check_m15_ignores_foreign_reports():
    assert check_m15({"experiment": "M13-triangular-afm"})[0] is None
    assert check_m15({"experiment": "M01-ising-verification", "T": [1], "chi": [1]})[0] is None


def test_to_report_unresolved_is_honest_null():
    rep = to_report(_reconstruct_result(_synthetic_report(n=0.25)))
    assert rep["supports_allen_cahn"] is False
    assert rep["status"] == "null"                          # honest failed-calibration grey leaf
    assert "null" in rep["headline"].lower()


def _reconstruct_result(rep) -> M15Result:
    """Rebuild an ``M15Result`` from a synthetic report dict so ``to_report`` shape/null tests run
    without a Monte-Carlo pass. Mirrors the runner's field wiring."""
    from lab.m15 import FitResult
    cf = rep["corr_fit"]
    corr = FitResult(exponent=cf["exponent"], stderr=cf["stderr"], r2=cf["r2"],
                     intercept=cf["intercept"], n_points=cf["n_points"],
                     t_lo=cf["t_lo"], t_hi=cf["t_hi"], L_lo=cf["L_lo"], L_hi=cf["L_hi"])
    ef = rep["energy_fit"]
    efit = FitResult(exponent=ef["exponent"], stderr=0.0, r2=1.0, intercept=0.0,
                     n_points=ef["n_points"], t_lo=0, t_hi=0, L_lo=0, L_hi=0)
    return M15Result(
        times=rep["times"], L_corr=rep["L_corr"], L_energy=rep["L_energy"],
        energy=rep["energy"], excess_energy=rep["excess_energy"], e_eq=rep["e_eq"],
        G_snapshots={}, snapshots={}, corr_fit=corr, energy_fit=efit,
        late_exponent=rep["late_exponent"], exponent=rep["exponent"],
        exponent_stderr=rep["exponent_stderr"], systematic_spread=rep["systematic_spread"],
        r2=rep["r2"], supports_allen_cahn=rep["supports_allen_cahn"],
        allen_cahn_exponent=ALLEN_CAHN_EXPONENT, L=rep["L"], T=rep["T"], T_ratio=rep["T_ratio"],
        n_seeds=rep["n_seeds"], t_max=rep["t_max"], wall_seconds=rep["wall_seconds"],
        config=rep["config"],
    )
