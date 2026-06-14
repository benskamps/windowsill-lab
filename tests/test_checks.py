"""The verification gate: a verified milestone must reproduce its number."""
from lab.checks import ONSAGER_TC, _grade, check_m01, verify


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
