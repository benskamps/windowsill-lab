"""§3 of the shelf-exit contract: a lead is a property of a star, not a sector.

`lab.a05_star` assembles every committed observation of one TIC and grades the
STAR: per-sector fold evidence combined through `combine_p2_folds` (the
VET-F2-corrected signed quantity — never the folded magnitude), per-sector
verdicts aggregated, and every sector that could NOT be combined named with
its reason. An ungraded sector is a statement, not an omission.

Two fixtures anchor these tests to reality:

* the 2026-08-19 shelf sweep (`docs/investigations/2026-08-19-shelf-sweep.json`)
  — internally consistent by construction (difference/sigma == difference_sigma)
  and NOT reproducible from the committed receipts, because the sweep pulled
  every archival sector fresh while the receipts hold one sector per shelf
  star, from before the fold gate existed. The module must SAY that, loudly,
  rather than emit a one-sector "combination".
* the TIC 287328866 numbers from `combine_p2_folds`' own docstring
  (+0.00258±0.00041 and +0.00164±0.00047) — the live case §3 was written on.
"""
from __future__ import annotations

import json
from pathlib import Path

from lab import a05_star, shelf
from lab.a05_fold import combine_p2_folds

REPO = Path(__file__).resolve().parents[1]
SWEEP = REPO / "docs" / "investigations" / "2026-08-19-shelf-sweep.json"
HUNTS = REPO / "reports" / "hunts"


# ---------------------------------------------------------------- helpers --

def fold(signed, err_a, err_b, sigma=None, significant=True, phase=0.25):
    """A p2_fold evidence dict with exactly the fields combine_p2_folds reads."""
    import math
    s = math.hypot(err_a, err_b)
    return {
        "signed_difference": signed,
        "difference_sigma": sigma if sigma is not None else abs(signed) / s,
        "both_eclipses_significant": significant,
        "eclipse_a": {"sigma": err_a},
        "eclipse_b": {"sigma": err_b},
        "deeper_phase": phase,
    }


def obs(tic, sector, disposition="lead-awaiting-human-review", p2=None,
        receipt=None, day="2026-08-20"):
    row = {"tic": tic, "disposition": disposition, "period_days": 5.0,
           "depth": 0.05, "disposition_evidence": {}}
    if p2 is not None:
        row["disposition_evidence"]["fold"] = {"p2_fold": p2}
    return {"tic": tic, "sector": sector, "day": day,
            "receipt": receipt or f"hunt-{day}-s{sector}.json",
            "disposition": disposition, "row": row}


# ----------------------------------------------------------- the dossier --

def test_two_sectors_combine_through_the_reviewed_method_exactly():
    """The module must produce byte-identical numbers to combine_p2_folds —
    it wraps the reviewed statistic, it does not reimplement it."""
    folds = [fold(0.00258, 0.00029, 0.00029), fold(0.00164, 0.00033, 0.00033)]
    d = a05_star.star_dossier(287328866, [obs(287328866, 2, p2=folds[0]),
                                          obs(287328866, 3, p2=folds[1])])
    expected = combine_p2_folds(folds)
    assert d["combined_fold"] == expected
    assert d["combined_fold"]["n_sectors"] == 2
    assert d["graded_sectors"] == [2, 3]
    assert d["ungraded"] == []


def test_a_sector_without_fold_evidence_is_named_never_dropped():
    d = a05_star.star_dossier(111, [
        obs(111, 2, p2=fold(0.002, 0.0004, 0.0004)),
        obs(111, 3, p2=None),   # pre-2026-08-19 receipt: no fold gate ran
    ])
    assert d["graded_sectors"] == [2]
    (u,) = d["ungraded"]
    assert u["sector"] == 3 and "no fold evidence" in u["reason"]
    assert d["combined_fold"]["reason"] == "insufficient-sectors", \
        "one graded sector must refuse to call itself a combination"


def test_unsigned_fold_evidence_is_refused_and_named():
    """A pre-VET-F2 fold dict (no signed_difference) is the vacuous path —
    combine_p2_folds refuses it; the dossier says which sector and why."""
    bad = fold(0.002, 0.0004, 0.0004)
    del bad["signed_difference"]
    d = a05_star.star_dossier(222, [obs(222, 2, p2=bad),
                                    obs(222, 3, p2=fold(0.002, 4e-4, 4e-4))])
    (u,) = d["ungraded"]
    assert u["sector"] == 2 and "unsigned" in u["reason"]


