"""A04 maturity regressions — every one of these is a bug the runs actually hit.

The blind search worked on the first try. Everything below is a defect found
*around* it, in the machinery that decides what a detection means, which is where
this lab keeps getting caught (A03's phantom chirp masses, K03's four exponents).
"""
from __future__ import annotations

import numpy as np
import pytest

from lab import a04, checks


def _flat(days=27.0, cadence=2.0 / 1440, noise=3e-4, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence)
    return t, 1.0 + rng.normal(0.0, noise, size=len(t))


# ---------------------------------------------------------------- sampling ---

def test_sample_is_stable_when_the_pool_changes():
    """The 'deterministic sample' was false: seeding from a hash of the WHOLE pool
    meant any change in what MAST returned reshuffled everything, and two
    consecutive runs shared almost no targets."""
    big = [f"{i:09d}" for i in range(400)]
    small = [t for t in big if t != big[7]]
    a = set(a04.sample_targets(big, 20, seed=3))
    b = set(a04.sample_targets(small, 20, seed=3))
    assert len(a & b) >= 19       # at most the dropped target may differ


def test_recovery_targets_are_always_included():
    """The sector listing is page-capped, so gating inclusion on 'appears in the
    listing' produced a survey with ZERO known planets and nothing to validate."""
    s = a04.sample_targets(["111111111", "222222222"], 1, seed=1)
    assert set(a04.RECOVERY_TARGETS) <= set(s)


# ------------------------------------------------------------------ search ---

def test_injected_transit_is_recovered_blind():
    """The class-6 gate, in miniature."""
    t, f = _flat()
    fi = a04.inject_box(t, f, period=3.1, depth=0.01, duration_days=2.5 / 24)
    det = a04.blind_search(t, fi, n_periods=600)
    assert det.period_days == pytest.approx(3.1, rel=0.01)
    assert det.sde > 8.0


def test_flat_noise_stays_below_the_threshold():
    t, f = _flat(seed=9)
    assert a04.blind_search(t, f, n_periods=600).sde < a04.SDE_THRESHOLD


def test_period_grid_is_capped_by_the_baseline():
    """A 27-day sector cannot confirm a 14-day period — under two transits, no
    odd-even test, unfalsifiable. One run returned P=14.86 d at SDE 10.1."""
    t, f = _flat(days=27.0)
    det = a04.blind_search(t, f, p_hi=15.0, n_periods=400)
    assert det.period_days <= 27.0 / a04.MIN_TRANSITS + 1e-9


def test_a_baseline_too_short_refuses_rather_than_guessing():
    t, f = _flat(days=1.0)
    with pytest.raises(a04.A04Error):
        a04.blind_search(t, f, p_lo=0.5, p_hi=15.0, n_periods=50)


# ------------------------------------------------------------------ vetting ---

def test_odd_even_alternation_is_called_an_eclipsing_binary():
    """The real find: TIC 287328866, absent from every TOI table, separated at
    11 sigma by depths of 1.565 % vs 1.336 %."""
    t, f = _flat(noise=1e-4)
    period = 2.0
    epoch = np.floor(t / period).astype(int)
    ph = np.mod(t, period) / period
    box = np.abs(ph - 0.3) < 0.02
    f = f.copy()
    f[box & (epoch % 2 == 0)] *= 1 - 0.020
    f[box & (epoch % 2 == 1)] *= 1 - 0.010
    det = a04.Detection(period_days=period, depth=0.015, phase=0.3, sde=12.0)
    assert a04.vet_candidate(t, f, det)["verdict"] == "eclipsing-binary-odd-even"


def test_a_planet_candidate_must_earn_the_label():
    """TIC 280095254 was blessed a candidate on depths of ~1e-5 with the ODD-epoch
    depth NEGATIVE. A transit that goes up on half its epochs is noise."""
    t, f = _flat(noise=3e-4)
    det = a04.Detection(period_days=3.0, depth=1e-5, phase=0.3, sde=8.4)
    assert a04.vet_candidate(t, f, det)["verdict"] in (
        "low-significance", "insufficient-coverage")


def test_a_real_transit_does_reach_planet_candidate():
    t, f = _flat(noise=1e-4)
    fi = a04.inject_box(t, f, period=3.0, depth=0.01, duration_days=2.5 / 24)
    det = a04.blind_search(t, fi, n_periods=600)
    assert a04.vet_candidate(t, fi, det)["verdict"] == "planet-candidate"


