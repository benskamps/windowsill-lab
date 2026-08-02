"""K02 χ(r) shape — the estimators, the fits, and the resolution gate.

Three layers, matching ``test_k01_maturity.py``:

* **The estimators** (``parabola_vertex`` / ``locate_r_peak`` / the two shape fits) are
  pinned against cases whose answers are *known by construction* — a parabola whose
  vertex is chosen in advance and then sampled at deliberately unequal spacings, and
  exact ``a·r^p(1−r)^q`` data whose exponents the fitter has to recover.
* **The runner + report** are exercised on a real (tiny) ladder.
* **The check** is shown to **re-derive** its verdict from each rung's raw arrays: a
  forged headline must not move the grade in either direction, while corrupting the
  underlying curve must.

The load-bearing K02-specific property is the one in the middle of the estimator
layer: K02's r-axis is *non-uniform*, so the uniform-grid refinement K01 uses is
wrong here, and a test pins the difference rather than leaving it to a comment.

NumPy is imported through ``importorskip`` so this file degrades to a skip rather than
a collection error in CI's stdlib-only lane; ``lab.checks`` is stdlib and its K02 gate
is exercised on hand-built reports that need no engine at all.
"""
import math

import pytest

np = pytest.importorskip("numpy")

from lab import k02  # noqa: E402  (must follow the importorskip)
from lab.checks import (  # noqa: E402
    K02_CRITICAL_EXPONENT, K02_CRITICAL_EXPONENT_ERR, K02_CRITICAL_TOL,
    K02_EQUILIBRATION_MAX_DRIFT, K02_EQUILIBRATION_MAX_DRIFT_SIGMA,
    K02_INTERIOR_PEAK_RATIO, K02_KC_TOL,
    K02_K_PEAK_STEPS, K02_LADDER, K02_RUN01_R_STAR, K02_R_STAR_EXCLUSION_SIGMA,
    K02_CLIP_CONTROL_MAX_SIGMA, K02_R_STAR_SCATTER, K02_SEEDS, KURAMOTO_GAMMA,
    check_k02,
)


QUICK = dict(
    ladder=(250, 500), seeds=(42,), t_burn=20.0, t_measure=60.0,
    # The calibration pass defaults to windows long enough for N=4000 at criticality
    # (t = 2000 + 2000); left at those, this fixture would spend minutes proving
    # plumbing. Shrunk deliberately — which is also what makes the run a diagnostic
    # rather than the measurement, asserted below.
    critical_seeds=2, critical_t_burn=10.0, critical_t_measure=20.0,
    clip_control_n=100, clip_control_seeds=2, clip_control_t_burn=10.0,
    clip_control_t_measure=20.0,
)


# ───────────────── the estimators: answers known by construction ─────────────────

def test_parabola_vertex_recovers_a_known_vertex_from_unequal_spacing():
    """Three samples of y = −3(x − 0.37)² + 5, taken at deliberately lopsided
    abscissae — exactly the situation K02's r-axis creates around the peak."""
    def y(x):
        return -3.0 * (x - 0.37) ** 2 + 5.0

    xs = (0.30, 0.35, 0.62)          # 0.05 on the left, 0.27 on the right
    got = k02.parabola_vertex(xs[0], y(xs[0]), xs[1], y(xs[1]), xs[2], y(xs[2]))
    assert got == pytest.approx(0.37, abs=1e-9)


def test_uniform_refinement_would_be_wrong_on_this_axis():
    """The reason K02 does not reuse ``kuramoto.refine_peak``.

    The uniform-grid formula assumes equal spacing on both sides; fed the same
    lopsided samples it misses the true vertex badly. Pinning the *difference* keeps
    a future 'simplification' back to the shared helper from silently biasing r*.
    """
    from lab.kuramoto import refine_peak

    def y(x):
        return -3.0 * (x - 0.37) ** 2 + 5.0

    xs = [0.30, 0.35, 0.62]
    ys = [y(x) for x in xs]
    assert k02.parabola_vertex(xs[0], ys[0], xs[1], ys[1], xs[2], ys[2]) == pytest.approx(0.37)
    assert abs(refine_peak(xs, ys) - 0.37) > 0.02


