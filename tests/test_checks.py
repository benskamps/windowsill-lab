"""The verification gate: a verified milestone must reproduce its number."""
import json
import math
import statistics

import pytest

import lab.checks as checks
from lab.checks import (
    ALLEN_CAHN_EXPONENT, BETA_OVER_NU, GAMMA_OVER_NU, INV_NU, ONSAGER_TC, T_BKT,
    TC_3D, TC_SG_3D, TC_SG_3D_TOL, TC_TRI, TWO_OVER_PI, WANNIER_S0, WANNIER_S0_TOL,
    _grade, check_controls, check_m01, check_m02, check_m03, check_m04, check_m05,
    check_m06, check_m07, check_m08, check_m09, check_m10, check_m11, check_m12,
    check_m13, check_m14, check_m15, check_m17, verify,
)


def _tc_potts(q):
    return 1.0 / math.log(1.0 + math.sqrt(q))


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


def test_m01_gate_is_one_temperature_bin_not_two():
    ok, detail = check_m01(_ising_report(2.4))
    assert ok is False
    assert "±0.1" in detail


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


def test_verify_uses_public_receipts_in_a_clean_checkout(tmp_path, monkeypatch):
    """CI must regrade promoted work even when only compact evidence is tracked."""
    reports = tmp_path / "reports"
    receipts = reports / "receipts"
    lab_home = tmp_path / "lab-home"
    receipts.mkdir(parents=True)
    lab_home.mkdir()
    milestones = tmp_path / "MILESTONES.md"
    milestones.write_text("- [x] **M01** — Onsager gate\n", encoding="utf-8")
    (receipts / "run-2026-06-15-m01.json").write_text(
        json.dumps(_ising_report(round(ONSAGER_TC, 1))), encoding="utf-8",
    )

    monkeypatch.setattr(checks, "REPORTS_DIR", reports)
    monkeypatch.setattr(checks, "LAB_HOME", lab_home)
    monkeypatch.setattr(checks, "MILESTONES_MD", milestones)

    assert checks.verify() == [{
        "id": "M01",
        "status": "pass",
        "detail": checks.check_m01(_ising_report(round(ONSAGER_TC, 1)))[1],
    }]


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


# ── M06: 3D-Ising check ──────────────────────────────────────────────────────
def _m06_report(peak_at=TC_3D):
    """A toy 3D-Ising report whose χ peaks at temperature ``peak_at``."""
    T = [round(4.1 + 0.04 * i, 3) for i in range(21)]            # 4.1 … 4.9
    chi = [1.0 / (abs(t - peak_at) + 0.02) for t in T]          # sharp peak at peak_at
    return {"experiment": "M06-3d-ising", "T": T, "chi": chi}


def test_m06_passes_near_benchmark():
    ok, detail = check_m06(_m06_report(TC_3D))
    assert ok, detail
    assert "4.51" in detail   # cites the MC benchmark


def test_m06_fails_when_peak_is_wrong():
    # A transition located at the 2D T_c (≈2.27) — i.e. a dimensionality bug —
    # is nowhere near 4.5115 and must be caught. (Use an in-window wrong peak.)
    ok, _ = check_m06(_m06_report(4.2))
    assert ok is False


def test_m06_not_applicable_to_an_ising_report():
    ok, detail = check_m06(_ising_report(2.3))   # no experiment tag → 2D M01-shaped
    assert ok is None and "not a 3D-Ising" in detail


def test_m01_skips_an_m06_report():
    # THE cross-grading guard: an M06 report carries top-level T+chi but a 3D
    # T_c. The M01 check must NOT grade it against Onsager's 2D 2.269.
    ok, detail = check_m01(_m06_report(TC_3D))
    assert ok is None and "2D Ising" in detail


def _m04_report(peak_at=ONSAGER_TC):
    """A toy 2D-Ising report whose specific heat C(T) peaks at ``peak_at``."""
    T = [round(2.0 + 0.05 * i, 3) for i in range(13)]            # 2.0 … 2.6
    cv = [1.0 / (abs(t - peak_at) + 0.02) for t in T]           # sharp peak at peak_at
    return {"experiment": "M04-specific-heat", "T": T, "specific_heat": cv}


def test_m04_passes_near_tc():
    ok, detail = check_m04(_m04_report(ONSAGER_TC))
    assert ok, detail
    assert "2.269" in detail   # cites Onsager's exact 2D T_c


def test_m04_fails_when_peak_is_wrong():
    # A C peak well above T_c (beyond the ±0.1 finite-L tolerance) is a broken
    # thermal measurement and must be caught.
    ok, _ = check_m04(_m04_report(2.5))
    assert ok is False


def test_m04_not_applicable_to_an_m06_report():
    ok, detail = check_m04(_m06_report(TC_3D))
    assert ok is None and "not an M04" in detail


def test_m04_skips_a_bare_ising_report():
    # An M01-shaped report (χ, not specific_heat) is not an M04 report.
    ok, _ = check_m04(_ising_report(2.3))
    assert ok is None


def test_m01_still_grades_its_own_tagged_report():
    # The guard must let the real M01 tag through (render.py tags it
    # "M01-ising-verification"), not just untagged legacy dumps.
    rep = _ising_report(round(ONSAGER_TC, 1))
    rep["experiment"] = "M01-ising-verification"
    ok, detail = check_m01(rep)
    assert ok, detail


# ── M05: triangular-lattice Ising check ──────────────────────────────────────
def _m05_report(peak_at=TC_TRI):
    """A toy triangular-Ising report whose χ peaks at temperature ``peak_at``."""
    T = [round(3.3 + 0.03 * i, 3) for i in range(25)]           # 3.3 … 4.02
    chi = [1.0 / (abs(t - peak_at) + 0.02) for t in T]          # sharp peak at peak_at
    return {"experiment": "M05-triangular", "T": T, "chi": chi}


