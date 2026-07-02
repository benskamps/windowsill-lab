"""M13 frustrated triangular antiferromagnet — the entropy integrator, the engine, the check.

Three layers, matching the house style (cf. ``test_m12.py`` + ``test_m10.py``):

* **The integration primitive** (``entropy.py``) is validated *against exactly-known
  analytic curves* — the whole method is new to the lab, so the integrator is pinned
  before it is ever pointed at Monte-Carlo data. A Schottky two-level specific heat
  integrates to its exact total entropy change, and a two-level system with a
  *degenerate* ground state recovers a known **non-zero residual** (ln 2) — the exact
  analog of the Wannier measurement, on a curve whose answer is known in closed form.
* **The torch engine** (``ising_tri_afm.py``) runs on CPU with tiny lattices: the
  frustrated ground-state energy is pinned to the exact −1 per spin, and — the strongest
  guard — with ``J = +1`` the engine reproduces the M05 ferromagnet's energy bond-for-bond
  (same seed, same trajectory), so the only change from M05 (the coupling sign) is proven
  correct and nothing else drifted.
* **The runner + check** (``m13.py`` / ``checks.check_m13``) are exercised for report shape,
  the honest-null path, and that the check *re-derives* the residual from the report arrays
  (a receipt) and owns its own tolerance.
"""
import math

import numpy as np
import pytest

from lab.entropy import (
    LN2,
    cooling_integral,
    high_t_tail,
    entropy_curve,
    residual_entropy,
    total_entropy_removed,
)
from lab.ising_tri_afm import TriAFMRunConfig, TriAFMRunResult, run
from lab.m13 import run_m13, to_report, M13Result, entropy_grid, WANNIER_S0, GROUND_ENERGY
from lab.checks import check_m13


# ───────────────────────── the integration primitive: exact analytic checks ──────────────
def _schottky_C(T, gap=1.0, g0=1, g1=1):
    """Analytic specific heat of a two-level system (energies 0 and ``gap``, degeneracies
    ``g0``/``g1``): C = x² g0 g1 e^{−x} / (g0 + g1 e^{−x})², x = gap/T. Uses e^{−x} (never
    e^{+x}) so the cold tail underflows to 0 cleanly. Its exact total entropy change from
    T=0 to ∞ is ln((g0+g1)/g0); the residual (T→0) entropy is ln g0."""
    x = gap / T
    ex = math.exp(-x)
    return x * x * g0 * g1 * ex / (g0 + g1 * ex) ** 2


def _fine_geom_grid(t_lo, t_hi, n):
    lo, hi = math.log(t_lo), math.log(t_hi)
    return [math.exp(lo + (hi - lo) * i / (n - 1)) for i in range(n)]


def test_high_t_tail_is_half_c_max():
    # Leading high-T form C ≈ a/T² ⇒ ∫_{T_max}^∞ C/T dT = a/(2 T_max²) = C_max/2.
    assert high_t_tail(10.0, 0.06) == pytest.approx(0.03)


def test_cooling_integral_exact_on_constant_C():
    # The integral is taken in log-T (C d ln T), so a CONSTANT C is the exact anchor:
    # ∫_{T_i}^{T_max} c d(ln T) = c·ln(T_max/T_i), which the trapezoid nails exactly.
    T = [0.5, 1.0, 2.0, 4.0, 8.0]
    c = 0.3
    C = [c] * len(T)
    I = cooling_integral(T, C)
    assert I[-1] == pytest.approx(0.0)
    for i in range(len(T)):
        assert I[i] == pytest.approx(c * math.log(T[-1] / T[i]), abs=1e-12)


def test_schottky_recovers_ln2_total_entropy():
    """A non-degenerate two-level system removes exactly ln 2 of entropy from ∞ to 0, so
    ∫ C/T = ln 2 and the residual (with S∞ = ln 2) is 0 — the integrator's first physics
    validation, on a curve with a closed-form answer."""
    T = _fine_geom_grid(0.02, 40.0, 400)
    C = [_schottky_C(t) for t in T]
    assert total_entropy_removed(T, C) == pytest.approx(LN2, abs=5e-3)
    assert residual_entropy(T, C, s_inf=LN2) == pytest.approx(0.0, abs=5e-3)


def test_degenerate_ground_recovers_known_nonzero_residual():
    """The exact analog of Wannier: a two-level system with a DOUBLY-degenerate ground
    state (g0=2, g1=1) keeps a residual entropy ln 2 at T→0. Integrating its analytic C/T
    down from S∞ = ln 3 must recover ln 2 — a KNOWN non-zero residual, closed-form."""
    T = _fine_geom_grid(0.02, 40.0, 400)
    C = [_schottky_C(t, gap=1.0, g0=2, g1=1) for t in T]
    s0 = residual_entropy(T, C, s_inf=math.log(3.0))
    assert s0 == pytest.approx(math.log(2.0), abs=5e-3)


