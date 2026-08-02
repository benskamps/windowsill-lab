"""K01 Kuramoto synchronization — the engine, the estimators, the calibration gate.

Three layers, matching the house style (cf. ``test_m17.py`` / ``test_c01_maturity.py``):

* **The engine** (``kuramoto.py``) is pinned against *hand-computable* cases before it is
  ever pointed at a sweep: the Lorentzian quantile draw must be exactly antisymmetric and
  reproduce its own analytic quartiles, the order parameter must return the known centroid
  of phase sets whose answer is obvious, an uncoupled population must integrate to exactly
  its free-running phases, and a fully locked population must stay locked.
* **The estimators** (``refine_peak`` / ``steepest_slope_crossing`` / ``mean_field_r``)
  recover *known* answers from synthetic curves whose peak and closed form are exact.
* **The runner + report + check** (``k01.py`` / ``checks.check_k01``) are exercised on a
  real (tiny) run, and — the load-bearing one — the check is shown to **re-derive** every
  graded number from the report's raw arrays: corrupting the stored headline must not move
  the grade, while corrupting the underlying curve must.

NumPy is imported through ``importorskip`` so this file degrades to a skip rather than a
collection error in CI's stdlib-only pipeline lane; ``lab.checks`` itself is stdlib and its
K01 gate is exercised on hand-built reports that need no engine at all.
"""
import math

import pytest

np = pytest.importorskip("numpy")

from lab import k01, kuramoto  # noqa: E402  (must follow the importorskip)
from lab.checks import (  # noqa: E402
    KURAMOTO_BRANCH_TOL, KURAMOTO_GAMMA, KURAMOTO_KC, KURAMOTO_KC_TOL,
    KURAMOTO_K_MAX_OVER_GAMMA, KURAMOTO_N, KURAMOTO_POINTS, check_k01,
)


QUICK = dict(n=400, n_points=13, dt=0.02, t_burn=40.0, t_measure=120.0, seed=42)


# ───────────────────── the engine: frequencies that are exactly known ─────────────────────

def test_quantile_frequencies_are_exactly_antisymmetric():
    """The (i+½)/N grid pairs u with 1−u, so Σω = 0 identically — which is why the
    mean phase ψ has no spurious drift for the integrator to accumulate."""
    omega = kuramoto.lorentzian_frequencies(1000, gamma=0.5)
    assert omega.size == 1000
    np.testing.assert_allclose(omega, -omega[::-1], atol=1e-12)
    assert abs(omega.sum()) < 1e-9


def test_quantile_frequencies_reproduce_the_analytic_quartiles():
    """A Lorentzian's quartiles are ±γ exactly (F(±γ) = ½ ± ¼). A draw that got the
    inverse CDF wrong — a factor of 2, a missing π — misses this immediately."""
    omega = kuramoto.lorentzian_frequencies(4000, gamma=0.5)
    lower = float(np.quantile(omega, 0.25))
    upper = float(np.quantile(omega, 0.75))
    assert lower == pytest.approx(-0.5, abs=0.01)
    assert upper == pytest.approx(0.5, abs=0.01)
    assert float(np.median(omega)) == pytest.approx(0.0, abs=1e-9)


def test_tails_are_clipped_without_moving_the_density_at_zero():
    """Clipping bounds |ω|·dt; unlike truncate-and-renormalize it must NOT thin the
    population near ω=0, because g(0) is what fixes the exact K_c = 2γ."""
    gamma, n = 0.5, 20000
    omega = kuramoto.lorentzian_frequencies(n, gamma=gamma)
    assert np.abs(omega).max() == pytest.approx(kuramoto.OMEGA_CLIP_SCALE * gamma)
    # the fraction inside ±γ is the untouched analytic ½ (F(γ)−F(−γ) = ½)
    assert float(np.mean(np.abs(omega) <= gamma)) == pytest.approx(0.5, abs=0.01)


def test_odd_population_is_refused_rather_than_silently_drifting():
    with pytest.raises(ValueError, match="even"):
        kuramoto.lorentzian_frequencies(999)


# ───────────────────── the engine: the order parameter, by hand ─────────────────────

