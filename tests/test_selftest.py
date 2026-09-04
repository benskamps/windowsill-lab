"""The test suite's own turn — the producer, the cadence, and the honest block.

The defect this suite guards (2026-09-04) is not "pytest is broken". It is that
NOTHING SCHEDULED RAN PYTEST, and ``pot.json`` — the only windowsill signal the
estate reads — said nothing either way, so "a box published a receipt" quietly
became the proxy for "the tests ran". These tests hold the three properties that
make the new signal worth having:

  * absent is not passing — a missing or malformed result reads as ``unknown``;
  * stale is not passing — an old green is demoted where it cannot be misread;
  * a green suite that SKIPPED the GPU-gated tests does not read like one that
    ran them.

Every rule that can be a pure function is tested as one. ``run`` is driven
through its ``runner`` seam against real junit XML rather than by launching a
nested pytest, which would take 13 minutes and test the wrong thing.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lab import archive, publish, selftest


NOW = datetime(2026, 9, 4, 4, 0, 0, tzinfo=timezone.utc)


def _record(**over) -> dict:
    base = {
        "schema": selftest.RESULT_SCHEMA,
        "status": "pass",
        "passed": 1200, "failed": 0, "skipped": 16, "errors": 0, "total": 1216,
        "gpu_skipped": 0,
        "gpu_tests_ran": True,
        "at": (NOW - timedelta(hours=2)).isoformat(),
        "utc_date": "2026-09-04",
        "machine": "windows-cuda",
        "detail": "1200 passed, 0 failed, 16 skipped; the GPU-gated tests ran",
    }
    base.update(over)
    return base


def _junit(cases: str) -> str:
    return f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">{cases}</testsuite></testsuites>'


PASS_CASE = '<testcase classname="tests.test_x" name="test_a" time="0.1"/>'
# The two modules that hold GPU-gated tests. A run must be SEEN to reach both
# before it may claim it exercised them — see selftest.gpu_tests_ran.
GPU_RAN = "".join(
    f'<testcase classname="{m}" name="test_gpu_smoke" time="0.4"/>'
    for m in selftest.GPU_TEST_MODULES)
FAIL_CASE = ('<testcase classname="tests.test_x" name="test_b" time="0.1">'
             '<failure message="assert 1 == 2">boom</failure></testcase>')
GPU_SKIP = ('<testcase classname="tests.test_ising" name="test_gpu" time="0.0">'
            '<skipped type="pytest.skip" message="GPU not available">unconditional skip</skipped>'
            '</testcase>')
OTHER_SKIP = ('<testcase classname="tests.test_y" name="test_c" time="0.0">'
              '<skipped type="pytest.skip" message="needs network">skipped</skipped></testcase>')


# ── absent / malformed: unknown, never green ────────────────────────────────

def test_a_missing_result_file_reads_as_unknown_not_green(tmp_path):
    block = selftest.tests_block(tmp_path / "nothing.json", now=NOW)
    assert block["status"] == "unknown"
    assert block["status"] != "pass"
    assert block["gpu_tests_ran"] is False
    assert block["at"] is None
    assert block["passed"] is None
    assert "never" in block["detail"] or "not a passing one" in block["detail"]


def test_a_malformed_result_file_reads_as_unknown_not_green(tmp_path):
    path = tmp_path / selftest.RESULT_NAME
    path.write_text("{not json at all", encoding="utf-8")
    block = selftest.tests_block(path, now=NOW)
    assert block["status"] == "unknown"
    assert block["gpu_tests_ran"] is False


@pytest.mark.parametrize("record", [
    "a bare string",
    ["a", "list"],
    {},                                                   # no schema
    {"schema": 999, "status": "pass", "at": NOW.isoformat()},   # a future schema
    {"schema": selftest.RESULT_SCHEMA, "status": "green"},      # unknown vocabulary
    {"schema": selftest.RESULT_SCHEMA, "status": "pass"},       # no timestamp
    {"schema": selftest.RESULT_SCHEMA, "status": "pass", "at": ""},
])
def test_every_unreadable_record_shape_degrades_to_unknown(record):
    block = selftest.block_from(record, now=NOW)
    assert block["status"] == "unknown", record
    assert block["gpu_tests_ran"] is False


def test_the_unknown_block_carries_every_field_a_reader_expects(tmp_path):
    """Shape-identical to a real one, so a consumer never KeyErrors into a guess."""
    unknown = selftest.tests_block(tmp_path / "nothing.json", now=NOW)
    fresh = selftest.block_from(_record(), now=NOW)
    assert set(unknown) <= set(fresh)
    assert set(fresh) - set(unknown) == set()


# ── stale: an old green is not a current one ────────────────────────────────

def test_a_fresh_pass_reads_as_pass():
    block = selftest.block_from(_record(), now=NOW)
    assert block["status"] == "pass"
    assert "recorded_status" not in block
    assert block["machine"] == "windows-cuda"
    assert (block["passed"], block["failed"], block["skipped"]) == (1200, 0, 16)


def test_a_stale_pass_does_not_read_as_pass():
    old = _record(at=(NOW - timedelta(hours=selftest.STALE_AFTER_H + 1)).isoformat())
    block = selftest.block_from(old, now=NOW)
    assert block["status"] == "stale"
    assert block["status"] != "pass"
    assert block["recorded_status"] == "pass"      # the old grade, demoted
    assert "says nothing about now" in block["detail"]


def test_the_staleness_boundary_is_where_it_says_it_is():
    inside = _record(at=(NOW - timedelta(hours=selftest.STALE_AFTER_H - 1)).isoformat())
    outside = _record(at=(NOW - timedelta(hours=selftest.STALE_AFTER_H + 1)).isoformat())
    assert selftest.block_from(inside, now=NOW)["status"] == "pass"
    assert selftest.block_from(outside, now=NOW)["status"] == "stale"


def test_an_unparseable_timestamp_is_not_treated_as_fresh():
    block = selftest.block_from(_record(at="last tuesday"), now=NOW)
    assert block["status"] == "stale"
    assert block["recorded_status"] == "pass"


def test_a_stamp_from_the_future_can_never_read_as_a_current_pass():
    """The one stale case ``STALE_AFTER_H`` alone cannot catch.

    Staleness is ``age > STALE_AFTER_H``, and a stamp ahead of now has a
    NEGATIVE age — it fails that test today and every day after, so a single
    green run written under a skewed clock (a box that came back from sleep with
    a bad RTC, a VM restored from a snapshot) would publish as a current pass
    forever. That is the same shape as a stale green, arrived at from the other
    side, so it degrades the same way.
    """
    ahead = _record(at=(NOW + timedelta(hours=48)).isoformat())
    block = selftest.block_from(ahead, now=NOW)
    assert block["status"] == "stale"
    assert block["recorded_status"] == "pass"
    assert "FUTURE" in block["detail"]
    # ...and ordinary clock noise is still fresh, not an alarm.
    near = _record(at=(NOW + timedelta(minutes=5)).isoformat())
    assert selftest.block_from(near, now=NOW)["status"] == "pass"


def test_a_naive_timestamp_is_read_as_utc_rather_than_rejected():
    naive = (NOW - timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert selftest.block_from(_record(at=naive), now=NOW)["status"] == "pass"


def test_a_recorded_failure_stays_a_failure():
    block = selftest.block_from(_record(status="fail", failed=3), now=NOW)
    assert block["status"] == "fail"
    assert block["failed"] == 3


# ── the GPU flag: the whole point ───────────────────────────────────────────

def test_the_gpu_module_names_match_the_real_gated_tests():
    """The list is only useful while it names modules that exist and gate on CUDA."""
    root = publish.REPO_ROOT
    for module in selftest.GPU_TEST_MODULES:
        path = root / (module.replace(".", "/") + ".py")
        assert path.exists(), f"{module} no longer exists — the GPU flag is now blind"
        assert selftest.GPU_SKIP_REASON in path.read_text(encoding="utf-8")


def test_the_gpu_flag_is_false_when_the_gpu_tests_skipped(tmp_path):
    counts = selftest.parse_junit(_junit(PASS_CASE + GPU_SKIP + GPU_SKIP))
    assert counts["gpu_skipped"] == 2
    assert counts["passed"] == 1 and counts["skipped"] == 2
    record = selftest.run(tmp_path, tmp_path / selftest.RESULT_NAME, runner=_stub_runner(
        _junit(PASS_CASE + GPU_SKIP + GPU_SKIP), 0), now=NOW)
    assert record["gpu_tests_ran"] is False
    assert "SKIPPED" in record["detail"]
    assert selftest.block_from(record, now=NOW)["gpu_tests_ran"] is False


def test_a_cpu_only_green_suite_does_not_read_like_a_gpu_one(tmp_path):
    """CI reports 24 skipped, a CUDA box 16 — and they must not publish alike."""
    cpu = selftest.run(tmp_path, tmp_path / "cpu.json",
                       runner=_stub_runner(_junit(PASS_CASE + GPU_SKIP), 0), now=NOW)
    gpu = selftest.run(tmp_path, tmp_path / "gpu.json",
                       runner=_stub_runner(_junit(PASS_CASE + GPU_RAN), 0), now=NOW)
    assert cpu["status"] == gpu["status"] == "pass"
    assert cpu["gpu_tests_ran"] is False
    assert gpu["gpu_tests_ran"] is True
    assert selftest.block_from(cpu, now=NOW) != selftest.block_from(gpu, now=NOW)


def test_a_non_gpu_skip_does_not_clear_the_gpu_flag():
    counts = selftest.parse_junit(_junit(PASS_CASE + GPU_RAN + OTHER_SKIP))
    assert counts["skipped"] == 1 and counts["gpu_skipped"] == 0
    assert selftest.gpu_tests_ran(counts) is True


def test_a_truncated_run_never_claims_the_gpu_tests_ran(tmp_path):
    """The bring-up run that found this: a MemoryError killed pytest at test 424
    of 2235, it never reached test_ising, nothing was skipped for want of a card
    — and the first cut of this module recorded ``gpu_tests_ran: true``. "No GPU
    test was skipped" is not evidence that any GPU test ran."""
    counts = selftest.parse_junit(_junit(PASS_CASE * 400))
    assert counts["gpu_skipped"] == 0          # nothing was skipped...
    assert selftest.gpu_tests_ran(counts) is False   # ...and nothing was proven
    record = selftest.run(tmp_path, tmp_path / selftest.RESULT_NAME,
                          runner=_stub_runner(_junit(PASS_CASE * 400), 1), now=NOW)
    assert record["gpu_tests_ran"] is False
    assert "UNCONFIRMED" in record["detail"]