def test_parabola_vertex_falls_back_on_three_collinear_points():
    assert k02.parabola_vertex(0.0, 1.0, 1.0, 2.0, 2.0, 3.0) == 1.0


def test_locate_r_peak_returns_the_measured_argmax_and_the_grid_floor():
    """r* is the *measured* coherence at the argmax — never the refined number and
    never an assumed value — and the resolution floor is half the span its two
    neighbours cover."""
    r = np.array([0.02, 0.05, 0.09, 0.30, 0.55])
    chi = np.array([0.2, 0.5, 1.0, 0.6, 0.3])
    i, r_star, refined, resolution = k02.locate_r_peak(r, chi)
    assert i == 2
    assert r_star == pytest.approx(0.09)
    assert resolution == pytest.approx(0.5 * (0.30 - 0.05))
    assert 0.05 < refined < 0.30


def test_locate_r_peak_reports_an_endpoint_peak_as_unresolved():
    """A monotone curve has no interior maximum; the floor must come back NaN rather
    than a number the check could grade as if the peak had been resolved."""
    r = np.array([0.02, 0.05, 0.09, 0.30, 0.55])
    chi = np.array([1.0, 0.8, 0.6, 0.4, 0.2])
    i, r_star, _, resolution = k02.locate_r_peak(r, chi)
    assert i == 0
    assert r_star == pytest.approx(0.02)
    assert math.isnan(resolution)


@pytest.mark.parametrize(("p", "q"), [(2.0, 3.0), (1.5, 6.0), (4.0, 4.0)])
def test_free_fit_recovers_exponents_it_was_not_told(p, q):
    """Exact ``a·r^p(1−r)^q`` data, no noise: the fitter has to return (p, q) and an
    R² of 1. This is what makes a *measured* (p, q) elsewhere meaningful."""
    r = np.linspace(0.03, 0.95, 40)
    chi = 7.3 * r ** p * (1.0 - r) ** q
    fit = k02.fit_beta_shape(r, chi)
    assert fit["p"] == pytest.approx(p, abs=0.05)
    assert fit["q"] == pytest.approx(q, abs=0.05)
    assert fit["a"] == pytest.approx(7.3, rel=0.05)
    assert fit["r2"] > 0.999
    assert fit["peak"] == pytest.approx(p / (p + q), abs=0.01)


def test_pinned_fit_scores_perfectly_on_its_own_form_and_badly_on_another():
    """The constrained (2,3) fit must be a fair instrument: R²≈1 when the data really
    is r²(1−r)³, and clearly poor when it is not. Without both halves a negative R²
    downstream would be uninterpretable."""
    r = np.linspace(0.03, 0.95, 40)
    own = k02.fit_fixed_shape(r, 5.0 * r ** 2 * (1.0 - r) ** 3)
    assert own["r2"] > 0.9999
    assert own["a"] == pytest.approx(5.0, rel=1e-6)
    other = k02.fit_fixed_shape(r, 5.0 * r ** 6 * (1.0 - r) ** 1)
    assert other["r2"] < 0.5


def test_pinned_fit_can_score_below_zero():
    """R² < 0 means 'worse than a flat line through the data's own mean'. K02 relies on
    that being reachable rather than clamped, because it is the sharpest way to say a
    published closed form does not describe a curve."""
    r = np.linspace(0.03, 0.95, 40)
    # A bump that peaks near r→0, where r²(1−r)³ is pinned to ~zero.
    chi = 1.0 / (1.0 + 400.0 * (r - 0.05) ** 2)
    assert k02.fit_fixed_shape(r, chi)["r2"] < 0.0


