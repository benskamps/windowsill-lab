"""A01 maturity regressions: bounded discovery and independent receipts."""
from __future__ import annotations

import hashlib
import urllib.error

import pytest

from lab import a01, checks


def _product(name: str, uri: str, *, subgroup: str = "LC") -> dict:
    return {
        "productFilename": name,
        "productSubGroupDescription": subgroup,
        "dataURI": uri,
        "size": 123,
    }


def test_discovery_orders_deduplicates_and_stops_after_enough_products(monkeypatch):
    observations = [
        {"obsid": "late", "provenance_name": "SPOC", "sequence_number": 9},
        {"obsid": "early", "provenance_name": "SPOC", "sequence_number": 1},
        {"obsid": "early", "provenance_name": "SPOC", "sequence_number": 1},
        {"obsid": "not-spoc", "provenance_name": "QLP", "sequence_number": 0},
        {"obsid": "middle", "provenance_name": "spoc", "sequence_number": 4},
    ]
    queried: list[str] = []

    def fake_mast(service, params, **_kwargs):
        if service == "Mast.Caom.Filtered":
            return observations
        obsid = params["obsid"]
        queried.append(obsid)
        if obsid == "early":
            return [
                _product("notes.txt", "mast:notes", subgroup="AUX"),
                _product("sector1_lc.fits", "mast:sector1"),
                _product("sector1_duplicate_lc.fits", "mast:sector1"),
            ]
        if obsid == "middle":
            return [
                _product("sector4_tp.fits", "mast:target-pixels", subgroup="TP"),
                _product("sector4_lc.fits", "mast:sector4"),
            ]
        raise AssertionError("discovery queried an observation after reaching its limit")

    monkeypatch.setattr(a01, "_mast", fake_mast)
    products = a01.discover_spoc_light_curves(max_sectors=2)

    assert queried == ["early", "middle"]
    assert [product["sector"] for product in products] == [1, 4]
    assert [product["uri"] for product in products] == ["mast:sector1", "mast:sector4"]


def test_request_has_a_finite_retry_budget(monkeypatch):
    attempts = []

    def fail(_request, *, timeout):
        attempts.append(timeout)
        raise urllib.error.URLError("archive unavailable")

    monkeypatch.setattr(a01.urllib.request, "urlopen", fail)
    monkeypatch.setattr(a01.time, "sleep", lambda _seconds: None)

    with pytest.raises(a01.A01NetworkError, match="3/3 attempts"):
        a01._request("https://example.invalid/a01", retries=2)
    assert len(attempts) == 3


def test_request_refuses_to_start_after_overall_deadline(monkeypatch):
    monkeypatch.setattr(a01.time, "monotonic", lambda: 42.0)
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not start after the deadline")

    monkeypatch.setattr(a01.urllib.request, "urlopen", unexpected)
    with pytest.raises(a01.A01DeadlineExceeded, match="deadline exceeded"):
        a01._request("https://example.invalid/a01", deadline=42.0)
    assert not called


def _report(period: float = checks.WASP18_PERIOD_DAYS,
            depth: float = checks.WASP18_DEPTH_FRACTION) -> dict:
    epochs = list(range(12))
    return {
        "experiment": "A01-tess-hot-jupiter-calibration",
        "transit_times": [1000.0 + period * epoch for epoch in epochs],
        "transit_epochs": epochs,
        "transit_depths": [depth] * len(epochs),
        "kept_transits": [True] * len(epochs),
        "products": [{"sha256": hashlib.sha256(b"real-fits").hexdigest()}],
        "benchmark": {
            "period_days": 99.0,
            "period_err_days": 99.0,
            "depth_fraction": 0.5,
            "depth_err_fraction": 0.5,
        },
    }


def test_check_uses_owned_wasp18_constants_not_report_benchmark():
    ok, detail = checks.check_a01(_report())
    assert ok, detail

    tampered = _report(period=1.2345, depth=0.2)
    tampered["benchmark"] = {
        "period_days": 1.2345,
        "period_err_days": 1.0,
        "depth_fraction": 0.2,
        "depth_err_fraction": 1.0,
    }
    ok, detail = checks.check_a01(tampered)
    assert not ok, detail


def test_check_rejects_length_only_non_hex_product_hash():
    report = _report()
    report["products"] = [{"sha256": "z" * 64}]
    ok, detail = checks.check_a01(report)
    assert not ok, detail
