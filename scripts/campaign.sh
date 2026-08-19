#!/usr/bin/env bash
# campaign.sh — Windowsill's "run constantly" loop.  (Loam, 2026-07-22 night shift.)
#
# Continuously:  sync main → run one experiment (the open milestone via `lab next`,
# with a FRESH INDEPENDENT SEED each pass) → publish the feed → re-grade every
# promoted milestone (`lab verify`; a red grade withholds the commit) → commit +
# push-retry → sleep → repeat.  Reuses the nightly's on-main / pull-rebase /
# push-retry guards so it is safe alongside the other room and the page-mirror bot.
#
# HONEST SCOPE: each pass publishes the LATEST independent sample (dated reports
# overwrite within a day, so the feed shows a fresh result, not an accumulating average).
# Per-milestone statistical accumulation across seeds (averaging many seeds into ONE
# deeper result) is a documented next step — it needs runner-side sample appending and is
# NOT claimed here.  What this delivers: the instrument is continuously alive, computing
# and publishing verified independent physics every INTERVAL instead of once a night.
#
# INTERLEAVE CONTRACT (2026-08-01): Win runs 00/06/12/18 local (Task Scheduler,
# 4 daily triggers) ↔ Loam runs 03/09/15/21 local (LAB_CAMPAIGN_HOURS below) —
# 8 turns/day across the portfolio, no overlapping slots. When HOURS is set the
# loop sleeps to the NEXT listed local hour boundary (recomputed from the wall
# clock each pass — drift-free, DST-proof) instead of accumulating
# `sleep INTERVAL` drift. Docs: docs/investigations/2026-08-01-portfolio-rotation.md.
#
# Stop gracefully:  touch ~/.lab/campaign.stop   (honored after the current pass)  or SIGINT.
# Config (env):
#   LAB_CAMPAIGN_INTERVAL  seconds between passes           (default 1800 = 30m)
#   LAB_CAMPAIGN_HOURS     space-separated local hours to anchor passes to
#                          (e.g. "3 9 15 21"); unset = plain interval sleep
#   LAB_CAMPAIGN_DEVICE    cuda | cpu                        (default cuda)
#   LAB_CAMPAIGN_SEED      seed base; pass N uses base+N     (default 1000)
#   LAB_CAMPAIGN_MAX_ITERS 0 = forever                       (default 0)
#   LAB_CAMPAIGN_DRY       set = run+render locally, leave unstaged, skip commit/push
#   LAB_CAMPAIGN_LOG       log path                          (default ~/.lab/campaign.log)
#   LAB_CAMPAIGN_STATE     persisted pass counter             (default ~/.lab/campaign.iter)
set -uo pipefail

# Both overridable so the conflict fixtures can drive the real functions against a
# throwaway clone and a stub interpreter instead of this box's paths.
# Derived from the script's own location, not hardcoded: this file lives in
# <repo>/scripts/, so the parent of its directory IS the repo. A hardcoded home
# path published the operator's account name in a public repo AND broke for
# anyone who cloned it anywhere else.
REPO="${LAB_CAMPAIGN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$REPO" || exit 1
export TMPDIR="${TMPDIR:-$HOME/.cache/wtmp}"; mkdir -p "$TMPDIR"
PY="${LAB_CAMPAIGN_PY:-$REPO/.venv/bin/python3}"

INTERVAL="${LAB_CAMPAIGN_INTERVAL:-1800}"
HOURS="${LAB_CAMPAIGN_HOURS:-}"
DEVICE="${LAB_CAMPAIGN_DEVICE:-cuda}"
SEED_BASE="${LAB_CAMPAIGN_SEED:-1000}"
MAX_ITERS="${LAB_CAMPAIGN_MAX_ITERS:-0}"
STOP="$HOME/.lab/campaign.stop"
LOG="${LAB_CAMPAIGN_LOG:-$HOME/.lab/campaign.log}"
STATE="${LAB_CAMPAIGN_STATE:-$HOME/.lab/campaign.iter}"
STATE_DIR="$(dirname "$STATE")"
if ! mkdir -p "$(dirname "$LOG")" "$(dirname "$STOP")" "$STATE_DIR"; then
  printf '%s\n' "campaign: FATAL — could not create runtime directories" >&2
  exit 1
