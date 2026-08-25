"""Publish a sanitized windowsill snapshot — the food for the windowsill page.

The windowsill is the lab's calm, public face. Each verified milestone on the
ladder becomes a node on the seedling's stem at
https://www.brokenbranch.dev/windowsill/ ; a failed calibration is a folded
grey leaf (an honest null). This module builds a small, sanitized ``pot.json``
(milestones, run cadence, CPU heat — no private data, no project internals) and
optionally pushes it to a legacy public gist.  The canonical page and its
``snapshot.json`` link both read this repository's raw ``pot.json`` directly.

Kept deliberately import-light (standard library only) so the pure functions
``parse_milestones`` / ``build_snapshot`` are unit-tested without pulling in
torch or matplotlib.
"""
from __future__ import annotations
from .hw import hw

import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import origin
from .atomic import atomic_write_text
from .stories import STORIES   # durable plain-language story layer (stdlib-only dict)
from .curriculum import RUNNERS
from .m01_quality import assess_m01_quality

# Mirror render.LAB_HOME without importing it (render pulls matplotlib).
from .labhome import LAB_HOME
REPO_ROOT = Path(__file__).resolve().parents[2]
MILESTONES_MD = REPO_ROOT / "MILESTONES.md"
REPORTS_DIR = REPO_ROOT / "reports"
RECEIPTS_DIR = REPORTS_DIR / "receipts"
POT_JSON = REPO_ROOT / "pot.json"   # committed live feed the windowsill reads

# Bump when the snapshot contract changes in a way consumers must adapt to. The
# /windowsill/ page and schema/pot.schema.json track this number.
# v3: pot.json gains a newest-first ``reports`` array (every run, incl. honest
# nulls) so the page can deep-link each node on the seedling stem; the single
# ``latest_report`` stays as ``reports[0]`` for back-compat. v4 distinguishes
# machine-checked ``review`` milestones from human-promoted ``verified`` ones
# and declares whether each curriculum step has a runnable implementation.
# v5: consecutive same-milestone same-verdict runs collapse to the newest row
# + group_count/group_first_date; the archive index keeps every run.
SCHEMA_VERSION = 5

# Onsager's exact 2D Ising critical temperature, 1944 — the lab's calibration target.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.2692

# A rendered "full report" the page deep-links. The nightly commits
# reports/latest.html every run, so this always resolves to the newest one
# (htmlpreview renders committed HTML straight from GitHub — no extra hosting).
# Prefix for the *permanent* per-run reports: each run's deep-link is
# ``REPORT_URL_BASE + "<date>-<slug>.html"``. htmlpreview renders committed HTML
# straight from GitHub raw — so a per-run link only resolves once the nightly
# has committed + pushed that file (same constraint latest.html already has).
def report_url_base() -> str | None:
    """htmlpreview prefix for this repo's committed reports, or None.

    Derived from the checkout's own git remote (see :mod:`lab.origin`), never
    hardcoded: a fork that published links built from the upstream author's slug
    would show its own numbers above somebody else's evidence, which is the most
    damaging failure available to a lab whose whole claim is checkability.
    """
    return origin.join(origin.preview_base(), "reports/")


def report_url() -> str | None:
    return origin.join(report_url_base(), "latest.html")

def archive_url() -> str | None:
    """The committed every-run ledger page — a sibling of :func:`report_url`,
    so the windowsill page's "see all N runs" link resolves with no extra
    hosting."""
    return origin.join(report_url_base(), "index.html")


def receipt_url_base() -> str | None:
    return origin.join(origin.raw_base(), "reports/receipts/")

# A checklist line: "- [x] **M01** — 2D Ising verification. ..."
# IDs are letter-prefixed by track: M=physics, C=compute/number-theory,
# A=astronomy, I=instrument, B=BOINC. An optional trailing "{venue=…; url=…;
# doi=…}" tag links a contribution to its official record.
_MILESTONE_RE = re.compile(
    r"^\s*-\s*\[(?P<box>[ xX~?\->])\]\s*\*\*(?P<id>[A-Z]{1,3}\d+)\*\*\s*[—\-]\s*(?P<body>.*\S)\s*$"
)
_TAG_RE = re.compile(r"\{([^}]*)\}\s*$")
TRACKS = {"M": "physics", "K": "coherence", "C": "compute", "A": "astronomy",
          "I": "instrument", "B": "boinc"}

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
    # Coherence is a convergence ladder too — same shape of climb, same kind of
    # exactly-known rung — so it deliberately REUSES the fern rather than shipping
    # a seventh plant nobody asked for. A bespoke coherence form is a follow-up
    # (BACKLOG §"Growth forms"), not a blocker on the track's first rung.
    "coherence": "fern",
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


def _parenthetical_groups(text: str) -> list[str]:
    """Return balanced top-level parenthetical contents.

    Milestone receipts routinely contain nested notation such as ``tanh(1/T)``
    and ``O(3)``. A regex ending at the first ``)`` silently truncated those
    public technical results, so parse the tiny balanced structure directly.
    """

    groups: list[str] = []
    depth = 0
    start: int | None = None
    for i, char in enumerate(text):
        if char == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif char == ")" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(text[start:i])
                start = None
    return groups


_BOLD_LEAD_RE = re.compile(r"^\*\*(?P<bold>.+?)\*\*")


def _title_for(body: str) -> str:
    """The milestone's short title, from the head of its prose.

    Normally the title is the first clause — everything up to the first ``.`` or
    ``:``. But an author who wraps the whole title in ``**bold**`` has already
    marked where it ends, and that span may legitimately contain a colon or a
    question mark: K03's ``**Daido vs Hong: is the exponent asymmetric?**``
    truncated to ``**Daido vs Hong`` under the naive split, dangling asterisks
    and all. So a bold span is honoured as the title when it spans a whole
    clause, and otherwise treated as mere emphasis and split through as before.
    """
    lead = _BOLD_LEAD_RE.match(body)
    if lead:
        bold = lead.group("bold").strip()
        # Emphasis on a word or two is not a title; a bold span that runs to a
        # clause boundary is. Require the span to look like a phrase, and to be
        # the reason the naive split would have cut early.
        if len(bold.split()) >= 3 and re.search(r"[.:?]", bold):
            return bold
    return re.split(r"[.:]", body, maxsplit=1)[0].replace("**", "").strip()