def test_seed_combination_survives_one_intermittent_excursion():
    """The property that forced the median: four well-behaved initial conditions and
    one that made a rare de-sync excursion at a single coupling. The combined curve
    must still peak where the four agree — a mean lets the one outlier move it.

    The numbers here are the shape of the real N=2000 failure from the first pass.
    """
    quiet = [1.0, 1.2, 1.6, 1.7, 1.6, 1.1, 0.5]        # peak at index 3
    seeds = [list(quiet) for _ in range(4)]
    rogue = list(quiet)
    rogue[5] = 12.0                                     # the excursion
    seeds.append(rogue)

    combined = k02.combine_over_seeds(seeds)
    assert int(np.argmax(combined)) == 3
    assert combined[5] == pytest.approx(1.1)            # the outlier is rejected
    # ...and the mean would have been hijacked, which is the whole reason.
    assert int(np.argmax(np.mean(seeds, axis=0))) == 5


def test_seed_combination_is_the_plain_answer_when_nothing_is_pathological():
    """Robustness must not cost correctness on well-behaved input."""
    seeds = [[1.0, 2.0, 3.0], [1.1, 2.1, 3.1], [0.9, 1.9, 2.9]]
    np.testing.assert_allclose(k02.combine_over_seeds(seeds), [1.0, 2.0, 3.0])


# ───────────────── the calibration: r(K_c, N) against a published exponent ─────────────────

def test_critical_exponent_fit_recovers_an_exact_power_law():
    """Synthetic r = A·N^−0.39 with no noise: the fitter has to return 0.39 and R²=1."""
    rungs = [{"n": n, "r_critical": 0.5 * n ** -0.39, "r_sem": 1e-6} for n in K02_LADDER]
    fit = k02.fit_critical_exponent(rungs)
    assert fit["exponent"] == pytest.approx(0.39, abs=1e-6)
    assert fit["r2"] > 0.9999
    assert fit["points"] == len(K02_LADDER)


def test_critical_exponent_error_bar_is_the_larger_of_two_estimates():
    """A tidy line through points with big individual error bars must NOT report the
    tiny regression error — that is how a fit claims precision its inputs lack."""
    rungs = [{"n": n, "r_critical": 0.5 * n ** -0.39, "r_sem": 0.25 * (0.5 * n ** -0.39)}
             for n in K02_LADDER]
    fit = k02.fit_critical_exponent(rungs)
    assert fit["err_regression"] < 1e-6          # the points are exactly collinear
    assert fit["err_propagated"] > 0.05          # ...but each one is badly known
    assert fit["err"] == pytest.approx(fit["err_propagated"])


def test_critical_coherence_reports_its_own_equilibration_drift():
    """The measurement carries the diagnostic that would have caught the retired
    headline: how much ⟨r⟩ moved between the halves of its own window."""
    got = k02.critical_coherence(250, seeds=3, t_burn=40.0, t_measure=80.0)
    assert 0.0 < got["r_critical"] < 1.0
    assert got["equilibration_drift"] == pytest.approx(
        abs(got["r_second_half"] - got["r_first_half"]) / got["r_critical"], rel=1e-9,
    )
    assert len(got["r_by_seed"]) == 3


def test_check_passes_a_calibration_that_matches_the_published_exponent():
    ok, detail = check_k02(_ladder_report())
    assert ok, detail
    assert "reproduces the published finite-size exponent" in detail
    assert "Hong et al. 2015" in detail


def test_check_rejects_the_random_sampling_universality_class():
    """The gate's main job: a frequency draw that lost the deterministic quantile grid
    lands in the RANDOM class at β/ν̄ = 0.20, not 0.39. That must fail."""
    report = _ladder_report(critical=_critical(exponent=0.20))
    ok, detail = check_k02(report)
    assert ok is False
    assert "misses the published" in detail


def test_check_rejects_the_retired_beta_fit_artifact_value():
    """0.28 is the number the demoted p/(p+q) estimator produced. The calibration gate
    must not accept it, or the regression this revision fixes could silently return."""
    ok, detail = check_k02(_ladder_report(critical=_critical(exponent=0.28)))
    assert ok is False
    assert "misses the published" in detail


def test_check_rejects_a_rung_that_never_equilibrated():
    """The defect behind the retired headline: averaging a transient. A rung still
    drifting between the halves of its own window is refused, not averaged."""
    block = _critical()
    block[-1]["equilibration_drift"] = 0.6
    block[-1]["equilibration_drift_sigma"] = 9.0
    ok, detail = check_k02(_ladder_report(critical=block))
    assert ok is False
    assert "still drifting" in detail
    assert "transient" in detail


