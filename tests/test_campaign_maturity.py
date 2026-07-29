"""Static safety contracts for the unattended campaign."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    pull = script.index("git pull --rebase")
    experiment = script.index("-m lab.cli next")
    assert worktree_guard < pull < experiment
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
