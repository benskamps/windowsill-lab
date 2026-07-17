"""Build ``physics-latest.json`` — the compact, plottable physics feed.

The windowsill page's calm face narrates the physics but never *shows* it: the
real χ(T) susceptibility spike, the |m|(T) magnetization landing on Onsager's
exact 1944 curve, and — the iconic image — the 128×128 spin lattice ordered,
near-critical, and disordered, all sit unplotted inside a 600 KB report JSON.

This module distills the newest M01 heartbeat report into a tiny (~8 KB) feed
the page can fetch and render: the six measured arrays, the located χ-peak, and
the three lattice snapshots bit-packed to base64 (each 128×128 ±1 lattice → one
bit per site → 2 KB → base64). Nothing is fabricated — every number is copied
straight from a provenance-stamped run and the source report is named in the
feed so a reader can diff it against the raw JSON.

Kept standard-library-only (no torch, no matplotlib) so it stays cheap and the
pure builder is unit-tested without the scientific stack. Written by ``publish``
on every run, so the nightly keeps the physics face as fresh as the plant.
"""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"
LAB_HOME = Path.home() / ".lab"
PHYSICS_JSON = REPO_ROOT / "physics-latest.json"   # committed feed the page reads

# Bump when the feed contract changes in a way the page must adapt to.
PHYSICS_SCHEMA = 1

# Onsager's exact 2D Ising critical temperature (1944) — the calibration target.
ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))   # ≈ 2.269185

_DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"

# The measured arrays we lift verbatim (name in report → name in feed). Each is
# a per-temperature list parallel to ``T``; a missing one is simply omitted.
_CURVES = ("abs_mag", "abs_mag_err", "chi", "chi_abs", "energy", "specific_heat")


def _date_of(path: Path) -> str:
    return path.stem[:10]


def _is_snapshot_report(data: dict) -> bool:
    """True for an M01-shape report carrying lattice snapshots + a χ-sweep."""
    return (
        isinstance(data.get("snapshots"), dict)
        and isinstance(data.get("T"), list)
        and isinstance(data.get("chi"), list)
        and len(data["T"]) == len(data["chi"])
        and len(data["T"]) > 1
    )


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


def _peak_t(T: list, chi: list) -> float:
    return round(T[max(range(len(chi)), key=lambda i: chi[i])], 4)


def build_feed(reports_dir: Path = REPORTS_DIR,
               lab_home: Path = LAB_HOME,
               provenance: dict | None = None) -> dict | None:
    """Assemble the physics feed dict from the newest snapshot report.

    ``provenance`` (e.g. ``publish.provenance()``) rides along verbatim so the
    feed records the exact code that produced the run. Returns ``None`` when
    there is no snapshot report yet (the caller then writes nothing and the page
    simply omits its physics section).
    """
    found = _newest_snapshot_report(reports_dir, lab_home)
    if found is None:
        return None
    rep, source_rel = found

    T = [round(float(t), 4) for t in rep["T"]]
    chi = [float(c) for c in rep["chi"]]
    cfg = rep.get("config", {}) or {}

    m01: dict = {
        "source_report": source_rel,
        "date": rep.get("_date") or Path(source_rel).name[:10],
        "config": {
            k: cfg.get(k)
            for k in ("L", "seed", "device", "n_sweeps", "n_burnin", "n_temps")
            if cfg.get(k) is not None
        },
        "wall_seconds": rep.get("wall_seconds"),
        "T": T,
        "chi_peak_t": _peak_t(T, chi),
    }
    for name in _CURVES:
        arr = rep.get(name)
        if isinstance(arr, list) and len(arr) == len(T):
            m01[name] = [float(x) for x in arr]

    # Lattice snapshots: report keys look like "T=1.500" → feed keys "1.5".
    snaps = rep.get("snapshots") or {}
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

    return {
        "schema": PHYSICS_SCHEMA,
        "onsager_tc": round(ONSAGER_TC, 6),
        "source": "windowsill-lab",
        "generated_from": source_rel,
        "provenance": provenance or {},
        "m01": m01,
    }


def build_physics_feed(out_path: Path = PHYSICS_JSON,
                       reports_dir: Path = REPORTS_DIR,
                       lab_home: Path = LAB_HOME,
                       provenance: dict | None = None) -> Path | None:
    """Write ``physics-latest.json``; return its path (or ``None`` if no data).

    Best-effort by contract: the caller (``publish``) wraps it so a missing
    report or a write error never breaks the run.
    """
    feed = build_feed(reports_dir, lab_home, provenance)
    if feed is None:
        return None
    out_path.write_text(json.dumps(feed, indent=2) + "\n", encoding="utf-8")
    return out_path
