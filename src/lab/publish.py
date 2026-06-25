"""Publish a sanitized windowsill snapshot — the food for the windowsill page.

The windowsill is the lab's calm, public face. Each verified milestone on the
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
import math
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
# v3: pot.json gains a newest-first ``reports`` array (every run, incl. honest
# nulls) so the page can deep-link each node on the seedling stem; the single
# ``latest_report`` stays as ``reports[0]`` for back-compat.
SCHEMA_VERSION = 3

# Onsager's exact 2D Ising critical temperature, 1944 — the lab's calibration target.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.2692

# A rendered "full report" the page deep-links. The nightly commits
# reports/latest.html every run, so this always resolves to the newest one
# (htmlpreview renders committed HTML straight from GitHub — no extra hosting).
# Prefix for the *permanent* per-run reports: each run's deep-link is
# ``REPORT_URL_BASE + "<date>-<slug>.html"``. htmlpreview renders committed HTML
# straight from GitHub raw — so a per-run link only resolves once the nightly
# has committed + pushed that file (same constraint latest.html already has).
REPORT_URL_BASE = (
    "https://htmlpreview.github.io/?"
    "https://raw.githubusercontent.com/benskamps/windowsill-lab/main/reports/"
)
REPORT_URL = REPORT_URL_BASE + "latest.html"

# The committed archive index — the honest every-run ledger page. A sibling of
# REPORT_URL (htmlpreview over the committed reports/index.html), so the
# windowsill page's "see all N runs" link resolves with no extra hosting.
ARCHIVE_URL = REPORT_URL_BASE + "index.html"

# A checklist line: "- [x] **M01** — 2D Ising verification. ..."
# IDs are letter-prefixed by track: M=physics, C=compute/number-theory,
# A=astronomy, I=instrument, B=BOINC. An optional trailing "{venue=…; url=…;
# doi=…}" tag links a contribution to its official record.
_MILESTONE_RE = re.compile(
    r"^\s*-\s*\[(?P<box>[ xX~\->])\]\s*\*\*(?P<id>[A-Z]{1,3}\d+)\*\*\s*[—\-]\s*(?P<body>.*\S)\s*$"
)
_TAG_RE = re.compile(r"\{([^}]*)\}\s*$")
TRACKS = {"M": "physics", "C": "compute", "A": "astronomy", "I": "instrument", "B": "boinc"}

# Growth forms — the feed contract's render-strategy hint (see BACKLOG.md §"Growth
# forms"). The hard constraint is *homogeneous*: same clay pot, same palette, same
# light-follows-your-clock soul, same pot.json contract — only the *form* of the
# green thing changes, so the windowsill page can make the *kind* of science
# legible at a glance (a physics convergence sweep ≠ a long astronomy time-series
# ≠ an instrument calibration ≠ a distributed-compute contribution) while a wall
# of windowsills still reads as one garden. The form is *derived* from a
# milestone's track — not a new field a milestone has to set — so existing
# MILESTONES.md lines gain it for free and the producer stays the single source
# of truth. ``misc`` (and any unknown track) falls back to the homogeneous
# seedling, so the page degrades cleanly.
GROWTH_FORMS = {
    "physics": "fern",        # the core convergence ladder — fronds unfurl rung by rung
    "compute": "vine",        # climbing integer sequences (e.g. OEIS extensions)
    "astronomy": "creeper",   # a long time-series that trails across the seasons
    "instrument": "succulent",  # a calibration: compact, slow, precise
    "boinc": "moss",          # a distributed, mat-forming (BOINC-style) contribution
    "misc": "sprout",         # the homogeneous default seedling
}
DEFAULT_GROWTH_FORM = "sprout"


def _track_for(mid: str) -> str:
    prefix = re.match(r"[A-Z]+", mid)
    return TRACKS.get(prefix.group()[0], "misc") if prefix else "misc"


def growth_form_for(track: str | None) -> str:
    """The growth form derived from a milestone's ``track`` — the feed contract's
    render-strategy hint. An unknown/absent track falls back to the homogeneous
    default seedling (``sprout``), so the windowsill page never has to special-case
    a form it doesn't recognise. The single source-of-truth rule both the producer
    (``parse_milestones``) and any consumer should use, so the two never drift."""
    return GROWTH_FORMS.get(track or "misc", DEFAULT_GROWTH_FORM)


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
    milestone carries its ``track`` (from the id prefix), its ``growth_form``
    (derived from the track — the feed contract's render-strategy hint), an
    optional ``progress`` (0–1), and any ``venue``/``url``/``doi`` linking a
    verified contribution to its official record.
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
        track = _track_for(mid)
        ms = {"id": mid, "title": title, "status": status, "track": track,
              "growth_form": growth_form_for(track)}

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
    """Best-effort CPU temperature — sets the windowsill's season.

    Linux: ``/sys/class/thermal``. Windows: LibreHardwareMonitor's web JSON at
    localhost:8085 (enable it: Options > Web Server > Run). ``None`` (the page
    falls back to spring) when neither is available.
    """
    if os.name == "nt":
        return _cpu_temp_windows()
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


def _cpu_temp_windows() -> float | None:
    """CPU temperature from a local LibreHardwareMonitor web server (port 8085).

    Walks LHM's ``data.json`` sensor tree for a CPU temperature, preferring a
    package/Tctl/Tdie reading over an individual core. Best-effort: returns
    ``None`` if LHM's web server isn't running.
    """
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8085/data.json", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 — LHM may be off; the season just stays calm
        return None

    best: list = []  # [temp, preferred] of the chosen sensor

    def walk(node: dict, in_cpu: bool) -> None:
        low = str(node.get("Text", "")).lower()
        here_cpu = in_cpu or any(t in low for t in ("cpu", "ryzen", "core i", "intel", "amd"))
        value = str(node.get("Value", ""))
        if here_cpu and "°C" in value:
            try:
                t = float(value.replace("°C", "").replace(",", ".").strip())
            except ValueError:
                t = None
            if t is not None and -20.0 < t < 130.0:
                pref = any(k in low for k in ("package", "tctl", "tdie", "cpu"))
                if not best or (pref and not best[1]):
                    best[:] = [t, pref]
        for child in node.get("Children", []) or []:
            walk(child, here_cpu)

    try:
        walk(data, False)
    except Exception:  # noqa: BLE001
        return None
    return round(best[0], 1) if best else None


def today_local() -> str:
    """The local calendar date as ``YYYY-MM-DD`` — the operator's "tonight".

    Reports are dated in *local* time, not UTC. The windowsill is a personal
    instrument; "last night I ran ..." should match the day on the human's wall
    clock, so an evening run isn't stamped tomorrow. (The 03:00 nightly is
    unaffected — at 3 a.m. the local and UTC dates already agree for any sane
    timezone; the divergence only bit off-hours manual runs.)
    """
    return datetime.now().date().isoformat()


# A report JSON is named either ``<date>.json`` (legacy bare-date dump) or
# ``<date>-<slug>.json`` (the permanent per-run file). Both start with the date.
_DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"


def _report_jsons() -> list[Path]:
    """Every daily report JSON on record, across the repo and ``~/.lab``.

    Matches both the legacy ``<date>.json`` dumps and the permanent
    ``<date>-<slug>.json`` files (so run cadence keeps counting after the
    permanence refactor). ``<date>.html``/``-<slug>.html`` are excluded.
    """
    seen: set = set()
    paths: list[Path] = []
    for directory in (REPORTS_DIR, LAB_HOME):
        if not directory.exists():
            continue
        for p in directory.glob(f"{_DATE_GLOB}*.json"):
            if p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def _date_of(path: Path) -> str:
    """The leading ``YYYY-MM-DD`` of a report filename (handles ``-slug`` tails)."""
    return path.stem[:10]


def run_cadence() -> tuple[str | None, int]:
    """``(last_run ISO, total runs)`` from daily report JSONs.

    Each ``YYYY-MM-DD.json`` report (in the repo's ``reports/`` and in
    ``~/.lab``) counts as one patient overnight run. "Last run" is the report
    written most recently — keyed off file mtime, not the highest date string —
    so a stale future-dated artifact (or a backfilled date) can't masquerade as
    the latest. The leading date stem breaks an mtime tie, so a fresh git clone
    (which resets every mtime identically) still orders stably. ``total`` is the
    number of *distinct* days observed.
    """
    paths = _report_jsons()
    if not paths:
        return None, 0
    # Order by (mtime, date_stem): the leading date breaks an mtime tie so a
    # fresh git clone — which resets every mtime to the same value — still picks
    # the run with the latest date, not an arbitrary one (mirrors scan_runs).
    last_path = max(paths, key=lambda p: (p.stat().st_mtime, _date_of(p)))
    last_iso = datetime.fromtimestamp(last_path.stat().st_mtime, timezone.utc).isoformat()
    # Distinct *days*, not files: a permanent ``<date>-<slug>.json`` and a legacy
    # ``<date>.json`` for the same day count once.
    total = len({_date_of(p) for p in paths})
    return last_iso, total


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


def _newest_report() -> dict | None:
    """The newest daily report JSON (repo ``reports/`` or ``~/.lab``).

    "Newest" = most recently written (mtime), not the highest date string. The
    page shows whatever ran last; a leftover future-dated file must not win. The
    leading date stem breaks an mtime tie so a fresh clone (all mtimes equal)
    still picks the latest-dated run rather than an arbitrary one.
    """
    paths = _report_jsons()
    if not paths:
        return None
    # (mtime, date_stem): the date breaks an mtime tie so a fresh clone (all
    # mtimes equal) still picks the latest-dated run, not an arbitrary one.
    newest = max(paths, key=lambda p: (p.stat().st_mtime, _date_of(p)))
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data["_date"] = _date_of(newest)
    return data


def latest_report() -> dict | None:
    """A tiny summary of the most recent run for the windowsill page to show
    under the seedling — immediate attribution, no heavy payload. ``None`` until
    a run has happened (the page just omits the line)."""
    rep = _newest_report()
    if not rep:
        return None
    # Reuse the guarded χ-peak helper — a scalar-T report (e.g. M09's fixed-T
    # L-family) has no locatable peak and must not crash on ``len(T)``.
    peak_t = _peak_t(rep)
    wall = rep.get("wall_seconds")
    headline = rep.get("headline")
    if not headline and peak_t is not None:
        headline = f"χ peaked at T≈{peak_t:.3f} vs Onsager {ONSAGER_TC:.4f}"
        if wall:
            headline += f" · {wall:.0f}s on GPU"
    return {
        "date": rep.get("_date"),
        "headline": headline,
        "peak_t": peak_t,
        "onsager_tc": round(ONSAGER_TC, 4),
        "wall_s": wall,
        "url": REPORT_URL,
    }


def _slug_for(report: dict) -> str:
    """The permanent-report slug for a run — the single source-of-truth rule.

    ``{"experiment": "M02-finite-size-scaling"}`` → ``"m02"`` (the milestone id,
    lowercased). A legacy M01 dump carries no ``experiment`` field but has the
    Ising ``T``+``chi`` arrays → ``"m01"``. Anything else → ``"run"``.

    ``render._slug_for`` is an alias of this function so the two never drift.
    """
    exp = report.get("experiment")
    if exp:
        m = re.match(r"[A-Z]{1,3}\d+", exp)
        if m:
            return m.group(0).lower()
    if report.get("T") and report.get("chi"):
        return "m01"
    return "run"


def _milestone_for(report: dict) -> str | None:
    """The milestone id (``M01``/``M02``/…) inferred from a report, or ``None``."""
    slug = _slug_for(report)
    return slug.upper() if slug != "run" else None


def _peak_t(report: dict) -> float | None:
    """T at max(χ) for an Ising χ-sweep, else ``None`` (e.g. M02/M03/M09 reports).

    Guards against reports whose ``T`` is *not* a parallel-to-χ array: M09, for
    instance, carries a **scalar** ``T`` (a fixed-temperature L-family sweep) and a
    per-L ``chi`` list, so ``len(T)`` would blow up. Only a list/tuple ``T`` the
    same length as a list/tuple ``chi`` is a locatable χ-sweep.
    """
    T, chi = report.get("T"), report.get("chi")
    if (isinstance(T, (list, tuple)) and isinstance(chi, (list, tuple))
            and T and len(T) == len(chi)):
        return round(T[max(range(len(chi)), key=lambda i: chi[i])], 3)
    return None


def _run_record(path: Path, data: dict) -> dict:
    """A compact, sanitized record of one run for the ``reports`` array.

    ``status`` is the run's honest verdict. This is the FALLBACK record (used when
    the verdict-graded ``archive.run_ledger()`` raises), so it must never claim a
    verification it didn't perform:

    * an explicit failed-calibration marker (``"status": "null"`` in the JSON) →
      ``"null"`` — a folded grey leaf on the windowsill;
    * anything else → ``"unscored"`` — a plain node, NOT ``"verified"``. A bare
      structural record can't know a run passed, and a FAILED run must never ride
      out as a green leaf. Only the archive's check-graded ledger may emit
      ``"verified"`` (it re-derives the headline number through the checks
      registry); this fallback claims nothing it didn't grade.

    ``url`` deep-links the committed permanent report when the file lives in the
    repo ``reports/`` tree; otherwise it points at the local cached path so the
    record is still traceable before a backfill.
    """
    date = _date_of(path)
    slug = _slug_for(data)
    # Always the committed permanent deep-link: REPORT_URL_BASE + "<date>-<slug>.html".
    # It resolves through htmlpreview once the nightly commits + pushes that file
    # — the same "only after a push" constraint latest.html already carries. A
    # local ~/.lab copy maps to the same canonical URL it'll have once backfilled,
    # so the record stays an http link (page link-guard + schema both want http).
    url = REPORT_URL_BASE + f"{date}-{slug}.html"
    status = "null" if str(data.get("status", "")).lower() == "null" else "unscored"
    return {
        "date": date,
        "milestone": _milestone_for(data),
        "experiment": data.get("experiment"),
        "headline": data.get("headline"),
        "peak_t": _peak_t(data),
        "wall_s": data.get("wall_seconds"),
        "url": url,
        "code_sha": data.get("code_sha"),
        "status": status,
    }


def discover_runs() -> list[dict]:
    """Every run on record across the repo ``reports/`` and ``~/.lab``.

    Walks both trees, parses each report JSON into a compact ``_run_record``,
    dedupes by ``(date, slug)`` with the committed repo copy winning over the
    local ``~/.lab`` cache, and sorts newest-first by file mtime. This is the
    list that becomes ``pot.json``'s ``reports`` array, so the windowsill page
    can deep-link every node on the seedling stem — including the honest nulls.
    """
    # Per (date, slug): prefer the repo copy; among same-priority files keep the
    # most recently written. Each entry is (mtime, record, is_repo).
    by_key: dict[tuple[str, str], tuple[float, dict, bool]] = {}
    for directory in (REPORTS_DIR, LAB_HOME):
        if not directory.exists():
            continue
        is_repo = directory.resolve() == REPORTS_DIR.resolve()
        for p in directory.glob(f"{_DATE_GLOB}*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            key = (_date_of(p), _slug_for(data))
            mtime = p.stat().st_mtime
            cur = by_key.get(key)
            if cur is None:
                by_key[key] = (mtime, _run_record(p, data), is_repo)
                continue
            cur_mtime, _, cur_repo = cur
            # Repo always beats ~/.lab; within the same priority, newest mtime wins.
            if (is_repo and not cur_repo) or (is_repo == cur_repo and mtime > cur_mtime):
                by_key[key] = (mtime, _run_record(p, data), is_repo)
    records = sorted(by_key.values(), key=lambda v: v[0], reverse=True)
    return [rec for _, rec, _ in records]


def build_snapshot(milestones, last_run, runs, temp_c, report=None,
                   reports=None, reports_ledger=None) -> dict:
    """Assemble the sanitized snapshot the /windowsill/ page consumes.

    ``reports_ledger`` (new) is the archive's sanitized every-run ledger
    (``archive.run_ledger()`` — rows of ``{date, milestone, verdict, headline,
    href}``). ``reports`` is the legacy compact run-record list. Either fills
    the ``reports`` array; ``reports_ledger`` wins when both are given. When a
    ``reports`` array is present, ``latest_report`` is its first (headline) row;
    otherwise the legacy single ``report`` argument fills it — so old callers and
    old consumers degrade cleanly. ``archive_url`` deep-links the index page.
    """
    rows = reports_ledger if reports_ledger is not None else reports
    snap = {
        "schema_version": SCHEMA_VERSION,
        "source": "windowsill-lab",
        "milestones": milestones,
        "total": len(milestones),
        "last_run": last_run,
        "runs": runs,
        "temp_c": temp_c,
        "latest_report": (rows[0] if rows else report),
        "archive_url": ARCHIVE_URL,
        "updated": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance(),
    }
    if rows is not None:
        snap["reports"] = rows
    return snap


def collect() -> dict:
    """Build the snapshot from the repo's milestone ladder + local run history.

    The ``reports`` array is the archive's verdict-graded ledger
    (``archive.run_ledger()`` — each run carries an honest verified/null/unscored
    verdict re-derived through the checks registry). Built best-effort, with the
    same guard the gist push uses: if the archive layer raises, fall back to the
    structural ``discover_runs()`` records so the feed is never broken by it.
    """
    text = MILESTONES_MD.read_text(encoding="utf-8") if MILESTONES_MD.exists() else ""
    last_run, runs = run_cadence()
    try:
        from . import archive
        ledger = archive.run_ledger()
    except Exception:  # noqa: BLE001 — provenance is never allowed to break the feed
        ledger = None
    if ledger is not None:
        return build_snapshot(
            parse_milestones(text), last_run, runs, cpu_temp_c(),
            reports_ledger=ledger,
        )
    return build_snapshot(
        parse_milestones(text), last_run, runs, cpu_temp_c(),
        reports=discover_runs(),
    )


def backfill(dry_run: bool = False) -> list[Path]:
    """Render/copy every ``~/.lab`` dated report into the repo ``reports/`` tree.

    Idempotent: a run already present as ``reports/<date>-<slug>.json`` is
    skipped. The JSON sidecar is always *copied* (never moved — the ``~/.lab``
    history is preserved); the HTML is re-rendered from the existing JSON when
    matplotlib + the renderer are importable, and quietly skipped otherwise so a
    headless/torch-free box still backfills the machine-readable feed. Returns
    the paths written (the planned paths on ``dry_run``); a human runs this once
    via ``lab backfill`` after the refactor lands. Never runs a simulation.
    """
    written: list[Path] = []
    if not LAB_HOME.exists():
        return written

    # What's already committed, so we skip it (idempotency).
    existing = {p.name for p in REPORTS_DIR.glob(f"{_DATE_GLOB}*.json")} if REPORTS_DIR.exists() else set()

    for src in sorted(LAB_HOME.glob(f"{_DATE_GLOB}*.json")):
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        date = _date_of(src)
        slug = _slug_for(data)
        json_name = f"{date}-{slug}.json"
        if json_name in existing:
            continue   # already backfilled — idempotent
        json_dest = REPORTS_DIR / json_name
        html_dest = REPORTS_DIR / f"{date}-{slug}.html"
        if dry_run:
            written.append(json_dest)
            continue

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        # Copy the machine-readable report verbatim (never move — keep ~/.lab).
        json_dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(json_dest)

        # Re-render the HTML from the EXISTING JSON. Lazy import so the JSON
        # path works even where matplotlib/torch aren't installed.
        src_html = src.with_suffix(".html")
        try:
            if src_html.exists():
                html_dest.write_text(src_html.read_text(encoding="utf-8"), encoding="utf-8")
                written.append(html_dest)
            else:
                exp = str(data.get("experiment", ""))
                renderer = None
                if exp.startswith("M02"):
                    renderer = "render_fss"
                elif exp.startswith("M03"):
                    renderer = "render_m03"
                if renderer is not None:
                    from . import render as render_mod  # noqa: PLC0415 — heavy, lazy
                    getattr(render_mod, renderer)(data, date=date)
                    if html_dest.exists():
                        written.append(html_dest)
        except Exception:  # noqa: BLE001 — HTML is best-effort; JSON already landed
            pass
        existing.add(json_name)
    return written


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
    POT_JSON.write_text(content, encoding="utf-8")  # canonical, committed live feed
    LAB_HOME.mkdir(parents=True, exist_ok=True)
    out = LAB_HOME / "pot.json"
    out.write_text(content, encoding="utf-8")

    # Refresh the committed archive index (reports/index.html) so the every-run
    # ledger page tracks the feed. Best-effort — same guard as the gist push;
    # the nightly's `git add -A reports/` commits it.
    try:
        from . import archive
        archive.write_index()
    except Exception:  # noqa: BLE001 — the index is never allowed to break publish
        pass

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
