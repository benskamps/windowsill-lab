"""A05 fold-gate tests — the P/2 alias gate and the duration-matched depths.

Built from the 2026-08-18 TIC 287328866 refutation. The synthetic binary below
is that star's geometry (P = 2.0765 d, unequal eclipses half a period apart,
detected at the 1.0382 d alias); the synthetic planet is the negative control
that must survive the same gate untouched, because a gate that cannot be made
to stay quiet is not a gate, it is a verdict.

Every threshold is exercised from BOTH sides: a depth difference below the bar
must not fire, and a dip too weak to measure must report a reason instead of a
number.
"""
from __future__ import annotations

import numpy as np
import pytest

from lab import a04, a05_fold as fold
from lab.a04 import Detection


CADENCE = 2.0 / 1440          # 2-minute TESS cadence, in days
BASELINE_DAYS = 27.0          # one sector


def _flat(noise=3e-4, seed=11, days=BASELINE_DAYS):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, CADENCE)
    return t, 1.0 + rng.normal(0.0, noise, size=len(t))


def _box(t, f, period, depth, t0, duration_days):
    ph = np.mod(t - t0 + 0.5 * period, period) - 0.5 * period
    out = f.copy()
    out[np.abs(ph) < duration_days / 2] *= (1.0 - depth)
    return out


def _trapezoid(t, f, period, depth, t0, duration_days, ingress_frac=0.3):
    """A shaped eclipse: flat bottom with linear ingress/egress.

    Real eclipses are not boxes, and the difference is exactly what breaks a
    median taken over a window wider than the event: the median lands partway
    down the ingress instead of on the floor. Every dilution test below needs
    this shape — a box would give a step function (median = baseline or median
    = floor, nothing between) and would hide the seam it is meant to show.
    """
    ph = np.mod(t - t0 + 0.5 * period, period) - 0.5 * period
    half = duration_days / 2
    ramp = max(ingress_frac * duration_days, 1e-9)
    x = np.clip((half - np.abs(ph)) / ramp, 0.0, 1.0)
    return f * (1.0 - depth * x)


def _binary(depth_primary=0.021, depth_secondary=0.0166,
            p_bin=2.0765, duration=0.08, noise=3e-4, seed=11):
    """An EB whose primary and secondary are half a period apart.

    Returns (t, f, detection-at-the-P/2-alias). The detection is constructed,
    not searched: these tests grade the GATE, and a blind search that failed to
    land on the alias would silently turn a gate test into a search test.
    """
    t, f = _flat(noise=noise, seed=seed)
    p_det = p_bin / 2.0
    t0 = 0.37 * p_det
    f = _box(t, f, p_bin, depth_primary, t0, duration)
    f = _box(t, f, p_bin, depth_secondary, t0 + p_bin / 2.0, duration)
    det = Detection(period_days=p_det,
                    depth=0.5 * (depth_primary + depth_secondary),
                    phase=(t0 % p_det) / p_det, sde=9.0)
    return t, f, det


def _planet(depth=0.012, period=2.0765, duration=0.08, noise=3e-4, seed=12):
    """A real transiting planet at ``period`` — equal depths at every epoch."""
    t, f = _flat(noise=noise, seed=seed)
    t0 = 0.37 * period
    f = _box(t, f, period, depth, t0, duration)
    det = Detection(period_days=period, depth=depth,
                    phase=(t0 % period) / period, sde=9.0)
    return t, f, det


# ------------------------------------------------------------- measure_dip ---

def test_measure_dip_recovers_a_known_box_depth():
    t, f, det = _planet(depth=0.012)
    dip = fold.measure_dip(t, f, det.period_days, det.phase,
                           fold.MEASURE_WINDOW_PHASE)
    assert dip["depth"] == pytest.approx(0.012, rel=0.06)
    assert dip["depth_sigma"] > 20
    assert dip["n_in"] >= fold.MIN_DIP_CADENCES


