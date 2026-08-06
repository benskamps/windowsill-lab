"""The lab runs in TURNS — two machines, one small lab, one honest counter.

A "turn" is one scheduled pass, whichever machine took it. That single word
change has real machinery behind it, and this module guards the parts of it
that can lie:

* **Receipts must survive same-day re-runs.** Before turn-stamping, two passes
  of one milestone on one day shared a filename and the second destroyed the
  first — which would make a turn counter undercount AND falsify the archive's
  "every run is kept" promise. The stamping is therefore the prerequisite, and
  its tests come first.
* **The machine is derived, never guessed.** A run that never recorded its
  provenance gets no machine mark, forever. Absence is the record telling the
  truth about itself; a date-inferred backfill would be fiction.
* **Expected cadence is DECLARED.** Nothing here may infer a rate from observed
  history — an inferred expectation lets a dying box quietly lower its own bar.
* **Cross-machine collapse is deliberate, and disclosed.** Merging two boxes'
  agreements is honest because the verdict is what's being grouped; the
  compensating controls are ``group_machines`` and the divergence detector, and
  both are tested against counter-fixtures that must NOT fire.

Stdlib-only, every fixture in ``tmp_path`` with the module dirs monkeypatched —
these never touch the live ``reports/`` or ``~/.lab``.
"""
import json
import os
import re
from pathlib import Path

from lab import archive, publish
from lab.archive import detect_divergence, machine_of, run_ledger, scan_runs

WEB = Path(__file__).resolve().parent.parent / "web" / "index.html"


def _patch(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    for module in (archive, publish):
        monkeypatch.setattr(module, "REPORTS_DIR", reports)
        monkeypatch.setattr(module, "RECEIPTS_DIR", reports / "receipts")
        monkeypatch.setattr(module, "LAB_HOME", lab_home)
    return reports, lab_home


def _provenance(machine="linux-rocm"):
    """Receipt provenance for a named box, in the real shape render.py writes."""
    os_half, accelerator = machine.split("-")
    arch = "x86_64" if os_half == "linux" else "amd64"
    torch = {"rocm": "2.10.0.dev20251031+rocm6.4", "cuda": "2.6.0+cu124"}[accelerator]
    return {
        "platform": f"{os_half}-{arch}",
        "python": "3.14.4",
        "source_clean": True,
        "source_commit": "0" * 40,
        "dependencies": {"torch": torch, "numpy": "2.5.1"},
    }


def _receipt(receipts, date, slug, *, turn=None, machine="linux-rocm",
             at=None, null=False, mtime=1000):
    """Write one committed receipt — the durable per-turn public record."""
    receipts.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": f"{slug.upper()}-verification",
        "headline": f"{slug} at {date} {turn or ''}".strip(),
        # A χ-sweep peaking at 2.3 verifies against Onsager; 1.6 is an honest null.
        "T": [2.2, 2.3, 2.4] if not null else [1.5, 1.6, 1.7],
        "chi": [1.0, 9.0, 1.0],
    }
    if machine:
        payload["provenance"] = _provenance(machine)
    if at:
        payload["generated_at"] = at
    path = receipts / publish._receipt_filename(date, slug, turn)
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _declare(monkeypatch, *, effective_from="2026-07-01", interval=3,
             machines=("windows-cuda", "linux-rocm")):
    monkeypatch.setattr(publish, "CADENCE", {
        "expected_interval_h": interval,
        "machines": list(machines),
        "effective_from": effective_from,
    })
    monkeypatch.setattr(archive, "CADENCE", publish.CADENCE)


# ── 1. The prerequisite: two turns in a day are two receipts ─────────────────

