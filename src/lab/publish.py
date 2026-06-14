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
POT_JSON = REPO_ROOT / "pot.json"   # committed live feed the windowsill reads

# Bump when the snapshot contract changes in a way consumers must adapt to. The
# /windowsill/ page and schema/pot.schema.json track this number.
SCHEMA_VERSION = 1

# A checklist line: "- [x] **M01** — 2D Ising verification. ..."
# IDs are letter-prefixed by track: M=physics, C=compute/number-theory,
# A=astronomy, I=instrument, B=BOINC. An optional trailing "{venue=…; url=…;
# doi=…}" tag links a contribution to its official record.
_MILESTONE_RE = re.compile(
    r"^\s*-\s*\[(?P<box>[ xX~\->])\]\s*\*\*(?P<id>[A-Z]{1,3}\d+)\*\*\s*[—\-]\s*(?P<body>.*\S)\s*$"
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
            if k in ("venue", "url", "doi", "progress") and v:
                tags[k] = v
    return body[: m.start()].strip(), tags


def parse_milestones(text: str) -> list[dict]:
    """Parse MILESTONES.md checklist lines into milestone dicts.

    ``[x]`` → verified, ``[~]``/``[-]`` → null (failed calibration, kept on the
    books), ``[>]`` → the explicitly-open experiment (any track), ``[ ]`` →
    pending. If nothing is marked ``[>]``, the first pending milestone is
    promoted to ``open`` — the experiment running now / next on the bench. Each
    milestone carries its ``track`` (from the id prefix), an optional
    ``progress`` (0–1), and any ``venue``/``url``/``doi`` linking a verified
    contribution to its official record.
    """
    out: list[dict] = []
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
        elif box == ">":
            status = "open"
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

        ms.update(tags)   # venue / url / doi / progress when present
        if "progress" in ms:
            try:
                ms["progress"] = max(0.0, min(1.0, float(ms["progress"])))
            except (TypeError, ValueError):
                del ms["progress"]

        out.append(ms)

    # The lab runs one experiment at a time. If a milestone is explicitly marked
    # open (any track), respect it; otherwise the first pending is the open bench.
    if not any(m["status"] == "open" for m in out):
        nxt = next((m for m in out if m["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "open"
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


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _git_sha() -> str | None:
    """Short commit SHA, with ``-dirty`` only if *code* has uncommitted changes.

    Scoped to ``src/`` + ``pyproject.toml`` on purpose: a fresh untracked run
    report or a rewritten ``pot.json`` is data churn, not a code change, and
    shouldn't make every published number look like it came from a dirty tree.
    """
    sha = _git("rev-parse", "--short", "HEAD")
    if not sha:
        return None
    dirty = _git("status", "--porcelain", "--", "src", "pyproject.toml")
    return sha + "-dirty" if dirty else sha


def _deps() -> dict:
    """Versions of the scientific packages a result depends on (best-effort)."""
    out: dict = {}
    try:
        from importlib.metadata import PackageNotFoundError, version
        for pkg in ("torch", "numpy", "matplotlib"):
            try:
                out[pkg] = version(pkg)
            except PackageNotFoundError:
                pass
    except Exception:  # noqa: BLE001 — provenance is never allowed to break a run
        pass
    return out


def _env() -> str:
    """A compact, sanitized environment string for provenance (no host/user)."""
    import platform
    return f"python {platform.python_version()} · {platform.system().lower()}"


def provenance() -> dict:
    """Receipts over vibes: what code + environment produced a result, so it can
    be traced back and re-run. No host or user data — safe to publish."""
    return {"code_sha": _git_sha(), "env": _env(), "deps": _deps()}


def build_snapshot(milestones, last_run, runs, temp_c) -> dict:
    """Assemble the sanitized snapshot the /windowsill/ page consumes."""
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "windowsill-lab",
        "milestones": milestones,
        "total": len(milestones),
        "last_run": last_run,
        "runs": runs,
        "temp_c": temp_c,
        "updated": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance(),
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
    """Write the committed ``pot.json`` (the live feed) + a ~/.lab copy.

    The repo's ``pot.json`` is the canonical feed: the /windowsill/ page reads it
    straight from GitHub raw, served through the site's edge cache — no gist or
    secret required. A nightly run commits + pushes it. ``gist_id`` (or the
    ``POT_GIST_ID`` env var) remains an optional legacy push target.
    """
    snap = collect()
    content = json.dumps(snap, indent=2) + "\n"
    POT_JSON.write_text(content)          # canonical, committed live feed
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
        print("  (no gist configured — pot.json is committed to the repo instead)")
    return POT_JSON