def test_measure_dip_recovers_the_duration_not_the_window():
    """The support must track the eclipse, not the window it was found in."""
    t, f, det = _planet(depth=0.012, duration=0.08)
    dip = fold.measure_dip(t, f, det.period_days, det.phase,
                           fold.MEASURE_WINDOW_PHASE)
    expected_phase = 0.08 / det.period_days
    assert dip["duration_phase"] == pytest.approx(expected_phase, rel=0.35)
    assert dip["duration_phase"] < 2 * fold.MEASURE_WINDOW_PHASE
    assert dip["edge_limited"] is False


def test_measure_dip_reports_a_bump_as_negative_depth():
    """'Nothing there' and 'the opposite of an eclipse' must not look alike."""
    t, f = _flat(seed=21)
    f = _box(t, f, 2.0, -0.01, 0.74, 0.08)          # negative depth = brightening
    dip = fold.measure_dip(t, f, 2.0, 0.37, fold.MEASURE_WINDOW_PHASE)
    assert dip["depth"] < 0
    assert dip["reason"] == "no-dip"


def test_measure_dip_refuses_when_there_are_too_few_cadences():
    t = np.linspace(0.0, 1.0, 40)
    f = np.ones_like(t)
    dip = fold.measure_dip(t, f, 2.0, 0.5, 0.001)
    assert dip["depth"] is None
    assert dip["reason"] == "insufficient-cadences"


def test_measure_dip_baseline_is_local_and_survives_a_slow_trend():
    """A ramp across the sector must not be read as depth."""
    t, f, det = _planet(depth=0.012)
    f = f * (1.0 + 0.02 * (t - t.mean()) / (t.max() - t.min()))
    dip = fold.measure_dip(t, f, det.period_days, det.phase,
                           fold.MEASURE_WINDOW_PHASE)
    assert dip["depth"] == pytest.approx(0.012, rel=0.10)


# ----------------------------------------------------------------- p2_fold ---

def test_p2_fold_fires_on_the_unequal_eclipse_binary():
    t, f, det = _binary()
    out = fold.p2_fold(t, f, det)
    assert out["verdict"] == "eclipsing-binary-p2-alias"
    assert out["both_eclipses_significant"] is True
    assert out["depth_ratio"] > 1.0
    assert out["difference_sigma"] >= fold.P2_ALIAS_SIGMA
    assert out["period_2p_days"] == pytest.approx(2.0765, rel=1e-9)


def test_p2_fold_measures_both_eclipse_depths():
    t, f, det = _binary(depth_primary=0.021, depth_secondary=0.0166)
    out = fold.p2_fold(t, f, det)
    assert out["eclipse_a"]["depth"] == pytest.approx(0.021, rel=0.08)
    assert out["eclipse_b"]["depth"] == pytest.approx(0.0166, rel=0.08)


def test_p2_fold_stays_quiet_on_a_real_planet():
    """THE negative control. Both dips are the same transit; nothing to find."""
    t, f, det = _planet()
    out = fold.p2_fold(t, f, det)
    assert out["verdict"] is None
    assert out["both_eclipses_significant"] is True     # both dips ARE real
    assert out["difference_sigma"] < fold.P2_ALIAS_SIGMA


def test_p2_fold_stays_quiet_on_a_planet_across_seeds_and_depths():
    """A one-seed negative control proves nothing about a 5-sigma bar."""
    for seed in range(12, 20):
        for depth in (0.006, 0.012, 0.02):
            t, f, det = _planet(depth=depth, seed=seed)
            out = fold.p2_fold(t, f, det)
            assert out["verdict"] is None, f"fired on planet seed={seed} d={depth}"


def test_p2_fold_needs_both_eclipses_before_it_will_grade_a_difference():
    """One real dip plus one noise excursion must never refute a candidate."""
    t, f = _flat(seed=31)
    p_bin, p_det = 2.0765, 1.03825
    t0 = 0.37 * p_det
    f = _box(t, f, p_bin, 0.02, t0, 0.08)              # primary only, no secondary
    det = Detection(period_days=p_det, depth=0.01,
                    phase=(t0 % p_det) / p_det, sde=9.0)
    out = fold.p2_fold(t, f, det)
    assert out["both_eclipses_significant"] is False
    assert out["verdict"] is None