def test_two_same_day_turns_of_one_milestone_are_two_rows(tmp_path, monkeypatch):
    """The whole reason turn-stamping exists. Two passes of M01 on one day used
    to collide on ``run-<date>-m01.json`` and the second silently destroyed the
    first — so the ledger showed one run and the archive's "every run is kept"
    claim was false. Stamped, they are two receipts and two rows."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    _receipt(receipts, "2026-08-01", "m01", turn="0300",
             at="2026-08-01T07:00:00+00:00", mtime=1000)
    _receipt(receipts, "2026-08-01", "m01", turn="1500",
             at="2026-08-01T19:00:00+00:00", mtime=2000)

    assert len(list(receipts.glob("*.json"))) == 2
    rows = scan_runs()
    assert len(rows) == 2
    assert [r["turn"] for r in rows] == ["1500", "0300"]
    # Both are the same date, so ``runs`` (distinct dates) stays 1 while the
    # turn count is 2. Both numbers are true; they answer different questions.
    assert publish.run_cadence()[1] == 1
    assert publish.turn_cadence()["count"] == 2


def test_each_turn_keeps_its_own_archive_anchor(tmp_path, monkeypatch):
    """Two turns of one milestone must deep-link to two different rows —
    otherwise every same-day link resolves to whichever rendered last."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    _receipt(receipts, "2026-08-01", "m01", turn="0300", at="2026-08-01T07:00:00+00:00")
    _receipt(receipts, "2026-08-01", "m01", turn="1500", at="2026-08-01T19:00:00+00:00")
    hrefs = [r["report_href"] for r in scan_runs()]
    assert len(set(hrefs)) == 2
    assert all("#run-2026-08-01-" in h for h in hrefs)


def test_legacy_bare_receipt_name_parses_as_no_turn(tmp_path, monkeypatch):
    """Every receipt written before stamping keeps its name, its URL, and its
    behaviour: turn ``None``, one row, exactly as before."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _receipt(reports / "receipts", "2026-06-14", "m01", turn=None, machine=None)
    rows = scan_runs()
    assert len(rows) == 1
    assert rows[0]["turn"] is None
    assert rows[0]["receipt_href"].endswith("run-2026-06-14-m01.json")


def test_a_four_digit_turn_stamp_can_never_eat_a_milestone_slug():
    """The structural guard behind the filename grammar: slugs always start with
    a letter, so a leading ``\\d{4}-`` is unambiguously a turn stamp. If a slug
    could ever start with four digits, ``run-2026-08-01-1234-x.json`` would be
    unparseable — this pins the assumption rather than trusting it."""
    for slug in ("m01", "m17", "c01", "a01", "i01", "run"):
        assert publish._split_receipt_stem(f"2026-08-01-{slug}") == (
            "2026-08-01", None, slug)
        assert publish._split_receipt_stem(f"2026-08-01-0300-{slug}") == (
            "2026-08-01", "0300", slug)
        assert not re.match(r"^\d", slug), f"slug {slug!r} would collide with a stamp"


def test_backfill_never_mints_a_stamped_twin(tmp_path, monkeypatch):
    """``ensure_public_receipts`` rebuilds receipts from dated reports, which
    have already collapsed a day's turns into one file. If it invented a stamp
    it would put a SECOND receipt on the books for a run that already has one,
    double-counting every modern turn the moment this shipped."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "2026-06-14-m01.json").write_text(json.dumps({
        "experiment": "M01-ising-verification", "headline": "hi",
        "T": [2.2, 2.3, 2.4], "chi": [1.0, 9.0, 1.0],
        "generated_at": "2026-06-14T07:00:00+00:00",
    }), encoding="utf-8")
    _receipt(receipts, "2026-06-14", "m01", turn=None,
             at="2026-06-14T07:00:00+00:00", machine=None)

    publish.ensure_public_receipts()
    assert sorted(p.name for p in receipts.glob("*.json")) == [
        "run-2026-06-14-m01.json"]