def test_per_sector_verdicts_ride_the_dossier():
    d = a05_star.star_dossier(333, [
        obs(333, 2, p2=fold(0.002, 0.0004, 0.0004)),
        obs(333, 5, disposition="eclipsing-binary-odd-even"),
    ])
    assert d["sector_verdicts"] == {5: "eclipsing-binary-odd-even"}


# --------------------------------------------------- the sweep as anchor --

def test_the_sweep_fixture_is_internally_consistent():
    data = json.loads(SWEEP.read_text(encoding="utf-8"))
    assert len(data) == 6
    for tic, star in data.items():
        c = star["combined"]
        assert abs(c["difference"] / c["sigma"] - c["difference_sigma"]) < 1e-9


def test_committed_receipts_cannot_reproduce_the_sweep_and_the_module_says_so():
    """The honest negative: the sweep's 28.3σ (TIC 234518605, 6 sectors) is
    NOT derivable from the committed receipts — they hold ONE sector for that
    star and predate the fold gate. The module must state exactly that, not
    manufacture a number."""
    grouped = shelf.collect(HUNTS)
    for tic in (234518605, 369603748, 49558810):
        d = a05_star.star_dossier(tic, grouped[tic])
        assert d["combined_fold"]["difference_sigma"] is None
        assert d["combined_fold"]["reason"] == "insufficient-sectors"
        assert d["ungraded"], f"TIC {tic}: pre-fold-gate sectors must be named"
        assert all("no fold evidence" in u["reason"] for u in d["ungraded"])


# ------------------------------------------- shelf: the star-level gate --

def make_receipt(tmp_path, name, sector, generated_at, rows):
    d = tmp_path / "hunts"
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps({
        "experiment": "a05", "generated_at": generated_at,
        "sector": sector, "targets": rows,
        "uniformity": {"n_control": 25, "p_values": [0.5] * 25,
                       "ks_stat": 0.11, "pass": True}}), encoding="utf-8")
    return d


def lead_with_fold(tic, signed, err, fap=0.0039):
    return {
        "tic": tic, "disposition": "lead-awaiting-human-review",
        "period_days": 5.0, "depth": 0.05, "depth_err": 0.002, "sde": 8.0,
        "fap": {"schemes": {"iid": {"fap_empirical": fap},
                            "block": {"fap_empirical": fap}}},
        "disposition_evidence": {
            "physical": {"verdict": None, "reason": None},
            "fold": {"p2_fold": fold(signed, err, err)},
        },
    }


def test_a_star_refuted_only_in_combination_parks_on_the_combined_gate(tmp_path):
    """TIC 287328866's shape: each sector under the 5σ bar alone, the
    inverse-variance combination far over it. No single-sector gate fired;
    the star-level one must."""
    make_receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
                 [lead_with_fold(888, 0.0024, 0.00060)])   # 2.8σ alone
    hunts = make_receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                         "2026-08-15T10:00:00",
                         [lead_with_fold(888, 0.0025, 0.00055)])  # 3.2σ alone
    make_receipt(tmp_path, "hunt-2026-08-16-s4.json", 4, "2026-08-16T10:00:00",
                 [lead_with_fold(888, 0.0024, 0.00058)])   # 2.9σ alone
    make_receipt(tmp_path, "hunt-2026-08-17-s5.json", 5, "2026-08-17T10:00:00",
                 [lead_with_fold(888, 0.0023, 0.00057)])   # 2.9σ; combined ≈5.9σ
    from datetime import date
    (e,) = shelf.register(hunts, rulings=None, today=date(2026, 8, 22))
    assert any("combined" in r and "eclipsing-binary-p2-alias" in r
               for r in e["parked_on"]), e["parked_on"]
    assert e["state"] == "parked"


def test_singleton_or_foldless_stars_grade_exactly_as_before(tmp_path):
    """The fallback: no fold evidence -> the register's §4 grading is
    unchanged (same reasons the pre-§3 shelf produced)."""
    row = {"tic": 999, "disposition": "lead-awaiting-human-review",
           "period_days": 5.0, "depth": 0.05, "sde": 8.0,
           "fap": {"schemes": {"iid": {"fap_empirical": 0.0039},
                               "block": {"fap_empirical": 0.0039}}},
           "disposition_evidence": {}}
    hunts = make_receipt(tmp_path, "hunt-2026-08-14-s2.json", 2,
                         "2026-08-14T10:00:00", [row])
    from datetime import date
    (e,) = shelf.register(hunts, rulings=None, today=date(2026, 8, 22))
    assert any("persistence" in r for r in e["parked_on"])
    assert not any("combined" in r for r in e["parked_on"])
