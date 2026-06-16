"""The verification gate: a verified milestone must reproduce its number."""
import math

from lab.checks import (
    BETA_OVER_NU, GAMMA_OVER_NU, INV_NU, ONSAGER_TC,
    _grade, check_m01, check_m02, check_m03, verify,
)


def _fss_report(slope=GAMMA_OVER_NU, A=0.4):
    """A synthetic M02 report whose χ_max follows χ_max = A·L^slope."""
    Ls = [32, 64, 128, 256, 512]
    return {
        "experiment": "M02-finite-size-scaling",
        "curves": [
            {"L": L, "chi_max": A * L ** slope, "T_peak": 2.27} for L in Ls
        ],
    }


def _ising_report(peak_at):
    """A toy Ising report whose χ peaks at temperature ``peak_at``."""
    T = [round(1.5 + 0.1 * i, 1) for i in range(21)]            # 1.5 … 3.5
    chi = [1.0 / (abs(t - peak_at) + 0.05) for t in T]          # sharp peak at peak_at
    return {"T": T, "chi": chi}


def test_m01_passes_near_onsager():
    ok, detail = check_m01(_ising_report(round(ONSAGER_TC, 1)))
    assert ok, detail


def test_m01_fails_when_peak_is_wrong():
    ok, _ = check_m01(_ising_report(3.2))
    assert ok is False


def test_m01_not_applicable_to_non_ising_report():
    ok, detail = check_m01({"some": "other experiment"})   # no T/chi
    assert ok is None and "not an Ising" in detail


def test_grade_skips_reports_the_check_cant_read():
    # Newest report first is unreadable; the check should fall through to the
    # Ising one rather than grading against the wrong file (bug #2).
    reports = [{"unrelated": True}, _ising_report(round(ONSAGER_TC, 1))]
    status, _ = _grade(check_m01, reports)
    assert status == "pass"


def test_grade_no_usable_report():
    status, _ = _grade(check_m01, [{"unrelated": True}])
    assert status == "no-report"


def test_verify_runs_against_the_repo():
    # M01 is verified in MILESTONES.md and ships a real report → it must pass.
    results = {r["id"]: r for r in verify()}
    assert "M01" in results
    assert results["M01"]["status"] in ("pass", "no-report")
    if results["M01"]["status"] == "pass":
        assert "Onsager" in results["M01"]["detail"]


def test_verify_filters_by_id():
    assert verify(["ZZ99"]) == []   # not a verified milestone → nothing to do


# ── M02: finite-size scaling check ───────────────────────────────────────────
def test_m02_passes_on_correct_scaling():
    ok, detail = check_m02(_fss_report(slope=GAMMA_OVER_NU))
    assert ok, detail
    assert "L^1.7" in detail   # measured slope near 7/4


def test_m02_fails_on_wrong_scaling():
    # A simulation scaling like L^1 (e.g. a bug) must be caught.
    ok, _ = check_m02(_fss_report(slope=1.0))
    assert ok is False


def test_m02_not_applicable_to_an_ising_report():
    ok, detail = check_m02(_ising_report(2.3))
    assert ok is None and "not a finite-size" in detail


def test_m01_skips_an_fss_report():
    # The two checks must not cross-grade: M01 reads T/chi, which an FSS report
    # deliberately omits at top level.
    ok, detail = check_m01(_fss_report())
    assert ok is None


def test_m02_needs_enough_sizes():
    short = {"experiment": "M02-finite-size-scaling",
             "curves": [{"L": 32, "chi_max": 10.0}, {"L": 64, "chi_max": 33.0}]}
    ok, _ = check_m02(short)
    assert ok is None   # fewer than 3 sizes → not gradable


# ── M03: data-collapse check ─────────────────────────────────────────────────
def _F(x):
    return 1.0 / (1.0 + math.exp(3.0 * x))


def _m03_report(beta_over_nu=BETA_OVER_NU, inv_nu=INV_NU, Ls=(16, 24, 32, 48)):
    """A synthetic M03 report built from the exact scaling form.

    M = L^(-β/ν)·F((T-Tc)·L^(1/ν)). A clean collapse by construction.
    """
    xs = [-2.0 + 4.0 * i / 39 for i in range(40)]
    curves = []
    for L in Ls:
        T = [ONSAGER_TC + x * L ** (-inv_nu) for x in xs]
        M = [L ** (-beta_over_nu) * _F(x) for x in xs]
        curves.append({"L": L, "T": T, "M": M})
    return {"experiment": "M03-data-collapse", "curves": curves}


def test_m03_passes_on_clean_collapse():
    ok, detail = check_m03(_m03_report())
    assert ok, detail
    assert "0.125" in detail   # recovered β/ν near 1/8


def test_m03_fails_on_degraded_collapse():
    # Curves built from the WRONG exponent don't collapse at β/ν=1/8 and the
    # independent re-fit reads ~0.4, so the check must fail.
    ok, _ = check_m03(_m03_report(beta_over_nu=0.4))
    assert ok is False


def test_m03_not_applicable_to_an_ising_report():
    ok, detail = check_m03(_ising_report(2.3))
    assert ok is None and "not a data-collapse" in detail


def test_m01_skips_an_m03_report():
    # M03 deliberately omits top-level T/chi, so the M01 check is not-applicable.
    ok, _ = check_m01(_m03_report())
    assert ok is None


def test_m03_needs_enough_sizes():
    rep = _m03_report(Ls=(16, 32))
    ok, _ = check_m03(rep)
    assert ok is None   # fewer than 3 sizes → not gradable
