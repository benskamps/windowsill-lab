"""The frontier board — what this lab is FOR, what to do next, and what it has
already admitted it cannot yet answer.

The lab is very good at answering and has never once asked. Every rung on the
ladder was typed by a human months ago; the scheduler picks which existing rung
to work on and cannot invent a new one. So the frontier is frozen at whatever we
last imagined, and the estate's own audit named the same shape one level up:
*the care went into the measuring, it stopped at the telling.*

Three readings, none of which run anything:

**DESTINATION** — every track declares what arriving would look like, in
``TRACKS.md``. A ladder without a summit is a to-do list.

**STEWARD** — the standing review a thirty-year PM would give: per track, what
is done, what is open, what is blocked and on what, and the one thing worth
doing next with the reason attached. It reads committed state only.

**PROVOCATEUR** — the hypothesis surface, and the honest version of one. A
generator that invents questions is precisely the machine that invents plausible
nonsense, and this lab has priced that twice: a filter that reported chirp masses
which were pure noise, and a front door that fabricated Knox County on 44 % of
turns. So this one invents nothing. It HARVESTS: the milestones have been
writing down their own unanswered questions for months — *deferred to a large-L
hero run*, *needs the waveform physics, not more compute*, *stays a documented
open edge* — and nobody has ever collected them into one place.

    A question the lab has already admitted it cannot answer is not a guess.
    It is evidence, with a citation, that was sitting in plain sight.

Promotion to a real rung is deliberately hard: a harvested question is a
CANDIDATE, and it becomes a milestone only when a human gives it the six fields
in ``HYPOTHESIS_SCHEMA`` — including the kill condition and the honest "why this
might be nothing". That is the same discipline the transit shelf uses on leads,
applied to ideas.
"""
from __future__ import annotations

import re
from pathlib import Path

from .publish import MILESTONES_MD, REPO_ROOT, parse_milestones

#: A sentence ends at .!? followed by whitespace — never mid-number.
_SENTENCE_END = re.compile(r"[.!?](?=\s)")

TRACKS_MD = REPO_ROOT / "TRACKS.md"

#: Phrases the milestones use when confessing a limit. Harvested rather than
#: guessed: each one was read off the ladder's existing prose, so the list
#: describes how this lab actually writes, not how a generic one might.
#: HIGH PRECISION ONLY. The first cut included "cannot", "could not" and
#: "needs the", and they poisoned the harvest: M17's "prose and data cannot
#: drift apart" is a STRENGTH, and it surfaced as a confession. A generator that
#: is half noise teaches its reader to skip it, which is worse than no generator
#: — so a marker earns its place only if it is almost always a real admission.
CONFESSIONS: tuple[tuple[str, str], ...] = (
    ("deferred", "deferred to later work"),
    ("open edge", "explicitly left as an open edge"),
    ("still open", "stated as still open"),
    ("remains open", "stated as remaining open"),
    ("stays a documented open", "held open on purpose"),
    ("unresolved", "left unresolved"),
    ("out of reach", "out of reach at this scale"),
    ("hero run", "waiting on a larger run"),
    ("not claimed", "measured but deliberately not claimed"),
    ("needs its own", "needs an experiment of its own"),
)

#: What a harvested candidate must acquire before it can become a rung. The
#: kill condition and the disclaimer are the load-bearing two: an idea that
#: cannot say what would refute it is not a hypothesis, and one whose proposer
#: will not say how it might be nothing has not been thought about.
HYPOTHESIS_SCHEMA: tuple[str, ...] = (
    "question",            # one sentence, answerable
    "why_unanswered",      # a disagreement, an untested assumption, or a gap
    "observable",          # the number that would settle it
    "kill_condition",      # the result that makes us drop this
    "cheapest_decisive",   # the smallest experiment that could settle it
    "why_this_might_be_nothing",
)


def parse_tracks(text: str) -> dict:
    """``TRACKS.md`` → ``{track_letter: {name, goal, arrived_when}}``.

    Mirrors ``parse_milestones``: markdown is the writing format, the parser is
    the navigation layer, and the file stays readable by a human first.
    """
    tracks: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        head = re.match(r"^##\s+Track\s+([A-Z])\s+—\s+(.+?)\s*$", line)
        if head:
            current = head.group(1)
            tracks[current] = {"letter": current, "name": head.group(2).strip(),
                               "goal": "", "arrived_when": ""}
            continue
        if current is None:
            continue
        for key, field in (("**Goal.**", "goal"), ("**Arrived when.**", "arrived_when")):
            if line.strip().startswith(key):
                tracks[current][field] = line.strip()[len(key):].strip()
    return tracks


