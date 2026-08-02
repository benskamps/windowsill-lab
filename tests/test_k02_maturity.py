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
    K02_INTERIOR_PEAK_RATIO, K02_KC_TOL, K02_K_PEAK_STEPS, K02_LADDER,
    K02_RUN01_R_STAR, K02_R_STAR_EXCLUSION_SIGMA, K02_R_STAR_SCATTER, K02_SEEDS,
    KURAMOTO_GAMMA, check_k02,
)


QUICK = dict(ladder=(250, 500), seeds=(42,), t_burn=20.0, t_measure=60.0)


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


def _ladder_report(**kwargs) -> dict:
    return {
        "experiment": "K02-coherence-susceptibility-shape",
        "gamma": KURAMOTO_GAMMA,
        "kc_exact": 2.0 * KURAMOTO_GAMMA,
        "ladder": list(K02_LADDER),
        "seeds": list(K02_SEEDS),
        "run01_r_star": K02_RUN01_R_STAR,
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