def test_p2_fold_verdict_tracks_its_own_threshold_across_a_sweep():
    """The verdict must be a function of the measured sigma, at the stated bar.

    Swept rather than spot-checked: a two-point test can pass while the gate
    fires on the wrong quantity. Depths here run from identical to 20 % apart,
    and the only thing asserted is that verdict and difference_sigma never
    disagree about P2_ALIAS_SIGMA.
    """
    seen_both = set()
    for d2 in (0.0210, 0.02098, 0.02090, 0.0207, 0.0200, 0.0166):
        out = fold.p2_fold(*_binary(depth_primary=0.0210, depth_secondary=d2))
        fired = out["verdict"] == "eclipsing-binary-p2-alias"
        over = (out["difference_sigma"] >= fold.P2_ALIAS_SIGMA
                and out["both_eclipses_significant"])
        assert fired == over, (d2, out["difference_sigma"], out["verdict"])
        seen_both.add(fired)
    assert seen_both == {True, False}, "sweep never crossed the threshold"


# ------------------------------------------------------------ odd_even_fold ---

def _shaped_binary(depth_primary=0.021, depth_secondary=0.0166,
                   p_bin=2.0765, duration=0.035, seed=11):
    """A binary whose SHAPED eclipses are narrower than A04's vetting window.

    ±VET_WINDOW_PHASE at the detected 1.038 d period spans 0.065 d; these
    eclipses last 0.035 d. That is the regime where a median over the fixed
    window stops measuring the eclipse floor and starts measuring the ingress.
    """
    t, f = _flat(seed=seed)
    p_det = p_bin / 2.0
    t0 = 0.37 * p_det
    f = _trapezoid(t, f, p_bin, depth_primary, t0, duration)
    f = _trapezoid(t, f, p_bin, depth_secondary, t0 + p_bin / 2.0, duration)
    det = Detection(period_days=p_det,
                    depth=0.5 * (depth_primary + depth_secondary),
                    phase=(t0 % p_det) / p_det, sde=9.0)
    return t, f, det


def test_the_fixed_window_median_under_measures_a_narrow_shaped_eclipse():
    """The seam itself: A04's estimator, on a shaped eclipse, reads low."""
    t, f, det = _shaped_binary(depth_primary=0.021, depth_secondary=0.0166)
    ref = fold.windowed_odd_even(t, f, det)
    deep = max(ref["depth_odd"], ref["depth_even"])
    assert deep < 0.8 * 0.021, "fixture does not reproduce the dilution"


def test_duration_matched_depths_recover_what_the_window_median_loses():
    """Same star, same fold: the support-matched estimator gets the truth back."""
    t, f, det = _shaped_binary(depth_primary=0.021, depth_secondary=0.0166)
    gate = fold.fold_gate(t, f, det)
    oe, ref = gate["odd_even_fold"], gate["windowed_reference"]
    measured = sorted([oe["depth_odd"]["depth"], oe["depth_even"]["depth"]])
    # The trapezoid's mean depth over its own half-depth support is below the
    # floor depth by construction, so the bar is "closer than the window
    # median", not "exact".
    assert measured[1] > max(ref["depth_odd"], ref["depth_even"])
    assert abs(oe["difference"]) > abs(ref["difference"])
    assert gate["dilution"] > 1.3


def test_the_p2_gate_fires_on_the_shaped_binary_the_old_estimator_missed():
    """End to end: the star A04 would have shelved is refuted by the fold."""
    t, f, det = _shaped_binary()
    assert fold.fold_gate(t, f, det)["verdict"] == "eclipsing-binary-p2-alias"


def test_odd_even_fold_is_quiet_on_a_planet():
    t, f, det = _planet()
    out = fold.odd_even_fold(t, f, det)
    assert out["verdict"] is None
    assert abs(out["difference_sigma"]) < a04.ODD_EVEN_SIGMA


# ------------------------------------------------------------------ fold_gate ---

def test_fold_gate_prefers_the_p2_verdict_over_the_odd_even_one():
    """One geometry, one finding — the odd-even split is its consequence."""
    t, f, det = _binary()
    gate = fold.fold_gate(t, f, det)
    assert gate["verdict"] == "eclipsing-binary-p2-alias"
    assert gate["odd_even_fold"]["verdict"] == "eclipsing-binary-odd-even"


