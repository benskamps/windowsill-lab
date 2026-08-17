"""The full-provenance ARCHIVE — the lab's honest back-room ledger + index.

The /windowsill/ page shows the *living* face of the lab: a seedling whose
stem grows a node per verified milestone and a folded grey leaf per failed
calibration. The **archive** is its honest back-room — a flat, newest-first
index of EVERY run on record, not just the milestone summaries:

* a **verified** run is a green-leaf node (a check re-derived its number),
* a **null** run is a FOLDED GREY LEAF — a check ran and the number missed,
  kept on the books *with its real numbers* (the L=512 finite-size honesty),
* an **unscored** run is a plain node — no check understands it yet, so it's
  shown rather than silently assumed (a verdict is never dropped),
* an **unreadable** run is an honest gap — a corrupt report JSON, kept as a
  row rather than vanished.

Each row keeps a stable human-readable archive anchor and, where available, a
compact public receipt containing its gated measurements and provenance. Heavy
visual snapshots stay in the local/full report and are explicitly hash-pinned
as omissions rather than silently disappearing.

Kept deliberately import-light — *stdlib only* (mirrors ``publish.py``): no
torch, no matplotlib. The verdict is graded through ``checks.CHECKS`` (keyed by
the inferred milestone) so it self-updates as M04+ checks land, rather than
hard-coding three function names. Run discovery + dedupe defers to
``publish.discover_runs`` so the two never drift; this module adds the *verdict*
and the *index HTML*.
"""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path

from .publish import (
    ARCHIVE_URL, CADENCE, LAB_HOME, RECEIPTS_DIR, RECEIPT_URL_BASE, REPORTS_DIR,
    REPORT_URL_BASE, _DATE_GLOB, _date_of, _milestone_for, _peak_t,
    _receipt_filename, _slug_for, _split_receipt_stem, cadence_is_effective,
    today_local,
)

# Where the index lands. The nightly already ``git add -A reports/`` so writing
# reports/index.html here makes it the committed, deep-linkable archive page.
INDEX_HTML = REPORTS_DIR / "index.html"

# The calibration scoreboard "money plot" (rendered by scoreboard.py, committed as
# a PNG). Embedded here by reading the committed file and inlining it as base64 —
# so this module stays stdlib-only (no matplotlib) and the nightly's index regen
# preserves the figure as long as the PNG is committed. Resolved at call time so a
# test that repoints REPORTS_DIR is honoured.
def _scoreboard_png() -> Path:
    return REPORTS_DIR / "scoreboard.png"


def _scoreboard_section() -> str:
    """The scoreboard figure as an HTML section, or '' when the PNG isn't committed."""
    png = _scoreboard_png()
    if not png.exists():
        return ""
    try:
        b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return (
        '  <h2>calibration scoreboard</h2>\n'
        '  <p class="note">Every verified milestone\'s measured value against the exact '
        'or benchmark theory, in units of that milestone\'s own check tolerance '
        '(<code>z = (measured − theory) / tol</code>). A point inside the shaded band '
        'reproduced theory within its gate. One picture of everything the lab has '
        'claimed vs what statistical mechanics says.</p>\n'
        f'  <figure class="scoreboard"><img src="data:image/png;base64,{b64}" '
        'alt="calibration scoreboard: each milestone\'s measured value vs exact theory, '
        'in units of its check tolerance"></figure>\n'
    )

# htmlpreview deep-link for a dated HTML report (resolves once pushed).
_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)

# Map a report's "kind" off its experiment tag → a coarse family for grouping
# and headlines. fss = finite-size scaling (M02), collapse = data collapse
# (M03), ising = the single-lattice χ-sweep (M01 / legacy bare dumps).
def _kind_for(report: dict) -> str:
    exp = str(report.get("experiment", ""))
    if exp.startswith("M16"):
        return "aging"
    if exp.startswith("C01"):
        return "arithmetic"
    if exp.startswith("A01"):
        return "astronomy"
    if exp.startswith("I01"):
        return "instrument"
    if exp.startswith("M02") or "finite-size" in exp:
        return "fss"
    if exp.startswith("M03") or "collapse" in exp:
        return "collapse"
    return "ising"


def _numbers_for(report: dict, kind: str) -> str:
    """A compact, human number-string for a run — the receipt at a glance.

    ising  → peak T (χ-sweep) ; fss → measured slope + R² + L-values ;
    collapse → β/ν + residual ; falls back to wall-time / lattice size. Always
    a string, HTML-escaped at render time, never raw arrays.
    """
    if kind == "aging":
        ratio = report.get("collapse_ratio")
        separation = report.get("fixed_lag_separation")
        if ratio is not None and separation is not None:
            return f"scaled/fixed scatter={ratio:.2f}× · ΔC={separation:+.3f}"
    if kind == "arithmetic":
        terms = report.get("n_terms")
        residue = report.get("lucas_lehmer_residue")
        if terms is not None and residue is not None:
            return f"{terms} OEIS terms exact · LL residue={residue}"
    if kind == "astronomy":
        period = report.get("period_days")
        depth = report.get("depth_fraction")
        if period is not None and depth is not None:
            return f"P={period:.8f} d · depth={100*depth:.3f}%"
    if kind == "instrument":
        analysis = report.get("analysis")
        if not analysis:
            return "hardware unavailable · no frames measured"
        return (f"{analysis['shape'][0]} frames · {analysis['hot_pixel_count']} hot · "
                f"{analysis['track_candidate_count']} track-like")
    if kind == "fss":
        slope = report.get("gamma_over_nu_fit")
        r2 = report.get("fit_r2")
        Ls = [c.get("L") for c in report.get("curves") or [] if c.get("L")]
        bits = []
        if slope is not None:
            bits.append(f"slope γ/ν={slope:.3f}")
        if r2 is not None:
            bits.append(f"R²={r2:.3f}")
        if Ls:
            bits.append("L=" + ",".join(str(L) for L in Ls))
        if bits:
            return " · ".join(bits)
    if kind == "collapse":
        bon = report.get("beta_over_nu_fit")
        resid = report.get("collapse_residual")
        bits = []
        if bon is not None:
            bits.append(f"β/ν={bon:.3f}")
        if resid is not None:
            bits.append(f"residual={resid:.2e}")
        if bits:
            return " · ".join(bits)
    peak = _peak_t(report)
    if peak is not None:
        return f"χ peak at T≈{peak:.3f}"
    wall = report.get("wall_seconds")
    L = (report.get("config") or {}).get("L")
    bits = []
    if L:
        bits.append(f"L={L}")
    if wall:
        bits.append(f"{wall:.0f}s")
    return " · ".join(bits) if bits else "—"