def test_m05_passes_near_tc():
    ok, detail = check_m05(_m05_report(TC_TRI))
    assert ok, detail
    assert "3.641" in detail   # cites the exact triangular T_c = 4/ln3


def test_m05_fails_when_peak_is_wrong():
    # A χ peak well off the triangular T_c (e.g. a wrong neighbour count or the
    # square checkerboard misused on this non-bipartite lattice) must be caught.
    ok, _ = check_m05(_m05_report(3.9))
    assert ok is False


def test_m05_not_applicable_to_an_m06_report():
    ok, detail = check_m05(_m06_report(TC_3D))
    assert ok is None and "not an M05" in detail


def test_m05_skips_a_bare_ising_report():
    # An M01-shaped report (no experiment tag) is not an M05 report — and M05's
    # T_c (3.641) is nowhere near the 2D square T_c, so cross-grading would be a bug.
    ok, _ = check_m05(_ising_report(2.3))
    assert ok is None


def test_m01_skips_an_m05_report():
    # THE cross-grading guard: an M05 report carries top-level T+chi but a
    # triangular T_c (3.641). The M01 check must NOT grade it against Onsager's
    # 2D square 2.269.
    ok, detail = check_m01(_m05_report(TC_TRI))
    assert ok is None and "2D Ising" in detail


# ── M07: q-state Potts check ─────────────────────────────────────────────────
def _q_chi(peak_at, T):
    """A χ(T) array with a sharp peak at temperature ``peak_at`` over grid ``T``."""
    return [1.0 / (abs(t - peak_at) + 0.01) for t in T]


def _m07_report(peaks=None):
    """A toy M07 report whose per-q χ peaks at each q's exact T_c by default.

    ``peaks`` optionally overrides the χ-peak location for a given q (to model a
    broken run). The synthetic T grid for each q is centred on that q's actual
    peak (T_c by default, or the override) so the χ array genuinely peaks where
    intended — the check re-derives the peak from the array, so the grid has to
    bracket it for the test to model what it claims.
    """
    peaks = peaks or {}
    per_q = []
    for q in (3, 4, 5, 6):
        tc = _tc_potts(q)
        peak_at = peaks.get(q, tc)
        # Centre the grid on the peak so the χ array's argmax really is peak_at.
        T = [round(peak_at - 0.12 + 0.01 * i, 4) for i in range(25)]
        per_q.append({
            "q": q,
            "T": T,
            "chi": _q_chi(peak_at, T),
            "tc_chi_refined": peak_at,
            "tc_exact": tc,
            "rel_error": abs(peak_at - tc) / tc,
            "transition": "continuous" if q <= 4 else "first-order",
        })
    return {"experiment": "M07-potts", "per_q": per_q}


def test_m07_passes_when_every_q_locates_its_tc():
    ok, detail = check_m07(_m07_report())
    assert ok, detail
    assert "q=3" in detail and "q=6" in detail   # grades all four q


def test_m07_fails_when_a_q_peak_is_wrong():
    # A q=5 transition placed far from its T_c (e.g. a non-ordering lattice or a
    # wrong order parameter) is well beyond even the widened ±0.15 first-order
    # tolerance and must be caught.
    ok, _ = check_m07(_m07_report(peaks={5: _tc_potts(5) - 0.5}))
    assert ok is False


def test_m07_first_order_tolerance_is_wider_than_continuous():
    # A q=5 (first-order) peak 0.12 off its T_c PASSES (±0.15), while the same
    # 0.12 offset on q=3 (continuous, ±0.1) would FAIL — the documented physical
    # allowance for stronger first-order finite-size effects, applied per q.
    ok_first, _ = check_m07(_m07_report(peaks={5: _tc_potts(5) + 0.12}))
    assert ok_first   # within the q≥5 ±0.15 band
    ok_cont, _ = check_m07(_m07_report(peaks={3: _tc_potts(3) + 0.12}))
    assert ok_cont is False   # outside the q≤4 ±0.1 band


def test_m07_not_applicable_to_an_m05_report():
    ok, detail = check_m07(_m05_report(TC_TRI))
    assert ok is None and "not an M07" in detail


def test_m07_skips_a_bare_ising_report():
    # An M01-shaped report (top-level T/chi, no per_q) is not an M07 report.
    ok, _ = check_m07(_ising_report(2.3))
    assert ok is None


def test_other_checks_skip_an_m07_report():
    # M07's per-q structure carries no top-level T/chi, so none of the single-peak
    # checks should claim it (they'd grade it against the wrong T_c otherwise).
    rep = _m07_report()
    assert check_m01(rep)[0] is None
    assert check_m04(rep)[0] is None
    assert check_m05(rep)[0] is None
    assert check_m06(rep)[0] is None


# ── M08: 2D XY BKT (helicity-modulus jump) check ─────────────────────────────
def _m08_report(crossing_at=T_BKT, slope=2.5):
    """A toy M08 report whose Υ(T) crosses the (2/π)·T jump line at ``crossing_at``.

    Builds a smooth, monotonically-decreasing Υ(T) that starts above the jump line
    (2/π)·T at low T and drops below it, engineered so g(T) = Υ(T) − (2/π)·T has a
    single downward root exactly at ``crossing_at``. We use a straight line of
    negative ``slope`` through the point (crossing_at, (2/π)·crossing_at): then
    g(T) = (2/π)·crossing_at − slope·(T − crossing_at) − (2/π)·T, which is zero at
    T = crossing_at and decreasing — a clean single crossing the check re-derives.
    The grid straddles ``crossing_at`` so the crossing is bracketed.
    """
    T = [round(0.6 + 0.02 * i, 4) for i in range(26)]            # 0.6 … 1.1
    Y = [TWO_OVER_PI * crossing_at - slope * (t - crossing_at) for t in T]
    return {"experiment": "M08-xy-bkt", "T": T, "helicity_modulus": Y}


def test_m08_passes_near_benchmark():
    ok, detail = check_m08(_m08_report(T_BKT))
    assert ok, detail
    assert "0.8929" in detail   # cites the BKT benchmark


