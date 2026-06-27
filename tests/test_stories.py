"""The story layer — plain-language copy beside the curriculum.

Guards the contract that publish.parse_milestones merges src/lab/stories.py onto
each milestone, that every milestone in the curriculum has a story (so a new
milestone can't ship without one), that result_plain rides only on verified
milestones, and that jargon stays out of the plain-language fields.
"""
from pathlib import Path

from lab.publish import parse_milestones
from lab.stories import STORIES

MILESTONES_MD = Path(__file__).resolve().parents[1] / "MILESTONES.md"
TEXT_FIELDS = ("short_label", "question_plain", "why_it_matters")

# Technical terms that belong in the `result` field, never in the plain story.
# Chosen to be free of common-word substrings (e.g. "chi" would match "machine").
JARGON = (
    "susceptibility", "helicity", "binder", "cumulant", "onsager", "magnetization",
    "order parameter", "exponent", "metropolis", "wolff", "lattice",
    "hamiltonian", "renormaliz", "nishimori", "kosterlitz",
)


def _milestones():
    return parse_milestones(MILESTONES_MD.read_text(encoding="utf-8"))


def test_every_milestone_has_a_story():
    """A milestone without plain-language copy can't ship — catch it here."""
    missing = [m["id"] for m in _milestones() if m["id"] not in STORIES]
    assert not missing, f"milestones missing a story entry: {missing}"


def test_story_text_fields_present_and_nonempty():
    for mid, story in STORIES.items():
        for field in TEXT_FIELDS:
            val = story.get(field)
            assert val and val.strip(), f"{mid}.{field} is empty"


def test_parse_merges_story_fields():
    by = {m["id"]: m for m in _milestones()}
    m01 = by["M01"]
    assert m01["short_label"] == "Flat grid of magnets"
    assert m01["question_plain"].endswith("?")
    assert "result_plain" in m01 and m01["result_plain"]
    # The technical result is preserved, never overwritten by the story layer.
    assert "Onsager" in m01["result"]


def test_result_plain_only_on_verified():
    for m in _milestones():
        if m["status"] != "verified":
            assert "result_plain" not in m, (
                f"{m['id']} is {m['status']} but carries result_plain"
            )


def test_verified_milestones_have_result_plain():
    """Every verified milestone tells its outcome in plain language."""
    for m in _milestones():
        if m["status"] == "verified":
            assert m.get("result_plain"), f"{m['id']} verified but no result_plain"


def test_open_milestone_has_question_but_no_result():
    by = {m["id"]: m for m in _milestones()}
    opens = [m for m in by.values() if m["status"] == "open"]
    assert opens, "expected an open milestone (the growing tip)"
    for m in opens:
        assert m.get("question_plain"), f"{m['id']} open but no plain question"
        assert "result_plain" not in m


def test_no_jargon_in_plain_fields():
    """Plain copy is for total non-experts — technical terms stay in `result`."""
    offenders = []
    for mid, story in STORIES.items():
        for field in ("short_label", "question_plain", "why_it_matters", "result_plain"):
            val = (story.get(field) or "").lower()
            for term in JARGON:
                if term in val:
                    offenders.append(f"{mid}.{field}: '{term}'")
    assert not offenders, f"jargon leaked into plain copy: {offenders}"