def _verdict_for(report: dict, milestone: str | None) -> str:
    """Grade a run through the checks registry → verdict + (real) detail.

    Returns ``(verdict, detail)`` where verdict is one of
    ``verified`` / ``null`` / ``unscored``:

    * the milestone's check ``ok is True`` → ``verified`` (green leaf),
    * ``ok is False`` → ``null`` (folded grey leaf) — the detail KEEPS the real
      measured numbers the check reported (e.g. the off slope + L-values),
    * ``ok is None`` (not applicable) OR no check registered → ``unscored``
      (a plain node, kept on the books, never dropped).
    """
    from . import checks  # lazy: checks imports publish; keep archive import-light
    fn = checks.CHECKS.get(milestone) if milestone else None
    if fn is None:
        return "unscored", "no check understands this run yet"
    try:
        ok, detail = fn(report)
    except Exception as e:  # noqa: BLE001 — a misbehaving check is itself a null signal
        return "null", f"check raised: {e}"
    if ok is None:
        return "unscored", detail
    return ("verified" if ok else "null"), detail


def classify_run(report: dict) -> dict:
    """Classify ONE report into an archive row (pure — no disk).

    Returns a dict with: ``milestone`` (inferred id or ``None``), ``kind``
    (ising/fss/collapse), ``experiment``, ``headline``, ``verdict``
    (verified/null/unscored), ``detail`` (the check's real numbers, kept even on
    a null), ``numbers`` (a compact receipt string), and ``code_sha``. ``date``
    and the link fields are added by ``scan_runs`` (they need the file path).
    """
    milestone = _milestone_for(report)
    kind = _kind_for(report)
    verdict, detail = _verdict_for(report, milestone)
    headline = report.get("headline")
    # M01's checker may exclude a disclosed metastable sample.  Historical
    # reports can therefore carry a stale raw-argmax headline even though their
    # verdict was derived from the usable peak.  The public ledger must repeat
    # the checked result, not the contradicted raw claim.
    if milestone == "M01" and verdict in {"verified", "null"}:
        from .m01_quality import assess_m01_quality
        quality = assess_m01_quality(report)
        if quality["status"] != "ok":
            headline = detail
    return {
        "milestone": milestone,
        "kind": kind,
        "experiment": report.get("experiment"),
        "headline": headline,
        "verdict": verdict,
        "detail": detail,
        "numbers": _numbers_for(report, kind),
        "code_sha": report.get("code_sha"),
    }


def _anchor_for(date: str, slug: str, turn: str | None = None) -> str:
    """Stable, URL-safe archive row anchor for one dated run.

    Includes the turn stamp when there is one, so two turns of the same
    milestone on the same day get two anchors instead of both deep-linking to
    whichever row rendered last. A run without a stamp keeps the anchor it has
    always had — every link already published still resolves.
    """
    stem = f"{date}-{turn}-{slug}" if turn else f"{date}-{slug}"
    safe = re.sub(r"[^a-z0-9-]+", "-", stem.lower()).strip("-")
    return f"run-{safe}"


# ── Which machine took this turn ─────────────────────────────────────────────
# The ONE derivation site. Everything downstream (ledger rows, the turns object,
# the divergence detector) calls this rather than re-deriving, so "which box"
# has a single definition that can be changed in one place.
_MACHINE_RE = re.compile(r"^[a-z][a-z0-9-]{0,23}$")


def machine_of(receipt: dict) -> str | None:
    """``"windows-cuda"`` / ``"linux-rocm"`` for one run, or ``None`` if unknown.

    Derived from the run's OWN receipt: ``provenance.platform`` gives the OS
    half and the torch build suffix gives the accelerator half. Deliberately NOT
    from ``config.device`` (which reads "cuda" on both boxes — torch's ROCm
    build keeps the CUDA API names) and NOT from the feed's top-level
    ``provenance`` (that is the publishing box, which is a different question).

    When provenance is absent — the runs predating provenance stamping — this
    returns ``None`` and the field is simply omitted. It is never guessed and
    never backfilled by inferring from the date: the archive's job is to say
    what it knows, and "we did not record it" is what it knows about those.
    """
    prov = receipt.get("provenance")
    if not isinstance(prov, dict):
        return None
    platform = prov.get("platform")
    if not isinstance(platform, str) or not platform:
        return None
    os_half = platform.split("-")[0].strip().lower()
    if not os_half:
        return None
    deps = prov.get("dependencies")
    torch = deps.get("torch") if isinstance(deps, dict) else None
    accelerator = None
    if isinstance(torch, str):
        if "+rocm" in torch:
            accelerator = "rocm"
        elif "+cu" in torch:
            accelerator = "cuda"
    # An unparseable torch build still leaves the OS half true — a half-known
    # provenance is published as the half that is known, not discarded.
    machine = f"{os_half}-{accelerator}" if accelerator else os_half
    return machine if _MACHINE_RE.match(machine) else None