def test_m08_fails_when_crossing_is_wrong():
    # A crossing well off T_BKT (beyond ±0.07) — e.g. the dropped 1/T fluctuation
    # term in the helicity estimator, the #1 XY failure mode — must be caught.
    ok, _ = check_m08(_m08_report(0.6))
    assert ok is False


def test_m08_fails_when_no_crossing():
    # A Υ(T) that never crosses the jump line (e.g. an un-equilibrated run that
    # stays frozen-high) is not a BKT signature and must fail, not silently pass.
    T = [round(0.6 + 0.02 * i, 4) for i in range(26)]
    # Υ pinned at 5.0 — always above (2/π)·T over [0.6,1.1], so g never goes negative.
    rep = {"experiment": "M08-xy-bkt", "T": T, "helicity_modulus": [5.0] * len(T)}
    ok, detail = check_m08(rep)
    assert ok is False and "never crosses" in detail


def test_m08_first_order_tolerance_band():
    # A crossing 0.05 above T_BKT PASSES (within ±0.07 — the documented
    # log-correction window), while 0.1 above FAILS.
    assert check_m08(_m08_report(T_BKT + 0.05))[0] is True
    assert check_m08(_m08_report(T_BKT + 0.10))[0] is False


def test_m08_not_applicable_to_an_m05_report():
    ok, detail = check_m08(_m05_report(TC_TRI))
    assert ok is None and "not an M08" in detail


def test_m08_skips_a_bare_ising_report():
    # An M01-shaped report (top-level T/chi, no helicity_modulus) is not M08.
    ok, _ = check_m08(_ising_report(2.3))
    assert ok is None


def test_other_checks_skip_an_m08_report():
    # M08 carries (T, helicity_modulus) but NO χ/specific_heat/per_q, and its tag
    # is M08-xy-bkt — so none of the single-peak / Potts checks should claim it.
    rep = _m08_report()
    assert check_m01(rep)[0] is None
    assert check_m04(rep)[0] is None
    assert check_m05(rep)[0] is None
    assert check_m06(rep)[0] is None
    assert check_m07(rep)[0] is None


# ── M09: 2D Heisenberg / Mermin–Wagner (⟨|m|⟩ drift) check ────────────────────
def _m09_report(abs_mag=(0.48, 0.29, 0.14), Ls=(16, 32, 64), err=0.005):
    """A toy M09 report with a per-L ⟨|m|⟩ sequence (drifting down by default).

    The check re-derives the monotone-decrease + positive 1/L slope from the
    (L_values, abs_mag) arrays, so overriding ``abs_mag`` models a broken run (a
    flat or rising sequence = a fake finite-T transition / a lattice that orders).
    """
    return {
        "experiment": "M09-heisenberg",
        "L_values": list(Ls),
        "abs_mag": list(abs_mag),
        "abs_mag_err": [err] * len(Ls),
        "T": 0.7,
    }


def test_m09_passes_when_abs_mag_drifts_down():
    # The Mermin–Wagner signature: ⟨|m|⟩ falls toward 0 as L grows → absence of
    # order reproduced. This is the rare milestone whose PASS is a negative result.
    ok, detail = check_m09(_m09_report((0.48, 0.29, 0.14)))
    assert ok, detail
    assert "Mermin" in detail or "drifts toward 0" in detail


def test_m09_fails_when_abs_mag_is_flat():
    # A plateau — ⟨|m|⟩ NOT decreasing with L — is what spontaneous order would
    # look like (a fake finite-T transition); the absence is NOT reproduced → fail.
    ok, _ = check_m09(_m09_report((0.30, 0.30, 0.30)))
    assert ok is False


def test_m09_fails_when_abs_mag_rises():
    # ⟨|m|⟩ growing with L is the strongest possible false positive (the #1 way
    # M09 ships wrong — a single-L read mistaken for order); it must be caught.
    ok, _ = check_m09(_m09_report((0.14, 0.29, 0.48)))
    assert ok is False


def test_m09_noise_floor_blocks_a_statistical_tie():
    # A "decrease" smaller than the Monte-Carlo noise floor (1.5·SEM) is not a real
    # drift; with large error bars a barely-lower point must NOT pass as order's absence.
    ok, _ = check_m09(_m09_report((0.300, 0.299, 0.298), err=0.05))
    assert ok is False


def test_m09_needs_enough_sizes():
    ok, _ = check_m09(_m09_report((0.4, 0.2), Ls=(16, 32)))
    assert ok is None   # fewer than 3 sizes → not gradable


def test_m09_not_applicable_to_an_m08_report():
    ok, detail = check_m09(_m08_report(T_BKT))
    assert ok is None and "not an M09" in detail


def test_m09_skips_a_bare_ising_report():
    # An M01-shaped report (top-level T/chi, no L_values/abs_mag family) is not M09.
    ok, _ = check_m09(_ising_report(2.3))
    assert ok is None


def test_other_checks_skip_an_m09_report():
    # M09 carries (L_values, abs_mag) but NO χ-vs-T / helicity / per_q, and its tag
    # is M09-heisenberg — so none of the transition-locating checks should claim it.
    rep = _m09_report()
    assert check_m01(rep)[0] is None
    assert check_m04(rep)[0] is None
    assert check_m05(rep)[0] is None
    assert check_m06(rep)[0] is None
    assert check_m07(rep)[0] is None
    assert check_m08(rep)[0] is None


# ── M10: antiferromagnetic Ising (staggered-χ peak) check ────────────────────
def _m10_report(peak_at=ONSAGER_TC, max_unif=0.02):
    """A toy M10 report whose STAGGERED χ_s peaks at ``peak_at``.

    ``max_unif`` sets the (flat) uniform ⟨|m|⟩ level — ≈0 models the real AFM (no
    net moment); a large value models the silent-sign-error masquerade where the
    model secretly reverted to the ferromagnet and the uniform moment ordered.
    """
    T = [round(2.0 + 0.025 * i, 4) for i in range(25)]          # 2.0 … 2.6
    chi = [1.0 / (abs(t - peak_at) + 0.02) for t in T]          # sharp staggered peak
    return {
        "experiment": "M10-afm-ising", "T": T, "chi_staggered": chi,
        "abs_mag": [max_unif] * len(T),
    }


