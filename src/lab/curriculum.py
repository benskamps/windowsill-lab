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
    "C01": "c01",
    "A01": "a01",
    "I01": "i01",
}

# Options injected by an unattended scheduler are not universal experiment
# arguments.  Keeping the capability contract beside RUNNERS prevents `lab
# next --seed … --device …` from aborting C01/A01/I01 or M17 at argparse.
_SEEDED_AND_DEVICE = frozenset({"seed", "device"})
RUNNER_SCHEDULER_OPTIONS = {
    **{f"M{i:02d}": _SEEDED_AND_DEVICE for i in range(1, 17)},
    "M17": frozenset({"seed"}),
    "C01": frozenset(),
    "A01": frozenset(),
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
# M01 stays as ONE slot: the calibration pulse, demoted from daily headline.
ROTATION: tuple[str, ...] = (
    "M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10",
    "M11", "M13", "M14", "M15", "M17", "C01", "A01", "I01",
)


def _i01_hardware_gate() -> str | None:
    """I01 needs a real dark-frame stack or an explicitly configured camera.

    Deterministic and disclosed: the scheduler checks configuration only
    (an env var naming an existing stack, or an explicit ``LAB_I01_CAMERA``)
    — it never probes a device. There is currently no webcam on either box,
    so without configuration this gate skips I01 with a named reason instead
    of shipping a failure run every pass.
    """
    frames = os.environ.get("WINDOWSILL_I01_FRAMES")
    if frames and Path(frames).exists():
        return None
    if os.environ.get("LAB_I01_CAMERA"):
        return None
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


def rotation_pointer(records: Iterable[tuple[str, str]]) -> str | None:
    """The milestone of the newest-stamped receipt — the committed pointer.

    ``records`` are ``(generated_at_or_date, milestone)`` tuples read from the
    committed receipts ledger (``reports/receipts/``), the same clone-stable
    derivation ``publish.run_cadence`` trusts. Max is by stamp string (ISO
    stamps and bare ``YYYY-MM-DD`` dates share a lexicographic order; a bare
    date sorts before any stamped receipt of the same day), tie-broken by
    milestone id so every box derives the identical pointer. No records →
    ``None`` → the rotation starts at its first slot.
    """
    best: tuple[str, str] | None = None
    for stamp, mid in records:
        if not stamp or not mid:
            continue
        key = (str(stamp), str(mid))
        if best is None or key > best:
            best = key
    return best[1] if best else None


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