def parse_milestones(text: str) -> list[dict]:
    """Parse MILESTONES.md checklist lines into milestone dicts.

    ``[x]`` → verified, ``[~]``/``[-]`` → null (failed calibration, kept on the
    books), ``[?]`` → measured and awaiting human review, ``[>]`` → the
    explicitly-open experiment (any track), ``[ ]`` → pending. If nothing is
    marked ``[>]``, the first pending milestone is promoted to ``open`` — the
    current question on the bench.

    Verified, review AND null milestones all lift their receipt into ``result``.
    Nulls were excluded until 2026-08-11, which quietly broke the page's central
    promise: a grey leaf is a miss the lab kept on purpose *with its numbers*,
    and M12/A03 were reaching the live page with a title and nothing else. A
    kept miss earns the same receipt a kept win does. Each
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
        title = _title_for(body)

        if box == "x":
            status = "verified"
        elif box in ("~", "-"):
            status = "null"
        elif box == "?":
            status = "review"
        elif box == ">":
            status = "open"
        else:
            status = "pending"

        mid = m.group("id")
        track = _track_for(mid)
        ms = {"id": mid, "title": title, "status": status, "track": track,
              "growth_form": growth_form_for(track),
              "runner_available": mid in RUNNERS}

        if status in ("verified", "review", "null"):
            # Lift the balanced "(done/attempted <date> — <result>)" receipt.
            # Technical prose contains nested parentheses, so regex extraction
            # would truncate e.g. M14 at ``tanh(1/T``.
            parens = _parenthetical_groups(body)
            prefixes = ("done",) if status == "verified" else ("attempted", "measured")
            receipt = next(
                (p for p in parens if p.strip().lower().startswith(prefixes)), None
            )
            chosen = receipt if receipt is not None else (parens[-1] if parens else None)
            if chosen:
                # Promotion notes use both ``measured YYYY-MM-DD — result`` and
                # ``measured YYYY-MM-DD; reviewed …``. The old ``\S+`` pattern
                # backtracked into the ISO date and treated its final hyphen as
                # the separator, shipping every promoted result as ``07; ...``.
                # Match the date as a date, then one explicit separator.
                result = re.sub(
                    r"^(?:done|attempted|measured)"
                    r"(?:\s+\d{4}-\d{2}-\d{2})?\s*(?:[;,—-]\s*)?",
                    "", chosen,
                ).strip()
                if result:
                    ms["result"] = result

        # Merge the durable plain-language story layer (src/lab/stories.py) — the
        # public copy, kept beside the curriculum so the page never has to infer
        # plain language from technical prose. Never overwrites the technical
        # ``result``; ``result_plain`` only rides along on verified milestones.
        story = STORIES.get(mid)
        if story:
            for k in ("short_label", "question_plain", "why_it_matters"):
                v = story.get(k)
                if v:
                    ms[k] = v
            if status in ("verified", "review", "null") and story.get("result_plain"):
                ms["result_plain"] = story["result_plain"]

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


#: Substrings that mark a sensor as an actual CPU/package monitor.
_CPU_SENSOR_TAGS = ("cpu", "x86_pkg", "k10temp", "tctl", "coretemp", "zenpower")


def _cpu_temp_linux(thermal_base: Path, hwmon_base: Path) -> float | None:
    """CPU temperature from sysfs, or ``None`` when no sensor NAMES a CPU.

    Two roots, because the kernel splits them: ACPI thermal zones under
    ``/sys/class/thermal`` and hwmon chips under ``/sys/class/hwmon`` —
    AMD's ``k10temp`` (Tctl) lives only in the latter (the 2026-08-12
    two-producer investigation, §axis-two). There is deliberately NO
    first-readable-zone fallback: that fail-open path published loam's WiFi
    adapter to the public feed as "CPU heat". Unknown is ``None``, not a
    guess.
    """
    if thermal_base.exists():
        for zone in sorted(thermal_base.glob("thermal_zone*")):
            try:
                kind = (zone / "type").read_text().strip().lower()
            except OSError:
                continue
            if any(tag in kind for tag in _CPU_SENSOR_TAGS):
                try:
                    return round(
                        int((zone / "temp").read_text().strip()) / 1000.0, 1)
                except (OSError, ValueError):
                    pass
    if hwmon_base.exists():
        for chip in sorted(hwmon_base.glob("hwmon*")):
            try:
                name = (chip / "name").read_text().strip().lower()
            except OSError:
                continue
            if any(tag in name for tag in _CPU_SENSOR_TAGS):
                for sensor in sorted(chip.glob("temp*_input")):
                    try:
                        return round(
                            int(sensor.read_text().strip()) / 1000.0, 1)
                    except (OSError, ValueError):
                        continue
    return None


def cpu_temp_c() -> float | None:
    """Best-effort CPU temperature — sets the windowsill's season.

    Linux: a sysfs sensor that names a CPU (``_cpu_temp_linux``). Windows:
    LibreHardwareMonitor's web JSON at localhost:8085 (enable it: Options >
    Web Server > Run). ``None`` (the page falls back to spring) when no
    CPU-named sensor is available — fail closed, never a mystery zone.
    """
    if os.name == "nt":
        return _cpu_temp_windows()
    return _cpu_temp_linux(Path("/sys/class/thermal"),
                           Path("/sys/class/hwmon"))


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
    """The local calendar date as ``YYYY-MM-DD`` — the running machine's day.

    Reports are dated in *local* time, not UTC. The windowsill is a personal
    instrument; the day a turn is filed under should match the day on the
    human's wall clock, so an evening run isn't stamped tomorrow. A scheduled
    small-hours turn is unaffected — at 03:00 the local and UTC dates already
    agree for any sane timezone; the divergence only bit off-hours manual runs.
    """
    return datetime.now().date().isoformat()


def turn_stamp_now() -> str:
    """The local wall-clock ``HHMM`` of this turn — the receipt name's discriminator.

    Deliberately the SAME clock as ``today_local``: the pair
    ``(date, turn)`` is one machine's own local timestamp for the pass, so a
    date and its turns can never disagree about which day it was. Used only at
    write time by the box that ran the turn; every reader afterwards just parses
    the filename, so the ordering is identical in every clone regardless of the
    reader's timezone (converting a UTC ``generated_at`` on read would not be).
    """
    return datetime.now().strftime("%H%M")


# A report JSON is named either ``<date>.json`` (legacy bare-date dump) or
# ``<date>-<slug>.json`` (the permanent per-run file). Both start with the date.
_DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"


def _report_jsons() -> list[Path]:
    """Every daily report JSON on record, across the repo and ``~/.lab``.

    Matches both the legacy ``<date>.json`` dumps and the permanent
    ``<date>-<slug>.json`` files. ``<date>.html``/``-<slug>.html`` are
    excluded. Feeds ``_newest_report``; run cadence reads the committed
    receipts instead (see ``run_cadence``).
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