def test_reaching_only_one_gpu_module_is_not_enough(tmp_path):
    """A subset run (`pytest tests/test_ising_hex.py`) proves only what it ran."""
    one = f'<testcase classname="{selftest.GPU_TEST_MODULES[0]}" name="t" time="0.1"/>'
    counts = selftest.parse_junit(_junit(PASS_CASE + one))
    assert counts["gpu_modules_seen"] == [selftest.GPU_TEST_MODULES[0]]
    assert selftest.gpu_tests_ran(counts) is False


def test_a_run_that_collected_nothing_never_claims_the_gpu_tests_ran(tmp_path):
    record = selftest.run(tmp_path, tmp_path / selftest.RESULT_NAME,
                          runner=_stub_runner(_junit(""), 0), now=NOW)
    assert record["status"] == "error"
    assert record["gpu_tests_ran"] is False


# ── the junit reader ────────────────────────────────────────────────────────

def test_parse_junit_counts_each_outcome():
    counts = selftest.parse_junit(_junit(PASS_CASE * 3 + FAIL_CASE + GPU_SKIP + OTHER_SKIP))
    assert counts == {"passed": 3, "failed": 1, "skipped": 2, "errors": 0,
                      "gpu_skipped": 1, "total": 6,
                      "gpu_modules_seen": ["tests.test_ising"]}


