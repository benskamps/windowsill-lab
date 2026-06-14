"""The verification gate: a verified milestone must reproduce its number."""
from lab.checks import ONSAGER_TC, check_m01, verify


def _report(peak_at):
    """A toy Ising report whose χ peaks at temperature ``peak_at``."""
    T = [round(1.5 + 0.1 * i, 1) for i in range(21)]            # 1.5 … 3.5
    chi = [1.0 / (abs(t - peak_at) + 0.05) for t in T]          # sharp peak at peak_at
    return {"T": T, "chi": chi}


def test_m01_passes_near_onsager():
    ok, detail = check_m01(_report(round(ONSAGER_TC, 1)))
    assert ok, detail


def test_m01_fails_when_peak_is_wrong():
    ok, _ = check_m01(_report(3.2))
    assert not ok


def test_m01_fails_on_malformed_report():
    ok, detail = check_m01({"T": [1, 2, 3]})   # no chi
    assert not ok and "missing" in detail


def test_verify_runs_against_the_repo():
    # M01 is verified in MILESTONES.md and ships a real report → it must pass.
    results = {r["id"]: r for r in verify()}
    assert "M01" in results
    assert results["M01"]["status"] in ("pass", "no-report")
    if results["M01"]["status"] == "pass":
        assert "Onsager" in results["M01"]["detail"]


def test_verify_filters_by_id():
    assert verify(["ZZ99"]) == []   # not a verified milestone → nothing to do
