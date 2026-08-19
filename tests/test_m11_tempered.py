"""M11 goes cold — tempered by default, with the untempered ladder kept beside it.

Ben's ruling, 2026-08-19: re-run tempered and keep both ladders, so nothing this
milestone already published is quietly replaced. These tests hold the two
properties that ruling turns on — the comparison block is really a comparison
(same seed, same ladder, exchange off), and a report that goes cold WITHOUT the
exchange move is refused rather than graded.

Everything here runs tiny on CPU; the physics is M11's own maturity tests' job.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from lab import m11
from lab.checks import M11_UNTEMPERED_FLOOR, check_m11


def _tiny(**kw):
    base = dict(L=6, n_temps=6, n_realizations=3, n_sweeps=120, n_burnin=60,
                device="cpu", seed=7)
    base.update(kw)
    return m11.run_m11(**base)


# ------------------------------------------------------------- the defaults ---

def test_m11_now_runs_below_its_old_floor():
    assert m11.run_m11.__defaults__ is not None
    assert m11.T_FLOOR_TEMPERED < m11.T_FLOOR
    result = _tiny()
    assert result.config["T_min"] == pytest.approx(m11.T_FLOOR_TEMPERED)


def test_m11_tempers_by_default():
    result = _tiny()
    assert result.config["swap_every"] == m11.SWAP_EVERY
    assert result.swap_health is not None
    assert result.swap_health["connected"] in (True, False)   # measured, not None


def test_the_ladder_health_is_reported_so_a_dead_rung_is_visible():
    health = _tiny().swap_health
    assert set(health) >= {"per_pair", "min", "mean", "connected", "argmin_pair"}
    assert len(health["per_pair"]) == 5                        # n_temps - 1


# ------------------------------------------------------- the comparison block ---

def test_the_comparison_ladder_is_present_and_untempered():
    comparison = _tiny().comparison
    assert comparison is not None
    assert comparison["swap_every"] == 0
    assert "q2_argmax_T" in comparison


def test_the_comparison_uses_the_same_ladder_as_the_tempered_run():
    """Different temperatures would make it a different experiment, not a control."""
    result = _tiny()
    assert result.comparison["T"] == pytest.approx(result.T)


def test_the_comparison_carries_its_own_equilibration_diagnostic():
    comparison = _tiny().comparison
    assert comparison["max_abs_q_mean"] >= 0.0
    assert isinstance(comparison["monotone_broadening"], bool)


def test_the_comparison_can_be_switched_off_for_a_cheap_run():
    assert _tiny(comparison=False).comparison is None


def test_no_comparison_is_produced_when_there_was_nothing_to_compare_against():
    """An untempered primary has no exchange move to contrast with."""
    result = _tiny(swap_every=0, T_min=m11.T_FLOOR)
    assert result.comparison is None
    assert result.swap_health is None


def test_the_comparison_reaches_the_report():
    report = m11.to_report(_tiny())
    assert report["comparison"]["swap_every"] == 0
    assert report["swap_health"] is not None
    assert report["config"]["swap_every"] == m11.SWAP_EVERY


# ------------------------------------------------------------- the cold guard ---

def test_going_cold_without_tempering_is_flagged_on_the_result():
    assert _tiny(swap_every=0, T_min=0.3).below_untempered_floor is True


def test_going_cold_with_tempering_is_not_flagged():
    assert _tiny(T_min=0.3).below_untempered_floor is False


def test_staying_warm_without_tempering_is_not_flagged():
    assert _tiny(swap_every=0, T_min=m11.T_FLOOR).below_untempered_floor is False


def _report_with(config_overrides):
    """A real M11 report with its config overridden.

    Note the explicit ``swap_every`` in each caller: the newest report on disk is
    now the TEMPERED one, so a test that only overrode ``T_min`` would silently
    inherit ``swap_every=50`` and stop testing the guard it was written for. The
    fixture must not carry an assumption the repo can change out from under it.
    """
    path = sorted((pathlib.Path(__file__).resolve().parents[1] / "reports")
                  .glob("*-m11.json"))[-1]
    report = json.loads(path.read_text(encoding="utf-8"))
    report["config"] = dict(report["config"], **config_overrides)
    return report


def test_the_check_refuses_a_cold_untempered_report():
    ok, detail = check_m11(_report_with({"T_min": 0.3, "swap_every": 0}))
    assert ok is False
    assert "parallel tempering" in detail


def test_the_check_grades_a_cold_tempered_report_normally():
    ok, _ = check_m11(_report_with({"T_min": 0.3, "swap_every": 50}))
    assert ok is True


def test_the_check_still_passes_every_historical_report():
    """Reports predating the flag have no swap_every key and T_min at the floor."""
    for path in (pathlib.Path(__file__).resolve().parents[1] / "reports").glob("*-m11.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        assert check_m11(report)[0] is True, path.name


def test_the_floor_is_owned_by_the_check_not_by_the_report():
    """A run must not be able to widen its own trustworthy window."""
    report = _report_with({"T_min": 0.3, "swap_every": 0,
                           "M11_UNTEMPERED_FLOOR": 0.1, "untempered_floor": 0.1})
    assert check_m11(report)[0] is False
    assert M11_UNTEMPERED_FLOOR == pytest.approx(m11.T_FLOOR)


def test_the_guard_ignores_a_nonsense_t_min_rather_than_crashing():
    for bad in ("cold", None, True):
        report = _report_with({"T_min": bad, "swap_every": 0})
        assert check_m11(report)[0] in (True, False, None)


# ------------------------------------------------------------- the headline ---

def test_the_headline_names_the_sampler():
    """This milestone stopped at T=0.6 for its whole life because of the sampler.

    A headline reaching 0.30 without saying WHY reads as the same measurement
    getting a better answer. It is a different sampler, and the reader is owed
    that word.
    """
    assert "parallel tempering" in m11.to_report(_tiny())["headline"]
    plain = _tiny(swap_every=0, T_min=m11.T_FLOOR, comparison=False)
    assert "single-spin Metropolis" in m11.to_report(plain)["headline"]


def test_the_headline_surfaces_the_untempered_turnover():
    """The dip must not be buried in a JSON block while the headline quotes only
    the tempered number — that is the silent replacement the ruling forbids."""
    headline = m11.to_report(_tiny())["headline"]
    assert "without the exchange move turns over at" in headline


def test_the_headline_reports_the_hardware_it_actually_used():
    """hw() labels a config with no device key as CPU, so omitting it
    under-reported the hardware in a public headline."""
    result = _tiny(device="cpu")
    assert result.config["device"] == "cpu"
    assert m11.to_report(result)["headline"].endswith("on CPU")
