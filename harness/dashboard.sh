#!/usr/bin/env bash
# Start / stop / status for the dashboard daemon.
#   ./harness/dashboard.sh start|stop|restart|status
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$REPO/harness/state"; LOG="$REPO/harness/logs/dashboard.log"
PIDFILE="$STATE/dashboard.pid"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
PORT="${DASHBOARD_PORT:-8787}"; BIND="${DASHBOARD_BIND:-auto}"
mkdir -p "$STATE" "$REPO/harness/logs"

alive() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; }

case "${1:-status}" in
  start)
    if alive; then echo "dashboard already running (pid $(cat "$PIDFILE"))"; exit 0; fi
    cd "$REPO" || exit 1
    setsid nohup "$PY" -u harness/dashboard.py --bind "$BIND" --port "$PORT" \
      >> "$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
    sleep 3
    if alive; then
      echo "dashboard started (pid $(cat "$PIDFILE"))"
      grep -h "listening on\|NOTE:\|WARNING:" "$LOG" | tail -5
    else
      echo "ERROR: dashboard failed to start" >&2; tail -n 20 "$LOG" >&2; exit 1
    fi ;;
  stop)
    if alive; then kill -TERM "$(cat "$PIDFILE")"; sleep 1; rm -f "$PIDFILE"; echo "stopped"
    else echo "not running"; rm -f "$PIDFILE"; fi ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  status)
    if alive; then echo "dashboard RUNNING (pid $(cat "$PIDFILE"), port $PORT)"
    else echo "dashboard STOPPED"; fi ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
