import argparse
import contextlib
import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import curriculum
from .curriculum import RUNNERS, filter_scheduler_options

# Lightweight commands (open / publish / help) must work without torch or
# matplotlib, so ising/render are imported lazily inside `run`. LAB_HOME is a
# trivial constant we keep here to avoid importing render just for the path.
from .labhome import LAB_HOME  # ~/.lab, or $LAB_HOME when set

# One turn per box. See `next_run_lock` below and tests/test_next_lock.py.
NEXT_LOCK_NAME = "next.lock"

#: Set in the environment for as long as this process holds the run lock, so a
#: child dispatched BY the turn (``lab next`` → ``lab hunt`` → a subprocess
#: running ``scripts/a05_hunt.py``) can tell "my own turn owns this" apart from
#: "another box turn owns this" and re-enter instead of deadlocking on itself.
NEXT_LOCK_ENV = "LAB_NEXT_LOCK_PID"

#: How often a waiting acquirer re-checks a busy lock. Short enough that the
#: handoff is prompt, long enough that a 5-minute wait is ~150 stat calls.
LOCK_POLL_SECONDS = 2.0


class LockBusy(Exception):
    """Another live `lab next` turn owns the run lock."""

    def __init__(self, pid, started):
        self.pid = pid
        self.started = started
        super().__init__(f"lab next is already running (pid {pid} since {started})")


def _process_is_live_python(pid) -> bool:
    """Is ``pid`` a running python interpreter?

    Liveness alone is not enough on Windows, where PIDs are recycled quickly: a
    reused PID would make a stale lock look live and wedge the scheduler for
    good. So we also check the process NAME where we can. ``psutil`` gives us
    that cheaply but is deliberately NOT a declared dependency of this package —
    when it is absent we fall back to a liveness-only probe and accept the small
    reuse risk, which costs at most one skipped slot (the next turn's takeover
    path recovers).
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        import psutil  # noqa: PLC0415 — optional; never a declared dependency
    except ImportError:
        pass
    else:
        try:
            return "python" in psutil.Process(pid).name().lower()
        except Exception:  # noqa: BLE001 — no such process / access denied
            return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, owned by someone else
    return True


def _read_lock(path):
    """Parse a lock file, or return ``None`` when it is missing/unreadable.

    An unparseable lock names no owner, so it cannot be honored — treat it as
    stale and fail toward running rather than toward a silent standstill.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def note_lock_milestone(path, milestone) -> None:
    """Stamp the running milestone into an already-held lock.

    Selection only knows WHAT it is running after the lock is taken, and a lock
    that says `M02 since 12:00` is the difference between a diagnosable box and
    a mystery. Best-effort: never fail a real turn over its own bookkeeping.
    """
    payload = _read_lock(path) or {}
    payload["milestone"] = milestone
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def _held_by_this_process_tree(path) -> bool:
    """Does an ANCESTOR of this process already hold the lock at ``path``?

    The lock protects the box, not one process, and a turn dispatches real work
    into children: `lab next` takes the lock and then reaches `lab hunt`, which
    runs ``scripts/a05_hunt.py`` in a SUBPROCESS (see ``cmd == "hunt"``). A
    child that asks for the same lock its own parent is holding must not be told
    the box is busy — it is the busy-ness. Without this, a hunt driver that
    locks its pot refresh would block on its own dispatcher for the whole wait
    budget and then withhold a perfectly good receipt.

    The environment variable is the ancestry channel (``subprocess`` inherits
    it), and the lock FILE is the proof: the two must agree and the named pid
    must still be a live python, or this is a leaked variable from a dead turn
    and the caller falls through to real acquisition.
    """
    claimed = os.environ.get(NEXT_LOCK_ENV)
    if not claimed:
        return False
    holder = _read_lock(path)
    if holder is None or str(holder.get("pid")) != str(claimed):
        return False
    try:
        return _process_is_live_python(int(claimed))
    except (TypeError, ValueError):
        return False


@contextlib.contextmanager
def next_run_lock(path=None, wait_seconds=0.0):
    """Hold the one-turn-per-box lock for the duration of a `lab next` turn.

    Overlap prevention lives HERE, in the process that actually knows whether a
    turn is running — not in the scheduled task's ExecutionTimeLimit, which the
    2026-08-02 incident falsified: Task Scheduler killed the powershell wrapper
    at the 2h mark and the python child kept running, so the limit prevented no
    overlap and only orphaned the logger.

    Raises ``LockBusy`` when a live python process already holds it. A lock whose
    owner is dead (killed turn, reboot, power loss) is announced and taken over.

    ``wait_seconds`` polls for a busy lock instead of giving up on the first
    look, and defaults to 0 so `lab next` keeps its original behaviour exactly:
    a scheduled turn that finds the box busy skips its slot rather than queueing
    behind one. Callers that are FINISHING work rather than starting it — the
    hunt driver's pot refresh — pass a budget, because for them waiting a few
    minutes is cheaper than throwing away a graded slice.

    Re-entrant across a process tree: see :func:`_held_by_this_process_tree`.
    """
    path = Path(path) if path is not None else LAB_HOME / NEXT_LOCK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    if _held_by_this_process_tree(path):
        # Our own turn owns it. Yield it, and do NOT release on the way out —
        # the ancestor that took it is the one that gets to give it back.
        yield path
        return
    payload = json.dumps({
        "pid": os.getpid(),
        "started": datetime.now(timezone.utc).isoformat(),
        "milestone": None,
    })
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    announced = False
    while True:
        try:
            # O_EXCL so two turns starting in the same instant cannot both win.
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            holder = _read_lock(path)
            held_pid = holder.get("pid") if holder else None
            if holder is not None and _process_is_live_python(held_pid):
                if time.monotonic() >= deadline:
                    raise LockBusy(held_pid,
                                   holder.get("started", "unknown")) from None
                if not announced:
                    print(f"lab · run lock held by pid {held_pid} — waiting up "
                          f"to {float(wait_seconds):.0f}s")
                    announced = True
                time.sleep(LOCK_POLL_SECONDS)
                continue
            print(
                f"lab next · stale lock from pid {held_pid} "
                f"(since {holder.get('started', 'unknown') if holder else 'unreadable'}) "
                "— taking it over"
            )
            fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
            break
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    previously_claimed = os.environ.get(NEXT_LOCK_ENV)
    os.environ[NEXT_LOCK_ENV] = str(os.getpid())
    try:
        yield path
    finally:
        if previously_claimed is None:
            os.environ.pop(NEXT_LOCK_ENV, None)
        else:
            os.environ[NEXT_LOCK_ENV] = previously_claimed
        # Only clear a lock we still own: if a later turn decided ours was stale
        # and took over, that lock is theirs to release.
        current = _read_lock(path)
        if current is None or current.get("pid") == os.getpid():
            with contextlib.suppress(OSError):
                path.unlink()

# Milestone → runnable ``lab`` subcommand lives in ``curriculum.py`` so the
# scheduler and the public feed expose the same operational truth. M01 is the
# un-prefixed heartbeat; milestones past M15 currently remain on the bench.


def _select_next(milestones):
    """Pick the lowest OPEN milestone and say whether we can run it.

    ``parse_milestones`` already flags exactly one milestone ``status=='open'``
    — the first pending in file order (M-track before the Citizen-Science
    tracks), unless one is explicitly marked ``[>]``. That is the lab's single
    bench: the experiment running now / next. We return its id and whether a
    runner is registered for it. Returns ``(None, False)`` when nothing is open
    (every milestone verified/null) — the caller then falls back to the
    heartbeat. This is pure selection: it reads state and decides, it never runs
    a simulation or edits ``MILESTONES.md``.
    """
    open_ms = next((m for m in milestones if m.get("status") == "open"), None)
    if open_ms is None:
        return None, False
    mid = open_ms["id"]
    return mid, mid in RUNNERS


def _receipt_records() -> list[tuple[str, str]]:
    """``(stamp, milestone)`` tuples from the committed receipts ledger."""
    return _planner_ledger()[0]


def _planner_ledger() -> tuple[list[tuple[str, str]], dict[str, list[float]]]:
    """``(records, durations)`` from the committed receipts ledger in ONE read.

    The thin disk reader that feeds ``curriculum.rotation_pointer``. Stamp is
    the receipt's ``generated_at``; an unreadable or unstamped receipt degrades
    to its filename date (the ``publish.run_cadence`` discipline) — committed
    content either way, so every clone derives the identical pointer.

    The filename is split by ``publish._split_receipt_stem``, the same parser
    the WRITER uses, so the two can never disagree about a name again. They did
    for nine days: PR #79 (2026-08-02) turn-stamped receipts to
    ``run-<date>-<hhmm>-<slug>.json`` and this reader still hardcoded the legacy
    offsets, so it read the slug as ``2336-M02`` — in no rotation, therefore
    skipped — and the pointer fell back to the last legacy-named receipt
    forever. ``lab next`` picked the same slot 43 passes running.

    ``durations`` maps milestone → the ``wall_seconds`` its receipts carry
    (missing/absent entries simply don't appear): the planner's cost seam,
    read from the same JSON decode the stamp already pays for, so cost data
    is free exactly when it exists and honestly absent when it doesn't.
    """
    from . import publish as publish_mod
    records: list[tuple[str, str]] = []
    durations: dict[str, list[float]] = {}
    receipts_dir = publish_mod.RECEIPTS_DIR
    if not receipts_dir.exists():
        return records, durations
    date_glob = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
    for path in sorted(receipts_dir.glob(f"run-{date_glob}-*.json")):
        date, _turn, slug = publish_mod._split_receipt_stem(
            path.stem[len("run-"):])
        if not slug:
            continue
        stamp = None
        wall = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stamp = data.get("generated_at")
            wall = data.get("wall_seconds")
        except (OSError, ValueError):
            pass
        if not (isinstance(stamp, str) and stamp):
            stamp = date
        mid = slug.upper()
        records.append((stamp, mid))
        if isinstance(wall, (int, float)) and wall > 0:
            durations.setdefault(mid, []).append(float(wall))
    return records, durations


def _hunt_status() -> dict | None:
    """Remaining survey coverage from the newest committed hunt receipt.

    The planner's synthetic ``A05-HUNT`` candidate exists only when COMMITTED
    state proves there is new sky to search: the newest ACCEPTED
    ``reports/hunts`` receipt must carry its sector's enumeration total
    (``n_enumerated``), and the searched count is summed across every accepted
    receipt by the same per-receipt counters pot.json uses — one reader, one
    truth. Anything missing → ``None`` and the candidate never appears —
    honest over wishful. Acceptance, refusal, and ``supersedes`` resolution
    are ``publish._accepted_hunt_receipts``'s, not re-derived here.
    """
    from . import publish as publish_mod
    hunts_dir = publish_mod.REPO_ROOT / "reports" / "hunts"
    if not hunts_dir.exists():
        return None
    accepted, _refused, _superseded = publish_mod._accepted_hunt_receipts(
        hunts_dir)
    if not accepted:
        return None
    # Per-SECTOR ledger: each sector's enumeration total comes from its own
    # newest receipt that declares one, and its searched count is summed by
    # the same per-receipt counters the pot uses — the schema-1 survey
    # receipts carry no top-level cumulative ``targets_searched``, and a
    # reader that required one dropped the survey slot the night it landed.
    # A sector that never declared an enumeration contributes nothing:
    # honest over wishful.
    enums: dict[int, tuple[tuple[str, str], int]] = {}
    searched: dict[int, int] = {}
    for date, path, receipt in accepted:
        sector = receipt.get("sector")
        if not isinstance(sector, int):
            continue
        searched[sector] = (searched.get(sector, 0)
                            + publish_mod._hunt_receipt_counters(receipt)
                            ["targets_searched"])
        enum_total = receipt.get("n_enumerated")
        stamp = (date, path.name)
        if isinstance(enum_total, int) and stamp >= enums.get(
                sector, (("", ""), 0))[0]:
            enums[sector] = (stamp, enum_total)
    per_sector = {sector: max(0, enum_total - searched.get(sector, 0))
                  for sector, (_, enum_total) in enums.items()}
    remaining = sum(per_sector.values())
    if remaining <= 0:
        return None
    return {"remaining_targets": remaining, "sectors": sorted(enums),
            "per_sector": per_sector}


def _hunt_status_for_dispatch() -> dict | None:
    """The seam restricted to THIS box's assigned lane — the dispatch truth.

    ``_hunt_status()`` is the global committed ledger; a scheduler must only
    act on the slice of it this box is allowed to hunt (curriculum.hunt_lane),
    or two boxes end up hunting the same sector — the 2026-08-15 receipt
    clobber. ``None`` when the box has no lane or its lane has no remaining
    coverage; the planner then simply never sees a survey candidate, and the
    portfolio continues without refusal spam.
    """
    status = _hunt_status()
    if status is None:
        return None
    lane = curriculum.hunt_lane()
    if lane is None:
        return None
    per_sector = {s: n for s, n in status["per_sector"].items()
                  if s in lane and n > 0}
    remaining = sum(per_sector.values())
    if remaining <= 0:
        return None
    return {"remaining_targets": remaining, "sectors": sorted(per_sector),
            "per_sector": per_sector}