def test_m10_passes_near_tn():
    ok, detail = check_m10(_m10_report(ONSAGER_TC))
    assert ok, detail
    assert "2.269" in detail   # cites Onsager's exact 2D T_c (= T_N)


def test_m10_fails_when_peak_is_wrong():
    # A staggered-χ peak well off T_N (e.g. a broken AFM that never Néel-orders)
    # is beyond the ±0.1 finite-L tolerance and must be caught.
    ok, _ = check_m10(_m10_report(2.5))
    assert ok is False


def test_m10_fails_when_uniform_moment_is_large():
    # THE headline AFM guard: a silent sign-flip that reverts the model to the FM
    # would still peak at 2.2692 — but on the UNIFORM moment (⟨|m|⟩ large at low T).
    # The staggered peak landing right but the uniform moment ordering must FAIL.
    ok, detail = check_m10(_m10_report(ONSAGER_TC, max_unif=0.9))
    assert ok is False
    assert "FM" in detail or "uniform moment too large" in detail


def test_m10_not_applicable_to_an_m05_report():
    ok, detail = check_m10(_m05_report(TC_TRI))
    assert ok is None and "not an M10" in detail


def test_m10_skips_a_bare_ising_report():
    # An M01-shaped report carries top-level T/chi, not chi_staggered → not M10.
    ok, _ = check_m10(_ising_report(2.3))
    assert ok is None


def test_other_checks_skip_an_m10_report():
    # M10 carries (T, chi_staggered) but NO top-level chi/specific_heat/per_q, and
    # its tag is M10-afm-ising — so none of the other checks should claim it. In
    # particular check_m01 (reads top-level `chi`) is not-applicable by structure.
    rep = _m10_report()
    assert check_m01(rep)[0] is None
    assert check_m04(rep)[0] is None
    assert check_m05(rep)[0] is None
    assert check_m06(rep)[0] is None
    assert check_m07(rep)[0] is None
    assert check_m08(rep)[0] is None
    assert check_m09(rep)[0] is None


# ── M11: 2D Edwards–Anderson spin glass · P(q) broadening (T_c = 0) ───────────
def _m11_report(q2_cold=0.45, q2_hot=0.03, max_abs_q=0.02, n_temps=8):
    """A synthetic M11 report whose ⟨q²⟩ rises smoothly as T → 0 (P(q) broadens).

    Temperatures ascend; ⟨q²⟩ interpolates linearly from ``q2_cold`` (lowest T) down
    to ``q2_hot`` (highest T), so the disorder-averaged overlap second moment grows
    as T falls — the 2D-EA broadening signature. ``q_mean`` is ≈0 (the symmetry /
    equilibration diagnostic).
    """
    T = [round(0.2 + (2.0 - 0.2) * i / (n_temps - 1), 3) for i in range(n_temps)]
    # q2 decreasing in T (so increasing toward T→0): cold→hot across ascending T.
    q2 = [round(q2_cold + (q2_hot - q2_cold) * i / (n_temps - 1), 4) for i in range(n_temps)]
    q_mean = [(-1) ** i * max_abs_q for i in range(n_temps)]   # small, alternating sign
    return {
        "experiment": "M11-spin-glass-2d",
        "T": T, "q2_mean": q2, "q_mean": q_mean,
        "max_abs_q_mean": max(abs(v) for v in q_mean),
    }


def test_m11_passes_on_clean_broadening():
    ok, detail = check_m11(_m11_report())
    assert ok, detail
    assert "broadens toward the T=0" in detail


def test_m11_fails_when_pq_does_not_broaden():
    # A flat ⟨q²⟩ (cold ≈ hot) is NOT the expected broadening — must fail.
    ok, _ = check_m11(_m11_report(q2_cold=0.05, q2_hot=0.04))
    assert ok is False


def test_m11_fails_on_inverted_trend():
    # ⟨q²⟩ shrinking as T → 0 (the wrong sign — e.g. a broken overlap) must fail.
    ok, _ = check_m11(_m11_report(q2_cold=0.03, q2_hot=0.45))
    assert ok is False


def test_m11_fails_on_broken_symmetry():
    # ⟨q²⟩ broadens, but a large |⟨q⟩| means an un-equilibrated / symmetry-broken
    # replica leaked through — the symmetry guard must fail it even so.
    ok, detail = check_m11(_m11_report(max_abs_q=0.4))
    assert ok is False
    assert "symmetric" in detail or "equilibrated" in detail


def test_m11_not_applicable_to_an_m10_report():
    ok, detail = check_m11(_m10_report())
    assert ok is None and "not an M11" in detail


def test_m11_needs_enough_temperatures():
    rep = _m11_report(n_temps=2)
    ok, _ = check_m11(rep)
    assert ok is None   # fewer than 3 temperatures → not gradable


