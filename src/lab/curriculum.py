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
}


def runner_for(milestone_id: str) -> str | None:
    """Return the runnable ``lab`` subcommand for a milestone, if one exists."""

    return RUNNERS.get(milestone_id)
