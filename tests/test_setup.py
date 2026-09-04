"""`lab setup` — the generated artifacts and pre-flight are pure + testable."""
import shutil
import subprocess
from pathlib import Path

import pytest

from lab import setup
from lab.publish import REPO_ROOT


def test_nightly_script_is_runnable_and_self_contained():
    sh = setup.nightly_script()
    assert sh.startswith("#!/usr/bin/env bash")
    assert str(REPO_ROOT) in sh                    # cd's into the repo
    # The nightly advances the frontier via the milestone-aware scheduler `lab next`
    # (swapped from `lab run` 2026-07-05), then RE-GRADES with `lab verify` before
    # publishing. The `lab publish` fallback on failure was removed 2026-08-22
    # (AUTO-F7): it refreshed the feed and let the block below commit a "nightly:"
    # receipt for an experiment that had just failed.
    assert "lab.cli next" in sh and "lab.cli verify" in sh
    assert "lab.cli publish" not in sh
    assert "git push" in sh                        # it pushes the feed
    assert "git diff --cached --quiet" in sh       # commits only on change
    # The whole reports/ tree is staged so every permanent per-run report lands.
    assert "reports/" in sh
    assert "git add pot.json physics-latest.json" in sh
    # Guard: nightly publishes ONLY from main. If the clone is left on a feature
    # branch, it must refuse — otherwise the public feed gets stranded.
    assert 'abbrev-ref HEAD' in sh
    assert '!= "main"' in sh
    assert "REFUSING" in sh
    # Sync before pushing: a bare push from a stale main is rejected the moment
    # remote advances (a merged PR, the mirror bot), which stranded the feed for
    # days in June 2026. The nightly must rebase onto remote, not just push.
    assert "git pull --rebase" in sh


def test_units_reference_the_nightly_script_and_schedule():
    assert "ExecStart=" in setup.service_unit()
    assert str(setup.NIGHTLY_SH) in setup.service_unit()
    assert "OnCalendar=*-*-* 04:30:00" in setup.timer_unit(at="04:30:00")
    assert "WantedBy=timers.target" in setup.timer_unit()


def test_cron_line_points_at_the_nightly_script():
    line = setup.cron_line(at_hour=5)
    assert line.startswith("0 5 * * *")
    assert str(setup.NIGHTLY_SH) in line


def test_health_checks_report_python_and_remote():
    names = {c["name"] for c in setup.health_checks()}
    assert {"python", "git remote", "compute", "feed writable"} <= names
    for c in setup.health_checks():
        assert set(c) == {"name", "ok", "detail"}


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    sentinel = tmp_path / "scripts" / "nightly.sh"
    monkeypatch.setattr(setup, "NIGHTLY_SH", sentinel)
    plan = setup.install(dry_run=True)
    assert not sentinel.exists()
    assert plan["method"] in ("systemd", "cron", "schtasks")


# ── Windows nightly (Task Scheduler) — pure generators are platform-neutral ──
def test_nightly_ps1_is_runnable_and_self_contained():
    ps = setup.nightly_ps1()
    assert str(REPO_ROOT) in ps                        # cd's into the repo
    # As above: `lab next`, then the `lab verify` re-grade. The publish-on-failure
    # fallback is gone (AUTO-F7, 2026-08-22).
    assert "lab.cli next" in ps and "lab.cli verify" in ps
    assert "lab.cli publish" not in ps
    assert "git push" in ps                            # it pushes the feed
    assert "git diff --cached --quiet" in ps           # commits only on change
    assert "reports/" in ps                            # stages the whole reports/ tree
    assert "git add pot.json physics-latest.json" in ps
    # Guard: nightly publishes ONLY from main (same as the bash analog).
    assert "abbrev-ref HEAD" in ps
    assert "-ne 'main'" in ps
    assert "REFUSING" in ps
    # Same sync-before-push guard as the bash analog (the June 2026 stranding fix).
    assert "git pull --rebase" in ps
    assert "push failed after 4 attempts" in ps


# ── nightly hardening: index safety + independent nightly seeds ─────────────
# The defect being fixed: the nightly committed with a bare `git commit`, so
# anything pre-staged in the clone at 03:00 (agents work in it — IN-USE.md is a
# live convention) shipped to main under a "nightly:" message. campaign.sh got
# the pre-staged refusal + --only pathspec in PR #66; the nightly templates
# did not. NOTE: the installed scripts/nightly.ps1 is gitignored — these
# templates only take effect after `lab setup` is re-run on the box.

