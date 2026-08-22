"""A07 — Galilean clockwork, tested with the network unplugged.

Every fixture is a SYNTHETIC Keplerian system whose right answers are
constructed, so the tests grade the pipeline's recovery against ground truth
it can never have peeked at: circular jovicentric orbits at the published
periods, serialized into byte-faithful Horizons CSV VECTORS responses, run
through the same parse → plane-recovery → phase-slope path as the sky.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pytest

from lab import a07
from lab.checks import check_a07


GM = a07.GM_JUPITER_KM3_S2  # km^3 s^-2

#: The constructed system: published periods, Kepler-consistent radii.
DAY_S = 86400.0


def kepler_a_km(period_days: float) -> float:
    T = period_days * DAY_S
    return (GM * T * T / (4.0 * math.pi ** 2)) ** (1.0 / 3.0)


def synthetic_response(moon_id: str, period_days: float,
                       n_days: float = 120.0, step_h: float = 1.0,
                       phase0: float = 0.3, incl_deg: float = 2.0) -> bytes:
    """A Horizons CSV VECTORS response for one circular Keplerian orbit.

    The orbit is tilted by ``incl_deg`` so the plane-recovery step has real
    work to do (a flat orbit would pass even if the projection were wrong).
    """
    a = kepler_a_km(period_days)
    n = 2.0 * math.pi / (period_days)          # rad / day
    v_mag = 2.0 * math.pi * a / (period_days * DAY_S)   # km/s
    inc = math.radians(incl_deg)
    t_jd0 = 2461041.5
    rows = []
    steps = int(n_days * 24.0 / step_h)
    for k in range(steps + 1):
        t_d = k * step_h / 24.0
        th = phase0 + n * t_d
        x, y = a * math.cos(th), a * math.sin(th)
        # tilt about the x-axis
        r = (x, y * math.cos(inc), y * math.sin(inc))
        vx, vy = -v_mag * math.sin(th), v_mag * math.cos(th)
        v = (vx, vy * math.cos(inc), vy * math.sin(inc))
        rows.append(
            f"{t_jd0 + t_d:.9f}, A.D. synth, "
            f"{r[0]:.9E}, {r[1]:.9E}, {r[2]:.9E}, "
            f"{v[0]:.9E}, {v[1]:.9E}, {v[2]:.9E},")
    body = "\n".join(rows)
    return (f"API SYNTHETIC for {moon_id}\n$$SOE\n{body}\n$$EOE\n"
            "End of synthetic\n").encode()


def install_synthetic_cache(cache_dir, periods=None):
    """Write all four moons' synthetic responses where fetch/check look."""
    periods = periods or a07.PUBLISHED_PERIOD_DAYS
    pins = {}
    cache_dir.mkdir(parents=True, exist_ok=True)
    for moon in a07.MOONS:
        blob = synthetic_response(moon, periods[moon],
                                  phase0=0.1 * int(moon[-1]),
                                  incl_deg=1.0 + int(moon[-1]))
        path = cache_dir / a07.cache_basename(moon)
        path.write_bytes(blob)
        pins[moon] = {"file": path.name,
                      "sha256": hashlib.sha256(blob).hexdigest()}
    return pins


# ------------------------------------------------------------- the physics --

def test_the_pipeline_recovers_a_constructed_period_to_1e6(tmp_path):
    blob = synthetic_response("501", a07.PUBLISHED_PERIOD_DAYS["501"])
    t, r, v = a07.parse_vectors(blob.decode())
    m = a07.mean_motion(t, r, v)
    assert abs(m["period_days"] / a07.PUBLISHED_PERIOD_DAYS["501"] - 1.0) < 1e-6
    assert abs(m["a_km"] / kepler_a_km(a07.PUBLISHED_PERIOD_DAYS["501"]) - 1.0) < 1e-6


