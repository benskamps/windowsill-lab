"""Safety contracts for the unattended campaign: static text pins plus a bash parse gate."""
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
    state_write = script.index('if ! persist_counter "$next_iter"; then')
    experiment = script.index("-m lab.cli next")
    assert "LAB_CAMPAIGN_STATE" in script
    assert state_write < experiment
    assert 'mktemp "$STATE_DIR/.${state_base}.tmp.XXXXXX"' in script
    assert 'mv -f -- "$state_tmp" "$STATE"' in script
    assert 'state_tmp="${STATE}.$$"' not in script
    persist_failure = script.index(
        "campaign: counter persistence failed; no experiment was launched"
    )
    assert state_write < persist_failure < experiment
    assert "exit 1" in script[persist_failure:experiment]
    assert "passes=$((passes+1))" in script


def test_campaign_stages_both_public_feeds():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    assert "git add -- pot.json physics-latest.json" in script


def test_campaign_refuses_a_preexisting_index_before_experiment():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    index_guard = script.index("git diff --cached --quiet -- 2>/dev/null")
    experiment = script.index("-m lab.cli next")
    assert index_guard < experiment
    assert "pre-existing staged changes; refusing to run or alter the index" in script


def test_campaign_refuses_a_dirty_tracked_worktree_before_pull_or_experiment():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    worktree_guard = script.index("git diff --quiet -- 2>/dev/null")
    # The pass flow pulls via safe_pull_rebase (the loud wrapper that aborts a
    # conflicted rebase instead of stranding the clone). Its BODY — the only
    # place the raw `git pull --rebase` runs — is defined before the loop, so
    # the ordering that matters is guard < CALL SITE < experiment.
    # (`.index` with a start offset raises if the call site is not after the
    # guard, so a reordering fails loudly, not silently.)
    pull_call = script.index("elif ! safe_pull_rebase", worktree_guard)
    experiment = script.index("-m lab.cli next")
    assert worktree_guard < pull_call < experiment
    assert "pre-existing tracked worktree changes; refusing to pull or run" in script
    assert "git pull --rebase --autostash" not in script


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
    assert "-m lab.cli verify" in script
    run = script.index("-m lab.cli next")
    gate = script.index("-m lab.cli verify")
    stage = script.index("git add -- pot.json physics-latest.json")
    assert run < gate < stage
    assert "verify failed; publishing withheld" in script


def test_campaign_withheld_pass_restores_owned_paths_for_the_next_pass():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    restore = "git checkout -q -- pot.json physics-latest.json reports/"
    assert restore in script
    withheld = script.index("verify failed; publishing withheld")
    stage = script.index("git add -- pot.json physics-latest.json")
    assert withheld < script.index(restore) < stage


def test_campaign_commit_message_dates_in_local_time():
    script = (ROOT / "scripts" / "campaign.sh").read_text(encoding="utf-8")
    assert 'pass_day="$(date +%F)"' in script
    assert '"campaign: pass $iter $pass_day seed=$seed"' in script
    assert "$(date -u +%F) seed=$seed" not in script