def _stamp_provenance(row: dict, data: dict) -> None:
    """Add ``machine`` / ``at`` to a ledger row when the run recorded them.

    Absence is the point: a run that never wrote provenance gets neither field
    and renders bare, which is the record telling the truth about itself. Both
    are set from the run's own document, never inferred from its neighbours.
    """
    machine = machine_of(data)
    if machine:
        row["machine"] = machine
    stamp = data.get("generated_at")
    if isinstance(stamp, str) and stamp:
        row["at"] = stamp


def _href_for(date: str, slug: str, is_repo: bool,
              local_path: Path, turn: str | None = None) -> str:
    """The report deep-link for a run.

    Dated per-run renders are gitignored (too large to accrete in git history —
    see ``reports/.gitignore``), so they NEVER resolve through htmlpreview even
    when a copy sits in ``reports/`` locally — a dated deep-link 400s on GitHub.
    The only committed, htmlpreview-able report surfaces are
    ``reports/latest.html`` (the newest run — linked as the page's main "full
    report") and ``reports/index.html`` (this committed every-run ledger). So a
    committed run deep-links to its stable row anchor in the archive index; its
    separate ``receipt_href`` points at a small, durable measurement receipt.
    A local-only (~/.lab) run keeps its dated JSON path for traceability before
    publication (the page link-guard keeps non-http hrefs out of the feed).
    """
    if is_repo:
        return f"{ARCHIVE_URL}#{_anchor_for(date, slug, turn)}"
    # Local-only: a file path to the dated JSON cache. Not an http link.
    return local_path.as_uri() if local_path.exists() else str(local_path)


def _receipts_by_run() -> dict[tuple[str, str, str], tuple[str | None, Path]]:
    """``(date, slug, generated_at)`` → ``(turn, path)`` for every committed receipt.

    The join key a dated report uses to find ITS OWN receipt. Filenames can't do
    that job any more: under a multi-turn rotation the dated report is the
    latest turn of its day, and matching it to a receipt by ``(date, slug)``
    alone would pair it with an arbitrary one of that day's turns. The
    ``generated_at`` stamp is the run's own identity and is content, so the
    pairing is identical in every clone.
    """
    index: dict[tuple[str, str, str], tuple[str | None, Path]] = {}
    if not RECEIPTS_DIR.exists():
        return index
    for path in RECEIPTS_DIR.glob(f"run-{_DATE_GLOB}-*.json"):
        date, turn, slug = _split_receipt_stem(path.stem[len("run-"):])
        if not slug:
            continue
        try:
            stamp = json.loads(path.read_text(encoding="utf-8")).get("generated_at")
        except (OSError, ValueError):
            continue
        if isinstance(stamp, str) and stamp:
            index[(date, slug, stamp)] = (turn, path)
    return index