fi

passes=0
log(){ echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

# pot.json and physics-latest.json are DERIVED: both boxes rebuild them from the same
# committed receipts every pass, so their contents collide by construction on any
# concurrent publish. On 2026-07-31 BOTH files conflicted on the same replay — the
# multi-file case, not a single-file one. Neither side's copy is authoritative and
# neither is worth keeping, so we do not pick a side: `--ours`/`--theirs` inverts
# meaning under rebase (the replayed commit is "theirs"), and that inversion bit both
# boxes during the manual recovery. Instead: abort, hard-sync to upstream, put our own
# unpushed receipts back on top, and rebuild both files from the merged receipt set —
# deterministic since #66. The receipts are the only irreplaceable thing in flight.
resolve_by_regeneration(){
  local conflicted ahead_paths stash_dir
  conflicted="$(git diff --name-only --diff-filter=U 2>/dev/null)"
  if [ -z "$conflicted" ]; then
    log "campaign: ERROR mid-rebase with no unmerged paths; not auto-resolving"
    return 1
  fi
  # Only DERIVED feeds may be resolved this way. A conflict anywhere else is a real
  # divergence of authored content and a human has to look at it.
  #
  # reports/*.html belong on this list and were missing from it until 2026-08-05.
  # They are derived by the very same `lab.cli publish` below, and the rest of this
  # function already treats reports/ as campaign-owned (the ahead_paths guard allows
  # '^reports/'; the staging step runs `git add -A -- reports/`). Only THIS guard
  # disagreed — so the 2026-08-04 09:35 nightly, whose conflict was
  # pot.json + reports/index.html + reports/latest.html, bailed out here and left the
  # clone detached mid-rebase. The campaign then ran zero passes for ~37h (last pass
  # 08-04 07:30) with no louder signal than a line in the log.
  #
  # reports/receipts/** is deliberately NOT allowed: receipts are immutable and
  # append-only (#83) and are the only irreplaceable thing in flight. A receipt that
  # genuinely conflicts is a real divergence and must stop for a human.
  if printf '%s\n' "$conflicted" | grep -qvx \
       -e 'pot.json' -e 'physics-latest.json' \
       -e 'reports/index.html' -e 'reports/latest.html'; then
    log "campaign: ERROR conflict touches non-derived paths ($(printf '%s' "$conflicted" | tr '\n' ' ')); not auto-resolving"
    return 1
  fi
  log "campaign: conflict on derived feeds only ($(printf '%s' "$conflicted" | tr '\n' ' ')); resolving by regeneration"
  if ! git rebase --abort >/dev/null 2>&1; then
    log "campaign: ERROR rebase abort FAILED - clone is STRANDED, manual repair required"
    return 1
  fi
  # The hard-sync below discards our unpushed commits, so refuse if they carry anything
  # this loop did not author. campaign commits only ever touch these paths.
  ahead_paths="$(git diff --name-only origin/main...HEAD 2>/dev/null)"
  if [ -n "$ahead_paths" ] && printf '%s\n' "$ahead_paths" \
    | grep -qv -e '^pot\.json$' -e '^physics-latest\.json$' -e '^reports/'; then
    log "campaign: ERROR unpushed commits touch paths outside the campaign's own ($(printf '%s' "$ahead_paths" | tr '\n' ' ')); not auto-resolving"
    return 1
  fi
  if ! stash_dir="$(mktemp -d "$TMPDIR/campaign-regen.XXXXXX")"; then
    log "campaign: ERROR could not create a temp dir to preserve receipts; not auto-resolving"
    return 1
  fi
  if [ -d reports ] && ! cp -a reports "$stash_dir/reports"; then
    rm -rf -- "$stash_dir"
    log "campaign: ERROR could not preserve local receipts; not auto-resolving"
    return 1
  fi
  if ! git reset -q --hard origin/main; then
    rm -rf -- "$stash_dir"
    log "campaign: ERROR hard-sync to origin/main failed; clone left as-is for inspection"
    return 1
  fi
  # Upstream's receipts arrived with the reset; ours go back on top. A same-named file
  # is the same milestone on the same day, so overlaying is a union, not a clobber.
  if [ -d "$stash_dir/reports" ] && ! cp -a "$stash_dir/reports/." reports/; then
    rm -rf -- "$stash_dir"
    log "campaign: ERROR could not restore local receipts after sync; clone left for inspection"
    return 1
  fi
  rm -rf -- "$stash_dir"
  if ! "$PY" -m lab.cli publish >> "$LOG" 2>&1; then
    log "campaign: ERROR regeneration failed after conflict; clone left for inspection"
    return 1
  fi
  if ! git add -- pot.json physics-latest.json >/dev/null 2>&1 \
    || ! git add -A -- reports/ >/dev/null 2>&1; then
    git reset -q -- pot.json physics-latest.json reports/ 2>/dev/null || true
    log "campaign: ERROR staging the regenerated feeds failed"
    return 1
  fi
  if git diff --cached --quiet -- pot.json physics-latest.json reports/ 2>/dev/null; then
    log "campaign: conflict resolved by regeneration — upstream already carried this state"
    return 0
  fi
  if ! git commit -q --only -m "campaign: reconcile pass $iter — regenerated pot.json + physics-latest.json after conflict" \
    -- pot.json physics-latest.json reports/ >/dev/null 2>&1; then
    log "campaign: ERROR reconcile commit failed"
    return 1
  fi
  log "campaign: conflict resolved by regeneration — both feeds rebuilt from the merged receipt set"
  return 0
}

# A conflicted `git pull --rebase` leaves the clone detached and mid-rebase. This used to be
# written `git pull --rebase >/dev/null 2>&1 || true`, which discarded the output AND the exit
# status, so the strand was invisible: the unit stayed green, physics kept running, and every
# later pass tripped the on-main guard and logged "on 'HEAD' not main" — a symptom four days
# downstream of its cause. That is exactly how Loam lost passes 2-8 on 2026-07-31.
# pot.json and physics-latest.json are regenerated by BOTH boxes every pass, so this recurs by
# construction once we share the 4/day rotation. Resolve it by regeneration when only those
# derived feeds conflict; otherwise fail loudly, leave the clone usable, and let the caller
# skip the pass rather than pretend it synced.
safe_pull_rebase(){
  local out rc
  out="$(git pull --rebase 2>&1)"; rc=$?
  [ "$rc" -eq 0 ] && return 0
  log "campaign: ERROR pull --rebase failed rc=$rc: $(printf '%s' "$out" | tail -3 | tr '\n' ' ')"
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    if resolve_by_regeneration; then
      return 0
    fi
  fi
  # Regeneration declined or failed before it could abort — leave the clone usable.
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    if git rebase --abort >/dev/null 2>&1; then
      log "campaign: ERROR rebase aborted, clone restored to '$(git rev-parse --abbrev-ref HEAD 2>/dev/null)'"
    else
      log "campaign: ERROR rebase abort FAILED - clone is STRANDED, manual repair required"
    fi
  fi
  return 1
}
trap 'log "campaign: signal — stopping after pass $iter"; exit 0' INT TERM

# Seconds until the soonest next LOCAL H:00:00 strictly in the future, over a
# space-separated hour list. Anchored to the wall clock (targets are rebuilt
# from local date strings, so DST shifts are absorbed) rather than accumulated
# sleeps, which drift later by each pass's walltime. NOW_EPOCH is a test seam.
next_wake_seconds() {
  local hours="$1" now today tomorrow h target best
  now="${NOW_EPOCH:-$(date +%s)}"
  today="$(date -d "@$now" +%F)"
  tomorrow="$(date -d "@$((now + 86400))" +%F)"
  best=""
  for h in $hours; do
    target="$(date -d "$today $h:00:00" +%s)"
    if [ "$target" -le "$now" ]; then
      target="$(date -d "$tomorrow $h:00:00" +%s)"
    fi
    if [ -z "$best" ] || [ "$target" -lt "$best" ]; then best="$target"; fi
  done
  echo $((best - now))
}

persist_counter() {
  local value="$1"
  local state_base state_tmp
  state_base="$(basename "$STATE")"
  if ! state_tmp="$(umask 077 && mktemp "$STATE_DIR/.${state_base}.tmp.XXXXXX")"; then
    log "campaign: FATAL — could not create counter temp file for $STATE"
    return 1
  fi
  if ! printf '%s\n' "$value" > "$state_tmp"; then
    rm -f -- "$state_tmp"
    log "campaign: FATAL — could not write counter temp file for $STATE"
    return 1
  fi
  if ! mv -f -- "$state_tmp" "$STATE"; then
    rm -f -- "$state_tmp"
    log "campaign: FATAL — could not persist counter to $STATE"
    return 1
  fi
}

# The counter picks the seed (SEED_BASE + iter), so losing it REUSES seeds. The state
# file is only a cache: a fresh clone, a wiped ~/.lab, or a restored box leaves it absent
# and the loop silently restarts at pass 1. That is what happened on 2026-07-31 — Loam
# came back up logging "pass 1 seed=1001" and replayed July's seeds 1001+ against the same
# milestones, which makes independent samples look independent when they are not. The
# published ledger is the durable record, so derive from it and let the file only agree
# or lag. Highest wins; the counter must never walk backwards.
ledger_counter(){
  git log --format=%s -n 4000 -- pot.json physics-latest.json 2>/dev/null \
    | sed -n 's/^campaign: pass \([0-9][0-9]*\) .*/\1/p' \
    | sort -rn | head -1
}

iter=0
if [ -r "$STATE" ]; then
  IFS= read -r saved_iter < "$STATE" || true
  case "$saved_iter" in
    ''|*[!0-9]*) ;;
    *) iter="$saved_iter" ;;
  esac