def test_equilibration_gate_forgives_a_drift_that_is_only_noise():
    """The correction this gate needed: at N=2000 the shipped protocol returned an
    11.3% half-to-half change that is well inside the drift estimator's own noise. A
    bare-percentage gate would have refused a settled rung; the sigma gate must not."""
    block = _critical()
    block[3]["equilibration_drift"] = 0.113
    block[3]["equilibration_drift_sigma"] = 1.8
    ok, detail = check_k02(_ladder_report(critical=block))
    assert ok, detail


def test_equilibration_absolute_cap_still_catches_an_unreadable_sigma():
    """If the drift's error bar is missing or unusable, the loose absolute cap is the
    fallback — a rung cannot dodge the gate by omitting its uncertainty."""
    block = _critical()
    block[-1]["equilibration_drift"] = 0.6
    block[-1]["equilibration_drift_sigma"] = float("nan")
    ok, detail = check_k02(_ladder_report(critical=block))
    assert ok is False
    assert "absolute cap" in detail


def test_check_refits_the_exponent_and_ignores_a_forged_one():
    """A receipt claiming the right answer over wrong data must still fail."""
    report = _ladder_report(critical=_critical(exponent=0.20))
    report["critical_fit"] = {"exponent": K02_CRITICAL_EXPONENT, "err": 0.001}
    report["headline"] = "matches the published exponent exactly"
    assert check_k02(report)[0] is False


def test_check_rejects_a_report_with_no_calibration_block():
    report = _ladder_report()
    del report["critical"]
    ok, detail = check_k02(report)
    assert ok is False
    assert "missing its r(K_c, N) calibration" in detail


def test_check_passes_a_clip_control_whose_two_settings_agree():
    ok, detail = check_k02(_ladder_report())
    assert ok, detail
    assert "tail-clip control agrees" in detail


def test_check_rejects_an_exponent_riding_on_the_frequency_clip():
    """The assay flagged the |ω| ≤ 40γ clip as an uncontrolled deviation from the
    published configuration. If loosening it moved r(K_c), the calibration would be
    measuring the clip rather than the physics — that must fail."""
    ok, detail = check_k02(_ladder_report(clip_control=_clip_control(delta=0.02)))
    assert ok is False
    assert "riding on the clip" in detail


def test_check_rejects_a_clip_control_that_compared_a_setting_to_itself():
    """A control that never varied the thing it controls for is not a control."""
    same = _clip_control()
    same[1]["clip_scale"] = same[0]["clip_scale"]
    ok, detail = check_k02(_ladder_report(clip_control=same))
    assert ok is False
    assert "SAME clip to itself" in detail


def test_check_rejects_a_report_with_no_clip_control():
    report = _ladder_report()
    del report["clip_control"]
    ok, detail = check_k02(report)
    assert ok is False
    assert "missing its tail-clip negative control" in detail


def test_clip_control_constants_are_mirrored_and_actually_vary_the_clip():
    assert k02.CLIP_CONTROL_ALT_SCALE != k02.kuramoto_clip_default()
    # dt must shrink with the looser clip or the fastest drifter is aliased, which
    # would make the control fail for an integration reason rather than a physical one.
    assert k02.CLIP_CONTROL_ALT_DT < k02.DT
    assert (k02.CLIP_CONTROL_ALT_SCALE * k02.CALIBRATION_GAMMA
            * k02.CLIP_CONTROL_ALT_DT) <= 0.5
    assert K02_CLIP_CONTROL_MAX_SIGMA >= 2.0


def test_published_benchmark_is_mirrored_between_runner_and_check():
    assert K02_CRITICAL_EXPONENT == k02.CRITICAL_EXPONENT_PUBLISHED
    assert K02_CRITICAL_EXPONENT_ERR == k02.CRITICAL_EXPONENT_PUBLISHED_ERR


