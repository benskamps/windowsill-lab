"""M17 KPZ growth on a ring — the engine, the exponent fits, the controls, the check.

Three layers, matching the house style (cf. ``test_m15.py`` / ``test_m13.py``):

* **The engine** (``kpz.py``) is pinned against *hand-computable* cases before it is ever
  pointed at a growth run: the single-step constraint is an invariant that must survive
  arbitrary evolution, random deposition must reproduce its exact ``w²=p(1−p)t`` closed form,
  the local-minimum density (which fixes the SIGN of the KPZ nonlinearity, and therefore the
  sign of the predicted skewness) is brute-forced against ``q(1−q)``, and the width and shape
  statistics are checked on distributions whose moments are known exactly.
* **The fits** (``m17.fit_exponent`` / ``fit_alpha`` / ``rd_exact_deviation``) recover *known*
  slopes from synthetic perfect power laws and honour the scaling window.
* **The runner + report + check** (``m17.py`` / ``checks.check_m17``) are exercised on a real
  (tiny) run, and — the load-bearing one — the check is shown to **re-derive** every graded
  exponent from the report's raw arrays: corrupting the stored ``beta`` must not move the
  grade, while corrupting the underlying curve must.
"""
import math

import numpy as np
import pytest

from lab import kpz
from lab.kpz import (
    KPZ_BETA, KPZ_ALPHA, KPZ_Z, EW_BETA, RD_BETA, P_FLIP,
    TW_GUE_SKEW, TW_GOE_SKEW, PREDICTED_SKEW,
    flat_heights, droplet_heights, droplet_time_budget, is_single_step,
    single_step_sweep, random_deposition_sweep, edwards_wilkinson_step,
    interface_width, width_squared, skewness, excess_kurtosis,
    local_minimum_density, slope_velocity, log_spaced_times,
    run_growth, run_saturation, run_height_distribution,
)
from lab.m17 import (
    run_m17, to_report, fit_exponent, fit_alpha, rd_exact_deviation, assign_tw_class,
    T_FIT_MIN, W_FIT_MIN,
)
from lab.checks import check_m17


# ───────────────── the engine: the single-step constraint is an invariant ─────────────────
def test_flat_and_droplet_initial_conditions_are_single_step():
    """Both initial conditions must be legal zig-zag paths — every bond a ±1 step. A wedge or
    a zig-zag built wrong would silently break the model's only structural invariant."""
    assert is_single_step(flat_heights(4, 32))
    assert is_single_step(droplet_heights(4, 32))


def test_odd_ring_is_refused():
    """A ±1 step path can only close on an even ring: an odd L cannot be zig-zagged at all."""
    with pytest.raises(ValueError):
        flat_heights(2, 31)
    with pytest.raises(ValueError):
        droplet_heights(2, 31)


def test_single_step_constraint_survives_arbitrary_evolution():
    """THE invariant. A corner flip turns a local minimum into a local maximum, so both of its
    bonds stay ±1; and same-parity sites are never adjacent, so the sublattice-parallel update
    can never have two flips interfere. If either were false the surface would tear — this
    test is what licenses the parallel update as exact rather than approximate."""
    rng = np.random.default_rng(0)
    for p in (0.2, 0.5, 0.9):
        h = flat_heights(6, 64)
        for _ in range(120):
            single_step_sweep(h, p, rng)
            assert is_single_step(h), f"single-step constraint broken at p={p}"


def test_droplet_stays_a_wedge_inside_its_time_budget():
    """A droplet is only a droplet while its growing region has not wrapped the ring. Inside
    the budget the far side of the wedge must be untouched — otherwise the geometry has
    silently changed and the GUE expectation no longer applies to it."""
    L, batch = 256, 4
    t = droplet_time_budget(L)
    h = droplet_heights(batch, L)
    rng = np.random.default_rng(3)
    for _ in range(t):
        single_step_sweep(h, 0.5, rng)
    untouched = droplet_heights(batch, L)[:, 0]
    assert np.array_equal(h[:, 0], untouched), "the wedge wrapped inside its own budget"


def test_droplet_run_refuses_to_outgrow_its_ring():
    with pytest.raises(ValueError, match="outgrows"):
        run_height_distribution("droplet", L=64, t=droplet_time_budget(64) + 1, batch=2)


def test_droplet_refuses_multi_site_sampling():
    """Only the wedge apex is the GUE point on a droplet; other sites are not statistically
    equivalent, so sampling them would mix distributions."""
    with pytest.raises(ValueError, match="n_sites"):
        run_height_distribution("droplet", L=256, t=8, batch=4, n_sites=4)