def _lab_report(lab_home, date, slug, chi, *, mtime=9000):
    """A dated report in the ``~/.lab`` cache — the backfill's other source."""
    lab_home.mkdir(parents=True, exist_ok=True)
    path = lab_home / f"{date}-{slug}.json"
    path.write_text(json.dumps({
        "experiment": f"{slug.upper()}-ising-verification",
        "headline": "a different run of the same milestone",
        "T": [2.2, 2.3, 2.4], "chi": chi,
        "generated_at": f"{date}T19:00:00+00:00",
    }), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_a_committed_receipt_is_never_rewritten_from_a_lab_twin(tmp_path, monkeypatch):
    """The honest-archive invariant, from the incident of 2026-08-01.

    A receipt is EVIDENCE: once it is committed, the numbers in it are what that
    run measured, permanently. The backfill picks its source per (date, slug) —
    repo report, else newest ``~/.lab`` twin — and the repo's dated reports are
    gitignored, so on a fresh clone, on the other machine, or inside a worktree
    there is NO repo report to win. A worktree re-run of the same milestone on
    the same day then leaves a divergent ``~/.lab`` twin, and the backfill
    regenerated the reviewed receipt from it: K01's measured χ values were
    replaced with another run's numbers and 20 other receipts' provenance
    hashes churned (poison 51dc784, reverted 3119074).

    Regeneration cannot tell a correction from a corruption, so it may not
    happen at all. The receipt on disk wins over any source, forever."""
    reports, lab_home = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    committed = _receipt(receipts, "2026-08-01", "k01", turn=None,
                         at="2026-08-01T07:00:00+00:00", machine=None)
    before = committed.read_bytes()
    # The divergent twin: same run key, different measurements, newer mtime.
    _lab_report(lab_home, "2026-08-01", "k01", [1.0, 42.0, 1.0])

    paths = publish.ensure_public_receipts()

    assert committed.read_bytes() == before
    assert b"42.0" not in committed.read_bytes()
    assert json.loads(committed.read_text(encoding="utf-8"))["chi"] == [1.0, 9.0, 1.0]
    # Still reported as a receipt on the books — the guard skips the WRITE,
    # not the run, so callers that publish the returned list stay complete.
    assert paths == [committed]


def test_a_missing_receipt_is_still_backfilled(tmp_path, monkeypatch):
    """The counter-test for the guard above: immutability must protect only
    what already exists. A run whose receipt was never written still gets one —
    that is the backfill's actual job, and a guard that swallowed it would
    silently empty the public evidence feed on a fresh clone."""
    reports, lab_home = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    _lab_report(lab_home, "2026-08-01", "k01", [1.0, 42.0, 1.0])

    paths = publish.ensure_public_receipts()

    written = receipts / "run-2026-08-01-k01.json"
    assert paths == [written]
    assert json.loads(written.read_text(encoding="utf-8"))["chi"] == [1.0, 42.0, 1.0]


def test_same_day_turns_order_by_stamp_in_a_fresh_clone(tmp_path, monkeypatch):
    """A fresh clone flattens every mtime, so the sort has to fall back to
    content. Date alone can't order two turns of one day — the stamp can."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    for turn in ("0300", "1500", "0900"):
        _receipt(receipts, "2026-08-01", "m01", turn=turn,
                 at=f"2026-08-01T{turn[:2]}:00:00+00:00", mtime=5000)
    assert [r["turn"] for r in scan_runs()] == ["1500", "0900", "0300"]


# ── 2. The machine mark: derived from the run's own receipt, never guessed ───

def test_machine_derivation_reads_platform_and_torch_build():
    assert machine_of({"provenance": _provenance("linux-rocm")}) == "linux-rocm"
    assert machine_of({"provenance": _provenance("windows-cuda")}) == "windows-cuda"


def test_machine_derivation_keeps_the_half_it_knows():
    """An unrecognised torch build still leaves the OS half true. Half-known
    provenance is published as the half that is known, not discarded."""
    prov = _provenance("linux-rocm")
    prov["dependencies"]["torch"] = "2.9.0"        # no accelerator suffix
    assert machine_of({"provenance": prov}) == "linux"
    del prov["dependencies"]
    assert machine_of({"provenance": prov}) == "linux"


def test_machine_is_absent_never_guessed_on_pre_provenance_runs():
    """The load-bearing honesty control. The runs predating provenance stamping
    genuinely do not record which box ran them, and no amount of date inference
    changes that. The field must be ABSENT — not null, not a best guess."""
    assert machine_of({}) is None
    assert machine_of({"provenance": None}) is None
    assert machine_of({"provenance": {}}) is None
    assert machine_of({"provenance": {"python": "3.14.4"}}) is None
    # Nor from config.device, which reads "cuda" on BOTH boxes — torch's ROCm
    # build keeps the CUDA API names, so device is not evidence of a machine.
    assert machine_of({"config": {"device": "cuda"}}) is None


def test_machine_derivation_has_exactly_one_definition_site():
    """One pinned function. If a second derivation appears, the two drift and
    the page starts disagreeing with itself about which box ran a turn."""
    src = (Path(archive.__file__)).read_text(encoding="utf-8")
    assert src.count("def machine_of(") == 1
    for other in (publish, ):
        assert "def machine_of(" not in Path(other.__file__).read_text(encoding="utf-8")


def test_ledger_rows_carry_machine_and_at_only_when_recorded(tmp_path, monkeypatch):
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    _receipt(receipts, "2026-06-14", "m01", machine=None, mtime=1000)   # legacy
    _receipt(receipts, "2026-08-01", "m17", machine="windows-cuda",
             at="2026-08-01T12:03:11+00:00", mtime=2000)
    modern, legacy = run_ledger()
    assert modern["machine"] == "windows-cuda"
    assert modern["at"] == "2026-08-01T12:03:11+00:00"
    assert "machine" not in legacy and "at" not in legacy


# ── 3. The collapse: cross-machine merging is deliberate AND disclosed ───────

def test_cross_machine_agreement_merges_and_discloses_both_boxes(tmp_path, monkeypatch):
    """Merging agreements across machines is the DESIGNED behaviour: the claim
    being grouped is the verdict, and keying on machine would forbid nearly
    every collapse under an interleaved rotation. What makes it honest is the
    disclosure — ``group_machines`` names the boxes the group spans."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    for i, (date, machine) in enumerate([
        ("2026-07-28", "windows-cuda"), ("2026-07-29", "linux-rocm"),
        ("2026-07-30", "windows-cuda"), ("2026-07-31", "linux-rocm"),
    ]):
        _receipt(receipts, date, "m01", turn="0300", machine=machine,
                 at=f"{date}T07:00:00+00:00", mtime=1000 + i)
    rows = run_ledger()
    assert len(rows) == 1
    assert rows[0]["group_count"] == 4
    assert rows[0]["group_machines"] == ["linux-rocm", "windows-cuda"]


