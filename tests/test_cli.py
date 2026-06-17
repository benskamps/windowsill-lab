"""CLI surface — the ``lab`` commands. Torch-free: the m03 command is exercised
with ``m03.run_m03`` + ``render.render_m03`` monkeypatched, so no simulation and
no GPU are ever touched. We only assert the command ROUTES (parses its flags,
calls the runner with them, renders, publishes best-effort) — the analysis and
rendering themselves are covered by test_m03 / test_render.
"""
import lab.cli as cli


def test_help_lists_m03(capsys):
    rc = cli.main(["help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "lab m03" in out
    assert "data-collapse" in out or "data collapse" in out


def test_m03_command_routes_to_runner_and_renderer(monkeypatch, capsys):
    """`lab m03 --L 16,24,32 --device cpu` parses flags, runs M03, renders, and
    tries to publish — all without importing torch (the runner is stubbed)."""
    calls = {}

    class _FakeResult:
        beta_over_nu_fit = 0.125
        collapse_quality = 1e-15
        wall_seconds = 3.0

    def fake_run_m03(**kwargs):
        calls["run"] = kwargs
        return _FakeResult()

    def fake_to_report(result):
        return {"experiment": "M03-data-collapse", "curves": []}

    def fake_render_m03(report, date=None):
        calls["render"] = report
        return "/tmp/fake-2026-06-15-m03.html"

    # Stub the heavy surfaces. Import the modules the CLI imports lazily.
    from lab import m03 as m03_mod
    from lab import render as render_mod
    from lab import publish as publish_mod
    monkeypatch.setattr(m03_mod, "run_m03", fake_run_m03)
    monkeypatch.setattr(m03_mod, "to_report", fake_to_report)
    monkeypatch.setattr(render_mod, "render_m03", fake_render_m03)
    monkeypatch.setattr(publish_mod, "publish", lambda *a, **k: "/tmp/pot.json")

    rc = cli.main(["m03", "--L", "16,24,32", "--device", "cpu", "--sweeps", "200"])
    assert rc == 0
    # Flags were parsed and forwarded to the runner.
    assert calls["run"]["L_values"] == (16, 24, 32)
    assert calls["run"]["device"] == "cpu"
    assert calls["run"]["n_sweeps"] == 200
    # The report was rendered.
    assert calls["render"]["experiment"] == "M03-data-collapse"
    out = capsys.readouterr().out
    assert "M03 data collapse" in out


def test_help_lists_m06(capsys):
    rc = cli.main(["help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "lab m06" in out
    assert "3D" in out and "4.5115" in out


def test_m06_command_routes_to_runner_and_renderer(monkeypatch, capsys):
    """`lab m06 --L 8 --sweeps 200` parses flags, runs M06, renders, publishes —
    the runner + renderer are stubbed so no Monte-Carlo sweep runs in the test."""
    calls = {}

    class _FakeResult:
        tc_chi_refined = 4.504
        tc_benchmark = 4.5115
        rel_error = 0.0017
        wall_seconds = 28.0

    def fake_run_m06(**kwargs):
        calls["run"] = kwargs
        return _FakeResult()

    def fake_to_report(result):
        return {"experiment": "M06-3d-ising", "T": [], "chi": []}

    def fake_render_m06(report, date=None):
        calls["render"] = report
        return "/tmp/fake-2026-06-16-m06.html"

    from lab import m06 as m06_mod
    from lab import render as render_mod
    from lab import publish as publish_mod
    monkeypatch.setattr(m06_mod, "run_m06", fake_run_m06)
    monkeypatch.setattr(m06_mod, "to_report", fake_to_report)
    monkeypatch.setattr(render_mod, "render_m06", fake_render_m06)
    monkeypatch.setattr(publish_mod, "publish", lambda *a, **k: "/tmp/pot.json")

    rc = cli.main(["m06", "--L", "8", "--sweeps", "200", "--n-temps", "11"])
    assert rc == 0
    assert calls["run"]["L"] == 8
    assert calls["run"]["n_sweeps"] == 200
    assert calls["run"]["n_temps"] == 11
    assert calls["render"]["experiment"] == "M06-3d-ising"
    out = capsys.readouterr().out
    assert "M06 3D simple-cubic Ising" in out
