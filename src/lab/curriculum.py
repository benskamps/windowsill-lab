"""Shared curriculum capabilities.

This module is deliberately import-light (stdlib only). Both the scheduler and
the public snapshot need to know whether an open milestone has an implemented
runner; one small registry keeps that operational fact from drifting between
them. The portfolio ROTATION and its hardware gates live here for the same
reason: selection facts shared by every box must have exactly one committed
home (docs/investigations/2026-08-01-portfolio-rotation.md).
"""
import math
import os
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

RUNNERS = {
    "M01": "run",
    "M02": "m02",
    "M03": "m03",
    "M04": "m04",
    "M05": "m05",
    "M06": "m06",
    "M07": "m07",
    "M08": "m08",
    "M09": "m09",
    "M10": "m10",
    "M11": "m11",
    "M12": "m12",
    "M13": "m13",
    "M14": "m14",
    "M15": "m15",
    "M16": "m16",
    "M17": "m17",
    "M18": "m18",
    "K01": "k01",
    "K02": "k02",
    "C01": "c01",
    "A01": "a01",
    "A03": "a03",
    "A04": "a04",
    # A05's runner is the survey driver: a bounded, checkpointed, resumable
    # hunt slice (scripts/a05_hunt.py via `lab hunt`). Registered 2026-08-15 —
    # until then the planner's survey-slot special case carried dispatch and
    # the groundskeeper flagged "frontier A05 has NO RUNNER while the pipeline
    # is active". Dispatch is gated by _a05_survey_gate below: a box hunts
    # only its assigned sector lane, and only while committed receipts show
    # remaining coverage there.
    "A05": "hunt",
    "I01": "i01",
}

# Options injected by an unattended scheduler are not universal experiment
# arguments.  Keeping the capability contract beside RUNNERS prevents `lab
# next --seed … --device …` from aborting C01/A01/I01 or M17 at argparse.
_SEEDED_AND_DEVICE = frozenset({"seed", "device"})
RUNNER_SCHEDULER_OPTIONS = {
    **{f"M{i:02d}": _SEEDED_AND_DEVICE for i in range(1, 17)},
    "M17": frozenset({"seed"}),
    "M18": frozenset({"seed", "device"}),
    "K01": frozenset({"seed"}),
    # K02 sweeps a LADDER of population sizes over a fixed set of initial
    # conditions (`--seeds`), so a scheduler's single `--seed` is not a thing it
    # can accept — the seed set is part of the measurement's identity.
    "K02": frozenset(),
    "C01": frozenset(),
    "A01": frozenset(),
    # A03 pins its own event, band and chirp-mass grid; a scheduler seed would
    # not change the measurement, only pretend to.
    "A03": frozenset(),
    "A04": frozenset(),
    # The hunt driver names its own seed and slice; scheduler --seed/--device
    # would abort at its argparse.
    "A05": frozenset(),
    "I01": frozenset(),
}


def runner_for(milestone_id: str) -> str | None:
    """Return the runnable ``lab`` subcommand for a milestone, if one exists."""

    return RUNNERS.get(milestone_id)