def _receipt_date(path: Path) -> str:
    """The ``YYYY-MM-DD`` inside a ``run-<date>-<slug>.json`` receipt name."""
    return path.stem[4:14]


def run_cadence() -> tuple[str | None, int]:
    """``(last_run ISO, total runs)`` from the committed evidence receipts.

    Receipts (``reports/receipts/run-<date>-<slug>.json``) are committed on
    every pass, so every clone derives the *same* cadence. The old source —
    dated report JSONs — was box-local (gitignored in ``reports/``, private in
    ``~/.lab``), so each box published its own numbers: one box computed
    ('2026-07-23', 28) while the committed feed said ('2026-07-30', 24) and the
    shared receipts ledger held 39 distinct days.

    ``last_run`` is the max ``generated_at`` stamp among the receipts of the
    newest date — committed content, so it survives a fresh clone (which resets
    every mtime). Receipts predating ``generated_at`` (or unreadable ones)
    degrade to the bare receipt date, still clone-stable. ``total`` counts
    *distinct DATES*: a day with two milestones is one run day. This is NOT the
    turn count and is deliberately not renamed — ``runs`` is a shipped field
    with existing consumers, and days-tended stays true for as long as anyone
    reads it. ``turn_cadence`` counts the passes themselves.
    """
    if not RECEIPTS_DIR.exists():
        return None, 0
    receipts = sorted(RECEIPTS_DIR.glob(f"run-{_DATE_GLOB}-*.json"))
    if not receipts:
        return None, 0
    dates = {_receipt_date(p) for p in receipts}
    last_date = max(dates)
    stamps = []
    for p in receipts:
        if _receipt_date(p) != last_date:
            continue
        try:
            stamp = json.loads(p.read_text(encoding="utf-8")).get("generated_at")
        except (OSError, ValueError):
            stamp = None
        if isinstance(stamp, str) and stamp:
            stamps.append(stamp)
    last_iso = max(stamps) if stamps else last_date
    return last_iso, len(dates)


# ── The declared cadence ─────────────────────────────────────────────────────
# Expected is DECLARED or it is nothing. The page's freshness, soil-drying and
# "one machine quiet" clause all read this constant and never a rate inferred
# from history — an inferred expectation lets a dying box quietly lower its own
# bar (fewer runs → "cadence" drops → everything looks on time again), and it
# retro-grades months of one-machine history against a two-machine schedule.
#
# ``effective_from`` stays None until BOTH boxes are actually armed (see
# docs/investigations/2026-08-01-portfolio-rotation.md). While it is None the
# feed omits ``expected_interval_h`` entirely, the page falls back to its legacy
# constants, and the footer clause never renders. Flipping this one date is the
# whole arming ceremony.
#
# MERGE GATE (resolved 2026-08-01 by softening): the explainer no longer
# promises a cadence — "one turn at a time, whenever a machine wakes to run" /
# "either of two machines can pick up the next turn" are true while unarmed.
# When the arming ceremony flips ``effective_from``, the cadence copy ("a turn
# every few hours, day and night", "alternating turns") may be restored in the
# same change — the page and this constant must not disagree about whether the
# rotation is real.
CADENCE: dict = {
    "expected_interval_h": 3,
    "machines": ["windows-cuda", "linux-rocm"],
    # Arming ceremony 2026-08-02 (Ben's approval): win task re-registered
    # 00/06/12/18 and linux-rocm filing turns the same day. First full
    # armed day is the 3rd — the declared cadence starts there.
    "effective_from": "2026-08-03",
}


def cadence_is_effective(today: str | None = None) -> bool:
    """True once ``CADENCE['effective_from']`` has arrived (and is declared)."""
    start = CADENCE.get("effective_from")
    if not isinstance(start, str) or not start:
        return False
    return (today or today_local()) >= start