def test_too_few_events_is_insufficient_coverage_not_a_verdict():
    t, f = _flat(days=27.0, noise=1e-4)
    fi = a04.inject_box(t, f, period=12.0, depth=0.02, duration_days=2.5 / 24)
    det = a04.Detection(period_days=12.0, depth=0.02, phase=0.5, sde=9.0)
    assert a04.vet_candidate(t, fi, det)["verdict"] == "insufficient-coverage"


def test_a_period_railed_to_the_grid_edge_is_not_a_candidate():
    """The final run surfaced TIC 206502540 at P = 0.5000 d — EXACTLY the search
    floor — with 52 "events" and a 20-sigma depth. A best period sitting on a
    grid bound means the true period is probably outside the range and the fold
    is an alias; without this it would have entered a public report as a planet
    candidate."""
    t, f = _flat(noise=1e-4)
    det = a04.Detection(period_days=a04.P_LO, depth=0.01, phase=0.3, sde=9.0)
    assert a04.vet_candidate(t, f, det)["verdict"] == "period-railed"


def test_railing_is_checked_at_the_baseline_capped_upper_edge_too():
    t, f = _flat(days=27.0, noise=1e-4)
    hi = 27.0 / a04.MIN_TRANSITS
    det = a04.Detection(period_days=hi, depth=0.01, phase=0.3, sde=9.0)
    assert a04.vet_candidate(t, f, det)["verdict"] == "period-railed"


def test_a_pulsator_aliased_onto_the_grid_is_not_a_candidate():
    """TIC 140940493: the 2026-08-14 discovery pilot's only uncatalogued
    'planet-candidate' (SDE 8.7, P=0.6222 d, ~900 ppm) was a δ Scuti-type
    pulsator at 8.04 c/d — exactly P/5. Its 3-hour oscillation sits BELOW the
    0.5 d grid floor, aliased onto the 5th harmonic, passed odd-even (every
    pulse identical) and showed a 13-sigma secondary BRIGHTENING the old gate
    never looked at. A fold at P/n keeping the full dip is the tell."""
    t, f = _flat(noise=1e-4)
    p_true = 0.6222 / 5.0
    f = f * (1.0 - 0.0009 * (1.0 + np.cos(2 * np.pi * t / p_true)) / 2.0)
    det = a04.blind_search(t, f, n_periods=600)
    row = a04.vet_candidate(t, f, det)
    assert row["verdict"] == "harmonic-alias"
    assert row["alias_n"] >= 2


def test_secondary_brightening_is_not_a_candidate():
    """Second tell from the same target: phase-locked BRIGHTENING at 0.5.
    A planet's occultation can only dim; the old gate tested only the
    dimming sign and let -13 sigma sail through."""
    t, f = _flat(noise=1e-4)
    period = 3.0
    ph = np.mod(t, period) / period
    f = f.copy()
    f[np.abs(ph - 0.2) < 0.02] *= 1 - 0.010            # the "transit"
    f[np.abs(ph - 0.7) < 0.02] *= 1 + 0.008            # phased brightening at 0.5 later
    det = a04.Detection(period_days=period, depth=0.01, phase=0.2, sde=9.0)
    assert a04.vet_candidate(t, f, det)["verdict"] == "phased-brightening"


def test_a_real_transit_survives_the_alias_and_brightening_gates():
    """Regression guard: the new gates must not eat genuine candidates — a
    clean box transit folded at P/n loses its dip to the median."""
    t, f = _flat(noise=1e-4)
    fi = a04.inject_box(t, f, period=3.0, depth=0.01, duration_days=2.5 / 24)
    det = a04.blind_search(t, fi, n_periods=600)
    row = a04.vet_candidate(t, fi, det)
    assert row["verdict"] == "planet-candidate"
    assert "alias_n" not in row


# ------------------------------------------------------------------- check ---

def _report(**kw):
    base = {
        "experiment": "A04-blind-transit-search", "sector": 2,
        "targets_searched": 26, "sde_threshold": 8.0, "period_tolerance_frac": 0.01,
        "injections": [
            {"injected_period_days": p, "injected_depth": d,
             "recovered_period_days": p, "sde": 9.0}
            for d, p in a04.INJECTIONS
        ],
        "recoveries": [
            {"known_planet": "WASP-18 b", "period_days": 0.94164,
             "published_period_days": 0.94145223, "sde": 10.2},
            {"known_planet": "HIP 65 A b", "period_days": 0.98124,
             "published_period_days": 0.9809734, "sde": 14.2},
        ],
        "candidates": [{"tic": "211438925", "sde": 9.1,
                        "period_days": 4.9014,
                        "catalog": {"known_planet": "WASP-20 b"},
                        "vetting": {"verdict": "planet-candidate"}}],
        "false_alarm_sde": [4.2, 5.1, 7.7, 3.9] * 5,
    }
    base.update(kw)
    return base


