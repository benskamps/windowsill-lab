"""Gates on ``scripts/tic374861595_refit.py``.

The script's own ``--selftest`` is the end-to-end gate and this file does not
duplicate it. What it adds is the granularity a suite gives you and a single
pass/fail does not: when the Mann coefficients get retyped, or someone swaps
the occultation quadrature for something faster, these say *which* thing broke.

Three things get pinned here and nothing else, because nothing else in that
script is checkable without a light curve:

1. **The Mann relations, against hand-computed values and against TIC v8.**
   Two routes. The hand arithmetic catches a mistyped coefficient; agreeing
   with TIC v8's published 0.6159 R☉ and 0.601 M☉ for this star — which TIC
   derived from the same relations on the same M_K — catches using the *wrong
   relation*, which the hand check by itself would happily confirm.
2. **The occultation model, against the closed forms it is supposed to
   reproduce.** A limb-darkening integrator that only ever gets fed limb
   darkening has nothing to be checked against; set every coefficient to zero
   and Mandel & Agol (2002) Eq. 1 is an exact answer written by other people.
3. **Injection-recovery at low noise.** A fitter nobody has handed a known
   answer is indistinguishable from one that returns its starting guess, and
   the starting guess here is SPOC's published fit — which would look
   *extremely* convincing.

The deliberate absence: there is no test that the script gets TIC 374861595
right, because nothing in this repo knows what right is. That is the whole
reason the candidate is still a candidate.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "tic374861595_refit.py"


def _load():
    """Import the script by path — it lives in scripts/, not in the package."""
    spec = importlib.util.spec_from_file_location("tic374861595_refit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


refit = _load()


# ------------------------------------------------------- the Mann relations --


def test_mann15_radius_hand_computed():
    """R★ = 1.9515 − 0.3520·M_K + 0.01680·M_K², at two points done on paper."""
    # M_K = 4.98: 1.9515 − 1.752960 + 0.016800·24.8004 = 1.9515 − 1.75296 + 0.416647
    assert refit.mann15_radius(4.98) == pytest.approx(0.615187, abs=1e-6)
    # M_K = 7.00: 1.9515 − 2.4640 + 0.8232
    assert refit.mann15_radius(7.00) == pytest.approx(0.310700, abs=1e-6)
    # M_K = 9.00: 1.9515 − 3.1680 + 1.360800
    assert refit.mann15_radius(9.00) == pytest.approx(0.144300, abs=1e-6)


def test_mann15_reproduces_tic_v8_for_this_star():
    """The independent leg: TIC v8 lists 0.615867 R☉ from M_K = 4.98."""
    assert refit.mann15_radius(4.98) == pytest.approx(
        refit.SPOC_DV["rstar_sun"], abs=2e-3)


def test_mann15_is_decreasing_and_sane_across_its_range():
    mk = np.linspace(*refit.MANN15_MK_RANGE, 60)
    r = refit.mann15_radius(mk)
    assert np.all(np.diff(r) < 0), "R* must fall as M dwarfs get fainter"
    assert np.all(r > 0.08) and np.all(r < 0.75), (
        "M-dwarf radii outside 0.08-0.75 Rsun across the calibrated range")


def test_mann19_mass_hand_computed():
    """M★ = 10^(Σ aᵢ·(M_K − 7.5)ⁱ), at the zero point and at this target."""
    # At M_K = 7.5 every term but a0 vanishes: 10^(-0.642).
    assert refit.mann19_mass(7.5) == pytest.approx(0.228034, abs=1e-6)
    assert refit.mann19_mass(7.5) == pytest.approx(10.0**-0.642, rel=1e-12)
    # At M_K = 4.98 the polynomial sums to -0.22176431 (worked out in the
    # script's selftest comment, term by term).
    assert refit.mann19_mass(4.98) == pytest.approx(0.6001167, abs=1e-6)


def test_mann19_reproduces_tic_v8_mass_for_this_star():
    """TIC v8 lists 0.601 M☉; the relation gives 0.6001. Different route."""
    assert refit.mann19_mass(4.98) == pytest.approx(0.601, abs=0.01)


def test_mann19_zero_point_offset_is_not_optional():
    """A forgotten −7.5 offset is the failure mode this catches.

    If the polynomial were evaluated in M_K rather than (M_K − 7.5), the mass
    at M_K = 4.98 would come out near 10^(-0.642 − 0.208·4.98 + …) — wrong by a
    factor of several. Pinning that the two differ by more than 2x makes the
    offset load-bearing rather than decorative.
    """
    x = 4.98
    wrong = 10.0 ** sum(a * x**i for i, a in enumerate(refit.MANN19_M_COEFFS))
    right = float(refit.mann19_mass(x))
    assert not (0.5 < wrong / right < 2.0), (
        "dropping the M_K - 7.5 zero point changes nothing; the test is dead")


def test_mann19_is_decreasing_across_its_range():
    mk = np.linspace(*refit.MANN19_MK_RANGE, 60)
    m = refit.mann19_mass(mk)
    assert np.all(np.diff(m) < 0)
    assert np.all(m > 0.05) and np.all(m < 0.8)


def test_absolute_magnitude_round_trip():
    """M = m + 5·log10(ϖ/100); at 100 mas (10 pc) the two must be equal."""
    assert refit.absolute_magnitude(11.0, 100.0) == pytest.approx(11.0, abs=1e-12)
    # 4.47 mas -> 223.7 pc -> distance modulus 6.7485
    assert refit.absolute_magnitude(11.7285, 4.47) == pytest.approx(4.98, abs=0.01)
    # Extinction makes a star intrinsically brighter, i.e. M smaller.
    assert refit.absolute_magnitude(11.0, 10.0, 0.05) < refit.absolute_magnitude(11.0, 10.0)


def test_stellar_parameters_carry_the_relation_scatter():
    """The quoted error must exceed the measurement error alone.

    With ϖ/σ_ϖ = 150 and σ_K = 0.025, the measurement contribution to R★ is
    ~0.5 %. The relation's own calibration scatter is 2.89 %. If the reported
    error ever drops below ~2 %, the scatter has been dropped somewhere and
    every downstream error bar is three times too small.
    """
    star = refit.stellar_parameters(11.7285, 0.025, 4.47, 0.03, n_mc=8000)
    assert star["rstar_sun"] == pytest.approx(0.6152, abs=2e-3)
    assert star["mstar_sun"] == pytest.approx(0.6001, abs=5e-3)
    assert star["rstar_sun_err"] / star["rstar_sun"] > 0.02
    assert star["mstar_sun_err"] / star["mstar_sun"] > 0.02
    assert star["in_range_mann15"] and star["in_range_mann19"]
    assert star["distance_pc"] == pytest.approx(223.7, abs=0.5)


def test_density_units_are_reported_both_ways():
    """ρ★ in cgs and in solar units, and the conversion between them.

    The CTOI package prints 2.57 as 'g/cm³' where it is really M★/R★³ in solar
    units (3.63 g/cm³). Both numbers are pinned here so a reader of the script
    output can tell which is which without redoing the arithmetic.
    """
    star = refit.stellar_parameters(11.7285, 0.025, 4.47, 0.03, n_mc=2000)
    assert star["rho_star_cgs"] == pytest.approx(3.63, abs=0.05)
    assert star["rho_star_sun"] == pytest.approx(2.577, abs=0.02)
    assert star["rho_star_cgs"] / star["rho_star_sun"] == pytest.approx(
        refit.RHO_SUN_CGS, rel=1e-12)


# ----------------------------------------------------- the occultation model --


def test_out_of_transit_flux_is_exactly_one():
    """Past first contact (z > 1 + k) the model must return 1, not 1 − ε."""
    for law, coeffs in (("uniform", ()),
                        ("quadratic", (0.4, 0.2)),
                        ("nonlinear", refit.CLARET_TESS)):
        func, _ = refit.LD_LAWS[law]
        z = np.array([1.0 + 0.3 + 1e-9, 1.5, 3.0, 50.0])
        f = refit.occultation_ld(z, 0.3, lambda mu, c=coeffs, g=func: g(mu, c))
        assert np.allclose(f, 1.0, atol=1e-12), f"{law} leaks flux out of transit"


def test_flux_never_exceeds_one():
    intensity = lambda mu: refit.claret_nonlinear_intensity(mu, refit.CLARET_TESS)
    for k in (0.02, 0.1, 0.3, 0.43, 0.6):
        z = np.linspace(0.0, 1.0 + k, 701)
        f = refit.occultation_ld(z, k, intensity)
        assert np.all(f <= 1.0 + 1e-12), f"flux above 1 at k={k}"
        assert np.all(f >= 0.0), f"negative flux at k={k}"


def test_uniform_central_depth_is_exactly_k_squared():
    """No limb darkening, planet fully on the disk: depth = k², analytically."""
    for k in (0.05, 0.2, 0.3, 0.43):
        f = refit.occultation_ld(np.array([0.0]), k, refit.uniform_intensity, ng=40)
        assert (1.0 - f[0]) == pytest.approx(k * k, abs=1e-9)
        # And anywhere the planet is fully inside the disk, not just the centre.
        f2 = refit.occultation_ld(np.array([0.5 * (1.0 - k)]), k,
                                  refit.uniform_intensity, ng=40)
        assert (1.0 - f2[0]) == pytest.approx(k * k, abs=1e-9)


def test_limb_darkened_central_depth_exceeds_k_squared():
    """LD concentrates light in the middle, so a central transit is deeper.

    A sign error in the intensity law flips this, and nothing else in the
    fitter would notice: it would just come back with a smaller k.
    """
    k = 0.3
    intensity = lambda mu: refit.claret_nonlinear_intensity(mu, refit.CLARET_TESS)
    depth = 1.0 - refit.occultation_ld(np.array([0.0]), k, intensity, ng=40)[0]
    assert depth > k * k
    assert depth == pytest.approx(0.1058, abs=2e-3)


def test_central_depth_is_monotonic_in_k():
    intensity = lambda mu: refit.claret_nonlinear_intensity(mu, refit.CLARET_TESS)
    ks = [0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    depths = [1.0 - refit.occultation_ld(np.array([0.0]), k, intensity)[0] for k in ks]
    assert all(b > a for a, b in zip(depths, depths[1:])), depths


def test_depth_is_monotonic_in_impact_parameter():
    """Deeper the more central — for a fixed k, at fixed a/R★."""
    model = refit.TransitModel("nonlinear", refit.CLARET_TESS, backend="numpy")
    depths = [refit.transit_depth_ppm(model, 1.9369484, 0.3, 7.71, b)
              for b in (0.0, 0.2, 0.4, 0.6, 0.8, 0.95, 1.1)]
    assert all(b < a for a, b in zip(depths, depths[1:])), depths


def test_matches_mandel_agol_uniform_closed_form():
    """The independent-implementation check, at 1 ppm.

    ``uniform_occultation`` is analytic circle-circle overlap;
    ``occultation_ld`` is a radial quadrature. They share no line of code.
    """
    for k in (0.05, 0.3, 0.43, 0.7):
        z = np.unique(np.concatenate([
            np.linspace(0.0, 1.0 + k, 601),
            np.array([0.0, abs(1.0 - k), 1.0 + k, 1.0, k]),
        ]))
        mine = refit.occultation_ld(z, k, refit.uniform_intensity, ng=40)
        closed = refit.uniform_occultation(z, k)
        assert np.max(np.abs(mine - closed)) < 1e-6, f"k={k}"


def test_quadrature_normalisation_matches_closed_forms():
    """∫I dA/π by quadrature vs. the analytic value, for each law."""
    nodes, weights = refit._gauss_legendre(64)
    s = 0.5 + 0.5 * nodes
    for law, coeffs in (("uniform", ()),
                        ("quadratic", (0.35, 0.22)),
                        ("nonlinear", refit.CLARET_TESS)):
        func, _ = refit.LD_LAWS[law]
        num = float(np.sum(4.0 * s**3 * func(s * s, coeffs) * weights) * 0.5)
        assert num == pytest.approx(refit.ld_norm_closed_form(law, coeffs), abs=1e-9)


def test_interpolated_table_matches_direct_evaluation():
    """The speed shortcut must not cost more than 20 ppm on a 100,000 ppm dip."""
    intensity = lambda mu: refit.claret_nonlinear_intensity(mu, refit.CLARET_TESS)
    for k in (0.1, 0.3, 0.43):
        table = refit.OccultationTable(k, intensity)
        z = np.linspace(0.0, 1.0 + k, 2500)
        assert np.max(np.abs(table(z) - refit.occultation_ld(z, k, intensity))) < 2e-5


def test_secondary_eclipse_is_not_modelled():
    """Flux at phase 0.5 must be exactly 1 — the planet is behind the star.

    The package's whole discriminating measurement is the ABSENCE of a
    secondary (§5c). A model that drew one at phase 0.5 would make the data
    look like it had one.
    """
    model = refit.TransitModel("nonlinear", refit.CLARET_TESS, backend="numpy")
    p = 1.9369484
    t = 0.5 * p + np.linspace(-0.05, 0.05, 401)
    f = model(t, 0.0, p, 0.3, 7.71, 0.45)
    assert np.allclose(f, 1.0, atol=1e-12)


# --------------------------------------------------------- geometry + density --


def test_t14_matches_the_models_own_first_and_last_contact():
    """The analytic duration vs. where the model actually leaves flux 1."""
    p, k, a, b = 1.9369484, 0.30, 7.71, 0.45
    t14, t23, ing = refit.transit_durations(p, k, a, b)
    model = refit.TransitModel("uniform", (), backend="numpy")
    t = np.linspace(-0.2, 0.2, 200001)
    inside = t[model(t, 0.0, p, k, a, b) < 1.0 - 1e-12]
    measured = (inside.max() - inside.min()) * 24.0
    assert t14 == pytest.approx(measured, abs=0.01)
    assert t23 < t14
    assert ing == pytest.approx(0.5 * (t14 - t23), abs=1e-9)


def test_grazing_geometry_has_no_flat_bottom():
    """b > 1 − k means T23 is undefined, and the code must say NaN, not 0."""
    _, t23, ing = refit.transit_durations(1.9369484, 0.43, 7.71, 0.90)
    assert math.isnan(t23)
    assert math.isnan(ing)


def test_density_from_ar_round_trips():
    p = 1.9369484
    for a in (5.0, 7.71, 10.68, 20.0):
        rho = refit.density_from_ar(p, a)
        assert refit.ar_from_density(p, rho) == pytest.approx(a, rel=1e-12)


def test_density_reproduces_the_packages_shape_densities():
    """Both numbers the CTOI package quotes, in the units it actually used.

    §1 quotes a/R★ = 10.68 -> '6.2 g/cm³' (cgs, correct) and §5a quotes SPOC's
    a/R★ = 7.71 -> '1.64' (solar units, labelled g/cm³). Pinning both is how
    a reader of this script can tell the two apart.
    """
    rho_lab = refit.density_from_ar(refit.LAB_TRAPEZOID["period_days"], 10.68)
    assert rho_lab == pytest.approx(6.2, abs=0.1)
    rho_spoc = refit.density_from_ar(refit.SPOC_DV["period_days"], 7.71)
    assert rho_spoc == pytest.approx(2.31, abs=0.05)
    assert rho_spoc / refit.RHO_SUN_CGS == pytest.approx(1.64, abs=0.02)


# ------------------------------------------------------- injection-recovery --


def _inject(truth, *, noise_ppm, seed, cadence_min=10.0, starts=(2036.0, 2065.0, 2150.0)):
    model = refit.TransitModel("nonlinear", refit.CLARET_TESS, backend="numpy")
    rng = np.random.default_rng(seed)
    t = np.concatenate([np.arange(s, s + 24.0, cadence_min / 1440.0) for s in starts])
    clean = model(t, truth["epoch"], truth["period"], truth["k"],
                  truth["a_rstar"], truth["b"])
    sigma = noise_ppm * 1e-6
    f = clean + rng.normal(0.0, sigma, t.size)
    return model, [{"t": t, "f": f, "ferr": np.full_like(f, sigma),
                    "source": "synthetic"}]


def _fit(model, curves, guess, restarts=3):
    t14 = refit.transit_durations(guess[0], guess[2], guess[3], guess[4])[0]
    t, f, e, nwin = refit.window_and_detrend(curves, guess[0], guess[1], t14)
    w, sigma = refit.weights_from(f, e)
    best, chi2, n_ld = refit.fit_transit(t, f, w, model, guess, restarts=restarts)
    return dict(zip(refit.PARAM_NAMES, best[:5])), best, chi2, (t, f, w), nwin, n_ld


@pytest.mark.parametrize("noise_ppm", [200.0, 600.0])
def test_injection_recovery_low_noise(noise_ppm):
    """Inject, fit from a deliberately wrong start, insist on the truth back.

    The starting guess is offset in every parameter — by 3e−5 d in period
    (about a full O−C minute over the baseline), 4 ms in epoch, and a long way
    in (k, a/R★, b) — so passing this cannot be explained by the fitter
    sitting still.
    """
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model, curves = _inject(truth, noise_ppm=noise_ppm, seed=7)
    guess = (truth["period"] + 3e-5, truth["epoch"] + 4e-3, 0.38, 6.4, 0.75)
    got, best, chi2, (t, f, w), nwin, n_ld = _fit(model, curves, guess)

    assert nwin > 30
    assert got["period"] == pytest.approx(truth["period"], abs=1e-5)
    assert got["epoch"] == pytest.approx(truth["epoch"], abs=1e-3)
    assert got["k"] == pytest.approx(truth["k"], rel=0.03)
    assert got["a_rstar"] == pytest.approx(truth["a_rstar"], rel=0.10)
    assert got["b"] == pytest.approx(truth["b"], abs=0.08)
    assert chi2 / (t.size - 6) == pytest.approx(1.0, abs=0.15)


def test_injection_recovery_gets_the_depth_right():
    """The observable, not the parameter. Depth is what the package quotes."""
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model, curves = _inject(truth, noise_ppm=400.0, seed=11)
    true_depth = refit.transit_depth_ppm(model, truth["period"], truth["k"],
                                         truth["a_rstar"], truth["b"])
    guess = (truth["period"] + 3e-5, truth["epoch"] + 4e-3, 0.38, 6.4, 0.75)
    got, *_ = _fit(model, curves, guess)
    depth = refit.transit_depth_ppm(model, got["period"], got["k"],
                                    got["a_rstar"], got["b"])
    assert depth == pytest.approx(true_depth, rel=0.01)


def test_injection_recovery_grazing_keeps_ephemeris_and_depth():
    """SPOC's geometry. k is NOT asserted — the degeneracy is the finding."""
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.430, "a_rstar": 7.710, "b": 0.900}
    model, curves = _inject(truth, noise_ppm=600.0, seed=13)
    true_depth = refit.transit_depth_ppm(model, truth["period"], truth["k"],
                                         truth["a_rstar"], truth["b"])
    guess = (truth["period"] + 3e-5, truth["epoch"] + 4e-3, 0.33, 9.0, 0.55)
    got, *_ = _fit(model, curves, guess)
    depth = refit.transit_depth_ppm(model, got["period"], got["k"],
                                    got["a_rstar"], got["b"])
    assert got["period"] == pytest.approx(truth["period"], abs=2e-5)
    assert got["epoch"] == pytest.approx(truth["epoch"], abs=2e-3)
    assert depth == pytest.approx(true_depth, rel=0.03)
    assert got["b"] > 1.0 - got["k"] - 0.10, "the grazing geometry was lost"


