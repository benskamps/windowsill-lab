"""M05 triangular-lattice Ising — the exact-T_c constant and the report serializer.

Mirrors ``tests/test_m04.py``: M05 reuses m06's NumPy-only peak finders, so the
falsifiable pure surface is the exact triangular critical temperature it publishes
(T_c = 4/ln 3, a *different* number from the square lattice's 2.2692 — the whole
point of the geometry change) and ``to_report``'s JSON shape. ``run_m05`` (the real
triangular sweep) is never invoked.
"""
import json
import math
from pathlib import Path

from lab.checks import check_m05
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


# ── the honeycomb half (added 2026-08-11) ─────────────────────────────────────
from lab.m05 import TC_HEX, to_report_hex  # noqa: E402


def test_tc_hex_is_two_over_ln_two_plus_root_three_exact():
    # 2 / ln(2 + √3) ≈ 1.518651 — computed the SAME way the module does, so exact.
    assert TC_HEX == 2.0 / math.log(2.0 + math.sqrt(3.0))
    assert abs(TC_HEX - 1.518651) < 1e-5


def test_the_three_exact_tc_order_by_coordination_number():
    """z = 3 (honeycomb) < 4 (square) < 6 (triangular) ⇒ T_c orders the same way.

    Fewer neighbours holding a spin in line means thermal noise breaks the order
    at a lower temperature. This is the one relation between M05's two numbers
    and M01's that has to hold on physics grounds, so it catches a transcription
    error in any of the three closed forms.
    """
    square = 2.0 / math.log(1.0 + math.sqrt(2.0))
    assert TC_HEX < square < TC_TRI
    # And they are genuinely three different numbers, not a rounding apart.
    assert square - TC_HEX > 0.7
    assert TC_TRI - square > 1.3


def _toy_hex_result(tc_chi_refined=TC_HEX):
    T = [1.40, 1.47, 1.52, 1.60, 1.68]
    return M05Result(
        T=T,
        chi=[12.0, 44.0, 99.0, 41.0, 9.0],
        abs_mag=[0.9, 0.8, 0.5, 0.2, 0.1],
        abs_mag_err=[0.01] * 5,
        energy=[-1.4, -1.3, -1.1, -0.9, -0.8],
        specific_heat=[1.0, 2.0, 5.0, 2.2, 0.9],
        L=128,
        tc_chi=1.52,
        tc_chi_refined=tc_chi_refined,
        tc_cv_refined=1.515,
        tc_benchmark=TC_HEX,
        rel_error=abs(tc_chi_refined - TC_HEX) / TC_HEX,
        wall_seconds=95.0,
        config={"L": 128, "lattice": "honeycomb", "seed": 42},
    )


def test_to_report_hex_shape_is_check_ready():
    rep = to_report_hex(_toy_hex_result())
    assert rep["experiment"] == "M05-hexagonal"
    assert rep["T"] == [1.40, 1.47, 1.52, 1.60, 1.68]
    assert len(rep["chi"]) == len(rep["T"])
    assert rep["tc_benchmark"] == TC_HEX
    assert rep["L"] == 128
    assert rep["config"]["lattice"] == "honeycomb"
    assert "2/ln(2+" in rep["headline"]


def test_hexagonal_and_triangular_reports_carry_distinct_tags_and_benchmarks():
    """The tag is load-bearing, not decoration: every downstream surface picks the
    exact T_c off it. If these two ever collided, a correct honeycomb run would be
    graded against 3.6410 and reported as a 58 % error."""
    tri = to_report(_toy_result())
    hexa = to_report_hex(_toy_hex_result())
    assert tri["experiment"] != hexa["experiment"]
    assert tri["tc_benchmark"] != hexa["tc_benchmark"]
    # Neither headline may quote the other lattice's closed form.
    assert "2/ln(2+" not in tri["headline"]
    assert "4/ln3" not in hexa["headline"]


def test_to_report_hex_rel_error_zero_at_exact_tc():
    rep = to_report_hex(_toy_hex_result(tc_chi_refined=TC_HEX))
    assert rep["rel_error"] == 0.0


