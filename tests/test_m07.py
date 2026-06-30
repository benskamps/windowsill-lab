"""M07 q-state Potts — the order-drop probe, the exact-T_c map, and the serializer.

Mirrors ``tests/test_m06.py``: the NumPy-only ``_order_drop`` fingerprint and the
exact ``TC_POTTS(q)`` map are exercised against hand-built inputs (parameter-free,
exact by construction), and ``to_report`` is checked for its multi-q JSON shape.
The real ``run_m07`` / Potts engine is never invoked.
"""
import math

from lab.m07 import (
    TC_POTTS, Q_VALUES, _order_drop, to_report, M07Result, QResult,
)


# ── TC_POTTS (exact by construction) ──────────────────────────────────────────
def test_tc_potts_is_self_dual_exact():
    # 1 / ln(1 + √q) at every swept q, computed the SAME way the module does.
    for q in Q_VALUES:
        assert TC_POTTS(q) == 1.0 / math.log(1.0 + math.sqrt(q))


def test_tc_potts_matches_baxter_table():
    # The published self-dual values (MILESTONES / module docstring).
    assert abs(TC_POTTS(3) - 0.99497) < 1e-4
    assert abs(TC_POTTS(4) - 0.91024) < 1e-4
    assert abs(TC_POTTS(5) - 0.85153) < 1e-4
    assert abs(TC_POTTS(6) - 0.80760) < 1e-4


def test_tc_potts_decreases_with_q():
    tcs = [TC_POTTS(q) for q in Q_VALUES]
    assert tcs == sorted(tcs, reverse=True)   # strictly falling across q = 3..6


# ── _order_drop (steepest single-step melt) ───────────────────────────────────
def test_order_drop_is_largest_adjacent_decrease():
    # drops = [0.25, 0.5, 0.125] (binary-exact) → the steepest melt is 0.5.
    assert _order_drop([0, 1, 2, 3], [1.0, 0.75, 0.25, 0.125]) == 0.5


def test_order_drop_short_sequence_is_zero():
    # The n < 2 guard: a single point (or empty) has no step to drop across.
    assert _order_drop([0], [0.5]) == 0.0
    assert _order_drop([], []) == 0.0


def test_order_drop_monotone_rise_is_negative():
    # A purely increasing order parameter has no decrease — the steepest "drop" is
    # the least-negative step (here −0.25), not clamped to 0.
    assert _order_drop([0, 1, 2], [0.25, 0.5, 0.75]) == -0.25


# ── to_report ─────────────────────────────────────────────────────────────────
def _q(q, tc_chi_refined=None, chi_max=10.0, order_drop=0.2):
    tc = TC_POTTS(q)
    T = [tc - 0.1, tc, tc + 0.1]
    return QResult(
        q=q,
        T=T,
        order=[0.8, 0.5, 0.2],
        order_err=[0.01, 0.01, 0.01],
        chi=[20.0, chi_max, 18.0],
        energy=[-1.5, -1.3, -1.1],
        specific_heat=[1.0, 2.0, 1.2],
        tc_chi=tc,
        tc_chi_refined=tc if tc_chi_refined is None else tc_chi_refined,
        tc_exact=tc,
        rel_error=0.0 if tc_chi_refined is None else abs(tc_chi_refined - tc) / tc,
        chi_max=chi_max,
        order_drop=order_drop,
        wall_seconds=5.0,
    )


def _toy_result():
    # Two continuous (q ≤ 4) and two first-order (q ≥ 5) so both mean-branches in
    # to_report are exercised; first-order χ_max set taller, the qualitative claim.
    per_q = [
        _q(3, chi_max=30.0, order_drop=0.2),
        _q(4, chi_max=40.0, order_drop=0.3),
        _q(5, chi_max=120.0, order_drop=0.6),
        _q(6, chi_max=200.0, order_drop=0.7),
    ]
    return M07Result(
        per_q=per_q,
        L=128,
        transition_order={3: "continuous", 4: "continuous",
                          5: "first-order", 6: "first-order"},
        wall_seconds=300.0,
        config={"L": 128, "q_values": list(Q_VALUES), "seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M07-potts"
    assert not rep["experiment"].startswith("M01")
    # One per-q block per swept q, each carrying its arrays + measured/exact T_c.
    assert [b["q"] for b in rep["per_q"]] == [3, 4, 5, 6]
    for b in rep["per_q"]:
        assert {"T", "chi", "order", "tc_chi_refined", "tc_exact", "transition"} <= set(b)
        assert b["tc_exact"] == TC_POTTS(b["q"])
    # transition_order keys are stringified for JSON.
    assert rep["transition_order"] == {"3": "continuous", "4": "continuous",
                                       "5": "first-order", "6": "first-order"}
    assert "headline" in rep and "Potts" in rep["headline"]


def test_to_report_first_order_signature_is_taller():
    # The qualitative claim: the mean peak susceptibility climbs across the
    # continuous (q ≤ 4) → first-order (q ≥ 5) boundary.
    rep = to_report(_toy_result())
    assert rep["continuous_mean_chi_max"] == 35.0       # mean(30, 40)
    assert rep["first_order_mean_chi_max"] == 160.0      # mean(120, 200)
    assert rep["first_order_mean_chi_max"] > rep["continuous_mean_chi_max"]
    assert rep["first_order_mean_order_drop"] > rep["continuous_mean_order_drop"]
