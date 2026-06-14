"""Make ``verified`` mean something a machine confirmed.

A green leaf on the windowsill should be a *receipt*, not an honor-system
checkbox. This module re-derives a milestone's headline number from the run
report it committed and asserts it against the known answer. ``lab verify`` runs
the registered checks; CI runs ``lab verify`` so a milestone can't be marked
``[x]`` unless its number actually reproduces.

Stdlib only — no torch/numpy — so it runs in CI in a second.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .publish import LAB_HOME, MILESTONES_MD, REPORTS_DIR, parse_milestones

# Onsager's exact 2D Ising critical temperature, 1944.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.2692


def _latest_report() -> Path | None:
    candidates: list[Path] = []
    for d in (REPORTS_DIR, LAB_HOME):
        if d.exists():
            candidates += d.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")
    return max(candidates, key=lambda p: p.stem) if candidates else None


def check_m01(report: dict) -> tuple[bool, str]:
    """2D Ising: the susceptibility χ peaks at the (finite-size) critical point.

    Recover T at max(χ) and assert it sits near Onsager's exact T_c. A coarse
    temperature grid and finite L shift the pseudo-critical peak slightly up, so
    we allow a generous tolerance — this catches a broken simulation, not a
    high-precision exponent claim.
    """
    T, chi = report.get("T"), report.get("chi")
    if not T or not chi or len(T) != len(chi):
        return False, "report missing T/chi arrays"
    peak_T = T[max(range(len(chi)), key=lambda i: chi[i])]
    tol = 0.2
    ok = abs(peak_T - ONSAGER_TC) <= tol
    return ok, f"χ peak at T={peak_T:.3f} vs Onsager {ONSAGER_TC:.3f} (tol ±{tol})"


# milestone id → check. Add entries as milestones land; the rest report
# "unchecked" so the gap is visible rather than silently assumed.
CHECKS = {"M01": check_m01}


def verify(ids: list[str] | None = None) -> list[dict]:
    """Run registered checks against every verified milestone (or just ``ids``).

    Each result: ``pass`` / ``fail`` (check ran), ``unchecked`` (no check yet),
    or ``no-report`` (nothing to check against).
    """
    ms = parse_milestones(MILESTONES_MD.read_text() if MILESTONES_MD.exists() else "")
    report_path = _latest_report()
    report = json.loads(report_path.read_text()) if report_path else None

    results: list[dict] = []
    for m in ms:
        if m["status"] != "verified" or (ids and m["id"] not in ids):
            continue
        fn = CHECKS.get(m["id"])
        if fn is None:
            results.append({"id": m["id"], "status": "unchecked", "detail": "no check registered"})
        elif report is None:
            results.append({"id": m["id"], "status": "no-report", "detail": "no run report found"})
        else:
            ok, detail = fn(report)
            results.append({"id": m["id"], "status": "pass" if ok else "fail", "detail": detail})
    return results