def scan_runs() -> list[dict]:
    """Every run on record across the repo ``reports/`` and ``~/.lab``.

    Globs the same ``<date>*.json`` pattern as ``publish._report_jsons``,
    dedupes by ``(date, slug, turn)`` PREFERRING the committed ``reports/`` copy
    (and flagging ``local_only`` for runs that exist only in ``~/.lab``), keeps a
    corrupt report JSON as an honest ``unreadable`` gap row, and sorts
    newest-first by ``(mtime, date_stem, turn)`` so a stale future-dated file
    can't masquerade as the latest and two turns of one day keep their real
    order in a fresh clone (which flattens every mtime). Each row carries
    ``has_dated_html`` + ``report_href`` for deep-linking, and — when the run
    recorded its provenance — ``machine`` (which box took the turn) and ``at``
    (the run's own timestamp).

    The turn joins the dedupe key because a same-day re-run of one milestone is
    a SECOND turn, not a duplicate of the first. Runs with no turn stamp (every
    receipt written before stamping landed) key on ``turn=None`` and collapse
    exactly as they always have.
    """
    # Per (date, slug, turn): keep the best file. Repo beats ~/.lab; within the
    # same priority, the newest mtime wins. Value = (mtime, row).
    by_key: dict[tuple[str, str, str | None], tuple[float, dict]] = {}
    receipts_by_run = _receipts_by_run()

    for directory in (REPORTS_DIR, LAB_HOME):
        if not directory.exists():
            continue
        is_repo = directory.resolve() == REPORTS_DIR.resolve()
        for p in directory.glob(f"{_DATE_GLOB}*.json"):
            date = _date_of(p)
            mtime = p.stat().st_mtime
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # An honest unreadable gap — kept as a row, not vanished.
                key = (date, p.stem, None)
                row = {
                    "date": date, "milestone": None, "kind": "unreadable",
                    "slug": p.stem,
                    "experiment": None, "headline": None,
                    "verdict": "unreadable", "detail": "report JSON is corrupt",
                    "numbers": "—", "code_sha": None,
                    "has_dated_html": False, "local_only": not is_repo,
                    "receipt_href": None,
                    "report_href": (p.as_uri() if p.exists() else str(p)),
                }
                cur = by_key.get(key)
                if cur is None or mtime > cur[0]:
                    by_key[key] = (mtime, row)
                continue

            slug = _slug_for(data)
            stamp = data.get("generated_at")
            # This report's own receipt, found by the run's timestamp rather
            # than by name — that is what tells us which turn it was.
            turn, receipt = receipts_by_run.get(
                (date, slug, stamp) if isinstance(stamp, str) else ("", "", ""),
                (None, None),
            )
            if receipt is None:
                bare = RECEIPTS_DIR / _receipt_filename(date, slug)
                receipt = bare if bare.exists() else None
            key = (date, slug, turn)
            has_html = (directory / f"{date}-{slug}.html").exists()
            row = classify_run(data)
            row["date"] = date
            row["slug"] = slug
            row["turn"] = turn
            row["has_dated_html"] = has_html
            row["local_only"] = not is_repo
            row["report_href"] = _href_for(date, slug, is_repo, p, turn)
            row["receipt_href"] = (
                RECEIPT_URL_BASE + receipt.name if receipt is not None else None
            )
            _stamp_provenance(row, data)

            cur = by_key.get(key)
            cur_is_repo = (not cur[1]["local_only"]) if cur else False
            if cur is None or (is_repo and not cur_is_repo) or \
               (is_repo == cur_is_repo and mtime > cur[0]):
                by_key[key] = (mtime, row)

    # Receipts fallback — the multi-box safety net (2026-07-19). Dated report
    # JSONs are gitignored by design (heavy) and mostly live on the box that
    # ran them; receipts are committed for EVERY run and carry the regradeable
    # measurements. A box that has only the receipt (a fresh clone, or the
    # other nightly host) must still keep the run on the public books —
    # otherwise the feed's history shrinks to whichever box published last.
    if RECEIPTS_DIR.exists():
        for p in RECEIPTS_DIR.glob(f"run-{_DATE_GLOB}-*.json"):
            date, turn, slug = _split_receipt_stem(p.stem[len("run-"):])
            if not slug:
                continue
            key = (date, slug, turn)
            current = by_key.get(key)
            # A committed report is already the richer public row. A local raw
            # report with the same turn stamp is only a recovery input: it must
            # never prevent its committed receipt from becoming the public row.
            # Filtering local rows later is too late because the key has already
            # been occupied; replace that local shadow here at the source.
            if current is not None and not current[1].get("local_only"):
                continue
            mtime = p.stat().st_mtime
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # Same honesty as a corrupt dated report: a kept gap row.
                by_key[key] = (mtime, {
                    "date": date, "milestone": None, "kind": "unreadable",
                    "slug": slug, "turn": turn,
                    "experiment": None, "headline": None,
                    "verdict": "unreadable", "detail": "receipt JSON is corrupt",
                    "numbers": "—", "code_sha": None,
                    "has_dated_html": False, "local_only": False,
                    "receipt_href": None,
                    "report_href": f"{ARCHIVE_URL}#{_anchor_for(date, slug, turn)}",
                })
                continue
            row = classify_run(data)
            row["date"] = date
            row["slug"] = slug
            row["turn"] = turn
            row["has_dated_html"] = False
            # Receipts are committed — this run is repo-backed, not local-only.
            row["local_only"] = False
            row["report_href"] = f"{ARCHIVE_URL}#{_anchor_for(date, slug, turn)}"
            row["receipt_href"] = RECEIPT_URL_BASE + p.name
            _stamp_provenance(row, data)
            by_key[key] = (mtime, row)

    # Newest-first by (mtime, date_stem, turn): the date breaks an mtime tie so a
    # fresh git clone (which loses mtimes) still orders by the run's own date,
    # and the turn stamp breaks the remaining tie between two passes of the same
    # day — otherwise a clone orders same-day turns arbitrarily.
    ordered = sorted(
        by_key.items(),
        key=lambda kv: (kv[1][0], kv[0][0], kv[0][2] or ""),
        reverse=True,
    )
    return [row for _, (_, row) in ordered]


def public_runs() -> list[dict]:
    """Committed runs a visitor can verify, newest first.

    ``scan_runs`` deliberately includes publisher-local ``~/.lab`` inputs for
    recovery. Those files are not a second public record and their ``file://``
    paths cannot work for anyone else, so every published surface crosses this
    boundary before counting, grouping, or comparing machines.
    """
    return [r for r in scan_runs() if not r.get("local_only")]


# ── run_ledger: the sanitized rows that ride in pot.json ─────────────────────
def _public_href(href: str | None) -> str | None:
    """Keep only http(s) hrefs in the public feed (the page's link-guard)."""
    return href if (isinstance(href, str) and _HTTP_RE.match(href)) else None


def _collapse_streaks(rows: list[dict]) -> list[dict]:
    """Collapse CONSECUTIVE newest-first rows sharing ``(milestone, verdict)``.

    Presentation grouping only (schema v5): a streak of repeated turns of the
    same milestone with the same verdict becomes its newest row plus
    ``group_count`` (how many runs it stands for) and ``group_first_date`` (the
    oldest date in the streak). A streak of one carries NEITHER field — a lone
    run is not a group, and the schema enforces ``group_count >= 2``.

    The grouping key includes the VERDICT, so a verdict change always breaks
    the streak by construction — a null after verified can never be hidden
    inside a green group. Non-adjacent same-milestone rows never merge; only
    consecutive rows do. Every underlying run remains in the archive index and
    the receipts ledger — this changes which rows ride in ``pot.json``, not
    what is on the books.

    A ``None`` milestone is an UNKNOWN identity, not a shared one: freeform
    runs and unreadable gap rows both carry ``milestone None``, and two
    adjacent such rows may be entirely different experiments. Grouping them
    would put a false "same experiment" claim on the rail, so rows without a
    named milestone never group (fail closed).

    The MACHINE is deliberately not in the key. Under a rotation the two boxes
    interleave, so keying on machine would forbid nearly every collapse — eight
    identical green rows a day, the exact wall this function exists to calm —
    and buy no honesty, because the verdict is already in the key: a null after
    a verified breaks the streak whichever box produced it. Merging agreements
    across machines is a true statement (the claim being grouped is the
    verdict), and it is disclosed two ways: ``group_machines`` lists the boxes a
    group spans, and ``detect_divergence`` surfaces the one case where the
    machine mattered — the boxes disagreeing along machine lines.

    Two things always break a streak besides the verdict: a calendar gap of
    more than a day (a missed day is a seam in the record and must not be
    smoothed inside an "×9 turns" chip) and, of course, a different milestone.
    """
    out: list[dict] = []
    members: list[set[str]] = []
    for row in rows:
        prev = out[-1] if out else None
        if prev is not None and row.get("milestone") is not None and (
            (prev.get("milestone"), prev.get("verdict"))
            == (row.get("milestone"), row.get("verdict"))
        ) and _within_a_day(row.get("date"), prev.get("group_first_date")
                            or prev.get("date")):
            prev["group_count"] = prev.get("group_count", 1) + 1
            prev["group_first_date"] = row.get("date")   # newest-first → oldest wins
            if row.get("machine"):
                members[-1].add(row["machine"])
        else:
            out.append(dict(row))
            members.append({row["machine"]} if row.get("machine") else set())

    for row, machines in zip(out, members):
        # Composition disclosure — only on rows that actually stand for a group,
        # and only when at least one member recorded which box ran it. A group
        # made entirely of pre-provenance runs stays bare, exactly as before.
        if row.get("group_count", 1) >= 2 and machines:
            row["group_machines"] = sorted(machines)
    return out