def test_calibration_tolerance_brackets_the_literature_and_excludes_the_artifacts():
    """The tolerance's justification is arithmetic, not taste.

    It must admit the whole published window for this sampling class — Hong's 0.39(2)
    and Park & Park's asymptotic 0.325(15), between which a finite ladder legitimately
    sits — while excluding the random-sampling class (0.20) and the 0.28 the demoted
    estimator produced.
    """
    lo = K02_CRITICAL_EXPONENT - K02_CRITICAL_TOL
    hi = K02_CRITICAL_EXPONENT + K02_CRITICAL_TOL
    assert lo <= k02.CRITICAL_EXPONENT_ASYMPTOTIC <= hi
    assert lo <= K02_CRITICAL_EXPONENT - K02_CRITICAL_EXPONENT_ERR
    assert not (lo <= k02.CRITICAL_EXPONENT_RANDOM_SAMPLING <= hi)
    assert not (lo <= 0.28 <= hi)          # the retired Beta-fit artifact
    # The equilibration gate is on SIGNIFICANCE; the absolute cap is only the fallback
    # for an unreadable error bar and is deliberately loose. Assert that ordering
    # rather than a magnitude, so the cap can be tuned without the test lying.
    assert K02_EQUILIBRATION_MAX_DRIFT_SIGMA >= 2.0
    assert K02_EQUILIBRATION_MAX_DRIFT > 0.15


def test_run01_constants_are_the_published_ones():
    assert (k02.RUN01_P, k02.RUN01_Q) == (2.0, 3.0)
    assert k02.RUN01_R_STAR == pytest.approx(0.4)


# ───────────────── the grid: dense where the r-axis is ill-conditioned ─────────────────

def test_coupling_grid_straddles_kc_and_is_dense_exactly_there():
    """The grid's whole justification is that r(K) = √(1−K_c/K) has infinite slope at
    K_c⁺, so the r-axis is resolved worst precisely where the peak lives. Assert the
    density is where the docstring says, not merely that a grid exists."""
    K = k02.coupling_grid(KURAMOTO_GAMMA)
    k_c = 2.0 * KURAMOTO_GAMMA
    assert K[0] == 0.0                              # the negative control is on the grid
    assert K.min() < k_c < K.max()
    near = K[(K >= 0.98 * k_c) & (K <= 1.12 * k_c)]
    assert near.size >= 15
    assert float(np.diff(near).max()) <= 0.011 * k_c
    # ...and sparse elsewhere, which is what keeps the ladder a CPU-minutes job.
    far = K[K > 1.4 * k_c]
    assert float(np.diff(far).min()) >= 0.15 * k_c


def test_grid_reaches_far_enough_up_the_ordered_branch_for_a_shape_fit():
    """The fit needs the whole r-range, not just the peak: at K = 2·K_c the exact
    branch is √(1−½) ≈ 0.707, so the sweep covers most of [0, 1]."""
    K = k02.coupling_grid(KURAMOTO_GAMMA)
    k_c = 2.0 * KURAMOTO_GAMMA
    assert K.max() >= 2.0 * k_c - 1e-12
    assert math.sqrt(1.0 - k_c / float(K.max())) > 0.7


# ───────────────── the runner + report ─────────────────

@pytest.fixture(scope="module")
def quick_run():
    return k02.run_k02(**QUICK)


def test_quick_ladder_finds_an_interior_peak_at_every_rung(quick_run):
    for rung in quick_run.rungs:
        assert 0 < rung.peak_index < len(rung.K) - 1
        assert 0.0 < rung.r_star < 1.0
        assert rung.chi_endpoint_ratio > 1.0


def test_chi_is_exactly_n_times_the_variance(quick_run):
    for rung in quick_run.rungs:
        for c, v in zip(rung.chi, rung.r_var):
            assert c == pytest.approx(rung.n * v, rel=1e-12)


def test_a_short_ladder_is_marked_a_diagnostic_not_the_measurement(quick_run):
    assert quick_run.is_calibration is False


def test_report_status_is_the_checks_verdict_not_the_runners(quick_run):
    report = k02.to_report(quick_run)
    ok, _ = check_k02(report)
    assert report["status"] == ("pass" if ok else "null")