# ── M12: 3D Edwards–Anderson spin glass · Binder crossing (±J benchmark) ─────
def _m12_report(t_sg=TC_SG_3D, max_abs_q=0.02, n_temps=7, sizes=(4, 6, 8), crossing=True):
    """A synthetic M12 report whose g_L(T) curves cross cleanly at ``t_sg``.

    Below the crossing the larger lattice is more ordered (higher g); above it, less —
    so ``d = g_large − g_small`` runs + → − through ``t_sg``, the check's crossing rule.
    ``crossing=False`` makes every size identical (parallel, no intersection) — the
    smeared/under-equilibrated failure the check must reject.
    """
    T = [round(0.4 + (1.6 - 0.4) * i / (n_temps - 1), 3) for i in range(n_temps)]
    binder_by_L = {}
    q_mean_by_L = {}
    for L in sizes:
        if crossing:
            binder_by_L[str(L)] = [round(0.5 + (t_sg - t) * (0.4 + 0.15 * L), 5) for t in T]
        else:
            binder_by_L[str(L)] = [0.3 for _ in T]   # flat & identical → no crossing
        q_mean_by_L[str(L)] = [(-1) ** i * max_abs_q for i in range(n_temps)]
    return {
        "experiment": "M12-spin-glass-3d",
        "T": T,
        "binder_by_L": binder_by_L,
        "q_mean_by_L": q_mean_by_L,
        "t_sg_benchmark": t_sg,
        "tolerance": TC_SG_3D_TOL,
    }


def test_m12_passes_on_clean_crossing():
    ok, detail = check_m12(_m12_report())
    assert ok, detail
    assert "cross near T_SG" in detail


def test_m12_fails_when_no_crossing_resolved():
    # Flat, identical g_L(T) → no multi-L intersection → the smeared/under-equilibrated
    # failure mode. Must fail (not pass on a flat curve), and say so.
    ok, detail = check_m12(_m12_report(crossing=False))
    assert ok is False
    assert "no multi-L Binder crossing" in detail


def test_m12_fails_when_crossing_far_from_benchmark():
    # A clean crossing, but at 0.4 — well outside the check-owned band around the
    # benchmark. Must fail. (The assertion tracks the constant, not a literal.)
    ok, detail = check_m12(_m12_report(t_sg=0.4))
    assert ok is False
    assert f"far from the {TC_SG_3D:.2f} benchmark" in detail


def test_m12_fails_on_broken_symmetry():
    # Curves cross at 0.95, but a large |⟨q⟩| means a symmetry-broken / un-equilibrated
    # replica leaked through — the symmetry guard must fail it.
    ok, detail = check_m12(_m12_report(max_abs_q=0.4))
    assert ok is False
    assert "symmetric" in detail


def test_m12_uses_own_tolerance_not_the_reports():
    # A report can't widen its own tolerance to pass: even if it claims tolerance=1.0,
    # the check uses its OWN ±0.15 band, so a crossing at 0.4 still fails.
    rep = _m12_report(t_sg=0.4)
    rep["tolerance"] = 1.0
    ok, _ = check_m12(rep)
    assert ok is False


def test_m12_not_applicable_to_an_m11_report():
    ok, detail = check_m12(_m11_report())
    assert ok is None and "not an M12" in detail


def test_m12_needs_three_sizes():
    rep = _m12_report(sizes=(4, 6))
    ok, _ = check_m12(rep)
    assert ok is None   # fewer than 3 lattice sizes → not gradable


def test_other_checks_skip_an_m11_report():
    # M11 carries (T, q2_mean) but NO top-level chi/specific_heat/per_q/helicity, and
    # its tag is M11-spin-glass-2d — so none of the transition-locating checks claim it.
    rep = _m11_report()
    assert check_m01(rep)[0] is None
    assert check_m04(rep)[0] is None
    assert check_m08(rep)[0] is None
    assert check_m09(rep)[0] is None
    assert check_m10(rep)[0] is None


# ── M13: frustrated triangular antiferromagnet · residual entropy (Wannier 0.3383) ──
def _schottky_C(T, gap=1.0, g0=1.0, g1=1.0):
    x = gap / T
    ex = math.exp(-x)
    return x * x * g0 * g1 * ex / (g0 + g1 * ex) ** 2


def _m13_report(g1=0.426, e_ground=-1.0):
    """A synthetic M13 report whose C(T) is an analytic two-level (Schottky) curve tuned so
    that ∫ C/T (from S∞ = ln2) leaves a KNOWN residual: g1=0.426 → 0.3383 (Wannier), while
    other g1 shift it away. The check integrates C/T itself, so a controllable analytic
    curve is the cleanest grader input — no engine, exact target. ``e_ground`` sets the
    cold-end energy the ground-state anchor reads (exact triangular-AFM value is −1)."""
    lo, hi, n = math.log(0.03), math.log(30.0), 220
    T = [math.exp(lo + (hi - lo) * i / (n - 1)) for i in range(n)]
    C = [_schottky_C(t, 1.0, 1.0, g1) for t in T]
    energy = [e_ground] + [e_ground + 0.2 * i for i in range(len(T) - 1)]
    return {"experiment": "M13-triangular-afm", "T": T, "specific_heat": C, "energy": energy}


def test_m13_passes_on_wannier_residual():
    ok, detail = check_m13(_m13_report())
    assert ok, detail
    assert "reproduced" in detail


def test_m13_fails_when_residual_too_high():
    # g1=0.05 removes almost no entropy → residual ≈ 0.64, far above 0.3383. Must fail.
    ok, detail = check_m13(_m13_report(g1=0.05))
    assert ok is False
    assert "misses 0.3383" in detail


def test_m13_fails_when_residual_too_low():
    # g1=1.0 removes the full ln2 → residual ≈ 0 (a non-degenerate ground state). Must fail.
    ok, detail = check_m13(_m13_report(g1=1.0))
    assert ok is False


def test_m13_fails_on_wrong_ground_energy():
    # Residual is right (Wannier) but the cold energy is −3 (an accidental ferromagnet):
    # the independent ground-state anchor must reject it even with a perfect integral.
    ok, detail = check_m13(_m13_report(e_ground=-3.0))
    assert ok is False
    assert "ground energy" in detail.lower()


def test_m13_re_derives_not_echoes():
    # The check integrates C/T from the arrays; a lie in a stored s0_measured is ignored.
    rep = _m13_report()
    rep["s0_measured"] = 0.999
    ok, _ = check_m13(rep)
    assert ok is True


def test_m13_needs_parallel_arrays():
    rep = _m13_report()
    rep["specific_heat"] = rep["specific_heat"][:5]   # length mismatch → not gradable
    ok, _ = check_m13(rep)
    assert ok is None


