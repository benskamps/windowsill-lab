"""M10 antiferromagnetic Ising — the exact-T_N constant and the report serializer.

Mirrors ``tests/test_m04.py``: M10 reuses m06's NumPy-only peak finders, so the
falsifiable pure surface is the exact Néel temperature it publishes (T_N = 2/ln(1+√2)
— identical to Onsager's square-lattice T_c by the bipartite sublattice gauge
duality) and ``to_report``'s JSON shape. The serializer's structural twist — the
order parameter lives under ``chi_staggered``, NOT a top-level ``chi`` — is asserted
here so check_m01 is not-applicable by structure as well as by tag. ``run_m10`` (the
real AFM sweep) is never invoked.
"""
import math

from lab.m10 import TC_AFM, to_report, M10Result


# ── constant (exact by construction) ──────────────────────────────────────────
def test_tc_afm_equals_onsager_exact():
    # The Néel temperature of the bipartite-square AFM is Onsager's T_c, computed
    # the SAME way — exact, not tolerance-bounded.
    assert TC_AFM == 2.0 / math.log(1.0 + math.sqrt(2.0))
    assert abs(TC_AFM - 2.269185314) < 1e-9


def test_tc_afm_matches_ferromagnetic_tc():
    # The duality claim made concrete: the AFM's T_N is *exactly* the FM's T_c (M04).
    from lab.m04 import TC_2D
    assert TC_AFM == TC_2D


# ── to_report ─────────────────────────────────────────────────────────────────
def _toy_result(tc_chi_refined=TC_AFM, max_abs_mag=0.02):
    T = [2.0, 2.1, 2.2, 2.3, 2.4]
    return M10Result(
        T=T,
        chi_staggered=[10.0, 40.0, 95.0, 38.0, 8.0],
        stag_mag=[0.9, 0.8, 0.5, 0.2, 0.1],
        stag_mag_err=[0.01] * 5,
        abs_mag=[0.01, 0.02, 0.015, 0.012, 0.01],   # uniform |m| stays ≈ 0
        energy=[-1.9, -1.8, -1.7, -1.5, -1.3],
        specific_heat=[1.0, 2.0, 5.0, 2.2, 0.9],
        L=128,
        tc_chi=2.2,
        tc_chi_refined=tc_chi_refined,
        tc_cv_refined=2.27,
        tc_benchmark=TC_AFM,
        rel_error=abs(tc_chi_refined - TC_AFM) / TC_AFM,
        max_abs_mag=max_abs_mag,
        wall_seconds=120.0,
        config={"L": 128, "J": -1.0, "lattice": "square-afm", "seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M10-afm-ising"
    assert not rep["experiment"].startswith("M01")
    # The structural discriminator: staggered susceptibility under chi_staggered,
    # and NO top-level "chi" (so check_m01, which reads "chi", is not-applicable).
    assert "chi_staggered" in rep
    assert "chi" not in rep
    assert rep["T"] == [2.0, 2.1, 2.2, 2.3, 2.4]
    assert rep["tc_benchmark"] == TC_AFM
    assert rep["L"] == 128
    # The AFM fingerprint: the uniform-|m| ceiling is carried and stays ≈ 0.
    assert rep["max_abs_mag"] == 0.02
    assert "headline" in rep and "Onsager exact" in rep["headline"]


def test_to_report_rel_error_zero_at_exact_tc():
    rep = to_report(_toy_result(tc_chi_refined=TC_AFM))
    assert rep["rel_error"] == 0.0
    assert rep["tc_chi_refined"] == TC_AFM
