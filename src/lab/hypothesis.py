"""A hypothesis that cannot say what would refute it is not a hypothesis.

The ladder's rungs were written as *tasks*: a thing to build, which then got a
result attached. That ordering produced three failures in a single day —

* M14 had a runner with no test on its order parameter. It was code that RAN,
  not a question that could be ANSWERED, and it nearly produced a p_c nobody
  could defend after four GPU-hours.
* A05's uniformity control ran for ten days while being structurally incapable
  of failing: graded per slice on n=14-22, where the critical value exceeds
  anything the statistic can reach.
* C05's runner has existed for weeks and has never once been executed.

None of those are possible when the runner IS the hypothesis, because a
hypothesis is not constructible here without the field that says how it dies.

The six fields are a build spec, not paperwork. ``kill_condition`` and
``why_this_might_be_nothing`` are the load-bearing pair: the first makes the
experiment decidable, and the second is the proposer stating, before any data
exists, the most likely boring outcome. A proposal that cannot manage both has
not been thought about yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: A run always ends in one of these. `KILLED` is a first-class success: the
#: hypothesis died on its own predeclared terms and the lab learned something
#: cheaply. `UNRESOLVED` is the honest third door — the experiment ran and the
#: evidence does not decide — and it must never be reported as either of the
#: other two.
SUPPORTED = "supported"
KILLED = "killed"
UNRESOLVED = "unresolved"
VERDICTS = (SUPPORTED, KILLED, UNRESOLVED)

#: Which side of the charter's SETI gate this runner sits on — the hinge where
#: work stops reproducing an answer we already know and starts searching for one
#: we don't. Every runner must declare it, because the alternative is what this
#: lab did for months: five of seven tracks on the calibrate side by their own
#: stated verbs, nobody counting, and no way to answer "is this lab still only
#: calibrating?" with a number instead of a feeling.
#:
#: `DISCOVER` is not self-declarable. A runner claiming it must name the
#: catalogued unknown it attacks, so the claim is checkable against `UNKNOWNS.md`
#: rather than asserted in its own docstring.
CALIBRATE = "calibrate"
DISCOVER = "discover"
STAGES = (CALIBRATE, DISCOVER)


@dataclass(frozen=True)
class Hypothesis:
    """A question with a way to die attached."""

    id: str
    question: str
    why_unanswered: str
    observable: str
    kill_condition: str
    cheapest_decisive: str
    why_this_might_be_nothing: str
    stage: str
    track: str = "?"
    unknown_id: str = ""

    def __post_init__(self) -> None:
        missing = [f for f in ("id", "question", "why_unanswered", "observable",
                               "kill_condition", "cheapest_decisive",
                               "why_this_might_be_nothing")
                   if not str(getattr(self, f, "")).strip()]
        if missing:
            raise ValueError(
                f"{self.id or 'hypothesis'} is missing {', '.join(missing)} — "
                "a question that cannot say what would refute it is not a "
                "hypothesis, and one whose proposer will not say how it might "
                "be nothing has not been thought about")
        if self.stage not in STAGES:
            raise ValueError(f"{self.id}: stage must be one of {STAGES}")
        if self.stage == DISCOVER and not self.unknown_id.strip():
            raise ValueError(
                f"{self.id} claims to cross the SETI gate but names no "
                "catalogued unknown. Discovery is not self-declarable — cite "
                "an id from UNKNOWNS.md so the claim can be checked rather "
                "than believed")

    def to_json(self) -> dict:
        return {
            "id": self.id, "track": self.track, "question": self.question,
            "why_unanswered": self.why_unanswered, "observable": self.observable,
            "kill_condition": self.kill_condition,
            "cheapest_decisive": self.cheapest_decisive,
            "why_this_might_be_nothing": self.why_this_might_be_nothing,
            "stage": self.stage,
            "unknown_id": self.unknown_id,
            "crosses_the_gate": self.stage == DISCOVER,
        }


@dataclass
class Finding:
    """What the run returned, and which of the three doors it went through."""

    hypothesis: Hypothesis
    verdict: str
    detail: str
    evidence: dict = field(default_factory=dict)
    controls: dict = field(default_factory=dict)
    wall_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"{self.verdict!r} is not one of {VERDICTS}")

    @property
    def decided(self) -> bool:
        """Did the experiment reach a conclusion on its predeclared terms?

        SUPPORTED and KILLED are both yes. This is the distinction the estate's
        `status` field would otherwise flatten.
        """
        return self.verdict in (SUPPORTED, KILLED)

    def to_report(self) -> dict:
        """A receipt in the shape the renderer and checkers already read.

        One subtlety worth stating loudly, because getting it wrong would
        corrupt the meaning of every receipt in the estate: **`status` here says
        the EXPERIMENT decided, not that the audited claim survived.** A killed
        hypothesis is a successful run — the lab spent an afternoon and bought
        back a claim it could not defend — and filing that as a failure would
        punish exactly the behaviour this whole runner exists to make cheap.
        `claim_boundary` therefore always spells out which of the two happened.
        """
        return {
            "experiment": f"{self.hypothesis.id}-hypothesis",
            "milestone": self.hypothesis.id,
            "schema": 1,
            "status": "pass" if self.decided else "null",
            "headline": self.headline(),
            "claim_boundary": self.boundary(),
            "hypothesis": self.hypothesis.to_json(),
            "verdict": self.verdict,
            "detail": self.detail,
            "evidence": self.evidence,
            "controls": self.controls,
            "wall_seconds": self.wall_seconds,
        }

    def headline(self) -> str:
        return {
            SUPPORTED: f"{self.hypothesis.id} ran and the claim under test survived",
            KILLED: f"{self.hypothesis.id} ran and killed the claim under test",
            UNRESOLVED: f"{self.hypothesis.id} ran and did not decide",
        }[self.verdict]

    def boundary(self) -> str:
        shared = ("`status: pass` on this receipt means the experiment reached a "
                  "verdict with its controls intact — it does NOT mean the "
                  "audited claim survived. ")
        return shared + {
            SUPPORTED: ("Here it did: the hypothesis was not killed by the "
                        "evidence declared in advance. That is weaker than "
                        "proof — it means one specific way of being wrong has "
                        "been ruled out, at one depth."),
            KILLED: ("Here it did not: the kill condition written before the "
                     "run was met, and the claim it names is retracted. This "
                     "receipt is the record of a lab correcting itself, and "
                     "should be read as a result, not a fault."),
            UNRESOLVED: ("Neither: the run happened and the evidence does not "
                         "decide. Nothing may be concluded from it in either "
                         "direction."),
        }[self.verdict]