def test_report_carries_the_raw_arrays_the_check_regrades_from(quick_run):
    report = k02.to_report(quick_run)
    for rung in report["rungs"]:
        assert len(rung["K"]) == len(rung["r_mean"]) == len(rung["r_var"]) == len(rung["chi"])
        assert rung["r_star_by_seed"]


# ───────────────── the check: a receipt, not an echo ─────────────────

def _rung(n: int, r_star: float = 0.10, k_peak_shift: float = 0.0,
          r0: float | None = None, r_spread: float = 1.0) -> dict:
    """One structurally honest rung, on the real coupling grid.

    The two things the check grades independently are deliberately given independent
    knobs, which a physics-shaped fixture cannot offer: ``k_peak_shift`` moves the χ
    maximum along the CONTROL axis (exercising the exact-K_c anchor) while ``r_star``
    sets the coherence at that maximum, and ``r_spread`` stretches the r-axis around
    the peak (exercising the resolution gate). ⟨r⟩ rises through ``r_star`` at the
    peak; χ is a bump centred on the same sample, so peak-in-K and peak-in-r are the
    same point exactly as they are in a real sweep.
    """
    k_c = 2.0 * KURAMOTO_GAMMA
    K = [float(x) for x in k02.coupling_grid(KURAMOTO_GAMMA)]
    m = len(K)
    target = k_c + k_peak_shift
    i = min(range(m), key=lambda j: abs(K[j] - target))
    i = max(1, min(m - 2, i))
    lo = r0 if r0 is not None else min(1.0 / math.sqrt(n), 0.5 * r_star)
    r_mean = []
    for j in range(m):
        if j <= i:
            r = lo + (r_star - lo) * (j / i)
        else:
            r = r_star + (0.95 - r_star) * ((j - i) / (m - 1 - i)) ** 2
        r_mean.append(r)
    if r_spread != 1.0:
        r_mean = [r_star + (r - r_star) * r_spread for r in r_mean]
    r_mean = [min(0.99, max(0.0, r)) for r in r_mean]
    r_var = [max(1e-9, 1.0 / (1.0 + ((j - i) / 2.5) ** 2)) / n for j in range(m)]
    return {
        "n": n, "K": K, "r_mean": r_mean, "r_var": r_var,
        "chi": [n * v for v in r_var],
    }


def _critical(exponent: float = K02_CRITICAL_EXPONENT, amplitude: float = 0.5,
              drift: float = 0.02, drift_sigma: float = 0.8) -> list[dict]:
    """The r(K_c, N) calibration block: an exact power law with the given exponent."""
    return [
        {
            "n": n,
            "r_critical": amplitude * n ** (-exponent),
            "r_sem": 0.001,
            "equilibration_drift": drift,
            "equilibration_drift_sigma": drift_sigma,
        }
        for n in K02_LADDER
    ]


def _clip_control(delta: float = 0.0, sem: float = 0.0016) -> list[dict]:
    """The tail-clip negative control: the same r(K_c) at two clip settings."""
    return [
        {"r_critical": 0.0498, "r_sem": sem, "clip_scale": 40.0},
        {"r_critical": 0.0498 + delta, "r_sem": sem, "clip_scale": 100.0},
    ]


def _ladder_report(critical=None, clip_control=None, **kwargs) -> dict:
    return {
        "experiment": "K02-coherence-susceptibility-shape",
        "gamma": KURAMOTO_GAMMA,
        "kc_exact": 2.0 * KURAMOTO_GAMMA,
        "ladder": list(K02_LADDER),
        "seeds": list(K02_SEEDS),
        "run01_r_star": K02_RUN01_R_STAR,
        "critical": _critical() if critical is None else critical,
        "clip_control": _clip_control() if clip_control is None else clip_control,
        # r* marching left as N grows — the shape the real ladder measures.
        "rungs": [_rung(n, r_star=s, **kwargs)
                  for n, s in zip(K02_LADDER, (0.16, 0.12, 0.09, 0.07, 0.05))],
        "status": "pass",
    }


