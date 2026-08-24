"""U-K02's reach projection — priced before a single GPU-hour is spent.

The discipline being tested is the ordering: a cost estimate that arrives after
the run is an invoice, not a feasibility test.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lab import u_k02_reach as u

RECEIPT = (Path(__file__).resolve().parents[1]
           / "reports/receipts/run-2026-08-23-2216-k03.json")


def test_more_oscillators_reduce_the_predicted_spread_as_one_over_root_n():
    a = u.spread_at(0.02, ref_eps=0.02, ref_spread=0.4, n_ratio=1)
    b = u.spread_at(0.02, ref_eps=0.02, ref_spread=0.4, n_ratio=100)
    assert b == pytest.approx(a / 10.0)


def test_noise_grows_toward_the_transition():
    """Critical slowing down: the same T buys fewer independent samples nearer
    K_c, which is the measured cause of the gate refusals."""
    near = u.spread_at(0.005, ref_eps=0.02, ref_spread=0.4)
    far = u.spread_at(0.32, ref_eps=0.02, ref_spread=0.4)
    assert near > far


def test_the_projection_aims_below_the_gate_not_at_it():
    """The 2026-08-23 run had a column pass at spread 0.133 against a 0.15
    tolerance and another refuse at 0.312 while sitting FURTHER from K_c. A
    plan that targets the threshold is planning to be decided by the draw."""
    from lab import k03
    r = u.project(RECEIPT, n_target=200_000)
    assert all(row["spread_predicted"] <= k03.SECANT_TOL * u.SAFETY + 1e-9
               for row in r["grid"])


def test_the_cost_curve_is_never_extrapolated_past_what_was_benchmarked():
    """The whole point of measuring the step cost is that its shape changes
    (launch-bound to bandwidth-bound). Guessing past the measured range would
    defeat the exercise, so it raises instead."""
    with pytest.raises(ValueError):
        u._interp_step_seconds(50_000_000, u.GPU_STEP_SECONDS)


def test_the_gpu_is_not_assumed_faster_at_small_n():
    """At N = 2,000 the measured GPU step is SLOWER than NumPy. Recording that
    honestly is what makes the N = 200,000 claim credible."""
    assert u.GPU_STEP_SECONDS[2_000] > u.STEP_SECONDS[2_000]


def test_the_committed_receipt_projects_in_reach_within_a_night():
    r = u.project(RECEIPT, n_target=200_000, eps_floor=0.005, budget_hours=8.0)
    assert r["reach"] == "in-reach"
    assert r["gpu_hours"] < 8.0
    assert r["speedup_vs_cpu"] > 10


def test_an_unaffordable_target_is_reported_out_of_reach_not_trimmed():
    """The failure mode to refuse: quietly cutting T_MEASURE to fit the budget,
    which reopens the exact noise problem the run exists to close."""
    r = u.project(RECEIPT, n_target=200_000, eps_floor=0.005, budget_hours=0.01)
    assert r["reach"] == "out-of-reach"
    assert "do NOT trim T_MEASURE" in r["detail"]


def test_a_receipt_with_no_subcritical_spreads_cannot_be_extrapolated(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text('{"columns_below": []}', encoding="utf-8")
    assert u.project(p)["reach"] == "out-of-reach"