def test_nightly_sh_refuses_prestaged_index_before_running():
    sh = setup.nightly_script()
    guard = sh.index("git diff --cached --quiet")
    assert "staged" in sh and "REFUSING" in sh[:sh.index("lab.cli next")]
    # The refusal gate sits BEFORE the experiment/publish — a dirty index means
    # no run, no sweep, exit 0 (skip, logged), same semantics as campaign.sh.
    assert guard < sh.index("lab.cli next")


def test_nightly_ps1_refuses_prestaged_index_before_running():
    ps = setup.nightly_ps1()
    guard = ps.index("git diff --cached --quiet")
    assert guard < ps.index("lab.cli next")
    assert "staged" in ps


def test_nightly_templates_commit_only_campaign_paths():
    """`--only` + explicit pathspec: even if something slips into the index
    mid-run, the nightly commit can only ever carry the feed + reports tree."""
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        assert "git commit" in script
        assert "--only" in script
        assert "-- pot.json physics-latest.json reports/" in script


def test_nightly_templates_derive_seed_from_utc_date():
    """The bash nightly keeps its UTC-date seed (one pass/night). The Windows
    nightly fires 4×/day, so its seed carries the HOUR — each of the four daily
    passes is an independent sample instead of the same-day deterministic
    repeat. (A retry within the same hour still repeats — documented in the
    template.)"""
    sh = setup.nightly_script()
    assert "--seed" in sh and 'date -u +%Y%m%d' in sh
    ps = setup.nightly_ps1()
    assert "--seed" in ps and "yyyyMMddHH" in ps


def test_task_xml_is_wellformed_and_runs_the_nightly():
    import xml.etree.ElementTree as ET
    xml = setup.task_xml()
    root = ET.fromstring(xml.encode("utf-16"))         # well-formed (declared UTF-16)
    # 4 passes/device/day: four explicit daily CalendarTriggers (legible in the
    # Task Scheduler UI), interleaved with Loam's 03/09/15/21 local turns.
    triggers = [el for el in root.iter()
                if el.tag.endswith("}CalendarTrigger")]
    assert len(triggers) == 4
    for hh in ("00:00:00", "06:00:00", "12:00:00", "18:00:00"):
        assert f"2026-01-01T{hh}" in xml
    # ExecutionTimeLimit is an anti-wedge watchdog, NOT overlap prevention: on
    # 2026-08-02 the old PT2H limit killed the wrapper mid-M02 while the python
    # child survived and finished, orphaning its logging. Overlap is the run
    # lock's job (cli.next_run_lock); the watchdog sits past the longest honest
    # milestone so it only fires on a genuinely wedged wrapper.
    assert "<ExecutionTimeLimit>PT12H</ExecutionTimeLimit>" in xml
    assert str(setup.NIGHTLY_PS1) in xml               # the action runs nightly.ps1
    assert "powershell.exe" in xml
    # Resilience: catch a missed start, and wake a sleeping box so the
    # windowsill grows even when nobody's at the machine.
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "<WakeToRun>true</WakeToRun>" in xml
    assert "<RestartOnFailure>" in xml
    assert "-NonInteractive -WindowStyle Hidden" in xml


def test_task_xml_accepts_custom_times():
    xml = setup.task_xml(times=("04:30:00",))
    assert "2026-01-01T04:30:00" in xml
    assert xml.count("<CalendarTrigger>") == 1


def test_windows_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "NIGHTLY_PS1", tmp_path / "scripts" / "nightly.ps1")
    monkeypatch.setattr(setup, "TASK_XML", tmp_path / "scripts" / "task.xml")
    plan = setup._install_windows(dry_run=True)
    assert not (tmp_path / "scripts" / "nightly.ps1").exists()
    assert plan["method"] == "schtasks"