def test_parse_junit_accepts_a_bare_testsuite_root():
    text = f'<testsuite name="pytest">{PASS_CASE}</testsuite>'
    assert selftest.parse_junit(text)["passed"] == 1


@pytest.mark.parametrize("text", ["", "not xml", "<other/>"])
def test_parse_junit_refuses_what_it_cannot_read(text):
    with pytest.raises(ValueError):
        selftest.parse_junit(text)


# ── the producer ────────────────────────────────────────────────────────────

def _stub_runner(junit_text: str | None, code: int):
    def runner(argv, junit: Path):
        assert "pytest" in argv, argv
        if junit_text is not None:
            junit.write_text(junit_text, encoding="utf-8")
        return code
    return runner


def test_run_writes_a_parseable_record_that_the_reader_agrees_with(tmp_path):
    dest = tmp_path / "lab" / selftest.RESULT_NAME
    record = selftest.run(tmp_path, dest,
                          runner=_stub_runner(_junit(PASS_CASE + GPU_SKIP), 0))
    on_disk = json.loads(dest.read_text(encoding="utf-8"))
    assert on_disk == record
    assert selftest.tests_block(dest)["status"] == "pass"
    assert selftest.last_run_date(dest) == on_disk["utc_date"]


def test_run_records_a_red_suite_as_a_failure_rather_than_dropping_it(tmp_path):
    dest = tmp_path / selftest.RESULT_NAME
    record = selftest.run(tmp_path, dest,
                          runner=_stub_runner(_junit(PASS_CASE + FAIL_CASE), 1))
    assert record["status"] == "fail"
    # Read on the same clock that wrote it. `run` without `now` stamps the real
    # one, so handing the reader the fixture clock (hours earlier) hands it a
    # record from its own future — which is now a `stale`, not a `fail`.
    assert selftest.tests_block(dest)["status"] == "fail"


def test_run_records_an_unlaunchable_pytest_as_an_error(tmp_path):
    def explode(argv, junit):
        raise OSError("no interpreter")
    record = selftest.run(tmp_path, tmp_path / selftest.RESULT_NAME, runner=explode)
    assert record["status"] == "error"
    assert record["gpu_tests_ran"] is False


def test_run_records_an_unreadable_report_as_an_error(tmp_path):
    record = selftest.run(tmp_path, tmp_path / selftest.RESULT_NAME,
                          runner=_stub_runner(None, 0))     # writes no junit at all
    assert record["status"] == "error"


def test_the_written_record_is_not_key_sorted(tmp_path):
    """DET-3 again: nothing this repo writes gains ``sort_keys``."""
    dest = tmp_path / selftest.RESULT_NAME
    selftest.write_result(dest, {"zeta": 1, "alpha": 2})
    text = dest.read_text(encoding="utf-8")
    assert text == '{\n  "zeta": 1,\n  "alpha": 2\n}\n'


def test_the_real_runner_never_hands_pytest_an_interactive_stdin(tmp_path, monkeypatch):
    """Nobody is at the keyboard when this fires.

    The default runner shells out from Task Scheduler and from the campaign
    loop. An inherited stdin there is invalid at best and an open pipe at worst,
    and any test — or any ``git`` a test spawns — that asked a question would
    block until ``TIMEOUT_S``, turning a one-second prompt into an hour of
    silence and a nightly whose only test signal is a timeout. DEVNULL makes
    that read EOF instead, so the suite fails fast and says something true.
    """
    seen = {}

    def fake_call(argv, **kw):
        seen.update(kw)
        return 0

    monkeypatch.setattr(selftest.subprocess, "call", fake_call)
    selftest.run(tmp_path, tmp_path / selftest.RESULT_NAME)   # no runner ⇒ real path
    assert seen["stdin"] is selftest.subprocess.DEVNULL
    assert seen["timeout"] == selftest.TIMEOUT_S


def test_machine_now_speaks_the_archives_vocabulary():
    """Whatever box runs this, the name is one archive.machine_of would emit."""
    from lab.archive import _MACHINE_RE
    machine = selftest.machine_now()
    assert machine is None or _MACHINE_RE.match(machine), machine


# ── the cadence ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hour", list(selftest.DUE_UTC_HOURS))
def test_a_pass_inside_the_window_is_due(hour):
    due, _ = selftest.is_due(NOW.replace(hour=hour), None)
    assert due


@pytest.mark.parametrize("hour", [h for h in range(24) if h not in selftest.DUE_UTC_HOURS])
def test_a_pass_outside_the_window_is_not_due(hour):
    due, why = selftest.is_due(NOW.replace(hour=hour), None)
    assert not due
    assert "window" in why


def test_a_second_pass_on_the_same_utc_day_is_not_due():
    """The window alone would fire 12x in loam's 30-minute interval mode."""
    due, why = selftest.is_due(NOW.replace(hour=1), "2026-09-04")
    assert not due
    assert "already ran today" in why


