"""M11 2D Edwards–Anderson spin glass — the P(q) broadening trend and serializer.

Mirrors ``tests/test_m06.py``: ``broadening_trend`` is exercised against hand-built
⟨q²⟩(T) arrays with a KNOWN monotonicity, including an UNSORTED temperature axis (to
prove the internal argsort) and the ``n == 0`` single-point guard. The real
``run_m11`` / spin-glass engine is never invoked — only the NumPy-only trend reducer
+ serializer are under test.
"""
from lab.m11 import broadening_trend, to_report, M11Result


# ── broadening_trend — ⟨q²⟩ rises as T → 0 ────────────────────────────────────
def test_trend_detects_clean_broadening():
    # ⟨q²⟩ falls with rising T (= broadens as T → 0) at every step → (True, 1.0).
    T = [0.6, 1.0, 2.0]
    q2 = [0.5, 0.3, 0.1]
    monotone, frac = broadening_trend(T, q2)
    assert monotone is True
    assert frac == 1.0


def test_trend_sorts_by_temperature_first():
    # Same physics but the arrays arrive UNSORTED in T — the internal argsort must
    # still read a clean broadening. (Indices [1,2,0] sort T → 0.6,1.0,2.0.)
    T = [2.0, 0.6, 1.0]
    q2 = [0.1, 0.5, 0.3]
    monotone, frac = broadening_trend(T, q2)
    assert monotone is True
    assert frac == 1.0


def test_trend_partial_fraction_when_one_step_rises():
    # One of two ascending-T steps goes the wrong way → not monotone, frac 0.5.
    T = [0.6, 1.0, 2.0]
    q2 = [0.5, 0.6, 0.1]      # 0.5→0.6 rises (bad), 0.6→0.1 falls (good)
    monotone, frac = broadening_trend(T, q2)
    assert monotone is False
    assert frac == 0.5


def test_trend_single_point_guard():
    # The n == 0 guard: one temperature has no adjacent step → (False, 0.0).
    assert broadening_trend([1.0], [0.3]) == (False, 0.0)


# ── to_report ─────────────────────────────────────────────────────────────────
def _toy_result(monotone=True):
    T = [0.6, 1.0, 2.0]
    q2 = [0.5, 0.3, 0.1]
    return M11Result(
        T=T,
        q_bin_centers=[-1.0, 0.0, 1.0],
        pq=[[0.2, 0.6, 0.2], [0.25, 0.5, 0.25], [0.3, 0.4, 0.3]],
        q2_mean=q2,
        q4_mean=[0.3, 0.15, 0.05],
        q_abs_mean=[0.5, 0.4, 0.3],
        q_mean=[0.0, 0.0, 0.0],
        binder=[0.4, 0.3, 0.2],
        energy=[-1.8, -1.6, -1.4],
        L=16,
        n_realizations=64,
        monotone_broadening=monotone,
        broadening_fraction=1.0 if monotone else 0.5,
        q2_cold=0.5,
        q2_hot=0.1,
        max_abs_q_mean=0.0,
        pq_symmetry_resid=0.0,
        wall_seconds=300.0,
        config={"L": 16, "n_realizations": 64, "model": "edwards-anderson-2d"},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M11-spin-glass-2d"
    assert not rep["experiment"].startswith("M01")
    # M11 carries (T, ⟨q²⟩) + P(q) histograms — NO transition to locate.
    assert rep["T"] == [0.6, 1.0, 2.0]
    assert len(rep["q2_mean"]) == len(rep["T"])
    assert rep["monotone_broadening"] is True
    assert rep["q2_cold"] == 0.5 and rep["q2_hot"] == 0.1
    assert rep["n_realizations"] == 64
    assert "headline" in rep and "broadens toward T=0" in rep["headline"]


def test_to_report_failure_verdict_wording():
    rep = to_report(_toy_result(monotone=False))
    assert rep["monotone_broadening"] is False
    assert "broadening NOT reproduced" in rep["headline"]