def test_the_honeycomb_runner_records_the_device_so_receipts_label_hardware_honestly():
    """``hw()`` reads ``config["device"]`` and falls back to "CPU" when the key is
    missing — deliberately, so a run can never overclaim the GPU. The cost of
    omitting it is the opposite error, and it bit: the 2026-08-11 honeycomb run
    executed on CUDA and its first receipt headline read "33s on CPU". A real
    (tiny, CPU) run end-to-end, not a source inspection.
    """
    from lab.hw import hw
    from lab.m05 import run_m05_hex

    result = run_m05_hex(L=8, T_min=1.4, T_max=1.7, n_temps=5, n_sweeps=40,
                         n_burnin=10, device="cpu")
    rep = to_report_hex(result)
    assert rep["config"]["device"] == "cpu"
    assert hw(rep["config"]) == "CPU"
    assert "on CPU" in rep["headline"]

    # And the same config shape would label a CUDA run honestly.
    assert hw(dict(rep["config"], device="cuda")) == "GPU"
    # The failure mode itself, pinned: no device key ⇒ silently "CPU".
    no_device = {k: v for k, v in rep["config"].items() if k != "device"}
    assert hw(no_device) == "CPU"


# ── the committed honeycomb receipt: the number itself, pinned ────────────────
# The canonical 2026-08-11 honeycomb run (L=128, seed=42, 25 temperatures). Its
# headline T_c is a *published* number: it appears in the receipt, in
# MILESTONES.md, and in the PR that landed the honeycomb half. Nothing in the
# suite re-derived it from the artifact, so a change to the peak refinement, the
# equilibration guard, or the sweep itself could silently move the published
# value while every test stayed green. This pins it to the digit.
M05_HEX_RECEIPT = (
    Path(__file__).resolve().parents[1]
    / "reports" / "receipts" / "run-2026-08-11-2341-m05.json"
)
M05_HEX_TC_CHI_REFINED = 1.5322714093222762


def _hex_receipt() -> dict:
    return json.loads(M05_HEX_RECEIPT.read_text(encoding="utf-8"))


def test_the_committed_honeycomb_receipt_still_reports_its_published_tc():
    """Exact equality, not a tolerance: this is the artifact's own recorded float."""
    receipt = _hex_receipt()
    assert receipt["experiment"] == "M05-hexagonal"
    assert receipt["tc_chi_refined"] == M05_HEX_TC_CHI_REFINED


def test_the_published_honeycomb_tc_is_what_the_checker_re_derives():
    """Engine drift breaks the suite here.

    ``check_m05`` re-runs the guard and the parabola refinement over the receipt's
    own (T, χ) arrays. Its answer must land on the published headline — if a
    future change to the refinement or the guard moves the peak, this fails
    instead of quietly republishing a different number under the same claim.
    """
    ok, detail = check_m05(_hex_receipt())
    assert ok is True, detail
    re_derived = float(detail.split("T=")[1].split(" ")[0])
    assert abs(re_derived - M05_HEX_TC_CHI_REFINED) < 5e-4, detail


def test_the_published_honeycomb_tc_sits_just_above_the_exact_value():
    """The physics the number has to satisfy, independent of the recorded float:
    a finite-L χ peak is shifted *above* the infinite-volume T_c, by ≈1 %."""
    receipt = _hex_receipt()
    assert receipt["tc_benchmark"] == TC_HEX
    assert M05_HEX_TC_CHI_REFINED > TC_HEX
    assert (M05_HEX_TC_CHI_REFINED - TC_HEX) / TC_HEX < 0.02
    assert receipt["rel_error"] == abs(
        M05_HEX_TC_CHI_REFINED - TC_HEX) / TC_HEX


def test_the_committed_honeycomb_receipt_reruns_the_honeycomb():
    """The reproduction command must name the geometry the receipt records.

    ``lab m05`` sweeps the *triangular* lattice at T_c ≈ 3.641; publishing it on
    a honeycomb receipt sent anyone reproducing this measurement to a different
    experiment. Derived from the experiment tag as of 2026-08-12.
    """
    receipt = _hex_receipt()
    assert receipt["reproduction"]["rerun"] == "python -m lab.cli m05-hex"
    assert receipt["reproduction"]["regrade"] == "python -m lab.cli verify M05"
    assert receipt["config"]["lattice"] == "honeycomb"