def test_bootstrap_errors_are_nonzero_and_bracket_the_truth():
    """A zero error bar is what a silently-stuck optimiser looks like."""
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model, curves = _inject(truth, noise_ppm=600.0, seed=17)
    guess = (truth["period"] + 2e-5, truth["epoch"] + 2e-3, 0.34, 6.8, 0.65)
    got, best, _, (t, f, w), _, n_ld = _fit(model, curves, guess)
    draws, errs = refit.bootstrap_errors(t, f, w, model, best, n_ld,
                                         n_boot=12, seed=99, maxiter=400)
    assert draws.shape[0] == 12
    assert np.all(errs[:5] > 0)
    for i, name in enumerate(refit.PARAM_NAMES):
        pull = abs(got[name] - truth[name]) / errs[i]
        assert pull < 6.0, f"{name} is {pull:.1f} sigma from truth"


def test_prayerbead_errors_run_and_are_not_smaller_than_nothing():
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model, curves = _inject(truth, noise_ppm=600.0, seed=23)
    guess = (truth["period"], truth["epoch"], 0.30, 7.7, 0.45)
    _, best, _, (t, f, w), _, n_ld = _fit(model, curves, guess, restarts=1)
    _, errs = refit.bootstrap_errors(t, f, w, model, best, n_ld, n_boot=8,
                                     seed=5, maxiter=300, method="prayerbead")
    assert np.all(np.isfinite(errs[:5]))
    assert np.all(errs[:5] > 0)