def test_order_parameter_on_phase_sets_whose_answer_is_obvious():
    identical = np.zeros((1, 64))
    r, _ = kuramoto.order_parameter(identical)
    assert float(r[0]) == pytest.approx(1.0)          # perfect lockstep

    antipodal = np.array([[0.0, math.pi] * 32])
    r, _ = kuramoto.order_parameter(antipodal)
    assert float(r[0]) == pytest.approx(0.0, abs=1e-12)   # two opposed clumps cancel

    spread = np.linspace(0.0, 2.0 * math.pi, 256, endpoint=False)[None, :]
    r, _ = kuramoto.order_parameter(spread)
    assert float(r[0]) == pytest.approx(0.0, abs=1e-9)    # a uniform crowd


def test_order_parameter_recovers_a_known_mean_phase():
    theta = np.array([[1.0 - 0.2, 1.0, 1.0 + 0.2]])
    r, psi = kuramoto.order_parameter(theta)
    assert float(psi[0]) == pytest.approx(1.0)
    assert 0.0 < float(r[0]) < 1.0


# ───────────────────── the engine: integration against exact solutions ─────────────────────

def test_uncoupled_oscillators_integrate_to_their_free_phases():
    """At K=0 the equation is dθ/dt = ω, whose solution is exact. RK4 must reproduce
    θ_0 + ω·t to machine precision — this is the integrator's own calibration."""
    omega = kuramoto.lorentzian_frequencies(64, gamma=0.5)
    theta = np.linspace(0.0, 2.0 * math.pi, 64, endpoint=False)[None, :].copy()
    start = theta.copy()
    coupling = np.zeros((1, 1))
    steps, dt = 200, 0.01
    for _ in range(steps):
        theta = kuramoto.rk4_step(theta, omega, coupling, dt)
    np.testing.assert_allclose(theta, start + omega * (steps * dt), atol=1e-10)


def test_identical_oscillators_stay_locked_under_coupling():
    """A perfectly locked population is a fixed point: sin(ψ−θ_i) = 0 for every i, so
    coupling can neither help nor disturb it. A sign error in the mean-field term
    would break this immediately."""
    omega = np.zeros(32)
    theta = np.full((1, 32), 0.7)
    coupling = np.array([[3.0]])
    for _ in range(100):
        theta = kuramoto.rk4_step(theta, omega, coupling, 0.02)
    r, _ = kuramoto.order_parameter(theta)
    assert float(r[0]) == pytest.approx(1.0, abs=1e-12)


def test_coupling_pulls_two_detuned_oscillators_together_and_zero_coupling_does_not():
    """The sign of the interaction, read off the simplest system that has one: two
    oscillators with opposite frequencies. Strong coupling must SHRINK their phase
    gap; the same run at K=0 must leave it growing."""
    omega = np.array([-0.2, 0.2])
    theta = np.array([[0.0, 1.0], [0.0, 1.0]])
    coupling = np.array([[4.0], [0.0]])
    for _ in range(400):
        theta = kuramoto.rk4_step(theta, omega, coupling, 0.02)
    coupled_gap = abs(theta[0, 1] - theta[0, 0])
    free_gap = abs(theta[1, 1] - theta[1, 0])
    assert coupled_gap < 1.0 < free_gap


# ───────────────────── the estimators, on curves whose answer is exact ─────────────────────

def test_refine_peak_recovers_a_known_sub_grid_vertex():
    """A parabola's vertex is exact under 3-point refinement, and the whole point is
    that it beats the discrete argmax — which here can only ever say 1.0."""
    x = np.linspace(0.0, 2.0, 25)
    y = -((x - 1.04) ** 2)
    assert kuramoto.refine_peak(x, y) == pytest.approx(1.04, abs=1e-9)
    assert x[int(np.argmax(y))] == pytest.approx(1.0)


def test_refine_peak_falls_back_to_the_argmax_on_an_endpoint():
    x = np.linspace(0.0, 2.0, 25)
    assert kuramoto.refine_peak(x, -x) == pytest.approx(0.0)
    assert kuramoto.refine_peak(x, x) == pytest.approx(2.0)


def test_mean_field_branch_is_the_closed_form_and_is_zero_below_kc():
    k = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    r = kuramoto.mean_field_r(k, gamma=0.5)
    np.testing.assert_allclose(r[:3], 0.0)
    assert r[3] == pytest.approx(math.sqrt(1.0 - 1.0 / 1.5))
    assert r[4] == pytest.approx(math.sqrt(0.5))


