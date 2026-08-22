"""CLI surface — the ``lab`` commands. Torch-free: the m03 command is exercised
with ``m03.run_m03`` + ``render.render_m03`` monkeypatched, so no simulation and
no GPU are ever touched. We only assert the command ROUTES (parses its flags,
calls the runner with them, renders, publishes best-effort) — the analysis and
rendering themselves are covered by test_m03 / test_render.
"""
import lab.cli as cli


def test_verify_command_is_fail_closed_for_missing_evidence(monkeypatch, capsys):
    from lab import checks as checks_mod

    monkeypatch.setattr(checks_mod, "verify", lambda _ids=None: [
        {"id": "M01", "status": "pass", "detail": "ok"},
        {"id": "M02", "status": "no-report", "detail": "missing receipt"},
        {"id": "M03", "status": "unchecked", "detail": "no checker"},
    ])
    rc = cli.main(["verify"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "M02 (no-report)" in captured.err
    assert "M03 (unchecked)" in captured.err


def test_verify_command_passes_only_when_every_result_passes(monkeypatch, capsys):
    from lab import checks as checks_mod

    monkeypatch.setattr(checks_mod, "verify", lambda _ids=None: [
        {"id": "M01", "status": "pass", "detail": "reproduced"},
        {"id": "M14", "status": "pass", "detail": "identity reproduced"},
    ])
    assert cli.main(["verify"]) == 0
    assert "VERIFICATION INCOMPLETE" not in capsys.readouterr().err


def test_verify_command_fails_when_filter_matches_nothing(monkeypatch, capsys):
    from lab import checks as checks_mod

    monkeypatch.setattr(checks_mod, "verify", lambda _ids=None: [])
    assert cli.main(["verify", "ZZ99"]) == 1
    assert "no verified milestones" in capsys.readouterr().err


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


def test_m02_command_forwards_updater(monkeypatch, capsys):
    """`lab m02 ... --updater wolff` parses the flag and forwards it to run_fss.

    Regression guard: the m02 handler references ``ns.updater`` for its banner
    and the run call, so ``_parse_m02`` MUST define ``--updater`` (default
    'wolff') or the command crashes with AttributeError. The runner + renderer
    are stubbed so no Monte-Carlo sweep runs."""
    calls = {}

    class _FakeResult:
        slope = 1.75
        r2 = 0.999
        wall_seconds = 42.0

    def fake_run_fss(**kwargs):
        calls["run"] = kwargs
        return _FakeResult()

    def fake_to_report(result):
        return {"experiment": "M02-finite-size-scaling", "curves": []}

    def fake_render_fss(report, date=None):
        calls["render"] = report
        return "/tmp/fake-2026-06-15-m02.html"

    from lab import fss as fss_mod
    from lab import render as render_mod
    from lab import publish as publish_mod
    monkeypatch.setattr(fss_mod, "run_fss", fake_run_fss)
    monkeypatch.setattr(fss_mod, "to_report", fake_to_report)
    monkeypatch.setattr(render_mod, "render_fss", fake_render_fss)
    monkeypatch.setattr(publish_mod, "publish", lambda *a, **k: "/tmp/pot.json")

    # explicit flag
    rc = cli.main(["m02", "--L", "8,12", "--device", "cpu", "--sweeps", "100",
                   "--updater", "wolff"])
    assert rc == 0
    assert calls["run"]["L_values"] == (8, 12)
    assert calls["run"]["updater"] == "wolff"
    assert calls["run"]["n_sweeps"] == 100
    out = capsys.readouterr().out
    assert "M02 finite-size scaling" in out
    assert "cluster updates" in out and "wolff" in out    # banner names the regime

    # default (no flag) is still wolff, and metropolis prints "sweeps"
    rc = cli.main(["m02", "--L", "8", "--device", "cpu", "--updater", "metropolis"])
    assert rc == 0
    assert calls["run"]["updater"] == "metropolis"
    out = capsys.readouterr().out
    assert "sweeps · metropolis" in out


def test_i01_bare_fails_fast_without_publishing(monkeypatch, capsys):
    """N1: `lab i01` with no camera, no --frames, and no WINDOWSILL_I01_FRAMES
    measures nothing — so it must exit nonzero (rc 3) with the named error and
    write NO dated report, NO receipt, NO public row. The regression this
    replaces: the CLI laundered the no_real_frames absence into a completed run
    (rc 0 + a published null science row per pass)."""
    monkeypatch.delenv("WINDOWSILL_I01_FRAMES", raising=False)
    from lab import publish as publish_mod
    from lab import render as render_mod

    calls = {}
    monkeypatch.setattr(
        render_mod, "render_calibration",
        lambda report, date=None: calls.setdefault("render", report) or "/tmp/i01.html",
    )
    monkeypatch.setattr(
        publish_mod, "publish",
        lambda *a, **k: calls.setdefault("publish", True) and "/tmp/pot.json",
    )
    rc = cli.main(["i01"])
    out = capsys.readouterr().out
    assert rc == 3
    assert "no_real_frames" in out
    assert "render" not in calls        # no dated report
    assert "publish" not in calls       # no receipt, no public row


def test_i01_measured_null_still_publishes(monkeypatch, capsys):
    """The boundary the fail-fast must NOT cross: a MEASURED null (real frames
    loaded and analyzed, calibration failed) is an honest science row — it
    still renders, publishes, and exits 0. A skip is a disclosed absence; a
    measured null is data."""
    from lab import i01 as i01_mod
    from lab import publish as publish_mod
    from lab import render as render_mod

    class _MeasuredNull:
        hardware_available = True
        calibration_passed = False
        reason = "temporal noise exceeded the calibration bound"
        analysis = {"shape": [24, 8, 8], "hot_pixel_count": 3,
                    "track_candidate_count": 1}
        input_evidence = []
        wall_seconds = 2.0
        error_code = None
        capture_metadata = None

    calls = {}
    monkeypatch.setattr(i01_mod, "run_i01", lambda *a, **k: _MeasuredNull())
    monkeypatch.setattr(i01_mod, "to_report", lambda result: {"experiment": "I01"})
    monkeypatch.setattr(
        render_mod, "render_calibration",
        lambda report, date=None: calls.setdefault("render", report) or "/tmp/i01.html",
    )
    monkeypatch.setattr(
        publish_mod, "publish",
        lambda *a, **k: calls.setdefault("publish", True) and "/tmp/pot.json",
    )
    rc = cli.main(["i01"])
    assert rc == 0
    assert "render" in calls and "publish" in calls


def test_setup_dry_run_never_claims_the_scheduler_was_installed(monkeypatch, capsys):
    from lab import setup as setup_mod

    monkeypatch.setattr(setup_mod, "health_checks", lambda: [
        {"name": "test", "ok": True, "detail": "ready"},
    ])
    monkeypatch.setattr(setup_mod, "install", lambda **_: {
        "method": "schtasks",
        "nightly": "nightly.ps1",
        "steps": ["(dry run — nothing written)"],
        "notes": [],
    })

    assert cli.main(["setup", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run complete — nothing was written or scheduled" in out
    assert "will now grow on its own" not in out


# ── lab m05-hex — the honeycomb command ───────────────────────────────────────

def test_parse_m05_hex_defaults_bracket_the_exact_honeycomb_tc():
    """The default window must actually straddle T_c = 2/ln(2+√3) ≈ 1.5187, with
    the peak comfortably interior — a parabola-refined peak on an endpoint would
    silently degrade to the coarse argmax."""
    import math

    from lab.cli import _parse_m05_hex

    ns = _parse_m05_hex([])
    tc = 2.0 / math.log(2.0 + math.sqrt(3.0))
    assert ns.t_min < tc < ns.t_max
    # Interior by at least two grid steps on each side.
    step = (ns.t_max - ns.t_min) / (ns.n_temps - 1)
    assert tc - ns.t_min > 2 * step and ns.t_max - tc > 2 * step
    assert ns.seed == 42                    # house determinism convention
    assert ns.L == 128 and ns.L % 2 == 0    # even L, the honeycomb's only constraint


def test_parse_m05_hex_window_is_not_the_triangular_one():
    """The triangular default window [3.3, 4.0] contains no honeycomb physics at
    all — a copy-paste of it would sweep 2.2× above T_c and find no peak."""
    from lab.cli import _parse_m05, _parse_m05_hex

    tri, hexa = _parse_m05([]), _parse_m05_hex([])
    assert hexa.t_max < tri.t_min
    assert hexa.L != tri.L      # 128 (even) vs 129 (multiple of 3)


def test_m05_hex_is_advertised_in_the_help_text():
    from lab.cli import HELP

    assert "lab m05-hex" in HELP
    assert "2/ln(2+" in HELP


def test_bare_hunt_dispatch_pins_a_slice_the_slot_can_actually_finish(monkeypatch):
    """The scheduled (bare) hunt's --n default must be completable inside its
    own --minutes default, or no receipt is ever written and the box's turn
    freezes: an incomplete slice writes nothing BY DESIGN (a05_hunt refuses
    to let a partial slice masquerade as a survey), so a default slice sized
    beyond the budget is a contract that can never be met. Measured on win
    2026-08-22 after the 08-20 search level-ups: --n 150 against 45 minutes
    advanced ~2 targets per slot — a receipt in weeks. Ruled by Ben
    2026-08-22: shrink the bare slice (loam's committed receipts are n=5-25,
    so small slices are established survey practice); explicit flags still
    override for attended runs.
    """
    import subprocess

    captured = {}

    def fake_call(argv, **kwargs):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(cli, "_hunt_status_for_dispatch",
                        lambda: {"per_sector": {2: 100}})
    rc = cli.main(["hunt"])
    assert rc == 0
    argv = captured["argv"]
    n = int(argv[argv.index("--n") + 1])
    minutes = float(argv[argv.index("--minutes") + 1])
    assert n <= 15, (
        f"bare slice --n {n} is not completable in a {minutes}-minute slot "
        "at post-2026-08-20 per-target cost")
    assert minutes == 45.0, "the slot budget itself is unchanged"
    assert argv[argv.index("--sector") + 1] == "2"


def test_explicit_hunt_flags_still_override_the_bare_defaults(monkeypatch):
    import subprocess

    captured = {}
    monkeypatch.setattr(subprocess, "call",
                        lambda argv, **kw: captured.update(argv=argv) or 0)
    monkeypatch.setattr(cli, "_hunt_status_for_dispatch",
                        lambda: {"per_sector": {2: 100}})
    assert cli.main(["hunt", "--n", "200", "--minutes", "100",
                     "--sector", "3"]) == 0
    argv = captured["argv"]
    assert argv[argv.index("--n") + 1] == "200"
    assert argv[argv.index("--minutes") + 1] == "100"
    assert argv[argv.index("--sector") + 1] == "3"


def test_every_runners_entry_resolves_to_a_real_dispatch_branch():
    """STR-4: the RUNNERS→cli seam is an unpinned string — dispatch happens by
    recursive ``main([subcmd])`` against literal ``if cmd == "..."`` branches,
    so a typo'd runner ships green and its rotation slot is permanently dead,
    visible only in task logs. This pins the seam by introspection: every
    subcommand the curriculum can dispatch must appear as a literal branch in
    ``cli.main``. No milestone is executed.
    """
    import inspect
    import re
    from lab.curriculum import RUNNERS

    source = inspect.getsource(cli.main)
    branches = set(re.findall(r'cmd\s*(?:==|in\s*\()\s*\(?["\']([\w-]+)["\']', source))
    branches |= set(re.findall(r'["\']([\w-]+)["\']', " ".join(
        m.group(1) for m in re.finditer(r'cmd\s+in\s+\(([^)]*)\)', source))))
    missing = {mid: sub for mid, sub in RUNNERS.items() if sub not in branches}
    assert not missing, (
        f"RUNNERS entries with no dispatch branch in cli.main: {missing} — "
        "each of these rotation slots would be silently dead")
