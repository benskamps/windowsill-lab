"""A05 survey hunt — the receipts-grade driver for the survey pipeline.

Promotes ``scripts/a04_hunt.py``'s driver shape to the A05 contract:

* **Resumable**: every completed target appends one JSONL row to
  ``$LAB_HOME/a05-hunt-<date>-s<sector>.jsonl`` the moment it finishes. A
  crash or a soft budget stop loses at most the in-flight chunk; rerunning
  the same command resumes from the checkpoint and — because stage-2
  decisions, control membership, and per-target seeds are all content-hashed,
  never order-dependent — produces the same rows it would have produced in
  one sitting.
* **Soft minutes budget**: the deadline stops the run CLEANLY between
  targets; an early-stopped run writes no receipt (an incomplete slice must
  never masquerade as a survey — ``to_report`` refuses it).
* **Bounded parallelism**: the permutation stage is the only expensive pure
  compute, so it fans out over a stdlib ``multiprocessing`` pool capped at
  ``MAX_WORKERS`` = 12 processes, each running single-target numpy. Network
  (MAST) stays serial in the main process — parallel downloads would only
  move the bottleneck onto someone else's server.
* **Receipt at wrap**: the completed run becomes
  ``reports/hunts/hunt-<date>-s<sector>.json`` (the schema of
  ``docs/a05-receipt-schema.md``), lead dossiers land next to it under
  ``reports/hunts/dossiers/``, and ``checks.check_a05`` is run on the fresh
  receipt immediately so a malformed receipt is caught at birth, not at CI.

Prior-target exclusion pulls from every earlier artifact on disk: the A04
graded receipt, the A04 pilot checkpoints, prior A05 checkpoints, and prior
hunt receipts. Floor history likewise folds in every hunt summary found in
``LAB_HOME`` (so the 2026-08-14 wide hunt's floor joins the receipt as soon
as its summary exists) on top of the schema doc's two prior points.

Usage:  python scripts/a05_hunt.py [--n 500] [--sector 2] [--minutes 50]
                                   [--workers 12] [--B 256] [--hunt-id ID]
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import platform
import subprocess
import sys
import time
from datetime import date
from multiprocessing import Pool, cpu_count
from pathlib import Path

from lab import a05, a05_sky, checks
from lab.labhome import LAB_HOME

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Extra wall clock the post-search sky lookups may use. They run in the wrap,
#: once per lead only, so this is a handful of queries — not a second survey.
SKY_LOOKUP_GRACE_SECONDS = 300.0

#: Hard cap on worker processes for the permutation stage. Each worker is
#: single-target numpy; 12 saturates the 16-core box while leaving headroom
#: for the main process's downloads and the OS.
MAX_WORKERS = 12

#: How many times one checkpoint may fail grading before the lane sets it aside.
#: ``find_checkpoint`` resumes what is OPEN, and an ungraded receipt is filed in
#: ``LAB_HOME/ungraded`` rather than committed — so a checkpoint whose grade fails
#: DETERMINISTICALLY never acquires the thing that would retire it. Without a bound
#: the sector lane rebuilds the same rows, writes the same receipt, fails the same
#: grade and requarantines it every slot, forever, under two green units: no new sky
#: is searched and nothing alarms. Bounded, not zero: a grade can fail for a reason
#: that clears, and a 100-minute slice is worth a second attempt.
GRADE_RETRY_LIMIT = 2


def _lab_roots() -> tuple[Path, ...]:
    """Where checkpoints and summaries actually land: LAB_HOME and its
    ``cache/`` — the 2026-08-14 wide hunt wrote today's summaries and
    checkpoints under ``cache/``, and a glob that missed them re-searched
    already-searched stars and dropped a measured floor."""
    return (LAB_HOME, LAB_HOME / "cache")


def was_attempted_but_never_searched(row: dict) -> bool:
    """An outage is not a search.

    The row vocabulary is closed (``checks.check_a05``): ``searched``,
    ``skipped-no-product``, ``error:<Exc>``. Only the last one is TRANSIENT — the
    target was attempted, MAST refused to serve it, and no sky was covered. It is
    written to the checkpoint and counted into ``result.rows`` exactly like a real
    search (``a05.run_a05``), so a full-outage slot "completes" with 200 error rows
    and this function used to read every one of those TICs as done. Nothing alarmed
    and nothing retried: that sky left the survey permanently. The partial case is
    worse, because it grades and publishes.

    ``skipped-no-product`` is permanent (there is genuinely no 2-minute product to
    search) and stays excluded. A row with no readable outcome keeps the old
    behaviour — A04's graded receipt lists bare ``searched`` rows with no outcome
    key at all, and the conservative reading of an unlabelled row is that it ran.
    """
    return str(row.get("outcome", "")).startswith("error:")


def split_resumable(done_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(inherit, retry) — what a resume keeps, and what it re-attempts.

    An errored row is an attempt, not a result, and the outage that produced it has
    had the whole slot to clear. Inheriting it as done would freeze the outage into
    this slice's receipt. Re-erroring costs one more row in the checkpoint;
    ``run_a05`` keys rows by TIC, so the last one per target wins.
    """
    inherit = [r for r in done_rows if not was_attempted_but_never_searched(r)]
    retry = [r for r in done_rows if was_attempted_but_never_searched(r)]
    return inherit, retry