# ------------------------------------------------------------- housekeeping --


def test_detrending_does_not_eat_the_transit():
    """A per-window baseline must leave the injected depth alone.

    The failure this guards is the classic one: a filter that is not told where
    the transit is flattens it away and the fit comes back shallow. Injected
    depth in, same depth out of ``window_and_detrend``, to 1 %.
    """
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model, curves = _inject(truth, noise_ppm=50.0, seed=31)
    true_depth = refit.transit_depth_ppm(model, truth["period"], truth["k"],
                                         truth["a_rstar"], truth["b"]) * 1e-6
    t, f, e, nwin = refit.window_and_detrend(
        curves, truth["period"], truth["epoch"],
        refit.transit_durations(truth["period"], truth["k"],
                                truth["a_rstar"], truth["b"])[0])
    phase = np.abs(np.mod(t - truth["epoch"] + 0.5 * truth["period"],
                          truth["period"]) - 0.5 * truth["period"])
    core = phase < 0.25 / 24.0
    assert core.sum() > 50
    measured = 1.0 - float(np.mean(f[core]))
    assert measured == pytest.approx(true_depth, rel=0.01)


def test_window_and_detrend_refuses_when_there_is_nothing_to_window():
    """It must raise, not return an empty fit that looks like a null result."""
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    _, curves = _inject(truth, noise_ppm=300.0, seed=37)
    thin = [{"t": c["t"][:8], "f": c["f"][:8], "ferr": c["ferr"][:8],
             "source": "thin"} for c in curves]
    with pytest.raises(refit.RefitError):
        refit.window_and_detrend(thin, truth["period"], truth["epoch"], 2.15)


