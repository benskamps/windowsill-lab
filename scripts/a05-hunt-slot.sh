#!/usr/bin/env bash
# a05-hunt-slot.sh — one bounded blind-transit hunt per loam interleave slot (3/9/15/21).
#
# Driven by `windowsill-hunt.timer` (systemd --user, 03/09/15/21:02 local). The
# runner (scripts/a05_hunt.py) owns the search, the checkpoints, the receipt and
# the grading; this wrapper owns only the git side: stage what the runner wrote,
# push it if and only if it graded, and leave the clone exactly as it found it.
#
# Contract: handoffs/2026-08-14-win-to-loam-a05-sector-split.md (loam = sectors 3, 30).
# Sector comes from $LAB/hunt.sector; stop with `touch $LAB/hunt.stop`.
#
# It lived unversioned in ~/.lab/ until 2026-08-18, which is how a stale glob in it
# went unnoticed for days (see THE STAGING RULE below). It sits beside campaign.sh
# now, under the same tests as the rest of the instrument.
#
# Config (env) — all three are test seams, defaulted to this box's real paths:
#   LAB_HUNT_LAB   runtime dir holding hunt.sector / hunt.stop / the logs  (~/.lab)
#   LAB_HUNT_REPO  the windowsill-lab clone to publish from
#   LAB_HUNT_PY    the interpreter that runs the hunt driver
set -u
shopt -s nullglob   # an absent dossier must vanish from the `git add` list, not
                    # reach git as a literal unexpanded glob

LAB="${LAB_HUNT_LAB:-$HOME/.lab}"
REPO="${LAB_HUNT_REPO:-$HOME/projects/windowsill-lab}"
PY="${LAB_HUNT_PY:-$REPO/.venv/bin/python}"

[ -e "$LAB/hunt.stop" ] && exit 0
exec 9>"$LAB/hunt.lock"
flock -n 9 || exit 0   # a hunt is already running — one hunt per slot per box

sector=$(cat "$LAB/hunt.sector" 2>/dev/null || echo 3)
log="$LAB/hunt-s${sector}-$(date +%F).log"

cd "$REPO" || exit 1

# THE POT RULE. pot.json's hunt block is a pure function of the receipts, and CI
# enforces `pot == hunt_block()` — so a receipt committed WITHOUT its refreshed pot
# ships a red main in the producer's own commit (the 2026-08-15 nightly did that),
# and a pot left dirty by a run we do NOT commit halts the physics lane: campaign.sh
# refuses to run against a dirty tracked file, which quietly ate campaign passes
# 119-124, ~33h, on 2026-08-17/18 with both units green. So the two paths differ:
# a pushed receipt takes pot.json WITH it, and any other exit restores pot.json.
restore_pot(){
  git diff --quiet -- pot.json 2>/dev/null && return 0
  git checkout -- pot.json 2>>"$log" \
    && echo "$(date -Is) pot.json restored — nothing of this run is being published" >>"$log"
}

# An ungraded receipt may not sit in reports/hunts/. The aggregator globs that
# DIRECTORY, not git (src/lab/publish.py), so a receipt left there is counted into
# the public ledger by the next run that publishes — while CI, which only ever sees
# the committed set, recomputes a different total and goes red. Filing it beside its
# log is what win's contract already says ("stays local with the log"); it keeps the
# evidence and keeps it out of the counters.
# COST, eyes open: already_searched() globs the same directory, so a quarantined
# run's targets become eligible again and a later slot may re-search them.
quarantine_receipt(){
  [ -n "${receipt:-}" ] && [ -f "$receipt" ] || return 0
  # The runner quarantines its own ungraded receipts and PRINTS the settled path,
  # so the path read back may already be the filed one — never move a file onto
  # itself.
  case "$receipt" in "$LAB/ungraded/"*) return 0 ;; esac
  mkdir -p "$LAB/ungraded" && mv -f "$receipt" "$LAB/ungraded/" \
    && echo "$(date -Is) ungraded receipt filed with the log -> $LAB/ungraded/$(basename "$receipt")" >>"$log"
}

