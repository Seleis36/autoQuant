#!/usr/bin/env bash
# The research host's half of the rsync link to the trading desk (see PLAN.md).
#
#   harness/research_host/sync.sh          # one pass; the research-sync timer runs it every 2 min
#
# One pass:
#   1. reconcile the session registry: a `running` entry whose pid is dead here becomes
#      aborted/orphaned (the PC was switched off mid-run) -- session_reap_orphans
#   2. pull the desk's capital book and status into harness/state/
#   3. pull the dashboard's requests (deleting them on the desk) and act on them
#   4. push logs (poller.log as desktop-poller.log), the registry, and the transcripts of
#      registered sessions
#   5. write heartbeat.json and push it LAST: the desk judges this host by its mtime
#
# Idempotent and safe to overlap with itself (flock). An unreachable desk is normal -- the
# PC is often off the tailnet -- so it logs the change of state once and exits 0.
# Never --delete: the desk keeps history after this host prunes.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"

DESK="${AQ_DESK_HOST:-100.120.177.5}"
DESK_USER="${AQ_DESK_USER:-aqsync}"
KEY="${AQ_SYNC_KEY:-$HOME/.ssh/autoquant_sync}"
STATE="$REPO/harness/state/research_host"
PENDING="$STATE/requests"
LOGS="$REPO/harness/logs"
LOG="$LOGS/sync.log"
TRANSCRIPTS="$HOME/.claude/projects/-home-seleis-autoQuant"
mkdir -p "$STATE" "$PENDING" "$LOGS"

say() { echo "[$(date -u +%FT%TZ)] sync: $*" >> "$LOG"; }

if [ "$(aq_role)" != research ]; then
  echo "REFUSED: sync.sh runs on the research host only (AQ_ROLE=$(aq_role))" >&2
  exit 5
fi

exec {lock}>"$STATE/sync.lock"
flock -n "$lock" || exit 0

# Log a line only when the link changes state, not every two minutes.
link_state() {  # link_state <up|down|refused> <detail>
  local prev; prev="$(cat "$STATE/link" 2>/dev/null)"
  [ "$prev" = "$1" ] || say "desk link $1${2:+: $2}"
  echo "$1" > "$STATE/link"
}

SSH="ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=10 -o IdentitiesOnly=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
r() { timeout 600 rsync -t -e "$SSH" "$@"; }
R="$DESK_USER@$DESK"

# ---- 1. reconcile the registry ------------------------------------------------
session_reap_orphans 2>>"$LOG"

# ---- reachability -------------------------------------------------------------
if ! timeout 8 bash -c "</dev/tcp/$DESK/22" 2>/dev/null; then
  link_state down "no answer from $DESK:22"
  exit 0
fi

# ---- 2. the desk's capital book and status --------------------------------------
pull_atomic() {  # pull_atomic <remote path> <local file>
  local tmp; tmp="$(mktemp "$(dirname "$2")/.pull.XXXXXX")"
  if r "$R:$1" "$tmp" 2>>"$STATE/rsync.err" && [ -s "$tmp" ] &&
     sl_py -c 'import json,sys; json.load(open(sys.argv[1]))' "$tmp" 2>/dev/null; then
    mv -f "$tmp" "$2"; return 0
  fi
  rm -f "$tmp"; return 1
}
: > "$STATE/rsync.err"
if ! pull_atomic outbox/desk.json "$REPO/harness/state/desk.json"; then
  link_state refused "$(tail -c 300 "$STATE/rsync.err" | tr '\n' ' ')"
  exit 0
fi
link_state up
pull_atomic outbox/allocations.json "$REPO/harness/state/allocations.json" \
  || say "could not pull outbox/allocations.json (kept the local copy)"

# ---- 3. requests ------------------------------------------------------------------
# Only <id>.json: the dashboard writes .<id>.tmp first and renames, so a half-written
# request is never taken. --remove-source-files deletes each one on the desk once copied.
r -r --remove-source-files --include='[!.]*.json' --exclude='*' \
  "$R:outbox/requests/" "$PENDING/" 2>>"$LOG" || say "request pull failed"
sl_py "$REPO/harness/research_host/handle_requests.py" "$PENDING" 2>>"$LOG"

# ---- 4. push logs, registry, transcripts ---------------------------------------------
PUSH=(--chmod=D0700,F0600)
logs=()
for f in "$LOGS"/*.log; do
  [ -f "$f" ] && [ "$(basename "$f")" != poller.log ] && logs+=("$f")
done
[ ${#logs[@]} -gt 0 ] && { r "${PUSH[@]}" "${logs[@]}" "$R:desktop/logs/" 2>>"$LOG" || say "log push failed"; }
[ -f "$LOGS/poller.log" ] && { r "${PUSH[@]}" "$LOGS/poller.log" "$R:desktop/logs/desktop-poller.log" 2>>"$LOG" \
  || say "poller.log push failed"; }

r -r "${PUSH[@]}" --include='*.json' --exclude='*' "$SL_SESSIONS/" "$R:desktop/sessions/" 2>>"$LOG" \
  || say "registry push failed"

list="$STATE/transcripts.list"
for f in "$SL_SESSIONS"/*.json; do
  b="$(basename "$f" .json)"
  [[ "$b" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || continue
  [ -f "$TRANSCRIPTS/$b.jsonl" ] && echo "$b.jsonl"
done > "$list"
if [ -s "$list" ]; then
  r "${PUSH[@]}" --files-from="$list" "$TRANSCRIPTS/" "$R:desktop/transcripts/" 2>>"$LOG" \
    || say "transcript push failed"
fi

# ---- 5. heartbeat, last ------------------------------------------------------------
today="$(TZ=Europe/Paris date +%F)"
stamp="$(cat "$STATE/last_batch" 2>/dev/null)"
[ "$stamp" = "$today" ] || stamp=""
free_gb="$(df -BG --output=avail "$REPO" | tail -1 | tr -dc 0-9)"
SL_TODAY="$stamp" SL_FREE="${free_gb:-0}" sl_py - "$SL_SESSIONS" "$STATE/heartbeat.json" <<'PY'
import datetime, glob, json, os, socket, sys
sessions, out = sys.argv[1], sys.argv[2]
running = []
for f in sorted(glob.glob(os.path.join(sessions, "*.json"))):
    if f.endswith(".result.json"):
        continue
    try:
        d = json.load(open(f))
        if d.get("status") == "running" and d.get("pid"):
            os.kill(int(d["pid"]), 0)
            running.append(d["id"])
    except Exception:
        pass
hb = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "host": socket.gethostname().lower(), "role": "research", "running": running,
      "research_today": os.environ["SL_TODAY"] or None,
      "disk_free_gb": int(os.environ["SL_FREE"])}
tmp = out + ".tmp"
json.dump(hb, open(tmp, "w"))
os.replace(tmp, out)
PY
r "${PUSH[@]}" "$STATE/heartbeat.json" "$R:desktop/heartbeat.json" 2>>"$LOG" || say "heartbeat push failed"
exit 0
