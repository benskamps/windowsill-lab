"""The find-your-own-planet kit: one star, the survey's ladder, no planet word.

Every test runs offline on synthetic SPOC files (the same FITS writer the A05
receipt tests use), at the coarse scale those tests established: 27-day
sectors, a 300-period grid, a small null.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from lab import a04, planetkit
from lab.a05_vocab import MACHINE_VOCABULARY

from tests.test_a05_receipts import CADENCE, DAYS, PLANT_DEPTH, PLANT_PERIOD, fits_bytes

TIC = "4206066"
PARAMS = {"seed": 7, "B": 32, "n_periods": 300, "n_placebo": 2}


def _prereg(tmp: Path, sectors=(2,), **extra) -> Path:
    body = {"tic": TIC, "sectors": list(sectors), **PARAMS, **extra}
    path = tmp / "prereg.md"
    path.write_text("# test\n\n```json\n" + json.dumps(body) + "\n```\n")
    return path


def _fits(tmp: Path, sector: int, *, depth: float = 0.0, seed: int = 1,
          tic: str = TIC, binary: bool = False) -> Path:
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, DAYS, CADENCE) + 1000.0 * sector
    f = 1.0 + rng.normal(0.0, 3e-4, len(t))
    if binary:
        # TIC 287328866's geometry (tests/test_a05_fold.py): two unequal
        # eclipses half a 2.0765 d orbit apart. The blind search lands on the
        # 1.04 d alias, which is exactly the trap the odd/even gate exists for.
        p_bin, t0 = 2.0765, t[0] + 0.37 * 2.0765 / 2
        f = a04.inject_box(t, f, p_bin, 0.021, 0.08, t0)
        f = a04.inject_box(t, f, p_bin, 0.0166, 0.08, t0 + p_bin / 2)
    elif depth:
        f = a04.inject_box(t, f, PLANT_PERIOD, depth, duration_days=2.5 / 24)
    path = tmp / f"tess2018234235059-s{sector:04d}-{int(tic):016d}-0121-s_lc.fits"
    path.write_bytes(fits_bytes(t, f))
    return path


def _uncatalogued(tic, period):
    return {"tic": tic, "known_toi": None, "known_planet": None,
            "published_period_days": None, "disposition": None}


def _known_toi(tic, period):
    return {"tic": tic, "known_toi": "1234.01", "known_planet": None,
            "published_period_days": PLANT_PERIOD, "disposition": "PC"}


# ------------------------------------------------------------------ verdicts

def test_quiet_star_says_nothing_above_threshold(tmp_path):
    r = planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2)],
                      catalog=_uncatalogued)
    assert r["star"]["status"] == "nothing-above-threshold"
    assert r["observations"][0]["placebo"]["pass"] is True
    assert r["planets_claimed"] == 0


def test_two_sector_transit_is_a_lead_and_never_a_planet(tmp_path):
    r = planetkit.run(_prereg(tmp_path, sectors=(2, 3)),
                      fits=[_fits(tmp_path, 2, depth=PLANT_DEPTH, seed=1),
                            _fits(tmp_path, 3, depth=PLANT_DEPTH, seed=2)],
                      catalog=_uncatalogued)
    star = r["star"]
    assert star["status"] == "lead-awaiting-human-review"
    assert star["persistent"] is True
    assert star["provisional_single_sector"] is False
    assert "not a planet" in r["verdict"]["may_say"]
    for obs in r["observations"]:
        assert obs["row"]["disposition"] in MACHINE_VOCABULARY
        assert obs["row"]["fap"]["fap_graded"] > 0
        assert "raw_maxima" not in obs["row"]["fap"]["schemes"]["iid"]


def test_single_sector_lead_is_marked_provisional(tmp_path):
    r = planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2,
                                                     depth=PLANT_DEPTH)],
                      catalog=_uncatalogued)
    assert r["star"]["status"] == "lead-awaiting-human-review"
    assert r["star"]["provisional_single_sector"] is True
    assert "provisional" in r["verdict"]["may_say"]


def test_offline_run_cannot_mint_a_lead(tmp_path):
    """An unrun gate is not a passed gate (shelf-exit contract §2)."""
    r = planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2,
                                                     depth=PLANT_DEPTH)],
                      catalog=None)
    assert r["star"]["status"] == "incomplete"
    assert r["catalog_checked"] is False


def test_catalogued_signal_is_already_known(tmp_path):
    r = planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2,
                                                     depth=PLANT_DEPTH)],
                      catalog=_known_toi)
    assert r["star"]["status"] == "already-known"
    assert r["star"]["by"] == {2: "recovery-or-known"}


def test_alternating_eclipses_are_refuted(tmp_path):
    r = planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2,
                                                     binary=True)],
                      catalog=_uncatalogued)
    assert r["star"]["status"] == "refuted"
    word = r["star"]["by"][2]
    assert word == "eclipsing-binary-odd-even"
    assert planetkit.PLAIN[word] in r["verdict"]["may_say"]


def test_csv_input_runs_the_same_ladder(tmp_path):
    rng = np.random.default_rng(3)
    t = np.arange(0.0, DAYS, CADENCE)
    f = a04.inject_box(t, 1.0 + rng.normal(0, 3e-4, len(t)), PLANT_PERIOD,
                       PLANT_DEPTH, duration_days=2.5 / 24)
    path = tmp_path / "lc.csv"
    path.write_text("time,flux\n" + "\n".join(f"{a},{b}" for a, b in zip(t, f)))
    r = planetkit.run(_prereg(tmp_path), csvs=[path], catalog=_uncatalogued)
    assert r["star"]["status"] == "lead-awaiting-human-review"
    assert abs(r["observations"][0]["row"]["period_days"] / PLANT_PERIOD - 1) < 0.01


# ------------------------------------------------------------------ refusals

def test_refuses_sectors_that_were_not_declared(tmp_path):
    with pytest.raises(planetkit.KitError, match="declares sectors"):
        planetkit.run(_prereg(tmp_path, sectors=(2,)),
                      fits=[_fits(tmp_path, 3)], catalog=_uncatalogued)


def test_refuses_a_different_star(tmp_path):
    with pytest.raises(planetkit.KitError, match="declares TIC"):
        planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2, tic="99")],
                      catalog=_uncatalogued)


def test_refuses_a_custom_threshold(tmp_path):
    with pytest.raises(planetkit.KitError, match="threshold is fixed"):
        planetkit.read_prereg(_prereg(tmp_path, sde_threshold=6.5))


def test_receipt_check_refuses_claims():
    base = {"planets_claimed": 0, "star": {"status": "refuted"},
            "observations": [],
            "verdict": {"may_say": "whatever blocks the light is too big to "
                                   "be a planet"}}
    planetkit.check_receipt(base)            # a negative statement is fine
    with pytest.raises(planetkit.KitError, match="planet claim"):
        planetkit.check_receipt({**base, "verdict": {
            "may_say": "I think I found a planet nobody knew existed"}})
    with pytest.raises(planetkit.KitError, match="literal 0"):
        planetkit.check_receipt({**base, "planets_claimed": 1})
    with pytest.raises(planetkit.KitError, match="star status"):
        planetkit.check_receipt({**base, "star": {"status": "planet"}})


def test_kit_vocabulary_has_no_planet_word():
    for word in (*planetkit.STAR_STATUSES, *MACHINE_VOCABULARY):
        assert word != "planet" and "planet-candidate" != word
    assert set(planetkit.PLAIN) >= set(MACHINE_VOCABULARY)


# ---------------------------------------------------------- preregistration

def test_template_round_trips(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(planetkit.prereg_template(TIC, [2, 29]))
    pre = planetkit.read_prereg(path)
    assert pre["declared"]["tic"] == TIC
    assert pre["declared"]["sectors"] == [2, 29]
    assert pre["declared"]["B"] == planetkit.PREREG_DEFAULTS["B"]
    assert pre["git"]["committed"] is False


def test_git_provenance_records_the_commit(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True,
                       capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    path = _prereg(tmp_path)
    git("add", path.name)
    git("commit", "-qm", "prereg")
    prov = planetkit.git_provenance(path)
    assert prov["committed"] is True and prov["clean"] is True
    path.write_text(path.read_text() + "\nedited after\n")
    assert planetkit.git_provenance(path)["clean"] is False


def test_uncommitted_prereg_is_flagged_in_the_verdict(tmp_path):
    r = planetkit.run(_prereg(tmp_path), fits=[_fits(tmp_path, 2)],
                      catalog=_uncatalogued)
    assert any("never committed" in w for w in r["verdict"]["warnings"])


def test_cli_end_to_end(tmp_path, capsys):
    out = tmp_path / "receipt.json"
    fits = _fits(tmp_path, 2, depth=PLANT_DEPTH)
    rc = planetkit.main(["run", "--prereg", str(_prereg(tmp_path)),
                         "--fits", str(fits), "--offline", "--out", str(out)])
    assert rc == 0
    receipt = json.loads(out.read_text())
    assert receipt["star"]["status"] == "incomplete"
    assert "Do not say" in capsys.readouterr().out
    assert planetkit.main(["explain", str(out)]) == 0


def test_doctor_reports_each_requirement_with_a_fix(tmp_path):
    rows = planetkit.doctor(tmp_path, reach=lambda url: (False, "blocked"))
    names = [r["check"] for r in rows]
    assert names[0].startswith("Python") and "numpy" in names
    git_row = next(r for r in rows if r["check"].startswith("git"))
    assert git_row["ok"] is False and "git init" in git_row["fix"]
    mast = next(r for r in rows if r["check"].startswith("MAST"))
    assert mast["ok"] is False and "--fits" in mast["fix"]
