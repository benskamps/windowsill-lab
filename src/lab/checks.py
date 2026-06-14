"""Make ``verified`` mean something a machine confirmed.

A green leaf on the windowsill should be a *receipt*, not an honor-system
checkbox. This module re-derives a milestone's headline number from a run report
and asserts it against the known answer. ``lab verify`` runs the registered
checks; CI runs ``lab verify`` so a milestone can't be marked ``[x]`` unless its
number actually reproduces.

Each check is *applicable* only to reports it understands (it returns ``None``
for ones it can't read), so a milestone is graded against the newest report it
can actually evaluate — not whatever ran most recently. Stdlib only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .publish import LAB_HOME, MILESTONES_MD, REPORTS_DIR, parse_milestones

# Onsager's exact 2D Ising critical temperature, 1944.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.2692


def _reports_newest_first() -> list[Path]:
    paths: list[Path] = []
    for d in (REPORTS_DIR, LAB_HOME):
        if d.exists():
            paths += d.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")
    return sorted(paths, key=lambda p: p.stem, reverse=True)


def check_m01(report: dict) -> tuple[bool | None, str]:
    """2D Ising: the susceptibility χ peaks at the (finite-size) critical point.

    Returns ``None`` if this report isn't an Ising χ-sweep (not applicable).
    Otherwise recovers T at max(χ) and asserts it sits near Onsager's exact T_c
    — a generous tolerance, since this catches a broken simulation, not a
    high-precision exponent claim.
    """
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi):
        return None, "not an Ising χ-sweep"
    peak_T = T[max(range(len(chi)), key=lambda i: chi[i])]
    tol = 0.2
    ok = abs(peak_T - ONSAGER_TC) <= tol
    return ok, f"χ peak at T={peak_T:.3f} vs Onsager {ONSAGER_TC:.3f} (tol ±{tol})"


# milestone id → check. Add entries as milestones land; the rest report
# "unchecked" so the gap is visible rather than silently assumed.
CHECKS = {"M01": check_m01}


def _grade(fn, reports: list[dict]) -> tuple[str, str]:
    """Grade a milestone against the newest report its check can evaluate."""
    for rep in reports:
        ok, detail = fn(rep)
        if ok is not None:
            return ("pass" if ok else "fail"), detail
    return "no-report", "no report this check can evaluate"


def verify(ids: list[str] | None = None) -> list[dict]:
    """Run registered checks against every verified milestone (or just ``ids``).

    Each result: ``pass`` / ``fail`` (check ran), ``unchecked`` (no check yet),
    or ``no-report`` (nothing the check can read).
    """
    ms = parse_milestones(MILESTONES_MD.read_text(encoding="utf-8") if MILESTONES_MD.exists() else "")
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in _reports_newest_first()]

    results: list[dict] = []
    for m in ms:
        if m["status"] != "verified" or (ids and m["id"] not in ids):
            continue
        fn = CHECKS.get(m["id"])
        if fn is None:
            results.append({"id": m["id"], "status": "unchecked", "detail": "no check registered"})
        else:
            status, detail = _grade(fn, reports)
            results.append({"id": m["id"], "status": status, "detail": detail})
    return results
