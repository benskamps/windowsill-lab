"""The survey paper's census — and the grep that keeps its prose honest.

``scripts/survey_paper_numbers.py`` is the reader between the committed hunt
receipts and the prose in ``docs/papers/2026-09-18-survey-methods-draft.md``.
Two things can go wrong with a paper whose numbers live in a repo:

* the reader drifts from ``lab.publish.hunt_block``, so two readers of one
  record disagree about what the record says — asserted against here;
* the prose drifts from the reader, so a sentence keeps a number the receipts
  no longer support — the draft's own census table is checked cell by cell.

The third test is the one the publication contract earns: the draft may not
call anything "confirmed", may not call the candidate a planet, and may not
print a count of targets where the record only supports a count of searches.

Stdlib-only, like the other publish-side tests.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "survey_paper_numbers.py"
DRAFT = ROOT / "docs" / "papers" / "2026-09-18-survey-methods-draft.md"

sys.path.insert(0, str(ROOT / "scripts"))
import survey_paper_numbers as spn                      # noqa: E402


def test_reader_agrees_with_the_aggregator():
    """One record, two readers, no disagreement — or the test names it."""
    numbers = spn.census()
    assert spn._agrees_with_aggregator(numbers) == []


def test_script_runs_clean():
    proc = subprocess.run([sys.executable, str(SCRIPT)],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Agrees with lab.publish.hunt_block" in proc.stdout


def test_draft_census_matches_the_receipts():
    """Every number in the draft's census table, checked against the record.

    The table is the paper's denominator. If a receipt is added, refused or
    re-dispositioned, this test fails on the specific cell rather than letting
    the paper quietly describe a survey that no longer exists.
    """
    text = DRAFT.read_text(encoding="utf-8")
    n = spn.census()
    expected = {
        "target-searches": f"{n['sample']['target_searches']:,}",
        "distinct identities": f"{n['sample']['distinct_identities_in_rows']:,}",
        "above threshold": str(n["detections"]["above_threshold_stars"]),
        "known planets recovered": str(n["outcomes"]["known_planets_recovered"]),
        "leads minted": str(n["outcomes"]["leads_minted"]),
        "leads refuted": str(len(n["outcomes"]["leads_refuted_and_counted"])),
        "receipts refused": str(len(n["receipts"]["refused"])),
        "placebo scrambles": f"{n['controls']['placebo_scrambles']:,}",
        "injections run": f"{n['controls']['injections_run']:,}",
    }
    rows = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2:
            rows[cells[0].strip("* ").lower()] = cells[1].strip("* ")
    for label, value in expected.items():
        assert label in rows, f"census row {label!r} missing from the draft"
        assert rows[label] == value, (
            f"{label}: draft says {rows[label]!r}, receipts say {value!r}")


def test_draft_claims_no_planet_and_nothing_confirmed():
    """The reserved words, enforced by grep rather than by good intentions.

    ``planets claimed: 0`` is the survey's pin; a draft that describes the
    candidate as a planet, or any survey output as confirmed or verified, has
    walked past it. Occurrences that name the rule, quote a catalogue's own
    vocabulary, or attach the word to a *known* planet are the allowed forms,
    so the test looks at sentences rather than at bare substrings.
    """
    banned = re.compile(
        r"\b(we (confirm|report the discovery)|"
        r"(a|the|our) (new|first) planet\b|"
        r"planet is confirmed|confirmed planet candidate)\b", re.I)
    text = DRAFT.read_text(encoding="utf-8")
    offenders = [line for line in text.splitlines() if banned.search(line)]
    assert not offenders, offenders


def test_draft_never_calls_the_searches_targets():
    """12,898 is a count of searches. A sentence that attaches it to the word
    'targets' or 'stars' is the overstatement this reader exists to catch.

    A quoted occurrence is the one allowed form: the draft's own retraction
    table prints the withdrawn wording verbatim, and a paper that may not
    quote the claim it is withdrawing cannot record a retraction.
    """
    text = DRAFT.read_text(encoding="utf-8")
    searches = f"{spn.census()['sample']['target_searches']:,}"
    bad = re.compile(r'(?<!")' + re.escape(searches) + r"\s+(targets|stars)\b", re.I)
    offenders = [line for line in text.splitlines() if bad.search(line)]
    assert not offenders, offenders


DVR = ROOT / "docs" / "submissions" / "TIC374861595-spoc-s1-s96-dvr.xml"


def _dv_sectors_observed():
    """(count, lowest, highest) from the DV product's own bitmap, one-indexed.

    Read one-indexed here because that is the stricter of the two readings the
    draft names: it puts the earliest sector one number LATER, so a test that
    passes under it also passes under the zero-indexed reading the draft
    prefers. The draft states only what both readings agree on.
    """
    text = DVR.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'sectorsObserved="([01]+)"', text)
    assert m, "the committed DV XML has no sectorsObserved bitmap"
    on = [i + 1 for i, c in enumerate(m.group(1)) if c == "1"]
    return len(on), min(on), max(on)


def test_draft_does_not_claim_2018_coverage():
    """§6.2 said "every 2-minute sector since 2018" and "seven years" until
    2026-09-19. The DV product's own bitmap marks no sector early enough for
    either to be true, and this is the grep that keeps them retracted.

    A quoted occurrence is allowed: Appendix B prints the withdrawn wording.
    """
    count, lowest, highest = _dv_sectors_observed()
    assert lowest > 20, (
        f"the DV bitmap's earliest sector is {lowest}; if that ever drops into "
        "TESS's first year the draft's 2020-onward statement needs rewriting")
    text = DRAFT.read_text(encoding="utf-8")
    banned = re.compile(r"(since 2018|in seven years|for seven years)", re.I)
    quoted = re.compile(r'"[^"]*"')
    offenders = [line for line in text.splitlines()
                 if banned.search(quoted.sub("", line))]
    assert not offenders, offenders


def test_draft_sector_count_matches_the_dv_bitmap():
    """The draft says 23 sectors. That number comes from the bitmap, and both
    of the draft's two candidate readings agree on it, so it is the one sector
    figure the paper is entitled to state without the light-curve files."""
    count, _, _ = _dv_sectors_observed()
    text = DRAFT.read_text(encoding="utf-8")
    assert f"{count} sectors" in text, (
        f"the DV bitmap marks {count} sectors; the draft does not say so")
