"""Input-contract and producer/checker consistency tests for M16."""
from __future__ import annotations

import math

import pytest

from lab import checks, m16


VALID_WAITING_TIMES = (1, 2, 4)
VALID_DELTA_TIMES = (1, 2, 4, 8)


def _valid_clock():
    return {
        "waiting_times": list(VALID_WAITING_TIMES),
        "delta_times": list(VALID_DELTA_TIMES),
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"L": 0}, "L must be a positive integer"),
        ({"L": -2}, "L must be a positive integer"),
        ({"L": 3}, "positive even L"),
        ({"L": 4.5}, "L must be a positive integer"),
        ({"T": 0}, "T must be finite and > 0"),
        ({"T": -0.1}, "T must be finite and > 0"),
        ({"T": float("nan")}, "T must be finite and > 0"),
        ({"T": float("inf")}, "T must be finite and > 0"),
        ({"n_realizations": 0}, "n_realizations must be a positive integer"),
        ({"n_realizations": -1}, "n_realizations must be a positive integer"),
        ({"n_realizations": 1.5}, "n_realizations must be a positive integer"),
        ({"waiting_times": [1, 2]}, "needs >=3 waiting times"),
        ({"delta_times": [1, 2, 4]}, "needs >=4 delta times"),
        ({"waiting_times": [1, 2, 2]}, "distinct times"),
        ({"delta_times": [1, 4, 2, 8]}, "strictly increasing"),
        ({"waiting_times": [0, 2, 4]}, "positive integer"),
        (
            {"waiting_times": [10, 20, 30], "delta_times": [1, 2, 3, 4]},
            ">=2 repeated dt/t_w ratio groups",
        ),
    ],
)
def test_run_rejects_invalid_inputs_before_simulation(overrides, message):
    kwargs = {
        "L": 2,
        "T": 0.6,
        "n_realizations": 1,
        "device": "cpu",
        **_valid_clock(),
        **overrides,
    }
    with pytest.raises(ValueError, match=message):
        m16.run_m16(**kwargs)


def _ideal_gate_metrics():
    return {
        "collapse_ratio": 0.5,
        "fixed_lag_separation": 0.1,
        "ratio_groups": 2,
        "difference_groups": 4,
        "correlations_in_range": True,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("collapse_ratio", 0.81),
        ("collapse_ratio", float("nan")),
        ("fixed_lag_separation", 0.029),
        ("ratio_groups", 1),
        ("difference_groups", 3),
        ("correlations_in_range", False),
    ],
)
def test_shared_aging_gate_owns_every_pass_requirement(field, value):
    metrics = _ideal_gate_metrics()
    assert m16.aging_gate(metrics)
    metrics[field] = value
    assert not m16.aging_gate(metrics)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda report: report["waiting_times"].__setitem__(0, 0),
        lambda report: report["delta_times"].reverse(),
        lambda report: report["correlations"]["1"].__setitem__(0, float("nan")),
        lambda report: report["correlations"]["1"].__setitem__(0, 1.1),
    ],
)
def test_checker_rejects_malformed_receipts_without_raising(mutate):
    rows = {
        str(tw): [math.exp(-math.sqrt(dt / tw)) for dt in VALID_DELTA_TIMES]
        for tw in VALID_WAITING_TIMES
    }
    report = {
        "experiment": "M16-spin-glass-aging",
        **_valid_clock(),
        "correlations": rows,
        "aging_resolved": True,
    }
    mutate(report)
    ok, detail = checks.check_m16(report)
    assert ok is False
    assert detail


def test_checker_rejects_a_clock_that_cannot_form_enough_ratio_groups():
    waiting = [10, 20, 30]
    deltas = [1, 2, 3, 4]
    report = {
        "experiment": "M16-spin-glass-aging",
        "waiting_times": waiting,
        "delta_times": deltas,
        "correlations": {str(tw): [0.5] * len(deltas) for tw in waiting},
    }
    ok, detail = checks.check_m16(report)
    assert ok is False
    assert "ratio groups" in detail


def test_tiny_runner_and_checker_use_the_same_verdict():
    pytest.importorskip("torch")
    result = m16.run_m16(
        L=2,
        T=0.6,
        n_realizations=1,
        device="cpu",
        seed=7,
        **_valid_clock(),
    )
    checked, detail = checks.check_m16(m16.to_report(result))
    assert checked is result.aging_resolved, detail
