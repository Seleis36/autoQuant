#!/usr/bin/env bash
# The nightly research batch: N asset classes, one after the other.
#
#   ./harness/nightly_research.sh             # NIGHTLY_COUNT (default 2) classes
#   ./harness/nightly_research.sh --dry-run   # print what tonight would run, launch nothing
#
# Run by autoquant-nightly.timer. Knobs, all environment variables:
#
#   NIGHTLY_COUNT        classes per night                                   (2)
#   NIGHTLY_CLASSES      explicit space-separated list; skips the rotation   (unset)
#   NIGHTLY_MODEL        model alias or id for every run tonight             (launcher default)
#   NIGHTLY_MAX_OPEN_PRS skip the night when this many PRs are already open  (4)
#   NIGHTLY_DEADLINE_H   launch nothing new after this many hours            (10)
#
# Rotation: least recently researched first, judged by the newest
# harness/logs/research-<class>-*.log -- the logs are the record of what ran, so there is
# no second list to fall out of sync with them, and a class launched by hand from the
# dashboard counts as its turn.
#
# Sequential, not parallel, on purpose. session_lib.sh gives research one slot out of
# AGENT_MAX_CONCURRENT so deploy/revise work can always start; a second concurrent
# research launch is refused (exit 3). Running back to back also spreads the night's
# usage across more of the subscription's rolling window instead of spending it at once.
#
# Everything runs inside main(), called on the last line -- see agent_exec.sh for why.
set -uo pipefail

main() {
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"
LOGS="$REPO/harness/logs"
mkdir -p "$LOGS"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

COUNT="${NIGHTLY_COUNT:-2}"
MAX_OPEN="${NIGHTLY_MAX_OPEN_PRS:-4}"
DEADLINE=$(( $(date +%s) + ${NIGHTLY_DEADLINE_H:-10} * 3600 ))
LOG="$LOGS/nightly-$(date -u +%Y%m%dT%H%M%SZ).log"
[ "$DRY" = 1 ] && LOG=/dev/stdout

say() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

# ---- tonight's classes -------------------------------------------------------
local picks
if [ -n "${NIGHTLY_CLASSES:-}" ]; then
  picks="$NIGHTLY_CLASSES"
else
  picks="$(pick_classes "$COUNT")"
fi
say "tonight: ${picks:-<nothing>}  (model=${NIGHTLY_MODEL:-launcher default})"
[ "$DRY" = 1 ] && return 0
[ -n "$picks" ] || { say "no asset classes found"; return 1; }

# ---- guards ------------------------------------------------------------------
# Keep the CLI current: model aliases resolve to the newest model the CLI knows, so a
# stale binary is a stale model. Harmless when already up to date; never fatal.
say "cli before: $("$CLAUDE_BIN" --version 2>&1 | head -1)"
timeout 300 "$CLAUDE_BIN" update >> "$LOG" 2>&1 < /dev/null || say "claude update failed (continuing)"
say "cli after:  $("$CLAUDE_BIN" --version 2>&1 | head -1)"

# Research makes work for deploy and revise. When the queue is already deep, adding to
# it only lengthens the wait for results nobody has looked at yet.
local open
open="$(gh pr list --state open --json number --jq length 2>/dev/null || echo "")"
if [ -n "$open" ] && [ "$open" -ge "$MAX_OPEN" ]; then
  say "skipping the night: $open open PRs >= NIGHTLY_MAX_OPEN_PRS=$MAX_OPEN"
  return 0
fi

# ---- run ---------------------------------------------------------------------
local ac uuid out rc before
for ac in $picks; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    say "deadline reached; not launching $ac"
    break
  fi
  wait_for_research_slot || { say "research slot still busy at the deadline; stopping"; break; }

  before="$(git -C "$REPO" status --porcelain 2>/dev/null)"
  out="$("$REPO/harness/launch_research.sh" "$ac" "" \
           ${NIGHTLY_MODEL:+--model "$NIGHTLY_MODEL"} 2>&1)"
  rc=$?
  echo "$out" | sed 's/^/    /' >> "$LOG"
  if [ "$rc" -ne 0 ]; then
    say "launch of $ac failed rc=$rc"
    continue
  fi
  uuid="$(echo "$out" | sed -n 's/.*session \([0-9a-f-]\{36\}\).*/\1/p' | head -1)"
  say "launched $ac as session ${uuid:-?}"
  [ -n "$uuid" ] && wait_for_session "$uuid"
  say "$ac finished: $(session_field "$uuid" status)/$(session_field "$uuid" reason)"
  check_stranded "$ac" "$before"
done
say "nightly batch done"
}

# pick_classes <n> -> the n asset classes whose last research log is oldest (never = oldest)
pick_classes() {
  local n="$1" f ac last
  for f in "$REPO"/.claude/commands/*-quant-research.md; do
    ac="$(basename "$f" -quant-research.md)"
    last="$(ls -t "$LOGS"/research-"$ac"-*.log 2>/dev/null | head -1)"
    echo "$( [ -n "$last" ] && stat -c %Y "$last" || echo 0 ) $ac"
  done | sort -n | head -n "$n" | awk '{print $2}' | tr '\n' ' '
}

session_field() {  # session_field <uuid> <key>
  sl_py -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get(sys.argv[2]) or "")
except Exception: print("")' "$SL_SESSIONS/$1.json" "$2"
}

# A session is over when its registry entry leaves "running" or its supervisor is gone
# (a reboot mid-run leaves "running" behind forever; the dashboard calls that orphaned).
wait_for_session() {
  local uuid="$1" pid
  while :; do
    [ "$(session_field "$uuid" status)" != "running" ] && return 0
    pid="$(session_field "$uuid" pid)"
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then return 0; fi
    sleep 60
  done
}

# Waits for no research agent to be running, until the deadline. slot_acquire is not
# used here: holding the slot would block the very launch we are waiting to make.
wait_for_research_slot() {
  local f pid busy
  while :; do
    busy=0
    for f in "$SL_SESSIONS"/*.json; do
      case "$f" in *.result.json) continue ;; esac
      grep -q '"kind": "research"' "$f" 2>/dev/null || continue
      grep -q '"status": "running"' "$f" 2>/dev/null || continue
      pid="$(sl_py -c 'import json,sys; print(json.load(open(sys.argv[1])).get("pid") or "")' "$f")"
      [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && busy=1
    done
    [ "$busy" = 0 ] && return 0
    [ "$(date +%s)" -ge "$DEADLINE" ] && return 1
    sleep 120
  done
}

# A run that ends "clean" can still have left its work uncommitted or unpushed -- the
# registry judges by exit code alone. Flag it here rather than find it days later.
check_stranded() {
  local ac="$1" before="$2" after branch
  after="$(git -C "$REPO" status --porcelain 2>/dev/null)"
  branch="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if [ "$after" != "$before" ] && [ -n "$after" ]; then
    say "WARNING stranded work after $ac: the working tree changed and is uncommitted (branch $branch)"
  fi
  if [ "$branch" != "main" ] &&
     ! git -C "$REPO" rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
    say "WARNING stranded work after $ac: branch $branch has no upstream -- never pushed"
  fi
}

main "$@"