def test_a_full_synthetic_run_passes_every_grade(tmp_path, monkeypatch):
    monkeypatch.setattr(a07, "CACHE_DIR", tmp_path)
    install_synthetic_cache(tmp_path)
    result = a07.run_a07(cache_dir=tmp_path)   # cache hit: no network
    assert result.passed, json.dumps(result.grades, indent=1)[:800]
    g = result.grades
    assert g["kepler"]["max_fractional_spread"] < 1e-4
    assert g["kepler"]["gm_rel_error"] < 1e-4
    assert g["laplace"]["residual_rel"] < 1e-5


def test_the_callisto_control_keeps_the_resonance_honest(tmp_path, monkeypatch):
    """The Laplace grade must FAIL if the 'resonance' would also close with
    Callisto substituted — a combination that closes for any moon is
    arithmetic, not celestial mechanics. Constructed: give Callisto a period
    that ALSO satisfies the relation; the grade must refuse.
    """
    monkeypatch.setattr(a07, "CACHE_DIR", tmp_path)
    periods = dict(a07.PUBLISHED_PERIOD_DAYS)
    n1 = 2 * math.pi / periods["501"]
    n2 = 2 * math.pi / periods["502"]
    # choose n4 so n1 - 3 n2 + 2 n4 = 0  → Callisto joins the "resonance"
    n4 = (3 * n2 - n1) / 2.0
    periods["504"] = 2 * math.pi / n4
    install_synthetic_cache(tmp_path, periods)
    result = a07.run_a07(cache_dir=tmp_path)
    assert result.grades["laplace"]["pass"] is False
    assert not result.passed


def test_an_outage_answers_nothing(tmp_path, monkeypatch):
    """No cache + no network → the A01 doctrine: raise, never fabricate."""
    monkeypatch.setattr(a07, "CACHE_DIR", tmp_path)
    from lab import a01 as a01_mod

    def refuse(url, **kw):
        raise a01_mod.A01NetworkError("synthetic outage")
    monkeypatch.setattr(a01_mod, "_request", refuse)
    with pytest.raises(a01_mod.A01NetworkError):
        a07.run_a07(cache_dir=tmp_path)


def test_a_response_without_the_table_is_a_named_parse_failure():
    with pytest.raises(a07.A07ParseError, match="SOE"):
        a07.parse_vectors("API ERROR: blocked\nno table here\n")


# ------------------------------------------------------------- the checker --

def _passing_report(tmp_path, monkeypatch):
    monkeypatch.setattr(a07, "CACHE_DIR", tmp_path)
    install_synthetic_cache(tmp_path)
    return a07.to_report(a07.run_a07(cache_dir=tmp_path))


def test_check_a07_rederives_a_true_receipt_from_cached_bytes(tmp_path, monkeypatch):
    report = _passing_report(tmp_path, monkeypatch)
    ok, why = check_a07(report)
    assert ok is True, why
    assert "re-derived" in why


def test_a_poisoned_period_grades_false_not_none(tmp_path, monkeypatch):
    report = _passing_report(tmp_path, monkeypatch)
    report["per_moon"]["Io"]["period_days"] *= 1.01   # the lie
    ok, why = check_a07(report)
    assert ok is False
    assert "does not re-derive" in why


def test_a_tampered_cache_is_false_never_a_shrug(tmp_path, monkeypatch):
    report = _passing_report(tmp_path, monkeypatch)
    path = tmp_path / a07.cache_basename("502")
    path.write_bytes(path.read_bytes().replace(b"$$SOE", b"$$SOE\n2461041.5, X, 1,1,1,1,1,1,"))
    ok, why = check_a07(report)
    assert ok is False
    assert "does not match its" in why or "no longer parses" in why


def test_a_missing_cache_is_none_cannot_rederive(tmp_path, monkeypatch):
    report = _passing_report(tmp_path, monkeypatch)
    (tmp_path / a07.cache_basename("503")).unlink()
    ok, why = check_a07(report)
    assert ok is None
    assert "cannot re-derive" in why


def test_a_foreign_receipt_is_not_graded(tmp_path):
    ok, why = check_a07({"experiment": "A04-blind-transit-search"})
    assert ok is None
