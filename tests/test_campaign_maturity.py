"""Safety contracts for the unattended campaign: static text pins plus a bash parse gate."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _script_body():
    """campaign.sh with comment-only lines blanked, for ordering assertions.

    These tests pin the order of RUNTIME steps but locate them with ``str.index``,
    which finds the first textual occurrence anywhere — including prose. b66a0e6
    added a comment explaining the ``git pull --rebase`` strand above the guards
    and turned the dirty-worktree ordering test red without changing any behavior.
    Blanking comments (rather than dropping the lines) keeps every offset's
    relative order intact while making the pins mean what they say.
    """
    text = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    return "\n".join(
        "" if line.lstrip().startswith("#") else line for line in text.splitlines()
    )


def _loop_body():
    """The pass loop only — the region the ordering pins below actually describe.

    The guards, the pull, the experiment, the verify gate and the staging all run
    inside ``while :; do``. Helper functions defined above the loop legitimately
    reuse the same commands (``resolve_by_regeneration`` re-stages the regenerated
    feeds), so a whole-file ``str.index`` finds the helper's copy instead and the
    pins stop meaning "the order the steps run in".
    """
    body = _script_body()
    return body[body.index("while :; do"):]


def _working_bash():
    """Locate a bash that actually runs (the WSL stub on Windows resolves but errors)."""
    exe = shutil.which("bash")
    if exe is None:
        return None
    try:
        probe = subprocess.run([exe, "--version"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if probe.returncode != 0 or b"bash" not in probe.stdout.lower():
        return None
    return exe


def test_campaign_script_parses_under_bash():
    exe = _working_bash()
    if exe is None:
        pytest.skip("no working bash on PATH")
    source = (ROOT / "scripts" / "campaign.sh").read_bytes()
    # Feed the script on stdin instead of as a path argument so the same test
    # runs under Git Bash and WSL, whose filesystem roots disagree on C:\ paths.
    proc = subprocess.run([exe, "-n"], input=source, capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")


def test_graceful_stop_survives_service_restart_policy():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    service = (ROOT / "scripts" / "windowsill-campaign.service").read_text(
        encoding="utf-8"
    )
    assert 'rm -f "$STOP"' not in script
    assert '[ -f "$STOP" ]' in script
    assert "Restart=on-failure" in service
    assert "Restart=always" not in service


def test_campaign_persists_counter_before_running_each_seed():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    loop = _loop_body()
    state_write = loop.index('if ! persist_counter "$next_iter"; then')
    experiment = loop.index("-m lab.cli next")
    assert "LAB_CAMPAIGN_STATE" in script
    assert state_write < experiment
    assert 'mktemp "$STATE_DIR/.${state_base}.tmp.XXXXXX"' in script
    assert 'mv -f -- "$state_tmp" "$STATE"' in script
    assert 'state_tmp="${STATE}.$$"' not in script
    persist_failure = loop.index(
        "campaign: counter persistence failed; no experiment was launched"
    )
    assert state_write < persist_failure < experiment
    assert "exit 1" in loop[persist_failure:experiment]
    assert "passes=$((passes+1))" in script


def test_campaign_stages_both_public_feeds():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    assert "git add -- pot.json physics-latest.json" in script


def test_campaign_refuses_a_preexisting_index_before_experiment():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    loop = _loop_body()
    index_guard = loop.index("git diff --cached --quiet -- 2>/dev/null")
    experiment = loop.index("-m lab.cli next")
    assert index_guard < experiment
    assert "pre-existing staged changes; refusing to run or alter the index" in script


def test_campaign_refuses_a_dirty_tracked_worktree_before_pull_or_experiment():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    body, loop = _script_body(), _loop_body()
    # The pull runs through safe_pull_rebase(), defined above the loop, so pin the
    # CALL SITE — that is the step the guards have to precede. Searching from the
    # guard's offset means a reordering raises here rather than failing an assert.
    worktree_guard = loop.index("git diff --quiet -- 2>/dev/null")
    pull = loop.index("elif ! safe_pull_rebase", worktree_guard)
    experiment = loop.index("-m lab.cli next")
    assert worktree_guard < pull < experiment
    assert "pre-existing tracked worktree changes; refusing to pull or run" in script
    assert "git pull --rebase --autostash" not in script
    # ...and the loop must never reach git pull directly: the helper owns the
    # conflict path, so exactly one invocation exists and it lives in the helper.
    assert body.count("git pull --rebase") == 1
    assert body.index("safe_pull_rebase(){") < body.index("git pull --rebase")
    assert "git pull --rebase" not in loop


def test_campaign_git_operations_are_limited_to_owned_paths():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    owned = "pot.json physics-latest.json reports/"
    assert f"git diff --cached --quiet -- {owned}" in script
    assert f"git reset -q -- {owned}" in script
    assert "git reset -q 2>/dev/null" not in script
    assert "git commit -q --only" in script
    assert f"-- {owned} >/dev/null" in script


def test_campaign_verify_gates_publication_between_run_and_staging():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    loop = _loop_body()
    assert "-m lab.cli verify" in script
    run = loop.index("-m lab.cli next")
    gate = loop.index("-m lab.cli verify")
    stage = loop.index("git add -- pot.json physics-latest.json")
    assert run < gate < stage
    assert "verify failed; publishing withheld" in script


def test_campaign_withheld_pass_restores_owned_paths_for_the_next_pass():
    """BOTH ways a pass can decline route through one helper since AUTO-F3, so this
    follows the call rather than an inlined copy of the restore. Two inlined copies
    is how the two branches drifted apart in the first place: a failed `verify`
    restored and withheld, a failed `lab next` did neither."""
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    loop = _loop_body()
    restore = "git checkout -q -- pot.json physics-latest.json reports/"
    assert "withhold_pass(){" in script
    assert script.count(restore) == 1, "the restore belongs to withhold_pass alone"
    stage = loop.index("git add -- pot.json physics-latest.json")
    for reason in ("experiment failed; publishing withheld",
                   "verify failed; publishing withheld"):
        logged = loop.index(reason)
        called = loop.index("withhold_pass", logged)
        assert logged < called < stage, f"{reason!r} does not reach withhold_pass"


def test_campaign_experiment_failure_never_reaches_the_publishing_path():
    """AUTO-F3, pinned as text so the masquerade cannot come back by edit.

    A failed `lab next` used to log "refreshing existing feed only", leave
    publishable=1, and commit under `campaign: pass N <date> seed=S` — a subject
    indistinguishable from a success, in a ledger the pass counter is recovered from.
    """
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    assert "refreshing existing feed only" not in script
    assert "experiment failed; publishing withheld" in script


def test_campaign_commit_message_dates_in_local_time():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    assert 'pass_day="$(date +%F)"' in script
    assert '"campaign: pass $iter $pass_day seed=$seed"' in script
    assert "$(date -u +%F) seed=$seed" not in script


# ── 4/day interleaved cadence (Win 00/06/12/18 ↔ Loam 03/09/15/21 local) ─────

def test_service_sets_interleaved_cadence():
    service = (ROOT / "scripts" / "windowsill-campaign.service").read_text(
        encoding="utf-8"
    )
    assert "LAB_CAMPAIGN_INTERVAL=21600" in service
    assert "LAB_CAMPAIGN_HOURS=3 9 15 21" in service


def test_campaign_anchors_sleep_to_the_clock_not_accumulated_interval():
    """`sleep INTERVAL` drifts later by each pass's walltime; the anchored
    next_wake_seconds recomputes against the wall clock. Plain interval sleep
    stays as the fallback when LAB_CAMPAIGN_HOURS is unset."""
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    assert "next_wake_seconds" in script
    assert "LAB_CAMPAIGN_HOURS" in script
    assert 'sleep "$INTERVAL"' in script            # fallback path survives
    # The anchored branch is guarded on HOURS being configured.
    assert '-n "$HOURS"' in script


def _extract_next_wake(script: str) -> str:
    start = script.index("next_wake_seconds()")
    end = script.index("\n}", start) + 2
    return script[start:end]


def _run_next_wake(exe: str, fn: str, now_epoch: int, hours: str) -> int:
    import os
    proc = subprocess.run(
        [exe, "-c", f'{fn}\nNOW_EPOCH={now_epoch} next_wake_seconds "{hours}"'],
        capture_output=True, timeout=60,
        env={**os.environ, "TZ": "UTC"},
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return int(proc.stdout.strip())


def test_next_wake_seconds_targets_the_next_listed_hour():
    exe = _working_bash()
    if exe is None:
        pytest.skip("no working bash on PATH")
    from datetime import datetime, timezone
    fn = _extract_next_wake(
        (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    )

    def epoch(h, m=0):
        return int(datetime(2026, 1, 1, h, m, tzinfo=timezone.utc).timestamp())

    # 04:00 → next listed hour is 09:00 (5h), not yesterday's drift.
    assert _run_next_wake(exe, fn, epoch(4), "3 9 15 21") == 5 * 3600
    # 23:30 → wraps to tomorrow 03:00 (3.5h).
    assert _run_next_wake(exe, fn, epoch(23, 30), "3 9 15 21") == 12600
    # Exactly ON a boundary → the NEXT boundary (a pass never re-fires its own slot).
    assert _run_next_wake(exe, fn, epoch(3), "3 9 15 21") == 6 * 3600


# ── The survey lane's units (loam only; win runs the campaign side) ──────────
#
# These were installed-only until 2026-08-18, so nothing could compare the
# machine against the repo — the exact gap Class 2 of the estate's bug taxonomy
# names, and the one that let LAB_CAMPAIGN_HOURS sit unset for weeks. Committing
# them lets groundskeeper's `units` check diff installed against committed.

def test_hunt_service_runs_the_versioned_script():
    """The slot script lived loose in ~/.lab until a stale glob in it stranded
    graded receipts unnoticed. The unit must point at the tested copy."""
    service = (ROOT / "scripts" / "windowsill-hunt.service").read_text(encoding="utf-8")
    assert "projects/windowsill-lab/scripts/a05-hunt-slot.sh" in service
    assert "%h/.lab/a05-hunt-slot.sh" not in service


def test_hunt_timer_fires_on_loams_interleave_slots():
    """Loam owns 03/09/15/21; win owns 00/06/12/18. The +2min offset lets the
    campaign pass claim the slot first — the two lanes coexist, CPU vs GPU."""
    timer = (ROOT / "scripts" / "windowsill-hunt.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 03,09,15,21:02:00" in timer


def test_hunt_slot_script_is_executable_and_gated():
    """The three behaviours that were production failures on 2026-08-17/18."""
    slot = (ROOT / "scripts" / "a05-hunt-slot.sh").read_text(encoding="utf-8")
    assert 'sed -n \'s|^receipt -> ||p\'' in slot, "stage what the runner printed"
    assert '"reports/hunts/dossiers/${stem}"-tic*.html' in slot, "dossier travels with receipt"
    assert "restore_pot" in slot and "git add -- pot.json" in slot, "the pot's two rules"
    assert os.access(ROOT / "scripts" / "a05-hunt-slot.sh", os.X_OK)


def test_campaign_runs_the_test_suite_after_publishing_and_never_gates_on_it():
    """Loam's twin of the nightly's pytest step (2026-09-04).

    Same contract as ``test_nightly_templates_test_after_publishing_and_never_gate_on_it``:
    the suite runs LAST in a pass, only on this box's one scheduled turn per UTC
    day (``--if-due`` — the loop's default interval mode wakes every 30 minutes,
    which the window alone would not survive), and a red suite produces a log
    line and nothing else. It must never reach ``withhold_pass``: the science
    pipeline's gates are ``lab next`` and ``lab verify``, and a failing unit test
    is not grounds to unpublish a run that graded clean.
    """
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    loop = _loop_body()
    assert "-m lab.cli selftest --if-due" in script
    stage = loop.index("git add -- pot.json physics-latest.json")
    selftest = loop.index("-m lab.cli selftest")
    assert loop.index("-m lab.cli next") < loop.index("-m lab.cli verify") < stage < selftest
    tail = loop[selftest:loop.index("MAX_ITERS")]
    assert "withhold_pass" not in tail
    assert "git checkout" not in tail
    assert "publish above stands" in tail


def test_campaign_commits_the_selftest_receipt_and_only_that():
    """Loam's twin of the nightly's receipt commit (2026-09-04).

    The feed's `tests` block is a per-machine map derived from the COMMITTED
    receipts, so a verdict that stays in the worktree is a verdict nothing
    reads — and worse than that, `withhold_pass` ends in
    `git clean -qfd -- reports/`, so the next refused pass DELETES an untracked
    selftest receipt. The step therefore files its own commit, scoped to
    reports/receipts and nothing else: this runs after the science commit and a
    commit here that could reach pot.json would be a second, ungraded publisher
    of the feed sitting in the loop's tail.
    """
    loop = _loop_body()
    tail = loop[loop.index("-m lab.cli selftest"):loop.index("MAX_ITERS")]
    # The prose in the tail names pot.json (it explains WHY the receipt has to be
    # committed), so the scoping assertions below read the COMMANDS.
    commands = "\n".join(line for line in tail.splitlines()
                          if not line.strip().startswith("#"))
    # Scoped to the receipts this step writes, never to the whole directory:
    # a torn artifact left by a partly-failed pass must not be swept onto the
    # ledger under a "selftest:" subject.
    assert "git add -- 'reports/receipts/selftest-*.json'" in commands
    assert 'git commit -q --only -m "selftest:' in commands
    assert "-- 'reports/receipts/selftest-*.json'" in commands
    assert "pot.json" not in commands and "physics-latest.json" not in commands
    assert "git add -A" not in commands
    # Still not a gate, and still not a way to undo a graded run.
    assert "withhold_pass" not in commands
    assert "git checkout" not in commands
    assert "git clean" not in commands


def test_campaign_unstages_a_receipt_it_could_not_commit():
    """The lane must not be able to wedge itself. See
    tests/test_campaign_pass_gate.py::test_a_receipt_commit_that_fails_leaves_the_lane_runnable
    for the driven proof; this pins the line so a refactor cannot quietly drop it.
    """
    text = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    assert "git reset -q -- 'reports/receipts/selftest-*.json'" in text
    _, _, tail = text.partition("git reset -q -- 'reports/receipts/selftest-*.json'")
    assert "could not be committed" in tail[:400], tail[:400]


def test_campaign_honours_dry_before_committing_the_receipt():
    """DRY is documented as "skip commit/push"; the receipt step must obey it."""
    text = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    dry = text.index('if [ -n "${LAB_CAMPAIGN_DRY:-}" ]; then\n'
                     '      log "campaign: pass $iter \u2014 DRY, selftest receipt')
    add = text.index("git add -- 'reports/receipts/selftest-*.json'")
    assert dry < add, "the DRY guard must gate the receipt staging, not follow it"