def test_m13_not_applicable_to_an_m12_report():
    ok, detail = check_m13(_m12_report())
    assert ok is None and "not an M13" in detail


def test_other_checks_skip_an_m13_report():
    # M13 carries (T, specific_heat, energy) with tag M13-triangular-afm — no χ/crossing/
    # helicity check should claim it (a bare-Ising χ check keys on a `chi` array it lacks).
    rep = _m13_report()
    assert check_m04(rep)[0] is None
    assert check_m05(rep)[0] is None
    assert check_m10(rep)[0] is None
    assert check_m12(rep)[0] is None


# ── M15 — Glauber domain-growth exponent (stdlib grading, mirrors the m13/m14 pattern) ──
def _m15_report(n=0.485, L_box=512, k=52):
    """A synthetic M15 report with a clean power law L_c(t) = 1.2*t^n (stdlib only), carrying
    the scaling-window rule the check re-reads. The check re-selects the window and re-fits the
    exponent from these arrays, so a clean t^n curve is graded by its recomputed slope."""
    lo, hi = math.log(1.0), math.log(8000.0)
    ts = sorted({int(round(math.exp(lo + (hi - lo) * i / (k - 1)))) for i in range(k)})
    Lc = [1.2 * t ** n for t in ts]
    return {
        "experiment": "M15-glauber-domain-growth",
        "L": L_box,
        "times": [float(t) for t in ts],
        "L_corr": Lc,
        "exponent": n,                      # a stored number the check must NOT trust blindly
        "t_fit_min": 20, "l_min_fit": 4.0, "sat_frac": 0.20,
    }


def test_check_m15_passes_a_clean_allen_cahn_half():
    ok, detail = check_m15(_m15_report(n=0.485))
    assert ok is True
    assert "0.48" in detail and str(ALLEN_CAHN_EXPONENT) in detail


def test_check_m15_is_a_receipt_not_an_echo():
    # A lie in the stored exponent must not flip the grade — the recomputed slope decides.
    rep = _m15_report(n=0.49)
    rep["exponent"] = 0.001
    assert check_m15(rep)[0] is True
    rep2 = _m15_report(n=0.25)
    rep2["exponent"] = 0.5                  # a flattering lie on a diffusive run
    assert check_m15(rep2)[0] is False


def test_check_m15_rejects_diffusive_and_ballistic_exponents():
    assert check_m15(_m15_report(n=0.25))[0] is False    # diffusive ¼ — off the ½ band
    assert check_m15(_m15_report(n=1.0))[0] is False      # ballistic 1 — off the ½ band


def test_check_m15_admits_the_documented_low_bias():
    # The finite-time effective exponent honestly sits a few percent below ½; the band admits it.
    assert check_m15(_m15_report(n=0.46))[0] is True


def test_check_m15_ignores_foreign_reports():
    assert check_m15({"experiment": "M13-triangular-afm"})[0] is None
    assert check_m15({"experiment": "M01-ising-verification", "T": [1, 2], "chi": [1, 2]})[0] is None


# ══ Checker hardening: re-derive from raw arrays, fail closed, survive bad files ══
#
# Negative controls for the fail-open / echo / crash holes: each test below models a
# hostile or broken report that used to grade green (or kill the gate) and asserts it
# now grades as a NAMED failure — plus a healthy-report control per fix proving the
# tightened guard is inert on clean data.


# ── M12 benchmark: the check must grade the model the engine simulates ────────
def test_m12_benchmark_mirrors_the_engine_constant():
    # The engine draws bimodal ±J couplings and owns the literature benchmark in
    # m12.py; the check's mirror must be the SAME number, or the headline and the
    # verify gate disagree about what counts as the transition.
    # lab.m12 imports numpy at module scope; the stdlib-only pipeline job skips
    # this mirror — the full-deps physics job still enforces it on every run.
    pytest.importorskip("numpy")
    import lab.m12 as m12
    assert TC_SG_3D == m12.T_SG_BENCHMARK
    assert TC_SG_3D_TOL == m12.CROSSING_TOL


def test_m12_gaussian_value_fails_the_bimodal_band():
    # Katzgraber–Körner–Young give 0.951(9) for GAUSSIAN disorder and 1.120(4) for
    # the bimodal ±J model this engine simulates (HPV refine: 1.1019(29)). A
    # crossing at the Gaussian value must FAIL, and one at the ±J value must PASS.
    ok_gauss, _ = check_m12(_m12_report(t_sg=0.95))
    assert ok_gauss is False
    ok_bimodal, detail = check_m12(_m12_report(t_sg=1.102))
    assert ok_bimodal is True, detail


# ── CTRL: re-derived cross-updater delta + null prominence ────────────────────
def _controls_report(mv=-1.40, wv=-1.41, chi_peak=1.0):
    """A synthetic CTRL report with raw per-entry updater values and a raw null χ.

    ``chi_peak`` scales an interior spike on an otherwise flat 1/T curve, so the
    re-derivable peak/median prominence is controllable (1.0 = flat, healthy null).
    The summary fields (delta / peak_to_median_ratio) are derived from the raw
    values exactly as the producer derives them; tests tamper from there.
    """
    T = [1.6, 1.9, 2.1, 2.269, 2.45, 2.7, 3.0]
    chi = [1.0 / t for t in T]
    chi[3] = chi_peak * chi[3]
    entries = []
    for T_e in (1.8, 3.2):
        for obs in ("energy", "abs_mag"):
            entries.append({
                "name": "wolff-vs-metropolis", "T": T_e, "L": 16,
                "observable": obs, "metropolis": mv, "wolff": wv,
                "delta": abs(mv - wv), "tol": 0.15,
            })
    return {
        "experiment": "CTRL-published-controls",
        "controls": entries,
        "null_control": {
            "name": "null-coupling-J0-flat-chi", "L": 16, "T": T, "chi": chi,
            "peak_to_median_ratio": max(chi) / statistics.median(chi),
            "ratio_max": 2.5,
        },
    }