def test_a_missed_day_is_a_seam_not_a_smoothed_streak(tmp_path, monkeypatch):
    """N5 — the gap seam. Same milestone, same verdict, three days apart: a
    fully-missed day must never disappear inside an "×N turns" chip. Absence
    shows up as a break between groups."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    _receipt(receipts, "2026-07-20", "m01", turn="0300",
             at="2026-07-20T07:00:00+00:00", mtime=1000)
    _receipt(receipts, "2026-07-23", "m01", turn="0300",
             at="2026-07-23T07:00:00+00:00", mtime=2000)
    rows = run_ledger()
    assert [r["date"] for r in rows] == ["2026-07-23", "2026-07-20"]
    assert all("group_count" not in r for r in rows)


def test_consecutive_days_still_merge(tmp_path, monkeypatch):
    """The seam must not be so eager that an ordinary daily streak breaks."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    for i, date in enumerate(["2026-07-20", "2026-07-21", "2026-07-22"]):
        _receipt(receipts, date, "m01", turn="0300",
                 at=f"{date}T07:00:00+00:00", mtime=1000 + i)
    rows = run_ledger()
    assert len(rows) == 1 and rows[0]["group_count"] == 3


def test_group_of_pre_provenance_runs_stays_bare(tmp_path, monkeypatch):
    """A streak made entirely of runs that never recorded a machine gets no
    ``group_machines`` — the history collapses exactly as it did before."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    for i, date in enumerate(["2026-06-14", "2026-06-15", "2026-06-16"]):
        _receipt(receipts, date, "m01", machine=None, mtime=1000 + i)
    rows = run_ledger()
    assert rows[0]["group_count"] == 3
    assert "group_machines" not in rows[0]


def test_verdict_change_still_breaks_the_streak_across_machines(tmp_path, monkeypatch):
    """N1, re-run through the new code path. The real 7/28–7/30 M01 history:
    verified / null / verified. Three rows, whichever boxes produced them —
    a failed calibration can never hide inside a green group."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    _receipt(receipts, "2026-07-28", "m01", machine="windows-cuda",
             at="2026-07-28T07:00:00+00:00", mtime=1000)
    _receipt(receipts, "2026-07-29", "m01", machine="linux-rocm", null=True,
             at="2026-07-29T07:00:00+00:00", mtime=2000)
    _receipt(receipts, "2026-07-30", "m01", machine="windows-cuda",
             at="2026-07-30T07:00:00+00:00", mtime=3000)
    rows = run_ledger()
    assert [(r["date"], r["verdict"]) for r in rows] == [
        ("2026-07-30", "verified"), ("2026-07-29", "null"),
        ("2026-07-28", "verified"),
    ]
    assert all("group_count" not in r for r in rows)


