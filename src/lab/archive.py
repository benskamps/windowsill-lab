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

import html
import json
import re
from pathlib import Path

from .publish import (
    ARCHIVE_URL, LAB_HOME, RECEIPTS_DIR, RECEIPT_URL_BASE, REPORTS_DIR,
    REPORT_URL_BASE, _DATE_GLOB, _date_of, _milestone_for, _peak_t,
    _receipt_filename, _slug_for, today_local,
)

# Where the index lands. The nightly already ``git add -A reports/`` so writing
# reports/index.html here makes it the committed, deep-linkable archive page.
INDEX_HTML = REPORTS_DIR / "index.html"

# htmlpreview deep-link for a dated HTML report (resolves once pushed).
_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)

# Map a report's "kind" off its experiment tag → a coarse family for grouping
# and headlines. fss = finite-size scaling (M02), collapse = data collapse
# (M03), ising = the single-lattice χ-sweep (M01 / legacy bare dumps).
def _kind_for(report: dict) -> str:
    exp = str(report.get("experiment", ""))
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
    return {
        "milestone": milestone,
        "kind": kind,
        "experiment": report.get("experiment"),
        "headline": report.get("headline"),
        "verdict": verdict,
        "detail": detail,
        "numbers": _numbers_for(report, kind),
        "code_sha": report.get("code_sha"),
    }


def _anchor_for(date: str, slug: str) -> str:
    """Stable, URL-safe archive row anchor for one dated run."""
    safe = re.sub(r"[^a-z0-9-]+", "-", f"{date}-{slug}".lower()).strip("-")
    return f"run-{safe}"


def _href_for(date: str, slug: str, is_repo: bool, has_dated_html: bool,
              local_path: Path) -> str:
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
        return f"{ARCHIVE_URL}#{_anchor_for(date, slug)}"
    # Local-only: a file path to the dated JSON cache. Not an http link.
    return local_path.as_uri() if local_path.exists() else str(local_path)


def scan_runs() -> list[dict]:
    """Every run on record across the repo ``reports/`` and ``~/.lab``.

    Globs the same ``<date>*.json`` pattern as ``publish._report_jsons``,
    dedupes by ``(date, slug)`` PREFERRING the committed ``reports/`` copy (and
    flagging ``local_only`` for runs that exist only in ``~/.lab``), keeps a
    corrupt report JSON as an honest ``unreadable`` gap row, and sorts
    newest-first by ``(mtime, date_stem)`` so a stale future-dated file can't
    masquerade as the latest. Each row carries ``has_dated_html`` +
    ``report_href`` for deep-linking.
    """
    # Per (date, slug): keep the best file. Repo beats ~/.lab; within the same
    # priority, the newest mtime wins. Value = (mtime, row).
    by_key: dict[tuple[str, str], tuple[float, dict]] = {}

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
                key = (date, p.stem)
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
            key = (date, slug)
            has_html = (directory / f"{date}-{slug}.html").exists()
            row = classify_run(data)
            row["date"] = date
            row["slug"] = slug
            row["has_dated_html"] = has_html
            row["local_only"] = not is_repo
            row["report_href"] = _href_for(date, slug, is_repo, has_html, p)
            receipt = RECEIPTS_DIR / _receipt_filename(date, slug)
            row["receipt_href"] = (
                RECEIPT_URL_BASE + _receipt_filename(date, slug)
                if receipt.exists() else None
            )

            cur = by_key.get(key)
            cur_is_repo = (not cur[1]["local_only"]) if cur else False
            if cur is None or (is_repo and not cur_is_repo) or \
               (is_repo == cur_is_repo and mtime > cur[0]):
                by_key[key] = (mtime, row)

    # Newest-first by (mtime, date_stem): the date breaks an mtime tie so a
    # fresh git clone (which loses mtimes) still orders by the run's own date.
    ordered = sorted(by_key.items(), key=lambda kv: (kv[1][0], kv[0][0]), reverse=True)
    return [row for _, (_, row) in ordered]


