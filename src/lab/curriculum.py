"""Shared curriculum capabilities.

This module is deliberately import-light (stdlib only). Both the scheduler and
the public snapshot need to know whether an open milestone has an implemented
runner; one small registry keeps that operational fact from drifting between
them. The portfolio ROTATION and its hardware gates live here for the same
reason: selection facts shared by every box must have exactly one committed
home (docs/investigations/2026-08-01-portfolio-rotation.md).
"""
import os
from collections.abc import Callable, Iterable
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
ROTATION: tuple[str, ...] = (
    "M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10",
    "M11", "M13", "M14", "M15", "M17", "K01", "C01", "A01", "A03", "I01",
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


# milestone id → gate; a gate returns None (eligible) or a named skip reason.
HARDWARE_GATES: dict[str, Callable[[], str | None]] = {
    "I01": _i01_hardware_gate,
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