def test_steepest_slope_crossing_finds_a_known_inflection():
    x = np.linspace(0.0, 2.0, 201)
    y = 1.0 / (1.0 + np.exp(-(x - 1.3) / 0.05))   # logistic: steepest at x=1.3
    assert kuramoto.steepest_slope_crossing(x, y) == pytest.approx(1.3, abs=0.02)


# ───────────────────── the runner: a real (tiny) sweep ─────────────────────

@pytest.fixture(scope="module")
def quick_run():
    return k01.run_k01(gamma=KURAMOTO_GAMMA, **QUICK)


def test_quick_run_finds_the_transition_and_the_incoherent_floor(quick_run):
    """Even a 400-oscillator pass must land the transition near 2γ and must show no
    order at all without coupling."""
    assert quick_run.kc_chi_peak == pytest.approx(KURAMOTO_KC, abs=0.15)
    assert quick_run.r_incoherent < 3.0 / math.sqrt(quick_run.n)
    assert quick_run.r_mean[-1] > 0.5           # strongly coupled end is ordered
    assert quick_run.branch_max_dev < 0.05


def test_chi_is_exactly_n_times_the_variance(quick_run):
    """The graded fluctuation is a *derived* quantity, not an independently stored
    one; the check re-derives it and refuses a receipt where the two disagree."""
    for chi, var in zip(quick_run.chi, quick_run.r_var):
        assert chi == pytest.approx(quick_run.n * var)


def test_a_downsized_run_is_a_diagnostic_not_the_calibration(quick_run):
    """The same rule ``lab c01 --terms 12`` obeys: a cheaper run is useful and is not
    allowed to call itself the calibration."""
    assert quick_run.is_calibration is False
    ok, detail = check_k01(k01.to_report(quick_run))
    assert ok is False
    assert "identity changed" in detail


def test_report_status_is_the_checks_verdict_not_the_runners(quick_run):
    report = k01.to_report(quick_run)
    ok, _ = check_k01(report)
    assert report["status"] == ("pass" if ok else "null")


# ───────────────────── the check: a receipt, not an echo ─────────────────────

def _calibration_report(
    kc: float = KURAMOTO_KC, branch_bias: float = 0.0, r0: float = 0.02,
) -> dict:
    """A synthetic but structurally honest K01 report at the fixed identity.

    ⟨r⟩ follows the exact ordered branch (optionally biased), and χ is a triangular
    bump centred on ``kc`` — enough for the checker to re-derive a peak, a branch
    deviation, and an incoherent floor without running the engine.
    """
    step = (KURAMOTO_K_MAX_OVER_GAMMA * KURAMOTO_GAMMA) / (KURAMOTO_POINTS - 1)
    K = [i * step for i in range(KURAMOTO_POINTS)]
    r_mean, r_var = [], []
    for k in K:
        r = math.sqrt(1.0 - KURAMOTO_KC / k) + branch_bias if k > KURAMOTO_KC else 0.0
        r_mean.append(r0 if k == 0.0 else max(0.0, min(1.0, r)))
        r_var.append(max(1e-6, (0.4 - abs(k - kc)) / KURAMOTO_N))
    chi = [KURAMOTO_N * v for v in r_var]
    return {
        "experiment": "K01-kuramoto-synchronization",
        "K": K, "r_mean": r_mean, "r_var": r_var, "chi": chi,
        "n": KURAMOTO_N, "gamma": KURAMOTO_GAMMA,
        "kc_exact": KURAMOTO_KC, "kc_chi_peak": kc, "status": "pass",
    }


def test_check_ignores_reports_it_cannot_read():
    assert check_k01({"experiment": "M04-specific-heat"})[0] is None
    assert check_k01({"experiment": "K01-kuramoto-synchronization"})[0] is None


def test_check_passes_a_well_formed_calibration_receipt():
    ok, detail = check_k01(_calibration_report())
    assert ok, detail
    assert "synchronization transition reproduced" in detail