# ── the portfolio rotation ──────────────────────────────────────────────────
# Curated and committed — NOT derived from RUNNERS. Membership is a cost
# decision as much as a capability one, so changes are deliberate one-line PRs.
# Deliberately excluded at birth:
#   M12 — the full parallel-tempering run exceeds the Windows PT2H task slot
#         (ExecutionTimeLimit in the nightly task XML); the `--quick` variant
#         ships a `[~]` null every pass (all three committed M12 receipts are
#         quick-run nulls). Either membership choice is receipt spam.
#   M16 — same wall-clock class as M12 (3D spin-glass aging).
#   K02 — an N-ladder, not a single run: five population sizes × five initial
#         conditions is ~20 min of CPU, the same wall-clock class as M12/M16, and
#         its verdict is a once-measured N-scaling statement rather than a nightly
#         pulse. Hand-run, like M12/M16.
# M01 stays as ONE slot: the calibration pulse, demoted from daily headline.
# K01 joined 2026-08-02 with the K (coherence) track: ~105 s of NumPy on CPU, no
# hardware gate, and a self-contained calibration whose verdict is meaningful on
# every pass — it clears both bars the exclusions above were written to enforce.
# It sits with the physics rungs rather than at the tail, because the walk is
# grouped: the convergence ladders (M, K) first, then the citizen-science tracks
# (C, A, I). That keeps I01 — the one gated slot — last, where the wrap lands on
# the M01 calibration pulse.
# A03 joined 2026-08-07 beside A01 on the astronomy track: ~445 s of NumPy on
# CPU after a one-time 328 MB GWOSC fetch that then lives in ~/.lab/cache, so
# steady-state cost is the same class as C01/A01. It ships a `[~]` null, which
# would normally read as receipt spam (see the M12 exclusion above) — the
# difference is that A03's null is CONTROLLED: every pass re-proves the filter
# recovers an injected chirp mass to ~2e-5 Msun before reporting on the sky, so
# a passing receipt is a live statement that the pipeline still works, and the
# day the sky column changes it will be because something real changed.
# 2026-08-14 growth (the planner era): M18, K02 and A04 joined once the value
# function took over selection — the original curation existed partly to stop
# a dumb wheel from wasting turns, and the planner's class ordering + repeat
# decay now do that by law, so membership is bounded by SAFETY, not taste.
# M18 = 227 s full GPU run; A04 ≈ 130 s warm with deadline-guarded MAST calls
# (a network outage fails one slot, never wedges it); K02's hero ladder is
# ~63 min — inside the Windows task ExecutionTimeLimit, and its cost divisor
# makes the planner reach for it rarely, which is the correct cadence for a
# verified rung. M12/M16 REMAIN excluded by wall-clock class (PT2H-exceeding
# full runs / null-spam quick variants — see the 2026-08-01 rotation doc);
# they are still hand-run.
ROTATION: tuple[str, ...] = (
    "M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10",
    "M11", "M13", "M14", "M15", "M17", "M18", "K01", "K02", "C01", "A01",
    "A03", "A04", "I01",
)


def _i01_hardware_gate() -> str | None:
    """I01 needs a real dark-frame stack the DISPATCH can actually measure.

    Deterministic and disclosed: the scheduler checks configuration only — it
    never probes a device. Eligible exactly when ``WINDOWSILL_I01_FRAMES``
    names an existing stack, because that is the one input a scheduled bare
    ``lab i01`` reads (the dispatch passes no capture flags, and ``run_i01``
    never consults ``LAB_I01_CAMERA``). A camera-only config must NOT pass:
    the dispatched run would exit 3 with no receipt, the pointer would never
    advance, and every later pass would re-pick I01 — a rotation livelock.
    Live capture stays an attended ``lab i01 --camera N``.
    """
    frames = os.environ.get("WINDOWSILL_I01_FRAMES")
    if frames and Path(frames).exists():
        return None
    if os.environ.get("LAB_I01_CAMERA"):
        return (
            "no-frames: LAB_I01_CAMERA is set, but a scheduled bare `lab i01` "
            "cannot capture (live capture is an attended `lab i01 --camera N`);"
            " set WINDOWSILL_I01_FRAMES to an existing dark-frame stack to put "
            "I01 in rotation"
        )
    return (
        "no-camera: no capture device configured (LAB_I01_CAMERA unset) and "
        "WINDOWSILL_I01_FRAMES names no existing dark-frame stack"
    )


