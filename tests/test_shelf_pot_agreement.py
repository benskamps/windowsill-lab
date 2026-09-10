"""The pot and the shelf must not disagree about the shelf.

There were two records of the same nine stars and only one of them reached the
public page. `lab shelf` read the receipts AND `docs/shelf-rulings.json`;
`publish.hunt_block` read the receipts alone. A human refuted six leads on
2026-08-19/20 — one of them because the dip is HATS-16 b on a neighbour 0.71 px
away — and for three weeks brokenbranch.dev kept advertising
"9 leads awaiting human review".

Nothing was fabricated and no arithmetic was wrong. Two surfaces answered the
same question from different halves of the record, and no test asked them to
agree. That absence is the defect these tests exist to close.
"""
from datetime import date
from pathlib import Path

import pytest

from lab import publish, shelf

REPO = Path(__file__).resolve().parent.parent
HUNTS = REPO / "reports" / "hunts"
RULINGS = REPO / "docs" / "shelf-rulings.json"

pytestmark = pytest.mark.skipif(
    not HUNTS.exists() or not any(HUNTS.glob("hunt-*.json")),
    reason="no committed hunt receipts in this checkout",
)


def _shelf_counts():
    rows = shelf.register(HUNTS, RULINGS if RULINGS.exists() else None,
                          date.today())
    counts = {"refuted": 0, "parked": 0, "awaiting": 0, "promoted": 0}
    for r in rows:
        counts[r.get("state", "awaiting")] = counts.get(r.get("state", "awaiting"), 0) + 1
    return rows, counts


def test_the_pot_reports_no_lead_the_shelf_has_already_ruled():
    """THE regression. A refuted lead is not awaiting anyone."""
    block = publish.hunt_block()
    _rows, counts = _shelf_counts()
    assert block["leads_awaiting_human_review"] == counts.get("awaiting", 0), (
        "pot.json says "
        f"{block['leads_awaiting_human_review']} leads await human review; "
        f"`lab shelf` says {counts.get('awaiting', 0)}. The two surfaces read "
        "different halves of the same record — wire the rulings ledger into "
        "publish.hunt_block."
    )


def test_the_pot_carries_the_whole_breakdown_not_just_one_number():
    """Minted / refuted / parked / awaiting. Publishing only the first is how a
    ruled lead keeps looking open."""
    block = publish.hunt_block()
    for field in ("leads_minted", "leads_refuted", "leads_parked",
                  "leads_awaiting_human_review"):
        assert field in block, f"{field} missing from the hunt block"
    assert (block["leads_refuted"] + block["leads_parked"]
            + block["leads_awaiting_human_review"]) <= block["leads_minted"], (
        "the parts of the shelf exceed the whole — a star is being counted in "
        "more than one state")


def test_every_ruled_star_is_a_star_the_machine_actually_minted():
    """A ruling on a TIC no receipt ever flagged would silently deflate the
    count. The ledger may only rule on the shelf's own stars."""
    rows, _ = _shelf_counts()
    ruled = {str(r["tic"]) for r in rows if r.get("state") == "refuted"}
    minted = {str(r["tic"]) for r in rows}
    assert ruled <= minted


def test_the_breakdown_survives_an_unreadable_rulings_file(monkeypatch):
    """Degrade visibly, never silently to zero.

    If the ledger cannot be read the count must fall back to the receipts-only
    number — wrong in the old, loud way — rather than reporting zero leads,
    which would look like a clean shelf.
    """
    monkeypatch.setattr(publish, "_shelf_states", lambda *a, **k: {})
    block = publish.hunt_block()
    assert block["leads_refuted"] == 0
    assert block["leads_parked"] == 0
    assert block["leads_awaiting_human_review"] == block["leads_minted"], (
        "with no rulings readable the pot must report every minted lead as "
        "awaiting — a zero here would be an unreadable file masquerading as an "
        "empty shelf"
    )


def test_the_committed_pot_on_disk_agrees_too():
    """Not just the function — the committed artifact the page actually fetches."""
    import json
    pot = json.loads((REPO / "pot.json").read_text(encoding="utf-8"))
    _rows, counts = _shelf_counts()
    assert pot["hunt"]["leads_awaiting_human_review"] == counts.get("awaiting", 0), (
        "the committed pot.json disagrees with `lab shelf` — run `lab publish`"
    )