def prior_targets() -> set[str]:
    """Every TIC any earlier graded run, pilot, or hunt already SEARCHED.

    Attempted-and-errored is not searched — see
    :func:`was_attempted_but_never_searched`.
    """
    already: set[str] = set()
    graded = REPO_ROOT / "reports/receipts/run-2026-08-08-2338-a04.json"
    if graded.exists():
        receipt = json.loads(graded.read_text(encoding="utf-8"))
        rep = receipt.get("report", receipt)
        already |= {row["tic"] for row in rep.get("searched", [])}
    for root in _lab_roots():
        for pattern in ("a04-hunt-*.jsonl", "a05-hunt-*.jsonl"):
            for path in root.glob(pattern):
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            row = json.loads(line)
                            tic = row["tic"]
                        except (ValueError, KeyError, TypeError):
                            continue
                        if not was_attempted_but_never_searched(row):
                            already.add(tic)
    hunts_dir = REPO_ROOT / "reports/hunts"
    if hunts_dir.exists():
        for path in hunts_dir.glob("hunt-*.json"):
            try:
                rep = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            already |= {row.get("tic") for row in rep.get("targets", [])
                        if row.get("tic")
                        and not was_attempted_but_never_searched(row)}
    return already


def floor_history() -> list[dict]:
    """The prior floor points, plus every hunt summary on disk (LAB_HOME and
    its cache/), plus the floors of committed schema-0 receipts.

    Deduped by source name AND by n: the same physical floor can reach here
    under two names (a summary in LAB_HOME and its committed receipt), and n —
    the count of noise targets behind the floor — identifies the sample.
    """
    points = [dict(p) for p in a05.PRIOR_FLOOR_HISTORY]
    seen_sources = {p["source"] for p in points}
    seen_n = {int(p["n"]) for p in points}

    def _add(source: str, n, floor_max) -> None:
        if (source in seen_sources or not n or floor_max is None
                or int(n) in seen_n):
            return
        points.append({"n": int(n), "floor_max": float(floor_max),
                       "source": source})
        seen_sources.add(source)
        seen_n.add(int(n))

    for root in _lab_roots():
        for pattern in ("a04-hunt-*-summary.json", "a05-hunt-*-summary.json"):
            for path in sorted(root.glob(pattern)):
                try:
                    s = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                _add(path.stem.replace("-summary", ""),
                     s.get("floor_n"), s.get("floor_max_sde"))
    hunts_dir = REPO_ROOT / "reports/hunts"
    if hunts_dir.exists():
        for path in sorted(hunts_dir.glob("hunt-*.json")):
            try:
                rep = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if rep.get("schema") == 0:
                floor = rep.get("floor") or {}
                _add(path.stem, floor.get("n"), floor.get("max_sde"))
    return points


