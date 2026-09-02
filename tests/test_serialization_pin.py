"""DET-3 — the committed artifacts' BYTES are the spec, and this pins them.

"Never ``sort_keys``" was enforced by comments only (``scripts/a05_hunt.py``
around line 310 is the clearest one). Every sync gate in this repo compares
PARSED objects — ``json.loads(a) == json.loads(b)`` — and parsed objects are
blind to key order, indent width, ``ensure_ascii`` and the trailing newline. So
a refactor that switched a serializer would ship green and rewrite every
committed artifact on its next run: a whole-file diff on ``pot.json``, a
whole-file diff on every receipt, and a guaranteed conflict with the other box
— the wedge incidents this repo already has scripts to recover from.

This file pins the layout that exists today. It changes nothing: the goldens
below were read off the current serializers and off the artifacts already
committed to the repo.

Four DIFFERENT layouts are in force and each is deliberate:

  ``pot.json``            indent=2, INSERTION order, ensure_ascii, "\\n"
  ``physics-latest.json`` indent=2, INSERTION order, ensure_ascii, "\\n"
  public receipts         indent=2, SORTED keys, ensure_ascii=False, "\\n"
  hunt receipts           indent=1, INSERTION order, ensure_ascii, no newline

The receipts are sorted ON PURPOSE — that is their spec, and this file pins it
sorted. Only the pot and the feeds are insertion-ordered, and those are the
ones a ``sort_keys`` refactor would wreck.

Two kinds of pin, because either alone has a hole. The golden-byte tests catch
a change to the SERIALIZER even when no artifact has been regenerated yet; the
round-trip tests catch a change that disagrees with the bytes actually on the
books, which is what a reader downloading the feed sees.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab import publish, receipt


REPO = Path(__file__).resolve().parents[1]


# A fixture whose keys are deliberately NOT in alphabetical order and whose
# values carry a non-ASCII character, so key order, indent and the ascii policy
# are all visible in the bytes.
FIXTURE = {
    "schema_version": 5,
    "source": "windowsill-lab",
    "alpha": {"zeta": 1, "beta": 2},
    "note": "— an em dash",
}


# ── pot.json / physics-latest.json: indent=2, insertion order, escaped ───────

POT_GOLDEN = (
    '{\n'
    '  "schema_version": 5,\n'
    '  "source": "windowsill-lab",\n'
    '  "alpha": {\n'
    '    "zeta": 1,\n'
    '    "beta": 2\n'
    '  },\n'
    '  "note": "\\u2014 an em dash"\n'
    '}\n'
)


def test_pot_serialization_layout_is_pinned():
    """The publisher's own line, byte for byte.

    Mirrors ``publish.publish``: ``json.dumps(snap, indent=2) + "\\n"``. If that
    call ever gains ``sort_keys``, loses its indent, or gains
    ``ensure_ascii=False``, this literal stops matching.
    """
    assert json.dumps(FIXTURE, indent=2) + "\n" == POT_GOLDEN


def test_pot_serialization_is_not_key_sorted():
    """The pin has teeth: sorted keys really would produce different bytes."""
    assert json.dumps(FIXTURE, indent=2, sort_keys=True) + "\n" != POT_GOLDEN


def test_publish_writes_the_pinned_pot_layout(tmp_path, monkeypatch):
    """Not the mirror — the real writer, driven end to end onto disk."""
    dest = tmp_path / "pot.json"
    monkeypatch.setattr(publish, "POT_JSON", dest)
    monkeypatch.setattr(publish, "LAB_HOME", tmp_path / "lab")
    # publish() also rewrites the page's shelf counters from the snapshot
    # it writes (refresh_shelf_fallback). Redirect that too, or a fixture
    # snapshot scribbles zeros over the SHIPPED web/index.html mid-suite.
    monkeypatch.setattr(publish, "WEB_INDEX", tmp_path / "index.html")
    monkeypatch.setattr(publish, "ensure_public_receipts", lambda *a, **k: [])
    monkeypatch.setattr(publish, "collect", lambda: FIXTURE)
    publish.publish(quiet=True)
    assert dest.read_text(encoding="utf-8") == POT_GOLDEN


# ── public receipts: indent=2, SORTED, ensure_ascii=False ────────────────────

RECEIPT_GOLDEN = (
    '{\n'
    '  "alpha": {\n'
    '    "beta": 2,\n'
    '    "zeta": 1\n'
    '  },\n'
    '  "note": "— an em dash",\n'
    '  "public_receipt": {\n'
)


def test_receipt_serialization_layout_is_pinned():
    """Receipts are sorted and unescaped — the OPPOSITE of the pot, on purpose.

    Pinned as a prefix plus the properties that make the rest of the file: the
    tail carries ``public_receipt`` metadata this test has no business
    duplicating, but its head shows key order, indent and the ascii policy.
    """
    text = receipt.receipt_text(dict(FIXTURE))
    assert text.startswith(RECEIPT_GOLDEN)
    assert text.endswith("\n")
    assert "\\u2014" not in text          # ensure_ascii=False
    assert json.loads(text)["note"] == "— an em dash"


# ── the artifacts actually on the books ──────────────────────────────────────

def _reserialize(text, **kwargs):
    return json.dumps(json.loads(text), **kwargs)


def test_committed_pot_matches_the_publishers_serialization(tmp_path, monkeypatch):
    """The committed feed, run back through the REAL publisher, byte for byte.

    This is the pin that bites hardest: it puts the actual ``pot.json`` on the
    books through ``publish.publish`` and compares the bytes. It fails the
    moment the publisher's layout and the committed feed disagree — which is
    exactly the state a ``sort_keys`` refactor creates, and which every
    parsed-object sync gate in this repo is blind to.
    """
    text = (REPO / "pot.json").read_text(encoding="utf-8")
    dest = tmp_path / "pot.json"
    monkeypatch.setattr(publish, "POT_JSON", dest)
    monkeypatch.setattr(publish, "LAB_HOME", tmp_path / "lab")
    # publish() also rewrites the page's shelf counters from the snapshot
    # it writes (refresh_shelf_fallback). Redirect that too, or a fixture
    # snapshot scribbles zeros over the SHIPPED web/index.html mid-suite.
    monkeypatch.setattr(publish, "WEB_INDEX", tmp_path / "index.html")
    monkeypatch.setattr(publish, "ensure_public_receipts", lambda *a, **k: [])
    monkeypatch.setattr(publish, "collect", lambda: json.loads(text))
    publish.publish(quiet=True)
    assert dest.read_text(encoding="utf-8") == text


def test_committed_physics_feed_matches_its_serialization():
    text = (REPO / "physics-latest.json").read_text(encoding="utf-8")
    assert _reserialize(text, indent=2) + "\n" == text


def test_committed_receipts_match_the_receipt_serialization():
    receipts = sorted((REPO / "reports" / "receipts").glob("run-*.json"))
    assert receipts, "no committed receipts to pin"
    bad = []
    for path in receipts:
        text = path.read_text(encoding="utf-8")
        expected = _reserialize(text, indent=2, ensure_ascii=False,
                                sort_keys=True) + "\n"
        if expected != text:
            bad.append(path.name)
    assert not bad, f"receipts whose bytes disagree with receipt_text: {bad[:5]}"


def test_committed_hunt_receipts_match_the_hunt_serialization():
    """``scripts/a05_hunt.py`` writes indent=1 and NO trailing newline.

    The two ``schema: 0`` pilot receipts from 2026-08-14 were written by an
    older hand at indent=2 with a trailing newline. They are committed
    evidence, so they are not rewritten to match — they are named here as the
    known exception, which is the whole point of a pin: the set of files that
    do not follow the rule is enumerated rather than discovered later.
    """
    hunts = sorted((REPO / "reports" / "hunts").glob("*.json"))
    assert hunts, "no committed hunt receipts to pin"
    current, pilots, bad = 0, [], []
    for path in hunts:
        text = path.read_text(encoding="utf-8")
        if _reserialize(text, indent=1) == text:
            current += 1
        elif json.loads(text).get("schema") == 0:
            pilots.append(path.name)      # frozen pre-schema pilot evidence
        else:
            bad.append(path.name)
    assert not bad, f"hunt receipts whose bytes disagree with a05_hunt: {bad[:5]}"
    assert current, "no hunt receipt in the current layout — nothing was pinned"
    assert pilots == ["hunt-2026-08-14-s2-pilot-158.json",
                      "hunt-2026-08-14-s2-pilot-570.json"], pilots


@pytest.mark.parametrize("path,kwargs", [
    ("pot.json", {"indent": 2}),
    ("physics-latest.json", {"indent": 2}),
])
def test_committed_feeds_are_not_key_sorted(path, kwargs):
    """The feeds really are insertion-ordered — so the round-trip pins bite."""
    text = (REPO / path).read_text(encoding="utf-8")
    assert _reserialize(text, sort_keys=True, **kwargs) + "\n" != text