def hunt_lane() -> tuple[int, ...] | None:
    """This box's assigned survey sectors, or ``None`` when unassigned.

    The A05 sector split (2026-08-14 handoff: win = 2,29 · loam = 3,30) is
    box-local configuration, exactly like I01's frame stack: the env var
    ``WINDOWSILL_HUNT_SECTORS`` wins, else the ``LAB_HOME/hunt-sectors`` file
    (one line, comma-separated sector ints — friendlier to a Windows
    Scheduled Task than env plumbing). Malformed config reads as unassigned:
    a box that cannot prove its lane must not hunt — on 2026-08-15 a bare
    hunt on the wrong box's lane silently overwrote a committed receipt and
    took a lead-awaiting-human-review row with it.
    """
    raw = os.environ.get("WINDOWSILL_HUNT_SECTORS", "")
    if not raw:
        from .labhome import LAB_HOME   # lazy: keep module import stdlib-only
        path = LAB_HOME / "hunt-sectors"
        try:
            raw = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        except OSError:
            raw = ""
    if not raw:
        return None
    try:
        sectors = tuple(int(part) for part in raw.replace(",", " ").split())
    except ValueError:
        return None
    return sectors or None


def _a05_survey_gate() -> str | None:
    """A05 dispatches only on a box with an assigned lane that still has sky.

    Same contract as the I01 gate: deterministic, configuration + committed
    files only, never probes hardware or network. Refusing here keeps the
    scheduler honest instead of livelocked — a dispatched hunt with no lane
    or no remaining coverage would exit without a receipt and be re-picked
    forever.
    """
    lane = hunt_lane()
    if lane is None:
        return (
            "no-lane: this box has no assigned survey sectors — set "
            "WINDOWSILL_HUNT_SECTORS or write LAB_HOME/hunt-sectors "
            "(2026-08-14 split: win '2,29' · loam '3,30') to put A05 in "
            "dispatch"
        )
    from . import cli   # lazy: cli imports this module at load time
    status = cli._hunt_status()
    if status is None:
        return "no-sky: committed receipts show no remaining enumerated coverage"
    per_sector = status.get("per_sector") or {}
    remaining = sum(per_sector.get(sector, 0) for sector in lane)
    if remaining <= 0:
        return (f"lane-exhausted: sectors {','.join(map(str, lane))} have no "
                "remaining committed coverage (other lanes may still have sky)")
    return None


# milestone id → gate; a gate returns None (eligible) or a named skip reason.
HARDWARE_GATES: dict[str, Callable[[], str | None]] = {
    "I01": _i01_hardware_gate,
    "A05": _a05_survey_gate,
}


def hardware_gate_reason(milestone_id: str) -> str | None:
    """None when the milestone's hardware gate passes (or it has no gate)."""
    gate = HARDWARE_GATES.get(milestone_id)
    return gate() if gate is not None else None


def select_rotation(
    milestones: list[dict], last_mid: str | None,
) -> tuple[str | None, list[tuple[str, str]]]:
    """Pick the next eligible ROTATION slot after ``last_mid`` (wrapping).

    Pure selection: reads state, runs nothing, edits nothing. Returns
    ``(pick, skips)`` where ``skips`` is every ``(milestone, reason)`` walked
    over — the caller must disclose them (a log line, not a receipt).
    Eligibility: a registered runner, a passing hardware gate, and not
    currently OPEN (the frontier branch owns the open bench — rotation must
    never double-dispatch it). An unknown or absent pointer starts at slot 0.
    Nothing eligible → ``(None, skips)`` and the caller fails closed to the
    heartbeat with a named reason.
    """
    skips: list[tuple[str, str]] = []
    if not ROTATION:
        return None, skips
    open_ids = {m.get("id") for m in milestones if m.get("status") == "open"}
    start = (ROTATION.index(last_mid) + 1) % len(ROTATION) if last_mid in ROTATION else 0
    for offset in range(len(ROTATION)):
        mid = ROTATION[(start + offset) % len(ROTATION)]
        if mid not in RUNNERS:
            skips.append((mid, "no runner registered"))
            continue
        reason = hardware_gate_reason(mid)
        if reason is not None:
            skips.append((mid, reason))
            continue
        if mid in open_ids:
            skips.append((mid, "open on the bench — the frontier branch owns it"))
            continue
        return mid, skips
    return None, skips


