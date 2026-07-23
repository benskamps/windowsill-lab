#!/usr/bin/env bash
# campaign.sh — Windowsill's "run constantly" loop.  (Loam, 2026-07-22 night shift.)
#
# Continuously:  sync main → run one experiment (the open milestone via `lab next`,
# with a FRESH INDEPENDENT SEED each pass) → publish the feed → commit + push-retry →
# sleep → repeat.  Reuses the nightly's on-main / pull-rebase / push-retry guards so it
# is safe alongside the other room and the page-mirror bot.
#
# HONEST SCOPE: each pass publishes the LATEST independent sample (dated reports
# overwrite within a day, so the feed shows a fresh result, not an accumulating average).
# Per-milestone statistical accumulation across seeds (averaging many seeds into ONE
# deeper result) is a documented next step — it needs runner-side sample appending and is
# NOT claimed here.  What this delivers: the instrument is continuously alive, computing
# and publishing verified independent physics every INTERVAL instead of once a night.
#
# Stop gracefully:  touch ~/.lab/campaign.stop   (honored after the current pass)  or SIGINT.
# Config (env):
#   LAB_CAMPAIGN_INTERVAL  seconds between passes           (default 1800 = 30m)
#   LAB_CAMPAIGN_DEVICE    cuda | cpu                        (default cuda)
#   LAB_CAMPAIGN_SEED      seed base; pass N uses base+N     (default 1000)
#   LAB_CAMPAIGN_MAX_ITERS 0 = forever                       (default 0)
#   LAB_CAMPAIGN_DRY       set = run+commit locally, skip push (testing)
#   LAB_CAMPAIGN_LOG       log path                          (default ~/.lab/campaign.log)
set -uo pipefail

REPO="/home/benslinuxbox/projects/windowsill-lab"
cd "$REPO" || exit 1
export TMPDIR="${TMPDIR:-$HOME/.cache/wtmp}"; mkdir -p "$TMPDIR"
PY="$REPO/.venv/bin/python3"

INTERVAL="${LAB_CAMPAIGN_INTERVAL:-1800}"
DEVICE="${LAB_CAMPAIGN_DEVICE:-cuda}"
SEED_BASE="${LAB_CAMPAIGN_SEED:-1000}"
MAX_ITERS="${LAB_CAMPAIGN_MAX_ITERS:-0}"
STOP="$HOME/.lab/campaign.stop"
LOG="${LAB_CAMPAIGN_LOG:-$HOME/.lab/campaign.log}"
mkdir -p "$(dirname "$LOG")" "$(dirname "$STOP")"
rm -f "$STOP"

iter=0
log(){ echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }
trap 'log "campaign: signal — stopping after pass $iter"; exit 0' INT TERM

log "campaign: START interval=${INTERVAL}s device=${DEVICE} seed_base=${SEED_BASE} max_iters=${MAX_ITERS} dry=${LAB_CAMPAIGN_DRY:-0}"
while :; do
  [ -f "$STOP" ] && { log "campaign: stop sentinel — done (iter=$iter)"; break; }
  iter=$((iter+1)); seed=$((SEED_BASE + iter))
  log "campaign: pass $iter (seed $seed)"

  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if [ "$branch" != "main" ]; then
    log "campaign: on '$branch' not main — publish skipped this pass"
  else
    git pull --rebase --autostash >/dev/null 2>&1 || true
    "$PY" -m lab.cli next --seed "$seed" --device "$DEVICE" >> "$LOG" 2>&1 \
      || "$PY" -m lab.cli publish >> "$LOG" 2>&1 || true
    git add pot.json physics-latest.json >/dev/null 2>&1 || true
    git add -A reports/ >/dev/null 2>&1 || true
    if git diff --cached --quiet 2>/dev/null; then
      log "campaign: pass $iter — nothing changed"
    elif [ -n "${LAB_CAMPAIGN_DRY:-}" ]; then
      git reset -q 2>/dev/null || true
      log "campaign: pass $iter — DRY, ran+rendered, push skipped"
    else
      git commit -q -m "campaign: pass $iter $(date -u +%F) seed=$seed" >/dev/null 2>&1 || true
      pushed=0
      for a in 1 2 3 4; do
        if git push -q >/dev/null 2>&1; then pushed=1; break; fi
        git pull --rebase --autostash >/dev/null 2>&1 || true
      done
      log "campaign: pass $iter — published (pushed=$pushed)"
    fi
  fi

  [ "$MAX_ITERS" -gt 0 ] && [ "$iter" -ge "$MAX_ITERS" ] && { log "campaign: reached max_iters=$MAX_ITERS"; break; }
  [ -f "$STOP" ] && { log "campaign: stop sentinel — done"; break; }
  sleep "$INTERVAL"
done
