"""``lab selftest`` — the test suite takes a turn, and the feed says whether it did.

THE DEFECT this closes (2026-09-04). The estate's whole model of windowsill
health is ``pot.json``: the morning pulse reads ``WINDOWSILL_POT`` and prints
``latest_report``, and nothing else. ``pot.json`` carried no test status at all,
and the nightly never ran pytest — ``nightly_ps1`` ran ``lab next``, then
``lab verify``, then committed, and ``campaign.sh`` was the same shape. The only
automated pytest anywhere was CI on push.

So when windows-cuda went quiet on 2026-08-20 (the hunt-dispatch livelock, fixed
2026-09-04), the sibling agent read the only signal it had — a two-week hole in
committed receipts — and reported "we haven't run a test since August 20th".
That was false: GitHub Actions ran the full CPU suite on main 2-25 times a day
straight through. But the agent was not wrong to say it, because
*"did a box publish a receipt"* had been standing in for *"did the tests run"*,
and those are different questions. This module makes the second one answerable.

It also makes it answerable HONESTLY, which is the harder half. CI is CPU-only:
a CI run reports 24 skipped, a run on a real CUDA box reports 16. The difference
is eight GPU-gated tests (``tests/test_ising.py``, ``tests/test_ising_hex.py``,
all guarded ``skipif(not CUDA_AVAILABLE, reason="GPU not available")``) that have
no scheduled runner anywhere and execute only when a human types ``pytest`` on a
box with a card. A green suite that skipped those must therefore not read the
same as one that ran them — hence ``gpu_tests_ran``, measured from the junit XML
of the run itself rather than inferred from a torch flag.

And absent is not passing. No block this module builds can be mistaken for
green: no result on the books publishes ``status: "unknown"``, a result older than
``STALE_AFTER_H`` publishes ``status: "stale"`` (the run's own verdict demoted to
``recorded_status``, where it cannot be read as current), and a malformed record
degrades to ``unknown`` rather than raising. That last one matters more than it
looks: ``publish.collect`` wraps its optional blocks in bare excepts that
silently DROP the key on any exception, so a parse error here would delete the
very field whose absence started this.

THE FACT IS ABOUT TWO BOXES, SO THE FEED CARRIES TWO ROWS. The first cut of this
module published one ``tests`` object filled from THIS box's
``~/.lab/selftest-latest.json``, on a feed both machines write. Win's red suite
was overwritten by loam's green a few hours later, and loam's by win's: a shared
mutable slot for a per-machine fact is last-writer-wins, which is the
green-while-dead class this whole change exists to retire. ``turns.last_by_machine``
had already solved it in the strong way — a per-machine map derived by walking
the COMMITTED receipt ledger — so ``tests_by_machine`` is that solution applied
again, not a second mechanism. The producer files a receipt
(``write_receipt``); the feed is a pure function of the committed set; and
because no box ever writes a filename another box writes, one machine erasing
another's verdict is impossible rather than merely detectable. A declared box
that has never reported gets a row saying so, because a MISSING key is what
reads as "fine".

Stdlib only, and every decision that can be a pure function is one, so the tests
exercise the real rules rather than grepping a template for hopeful substrings.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

#: The box-local SCRATCH record, written by ``run``. It is a handoff between the
#: pytest process and the receipt write, plus the cadence bookkeeping ``is_due``
#: reads (``last_run_date``) — and it is NOT a source of truth for the feed.
#:
#: It used to be. That was the fault the first pass of this module shipped with,
#: and it is worth naming because it is the same fault the module exists to
#: retire. ``pot.json`` carried ONE ``tests`` slot for a fact about TWO boxes,
#: and ``publish.collect`` filled it unconditionally from THIS box's copy of
#: this file. Both machines publish the same feed, hours apart, so a red suite
#: on win was overwritten by loam's green on loam's next pass and vice versa:
#: last-writer-wins on shared mutable state, which is green-while-dead wearing
#: a test result's clothes. The verdict now leaves the box as a committed
#: receipt (``write_receipt``) and the feed is derived from the receipt ledger,
#: so one box cannot reach the other box's verdict at all.
RESULT_NAME = "selftest-latest.json"

#: The committed receipt's ``schema`` string. Its own family, deliberately: a
#: selftest receipt is an operational fact and must never be mistaken for a
#: measurement receipt (``receipt.RECEIPT_SCHEMA``) by a reader walking the
#: ledger.
RECEIPT_SCHEMA_ID = "windowsill.selftest-receipt.v1"

#: The receipt filename's kind prefix, and the glob every reader uses.
#:
#: NOT ``run-``. Every science consumer in this repo globs
#: ``run-<date>-*.json`` over ``reports/receipts/`` — the turn counter, the
#: archive ledger, the scoreboard, the planner's repeat law, the physics feed,
#: CI's repeat alarm. A selftest receipt filed under ``run-`` would be counted
#: as a scientific turn by every one of them, which would inflate the cadence
#: the page publishes with passes that measured nothing. A distinct prefix keeps
#: the two ledgers in one directory without either reading the other's rows.
RECEIPT_PREFIX = "selftest"
RECEIPT_GLOB = f"{RECEIPT_PREFIX}-*.json"

#: Filename discriminator for a box whose provenance does not name a machine.
#: Deliberately not a plausible machine name: the filename is a uniqueness
#: device, and the machine a receipt belongs to is DERIVED from its provenance
#: by ``archive.machine_of`` on every read, never parsed back out of the name.
UNNAMED_MACHINE = "unnamed-box"

#: Bump when the on-disk record's shape changes. A record written by a newer
#: producer than the reader is treated as unreadable, not guessed at.
RESULT_SCHEMA = 1

#: How old a recorded result may be before the block publishes it as stale.
#: The suite runs once per UTC day per box (see ``is_due``), so 36h is one
#: missed run plus half a day of slack: long enough that a late slot is not a
#: false alarm, short enough that a box which stopped testing says so the next
#: morning rather than the next week.
STALE_AFTER_H = 36

#: How far into the future a recorded stamp may sit before it stops counting as
#: dateable at all. A result stamped ahead of now is not fresh — it is a result
#: written by a clock we cannot trust, and without this the staleness test
#: (``age > STALE_AFTER_H``) can NEVER fire for it: one green run written under a
#: skewed clock would publish as a current pass forever, which is precisely the
#: stale-reads-as-green shape ``STALE_AFTER_H`` exists to stop. An hour of slack
#: absorbs ordinary NTP drift and the seconds between writing and reading.
FUTURE_SLACK_H = 1

#: The UTC hours in which a pass may take the test turn.
#:
#: WHICH PASS, AND WHY THIS ONE: both boxes run four passes a day, six hours
#: apart — win at 00/06/12/18 local (Task Scheduler), loam at 03/09/15/21 local
#: (``LAB_CAMPAIGN_HOURS``). A window exactly six hours wide therefore catches
#: exactly ONE pass per box per day whatever the box's UTC offset is, which is
#: the whole trick: neither machine needs new config, neither needs to know
#: which slot is "its" slot, and the rule is the same line of code on both.
#: [00,06) UTC is the pick because the seed the nightly already derives is a UTC
#: hour, so this reads in the same clock as everything around it.
#:
#: The window alone is not enough — loam's campaign in plain interval mode wakes
#: every 30 minutes, which would put twelve pytest runs inside one window — so
#: ``is_due`` also refuses a second run on a UTC date that already has one. The
#: window picks the pass; the date stamp enforces once. On a DST-transition day a
#: box can see two passes in the window or none; the date stamp absorbs the first
#: case and the next day absorbs the second.
DUE_UTC_HOURS = range(0, 6)

#: pytest writes the skipif reason into the junit ``message`` attribute verbatim.
#: This is the string the eight GPU-gated tests share; see the module docstring.
GPU_SKIP_REASON = "GPU not available"

#: The junit ``classname`` of every module holding GPU-gated tests.
#:
#: "No GPU test was skipped" is NOT on its own evidence that they ran — a run
#: that died before collecting them skips nothing either. That is not
#: hypothetical: the 2026-09-04 bring-up run was killed by a MemoryError at test
#: 424 of 2235, never reached ``test_ising``, and the first cut of this module
#: dutifully recorded ``gpu_tests_ran: true`` on a suite that had not run a
#: single GPU test. So the flag also requires POSITIVE evidence that the run got
#: to these modules at all. If one is renamed and this list goes stale, the flag
#: reads False — "we cannot confirm" — which is the safe direction to fail.
GPU_TEST_MODULES: tuple[str, ...] = ("tests.test_ising", "tests.test_ising_hex")

#: A ceiling, not a schedule. The suite takes ~13 minutes; an hour means a
#: genuinely wedged pytest is recorded as an error instead of holding the nightly
#: open behind it.
TIMEOUT_S = 3600


# ── the published block ─────────────────────────────────────────────────────
#: What a declared machine that has never filed a selftest receipt publishes.
#: A machine with no row at all is the shape being closed here: a MISSING KEY
#: reads as "fine" to a careless consumer, so every declared box gets a row and
#: the row says it does not know.
#:
#: Worded "no readable receipt" rather than "never ran" on purpose. A receipt
#: whose JSON will not parse cannot be attributed to a box at all — the
#: attribution is ``machine_of`` over the receipt's own provenance, and there is
#: no provenance to read — so a machine whose only receipt is corrupt lands here
#: too. Both cases are honestly "nothing this publisher can read"; claiming the
#: box never filed anything would be a guess in the flattering direction.
NEVER_REPORTED = ("no readable test receipt from this machine is on the ledger — "
                  "an unmeasured suite is not a passing one")


def unknown_block(detail: str, machine: str | None = None) -> dict:
    """The honest nothing — every field present, nothing readable as green.

    Kept as a constructor rather than a constant so callers cannot mutate a
    shared dict, and so ``publish`` can build one before it has even imported
    this module (its own fallback, for the case where the import itself fails).

    ``machine`` is the box this row is ABOUT, which in the per-machine map is
    known even when nothing else is — the map's own key. Naming it here is what
    keeps "windows-cuda has never reported" from degrading into an anonymous
    blank the reader has to attribute for itself.
    """
    return {
        "status": "unknown",
        "detail": detail,
        "at": None,
        "machine": machine,
        "passed": None,
        "failed": None,
        "skipped": None,
        "gpu_tests_ran": False,
    }


def tests_block(path: Path | None = None, now: datetime | None = None) -> dict:
    """One RECORD FILE → a block. NEVER raises, NEVER reads as green.

    Reads the box-local scratch record. This is NOT what the feed publishes any
    more — ``tests_by_machine`` walks the committed receipt ledger for that — so
    it has one job left: it is the round-trip reader for what ``run`` just
    wrote, which is how the producer's output is checked against the reader's
    rules without a ledger in the way.
    """
    if path is None:
        from .labhome import LAB_HOME
        path = LAB_HOME / RESULT_NAME
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return unknown_block(
            "no test run has ever been recorded on this box — "
            "an unmeasured suite is not a passing one")
    except (OSError, ValueError):
        return unknown_block(
            "the recorded test result could not be read — treat as unmeasured")
    return block_from(record, now=now)


def tests_by_machine(receipts_dir: Path, machines, now: datetime | None = None) -> dict:
    """The feed's ``tests`` object: every DECLARED machine → its newest verdict.

    THE SHAPE, AND WHY IT IS THIS ONE. ``pot.json`` used to carry a single
    ``tests`` object for a fact about two boxes, filled from whichever machine
    published last. Win's red suite was erased by loam's green within hours and
    loam's by win's, because a shared mutable slot has no memory of who wrote it
    — the same last-writer-wins failure the whole module exists to retire, one
    layer up.

    ``turns.last_by_machine`` had already solved exactly this, and solved it in
    the strong way, so this is that solution applied again rather than a second
    mechanism: a PER-MACHINE map, derived by walking the COMMITTED receipt
    ledger and asking ``archive.machine_of`` which box wrote each row. Each box
    only ever APPENDS a receipt under a name no other box writes; the map is a
    pure function of the committed set. One box overwriting another's verdict is
    not detected here — it is structurally impossible, because no box ever
    writes a row the other box also writes.

    Every honesty property of the single-slot version survives PER MACHINE:

      * a declared machine with no receipt at all publishes ``unknown``
        (``NEVER_REPORTED``) rather than being ABSENT — a missing key reads as
        "fine" to a careless consumer, and that is the failure being closed;
      * an unreadable receipt, an unreadable record inside it, or one with no
        usable timestamp leaves that machine ``unknown``, never green;
      * a run older than ``STALE_AFTER_H`` publishes ``stale`` with its own
        grade demoted to ``recorded_status`` (``block_from``);
      * ``gpu_tests_ran`` stays measured from that run's own junit.

    ``machine`` on each row is the LEDGER's answer (``machine_of`` on the
    receipt's provenance), never the record's self-reported field: a box that
    mislabels itself must not be able to file its verdict under its sibling's
    name.
    """
    from .archive import machine_of   # the ONE derivation site, imported not copied

    blocks: dict[str, dict] = {
        m: unknown_block(NEVER_REPORTED, m) for m in (machines or ()) if isinstance(m, str)
    }
    newest: dict[str, str] = {}
    #: machine → why its rows were all refused, for a box that HAS receipts but
    #: none this function may believe. Without it those boxes read exactly like a
    #: box that never ran, which hides a live clock fault behind a quiet word.
    refused: dict[str, str] = {}
    #: derived-machine-name → how many receipts on the ledger carry it that no
    #: DECLARED machine matches. This is the quiet way this whole block goes
    #: inert. Attribution is ``machine_of`` over the receipt's provenance, and
    #: the accelerator half of that name comes from the torch build suffix — so
    #: a box that is reinstalled with a plain PyPI wheel (``2.9.1``, no
    #: ``+cu``/``+rocm``) starts filing perfectly good receipts under ``windows``
    #: instead of ``windows-cuda``. Every one of them is then skipped here, the
    #: declared box publishes ``NEVER_REPORTED`` forever, and NOTHING anywhere
    #: says the suite ran: a box testing itself nightly reads identically to one
    #: that has never run pytest. That is the safe DIRECTION to fail, but a
    #: watchdog that is permanently blind and silent about it is the class this
    #: module exists to retire, so the blindness is named in the row itself.
    unattributed: dict[str, int] = {}

    directory = Path(receipts_dir)
    if not directory.exists():
        return blocks
    for path in sorted(directory.glob(RECEIPT_GLOB)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Unattributable: the machine comes from the receipt's provenance,
            # and a file that will not parse has none to read. Its box falls
            # through to NEVER_REPORTED, whose wording covers exactly this.
            # The filename carries a machine too, but it is a uniqueness device
            # and reading it here would be a SECOND derivation of a machine name.
            continue
        if not isinstance(data, dict):
            continue
        machine = machine_of(data)
        # Only DECLARED machines get a row — the same rule ``turn_cadence``
        # applies, and for the same reason: inventing a row for an undeclared
        # box turns an observation into an expectation.
        if machine not in blocks:
            unattributed[machine or UNNAMED_MACHINE] = (
                unattributed.get(machine or UNNAMED_MACHINE, 0) + 1)
            continue
        block = block_from(data.get("selftest"), now=now)
        block["machine"] = machine
        stamp = block.get("at")
        if not isinstance(stamp, str) or not stamp:
            refused.setdefault(machine, block["detail"])
            continue
        if not stamp_is_datable(stamp, now):
            # Louder than an unreadable row, and it OVERWRITES one: a stamp from
            # the future would win every "is this the newest?" comparison from
            # now on, so a box carrying one cannot be described by whichever of
            # its receipts happens to sort next.
            refused[machine] = (
                f"the newest receipt on {machine} is stamped in the FUTURE — the "
                f"clock that wrote it cannot date a result, so no run on this box "
                f"can be shown as current")
            continue
        prior = newest.get(machine)
        if prior is None or stamp > prior:
            newest[machine] = stamp
            blocks[machine] = block
    for machine, detail in refused.items():
        if machine not in newest:
            blocks[machine] = unknown_block(detail, machine)
    if unattributed:
        # Say it where the silence would otherwise be. A box with no row and
        # receipts sitting on the ledger under a name nothing declares is not the
        # same fact as a box that never ran, and publishing the two identically
        # is how this block would quietly stop measuring anything.
        note = (" (the ledger also carries "
                + ", ".join(f"{n} receipt(s) filed as {name!r}"
                            for name, n in sorted(unattributed.items()))
                + " — an undeclared box name, so those verdicts reach no row)")
        for machine, row in blocks.items():
            if machine not in newest and machine not in refused:
                row["detail"] = NEVER_REPORTED + note
    return blocks


def block_from(record: object, now: datetime | None = None) -> dict:
    """``record`` (whatever it turns out to be) → the published block.

    Split out from ``tests_block`` so the degrade paths can be tested without a
    filesystem, and defensive to the point of paranoia about the record's shape:
    this runs inside the publisher, and the publisher drops the key on a raise.
    """
    if not isinstance(record, dict):
        return unknown_block("the recorded test result is not an object — "
                             "treat as unmeasured")
    if record.get("schema") != RESULT_SCHEMA:
        return unknown_block(
            f"the recorded test result is schema {record.get('schema')!r}, "
            f"not {RESULT_SCHEMA} — treat as unmeasured")
    status = record.get("status")
    if status not in ("pass", "fail", "error"):
        return unknown_block(f"the recorded test result has no readable status "
                             f"({status!r}) — treat as unmeasured")
    at = record.get("at")
    if not isinstance(at, str) or not at:
        return unknown_block("the recorded test result carries no timestamp — "
                             "an undateable result cannot be called current")

    block = {
        "status": status,
        "detail": _detail_for(record),
        "at": at,
        "machine": record.get("machine") if isinstance(record.get("machine"), str) else None,
        "passed": _count(record.get("passed")),
        "failed": _count(record.get("failed")),
        "skipped": _count(record.get("skipped")),
        "gpu_tests_ran": record.get("gpu_tests_ran") is True,
    }
    age = _age_hours(at, now)
    if age is None:
        # An unparseable stamp is not a fresh one. Say so where it cannot be
        # mistaken for the verdict.
        block["recorded_status"] = block["status"]
        block["status"] = "stale"
        block["detail"] = ("the recorded timestamp could not be parsed, so this "
                           "result cannot be shown as current")
    elif age < -FUTURE_SLACK_H:
        # Ahead of now by more than clock noise. Never age past STALE_AFTER_H,
        # so left alone this is a pass that can never go stale.
        block["recorded_status"] = block["status"]
        block["status"] = "stale"
        block["detail"] = (
            f"the recorded timestamp is {-age:.0f}h in the FUTURE — the clock that "
            f"wrote it cannot date a result, so this cannot be shown as current")
    elif age > STALE_AFTER_H:
        block["recorded_status"] = block["status"]
        block["status"] = "stale"
        block["detail"] = (
            f"last recorded test run was {age:.0f}h ago (> {STALE_AFTER_H}h) — "
            f"it graded '{block['recorded_status']}' then, and says nothing about now")
    return block


def _detail_for(record: dict) -> str:
    """One human line for a fresh result — what ran, and what did not."""
    note = record.get("detail")
    if isinstance(note, str) and note:
        return note
    gpu = ("the GPU-gated tests ran" if record.get("gpu_tests_ran") is True
           else "the GPU-gated tests did NOT run on this box")
    return (f"{_count(record.get('passed'))} passed, "
            f"{_count(record.get('failed'))} failed, "
            f"{_count(record.get('skipped'))} skipped; {gpu}")


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def stamp_is_datable(stamp: str, now: datetime | None = None) -> bool:
    """May a "which of these is newest?" comparison believe ``stamp``?

    False for anything unparseable, and false for anything more than
    ``FUTURE_SLACK_H`` ahead of ``now``.

    THE DEFECT THIS IS: a newest-wins comparison over wall-clock strings has no
    upper bound. ``if prior is None or stamp > prior`` accepts a stamp from 2099
    exactly as readily as one from a minute ago, and having accepted it, every
    real record filed afterwards loses the comparison — forever. One box that
    comes back from sleep with a bad RTC, one VM restored from a snapshot, one
    timezone bug, and that machine's row is pinned to a record that will never
    be superseded. The same defect in the staleness test is why ``block_from``
    demotes a future stamp: age is ``now - then``, so a stamp ahead of now has a
    NEGATIVE age and can never trip ``age > STALE_AFTER_H``.

    ``FUTURE_SLACK_H`` (1h) is the bound, and it is a bound rather than zero
    because the honest cases sit within seconds to minutes of now: the gap
    between writing a record and reading it back, and ordinary NTP drift on a
    box that has been asleep. An hour is far past both and far short of any
    skew that matters — a machine an hour ahead is already misconfigured.
    """
    age = _age_hours(stamp, now)
    return age is not None and age >= -FUTURE_SLACK_H


def _age_hours(stamp: str, now: datetime | None = None) -> float | None:
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current - then).total_seconds() / 3600.0


# ── when a pass takes the turn ──────────────────────────────────────────────
def is_due(now: datetime, last_utc_date: str | None) -> tuple[bool, str]:
    """``(due, why)`` for this pass. Pure — the whole scheduling rule, testable.

    See ``DUE_UTC_HOURS`` for why the window is six hours wide and starts at
    midnight UTC. ``last_utc_date`` is the UTC date of the last recorded run
    (``None`` when there has never been one).
    """
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if last_utc_date == today:
        return False, f"the suite already ran today ({today} UTC)"
    if now.hour not in DUE_UTC_HOURS:
        return False, (f"{now.hour:02d}:00 UTC is outside the test window "
                       f"({DUE_UTC_HOURS.start:02d}-{DUE_UTC_HOURS.stop:02d} UTC)")
    return True, f"inside the {DUE_UTC_HOURS.start:02d}-{DUE_UTC_HOURS.stop:02d} UTC window and not yet run today"


def last_run_date(path: Path) -> str | None:
    """The UTC date of the recorded run, or ``None`` — never raises."""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    date = record.get("utc_date") if isinstance(record, dict) else None
    return date if isinstance(date, str) and date else None


# ── the junit reader ────────────────────────────────────────────────────────
def parse_junit(text: str) -> dict:
    """pytest's junit XML → ``{passed, failed, skipped, errors, total, gpu_skipped}``.

    Counted from the per-``testcase`` elements rather than the ``testsuite``
    attributes, because the one number this whole exercise exists for —
    "did the GPU-gated tests actually execute?" — is only visible per test: a
    GPU test that RAN and a GPU test that was SKIPPED are indistinguishable in
    the suite totals. ``gpu_skipped`` counts the cases skipped with the reason
    the eight gated tests share (``GPU_SKIP_REASON``), which is a measurement of
    the run rather than a guess from ``torch.cuda.is_available()`` on some other
    process.

    Raises ``ValueError`` on XML this does not understand; ``run`` turns that
    into a recorded ``error``, which is the honest outcome for a run whose
    result could not be read.

    Stdlib ``ElementTree`` on purpose: this repo takes no dependency it does not
    need, the input is a file this process just asked pytest to write into a
    temp dir it owns, and CPython's parser does not resolve external entities.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"unparseable junit xml: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise ValueError("junit xml carries no <testsuite>")

    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "gpu_skipped": 0}
    gpu_modules: set[str] = set()
    for suite in suites:
        for case in suite.iter("testcase"):
            if case.get("classname") in GPU_TEST_MODULES:
                gpu_modules.add(case.get("classname"))
            skipped = case.find("skipped")
            if skipped is not None:
                counts["skipped"] += 1
                message = (skipped.get("message") or "") + (skipped.text or "")
                if GPU_SKIP_REASON in message:
                    counts["gpu_skipped"] += 1
            elif case.find("error") is not None:
                counts["errors"] += 1
            elif case.find("failure") is not None:
                counts["failed"] += 1
            else:
                counts["passed"] += 1
    counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"] + counts["errors"]
    counts["gpu_modules_seen"] = sorted(gpu_modules)
    return counts


