"""M04 specific-heat — the exact-T_c constants and the report serializer.

Mirrors ``tests/test_m03.py`` / ``tests/test_m06.py``: M04 has no analysis helper
of its own (it reuses m06's NumPy-only peak finders), so the falsifiable surface
here is the pair of analytic *constants* it publishes — Onsager's exact T_c and
the leading log-divergence amplitude — and ``to_report``'s JSON shape, the numbers
the public page and the M04 check consume. ``run_m04`` (the real 2D sweep) is never
invoked; only the pure constants + serializer are under test, keeping the suite
fast and CPU-only.
"""
import math

from lab.m04 import TC_2D, LOG_AMPLITUDE, to_report, M04Result


# ── constants (exact by construction) ─────────────────────────────────────────
def test_tc_2d_is_onsager_exact():
    # 2 / ln(1 + √2) — the same number M01 (magnetization) verified, computed the
    # SAME way, so the assertion is exact, not tolerance-bounded.
    assert TC_2D == 2.0 / math.log(1.0 + math.sqrt(2.0))
    assert abs(TC_2D - 2.269185314) < 1e-9


def test_log_amplitude_matches_onsager_leading_term():
    # A = (2/π)·(2/T_c)²  ≈ 0.4945 — carried for context, exact by construction.
    assert LOG_AMPLITUDE == (2.0 / math.pi) * (2.0 / TC_2D) ** 2
    assert abs(LOG_AMPLITUDE - 0.4945) < 1e-3


# ── to_report ─────────────────────────────────────────────────────────────────
def _toy_result(tc_cv_refined=TC_2D):
    T = [2.0, 2.1, 2.2, 2.3, 2.4]
    return M04Result(
        T=T,
        specific_heat=[1.0, 2.0, 5.0, 2.2, 0.9],
        energy=[-1.9, -1.8, -1.7, -1.5, -1.3],
        chi=[10.0, 40.0, 95.0, 38.0, 8.0],
        abs_mag=[0.9, 0.8, 0.5, 0.2, 0.1],
        abs_mag_err=[0.01] * 5,
        L=128,
        tc_cv=2.2,
        tc_cv_refined=tc_cv_refined,
        tc_chi_refined=2.27,
        tc_benchmark=TC_2D,
        rel_error=abs(tc_cv_refined - TC_2D) / TC_2D,
        log_amplitude=LOG_AMPLITUDE,
        wall_seconds=120.0,
        config={"L": 128, "seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M04-specific-heat"
    # A distinct tag so check_m01's χ-peak check skips it; not an M01 report.
    assert not rep["experiment"].startswith("M01")
    # Per-T arrays the page draws, passed through unchanged.
    assert rep["T"] == [2.0, 2.1, 2.2, 2.3, 2.4]
    assert len(rep["specific_heat"]) == len(rep["T"])
    # Headline numbers check_m04 re-derives.
    assert rep["tc_benchmark"] == TC_2D
    assert rep["log_amplitude"] == LOG_AMPLITUDE
    assert rep["L"] == 128
    assert "headline" in rep and "Onsager exact" in rep["headline"]


def test_to_report_rel_error_zero_at_exact_tc():
    # When the refined C-peak lands exactly on Onsager's T_c the reported rel. err
    # is identically 0 — the serializer echoes the result, it does not recompute.
    rep = to_report(_toy_result(tc_cv_refined=TC_2D))
    assert rep["rel_error"] == 0.0
    assert rep["tc_cv_refined"] == TC_2D