def turn_cadence() -> dict:
    """The ``turns`` object for the feed — one turn = one scheduled pass.

    Counts the committed receipts themselves rather than the distinct dates
    ``run_cadence`` reports, which is only honest because receipts are now
    turn-stamped (``_receipt_filename``): before that, two same-day passes of
    one milestone shared a filename and the second silently destroyed the first.

    ``expected_interval_h`` rides along ONLY while the cadence is declared and
    effective (see ``CADENCE``). ``last_by_machine`` carries every declared
    machine, ``None`` for one that has never filed a turn — a declared-but-silent
    box is a fact worth publishing, not a blank.
    """
    from .archive import machine_of  # one pinned derivation, imported not copied

    turns: dict = {"count": 0, "today": 0}
    if not RECEIPTS_DIR.exists():
        receipts: list[Path] = []
    else:
        receipts = sorted(RECEIPTS_DIR.glob(f"run-{_DATE_GLOB}-*.json"))

    today = today_local()
    last_by_machine: dict[str, str | None] = {
        m: None for m in CADENCE.get("machines", []) if isinstance(m, str)
    }
    for path in receipts:
        turns["count"] += 1
        if _receipt_date(path) == today:
            turns["today"] += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        machine = machine_of(data)
        # Only DECLARED machines get a slot: the object answers "how are the
        # machines we said would take turns doing", and inventing a row for an
        # undeclared box would quietly turn an observation into an expectation.
        if machine not in last_by_machine:
            continue
        stamp = data.get("generated_at")
        if not (isinstance(stamp, str) and stamp):
            continue
        prior = last_by_machine[machine]
        if prior is None or stamp > prior:
            last_by_machine[machine] = stamp

    turns["last_by_machine"] = last_by_machine
    if cadence_is_effective(today):
        turns["expected_interval_h"] = CADENCE["expected_interval_h"]
    return turns


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
    exp = rep.get("experiment")
    is_m01 = (
        str(exp).startswith("M01")
        if exp
        else (
            isinstance(rep.get("T"), (list, tuple))
            and isinstance(rep.get("chi"), (list, tuple))
            and bool(rep.get("T"))
            and len(rep["T"]) == len(rep["chi"])
        )
    )
    if is_m01:
        quality = assess_m01_quality(rep)
        if quality["status"] != "ok" or not headline:
            if peak_t is None:
                headline = f"M01 quality null · {quality['note']}"
            else:
                headline = f"χ peaked at T≈{peak_t:.3f} vs Onsager {ONSAGER_TC:.4f}"
                if wall:
                    headline += f" · {wall:.0f}s on {hw((rep.get('config') or {}))}"
                if quality["status"] == "degraded":
                    headline += (
                        f" · quality warning: {len(quality['excluded_indices'])} "
                        "non-equilibrated sample(s) excluded"
                    )
    return {
        "date": rep.get("_date"),
        "headline": headline,
        "peak_t": peak_t,
        "onsager_tc": round(ONSAGER_TC, 4),
        "wall_s": wall,
        "url": report_url(),
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
        exp = report.get("experiment")
        if not exp or str(exp).startswith("M01"):
            peak = assess_m01_quality(report)["peak_t"]
            return round(peak, 3) if peak is not None else None
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
    url = origin.join(report_url_base(), f"{date}-{slug}.html")
    status = "null" if str(data.get("status", "")).lower() == "null" else "unscored"
    headline = data.get("headline")
    if slug == "m01":
        quality = assess_m01_quality(data)
        peak_t = _peak_t(data)
        if quality["status"] != "ok" or not headline:
            if peak_t is None:
                headline = f"M01 quality null · {quality['note']}"
            else:
                headline = f"χ peaked at T≈{peak_t:.3f} vs Onsager {ONSAGER_TC:.4f}"
                if quality["status"] == "degraded":
                    headline += (
                        f" · quality warning: {len(quality['excluded_indices'])} "
                        "non-equilibrated sample(s) excluded"
                    )
    return {
        "date": date,
        "milestone": _milestone_for(data),
        "experiment": data.get("experiment"),
        "headline": headline,
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


# ── The hunt block: the survey ledger, aggregated from committed receipts ────
# reports/hunts/ holds one JSON receipt per completed hunt run (the A05
# contract, docs/a05-receipt-schema.md; schema 0 = the pre-A05 pilots). The
# ``hunt`` key in pot.json is a PURE FUNCTION of those committed files — the
# same rule the milestones key follows with MILESTONES.md — so every clone
# publishes the same numbers and the page can never say "live": it says
# "as of" the newest receipt, because that is all the committed record knows.
HUNTS_DIR = REPORTS_DIR / "hunts"

#: Fallback detection threshold for receipts that do not declare their own
#: ``sde_threshold``. Mirrors ``lab.a04.SDE_THRESHOLD`` (measured, not chosen —
#: see a04.py) but is deliberately restated here as a constant: publish stays
#: import-light (stdlib only) and a04 pulls numpy. A receipt that used a
#: different threshold must say so; the aggregator never guesses.
HUNT_SDE_THRESHOLD = 8.0

#: Machine dispositions that mean "the catalog already refutes this signal".
#: A TOI whose community disposition is FP (e.g. TIC 278866211 = TOI 189.01,
#: TFOPWG FP, hit at SDE 10.3 in the 2026-08-14 wide hunt) is NOT a recovery
#: and NOT a lead — it is a validation target for the blend/centroid gates,
#: and it gets its own verdict so the histogram cannot launder it into either.
HUNT_KNOWN_FP = "toi-known-fp"

#: The machine-terminal candidate states. ``lead-awaiting-human-review`` is the
#: A05 vocabulary; ``planet-candidate`` is the pre-A05 pilot vocabulary for the
#: same thing (the A04 claim boundary: "a lead for human review ... not a
#: discovery"). No machine path may emit ``planet`` — a receipt that does is
#: refused outright rather than counted.
HUNT_LEAD_STATES = ("lead-awaiting-human-review", "planet-candidate")

#: The TFOPWG-refuted false positive from the 2026-08-14 wide hunt. Any
#: schema-0 pilot row for this target carries ``toi-known-fp`` no matter what
#: the run-time vetting said: the catalog match with disposition FP outranks a
#: machine planet-candidate verdict, and the target becomes a validation case
#: for the centroid-shift gate rather than a lead.
_PILOT_KNOWN_FPS = {
    "278866211": {"known_toi": "TOI 189.01", "catalog_disposition": "FP"},
}

#: The pilot's own refutations, applied at translation time so the committed
#: schema-0 receipt records what the instrument NOW knows, not the forty
#: minutes it didn't. TIC 140940493 was vetted ``planet-candidate`` on
#: 2026-08-14 and refuted the same day (five equally spaced dips in the fold at
#: P; amplitude spectrum peaking at 8.035 c/d = the P/5 prediction — a δ Scuti-
#: type pulsator whose 5th harmonic the BLS grid latched onto; the "secondary"
#: a 13σ phase-locked brightening). The hardened vetting regrades the same
#: detection ``harmonic-alias`` (docs/investigations/2026-08-14-a04-discovery-pilot.md).
_PILOT_REGRADES = {
    "140940493": {
        "disposition": "harmonic-alias",
        "evidence": {
            "initial_verdict": "planet-candidate",
            "pulsation_cpd": 8.035,
            "refuted": ("2026-08-14 follow-up: delta Scuti-type pulsator at "
                        "P/5 = 2.99 h; BLS latched onto the 5th harmonic; the "
                        "'secondary' is a 13-sigma phase-locked brightening"),
        },
    },
}

#: The provenance label the aggregator stamps on a schema-0 last-hunt: the
#: pilot ran on the A04 instrument with run-level statistics only, before the
#: A05 per-target FAP machinery existed. Never presented as A05 output.
PILOT_PROVENANCE = "pilot (pre-A05 statistics)"


def translate_pilot_summary(summary: dict, supersedes: str | None = None) -> dict:
    """An ``a04-discovery-pilot`` summary → a schema-0 hunt receipt.

    Tolerant on purpose: today's two hunt runs share this summary shape but the
    second completes after the first lands, so the translator takes whatever
    rows the summary has and derives nothing it cannot see. A schema-0 receipt
    carries the searched rows (the above-threshold hits — the pilot's
    per-target checkpoints stay deliberately uncommitted), the machine
    dispositions, the RUN-LEVEL injections, the noise-floor block that lets the
    aggregator re-derive the searched count (``floor.n + len(rows)``), and an
    explicit ``pilot`` marker so no consumer can mistake it for A05 output.

    Grading-time corrections, applied in order:

    1. A catalog match with TFOPWG disposition **FP** → ``toi-known-fp``. A
       community-refuted false positive is not a recovery and not a lead —
       whatever the run-time vetting said, the catalog verdict outranks it,
       and the target becomes a validation case for the blend gates. The
       ``_PILOT_KNOWN_FPS`` map is the fallback for rows missing their
       catalog block.
    2. A catalog match with disposition **KP**/**CP** → ``known-planet``: a
       serendipitous recovery of an already-confirmed planet, identified at
       grading time only (the A04 pattern), never a lead and never counted as
       anything new.
    3. The pilot's own same-day refutations (``_PILOT_REGRADES``) — e.g.
       TIC 140940493's forty-minute planet-candidate, regraded
       ``harmonic-alias``.

    ``supersedes`` names an earlier receipt this one replaces: the wide run's
    summary is CUMULATIVE (its jsonl checkpoints carry the first run's targets
    forward), so committing both without the link would double-count the first
    slice. The superseded receipt stays on the books as history; the
    aggregator excludes it from every counter.
    """
    rows = []
    for hit in summary.get("hits") or []:
        tic = str(hit.get("tic", ""))
        verdict = ((hit.get("vetting") or {}).get("verdict")) or None
        catalog = hit.get("catalog") or {}
        row = {
            "tic": tic,
            "outcome": "searched",
            "sde": hit.get("sde"),
            "period_days": hit.get("period_days"),
            "depth": hit.get("depth"),
            "phase": hit.get("phase"),
            "disposition": verdict,
            "known_planet": catalog.get("known_planet"),
        }
        cat_disp = catalog.get("disposition")
        if cat_disp == "FP" or tic in _PILOT_KNOWN_FPS:
            fallback = _PILOT_KNOWN_FPS.get(tic, {})
            row["disposition"] = HUNT_KNOWN_FP
            row["known_planet"] = None      # an FP is nobody's planet
            row["disposition_evidence"] = {
                "known_toi": catalog.get("known_toi") or fallback.get("known_toi"),
                "catalog_disposition": cat_disp or fallback.get("catalog_disposition"),
                "initial_verdict": verdict,
            }
        elif cat_disp in ("KP", "CP"):
            row["disposition"] = "known-planet"
            row["known_planet"] = (catalog.get("known_planet")
                                   or ("TOI " + str(catalog.get("known_toi"))))
            row["disposition_evidence"] = {
                "known_toi": catalog.get("known_toi"),
                "catalog_disposition": cat_disp,
                "published_period_days": catalog.get("published_period_days"),
                "initial_verdict": verdict,
            }
        elif tic in _PILOT_REGRADES:
            regrade = _PILOT_REGRADES[tic]
            row["disposition"] = regrade["disposition"]
            row["disposition_evidence"] = dict(regrade["evidence"])
        rows.append(row)
    floor_n = summary.get("floor_n")
    receipt = {
        "experiment": "a05-survey-hunt",
        "schema": 0,
        "pilot": "pre-A05 pilot (A04 instrument, run-level statistics only)",
        "date": summary.get("date"),
        "sector": summary.get("sector"),
        "slice_rule": summary.get("slice_rule"),
        "sde_threshold": HUNT_SDE_THRESHOLD,
        "targets_searched": summary.get("targets_searched"),
        "targets": rows,
        "injections": summary.get("injections") or [],
        "floor": {"n": floor_n, "max_sde": summary.get("floor_max_sde")},
        "wall_seconds": summary.get("wall_seconds"),
        "claim_boundary": summary.get("claim_boundary"),
    }
    if supersedes:
        receipt["supersedes"] = supersedes
    return receipt


def _hunt_receipt_date(receipt: dict, path: Path) -> str:
    """The receipt's own date: ``date`` (schema 0), else ``generated_at``'s day,
    else the date embedded in the filename (``hunt-<date>-…``)."""
    date = receipt.get("date")
    if isinstance(date, str) and len(date) >= 10:
        return date[:10]
    stamp = receipt.get("generated_at")
    if isinstance(stamp, str) and len(stamp) >= 10:
        return stamp[:10]
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
    return m.group(1) if m else ""


def _hunt_refusal(receipt: dict, path: Path) -> str | None:
    """Why this receipt cannot be honestly aggregated, or ``None`` if it can.

    The refusals are the contract's teeth (docs/a05-receipt-schema.md rules
    2–3): an above-threshold row with no machine disposition is an unfinished
    grading pass, a schema≥1 receipt with no injection coverage on its hits has
    no sensitivity measurement to stand on, a schema-0 receipt without its
    pilot marker or run-level injections is not the shape the pilot committed,
    and a receipt whose declared searched count disagrees with what its own
    rows + floor imply is lying about one of them. Any ``planet`` disposition
    is refused outright — no machine path may emit it.
    """
    schema = receipt.get("schema")
    if not isinstance(schema, int) or schema < 0:
        return "missing-or-bad-schema"
    threshold = receipt.get("sde_threshold", HUNT_SDE_THRESHOLD)
    rows = receipt.get("targets")
    if not isinstance(rows, list):
        return "missing-targets"
    above = [r for r in rows
             if isinstance(r, dict) and r.get("outcome") == "searched"
             and isinstance(r.get("sde"), (int, float)) and r["sde"] >= threshold]
    for row in above:
        disposition = row.get("disposition")
        if not (isinstance(disposition, str) and disposition.strip()):
            return f"undispositioned-above-threshold-hit:{row.get('tic')}"
    all_rows = rows + list(receipt.get("recoveries") or [])
    for row in all_rows:
        if isinstance(row, dict) and row.get("disposition") == "planet":
            return f"machine-emitted-planet:{row.get('tic')}"
    if schema == 0:
        if not (isinstance(receipt.get("pilot"), str) and receipt["pilot"].strip()):
            return "schema0-missing-pilot-marker"
        if not receipt.get("injections"):
            return "schema0-missing-run-level-injections"
        floor = receipt.get("floor") or {}
        floor_n = floor.get("n")
        declared = receipt.get("targets_searched")
        if not isinstance(floor_n, int):
            return "schema0-missing-floor-count"
        # Schema 0 carries only the above-threshold rows, so the searched count
        # is derived floor.n + rows; a declared total that disagrees means one
        # of the two is wrong and the receipt cannot be honestly counted.
        if isinstance(declared, int) and declared != floor_n + len(above):
            return "schema0-searched-count-mismatch"
    else:
        for row in above:
            if not row.get("injections"):
                return f"missing-injection-block:{row.get('tic')}"
    return None


def _receipt_target_rows(receipt: dict) -> tuple[list[dict], list[dict]]:
    """(searched rows, above-threshold rows) of one receipt — the one row
    filter both the per-receipt counters and the cross-receipt star ledger
    derive from, so the two can never disagree about what a row is."""
    threshold = receipt.get("sde_threshold", HUNT_SDE_THRESHOLD)
    rows = [r for r in receipt.get("targets", []) if isinstance(r, dict)]
    searched = [r for r in rows if r.get("outcome") == "searched"]
    above = [r for r in searched
             if isinstance(r.get("sde"), (int, float)) and r["sde"] >= threshold]
    return searched, above


def _hunt_receipt_counters(receipt: dict) -> dict:
    """Counters re-derived from a single accepted receipt's rows.

    Never reads the receipt's own ``counts``/``above_threshold`` fields — rule
    2 of the contract. Schema-0's searched count is ``floor.n + hit rows``
    (consistency with any declared total is enforced at refusal time).
    """
    schema = receipt.get("schema", 0)
    searched, above = _receipt_target_rows(receipt)
    if schema == 0:
        n_searched = (receipt.get("floor") or {}).get("n", 0) + len(above)
    else:
        n_searched = len(searched)
    dispositions: dict[str, int] = {}
    for row in above:
        # STR-2: a bare row["disposition"] here meant ONE malformed hunt row
        # raised KeyError through cli._hunt_status() into both the planner
        # and the rotation fallback — every physics turn collapsed to the
        # M01 heartbeat. Malformation is counted BY NAME (loud in the
        # numbers, visible to every consumer of the counters), never dropped
        # and never classified as a real disposition, and it cannot stall
        # the physics ladder.
        d = row.get("disposition") or "malformed-row"
        dispositions[d] = dispositions.get(d, 0) + 1
    # Deduped by TIC: a designated recovery appears BOTH as a target row and
    # in the receipt's ``recoveries`` list (same star, two mentions), and a
    # counter that added the mentions would report one recovery as two.
    known_tics: set[str] = set()
    candidates = list(above) + [r for r in (receipt.get("recoveries") or [])
                                if isinstance(r, dict)]
    for row in candidates:
        if row.get("known_planet") and row.get("disposition") != HUNT_KNOWN_FP:
            known_tics.add(str(row.get("tic")))
    leads = sum(dispositions.get(state, 0) for state in HUNT_LEAD_STATES)
    return {
        "targets_searched": n_searched,
        "above_threshold": len(above),
        "dispositions": dispositions,
        "known_recovered": len(known_tics),
        "leads_awaiting_human_review": leads,
    }


def _accepted_hunt_receipts(
        directory: Path) -> tuple[list[tuple[str, Path, dict]],
                                  list[dict], list[dict]]:
    """Accepted hunt receipts as ``(date, path, receipt)`` rows, plus the
    refused and superseded listings.

    The ONE reader of ``reports/hunts``: pot.json's hunt block and the
    planner's hunt seam must count from the same accepted set — two readers
    drifted apart on 2026-08-14 (the schema-1 survey receipt fed the pot but
    not the planner) and the survey slot silently vanished.
    """
    paths = sorted(directory.glob("*.json"))
    accepted: list[tuple[str, Path, dict]] = []
    refused: list[dict] = []
    for path in paths:
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            refused.append({"file": path.name, "reason": "unreadable"})
            continue
        reason = _hunt_refusal(receipt, path)
        if reason is not None:
            refused.append({"file": path.name, "reason": reason})
            continue
        accepted.append((_hunt_receipt_date(receipt, path), path, receipt))

    # A receipt named by another ACCEPTED receipt's ``supersedes`` is history,
    # not a counter: the wide pilot run's summary is cumulative over the first
    # slice, so counting both would double-count 158 stars. The superseded
    # file stays committed and is named here, so nothing quietly vanishes.
    superseded_by = {}
    for _, path, receipt in accepted:
        target = receipt.get("supersedes")
        if isinstance(target, str) and target:
            superseded_by[target] = path.name
    superseded = [{"file": p.name, "by": superseded_by[p.name]}
                  for _, p, _ in accepted if p.name in superseded_by]
    accepted = [item for item in accepted if item[1].name not in superseded_by]
    return accepted, refused, superseded


def hunt_block(hunts_dir: Path | None = None) -> dict | None:
    """Aggregate every committed hunt receipt into pot.json's ``hunt`` block.

    A pure function of ``reports/hunts/*.json`` — no clock, no local state — so
    every clone derives the same block, exactly as the milestones key is a pure
    function of MILESTONES.md. ``None`` when no receipts exist (the page then
    omits the section entirely).

    Refused receipts are EXCLUDED from every counter and named in ``refused``
    (file + reason): a refusal is a fact about the record worth publishing, not
    a silent skip. ``claim_boundary`` and ``as_of`` come verbatim from the
    newest accepted receipt — the page must say "as of", never "live", because
    a committed ledger only knows its newest entry. ``planets_discovered`` is
    pinned to the literal 0 below and is not computed from anything: promoting
    a lead to a planet is a human act on the record (MILESTONES.md), and no
    machine path through this function can raise the number.
    """
    directory = hunts_dir if hunts_dir is not None else HUNTS_DIR
    if not directory.exists():
        return None
    if not any(directory.glob("*.json")):
        return None
    accepted, refused, superseded = _accepted_hunt_receipts(directory)

    if not accepted:
        empty = {"targets_searched": 0, "above_threshold": 0, "dispositions": {},
                 "known_recovered": 0, "leads_awaiting_human_review": 0,
                 "planets_discovered": 0, "last_hunt": None,
                 "claim_boundary": None, "as_of": None, "refused": refused}
        if superseded:
            empty["superseded"] = superseded
        return empty

    # ``targets_searched`` stays a per-receipt counter SUM — it is a statement
    # of work done, and re-searching a star in a later slice really is more
    # work. Every star-level number below is aggregated per DISTINCT star
    # instead, newest receipt's verdict winning: overlapping slices exist
    # (two boxes hunted overlapping sector-2 slices on 2026-08-15, and a
    # restore preserved all three), and a row-sum would report the same
    # lead-awaiting-human-review star once per slice it appears in. A lead
    # is a star, not a row.
    total_searched = 0
    star_disposition: dict[str, str] = {}
    star_known: dict[str, bool] = {}
    for _, _, receipt in sorted(accepted,
                                key=lambda item: (item[0], item[1].name)):
        total_searched += _hunt_receipt_counters(receipt)["targets_searched"]
        searched_rows, above = _receipt_target_rows(receipt)
        above_tics = {str(r.get("tic")) for r in above}
        for row in searched_rows:
            tic = str(row.get("tic"))
            if tic in above_tics:
                continue
            # Newest verdict wins: a re-searched star that no longer crosses
            # threshold leaves the EVENT ledger. Its recovery flag stays —
            # a detection already made is history, not a live claim a weaker
            # slice can un-make.
            star_disposition.pop(tic, None)
        for row in above:
            tic = str(row.get("tic"))
            star_disposition[tic] = row["disposition"]
            if row["disposition"] == HUNT_KNOWN_FP:
                # The community-refuted re-grade DOES clear a recovery: FP/FA
                # means the signal was never the planet (the TOI 189.01 rule).
                star_known.pop(tic, None)
        for row in above + [r for r in (receipt.get("recoveries") or [])
                            if isinstance(r, dict)]:
            if row.get("known_planet") and row.get("disposition") != HUNT_KNOWN_FP:
                star_known[str(row.get("tic"))] = True
    dispositions: dict[str, int] = {}
    for verdict in star_disposition.values():
        dispositions[verdict] = dispositions.get(verdict, 0) + 1
    totals = {
        "targets_searched": total_searched,
        "above_threshold": len(star_disposition),
        "known_recovered": len(star_known),
        "leads_awaiting_human_review": sum(
            dispositions.get(state, 0) for state in HUNT_LEAD_STATES),
    }

    newest_date, newest_path, newest = max(
        accepted, key=lambda item: (item[0], item[1].name))
    newest_counters = _hunt_receipt_counters(newest)
    block = {
        "targets_searched": totals["targets_searched"],
        "above_threshold": totals["above_threshold"],
        "dispositions": dispositions,
        "known_recovered": totals["known_recovered"],
        "leads_awaiting_human_review": totals["leads_awaiting_human_review"],
        # HARD-PINNED. Assigned from a literal, after all aggregation, on
        # purpose: there is no data path from any receipt to this number.
        "planets_discovered": 0,
        "last_hunt": {
            "date": newest_date,
            "sector": newest.get("sector"),
            "n": newest_counters["targets_searched"],
            "wall": newest.get("wall_seconds"),
            "provenance": (PILOT_PROVENANCE if newest.get("schema") == 0
                           else "a05"),
        },
        # Verbatim from the newest accepted receipt — never paraphrased here,
        # never paraphrased by the page.
        "claim_boundary": newest.get("claim_boundary"),
        "as_of": newest_date,
    }
    if refused:
        block["refused"] = refused
    if superseded:
        block["superseded"] = superseded
    block["planets_discovered"] = 0   # the pin, restated last so nothing above can move it
    return block


def build_snapshot(milestones, last_run, runs, temp_c, report=None,
                   reports=None, reports_ledger=None, turns=None,
                   divergence=None, hunt=None,
    goal: dict | None = None,
) -> dict:
    """Assemble the sanitized snapshot the /windowsill/ page consumes.

    ``turns`` (optional) is the ``turn_cadence()`` object — the pass counter and
    the declared cadence. ``divergence`` (optional) is the machine-aligned
    disagreement list from ``archive.detect_divergence``; both are omitted when
    absent and the page degrades to its legacy constants without them.
    ``hunt`` (optional) is the ``hunt_block()`` aggregate of the committed
    survey receipts; omitted when absent and the page hides its hunt section.

    ``reports_ledger`` (new) is the archive's sanitized every-run ledger
    (``archive.run_ledger()`` — rows of ``{date, milestone, verdict, headline,
    href}``). ``reports`` is the legacy compact run-record list. Either fills
    the ``reports`` array; ``reports_ledger`` wins when both are given. When a
    ``reports`` array is present, ``latest_report`` is its first (headline) row;
    otherwise the legacy single ``report`` argument fills it — so old callers and
    old consumers degrade cleanly. ``archive_url`` deep-links the index page.
    """
    rows = reports_ledger if reports_ledger is not None else reports
    latest = (rows[0] if rows else report)
    if reports_ledger is not None and latest is not None:
        # The latest field note has a real full render at latest.html. Archive
        # rows keep stable record anchors + receipt_url for older runs.
        latest = dict(latest)
        latest["href"] = report_url()
    snap = {
        "schema_version": SCHEMA_VERSION,
        "source": "windowsill-lab",
        "milestones": milestones,
        "total": len(milestones),
        "last_run": last_run,
        "runs": runs,
        "temp_c": temp_c,
        "latest_report": latest,
        "archive_url": archive_url(),
        "updated": datetime.now(timezone.utc).isoformat(),
        # PUBLISHER-box provenance: the environment that built this feed, which
        # is not necessarily the environment that ran any given result. Never
        # surface it as "the lab's environment" — per-turn truth is the ledger
        # row's own ``machine`` plus its receipt.
        "provenance": provenance(),
    }
    if rows is not None:
        snap["reports"] = rows
    if turns is not None:
        snap["turns"] = turns
    if divergence:
        snap["divergence"] = divergence
    if hunt is not None:
        snap["hunt"] = hunt
    if goal is not None:
        snap["goal"] = goal
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
    turns = divergence = None
    try:
        from . import archive
        turns = turn_cadence()
        divergence = archive.detect_divergence(archive.public_runs())
    except Exception:  # noqa: BLE001 — same guard: the turn layer never breaks the feed
        pass
    hunt = hunt_block()   # pure function of committed reports/hunts/*.json
    # The declared goal rides the feed the public page already reads, rather
    # than standing up a surface of its own. Its progress is COMPUTED from the
    # catalogue every publish — a goal whose progress is hand-written measures
    # the writer's mood — and it is allowed to read MISSED. Guarded because a
    # malformed catalogue must degrade the goal block, never the whole feed.
    goal_block = None
    try:
        from . import goal as goal_mod
        goal_block = goal_mod.progress()
    except Exception:  # noqa: BLE001
        pass
    if ledger is not None:
        return build_snapshot(
            parse_milestones(text), last_run, runs, cpu_temp_c(),
            reports_ledger=ledger, turns=turns, divergence=divergence,
            hunt=hunt, goal=goal_block,
        )
    return build_snapshot(
        parse_milestones(text), last_run, runs, cpu_temp_c(),
        reports=discover_runs(), hunt=hunt, goal=goal_block,
    )


def _receipt_filename(date: str, slug: str, turn: str | None = None) -> str:
    """Stable public-receipt name (does not match the dated-report gitignore).

    ``turn`` is the local ``HHMM`` of the pass. With it the name becomes
    ``run-<date>-<hhmm>-<slug>.json``, which is what makes two turns of the
    same milestone on the same day two receipts instead of one overwriting the
    other — the prerequisite for counting turns honestly and for the archive's
    "every run is kept" claim. Without it the legacy ``run-<date>-<slug>.json``
    is produced unchanged, so every receipt already on the books keeps its name
    and its URL forever.
    """
    stem = f"{date}-{turn}-{slug}" if turn else f"{date}-{slug}"
    return f"run-{stem}.json"


# A turn stamp is exactly four digits followed by a hyphen, at the head of what
# would otherwise be the slug. Slugs are milestone ids or ``run`` (see
# ``_slug_for``) and therefore always start with a LETTER, so this prefix can
# never eat a slug — the guard is structural, not a convention.
_TURN_PREFIX_RE = re.compile(r"^(\d{4})-(?=.)")


def _split_receipt_stem(stem: str) -> tuple[str, str | None, str]:
    """``<date>[-<hhmm>]-<slug>`` → ``(date, turn, slug)``; turn ``None`` if bare.

    Legacy receipts (written before turn-stamping) parse to ``turn=None`` and
    behave exactly as they always have.
    """
    date, rest = stem[:10], stem[11:]
    match = _TURN_PREFIX_RE.match(rest)
    if match:
        return date, match.group(1), rest[match.end():]
    return date, None, rest


def receipt_turn(path: Path) -> str | None:
    """The ``HHMM`` turn stamp in a receipt filename, or ``None`` when legacy."""
    return _split_receipt_stem(path.stem[len("run-"):])[1]


def _existing_receipt_for(date: str, slug: str) -> Path | None:
    """The receipt already on the books for ``(date, slug)``, whatever its name.

    Prefers the bare legacy name so a receipt that has been committed and linked
    for months keeps its URL; otherwise returns the newest stamped turn of that
    day. ``None`` when the run has no receipt yet.
    """
    if not RECEIPTS_DIR.exists():
        return None
    bare = RECEIPTS_DIR / _receipt_filename(date, slug)
    if bare.exists():
        return bare
    stamped = []
    for path in RECEIPTS_DIR.glob(f"run-{date}-*.json"):
        found_date, turn, found_slug = _split_receipt_stem(path.stem[len("run-"):])
        if turn and found_date == date and found_slug == slug:
            stamped.append((turn, path))
    return max(stamped)[1] if stamped else None


def ensure_public_receipts() -> list[Path]:
    """Create deterministic, compact evidence receipts for every known run.

    Full dated reports stay local/ignored because their embedded lattice images
    are large.  Receipts retain the numerical measurements, checker inputs,
    provenance, and reproduction commands while hashing omitted snapshots.  A
    repo report wins over its ``~/.lab`` twin so provenance-stamped copies are
    preferred.  Returns every receipt path, whether newly written or untouched.

    Backfill only ever ADDS. A receipt already on disk is never regenerated — it
    is the permanent record of what that run measured, the same promise
    ``archive.py`` makes about reports. Source selection is a heuristic and can
    pick a divergent twin; immutability is what keeps that from rewriting
    reviewed evidence.

    This is the BACKFILL path, and it never invents a turn stamp. A dated report
    has already collapsed a day's same-milestone turns into one file, so it
    cannot know how many turns it stands for; minting a stamped name here would
    put a second receipt on the books for a run that already has one. It writes
    to whatever name that run's receipt already carries and otherwise to the
    bare legacy name. Only ``render._commit_report`` — which sees the actual
    pass — stamps a turn.
    """
    from .receipt import paused_planned_decision, receipt_text  # stdlib-only

    # (date, slug) -> (is_repo, mtime, path, decoded report)
    selected: dict[tuple[str, str], tuple[bool, float, Path, dict]] = {}
    for directory in (LAB_HOME, REPORTS_DIR):
        if not directory.exists():
            continue
        is_repo = directory.resolve() == REPORTS_DIR.resolve()
        for path in directory.glob(f"{_DATE_GLOB}*.json"):
            try:
                raw = path.read_bytes()
                data = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            key = (_date_of(path), _slug_for(data))
            candidate = (is_repo, path.stat().st_mtime, path, data)
            current = selected.get(key)
            if current is None or (is_repo and not current[0]) or \
                    (is_repo == current[0] and candidate[1] > current[1]):
                selected[key] = candidate

    paths: list[Path] = []
    for (date, slug), (_, _, source, data) in sorted(selected.items()):
        destination = _existing_receipt_for(date, slug) \
            or RECEIPTS_DIR / _receipt_filename(date, slug)
        # A receipt already on disk is EVIDENCE, and evidence is immutable. The
        # source selection above cannot tell a correction from a corruption: the
        # repo's dated reports are gitignored, so in a fresh clone, on the other
        # box, or in a worktree there is no repo report to win and a divergent
        # ~/.lab twin of the same (date, slug) becomes the source. Regenerating
        # then overwrites reviewed measurements with another run's numbers —
        # which is exactly what happened to K01 on 2026-08-02. Keep the receipt,
        # report it, write nothing.
        if destination.exists():
            paths.append(destination)
            continue
        # Backfilled receipts belong to OTHER runs, so they must never inherit
        # the planned block of the turn that happens to be publishing.
        with paused_planned_decision():
            content = receipt_text(data, source.read_bytes())
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, content, encoding="utf-8")
        paths.append(destination)
    return paths


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
        # Copy the machine-readable report verbatim (never move — keep ~/.lab),
        # PRESERVING the source mtime: scan_runs orders newest-first by mtime,
        # so a today-stamped copy of an old run would masquerade as the
        # latest and scramble the public feed's order (bit on 2026-07-19).
        src_mtime = src.stat().st_mtime
        atomic_write_text(json_dest, src.read_text(encoding="utf-8"), encoding="utf-8")
        os.utime(json_dest, (src_mtime, src_mtime))
        written.append(json_dest)

        # Re-render the HTML from the EXISTING JSON. Lazy import so the JSON
        # path works even where matplotlib/torch aren't installed.
        src_html = src.with_suffix(".html")
        try:
            if src_html.exists():
                atomic_write_text(html_dest, src_html.read_text(encoding="utf-8"), encoding="utf-8")
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
    # Receipts must exist before collect(): the archive ledger then publishes a
    # stable evidence URL for each run in this very snapshot.
    ensure_public_receipts()
    snap = collect()
    content = json.dumps(snap, indent=2) + "\n"
    atomic_write_text(POT_JSON, content, encoding="utf-8")  # canonical, committed live feed
    LAB_HOME.mkdir(parents=True, exist_ok=True)
    out = LAB_HOME / "pot.json"
    atomic_write_text(out, content, encoding="utf-8")

    # Refresh the committed archive index (reports/index.html) so the every-run
    # ledger page tracks the feed. Best-effort — same guard as the gist push;
    # the nightly's `git add -A reports/` commits it.
    try:
        from . import archive
        archive.write_index()
    except Exception:  # noqa: BLE001 — the index is never allowed to break publish
        pass

    # Refresh physics-latest.json — the compact, plottable feed the windowsill's
    # "look through the instrument" panel reads (the real χ(T)/|m|(T) curves and
    # the ordered/critical/disordered lattice snapshots). Best-effort, same
    # guard: the physics face is never allowed to break the run, and a box with
    # no snapshot report yet simply writes nothing.
    try:
        from . import physics_feed
        # Fallback only: this describes the publishing box, and the feed's
        # provenance describes the run it was generated from. A report that
        # carries its own provenance keeps it.
        physics_feed.build_physics_feed(provenance=snap.get("provenance"))
    except Exception:  # noqa: BLE001 — the physics feed never breaks publish
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