# ───────────── the engine: random deposition against its EXACT closed form ─────────────
def test_random_deposition_matches_its_exact_closed_form():
    """Independent Bernoulli(p) columns are independent binomial walks, so ``w²(t) = p(1−p)t``
    EXACTLY at every t — no fitting, no asymptotics. This is M17's strongest anchor and the
    first thing that would break if the width estimator or the time axis were wrong."""
    for p in (0.3, 0.5):
        r = run_growth("rd", L=4096, batch=32, t_max=200, n_times=10, seed=5, p=p)
        for t, w2 in zip(r.times, r.width_sq):
            assert w2 == pytest.approx(p * (1.0 - p) * t, rel=0.06), (p, t, w2)


def test_rd_exact_deviation_flags_a_wrong_curve():
    """The exact-curve grader must actually reject: a w² curve off by 40% cannot pass."""
    times = [1, 2, 4, 8, 16]
    good = [0.25 * t for t in times]
    bad = [0.35 * t for t in times]
    assert rd_exact_deviation(times, good, 0.5)["max_rel_dev"] < 1e-9
    assert rd_exact_deviation(times, bad, 0.5)["max_rel_dev"] == pytest.approx(0.4, rel=1e-6)


# ───────────── the engine: the SIGN of the nonlinearity, derived not asserted ─────────────
@pytest.mark.parametrize("q", [0.2, 0.35, 0.5, 0.65, 0.8])
def test_local_minimum_density_matches_q_times_one_minus_q(q):
    """Site i is a local minimum iff the bond into it steps DOWN and the bond out of it steps
    UP, so under a product measure of ±1 steps with up-fraction ``q`` the density is exactly
    ``q(1−q)``. Brute-forced here against random step sequences.

    This is the load-bearing fact behind M17's distribution claim: the growth velocity is
    ``2p·ρ_min``, hence ``v(u) = (p/2)(1−u²)`` at mean slope ``u = 2q−1``, hence the KPZ
    nonlinearity ``λ = ∂²v/∂u² = −p < 0`` — which is why the predicted skewness is the
    MIRRORED (negative) Tracy–Widom value. A measured negative skewness is the prediction, not
    a sign bug."""
    rng = np.random.default_rng(int(q * 1000))
    L = 200_000
    steps = np.where(rng.random(L) < q, 1, -1)
    h = np.concatenate([[0], np.cumsum(steps)])[:L][None, :]
    assert local_minimum_density(h) == pytest.approx(q * (1.0 - q), abs=0.005)


def test_slope_velocity_is_a_downward_parabola_so_lambda_is_negative():
    """``v(u) = (p/2)(1−u²)`` peaks at zero slope and curves DOWN, so λ < 0. A second
    difference of the closed form recovers ``−p``."""
    p, du = 0.5, 1e-3
    second = (slope_velocity(du, p) - 2 * slope_velocity(0.0, p) + slope_velocity(-du, p)) / du ** 2
    assert second == pytest.approx(-p, rel=1e-6)
    assert second < 0
    assert PREDICTED_SKEW["droplet"] == pytest.approx(-TW_GUE_SKEW)
    assert PREDICTED_SKEW["flat"] == pytest.approx(-TW_GOE_SKEW)


# ───────────────────────── the engine: the width + shape statistics ─────────────────────────
def test_width_of_a_flat_surface_is_zero():
    assert interface_width(np.zeros((3, 16))) == pytest.approx(0.0)
    assert width_squared(np.zeros((3, 16))) == pytest.approx(0.0)


def test_width_of_a_known_sawtooth_is_exact():
    """A ±1 alternating surface has mean 0 and ⟨(h−h̄)²⟩ = 1, so w = 1 exactly — and the mean
    must be subtracted PER RING, which a constant offset added to one ring proves."""
    h = np.tile(np.array([1, -1] * 8, dtype=np.int64), (2, 1))
    assert interface_width(h) == pytest.approx(1.0)
    h2 = h.copy()
    h2[1] += 1000            # a rigid vertical shift is not roughness
    assert interface_width(h2) == pytest.approx(1.0)