# ── 4. Divergence: the compensating control, and what must NOT trigger it ────

def _split_history(receipts, verdict_by_machine, days=("2026-07-31", "2026-08-01")):
    i = 0
    for date in days:
        for machine, is_null in verdict_by_machine.items():
            _receipt(receipts, date, "m01", turn=f"{i:02d}00", machine=machine,
                     null=is_null, at=f"{date}T{i:02d}:00:00+00:00", mtime=1000 + i)
            i += 1


def test_machine_aligned_split_surfaces_one_plain_sentence(tmp_path, monkeypatch):
    """One box verified, the other null, twice each, inside 48h — the signature
    of a machine-specific problem rather than flakiness. Exactly one entry."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _declare(monkeypatch)
    monkeypatch.setattr(publish, "today_local", lambda: "2026-08-01")
    monkeypatch.setattr(archive, "today_local", lambda: "2026-08-01")
    _split_history(reports / "receipts",
                   {"windows-cuda": False, "linux-rocm": True})
    found = detect_divergence(scan_runs())
    assert found == [{"milestone": "M01", "machines": {
        "linux-rocm": "null", "windows-cuda": "verified"}}]


def test_one_flaky_null_is_not_divergence(tmp_path, monkeypatch):
    """Counter-fixture. Flakiness scatters across both boxes; a single miss must
    read as the noise it is, not as "the machines disagree"."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _declare(monkeypatch)
    monkeypatch.setattr(publish, "today_local", lambda: "2026-08-01")
    monkeypatch.setattr(archive, "today_local", lambda: "2026-08-01")
    receipts = reports / "receipts"
    _receipt(receipts, "2026-08-01", "m01", turn="0300", machine="windows-cuda",
             at="2026-08-01T03:00:00+00:00", mtime=1000)
    _receipt(receipts, "2026-08-01", "m01", turn="0600", machine="linux-rocm",
             at="2026-08-01T06:00:00+00:00", mtime=2000)
    _receipt(receipts, "2026-08-01", "m01", turn="0900", machine="windows-cuda",
             null=True, at="2026-08-01T09:00:00+00:00", mtime=3000)
    assert detect_divergence(scan_runs()) == []


def test_the_real_verified_null_verified_history_is_not_divergence(tmp_path, monkeypatch):
    """Counter-fixture from the committed record: the 7/28–7/30 M01 sequence is
    one box changing its mind over time, which is exactly what a calibration
    heartbeat looks like. It must not read as a machine split."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _declare(monkeypatch)
    monkeypatch.setattr(publish, "today_local", lambda: "2026-07-30")
    monkeypatch.setattr(archive, "today_local", lambda: "2026-07-30")
    receipts = reports / "receipts"
    for i, (date, null) in enumerate([("2026-07-28", False), ("2026-07-29", True),
                                      ("2026-07-30", False)]):
        _receipt(receipts, date, "m01", turn="0300", machine="linux-rocm",
                 null=null, at=f"{date}T03:00:00+00:00", mtime=1000 + i)
    assert detect_divergence(scan_runs()) == []


def test_divergence_is_inert_until_the_cadence_is_declared(tmp_path, monkeypatch):
    """Before both boxes are armed, "the machines disagree" is not a claim the
    lab is in a position to make — one of them isn't running on a schedule."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _declare(monkeypatch, effective_from=None)
    _split_history(reports / "receipts",
                   {"windows-cuda": False, "linux-rocm": True})
    assert detect_divergence(scan_runs()) == []


def test_divergence_ignores_history_older_than_48h(tmp_path, monkeypatch):
    reports, _ = _patch(tmp_path, monkeypatch)
    _declare(monkeypatch)
    monkeypatch.setattr(publish, "today_local", lambda: "2026-08-20")
    monkeypatch.setattr(archive, "today_local", lambda: "2026-08-20")
    _split_history(reports / "receipts",
                   {"windows-cuda": False, "linux-rocm": True})
    assert detect_divergence(scan_runs()) == []