def _newest_milestone(
    records: Iterable[tuple[str, str]], *, only_rotation: bool,
) -> str | None:
    """Max-stamp milestone over ``records``, optionally rotation-members only.

    Max is by stamp string (ISO stamps and bare ``YYYY-MM-DD`` dates share a
    lexicographic order; a bare date sorts before any stamped receipt of the
    same day), tie-broken by milestone id so every box derives the identical
    answer from the same committed ledger regardless of iteration order.
    """
    best: tuple[str, str] | None = None
    for stamp, mid in records:
        if not stamp or not mid:
            continue
        mid = str(mid)
        if only_rotation and mid not in ROTATION:
            continue
        key = (str(stamp), mid)
        if best is None or key > best:
            best = key
    return best[1] if best else None


def rotation_pointer(records: Iterable[tuple[str, str]]) -> str | None:
    """The newest-stamped receipt THE ROTATION OWNS — the committed pointer.

    ``records`` are ``(generated_at_or_date, milestone)`` tuples read from the
    committed receipts ledger (``reports/receipts/``), the same clone-stable
    derivation ``publish.run_cadence`` trusts.

    Receipts for milestones OUTSIDE ``ROTATION`` are skipped rather than
    returned as an unknown pointer. They exist and they are not rare: M12/M16
    are excluded from the rotation by name but are still hand-run (four such
    receipts are already committed), and the frontier lands one the moment its
    milestone gets a runner. An unknown pointer restarts the walk at slot 0, so
    letting one win meant a single manual ``lab m12`` re-seeded M01 as the next
    pick and rewound the whole lap — reintroducing exactly the M01-every-pass
    bias the rotation exists to remove. Skipping them resumes from the last
    slot the rotation itself ran.

    No rotation receipt → ``None`` → the walk opens at the first slot. Callers
    disclosing that case should use ``newest_receipt_milestone`` to say WHY
    (empty ledger vs. a ledger with only out-of-rotation receipts).
    """
    return _newest_milestone(records, only_rotation=True)


def newest_receipt_milestone(records: Iterable[tuple[str, str]]) -> str | None:
    """Newest-stamped receipt of ANY milestone — disclosure only, never selection.

    Selection reads ``rotation_pointer``. This exists so a reason line can name
    the out-of-rotation receipt that is NOT being used as the pointer, instead
    of claiming an empty ledger.
    """
    return _newest_milestone(records, only_rotation=False)


# ── the value-function planner (v1) ─────────────────────────────────────────
# WHY THIS EXISTS: 84 of the first 136 committed receipts were M01 (x40) and
# M02 (x44). Two scheduler bugs — a stuck open-pointer falling back to M01
# nightly, and a stem-slice parse bug livelocking M01→M02-every-pass for nine
# days — made the lab re-run verified calibration rungs on loop while CI
# stayed green. The round-robin walk (`select_rotation`) fixed the pointer but
# still treats a never-measured rung and a canary that ran yesterday as equal
# citizens. The planner replaces "whose turn is it" with "what is a turn worth":
# every decision is a value/cost score derived from the receipts ledger itself,
# the decision ships inside the receipt it produces, and repeats decay by law
# so no defect in any OTHER part of the scheduler can ever again buy 40
# consecutive receipts of one slug.

#: Planner identity stamped into every decision record — bump on any scoring
#: change so an old receipt's planned block is never re-derived against new law.
PLANNER_VERSION = "v1"

#: Class base values, strictly ordered: an OPEN frontier milestone is the whole
#: point of the lab; a rung that has NEVER produced a receipt is a missing
#: measurement; a NULL is a kept miss worth an occasional retry; a VERIFIED
#: rung is a canary — near-worthless the day after it ran, due again in a week.
OPEN_FRONTIER_VALUE = 8.0
NEVER_RUN_VALUE = 5.0
NULL_RETRY_VALUE = 3.0
VERIFIED_CANARY_VALUE = 1.0