def test_a_wrong_epoch_is_NOT_detected_and_this_is_the_documented_limit():
    """Pinning a limitation, not a feature.

    Windows are laid down at epoch + n·P across the whole time series, so an
    epoch wrong by half a period produces the same *number* of perfectly
    well-formed windows — they just contain no transit. ``window_and_detrend``
    cannot tell and does not claim to; the fit downstream is what fails, by
    driving k to its lower bound on flat baseline.

    This test exists so that if someone later adds a real epoch check, they
    have to come here and delete a test that says there isn't one, rather than
    discovering the gap from a published number.
    """
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    _, curves = _inject(truth, noise_ppm=300.0, seed=37)
    t, f, _e, nwin = refit.window_and_detrend(
        curves, truth["period"], truth["epoch"] + 0.5 * truth["period"], 2.15)
    assert nwin > 30, "it happily produced windows"
    centre = np.abs(np.mod(t - (truth["epoch"] + 0.5 * truth["period"])
                           + 0.5 * truth["period"], truth["period"])
                    - 0.5 * truth["period"]) < 0.25 / 24.0
    assert float(np.mean(f[centre])) == pytest.approx(1.0, abs=2e-3), (
        "the mis-phased windows are flat baseline, as expected")


def test_fit_refuses_an_out_of_bounds_starting_guess():
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model, curves = _inject(truth, noise_ppm=300.0, seed=41)
    t14 = refit.transit_durations(truth["period"], truth["k"],
                                  truth["a_rstar"], truth["b"])[0]
    t, f, e, _ = refit.window_and_detrend(curves, truth["period"],
                                          truth["epoch"], t14)
    w, _ = refit.weights_from(f, e)
    with pytest.raises(refit.RefitError):
        refit.fit_transit(t, f, w, model, (truth["period"], truth["epoch"],
                                           1.5, 7.7, 0.45))