# ── conflicted-pull recovery: the nightly must never strand the clone ───────
# THE OUTAGE (three times in a fortnight; 66h on 2026-08-08..11): the push-retry
# loop called `git pull --rebase --autostash` with no failure path. The nightly
# commits DERIVED files both boxes regenerate, so that pull conflicts routinely,
# and git left the clone detached mid-rebase with unmerged files. Attempts 2-4
# could then only die on "Pulling is not possible because you have unmerged
# files" → "ERROR: push failed after 4 attempts" → every LATER nightly hit the
# 08-05 STRANDED guard and exited 1, forever, until a human repaired the clone.
#
# These tests run the recovery helpers against a REAL conflicted rebase rather
# than grepping the template, because the whole class of bug here is a template
# that reads correct and behaves wrong.

def _working_bash():
    """A bash that can actually launch. On Windows ``which bash`` finds the WSL
    stub in System32, which errors with ``execvpe(/bin/bash) failed`` when no
    distro is installed — so probe, don't trust the PATH hit."""
    candidates = [shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe",
                  "/bin/bash"]
    for cand in candidates:
        if not cand or not Path(cand).exists():
            continue
        try:
            probe = subprocess.run([cand, "-c", "echo ok"],
                                   capture_output=True, text=True, timeout=20)
        except OSError:
            continue
        if probe.returncode == 0 and "ok" in probe.stdout:
            return cand
    return None


BASH = _working_bash()
PWSH = shutil.which("pwsh")


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(cwd), capture_output=True, text=True)


def _diverged_clone(tmp_path):
    """A clone whose local commit conflicts with origin on the same file —
    the exact shape of two boxes regenerating pot.json in the same window."""
    origin, win, loam = (tmp_path / n for n in ("origin.git", "win", "loam"))
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    subprocess.run(["git", "clone", str(origin), str(win)],
                   capture_output=True, check=True)
    # Cloning an EMPTY repo leaves the local branch at whatever the client's
    # init.defaultBranch says (master on plenty of boxes), so name it here
    # rather than assume — otherwise the push below dies on "src refspec main
    # does not match any" only on machines configured differently from mine.
    _git(win, "checkout", "-B", "main")
    (win / "pot.json").write_text("base\n", encoding="utf-8")
    _git(win, "add", "-A")
    _git(win, "commit", "-m", "base")
    _git(win, "push", "-u", "origin", "main")

    subprocess.run(["git", "clone", str(origin), str(loam)],
                   capture_output=True, check=True)
    (loam / "pot.json").write_text("loam turn\n", encoding="utf-8")
    _git(loam, "add", "-A")
    _git(loam, "commit", "-m", "loam nightly")
    _git(loam, "push")

    (win / "pot.json").write_text("win turn\n", encoding="utf-8")   # same file
    _git(win, "add", "-A")
    _git(win, "commit", "-m", "win nightly")
    return win


def _assert_clone_is_clean(clone: Path):
    """The STRANDED guard's own predicate, asserted from the other side: this is
    what the next nightly will see when it boots."""
    branch = _git(clone, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert branch == "main", f"clone left on '{branch}' — the next nightly is wedged"
    assert not (clone / ".git" / "rebase-merge").exists()
    assert not (clone / ".git" / "rebase-apply").exists()
    assert _git(clone, "ls-files", "--unmerged").stdout.strip() == ""


@pytest.mark.skipif(BASH is None, reason="no working bash on this box")
def test_unwedge_sh_aborts_a_real_conflicted_rebase(tmp_path):
    """sync_main returns 2 (conflicted-but-cleaned) and the clone comes out on
    main with no rebase in flight — so attempt 2 is a real attempt, not a
    guaranteed 'unmerged files' death."""
    win = _diverged_clone(tmp_path)
    script = tmp_path / "drive.sh"
    script.write_text(
        setup.UNWEDGE_SH + '\nsync_main; echo "RC=$?"\n', encoding="utf-8")
    out = subprocess.run([BASH, str(script)], cwd=str(win),
                         capture_output=True, text=True)
    assert "RC=2" in out.stdout, out.stdout + out.stderr
    assert "rebase --abort" in out.stdout          # it says what it did
    _assert_clone_is_clean(win)


@pytest.mark.skipif(BASH is None, reason="no working bash on this box")
def test_unwedge_sh_reports_a_clean_pull_as_success(tmp_path):
    """The recovery must not fire on the happy path: an ordinary fast-forward
    pull still returns 0 and aborts nothing."""
    win = _diverged_clone(tmp_path)
    _git(win, "reset", "--hard", "HEAD~1")         # drop the conflicting commit
    script = tmp_path / "drive.sh"
    script.write_text(
        setup.UNWEDGE_SH + '\nsync_main; echo "RC=$?"\n', encoding="utf-8")
    out = subprocess.run([BASH, str(script)], cwd=str(win),
                         capture_output=True, text=True)
    assert "RC=0" in out.stdout, out.stdout + out.stderr
    assert "abort" not in out.stdout
    assert (win / "pot.json").read_text(encoding="utf-8") == "loam turn\n"


@pytest.mark.skipif(PWSH is None, reason="pwsh unavailable")
def test_unwedge_ps1_aborts_a_real_conflicted_rebase(tmp_path):
    """The PowerShell twin — and the one that actually matters, because the box
    that stranded three times runs the .ps1 under Task Scheduler."""
    win = _diverged_clone(tmp_path)
    log = tmp_path / "nightly.log"
    script = tmp_path / "drive.ps1"
    # The two log shims the real nightly defines above the helper, verbatim.
    preamble = (
        "$log = '" + log.as_posix() + "'\n"
        'function Log($m) { Add-Content -LiteralPath $log -Value $m -Encoding utf8 }\n'
        'filter LogCmd { Log "$_" }\n'
    )
    script.write_text(
        preamble + setup.UNWEDGE_PS1
        + '\n$rc = @(Sync-Main)[-1]\nWrite-Output "RC=$rc"\n',
        encoding="utf-8")
    out = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(script)],
        cwd=str(win), capture_output=True, text=True)
    assert "RC=2" in out.stdout, out.stdout + out.stderr
    assert "rebase --abort" in log.read_text(encoding="utf-8")
    _assert_clone_is_clean(win)