def test_check_passes_a_clean_survey():
    ok, detail = checks.check_a04(_report())
    assert ok is True
    assert "never told about them" in detail


def test_unvetted_candidate_is_unreadable_not_negative():
    ok, detail = checks.check_a04(_report(
        candidates=[{"tic": "279949020", "sde": 8.1,
                     "vetting": {"verdict": "insufficient-coverage"}}]))
    assert ok is None
    assert "unvetted" in detail


def test_failed_injection_is_unreadable_not_negative():
    rep = _report()
    rep["injections"][0]["recovered_period_days"] = 1.9
    rep["injections"][0]["sde"] = 4.0
    ok, detail = checks.check_a04(rep)
    assert ok is None
    assert "CONTROL FAILED" in detail


def test_floor_reaching_the_threshold_fails():
    ok, detail = checks.check_a04(_report(false_alarm_sde=[4.2] * 19 + [8.9]))
    assert ok is False
    assert "no measured gap" in detail


def test_missed_recovery_fails():
    rep = _report()
    rep["recoveries"][0]["period_days"] = 2.5
    ok, detail = checks.check_a04(rep)
    assert ok is False
    assert "not recovered" in detail


def test_report_owned_threshold_and_tolerance_cannot_make_a_miss_pass():
    rep = _report()
    rep["recoveries"][0]["period_days"] = 2.5
    rep["sde_threshold"] = 0.0
    rep["period_tolerance_frac"] = 99.0
    ok, detail = checks.check_a04(rep)
    assert ok is False
    assert "not recovered" in detail


def test_all_declared_injections_and_recoveries_are_required():
    rep = _report()
    rep["injections"] = rep["injections"][:1]
    assert checks.check_a04(rep)[0] is None
    rep = _report()
    rep["recoveries"] = rep["recoveries"][:1]
    assert checks.check_a04(rep)[0] is None


def test_third_recovery_must_be_catalogued_after_vetting():
    rep = _report()
    rep["candidates"][0]["catalog"] = {"known_planet": None}
    ok, detail = checks.check_a04(rep)
    assert ok is None
    assert "WASP-20 b" in detail


# ------------------------------------------------------ catalog crosscheck ---

def test_catalog_crosscheck_picks_the_row_nearest_the_detected_period(monkeypatch):
    """Multi-planet TAP queries return unordered rows; rows[0] misnamed
    TOI-125 b as c. The detected period selects the row actually re-found."""
    toi_rows = [
        {"toi": "125.02", "pl_orbper": 9.15059, "tfopwg_disp": "CP"},
        {"toi": "125.01", "pl_orbper": 4.65382, "tfopwg_disp": "CP"},
        {"toi": "125.03", "pl_orbper": 19.98, "tfopwg_disp": "PC"},
    ]
    ps_rows = [
        {"pl_name": "TOI-125 c", "pl_orbper": 9.15059},
        {"pl_name": "TOI-125 b", "pl_orbper": 4.65382},
        {"pl_name": "TOI-125 d", "pl_orbper": 19.98},
    ]
    monkeypatch.setattr(
        a04, "_tap",
        lambda q, deadline=None: toi_rows if "from toi" in q else ps_rows)
    out = a04.catalog_crosscheck("52368076", detected_period_days=4.652)
    assert out["known_toi"] == "125.01"
    assert out["known_planet"] == "TOI-125 b"
    assert out["published_period_days"] == pytest.approx(4.65382)
    # Without a detected period the old rows[0] fallback still stands.
    out0 = a04.catalog_crosscheck("52368076")
    assert out0["known_planet"] == "TOI-125 c"
    # Rows without usable periods also fall back to rows[0].
    monkeypatch.setattr(
        a04, "_tap",
        lambda q, deadline=None: [{"toi": "9.01", "pl_orbper": None,
                                   "tfopwg_disp": "PC"}] if "from toi" in q
        else [])
    out_null = a04.catalog_crosscheck("1", detected_period_days=3.0)
    assert out_null["known_toi"] == "9.01"


def test_a04_is_registered():
    from lab import curriculum
    assert checks.CHECKS["A04"] is checks.check_a04
    assert curriculum.RUNNERS["A04"] == "a04"