def test_yesterdays_run_does_not_block_todays():
    due, _ = selftest.is_due(NOW.replace(hour=1), "2026-09-03")
    assert due


def test_is_due_normalises_a_non_utc_clock():
    """A box handing us local time must not get a different answer than UTC."""
    local = datetime(2026, 9, 4, 20, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert local.astimezone(timezone.utc).hour == 3
    due, _ = selftest.is_due(local, None)
    assert due


def test_exactly_one_of_four_six_hourly_passes_is_due_per_utc_day():
    """The cadence claim, exercised rather than asserted.

    Win takes 00/06/12/18 local and loam 03/09/15/21 local. A six-hour window
    catches exactly one of any four passes spaced six hours apart, whatever the
    box's UTC offset — which is why neither machine needs new config.
    """
    for offset in range(-12, 15):
        for local_slots in ([0, 6, 12, 18], [3, 9, 15, 21]):
            utc_hours = [(h - offset) % 24 for h in local_slots]
            due_count = sum(
                1 for h in utc_hours
                if selftest.is_due(NOW.replace(hour=h), None)[0]
            )
            assert due_count == 1, (offset, local_slots, utc_hours)


# ── the command: --if-due really gates, --status never eats the turn ────────

def test_if_due_does_not_launch_the_suite_on_a_pass_that_is_not_due(monkeypatch, capsys, tmp_path):
    """The gate has to be REAL, not just present in the template.

    ``campaign.sh`` calls this line on every pass, and loam's plain-interval
    mode wakes every 30 minutes. If ``--if-due`` ever stopped short-circuiting,
    the loop would launch a ~14-minute pytest 48 times a day on top of the
    science it is supposed to be running. Grepping the template for the flag
    cannot see that; calling the command can.
    """
    from lab import cli

    monkeypatch.setattr(cli, "LAB_HOME", tmp_path)
    monkeypatch.setattr(selftest, "is_due", lambda *a, **k: (False, "not this box's turn"))
    monkeypatch.setattr(selftest, "run", _never_run)
    assert cli.main(["selftest", "--if-due"]) == 0
    assert "not due" in capsys.readouterr().out


def test_if_due_launches_the_suite_on_the_pass_that_is_due(monkeypatch, capsys, tmp_path):
    """The fence on the test above: the gate must open, or it gates forever.

    And the run has to leave a RECEIPT, because that is the only way the verdict
    reaches the feed now — `~/.lab/selftest-latest.json` is scratch, and a run
    that files nothing publishes as `unknown` for this box.
    """
    from lab import cli

    receipts = tmp_path / "receipts"
    monkeypatch.setattr(cli, "LAB_HOME", tmp_path)
    monkeypatch.setattr(publish, "RECEIPTS_DIR", receipts)
    monkeypatch.setattr(selftest, "is_due", lambda *a, **k: (True, "its turn"))
    monkeypatch.setattr(selftest, "run", lambda *a, **k: _record(status="pass"))
    assert cli.main(["selftest", "--if-due"]) == 0
    assert "due" in capsys.readouterr().out
    filed = list(receipts.glob(selftest.RECEIPT_GLOB))
    assert len(filed) == 1, "the run's verdict never left the box"
    assert selftest.block_from(
        json.loads(filed[0].read_text(encoding="utf-8"))["selftest"],
        now=NOW)["status"] == "pass"


def test_status_is_a_reader_and_never_consumes_the_turn(monkeypatch, capsys, tmp_path):
    """``--status`` prints the block. It must not also be a way to skip the run.

    Handled after ``--if-due`` it was exactly that: on the one pass a box is due,
    ``selftest --if-due --status`` printed the block and returned 0 without ever
    running pytest — a green-looking line in the nightly log standing in for a
    suite that never ran.
    """
    from lab import cli

    monkeypatch.setattr(cli, "LAB_HOME", tmp_path)
    monkeypatch.setattr(publish, "RECEIPTS_DIR", tmp_path / "no-receipts-here")
    monkeypatch.setattr(selftest, "is_due", lambda *a, **k: (True, "its turn"))
    monkeypatch.setattr(selftest, "run", _never_run)
    assert cli.main(["selftest", "--if-due", "--status"]) == 0
    printed = json.loads(capsys.readouterr().out)
    # It prints what the FEED carries — every declared machine — not this box's
    # scratch record, so `--status` and pot.json can never disagree.
    assert set(printed) == set(publish.CADENCE["machines"])
    assert all(row["status"] == "unknown" for row in printed.values())


def _never_run(*a, **k):
    raise AssertionError("the suite was launched on a pass that should not have run it")


# ── the feed carries it, PER MACHINE ────────────────────────────────────────
# The blocker that stopped the first cut of this shipping. `pot.json` had ONE
# `tests` slot for a TWO-box fact and `publish.collect` filled it from THIS box's
# ~/.lab/selftest-latest.json, on a feed both machines publish. So win's red
# suite was overwritten by loam's green a few hours later and loam's by win's:
# last-writer-wins on shared mutable state, which is the green-while-dead class
# this whole change exists to retire.
#
# `turns.last_by_machine` had already solved it, and solved it in the strong
# way — a per-machine map derived by walking the COMMITTED receipt ledger, so
# each box only ever appends a row no other box writes. These tests hold that
# same property for `tests`.

_PLATFORM = {"windows-cuda": "windows-amd64", "linux-rocm": "linux-x86_64"}
_TORCH = {"windows-cuda": "2.9.1+cu124", "linux-rocm": "2.10.0.dev+rocm6.4"}


def _receipt(receipts, box="windows-cuda", torch=None, **over):
    """One committed selftest receipt, named and shaped as `lab selftest` files it."""
    record = _record(**over)
    stamp = record["at"]
    return selftest.write_receipt(
        receipts, record, date=stamp[:10], turn=stamp[11:13] + stamp[14:16],
        prov={"python": "3.11.9", "platform": _PLATFORM[box],
              "dependencies": {"torch": torch or _TORCH[box]}})


def _collect_with(monkeypatch, receipts):
    """Drive the REAL publisher over a fixture ledger.

    ~20s a call (collect() walks the whole committed archive), so only the tests
    that must prove the FEED carries something use it; the rest exercise
    ``tests_by_machine`` directly, which is the function collect() calls.
    """
    monkeypatch.setattr(publish, "RECEIPTS_DIR", receipts)
    monkeypatch.setattr(publish, "LAB_HOME", receipts / "no-such-lab-home")
    monkeypatch.setattr(selftest, "STALE_AFTER_H", 10 ** 6)   # never stale here
    return publish.collect()


def test_a_red_suite_on_one_box_survives_a_green_one_on_the_other(tmp_path, monkeypatch):
    """THE ERASURE PROOF, and the reason the shape changed.

    Two machines, two verdicts, one feed. Under the old single-slot shape the
    second box to publish simply overwrote the first — so this asserts both
    verdicts are present in the SAME pot.json, and then demonstrates the old
    shape losing one, so the test can tell a fix from a coincidence.
    """
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", status="fail", failed=3, passed=1197,
             detail="1197 passed, 3 failed, 16 skipped; the GPU-gated tests ran")
    _receipt(receipts, "linux-rocm", status="pass", failed=0, passed=1200,
             gpu_tests_ran=False,
             detail="1200 passed, 0 failed, 24 skipped; the GPU-gated tests did NOT run")

    snap = _collect_with(monkeypatch, receipts)

    # Both survive, in one feed, at the same time.
    assert snap["tests"]["windows-cuda"]["status"] == "fail"
    assert snap["tests"]["windows-cuda"]["failed"] == 3
    assert snap["tests"]["linux-rocm"]["status"] == "pass"
    assert snap["tests"]["linux-rocm"]["gpu_tests_ran"] is False

    # ...and the old shape really would have lost one. A single slot filled from
    # whichever box published last carries exactly ONE of these two verdicts, and
    # which one depends only on publish order.
    win = selftest.block_from(_record(status="fail", failed=3), now=NOW)
    loam = selftest.block_from(_record(status="pass"), now=NOW)
    assert win != loam
    for last_writer in (win, loam):
        single_slot = {"tests": last_writer}
        # One object, one status: whatever the last writer said is the whole of
        # what a reader sees, and the other box's grade is simply not in the file.
        assert single_slot["tests"]["status"] in ("fail", "pass")
        assert len([b for b in (win, loam)
                    if b["status"] == single_slot["tests"]["status"]]) == 1
    # The map holds both statuses the single slot had to choose between.
    assert {row["status"] for row in snap["tests"].values()} == {"fail", "pass"}


