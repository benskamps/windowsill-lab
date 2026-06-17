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
