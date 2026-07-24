"""M01 must not crown a non-equilibrated sample as the critical point.

The incident (2026-07-23, campaign pass 6, seed=1006): at T=1.8 — deep in the
ordered phase — the sampler failed to equilibrate. |M| came out 0.7756 against
0.9701 at T=1.7 and 0.9383 at T=1.9, i.e. magnetization *rose* with temperature
by 24 sigma, which equilibrium thermodynamics forbids. Its reported error was
0.00672, ~100x its neighbours'. Both chi and chi_abs exploded there (1936.5 and
822.9 against neighbours of ~0.1), the bare argmax crowned the glitch, and M01
reported T_c = 1.800 vs Onsager 2.2692 (z = -4.69). main went red.

The guard is a physics statement, not a tuned outlier filter: in equilibrium
|M|(T) is non-increasing, so a rise is impossible rather than merely unlikely.
Grading it in the run's own reported sigma is what keeps it from being a magic
number.
"""

from __future__ import annotations

import pytest

from lab.checks import ONSAGER_TC, check_m01, nonequilibrated_indices

# T = 1.5 .. 2.4, the low half of the real sweep grid.
_T = [1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4]


def _healthy() -> dict:
    """The 2026-07-22 shape (seed 1001): |M| falls monotonically, peak at 2.3."""
    return {
        "experiment": "M01-ising-verification",
        "T": list(_T),
        "chi": [0.0, 0.0, 0.1, 0.1, 0.2, 0.3, 0.6, 2.1, 765.9, 120.0],
        "abs_mag": [0.986, 0.9796, 0.9701, 0.957, 0.938, 0.911, 0.869, 0.784, 0.284, 0.077],
        "abs_mag_err": [0.00004, 0.00005, 0.00006, 0.00008, 0.00011, 0.00016,
                        0.00024, 0.00054, 0.00373, 0.00210],
    }


def _glitched() -> dict:
    """The 2026-07-23 shape (seed 1006): T=1.8 did not equilibrate."""
    r = _healthy()
    r["chi"] = [0.0, 0.0, 0.1, 1936.5, 0.2, 0.3, 0.6, 2.1, 700.0, 120.0]
    r["abs_mag"] = [0.986, 0.9796, 0.9701, 0.7756, 0.9383, 0.9112,
                    0.8688, 0.7844, 0.2839, 0.0769]
    r["abs_mag_err"] = [0.00004, 0.00005, 0.00006, 0.00672, 0.00011, 0.00016,
                        0.00024, 0.00054, 0.00373, 0.00210]
    return r


def test_healthy_sweep_excludes_nothing_and_is_unchanged():
    """The guard must be inert on a good run — no silent shift of the answer."""
    r = _healthy()
    assert nonequilibrated_indices(r) == []
    ok, msg = check_m01(r)
    assert ok is True, msg
    assert "2.300" in msg
    assert "excluded" not in msg


def test_glitched_sweep_is_currently_crowned_by_the_bare_argmax():
    """Pin the defect: without the guard, argmax picks the glitch."""
    r = _glitched()
    bare_peak = r["T"][max(range(len(r["chi"])), key=lambda i: r["chi"][i])]
    assert bare_peak == 1.8
    assert abs(bare_peak - ONSAGER_TC) > 0.4  # nowhere near Onsager


def test_glitched_sweep_excludes_only_the_bad_sample():
    r = _glitched()
    assert nonequilibrated_indices(r) == [3]  # T = 1.8, and nothing else


def test_glitched_sweep_recovers_the_real_peak():
    ok, msg = check_m01(_glitched())
    assert ok is True, msg
    assert "2.300" in msg


def test_exclusion_is_disclosed_not_silent():
    """An excluded sample must appear in the message — quiet repair is a lie."""
    _, msg = check_m01(_glitched())
    assert "excluded" in msg.lower()
    assert "1.800" in msg  # names which sample, so a reader can go look


def test_legacy_report_without_magnetisation_grades_exactly_as_before():
    """Old receipts carry no |M|; they must not start failing or being 'repaired'."""
    r = _healthy()
    del r["abs_mag"]
    del r["abs_mag_err"]
    assert nonequilibrated_indices(r) == []
    ok, msg = check_m01(r)
    assert ok is True, msg
    assert "excluded" not in msg


def test_a_thoroughly_broken_sweep_fails_loudly_instead_of_being_patched_up():
    """The guard rescues a single bad sample, not a broken simulation."""
    r = _healthy()
    # Magnetization ratchets upward with temperature all the way across.
    r["abs_mag"] = [0.10, 0.30, 0.20, 0.50, 0.35, 0.70, 0.55, 0.90, 0.75, 0.99]
    r["abs_mag_err"] = [0.001] * 10
    bad = nonequilibrated_indices(r)
    assert len(bad) > 2
    ok, msg = check_m01(r)
    assert ok is False, msg
    assert "not equilibrated" in msg.lower()


def test_noise_scale_sets_the_bar_not_a_fixed_delta():
    """A rise inside the run's own error bars is noise, not a failure."""
    r = _healthy()
    r["abs_mag"][4] = r["abs_mag"][3] + 0.0001   # rises, but by ~1 sigma
    r["abs_mag_err"] = [0.0001] * 10
    assert nonequilibrated_indices(r) == []


@pytest.mark.parametrize("tag", ["2026-07-22", "2026-07-23"])
def test_both_real_committed_receipts_pass(tag):
    """The regression, against the actual archive rather than a fixture."""
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "reports" / "receipts" / f"run-{tag}-m01.json"
    if not p.exists():
        pytest.skip(f"{p.name} not in this checkout")
    ok, msg = check_m01(json.loads(p.read_text(encoding="utf-8")))
    assert ok is True, f"{tag}: {msg}"