def test_entropy_curve_descends_from_s_inf_to_residual():
    T = _fine_geom_grid(0.02, 40.0, 200)
    C = [_schottky_C(t) for t in T]
    Ts, S = entropy_curve(T, C, s_inf=LN2)
    assert Ts == sorted(Ts)
    assert S[-1] == pytest.approx(LN2, abs=5e-3)      # hot end ≈ ln2
    assert S[0] == pytest.approx(0.0, abs=5e-3)       # cold end ≈ 0 (non-degenerate)
    assert all(S[i] <= S[i + 1] + 1e-9 for i in range(len(S) - 1))  # monotone up in T


def test_entropy_functions_are_order_insensitive():
    # Arrays may arrive unsorted in T; the reducers sort internally and agree.
    T = _fine_geom_grid(0.05, 20.0, 60)
    C = [_schottky_C(t) for t in T]
    idx = list(range(len(T)))[::-1]                   # reversed
    s0_fwd = residual_entropy(T, C, s_inf=LN2)
    s0_rev = residual_entropy([T[i] for i in idx], [C[i] for i in idx], s_inf=LN2)
    assert s0_fwd == pytest.approx(s0_rev, abs=1e-9)


# ───────────────────────────── the engine: config + frustration physics ──────────────────
def test_config_defaults_span_a_wide_window():
    cfg = TriAFMRunConfig()
    assert cfg.J == -1.0                              # antiferromagnetic
    assert cfg.L % 3 == 0                             # triangular 3-colour seam
    assert cfg.T_min < 1.0 < cfg.T_max                # brackets the C hump near T≈1


def test_odd_L_rejected():
    cfg = TriAFMRunConfig(L=10, device="cpu")         # not a multiple of 3
    with pytest.raises(ValueError):
        run(cfg)


def test_explicit_T_grid_is_used():
    grid = (0.5, 1.0, 2.0, 4.0)
    cfg = TriAFMRunConfig(L=12, T_values=grid, n_burnin=10, n_sweeps=40,
                          sample_every=10, seed=1, device="cpu")
    r = run(cfg)
    assert list(r.T) == pytest.approx(list(grid))


def test_cpu_run_smoke_and_json():
    cfg = TriAFMRunConfig(L=12, T_min=0.2, T_max=8.0, n_temps=8, n_burnin=60,
                          n_sweeps=240, sample_every=6, seed=2, device="cpu")
    r = run(cfg)
    assert isinstance(r, TriAFMRunResult)
    assert r.T.shape == (8,)
    for arr in (r.energy, r.energy_err, r.specific_heat, r.abs_mag):
        assert arr.shape == (8,)
    assert (r.specific_heat >= -1e-9).all()           # C is a variance — never negative
    # energy per spin on the 6-coordinated triangular lattice lives in [-3, 3]
    assert (r.energy >= -3.001).all() and (r.energy <= 3.001).all()
    assert float(np.max(r.abs_mag)) < 0.3             # no net moment (AFM)
    j = r.to_json()
    assert j["config"]["J"] == -1.0 and len(j["T"]) == 8


def test_determinism():
    cfg = TriAFMRunConfig(L=12, T_min=0.3, T_max=6.0, n_temps=6, n_burnin=30,
                          n_sweeps=120, sample_every=6, seed=99, device="cpu")
    r1, r2 = run(cfg), run(cfg)
    assert np.array_equal(r1.energy, r2.energy)
    assert np.array_equal(r1.specific_heat, r2.specific_heat)


def test_ground_state_energy_approaches_minus_one():
    """The load-bearing frustration anchor: at low T the triangular AFM settles onto its
    exact ground-state energy of −1 per spin (two of every triangle's three bonds kept).
    A wrong J sign (an accidental ferromagnet) would give −3; wrong geometry, something else."""
    cfg = TriAFMRunConfig(L=24, T_values=(0.1, 0.2, 0.4), n_burnin=400, n_sweeps=1200,
                          sample_every=6, seed=5, device="cpu")
    r = run(cfg)
    assert float(np.min(r.energy)) == pytest.approx(GROUND_ENERGY, abs=0.03)


