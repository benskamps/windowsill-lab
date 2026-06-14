"""Publish a sanitized windowsill snapshot — the food for seed-in-a-pot.

The lab is the calm sibling's food source. Each verified milestone on the
ladder becomes a node on the seedling's stem at
https://www.brokenbranch.dev/windowsill/ ; a failed calibration is a folded
grey leaf (an honest null). This module builds a small, sanitized ``pot.json``
(milestones, run cadence, CPU heat — no private data, no project internals) and
optionally pushes it to a public gist the site reads via ``/api/pot``.

Kept deliberately import-light (standard library only) so the pure functions
``parse_milestones`` / ``build_snapshot`` are unit-tested without pulling in
torch or matplotlib.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Mirror render.LAB_HOME without importing it (render pulls matplotlib).
LAB_HOME = Path.home() / ".lab"
REPO_ROOT = Path(__file__).resolve().parents[2]
MILESTONES_MD = REPO_ROOT / "MILESTONES.md"
REPORTS_DIR = REPO_ROOT / "reports"

# A checklist line: "- [x] **M01** — 2D Ising verification. ..."
# IDs are letter-prefixed by track: M=physics, C=compute/number-theory,
# A=astronomy, I=instrument, B=BOINC. An optional trailing "{venue=…; url=…;
# doi=…}" tag links a contribution to its official record.
_MILESTONE_RE = re.compile(
    r"^\s*-\s*\[(?P<box>[ xX~\-])\]\s*\*\*(?P<id>[A-Z]{1,3}\d+)\*\*\s*[—\-]\s*(?P<body>.*\S)\s*$"
)
_TAG_RE = re.compile(r"\{([^}]*)\}\s*$")
TRACKS = {"M": "physics", "C": "compute", "A": "astronomy", "I": "instrument", "B": "boinc"}


def _track_for(mid: str) -> str:
    prefix = re.match(r"[A-Z]+", mid)
    return TRACKS.get(prefix.group()[0], "misc") if prefix else "misc"


def _parse_tags(body: str) -> tuple[str, dict]:
    """Pull a trailing ``{venue=…; url=…; doi=…}`` block off a milestone line."""
    m = _TAG_RE.search(body)
    if not m:
        return body, {}
    tags: dict = {}
    for pair in re.split(r"[;,]", m.group(1)):
        if "=" in pair:
            k, v = pair.split("=", 1)
            k, v = k.strip().lower(), v.strip()
            if k in ("venue", "url", "doi") and v:
                tags[k] = v
    return body[: m.start()].strip(), tags


def parse_milestones(text: str) -> list[dict]:
    """Parse MILESTONES.md checklist lines into milestone dicts.

    ``[x]`` → verified, ``[~]``/``[-]`` → null (failed calibration, kept on the
    books), ``[ ]`` → pending. The first pending milestone is promoted to
    ``open`` — the experiment running now / next on the bench. Each milestone
    carries its ``track`` (from the id prefix) and any ``venue``/``url``/``doi``
    that links a verified contribution to its official record.
    """
    out: list[dict] = []
    first_pending = True
    for line in text.splitlines():
        m = _MILESTONE_RE.match(line)
        if not m:
            continue
        box = m.group("box").lower()
        body, tags = _parse_tags(m.group("body").strip())
        title = re.split(r"[.:]", body, 1)[0].strip()

        if box == "x":
            status = "verified"
        elif box in ("~", "-"):
            status = "null"
        else:
            status = "pending"

        mid = m.group("id")
        ms = {"id": mid, "title": title, "status": status, "track": _track_for(mid)}

        if status == "verified":
            # Lift the "(done <date> — <result>)" parenthetical. Prose can carry
            # its own parens (e.g. "M(T)"), so prefer the one that says "done".
            parens = re.findall(r"\(([^)]*)\)", body)
            done = next((p for p in parens if p.strip().lower().startswith("done")), None)
            chosen = done if done is not None else (parens[-1] if parens else None)
            if chosen:
                result = re.sub(r"^done\s+\S+\s*[—\-]\s*", "", chosen).strip()
                if result:
                    ms["result"] = result

        ms.update(tags)   # venue / url / doi when present

        if status == "pending" and first_pending:
            ms["status"] = "open"
            first_pending = False

        out.append(ms)
    return out


def cpu_temp_c() -> float | None:
    """Best-effort CPU temperature from Linux thermal zones (no extra deps)."""
    base = Path("/sys/class/thermal")
    if not base.exists():
        return None
    zones = sorted(base.glob("thermal_zone*"))
    # Prefer a zone that names a CPU/package sensor.
    for zone in zones:
        try:
            kind = (zone / "type").read_text().strip().lower()
        except OSError:
            continue
        if any(tag in kind for tag in ("cpu", "x86_pkg", "k10temp", "tctl", "coretemp")):
            try:
                return round(int((zone / "temp").read_text().strip()) / 1000.0, 1)
            except (OSError, ValueError):
                pass
    # Fall back to the first readable zone.
    for zone in zones:
        try:
            return round(int((zone / "temp").read_text().strip()) / 1000.0, 1)
        except (OSError, ValueError):
            continue
    return None


def run_cadence() -> tuple[str | None, int]:
    """``(last_run ISO, total runs)`` from daily report JSONs.

    Each ``YYYY-MM-DD.json`` report (in the repo's ``reports/`` and in
    ``~/.lab``) counts as one patient overnight run.
    """
    dates: set[str] = set()
    for directory in (REPORTS_DIR, LAB_HOME):
        if directory.exists():
            for p in directory.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"):
                dates.add(p.stem)
    if not dates:
        return None, 0
    last = max(dates)
    last_iso = datetime.fromisoformat(last).replace(tzinfo=timezone.utc).isoformat()
    return last_iso, len(dates)


def _git_sha() -> str | None:
    """Short commit SHA of the code that produced this snapshot (best-effort)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _env() -> str:
    """A compact, sanitized environment string for provenance (no host/user)."""
    import platform
    parts = ["python " + platform.python_version(), platform.system().lower()]
    try:
        from importlib.metadata import version
        parts.append("torch " + version("torch"))
    except Exception:  # noqa: BLE001 — torch may not be installed; provenance is best-effort
        pass
    return " · ".join(parts)


