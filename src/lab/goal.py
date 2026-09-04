"""The lab's declared goal — dated, observable, computed, and published.

A goal that lives in a plan document is a preference. This one has three
properties that make it a commitment instead:

1. **It is published.** It rides in `pot.json`, the feed the public windowsill
   page reads straight from GitHub raw. Nobody has to be told the lab missed;
   they can see it.
2. **Its progress is computed, never written.** Every number below is derived
   from `UNKNOWNS.md` and the receipt ledger at publish time. A goal whose
   progress is hand-edited measures the editor's mood.

   That claim was false where it mattered most for the goal's first ten days.
   The attempt condition read `"ATTEMPTED" in u.reach_evidence` — a
   case-sensitive, unanchored substring search against one physical line of a
   markdown file the grading agent edits — sitting directly under this
   paragraph. It was repaired on 2026-09-03: the attempt half is now joined out
   of the committed receipts by `archive.attempt_ledger`. The lever it removed
   was not a forgery anyone had to intend. Rewording U-A01's own correction
   from "verdict REANALYSED — NOT an attempt" to "— NOT ATTEMPTED" flipped this
   goal from OPEN to MET, which means the grader paid the lab for saying the
   thing more clearly. A number that moves when you improve a sentence is not
   computed; it is transcribed.
3. **It can fail.** After the deadline an unmet goal reads MISSED and stays
   that way. A deadline that slides is a wish with a calendar next to it.

## Why this goal

2026-08-24 was the day the lab stopped only climbing rungs and started charting
unknowns. The catalogue came out **4 field-unknowns of 7** — 57%, and probably
50% once U-C01 retires, since its entry is flagged as likely already answered by
the literature in 2004.

But charting is not crossing. Every unknown so far has been *priced*: U-K01
measured out-of-reach, U-K02 measured in-reach at 3.1 GPU-hours, U-A01 priced
its own false alarms, U-I01 has no instrument, U-P01 has a measured ceiling.
Pricing is the cheap half. The charter is explicit about which half counts:

> **The SETI gate** is the hinge of the whole lab: the moment work stops
> *reproducing* an answer we already know and starts *searching* for one we
> don't.

So the goal is the thing pricing is for — **an attempt, with a result either
way**, and every track honest about where it stands.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import unknowns as U

#: Deadline. Chosen as roughly a month, which is long enough for the deep lane
#: to run twenty-odd nights and short enough that missing it is embarrassing
#: rather than forgettable.
DEADLINE = date(2026, 9, 24)

#: Tracks that can never carry an unknown. Track B donates cycles to somebody
#: else's pipeline; there is nothing here it could fail to know.
EXEMPT_TRACKS = ("B",)


@dataclass(frozen=True)
class Goal:
    id: str
    statement: str
    arrived_when: str
    deadline: date
    why_now: str
    set_on: date


GOAL = Goal(
    id="G01",
    set_on=date(2026, 8, 24),
    deadline=DEADLINE,
    statement=("Stop pricing the frontier and cross it: attempt one field-unknown "
               "and report the result either way, with every track honest about "
               "where it stands."),
    arrived_when=(
        "Three things a stranger can check in pot.json: (a) every track that can "
        "carry an unknown has one, charted, with a measured reach verdict; (b) at "
        "least one `field` unknown has been ATTEMPTED — a run against the question "
        "itself, not another feasibility test; (c) that attempt has a published "
        "receipt whose verdict is supported, killed or unresolved. A verdict of "
        "`killed` or `unresolved` satisfies this goal exactly as well as "
        "`supported` — the commitment is to attempt and report, not to succeed."),
    why_now=(
        "Every unknown in the catalogue has been priced and none attempted. "
        "Pricing is the half this box is good at and the half that cannot "
        "produce a result."),
)


def _attempt_ledger(field) -> dict:
    """The receipt ledger, or an empty one carrying the reason it is empty.

    ``archive.attempt_ledger`` already promises never to raise; this guards the
    IMPORT as well, because the failure this whole module is built around is
    ``publish.py``'s bare ``except Exception: pass`` around ``progress()``,
    which deletes the ``goal`` key from ``pot.json`` and blanks the lab's public
    commitment from a pass that exits 0. An unmet goal published with its reason
    beats a met goal, and both beat no goal at all.
    """
    try:
        from . import archive
        return archive.attempt_ledger(field)
    except Exception as e:  # noqa: BLE001 — fail CLOSED, and say so out loud
        # ``strerror``, not ``str(e)``, for the same reason as
        # ``archive._why``: this string is PUBLISHED into ``pot.json``, and an
        # OSError renders the absolute filename it touched. The archive's own
        # helper cannot be reached from here — the failure being caught may be
        # the import of the module that holds it.
        return {"attempts": [], "undecidable": [], "refused": [],
                "unreadable": [],
                "error": f"{type(e).__name__}: "
                         f"{getattr(e, 'strerror', None) or e}"}


def progress(unknowns=None, today: date | None = None,
             ledger: dict | None = None) -> dict:
    """Where the goal stands, derived — never asserted.

    ``attempted`` deliberately does not count feasibility tests. A lab that
    scores its own reach measurements as attempts on the question can hit this
    goal without ever asking one.

    It also, since 2026-09-03, does not count PROSE. The condition used to read
    ``"ATTEMPTED" in u.reach_evidence`` — a substring search against a markdown
    line the grading agent writes — so this module's own docstring claim that
    progress is "computed, never written" was false at the one place it mattered
    most. The attempt half is now joined out of ``reports/receipts/`` by
    ``archive.attempt_ledger``, which re-derives each receipt through
    ``checks.check_hypothesis`` rather than believing it. Nothing anybody can
    type into ``UNKNOWNS.md`` moves this number in either direction.

    ``ledger`` is for tests and for a caller that has already paid for the scan;
    left None it is derived. A ledger that could not be read yields no attempts,
    which is the fail-closed direction: a goal this box cannot verify is not met.
    """
    cat = U.load() if unknowns is None else unknowns
    today = today or date.today()
    live = [u for u in cat if u.status != U.RETIRED]
    tracks = {u.track for u in live}
    charted_tracks = {u.track for u in live
                      if u.status == U.CHARTED and u.reach != U.UNTESTED}
    missing = sorted(tracks - charted_tracks)

    field = [u for u in live if u.crosses_the_gate]
    # An attempt is a run against the QUESTION, and the only thing that can say
    # one happened is a receipt. Reach verdicts are not attempts, so nothing
    # here can be satisfied by more pricing; and no field of the catalogue is
    # consulted at all beyond WHICH unknowns cross the gate, so nothing here can
    # be satisfied by better wording either.
    if ledger is None:
        ledger = _attempt_ledger(field)
    field_ids = {u.id for u in field}
    attempts = [a for a in ledger.get("attempts") or ()
                if a.get("unknown_id") in field_ids]
    attempted = sorted({str(a["unknown_id"]) for a in attempts})
    attempt_receipts = sorted({str(a.get("receipt", "")) for a in attempts})

    conditions = {
        "every_track_charted": not missing,
        "a_field_unknown_attempted": bool(attempted),
    }
    met = all(conditions.values())
    days = (GOAL.deadline - today).days
    if met:
        state = "MET"
    elif days < 0:
        state = "MISSED"
    else:
        state = "OPEN"
    return {
        "id": GOAL.id,
        "statement": GOAL.statement,
        "arrived_when": GOAL.arrived_when,
        "why_now": GOAL.why_now,
        "set_on": GOAL.set_on.isoformat(),
        "deadline": GOAL.deadline.isoformat(),
        "days_remaining": days,
        "state": state,
        "conditions": conditions,
        "tracks_without_a_charted_unknown": missing,
        "unknowns_total": len(live),
        "unknowns_charted": len([u for u in live if u.status == U.CHARTED]),
        "field_unknowns": len(field),
        "gate_ratio": U.gate_ratio(live)["ratio"],
        "attempted": attempted,
        # The receipts the flag above stands on, named so a stranger can open
        # them. A boolean nobody can check is the thing this goal replaced.
        "attempt_receipts": attempt_receipts,
        # And what the grader could NOT read. A gap is published rather than
        # rounded to zero: a ledger with a refused receipt in it is a different
        # public fact from a ledger with none, and both read OPEN.
        "attempt_ledger_gaps": {
            "undecidable": list(ledger.get("undecidable") or ()),
            "refused": list(ledger.get("refused") or ()),
            "unreadable": list(ledger.get("unreadable") or ()),
            "error": str(ledger.get("error") or ""),
        },
        "next_reach_test": (lambda n: n.id if n else None)(U.next_to_test(live)),
        "honesty_note": (
            "A `killed` or `unresolved` verdict meets this goal. The commitment "
            "is to attempt and report, not to succeed — a goal that only counts "
            "successes buys itself pressure to find them."),
    }
