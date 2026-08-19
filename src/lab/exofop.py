"""ExoFOP community candidates — the table the catalog crosscheck could not read.

A04's :func:`lab.a04.catalog_crosscheck` asks the NASA Exoplanet Archive two
questions: is this star a TOI, and is it a confirmed planet host. Both are
*curated* tables. ExoFOP carries a third one that neither covers — **CTOIs**,
community TESS Objects of Interest: candidates uploaded by anyone working the
public light curves, most of them never promoted to a TOI.

That hole cost the hunt three leads in one week. TIC 287328866 was filed twice
in 2019 as CTOI .01 (P = 2.063194 d) and .02 (P = 2.079861 d) — two entries on
one star at near-identical ~2.07 d periods with different depths, which is what
an eclipsing binary's primary and secondary look like when they are submitted
separately. The 2026-08-18 hunt re-found it at the 1.038 d P/2 alias, and the
crosscheck returned ``known_toi: null, known_planet: null`` because CTOIs are
not in either table it reads.

### Why the whole table instead of a per-target query

The table is ~1.4 MB for ~4000 rows — small enough to fetch once and keep. A
survey loop asking per target would make one network round-trip per star inside
the hot path, on two machines, with a failure mode (a slow or down endpoint)
that silently degrades every row's evidence. Fetching once and caching turns the
lookup into a dict access that works offline, which is also what makes it
testable without a network.

The cache carries the fetch timestamp and refreshes past CTOI_MAX_AGE_DAYS. A
stale table is a real hazard for a *negative* answer — "no CTOI" from a table
six months old is a weaker statement than "no CTOI" from one fetched today — so
every lookup reports the table's age and the caller records it.

### What a CTOI match means, and what it does not

A CTOI is not a planet, not a TOI, and not a refutation. It means somebody else
already filed this signal. The right disposition is `ctoi-known`: the row leaves
the shelf because it is not a fresh lead, without any claim about what the
signal IS. Promotion, refutation and confirmation all remain human work.

Alias-aware by construction: a detection at P must match a CTOI at 2P (the
TIC 287328866 case), at P/2, and at the integer harmonics in between, or the
gate re-opens the same hole one octave down.
"""
from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path

from .labhome import CACHE as LAB_CACHE

#: The whole community candidate table, CSV. Documented ExoFOP bulk endpoint.
CTOI_CSV_URL = "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?output=csv"

CACHE_DIR = LAB_CACHE / "exofop"
CTOI_CSV = CACHE_DIR / "ctoi.csv"
CTOI_META = CACHE_DIR / "ctoi.meta.json"

#: Refresh the cached table when it is older than this. Two weeks: CTOI
#: submissions trickle rather than flood, and a fortnight-old negative is still
#: a defensible negative when its age is reported alongside it.
CTOI_MAX_AGE_DAYS = 14.0

#: Period match tolerance, fractional. Matches A04's PERIOD_TOL_FRAC so
#: "the same period" means one thing across the whole pipeline.
PERIOD_TOL_FRAC = 0.01

#: Integer aliases tested in both directions: a detection at P is compared
#: against each CTOI period P_c as P*n vs P_c and P vs P_c*n. n = 2 is the case
#: that actually bit; 3 and 4 cost nothing and close the octave below.
ALIAS_HARMONICS = (1, 2, 3, 4)

#: Column names in the ExoFOP CSV. Kept in one place because they are somebody
#: else's schema: when the header changes, this is the line that changes.
COL_TIC = "TIC ID"
COL_CTOI = "CTOI"
COL_PERIOD = "Period (days)"
COL_DEPTH_PPM = "Depth ppm"
COL_DURATION_HR = "Duration (hrs)"
COL_PROMOTED = "Promoted to TOI"
COL_USER_DISP = "User Disposition"
COL_TFOPWG_DISP = "TFOPWG Disposition"


def _as_float(value):
    try:
        out = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return out if out == out else None          # NaN -> None


def cache_age_days(now: float | None = None) -> float | None:
    """Age of the cached table in days, or None when there is no cache."""
    if not CTOI_META.exists():
        return None
    try:
        stamp = float(json.loads(CTOI_META.read_text())["fetched_unix"])
    except (ValueError, KeyError, OSError, json.JSONDecodeError):
        return None
    return ((now if now is not None else time.time()) - stamp) / 86400.0