def test_J_plus_one_reproduces_the_m05_ferromagnet():
    """The strongest correctness guard: with J = +1 this engine IS the M05 ferromagnet.
    Same 3-colour update, same RNG seeding and draw order, so on an identical config the
    energy matches ``ising_tri.run`` bond-for-bond — proving the ONLY change from M05 (the
    coupling sign carried into ΔE) is correct and nothing else drifted."""
    from lab.ising_tri import TriRunConfig
    from lab.ising_tri import run as run_tri
    common = dict(L=12, T_min=1.0, T_max=5.0, n_temps=6, n_burnin=50,
                  n_sweeps=200, sample_every=10, seed=7, device="cpu")
    r_fm = run_tri(TriRunConfig(**common))
    r_afm = run(TriAFMRunConfig(J=1.0, **common))
    assert np.allclose(r_fm.energy, r_afm.energy)
    assert np.allclose(r_fm.specific_heat, r_afm.specific_heat)


# ──────────────────────────────── runner + report + check ────────────────────────────────
def test_entropy_grid_is_geometric_and_spans():
    g = entropy_grid(0.1, 14.0, 40)
    assert len(g) == 40
    assert g[0] == pytest.approx(0.1) and g[-1] == pytest.approx(14.0)
    ratios = [g[i + 1] / g[i] for i in range(len(g) - 1)]
    assert max(ratios) - min(ratios) < 1e-6           # constant ratio ⇒ geometric


def test_run_m13_integration_tiny_resolves_wannier():
    """The full runner over a real (tiny) sweep returns a check-ready result. The frustrated
    model equilibrates easily, so even this small run should land the residual near 0.3383
    and the ground energy near −1 — a genuine physics assertion, not just shape."""
    calls = []
    result = run_m13(L=24, T_min=0.15, T_max=12.0, n_temps=32, n_sweeps=2500,
                     n_burnin=800, seed=3, device="cpu",
                     progress=lambda r: calls.append(r))
    assert isinstance(result, M13Result)
    assert len(calls) == 1
    assert len(result.T) == 32 and len(result.specific_heat) == 32
    assert result.T == sorted(result.T)
    assert result.e_ground == pytest.approx(GROUND_ENERGY, abs=0.03)
    assert abs(result.s0_measured - WANNIER_S0) < 0.03
    assert result.resolved is True


def _toy_m13_result(resolved=True):
    """A hand-built result so ``to_report`` shape / null tests don't depend on a Monte-Carlo
    run landing on either side of the tolerance (which, at coarse scale, some seeds do)."""
    T = [0.2, 0.5, 1.0, 2.0, 5.0, 12.0]
    C = [0.02, 0.15, 0.23, 0.10, 0.02, 0.004]
    S = [0.34, 0.40, 0.52, 0.63, 0.68, 0.69]
    s0 = 0.339 if resolved else 0.45
    return M13Result(
        T=T, specific_heat=C, energy=[-1.0, -0.99, -0.9, -0.7, -0.4, -0.2],
        energy_err=[0.001] * 6, abs_mag=[0.01] * 6, entropy_curve=S, s_inf=LN2,
        s0_measured=s0, s0_no_tail=s0 + 0.005, high_t_tail=0.002,
        entropy_removed=LN2 - s0, s0_benchmark=WANNIER_S0,
        s0_abs_error=abs(s0 - WANNIER_S0), e_ground=-1.0, resolved=resolved,
        L=24, wall_seconds=12.0, config={"lattice": "triangular", "J": -1.0},
    )


def test_to_report_shape_is_check_ready():
    rep = to_report(_toy_m13_result(resolved=True))
    assert rep["experiment"] == "M13-triangular-afm"
    assert len(rep["T"]) == len(rep["specific_heat"]) == len(rep["entropy_curve"])
    assert rep["s0_benchmark"] == WANNIER_S0
    assert "status" not in rep                         # resolved → not a null
    assert "residual entropy" in rep["headline"].lower()


def test_to_report_unresolved_is_honest_null():
    rep = to_report(_toy_m13_result(resolved=False))
    assert rep["resolved"] is False
    assert rep["status"] == "null"                     # honest failed-calibration grey leaf
    assert "calibration null" in rep["headline"]


def test_check_m13_reads_a_real_engine_curve_end_to_end():
    """End-to-end receipt on genuine Monte-Carlo data: the engine's C(T) → report → check,
    where the check re-integrates C/T itself. Corrupting the stored ``s0_measured`` must NOT
    flip the grade — the recomputed residual from the real ``specific_heat`` is what decides.
    (Exhaustive pass/fail grading lives in test_checks.py with fast synthetic curves.)"""
    result = run_m13(L=24, T_min=0.15, T_max=12.0, n_temps=32, n_sweeps=2500,
                     n_burnin=800, seed=3, device="cpu")
    rep = to_report(result)
    assert check_m13(rep)[0] is True                    # real curve resolves near 0.3383
    rep["s0_measured"] = 0.999                          # a lie the check must ignore
    assert check_m13(rep)[0] is True                    # still passes on the real curve