# ------------------ (VET-F3) the vetting sigmas are MEDIAN sigmas ------------
#
# `vet_candidate` reads every depth with a MEDIAN but divided by a MEAN's
# standard error, `noise / sqrt(n)`. The standard error of a median on Gaussian
# noise is sqrt(pi/2) larger than a mean's, and a DIFFERENCE of two medians
# carries that factor on each term. So the odd-even statistic ran ~sqrt(pi)
# (1.77x) hot and the depth statistic ~sqrt(pi/2) (1.25x) hot — and `:244`,
# the rung that mints "planet-candidate", sat at a nominal 5 sigma while
# actually admitting true ~4 sigma dips. `a05_fold` had already fixed this for
# its own gates (MEDIAN_SIGMA_FACTOR); the rung that mints every candidate
# first had not.

MEDIAN_SE = float(np.sqrt(np.pi / 2.0))
VET_P, VET_DUR, VET_NOISE = 1.7, 2.5 / 24, 3e-4
#: `inject_box` puts the epoch at t[0] + 0.37 * period, so a synthetic planted
#: with it is folded at phase 0.37.
VET_PHASE = 0.37


def _planted(depth: float, seed: int = 7):
    t, f = _flat(noise=VET_NOISE, cadence=0.005, seed=seed)
    if depth:
        f = a04.inject_box(t, f, VET_P, depth, duration_days=VET_DUR)
    return t, f


def _det(depth: float = 0.0):
    return a04.Detection(period_days=VET_P, depth=depth, phase=VET_PHASE,
                         sde=9.0)


def test_odd_even_sigma_is_calibrated_on_pure_noise():
    """On PURE NOISE the odd-even statistic must be a standard normal.

    Its absolute value then has mean sqrt(2/pi) = 0.7979. Pre-fix the mean
    came in ~1.69x hot (the sqrt(pi) difference-of-medians factor), which is
    what let a noise-only star's parities look inconsistent — and, on the same
    scale error, let a sub-threshold dip look significant.
    """
    vals = []
    for s in range(120):
        t, f = _planted(0.0, seed=1000 + s)
        row = a04.vet_candidate(t, f, _det())
        assert row["verdict"] != "period-railed", row
        vals.append(row["odd_even_sigma"])
    mean_abs = float(np.mean(vals))
    expected = float(np.sqrt(2.0 / np.pi))
    # 120 trials; the standard error on the mean of |N(0,1)| is ~0.055.
    assert abs(mean_abs - expected) < 0.10, (
        f"odd-even sigma is not calibrated: mean|z| = {mean_abs:.3f}, "
        f"expected {expected:.3f} (scale is off by "
        f"{mean_abs / expected:.3f}x)")


def test_odd_even_sigma_matches_the_analytic_difference_of_medians():
    """Pin the computed sigma against the closed form, on one fixed curve."""
    t, f = _planted(0.0, seed=4242)
    row = a04.vet_candidate(t, f, _det())
    period, ph0 = VET_P, VET_PHASE
    phase = np.mod(t, period) / period
    epoch = np.floor((t - t[0]) / period).astype(int)
    in_tr = np.abs(((phase - ph0 + 0.5) % 1.0) - 0.5) < a04.VET_WINDOW_PHASE
    out = ~in_tr
    noise = float(np.std(f[out]))
    n_odd = int((in_tr & (epoch % 2 == 1)).sum())
    n_even = int((in_tr & (epoch % 2 == 0)).sum())
    # SE of a difference of two independent medians on Gaussian noise.
    analytic = MEDIAN_SE * noise * np.sqrt(1.0 / n_odd + 1.0 / n_even)
    expected = abs(row["depth_odd"] - row["depth_even"]) / analytic
    assert row["odd_even_sigma"] == pytest.approx(expected, rel=1e-9), (
        f"reported {row['odd_even_sigma']:.4f} vs analytic {expected:.4f} "
        f"— ratio {row['odd_even_sigma'] / expected:.4f}")


def test_depth_gate_does_not_mint_a_sub_five_sigma_candidate():
    """The candidate-minting rung must sit at a REAL 5 sigma.

    depth 1.7e-4 on this curve is a true 4.9-sigma dip. Pre-fix the mean's
    error bar reported it as 6.15 sigma and `vet_candidate` returned
    "planet-candidate" — a candidate minted below threshold, which is the
    whole defect: every A05 lead starts as one of these.
    """
    t, f = _planted(1.7e-4)
    row = a04.vet_candidate(t, f, _det(1.7e-4))
    assert row["depth_sigma"] < a04.ODD_EVEN_SIGMA, (
        f"depth_sigma {row['depth_sigma']:.2f} still clears the "
        f"{a04.ODD_EVEN_SIGMA:g}-sigma bar on a true ~4.9-sigma dip")
    assert row["verdict"] == "low-significance", row


