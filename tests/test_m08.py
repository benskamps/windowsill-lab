"""M08 2D XY / BKT — the helicity-jump crossing finder and the report serializer.

Mirrors ``tests/test_m06.py``: ``helicity_crossing`` is exercised against curves
built so that g(T) = Υ(T) − (2/π)·T crosses zero at a KNOWN temperature, so the
interpolated root is exact by construction; the ``None`` (no-bracket) branch and the
"first downward crossing" rule are pinned too. The real ``run_m08`` / XY engine is
never invoked — only the NumPy-only crossing finder + serializer are under test.
"""
import numpy as np

from lab.m08 import (
    T_BKT, TWO_OVER_PI, helicity_crossing, to_report, M08Result,
)


def _helicity_for(T, g):
    """Build Υ(T) so that Υ(T) − (2/π)·T == g exactly: Υ = g + (2/π)·T."""
    T = np.asarray(T, dtype=float)
    return (np.asarray(g, dtype=float) + TWO_OVER_PI * T).tolist()


# ── helicity_crossing — the crossing root ─────────────────────────────────────
def test_crossing_is_exact_linear_root():
    # g = [+0.2, −0.2, …] crosses zero halfway between T=0.8 and 0.9 → 0.85 exactly.
    T = [0.8, 0.9, 1.0]
    Y = _helicity_for(T, [0.2, -0.2, -0.3])
    tc = helicity_crossing(T, Y)
    assert tc is not None
    assert abs(tc - 0.85) < 1e-12


def test_crossing_returns_none_when_unbracketed():
    # Υ everywhere above the jump line → g > 0 throughout → no crossing → None.
    T = [0.6, 0.8, 1.0]
    Y = _helicity_for(T, [1.0, 1.0, 1.0])
    assert helicity_crossing(T, Y) is None


def test_crossing_takes_first_downward_crossing():
    # Two downward crossings; the physical one is the FIRST (Υ drops through the
    # line once near T_BKT). g = [+0.2, −0.2, +0.1, −0.1]: first root in [0.8, 0.9].
    T = [0.8, 0.9, 1.0, 1.1]
    Y = _helicity_for(T, [0.2, -0.2, 0.1, -0.1])
    tc = helicity_crossing(T, Y)
    assert abs(tc - 0.85) < 1e-12          # the first crossing, not the later one
    assert tc < 1.0


def test_crossing_handles_exact_zero_at_left_node():
    # g[i] == 0 (>= 0 branch) with g[i+1] < 0 → root sits exactly on T[i].
    T = [0.85, 0.95]
    Y = _helicity_for(T, [0.0, -0.3])
    assert helicity_crossing(T, Y) == 0.85


# ── to_report ─────────────────────────────────────────────────────────────────
def _toy_result(tc_crossing=0.9):
    T = [0.6, 0.8, 0.9, 1.0, 1.1]
    rel = (abs(tc_crossing - T_BKT) / T_BKT) if tc_crossing is not None else None
    return M08Result(
        T=T,
        helicity_modulus=[0.6, 0.55, 0.5, 0.3, 0.1],
        helicity_err=[0.01] * 5,
        energy=[-1.9, -1.7, -1.5, -1.3, -1.1],
        abs_mag=[0.3, 0.25, 0.2, 0.15, 0.1],
        acceptance=[0.5] * 5,
        L=64,
        tc_crossing=tc_crossing,
        tc_benchmark=T_BKT,
        rel_error=rel,
        updater="metropolis",
        wall_seconds=120.0,
        config={"L": 64, "model": "xy", "seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M08-xy-bkt"
    assert not rep["experiment"].startswith("M01")
    # M08 carries (T, helicity) — NO χ-peak — and the universal-jump slope.
    assert rep["T"] == [0.6, 0.8, 0.9, 1.0, 1.1]
    assert len(rep["helicity_modulus"]) == len(rep["T"])
    assert rep["two_over_pi"] == TWO_OVER_PI
    assert rep["tc_benchmark"] == T_BKT
    assert rep["L"] == 64
    assert "headline" in rep and "BKT" in rep["headline"]


def test_to_report_handles_missing_crossing():
    # The None branch of the serializer: no crossing → em-dash headline, no crash,
    # null fields carried through.
    rep = to_report(_toy_result(tc_crossing=None))
    assert rep["tc_crossing"] is None
    assert rep["rel_error"] is None
    assert "—" in rep["headline"]
