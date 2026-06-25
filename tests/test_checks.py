"""The verification gate: a verified milestone must reproduce its number."""
import math

from lab.checks import (
    BETA_OVER_NU, GAMMA_OVER_NU, INV_NU, ONSAGER_TC, T_BKT, TC_3D, TC_TRI,
    TWO_OVER_PI, _grade, check_m01, check_m02, check_m03, check_m04, check_m05,
    check_m06, check_m07, check_m08, check_m09, verify,
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