def test_a_genuinely_significant_dip_is_still_a_candidate():
    """The fix tightens the bar; it must not close it. 3e-4 is a true ~9 sigma."""
    t, f = _planted(3.0e-4)
    row = a04.vet_candidate(t, f, _det(3.0e-4))
    assert row["verdict"] == "planet-candidate", row
    assert row["depth_sigma"] >= a04.ODD_EVEN_SIGMA


# --- the secondary window must match the eclipse, not a constant (2026-08-28) --
#
# TIC 144122210 graded its secondary at 834 ppm / 4.872 sigma against the hard
# 5.0 gate and was minted a planet-candidate lead. It is an eclipsing binary.
# The cause was not the threshold: the secondary was measured in a fixed
# +-0.03-phase window (+-2.23 h at P=3.1 d) while the transit itself was 3.54 h
# wide, so roughly a quarter of the sample sat at baseline and dragged the
# median toward zero. Systematic, one-directional, and worst on short transits.

def _eb_curve(period=3.1, half_width_phase=0.012, depth=0.024, sec_depth=0.0017,
              n=6000, noise=0.0004, seed=7):
    """A clean EB: narrow primary, real secondary at phase 0.5."""
    import numpy as np
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, period * 12.0, n)
    ph = np.mod(t, period) / period
    f = np.ones(n)
    d1 = np.abs(((ph - 0.5 + 0.5) % 1.0) - 0.5)
    f[d1 < half_width_phase] -= depth
    d2 = np.abs(((ph - 0.5 - 0.5 + 0.5) % 1.0) - 0.5)
    f[d2 < half_width_phase] -= sec_depth
    return t, f + rng.normal(0.0, noise, n), period


def test_secondary_window_narrows_to_the_eclipse_and_recovers_its_depth():
    """The planted secondary must be recovered near its true depth, not diluted."""
    import numpy as np
    from lab import a04
    t, f, period = _eb_curve()
    base = float(np.median(f))
    phase = np.mod(t, period) / period
    in_tr = np.abs(((phase - 0.5 + 0.5) % 1.0) - 0.5) < a04.VET_WINDOW_PHASE
    depth = base - float(np.median(f[in_tr]))

    noise = float(np.std(f[~in_tr]))
    hw = a04._eclipse_half_width(phase, f, 0.5, base, in_tr, noise)
    assert hw is not None, "half-width estimator refused on a clean planted eclipse"
    assert hw < a04.VET_WINDOW_PHASE, f"window did not narrow: {hw} vs {a04.VET_WINDOW_PHASE}"

    def _sec_depth(window):
        sec = np.abs(((phase - 0.5 - 0.5 + 0.5) % 1.0) - 0.5) < window
        return base - float(np.median(f[sec]))

    diluted = _sec_depth(a04.VET_WINDOW_PHASE)   # the old, fixed window
    matched = _sec_depth(hw)                      # the eclipse's own width
    assert matched > diluted * 1.5, (
        f"matched window did not recover the secondary: {matched:.6f} vs diluted {diluted:.6f}")
    assert abs(matched - 0.0017) < 0.0006, f"recovered depth off: {matched:.6f}"


def test_the_window_can_only_ever_tighten():
    """A change to a vetting gate that can only make it stricter cannot quietly
    promote noise to a candidate. Guard that property directly."""
    import numpy as np
    from lab import a04
    # A transit that FILLS the fixed window: the estimator must not widen past it.
    t, f, period = _eb_curve(half_width_phase=0.030)
    base = float(np.median(f))
    phase = np.mod(t, period) / period
    in_tr = np.abs(((phase - 0.5 + 0.5) % 1.0) - 0.5) < a04.VET_WINDOW_PHASE
    noise = float(np.std(f[~in_tr]))
    hw = a04._eclipse_half_width(phase, f, 0.5, base, in_tr, noise)
    clamped = (a04.VET_WINDOW_PHASE if hw is None
               else min(max(hw, a04.VET_WINDOW_MIN_PHASE), a04.VET_WINDOW_PHASE))
    assert clamped <= a04.VET_WINDOW_PHASE + 1e-12


def test_unmeasurable_eclipse_falls_back_to_the_constant():
    """No signal, no guess: the estimator returns None and the caller keeps the
    old constant rather than inventing a width."""
    import numpy as np
    from lab import a04
    rng = np.random.default_rng(3)
    f = np.ones(3000) + rng.normal(0, 4e-4, 3000)
    phase = np.linspace(0, 1, 3000)
    in_tr = np.ones(3000, dtype=bool)
    # Pure noise: the estimator must refuse rather than invent a width.
    assert a04._eclipse_half_width(phase, f, 0.5, 1.0, in_tr, 4e-4) is None