def test_neither_box_can_write_the_other_boxs_row(tmp_path):
    """Structural, not merely detected: the two boxes cannot collide on a name.

    Each receipt is named for the machine `archive.machine_of` derives from its
    OWN provenance, so there is no filename both boxes produce and therefore no
    row one can land on top of. This is the property `turns.last_by_machine` has
    and the single `tests` slot did not.
    """
    receipts = tmp_path / "receipts"
    win = _receipt(receipts, "windows-cuda", status="fail")
    loam = _receipt(receipts, "linux-rocm", status="pass")
    assert win != loam
    assert "windows-cuda" in win.name and "linux-rocm" in loam.name
    assert sorted(p.name for p in receipts.glob(selftest.RECEIPT_GLOB)) == \
        sorted([win.name, loam.name])


def test_a_machine_that_never_reported_is_present_and_unknown(tmp_path, monkeypatch):
    """A MISSING key reads as 'fine' to a careless consumer. Every box gets a row."""
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda")
    snap = _collect_with(monkeypatch, receipts)
    assert set(snap["tests"]) == set(publish.CADENCE["machines"])
    silent = snap["tests"]["linux-rocm"]
    assert silent["status"] == "unknown"
    assert silent["status"] != "pass"
    assert silent["machine"] == "linux-rocm"      # the row names its own box
    assert silent["gpu_tests_ran"] is False
    assert "no readable test receipt" in silent["detail"]


def test_an_empty_ledger_still_publishes_every_declared_machine(tmp_path):
    blocks = selftest.tests_by_machine(tmp_path / "nothing-here",
                                       publish.CADENCE["machines"], now=NOW)
    assert set(blocks) == set(publish.CADENCE["machines"])
    assert all(row["status"] == "unknown" for row in blocks.values())


def test_the_row_is_filed_under_the_derived_machine_not_the_self_reported_one(tmp_path):
    """A box that mislabels itself must not file under its sibling's name.

    ONE derivation of a machine name in this repo — `archive.machine_of`, over
    the receipt's own provenance. The record carries a `machine` field too (the
    box's note about itself); it is never what the ledger believes.
    """
    receipts = tmp_path / "receipts"
    _receipt(receipts, "linux-rocm", machine="windows-cuda")   # the record lies
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert blocks["linux-rocm"]["status"] == "pass"
    assert blocks["linux-rocm"]["machine"] == "linux-rocm"
    assert blocks["windows-cuda"]["status"] == "unknown"