#: A verified canary comes due over about a week: its staleness multiplier is
#: log2(1 + days/CANARY_HALF_LIFE_DAYS) — ~0.19 the day after it ran, 1.0 at
#: seven days, then slow growth.
CANARY_HALF_LIFE_DAYS = 7.0

#: Staleness cap. Deliberately BELOW NEVER_RUN_VALUE / VERIFIED_CANARY_VALUE
#: (4 < 5): no matter how stale, a verified canary can never outrank a rung
#: that has never been measured at all. Class order is an invariant, not a
#: tendency (tests/test_planner.py pins it).
STALENESS_CAP = 4.0

#: The repeat law's hard cap: with at least two eligible candidates of nonzero
#: base value, the planner cannot choose the same mid more than this many
#: consecutive times. The exponential decay (value × 2^-repeats) makes a
#: fourth repeat unlikely; the cap makes it impossible — decay alone cannot
#: bound a frontier rung whose base value dwarfs every alternative.
REPEAT_HARD_CAP = 3

#: The synthetic survey-hunt candidate (scripts/a05_hunt.py). Not a ROTATION
#: member and not in RUNNERS — callers that cannot dispatch it pass
#: ``hunt_status=None`` and it never appears.
HUNT_CANDIDATE = "A05-HUNT"

#: remaining_targets at (or above) which the hunt scores full OPEN_FRONTIER
#: value; below it the hunt's value scales down linearly with what is left.
HUNT_FULL_VALUE_TARGETS = 500


def _parse_stamp(stamp: str) -> datetime | None:
    """A receipt stamp (ISO datetime or bare ``YYYY-MM-DD``) as aware UTC.

    Unparseable stamps return ``None`` — the caller degrades, never raises,
    because a malformed committed receipt must not kill the scheduler.
    """
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _head_run(ordered: list[tuple[str, str]]) -> tuple[str | None, int]:
    """The mid at the head (newest stamp) of the ledger and its consecutive run.

    Counted over ALL receipts, rotation members or not: a manual ``lab m12``
    genuinely breaks an M01 streak, so it genuinely resets the decay.
    """
    if not ordered:
        return None, 0
    head = ordered[-1][1]
    run = 0
    for _stamp, mid in reversed(ordered):
        if mid != head:
            break
        run += 1
    return head, run