def test_controls_healthy_report_passes():
    ok, detail = check_controls(_controls_report())
    assert ok is True, detail


def test_controls_report_cannot_widen_its_own_tolerance():
    # THE demonstrated false green: raw updater values 1.3 apart (badly broken)
    # under a hostile tol=99. The check re-derives |metropolis − wolff| against its
    # OWN band, so the report-carried tolerance must be powerless.
    rep = _controls_report(mv=-1.5, wv=-0.2)
    for e in rep["controls"]:
        e["tol"] = 99.0
    ok, detail = check_controls(rep)
    assert ok is False
    assert "✗" in detail or "failed" in detail


def test_controls_rederive_delta_from_raw_values_not_the_echo():
    # A report carrying delta=0.0 that contradicts its own raw metropolis/wolff
    # values must fail — the raw arrays decide, never the echoed summary.
    rep = _controls_report(mv=-1.5, wv=-0.2)
    for e in rep["controls"]:
        e["delta"] = 0.0
    ok, _ = check_controls(rep)
    assert ok is False


def test_controls_null_rederived_from_chi_not_ratio_fields():
    # The null χ genuinely grew a ~40× interior peak; hostile summary fields claim
    # ratio 40 ≤ ratio_max 50. The re-derived prominence must fail it.
    rep = _controls_report(chi_peak=40.0)
    rep["null_control"]["ratio_max"] = 50.0
    ok, _ = check_controls(rep)
    assert ok is False


def test_controls_fail_closed_when_null_chi_missing():
    # No raw χ array = the negative control cannot be re-derived = a named
    # failure, never a silent pass on the echoed ratio.
    rep = _controls_report()
    del rep["null_control"]["chi"]
    ok, _ = check_controls(rep)
    assert ok is False


def test_controls_need_two_gradable_raw_entries():
    # Entries without raw metropolis/wolff values cannot be re-derived; with fewer
    # than two gradable entries the report is not applicable — never a pass.
    rep = _controls_report()
    for e in rep["controls"][1:]:
        del e["metropolis"]
    ok, _ = check_controls(rep)
    assert ok is None


def test_controls_fail_on_a_self_contradictory_summary():
    # Raw values agree, but the carried delta wildly disagrees with them: a
    # receipt that contradicts its own raw arrays is malformed evidence.
    rep = _controls_report()
    rep["controls"][0]["delta"] = 0.9
    ok, _ = check_controls(rep)
    assert ok is False


# ── M11/M12: missing symmetry evidence fails closed ───────────────────────────
def test_m11_fails_closed_without_symmetry_evidence():
    # No q_mean array AND no max_abs_q_mean scalar: the P(q)=P(−q) guard has
    # nothing to grade. That must be a named failure, not a default-0.0 pass.
    rep = _m11_report()
    del rep["q_mean"]
    del rep["max_abs_q_mean"]
    ok, detail = check_m11(rep)
    assert ok is False
    assert "symmetry" in detail or "equilibration" in detail


def test_m11_scalar_symmetry_fallback_still_grades():
    # Only the scalar diagnostic present (older reports): still graded, not failed.
    rep = _m11_report()
    del rep["q_mean"]
    ok, detail = check_m11(rep)
    assert ok is True, detail


def test_m12_fails_closed_without_symmetry_evidence():
    rep = _m12_report()
    del rep["q_mean_by_L"]
    ok, detail = check_m12(rep)
    assert ok is False
    assert "symmetry" in detail or "equilibration" in detail


# ── M12: PT health re-derived from the raw attempt counters ───────────────────
def test_m12_rederives_pt_health_from_raw_attempt_counters():
    # The pt_health strings claim "ok", but the RAW counters show gaps 1 and 3
    # never attempted — the fragmented-ladder signature of the parity bug. The
    # check must re-derive from the counters, not trust the strings.
    rep = _m12_report()
    rep["swap_attempts_by_L"] = {"4": [6, 0, 6, 0, 6],
                                 "6": [6, 6, 6, 6, 6], "8": [6, 6, 6, 6, 6]}
    rep["pt_health_by_L"] = {"4": "ok", "6": "ok", "8": "ok"}
    ok, detail = check_m12(rep)
    assert ok is False
    assert "never" in detail and "L=4" in detail


def test_m12_malformed_attempt_counters_fail_closed():
    rep = _m12_report()
    rep["swap_attempts_by_L"] = {"4": "not-a-list"}
    ok, _ = check_m12(rep)
    assert ok is False


def test_m12_all_zero_counters_mean_pt_off_not_fragmented():
    # Mirrors the engine's own health rule: swap_every=0 records zero attempts at
    # EVERY gap ("off"); only the partial pattern is fragmented scheduling. A
    # PT-off run is still graded by the crossing + symmetry guards.
    rep = _m12_report()
    rep["swap_attempts_by_L"] = {L: [0, 0, 0, 0, 0] for L in ("4", "6", "8")}
    ok, _ = check_m12(rep)
    assert ok is True


# ── M17: a growth-only report grades, never crashes ───────────────────────────
def _m17_curves(ts=None):
    ts = ts or [float(t) for t in range(1, 2001, 40)]
    def curve(b, amp=2.0):
        return {"times": list(ts), "width": [amp * t ** b for t in ts]}
    return ts, curve


def _m17_growth_only_report():
    """Three clean growth curves, NO saturation table, NO distributions — the
    shape a partial/interrupted M17 run ships."""
    _, curve = _m17_curves()
    return {
        "experiment": "M17-kpz-growth",
        "growth": {"kpz": curve(1.0 / 3.0), "ew": curve(0.25), "rd": curve(0.5)},
    }