git pull --rebase --autostash -q 2>>"$log"

echo "$(date -Is) slot start — sector $sector" >>"$log"

# THE WINDOW RULE. There is ONE log file per sector per day and all four slots
# append to it, so anything read back out of it has to be scoped to THIS run.
# Read the whole file and a crashed slot 2 inherits slot 1's "receipt -> " line,
# republishing a receipt that is already committed; read a fixed `tail -5` window
# and this run's grade line is invisible the moment anything prints after it.
# Remember where this run starts and read only from there.
log_mark=$(wc -l <"$log" 2>/dev/null || echo 0)
PYTHONPATH=src "$PY" scripts/a05_hunt.py \
  --sector "$sector" --n 200 --minutes 100 >>"$log" 2>&1
rc=$?
echo "$(date -Is) runner exit $rc" >>"$log"
run_log="$(tail -n +$((log_mark + 1)) "$log")"

# THE STAGING RULE. Stage the receipt the RUNNER says it wrote, read back from its
# own "receipt -> PATH" line. This was once a glob, `hunt-*-s${sector}.json`, written
# before the runner gained a collision-proof -HHMM suffix on every receipt after the
# day's first: the glob then matched slot 1 and nothing else, so slots 2-4 wrote
# receipts that were never staged and `git commit` reported "nothing to commit" and
# exited 0 — a silent failure under a green unit. Two graded receipts stranded that
# way before it was caught. A path the producer PRINTS cannot drift out of sync with
# the producer's naming; a glob written from memory always can.
receipt="$(printf '%s\n' "$run_log" | sed -n 's|^receipt -> ||p' | tail -1)"

# THE GATE. Publishing needs two POSITIVE proofs, never the absence of a negative.
# It used to need neither: `rc` was captured on the line after the runner and never
# read again, and success was inferred from `tail -5 "$log"` NOT matching
# `check_a05: None|False`. A crash between the receipt write (a05_hunt.py:296) and
# the grade print satisfies that gate perfectly — a complete-looking receipt on
# disk, no failure string anywhere — and publishes an ungraded receipt alongside a
# pot.json the dead run never refreshed. CI recomputes `pot == hunt_block()` from
# the committed set and goes red in the producer's own commit: the realized
# 2026-08-15 class. Absence is what a crash, a truncated log, a scrolled-away line
# and a renamed grade token ALL look like.
#
# Proof 1: the runner exited 0.
if [ "$rc" -ne 0 ]; then
  echo "$(date -Is) runner failed rc=$rc — nothing of this run is published" >>"$log"
  quarantine_receipt
  restore_pot
  exit "$rc"
fi
if [ -z "$receipt" ] || [ ! -f "$receipt" ]; then
  echo "$(date -Is) no receipt path in this run's log — nothing staged" >>"$log"
  restore_pot
  exit 1
fi
# Proof 2: this run printed `check_a05: True`. None (a control failed, so the FAPs
# mean nothing) and False (a real failure) stay local with the log — win's contract.
if ! printf '%s\n' "$run_log" | grep -q '^check_a05: True'; then
  echo "$(date -Is) no positive grade in this run's log — receipt NOT pushed" >>"$log"
  quarantine_receipt
  restore_pot
  exit 0
fi

stem="$(basename "$receipt" .json)"

# A lead's rendered dossier is named <receipt stem>-tic<id>.html and is cited by the
# receipt that ships it, so it has to travel WITH that receipt. The 2026-08-18 lead
# (TIC 287328866) pushed its receipt and left its dossier sitting untracked.
if ! git add -- pot.json "$receipt" "reports/hunts/dossiers/${stem}"-tic*.html 2>>"$log"; then
  restore_pot
  exit 1
fi
git commit -q -m "a05: hunt receipt sector ${sector} $(date +%F) (loam slot)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" || exit 0  # nothing new to commit
git pull --rebase --autostash -q >>"$log" 2>&1
git push -q >>"$log" 2>&1 && echo "$(date -Is) receipt pushed" >>"$log"
