#!/usr/bin/env bash
# Start / stop / inspect a deployed live-paper strategy daemon.
#
#   ./harness/launch_live.sh start  spot-btc/bult
#   ./harness/launch_live.sh status [spot-btc/bult]
#   ./harness/launch_live.sh stop   spot-btc/bult
#   ./harness/launch_live.sh logs   spot-btc/bult [n]
#
# A strategy lives in live/<asset-class>/<short-name>/ and must contain runner.py.
# The daemon is detached with setsid so it outlives the launching shell, the
# Claude session and the poller.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE="$REPO/live"
RUN="$REPO/harness/state/run"
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
mkdir -p "$RUN"

slug() { echo "${1%/}" | tr '/' '_'; }

is_running() {  # $1 = pidfile
  [ -f "$1" ] || return 1
  local pid; pid="$(cat "$1" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

cmd_start() {
  local name="${1%/}" dir pidfile logfile
  dir="$LIVE/$name"
  [ -f "$dir/runner.py" ] || { echo "ERROR: $dir/runner.py not found" >&2; return 1; }
  pidfile="$RUN/$(slug "$name").pid"
  logfile="$dir/runner.log"

  if is_running "$pidfile"; then
    echo "already running: $name (pid $(cat "$pidfile"))"
    return 0
  fi

  # Fail fast on an import-time error rather than leaving a crash-looping daemon.
  if ! (cd "$dir" && "$PY" -c "import ast,sys; ast.parse(open('runner.py').read())"); then
    echo "ERROR: runner.py does not parse" >&2; return 1
  fi

  # Job control is off in a script, so the background child is not a process-group
  # leader and setsid execs in place -- $! is the python process itself.
  cd "$dir" || return 1
  setsid nohup "$PY" -u runner.py >> "$logfile" 2>&1 < /dev/null &
  local pid=$!
  cd "$REPO" || true
  sleep 3
  if ! kill -0 "$pid" 2>/dev/null || ! tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q runner.py; then
    echo "ERROR: $name exited immediately. Last log lines:" >&2
    tail -n 25 "$logfile" >&2
    return 1
  fi
  echo "$pid" > "$pidfile"
  echo "started $name (pid $pid) -- log: live/$name/runner.log"
}

cmd_stop() {
  local name="${1%/}" pidfile; pidfile="$RUN/$(slug "$name").pid"
  if ! is_running "$pidfile"; then echo "not running: $name"; rm -f "$pidfile"; return 0; fi
  local pid; pid="$(cat "$pidfile")"
  kill -TERM "$pid" 2>/dev/null
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
  rm -f "$pidfile"
  echo "stopped $name"
}

cmd_status() {
  local filter="${1:-}"
  shopt -s nullglob
  local any=0
  for pidfile in "$RUN"/*.pid; do
    local slug name; slug="$(basename "$pidfile" .pid)"
    name="$(find "$LIVE" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | while read -r d; do
              n="${d#"$LIVE"/}"; [ "$(echo "$n" | tr '/' '_')" = "$slug" ] && echo "$n"; done | head -1)"
    name="${name:-$slug}"
    [ -n "$filter" ] && [ "$name" != "${filter%/}" ] && continue
    any=1
    if is_running "$pidfile"; then
      printf 'RUNNING  %-32s pid %-8s ' "$name" "$(cat "$pidfile")"
    else
      printf 'DEAD     %-32s %-12s ' "$name" "-"
    fi
    local st="$LIVE/$name/state.json"
    if [ -f "$st" ]; then
      "$PY" -c "
import json,sys
s=json.load(open('$st'))
print('w=%-7s eq=%-11s %s %s' % (s.get('last_weight'), round(s.get('equity') or 0,2),
      'SHADOW' if s.get('shadow') else 'PAPER', s.get('updated','')))" 2>/dev/null || echo
    else
      echo "(no state.json yet)"
    fi
  done
  [ "$any" = 0 ] && echo "no strategies registered"
  return 0
}

cmd_logs() { tail -n "${2:-50}" -f "$LIVE/${1%/}/runner.log"; }

case "${1:-status}" in
  start)  shift; cmd_start "$@" ;;
  stop)   shift; cmd_stop "$@" ;;
  status) shift; cmd_status "$@" ;;
  logs)   shift; cmd_logs "$@" ;;
  restart) shift; cmd_stop "$1"; cmd_start "$1" ;;
  *) echo "usage: $0 {start|stop|restart|status|logs} <asset-class>/<short-name>" >&2; exit 2 ;;
esac