def _within_a_day(older: str | None, newer: str | None) -> bool:
    """True when two ``YYYY-MM-DD`` dates are the same day or consecutive days.

    The gap seam: a fully-missed day ends a streak. An unparseable date fails
    closed (no merge) — a row whose date we can't read cannot be asserted to be
    adjacent to anything.
    """
    if not isinstance(older, str) or not isinstance(newer, str):
        return False
    try:
        from datetime import date as _date
        gap = _date.fromisoformat(newer) - _date.fromisoformat(older)
    except ValueError:
        return False
    return 0 <= gap.days <= 1


def run_ledger(limit: int | None = None) -> list[dict]:
    """Newest-first sanitized rows for ``pot.json``'s ``reports`` array.

    Each row is ``{date, milestone, verdict, headline, href, receipt_url}`` —
    no config, no curves, no raw arrays leak into the feed — plus, on a row
    standing for a collapsed streak, ``group_count`` / ``group_first_date``
    (see ``_collapse_streaks``; the archive index page keeps every run).
    ``href`` opens the human-readable archive row; ``receipt_url`` opens the
    durable measurement evidence. Publisher-local ``~/.lab`` rows are recovery
    inputs, not public records, so they are omitted entirely rather than counted
    with an unusable ``file://`` link. ``unreadable`` and
    ``unscored`` rows are mapped to the schema's
    ``verified``/``null`` enum is NOT done here — the schema's ``report`` enum is
    extended to carry all four verdicts honestly. ``limit`` bounds the number
    of underlying RUNS considered (applied before grouping), not the number of
    grouped rows emitted.
    """
    rows = public_runs()
    if limit is not None:
        rows = rows[:limit]
    return _collapse_streaks([
        _prune({
            "date": r["date"],
            "milestone": r.get("milestone"),
            "verdict": r["verdict"],
            "headline": r.get("headline"),
            "href": _public_href(r.get("report_href")),
            "receipt_url": _public_href(r.get("receipt_href")),
            # Provenance, present only when the run recorded it.
            "machine": r.get("machine"),
            "at": r.get("at"),
        })
        for r in rows
    ])


def detect_divergence(rows: list[dict], now: str | None = None) -> list[dict]:
    """Milestones where the two machines are returning DIFFERENT verdicts.

    The compensating control for keeping the machine out of the collapse key
    (``_collapse_streaks``). Collapsing agreements across boxes is honest right
    up until the boxes stop agreeing — at which point the interesting fact is
    not any individual row but the pattern, and a pattern spread across eight
    rows a day is one no reader will assemble on their own.

    Fires only when the disagreement partitions PERFECTLY along machine lines:
    within the last 48 hours, a milestone run at least twice by each of two
    machines, where every run on box A got one verdict and every run on box B
    got another. That is the signature of a machine-specific problem — a driver,
    a build, a card — as opposed to flakiness, which scatters across both boxes
    and is correctly left to read as the noise it is.

    Inert until the declared cadence is effective: before both boxes are armed,
    "the machines disagree" is not yet a claim the lab is in a position to make.
    """
    if not cadence_is_effective():
        return []
    declared = {m for m in CADENCE.get("machines", []) if isinstance(m, str)}
    horizon = _days_ago(2, now)

    by_milestone: dict[str, dict[str, set[str]]] = {}
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        mid, machine, date = row.get("milestone"), row.get("machine"), row.get("date")
        if not mid or machine not in declared or not isinstance(date, str):
            continue
        if date < horizon:
            continue
        by_milestone.setdefault(mid, {}).setdefault(machine, set()).add(row["verdict"])
        counts.setdefault(mid, {})
        counts[mid][machine] = counts[mid].get(machine, 0) + 1

    out: list[dict] = []
    for mid in sorted(by_milestone):
        verdicts = by_milestone[mid]
        if len(verdicts) != 2:
            continue
        # Each box must be internally consistent — a box that returned two
        # different verdicts itself is flaky, not divergent.
        if any(len(v) != 1 for v in verdicts.values()):
            continue
        # ...and must have said it more than once, so one bad run on each side
        # can never look like a systematic split.
        if any(counts[mid][m] < 2 for m in verdicts):
            continue
        settled = {m: next(iter(v)) for m, v in verdicts.items()}
        if len(set(settled.values())) != 2:
            continue                                  # they agree — nothing to say
        out.append({"milestone": mid, "machines": dict(sorted(settled.items()))})
    return out


