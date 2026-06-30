"""M09 2D Heisenberg / Mermin–Wagner — the drift-slope fit and the serializer.

Mirrors ``tests/test_m06.py``: ``drift_slope`` is exercised against ⟨|m|⟩(L) data
built as an EXACT linear function of 1/L, so least squares recovers the slope to
machine precision; the ``sxx <= 0`` guard (all-equal L) and the flat-line (genuine
order) case are pinned too. The real ``run_m09`` / Heisenberg engine is never
invoked — only the NumPy-only slope fit + serializer are under test.
"""
from lab.m09 import drift_slope, to_report, M09Result


# ── drift_slope — least-squares d⟨|m|⟩/d(1/L) ─────────────────────────────────
def test_slope_recovers_exact_linear_drift():
    # y = a + b·(1/L) with a=0.1, b=2.0 → the LS slope is exactly b for perfectly
    # linear data. Positive slope ⇒ |m| washes out as L grows (Mermin–Wagner).
    Ls = [16, 32, 64]
    a, b = 0.1, 2.0
    y = [a + b * (1.0 / L) for L in Ls]
    assert abs(drift_slope(Ls, y) - b) < 1e-12


def test_slope_zero_for_genuine_order_plateau():
    # A flat ⟨|m|⟩(L) (what spontaneous order would look like) → zero slope.
    assert drift_slope([16, 32, 64], [0.5, 0.5, 0.5]) == 0.0


def test_slope_sxx_guard_on_degenerate_L():
    # The sxx <= 0 guard: all-equal L gives 1/L with zero variance → slope 0.0,
    # not a divide-by-zero.
    assert drift_slope([32, 32, 32], [0.5, 0.4, 0.3]) == 0.0


# ── to_report ─────────────────────────────────────────────────────────────────
def _toy_result(monotone=True):
    L_values = [16, 32, 64]
    abs_mag = [0.30, 0.20, 0.12]
    ratios = [abs_mag[i + 1] / abs_mag[i] for i in range(len(abs_mag) - 1)]
    return M09Result(
        L_values=L_values,
        T=0.7,
        abs_mag=abs_mag,
        abs_mag_err=[0.001, 0.001, 0.001],
        chi=[1.0, 1.1, 1.2],
        energy=[-1.5, -1.4, -1.3],
        acceptance=[0.5, 0.5, 0.5],
        ratios=ratios,
        slope_vs_inv_L=drift_slope(L_values, abs_mag),
        monotone_decreasing=monotone,
        updater="metropolis",
        wall_seconds=90.0,
        config={"L_values": L_values, "T": 0.7, "model": "heisenberg", "seed": 42},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_result())
    assert rep["experiment"] == "M09-heisenberg"
    assert not rep["experiment"].startswith("M01")
    # M09 carries (L, ⟨|m|⟩) — NO transition to locate — and the drift verdict.
    assert rep["L_values"] == [16, 32, 64]
    assert len(rep["abs_mag"]) == len(rep["L_values"])
    assert rep["monotone_decreasing"] is True
    assert rep["slope_vs_inv_L"] > 0.0          # |m| washes out as L grows
    assert "headline" in rep and "confirmed" in rep["headline"]


def test_to_report_failure_verdict_wording():
    # A non-decreasing ⟨|m|⟩(L) → the honest "ABSENCE NOT reproduced" headline.
    rep = to_report(_toy_result(monotone=False))
    assert rep["monotone_decreasing"] is False
    assert "ABSENCE NOT reproduced" in rep["headline"]