def test_check_regrades_from_the_arrays_and_ignores_the_stored_headline():
    """The load-bearing property: forging the headline number must not move the
    grade in EITHER direction — a lie cannot rescue a bad curve, and it cannot
    sink a good one."""
    good = _calibration_report()
    good["kc_chi_peak"] = 99.0
    good["status"] = "null"
    assert check_k01(good)[0] is True

    bad = _calibration_report(kc=1.9)
    bad["kc_chi_peak"] = KURAMOTO_KC          # claims the right answer
    ok, detail = check_k01(bad)
    assert ok is False
    assert "synchronization calibration failed" in detail


def test_check_rejects_a_chi_curve_that_disagrees_with_its_own_variances():
    report = _calibration_report()
    report["chi"] = [c * 3.0 for c in report["chi"]]
    ok, detail = check_k01(report)
    assert ok is False
    assert "not self-consistent" in detail


def test_check_rejects_a_fabricated_ordered_branch():
    """The hard half of the gate: the closed form is re-derived here, so an ⟨r⟩ curve
    that misses √(1−K_c/K) fails even with a perfect peak."""
    report = _calibration_report(branch_bias=0.08)
    ok, detail = check_k01(report)
    assert ok is False
    assert "ordered branch not reproduced" in detail


def test_check_rejects_order_that_appears_without_any_coupling():
    """The negative control. A collapsed frequency draw orders at K=0 and would sail
    through a peak-only gate."""
    report = _calibration_report(r0=0.9)
    ok, detail = check_k01(report)
    assert ok is False
    assert "uncoupled control failed" in detail


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"n": 500}, "identity changed"),
        ({"gamma": 0.25}, "identity changed"),
        ({"K": [0.0, 1.0, 2.0]}, "identity changed"),
        # A flat ordered branch, with the K=0 point left honest so this case
        # isolates the branch gate instead of tripping the uncoupled control first.
        ({"r_mean": [0.02] + [0.5] * (KURAMOTO_POINTS - 1)},
         "ordered branch not reproduced"),
        ({"r_var": [-1.0] * KURAMOTO_POINTS}, "negative"),
    ],
)
def test_check_rejects_tampered_identity_and_evidence(changes, reason):
    report = _calibration_report()
    report.update(changes)
    # Forged honor-system claims must not rescue bad evidence.
    report["status"] = "pass"
    report["kc_chi_peak"] = KURAMOTO_KC
    ok, detail = check_k01(report)
    assert ok is False
    assert reason in detail


def test_check_reports_unreadable_arrays_as_unreadable_not_as_a_default():
    report = _calibration_report()
    report["r_mean"] = [None] * KURAMOTO_POINTS
    ok, detail = check_k01(report)
    assert ok is None
    assert "readable" in detail


# ───────────────────── the identity, mirrored on both sides ─────────────────────

def test_k01_identity_mirrors_the_runner():
    """``checks`` owns the tolerance and the benchmark, but its identity constants
    must be the SAME calibration the runner ships — the pair is pinned here so a
    change to one that isn't made to the other reds instead of silently
    un-gating the milestone."""
    assert KURAMOTO_N == k01.CALIBRATION_N
    assert KURAMOTO_GAMMA == k01.CALIBRATION_GAMMA
    assert KURAMOTO_POINTS == k01.CALIBRATION_POINTS
    assert KURAMOTO_K_MAX_OVER_GAMMA == k01.CALIBRATION_K_MAX_OVER_GAMMA
    assert KURAMOTO_KC == kuramoto.critical_coupling(KURAMOTO_GAMMA)


def test_declared_tolerance_is_looser_than_the_sweep_resolution():
    """The tolerance's stated justification is that it is set by the grid. Assert
    that arithmetic rather than trusting the comment: ΔK = γ/6 = 0.0833, and the
    band must admit at least one grid step of peak-location error while staying far
    inside the distance to a broken run (the sweep endpoints, 1.0 away)."""
    delta_k = (KURAMOTO_K_MAX_OVER_GAMMA * KURAMOTO_GAMMA) / (KURAMOTO_POINTS - 1)
    assert KURAMOTO_KC_TOL >= delta_k
    assert KURAMOTO_KC_TOL < 0.25 * KURAMOTO_KC
    assert KURAMOTO_BRANCH_TOL < 0.05