def test_shape_statistics_recover_known_moments():
    """Skewness/excess kurtosis must be right on distributions whose moments are known: a
    Gaussian scores (0, 0) and an exponential scores (2, 6)."""
    rng = np.random.default_rng(1)
    g = rng.standard_normal(400_000)
    assert skewness(g) == pytest.approx(0.0, abs=0.02)
    assert excess_kurtosis(g) == pytest.approx(0.0, abs=0.05)
    e = rng.exponential(size=400_000)
    assert skewness(e) == pytest.approx(2.0, abs=0.06)
    assert excess_kurtosis(e) == pytest.approx(6.0, abs=0.5)


def test_shape_statistics_are_invariant_under_affine_rescaling():
    """The whole reason M17 grades on skewness/kurtosis: they are unchanged by ``x→(x−a)/b``,
    so the Tracy–Widom SHAPE can be tested without fitting the model constants v_∞ and Γ."""
    rng = np.random.default_rng(2)
    x = rng.gumbel(size=200_000)
    assert skewness((x - 17.3) / 4.2) == pytest.approx(skewness(x), rel=1e-9)
    assert excess_kurtosis((x - 17.3) / 4.2) == pytest.approx(excess_kurtosis(x), rel=1e-9)


def test_edwards_wilkinson_step_is_the_linear_equation():
    """With the noise switched off, one EW step must be exactly ``h += ν dt ∇²h`` — the
    discrete Laplacian and nothing else. (The MISSING (∇h)² term is what makes EW the control:
    that single absence moves β from 1/3 to 1/4.)"""
    class _NoNoise:
        def standard_normal(self, shape):
            return np.zeros(shape)
    h = np.array([[0.0, 1.0, 0.0, 3.0]])
    before = h.copy()
    edwards_wilkinson_step(h, nu=1.0, D=0.0, dt=0.1, rng=_NoNoise())
    lap = np.roll(before, 1, axis=1) + np.roll(before, -1, axis=1) - 2 * before
    assert np.allclose(h, before + 0.1 * lap)


def test_log_spaced_times_are_ascending_unique_and_in_range():
    ts = log_spaced_times(1000, 20)
    assert ts == sorted(set(ts))
    assert ts[0] >= 1 and ts[-1] <= 1000


# ──────────────────────────────── the fits ────────────────────────────────
def test_fit_exponent_recovers_a_known_power_law():
    """A synthetic w = 3·t^0.37 must be recovered to the digit, with R² = 1."""
    t = np.geomspace(1, 10_000, 60)
    w = 3.0 * t ** 0.37
    fit = fit_exponent(t, w)
    assert fit.exponent == pytest.approx(0.37, abs=1e-6)
    assert fit.r2 == pytest.approx(1.0, abs=1e-9)


def test_fit_exponent_honours_the_scaling_window():
    """Points below ``T_FIT_MIN`` in t or ``W_FIT_MIN`` in w must be excluded — the window is
    what keeps the O(1) sawtooth floor and the microscopic transient out of the slope."""
    t = np.geomspace(1, 10_000, 60)
    w = 3.0 * t ** 0.37
    fit = fit_exponent(t, w)
    assert fit.t_lo >= T_FIT_MIN
    assert fit.w_lo >= W_FIT_MIN


def test_fit_exponent_returns_none_without_a_window():
    assert fit_exponent([1, 2, 3], [0.1, 0.2, 0.3]) is None


def test_fit_alpha_recovers_a_known_roughness_exponent():
    sat = [{"L": L, "w_sat": 0.7 * L ** 0.5} for L in (16, 32, 64, 128, 256)]
    assert fit_alpha(sat).exponent == pytest.approx(0.5, abs=1e-6)


def test_assign_tw_class_picks_the_nearer_law_and_flags_a_wrong_one():
    """The graded distributional statement is ASSIGNMENT, so the assigner must be able to say
    'wrong class' — a droplet whose skewness sits on the GOE value must not pass."""
    right = assign_tw_class({"skewness": PREDICTED_SKEW["droplet"], "tw_law": "GUE"})
    assert right["correct"] and right["nearer"] == "GUE"
    wrong = assign_tw_class({"skewness": PREDICTED_SKEW["flat"], "tw_law": "GUE"})
    assert not wrong["correct"] and wrong["nearer"] == "GOE"
    gaussian = assign_tw_class({"skewness": 0.0, "tw_law": "GUE"})
    assert gaussian["decisiveness"] < 2.0, "a Gaussian must not look decisively like GUE"