def test_summary_renders_without_a_network():
    """The reporting path is code too, and it runs on every real invocation."""
    import io
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model, curves = _inject(truth, noise_ppm=600.0, seed=43)
    guess = (truth["period"], truth["epoch"], 0.30, 7.7, 0.45)
    _, best, chi2, (t, f, w), nwin, n_ld = _fit(model, curves, guess, restarts=1)
    star = refit.stellar_parameters(11.7285, 0.025, 4.47, 0.03, n_mc=2000)
    errs = np.array([1e-6, 1e-4, 1e-3, 0.05, 0.02])
    fit = refit.summarise(best, errs, n_ld, model, star, chi2=chi2, ndata=t.size)
    buf = io.StringIO()
    refit.print_summary(fit, star, out=buf)
    text = buf.getvalue()
    for needle in ("Mann+2015", "lab trapezoid", "SPOC DV", "this refit",
                   "DENSITY CROSS-CHECK", "planet candidate", "rho_sun"):
        assert needle in text, f"summary is missing {needle!r}"
    assert "g/cm^3" in text and "rho_sun" in text, "densities lack both units"


def _fits_card(key, value):
    if isinstance(value, bool):
        body = f"{'T' if value else 'F':>20}"
    elif isinstance(value, int):
        body = f"{value:>20}"
    else:
        body = f"'{value:<8}'" if len(str(value)) <= 8 else f"'{value}'"
    return f"{key:<8}= {body:<70}"[:80].ljust(80)