def gpu_tests_ran(counts: dict) -> bool:
    """Did the GPU-gated tests actually EXECUTE on this run? Two-sided, measured.

    Both halves are required, and each closes a way of lying:

      * no test was skipped for want of a card — otherwise a CPU-only box (CI
        reports 24 skipped where a CUDA box reports 16) would publish as though
        it had exercised them;
      * the run reached every module that holds gated tests — otherwise a run
        that died early, or one narrowed to a subset, skips nothing and would
        publish the same as a complete one.
    """
    return (counts.get("gpu_skipped") == 0
            and set(counts.get("gpu_modules_seen") or ()) == set(GPU_TEST_MODULES))


def provenance() -> dict:
    """This run's provenance, in the shape ``archive.machine_of`` reads.

    The same keys ``render._stamp_report_json`` writes into a science report,
    and for the same reason: a receipt has to be able to say which box wrote it
    WITHOUT anyone parsing a filename or trusting a self-reported label. Only
    ``platform`` and ``dependencies.torch`` are load-bearing — those are the two
    fields ``machine_of`` reads — and the rest is there because a receipt that
    outlives the box should say what produced it.

    Built here rather than imported from ``render`` because ``render`` pulls
    matplotlib, and this runs in the nightly's tail and (through the receipt it
    writes) feeds a publisher kept deliberately import-light.
    """
    import importlib.metadata
    import platform as _platform

    deps: dict[str, str] = {}
    for pkg in ("torch", "numpy"):
        try:
            deps[pkg] = importlib.metadata.version(pkg)
        except Exception:  # noqa: BLE001 — a torch-free box still names its OS half
            pass
    return {
        "python": _platform.python_version(),
        "platform": f"{_platform.system().lower()}-{_platform.machine().lower()}",
        "dependencies": deps,
    }