def test_fold_gate_returns_none_for_a_planet_and_says_nothing_more():
    t, f, det = _planet()
    gate = fold.fold_gate(t, f, det)
    assert gate["verdict"] is None
    assert set(gate) == {"verdict", "p2_fold", "odd_even_fold",
                         "windowed_reference", "dilution"}


def test_fold_gate_verdicts_are_in_the_machine_vocabulary():
    from lab import a05
    t, f, det = _binary()
    assert fold.fold_gate(t, f, det)["verdict"] in a05.MACHINE_DISPOSITIONS


# ------------------------------------------------------- the noise controls ---

def test_measure_dip_does_not_manufacture_depth_from_pure_noise():
    """The selection-bias control.

    An estimator that started its support at the DEEPEST bin in the window
    would pick the best of DIP_BINS noise excursions every time and report a
    biased-positive depth with a white-noise error bar that knows nothing about
    the search. Growing from the centre bin instead makes the measurement
    unbiased — so on flat noise, at arbitrary phases, the significance has to
    stay small and scatter around zero.
    """
    sigmas = []
    for seed in range(40, 60):
        t, f = _flat(seed=seed)
        dip = fold.measure_dip(t, f, 2.0765, 0.37, fold.MEASURE_WINDOW_PHASE)
        if dip["depth_sigma"] is not None:
            sigmas.append(dip["depth_sigma"])
    assert len(sigmas) >= 15
    assert max(sigmas) < fold.MIN_ECLIPSE_SIGMA, f"noise cleared the bar: {max(sigmas)}"
    assert abs(float(np.mean(sigmas))) < 1.5, "estimator is biased on pure noise"


def test_the_gates_never_fire_on_pure_noise():
    """No flat curve may be refuted — there is nothing there to refute."""
    for seed in range(60, 75):
        t, f = _flat(seed=seed)
        det = Detection(period_days=1.03825, depth=1e-3, phase=0.37, sde=9.0)
        assert fold.fold_gate(t, f, det)["verdict"] is None


# ------------------------------------------- why the 2P fold, not odd/even ---

def _straddling_binary(depth_primary=0.021, depth_secondary=0.0166,
                       p_bin=2.0765, duration=0.05, seed=11):
    """A binary whose eclipses sit ON A04's epoch boundary.

    A04 counts epochs as ``floor((t - t[0]) / P)``, which puts the boundary at
    whatever phase the first cadence happens to occupy — here, phase 0. Put the
    eclipses there and each one is split across both parities, so both parities
    hold half a primary and half a secondary and the alternation averages away.
    Nothing about the star changed; only where the counting started. TIC
    287328866 sector 3 is the live case: the two conventions disagree about the
    SIGN of the odd-even difference, which is what proves it is a labelling
    artifact rather than a measurement.
    """
    t, f = _flat(seed=seed)
    p_det = p_bin / 2.0
    t0 = 0.002 * p_det              # transit centre lands on the epoch boundary
    f = _trapezoid(t, f, p_bin, depth_primary, t0, duration)
    f = _trapezoid(t, f, p_bin, depth_secondary, t0 + p_bin / 2.0, duration)
    det = Detection(period_days=p_det,
                    depth=0.5 * (depth_primary + depth_secondary),
                    phase=(t0 % p_det) / p_det, sde=9.0)
    return t, f, det


def test_a04s_epoch_convention_loses_the_alternation_at_the_boundary():
    """The reference estimator, on the straddling geometry: nothing to see."""
    t, f, det = _straddling_binary()
    ref = fold.windowed_odd_even(t, f, det)
    assert abs(ref["difference"]) < 0.2 * (0.021 - 0.0166)


def test_the_centred_epoch_recovers_the_alternation_a04_averaged_away():
    """Same curve, boundary moved off the transit: the difference comes back."""
    t, f, det = _straddling_binary()
    oe = fold.odd_even_fold(t, f, det)
    ref = fold.windowed_odd_even(t, f, det)
    assert abs(oe["difference"]) > 3 * abs(ref["difference"])
    assert oe["verdict"] == "eclipsing-binary-odd-even"