# ── run_ledger: the sanitized rows that ride in pot.json ─────────────────────
def _public_href(href: str | None) -> str | None:
    """Keep only http(s) hrefs in the public feed (the page's link-guard)."""
    return href if (isinstance(href, str) and _HTTP_RE.match(href)) else None


def run_ledger(limit: int | None = None) -> list[dict]:
    """Newest-first sanitized rows for ``pot.json``'s ``reports`` array.

    Each row is ONLY ``{date, milestone, verdict, headline, href,
    receipt_url}`` — no config, no curves, no raw arrays leak into the feed.
    ``href`` opens the human-readable archive row; ``receipt_url`` opens the
    durable measurement evidence. A non-http href (a local-only ~/.lab path)
    becomes ``None`` so the page never tries to link it. ``unreadable`` and
    ``unscored`` rows are mapped to the schema's
    ``verified``/``null`` enum is NOT done here — the schema's ``report`` enum is
    extended to carry all four verdicts honestly.
    """
    rows = scan_runs()
    if limit is not None:
        rows = rows[:limit]
    return [
        {
            "date": r["date"],
            "milestone": r.get("milestone"),
            "verdict": r["verdict"],
            "headline": r.get("headline"),
            "href": _public_href(r.get("report_href")),
            "receipt_url": _public_href(r.get("receipt_href")),
        }
        for r in rows
    ]


# ── render_index: the HTML page (reuses the report templates' calm CSS) ───────
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
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · the archive</h1>
  <div class="lede">{summary}</div>
  <p class="note">Two honesties live here. A milestone's <b>green leaf</b> on the
  <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a> grades the
  <em>stem</em> — the curriculum. A <b>folded grey leaf</b> below grades a single
  <em>run</em>: a check ran and the number missed. They can legitimately
  disagree — a milestone can stand verified while an earlier messy run for it
  stays an honest null here, with its real numbers kept on the books.</p>
{groups}
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
    anchor = html.escape(_anchor_for(str(run.get("date") or "undated"), slug), quote=True)
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


def _group_html(milestone: str, runs: list[dict]) -> str:
    head = html.escape(milestone)
    rows = "\n".join(_row_html(r) for r in runs)
    return (
        f'  <h2>{head}</h2>\n'
        f'  <table>\n'
        f'    <tr><th></th><th>date</th><th>run</th><th>numbers</th><th>evidence</th></tr>\n'
        f'{rows}\n'
        f'  </table>'
    )


def render_index(runs: list[dict] | None = None) -> str:
    """Render the archive index to an HTML string (pure when ``runs`` given).

    Groups runs by milestone (newest milestone group first, by its newest run),
    keeps EVERY run — verified, null, unscored, unreadable — and HTML-escapes
    every interpolated value. A null row stays a muted folded-grey row that
    still shows its real numbers and links its report.
    """
    if runs is None:
        runs = scan_runs()

    # Group by milestone, preserving newest-first order within each group.
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for r in runs:
        key = r.get("milestone") or "unfiled"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    n_verified = sum(1 for r in runs if r["verdict"] == "verified")
    n_null = sum(1 for r in runs if r["verdict"] == "null")
    summary = html.escape(
        f"Every run the lab has on record — {len(runs)} so far, "
        f"{n_verified} passing checks, {n_null} honest null"
        + ("s" if n_null != 1 else "")
        + ". Nothing hidden, nothing deleted."
    )
    groups_html = "\n".join(_group_html(m, groups[m]) for m in order)
    # Local date, matching how runs are dated (publish.today_local) — an evening
    # regen must not stamp the archive "tomorrow" in UTC.
    generated = today_local()
    return INDEX_TEMPLATE.format(
        summary=summary, groups=groups_html, count=len(runs), generated=generated,
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