# ─────────────── the engine really is in the right class (small but real) ───────────────
def test_the_three_models_give_three_different_exponents():
    """The negative control, in miniature. One pipeline, three growth rules, three exact
    answers — 1/3, 1/4, 1/2. The point is the SEPARATION: a pipeline that manufactured a KPZ
    exponent out of any curve would report the same slope three times."""
    k = fit_exponent(*_curve(run_growth("kpz", L=2048, batch=16, t_max=1200, n_times=24, seed=9)))
    e = fit_exponent(*_curve(run_growth("ew", L=1024, batch=16, t_max=600, n_times=24, seed=9)))
    r = fit_exponent(*_curve(run_growth("rd", L=1024, batch=16, t_max=600, n_times=24, seed=9)))
    assert r.exponent == pytest.approx(RD_BETA, abs=0.02)
    assert e.exponent == pytest.approx(EW_BETA, abs=0.03)
    # KPZ sits a few percent below the asymptotic 1/3 at this scale (the documented
    # preasymptotic approach from below) — but nowhere near either control.
    assert k.exponent == pytest.approx(KPZ_BETA, abs=0.05)
    assert abs(k.exponent - e.exponent) > 0.04
    assert abs(k.exponent - r.exponent) > 0.10


def _curve(run):
    return run.times, run.width


def test_saturation_gives_a_roughness_exponent_near_one_half():
    sat = run_saturation([16, 32, 64], batch=32, sweeps_per_Lz=10.0, seed=7)
    assert [s["L"] for s in sat] == [16, 32, 64]
    assert all(s["w_sat"] > 0 for s in sat)
    assert fit_alpha(sat).exponent == pytest.approx(KPZ_ALPHA, abs=0.08)


def test_unknown_model_is_refused():
    with pytest.raises(ValueError, match="unknown growth model"):
        run_growth("eden", L=64, batch=2, t_max=2, n_times=2)


# ─────────────────────── the runner, the report, and the check ───────────────────────
@pytest.fixture(scope="module")
def tiny_run():
    """One small end-to-end run reused by the report/check tests (it is the slow fixture)."""
    return run_m17(L=1024, batch=12, t_max=500, n_times=22,
                   ew_L=512, ew_t_max=300, rd_L=512, rd_t_max=300,
                   sat_L=(8, 16, 32), sat_batch=12,
                   dist_t=40, droplet_batch=250, flat_L=512, flat_batch=200, flat_sites=4,
                   seed=42)


def test_runner_produces_every_stage(tiny_run):
    assert set(tiny_run.growth) == {"kpz", "ew", "rd"}
    assert len(tiny_run.saturation) == 3
    assert set(tiny_run.distributions) == {"droplet", "flat"}
    assert set(tiny_run.assignments) == {"droplet", "flat"}
    assert math.isfinite(tiny_run.beta)
    assert tiny_run.alpha is not None and tiny_run.z is not None
    assert tiny_run.inv_z == pytest.approx(tiny_run.beta / tiny_run.alpha)


def test_report_shape_and_boundary(tiny_run):
    rep = to_report(tiny_run)
    assert rep["experiment"] == "M17-kpz-growth"
    assert rep["status"] in {"pass", "null"}
    assert rep["beta_exact"] == pytest.approx(1 / 3)
    assert rep["alpha_exact"] == 0.5
    assert rep["z_exact"] == 1.5
    for key in ("growth", "saturation", "distributions", "assignments",
                "rd_exact_curve", "t_fit_min", "w_fit_min", "claim_boundary"):
        assert key in rep, key
    # The boundary must name what is NOT claimed — the kurtosis and the TW constants.
    assert "kurtosis" in rep["claim_boundary"].lower()
    for name in ("kpz", "ew", "rd"):
        assert len(rep["growth"][name]["times"]) == len(rep["growth"][name]["width"])


def test_moment_resolution_reports_gaps_in_sampling_sigmas():
    """Gaps must be expressed in sampling sigmas (``sqrt(6/n)`` and ``sqrt(24/n)``) so 'did it
    resolve' is a derived number rather than an opinion — and a multi-site flat sample must be
    flagged as non-independent so its sigma is read as a floor."""
    sample = {"tw_law": "GUE", "n_samples": 6000, "skewness": PREDICTED_SKEW["droplet"],
              "excess_kurtosis": 0.0935, "n_sites": 1, "site_spacing_over_xi": None}
    from lab.m17 import moment_resolution
    r = moment_resolution(sample)
    assert r["skew_gap"] == pytest.approx(0.0, abs=1e-9)
    assert r["skew_sampling_sigma"] == pytest.approx(math.sqrt(6 / 6000))
    assert r["kurt_sampling_sigma"] == pytest.approx(math.sqrt(24 / 6000))
    assert r["independent_samples"] is True
    multi = moment_resolution({**sample, "n_sites": 8, "site_spacing_over_xi": 4.7})
    assert multi["independent_samples"] is False