def fetch_ctoi_csv(deadline: float | None = None, force: bool = False,
                   max_age_days: float = CTOI_MAX_AGE_DAYS) -> str:
    """The CTOI table as CSV text, from cache when it is fresh enough.

    A failed refresh with a stale cache on disk returns the STALE cache rather
    than raising: a lookup against an old table plus a reported age is more
    useful to a hunt than no lookup at all. A failed refresh with no cache is a
    real failure and propagates.
    """
    age = cache_age_days()
    if not force and CTOI_CSV.exists() and age is not None and age <= max_age_days:
        return CTOI_CSV.read_text(encoding="utf-8", errors="replace")
    from . import a01                       # local: shares A01's HTTP path
    try:
        raw = a01._request(CTOI_CSV_URL, deadline=deadline)
    except Exception:                       # noqa: BLE001 — see docstring
        if CTOI_CSV.exists():
            return CTOI_CSV.read_text(encoding="utf-8", errors="replace")
        raise
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CTOI_CSV.write_text(text, encoding="utf-8")
    CTOI_META.write_text(json.dumps({"fetched_unix": time.time(),
                                     "url": CTOI_CSV_URL,
                                     "bytes": len(text)}))
    return text


def parse_ctoi_csv(text: str) -> dict[str, list[dict]]:
    """CSV text -> ``{tic: [row, ...]}`` with only the fields the gate uses.

    Rows whose TIC will not parse as an integer are dropped rather than kept
    under a garbage key: a malformed line must not become a phantom candidate.
    """
    table: dict[str, list[dict]] = {}
    for raw in csv.DictReader(io.StringIO(text)):
        tic_raw = (raw.get(COL_TIC) or "").strip()
        try:
            tic = str(int(float(tic_raw)))
        except (TypeError, ValueError):
            continue
        table.setdefault(tic, []).append({
            "ctoi": (raw.get(COL_CTOI) or "").strip() or None,
            "period_days": _as_float(raw.get(COL_PERIOD)),
            "depth_ppm": _as_float(raw.get(COL_DEPTH_PPM)),
            "duration_hours": _as_float(raw.get(COL_DURATION_HR)),
            "promoted_to_toi": (raw.get(COL_PROMOTED) or "").strip() or None,
            "user_disposition": (raw.get(COL_USER_DISP) or "").strip() or None,
            "tfopwg_disposition": (raw.get(COL_TFOPWG_DISP) or "").strip() or None,
        })
    return table


def alias_match(detected_period: float, catalog_period: float,
                harmonics=ALIAS_HARMONICS,
                tol: float = PERIOD_TOL_FRAC) -> int | None:
    """Signed harmonic relating two periods, or None.

    Returns ``+n`` when ``detected * n`` matches the catalog period (our
    detection is the catalog signal's 1/n alias — the TIC 287328866 case, n=2),
    ``-n`` when ``catalog * n`` matches ours, and ``1`` for a direct match.
    """
    if not detected_period or not catalog_period:
        return None
    if abs(detected_period / catalog_period - 1.0) <= tol:
        return 1
    for n in harmonics:
        if n == 1:
            continue
        if abs(detected_period * n / catalog_period - 1.0) <= tol:
            return n
        if abs(catalog_period * n / detected_period - 1.0) <= tol:
            return -n
    return None


def ctoi_crosscheck(tic: str, detected_period_days: float | None = None,
                    deadline: float | None = None,
                    table: dict[str, list[dict]] | None = None) -> dict:
    """Does ExoFOP already carry this star as a community candidate?

    ``table`` short-circuits the fetch (tests, and any caller that already holds
    the parsed table). Otherwise the cached CSV is used or refreshed.

    Reports EVERY CTOI on the star, and separately the subset whose period is
    commensurate with the detection. Two CTOIs on one star at nearly the same
    period is itself a tell — that is what a binary's primary and secondary look
    like when filed separately — so ``n_ctoi`` is reported even when nothing
    matches the detected period.
    """
    out = {"tic": str(tic), "known_ctoi": None, "ctoi_period_days": None,
           "ctoi_alias_n": None, "n_ctoi": 0, "ctoi_rows": [],
           "matched_rows": [], "table_age_days": None, "lookup_error": None}
    try:
        if table is None:
            table = parse_ctoi_csv(fetch_ctoi_csv(deadline=deadline))
            out["table_age_days"] = cache_age_days()
    except Exception as exc:                # noqa: BLE001 — never sink a survey
        out["lookup_error"] = type(exc).__name__
        return out
    rows = table.get(str(int(float(str(tic).strip())))) if str(tic).strip() else None
    if not rows:
        return out
    out["n_ctoi"] = len(rows)
    out["ctoi_rows"] = rows
    if detected_period_days is None:
        return out
    matched = []
    for row in rows:
        n = alias_match(float(detected_period_days), row["period_days"] or 0.0)
        if n is not None:
            matched.append(dict(row, alias_n=n))
    if matched:
        # The direct match wins over an alias; among aliases, the lowest order.
        best = min(matched, key=lambda r: abs(r["alias_n"]))
        out["matched_rows"] = matched
        out["known_ctoi"] = best["ctoi"]
        out["ctoi_period_days"] = best["period_days"]
        out["ctoi_alias_n"] = best["alias_n"]
    return out