def test_an_undeclared_machine_gets_no_row(tmp_path):
    """Same rule turn_cadence applies: a row for an undeclared box would turn an
    observation into an expectation."""
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", torch="2.9.1")   # no +cu ⇒ plain "windows"
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert set(blocks) == set(publish.CADENCE["machines"])
    assert blocks["windows-cuda"]["status"] == "unknown"


def test_the_newest_receipt_wins_within_a_machine(tmp_path):
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", status="fail",
             at=(NOW - timedelta(hours=30)).isoformat())
    _receipt(receipts, "windows-cuda", status="pass",
             at=(NOW - timedelta(hours=2)).isoformat())
    assert len(list(receipts.glob(selftest.RECEIPT_GLOB))) == 2
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert blocks["windows-cuda"]["status"] == "pass"


def test_a_future_stamped_receipt_cannot_pin_a_machines_row_forever(tmp_path):
    """The clock defect, at the map level.

    `stamp > prior` has no upper bound, so a receipt from 2099 wins every
    newest-wins comparison from now on and nothing filed afterwards can ever
    replace it. Refusing it leaves the real newest receipt in charge; a box whose
    ONLY receipts are future-stamped reads `unknown` and says why, which is loud
    and is the safe direction — never a green.
    """
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", status="fail",
             at=(NOW - timedelta(hours=1)).isoformat())
    _receipt(receipts, "windows-cuda", status="pass",
             at=(NOW + timedelta(days=400)).isoformat())
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert blocks["windows-cuda"]["status"] == "fail", \
        "a stamp from the future pinned the row and hid the real newest run"

    only_future = tmp_path / "only-future"
    _receipt(only_future, "linux-rocm", status="pass",
             at=(NOW + timedelta(days=400)).isoformat())
    blocks = selftest.tests_by_machine(only_future, publish.CADENCE["machines"], now=NOW)
    assert blocks["linux-rocm"]["status"] == "unknown"
    assert "FUTURE" in blocks["linux-rocm"]["detail"]


def test_a_stale_row_keeps_its_grade_where_it_cannot_read_as_current(tmp_path):
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", status="pass",
             at=(NOW - timedelta(hours=selftest.STALE_AFTER_H + 5)).isoformat())
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert blocks["windows-cuda"]["status"] == "stale"
    assert blocks["windows-cuda"]["recorded_status"] == "pass"


@pytest.mark.parametrize("body", ["{not json", '{"schema": "x"}', "[]",
                                  '{"schema": "windowsill.selftest-receipt.v1"}'])
def test_an_unreadable_receipt_leaves_its_machine_unknown(tmp_path, body):
    receipts = tmp_path / "receipts"
    good = _receipt(receipts, "windows-cuda")
    good.write_text(body, encoding="utf-8")
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert blocks["windows-cuda"]["status"] == "unknown"
    assert blocks["windows-cuda"]["gpu_tests_ran"] is False


def test_the_gpu_flag_stays_two_sided_through_the_ledger(tmp_path):
    """A CPU-only green suite must not read like one that exercised the card —
    the property the whole block exists for, held per machine end to end."""
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", gpu_tests_ran=True)
    _receipt(receipts, "linux-rocm", gpu_tests_ran=False)
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert blocks["windows-cuda"]["gpu_tests_ran"] is True
    assert blocks["linux-rocm"]["gpu_tests_ran"] is False
    assert blocks["windows-cuda"]["status"] == blocks["linux-rocm"]["status"] == "pass"
    assert blocks["windows-cuda"] != blocks["linux-rocm"]


def test_build_snapshot_carries_the_tests_map():
    snap = publish.build_snapshot([], None, 0, None,
                                  tests={"windows-cuda": selftest.unknown_block(
                                      "nothing yet", "windows-cuda")})
    assert snap["tests"]["windows-cuda"]["status"] == "unknown"


def test_a_broken_reader_still_publishes_a_row_per_machine(tmp_path, monkeypatch):
    """publish.collect wraps its optional blocks in bare excepts that DROP the key
    on a raise. For this one that would delete the very field whose absence
    started all this — and a map that silently drops a BOX is the same defect one
    level in — so the per-machine fallback is seeded before the try."""
    monkeypatch.setattr(publish, "RECEIPTS_DIR", tmp_path)
    monkeypatch.setattr(publish, "LAB_HOME", tmp_path / "lab")
    monkeypatch.setattr(selftest, "tests_by_machine",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    snap = publish.collect()
    assert set(snap["tests"]) == set(publish.CADENCE["machines"])
    for machine, row in snap["tests"].items():
        assert row["status"] == "unknown"
        assert row["machine"] == machine
        assert row["gpu_tests_ran"] is False


def test_the_tests_map_conforms_to_the_published_schema(tmp_path):
    """Producer and consumer share schema/pot.schema.json; keep them from drifting."""
    from tests.test_schema import SCHEMA, validate   # the repo's tiny validator

    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", status="fail", failed=2)
    _receipt(receipts, "linux-rocm", status="pass",
             at=(NOW - timedelta(days=9)).isoformat())
    for block in (selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW),
                  selftest.tests_by_machine(tmp_path / "empty",
                                            publish.CADENCE["machines"], now=NOW)):
        snap = publish.build_snapshot([], None, 0, None, tests=block)
        assert validate(snap, SCHEMA) == [], (block, validate(snap, SCHEMA))