def _track_of(milestone: dict) -> str:
    return str(milestone.get("id", "?"))[:1].upper()


def steward(milestones: list[dict], tracks: dict) -> list[dict]:
    """Per-track standing review, read-only: state, frontier, and blockers."""
    board = []
    by_track: dict[str, list] = {}
    for m in milestones:
        by_track.setdefault(_track_of(m), []).append(m)

    for letter in sorted(by_track):
        rungs = by_track[letter]
        counts: dict[str, int] = {}
        for m in rungs:
            counts[m["status"]] = counts.get(m["status"], 0) + 1
        open_rung = next((m for m in rungs if m["status"] == "open"), None)
        review = [m for m in rungs if m["status"] == "review"]
        nulls = [m for m in rungs if m["status"] == "null"]
        # A pending rung with no runner cannot be dispatched at all — the
        # scheduler will walk past it forever, which is a blocker wearing the
        # costume of a plan.
        unrunnable = [m for m in rungs
                      if m["status"] == "pending" and not m.get("runner_available")]
        chart = tracks.get(letter, {})
        board.append({
            "track": letter,
            "name": chart.get("name") or (rungs[0].get("track") or "?"),
            "goal": chart.get("goal", ""),
            "arrived_when": chart.get("arrived_when", ""),
            "counts": counts,
            "total": len(rungs),
            "open": open_rung["id"] if open_rung else None,
            "awaiting_review": [m["id"] for m in review],
            "nulls": [m["id"] for m in nulls],
            "no_runner": [m["id"] for m in unrunnable],
            "charter_missing": not chart.get("goal"),
        })
    return board


def harvest(milestones: list[dict]) -> list[dict]:
    """Every question the ladder has already admitted it cannot yet answer.

    Returns candidates, never hypotheses: each carries the milestone that said
    it and the sentence it said it in, so the reader can judge the source rather
    than the summary. Nothing here is generated — if the lab never wrote it
    down, it does not appear.
    """
    found = []
    for m in milestones:
        prose = str(m.get("result") or "")
        if not prose:
            continue
        lower = prose.lower()
        for marker, meaning in CONFESSIONS:
            idx = lower.find(marker)
            if idx < 0:
                continue
            # Quote the sentence, not the fragment: a confession out of context
            # reads as a defect when it is usually a boundary held on purpose.
            # Split on sentence ends, not on every period: this prose is full
            # of "L=6,8,10,12" and "0.80", and the naive splitter returned
            # fragments like "on one 0" that read as gibberish.
            starts = [m.end() for m in _SENTENCE_END.finditer(prose, 0, idx)]
            start = starts[-1] if starts else 0
            tail = _SENTENCE_END.search(prose, idx)
            end = tail.start() + 1 if tail else len(prose)
            sentence = prose[start:end].strip()
            if len(sentence) < 20:
                continue
            found.append({
                "milestone": m["id"],
                "status": m["status"],
                "track": _track_of(m),
                "marker": marker,
                "meaning": meaning,
                "sentence": sentence[:400],
                "needs": list(HYPOTHESIS_SCHEMA),
            })
            break        # one confession per milestone; the loudest wins
    return found


def board(milestones=None, tracks_text=None) -> dict:
    """The whole reading: destinations, steward review, harvested candidates."""
    milestones = milestones if milestones is not None else parse_milestones(
        MILESTONES_MD.read_text(encoding="utf-8"))
    if tracks_text is None:
        tracks_text = TRACKS_MD.read_text(encoding="utf-8") if TRACKS_MD.exists() else ""
    tracks = parse_tracks(tracks_text)
    review = steward(milestones, tracks)
    candidates = harvest(milestones)
    return {
        "tracks": review,
        "candidates": candidates,
        "totals": {
            "tracks": len(review),
            "tracks_without_a_goal": sum(1 for t in review if t["charter_missing"]),
            "milestones": len(milestones),
            "awaiting_review": sum(len(t["awaiting_review"]) for t in review),
            "unrunnable": sum(len(t["no_runner"]) for t in review),
            "candidates": len(candidates),
        },
        "schema": list(HYPOTHESIS_SCHEMA),
    }
