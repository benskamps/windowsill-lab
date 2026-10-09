"""The kit's per-run dashboard: static, offline, and never more than the
verdict. Receipts come from the same synthetic SPOC files as
tests/test_planetkit.py."""
from __future__ import annotations

import json
import re

import pytest

from lab import planetkit, planetkit_dashboard as dash
from lab.planetkit import KitError

from tests.test_planetkit import PLANT_DEPTH, _fits, _known_toi, _prereg, _uncatalogued


def _rt(receipt: dict) -> dict:
    return json.loads(json.dumps(receipt, default=planetkit._json_default))


def _offline_safe(page: str) -> None:
    assert "<script" not in page.lower()
    # no external fetches: only data: images, no stylesheets or fonts by URL
    assert not re.search(r'<(img|link|iframe)[^>]+(src|href)="https?:', page)
    assert "@import" not in page and "url(http" not in page


def test_lead_dashboard_draws_an_unknown_and_quotes_the_verdict(tmp_path):
    fits = [_fits(tmp_path, 2, depth=PLANT_DEPTH), _fits(tmp_path, 3, depth=PLANT_DEPTH, seed=2)]
    r = _rt(planetkit.run(_prereg(tmp_path, sectors=(2, 3)), fits=fits,
                          catalog=_uncatalogued))
    assert r["star"]["status"] == "lead-awaiting-human-review"
    curves = {s: dash.verify_curve(r, s, blob=f.read_bytes())
              for s, f in zip((2, 3), fits)}
    page = dash.render(r, curves=curves,
                       star={"r_star_sun": 0.6, "m_star_sun": 0.6, "source": "test"})
    _offline_safe(page)
    assert "lead-awaiting-human-review" in page
    assert r["verdict"]["may_say"] in page
    assert 'class="unknown"' in page and "not measured" in page
    assert "Kepler III" in page and "orbit " in page
    assert page.count('class="curve"') == 2
    assert "planet" not in r["star"]["status"]


def test_refuted_star_gets_no_companion(tmp_path):
    r = _rt(planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2, binary=True)],
                          catalog=_uncatalogued))
    assert r["star"]["status"] == "refuted"
    page = dash.render(r)
    _offline_safe(page)
    assert 'class="unknown"' not in page
    assert "refuted:" in page


def test_quiet_star_draws_no_orbit_and_asks_for_the_curve(tmp_path):
    r = _rt(planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2)],
                          catalog=_uncatalogued))
    page = dash.render(r)
    assert 'class="orbit"' not in page and 'class="unknown"' not in page
    assert "no orbit to draw" in page
    assert "pass its light curve" in page


def test_already_known_without_mass_says_what_is_missing(tmp_path):
    r = _rt(planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2, depth=PLANT_DEPTH)],
                          catalog=_known_toi))
    assert r["star"]["status"] == "already-known"
    page = dash.render(r)
    assert "needs the star&#x27;s mass" in page


def test_a_different_light_curve_is_refused(tmp_path):
    r = _rt(planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2)],
                          catalog=_uncatalogued))
    (tmp_path / "other").mkdir()
    other = _fits(tmp_path / "other", 2, seed=9)
    with pytest.raises(KitError, match="SHA-256"):
        dash.verify_curve(r, 2, blob=other.read_bytes())


def test_a_claiming_receipt_is_refused(tmp_path):
    r = _rt(planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2)],
                          catalog=_uncatalogued))
    with pytest.raises(KitError):
        dash.render({**r, "planets_claimed": 1})
    forged = json.loads(json.dumps(r))
    forged["claim_boundary"] = "We discovered a new planet."
    with pytest.raises(KitError, match="planet claim"):
        dash.render(forged)


def test_unknown_star_keys_are_refused(tmp_path):
    r = _rt(planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2)],
                          catalog=_uncatalogued))
    with pytest.raises(KitError, match="unknown keys"):
        dash.render(r, star={"planet": "yes"})


def test_cli_writes_the_page_beside_the_receipt(tmp_path, capsys):
    fits = _fits(tmp_path, 2, depth=PLANT_DEPTH)
    out = tmp_path / "receipt-TIC4206066-test.json"
    assert planetkit.main(["run", "--prereg", str(_prereg(tmp_path)),
                           "--fits", str(fits), "--offline", "--out", str(out)]) == 0
    assert dash.main([str(out), "--fits", str(fits)]) == 0
    page = out.with_suffix(".html").read_text()
    _offline_safe(page)
    assert "TIC 4206066" in page and 'class="curve"' in page


def test_run_writes_the_dashboard_beside_the_receipt(tmp_path, capsys):
    out = tmp_path / "receipt-TIC4206066-auto.json"
    assert planetkit.main(["run", "--prereg", str(_prereg(tmp_path)),
                           "--fits", str(_fits(tmp_path, 2, depth=PLANT_DEPTH)),
                           "--offline", "--out", str(out)]) == 0
    assert "dashboard:" in capsys.readouterr().out
    page = out.with_suffix(".html").read_text()
    _offline_safe(page)
    assert "data:image/svg+xml;base64," in page   # the kit's own fold plot
