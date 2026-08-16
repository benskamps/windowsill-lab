"""K03 — the gated two-branch linear-response measurement (Daido vs Hong).

What these tests pin: the estimator-assay contract. Every fit carries an
intercept, a drifting secant REFUSES rather than fits, the branch exponent
re-derives from surviving columns only, and ``check_k03`` re-refuses a
tampered receipt. The physics run itself is hour-scale and lives in the
receipts ledger, not here — the micro run below proves the two-pass pipeline
end to end at toy scale and nothing more.
"""
import numpy as np
import pytest

from lab import checks, curriculum, k03
from lab.kuramoto import mean_field_r


# ── the ε grid ────────────────────────────────────────────────────────────────

def test_eps_grid_is_log_spaced_with_pinned_endpoints():
    grid = k03.eps_grid()
    assert grid[0] == pytest.approx(k03.EPS_MIN)
    assert grid[-1] == pytest.approx(k03.EPS_MAX)
    ratios = grid[1:] / grid[:-1]
    assert np.allclose(ratios, ratios[0])          # geometric
    # The floor honors the assay's finite-size rule: about a decade above
    # the N=2000 rounding at ε ≈ 0.0023.
    assert k03.EPS_MIN >= 0.02


# ── OLS with intercept ────────────────────────────────────────────────────────

def test_ols_line_recovers_slope_and_intercept_exactly():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    fit = k03._ols_line(x, 0.7 + 2.5 * x)
    assert fit["slope"] == pytest.approx(2.5)
    assert fit["intercept"] == pytest.approx(0.7)
    assert fit["r2"] == pytest.approx(1.0)


# ── the column gate ───────────────────────────────────────────────────────────

def test_linear_column_passes_and_reports_the_slope():
    h = np.array([0.0, 0.01, 0.02, 0.03])
    rec = k03.column_response(h, 0.05 + 3.0 * h)
    assert rec["ok"] is True
    assert rec["chi"] == pytest.approx(3.0)
    assert rec["fit"]["intercept"] == pytest.approx(0.05)   # never through origin
    assert rec["secant_spread"] == pytest.approx(0.0, abs=1e-9)


def test_curved_column_is_refused_not_fitted():
    """The assay's rule 2: a drifting secant means no single slope exists.
    The refusal carries the secants so the check can re-refuse."""
    h = np.array([0.0, 0.01, 0.02, 0.03])
    rec = k03.column_response(h, 3.0 * h + 40.0 * h ** 2)   # saturating-ish
    assert rec["ok"] is False
    assert rec["reason"] == "nonlinear-secants"
    assert rec["chi"] is None
    assert len(rec["secants"]) == 3


def test_flat_column_is_refused():
    h = np.array([0.0, 0.01, 0.02])
    rec = k03.column_response(h, np.array([0.2, 0.2, 0.2]))
    assert rec["ok"] is False and rec["reason"] == "flat-response"


def test_column_requires_a_zero_baseline_and_ascending_fields():
    with pytest.raises(ValueError):
        k03.column_response(np.array([0.001, 0.01, 0.02]), np.zeros(3))
    with pytest.raises(ValueError):
        k03.column_response(np.array([0.0, 0.02, 0.01]), np.zeros(3))


# ── the branch exponent ───────────────────────────────────────────────────────

def test_branch_exponent_recovers_a_known_power_law():
    eps = k03.eps_grid()
    fit = k03.branch_exponent(eps, 2.0 * eps ** -0.25)
    assert fit["gamma"] == pytest.approx(0.25, abs=1e-9)
    assert fit["r2"] == pytest.approx(1.0)


def test_branch_exponent_refuses_non_positive_chi():
    fit = k03.branch_exponent(np.array([0.02, 0.04, 0.08, 0.16]),
                              np.array([1.0, 0.5, -0.1, 0.2]))
    assert fit["gamma"] is None
    assert "non-positive" in fit["reason"]


# ── a synthetic PASSING receipt, and check_k03 as its adversary ───────────────

def _synthetic_report(gamma_above=0.25, gamma_prime=1.0, n=2000):
    """A receipt whose columns are perfect linear ladders realizing the given
    exponents, with textbook baselines — the shape a flawless run would emit."""
    eps = k03.eps_grid(5)
    k_c = 1.0
    columns = {"below": [], "above": []}
    for branch, gam in (("below", gamma_prime), ("above", gamma_above)):
        for e in eps:
            K = k_c * (1 - e) if branch == "below" else k_c * (1 + e)
            chi = float(0.05 * e ** -gam)
            baseline = 0.0 if branch == "below" else float(mean_field_r(K, 0.5))
            h = np.array([0.0, 0.005, 0.010, 0.015])
            obs = baseline + chi * h
            rec = k03.column_response(h, obs)
            rec.update({"eps": float(e), "K": float(K), "branch": branch,
                        "h_ladder": h.tolist(), "obs": obs.tolist(),
                        "half_window_drift": 0.0, "pilot_chi": chi})
            columns[branch].append(rec)

    def fit(cols):
        ok = [c for c in cols if c["ok"]]
        f = k03.branch_exponent(np.array([c["eps"] for c in ok]),
                                np.array([c["chi"] for c in ok]))
        f["n_columns"] = len(ok)
        return f

    return {
        "experiment": "K03-daido-vs-hong", "milestone": "K03",
        "status": "pass", "n": n, "gamma_width": 0.5, "k_c": k_c,
        "eps_grid": eps.tolist(),
        "columns_below": columns["below"], "columns_above": columns["above"],
        "fit_below": fit(columns["below"]), "fit_above": fit(columns["above"]),
    }


