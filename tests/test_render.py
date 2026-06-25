"""Permanent committed reports — the core of the permanence refactor.

The old bug: both renderers wrote a single ``reports/latest.html`` that every
run clobbered, so M02/M03 milestone reports were buried under "whatever ran
last." The fix gives every run a permanently-named, never-overwritten pair in
the repo (``reports/<date>-<slug>.html`` + ``.json``); ``latest.html`` becomes a
back-compat *copy* of the newest, never the archive slot.

These tests exercise the pure persistence helpers (``_commit_report`` and
``_slug_for``) directly — no plotting, no torch, no matplotlib figures — so they
run fast and never touch the live ``reports/`` or ``~/.lab``. Everything goes
through monkeypatched tmp dirs.
"""
import json

from lab import render
from lab.render import _commit_report, _slug_for


def _patch_dirs(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(render, "REPO_REPORTS", reports)
    monkeypatch.setattr(render, "LAB_HOME", lab_home)
    return reports, lab_home


def test_commit_report_writes_permanent_pair(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    dump = json.dumps({"experiment": "M02-finite-size-scaling", "headline": "hi"})
    path = _commit_report("2026-06-15", "m02", "<html>m02</html>", dump)

    html_file = reports / "2026-06-15-m02.html"
    json_file = reports / "2026-06-15-m02.json"
    assert html_file.exists() and json_file.exists()
    assert path == html_file
    assert html_file.read_text(encoding="utf-8") == "<html>m02</html>"
    # JSON round-trips back to the same object.
    assert json.loads(json_file.read_text(encoding="utf-8"))["experiment"] == "M02-finite-size-scaling"


def test_second_render_does_not_clobber_first(tmp_path, monkeypatch):
    """The core bug: two distinct runs must both survive on disk."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    _commit_report("2026-06-14", "m01", "<html>first</html>", json.dumps({"a": 1}))
    _commit_report("2026-06-15", "m02", "<html>second</html>", json.dumps({"b": 2}))

    assert (reports / "2026-06-14-m01.html").read_text(encoding="utf-8") == "<html>first</html>"
    assert (reports / "2026-06-15-m02.html").read_text(encoding="utf-8") == "<html>second</html>"
    # latest.html is a COPY of the most recently committed report, never an archive.
    assert (reports / "latest.html").read_text(encoding="utf-8") == "<html>second</html>"


def test_latest_html_is_a_copy_not_the_archive(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    _commit_report("2026-06-15", "m02", "<html>newest</html>", json.dumps({}))
    latest = reports / "latest.html"
    permanent = reports / "2026-06-15-m02.html"
    assert latest.exists() and permanent.exists()
    assert latest.read_text(encoding="utf-8") == permanent.read_text(encoding="utf-8")
    # They are distinct files — editing the archive would not touch the pointer.
    assert latest != permanent


def test_slug_for_maps_known_experiments():
    assert _slug_for({"experiment": "M02-finite-size-scaling"}) == "m02"
    assert _slug_for({"experiment": "M03-data-collapse"}) == "m03"
    assert _slug_for({"experiment": "M01-ising-verification"}) == "m01"
    assert _slug_for({"experiment": "M08-xy-bkt"}) == "m08"
    assert _slug_for({"experiment": "M10-afm-ising"}) == "m10"


def test_slug_for_infers_m01_from_structure():
    # Legacy M01 dumps carry no `experiment` field — infer from T + chi.
    assert _slug_for({"T": [2.2, 2.3], "chi": [1.0, 9.0]}) == "m01"


def test_slug_for_falls_back_to_run():
    assert _slug_for({}) == "run"


def test_slug_for_is_shared_with_publish():
    """One rule, one source of truth — render and publish agree (spec signature)."""
    from lab import publish
    for rep in (
        {"experiment": "M02-finite-size-scaling"},
        {"experiment": "M03-data-collapse"},
        {"T": [1], "chi": [1]},
        {},
    ):
        assert render._slug_for(rep) == publish._slug_for(rep)


# ── FIX 2: render_m03 — the M03 milestone gets a render/publish path ──────────
# M03 can be RUN (m03.run_m03 → M03Result, m03.to_report) but had no renderer,
# so the data-collapse milestone could never be archived. render_m03 mirrors
# render_fss: M(T) family plot + the β data-collapse plot, an honest verdict,
# JSON sidecar, and a permanent committed reports/<date>-m03.html/.json pair.

import numpy as np

from lab.m03 import to_report as m03_to_report, M03Result, M03Curve, T_C, BETA_OVER_NU, INV_NU, NU


def _F(x):
    return 1.0 / (1.0 + np.exp(3.0 * np.asarray(x, dtype=float)))


def _m03_fixture_report(beta_over_nu_fit=BETA_OVER_NU, collapse_quality=1e-15):
    """A fixture M03 ``to_report`` dict built from exact synthetic curves — no GPU."""
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 24)
    curves = []
    for L in Ls:
        T = T_C + xs * L ** (-INV_NU)
        M = L ** (-BETA_OVER_NU) * _F(xs)
        curves.append(M03Curve(L=L, T=T.tolist(), M=M.tolist(),
                               M_err=[0.0] * len(T), wall_seconds=1.0))
    result = M03Result(
        curves=curves, beta_over_nu_fit=beta_over_nu_fit, inv_nu_fit=1.0,
        collapse_quality=collapse_quality, tc=float(T_C),
        beta_over_nu_theory=BETA_OVER_NU, nu=NU, wall_seconds=120.0,
        config={"seed": 42},
    )
    return m03_to_report(result)


def test_render_m03_writes_permanent_report_pair(tmp_path, monkeypatch):
    reports, lab_home = _patch_dirs(tmp_path, monkeypatch)
    report = _m03_fixture_report()
    out = render.render_m03(report, date="2026-06-15")

    # Permanent committed pair under the M03 slug — never buried by another run.
    html_file = reports / "2026-06-15-m03.html"
    json_file = reports / "2026-06-15-m03.json"
    assert html_file.exists() and json_file.exists()
    # Both the collapse plot and the M(T) family plot landed (two <img> figures).
    html = html_file.read_text(encoding="utf-8")
    assert html.count("data:image/png;base64,") >= 2
    assert "M03" in html
    # JSON sidecar round-trips to the M03 report.
    assert json.loads(json_file.read_text(encoding="utf-8"))["experiment"] == "M03-data-collapse"
    # Back-compat latest.html copy refreshed.
    assert (reports / "latest.html").exists()
    assert out == lab_home / "2026-06-15.html" or out == html_file or out.exists()


def test_render_m03_verdict_passes_near_exact_beta_over_nu(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    report = _m03_fixture_report(beta_over_nu_fit=BETA_OVER_NU)
    render.render_m03(report, date="2026-06-15")
    html = (reports / "2026-06-15-m03.html").read_text(encoding="utf-8")
    # An honest PASS verdict for β/ν ≈ 1/8.
    assert "✓" in html


def test_render_m03_verdict_is_honest_null_when_off(tmp_path, monkeypatch):
    """A run whose β/ν misses 1/8 is kept as a null — never mislabeled a pass."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    report = _m03_fixture_report(beta_over_nu_fit=0.30, collapse_quality=0.5)
    render.render_m03(report, date="2026-06-15")
    html = (reports / "2026-06-15-m03.html").read_text(encoding="utf-8")
    assert "✓" not in html
    assert "null" in html.lower()


def test_render_m03_appears_in_discovery_and_ledger(tmp_path, monkeypatch):
    """The rendered M03 report is discoverable as a run and rides the ledger."""
    reports, lab_home = _patch_dirs(tmp_path, monkeypatch)
    from lab import publish, archive
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    monkeypatch.setattr(archive, "LAB_HOME", lab_home)

    render.render_m03(_m03_fixture_report(), date="2026-06-15")
    runs = publish.discover_runs()
    assert any(r["milestone"] == "M03" for r in runs)
    ledger = archive.run_ledger()
    m03_rows = [r for r in ledger if r["milestone"] == "M03"]
    assert m03_rows and m03_rows[0]["verdict"] == "verified"   # exact fixture → green leaf


def test_slug_for_maps_m03_report():
    assert _slug_for(_m03_fixture_report()) == "m03"


# ── FIX 3: ~/.lab dated cache is slug-keyed (no same-day collision) ───────────
def _m02_fixture_report():
    """A minimal M02 finite-size-scaling report for render_fss (no GPU)."""
    Ls = (32, 64, 128)
    curves = []
    for L in Ls:
        T = [2.27, 2.30, 2.33, 2.36]
        chi = [1.0, float(L), 1.5, 1.0]   # peak at T=2.30, grows with L
        curves.append({"L": L, "T": T, "chi": chi,
                       "chi_max": float(L), "T_peak": 2.30, "wall_seconds": 1.0})
    return {
        "experiment": "M02-finite-size-scaling",
        "headline": "fss fixture",
        "L_values": list(Ls),
        "curves": curves,
        "gamma_over_nu_fit": 1.74,
        "gamma_over_nu_theory": 1.75,
        "fit_r2": 0.99,
        "nu": 1.0,
        "tc": float(T_C),
        "wall_seconds": 5.0,
        "config": {"seed": 42},
    }


def test_lab_cache_slug_keyed_same_day_two_milestones_survive(tmp_path, monkeypatch):
    """FIX 3: M02 and M03 rendered on the SAME day must both keep their own
    ~/.lab dated cache — the old bare ``<date>.json``/``.html`` clobbered the
    first. latest.html is still refreshed to the newest."""
    reports, lab_home = _patch_dirs(tmp_path, monkeypatch)
    render.render_fss(_m02_fixture_report(), date="2026-06-15")
    render.render_m03(_m03_fixture_report(), date="2026-06-15")

    # Both slug-keyed cache files coexist locally — neither buried the other.
    assert (lab_home / "2026-06-15-m02.json").exists()
    assert (lab_home / "2026-06-15-m02.html").exists()
    assert (lab_home / "2026-06-15-m03.json").exists()
    assert (lab_home / "2026-06-15-m03.html").exists()
    # The local latest pointer still exists (points at the newest render).
    assert (lab_home / "latest.html").exists()


def test_lab_cache_discovery_finds_slug_keyed_files(tmp_path, monkeypatch):
    """Discovery (publish + archive) still finds the slug-keyed ~/.lab caches."""
    reports, lab_home = _patch_dirs(tmp_path, monkeypatch)
    from lab import publish, archive
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    monkeypatch.setattr(archive, "LAB_HOME", lab_home)
    render.render_fss(_m02_fixture_report(), date="2026-06-15")
    render.render_m03(_m03_fixture_report(), date="2026-06-15")
    milestones = {r["milestone"] for r in publish.discover_runs()}
    assert {"M02", "M03"} <= milestones


# ── M07 — q-state Potts render path ──────────────────────────────────────────
import math


def _m07_fixture_report(misses=None):
    """A synthetic M07 ``to_report``-shaped dict (no GPU). ``misses`` optionally
    sets a q's χ-peak off its exact T_c (to model an honest null on that q)."""
    misses = misses or {}
    per_q = []
    for q in (3, 4, 5, 6):
        tc = 1.0 / math.log(1.0 + math.sqrt(q))
        peak = misses.get(q, tc)
        T = [round(peak - 0.12 + 0.01 * i, 4) for i in range(25)]
        chi = [1.0 / (abs(t - peak) + 0.02) for t in T]
        per_q.append({
            "q": q, "T": T, "chi": chi,
            "order": [1.0 if t < tc else 0.05 for t in T],
            "order_err": [0.01] * 25,
            "energy": [-1.5] * 25, "specific_heat": [0.5] * 25,
            "tc_chi": peak, "tc_chi_refined": peak, "tc_exact": tc,
            "rel_error": abs(peak - tc) / tc,
            "chi_max": (1000.0 if q >= 5 else 200.0), "order_drop": 0.3,
            "transition": "continuous" if q <= 4 else "first-order",
            "wall_seconds": 10.0,
        })
    return {
        "experiment": "M07-potts", "headline": "M07 test", "L": 64,
        "per_q": per_q,
        "transition_order": {"3": "continuous", "4": "continuous",
                             "5": "first-order", "6": "first-order"},
        "continuous_mean_order_drop": 0.3, "first_order_mean_order_drop": 0.3,
        "continuous_mean_chi_max": 200.0, "first_order_mean_chi_max": 1000.0,
        "wall_seconds": 40.0, "config": {"seed": 42},
    }


def test_render_m07_writes_permanent_report_pair(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    out = render.render_m07(_m07_fixture_report(), date="2026-06-25")
    html_file = reports / "2026-06-25-m07.html"
    json_file = reports / "2026-06-25-m07.json"
    assert html_file.exists() and json_file.exists()
    html = html_file.read_text(encoding="utf-8")
    assert "M07" in html and "Potts" in html
    # The per-q table and both plots are present.
    assert "<table>" in html and "transition" in html
    assert json.loads(json_file.read_text(encoding="utf-8"))["experiment"] == "M07-potts"


def test_render_m07_verdict_passes_when_every_q_locates_tc(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m07(_m07_fixture_report(), date="2026-06-25")
    html = (reports / "2026-06-25-m07.html").read_text(encoding="utf-8")
    assert "✓" in html
    # Names the continuous→first-order signature via χ_max.
    assert "first-order" in html and "χ_max" in html


def test_render_m07_verdict_is_honest_null_when_a_q_is_off(tmp_path, monkeypatch):
    """A q whose χ peak misses its exact T_c by more than tolerance is kept as a
    null — never relabeled a pass (q=3 continuous, ±0.1; push it 0.3 off)."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    tc3 = 1.0 / math.log(1.0 + math.sqrt(3))
    render.render_m07(_m07_fixture_report(misses={3: tc3 - 0.3}), date="2026-06-25")
    html = (reports / "2026-06-25-m07.html").read_text(encoding="utf-8")
    assert "✓" not in html
    assert "null" in html.lower()


# ── M08: 2D XY BKT render path ───────────────────────────────────────────────
def _m08_fixture_report(crossing_at=0.913, with_crossing=True):
    """A synthetic M08 ``to_report``-shaped dict (no GPU).

    Builds a smooth Υ(T) that crosses the (2/π)·T jump line at ``crossing_at`` (a
    straight line of negative slope through that point — a clean single downward
    root). ``with_crossing=False`` pins Υ above the line everywhere (no crossing →
    honest null). The crossing the renderer reports is computed the same way the
    real run does, via ``m08.helicity_crossing``.
    """
    from lab.m08 import TWO_OVER_PI, T_BKT, helicity_crossing
    T = [round(0.6 + 0.02 * i, 4) for i in range(26)]
    if with_crossing:
        Y = [TWO_OVER_PI * crossing_at - 2.5 * (t - crossing_at) for t in T]
    else:
        Y = [5.0] * len(T)   # always above the jump line → no crossing
    cross = helicity_crossing(T, Y)
    rel = abs(cross - T_BKT) / T_BKT if cross is not None else None
    return {
        "experiment": "M08-xy-bkt", "headline": "M08 test", "L": 64,
        "T": T, "helicity_modulus": Y,
        "helicity_err": [0.01] * len(T),
        "energy": [-1.5] * len(T), "abs_mag": [0.1] * len(T),
        "acceptance": [0.4] * len(T),
        "tc_crossing": cross, "tc_benchmark": T_BKT, "rel_error": rel,
        "two_over_pi": TWO_OVER_PI, "updater": "metropolis",
        "wall_seconds": 94.0, "config": {"seed": 42, "model": "xy"},
    }


def test_render_m08_writes_permanent_report_pair(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    out = render.render_m08(_m08_fixture_report(), date="2026-06-25")
    html_file = reports / "2026-06-25-m08.html"
    json_file = reports / "2026-06-25-m08.json"
    assert html_file.exists() and json_file.exists()
    html = html_file.read_text(encoding="utf-8")
    assert "M08" in html and "XY" in html and "helicity" in html.lower()
    assert json.loads(json_file.read_text(encoding="utf-8"))["experiment"] == "M08-xy-bkt"


def test_render_m08_verdict_passes_near_benchmark(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m08(_m08_fixture_report(crossing_at=0.913), date="2026-06-25")
    html = (reports / "2026-06-25-m08.html").read_text(encoding="utf-8")
    assert "✓" in html
    # Names the BKT signature: the universal jump / helicity crossing.
    assert "jump" in html.lower() and "crossing" in html.lower()


def test_render_m08_verdict_is_honest_null_when_crossing_off(tmp_path, monkeypatch):
    """A crossing outside the ±0.07 window is kept as a null, never a pass."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m08(_m08_fixture_report(crossing_at=0.70), date="2026-06-25")
    html = (reports / "2026-06-25-m08.html").read_text(encoding="utf-8")
    assert "✓" not in html
    assert "null" in html.lower()


def test_render_m08_verdict_is_honest_null_when_no_crossing(tmp_path, monkeypatch):
    """A Υ(T) that never crosses the jump line is an honest null, not a discovery."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m08(_m08_fixture_report(with_crossing=False), date="2026-06-25")
    html = (reports / "2026-06-25-m08.html").read_text(encoding="utf-8")
    assert "✓" not in html
    assert "null" in html.lower()


def test_render_m08_appears_in_discovery_and_ledger(tmp_path, monkeypatch):
    """The rendered M08 report is discoverable as a run and rides the ledger as a
    verified green leaf (the exact-crossing fixture passes check_m08)."""
    reports, lab_home = _patch_dirs(tmp_path, monkeypatch)
    from lab import publish, archive
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    monkeypatch.setattr(archive, "LAB_HOME", lab_home)

    render.render_m08(_m08_fixture_report(), date="2026-06-25")
    runs = publish.discover_runs()
    assert any(r["milestone"] == "M08" for r in runs)
    ledger = archive.run_ledger()
    m08_rows = [r for r in ledger if r["milestone"] == "M08"]
    assert m08_rows and m08_rows[0]["verdict"] == "verified"   # exact fixture → green leaf


def test_slug_for_maps_m08_report():
    assert _slug_for(_m08_fixture_report()) == "m08"


# ── M09: 2D Heisenberg / Mermin–Wagner render path ───────────────────────────
def _m09_fixture_report(abs_mag=(0.476, 0.285, 0.143), Ls=(16, 32, 64)):
    """A synthetic M09 ``to_report``-shaped dict (no GPU).

    Defaults to a clean Mermin–Wagner drift (⟨|m|⟩ halving as L doubles → the
    absence of order). Overriding ``abs_mag`` with a flat/rising sequence models a
    broken run (a fake finite-T transition). The drift verdict the renderer reports
    is recomputed the same way the real run does, via ``m09`` helpers.
    """
    from lab.m09 import drift_slope
    m = list(abs_mag)
    ratios = [m[i + 1] / m[i] for i in range(len(m) - 1)]
    err = [0.005] * len(Ls)
    monotone = all(m[i + 1] < m[i] - 1.5 * max(err[i], err[i + 1])
                   for i in range(len(m) - 1))
    return {
        "experiment": "M09-heisenberg", "headline": "M09 test",
        "L_values": list(Ls), "T": 0.7,
        "abs_mag": m, "abs_mag_err": err,
        "chi": [0.1] * len(Ls), "energy": [-1.15] * len(Ls),
        "acceptance": [0.55] * len(Ls),
        "ratios": ratios, "slope_vs_inv_L": drift_slope(Ls, m),
        "monotone_decreasing": monotone, "updater": "metropolis",
        "wall_seconds": 80.0, "config": {"seed": 42, "model": "heisenberg"},
    }


def test_render_m09_writes_permanent_report_pair(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    out = render.render_m09(_m09_fixture_report(), date="2026-06-25")
    html_file = reports / "2026-06-25-m09.html"
    json_file = reports / "2026-06-25-m09.json"
    assert html_file.exists() and json_file.exists()
    html = html_file.read_text(encoding="utf-8")
    assert "M09" in html and "Heisenberg" in html and "Mermin" in html
    assert json.loads(json_file.read_text(encoding="utf-8"))["experiment"] == "M09-heisenberg"


def test_render_m09_verdict_passes_on_drift_to_zero(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m09(_m09_fixture_report(abs_mag=(0.476, 0.285, 0.143)), date="2026-06-25")
    html = (reports / "2026-06-25-m09.html").read_text(encoding="utf-8")
    assert "✓" in html
    # Names the result: the absence of order, confirmed by the L-drift.
    assert "Mermin" in html and "absence" in html.lower()


def test_render_m09_verdict_is_honest_miss_when_flat(tmp_path, monkeypatch):
    """A non-decreasing ⟨|m|⟩(L) (a fake transition) is kept as a miss, never order."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m09(_m09_fixture_report(abs_mag=(0.30, 0.30, 0.30)), date="2026-06-25")
    html = (reports / "2026-06-25-m09.html").read_text(encoding="utf-8")
    assert "✓" not in html
    assert "not reproduced" in html.lower()


def test_render_m09_appears_in_discovery_and_ledger(tmp_path, monkeypatch):
    """The rendered M09 report is discoverable as a run and rides the ledger as a
    verified green leaf (the drifting fixture passes check_m09 — a reproduced
    *absence* is the green leaf for this milestone)."""
    reports, lab_home = _patch_dirs(tmp_path, monkeypatch)
    from lab import publish, archive
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    monkeypatch.setattr(archive, "LAB_HOME", lab_home)

    render.render_m09(_m09_fixture_report(), date="2026-06-25")
    runs = publish.discover_runs()
    assert any(r["milestone"] == "M09" for r in runs)
    ledger = archive.run_ledger()
    m09_rows = [r for r in ledger if r["milestone"] == "M09"]
    assert m09_rows and m09_rows[0]["verdict"] == "verified"   # drift fixture → green leaf


def test_slug_for_maps_m09_report():
    assert _slug_for(_m09_fixture_report()) == "m09"


# ── M10: antiferromagnetic Ising render path ─────────────────────────────────
def _m10_fixture_report(peak_at=2.27, max_unif=0.02):
    """A synthetic M10 ``to_report``-shaped dict (no GPU).

    Staggered χ_s peaks at ``peak_at``; ``max_unif`` is the flat uniform ⟨|m|⟩
    level (≈0 = the real AFM; large = the silent-FM-revert masquerade → null).
    """
    from lab.m10 import TC_AFM
    T = [round(2.0 + 0.025 * i, 4) for i in range(25)]
    chi = [1.0 / (abs(t - peak_at) + 0.02) for t in T]
    ms = [0.95 if t < peak_at else 0.1 for t in T]   # staggered order melts at peak
    rel = abs(peak_at - TC_AFM) / TC_AFM
    return {
        "experiment": "M10-afm-ising", "headline": "M10 test", "L": 128,
        "T": T, "chi_staggered": chi, "stag_mag": ms,
        "stag_mag_err": [0.01] * len(T),
        "abs_mag": [max_unif] * len(T),
        "energy": [-1.5] * len(T), "specific_heat": [0.5] * len(T),
        "tc_chi": peak_at, "tc_chi_refined": peak_at, "tc_cv_refined": peak_at,
        "tc_benchmark": TC_AFM, "rel_error": rel, "max_abs_mag": max_unif,
        "wall_seconds": 40.0, "config": {"seed": 42, "J": -1.0},
    }


def test_render_m10_writes_permanent_report_pair(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    out = render.render_m10(_m10_fixture_report(), date="2026-06-25")
    html_file = reports / "2026-06-25-m10.html"
    json_file = reports / "2026-06-25-m10.json"
    assert html_file.exists() and json_file.exists()
    html = html_file.read_text(encoding="utf-8")
    assert "M10" in html and "antiferromagnetic" in html.lower() and "staggered" in html.lower()
    assert json.loads(json_file.read_text(encoding="utf-8"))["experiment"] == "M10-afm-ising"


def test_render_m10_verdict_passes_near_benchmark(tmp_path, monkeypatch):
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m10(_m10_fixture_report(peak_at=2.27), date="2026-06-25")
    html = (reports / "2026-06-25-m10.html").read_text(encoding="utf-8")
    assert "✓" in html
    # Names the framework-sanity point (negative J) and the uniform-stays-zero trap.
    assert "negative coupling" in html.lower() and "uniform" in html.lower()


def test_render_m10_verdict_is_honest_null_when_peak_off(tmp_path, monkeypatch):
    """A staggered χ_s peak outside the ±0.1 window is kept as a null, never a pass."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m10(_m10_fixture_report(peak_at=2.5), date="2026-06-25")
    html = (reports / "2026-06-25-m10.html").read_text(encoding="utf-8")
    assert "✓" not in html
    assert "null" in html.lower()


def test_render_m10_verdict_is_honest_null_when_uniform_orders(tmp_path, monkeypatch):
    """A large uniform moment (the silent FM-revert) is a null even if χ_s peaks right."""
    reports, _ = _patch_dirs(tmp_path, monkeypatch)
    render.render_m10(_m10_fixture_report(peak_at=2.27, max_unif=0.9), date="2026-06-25")
    html = (reports / "2026-06-25-m10.html").read_text(encoding="utf-8")
    assert "✓" not in html
    assert "null" in html.lower()


def test_render_m10_appears_in_discovery_and_ledger(tmp_path, monkeypatch):
    """The rendered M10 report is discoverable as a run and rides the ledger as a
    verified green leaf (the exact-peak fixture passes check_m10)."""
    reports, lab_home = _patch_dirs(tmp_path, monkeypatch)
    from lab import publish, archive
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    monkeypatch.setattr(archive, "LAB_HOME", lab_home)

    render.render_m10(_m10_fixture_report(), date="2026-06-25")
    runs = publish.discover_runs()
    assert any(r["milestone"] == "M10" for r in runs)
    ledger = archive.run_ledger()
    m10_rows = [r for r in ledger if r["milestone"] == "M10"]
    assert m10_rows and m10_rows[0]["verdict"] == "verified"   # exact fixture → green leaf


def test_slug_for_maps_m10_report():
    assert _slug_for(_m10_fixture_report()) == "m10"