def _m17_full_report():
    """A synthetic M17 report every graded probe passes: exact-exponent curves,
    the RD closed form w²=p(1−p)t exactly, an α=1/2 saturation table, and the
    correct Tracy–Widom skewness per geometry."""
    ts, curve = _m17_curves()
    rd = curve(0.5, amp=0.5)                      # w = 0.5·t^½ → w² = 0.25·t
    rd["width_sq"] = [0.25 * t for t in ts]       # exactly p(1−p)t at p=0.5
    return {
        "experiment": "M17-kpz-growth",
        "growth": {"kpz": curve(1.0 / 3.0), "ew": curve(0.25), "rd": rd},
        "saturation": [{"L": L, "w_sat": 0.9 * L ** 0.5} for L in (64, 128, 256, 512)],
        "distributions": {"droplet": {"skewness": -0.2241},
                          "flat": {"skewness": -0.2935}},
        "config": {"p_flip": 0.5},
    }


def test_m17_full_synthetic_report_passes():
    ok, detail = check_m17(_m17_full_report())
    assert ok is True, detail


def test_m17_growth_only_report_grades_instead_of_crashing():
    # No saturation table → α is None. That used to TypeError inside the detail
    # format string and (without isolation) kill the whole verify gate. It must
    # grade as a named failure instead.
    ok, detail = check_m17(_m17_growth_only_report())
    assert ok is False
    assert "α=—" in detail or "saturation" in detail


# ── M15/M17: the fit window belongs to the check ──────────────────────────────
def test_m15_report_cannot_choose_its_own_window():
    # The window is as powerful a dial as the tolerance on a slightly curved
    # log-log line; out-of-bounds window params must grade FAIL, not be honoured.
    rep = _m15_report(n=0.485)
    rep["sat_frac"] = 0.9                          # drags the fit across the knee
    ok, detail = check_m15(rep)
    assert ok is False
    assert "window" in detail.lower()
    rep2 = _m15_report(n=0.485)
    rep2["t_fit_min"] = 500                        # cherry-picks the late tail
    assert check_m15(rep2)[0] is False


def test_m15_default_window_reports_still_grade():
    # The module-default window params (what real reports store) stay in bounds.
    ok, detail = check_m15(_m15_report(n=0.485))
    assert ok is True, detail


def test_m17_report_cannot_choose_its_own_window():
    rep = _m17_full_report()
    rep["w_fit_min"] = 0.2                         # below the check-owned band
    ok, detail = check_m17(rep)
    assert ok is False
    assert "window" in detail.lower()
    rep2 = _m17_full_report()
    rep2["t_fit_min"] = 500.0
    assert check_m17(rep2)[0] is False


# ── M14: an off-line point is breakage evidence, not inapplicability ──────────
def _m14_report(n_pts=4, off_line=()):
    """A synthetic M14 report whose points sit exactly ON the Nishimori line with
    the exact energy E/N = −2·tanh(1/T); indices in ``off_line`` get their T pushed
    off the line — the broken-wiring signature the on-line guard exists to catch."""
    pts = []
    for i in range(n_pts):
        p = 0.04 + 0.02 * i
        T = 1.0 / math.atanh(1.0 - 2.0 * p)
        pts.append({"p": p, "T": T, "energy": -2.0 * math.tanh(1.0 / T)})
    for i in off_line:
        pts[i]["T"] *= 1.5
    return {"experiment": "M14-random-bond-nishimori", "calibration_points": pts}


def test_m14_healthy_line_passes():
    ok, detail = check_m14(_m14_report())
    assert ok is True, detail


def test_m14_off_line_points_fail_never_fall_through():
    # Every point off the line (broken T/p wiring). Before hardening this returned
    # None (“<3 gradable”) and _grade silently fell through to an OLDER report; the
    # newest report's breakage evidence must grade FAIL instead.
    broken = _m14_report(off_line=(0, 1, 2, 3))
    ok, detail = check_m14(broken)
    assert ok is False
    assert "off the nishimori line" in detail.lower()
    status, _ = _grade(check_m14, [broken, _m14_report()])
    assert status == "fail"


def test_m14_structurally_missing_points_still_not_applicable():
    # None stays reserved for reports that structurally lack the evidence.
    assert check_m14({"experiment": "M14-random-bond-nishimori"})[0] is None
    assert check_m14(_m14_report(n_pts=2))[0] is None


# ── verify(): one bad file degrades to a named row, never kills the gate ──────
def test_verify_survives_unreadable_report_files(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    receipts = reports / "receipts"
    lab_home = tmp_path / "lab-home"
    receipts.mkdir(parents=True)
    lab_home.mkdir()
    milestones = tmp_path / "MILESTONES.md"
    milestones.write_text("- [x] **M01** — Onsager gate\n", encoding="utf-8")
    (receipts / "run-2026-06-15-m01.json").write_text(
        json.dumps(_ising_report(round(ONSAGER_TC, 1))), encoding="utf-8")
    (receipts / "run-2026-06-16-m01.json").write_text(
        '{"experiment": "M01-isi', encoding="utf-8")        # truncated mid-write
    (receipts / "run-2026-06-17-m01.json").write_text(
        "[1, 2, 3]", encoding="utf-8")                      # parses, not an object

    monkeypatch.setattr(checks, "REPORTS_DIR", reports)
    monkeypatch.setattr(checks, "LAB_HOME", lab_home)
    monkeypatch.setattr(checks, "MILESTONES_MD", milestones)

    results = checks.verify()
    unreadable = {r["id"] for r in results if r["status"] == "unreadable"}
    assert unreadable == {"run-2026-06-16-m01.json", "run-2026-06-17-m01.json"}
    m01 = [r for r in results if r["id"] == "M01"]
    assert m01 and m01[0]["status"] == "pass"               # the gate kept grading


def test_grade_surfaces_a_crashing_checker_as_a_named_fail():
    def boom(rep):
        raise ValueError("kaboom")
    status, detail = _grade(boom, [{"experiment": "X"}])
    assert status == "fail"
    assert "checker crashed" in detail and "kaboom" in detail