def plan_turn(
    records: Iterable[tuple[str, str]],
    milestones: Mapping[str, str] | None = None,
    now: datetime | None = None,
    hunt_status: Mapping[str, object] | None = None,
    durations: Mapping[str, Sequence[float]] | None = None,
) -> tuple[str | None, dict]:
    """Score every eligible candidate and pick the most valuable turn.

    Pure in the scheduler's sense: reads committed state (``records`` — the
    ``(stamp, mid)`` receipt-ledger tuples ``cli._receipt_records`` produces —
    plus a ``{mid: status}`` mapping the caller derives from
    ``parse_milestones``), runs nothing, writes nothing. Every input the score
    depends on is a parameter, so a checker holding the same ledger re-derives
    the same decision (``now`` defaults to the wall clock; pass it explicitly
    to re-derive). The hardware gates it consults read configuration only, the
    same promise ``select_rotation`` makes.

    Candidates: ROTATION members with a runner and a passing hardware gate;
    plus any OPEN milestone with a runner and passing gate (the frontier —
    inside or outside the rotation, its class outscores everything, which is
    the 2026-06-26 frontier-first decision expressed as value instead of
    branch order); plus the synthetic ``A05-HUNT`` when ``hunt_status`` says
    targets remain.

    Score(mid) = value(mid) / cost(mid):

    * class base value (constants above), staleness-scaled for verified rungs;
    * repeat decay — value × 2^-(consecutive repeats at the ledger head), and
      at ``REPEAT_HARD_CAP`` repeats the value drops to zero outright whenever
      any other candidate still scores above zero. The hunt is EXEMPT: each
      hunt turn searches a fresh slice of the sector (cumulative by
      construction), so a repeated hunt is new coverage, not a re-measurement;
    * cost — ``max(1.0, median_wall_seconds / median_of_medians)`` when the
      caller supplies durations, else 1.0. A penalty only, never a discount:
      clamping at 1.0 keeps a cheap canary from buying its way past the class
      ordering, so the invariant above survives the cost seam.

    Ties break by the rotation walk order starting after the ledger pointer —
    the planner degrades EXACTLY to ``select_rotation`` when the scores cannot
    distinguish candidates, which keeps two boxes reading the same committed
    ledger picking different slots, not the same one.

    Returns ``(mid, decision)`` — ``mid`` is ``None`` only when nothing is
    eligible. ``decision`` is the receipt-ready record: chosen, one-line
    reason, top-5 scoreboard, planner version, and the named skips the caller
    must disclose.
    """
    statuses = dict(milestones or {})
    if now is None:
        now = datetime.now(timezone.utc)
    ordered = sorted(
        (str(stamp), str(mid)) for stamp, mid in records if stamp and mid
    )
    head_mid, head_run = _head_run(ordered)
    last_stamp: dict[str, str] = {}
    for stamp, mid in ordered:
        last_stamp[mid] = stamp  # ordered ascending — the last write wins

    skips: list[tuple[str, str]] = []
    open_ids = [m for m, s in statuses.items() if s == "open"]

    # Ordered candidate list; rank is the tie-break (see docstring).
    pointer = _newest_milestone(ordered, only_rotation=True)
    start = (ROTATION.index(pointer) + 1) % len(ROTATION) \
        if pointer in ROTATION else 0
    candidates: list[tuple[str, int]] = []   # (mid, walk_rank)
    for mid in open_ids:
        if mid in ROTATION:
            continue  # ranked below with its rotation slot; class still wins
        if mid not in RUNNERS:
            continue  # branch-1 territory: cli names "no runner" itself
        reason = hardware_gate_reason(mid)
        if reason is not None:
            skips.append((mid, reason))
            continue
        candidates.append((mid, -2))         # exact ties: the bench wins
    if hunt_status is not None and int(hunt_status.get("remaining_targets", 0) or 0) > 0:
        candidates.append((HUNT_CANDIDATE, -1))
    for offset in range(len(ROTATION)):
        mid = ROTATION[(start + offset) % len(ROTATION)]
        if mid not in RUNNERS:
            skips.append((mid, "no runner registered"))
            continue
        reason = hardware_gate_reason(mid)
        if reason is not None:
            skips.append((mid, reason))
            continue
        candidates.append((mid, offset))

    med_by_mid: dict[str, float] = {}
    if durations:
        for mid, walls in durations.items():
            walls = [w for w in walls if isinstance(w, (int, float)) and w > 0]
            if walls:
                med_by_mid[mid] = statistics.median(walls)
    norm = statistics.median(med_by_mid.values()) if med_by_mid else 1.0

    scoreboard: list[dict] = []
    for mid, rank in candidates:
        if mid == HUNT_CANDIDATE:
            cls = "hunt"
            remaining = int(hunt_status.get("remaining_targets", 0) or 0)
            value = OPEN_FRONTIER_VALUE * min(
                1.0, remaining / HUNT_FULL_VALUE_TARGETS)
        elif statuses.get(mid) == "open":
            cls, value = "open-frontier", OPEN_FRONTIER_VALUE
        elif mid not in last_stamp:
            cls, value = "never-run", NEVER_RUN_VALUE
        elif statuses.get(mid) == "null":
            cls, value = "null-retry", NULL_RETRY_VALUE
        else:
            cls = "verified-canary"
            stamped = _parse_stamp(last_stamp[mid])
            if stamped is None:
                multiplier = 1.0  # unreadable stamp: neither free nor urgent
            else:
                days = max(0.0, (now - stamped).total_seconds() / 86400.0)
                multiplier = min(
                    STALENESS_CAP,
                    math.log2(1.0 + days / CANARY_HALF_LIFE_DAYS),
                )
            value = VERIFIED_CANARY_VALUE * multiplier
        repeats = head_run if (mid == head_mid and mid != HUNT_CANDIDATE) else 0
        value *= 2.0 ** -repeats
        cost = max(1.0, med_by_mid[mid] / norm) if mid in med_by_mid and norm > 0 \
            else 1.0
        scoreboard.append({
            "mid": mid, "cls": cls, "value": round(value, 4),
            "cost": round(cost, 4), "score": round(value / cost, 4),
            "repeats": repeats, "_rank": rank,
        })

    # The repeat law's hard cap: decay alone cannot bound a class gap.
    capped = next(
        (e for e in scoreboard if e["repeats"] >= REPEAT_HARD_CAP), None)
    if capped is not None and any(
            e["score"] > 0 for e in scoreboard if e is not capped):
        capped["value"] = 0.0
        capped["score"] = 0.0
        capped["cls"] += " (repeat-capped)"

    scoreboard.sort(key=lambda e: (-e["score"], e["_rank"], e["mid"]))
    decision: dict = {"planner": PLANNER_VERSION, "skips": skips}
    if not scoreboard:
        decision.update({
            "chosen": None, "scoreboard": [],
            "reason": "planner v1: no eligible candidates",
        })
        return None, decision

    top, runner_up = scoreboard[0], (scoreboard[1] if len(scoreboard) > 1 else None)
    chosen = top["mid"]
    if runner_up is not None and runner_up["score"] == top["score"]:
        # A tie is the round-robin case — say so in the rotation's own words.
        if not ordered:
            context = "no receipts — rotation opens at its first slot"
        elif pointer is None:
            newest = _newest_milestone(ordered, only_rotation=False)
            context = (
                f"no rotation receipt yet (newest is {newest}, outside the "
                "rotation) — rotation opens at its first slot"
            )
        else:
            context = (
                f"rotation continues after {pointer} "
                f"(tie at {top['score']:.2f})"
            )
        reason = f"planner v1: {chosen} {top['cls']} — {context}"
    elif runner_up is None:
        reason = (
            f"planner v1: {chosen} {top['cls']} "
            f"(score {top['score']:.2f}) is the only eligible candidate"
        )
    else:
        reason = (
            f"planner v1: {chosen} {top['cls']} (score {top['score']:.2f}) "
            f"beats {runner_up['mid']} {runner_up['cls']} "
            f"({runner_up['score']:.2f})"
        )
    for entry in scoreboard:
        entry.pop("_rank", None)
    decision.update({
        "chosen": chosen, "reason": reason, "scoreboard": scoreboard[:5],
    })
    return chosen, decision


def filter_scheduler_options(
    milestone_id: str, args: list[str],
) -> tuple[list[str], list[str]]:
    """Drop only unsupported scheduler-owned ``--seed``/``--device`` knobs.

    All other arguments are preserved for the target parser to validate.  The
    second return value names dropped options so callers can log the decision
    instead of silently changing a run.
    """
    supported = RUNNER_SCHEDULER_OPTIONS.get(milestone_id, frozenset())
    kept: list[str] = []
    dropped: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        matched = next(
            (
                name for name in ("seed", "device")
                if arg == f"--{name}" or arg.startswith(f"--{name}=")
            ),
            None,
        )
        if matched is None or matched in supported:
            kept.append(arg)
            i += 1
            continue

        dropped.append(f"--{matched}")
        i += 1
        # A bare scheduler option owns its following token only when that token
        # is actually a value.  Malformed input such as ``--seed --quick`` must
        # not make filtering swallow ``--quick`` before the target parser sees
        # it.  Attached values (``--seed=17``) are already contained in ``arg``.
        if (
            arg == f"--{matched}"
            and i < len(args)
            and (
                not args[i].startswith("-")
                or args[i][1:].isdigit()
            )
        ):
            i += 1
    return kept, dropped