def test_check_ignores_reports_it_cannot_read():
    assert check_k02({"experiment": "K01-kuramoto-synchronization"})[0] is None
    assert check_k02({"experiment": "K02-coherence-susceptibility-shape"})[0] is None


def test_check_passes_a_well_formed_ladder_receipt():
    ok, detail = check_k02(_ladder_report())
    assert ok, detail
    assert "interior χ maximum in r resolved at every rung" in detail


def test_check_reports_the_collapse_as_a_finding_without_gating_on_it():
    """The scientific verdict is *stated* by the check, never *graded* by it — a
    ladder whose r* is instead N-independent must still PASS, because the gate
    certifies the instrument, not the direction the physics went."""
    collapsing = _ladder_report()
    ok, detail = check_k02(collapsing)
    assert ok
    assert "r* COLLAPSES with N" in detail

    flat = _ladder_report()
    flat["rungs"] = [_rung(n, r_star=0.15) for n in K02_LADDER]
    ok_flat, detail_flat = check_k02(flat)
    assert ok_flat, detail_flat
    assert "r* is N-INDEPENDENT at this resolution" in detail_flat


def test_check_regrades_from_the_arrays_and_ignores_the_stored_headline():
    """A forged headline must not move the grade in EITHER direction."""
    good = _ladder_report()
    good["headline"] = "r* is exactly 2/5 at every N"
    good["scaling_exponent"] = 0.0
    good["status"] = "null"
    assert check_k02(good)[0] is True

    bad = _ladder_report()
    bad["rungs"][2] = _rung(1000, r_star=0.09, k_peak_shift=0.9)
    bad["headline"] = "every rung anchored on the exact K_c"
    ok, detail = check_k02(bad)
    assert ok is False
    assert "off the exact K_c" in detail


def test_check_rejects_a_chi_curve_that_disagrees_with_its_own_variances():
    report = _ladder_report()
    report["rungs"][1]["chi"] = [c * 3.0 for c in report["rungs"][1]["chi"]]
    ok, detail = check_k02(report)
    assert ok is False
    assert "not self-consistent" in detail


def test_check_rejects_a_ladder_with_no_interior_peak():
    """χ that rises monotonically to the end of the sweep has no interior maximum in
    r — sub-claim 1 failing is the one result that must never be graded a pass."""
    report = _ladder_report()
    rung = report["rungs"][0]
    rung["r_var"] = [(i + 1) / (100.0 * rung["n"]) for i in range(len(rung["K"]))]
    rung["chi"] = [rung["n"] * v for v in rung["r_var"]]
    ok, detail = check_k02(report)
    assert ok is False
    assert "no interior peak in r" in detail


def test_check_rejects_a_peak_with_no_margin_over_the_ends():
    """A flat, noise-dominated χ curve satisfies a bare argmax test. The margin gate
    is what refuses it."""
    report = _ladder_report()
    rung = report["rungs"][0]
    flat = [1.0] * len(rung["K"])
    flat[len(flat) // 2] = 1.05
    rung["r_var"] = [v / rung["n"] for v in flat]
    rung["chi"] = [rung["n"] * v for v in rung["r_var"]]
    ok, detail = check_k02(report)
    assert ok is False
    assert "no resolved interior maximum" in detail


def test_check_rejects_a_run_that_did_not_resolve_r_star():
    """The gate that bites hardest: a peak straddled by neighbours far apart in r has
    not measured anything, whichever way the number points."""
    report = _ladder_report()
    # Stretch the r-axis around the peak so its two neighbours straddle a wide span.
    report["rungs"][0] = _rung(K02_LADDER[0], r_star=0.16, r_spread=16.0)
    ok, detail = check_k02(report)
    assert ok is False
    assert "cannot tell the two apart" in detail


def test_check_rejects_a_rung_that_lands_on_the_claim_it_is_testing():
    """The symmetric half of gate 2. A peak sitting *on* 2/5 within its own error is
    inconclusive — and must fail, so the gate can never be read as rewarding either
    outcome. Without this the gate would quietly be 'did you refute Run 01?'."""
    report = _ladder_report()
    report["rungs"] = [_rung(n, r_star=K02_RUN01_R_STAR) for n in K02_LADDER]
    ok, detail = check_k02(report)
    assert ok is False
    assert "from Run 01's r*=0.40" in detail


def test_check_rejects_order_that_appears_without_any_coupling():
    """The negative control, re-run at every population size."""
    report = _ladder_report(r0=0.9)
    ok, detail = check_k02(report)
    assert ok is False
    assert "uncoupled control failed" in detail


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda rep: rep.update(gamma=0.25), "ladder identity changed"),
        (lambda rep: rep.update(ladder=[250, 500]), "ladder identity changed"),
        (lambda rep: rep.update(seeds=[42]), "ladder identity changed"),
        (lambda rep: rep["rungs"][0].update(n=999), "ladder identity changed"),
        (lambda rep: rep["rungs"][0].update(
            r_var=[-1.0] * len(rep["rungs"][0]["K"])), "negative variance"),
        (lambda rep: rep["rungs"][0].update(
            r_mean=[1.4] * len(rep["rungs"][0]["K"])), "outside [0,1]"),
    ],
)
def test_check_rejects_tampered_identity_and_evidence(mutate, reason):
    report = _ladder_report()
    mutate(report)
    report["status"] = "pass"
    report["headline"] = "everything is fine"
    ok, detail = check_k02(report)
    assert ok is False
    assert reason in detail