def machine_now() -> str | None:
    """This box in the archive's vocabulary — ``windows-cuda`` / ``linux-rocm``.

    ONE derivation of a machine name in this repo, and this is not a second one:
    it hands ``archive.machine_of`` the provenance above and publishes whatever
    comes back. Used for the receipt's FILENAME (a uniqueness device) and for
    the scratch record's note about itself; the feed re-derives the machine from
    the receipt's provenance on every read rather than believing either.
    """
    from .archive import machine_of
    return machine_of({"provenance": provenance()})


# ── the committed receipt ───────────────────────────────────────────────────
def receipt_name(date: str, turn: str, machine: str | None) -> str:
    """``selftest-<date>-<hhmm>-<machine>.json`` — the ledger row's name.

    The same naming discipline every other receipt in this directory follows
    (``publish._receipt_filename``): a kind prefix, the writing box's LOCAL
    date, the ``HHMM`` turn stamp that makes two runs in one day two rows
    instead of an overwrite, and a discriminator. The discriminator is the
    machine, which is what makes cross-box erasure impossible by construction
    rather than by convention — win and loam cannot produce the same filename,
    so neither can land on top of the other's evidence.
    """
    return f"{RECEIPT_PREFIX}-{date}-{turn}-{machine or UNNAMED_MACHINE}.json"