def test_check_k03_passes_a_flawless_receipt_and_names_both_exponents():
    ok, detail = checks.check_k03(_synthetic_report())
    assert ok is True
    assert "γ=0.250" in detail and "γ'=1.000" in detail


def test_check_k03_ignores_non_k03_reports():
    ok, _ = checks.check_k03({"experiment": "M01-ising"})
    assert ok is None


def test_check_k03_refuses_a_tampered_chi():
    report = _synthetic_report()
    report["columns_above"][2]["chi"] *= 1.05      # cooked number, honest ladder
    ok, detail = checks.check_k03(report)
    assert ok is False and "does not reproduce" in detail


def test_check_k03_refuses_a_tampered_branch_exponent():
    report = _synthetic_report()
    report["fit_below"]["gamma"] = 0.25            # claim Hong without the data
    ok, detail = checks.check_k03(report)
    assert ok is False and "does not reproduce" in detail


def test_check_k03_refuses_an_ordered_subcritical_baseline():
    """The incoherent state must be incoherent: an h=0 baseline above the
    finite-N floor on the below branch means the run measured something else."""
    report = _synthetic_report()
    col = report["columns_below"][0]
    h = np.array(col["h_ladder"])
    obs = 0.5 + np.array(col["obs"])               # spuriously ordered
    rec = k03.column_response(h, obs)
    rec.update({k: col[k] for k in ("eps", "K", "branch", "half_window_drift",
                                    "pilot_chi")})
    rec.update({"h_ladder": h.tolist(), "obs": obs.tolist()})
    report["columns_below"][0] = rec
    ok, detail = checks.check_k03(report)
    assert ok is False and "finite-N floor" in detail


def test_check_k03_refuses_a_goldstone_confused_supercritical_baseline():
    """⟨cos θ⟩ above K_c saturates at the spontaneous r — but a run whose h=0
    coherence is far from √(1−K_c/K) has lost the ordered state entirely."""
    report = _synthetic_report()
    col = report["columns_above"][-1]
    h = np.array(col["h_ladder"])
    chi = col["chi"]
    obs = 0.9 + chi * h                            # baseline nowhere near exact
    rec = k03.column_response(h, obs)
    rec.update({k: col[k] for k in ("eps", "K", "branch", "half_window_drift",
                                    "pilot_chi")})
    rec.update({"h_ladder": h.tolist(), "obs": obs.tolist()})
    report["columns_above"][-1] = rec
    ok, detail = checks.check_k03(report)
    assert ok is False and "exact spontaneous" in detail


def test_check_k03_refuses_when_too_few_columns_survive():
    report = _synthetic_report()
    # Curve every below-column past the gate: the branch fit must then refuse.
    for col in report["columns_below"][:4]:
        h = np.array(col["h_ladder"])
        obs = np.array(col["obs"]) + 200.0 * col["chi"] * h ** 2
        rec = k03.column_response(h, obs)
        rec.update({k: col[k] for k in ("eps", "K", "branch",
                                        "half_window_drift", "pilot_chi")})
        rec.update({"h_ladder": h.tolist(), "obs": obs.tolist()})
        report["columns_below"][report["columns_below"].index(col)] = rec
    # The recorded fit must match what survives, else the mismatch gate fires
    # first — recompute it the way the runner would.
    ok_cols = [c for c in report["columns_below"] if c["ok"]]
    if len(ok_cols) >= 2:
        f = k03.branch_exponent(np.array([c["eps"] for c in ok_cols]),
                                np.array([c["chi"] for c in ok_cols]))
        f["n_columns"] = len(ok_cols)
        report["fit_below"] = f
    ok, detail = checks.check_k03(report)
    assert ok is False and "did not happen" in detail


# ── the runner end to end, toy scale ─────────────────────────────────────────

def test_run_k03_micro_produces_a_receipts_grade_report():
    """Toy N and toy windows: the two-pass pipeline runs, every column carries
    its ladder, observables, drift, and gate verdict, and the report is the
    shape check_k03 reads. No physics claim at this scale — refusals are fine
    and expected; STRUCTURE is what this test pins."""
    result = k03.run_k03(n=16, n_points=2, rungs=2, t_burn=1.0, t_measure=2.0,
                         pilot_t_burn=0.5, pilot_t_measure=1.0, seed=7)
    report = k03.to_report(result)
    assert report["experiment"] == "K03-daido-vs-hong"
    assert len(report["columns_below"]) == 2
    assert len(report["columns_above"]) == 2
    for col in report["columns_below"] + report["columns_above"]:
        assert col["h_ladder"][0] == 0.0
        assert len(col["h_ladder"]) == 3           # h=0 + 2 rungs
        assert len(col["obs"]) == 3
        assert "half_window_drift" in col
        assert col["ok"] in (True, False)
    assert report["claim_boundary"]
    assert report["verdict"]["note"]


# ── registration ─────────────────────────────────────────────────────────────

def test_k03_is_registered_and_scheduler_options_are_declared():
    assert curriculum.RUNNERS["K03"] == "k03"
    assert "K03" in curriculum.ROTATION
    assert curriculum.RUNNER_SCHEDULER_OPTIONS["K03"] == frozenset({"seed"})