def test_check_reports_unreadable_arrays_as_unreadable_not_as_a_default():
    report = _ladder_report()
    report["rungs"][1]["r_mean"] = [None] * len(report["rungs"][1]["K"])
    ok, detail = check_k02(report)
    assert ok is None
    assert "readable" in detail


# ───────────────── the identity + the declared floors, mirrored ─────────────────

def test_k02_identity_mirrors_the_runner():
    """``checks`` owns the floors, but its identity constants must be the SAME ladder
    the runner ships — pinned here so changing one without the other reds instead of
    silently un-gating the milestone."""
    assert K02_LADDER == k02.CALIBRATION_LADDER
    assert K02_SEEDS == k02.CALIBRATION_SEEDS
    assert KURAMOTO_GAMMA == k02.CALIBRATION_GAMMA
    assert K02_RUN01_R_STAR == pytest.approx(k02.RUN01_R_STAR)


def test_declared_floors_are_consistent_with_what_they_claim_to_bound():
    """The floors' stated justification is arithmetic, not taste — assert it.

    The r* floor is the local spacing WIDENED, never narrowed: the peak's index is
    what is uncertain, so a floor at one grid step would understate it. And the
    absolute minimum has to stay well under the distance to the hypothesis being
    tested, or no grid however fine could clear the gate.
    """
    assert K02_K_PEAK_STEPS > 1.0
    assert K02_R_STAR_SCATTER < K02_RUN01_R_STAR / 3.0
    assert K02_R_STAR_EXCLUSION_SIGMA >= 1.0
    assert K02_INTERIOR_PEAK_RATIO >= 2.0
    # The K_c anchor must admit the physical finite-N shift K01 measured at the
    # smallest rung (+0.050 at N=250) while staying far inside a broken run's miss.
    assert K02_KC_TOL >= 0.05
    assert K02_KC_TOL < 0.25 * (2.0 * KURAMOTO_GAMMA)


def test_the_shipped_grid_beats_the_resolution_gate_at_every_rung_it_was_designed_for():
    """The grid and the gate are declared in different files; this pins them together
    so a 'harmless' grid coarsening cannot quietly make the milestone ungradeable."""
    report = _ladder_report()
    for rung in report["rungs"]:
        i = max(range(len(rung["chi"])), key=lambda k: rung["chi"][k])
        assert 0 < i < len(rung["chi"]) - 1
        floor = max(
            K02_K_PEAK_STEPS * 0.5 * abs(rung["r_mean"][i + 1] - rung["r_mean"][i - 1]),
            K02_R_STAR_SCATTER,
        )
        assert abs(rung["r_mean"][i] - K02_RUN01_R_STAR) > floor