def receipt_document(record: dict, prov: dict) -> dict:
    """The receipt's contents: provenance the ledger reads, plus the record.

    The verdict rides in its own ``selftest`` key rather than at the top level
    so the record's ``schema`` (an int, this module's record version) cannot
    collide with the receipt's (a string, this file's family) — two versions of
    two different things, neither able to be read as the other.
    """
    return {
        "schema": RECEIPT_SCHEMA_ID,
        "generated_at": record.get("at"),
        "provenance": prov,
        "selftest": record,
    }


def write_receipt(receipts_dir: Path, record: dict, date: str | None = None,
                  turn: str | None = None, prov: dict | None = None) -> Path:
    """Put this run's verdict on the committed ledger. Returns the path.

    This is the step that takes the fact off the box. Before it existed the
    verdict lived only in ``~/.lab/selftest-latest.json`` and the feed published
    whichever box happened to publish last, which meant a red suite on one
    machine was erased by the other machine's green a few hours later. A receipt
    is append-only and machine-named: nothing here can reach the other box's row.

    Serialized like the pot and the scratch record — ``indent=2``, INSERTION
    order, ``ensure_ascii``, trailing newline — and NOT like the public
    measurement receipts, which are sorted. Both layouts are pinned in
    ``tests/test_serialization_pin.py``; this is a new artifact family and it
    gets the same serializer ``write_result`` already uses, so there is one
    layout for the record whether it is on the box or on the books.
    """
    from .atomic import atomic_write_text
    from .publish import today_local, turn_stamp_now

    prov = prov if prov is not None else provenance()
    from .archive import machine_of
    path = Path(receipts_dir) / receipt_name(
        date or today_local(), turn or turn_stamp_now(),
        machine_of({"provenance": prov}))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(receipt_document(record, prov), indent=2) + "\n",
        encoding="utf-8")
    return path


