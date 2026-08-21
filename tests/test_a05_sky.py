"""The sky gates: whose light is this?

The regression these lock down is TIC 77044472 — a lead that walked the whole
light-curve ladder and was HATS-16 b on a neighbour 0.71 px away.
"""
import math

import pytest

from lab import a05_sky


# The real field, from the 2026-08-20 investigation.
NEAR_77044472 = [
    {"tic": "77044471", "sep_px": 0.71, "flux_rel": 10.466, "r_star_sun": 1.1827},
    {"tic": "2051811883", "sep_px": 0.67, "flux_rel": 0.178, "r_star_sun": 0.8511},
]
CROWDSAP_77044472 = 0.11929
DEPTH_77044472 = 0.0634          # detrended PDCSAP, already deblended
PERIOD_77044472 = 2.685728750580555
HATS16B_PERIOD = 2.6865063856827396


def test_separation_px_matches_the_measured_field():
    # 77044471 sits 15.01 arcsec from 77044472 => 0.71 TESS pixels
    sep = a05_sky.separation_px(358.55768, -30.008963, 358.55768, -30.008963 + 15.01 / 3600)
    assert sep == pytest.approx(0.715, abs=0.01)


def test_aperture_shares_sum_to_one_and_favour_the_bright_neighbour():
    sh = a05_sky.aperture_shares(CROWDSAP_77044472, NEAR_77044472)
    total = sh["target"] + sum(sh["neighbours"].values())
    assert total == pytest.approx(1.0, abs=1e-9)
    assert sh["neighbours"]["77044471"] > 0.85
    assert sh["target"] < 0.13


def test_flux_budget_ranks_the_neighbour_as_least_strained():
    fb = a05_sky.flux_budget(DEPTH_77044472, CROWDSAP_77044472, NEAR_77044472,
                             r_star_sun=None)
    # the dip as a share of ALL aperture light is source-independent
    assert fb["d_aperture"] == pytest.approx(DEPTH_77044472 * CROWDSAP_77044472)
    best = fb["candidates"][0]
    assert best["tic"] == "77044471"
    target = next(c for c in fb["candidates"] if c["is_target"])
    # the target must dim ~7x harder than the neighbour to make the same dip
    assert target["implied_depth"] / best["implied_depth"] > 6.0
    # ~1 % on the neighbour is the published HATS-16 b depth (1.214 %)
    assert best["implied_depth"] == pytest.approx(0.0088, abs=0.004)


def test_flux_budget_stays_silent_on_an_uncrowded_target():
    # WASP-18: CROWDSAP 0.987, no meaningful neighbours. The gate must not fire.
    fb = a05_sky.flux_budget(0.0109, 0.9872,
                             [{"tic": "x", "sep_px": 3.0, "flux_rel": 0.01}],
                             r_star_sun=1.26)
    assert fb["verdict"] is None


def test_flux_budget_refuses_without_crowdsap():
    assert a05_sky.flux_budget(0.01, None, NEAR_77044472)["reason"] == "no-crowdsap"


def test_neighbour_crosscheck_finds_hats16b_on_the_neighbour():
    def lookup(tic):
        if tic == "77044471":
            return {"period_days": HATS16B_PERIOD, "disposition": "KP",
                    "toi": "228.01", "name": "HATS-16 b"}
        return None

    res = a05_sky.neighbour_crosscheck(PERIOD_77044472, NEAR_77044472, lookup)
    assert res["verdict"] == "blended-known-planet"
    assert res["matches"][0]["tic"] == "77044471"
    assert res["matches"][0]["alias_n"] == 1
    assert "HATS-16 b" in res["reason"] or "228.01" in res["reason"]


def test_neighbour_crosscheck_is_alias_aware():
    def lookup(tic):
        return {"period_days": 2.0 * PERIOD_77044472, "disposition": "KP"}

    res = a05_sky.neighbour_crosscheck(PERIOD_77044472, NEAR_77044472, lookup)
    assert res["verdict"] == "blended-known-planet"
    assert res["matches"][0]["alias_n"] == 2


def test_neighbour_crosscheck_ignores_distant_stars():
    far = [{"tic": "999", "sep_px": 40.0, "flux_rel": 5.0}]
    res = a05_sky.neighbour_crosscheck(
        PERIOD_77044472, far,
        lambda _t: {"period_days": PERIOD_77044472, "disposition": "KP"})
    assert res["verdict"] is None


def test_neighbour_crosscheck_ignores_a_period_that_does_not_match():
    res = a05_sky.neighbour_crosscheck(
        PERIOD_77044472, NEAR_77044472,
        lambda _t: {"period_days": 7.77, "disposition": "KP"})
    assert res["verdict"] is None


def test_cluster_detections_groups_one_event_seen_through_two_apertures():
    rows = [
        {"tic": "77044472", "period_days": PERIOD_77044472,
         "ra": 358.55768, "dec": -30.008963, "implied_depth": 0.0634},
        {"tic": "77044471", "period_days": HATS16B_PERIOD,
         "ra": 358.55768, "dec": -30.008963 + 15.01 / 3600,
         "implied_depth": 0.0088},
        {"tic": "999", "period_days": 11.3, "ra": 10.0, "dec": 10.0,
         "implied_depth": 0.01},
    ]
    clusters = a05_sky.cluster_detections(rows)
    blended = [c for c in clusters if c["n_members"] == 2]
    assert len(blended) == 1
    # the least-strained member is named the source
    assert blended[0]["source_tic"] == "77044471"
    assert blended[0]["n_shadows"] == 1
    assert any(c["n_members"] == 1 for c in clusters)