def test_the_2p_fold_also_survives_the_boundary_case():
    """The phase-assigned gate never had a counting scheme to get wrong."""
    t, f, det = _straddling_binary()
    assert fold.p2_fold(t, f, det)["verdict"] == "eclipsing-binary-p2-alias"


def test_the_2p_fold_does_not_depend_on_where_the_epoch_count_starts():
    """A verdict that moves when you re-origin the clock is a labelling artifact.

    Trimming cadences off the front shifts ``t[0]`` and therefore every A04
    epoch index. The 2P fold's numbers must not move.
    """
    t, f, det = _binary()
    full = fold.p2_fold(t, f, det)
    shifted = fold.p2_fold(t[137:], f[137:], det)
    assert full["verdict"] == shifted["verdict"]
    assert full["difference_sigma"] == pytest.approx(
        shifted["difference_sigma"], rel=0.10)


def test_the_centred_odd_even_is_also_origin_independent():
    t, f, det = _straddling_binary()
    a = fold.odd_even_fold(t, f, det)
    b = fold.odd_even_fold(t[137:], f[137:], det)
    assert abs(a["difference"]) == pytest.approx(abs(b["difference"]), rel=0.15)


# ------------------------------------------------- combining across sectors ---

def _fold_dict(diff, sigma, both=True):
    half = sigma / np.sqrt(2)
    return {"depth_difference": diff, "difference_sigma": diff / sigma,
            "both_eclipses_significant": both,
            "eclipse_a": {"sigma": half, "depth": 0.02, "depth_sigma": 50},
            "eclipse_b": {"sigma": half, "depth": 0.02 - diff, "depth_sigma": 50}}


def test_combining_sectors_clears_a_bar_no_single_sector_clears():
    """The TIC 287328866 shape: consistent, individually sub-threshold."""
    folds = [_fold_dict(0.0016, 0.00046) for _ in range(6)]
    assert all(f["difference_sigma"] < fold.P2_ALIAS_SIGMA for f in folds)
    out = fold.combine_p2_folds(folds)
    assert out["verdict"] == "eclipsing-binary-p2-alias"
    assert out["difference_sigma"] > fold.P2_ALIAS_SIGMA
    assert out["n_sectors"] == 6


def test_combining_refuses_when_the_sign_disagrees():
    """Differences that flip sign are noise; combining must not launder them."""
    folds = [_fold_dict(+0.0016, 0.00046), _fold_dict(-0.0016, 0.00046),
             _fold_dict(+0.0016, 0.00046), _fold_dict(+0.0030, 0.00046)]
    out = fold.combine_p2_folds(folds)
    assert out["sign_consistent"] is False
    assert out["verdict"] is None


def test_combining_needs_more_than_one_sector():
    out = fold.combine_p2_folds([_fold_dict(0.004, 0.0002)])
    assert out["verdict"] is None
    assert out["reason"] == "insufficient-sectors"


def test_combining_ignores_sectors_whose_eclipses_were_not_significant():
    good = [_fold_dict(0.0016, 0.00046) for _ in range(6)]
    junk = [_fold_dict(0.02, 0.00001, both=False) for _ in range(3)]
    out = fold.combine_p2_folds(good + junk)
    assert out["n_sectors"] == 6
    assert out["difference"] == pytest.approx(0.0016, rel=1e-6)


def test_combining_pure_noise_across_many_sectors_stays_quiet():
    """Twenty sectors of nothing must not accumulate into a verdict."""
    rng = np.random.default_rng(7)
    for _ in range(20):
        sig = 0.0004
        folds = [_fold_dict(float(rng.normal(0.0, sig)), sig) for _ in range(8)]
        out = fold.combine_p2_folds(folds)
        # Sign consistency across 8 zero-mean draws is rare; when it happens the
        # combined significance must still be small.
        assert out["verdict"] is None or out["difference_sigma"] < fold.P2_ALIAS_SIGMA