def _write_minimal_tess_fits(path, t, f, ferr, quality):
    """A SPOC-shaped light-curve FITS, written by hand.

    Only enough of the standard to be read: a null primary HDU and a BINTABLE
    with the four columns ``lab.a01.read_tess_light_curve`` requires. Writing
    it here rather than committing a real 4 MB TESS file keeps the offline path
    — the one Ben uses with ``--fits-dir`` — under test without a fixture that
    nobody can regenerate.
    """
    primary = "".join([_fits_card("SIMPLE", True), _fits_card("BITPIX", 8),
                       _fits_card("NAXIS", 0), _fits_card("EXTEND", True),
                       "END".ljust(80)])
    primary += " " * ((2880 - len(primary) % 2880) % 2880)

    row = np.dtype([("TIME", ">f8"), ("PDCSAP_FLUX", ">f4"),
                    ("PDCSAP_FLUX_ERR", ">f4"), ("QUALITY", ">i4")])
    rows = np.zeros(len(t), dtype=row)
    rows["TIME"] = t
    rows["PDCSAP_FLUX"] = f
    rows["PDCSAP_FLUX_ERR"] = ferr
    rows["QUALITY"] = quality

    cards = [_fits_card("XTENSION", "BINTABLE"), _fits_card("BITPIX", 8),
             _fits_card("NAXIS", 2), _fits_card("NAXIS1", row.itemsize),
             _fits_card("NAXIS2", len(t)), _fits_card("PCOUNT", 0),
             _fits_card("GCOUNT", 1), _fits_card("TFIELDS", 4)]
    for i, (name, form) in enumerate(
            [("TIME", "D"), ("PDCSAP_FLUX", "E"),
             ("PDCSAP_FLUX_ERR", "E"), ("QUALITY", "J")], start=1):
        cards += [_fits_card(f"TTYPE{i}", name), _fits_card(f"TFORM{i}", form)]
    header = "".join(cards) + "END".ljust(80)
    header += " " * ((2880 - len(header) % 2880) % 2880)

    data = rows.tobytes()
    data += b"\0" * ((2880 - len(data) % 2880) % 2880)
    Path(path).write_bytes(primary.encode("ascii") + header.encode("ascii") + data)