def test_nightly_templates_abort_a_conflicted_pull_before_retrying():
    """Structural lock (always on, even where no shell is available): both
    templates route EVERY pull through the aborting helper — a bare
    `git pull --rebase` anywhere in the script is the bug coming back."""
    sh, ps = setup.nightly_script(), setup.nightly_ps1()
    assert setup.UNWEDGE_SH in sh and setup.UNWEDGE_PS1 in ps
    # The only literal `git pull --rebase` in each script is the one inside the
    # helper; the retry loop and the pre-work sync both call the helper.
    assert sh.count("git pull --rebase") == 1
    assert ps.count("git pull --rebase") == 1
    assert sh.count("sync_main") >= 3          # helper def + pre-work + retry
    assert ps.count("Sync-Main") >= 3
    for script, abort in ((sh, "git rebase --abort"), (ps, "git rebase --abort")):
        assert abort in script


def test_nightly_templates_give_up_loudly_but_clean_on_a_second_conflict():
    """The 2026-08-05 contract survives: a genuine divergence is an OUTAGE, so
    the run still ends loud and non-zero. What changed is WHERE it leaves the
    clone — clean on main, so the next nightly is not born wedged."""
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        assert "conflicted twice" in script
        assert "CLEAN on main" in script
        assert "push failed after 4 attempts (clone left clean on main)" in script
    assert "exit 1" in setup.nightly_script()
    assert "exit 1" in setup.nightly_ps1()


# ── the generated scripts must actually PARSE ───────────────────────────────
# scripts/nightly.* are gitignored generated artifacts: nothing lints them, and
# a syntax error only surfaces at 00:00 as a silent no-run. Both templates grew
# real control flow (functions, a retry loop with a conflict counter), so parse
# them here — cheap, and it catches an escaping slip in the f-string/token
# templates that every substring assertion above would happily pass.