def test_the_schema_validator_actually_checks_the_map_rows():
    """The fence on the test above.

    The tiny validator walked `properties` only, so an `additionalProperties`
    map — `turns.last_by_machine`, and now `tests` — went entirely unchecked and
    a conformance assertion over it proved nothing at all. This proves it bites.
    """
    from tests.test_schema import SCHEMA, validate

    assert validate({"tests": {"windows-cuda": {"status": "green"}}}, SCHEMA)
    assert validate({"tests": {"windows-cuda": {"passed": -1}}}, SCHEMA)
    assert validate({"tests": {"windows-cuda": {"status": "fail"}}}, SCHEMA) == []


# ── the receipt itself ──────────────────────────────────────────────────────

def test_the_receipt_is_not_filed_as_a_science_run(tmp_path):
    """`run-<date>-*.json` is the SCIENCE ledger's glob.

    The turn counter, the archive index, the scoreboard, the planner's repeat
    law, the physics feed and CI's repeat alarm all walk it. A selftest receipt
    filed under that prefix would be counted by every one of them as a turn that
    measured something, inflating the cadence the public page publishes.
    """
    path = _receipt(tmp_path / "receipts", "windows-cuda")
    assert path.name.startswith("selftest-")
    assert not path.name.startswith("run-")
    assert list((tmp_path / "receipts").glob("run-*.json")) == []


def test_the_receipt_carries_provenance_the_archive_can_read(tmp_path):
    path = _receipt(tmp_path / "receipts", "linux-rocm")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert archive.machine_of(data) == "linux-rocm"
    assert data["schema"] == selftest.RECEIPT_SCHEMA_ID
    assert data["selftest"]["schema"] == selftest.RESULT_SCHEMA
    assert selftest.block_from(data["selftest"], now=NOW)["status"] == "pass"


def test_the_real_write_receipt_names_this_box_through_machine_of(tmp_path):
    """No second naming scheme: the filename's machine half is whatever
    archive.machine_of says about the provenance the receipt carries."""
    path = selftest.write_receipt(tmp_path, _record(), date="2026-09-04", turn="0312")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == selftest.receipt_name("2026-09-04", "0312",
                                              archive.machine_of(data))
    assert selftest.machine_now() == archive.machine_of(data)


def test_the_receipt_serialization_is_pinned_and_not_key_sorted(tmp_path):
    """DET-3 again: nothing this repo writes gains ``sort_keys``.

    A new committed artifact family needs its layout pinned, or a serializer
    refactor rewrites every receipt on the books on its next run and guarantees a
    conflict with the other box. This one is written like the pot and like the
    scratch record — indent=2, INSERTION order, ensure_ascii, trailing newline —
    and deliberately NOT like the sorted public measurement receipts.
    """
    path = selftest.write_receipt(tmp_path, {"zeta": 1, "alpha": 2, "at": None},
                                  date="2026-09-04", turn="0312",
                                  prov={"platform": "linux-x86_64",
                                        "dependencies": {"torch": "2.1+rocm6"}})
    text = path.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2) + "\n"
    assert text != json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
    assert text.index('"zeta"') < text.index('"alpha"')


# ── the turns comparison: the same clock defect, where it already lived ─────

def _run_receipt(receipts, name, at, torch):
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / name).write_text(json.dumps({
        "generated_at": at,
        "provenance": {"platform": "windows-amd64" if "cu" in torch else "linux-x86_64",
                       "dependencies": {"torch": torch}},
    }), encoding="utf-8")


def test_a_future_stamped_run_receipt_cannot_pin_last_by_machine(tmp_path, monkeypatch):
    """`turns.last_by_machine` carried the identical bug and it was still live.

        if prior is None or stamp > prior:

    is a bare wall-clock comparison with no upper bound. One receipt stamped
    ahead of now wins it today and every day after, so that machine's row is
    pinned to a record nothing can supersede — and the page's freshness clause
    reads that row, so the failure mode is a box that looks permanently fresh
    while it has stopped filing turns.
    """
    receipts = tmp_path / "receipts"
    real = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _run_receipt(receipts, "run-2026-09-04-0300-m01.json", real, "2.9.1+cu124")
    _run_receipt(receipts, "run-2099-01-01-0000-m02.json",
                 (datetime.now(timezone.utc) + timedelta(days=400)).isoformat(),
                 "2.9.1+cu124")

    monkeypatch.setattr(publish, "RECEIPTS_DIR", receipts)
    turns = publish.turn_cadence()
    assert turns["last_by_machine"]["windows-cuda"] == real, \
        "a stamp from the future was accepted as the newest turn"
    # The receipt still COUNTS as a turn — it happened. Only the "newest" claim
    # is refused, because that is the claim its clock cannot support.
    assert turns["count"] == 2


def test_ordinary_clock_noise_is_still_accepted_as_newest(tmp_path, monkeypatch):
    """The fence: minutes of skew between writing and reading is not an alarm."""
    receipts = tmp_path / "receipts"
    ahead = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    _run_receipt(receipts, "run-2026-09-04-0300-m01.json", ahead,
                 "2.10.0.dev+rocm6.4")
    monkeypatch.setattr(publish, "RECEIPTS_DIR", receipts)
    assert publish.turn_cadence()["last_by_machine"]["linux-rocm"] == ahead


@pytest.mark.parametrize("offset_h,expected", [
    (-100000, False),      # a stamp from the future: never "newer"
    (-2, False),
    (-0.5, True),          # inside the slack
    (0, True),
    (10000, True),         # merely old is perfectly datable
])
def test_stamp_is_datable_draws_the_line_where_it_says_it_does(offset_h, expected):
    stamp = (NOW - timedelta(hours=offset_h)).isoformat()
    assert selftest.stamp_is_datable(stamp, NOW) is expected


def test_an_unparseable_stamp_is_never_datable():
    assert selftest.stamp_is_datable("last tuesday", NOW) is False