fi
ledger_iter="$(ledger_counter)"
case "$ledger_iter" in ''|*[!0-9]*) ledger_iter=0 ;; esac
if [ "$ledger_iter" -gt "$iter" ]; then
  log "campaign: counter recovered from ledger — state file said $iter, published ledger says $ledger_iter"
  iter="$ledger_iter"
fi

# Sourced by the conflict fixtures to drive the functions above against a throwaway
# clone without entering the loop:  LAB_CAMPAIGN_LIB=1 . scripts/campaign.sh
if [ -n "${LAB_CAMPAIGN_LIB:-}" ]; then
  return 0 2>/dev/null || exit 0
fi

log "campaign: START interval=${INTERVAL}s hours='${HOURS}' device=${DEVICE} seed_base=${SEED_BASE} max_iters=${MAX_ITERS} dry=${LAB_CAMPAIGN_DRY:-0}"
while :; do
  [ -f "$STOP" ] && { log "campaign: stop sentinel — done (iter=$iter)"; break; }
  next_iter=$((iter+1))
  if ! persist_counter "$next_iter"; then
    printf '%s\n' "campaign: counter persistence failed; no experiment was launched" >&2
    exit 1
  fi
  iter="$next_iter"; passes=$((passes+1)); seed=$((SEED_BASE + iter))
  log "campaign: pass $iter (seed $seed)"

  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if [ "$branch" != "main" ]; then
    log "campaign: on '$branch' not main — publish skipped this pass"
  elif ! git diff --cached --quiet -- 2>/dev/null; then
    log "campaign: pass $iter — pre-existing staged changes; refusing to run or alter the index"
  elif ! git diff --quiet -- 2>/dev/null; then
    log "campaign: pass $iter — pre-existing tracked worktree changes; refusing to pull or run"
  elif ! safe_pull_rebase; then
    log "campaign: pass $iter - publish skipped: could not sync with origin (see ERROR above)"
  else
    publishable=1
    if ! "$PY" -m lab.cli next --seed "$seed" --device "$DEVICE" >> "$LOG" 2>&1; then
      log "campaign: pass $iter — experiment failed; refreshing existing feed only"
      "$PY" -m lab.cli publish >> "$LOG" 2>&1 \
        || log "campaign: pass $iter — feed refresh also failed"
    elif ! "$PY" -m lab.cli verify >> "$LOG" 2>&1; then
      publishable=0
      log "campaign: pass $iter — verify failed; publishing withheld"
      # Restore campaign-owned tracked paths to HEAD, or the dirty-worktree guard
      # would refuse every later pass; the failing grades are in the log above.
      if git checkout -q -- pot.json physics-latest.json reports/ 2>/dev/null; then
        log "campaign: pass $iter — campaign-owned paths restored to last committed state"
      else
        log "campaign: pass $iter — restore failed; next pass will refuse the dirty worktree"
      fi
    fi
    if [ "$publishable" -eq 0 ]; then
      : # withheld above — nothing staged this pass
    elif ! git add -- pot.json physics-latest.json >/dev/null 2>&1 \
      || ! git add -A -- reports/ >/dev/null 2>&1; then
      git reset -q -- pot.json physics-latest.json reports/ 2>/dev/null || true
      log "campaign: pass $iter — staging campaign-owned paths failed"
    elif git diff --cached --quiet -- pot.json physics-latest.json reports/ 2>/dev/null; then
      log "campaign: pass $iter — nothing changed"
    elif [ -n "${LAB_CAMPAIGN_DRY:-}" ]; then
      if git reset -q -- pot.json physics-latest.json reports/ 2>/dev/null; then
        log "campaign: pass $iter — DRY, ran+rendered, campaign paths left unstaged"
      else
        log "campaign: pass $iter — DRY, failed to unstage campaign paths"
      fi
    else
      # Ledger dates in LOCAL time to match report dating (publish.today_local);
      # log() lines carry the UTC stamp alongside.
      pass_day="$(date +%F)"
      if ! git commit -q --only -m "campaign: pass $iter $pass_day seed=$seed" \
        -- pot.json physics-latest.json reports/ >/dev/null 2>&1; then
        log "campaign: pass $iter — commit failed"
      else
        pushed=0
        for a in 1 2 3 4; do
          if git push -q >/dev/null 2>&1; then pushed=1; break; fi
          safe_pull_rebase || break
        done
        if [ "$pushed" -eq 1 ]; then
          # Heartbeat for the estate watcher, touched ONLY here. Everything else
          # this loop writes moves on a REFUSED pass too — the counter advances,
          # the log grows, pot.json gets rewritten by the other lane — so an
          # mtime watcher reading any of them scores a halted campaign as
          # healthy. That is how passes 119-124 stalled ~33h in plain sight.
          # Consumer: groundskeeper/checks/freshness.py.
          : > "$STATE_DIR/campaign.published" 2>/dev/null || true
          log "campaign: pass $iter — published"
        else
          log "campaign: pass $iter — committed locally; push failed"
        fi
      fi
    fi
  fi

  [ "$MAX_ITERS" -gt 0 ] && [ "$passes" -ge "$MAX_ITERS" ] && { log "campaign: reached max_iters=$MAX_ITERS"; break; }
  [ -f "$STOP" ] && { log "campaign: stop sentinel — done"; break; }
  if [ -n "$HOURS" ]; then
    wait_s="$(next_wake_seconds "$HOURS")"
    log "campaign: sleeping ${wait_s}s until the next anchored hour (${HOURS})"
    sleep "$wait_s"
  else
    sleep "$INTERVAL"
  fi
done