HELP = """lab — a windowsill physics lab.

Usage:
  lab                 open the latest report (alias of `lab open`)
  lab run             run only — don't open the browser (the M01 heartbeat)
  lab next            run the open milestone's experiment; otherwise the planner
                      scores the portfolio by value/cost from the receipts
                      ledger and runs the pick (M01 heartbeat only if empty)
  lab next --dry-run  print the pick + every skip reason — run nothing
  lab m02             run M02: finite-size scaling across lattice sizes
  lab m03             run M03: critical-exponent β via magnetization data-collapse
  lab m04             run M04: 2D Ising specific heat — the thermal cross-check of T_c
  lab m05             run M05: triangular-lattice 2D Ising — verify T_c = 4/ln3 ≈ 3.641
  lab m05-hex         run M05: honeycomb-lattice 2D Ising — verify T_c = 2/ln(2+√3) ≈ 1.519
  lab m06             run M06: 3D simple-cubic Ising — verify T_c ≈ 4.5115 (Phase 2)
  lab m07             run M07: q-state Potts (q=3..6) — continuous→first-order transition
  lab m08             run M08: 2D XY model — BKT transition via the helicity-modulus jump
  lab m09             run M09: 2D Heisenberg — verify NO finite-T order (Mermin–Wagner)
  lab m10             run M10: antiferromagnetic Ising — T_N = Onsager 2.2692 on staggered m_s
  lab m11             run M11: 2D Edwards–Anderson spin glass — P(q) broadens toward T_c=0
  lab m12             run M12: 3D EA spin glass — Binder-cumulant crossing at the ±J T_SG benchmark (parallel tempering)
  lab m13             run M13: frustrated triangular AFM — residual entropy S0/N≈0.3383 via C/T integration
  lab m14             run M14: random-bond Ising — exact Nishimori-line energy, map toward the MNP p_c≈0.109
  lab m15             run M15: Glauber dynamics — domain growth L(t)∼t^(1/2) after a quench (Phase 4)
  lab m16             run M16: 3D spin-glass aging — compare t/t_w with t−t_w collapse
  lab m17             run M17: KPZ growth on a ring — β=1/3, α=1/2, z=3/2 + Tracy–Widom class
  lab k01             run K01: Kuramoto synchronization — verify K_c = 2γ (Track K)
  lab k02             run K02: does the χ(r) shape survive N? (Track K)
  lab k03             run K03: Daido vs Hong — is the susceptibility exponent asymmetric across K_c? (Track K)
  lab k04             run K04: Mirollo–Strogatz fireflies — measure the almost-sure sync theorem (Track K)
  lab c01             run C01: OEIS byte + Lucas–Lehmer arithmetic calibration
  lab c05             run C05: BBP hex digits of π extracted at position, byte-checked
                      against an independent Machin expansion; deep window at 10^7
  lab a01             run A01: recover WASP-18 b from official TESS SPOC light curves
  lab a03             run A03: chirp mass of a GWOSC event by matched filtering
  lab m18             run M18: directed percolation in 2+1d (absorbing-state transition)
  lab a04             run A04: blind transit search across a TESS sector
  lab a07             run A07: Galilean moons from JPL Horizons — Kepler III + Laplace resonance
  lab i01             run I01: calibrate a real capped-CMOS dark-frame stack
  lab i01 --camera 0  acquire a bounded live grayscale stack, then calibrate it
  lab open            open the latest report (no run)
  lab web             open your seed-in-the-pot page (web/index.html) locally
  lab publish         write the committed pot.json — feeds the windowsill
  lab backfill        copy ~/.lab history into reports/ under permanent names
  lab verify [IDs]    re-derive verified milestones from their reports (CI gate)
  lab verify --rerun-smoke
                      also re-run the pinned L=16 CPU smoke config and prove it
                      reproduces itself + the committed golden (determinism gate)
  lab shelf           grade every lead-awaiting-human-review row against the
                      shelf-exit contract (docs/shelf-exit-contract.md): who is
                      promotable, who is parked and on what, whose clock has run
  lab shelf --json    the same register as JSON (for surfaces; insertion order)
  lab scoreboard      render the calibration scoreboard (measured vs theory) + archive
  lab controls        run published controls: cross-updater agreement + a J=0 null
  lab setup           install the nightly job (run → publish → push)
  lab help            show this message

Backfill options (only with `backfill`):
  --dry-run           list what would be written, write nothing

Setup options (only with `setup`):
  --check             pre-flight health check only — install nothing
  --cron              install a cron line instead of a systemd user timer
  --dry-run           show what would happen, write nothing

Publish options (only with `publish`):
  --gist ID           push the snapshot to this public gist (or set POT_GIST_ID)

Knobs (only with `run`):
  --L INT             lattice side length (default 128)
  --t-min FLOAT       lower temperature (default 1.5)
  --t-max FLOAT       upper temperature (default 3.5)
  --n-temps INT       number of temperatures swept in parallel (default 21)
  --sweeps INT        measurement sweeps per lattice (default 40000)
  --burnin INT        burn-in sweeps (default 8000)
  --device STR        'cuda' or 'cpu' (default cuda)
  --seed INT          RNG seed (default 42)
  --initial-state STR 'ordered' (heartbeat default) or 'random'

Phase 1 reproduces Onsager's 2D Ising result. Later phases will sweep more
exotic systems. State accumulates under ~/.lab/.
"""


def _parse_run(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=128)
    p.add_argument("--t-min", type=float, default=1.5)
    p.add_argument("--t-max", type=float, default=3.5)
    p.add_argument("--n-temps", type=int, default=21)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--initial-state", choices=("ordered", "random"), default="ordered",
        help="starting lattice (ordered avoids cold-start metastability at L=128)",
    )
    return p.parse_args(args)


def _parse_m02(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=str, default=None,
                   help="comma-separated lattice sizes, e.g. 32,64,128,256,512")
    p.add_argument("--quick", action="store_true",
                   help="cap at L=128 for a faster pass")
    p.add_argument("--t-min", type=float, default=2.27)
    p.add_argument("--t-max", type=float, default=2.40)
    p.add_argument("--n-temps", type=int, default=24)
    p.add_argument("--sweeps", type=int, default=80000)
    p.add_argument("--burnin", type=int, default=30000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--updater", default="wolff",
                   help="'wolff' (cluster, near-T_c; unlocks L≥512) or 'metropolis'")
    p.add_argument("--wolff-init", default="ordered",
                   help="wolff start: 'ordered' (fast burn-in at scale) or 'random'")
    return p.parse_args(args)


def _parse_m03(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=str, default=None,
                   help="comma-separated lattice sizes, e.g. 16,24,32,48")
    p.add_argument("--quick", action="store_true",
                   help="cap at L=32 for a faster pass")
    p.add_argument("--t-min", type=float, default=2.24)
    p.add_argument("--t-max", type=float, default=2.30)
    p.add_argument("--n-temps", type=int, default=24)
    p.add_argument("--sweeps", type=int, default=20000)
    p.add_argument("--burnin", type=int, default=4000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--updater", default="wolff",
                   help="'wolff' (cluster, near-T_c) or 'metropolis'")
    return p.parse_args(args)