def test_claim_boundary_is_derived_from_this_run_not_hand_written(tiny_run):
    """The honesty text must be built FROM the measurement. If it were prose, it would go stale
    the first time the run changed — the exact failure mode that makes two surfaces disagree.
    So: the boundary must quote this run's own beta and its own moment gaps, and must change
    when the underlying numbers change."""
    rep = to_report(tiny_run)
    boundary = rep["claim_boundary"]
    assert f"{tiny_run.beta:.4f}" in boundary, "boundary does not quote this run's beta"
    for ic in ("droplet", "flat"):
        gap = tiny_run.resolution[ic]["skew_gap"]
        assert f"{gap:.4f}" in boundary, f"boundary does not quote the {ic} skewness gap"
    assert "NOT graded" in boundary

    # Move the measurement; the sentence must move with it.
    import dataclasses
    from lab.m17 import moment_resolution
    worse = dataclasses.replace(
        tiny_run,
        distributions={ic: {**d, "skewness": 0.0}
                       for ic, d in tiny_run.distributions.items()})
    worse.resolution = {ic: moment_resolution(d) for ic, d in worse.distributions.items()}
    assert to_report(worse)["claim_boundary"] != boundary


def test_check_rejects_a_foreign_report():
    ok, _ = check_m17({"experiment": "M15-glauber-domain-growth"})
    assert ok is None


def test_check_re_derives_the_exponent_rather_than_reading_it(tiny_run):
    """THE receipt test. The check must arrive at β from the raw ``(times, width)`` arrays, so
    corrupting the *reported* exponent cannot change the grade — while corrupting the actual
    curve must. A check that echoed the report would pass both and prove nothing."""
    rep = to_report(tiny_run)
    _, detail_true = check_m17(rep)

    lying = {**rep, "beta": 0.99, "kpz_fit": {**(rep["kpz_fit"] or {}), "exponent": 0.99},
             "supports_kpz": True, "status": "pass"}
    ok_lie, detail_lie = check_m17(lying)
    assert detail_lie == detail_true, "the check echoed the reported exponent instead of re-fitting"

    # Corrupting the underlying curve to a flat line must be caught.
    broken = {**rep, "growth": {**rep["growth"],
                                "kpz": {**rep["growth"]["kpz"],
                                        "width": [5.0] * len(rep["growth"]["kpz"]["width"])}}}
    ok_broken, _ = check_m17(broken)
    assert ok_broken is False


def test_check_fails_when_a_control_collapses_onto_kpz(tiny_run):
    """The negative control has to be able to FAIL. If random deposition's curve is replaced by
    a KPZ-like one — i.e. the pipeline reporting 1/3 for everything — the check must refuse,
    because that is precisely the failure mode the controls exist to catch."""
    rep = to_report(tiny_run)
    kpz_curve = rep["growth"]["kpz"]
    faked = {**rep, "growth": {**rep["growth"],
                               "rd": {**rep["growth"]["rd"],
                                      "times": list(kpz_curve["times"]),
                                      "width": list(kpz_curve["width"]),
                                      "width_sq": [w * w for w in kpz_curve["width"]]}}}
    ok, detail = check_m17(faked)
    assert ok is False
    assert "CONTROL" in detail


def test_check_fails_on_a_wrong_tracy_widom_class(tiny_run):
    """Swapping the two geometries' skewnesses must be caught: the graded claim is class
    ASSIGNMENT, so a droplet that looks like GOE is a failure, not a curiosity."""
    rep = to_report(tiny_run)
    dro = dict(rep["distributions"]["droplet"])
    fla = dict(rep["distributions"]["flat"])
    swapped = {**rep, "distributions": {
        "droplet": {**dro, "skewness": TW_GOE_SKEW},
        "flat": {**fla, "skewness": TW_GUE_SKEW}}}
    ok, detail = check_m17(swapped)
    assert ok is False


def test_check_fails_on_a_positive_skewness(tiny_run):
    """λ < 0 predicts a NEGATIVE skewness. A positive one means the growth direction or the
    height map was inverted somewhere, and must not be graded as a Tracy–Widom success."""
    rep = to_report(tiny_run)
    flipped = {**rep, "distributions": {
        ic: {**d, "skewness": -float(d["skewness"])}
        for ic, d in rep["distributions"].items()}}
    ok, _ = check_m17(flipped)
    assert ok is False