def test_fits_dir_path_reads_and_fits_a_synthetic_file(tmp_path):
    """The offline route, end to end: FITS on disk -> windows -> fit.

    This is the path that runs on Ben's machine when MAST is unreachable, and
    it is the one no amount of selftest exercises, because the selftest hands
    arrays straight to the fitter. It also pins the column names: the lab's
    reader returns FITS TTYPEs verbatim ("TIME", "PDCSAP_FLUX"), and reaching
    for lower-case aliases silently routed this into the astropy fallback.
    """
    truth = {"period": 1.9369484, "epoch": 2036.5479415,
             "k": 0.300, "a_rstar": 7.700, "b": 0.450}
    model = refit.TransitModel("nonlinear", refit.CLARET_TESS, backend="numpy")
    rng = np.random.default_rng(3)
    for sector, start in enumerate((2036.0, 2065.0), start=30):
        t = np.arange(start, start + 24.0, 10.0 / 1440.0)
        clean = model(t, truth["epoch"], truth["period"], truth["k"],
                      truth["a_rstar"], truth["b"])
        flux = 1234.0 * (clean + rng.normal(0.0, 3e-4, t.size))
        qual = np.zeros(t.size, dtype=int)
        qual[::97] = 128                     # some flagged cadences to drop
        _write_minimal_tess_fits(
            tmp_path / f"tess-s00{sector}-0000000374861595-s_lc.fits",
            t, flux, np.full(t.size, 1234.0 * 3e-4), qual)

    curves = refit.load_from_dir(tmp_path)
    assert len(curves) == 2
    for c in curves:
        assert np.all(np.isfinite(c["t"])) and np.all(np.isfinite(c["f"]))
        assert float(np.median(c["f"])) == pytest.approx(1.0, abs=1e-3), (
            "flux was not normalised by its median")
        assert c["t"].size < 24 * 144, "flagged cadences were not dropped"

    guess = (truth["period"] + 2e-5, truth["epoch"] + 2e-3, 0.36, 6.6, 0.70)
    got, *_ = _fit(model, curves, guess)
    assert got["period"] == pytest.approx(truth["period"], abs=5e-5)
    assert got["k"] == pytest.approx(truth["k"], rel=0.05)


def test_load_from_dir_refuses_an_empty_directory(tmp_path):
    with pytest.raises(refit.RefitError):
        refit.load_from_dir(tmp_path)


def test_error_formatting_stays_readable():
    """Two significant figures, and no exponent where fixed notation fits."""
    assert refit._fmt_err(372.27) == "372"
    assert refit._fmt_err(0.0186475) == "0.019"
    assert refit._fmt_err(0.1119763) == "0.11"
    assert refit._fmt_err(2.4707e-06) == "2.5e-06"
    # %g strips trailing zeros, so the value keeps only its significant digits.
    assert refit._fmt(1.9369093, 2.4707e-06, 10) == "1.9369093 ± 2.5e-06"
    assert refit._fmt(float("nan")) == "—"


def test_no_network_import_at_module_level():
    """Importing the script must not reach for lightkurve, astropy or MAST.

    ``--selftest`` promises 'no network'. The cheapest way to break that
    promise is a top-level import that phones home on first use.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    head = source.split("class RefitError", 1)[0]
    for banned in ("import lightkurve", "from astropy", "import astropy",
                   "import requests", "import urllib"):
        assert banned not in head, f"{banned!r} at module level"


def test_selftest_exits_zero():
    """The script's own gate, run as the script runs it. Slow but load-bearing."""
    assert refit.selftest(verbose=False) == 0


# --- the joint posterior (2026-09-19) ---------------------------------------
#
# The 2026-09-18 run wrote 16/50/84 marginals and dropped the chain, which is
# the one thing §6.4 of the survey paper cannot argue from: its claim is that
# k and b lie on a correlated ridge, and a marginal is that ridge's shadow on
# one axis. These cover `joint_summary`, the block that fixes it.

def _valley_chain(n=4000, seed=7):
    """A synthetic posterior with a deliberate k-b ridge and known fractions."""
    import numpy as _np
    rng = _np.random.default_rng(seed)
    k = rng.normal(0.54, 0.10, n)
    b = 0.55 + 0.92 * k + rng.normal(0, 0.03, n)
    return _np.column_stack([
        _np.full(n, 1.9369), _np.full(n, 2036.5), k, 7.8 + 2 * (k - 0.54), b])