# ── the producer ────────────────────────────────────────────────────────────
def run(repo_root: Path, result_path: Path, python: str | None = None,
        now: datetime | None = None, runner=None) -> dict:
    """Run the suite once and write the box-local record. Returns the record.

    ``runner`` is the seam the tests drive: a callable taking the argv list and
    the junit destination, returning the process return code. The default shells
    out to ``python -m pytest``.

    A failure is RECORDED, not swallowed — the point of the whole exercise is
    that a red suite is visible in the feed, and a caller that treats a red
    suite as fatal would let the test signal revert a good science run. The
    nightly's contract is: call this after publishing, log what it says, and
    keep going.

    ``result_path`` is the box-local SCRATCH (see ``RESULT_NAME``): the cadence
    bookkeeping ``is_due`` reads, and a handoff between this process and the
    receipt write. It is not what the feed publishes. The caller must hand the
    returned record to ``write_receipt`` for the verdict to leave this machine —
    ``lab selftest`` does, and it is the only production caller. Forgetting is
    fail-safe rather than fail-green: with no receipt on the ledger the feed
    publishes ``unknown`` for this box, never a stale pass.
    """
    started = now or datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="lab-selftest-") as tmp:
        junit = Path(tmp) / "junit.xml"
        argv = [python or sys.executable, "-m", "pytest", "-q",
                "-p", "no:cacheprovider", f"--junitxml={junit}"]
        record = _execute(argv, junit, repo_root, runner)
    finished = datetime.now(timezone.utc) if now is None else started
    record.update({
        "schema": RESULT_SCHEMA,
        "at": finished.isoformat(),
        "utc_date": finished.strftime("%Y-%m-%d"),
        "machine": machine_now(),
        "duration_s": round((finished - started).total_seconds(), 1),
    })
    write_result(result_path, record)
    return record