def _parse_m06(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=10,
                   help="lattice side (even; default 10)")
    p.add_argument("--quick", action="store_true",
                   help="L=6, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=4.1)
    p.add_argument("--t-max", type=float, default=4.9)
    p.add_argument("--n-temps", type=int, default=21)
    p.add_argument("--sweeps", type=int, default=8000)
    p.add_argument("--burnin", type=int, default=3000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--updater", default="metropolis",
                   choices=("metropolis", "wolff"),
                   help="sampler: 'metropolis' (default, verified checkerboard) or "
                        "'wolff' (3D cluster updater, beats critical slowing for larger L)")
    p.add_argument("--device", default="cpu",
                   help="torch device for the wolff updater (ignored by metropolis)")
    return p.parse_args(args)


def _parse_m04(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=128,
                   help="lattice side (default 128)")
    p.add_argument("--quick", action="store_true",
                   help="L=48, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=2.0)
    p.add_argument("--t-max", type=float, default=2.6)
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m05(args):
    p = argparse.ArgumentParser(add_help=False)
    # L must be a multiple of 3 for the triangular 3-colour update; 129 is the
    # multiple of 3 nearest the square engine's 128 (ising_tri raises otherwise).
    p.add_argument("--L", type=int, default=129,
                   help="lattice side, must be a multiple of 3 (default 129)")
    p.add_argument("--quick", action="store_true",
                   help="L=48, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=3.3)
    p.add_argument("--t-max", type=float, default=4.0)
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m05_hex(args):
    p = argparse.ArgumentParser(add_help=False)
    # L must be EVEN for the honeycomb brick-wall (odd L breaks the parity rule's
    # reciprocity at the row seam — see ising_hex.require_even_L). Unlike the
    # triangular 3|L constraint this lets us use the square engine's own 128.
    p.add_argument("--L", type=int, default=128,
                   help="lattice side, must be even (default 128)")
    p.add_argument("--quick", action="store_true",
                   help="L=48, short sweep for a fast sanity pass")
    # The window is the triangular run's, rescaled by T_c: it spanned 0.906–1.099
    # of its own exact value, so this resolves the peak equally well (ΔT=0.0146).
    p.add_argument("--t-min", type=float, default=1.35)
    p.add_argument("--t-max", type=float, default=1.70)
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m07(args):
    p = argparse.ArgumentParser(add_help=False)
    # M07 sweeps a per-q window straddling each exact T_c(q)=1/ln(1+√q), so the
    # temperature bounds are derived per q (T_c ± half-window) rather than fixed.
    # The default updater is Wolff (cluster) — single-spin Metropolis is
    # metastably trapped through the Potts transition — so --sweeps/--burnin are
    # counted in *cluster updates* (far fewer needed than Metropolis sweeps).
    # L defaults to 64 (not the 128 of the Ising engines): the Wolff cluster
    # flood costs O(L) BFS passes per update near T_c, so the 4-q sweep is only
    # tractable at L=64 — which already locates every T_c within tolerance (the
    # finite-L shift is absorbed by the per-q tolerances). Pass --L 128 for a
    # sharper single-q run.
    p.add_argument("--L", type=int, default=64,
                   help="lattice side (default 64; Wolff BFS cost scales with L)")
    p.add_argument("--quick", action="store_true",
                   help="L=32, short sweep for a fast sanity pass")
    p.add_argument("--q", type=str, default=None,
                   help="comma-separated q values (default 3,4,5,6)")
    p.add_argument("--half-window", type=float, default=0.12,
                   help="half-width of the per-q T window around T_c (default 0.12)")
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=4000,
                   help="Wolff cluster updates per q (default 4000)")
    p.add_argument("--burnin", type=int, default=1500,
                   help="Wolff burn-in cluster updates (default 1500)")
    p.add_argument("--updater", default="wolff",
                   help="'wolff' (cluster, default) or 'metropolis' (cross-check)")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m08(args):
    p = argparse.ArgumentParser(add_help=False)
    # M08 sweeps a window straddling the BKT benchmark T_BKT ≈ 0.8929 and locates
    # it from the helicity-modulus jump crossing Υ(T)=(2/π)T — there is NO χ/C peak
    # for this transition. L defaults to 64 (the XY engine is float-angle and uses
    # over-relaxation; L=64 already brackets the crossing within the documented
    # ±0.07 finite-L window). The default Metropolis-plus-over-relaxation updater
    # gives a smooth Υ(T); pass --updater wolff for the hardest near-T_BKT points.
    p.add_argument("--L", type=int, default=64,
                   help="lattice side (default 64)")
    p.add_argument("--quick", action="store_true",
                   help="L=32, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=0.6)
    p.add_argument("--t-max", type=float, default=1.1)
    p.add_argument("--n-temps", type=int, default=26)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--over-relax", type=int, default=1,
                   help="microcanonical over-relaxation sweeps per Metropolis sweep")
    p.add_argument("--updater", default="metropolis",
                   help="'metropolis' (+ over-relaxation; default) or 'wolff'")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m09(args):
    p = argparse.ArgumentParser(add_help=False)
    # M09 sweeps a *family* of L at a single fixed T and shows the Mermin–Wagner
    # drift ⟨|m|⟩(L) → 0 — there is NO transition and NO T-sweep. L defaults to the
    # {16,32,64} family (already resolves the monotone drift); T=0.7 is moderate
    # (cold enough that small L carries an appreciable, falsifiable ⟨|m|⟩, warm
    # enough that ξ(T) ≪ 64 so the drift is visible without needing L=128+). The
    # default Metropolis-plus-over-relaxation updater (over-relaxation cures the
    # spin-wave critical slowing at the low-T, large-ξ points); --updater wolff
    # uses the embedded-Ising single-cluster move.
    p.add_argument("--L", type=str, default=None,
                   help="comma-separated lattice sizes (default 16,32,64)")
    p.add_argument("--quick", action="store_true",
                   help="L=8,12,16, short sweep for a fast sanity pass")
    p.add_argument("--T", type=float, default=None,
                   help="fixed temperature for the L-family (default 0.7)")
    p.add_argument("--sweeps", type=int, default=20000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--over-relax", type=int, default=3,
                   help="microcanonical over-relaxation sweeps per Metropolis sweep")
    p.add_argument("--updater", default="metropolis",
                   help="'metropolis' (+ over-relaxation; default) or 'wolff'")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m10(args):
    p = argparse.ArgumentParser(add_help=False)
    # M10 reuses M01/M04's setup — J = −1 (antiferromagnetic) and the STAGGERED
    # order parameter — over a window straddling the Néel point T_N = Onsager's
    # exact 2.2692 (the bipartite gauge duality makes the AFM the FM in disguise).
    p.add_argument("--L", type=int, default=128,
                   help="lattice side (default 128)")
    p.add_argument("--quick", action="store_true",
                   help="L=48, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=2.0)
    p.add_argument("--t-max", type=float, default=2.6)
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m11(args):
    p = argparse.ArgumentParser(add_help=False)
    # M11 sweeps a T-window down toward T = 0 (the 2D EA glass orders only at T = 0
    # — no finite-T transition) and shows the disorder-averaged P(q) broadening as T
    # falls. It batches realizations × temperatures × 2 replicas in one GPU pass; the
    # disorder average over MANY realizations is mandatory. L is modest (spin glasses
    # are expensive and the overlap needs two replicas each).
    #
    # The cold edge used to default to T=0.6, because below ≈0.5–0.6 single-spin
    # Metropolis cannot equilibrate the L=16 glass in tractable time and the coldest
    # points fall into an under-equilibration dip. Since 2026-08-19 the run TEMPERS
    # by default (parallel tempering, the move that failure exists to motivate) and
    # the cold edge is 0.30 — measured, at the same wall-clock, with the untempered
    # ladder kept alongside as a comparison so nothing already published is silently
    # replaced. These defaults must track lab.m11's, or `lab m11` would quietly run
    # the old experiment while the module claimed the new one.
    from . import m11 as _m11_defaults
    p.add_argument("--L", type=int, default=16,
                   help="lattice side (default 16; spin glasses are expensive)")
    p.add_argument("--quick", action="store_true",
                   help="L=8, few realizations, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=_m11_defaults.T_FLOOR_TEMPERED,
                   help=("cold edge (default %(default)s — reachable because the run "
                         "tempers; the untempered floor is 0.6)"))
    p.add_argument("--swap-every", type=int, default=_m11_defaults.SWAP_EVERY,
                   help=("sweeps between parallel-tempering exchanges (default "
                         "%(default)s; 0 disables tempering, which below T=0.6 "
                         "produces the dip and is refused by check_m11)"))
    p.add_argument("--no-comparison", action="store_true",
                   help=("skip the second, untempered ladder. Halves the wall-clock "
                         "and drops the side-by-side that keeps the dip visible"))
    p.add_argument("--t-max", type=float, default=2.0)
    p.add_argument("--n-temps", type=int, default=16)
    p.add_argument("--realizations", type=int, default=64,
                   help="quenched ±J disorder realizations to average P(q) over")
    p.add_argument("--sweeps", type=int, default=60000)
    p.add_argument("--burnin", type=int, default=30000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m12(args):
    p = argparse.ArgumentParser(add_help=False)
    # M12 is the 3D EA glass: a genuine finite-T spin-glass transition at the ±J
    # benchmark (m12.T_SG_BENCHMARK), found by the disorder-averaged Binder-cumulant
    # CROSSING across ≥3 lattice sizes on a SHARED T ladder that straddles it.
    # Parallel tempering is mandatory — single-spin Metropolis can't equilibrate the
    # cold rungs and the crossing washes out (M11's documented failure mode). --quick
    # runs a small CPU pass that proves the code end to end but does not generally
    # resolve the crossing (that needs a GPU run with many disorder realizations); it
    # then ships a [~] null, per the lab's convention.
    p.add_argument("--L-values", default="4,6,8",
                   help="comma-separated even lattice sizes on the shared ladder (default 4,6,8)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (few realizations, short sweep) — proves the code, not the physics")
    p.add_argument("--t-min", type=float, default=0.4,
                   help="cold edge — must sit below the T_SG benchmark (default 0.4)")
    p.add_argument("--t-max", type=float, default=1.6,
                   help="hot edge — the ergodic end parallel tempering decorrelates in (default 1.6)")
    p.add_argument("--n-temps", type=int, default=16)
    p.add_argument("--realizations", type=int, default=200,
                   help="quenched ±J disorder realizations to average the Binder cumulant over")
    p.add_argument("--sweeps", type=int, default=20000)
    p.add_argument("--burnin", type=int, default=10000)
    p.add_argument("--swap-every", type=int, default=10,
                   help="attempt a parallel-tempering even/odd swap round every N sweeps")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m13(args):
    p = argparse.ArgumentParser(add_help=False)
    # M13 is the frustrated triangular antiferromagnet (J=−1): NO ordering transition, a
    # macroscopically degenerate ground state, and the signature is the residual entropy
    # S0/N = 0.3383 k_B (Wannier), measured by integrating C(T)/T from S(∞)=ln2 down. So
    # the window is WIDE (near T=0 up to high T where S→ln2), not a tight peak straddle,
    # and the grid is geometric — packed into the low-T hump where C/T carries its weight.
    # L must be a multiple of 3 (the triangular 3-colour update's periodic seam).
    p.add_argument("--L", type=int, default=96,
                   help="lattice side, a multiple of 3 (default 96)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (L=24, short sweep) — proves the pipeline end to end")
    p.add_argument("--t-min", type=float, default=0.10,
                   help="cold edge — near T=0 to expose the residual (default 0.10)")
    p.add_argument("--t-max", type=float, default=14.0,
                   help="hot edge — high enough that S climbs back to ln2 (default 14.0)")
    p.add_argument("--n-temps", type=int, default=80,
                   help="geometric temperature-grid points (default 80)")
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m14(args):
    p = argparse.ArgumentParser(add_help=False)
    # M14 is the random-bond Ising model swept along its Nishimori line (tanh(1/T)=1−2p).
    # The VERIFIED claim is the exact Nishimori-line energy E/N = −2 tanh(1/T); the sweep
    # also maps the ferro-order collapse toward the multicritical point p_c≈0.109 (only
    # approximately at this scale). L defaults to a two-size (12,24) map, the larger of
    # which grades the energy; the ±J disorder is averaged over many realizations. --quick
    # runs a small CPU pass that proves the pipeline end to end.
    p.add_argument("--L-values", default="12,24",
                   help="comma-separated map lattice sizes; the largest grades the energy (default 12,24)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (L=8,12, few realizations, short sweep) — proves the pipeline")
    p.add_argument("--p-values", default=None,
                   help="comma-separated AF-bond fractions along the Nishimori line "
                        "(default 0.04,0.06,0.08,0.10,0.1094,0.12,0.14,0.16)")
    p.add_argument("--realizations", type=int, default=64,
                   help="quenched ±J disorder realizations to average over")
    p.add_argument("--sweeps", type=int, default=10000)
    p.add_argument("--burnin", type=int, default=4000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m15(args):
    p = argparse.ArgumentParser(add_help=False)
    # M15 is NON-equilibrium: a single lattice quenched from T=inf to T<T_c, evolved under
    # single-spin Glauber (heat-bath) dynamics — cluster updates are FORBIDDEN, they destroy
    # the coarsening. There is no temperature sweep; T is the fixed quench target (default
    # ~0.66·T_c). The x-axis is Monte-Carlo time (sweeps). L defaults to 512 (a large box so
    # domains grow over a wide window before finite-size saturation); n_seeds averages several
    # random starts. --quick runs a small CPU pass that proves the pipeline end to end.
    p.add_argument("--L", type=int, default=512,
                   help="lattice side (default 512; bigger box = wider scaling window)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (L=96, few seeds, short time) — proves the pipeline")
    p.add_argument("--T", type=float, default=None,
                   help="quench temperature < T_c (default ~0.66·T_c ≈ 1.498)")
    p.add_argument("--seeds", type=int, default=48,
                   help="independent random initial conditions, averaged (default 48)")
    p.add_argument("--t-max", type=int, default=8000,
                   help="final Monte-Carlo time in sweeps (default 8000)")
    p.add_argument("--n-times", type=int, default=52,
                   help="log-spaced measurement times (default 52)")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m16(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=12)
    p.add_argument("--quick", action="store_true",
                   help="small CPU aging pass for pipeline validation")
    p.add_argument("--T", type=float, default=0.60)
    p.add_argument("--realizations", type=int, default=64)
    p.add_argument("--waiting-times", default="16,32,64,128")
    p.add_argument("--delta-times", default="8,16,32,64,128,256")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m18(args):
    p = argparse.ArgumentParser(add_help=False)
    # M18 is an ABSORBING-STATE transition: the all-zero lattice is a trap with no
    # thermal escape, so there is no temperature and the control parameter is the
    # transmission probability p. The measurement is a BRACKET — a subcritical and
    # a supercritical run bound delta between them — so the two p values are the
    # experiment's input and the run refuses if they turn out not to straddle p_c.
    # L must stay well above xi_perp ~ t_max^(1/1.766) or the box is being measured.
    p.add_argument("--p-low", type=float, default=None,
                   help="subcritical bracket endpoint (default 0.22410)")
    p.add_argument("--p-high", type=float, default=None,
                   help="supercritical bracket endpoint (default 0.22420)")
    p.add_argument("--L", type=int, default=None, help="lattice side (default 2048)")
    p.add_argument("--batch", type=int, default=None, help="independent lattices (default 4)")
    p.add_argument("--t-max", type=int, default=None, help="time steps (default 50000)")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--device", default="cuda", help="cuda (ROCm HIP) or cpu")
    p.add_argument("--quick", action="store_true",
                   help="small fast pass — proves bracket + controls end to end on CPU")
    return p.parse_args(args)


def _parse_m17(args):
    p = argparse.ArgumentParser(add_help=False)
    # M17 is NON-equilibrium and watches a SURFACE, not spins: a 1+1d interface grown on a
    # periodic ring. There is no temperature — the control parameter is the corner-flip
    # probability p, which must stay strictly inside (0,1) (at p=1 the sublattice-parallel
    # rule is deterministic and stops being stochastically rough, i.e. stops being KPZ).
    # The x-axis is Monte-Carlo time. L must be large enough that the ring never saturates
    # inside t_max (the runner asserts w(t_max) ≤ 0.20·√L). --quick proves the pipeline on CPU.
    p.add_argument("--L", type=int, default=4096,
                   help="KPZ ring size (default 4096; bigger ring = later saturation)")
    p.add_argument("--quick", action="store_true",
                   help="small fast pass — proves growth + controls + distributions end to end")
    p.add_argument("--batch", type=int, default=64,
                   help="independent rings averaged for the width (default 64)")
    p.add_argument("--t-max", type=int, default=8000,
                   help="final Monte-Carlo time in sweeps for the KPZ run (default 8000)")
    p.add_argument("--n-times", type=int, default=44,
                   help="log-spaced measurement sweeps (default 44)")
    p.add_argument("--dist-t", type=int, default=400,
                   help="sweeps for the Tracy-Widom distribution runs (default 400)")
    p.add_argument("--droplet-batch", type=int, default=6000,
                   help="independent droplets sampled for the GUE test (default 6000)")
    p.add_argument("--flat-batch", type=int, default=3000,
                   help="independent flat rings sampled for the GOE test (default 3000)")
    p.add_argument("--p-flip", type=float, default=0.5,
                   help="corner-flip probability, strictly in (0,1) (default 0.5)")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_k01(args):
    # Imported here (not at module scope) so the CLI stays import-light; k01 itself
    # defers NumPy to run time, so this costs nothing but keeps the parser defaults
    # anchored to the calibration identity rather than re-typed beside it.
    from . import k01 as k01_mod

    p = argparse.ArgumentParser(add_help=False)
    # K01 has no temperature and no lattice: the control parameter is the coupling
    # K, swept from zero up to 4γ so the sweep straddles the exact K_c = 2γ. The
    # fixed calibration identity is N=2000, γ=0.5, 25 points — `--quick` changes it
    # deliberately, which makes the run a diagnostic rather than the calibration
    # (checks.check_k01 says so out loud, the same way `lab c01 --terms 12` does).
    p.add_argument("--n", type=int, default=k01_mod.CALIBRATION_N,
                   help="oscillators, must be even (default 2000)")
    p.add_argument("--gamma", type=float, default=k01_mod.CALIBRATION_GAMMA,
                   help="Lorentzian half-width γ; exact K_c = 2γ (default 0.5)")
    p.add_argument("--points", type=int, default=k01_mod.CALIBRATION_POINTS,
                   help="couplings swept over [0, 4γ] (default 25)")
    p.add_argument("--quick", action="store_true",
                   help="small fast pass — proves the sweep, the branch, and the control end to end")
    p.add_argument("--dt", type=float, default=0.02,
                   help="RK4 step (default 0.02; dt=0.01 agrees to four decimals)")
    p.add_argument("--t-burn", type=float, default=100.0)
    p.add_argument("--t-measure", type=float, default=300.0)
    p.add_argument("--seed", type=int, default=42)
    ns = p.parse_args(args)
    if ns.quick:
        ns.n, ns.points = 500, 13
        ns.t_burn, ns.t_measure = 50.0, 150.0
    return ns


def _parse_k02(args):
    # Same import-late rule as _parse_k01: the parser defaults are anchored to the
    # ladder identity rather than re-typed beside it, so the CLI and the runner
    # cannot drift.
    from . import k02 as k02_mod

    p = argparse.ArgumentParser(add_help=False)
    # K02's control is not one coupling but a LADDER of population sizes. The fixed
    # identity is the 5-rung ladder over 3 initial conditions at γ=0.5; --quick
    # deliberately changes it, which makes the run a diagnostic rather than this
    # measurement (checks.check_k02 says so out loud).
    p.add_argument("--ladder", type=str,
                   default=",".join(str(n) for n in k02_mod.CALIBRATION_LADDER),
                   help="comma-separated N-ladder (default 250,500,1000,2000,4000)")
    p.add_argument("--seeds", type=str,
                   default=",".join(str(s) for s in k02_mod.CALIBRATION_SEEDS),
                   help="comma-separated initial conditions averaged per rung")
    p.add_argument("--gamma", type=float, default=k02_mod.CALIBRATION_GAMMA,
                   help="Lorentzian half-width γ; exact K_c = 2γ (default 0.5)")
    p.add_argument("--quick", action="store_true",
                   help="small fast pass — proves the ladder, the fits, and the check end to end")
    p.add_argument("--dt", type=float, default=k02_mod.DT)
    p.add_argument("--t-burn", type=float, default=k02_mod.T_BURN)
    p.add_argument("--t-measure", type=float, default=k02_mod.T_MEASURE)
    # The r(K_c,N) calibration needs windows an order of magnitude longer than the
    # sweep's — relaxation at criticality slows with N, and reading the sweep's window
    # at N=4000 measures a transient. See k02.critical_coherence.
    p.add_argument("--critical-seeds", type=int, default=k02_mod.CRITICAL_SEEDS)
    p.add_argument("--critical-t-burn", type=float, default=k02_mod.CRITICAL_T_BURN)
    p.add_argument("--critical-t-measure", type=float, default=k02_mod.CRITICAL_T_MEASURE)
    ns = p.parse_args(args)
    if ns.quick:
        ns.ladder, ns.seeds = "250,500", "42"
        ns.t_burn, ns.t_measure = 20.0, 60.0
        ns.critical_seeds = 2
        ns.critical_t_burn, ns.critical_t_measure = 10.0, 20.0
    ns.ladder = tuple(int(x) for x in ns.ladder.split(",") if x.strip())
    ns.seeds = tuple(int(x) for x in ns.seeds.split(",") if x.strip())
    return ns


def _parse_k03(args):
    # Import-late like _parse_k01/_parse_k02: defaults anchored to the module's
    # measurement identity so the CLI and the runner cannot drift.
    from . import k03 as k03_mod

    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--n", type=int, default=k03_mod.N_OSCILLATORS)
    p.add_argument("--gamma", type=float, default=k03_mod.GAMMA,
                   help="Lorentzian half-width γ; exact K_c = 2γ (default 0.5)")
    p.add_argument("--points", type=int, default=k03_mod.EPS_POINTS,
                   help="ε grid points per branch (default 7)")
    p.add_argument("--eps-min", type=float, default=k03_mod.EPS_MIN)
    p.add_argument("--eps-max", type=float, default=k03_mod.EPS_MAX)
    p.add_argument("--rungs", type=int, default=k03_mod.LADDER_RUNGS,
                   help="h>0 field-ladder rungs per column (default 3)")
    p.add_argument("--quick", action="store_true",
                   help="small fast pass — proves grid, ladders, gates and "
                        "check end to end; will not resolve the exponents")
    p.add_argument("--dt", type=float, default=k03_mod.DT)
    p.add_argument("--t-burn", type=float, default=k03_mod.T_BURN)
    p.add_argument("--t-measure", type=float, default=k03_mod.T_MEASURE)
    p.add_argument("--seed", type=int, default=42)
    ns = p.parse_args(args)
    if ns.quick:
        ns.n, ns.points, ns.rungs = 200, 4, 2
        ns.t_burn, ns.t_measure = 30.0, 60.0
    return ns


def _parse_k04(args):
    # Import-late like the other K parsers: defaults anchored to the module's
    # calibration identity so the CLI and the runner cannot drift. A run that
    # overrides any of them is a diagnostic and check_k04 says so out loud.
    from . import k04 as k04_mod

    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--n", type=int, default=k04_mod.CALIBRATION_N,
                   help="oscillators (default 100 — the calibration)")
    p.add_argument("--b", type=float, default=k04_mod.B_DISSIPATION,
                   help="charging-curve concavity b > 0 (default 3.0)")
    p.add_argument("--eps", type=float, default=k04_mod.CALIBRATION_EPS,
                   help="per-oscillator flash kick ε (default 0.001)")
    p.add_argument("--trials", type=int, default=k04_mod.CALIBRATION_TRIALS,
                   help="independent initial conditions (default 200)")
    p.add_argument("--max-events", type=int,
                   default=k04_mod.CALIBRATION_MAX_EVENTS)
    p.add_argument("--no-ladders", action="store_true",
                   help="skip the reported-not-graded N and ε ladders")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_c01(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--terms", type=int, default=40)
    return p.parse_args(args)


def _parse_c05(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--digits", type=int, default=None,
                   help="reference expansion length (diagnostic only; the "
                        "public calibration identity is fixed)")
    p.add_argument("--deep", type=int, default=None,
                   help="deep extraction position (diagnostic only)")
    return p.parse_args(args)


def _parse_a01(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--sectors", type=int, default=8,
                   help="maximum number of official SPOC sectors (default 8)")
    p.add_argument("--cache-dir", default=None,
                   help="optional FITS cache; defaults to ~/.lab/cache/a01")
    p.add_argument("--deadline", type=float, default=600.0,
                   help="hard end-to-end deadline in seconds (default 600)")
    return p.parse_args(args)


def _parse_a03(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--event", default="GW170817",
                   help="GWOSC event name (default GW170817 — a BNS, where an "
                        "inspiral-only template is the correct model)")
    p.add_argument("--catalog", default="GWTC-1-confident")
    p.add_argument("--version", default="v3")
    p.add_argument("--dmc", type=float, default=2e-5,
                   help="chirp-mass grid step in Msun (default 2e-5)")
    p.add_argument("--cache-dir", default=None,
                   help="optional strain cache; defaults to ~/.lab/cache/a03")
    return p.parse_args(args)


def _parse_a04(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--sector", type=int, default=None, help="TESS sector (default 2)")
    p.add_argument("--targets", type=int, default=24,
                   help="how many sector targets to search (default 24). A full "
                        "sector is thousands; this is a deterministic SAMPLE and "
                        "the report says so.")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--cache-dir", default=None)
    return p.parse_args(args)


def _parse_i01(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--frames", default=None,
                   help="real .npy/.npz dark stack or directory of 2-D .npy frames")
    p.add_argument("--camera", type=int, default=None,
                   help="capture from this real camera index in a timeout-bounded child process")
    p.add_argument("--capture-output", default=None,
                   help="saved .npy capture path (default ~/.lab/captures/<timestamp>.npy)")
    p.add_argument("--capture-frames", type=int, default=24,
                   help="grayscale frames to acquire (default 24; calibration needs at least 16)")
    p.add_argument("--capture-timeout", type=float, default=30.0,
                   help="hard acquisition deadline in seconds (default 30)")
    p.add_argument("--capture-width", type=int, default=None,
                   help="optional requested frame width")
    p.add_argument("--capture-height", type=int, default=None,
                   help="optional requested frame height")
    return p.parse_args(args)


def _run_next(args, dry, lock_path=None):
    """Pick and dispatch this turn's experiment. Selection precedence (each
    branch prints its one-line reason, dry-run included):

      1. FRONTIER — the open milestone, when it has a runner and passes its
         hardware gate (preserves the 2026-06-26 decision).
      2. VALUE-FUNCTION PLANNER — otherwise, `curriculum.plan_turn` scores
         every eligible ROTATION member by value/cost derived from the
         receipts ledger (class > staleness > repeat decay > cost) and the
         decision rides inside the receipt the run writes. Gated or
         runnerless slots are skipped with a disclosed one-line reason (a log
         line — never a receipt, never a science row). Any planner exception
         falls back to the round-robin `select_rotation` walk, logged by name
         — the scheduler must never die of its own planner.
      3. M01 HEARTBEAT — only when nothing is eligible (fail closed,
         named reason).

    Selection is read-only — it never edits MILESTONES.md; a milestone is only
    marked done by the verify gate + a human-reviewed PR. Decisions:
    docs/investigations/2026-06-26-heartbeat-vs-lab-next.md and
    docs/investigations/2026-08-01-portfolio-rotation.md.

    ``lock_path``, when the caller holds the run lock, is stamped with the
    selected milestone before dispatch.
    """
    from . import publish as publish_mod
    passthrough = [a for a in args[1:] if a != "--dry-run"]
    text = (publish_mod.MILESTONES_MD.read_text(encoding="utf-8")
            if publish_mod.MILESTONES_MD.exists() else "")
    milestones = publish_mod.parse_milestones(text)
    open_mid, has_runner = _select_next(milestones)
    skips: list[tuple[str, str]] = []
    mid: str | None = None
    subcmd: str | None = None
    reason = ""
    planned_decision: dict | None = None
    if open_mid is not None and has_runner:
        gate_reason = curriculum.hardware_gate_reason(open_mid)
        if gate_reason is None:
            mid, subcmd = open_mid, RUNNERS[open_mid]
            reason = f"open milestone {open_mid}"
        else:
            skips.append((open_mid, gate_reason))
    if subcmd is None:
        if open_mid is None:
            why = "no open milestone"
        elif not has_runner:
            why = f"no runner for {open_mid} yet"
        else:
            why = f"open milestone {open_mid} is hardware-gated"
        try:
            records, durations = _planner_ledger()
            status_map = {
                str(m.get("id")): str(m.get("status"))
                for m in milestones if m.get("id")
            }
            pick: str | None
            try:
                pick, decision = curriculum.plan_turn(
                    records, status_map, durations=durations,
                    hunt_status=_hunt_status_for_dispatch(),
                )
                skips.extend(decision.get("skips", []))
                if pick == curriculum.HUNT_CANDIDATE:
                    # The survey slot: `lab hunt` runs a bounded, resumable
                    # A05 slice whose driver owns its own checkpoint, receipt
                    # and check. It writes a HUNT receipt (reports/hunts/),
                    # not a run receipt, so the planned-block seam does not
                    # apply — the decision is disclosed here in the log line.
                    mid, subcmd = "A05", "hunt"
                    passthrough = []
                    reason = f"{why} — {decision['reason']}"
                elif pick is not None and pick in RUNNERS:
                    mid, subcmd = pick, RUNNERS[pick]
                    reason = f"{why} — {decision['reason']}"
                    planned_decision = decision
                else:
                    subcmd = "run"
                    reason = (f"{why} — planner found nothing eligible "
                              "— M01 heartbeat")
            except Exception as exc:  # noqa: BLE001 — the scheduler must never
                # die of its own planner: fall back to the round-robin walk.
                print(f"lab next · planner failed ({exc}) — "
                      "falling back to the rotation walk")
                pointer = curriculum.rotation_pointer(records)
                pick, rot_skips = curriculum.select_rotation(milestones, pointer)
                skips.extend(rot_skips)
                if pick is not None:
                    mid, subcmd = pick, RUNNERS[pick]
                    if pointer is not None:
                        after = f"rotation continues after {pointer}"
                    else:
                        # No receipt the rotation owns. The claim must match
                        # the selection — say WHY the walk opens at slot 0,
                        # and name the out-of-rotation receipt (manual
                        # M12/M16, a just-verified frontier run) that is
                        # deliberately NOT the pointer, rather than implying
                        # an empty ledger.
                        newest = curriculum.newest_receipt_milestone(records)
                        after = (
                            "no receipts — rotation starts at its first slot"
                            if newest is None else
                            f"no rotation receipt yet (newest is {newest}, "
                            "outside the rotation) — starting at its first slot"
                        )
                    reason = f"{why} — {after}"
                else:
                    subcmd = "run"
                    reason = (f"{why} — rotation found nothing eligible "
                              "— M01 heartbeat")
        except Exception as exc:  # noqa: BLE001 — scheduler fails CLOSED, named
            subcmd = "run"
            reason = f"{why} — rotation unavailable ({exc}) — M01 heartbeat"
    label = mid or "—"
    target_mid = mid or "M01"
    passthrough, dropped = filter_scheduler_options(target_mid, passthrough)
    option_note = (
        f" · ignored unsupported scheduler option(s): {', '.join(dropped)}"
        if dropped else ""
    )
    # Disclosed once per pass, to stdout/log — a skip is not a failure and
    # not a success; it is a named absence, and it must not spam receipts.
    for skipped_mid, skip_reason in skips:
        print(f"lab next · skipped {skipped_mid} — {skip_reason}")
    if dry:
        print(
            f"lab next → {label}: would run `lab {subcmd}` "
            f"({reason}){option_note}"
        )
        return 0
    if lock_path is not None:
        note_lock_milestone(lock_path, mid)
    print(
        f"lab next → {label}: running `lab {subcmd}` "
        f"({reason}){option_note}"
    )
    if planned_decision is None:
        return main([subcmd, *passthrough])
    # A scheduled receipt carries its own selection rationale (the compact
    # `planned` block); the seam is armed around exactly this one dispatch and
    # cleared in the finally so a manual run can never inherit it.
    from . import receipt as receipt_mod
    receipt_mod.set_planned_decision(planned_decision)
    try:
        return main([subcmd, *passthrough])
    finally:
        receipt_mod.clear_planned_decision()


def main(argv=None):
    # Windows consoles default to the cp1252 codec, which can't encode the
    # unicode the CLI prints (→ ✓ · 🌱) or the reports carry — without this,
    # every `lab` invocation crashes with a UnicodeEncodeError. A no-op where
    # stdout is already UTF-8 (Linux/macOS) or isn't reconfigurable (a pipe).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "open"

    if cmd in ("help", "-h", "--help"):
        print(HELP); return 0

    if cmd == "open":
        path = LAB_HOME / "latest.html"
        if not path.exists():
            print("no report yet — run `lab run` first.", file=sys.stderr); return 1
        webbrowser.open(f"file://{path}")
        print(path); return 0

    if cmd == "web":
        from .publish import REPO_ROOT
        path = REPO_ROOT / "web" / "index.html"
        if not path.exists():
            print("web page missing — expected web/index.html", file=sys.stderr); return 1
        webbrowser.open(f"file://{path}")
        print(path); return 0

    if cmd == "shelf":
        # The shelf-exit contract, enforced: a pure read of the committed
        # receipts — writes nothing, publishes nothing (surfaces render on
        # their own schedule, from the same derivation).
        import argparse
        from datetime import date as _date
        from . import shelf as shelf_mod
        from .publish import REPO_ROOT
        p = argparse.ArgumentParser(prog="lab shelf")
        p.add_argument("--json", action="store_true")
        p.add_argument("--today", default=None,
                       help="grade as of this YYYY-MM-DD (default: today)")
        opts = p.parse_args(args[1:])
        today = (_date.fromisoformat(opts.today) if opts.today
                 else _date.today())
        rulings = REPO_ROOT / "docs" / "shelf-rulings.json"
        entries = shelf_mod.register(
            REPO_ROOT / "reports" / "hunts",
            rulings if rulings.exists() else None, today)
        if opts.json:
            print(json.dumps(entries, indent=2))
        else:
            print(shelf_mod.render_text(entries))
        return 0

    if cmd == "hunt":
        # The scheduler's survey slot: a bounded, resumable A05 hunt slice.
        # scripts/a05_hunt.py owns checkpointing, the committed receipt and
        # check_a05; this wrapper pins slot-safe defaults (well inside the
        # Windows task ExecutionTimeLimit) and lets explicit flags override.
        import subprocess
        from . import publish as publish_mod
        script = publish_mod.REPO_ROOT / "scripts" / "a05_hunt.py"
        if not script.exists():
            print("hunt driver missing — expected scripts/a05_hunt.py",
                  file=sys.stderr)
            return 1
        extra = list(args[1:])
        defaults = []
        if not any(a == "--n" for a in extra):
            # The bare slice must be COMPLETABLE inside the bare budget, or no
            # receipt is ever written (an incomplete slice writes nothing by
            # design) and the box's turn freezes. 150 was sized before the
            # 2026-08-20 search level-ups made each target minutes-dear;
            # measured on win 2026-08-22 it advanced ~2 targets per 45-minute
            # slot — a receipt in weeks. Ruled by Ben 2026-08-22: shrink the
            # bare slice. Loam's committed receipts are n=5-25, so small
            # slices are established practice; the false-alarm-floor statistic
            # is simply computed over fewer stars per receipt and keeps
            # accruing across the floor history. Attended runs override.
            defaults += ["--n", "12"]
        if not any(a == "--minutes" for a in extra):
            defaults += ["--minutes", "45"]
        if not any(a == "--sector" for a in extra):
            # A bare (scheduled) hunt must hunt THIS box's lane, never the
            # driver's hardcoded default — loam's bare survey-slot hunt
            # defaulted into win's sector on 2026-08-15 and overwrote a
            # committed receipt. The sector with the most remaining committed
            # coverage in the lane is the honest pick; with no lane or no
            # remaining lane coverage a bare hunt refuses (attended runs say
            # `lab hunt --sector N` explicitly).
            status = _hunt_status_for_dispatch()
            if status is None:
                reason = (curriculum.hardware_gate_reason("A05")
                          or "no eligible lane sector")
                print(f"lab hunt · refusing bare dispatch — {reason}",
                      file=sys.stderr)
                return 3
            sector = max(status["per_sector"],
                         key=lambda s: status["per_sector"][s])
            defaults += ["--sector", str(sector)]
        env = dict(os.environ)
        src_dir = str(publish_mod.REPO_ROOT / "src")
        env["PYTHONPATH"] = (src_dir + os.pathsep + env["PYTHONPATH"]
                             if env.get("PYTHONPATH") else src_dir)
        return subprocess.call(
            [sys.executable, str(script), *defaults, *extra],
            env=env, cwd=str(publish_mod.REPO_ROOT))

    if cmd == "publish":
        from . import publish as publish_mod
        gist = None
        if "--gist" in args:
            i = args.index("--gist")
            gist = args[i + 1] if i + 1 < len(args) else None
        path = publish_mod.publish(gist_id=gist)
        print(f"  ✓ snapshot: {path}")
        return 0

    if cmd == "backfill":
        from . import publish as publish_mod
        dry = "--dry-run" in args
        paths = publish_mod.backfill(dry_run=dry)
        verb = "would write" if dry else "wrote"
        for p in paths:
            print(f"  {verb}: {p}")
        print(f"\n{verb} {len(paths)} file(s) into reports/."
              + (" (dry run — nothing written)" if dry else ""))
        return 0

    if cmd == "verify":
        from . import checks
        rerun_smoke = "--rerun-smoke" in args
        bless = "--bless" in args
        ids = [a for a in args[1:] if not a.startswith("-")] or None
        results = checks.verify(ids)
        rc = 0
        if results:
            mark = {"pass": "✓", "fail": "✗", "unchecked": "·", "no-report": "?"}
            for r in results:
                print(f"  {mark.get(r['status'], '?')} {r['id']} [{r['status']}] — {r['detail']}")
            # `needs-deps` is disclosed on its own line and does NOT block:
            # it means this environment cannot execute the check, not that the
            # milestone failed. Every other non-pass still blocks.
            blocked = [r for r in results
                       if r["status"] not in ("pass", "needs-deps")]
            deferred = [r for r in results if r["status"] == "needs-deps"]
            if deferred:
                print(f"\n{len(deferred)} check(s) deferred to the full-stack job: "
                      + ", ".join(r["id"] for r in deferred))
            if blocked:
                summary = ", ".join(f"{r['id']} ({r['status']})" for r in blocked)
                print(f"\nVERIFICATION INCOMPLETE: {summary}", file=sys.stderr)
                print("Every promoted milestone must have a registered check and a readable passing report.",
                      file=sys.stderr)
                rc = 1
        elif not rerun_smoke:
            print("no verified milestones to check.", file=sys.stderr)
            return 1

        if bless and not rerun_smoke:
            print("--bless only applies with --rerun-smoke.", file=sys.stderr)
            return 2

        if rerun_smoke:
            from . import determinism
            if bless:
                path = determinism.write_golden()
                print(f"  ✓ blessed determinism golden → {path}")
                return 0
            gate = determinism.run_gate()
            glyph = "✓" if gate["ok"] else "✗"
            print(f"  {glyph} determinism (golden-seed L=16 smoke, {gate['golden']}) — {gate['detail']}")
            if not gate["ok"]:
                print("\nDETERMINISM GATE FAILED: the pinned CPU smoke run did not reproduce.",
                      file=sys.stderr)
                rc = 1
        return rc

    if cmd == "scoreboard":
        from . import scoreboard as scoreboard_mod
        from . import archive as archive_mod
        entries = scoreboard_mod.collect_entries()
        png = scoreboard_mod.write_scoreboard(entries=entries)
        n_pass = sum(1 for e in entries if e.passed)
        print(f"  ✓ scoreboard: {len(entries)} milestones, {n_pass} within tolerance → {png}")
        for e in entries:
            mark = "✓" if e.passed else "✗"
            print(f"    {mark} {e.milestone} {e.observable}: {e.value_label()}  (z={e.z:+.2f})")
        index = archive_mod.write_index()
        print(f"  ✓ embedded into {index}")
        if "--open" in args:
            webbrowser.open(index.as_uri())
        return 0 if n_pass == len(entries) else 1

    if cmd == "controls":
        import json as _json
        from . import controls as controls_mod
        from . import checks
        from .publish import today_local
        rep = controls_mod.build_controls_report()
        ok, detail = checks.check_controls(rep)
        # The receipt lands in ~/.lab (not the committed archive): a published control
        # that would ride into pot.json is a separate promotion step.
        LAB_HOME.mkdir(parents=True, exist_ok=True)
        out = LAB_HOME / f"{today_local()}-controls.json"
        out.write_text(_json.dumps(rep, indent=2), encoding="utf-8")
        print(f"  {'✓' if ok else '✗'} controls — {detail}")
        print(f"  receipt: {out}")
        return 0 if ok else 1

    if cmd == "setup":
        from . import setup as setup_mod
        flags = args[1:]
        print("windowsill-lab — pre-flight\n")
        checks = setup_mod.health_checks()
        for c in checks:
            print(f"  {'✓' if c['ok'] else '✗'} {c['name']}: {c['detail']}")
        if "--check" in flags:
            return 0 if all(c["ok"] for c in checks) else 1
        if not all(c["ok"] for c in checks):
            print("\nfix the ✗ above first, or re-run with --check to inspect.", file=sys.stderr)
            return 1
        plan = setup_mod.install(prefer_cron="--cron" in flags, dry_run="--dry-run" in flags)
        print(f"\nnightly job ({plan['method']}): {plan['nightly']}")
        for s in plan["steps"]:
            print(f"  · {s}")
        for n in plan["notes"]:
            print(n)
        if "--dry-run" in flags:
            print("\ndry run complete — nothing was written or scheduled.")
        else:
            print("\nthe windowsill will now grow on its own. 🌱")
        return 0

    if cmd == "m02":
        ns = _parse_m02(args[1:])
        from . import fss
        from . import render as render_mod
        if ns.L:
            L_values = tuple(int(x) for x in ns.L.split(","))
        elif ns.quick:
            L_values = (32, 64, 128)
        else:
            L_values = fss.DEFAULT_L
        unit = "cluster updates" if ns.updater == "wolff" else "sweeps"
        print(f"M02 finite-size scaling · L = {', '.join(map(str, L_values))} · "
              f"{ns.n_temps} temps in [{ns.t_min}, {ns.t_max}] · {ns.sweeps:,} {unit} "
              f"· {ns.updater} on {ns.device}")

        def _progress(L, curve):
            print(f"  ✓ L={L:<4} χ_max={curve.chi_max:8.1f} at T={curve.T_peak:.3f}"
                  f"  ({curve.wall_seconds:.1f}s)")

        result = fss.run_fss(
            L_values=L_values, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=ns.sweeps, n_burnin=ns.burnin, seed=ns.seed, device=ns.device,
            updater=ns.updater, wolff_init=ns.wolff_init, progress=_progress,
        )
        report = fss.to_report(result)
        print(f"  → χ_max ∝ L^{result.slope:.3f}  (theory γ/ν = 7/4 = 1.75, "
              f"R²={result.r2:.4f})  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_fss(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m03":
        ns = _parse_m03(args[1:])
        from . import m03
        from . import render as render_mod
        if ns.L:
            L_values = tuple(int(x) for x in ns.L.split(","))
        elif ns.quick:
            L_values = (16, 24, 32)
        else:
            L_values = m03.DEFAULT_L
        print(f"M03 data collapse · L = {', '.join(map(str, L_values))} · "
              f"{ns.n_temps} temps in [{ns.t_min}, {ns.t_max}] · {ns.sweeps:,} sweeps "
              f"· {ns.updater}")

        def _progress(L, curve):
            print(f"  ✓ L={L:<4} {len(curve.T)} temps  ({curve.wall_seconds:.1f}s)")

        result = m03.run_m03(
            L_values=L_values, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=ns.sweeps, n_burnin=ns.burnin, seed=ns.seed, device=ns.device,
            updater=ns.updater, progress=_progress,
        )
        report = m03.to_report(result)
        print(f"  → β/ν = {result.beta_over_nu_fit:.3f}  (theory 1/8 = "
              f"{m03.BETA_OVER_NU:.3f}, residual={result.collapse_quality:.1e})"
              f"  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m03(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m04":
        ns = _parse_m04(args[1:])
        from . import m04
        from . import render as render_mod
        L = 48 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        print(f"M04 2D Ising specific heat · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps on {ns.device}")

        def _progress_m04(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m04.run_m04(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=ns.device,
            progress=_progress_m04,
        )
        report = m04.to_report(result)
        print(f"  → C-peak T_c = {result.tc_cv_refined:.3f}  (Onsager exact "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)"
              f"  ·  χ cross-check {result.tc_chi_refined:.3f}  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m04(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m05":
        ns = _parse_m05(args[1:])
        from . import m05
        from . import render as render_mod
        L = 48 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        print(f"M05 triangular-lattice 2D Ising · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps on {ns.device}")

        def _progress_m05(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m05.run_m05(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=ns.device,
            progress=_progress_m05,
        )
        report = m05.to_report(result)
        print(f"  → χ-peak T_c = {result.tc_chi_refined:.3f}  (exact 4/ln3 = "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)"
              f"  ·  C cross-check {result.tc_cv_refined:.3f}  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m05(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m05-hex":
        ns = _parse_m05_hex(args[1:])
        from . import m05
        from . import render as render_mod
        L = 48 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        print(f"M05 honeycomb-lattice 2D Ising · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps on {ns.device}")

        def _progress_m05_hex(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m05.run_m05_hex(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=ns.device,
            progress=_progress_m05_hex,
        )
        report = m05.to_report_hex(result)
        print(f"  → χ-peak T_c = {result.tc_chi_refined:.3f}  (exact 2/ln(2+√3) = "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)"
              f"  ·  C cross-check {result.tc_cv_refined:.3f}  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m05(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m06":
        ns = _parse_m06(args[1:])
        from . import m06
        from . import render as render_mod
        L = 6 if ns.quick else ns.L
        sweeps = 1500 if ns.quick else ns.sweeps
        burnin = 800 if ns.quick else ns.burnin
        unit = "cluster updates" if ns.updater == "wolff" else "sweeps"
        print(f"M06 3D simple-cubic Ising · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} {unit} · {ns.updater}")

        def _progress(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m06.run_m06(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed,
            updater=ns.updater, device=ns.device, progress=_progress,
        )
        report = m06.to_report(result)
        print(f"  → χ-peak T_c = {result.tc_chi_refined:.3f}  (MC benchmark "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)"
              f"  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m06(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m07":
        ns = _parse_m07(args[1:])
        from . import m07
        from . import render as render_mod
        # Quick mode: small lattice + short Wolff burn — a fast sanity pass only.
        L = 32 if ns.quick else ns.L
        sweeps = 1000 if ns.quick else ns.sweeps
        burnin = 400 if ns.quick else ns.burnin
        q_values = (tuple(int(x) for x in ns.q.split(",")) if ns.q else m07.Q_VALUES)
        unit = "cluster updates" if ns.updater == "wolff" else "sweeps"
        print(f"M07 q-state Potts · L={L} · q={', '.join(map(str, q_values))} · "
              f"{ns.n_temps} temps per q (T_c ± {ns.half_window}) · {sweeps:,} {unit} "
              f"· {ns.updater} on {ns.device}")

        def _progress_m07(qr):
            kind = "1st-order" if qr.q >= 5 else "continuous"
            print(f"  ✓ q={qr.q} ({kind:9}) χ-peak T_c={qr.tc_chi_refined:.3f} "
                  f"(exact {qr.tc_exact:.3f}, rel. err {qr.rel_error*100:.1f}%)  "
                  f"({qr.wall_seconds:.1f}s)")

        result = m07.run_m07(
            L=L, q_values=q_values, n_temps=ns.n_temps, n_sweeps=sweeps,
            n_burnin=burnin, seed=ns.seed, device=ns.device,
            half_window=ns.half_window, updater=ns.updater, progress=_progress_m07,
        )
        report = m07.to_report(result)
        print(f"  → continuous (q≤4) → first-order (q≥5): "
              f"mean χ_max {report['continuous_mean_chi_max']:.0f} (q≤4) "
              f"vs {report['first_order_mean_chi_max']:.0f} (q≥5) — the taller "
              f"first-order spike  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m07(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m08":
        ns = _parse_m08(args[1:])
        from . import m08
        from . import render as render_mod
        # Quick mode: small lattice + short sweep — a fast sanity pass only.
        L = 32 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        unit = "cluster updates" if ns.updater == "wolff" else "sweeps"
        print(f"M08 2D XY model (BKT) · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} {unit} · {ns.updater} on {ns.device}")

        def _progress_m08(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m08.run_m08(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, over_relax=ns.over_relax,
            seed=ns.seed, device=ns.device, updater=ns.updater,
            progress=_progress_m08,
        )
        report = m08.to_report(result)
        if result.tc_crossing is not None:
            print(f"  → Υ(T)=(2/π)T crossing T_BKT = {result.tc_crossing:.3f}  "
                  f"(benchmark {result.tc_benchmark:.4f}, rel. err "
                  f"{result.rel_error*100:.1f}%)  ·  {result.wall_seconds:.0f}s")
        else:
            print(f"  → no crossing of Υ(T) with the (2/π)T jump line on this window "
                  f"(un-equilibrated or window mis-placed)  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m08(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m09":
        ns = _parse_m09(args[1:])
        from . import m09
        from . import render as render_mod
        if ns.L:
            L_values = tuple(int(x) for x in ns.L.split(","))
        elif ns.quick:
            L_values = (8, 12, 16)
        else:
            L_values = m09.DEFAULT_L
        T = ns.T if ns.T is not None else m09.DEFAULT_T
        sweeps = 2000 if ns.quick else ns.sweeps
        burnin = 800 if ns.quick else ns.burnin
        print(f"M09 2D Heisenberg (Mermin–Wagner) · L = {', '.join(map(str, L_values))} "
              f"at T={T} · {sweeps:,} sweeps · {ns.updater} on {ns.device}")

        def _progress_m09(L, r):
            print(f"  ✓ L={L:<4} ⟨|m|⟩={r.abs_mag[0]:.4f} ± {r.abs_mag_err[0]:.4f}  "
                  f"E={r.energy[0]:.3f}  accept={r.acceptance[0]:.3f}  ({r.wall_seconds:.1f}s)")

        result = m09.run_m09(
            L_values=L_values, T=T, n_sweeps=sweeps, n_burnin=burnin,
            over_relax=ns.over_relax, seed=ns.seed, device=ns.device,
            updater=ns.updater, progress=_progress_m09,
        )
        report = m09.to_report(result)
        ratio_str = " → ".join(f"{r:.3f}" for r in result.ratios) or "—"
        verdict = ("Mermin–Wagner confirmed (no finite-T order)"
                   if result.monotone_decreasing else "absence NOT reproduced")
        print(f"  → ⟨|m|⟩ drifts {', '.join(f'{m:.3f}' for m in result.abs_mag)} "
              f"(ratios {ratio_str}, slope vs 1/L = {result.slope_vs_inv_L:+.3f}) — "
              f"{verdict}  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m09(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m10":
        ns = _parse_m10(args[1:])
        from . import m10
        from . import render as render_mod
        L = 48 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        print(f"M10 antiferromagnetic Ising (J=−1) · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps on {ns.device}")

        def _progress_m10(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m10.run_m10(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=ns.device,
            progress=_progress_m10,
        )
        report = m10.to_report(result)
        print(f"  → staggered χ_s-peak T_N = {result.tc_chi_refined:.3f}  (Onsager exact "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)  ·  "
              f"C cross-check {result.tc_cv_refined:.3f}  ·  uniform ⟨|m|⟩ ≤ "
              f"{result.max_abs_mag:.3f}  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m10(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m11":
        ns = _parse_m11(args[1:])
        from . import m11
        from . import render as render_mod
        L = 8 if ns.quick else ns.L
        realizations = 8 if ns.quick else ns.realizations
        sweeps = 2000 if ns.quick else ns.sweeps
        burnin = 800 if ns.quick else ns.burnin
        print(f"M11 2D Edwards–Anderson spin glass · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {realizations} disorder realizations × 2 "
              f"replicas · {sweeps:,} sweeps on {ns.device}")

        def _progress_m11(result):
            print(f"  ✓ swept {len(result.T)} temps × {result.n_realizations} "
                  f"realizations  ({result.wall_seconds:.1f}s)")

        result = m11.run_m11(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_realizations=realizations, n_sweeps=sweeps, n_burnin=burnin,
            seed=ns.seed, device=ns.device, swap_every=ns.swap_every,
            comparison=not ns.no_comparison, progress=_progress_m11,
        )
        report = m11.to_report(result)
        verdict = ("P(q) broadens toward T=0" if result.monotone_broadening
                   else "broadening NOT clean — see report")
        print(f"  → ⟨q²⟩ grows {result.q2_hot:.3f} → {result.q2_cold:.3f} as T→0 "
              f"({result.broadening_fraction*100:.0f}% of steps) · max|⟨q⟩|="
              f"{result.max_abs_q_mean:.3f} · {verdict} · {result.wall_seconds:.0f}s")
        if result.swap_health:
            health = result.swap_health
            ladder = ("ladder connected" if health["connected"]
                      else "LADDER BROKEN at pair " + str(health["argmin_pair"]))
            print(f"  → exchange: min adjacent acceptance {health['min']:.2f}, "
                  f"mean {health['mean']:.2f}, "
                  f"{ladder}")
        if result.comparison and not result.comparison["monotone_broadening"]:
            print(f"  → without the exchange move the same ladder turns over at "
                  f"T={result.comparison['q2_argmax_T']:.2f} (the dip, kept in the report)")
        path = render_mod.render_m11(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m12":
        ns = _parse_m12(args[1:])
        from . import m12
        from . import render as render_mod
        L_values = [int(x) for x in ns.L_values.split(",") if x.strip()]
        device = ns.device
        if ns.quick:
            # A small CPU pass: proves the multi-file recipe end-to-end and writes
            # HTML+JSON. It will not generally resolve the crossing — that is the GPU
            # full run's job — so an unresolved crossing here ships as a [~] null.
            L_values = [4, 6, 8]
            realizations, n_temps = 8, 10
            sweeps, burnin, swap_every = 800, 400, 5
            device = "cpu"
        else:
            realizations, n_temps = ns.realizations, ns.n_temps
            sweeps, burnin, swap_every = ns.sweeps, ns.burnin, ns.swap_every
        print(f"M12 3D Edwards–Anderson spin glass · L={L_values} · {n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] straddling T_SG≈{m12.T_SG_BENCHMARK:g} · "
              f"{realizations} disorder "
              f"realizations × 2 replicas · parallel tempering (swap every {swap_every}) "
              f"· {sweeps:,} sweeps on {device}")

        def _progress_m12(L, r):
            print(f"  ✓ L={L:<3} swept {len(r.T)} temps  (swap≈{r.swap_rate.mean():.2f}, "
                  f"{r.wall_seconds:.1f}s)")

        result = m12.run_m12(
            L_values=L_values, T_min=ns.t_min, T_max=ns.t_max, n_temps=n_temps,
            n_realizations=realizations, n_sweeps=sweeps, n_burnin=burnin,
            swap_every=swap_every, seed=ns.seed, device=device, progress=_progress_m12,
        )
        report = m12.to_report(result)
        ct = result.crossing_T
        ct_str = f"{ct:.3f}" if ct is not None else "none"
        verdict = ("Binder crossing at T_SG≈%s — the finite-T 3D glass transition" % ct_str
                   if result.crossing_resolved
                   else f"no clean crossing near {result.t_sg_benchmark:g} — [~] null "
                        f"(needs the GPU full run)")
        print(f"  → Binder crossing T_SG = {ct_str} (benchmark {result.t_sg_benchmark:.2f} "
              f"± {result.tolerance:.2f}) · max|⟨q⟩|={result.max_abs_q_mean:.3f} · "
              f"{verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m12(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m13":
        ns = _parse_m13(args[1:])
        from . import m13
        from . import render as render_mod
        if ns.quick:
            # A small CPU pass: proves the multi-file recipe end-to-end and writes
            # HTML+JSON. The frustrated model equilibrates easily (single-spin flips walk
            # the degenerate ground manifold), so even this coarse grid usually lands the
            # integrated residual near 0.3383 — but a miss here still ships a [~] null.
            L, n_temps = 24, 40
            t_min, t_max = 0.15, 12.0
            sweeps, burnin = 3000, 1000
            device = "cpu"
        else:
            L, n_temps = ns.L, ns.n_temps
            t_min, t_max = ns.t_min, ns.t_max
            sweeps, burnin = ns.sweeps, ns.burnin
            device = ns.device
        print(f"M13 frustrated triangular antiferromagnet · L={L} · {n_temps} geometric "
              f"temps in [{t_min}, {t_max}] · {sweeps:,} sweeps on {device} · integrating "
              f"C(T)/T → residual entropy vs Wannier 0.3383")

        def _progress_m13(result):
            print(f"  ✓ swept {len(result.T)} temps  (ground energy {result.e_ground:.4f}, "
                  f"{result.wall_seconds:.1f}s)")

        result = m13.run_m13(
            L=L, T_min=t_min, T_max=t_max, n_temps=n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=device,
            progress=_progress_m13,
        )
        report = m13.to_report(result)
        verdict = ("residual entropy reproduced — Wannier 0.3383" if result.resolved
                   else "integrated residual off 0.3383 — [~] null")
        print(f"  → residual S0/N = {result.s0_measured:.4f} (Wannier {result.s0_benchmark:.4f}, "
              f"Δ={result.s0_abs_error:.4f}) · ground energy {result.e_ground:.4f}/spin (exact −1) "
              f"· {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m13(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m14":
        ns = _parse_m14(args[1:])
        from . import m14
        from . import render as render_mod
        L_values = tuple(int(x) for x in ns.L_values.split(",") if x.strip())
        p_values = (tuple(float(x) for x in ns.p_values.split(",") if x.strip())
                    if ns.p_values else
                    (0.04, 0.06, 0.08, 0.10, 0.1094, 0.12, 0.14, 0.16))
        device = ns.device
        if ns.quick:
            # A small CPU pass: proves the multi-file recipe end to end and writes HTML+JSON.
            # The Nishimori-line energy is an exact identity, so even this coarse pass usually
            # reproduces it; a miss still ships a [~] null.
            L_values = (8, 12)
            p_values = (0.05, 0.10, 0.1094, 0.15)
            realizations, sweeps, burnin = 16, 3000, 1200
            device = "cpu"
        else:
            realizations, sweeps, burnin = ns.realizations, ns.sweeps, ns.burnin
        print(f"M14 random-bond Ising (Nishimori line) · L={list(L_values)} · "
              f"p={', '.join(f'{p:.3f}' for p in p_values)} · {realizations} disorder "
              f"realizations · {sweeps:,} sweeps on {device} · verifying E/N = −2 tanh(1/T)")

        def _progress_m14(L, p, r):
            print(f"  ✓ L={L:<3} p={p:.4f} T_NL={r.T:.4f}  E={r.energy:.4f} "
                  f"(exact {r.energy_exact_nl:.4f}, Δ={abs(r.energy-r.energy_exact_nl):.4f}) "
                  f"|m|={r.abs_mag:.3f}  ({r.wall_seconds:.1f}s)")

        result = m14.run_m14(
            p_values=p_values, L_values=L_values, n_realizations=realizations,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=device,
            progress=_progress_m14,
        )
        report = m14.to_report(result)
        ph = result.mnp_order_p_half
        ph_str = f"p≈{ph:.3f}" if ph is not None else "unresolved"
        verdict = ("exact Nishimori-line energy reproduced" if result.energy_resolved
                   else "Nishimori-line energy off — [~] null")
        print(f"  → max energy Δ = {result.max_energy_dev:.4f} vs exact −2 tanh(1/T) "
              f"(L={result.gate_L}) · ferro order collapses near {ph_str} "
              f"(MNP p_c≈{result.p_c_benchmark:.4f}) · {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m14(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m15":
        ns = _parse_m15(args[1:])
        from . import m15
        from . import render as render_mod
        device = ns.device
        if ns.quick:
            # A small CPU pass: proves the quench → measure → fit → report pipeline end to end
            # and writes HTML+JSON. The scaling window is short at this scale, so the exponent
            # is coarse — a miss still ships a [~] null, per the lab's convention.
            L, seeds, t_max, n_times = 96, 8, 1500, 32
            device = "cpu"
        else:
            L, seeds, t_max, n_times = ns.L, ns.seeds, ns.t_max, ns.n_times
        from .onsager import T_C as _TC
        T = ns.T if ns.T is not None else 0.66 * float(_TC)
        print(f"M15 Glauber domain growth · L={L} · quench T={T:.3f} ({T/float(_TC):.2f}·T_c) · "
              f"{seeds} seeds · t_max={t_max:,} sweeps on {device} · fitting L(t)∼t^n vs "
              f"Allen–Cahn ½ (single-spin heat-bath — NO cluster updates)")

        def _progress_m15(result):
            print(f"  ✓ measured {len(result.times)} times  (n={result.exponent:.3f}, "
                  f"R²={result.r2:.4f}, {result.wall_seconds:.1f}s)")

        result = m15.run_m15(
            L=L, T=ns.T, n_seeds=seeds, t_max=t_max, n_times=n_times,
            seed=ns.seed, device=device, progress=_progress_m15,
        )
        report = m15.to_report(result)
        energy_n = result.energy_fit.exponent if result.energy_fit is not None else None
        en_str = f"{energy_n:.3f}" if energy_n is not None else "—"
        verdict = ("consistent with Allen–Cahn t^(1/2)" if result.supports_allen_cahn
                   else "off the Allen–Cahn ½ — [~] null")
        print(f"  → growth exponent n = {result.exponent:.3f} ± {result.exponent_stderr:.3f} "
              f"(stat) · energy-length cross-check {en_str} · systematic band "
              f"±{max(result.systematic_spread, 0.02):.2f} · {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m15(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m16":
        ns = _parse_m16(args[1:])
        from . import m16
        from . import render as render_mod
        waiting = [int(x) for x in ns.waiting_times.split(",") if x.strip()]
        deltas = [int(x) for x in ns.delta_times.split(",") if x.strip()]
        L, realizations, device = ns.L, ns.realizations, ns.device
        if ns.quick:
            L, realizations, device = 6, 8, "cpu"
            waiting, deltas = [4, 8, 16], [2, 4, 8, 16, 32]
        print(f"M16 3D ±J spin-glass aging · L={L} · T={ns.T:.2f} · "
              f"{realizations} disorder realizations · t_w={waiting} · Δt={deltas} "
              f"on {device} (single-spin clock; no cluster/PT shortcuts)")

        def _progress_m16(sweep, last):
            print(f"  · clock {sweep:>4}/{last} sweeps")

        result = m16.run_m16(
            L=L, T=ns.T, n_realizations=realizations, waiting_times=waiting,
            delta_times=deltas, seed=ns.seed, device=device, progress=_progress_m16,
        )
        report = m16.to_report(result)
        print(f"  → ratio-collapse residual = {result.collapse_ratio:.2f}× fixed-lag "
              f"residual · ΔC={result.fixed_lag_separation:+.3f} at Δt={result.fixed_lag} · "
              f"{'aging resolved' if result.aging_resolved else '[~] null'} · "
              f"{result.wall_seconds:.1f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m18":
        ns = _parse_m18(args[1:])
        from . import m18 as m18_mod
        from . import render as render_mod
        if ns.quick:
            kw = dict(L=256, batch=4, t_max=2000)
        else:
            kw = dict(L=ns.L or m18_mod.L_DEFAULT,
                      batch=ns.batch or m18_mod.BATCH_DEFAULT,
                      t_max=ns.t_max or m18_mod.T_MAX_DEFAULT)
        p_low = ns.p_low if ns.p_low is not None else m18_mod.P_LOW_DEFAULT
        p_high = ns.p_high if ns.p_high is not None else m18_mod.P_HIGH_DEFAULT
        print(f"M18 directed percolation in 2+1d · L={kw['L']} × {kw['batch']} lattices · "
              f"t_max={kw['t_max']:,} steps · bracketing p_c with p={p_low}/{p_high} · "
              f"grading delta against the (2+1)d DP value 0.4505, with mean-field 1.0 "
              f"as the class that must be excluded")

        def _phase(kind, payload):
            if kind in ("bracket-low", "bracket-high"):
                print(f"  · {kind}: p={payload['p']}")
            elif kind == "control":
                print(f"    control: {payload['name']}")

        result = m18_mod.run_m18(p_low=p_low, p_high=p_high, seed=ns.seed,
                                 device=ns.device, phase=_phase, **kw)
        report = m18_mod.to_report(result)
        print(f"  → bracket [{result.bracket[0]:.4f}, {result.bracket[1]:.4f}] · "
              f"p_c={result.p_c_estimate:.5f}±{result.p_c_uncertainty:.5f} · "
              f"{'contains 0.4505' if result.contains_dp else 'MISSES 0.4505'} · "
              f"{'excludes mean-field' if result.excludes_mean_field else 'MEAN-FIELD NOT EXCLUDED'} · "
              f"{'calibrated' if result.calibration_passed else '[~] null'} · "
              f"{result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m17":
        ns = _parse_m17(args[1:])
        from . import m17
        from . import render as render_mod
        if ns.quick:
            # A small pass: proves growth → controls → saturation → both geometries → report
            # end to end and writes HTML+JSON. The scaling window and the sample sizes are
            # short at this scale, so the exponents are coarse and the third moments noisy —
            # a miss still ships a [~] null, per the lab's convention.
            kw = dict(L=1024, batch=16, t_max=600, n_times=24,
                      ew_L=512, ew_t_max=300, rd_L=512, rd_t_max=300,
                      sat_L=(8, 16, 32), sat_batch=16,
                      dist_t=60, droplet_batch=400, flat_L=512, flat_batch=300, flat_sites=4)
        else:
            kw = dict(L=ns.L, batch=ns.batch, t_max=ns.t_max, n_times=ns.n_times,
                      dist_t=ns.dist_t, droplet_batch=ns.droplet_batch,
                      flat_batch=ns.flat_batch)
        print(f"M17 KPZ growth on a ring · L={kw['L']} · {kw['batch']} rings · "
              f"t_max={kw['t_max']:,} sweeps · p={ns.p_flip} · fitting β vs the exact KPZ 1/3, "
              f"with Edwards–Wilkinson (¼) and random deposition (½) as negative controls "
              f"on the same pipeline")

        result = m17.run_m17(p=ns.p_flip, seed=ns.seed, progress=lambda m: print(f"  · {m}"), **kw)
        report = m17.to_report(result)
        ew_b = (result.growth["ew"]["fit"] or {}).get("exponent")
        rd_b = (result.growth["rd"]["fit"] or {}).get("exponent")
        print(f"  → β = {result.beta:.4f} ± {result.beta_stderr:.4f} (stat) vs exact 1/3 · "
              f"α = {result.alpha:.4f} vs ½ · z = {result.z:.3f} vs 3/2 · "
              f"1/z = {result.inv_z:.3f} vs 2/3")
        print(f"  → controls: EW β={ew_b:.4f} (exact ¼) · RD β={rd_b:.4f} (exact ½), "
              f"w² within {100 * result.rd_exact['max_rel_dev']:.1f}% of the exact p(1−p)t · "
              f"{'separated' if result.controls_separate else 'CONTROL FAILED'}")
        for ic, a in result.assignments.items():
            print(f"  → {ic:>7}: skew {a['skewness']:+.4f} → nearer {a['nearer']} "
                  f"(expected {a['expected']}, {a['decisiveness']:.1f}×) "
                  f"{'✓' if a['correct'] else '✗'}")
        verdict = ("KPZ exponents + Tracy–Widom assignment reproduced"
                   if report["status"] == "pass" else "[~] null — see the report")
        print(f"  → {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "k02":
        ns = _parse_k02(args[1:])
        from . import k02 as k02_mod
        from . import render as render_mod
        k_c = 2.0 * ns.gamma
        print(f"K02 susceptibility shape · N-ladder {list(ns.ladder)} · "
              f"{len(ns.seeds)} initial conditions · γ={ns.gamma} · exact K_c = 2γ = {k_c:g}")
        print(f"  testing Run 01's χ(r) = a·r²(1−r)³ with its interior max at r* = 2/5,")
        print(f"  and calibrating r(K_c,N) against the published β/ν̄_c = "
              f"{k02_mod.CRITICAL_EXPONENT_PUBLISHED}"
              f"({int(k02_mod.CRITICAL_EXPONENT_PUBLISHED_ERR * 100)}) "
              f"[Hong et al. 2015 Eq. 4.3]")

        def progress(stage, done, total, n):
            if stage == "rung":
                print(f"  · sweep rung {done + 1}/{total}: N={n} oscillators")
            elif stage == "critical":
                print(f"  · calibration rung {done + 1}/{total}: N={n} at exact K_c")

        result = k02_mod.run_k02(
            ladder=ns.ladder, gamma=ns.gamma, seeds=ns.seeds, dt=ns.dt,
            t_burn=ns.t_burn, t_measure=ns.t_measure,
            critical_seeds=ns.critical_seeds, critical_t_burn=ns.critical_t_burn,
            critical_t_measure=ns.critical_t_measure, progress=progress,
        )
        report = k02_mod.to_report(result)
        for rung in result.rungs:
            print(f"  → N={rung.n:5d}  r*={rung.r_star:.4f} ±{rung.r_resolution:.4f} "
                  f"(grid)  K_peak={rung.k_peak:.4f}  free (p,q)="
                  f"({rung.fit_free['p']:.2f},{rung.fit_free['q']:.2f}) R²="
                  f"{rung.fit_free['r2']:.3f}  pinned (2,3) R²={rung.fit_run01['r2']:.3f}")
        for c in result.critical:
            print(f"  → N={c['n']:5d}  ⟨r⟩ at exact K_c = {c['r_critical']:.5f} "
                  f"± {c['r_sem']:.5f}  (equilibration drift "
                  f"{c['equilibration_drift'] * 100:.1f}%)")
        cf = result.critical_fit
        print(f"  → CALIBRATION: r(K_c,N) ~ N^−{cf['exponent']:.3f}±{cf['err']:.3f} "
              f"(R²={cf['r2']:.3f}) vs published "
              f"{k02_mod.CRITICAL_EXPONENT_PUBLISHED}"
              f"({int(k02_mod.CRITICAL_EXPONENT_PUBLISHED_ERR * 100)})")
        print(f"  → χ(r) argmax r* {result.rungs[0].r_star:.4f} → "
              f"{result.rungs[-1].r_star:.4f} vs Run 01's N-independent 2/5")
        verdict = ("interior peak resolved at every N; see the report for the shape verdict"
                   if report["status"] == "pass" else "[~] null — see the report")
        print(f"  → {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "k03":
        ns = _parse_k03(args[1:])
        from . import checks as checks_mod
        from . import k03 as k03_mod
        from . import render as render_mod
        k_c = 2.0 * ns.gamma
        print(f"K03 Daido vs Hong · N={ns.n} · γ={ns.gamma} · exact K_c = 2γ = "
              f"{k_c:g} · ε ∈ [{ns.eps_min:g}, {ns.eps_max:g}] × {ns.points} "
              f"per branch · {ns.rungs}-rung per-column field ladders")
        print("  Daido predicts (γ, γ') = (1/4, 1); Hong et al. (1/4, 1/4) — "
              "the check gates the measurement, the σ-distances adjudicate")
        last = [None]

        def progress(stage, done, total):
            if stage != last[0]:
                labels = {"pilot": "pilot pass — scaling the field ladders",
                          "graded": "graded pass — the measurement",
                          "burn-in": "  settling (burn-in)",
                          "measure": "  measuring both observables"}
                if stage in labels:
                    print(f"  · {labels[stage]}")
                last[0] = stage

        result = k03_mod.run_k03(
            n=ns.n, gamma=ns.gamma, n_points=ns.points, eps_min=ns.eps_min,
            eps_max=ns.eps_max, rungs=ns.rungs, dt=ns.dt, t_burn=ns.t_burn,
            t_measure=ns.t_measure, seed=ns.seed, progress=progress,
        )
        report = k03_mod.to_report(result)
        for branch, cols, fit, name in (
                ("below", result.below, result.fit_below, "γ'"),
                ("above", result.above, result.fit_above, "γ")):
            ok = sum(1 for c in cols if c["ok"])
            print(f"  → {branch}: {ok}/{len(cols)} columns passed the "
                  "linearity gate")
            for c in cols:
                if not c["ok"]:
                    print(f"     · refused ε={c['eps']:g} — {c['reason']} "
                          f"(spread {c['secant_spread'] if c['secant_spread'] is None else round(c['secant_spread'], 3)})")
            if fit.get("gamma") is not None:
                print(f"  → {name} = {fit['gamma']:.3f} ± {fit['err']:.3f} "
                      f"(R²={fit['r2']:.3f}, {fit['n_columns']} columns)")
            else:
                print(f"  → {name}: NOT MEASURED — {fit.get('reason')}")
        v = report["verdict"]
        if v.get("nearest"):
            print(f"  → nearest published pair: {v['nearest'].upper()} "
                  f"(σ_daido={v['sigma_daido']:.1f}, σ_hong={v['sigma_hong']:.1f})")
        ok, detail = checks_mod.check_k03(report)
        print(f"  check_k03: {ok} — {detail}")
        print(f"  · {result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "k01":
        ns = _parse_k01(args[1:])
        from . import k01 as k01_mod
        from . import render as render_mod
        k_c = 2.0 * ns.gamma
        print(f"K01 Kuramoto synchronization · N={ns.n} oscillators · γ={ns.gamma} · "
              f"{ns.points} couplings over [0, {4 * ns.gamma:g}] · exact K_c = 2γ = {k_c:g}")
        last = [None]

        def progress(stage, done, total):
            if stage != last[0]:
                labels = {"burn-in": "settling the crowd (burn-in)",
                          "measure": "measuring ⟨r⟩ and its fluctuation"}
                if stage in labels:
                    print(f"  · {labels[stage]}")
                last[0] = stage

        result = k01_mod.run_k01(
            n=ns.n, gamma=ns.gamma, n_points=ns.points, dt=ns.dt,
            t_burn=ns.t_burn, t_measure=ns.t_measure, seed=ns.seed,
            progress=progress,
        )
        report = k01_mod.to_report(result)
        print(f"  → χ=N·Var(r) peak at K_c={result.kc_chi_peak:.4f} vs exact {k_c:g} "
              f"(rel. err {result.rel_error*100:.1f}%) · steepest-rise cross-check "
              f"{result.kc_slope_crossing:.4f}")
        print(f"  → ordered branch √(1−K_c/K) matched to {result.branch_max_dev:.2e} over "
              f"{result.branch_points} couplings · ⟨r⟩(K=0)={result.r_incoherent:.4f} "
              f"vs 1/√N={result.r_incoherent_scale:.4f}")
        verdict = ("synchronization transition reproduced"
                   if report["status"] == "pass" else "[~] null — see the report")
        print(f"  → {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "k04":
        ns = _parse_k04(args[1:])
        from . import k04 as k04_mod
        from . import render as render_mod
        print(f"K04 Mirollo–Strogatz fireflies · N={ns.n} · b={ns.b:g} · "
              f"ε={ns.eps:g} · {ns.trials} initial conditions · event bound "
              f"{ns.max_events} · theorem: almost-sure unison")
        last = [None]

        def progress(stage, done, total):
            labels = {"trials": f"  · trials {done}/{total}",
                      "null": "  · ε=0 control (order without coupling would "
                              "be bookkeeping)",
                      "ladders": "  · N and ε ladders (reported, not graded)"}
            msg = labels.get(stage)
            if msg and (stage != last[0] or stage == "trials"):
                print(msg)
                last[0] = stage

        result = k04_mod.run_k04(
            n=ns.n, b=ns.b, eps=ns.eps, trials=ns.trials,
            max_events=ns.max_events, seed=ns.seed,
            ladders=not ns.no_ladders, progress=progress,
        )
        report = k04_mod.to_report(result)
        print(f"  → {result.synced}/{result.trials} reached unison · median "
              f"{result.events_median:.0f} / max {result.events_max} events "
              f"vs bound {result.max_events_bound}")
        nulls = result.null_clusters
        print(f"  → ε=0 control: {min(nulls) if nulls else 0} clusters of "
              f"{result.n} after {result.null_event_budget} events "
              f"({result.null_trials} trials)")
        verdict = ("almost-sure synchronization reproduced"
                   if report["status"] == "pass" else "[~] null — see the report")
        print(f"  → {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "c01":
        ns = _parse_c01(args[1:])
        from . import c01
        from . import render as render_mod
        print(f"C01 arithmetic calibration · OEIS A000045 first {ns.terms} terms · "
              "Lucas–Lehmer for 2^31−1")
        result = c01.run_c01(n_terms=ns.terms)
        report = c01.to_report(result)
        print(f"  → OEIS bytes {'match' if result.bfile_exact_match else 'DO NOT match'} · "
              f"Lucas–Lehmer residue={result.lucas_lehmer_residue} · "
              f"{'calibrated' if result.calibration_passed else '[~] null'} · "
              f"{result.wall_seconds:.2f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "c05":
        ns = _parse_c05(args[1:])
        from . import c05
        from . import render as render_mod
        n = ns.digits if ns.digits is not None else c05.CALIBRATION_HEX_DIGITS
        deep = ns.deep if ns.deep is not None else c05.DEEP_POSITION
        print(f"C05 BBP digit extraction · Machin reference {n} hex digits · "
              f"deep window at {deep:,}")
        result = c05.run_c05(n_digits=n, deep_position=deep)
        report = c05.to_report(result)
        n_match = sum(1 for w in result.windows if w["match"])
        print(f"  → {n_match}/{len(result.windows)} windows byte-identical · "
              f"overlaps {'agree' if result.all_overlaps_agree else 'DISAGREE'} · "
              f"deep {result.deep['digits']} in {result.deep['wall_seconds']}s · "
              f"{'calibrated' if result.calibration_passed else '[~] null'} · "
              f"{result.wall_seconds:.1f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "a01":
        ns = _parse_a01(args[1:])
        from . import a01
        from . import render as render_mod
        cache = Path(ns.cache_dir) if ns.cache_dir else a01.CACHE_DIR
        print(f"A01 archive photometry · {a01.TARGET_NAME} / TIC {a01.TIC_ID} · "
              f"up to {ns.sectors} official TESS SPOC sectors")

        def _progress_a01(done, total, product):
            source = "cache" if product["cached"] else "MAST"
            print(f"  ✓ sector {product['sector']:<3} {product['bytes']/1e6:.1f} MB from {source} "
                  f"({done}/{total})")

        def _phase_a01(phase, details):
            state = details.get("state")
            if state == "started":
                labels = {
                    "benchmark": "fetching the independent NASA benchmark",
                    "discovery": "finding official SPOC light curves",
                    "period-search": "blind-searching the first sector for a period",
                }
                print(f"  · {labels.get(phase, phase)}")
            elif phase == "discovery" and "queried_observations" in details:
                print(
                    f"    checked {details['queried_observations']}/"
                    f"{details['candidate_observations']} observations · "
                    f"{details['products_found']}/{details['products_requested']} products"
                )
            elif phase == "ephemeris":
                print(
                    f"    ephemeris {details['iteration']}/{details['iterations']} · "
                    f"{details['transit_count']} transits · "
                    f"P={details['period_days']:.8f} d"
                )

        result = a01.run_a01(
            max_sectors=ns.sectors,
            cache_dir=cache,
            progress=_progress_a01,
            deadline_seconds=ns.deadline,
            phase_progress=_phase_a01,
        )
        report = a01.to_report(result)
        print(f"  → P={result.period_days:.8f} d (Δ={result.period_error_days:.2g} d) · "
              f"depth={100*result.depth_fraction:.3f}% "
              f"(Δ={100*result.depth_error_fraction:.3f}%) · "
              f"{sum(result.kept_transits)} timed transits · "
              f"{'calibrated' if result.calibration_passed else '[~] null'} · "
              f"{result.wall_seconds:.1f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "deep":
        from . import deep as deep_mod
        if "--queue" in args:
            for i, job in enumerate(deep_mod.read_queue(), 1):
                print(f"  {i}. {job}")
            if not deep_mod.read_queue():
                print("  (empty — the deep lane will report the vacuum, not invent work)")
            return 0
        print(f"deep lane · unit of work is a NIGHT, not a slot · queue "
              f"{deep_mod.QUEUE}")
        verdict = deep_mod.run_next()
        print(f"  → {verdict['outcome']}: {verdict['detail']}")
        return 0 if verdict["outcome"] in ("ok", "idle") else 1

    if cmd == "frontier":
        import textwrap as _tw
        from . import frontier as frontier_mod
        b = frontier_mod.board()
        tot = b["totals"]
        print("── the frontier board ─────────────────────────────────────────")
        print(f"  {tot['milestones']} rungs across {tot['tracks']} tracks · "
              f"{tot['awaiting_review']} awaiting review · "
              f"{tot['unrunnable']} pending with NO RUNNER · "
              f"{tot['candidates']} harvested questions")
        if tot["tracks_without_a_goal"]:
            print(f"  ⚠ {tot['tracks_without_a_goal']} track(s) have no declared goal "
                  f"— a ladder without a summit is a to-do list")
        for t_ in b["tracks"]:
            print()
            print(f"  Track {t_['track']} · {t_['name']}")
            if t_["goal"]:
                for line in _tw.wrap(t_["goal"], 74):
                    print(f"      {line}")
            else:
                print("      *** NO GOAL DECLARED ***")
            state = " ".join(f"{k}={v}" for k, v in sorted(t_["counts"].items()))
            print(f"      {t_['total']} rungs · {state}")
            if t_["open"]:
                print(f"      on the bench: {t_['open']}")
            if t_["awaiting_review"]:
                print(f"      awaiting your review: {', '.join(t_['awaiting_review'])}")
            if t_["nulls"]:
                print(f"      standing nulls: {', '.join(t_['nulls'])}")
            if t_["no_runner"]:
                print(f"      BLOCKED — no runner, the scheduler walks past these "
                      f"forever: {', '.join(t_['no_runner'])}")
            if not t_["open"] and not t_["no_runner"] and \
                    set(t_["counts"]) <= {"verified"}:
                print("      ARRIVED? every rung verified and nothing open — "
                      "declare it finished or give it a new question")
        print()
        print("── questions this lab already admitted it cannot answer ───────")
        print("   harvested from the ladder's own prose — nothing here is invented")
        for c in b["candidates"]:
            print()
            print(f"  {c['milestone']} ({c['status']}) — {c['meaning']}")
            for line in _tw.wrap(c["sentence"], 72)[:4]:
                print(f"      {line}")
        print()
        print(f"  A candidate becomes a rung only with all of: "
              f"{', '.join(b['schema'])}.")
        print("  The kill condition is not optional — an idea that cannot say what")
        print("  would refute it is not a hypothesis.")
        return 0

    if cmd == "p01":
        from . import p01
        from . import render as render_mod
        print(f"P01 HP lattice folding · {len(p01.GRADED)} sequences whose ground "
              f"state is PROVEN by exhaustive enumeration, then searched blind · "
              f"{len(p01.PARITY_CONTROLS)} bipartite-parity controls · "
              f"replica exchange, {p01.N_REPLICAS} replicas")

        def _row(kind, r):
            if kind == "graded":
                print(f"    {r['sequence']:<14} proven E* = {r['enumerated']:<3} "
                      f"search found {r['energy']:<3} "
                      f"{'RECOVERED' if r['recovered'] else 'MISSED'}"
                      f"  · shuffle {r['shuffled_sequence']} E* = "
                      f"{r['shuffle_enumerated']:<3} "
                      f"{'ok' if r['shuffle_recovered'] else 'MISSED'}")
            elif kind == "parity":
                print(f"    {r['sequence']:<14} parity control · enumeration "
                      f"{r['enumerated']}, search {r['energy']} (geometry forbids any contact)")
            else:
                print(f"    {r['sequence']:<26} best found {r['energy']} — not proven optimal")

        result = p01.run_p01(progress=_row)
        report = p01.to_report(result)
        c = report["counts"]
        print(f"  → {c['recovered']}/{c['graded']} ground states recovered blind, "
              f"{c['parity_controls']} parity controls exact · "
              f"{'PASS' if result.passed else '[~] null'} · {result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "a02":
        from . import a02
        from . import render as render_mod
        print(f"A02 variable-star recovery · {len(a02.TARGETS)} known variables, "
              f"resolved from NAME · dominant frequency measured blind over "
              f"{a02.F_LO_CPD}-{a02.F_HI_CPD} c/d · AAVSO VSX read only at grading")

        def _row(r):
            if r.get("outcome") != "measured":
                print(f"    {r['ident']:<10} {r.get('outcome')}"
                      f"{' — ' + r['reason'] if r.get('reason') else ''}")
                return
            print(f"    {r['ident']:<10} TIC {r['tic']:>10} s{r['sector']:<3} "
                  f"P = {r['period_days']:.6f} d  vs {r['published_period_days']:.6f} "
                  f"(rel {r['rel_error']:.1e}, {r['resolution_beat_factor']:.0f}x inside "
                  f"resolution, control x{r['control_margin']:.0f})"
                  + (f"  [{r['harmonic']}]" if r.get("harmonic") else "")
                  + ("  [Blazhko-modulated]" if r.get("blazhko") else ""))

        result = a02.run_a02(on_row=_row)
        report = a02.to_report(result)
        c = report["counts"]
        print(f"  → {c['within_resolution']}/{c['measured']} recovered inside their own "
              f"resolution element, {c['control_clear']}/{c['measured']} clear of the "
              f"shuffled control · {'PASS' if result.passed else '[~] null'}")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "a07":
        from . import a07
        from . import render as render_mod
        print(f"A07 Galilean clockwork · Io/Europa/Ganymede/Callisto from JPL "
              f"Horizons · {a07.START} → {a07.STOP} @ {a07.STEP}, jovicentric "
              f"({a07.CENTER}) · Kepler III + the Laplace resonance")

        def _phase(kind, payload):
            if kind == "moon":
                print(f"    {payload['name']:<9} P = {payload['period_days']:.6f} d "
                      f"(a = {payload['a_km']:.0f} km, "
                      f"{payload['n_samples']} samples)")

        result = a07.run_a07(phase=_phase)
        report = a07.to_report(result)
        g = result.grades
        print(f"  → periods {'ok' if all(x['pass'] for x in g['periods'].values()) else 'OUT OF TOLERANCE'} · "
              f"Kepler spread {g['kepler']['max_fractional_spread']:.2e} · "
              f"GM rel err {g['kepler']['gm_rel_error']:.2e} · "
              f"Laplace {g['laplace']['residual_rel']:.1e} "
              f"(Callisto control {g['laplace']['callisto_substituted_rel']:.2f}) · "
              f"{'PASS' if result.passed else '[~] null'} · "
              f"{result.wall_seconds:.1f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "a03":
        ns = _parse_a03(args[1:])
        from . import a03
        from . import render as render_mod
        cache = Path(ns.cache_dir) if ns.cache_dir else a03.CACHE_DIR
        print(f"A03 gravitational-wave chirp mass · {ns.event} from GWOSC · "
              f"3.5PN TaylorF2 inspiral, {a03.SEG_SEC}s @ {a03.FS} Hz")

        def _progress(detector, nbytes, digest):
            print(f"  ✓ {detector} strain {nbytes/1e6:.1f} MB  sha256={digest[:16]}…")

        def _phase(kind, payload):
            if kind == "event":
                print(f"  · published Mc={payload['chirp_mass_source']:.4f} "
                      f"+{payload['chirp_mass_source_upper']:g}/"
                      f"-{payload['chirp_mass_source_lower']:g} Msun (source), "
                      f"z={payload['redshift']:g} → detector-frame "
                      f"{payload['chirp_mass_detector']:.5f}")
            elif kind == "detector":
                c, r = payload["control"], payload["real"]
                print(f"    {payload['detector']} control: SNR={c['peak_snr']:.1f} "
                      f"Mc={c['mc_detector']:.5f} (err {payload['control_error_msun']:.1e})")
                print(f"    {payload['detector']} sky:     SNR={r['peak_snr']:.1f} "
                      f"vs background {r['background_max']:.1f} → "
                      f"{'DETECTED' if payload['real_detected'] else 'no detection'}")

        result = a03.run_a03(catalog=ns.catalog, event=ns.event, version=ns.version,
                             cache_dir=cache, dmc=ns.dmc,
                             progress=_progress, phase=_phase)
        report = a03.to_report(result)
        print(f"  → control {'PASSED' if result.control_passed else 'FAILED'} · "
              f"event {'recovered' if result.recovered else 'NOT recovered'} · "
              f"{'calibrated' if result.calibration_passed else '[~] null'} · "
              f"{result.wall_seconds:.1f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "a04":
        ns = _parse_a04(args[1:])
        from . import a04
        from . import render as render_mod
        sector = ns.sector or a04.DEFAULT_SECTOR
        print(f"A04 blind transit search · TESS sector {sector} · {ns.targets} targets · "
              f"BLS {a04.P_LO}-{a04.P_HI} d, ranked by SDE · injections and a "
              f"false-alarm floor decide the threshold, not a choice")

        def _phase(kind, payload):
            if kind == "enumerate":
                print(f"  · enumerating sector {payload['sector']} SPOC targets")
            elif kind == "sample":
                print(f"    enumerated {payload['sector_size']} targets "
                      f"(page-capped, NOT the whole sector); searching "
                      f"{payload['sampled']}")
            elif kind == "injection":
                print("  · positive control: injecting synthetic transits")

        def _progress(tic, det, known):
            tag = f" <- {known['name']}" if known else ""
            print(f"    TIC {tic}: P={det.period_days:7.4f} d  depth={100*det.depth:.3f}%  "
                  f"SDE={det.sde:5.1f}{tag}")

        result = a04.run_a04(sector=sector, n_targets=ns.targets, seed=ns.seed,
                             cache_dir=Path(ns.cache_dir) if ns.cache_dir else None,
                             progress=_progress, phase=_phase)
        report = a04.to_report(result)
        print(f"  → control {'PASSED' if result.control_passed else 'FAILED'} · "
              f"floor {'clear' if result.floor_clear else 'REACHES THRESHOLD'} · "
              f"recoveries {sum(r.get('recovered', False) for r in result.recoveries)}"
              f"/{len(result.recoveries)} · "
              f"{'calibrated' if result.calibration_passed else '[~] null'} · "
              f"{result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "i01":
        ns = _parse_i01(args[1:])
        from . import i01
        from . import render as render_mod
        print("I01 CMOS particle-detector calibration · real capped-sensor dark frames only")
        capture_output = ns.capture_output
        if ns.camera is not None and capture_output is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            capture_output = LAB_HOME / "captures" / f"i01-camera-{ns.camera}-{stamp}.npy"
        last_stage = None

        def progress(event):
            nonlocal last_stage
            stage = event.get("stage")
            current, total = event.get("current"), event.get("total")
            if stage != last_stage:
                labels = {
                    "capture_start": "opening isolated camera worker",
                    "capture": "capturing real grayscale frames",
                    "capture_complete": "capture saved and hashed",
                    "preflight": "checking frame bounds and format",
                    "load": "loading bounded float32 stack",
                    "analysis_baseline": "measuring dark baseline and temporal noise",
                    "analysis_frame": "classifying transient components",
                    "complete": "calibration complete",
                }
                print(f"  · {labels.get(stage, stage)}")
                last_stage = stage
            if current and total and (current == total or current == 1 or current % 8 == 0):
                print(f"    {current}/{total}")

        result = i01.run_i01(
            frames_path=ns.frames,
            capture_camera=ns.camera,
            capture_output=capture_output,
            capture_frames=ns.capture_frames,
            capture_timeout_seconds=ns.capture_timeout,
            capture_width=ns.capture_width,
            capture_height=ns.capture_height,
            progress=progress,
        )
        if not result.analysis:
            # Nothing was measured (no frames, no camera, capture/input error).
            # A disclosed absence is not a science row: no dated report, no
            # receipt, no publish — and a named nonzero exit (3) so unattended
            # callers (campaign.sh) log "experiment failed" instead of
            # committing a null row every pass. The committed 2026-07-14 null
            # receipt predates this gate and stays — honest archive. A MEASURED
            # null (real frames analyzed, calibration failed) still publishes
            # below: that is data, not absence.
            label = result.error_code or "hardware-null"
            print(f"  → {label}: {result.reason}")
            if result.capture_metadata:
                print(f"  ✓ captured stack: {result.capture_metadata.get('output_path')}")
            return 3
        report = i01.to_report(result)
        print(f"  → {result.analysis['shape'][0]} frames · "
              f"{result.analysis['hot_pixel_count']} hot pixels · "
              f"{result.analysis['track_candidate_count']} track-like components · "
              f"{'calibrated' if result.calibration_passed else '[~] null'}")
        if result.capture_metadata:
            print(f"  ✓ captured stack: {result.capture_metadata.get('output_path')}")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "next":
        # A turn runs under the run lock; a dry run claims nothing (it runs
        # nothing, and must stay usable as a diagnostic while a turn is live).
        if "--dry-run" in args:
            return _run_next(args, dry=True)
        try:
            with next_run_lock() as lock_path:
                return _run_next(args, dry=False, lock_path=lock_path)
        except LockBusy as busy:
            # A skipped slot is a healthy outcome, not a failure: exit 0 so Task
            # Scheduler's LastTaskResult stays clean and nobody chases a ghost.
            print(
                f"lab next · another turn is running (pid {busy.pid} since "
                f"{busy.started}) — skipping this slot"
            )
            return 0

    if cmd == "run" or (cmd not in ("help", "open") and cmd.startswith("--")):
        rest = args if cmd != "run" else args[1:]
        ns = _parse_run(rest)
        from . import ising
        from . import render as render_mod
        cfg = ising.RunConfig(
            L=ns.L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_burnin=ns.burnin, n_sweeps=ns.sweeps, device=ns.device, seed=ns.seed,
            initial_state=ns.initial_state,
        )
        print(
            f"running Ising on {cfg.device} · L={cfg.L} · {cfg.n_temps} temps · "
            f"{cfg.n_sweeps:,} sweeps · {cfg.initial_state} start ..."
        )
        result = ising.run(cfg)
        print(f"  ✓ {cfg.n_sweeps:,} sweeps in {result.wall_seconds:.1f}s")
        path = render_mod.render(result)
        print(f"  ✓ report: {path}")
        # A run also waters the seed: refresh the sanitized snapshot (and push
        # it if POT_GIST_ID is set). Best-effort — never let it break a run.
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(gist_id=os.environ.get("POT_GIST_ID"), quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        if cmd != "run":
            webbrowser.open(f"file://{path}")
        return 0

    print(f"unknown command: {cmd!r}\n", file=sys.stderr)
    print(HELP, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
