"""Shared curriculum capabilities.

This module is deliberately import-light. Both the scheduler and the public
snapshot need to know whether an open milestone has an implemented runner; one
small registry keeps that operational fact from drifting between them.
"""

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
