"""K04 fireflies — the engine, the cascade, the theorem gate.

Three layers, matching the K-track house style (cf. ``test_k01_maturity.py``):

* **The charging curve** is pinned against its own hypotheses — the theorem
  needs f smooth, monotone, concave down with f(0)=0, f(1)=1, and a wrong
  curve (convex, or a broken inverse) voids the theorem the milestone grades.
* **The cascade** is pinned on hand-placed configurations whose outcome is
  computable on paper: a kick that must absorb, a kick that must not, and a
  chain absorption that only happens because an absorbed oscillator's own
  flash joins the cascade.
* **The runner + report + check**: the ε = 0 population must never order (the
  null, as a test), a small population must always reach unison (the theorem,
  as a test), and — the load-bearing one — ``check_k04`` must re-derive its
  verdict from the per-trial rows, refusing tampered and unreadable receipts
  in the right directions (False vs None per the check_a05 doctrine).

NumPy is imported through ``importorskip`` so this file degrades to a skip in
CI's stdlib-only pipeline lane; the check-layer tests run on hand-built
reports that need no engine at all.
"""
import math

import pytest

np = pytest.importorskip("numpy")

from lab import k04  # noqa: E402  (must follow the importorskip)
from lab.checks import (  # noqa: E402
    FIREFLY_B, FIREFLY_EPS, FIREFLY_MAX_EVENTS, FIREFLY_N,
    FIREFLY_NULL_EVENT_BUDGET, FIREFLY_NULL_TRIALS, FIREFLY_TRIALS, check_k04,
)


# ─────────────────── the charging curve: the theorem's hypotheses ───────────────────

def test_charging_curve_satisfies_the_theorems_hypotheses():
    """f(0)=0, f(1)=1, strictly increasing, strictly concave down — the exact
    conditions Mirollo–Strogatz require; a curve that lost concavity would
    void the theorem this milestone grades against."""
    phi = np.linspace(0.0, 1.0, 401)
    x = k04.charging_curve(phi)
    assert x[0] == pytest.approx(0.0, abs=1e-12)
    assert x[-1] == pytest.approx(1.0, abs=1e-12)
    assert np.all(np.diff(x) > 0), "monotone increasing"
    assert np.all(np.diff(x, 2) < 0), "concave down everywhere"


def test_charging_inverse_round_trips_exactly():
    phi = np.linspace(0.0, 0.999, 97)
    back = k04.charging_inverse(k04.charging_curve(phi))
    np.testing.assert_allclose(back, phi, atol=1e-12)


# ─────────────────── the cascade, on paper-computable configurations ───────────────────

def _phase_with_charge(x: float) -> float:
    return float(k04.charging_inverse(x))


def test_a_kick_that_reaches_threshold_absorbs_into_unison():
    """Two oscillators: one fires; the other sits ε/2 below threshold in
    CHARGE, so the single flash must absorb it — unison in one event."""
    eps = 0.01
    init = [1.0, _phase_with_charge(1.0 - eps / 2)]
    out = k04.run_trial(2, k04.B_DISSIPATION, eps, None, 10, init_phi=init)
    assert out == {"events": 1, "clusters": 1, "largest_cascade": 2}


def test_a_kick_that_falls_short_does_not_absorb():
    """Same setup but the trailing oscillator sits 2ε below threshold in
    charge: the flash moves it, and must NOT fire it this event."""
    eps = 0.01
    init = [1.0, _phase_with_charge(1.0 - 2 * eps)]
    out = k04.run_trial(2, k04.B_DISSIPATION, eps, None, 1, init_phi=init)
    assert out["events"] is None and out["clusters"] == 2


def test_chain_absorption_needs_the_absorbed_oscillators_own_flash():
    """Three oscillators: A fires. B sits ε/2 below threshold (absorbed by
    A's flash alone). C sits 1.5ε below — out of reach of A's single kick,
    inside reach of A's + B's two kicks. Unison in one event proves absorbed
    oscillators' flashes join the cascade; a cascade that dropped them would
    leave C behind."""
    eps = 0.01
    init = [1.0,
            _phase_with_charge(1.0 - eps / 2),
            _phase_with_charge(1.0 - 1.5 * eps)]
    out = k04.run_trial(3, k04.B_DISSIPATION, eps, None, 10, init_phi=init)
    assert out == {"events": 1, "clusters": 1, "largest_cascade": 3}


