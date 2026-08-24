"""The catalogue of unknowns — what this lab does not know, and whether it can reach it.

`MILESTONES.md` is the ladder: what was measured. `TRACKS.md` is the summit:
what each track is for. This is the third thing, and until 2026-08-24 it did
not exist: **the map of what is not known at all.**

Its absence was the lab's largest structural gap. Read the track goals against
the charter's SETI gate — the hinge where work stops reproducing an answer we
already know and starts searching for one we don't — and five of seven tracks
sit on the calibrate side by their own stated verbs: *reproduce*, *verify*,
*characterise*, *prove*. That is not a flaw; the charter says it is how you earn
the right to be believed. But nothing in the estate said when the crossing
happens, or even which side a given question sits on. A lab that only ever
answers questions it already knows the answers to becomes, at scale, the most
trustworthy instrument in the world that has never been pointed at anything.

## The distinction this file exists to force

An unknown must declare **`known_to_whom`**, and the honest answer is usually
the uncomfortable one:

* ``field`` — nobody knows. A genuine open question. Rare, and the burden of
  proof for claiming one is high.
* ``us`` — the field knows; this lab has not measured it. Most "unknowns" are
  this, and calling them frontier work is the single easiest way to fool
  yourself.
* ``reach`` — whether THIS instrument can touch it is what is unknown.

Conflating those three is how a calibration bench convinces itself it is doing
discovery. The catalogue refuses to let the three share a word.

## The cheap kill test on ourselves

Every unknown carries a **`feasibility_test`**: the cheapest thing that decides
whether this box can reach the question at all, run *before* any attempt on the
question itself. A failed feasibility test is a **result** — "out of reach, and
here is the measured reason" — not a disappointment, and it is recorded with
the number that says so. That is what keeps a catalogue of unknowns from
becoming a catalogue of wishes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Who does not know this. See the module docstring — the whole discipline of
#: the catalogue lives in keeping these three apart.
FIELD = "field"
US = "us"
REACH = "reach"
KNOWN_TO = (FIELD, US, REACH)

#: Can this instrument touch the question? Answered by the feasibility test,
#: never by argument.
UNTESTED = "untested"
IN_REACH = "in-reach"
OUT_OF_REACH = "out-of-reach"
REACH_VERDICTS = (UNTESTED, IN_REACH, OUT_OF_REACH)

#: Has anyone confirmed the unknown is actually unknown? A claim that the field
#: does not know something is itself a claim, and it gets the same treatment as
#: any other: it is a proposal until somebody checks the literature and says so.
CLAIMED = "claimed-open"
CHARTED = "charted"
RETIRED = "retired"        # someone answered it, or it was never open
LIFECYCLE = (CLAIMED, CHARTED, RETIRED)

REQUIRED = ("question", "why_open", "known_to_whom", "who_would_care",
            "feasibility_test", "if_out_of_reach")


@dataclass(frozen=True)
class Unknown:
    """A question nobody here can answer yet, and the cheap test for whether we could.

    The fields are not paperwork. ``known_to_whom`` stops a calibration gap from
    being dressed as a frontier; ``feasibility_test`` stops a frontier from
    being attempted with an instrument that cannot see it; ``if_out_of_reach``
    forces the proposer to say what would have to change, so an out-of-reach
    verdict leaves a next step instead of a shrug.
    """

    id: str
    track: str
    question: str
    why_open: str
    known_to_whom: str
    who_would_care: str
    feasibility_test: str
    if_out_of_reach: str
    importance: int = 3               # 1 (idle curiosity) … 5 (why the track exists)
    status: str = CLAIMED
    reach: str = UNTESTED
    reach_evidence: str = ""

    def __post_init__(self) -> None:
        missing = [f for f in REQUIRED if not str(getattr(self, f, "")).strip()]
        if missing:
            raise ValueError(
                f"{self.id or 'unknown'} is missing {', '.join(missing)} — an "
                "unknown with no feasibility test is a wish, and one that will "
                "not say who does not know it is usually a gap in us wearing a "
                "frontier's coat")
        if self.known_to_whom not in KNOWN_TO:
            raise ValueError(f"{self.id}: known_to_whom must be one of {KNOWN_TO}")
        if self.reach not in REACH_VERDICTS:
            raise ValueError(f"{self.id}: reach must be one of {REACH_VERDICTS}")
        if self.status not in LIFECYCLE:
            raise ValueError(f"{self.id}: status must be one of {LIFECYCLE}")
        if not 1 <= int(self.importance) <= 5:
            raise ValueError(f"{self.id}: importance must be 1-5")

    @property
    def crosses_the_gate(self) -> bool:
        """Is answering this discovery, or is it calibration wearing a costume?

        Only a `field` unknown crosses the charter's SETI gate. A `us` unknown
        is calibration — worth doing, frequently the right thing to do, and not
        the same thing. A `reach` unknown is the question of whether we are
        allowed to try.
        """
        return self.known_to_whom == FIELD

    def to_json(self) -> dict:
        return {
            "id": self.id, "track": self.track, "question": self.question,
            "why_open": self.why_open, "known_to_whom": self.known_to_whom,
            "who_would_care": self.who_would_care,
            "feasibility_test": self.feasibility_test,
            "if_out_of_reach": self.if_out_of_reach,
            "importance": self.importance, "status": self.status,
            "reach": self.reach, "reach_evidence": self.reach_evidence,
            "crosses_the_gate": self.crosses_the_gate,
        }


# ── the heartbeat's choice ───────────────────────────────────────────────────

def next_to_test(unknowns) -> Unknown | None:
    """The most important unknown whose reach has never been tested.

    Deliberately NOT "the most important unknown". Attempting a question before
    knowing whether the instrument can see it is how a lab spends four
    GPU-hours to learn nothing — the feasibility test is always cheaper than
    the attempt, so it always goes first. Retired unknowns are skipped; an
    out-of-reach one is skipped too, because re-testing reach without changing
    the instrument just re-measures the same wall.
    """
    live = [u for u in unknowns if u.status != RETIRED and u.reach == UNTESTED]
    if not live:
        return None
    return sorted(live, key=lambda u: (-int(u.importance), u.id))[0]


def gate_ratio(unknowns) -> dict:
    """What fraction of the catalogue is actually on the far side of the gate?

    One number, hard to game by working harder, and the honest answer to "is
    this lab still only calibrating?".
    """
    live = [u for u in unknowns if u.status != RETIRED]
    crossing = [u for u in live if u.crosses_the_gate]
    return {
        "total": len(live),
        "field": len(crossing),
        "us": len([u for u in live if u.known_to_whom == US]),
        "reach": len([u for u in live if u.known_to_whom == REACH]),
        "ratio": (len(crossing) / len(live)) if live else 0.0,
        "charted": len([u for u in live if u.status == CHARTED]),
        "in_reach": len([u for u in live if u.reach == IN_REACH]),
        "out_of_reach": len([u for u in live if u.reach == OUT_OF_REACH]),
        "untested": len([u for u in live if u.reach == UNTESTED]),
    }


# ── the catalogue on disk ────────────────────────────────────────────────────

UNKNOWNS_MD = Path(__file__).resolve().parents[2] / "UNKNOWNS.md"

_FIELD_LINE = re.compile(r"^\*\*(?P<key>[a-z_ ]+)\.?\*\*\s*(?P<value>.+)$", re.I)
_HEADING = re.compile(r"^##\s+(?P<id>U-[A-Z]\d+)\s+·\s+track\s+(?P<track>[A-Z])\s*$")

_KEYS = {
    "question": "question", "why open": "why_open", "why_open": "why_open",
    "known to": "known_to_whom", "known_to_whom": "known_to_whom",
    "who would care": "who_would_care", "who_would_care": "who_would_care",
    "feasibility test": "feasibility_test", "feasibility_test": "feasibility_test",
    "if out of reach": "if_out_of_reach", "if_out_of_reach": "if_out_of_reach",
    "importance": "importance", "status": "status", "reach": "reach",
    "reach evidence": "reach_evidence", "reach_evidence": "reach_evidence",
}


def parse_unknowns(text: str) -> list[Unknown]:
    """Read the catalogue. Malformed entries raise rather than being skipped —
    an unknown silently dropped from the map is worse than no map."""
    out: list[Unknown] = []
    cur: dict | None = None

    def flush():
        if cur is None:
            return
        kw = dict(cur)
        kw["importance"] = int(str(kw.get("importance", 3)).split()[0])
        out.append(Unknown(**kw))

    for raw in text.splitlines():
        line = raw.strip()
        h = _HEADING.match(line)
        if h:
            flush()
            cur = {"id": h.group("id"), "track": h.group("track")}
            continue
        if cur is None:
            continue
        m = _FIELD_LINE.match(line)
        if m:
            key = _KEYS.get(m.group("key").strip().lower().rstrip("."))
            if key:
                cur[key] = m.group("value").strip()
    flush()
    return out


def load(path: Path | None = None) -> list[Unknown]:
    p = path or UNKNOWNS_MD
    return parse_unknowns(p.read_text(encoding="utf-8")) if p.exists() else []
