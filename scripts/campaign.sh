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
# The one way a pass declines to publish. Both failure branches call it, so the two
# cannot drift into two different conventions — which is exactly how a failed
# `lab next` ended up on the publishing path while a failed `verify` did not.
#
# Restoring the campaign-owned TRACKED paths matters twice over: the dirty-worktree
# guard at the top of every pass would otherwise refuse the lane until a human
# cleared it, and anything the failed run half-wrote must not survive to be swept up
# by the NEXT pass's `git add -A -- reports/`. `git checkout` only restores tracked
# files, so untracked wreckage in reports/ is cleaned explicitly.
withhold_pass(){
  if git checkout -q -- pot.json physics-latest.json reports/ 2>/dev/null; then
    log "campaign: pass $iter — campaign-owned paths restored to last committed state"
  else
    log "campaign: pass $iter — restore failed; next pass will refuse the dirty worktree"
  fi
  if ! git clean -qfd -- reports/ 2>/dev/null; then
    log "campaign: pass $iter — could not clear untracked artifacts under reports/"
  fi
}

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
  # shellcheck disable=SC2317  # reached when SOURCED; the loop below is what is skipped
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
    # A pass publishes only what it can VOUCH for, and there are two ways it cannot.
    # Until 2026-08-22 they were treated as one benign and one fatal.
    #
    # A failed `lab next` used to log "experiment failed; refreshing existing feed
    # only", leave publishable=1, and fall straight through to the staging block —
    # which `git add -A -- reports/` (indiscriminate) then committed as
    # `campaign: pass N <date> seed=S`, a subject IDENTICAL IN SHAPE to a successful
    # pass. Four things went wrong at once: `verify` re-grades only on the SUCCEEDED
    # path, so nothing re-checked what shipped; a real `lab next` fails PART WAY
    # THROUGH, so the artifacts swept in were torn; the commit was pushed; and the
    # `campaign.published` heartbeat was touched, so the estate watcher scored the
    # failed lane healthy. The pass counter is recovered by reading these subjects
    # back out of the ledger, so the masquerade corrupted the ledger as well as the
    # feed.
    #
    # One convention now: EITHER failure withholds, restores the campaign-owned
    # paths, and commits nothing. The feed is not "refreshed" on the way past —
    # regenerating it here only ever produced output this same pass then had to
    # restore, and the next successful pass rebuilds it from the committed receipts
    # anyway.
    publishable=1
    if ! "$PY" -m lab.cli next --seed "$seed" --device "$DEVICE" >> "$LOG" 2>&1; then
      publishable=0
      log "campaign: pass $iter — experiment failed; publishing withheld"
      withhold_pass
    elif ! "$PY" -m lab.cli verify >> "$LOG" 2>&1; then
      publishable=0
      log "campaign: pass $iter — verify failed; publishing withheld"
      withhold_pass
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
        for _ in 1 2 3 4; do   # attempt counter is unused by design
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
    # The test suite's own turn — LAST in the pass, and deliberately harmless.
    # Until 2026-09-04 no scheduled job on either box ran pytest at all: this loop
    # ran `lab next` + `lab verify` and stopped, the Windows nightly was the same
    # shape, and the only automated pytest anywhere was CI on push. Meanwhile
    # pot.json — the estate's whole model of windowsill health — carried no test
    # status, so "did a box publish a receipt" stood in for "did the tests run".
    # Reading the first as the second is how a two-week hole in committed
    # receipts got reported as a two-week test outage that never happened.
    #
    # AFTER the experiment and the publish, and its exit status is logged but
    # never acted on. This pass has its own gates (the `lab next` / `lab verify`
    # withholds above); the test signal is a DIFFERENT signal and must never be
    # able to revert or withhold a run that already graded clean. A red suite is
    # recorded in the feed's `tests` block and logged here — that is all it does.
    #
    # --if-due owns the cadence so this line does not: one pass per box per UTC
    # day, picked from the UTC hour, no new entry in the env block above. It also
    # covers plain-interval mode (HOURS unset ⇒ a pass every 30 min), where the
    # window alone would fire twelve times — see lab/selftest.py:DUE_UTC_HOURS.
    if ! "$PY" -m lab.cli selftest --if-due >> "$LOG" 2>&1; then
      log "campaign: pass $iter — selftest reported a FAILURE; recorded in the feed, publish above stands"
    fi
    # ...and the verdict has to LEAVE THIS BOX or it is not a signal. `lab
    # selftest` files reports/receipts/selftest-<date>-<hhmm>-<machine>.json,
    # and nothing else stages it: this pass already ran its own
    # `git add -A -- reports/` further up, and withhold_pass runs
    # `git clean -qfd -- reports/`, so a receipt left untracked here is
    # DELETED by the next refused pass — the verdict erased before anyone
    # reads it. Commit it now, in its own commit, touching nothing but the
    # receipt itself.
    #
    # Still NOT a gate, and it cannot become one: this runs after the science
    # commit and push, it stages nothing but its own receipt, and every
    # failure below is a log line. A push that loses a race waits for the next pass
    # — safe_pull_rebase rebases the local commit and the next push carries
    # it, which is the same recovery the science commit already relies on.
    #
    # Scoped to selftest-*.json, not to the directory: on the two branches where
    # staging or committing the science paths FAILED, `git reset` leaves the
    # pass's untracked debris behind, and a receipt is immutable evidence — a
    # torn run-*.json swept in here would land on the ledger under a "selftest:"
    # subject. The glob can only ever match what this step wrote.
    # DRY never touches the remote. `LAB_CAMPAIGN_DRY` is documented at the top
    # of this file as "run+render locally, leave unstaged, skip commit/push", and
    # the science path above honours it by resetting whatever it staged. Without
    # this branch the receipt step below would git add + commit + PUSH to
    # origin/main out of a run whose entire contract is that it publishes nothing.
    if [ -n "${LAB_CAMPAIGN_DRY:-}" ]; then
      log "campaign: pass $iter — DRY, selftest receipt (if any) left uncommitted"
    elif ls reports/receipts/selftest-*.json >/dev/null 2>&1 \
       && git add -- 'reports/receipts/selftest-*.json' >/dev/null 2>&1 \
       && ! git diff --cached --quiet -- 'reports/receipts/selftest-*.json' 2>/dev/null; then
      if git commit -q --only -m "selftest: $(date -u +%F) pass $iter" -- 'reports/receipts/selftest-*.json' >/dev/null 2>&1; then
        if git push -q >/dev/null 2>&1; then
          log "campaign: pass $iter — selftest receipt committed and pushed"
        else
          log "campaign: pass $iter — selftest receipt committed; push deferred to the next pass"
        fi
      else
        # UNSTAGE, always. The `git add` above put the receipt in the index, and
        # this loop's own top-of-pass guard treats a pre-loaded index as a reason
        # to skip the ENTIRE pass ("pre-existing staged changes; refusing to run
        # or alter the index") — so one failed commit here would halt the
        # science lane on every pass from then on, silently, until a human
        # noticed. The science commit's own failure path resets for exactly this
        # reason. Losing this receipt to a later `git clean` costs ONE verdict,
        # which the feed then publishes as `unknown`; a wedged lane costs every
        # pass after it, and publishes nothing at all.
        git reset -q -- 'reports/receipts/selftest-*.json' >/dev/null 2>&1 || true
        log "campaign: pass $iter — selftest receipt could not be committed; unstaged, it stays in the worktree"
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
