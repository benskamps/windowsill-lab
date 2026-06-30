"""M05 triangular-lattice Ising — the exact-T_c constant and the report serializer.

Mirrors ``tests/test_m04.py``: M05 reuses m06's NumPy-only peak finders, so the
falsifiable pure surface is the exact triangular critical temperature it publishes
(T_c = 4/ln 3, a *different* number from the square lattice's 2.2692 — the whole
point of the geometry change) and ``to_report``'s JSON shape. ``run_m05`` (the real
triangular sweep) is never invoked.
"""
import math

from lab.m05 import TC_TRI, to_report, M05Result


# ── constant (exact by construction) ──────────────────────────────────────────
def test_tc_tri_is_four_over_ln3_exact():
    # 4 / ln 3 ≈ 3.64096 — the exact triangular-lattice Ising T_c, computed the
    # SAME way the module does, so the assertion is exact.
    assert TC_TRI == 4.0 / math.log(3.0)
    assert abs(TC_TRI - 3.640957) < 1e-6


def test_tc_tri_differs_from_square_lattice():
    # The geometry check: the triangular T_c must NOT be the square-lattice 2.2692.
    square_tc = 2.0 / math.log(1.0 + math.sqrt(2.0))
    assert TC_TRI > square_tc
    assert abs(TC_TRI - square_tc) > 1.0


# ── to_report ─────────────────────────────────────────────────────────────────
def _toy_result(tc_chi_refined=TC_TRI):
    T = [3.4, 3.5, 3.64, 3.8, 3.9]
    return M05Result(
        T=T,
        chi=[10.0, 40.0, 95.0, 38.0, 8.0],
        abs_mag=[0.9, 0.8, 0.5, 0.2, 0.1],
        abs_mag_err=[0.01] * 5,
        energy=[-2.9, -2.7, -2.4, -2.1, -1.9],
        specific_heat=[1.0, 2.0, 5.0, 2.2, 0.9],
        L=129,
        tc_chi=3.64,
        tc_chi_refined=tc_chi_refined,
        tc_cv_refined=3.63,
        tc_benchmark=TC_TRI,
        rel_error=abs(tc_chi_refined - TC_TRI) / TC_TRI,
        wall_seconds=120.0,
        config={"L": 129, "lattice": "triangular", "seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M05-triangular"
    # Distinct tag so the square-lattice χ-peak check (check_m01) skips it.
    assert not rep["experiment"].startswith("M01")
    assert rep["T"] == [3.4, 3.5, 3.64, 3.8, 3.9]
    assert len(rep["chi"]) == len(rep["T"])
    assert rep["tc_benchmark"] == TC_TRI
    assert rep["L"] == 129
    assert rep["config"]["lattice"] == "triangular"
    assert "headline" in rep and "4/ln3" in rep["headline"]


def test_to_report_rel_error_zero_at_exact_tc():
    rep = to_report(_toy_result(tc_chi_refined=TC_TRI))
    assert rep["rel_error"] == 0.0
    assert rep["tc_chi_refined"] == TC_TRI