# ─────────────────── the theorem and its null, as tests ───────────────────

def test_every_random_start_reaches_unison_on_a_quick_population():
    for trial in range(10):
        out = k04.run_trial(25, k04.B_DISSIPATION, 0.002,
                            np.random.default_rng([7, trial]), 2000)
        assert out["events"] is not None and out["clusters"] == 1


def test_an_uncoupled_population_never_orders():
    """ε = 0 is the null the check grades: no kick, no merging, ever — a
    population that ordered anyway would be ordering through bookkeeping."""
    out = k04.run_trial(50, k04.B_DISSIPATION, 0.0,
                        np.random.default_rng([11]), 1500)
    assert out["events"] is None
    assert out["clusters"] == 50


# ─────────────────── identity mirror + the check re-derives ───────────────────

def test_k04_identity_mirrors_the_runner():
    assert (FIREFLY_N, FIREFLY_B, FIREFLY_EPS, FIREFLY_TRIALS,
            FIREFLY_MAX_EVENTS, FIREFLY_NULL_TRIALS,
            FIREFLY_NULL_EVENT_BUDGET) == (
        k04.CALIBRATION_N, k04.B_DISSIPATION, k04.CALIBRATION_EPS,
        k04.CALIBRATION_TRIALS, k04.CALIBRATION_MAX_EVENTS,
        k04.NULL_TRIALS, k04.NULL_EVENT_BUDGET)


def _calibration_report(**overrides) -> dict:
    events = [100 + (i % 117) for i in range(FIREFLY_TRIALS)]
    report = {
        "experiment": "K04-firefly-synchronization",
        "n": FIREFLY_N, "b": FIREFLY_B, "eps": FIREFLY_EPS,
        "trials": FIREFLY_TRIALS, "max_events_bound": FIREFLY_MAX_EVENTS,
        "events": events,
        "synced": FIREFLY_TRIALS,
        "events_max": max(events),
        "null_clusters": [FIREFLY_N] * FIREFLY_NULL_TRIALS,
    }
    report.update(overrides)
    return report


def test_check_passes_a_self_consistent_calibration_receipt():
    ok, detail = check_k04(_calibration_report())
    assert ok is True and "almost-sure synchronization" in detail


def test_a_trial_that_missed_unison_fails_the_theorem_gate():
    events = _calibration_report()["events"]
    events[137] = None
    ok, detail = check_k04(_calibration_report(
        events=events, synced=FIREFLY_TRIALS - 1))
    assert ok is False and "did not reach unison" in detail


def test_a_headline_that_disagrees_with_its_rows_is_not_self_consistent():
    """The load-bearing property: the check re-derives from the rows, so a
    tampered stored summary cannot buy a pass."""
    ok, detail = check_k04(_calibration_report(events_max=1))
    assert ok is False and "not self-consistent" in detail


def test_a_null_control_that_merged_fails_loudly():
    nulls = [FIREFLY_N] * FIREFLY_NULL_TRIALS
    nulls[3] = FIREFLY_N - 1
    ok, detail = check_k04(_calibration_report(null_clusters=nulls))
    assert ok is False and "uncoupled control failed" in detail


def test_a_changed_identity_is_a_diagnostic_not_this_calibration():
    ok, detail = check_k04(_calibration_report(eps=0.01))
    assert ok is False and "identity changed" in detail


def test_unreadable_receipts_are_none_never_negative():
    assert check_k04({"experiment": "K01-kuramoto-synchronization"})[0] is None
    assert check_k04(_calibration_report(events=None))[0] is None
    short = _calibration_report()
    short["events"] = short["events"][:10]
    assert check_k04(short)[0] is None


# ─────────────────── the real runner end to end (quick, non-calibration) ───────────────────

def test_a_quick_run_reports_honestly_that_it_is_not_the_calibration():
    result = k04.run_k04(n=20, trials=5, max_events=2000, seed=42,
                         ladders=False)
    assert result.synced == 5
    assert result.is_calibration is False
    report = k04.to_report(result)
    # A diagnostic run must grade null (identity changed), never pass.
    assert report["status"] == "null"
    assert "claim_boundary" in report and "theorem" in report["claim_boundary"]


def test_math_import_is_used():  # keep flake honest about the math import
    assert math.isfinite(1.0)
