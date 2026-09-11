#!/usr/bin/env bash
# Start / stop / status for the dashboard daemon.
#   ./harness/dashboard.sh start|stop|restart|status
#
# The pidfile is a hint, not the truth. A dashboard started by hand, by systemd or by an
# earlier pidfile that was then lost still holds the port, and trusting the pidfile alone
# left exactly that state unrecoverable: `status` said STOPPED, `stop` was a no-op and
# every `start` died on "Address already in use" while the poller's watchdog retried it
# forever. So the process table is consulted too -- the same fix launch_live.sh already
# carries for strategy daemons.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$REPO/harness/state"; LOG="$REPO/harness/logs/dashboard.log"
PIDFILE="$STATE/dashboard.pid"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
PORT="${DASHBOARD_PORT:-8788}"; BIND="${DASHBOARD_BIND:-auto}"
mkdir -p "$STATE" "$REPO/harness/logs"

# Every dashboard process for THIS repo, pidfile or not. Matched on the working directory
# so a second checkout's dashboard is never mistaken for ours.
#
# argv is compared element by element rather than as one flattened string. A substring
# test matches any process that merely MENTIONS the path -- `bash -c "...dashboard.py..."`,
# a grep, an editor -- and those shells run from the repo root, so the cwd check does not
# filter them out either. A false positive here is not cosmetic: `stop` would signal an
# innocent process and `start` would refuse to start, both believing a dashboard is up.
running_pids() {
  local p argv
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    mapfile -d '' -t argv < "$p/cmdline" 2>/dev/null || continue
    [ "${#argv[@]}" -gt 1 ] || continue
    case "${argv[0]##*/}" in python|python3|python3.*) ;; *) continue ;; esac
    local a hit=""
    for a in "${argv[@]:1}"; do
      case "$a" in *dashboard.py) hit=1; break ;; esac
    done
    [ -n "$hit" ] || continue
    [ "$(readlink -f "/proc/${p#/proc/}/cwd" 2>/dev/null)" = "$REPO" ] && echo "${p#/proc/}"
  done
}

alive() { [ -n "$(running_pids)" ]; }

# Serialise start/stop. check-then-spawn is not atomic, and the poller's watchdog runs
# this script too: a watchdog sweep landing between an operator's `alive` check and the
# spawn left two dashboards up, one of them without the port and useless.
LOCKFILE="$STATE/dashboard.lock"
lock() {
  exec 8>"$LOCKFILE"
  flock -w 60 8 || { echo "ERROR: another dashboard.sh is running" >&2; exit 1; }
}

case "${1:-status}" in
  start)
    lock
    if alive; then
      echo "dashboard already running (pid $(running_pids | tr '\n' ' '))"
      running_pids | head -1 > "$PIDFILE"      # re-adopt, so stop/status agree
      exit 0
    fi
    cd "$REPO" || exit 1
    # Where this run's output starts, so the report below quotes THIS start and not a
    # warning from some previous one that has long since been resolved.
    mark=$(wc -c < "$LOG" 2>/dev/null || echo 0)
    # 8>&- closes the lock fd in the child. Without it the daemon inherits the open
    # descriptor and keeps the flock for its whole life, so the next start or stop
    # blocks for the full timeout and then reports a phantom concurrent run.
    setsid nohup "$PY" -u harness/dashboard.py --bind "$BIND" --port "$PORT" \
      >> "$LOG" 2>&1 < /dev/null 8>&- &
    sleep 3
    if alive; then
      # Record the process actually serving, not $!: setsid may fork, and the poller's
      # watchdog treats a pidfile naming a dead pid as a dead dashboard.
      running_pids | head -1 > "$PIDFILE"
      echo "dashboard started (pid $(cat "$PIDFILE"))"
      tail -c "+$((mark + 1))" "$LOG" | grep -h "listening on\|NOTE:\|WARNING:" | tail -5
    else
      echo "ERROR: dashboard failed to start" >&2; tail -n 20 "$LOG" >&2; exit 1
    fi ;;
  stop)
    lock
    pids="$(running_pids)"
    if [ -z "$pids" ]; then echo "not running"; rm -f "$PIDFILE"; exit 0; fi
    for pid in $pids; do kill -TERM "$pid" 2>/dev/null; done
    # Wait for the port to actually be released -- `restart` used to sleep a flat 1s and
    # then race its own predecessor for the socket.
    for _ in $(seq 1 20); do
      [ -z "$(running_pids)" ] && break
      sleep 0.5
    done
    for pid in $(running_pids); do kill -KILL "$pid" 2>/dev/null; done
    rm -f "$PIDFILE"
    echo "stopped ($(echo "$pids" | tr '\n' ' '))" ;;
  restart) "$0" stop; "$0" start ;;
  status)
    if alive; then echo "dashboard RUNNING (pid $(running_pids | tr '\n' ' '), port $PORT)"
    else echo "dashboard STOPPED"; fi ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