@pytest.mark.skipif(BASH is None, reason="no working bash on this box")
def test_generated_nightly_sh_parses(tmp_path):
    script = tmp_path / "nightly.sh"
    script.write_text(setup.nightly_script(), encoding="utf-8", newline="\n")
    out = subprocess.run([BASH, "-n", str(script)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


@pytest.mark.skipif(PWSH is None, reason="pwsh unavailable")
def test_generated_nightly_ps1_parses(tmp_path):
    script = tmp_path / "nightly.ps1"
    script.write_text(setup.nightly_ps1(), encoding="utf-8")
    checker = tmp_path / "check.ps1"
    checker.write_text(
        "$errs = $null\n"
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script.as_posix()}', [ref]$null, [ref]$errs)\n"
        "if ($errs) { $errs | ForEach-Object { Write-Output $_.Message }; exit 1 }\n",
        encoding="utf-8")
    out = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(checker)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


# ── the pytest step (2026-09-04) ─────────────────────────────────────────────
# Neither nightly ran the test suite at all until this landed: `lab next`, then
# `lab verify`, then commit. The only automated pytest anywhere was CI on push,
# and pot.json carried no test status, so the estate had to read "a box published
# a receipt" as "the tests ran". These pin the step into both templates and pin
# the two properties that make it safe to have there.

def test_nightly_templates_run_the_test_suite_once_a_day():
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        assert "lab.cli selftest" in script
        # --if-due, never a bare `selftest`: the cadence rule lives in ONE place
        # (lab/selftest.py) so the two templates cannot drift into two answers,
        # and so a 30-minute campaign interval cannot run the suite 12x a day.
        assert "selftest --if-due" in script


def test_nightly_templates_test_after_publishing_and_never_gate_on_it():
    """A red suite must be RECORDED, never allowed to revert a good science run.

    The science pipeline has its own gate (`lab verify`, which withholds). This
    is a different signal on a different question, so it runs last and its exit
    status only ever produces a log line.
    """
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        run = script.index("lab.cli next")
        verify = script.index("lab.cli verify")
        commit = script.index("git commit")
        selftest = script.index("lab.cli selftest")
        assert run < verify < commit < selftest
        # Nothing between the selftest and the end of the script may exit
        # non-zero or undo the publish — the tail is a log line and nothing else.
        tail = script[selftest:]
        assert "exit 1" not in tail
        assert "git checkout" not in tail and "Restore-CampaignPaths" not in tail
        assert "the publish above stands" in tail


def test_nightly_templates_commit_the_selftest_receipt():
    """The verdict has to LEAVE THE BOX, or the feed cannot carry it.

    pot.json's `tests` block is a PER-MACHINE map derived from the committed
    receipts in reports/receipts/ — the same shape and the same source as
    turns.last_by_machine. That shape exists because the first cut published one
    slot filled from this box's ~/.lab/selftest-latest.json, and both machines
    publish the same feed: one box's red suite was overwritten by the other's
    green within hours.

    So a receipt that is never committed is a verdict nothing reads. Nothing
    else in either script stages it — the `git add -A reports/` ran before the
    selftest step, and a refused run restores reports/ out from under it — which
    is why the step files its own commit.
    """
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        tail = script[script.index("lab.cli selftest"):]
        # The prose in the tail names pot.json (it explains WHY the receipt has
        # to be committed), so the scoping assertions below read the COMMANDS.
        commands = "\n".join(line for line in tail.splitlines()
                              if not line.strip().startswith("#"))
        # Scoped to the receipts this step writes, never to the whole
        # directory: a torn artifact left by a partly-failed run must not be
        # swept onto the ledger under a "selftest:" subject.
        assert "git add -- 'reports/receipts/selftest-*.json'" in commands
        assert "git commit" in commands
        assert "-- 'reports/receipts/selftest-*.json'" in commands
        assert "-- reports/receipts\n" not in commands
        # Scoped to the receipts directory and nothing else: this runs after the
        # science commit, and a commit here that could reach pot.json would be a
        # second, ungraded publisher of the feed sitting in the script's tail.
        assert "pot.json" not in commands
        assert "physics-latest.json" not in commands
        assert "git add -A" not in commands
        # ...and it still cannot fail the run. RestartOnFailure re-runs the whole
        # nightly twice, five minutes apart, on a non-zero exit.
        assert "exit 1" not in commands


def test_nightly_templates_unstage_a_receipt_they_could_not_commit():
    """Both nightlies REFUSE a pre-loaded index at the top and stop (bash exits,
    PowerShell exits 0 with "skipped: staged changes present"). The selftest step
    runs `git add` before its commit, so a commit that fails once would leave the
    index loaded and turn every later night into a silent no-op that still
    reports success. Reset on the failure path, exactly as the science commit
    does.
    """
    for script in (setup.nightly_script(), setup.nightly_ps1()):
        assert "git reset -q -- 'reports/receipts/selftest-*.json'" in script, script[:200]
        # ...and it sits on the FAILURE branch, never in the happy path.
        head, _, tail = script.partition(
            "git reset -q -- 'reports/receipts/selftest-*.json'")
        assert "could not be committed" in tail[:400], tail[:400]