# ── the suite must be safe to run IN the live clone ─────────────────────────

def test_a_publish_under_test_never_writes_the_committed_archive_index(tmp_path, monkeypatch):
    """The precondition for scheduling pytest at all, and it did not hold.

    ``publish.publish`` refreshes the COMMITTED ``reports/index.html`` through
    ``archive.write_index``, which resolves it off ``archive.REPORTS_DIR``. Three
    tests drove the real publisher with ``POT_JSON``/``LAB_HOME``/``WEB_INDEX``
    redirected but not that, so every ``pytest`` run rewrote a committed artifact
    and left the clone dirty.

    That was invisible while nothing scheduled ran pytest. The moment the nightly
    does, it is a lane-freezing bug: ``campaign.sh`` refuses a pass whose worktree
    is already dirty ("pre-existing tracked worktree changes; refusing to pull or
    run"), and the Windows nightly's ``git add -A reports/`` would sweep a
    fixture-built index into the next ``nightly:`` commit. So this is a tripwire,
    not a nicety.
    """
    committed = publish.REPO_ROOT / "reports" / "index.html"
    before = committed.read_bytes() if committed.exists() else None

    from lab import archive
    monkeypatch.setattr(publish, "POT_JSON", tmp_path / "pot.json")
    monkeypatch.setattr(publish, "LAB_HOME", tmp_path / "lab")
    monkeypatch.setattr(publish, "WEB_INDEX", tmp_path / "web-index.html")
    monkeypatch.setattr(archive, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(publish, "ensure_public_receipts", lambda *a, **k: [])
    monkeypatch.setattr(publish, "collect", lambda: {"schema_version": 5, "reports": []})
    publish.publish(quiet=True)

    after = committed.read_bytes() if committed.exists() else None
    assert after == before, "a test run rewrote the committed reports/index.html"


# ── the quiet way this block goes inert ─────────────────────────────────────

def test_a_receipt_no_declared_machine_matches_is_named_not_swallowed(tmp_path):
    """A box can stop being attributable WITHOUT anything looking wrong.

    Attribution is `archive.machine_of` over the receipt's provenance, and the
    accelerator half of that name comes from the torch build suffix. A box
    reinstalled with a plain PyPI wheel (`2.9.1`, no `+cu`/`+rocm`) derives as
    `windows`, not `windows-cuda` — so it files a perfect receipt every night,
    every one of them is skipped here, and its declared row reads exactly like a
    box that has never run pytest in its life. Silent, in the safe direction,
    and still a watchdog measuring nothing.

    (This is not hypothetical: it is the state of the review worktree's own venv,
    where `importlib.metadata.version("torch")` returns `2.9.1`.)
    """
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda", torch="2.9.1")     # no +cu ⇒ plain "windows"
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)

    row = blocks["windows-cuda"]
    assert row["status"] == "unknown"          # never green — that half was right
    assert "windows" in row["detail"]
    assert "undeclared box name" in row["detail"], (
        "a box filing unattributable receipts reads identically to one that "
        f"never ran: {row['detail']!r}")
    # The sibling that genuinely never reported keeps the plain wording, and the
    # note never contradicts a machine that DID report.
    assert "undeclared box name" in blocks["linux-rocm"]["detail"]


def test_the_note_is_absent_when_every_receipt_found_its_row(tmp_path):
    """The fence: a clean ledger must not grow a scary clause it has not earned."""
    receipts = tmp_path / "receipts"
    _receipt(receipts, "windows-cuda")
    blocks = selftest.tests_by_machine(receipts, publish.CADENCE["machines"], now=NOW)
    assert blocks["windows-cuda"]["status"] == "pass"
    assert "undeclared" not in blocks["linux-rocm"]["detail"]
    assert blocks["linux-rocm"]["detail"] == selftest.NEVER_REPORTED


def test_the_producer_says_so_when_its_verdict_will_reach_no_row(
        monkeypatch, capsys, tmp_path):
    """...and it says it ON THE BOX, on the run that would otherwise vanish.

    The feed's note is read by whoever opens pot.json. The nightly log is read by
    whoever is debugging the box. A 14-minute suite whose verdict is about to be
    dropped on the floor should say so in both.
    """
    from lab import cli

    monkeypatch.setattr(cli, "LAB_HOME", tmp_path)
    monkeypatch.setattr(publish, "RECEIPTS_DIR", tmp_path / "receipts")
    monkeypatch.setattr(selftest, "is_due", lambda *a, **k: (True, "its turn"))
    monkeypatch.setattr(selftest, "run", lambda *a, **k: _record())
    monkeypatch.setattr(selftest, "machine_now", lambda: "windows")   # no +cu wheel
    assert cli.main(["selftest", "--if-due"]) == 0
    out = capsys.readouterr().out
    assert "WARNING" in out and "'windows'" in out, out
    assert "IGNORED by the feed" in out, out


def test_the_producer_is_quiet_when_the_box_names_itself_properly(
        monkeypatch, capsys, tmp_path):
    """The fence on the warning — it must not cry on every ordinary night."""
    from lab import cli

    monkeypatch.setattr(cli, "LAB_HOME", tmp_path)
    monkeypatch.setattr(publish, "RECEIPTS_DIR", tmp_path / "receipts")
    monkeypatch.setattr(selftest, "is_due", lambda *a, **k: (True, "its turn"))
    monkeypatch.setattr(selftest, "run", lambda *a, **k: _record())
    monkeypatch.setattr(selftest, "machine_now", lambda: "windows-cuda")
    assert cli.main(["selftest", "--if-due"]) == 0
    assert "WARNING" not in capsys.readouterr().out