def _grade_failure_ledger(hunt_id: str) -> Path:
    """Where a hunt id's failed-grade tally lives — beside the receipt it filed."""
    return LAB_HOME / "ungraded" / f"{hunt_id}.grade-failures"


def grade_failures(hunt_id: str) -> int:
    try:
        return int(_grade_failure_ledger(hunt_id).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def record_grade_failure(hunt_id: str) -> int:
    """Count one failed grade for this hunt id and return the running total."""
    ledger = _grade_failure_ledger(hunt_id)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    total = grade_failures(hunt_id) + 1
    ledger.write_text(f"{total}\n", encoding="utf-8")
    return total


def is_retired(hunt_id: str, hunts_dir: Path) -> bool:
    """Is this hunt id finished — by EITHER of the two ways a hunt can finish?

    A committed receipt in ``reports/hunts/`` is one. Being SET ASIDE after
    ``GRADE_RETRY_LIMIT`` failed grades is the other, and its receipt lives in
    ``LAB_HOME/ungraded/`` where the first test cannot see it.

    Both branches of ``find_checkpoint`` must ask this same question. The first
    version of the AUTO-F4 fix asked it only in the resume loop and then built a
    fresh id from ``date.today()`` — which, for a checkpoint any of today's four
    slots created, is BYTE-IDENTICAL to the id just set aside. ``find_checkpoint``
    handed back the very file it had refused, the run resumed it, and the livelock
    survived for the only case that happens in production. One predicate, both
    branches, so the two can never drift apart again.
    """
    if (hunts_dir / f"{hunt_id}.json").exists():
        return True
    return grade_failures(hunt_id) >= GRADE_RETRY_LIMIT


def find_checkpoint(sector: int, hunt_id: str | None = None) -> tuple[str, Path]:
    """(hunt_id, checkpoint path): resume what is OPEN, not what is dated today.

    A run that starts before midnight checkpoints under yesterday's date; the
    old date-stamped naming made the post-midnight rerun open a FRESH file and
    re-search the slice. The rule now: resume the NEWEST ``a05-hunt-*-s{sector}``
    checkpoint that has no committed receipt, whatever its date; ``--hunt-id``
    overrides for surgical resumes. Only when every checkpoint is receipted — or
    SET ASIDE after ``GRADE_RETRY_LIMIT`` failed grades — does a fresh dated id
    start.
    """
    if hunt_id:
        return hunt_id, LAB_HOME / f"a05-{hunt_id}.jsonl"
    hunts_dir = REPO_ROOT / "reports/hunts"
    candidates = sorted(LAB_HOME.glob(f"a05-hunt-*-s{sector}.jsonl"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    for ckpt in candidates:
        hid = ckpt.stem[len("a05-"):]
        # A committed receipt is not the only way a checkpoint finishes. One whose
        # grade has failed GRADE_RETRY_LIMIT times is set aside so the lane advances
        # — its rows and its quarantined receipt stay on disk as evidence, and its
        # searched targets stay excluded by prior_targets(), so no sky is re-covered.
        if is_retired(hid, hunts_dir):
            failures = grade_failures(hid)
            if failures >= GRADE_RETRY_LIMIT:
                print(f"setting aside {hid}: failed grading {failures} times "
                      "— the sector lane moves on")
            continue
        return hid, ckpt
    # Fresh id — but NEVER one that is already RETIRED, by either route. The bare
    # dated id collides the moment a second producer (or a second same-day
    # slot) hunts the same sector: on 2026-08-15 loam's bare survey-slot hunt
    # defaulted to sector 2 and silently overwrote win's committed s2 receipt,
    # taking a lead-awaiting-human-review row with it. Same-day second slices
    # get a UTC time stamp — a NEW receipt beside the old one, never an
    # overwrite (the #79 turn-stamp lesson, re-learned the hard way).
    #
    # A SET-ASIDE checkpoint collides here exactly as hard, and this is where the
    # first AUTO-F4 fix leaked: the loop above refused the stuck checkpoint, this
    # branch rebuilt its id verbatim from today's date, and the caller resumed the
    # same file. Same predicate here as there.
    hid = f"hunt-{date.today().isoformat()}-s{sector}"
    if is_retired(hid, hunts_dir):
        stamp = time.strftime("%H%M", time.gmtime())
        hid = f"{hid}-{stamp}"
        if is_retired(hid, hunts_dir):
            stamp = time.strftime("%H%M%S", time.gmtime())
            hid = f"hunt-{date.today().isoformat()}-s{sector}-{stamp}"
    return hid, LAB_HOME / f"a05-{hid}.jsonl"


def provenance() -> dict:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001 — provenance is reported, never graded
        sha = ""
    return {"machine": platform.node(),
            "code_sha": sha,
            "python": platform.python_version()}


def settle_receipt(receipt_path: Path, ok: bool | None,
                   dossiers: dict | None = None) -> Path:
    """Where a graded receipt belongs — in the ledger, or beside the logs.

    ``check_a05`` returns ``None`` for *uninterpretable* (a control failed, so
    the FAPs mean nothing) and ``False`` for a real failure; neither may be
    published. Enforcing that in the SCHEDULER was not enough: the slot script
    held ungraded receipts back, and the campaign lane — which reaches the same
    hunt through ``lab next`` when A05 is the open milestone — staged all of
    ``reports/`` and published them anyway. Two lanes, one runner, one gate: it
    belongs here, where every caller inherits it.

    Leaving the file in ``reports/hunts/`` is not a neutral act. The pot
    aggregator globs that DIRECTORY rather than git, so an ungraded receipt is
    counted into the public hunt ledger by the next run that publishes, while CI
    recomputes the block from the committed receipts alone and goes red. Its
    dossiers travel with it for the same reason.

    Cost, eyes open: ``already_searched()`` globs the same directory, so a
    quarantined run's targets become eligible for a later slice again.
    """
    if ok is True:
        return receipt_path
    dest_dir = LAB_HOME / "ungraded"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Tally it. Quarantining alone leaves no trace that survives to the NEXT slot's
    # find_checkpoint, which is why a deterministic grade failure used to livelock
    # the sector lane (see GRADE_RETRY_LIMIT).
    total = record_grade_failure(receipt_path.stem)
    print(f"grade failure {total}/{GRADE_RETRY_LIMIT} for {receipt_path.stem}")
    for tic in (dossiers or {}):
        rendered = receipt_path.parent / "dossiers" / f"{receipt_path.stem}-tic{tic}.html"
        if rendered.exists():
            rendered.replace(dest_dir / rendered.name)
    dest = dest_dir / receipt_path.name
    receipt_path.replace(dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--sector", type=int, default=2)
    ap.add_argument("--minutes", type=float, default=50.0,
                    help="soft wall-clock budget; stops cleanly, resume by rerun")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--B", type=int, default=256)
    ap.add_argument("--hunt-id", default=None,
                    help="resume/name a specific hunt id (default: newest "
                         "receipt-less checkpoint for the sector, else a "
                         "fresh dated id)")
    args = ap.parse_args()

    t0 = time.time()
    hunt_id, ckpt = find_checkpoint(args.sector, args.hunt_id)
    ckpt.parent.mkdir(parents=True, exist_ok=True)

    done_rows: list[dict] = []
    if ckpt.exists():
        for line in ckpt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done_rows.append(json.loads(line))
                except (ValueError, json.JSONDecodeError):
                    print(f"warning: skipping malformed checkpoint line in {ckpt.name}")
                    continue
        print(f"resuming: {len(done_rows)} targets already checkpointed")

    done_rows, retry_rows = split_resumable(done_rows)
    if retry_rows:
        print(f"retrying {len(retry_rows)} targets that errored on an earlier "
              "pass — an outage is not a search")

    already = prior_targets() - {r["tic"] for r in done_rows}
    print(f"excluding {len(already)} previously searched targets")

    out = ckpt.open("a", encoding="utf-8")

    def on_row(row: dict) -> None:
        out.write(json.dumps(row) + "\n")
        out.flush()
        sde = row.get("sde")
        note = f"SDE {sde:.1f}" if isinstance(sde, float) else row.get("outcome")
        extra = f" -> {row['disposition']}" if row.get("disposition") else ""
        print(f"  TIC {row['tic']}: {note}{extra}")

    # The sky lookups happen in the WRAP, after the search budget is spent, so
    # they get their own deadline past the hunt's soft wall rather than
    # inheriting an already-expired one.
    sky_deadline = t0 + args.minutes * 60.0 + SKY_LOOKUP_GRACE_SECONDS

    n_workers = max(1, min(args.workers, MAX_WORKERS, cpu_count()))
    with Pool(n_workers) as pool:
        result = a05.run_a05(
            sector=args.sector, n_targets=args.n,
            already=already, done_rows=done_rows,
            B=args.B, deadline=t0 + args.minutes * 60.0,
            soft_budget_seconds=args.minutes * 60.0,
            # The sky gates (a05.apply_sky_gates, the 2026-08-20 HATS-16 b
            # fix) are a no-op inside run_a05 unless these two seams are
            # passed, and this driver is where every production lead is
            # minted. They went unwired for a day; the receipt's `sky_gates`
            # block now states out loud whether they ran (VET-F4).
            neighbours=functools.partial(a05_sky.resolve_neighbours,
                                         deadline=sky_deadline),
            sky_catalog=functools.partial(a05_sky.sky_catalog_lookup,
                                          deadline=sky_deadline),
            on_row=on_row, pool_map=pool.map, hunt_id=hunt_id)
    out.close()

    if not result.complete:
        print(f"[budget] soft wall reached with {len(result.rows)} rows "
              "checkpointed; rerun the same command to resume — no receipt "
              "is written for an incomplete slice")
        return 0

    report = a05.to_report(result, prior_floor_history=tuple(floor_history()),
                           provenance=provenance())
    hunts_dir = REPO_ROOT / "reports/hunts"
    hunts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = hunts_dir / f"{hunt_id}.json"
    tmp_receipt = receipt_path.with_suffix('.tmp')
    with tmp_receipt.open("w", encoding="utf-8") as f:
        f.write(json.dumps(report, indent=1))
        os.fsync(f.fileno())
    tmp_receipt.replace(receipt_path)
    for tic, html in result.dossiers.items():
        dossier_dir = hunts_dir / "dossiers"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        (dossier_dir / f"{hunt_id}-tic{tic}.html").write_text(
            html, encoding="utf-8")

    counts = report["counts"]
    print(f"\nreceipt -> {receipt_path}")
    print(f"searched {counts['searched']}/{counts['attempted']}, "
          f"stage2 {counts['stage2']}, above threshold "
          f"{counts['above_threshold']}, leads "
          f"{counts['leads_awaiting_human_review']}")
    ok, detail = checks.check_a05(report)
    print(f"check_a05: {ok} — {detail}")
    settled = settle_receipt(receipt_path, ok, dossiers=result.dossiers)
    if settled != receipt_path:
        print(f"receipt -> {settled}  (ungraded: filed with the logs, "
              "not published and not aggregated)")
        return 0

    # pot.json's ``hunt`` key is a pure function of the committed receipts
    # (CI enforces pot == hunt_block()). A receipt written WITHOUT refreshing
    # the pot ships a red main in the producer's own commit — the 2026-08-15
    # nightly did exactly that. Refresh surgically: the hunt key only, the
    # publisher's own serialization (indent=2, insertion order — never
    # sort_keys), so the receipt and its aggregate land together.
    from lab.publish import POT_JSON, hunt_block
    pot = json.loads(POT_JSON.read_text(encoding="utf-8"))
    pot["hunt"] = hunt_block()
    tmp_pot = POT_JSON.with_suffix('.tmp')
    with tmp_pot.open("w", encoding="utf-8") as f:
        f.write(json.dumps(pot, indent=2) + "\n")
        os.fsync(f.fileno())
    tmp_pot.replace(POT_JSON)
    print(f"pot hunt block refreshed -> {POT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