# ── 5. The turns object: counted, and declared ───────────────────────────────

def test_turn_count_and_days_tended_are_both_true(tmp_path, monkeypatch):
    """Two turns of DIFFERENT milestones on one day: ``turns.count`` is 2 and
    ``runs`` is 1. Neither is wrong; ``runs`` keeps its name and its meaning so
    existing consumers are not silently re-pointed at a different number."""
    reports, _ = _patch(tmp_path, monkeypatch)
    receipts = reports / "receipts"
    monkeypatch.setattr(publish, "today_local", lambda: "2026-08-01")
    _receipt(receipts, "2026-08-01", "m01", turn="0300", at="2026-08-01T03:00:00+00:00")
    _receipt(receipts, "2026-08-01", "m17", turn="0900", at="2026-08-01T09:00:00+00:00")
    turns = publish.turn_cadence()
    assert turns["count"] == 2
    assert turns["today"] == 2
    assert publish.run_cadence()[1] == 1


def test_expected_interval_is_omitted_until_the_cadence_is_effective(tmp_path, monkeypatch):
    """The honesty rule made mechanical: expected is declared or it is nothing.
    A silent box can never lower its own bar by dragging an inferred rate down
    with it, and months of one-machine history are never retro-graded."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _receipt(reports / "receipts", "2026-08-01", "m01", turn="0300",
             at="2026-08-01T03:00:00+00:00")
    _declare(monkeypatch, effective_from=None)
    assert "expected_interval_h" not in publish.turn_cadence()
    _declare(monkeypatch, effective_from="2999-01-01")
    assert "expected_interval_h" not in publish.turn_cadence()
    _declare(monkeypatch, effective_from="2026-01-01")
    assert publish.turn_cadence()["expected_interval_h"] == 3


def test_a_declared_machine_that_never_ran_is_null_not_missing(tmp_path, monkeypatch):
    """Declared-but-silent is a FACT worth publishing. Dropping the key would
    make a box that has never run indistinguishable from one nobody expected."""
    reports, _ = _patch(tmp_path, monkeypatch)
    _declare(monkeypatch)
    _receipt(reports / "receipts", "2026-08-01", "m01", turn="0300",
             machine="linux-rocm", at="2026-08-01T03:00:00+00:00")
    last = publish.turn_cadence()["last_by_machine"]
    assert last == {"windows-cuda": None,
                    "linux-rocm": "2026-08-01T03:00:00+00:00"}


def test_turns_and_divergence_ride_the_snapshot_only_when_present():
    """The page degrades fully without them: a feed built the old way carries
    neither key, and the page falls back to its legacy constants."""
    snap = publish.build_snapshot([], "2026-08-01T00:00:00+00:00", 3, 47.0)
    assert "turns" not in snap and "divergence" not in snap
    snap = publish.build_snapshot([], "2026-08-01T00:00:00+00:00", 3, 47.0,
                                  turns={"count": 61}, divergence=[])
    assert snap["turns"] == {"count": 61}
    # An EMPTY divergence list is absence, not an empty rendering slot.
    assert "divergence" not in snap


# ── 6. The page: copy sweep + graceful degradation ──────────────────────────

# The two places "night" legitimately survives, both deliberate:
#   * the sky is the VISITOR's clock (dawn/noon/dusk/night), nothing to do with
#     when the lab runs — retiring it would be a different, wrong change;
#   * two sentences that record the lab's own history without retconning it.
_NIGHT_ALLOWLIST = (
    "dawn, noon, dusk, night",                       # sky legend row
    "before July 2026 it counted nights",            # the counter's definition change
    "began as one machine's night shift",            # the lab's real history
)


def _visible_text(html: str) -> str:
    """Everything a reader can see: element text plus the meta descriptions.

    Strips <script>/<style> bodies and HTML comments so engineering notes and
    the sky-phase code (which legitimately says "night") aren't mistaken for
    copy, then removes the allowlisted phrases so what remains is only the
    night-shift framing this rename retired.
    """
    text = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.S | re.I)
    metas = " ".join(re.findall(r'<meta[^>]*content="([^"]*)"', html, flags=re.I))
    text = re.sub(r"<[^>]+>", " ", text) + " " + metas
    for allowed in _NIGHT_ALLOWLIST:
        text = text.replace(allowed, " ")
    return text


def test_no_night_shift_framing_survives_in_visible_copy():
    """The rename is one commit or it is nothing — a half-renamed page
    contradicts itself, telling a reader both that the lab keeps a night shift
    and that two machines take turns."""
    leftovers = re.findall(r"\b\w*(?:nightly|overnight|tonight|night)\w*\b",
                           _visible_text(WEB.read_text(encoding="utf-8")), re.I)
    assert leftovers == [], f"night-shift framing still visible: {leftovers}"


def test_the_concept_line_is_on_the_page():
    """The hero names the agents and names the gate.

    Until 2026-08-05 the page's load-bearing fact — that agents wrote every
    layer and design the experiments — lived in one sentence inside a
    ``<details>`` collapsed at the foot of the page, while every visible line
    attributed the work to "two home machines". A reader took that for a cron
    job. The machines are still named, one rung down: they take the turns.

    The gate assertion is the honesty half. Naming the agents without naming
    who promotes a result would overclaim, so the two travel together.
    """
    html = WEB.read_text(encoding="utf-8")
    assert "A fleet of AI agents wrote this instrument and keeps it running." in html
    assert "A human decides what earns a leaf." in html
    assert "Two home machines take the turns" in html
    for stale in ("A home machine keeps a night shift.",
                  "Two home machines tend one small lab in turns."):
        assert stale not in html, f"stale concept line on the page: {stale!r}"


def test_machine_marks_are_archive_only():
    """A lens engraving, not a badge: the mark belongs on the archive row and
    nowhere near the rail, the hero, or the legend."""
    html = WEB.read_text(encoding="utf-8")
    # One CSS rule, one JS class assignment — nothing else anywhere.
    assert html.count("arc-mach") == 2
    assert html.count("'arc-mach'") == 1
    # A row's ``machine`` is read exactly once in the whole page, and that read
    # is inside the archive's row builder. If a second reader appears, the mark
    # has escaped the archive and this needs a deliberate decision, not a patch.
    assert html.count("r.machine") == 3            # guard, textContent, title
    archive_block = html.split("function drawRunList", 1)[1] \
                        .split("// ── Helpers", 1)[0]
    assert archive_block.count("r.machine") == 3


def test_the_counter_falls_back_to_days_tended_without_a_turns_object():
    """Graceful degradation is in the source, not just in intent: both branches
    exist, and the legacy one is what a feed with no ``turns`` gets."""
    html = WEB.read_text(encoding="utf-8")
    assert 'id="m-runs-label">days tended<' in html      # the pre-feed default
    assert "runsLabel.textContent = 'turns'" in html
    assert "runsLabel.textContent = 'days tended'" in html
    # Legacy constants survive for a feed with no declared cadence.
    assert "4 * iv : 36" in html
    assert "2 * iv : 16" in html


def test_a_marked_row_wraps_on_phones_instead_of_overflowing():
    """The row was already at its element budget at phone width: adding the
    machine mark pushed it ~9px past a 390px viewport, so the page scrolled
    sideways. It wraps instead — nothing hidden, no evidence link truncated —
    and ONLY rows that carry a mark do, so a run with no recorded provenance
    keeps its single line exactly as before.
    """
    html = WEB.read_text(encoding="utf-8")
    assert "row.classList.add('has-mach')" in html
    narrow = html.split("@media (max-width:560px)", 1)[1].split("}\n\n", 1)[0]
    assert ".arc-row.has-mach { flex-wrap:wrap;" in narrow
    # Unscoped rules here would re-wrap the legacy rows too.
    assert ".arc-row {" not in narrow
    # The headline must be able to shrink below its content or the ellipsis
    # never fires and the row overflows again.
    assert "flex:1 1 auto; min-width:0;" in html


def test_the_chip_counts_turns_and_only_claims_both_machines_when_true():
    html = WEB.read_text(encoding="utf-8")
    assert "'×' + r.group_count + ' turns'" in html
    assert "' nights'" not in html
    assert "spansBoth ? ', on both machines' : ''" in html