def _days_ago(days: int, now: str | None = None) -> str:
    from datetime import date as _date, timedelta
    today = _date.fromisoformat(now) if now else _date.fromisoformat(today_local())
    return (today - timedelta(days=days)).isoformat()


def _prune(row: dict) -> dict:
    """Drop the optional provenance keys that are ``None``.

    ``machine`` and ``at`` are absent-or-true: emitting ``"machine": null`` on
    the 39 pre-provenance runs would put a shape on the feed that reads like a
    field waiting to be filled, when the fact is that it was never recorded.
    """
    for key in ("machine", "at"):
        if row.get(key) is None:
            row.pop(key, None)
    return row


# ── render_index: the HTML page (reuses the report templates' calm CSS) ───────

#: A run of at least this many CONSECUTIVE same-milestone rows — in the global
#: newest-first ordering the index renders — condenses into one era band (a
#: <details> element). Below this, repetition is just cadence; at and above it,
#: it is a treadmill worth bundling. Chosen so a normal 2–3-turn day never
#: bands while every real 2026 treadmill streak (the shortest was ×5) does.
ERA_MIN_STREAK = 4

#: Honest labels for the two REAL treadmill eras, written from the receipts and
#: the fixes that ended them. Keyed by ``(milestone, first-date-prefix)`` where
#: "first date" is the band's OLDEST date; a band whose first date starts with
#: the prefix gets the label. Prefixes are deliberately loose enough to span
#: every band of their era — the schedulers' failures produced SEVERAL streaks
#: interrupted by other runs sneaking through, and each fragment deserves the
#: same diagnosis. The banding MECHANISM above is general; this dict is the
#: curated part: exactly the two failure modes the lab actually had, no more.
ANNOTATIONS: dict[tuple[str, str], str] = {
    # 40 M01 runs, June–July 2026: a stuck open-pointer made the scheduler fall
    # back to its safe default — the already-verified M01 rung — night after
    # night. Spans the ×5, ×8, ×5 and ×11 M01 bands of that stretch.
    ("M01", "2026-0"): (
        "the stuck-pointer era — the scheduler's safe default ran nightly; "
        "root-fixed by the portfolio rotation, PR #77"
    ),
    # 44 M02 runs, Aug 2–11 2026: a filename stem-slice parse bug livelocked
    # the fresh rotation into M01→M02 every turn for 9 days. Spans the ×19, ×6
    # and ×10 M02 bands of that stretch.
    ("M02", "2026-08-0"): (
        "the livelock era — a filename parse bug pinned the rotation for "
        "9 days; root-fixed in PR #97"
    ),
}

#: The one-line disclosure shown in the header region iff any band rendered —
#: the reader must never wonder whether condensation deleted anything.
ERA_NOTE = ("Repeated-run eras are bundled — every receipt is still here, "
            "expanded in place.")

