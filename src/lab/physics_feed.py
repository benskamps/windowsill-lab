"""Build ``physics-latest.json`` — the compact, plottable physics feed.

The windowsill page's calm face narrates the physics but never *shows* it: the
real χ(T) susceptibility spike, the |m|(T) magnetization landing on Onsager's
exact 1944 curve, and — the iconic image — the 128×128 spin lattice ordered,
near-critical, and disordered, all sit unplotted inside a 600 KB report JSON.

This module distills the newest M01 heartbeat report into a tiny (~8 KB) feed
the page can fetch and render: the six measured arrays, both the raw and
equilibrium-qualified χ peaks, disclosed quality exclusions, and the three
lattice snapshots bit-packed to base64 (each 128×128 ±1 lattice → one bit per
site → 2 KB → base64) beside ``snapshot_peak_t``, the temperature of the middle
frame the engine actually rendered. Nothing is fabricated — measurements are
copied from a provenance-stamped run, while the quality decision is re-derived by
the same shared guard as the checker. The source report is named so a reader can
diff it.

Kept standard-library-only (no torch, no matplotlib) so it stays cheap and the
pure builder is unit-tested without the scientific stack. Written by ``publish``
on every run, so the nightly keeps the physics face as fresh as the plant.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from pathlib import Path

from .m01_quality import assess_m01_quality
from .atomic import atomic_write_text

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"
from .labhome import LAB_HOME
PHYSICS_JSON = REPO_ROOT / "physics-latest.json"   # committed feed the page reads

# Bump when the feed contract changes in a way the page must adapt to.
PHYSICS_SCHEMA = 2

# Onsager's exact 2D Ising critical temperature (1944) — the calibration target.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.269185

_DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
_M01_EXPERIMENT = "M01-ising-verification"

# A receipt filename is ``run-<date>[-<hhmm>]-<slug>.json`` (turn-stamping landed
# 2026-08-02); the full report it was distilled from is ``<date>-<slug>.json``.
# The turn stamp lives ONLY in the receipt name — ``render._commit_report`` writes
# one report per (date, slug) and lets a same-day re-run overwrite it, while the
# receipt is stamped so two turns are two receipts. So recovering the raw name is
# a parse, not a slice: strip ``run-``, then strip a four-digit turn group if one
# is there. The four-digit guard is structural, not a convention — slugs are
# milestone ids or ``run`` and therefore always start with a letter, so this can
# never eat a slug. Mirrors ``publish._split_receipt_stem`` without importing it,
# for the same reason ``_date_of`` is duplicated here: this module is the cheap,
# stdlib-only feed builder and does not drag the publisher in behind it.
_RECEIPT_TURN_RE = re.compile(r"^\d{4}-(?=.)")

# The measured arrays we lift verbatim (name in report → name in feed). Each is
# a per-temperature list parallel to ``T``; a missing one is simply omitted.
_CURVES = ("abs_mag", "abs_mag_err", "chi", "chi_abs", "energy", "specific_heat")


def _date_of(path: Path) -> str:
    stem = path.stem
    return stem[4:14] if stem.startswith("run-") else stem[:10]


def _is_m01_report(data: dict) -> bool:
    """True for an M01 χ-sweep, including legacy reports without an identity."""
    return (
        ("experiment" not in data or data.get("experiment") == _M01_EXPERIMENT)
        and isinstance(data.get("T"), list)
        and isinstance(data.get("chi"), list)
        and len(data["T"]) == len(data["chi"])
        and len(data["T"]) > 1
    )


def _is_snapshot_report(data: dict) -> bool:
    """True for an M01 report that also carries full lattice snapshots."""
    return _is_m01_report(data) and isinstance(data.get("snapshots"), dict)


def _source_rel(path: Path, reports_dir: Path) -> str:
    try:
        within_reports = path.relative_to(reports_dir)
    except ValueError:
        return path.name
    return (Path("reports") / within_reports).as_posix()


def _newest_m01_report(reports_dir: Path = REPORTS_DIR,
                       lab_home: Path = LAB_HOME) -> tuple[dict, str] | None:
    """Newest M01 sweep from full local reports or durable public receipts."""
    paths: list[tuple[Path, Path]] = []
    for directory in (reports_dir, lab_home):
        if directory.exists():
            paths.extend((path, directory) for path in directory.glob(f"{_DATE_GLOB}*.json"))
    receipts_dir = reports_dir / "receipts"
    if receipts_dir.exists():
        paths.extend(
            (path, reports_dir)
            for path in receipts_dir.glob(f"run-{_DATE_GLOB}*.json")
        )

    best: tuple[float, str, dict, Path, Path] | None = None
    for path, source_root in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not _is_m01_report(data):
            continue
        key = (path.stat().st_mtime, _date_of(path))
        if best is None or key > (best[0], best[1]):
            best = (key[0], key[1], data, path, source_root)
    if best is None:
        return None
    _, _, data, path, source_root = best
    source_rel = (
        _source_rel(path, reports_dir)
        if source_root == reports_dir
        else path.name
    )
    return data, source_rel


def _newest_snapshot_report(reports_dir: Path = REPORTS_DIR,
                            lab_home: Path = LAB_HOME) -> tuple[dict, str] | None:
    """The most recently written report that carries lattice snapshots.

    Ordered by ``(mtime, date_stem)`` so a fresh clone (identical mtimes) still
    picks the latest-dated run, mirroring ``publish._newest_report``. Returns
    ``(report_dict, "reports/<name>")`` or ``None`` when no snapshot report
    exists yet.
    """
    best: tuple[float, str, dict, Path] | None = None
    for directory in (reports_dir, lab_home):
        if not directory.exists():
            continue
        for path in directory.glob(f"{_DATE_GLOB}*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not _is_snapshot_report(data):
                continue
            key = (path.stat().st_mtime, _date_of(path))
            if best is None or key > (best[0], best[1]):
                best = (key[0], key[1], data, path)
    if best is None:
        return None
    _, _, data, path = best
    rel = f"reports/{path.name}" if path.parent == reports_dir else path.name
    return data, rel


def _snapshot_digest(snapshots: dict) -> str:
    canonical = json.dumps(
        snapshots, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _attested_snapshot_digest(report: dict) -> str | None:
    receipt = report.get("public_receipt")
    if not isinstance(receipt, dict):
        return None
    omitted = receipt.get("omitted")
    if not isinstance(omitted, list):
        return None
    for item in omitted:
        if (
            isinstance(item, dict)
            and item.get("path") == "snapshots"
            and isinstance(item.get("sha256"), str)
        ):
            return item["sha256"]
    return None


def _raw_report_names(receipt_name: str) -> list[str]:
    """Filenames the full report behind ``run-<date>[-<hhmm>]-<slug>.json`` may use.

    Turn-stamped first (the parsed ``<date>-<slug>.json``, which is what
    ``render._commit_report`` actually writes), then the literal ``run-``-stripped
    name for the pre-2026-08-02 layout where the two were the same string. For a
    legacy unstamped receipt both candidates ARE that same string, so the older
    behaviour is preserved exactly and only the stamped case gains a hit.

    This is the seam that broke silently: a blind ``name[4:]`` kept the ``2100-``
    of ``run-2026-08-30-2100-m01.json`` and looked for a file that has never
    existed on any box, so attestation could not run and the page served the
    2026-08-01 lattices under a 2026-08-30 provenance line for 33 days while three
    M01 turns computed fresh ones and discarded them. Failure was invisible
    because the miss is indistinguishable from "no local raw report here" — the
    honest carry-forward path downstream then labelled the stale panels correctly
    and nothing ever raised.
    """
    stripped = receipt_name[len("run-"):]
    # The turn stamp sits AFTER the date, so the date has to come off before the
    # four-digit group is looked for — otherwise the year itself matches it.
    date, rest = stripped[:10], stripped[11:]
    names = [stripped]
    if rest:
        names.insert(0, f"{date}-{_RECEIPT_TURN_RE.sub('', rest, count=1)}")
    return list(dict.fromkeys(names))


def _attested_raw_snapshots(report: dict, source_rel: str,
                            reports_dir: Path, lab_home: Path) -> dict | None:
    """Load receipt-omitted snapshots only when their recorded digest matches."""
    expected = _attested_snapshot_digest(report)
    source_name = Path(source_rel).name
    if expected is None or not source_name.startswith("run-"):
        return None
    for raw_name in _raw_report_names(source_name):
        for directory in (reports_dir, lab_home):
            path = directory / raw_name
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            snapshots = candidate.get("snapshots")
            if (
                _is_snapshot_report(candidate)
                and isinstance(snapshots, dict)
                and _snapshot_digest(snapshots) == expected
            ):
                return snapshots
    return None


def _unpack_snapshots(packed: dict, lattice_L: int) -> dict | None:
    """Reconstruct the canonical raw snapshot object for receipt verification."""
    if lattice_L < 1:
        return None
    raw_snapshots: dict[str, list[list[int]]] = {}
    n_sites = lattice_L * lattice_L
    expected_bytes = (n_sites + 7) // 8
    padding_bits = expected_bytes * 8 - n_sites
    for key, encoded in packed.items():
        if not isinstance(encoded, str):
            return None
        try:
            temp = float(key)
            blob = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError):
            return None
        if len(blob) != expected_bytes:
            return None
        if padding_bits and blob[-1] & ((1 << padding_bits) - 1):
            return None
        spins = [
            1 if blob[i // 8] & (1 << (7 - (i % 8))) else -1
            for i in range(n_sites)
        ]
        raw_snapshots[f"T={temp:.3f}"] = [
            spins[start:start + lattice_L]
            for start in range(0, n_sites, lattice_L)
        ]
    return raw_snapshots


def _attested_packed_snapshots(report: dict,
                               previous_feed: dict | None) -> tuple[dict, int] | None:
    """Reuse an existing compact lattice only when the receipt attests it."""
    expected = _attested_snapshot_digest(report)
    if expected is None or not isinstance(previous_feed, dict):
        return None
    previous_m01 = previous_feed.get("m01")
    if not isinstance(previous_m01, dict):
        return None
    packed = previous_m01.get("snapshots")
    lattice_L = previous_m01.get("snapshot_L")
    if (
        not isinstance(packed, dict)
        or not isinstance(lattice_L, int)
        or isinstance(lattice_L, bool)
    ):
        return None
    reconstructed = _unpack_snapshots(packed, lattice_L)
    if reconstructed is None or _snapshot_digest(reconstructed) != expected:
        return None
    return packed, lattice_L


def _carried_stale_snapshots(
    previous_feed: dict | None,
) -> tuple[dict, int, str, str] | None:
    """Previous feed's packed lattices, labeled for disclosed carry-forward.

    When the newest receipt cannot attest the previous feed's lattices (a
    rebuild on a box without the raw report, or a receipt with no snapshot
    digest), the page's triptych would otherwise go dark. The previous
    lattices ride forward instead — but only when they still unpack cleanly
    AND their origin run can be named, so the feed labels them
    (``snapshots_source_report`` + ``snapshots_date``) rather than presenting
    them as this run's evidence. A prior carry's labels propagate, so the
    named origin is always the run that produced the lattices.
    """
    if not isinstance(previous_feed, dict):
        return None
    previous_m01 = previous_feed.get("m01")
    if not isinstance(previous_m01, dict):
        return None
    packed = previous_m01.get("snapshots")
    lattice_L = previous_m01.get("snapshot_L")
    if (
        not isinstance(packed, dict)
        or not packed
        or not isinstance(lattice_L, int)
        or isinstance(lattice_L, bool)
    ):
        return None
    if _unpack_snapshots(packed, lattice_L) is None:
        return None
    source = previous_m01.get("snapshots_source_report") or previous_m01.get("source_report")
    date = previous_m01.get("snapshots_date") or previous_m01.get("date")
    if not isinstance(source, str) or not isinstance(date, str):
        return None
    return packed, lattice_L, source, date


def _set_snapshot_peak_t(m01: dict, value: object) -> None:
    """Record the middle frame's temperature, when its source declared one.

    ``snapshot_peak_t`` describes the LATTICES, not the run: it is the temperature
    of the frame the page captions "near the tipping point", chosen by the engine
    from that run's own χ' curve (``ising.snapshot_indices``). So it travels with
    whichever lattices reach the feed — this run's value when the lattices are
    this run's, the previous feed's when they carry forward disclosed-stale — and
    is never re-derived here, because a temperature derived from THIS run's curve
    beside ANOTHER run's lattices is exactly the mislabel this field exists to
    close. Reports from before the engine declared it omit the field entirely, and
    the page keeps its existing fallback of captioning the delivered key nearest
    T_c.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    if not math.isfinite(value):
        return
    m01["snapshot_peak_t"] = round(float(value), 4)