def _execute(argv, junit: Path, repo_root: Path, runner) -> dict:
    """Run the suite and read its junit. Every failure lands as a record, not a raise."""
    try:
        # stdin=DEVNULL because nobody is at the keyboard. This runs from Task
        # Scheduler and from a systemd-ish loop, where an inherited stdin is at
        # best invalid and at worst an open pipe; a test (or a git subprocess a
        # test spawns) that ever asks a question would otherwise block until
        # TIMEOUT_S and turn a one-second prompt into an hour of nothing. With
        # DEVNULL the read returns EOF and the suite fails fast and honestly.
        code = (runner(argv, junit) if runner is not None
                else subprocess.call(argv, cwd=str(repo_root), timeout=TIMEOUT_S,
                                     stdin=subprocess.DEVNULL))
    except subprocess.TimeoutExpired:
        return {"status": "error", "gpu_tests_ran": False,
                "detail": f"pytest did not finish inside {TIMEOUT_S}s — recorded as an error, not a pass"}
    except OSError as exc:
        return {"status": "error", "gpu_tests_ran": False,
                "detail": f"pytest could not be launched ({exc}) — recorded as an error, not a pass"}
    try:
        counts = parse_junit(junit.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "error", "gpu_tests_ran": False,
                "detail": f"pytest exited {code} but its report was unreadable ({exc})"}

    record = dict(counts)
    record["gpu_tests_ran"] = counts["total"] > 0 and gpu_tests_ran(counts)
    if counts["total"] == 0:
        record["status"] = "error"
        record["detail"] = f"pytest exited {code} having collected no tests"
        return record
    record["status"] = "pass" if (code == 0 and not counts["failed"] and not counts["errors"]) else "fail"
    if record["gpu_tests_ran"]:
        gpu = "the GPU-gated tests ran"
    elif counts["gpu_skipped"]:
        gpu = (f"{counts['gpu_skipped']} GPU-gated tests were SKIPPED — "
               f"this box did not exercise them")
    else:
        gpu = ("the run never reached every GPU-gated module "
               f"(saw {counts['gpu_modules_seen'] or 'none'}) — the GPU tests are UNCONFIRMED")
    record["detail"] = (f"{counts['passed']} passed, {counts['failed']} failed, "
                        f"{counts['skipped']} skipped; {gpu}")
    return record


def write_result(path: Path, record: dict) -> Path:
    """Write the record. Insertion order, never ``sort_keys`` — see DET-3."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path