_LEAF = {
    # Run verdicts describe the deterministic checker, not the separate human
    # milestone-promotion lifecycle exposed by pot.json v4.
    "verified": ("●", "machine check passed", "leaf"),
    "null":     ("◑", "null · folded grey leaf", "null"),
    "unscored": ("○", "unscored", "unscored"),
    "unreadable": ("⚠", "unreadable", "unreadable"),
}

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · archive</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 820px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase;
        opacity: 0.55; margin: 34px 0 10px; font-weight: 600; }}
  .lede {{ font-size: 16px; padding: 16px 20px; background: #fbf6ea;
           border-left: 3px solid #c89878; border-radius: 2px; margin-bottom: 8px; }}
  .note {{ font-size: 13px; opacity: 0.62; margin: 8px 0 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  td, th {{ text-align: left; padding: 8px 10px; vertical-align: top;
            border-bottom: 1px solid #e2d4ba; }}
  th {{ font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
        opacity: 0.5; font-weight: 600; }}
  .glyph {{ font-size: 15px; width: 1.4em; }}
  .leaf .glyph {{ color: #5f8b46; }}
  .null .glyph {{ color: #8a8f82; }}
  .unscored .glyph {{ color: #9b8a6e; }}
  .unreadable .glyph {{ color: #b06a45; }}
  tr.null {{ opacity: 0.78; }}                 /* folded grey leaf — muted but kept */
  .date {{ font-variant-numeric: tabular-nums; white-space: nowrap; opacity: 0.8; }}
  .mid {{ font-weight: 600; letter-spacing: 0.02em; }}
  .num {{ font-family: 'SF Mono', ui-monospace, Menlo, monospace; font-size: 12.5px; opacity: 0.85; }}
  .verd {{ font-size: 12px; letter-spacing: 0.03em; }}
  a.run {{ color: #7a4e2f; text-decoration: none; border-bottom: 1px dotted #c0a988; }}
  a.run:hover {{ color: #3a2e21; }}
  .flag {{ font-size: 11px; opacity: 0.55; margin-left: 6px; }}
  .footer {{ margin-top: 56px; padding-top: 18px; border-top: 1px solid #d6c0a2;
             opacity: 0.55; font-size: 12px; }}
  /* Era bands — a condensed treadmill streak. Muted on purpose: repetition is
     the least interesting thing on the page, so it takes the least ink. */
  tr.era > td {{ padding: 4px 0; }}
  details.era {{ background: #f1e7d2; border: 1px solid #e2d4ba; border-radius: 2px; }}
  details.era > summary {{ cursor: pointer; padding: 8px 10px; font-size: 13px;
                           opacity: 0.72; font-variant-numeric: tabular-nums; }}
  details.era > summary:hover {{ opacity: 1; }}
  details.era[open] > summary {{ border-bottom: 1px solid #e2d4ba; }}
  .era-label {{ font-size: 12.5px; font-style: italic; opacity: 0.68;
                padding: 6px 10px 2px; }}
  details.era table {{ margin: 0; }}
  figure.scoreboard {{ margin: 8px 0 4px; }}
  figure.scoreboard img {{ width: 100%; max-width: 100%; height: auto;
                           border-radius: 4px; border: 1px solid #e2d4ba; }}
  code {{ font-family: 'SF Mono', ui-monospace, Menlo, monospace; font-size: 12.5px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · the archive</h1>
  <div class="lede">{summary}</div>
{scoreboard}
  <p class="note">Two ledgers live here. A milestone's <b>green leaf</b> on the
  <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a> grades the
  <em>stem</em> — the curriculum. A <b>folded grey leaf</b> below grades a single
  <em>run</em>: a check ran and the number missed. They can legitimately
  disagree — a milestone can stand verified while an earlier messy run for it
  stays a null here, with its measured numbers kept on the books.</p>
{eranote}{groups}
  <div class="footer">
    {count} runs on record · newest first · generated {generated}.
    The calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>;
    the code is <a href="https://github.com/benskamps/windowsill-lab">windowsill-lab</a>.
  </div>
</div>
</body>
</html>
"""


def _row_html(run: dict) -> str:
    glyph, label, cls = _LEAF.get(run["verdict"], _LEAF["unscored"])
    date = html.escape(str(run.get("date") or "—"))
    headline = html.escape(str(run.get("headline") or run.get("experiment") or "—"))
    numbers = html.escape(str(run.get("numbers") or "—"))
    detail = html.escape(str(run.get("detail") or ""))
    verd = html.escape(label)
    receipt_href = run.get("receipt_href")
    href = run.get("report_href")
    slug = str(run.get("slug") or run.get("milestone") or "run").lower()
    anchor = html.escape(
        _anchor_for(str(run.get("date") or "undated"), slug, run.get("turn")),
        quote=True,
    )
    flag = ' <span class="flag">(local only — backfill pending)</span>' if run.get("local_only") else ""
    # The link cell: only ever a same-origin/href the index itself owns; the
    # public pot.json ledger separately strips non-http. textContent-equivalent
    # escaping (we escape every interpolated value above).
    if receipt_href:
        link = (f'<a class="run" href="{html.escape(receipt_href, quote=True)}">'
                f'receipt.json ↗</a>{flag}')
    elif href and run.get("local_only"):
        link = f'<a class="run" href="{html.escape(href, quote=True)}">local report ↗</a>{flag}'
    else:
        link = f'<span class="flag">receipt unavailable</span>{flag}'
    # The null's real numbers + detail are shown, never deleted.
    body = f'<span class="num">{numbers}</span>'
    if detail and detail != numbers:
        body += f'<br><span class="num" style="opacity:0.7">{detail}</span>'
    return (
        f'<tr class="{cls}" id="{anchor}">'
        f'<td class="glyph">{glyph}</td>'
        f'<td class="date">{date}</td>'
        f'<td><span class="verd">{verd}</span><br>{headline}</td>'
        f'<td>{body}</td>'
        f'<td>{link}</td>'
        f'</tr>'
    )


#: The one table header, shared by group tables and the nested table inside an
#: era band — so the expanded body of a band reads exactly like the open index.
_TABLE_HEADER = ('    <tr><th></th><th>date</th><th>run</th><th>numbers</th>'
                 '<th>evidence</th></tr>')


def _era_annotation(milestone: str, first_date: str) -> str | None:
    """The curated label for a band, or ``None`` for an uncurated streak.

    Matching is by milestone plus a startswith on the band's OLDEST date — see
    ``ANNOTATIONS`` for why prefixes rather than exact dates. An unmatched band
    still bands (the mechanism is general); it just carries count + dates only
    (the diagnosis is curated, never guessed).
    """
    for (mid, prefix), label in ANNOTATIONS.items():
        if mid == milestone and first_date.startswith(prefix):
            return label
    return None


def _era_items(runs: list[dict],
               era_min_streak: int | None) -> list[tuple[str, object]]:
    """Segment the GLOBAL newest-first run list into rows and era bands.

    Returns ``("run", row)`` and ``("band", [rows])`` items in order. A band is
    ``era_min_streak`` or more CONSECUTIVE rows sharing one named milestone —
    consecutive in the global ordering, so a single interleaved run of another
    slug breaks the streak (two fragments of the same treadmill separated by an
    interruption are two bands, or no band at all if each fragment is short:
    the seam in the record is kept, not smoothed). Rows with ``milestone None``
    never band — same fail-closed reasoning as ``_collapse_streaks``: freeform
    and unreadable rows share an UNKNOWN identity, not a common one.

    ``era_min_streak=None`` disables banding entirely; the unbundled render it
    produces is the reference surface the no-deletion test compares against.
    """
    items: list[tuple[str, object]] = []
    i, n = 0, len(runs)
    while i < n:
        mid = runs[i].get("milestone")
        j = i + 1
        while mid is not None and j < n and runs[j].get("milestone") == mid:
            j += 1
        if (mid is not None and era_min_streak is not None
                and j - i >= era_min_streak):
            items.append(("band", runs[i:j]))
        else:
            items.extend(("run", r) for r in runs[i:j])
        i = j
    return items


def _verdict_mix(rows: list[dict]) -> str:
    """``"19 verified"`` / ``"10 verified · 1 null"`` — a band's honest ledger.

    Every verdict present in the band is named with its count, in the fixed
    severity order; a verdict this module doesn't know still gets counted and
    shown (sorted, after the known ones) rather than silently dropped.
    """
    counts: dict[str, int] = {}
    for r in rows:
        v = str(r.get("verdict"))
        counts[v] = counts.get(v, 0) + 1
    known = ("verified", "null", "unscored", "unreadable")
    bits = [f"{counts[v]} {v}" for v in known if counts.get(v)]
    bits += [f"{counts[v]} {v}" for v in sorted(counts) if v not in known]
    return " · ".join(bits) if bits else "—"


def _band_html(rows: list[dict]) -> str:
    """One era band: a summary line over the SAME full rows, zero deleted.

    The collapsed face is one line — ``M02 × 19 · 2026-08-02 → 2026-08-07 ·
    19 verified`` — and the expanded body is the identical ``_row_html`` rows
    the index renders unbundled, inside a nested table with the same header:
    every anchor id, every receipt link, every real number survives verbatim
    (browsers auto-expand a ``<details>`` when a fragment inside it is
    navigated to, so published deep links still land). A curated annotation,
    when one matches, is the first body line.
    """
    milestone = str(rows[0].get("milestone"))
    first = str(rows[-1].get("date") or "—")     # newest-first → last row is oldest
    last = str(rows[0].get("date") or "—")
    summary = (f"{milestone} × {len(rows)} · {first} → {last} · "
               f"{_verdict_mix(rows)}")
    label = _era_annotation(milestone, first)
    note = (f'<div class="era-label">{html.escape(label)}</div>'
            if label else "")
    inner = "\n".join(_row_html(r) for r in rows)
    return (
        f'<tr class="era"><td colspan="5">'
        f'<details class="era"><summary>{html.escape(summary)}</summary>'
        f'{note}'
        f'<table>\n{_TABLE_HEADER}\n{inner}\n</table>'
        f'</details></td></tr>'
    )


def _group_html(milestone: str, items: list[tuple[str, object]]) -> str:
    head = html.escape(milestone)
    rows = "\n".join(
        _band_html(payload) if kind == "band" else _row_html(payload)
        for kind, payload in items
    )
    return (
        f'  <h2>{head}</h2>\n'
        f'  <table>\n'
        f'{_TABLE_HEADER}\n'
        f'{rows}\n'
        f'  </table>'
    )


def render_index(runs: list[dict] | None = None, *,
                 era_min_streak: int | None = ERA_MIN_STREAK) -> str:
    """Render the archive index to an HTML string (pure when ``runs`` given).

    Groups runs by milestone (newest milestone group first, by its newest run),
    keeps EVERY run — verified, null, unscored, unreadable — and HTML-escapes
    every interpolated value. A null row stays a muted folded-grey row that
    still shows its real numbers and links its report.

    Treadmill streaks — ``era_min_streak`` or more consecutive same-milestone
    rows in the global newest-first order — render as one era band whose
    expanded body contains the identical full rows (see ``_era_items`` /
    ``_band_html``): the page condenses the 2026 scheduler waste without
    deleting a byte of it. ``era_min_streak=None`` renders unbundled — that
    surface is what the row-count-invariant test compares against.
    """
    if runs is None:
        # The committed HTML is a PUBLIC archive. LAB_HOME is still scanned for
        # recovery and local inspection, but a publisher's raw cache is neither
        # a second run nor a URL a visitor can open.
        runs = public_runs()

    # Band FIRST, on the global order — an interruption by another slug must
    # break a streak even though the interrupted fragments end up rendered
    # adjacent inside their milestone's group — THEN group by milestone,
    # preserving newest-first order within each group.
    items = _era_items(runs, era_min_streak)
    any_band = any(kind == "band" for kind, _ in items)
    groups: dict[str, list[tuple[str, object]]] = {}
    order: list[str] = []
    for kind, payload in items:
        row = payload[0] if kind == "band" else payload
        key = row.get("milestone") or "unfiled"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((kind, payload))

    n_verified = sum(1 for r in runs if r["verdict"] == "verified")
    n_null = sum(1 for r in runs if r["verdict"] == "null")
    n_unscored = sum(1 for r in runs if r["verdict"] == "unscored")
    n_unreadable = sum(1 for r in runs if r["verdict"] == "unreadable")
    verdict_counts = [
        f"{n_verified} passing check" + ("s" if n_verified != 1 else ""),
        f"{n_null} null" + ("s" if n_null != 1 else ""),
    ]
    if n_unscored:
        verdict_counts.append(
            f"{n_unscored} unscored run" + ("s" if n_unscored != 1 else "")
        )
    if n_unreadable:
        verdict_counts.append(
            f"{n_unreadable} unreadable run" + ("s" if n_unreadable != 1 else "")
        )
    summary = html.escape(
        f"Every committed run on the public record — {len(runs)} so far, "
        + ", ".join(verdict_counts)
        + "."
    )
    groups_html = "\n".join(_group_html(m, groups[m]) for m in order)
    # The disclosure rides exactly when a band does — a page with no bands
    # must not carry a sentence about bundling that happened to nobody.
    eranote = (f'  <p class="note">{html.escape(ERA_NOTE)}</p>\n'
               if any_band else "")
    # Local date, matching how runs are dated (publish.today_local) — an evening
    # regen must not stamp the archive "tomorrow" in UTC.
    generated = today_local()
    return INDEX_TEMPLATE.format(
        summary=summary, scoreboard=_scoreboard_section(), groups=groups_html,
        count=len(runs), generated=generated, eranote=eranote,
    )


def write_index() -> Path:
    """Write the archive index to ``reports/index.html`` and return its path.

    The nightly's ``git add -A reports/`` then commits it, so the archive is a
    permanent, deep-linkable companion to the windowsill page.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "index.html"
    out.write_text(render_index(), encoding="utf-8")
    return out