def test_joint_summary_recovers_a_planted_correlation():
    import numpy as _np
    chain = _valley_chain()
    j = refit.joint_summary(chain)
    ik = j["parameters"].index("k")
    ib = j["parameters"].index("b")
    planted = float(_np.corrcoef(chain[:, ik], chain[:, ib])[0, 1])
    assert j["k_b"]["correlation"] == pytest.approx(planted, abs=1e-9)
    assert j["correlation"][ik][ib] == pytest.approx(planted, abs=1e-9)
    assert j["k_b"]["correlation"] > 0.9, "a planted ridge must read as a ridge"


def test_joint_density_is_normalised_and_gridded():
    j = refit.joint_summary(_valley_chain(), nbins=25)
    density = j["k_b"]["density"]
    assert len(density) == 25 and all(len(row) == 25 for row in density)
    assert len(j["k_b"]["k_edges"]) == 26
    assert sum(map(sum, density)) == pytest.approx(1.0, abs=1e-9)


def test_joint_reports_the_two_physical_fractions():
    """b > 1 is odd geometry; b > 1 + k is no transit at all. The second is the
    one that indicts the sampler rather than the star, so it is reported
    separately and must be zero for a well-behaved planted posterior."""
    import numpy as _np
    chain = _valley_chain()
    k, b = chain[:, 2], chain[:, 4]
    j = refit.joint_summary(chain)
    assert j["k_b"]["fraction_b_above_1"] == pytest.approx(float(_np.mean(b > 1)))
    assert j["k_b"]["fraction_no_overlap_b_above_1_plus_k"] == 0.0


def test_joint_summary_declines_rather_than_raises_on_a_useless_chain():
    """An error method that produced no samples should cost the run its joint
    block, never its receipt."""
    import numpy as _np
    assert refit.joint_summary(_np.zeros((1, 5))) is None
    assert refit.joint_summary(_np.zeros((0, 5))) is None
    assert refit.joint_summary(_np.zeros(5)) is None


def test_chain_flag_is_offered():
    parser = refit.build_parser()
    args = parser.parse_args(["--chain", "c.npz"])
    assert str(args.chain) == "c.npz"
    assert parser.parse_args([]).chain is None
# --- sector_coverage ---------------------------------------------------------
# Added 2026-09-19. The 2026-09-18 run reported "24 sectors (27-97)" and no
# artifact recorded which 24: the range was typed from the product count, and
# arithmetic on the DV baseline does not support its top end. These pin the
# derived replacement, including the degenerate cases that would otherwise let
# a wrong list look authoritative.

def _curves(*sources):
    return [{"source": s} for s in sources]


def test_sector_coverage_sorts_and_counts():
    cov = refit.sector_coverage(_curves("sector 35", "sector 27", "sector 96"))
    assert cov["sectors"] == [27, 35, 96]
    assert (cov["lowest"], cov["highest"]) == (27, 96)
    assert cov["unknown"] == 0
    assert cov["n_curves"] == 3


def test_sector_coverage_collapses_duplicates():
    cov = refit.sector_coverage(_curves("sector 27", "sector 27"))
    assert cov["sectors"] == [27]
    assert cov["n_curves"] == 2, "n_curves counts products, not distinct sectors"


def test_sector_coverage_flags_unidentified_products():
    # A curve with no SECTOR keyword must be counted, not silently dropped --
    # otherwise the printed list is short and nothing says so.
    cov = refit.sector_coverage(_curves("sector 27", "lightkurve", "sector 28"))
    assert cov["sectors"] == [27, 28]
    assert cov["unknown"] == 1
    assert cov["n_curves"] == 3


def test_sector_coverage_survives_nothing_identified():
    cov = refit.sector_coverage(_curves("lightkurve"))
    assert cov["sectors"] == []
    assert cov["lowest"] is None and cov["highest"] is None
    assert cov["unknown"] == 1


def test_sector_coverage_does_not_invent_a_range():
    # The defect this replaces: 24 products summarised as the range "27-97",
    # which silently asserts sectors that were never observed. The derived list
    # must name only what is there.
    observed = [27, 28, 30, 31, 35, 36, 37, 38, 61, 62, 63, 65, 66, 67, 68, 69,
                87, 88, 89, 90, 93, 94, 96, 98]
    cov = refit.sector_coverage(_curves(*[f"sector {n}" for n in observed]))
    assert cov["sectors"] == observed
    assert len(cov["sectors"]) == 24
    gaps = set(range(cov["lowest"], cov["highest"] + 1)) - set(cov["sectors"])
    assert gaps, "the range form would have claimed these sectors"
    assert 97 in gaps