def pack_lattice(rows: list[list[int]]) -> str:
    """Bit-pack a square ±1 spin lattice (row-major) to base64.

    ``+1`` → set bit, ``-1`` (or ``0``) → clear bit, MSB-first within each byte,
    zero-padded to a byte boundary. A 128×128 lattice → 2048 bytes → base64. The
    decoder on the page reverses this exactly.
    """
    bits = bytearray()
    acc = 0
    nbits = 0
    for row in rows:
        for v in row:
            acc = (acc << 1) | (1 if v > 0 else 0)
            nbits += 1
            if nbits == 8:
                bits.append(acc)
                acc = 0
                nbits = 0
    if nbits:
        bits.append(acc << (8 - nbits))
    return base64.b64encode(bytes(bits)).decode("ascii")


def build_feed(reports_dir: Path = REPORTS_DIR,
               lab_home: Path = LAB_HOME,
               provenance: dict | None = None,
               previous_feed: dict | None = None) -> dict | None:
    """Assemble the physics feed dict from the newest M01 report or receipt.

    The feed's ``provenance`` sits beside ``generated_from`` and therefore
    describes THAT RUN: the selected report's own provenance always wins.
    ``provenance`` (e.g. ``publish.provenance()``) is only a fallback for legacy
    reports that carry none — it describes the box doing the publishing, which is
    not the same claim. Letting it win mislabels a run with whatever environment
    happened to republish it, most visibly on the degraded path where an
    experiment fails and ``publish`` merely refreshes an older run's feed. A public receipt may reuse
    packed snapshots from ``previous_feed``, but only when its omission digest
    attests the reconstructed lattice exactly; when attestation fails or is
    absent, the previous lattices carry forward labeled with
    ``snapshots_source_report`` + ``snapshots_date`` so stale panels are
    disclosed instead of dark. Returns ``None`` when no M01 sweep exists.
    """
    found = _newest_m01_report(reports_dir, lab_home)
    if found is None:
        return None
    rep, source_rel = found

    # The shape gate checks lists, not elements — a non-numeric entry is "no
    # usable M01 sweep", not a crash of the publish path.
    try:
        T = [round(float(t), 4) for t in rep["T"]]
        chi = [float(c) for c in rep["chi"]]
    except (TypeError, ValueError, OverflowError):
        return None
    cfg = rep.get("config", {}) or {}
    quality = assess_m01_quality(rep)
    peak_t = quality["peak_t"]
    raw_peak_t = T[max(range(len(chi)), key=lambda i: chi[i])]

    m01: dict = {
        "source_report": source_rel,
        "date": rep.get("_date") or _date_of(Path(source_rel)),
        "config": {
            k: cfg.get(k)
            for k in ("L", "seed", "device", "n_sweeps", "n_burnin", "n_temps")
            if cfg.get(k) is not None
        },
        "wall_seconds": rep.get("wall_seconds"),
        "T": T,
        "chi_peak_t": round(peak_t, 4) if peak_t is not None else None,
        "raw_chi_peak_t": round(raw_peak_t, 4),
        "quality_status": quality["status"],
        "quality_note": quality["note"],
        "excluded_indices": quality["excluded_indices"],
        "valid_indices": quality["valid_indices"],
    }
    for name in _CURVES:
        arr = rep.get(name)
        if isinstance(arr, list) and len(arr) == len(T):
            m01[name] = [float(x) for x in arr]

    # Lattice snapshots: report keys look like "T=1.500" → feed keys "1.5".
    # Receipts omit this heavy field, so recover the matching local source or an
    # already-packed feed only after verifying the receipt's SHA-256 attestation.
    snaps = rep.get("snapshots") or _attested_raw_snapshots(
        rep, source_rel, reports_dir, lab_home,
    ) or {}
    packed: dict[str, str] = {}
    lattice_L = None
    for key, rows in snaps.items():
        if not isinstance(rows, list) or not rows:
            continue
        try:
            temp = float(str(key).split("=")[-1])
        except ValueError:
            continue
        lattice_L = len(rows)
        packed[f"{temp:g}"] = pack_lattice(rows)
    if packed:
        m01["snapshots"] = packed
        m01["snapshot_L"] = lattice_L
        _set_snapshot_peak_t(m01, rep.get("snapshot_peak_t"))
    else:
        retained = _attested_packed_snapshots(rep, previous_feed)
        if retained is not None:
            m01["snapshots"], m01["snapshot_L"] = retained
            # Attested: the packed lattices ARE this run's, so its own frame
            # temperature describes them.
            _set_snapshot_peak_t(m01, rep.get("snapshot_peak_t"))
        else:
            # Attestation failed or absent: carry the previous lattices
            # forward labeled with their origin run, never as this run's own.
            carried = _carried_stale_snapshots(previous_feed)
            if carried is not None:
                (
                    m01["snapshots"],
                    m01["snapshot_L"],
                    m01["snapshots_source_report"],
                    m01["snapshots_date"],
                ) = carried
                _set_snapshot_peak_t(
                    m01, (previous_feed.get("m01") or {}).get("snapshot_peak_t"),
                )

    return {
        "schema": PHYSICS_SCHEMA,
        "onsager_tc": round(ONSAGER_TC, 6),
        "source": "windowsill-lab",
        "generated_from": source_rel,
        "provenance": rep.get("provenance") or provenance or {},
        "m01": m01,
    }


def build_physics_feed(out_path: Path = PHYSICS_JSON,
                       reports_dir: Path = REPORTS_DIR,
                       lab_home: Path = LAB_HOME,
                       provenance: dict | None = None,
                       previous_feed: dict | None = None) -> Path | None:
    """Write ``physics-latest.json``; return its path (or ``None`` if no data).

    Best-effort by contract: the caller (``publish``) wraps it so a missing
    report or a write error never breaks the run.
    """
    if previous_feed is None:
        try:
            previous_feed = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous_feed = None
    feed = build_feed(reports_dir, lab_home, provenance, previous_feed)
    if feed is None:
        return None
    atomic_write_text(out_path, json.dumps(feed, indent=2) + "\n", encoding="utf-8")
    return out_path