def build_snapshot(milestones, last_run, runs, temp_c) -> dict:
    """Assemble the sanitized snapshot the /windowsill/ page consumes."""
    return {
        "source": "windowsill-lab",
        "milestones": milestones,
        "total": len(milestones),
        "last_run": last_run,
        "runs": runs,
        "temp_c": temp_c,
        "updated": datetime.now(timezone.utc).isoformat(),
        # Receipts over vibes: every snapshot says which code + environment made
        # it, so a result can be traced back and re-run. No host or user data.
        "provenance": {"code_sha": _git_sha(), "env": _env()},
    }


def collect() -> dict:
    """Build the snapshot from the repo's milestone ladder + local run history."""
    text = MILESTONES_MD.read_text() if MILESTONES_MD.exists() else ""
    last_run, runs = run_cadence()
    return build_snapshot(parse_milestones(text), last_run, runs, cpu_temp_c())


def _push_gist(gist_id: str, content: str) -> None:
    """Update the public gist's pot.json via the GitHub CLI (best-effort)."""
    payload = json.dumps({"files": {"pot.json": {"content": content}}})
    subprocess.run(
        ["gh", "api", "-X", "PATCH", f"gists/{gist_id}", "--input", "-"],
        input=payload, text=True, check=True, capture_output=True,
    )


def publish(gist_id: str | None = None, quiet: bool = False) -> Path:
    """Write ~/.lab/pot.json and (if a gist id is given) push it.

    ``gist_id`` falls back to the ``POT_GIST_ID`` environment variable.
    """
    snap = collect()
    content = json.dumps(snap, indent=2)
    LAB_HOME.mkdir(parents=True, exist_ok=True)
    out = LAB_HOME / "pot.json"
    out.write_text(content)

    gist_id = gist_id or os.environ.get("POT_GIST_ID")
    if gist_id:
        try:
            _push_gist(gist_id, content)
            if not quiet:
                print(f"  ✓ pushed to gist {gist_id}")
        except FileNotFoundError:
            if not quiet:
                print("  (gist push skipped: GitHub CLI `gh` not found)")
        except subprocess.CalledProcessError as e:
            if not quiet:
                print(f"  (gist push failed: {e.stderr.strip() if e.stderr else e})")
    elif not quiet:
        print("  (no gist configured — set POT_GIST_ID or pass --gist <id> to push)")
    return out
