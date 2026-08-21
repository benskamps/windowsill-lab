"""FAP resolution: a bound pinned at its floor is not a measurement."""
import pytest

from lab import a05_stats


def test_resolution_floor_is_the_add_one_rule():
    assert a05_stats.resolution_floor(256) == pytest.approx(1 / 257)
    assert a05_stats.resolution_floor(16384) == pytest.approx(1 / 16385)


def test_the_2026_08_20_ledger_value_is_saturated():
    """130 of 133 graded targets read exactly this. It is 1/257, not a
    measurement of how significant they are."""
    assert a05_stats.saturated(0.0038910505836575876, 256) is True


def test_an_unsaturated_fap_is_not_flagged():
    assert a05_stats.saturated(0.05, 256) is False


def test_escalation_ladder_is_monotone_and_terminates():
    assert a05_stats.next_rung(256) == 2048
    assert a05_stats.next_rung(2048) == 16384
    assert a05_stats.next_rung(16384) is None


def test_survey_trials_states_the_look_elsewhere_across_stars():
    """The per-target FAP corrects across PERIODS, not across STARS."""
    out = a05_stats.survey_trials(7346, 1 / 257)
    assert out["expected_false_alarms"] == pytest.approx(28.58, abs=0.1)
    assert out["p_at_least_one"] > 0.99


def test_escalation_makes_the_survey_claim_survivable():
    out = a05_stats.survey_trials(7346, a05_stats.resolution_floor(16384))
    assert out["expected_false_alarms"] < 1.0
