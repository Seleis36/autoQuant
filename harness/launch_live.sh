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

# When a strategy is under a systemd unit, systemd is the supervisor: starting or
# stopping it any other way just races Restart=always. These helpers let the same
# commands (and the dashboard buttons that call them) keep working either way.
unit_for() { echo "autoquant-strategy@$(systemd-escape "${1%/}").service"; }

systemd_managed() {
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl --user is-enabled "$(unit_for "$1")" >/dev/null 2>&1
}

sync_pidfile_from_systemd() {  # $1 = name -- keeps status/watchdog agreeing with systemd
  local pid; pid="$(systemctl --user show "$(unit_for "$1")" -p MainPID --value 2>/dev/null)"
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then echo "$pid" > "$RUN/$(slug "${1%/}").pid"
  else rm -f "$RUN/$(slug "${1%/}").pid"; fi
}

is_running() {  # $1 = pidfile
  [ -f "$1" ] || return 1
  local pid; pid="$(cat "$1" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# The pidfile alone is not proof: after a WSL restart it holds a dead pid, and two
# starts racing between the spawn and the pidfile write both saw "not running" and
# both spawned -- two daemons trading one ledger. This asks the process table
# instead, matching on the runner's working directory.
running_pids_for() {  # $1 = strategy dir
  local dir; dir="$(readlink -f "$1")"
  local p argv
  for p in /proc/[0-9]*; do
    # A process can exit between the glob and the read; that is normal, not an error.
    [ -r "$p/cmdline" ] || continue
    # argv element by element, not a substring of the flattened line: a shell or editor
    # that merely mentions runner.py must not be mistaken for the daemon and killed.
    mapfile -d '' -t argv < "$p/cmdline" 2>/dev/null || continue
    [ "${#argv[@]}" -gt 1 ] || continue
    case "${argv[0]##*/}" in python|python3|python3.*) ;; *) continue ;; esac
    local a hit=""
    for a in "${argv[@]:1}"; do
      case "$a" in *runner.py) hit=1; break ;; esac
    done
    [ -n "$hit" ] || continue
    [ "$(readlink -f "/proc/${p#/proc/}/cwd" 2>/dev/null)" = "$dir" ] && echo "${p#/proc/}"
  done
}

cmd_start() {
  if systemd_managed "$1"; then
    systemctl --user start "$(unit_for "$1")" && sleep 2
    sync_pidfile_from_systemd "$1"
    echo "started ${1%/} via systemd ($(unit_for "$1"))"
    return 0
  fi
  # Serialise start for this strategy: check-then-spawn must be atomic.
  local lock="$RUN/$(slug "${1%/}").lock"
  exec 8>"$lock"
  if ! flock -w 30 8; then
    echo "ERROR: another start for ${1%/} is in progress" >&2; return 1
  fi
  _cmd_start_locked "$@"
}

_cmd_start_locked() {
  local name="${1%/}" dir pidfile logfile
  dir="$LIVE/$name"
  [ -f "$dir/runner.py" ] || { echo "ERROR: $dir/runner.py not found" >&2; return 1; }
  pidfile="$RUN/$(slug "$name").pid"
  logfile="$dir/runner.log"

  local existing; existing="$(running_pids_for "$dir" | tr '\n' ' ')"
  if [ -n "${existing// /}" ]; then
    echo "already running: $name (pid ${existing% })"
    echo "${existing%% *}" > "$pidfile"      # re-adopt, so status and the watchdog agree
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
  if systemd_managed "$1"; then
    systemctl --user stop "$(unit_for "$1")"
    rm -f "$RUN/$(slug "${1%/}").pid"
    echo "stopped ${1%/} via systemd"
    return 0
  fi
  local name="${1%/}" pidfile; pidfile="$RUN/$(slug "$name").pid"
  # Stop every process for this strategy, not just whichever the pidfile names --
  # an orphan left by a past race must not survive a stop.
  local pids; pids="$(running_pids_for "$LIVE/$name")"
  if [ -z "$pids" ]; then echo "not running: $name"; rm -f "$pidfile"; return 0; fi
  local pid
  for pid in $pids; do kill -TERM "$pid" 2>/dev/null; done
  for _ in $(seq 1 20); do
    [ -z "$(running_pids_for "$LIVE/$name")" ] && break
    sleep 1
  done
  for pid in $(running_pids_for "$LIVE/$name"); do kill -KILL "$pid" 2>/dev/null; done
  rm -f "$pidfile"
  echo "stopped $name ($(echo "$pids" | tr '\n' ' '))"
}

cmd_status() {
  local filter="${1:-}"
  local any=0 name pid
  # Enumerate deployments, not pidfiles: a systemd-supervised strategy has no
  # pidfile of its own until we sync one, so pidfiles alone would show nothing.
  while read -r name; do
    [ -z "$name" ] && continue
    [ -n "$filter" ] && [ "$name" != "${filter%/}" ] && continue
    any=1
    local managed="" ; pid=""
    if systemd_managed "$name"; then
      managed=" [systemd]"
      sync_pidfile_from_systemd "$name"
      pid="$(systemctl --user show "$(unit_for "$name")" -p MainPID --value 2>/dev/null)"
      [ "$pid" = "0" ] && pid=""
    else
      pid="$(running_pids_for "$LIVE/$name" | head -1)"
      if [ -n "$pid" ]; then echo "$pid" > "$RUN/$(slug "$name").pid"; fi
    fi

    if [ -n "$pid" ]; then printf 'RUNNING  %-32s pid %-8s ' "$name" "$pid"
    else printf 'STOPPED  %-32s %-12s ' "$name" "-"; fi

    local st="$LIVE/$name/state.json"
    if [ -f "$st" ]; then
      "$PY" -c "
import json
s=json.load(open('$st'))
# 'sim' is a simulated book working as designed; 'SHADOW' is a venue book that
# could not reach its venue. Both set shadow=True, so only one of them is a fault.
mode = s.get('mode') or ('shadow' if s.get('shadow') else 'live')
print('w=%-7s eq=%-11s %-6s %s%s' % (round(s.get('last_weight') or 0,4), round(s.get('equity') or 0,2),
      {'sim':'SIM','shadow':'SHADOW','live':'PAPER'}.get(mode, mode.upper()), s.get('updated',''), '$managed'))" 2>/dev/null         || echo "$managed"
    else
      echo "(no state.json yet)$managed"
    fi
  done < <(find "$LIVE" -mindepth 3 -maxdepth 3 -name runner.py -printf '%h\n' 2>/dev/null \
             | sed "s|^$LIVE/||" | sort)
  [ "$any" = 0 ] && echo "no strategies deployed"
  return 0
}

cmd_logs() { tail -n "${2:-50}" -f "$LIVE/${1%/}/runner.log"; }

case "${1:-status}" in
  start)  shift; cmd_start "$@" ;;
  stop)   shift; cmd_stop "$@" ;;
  status) shift; cmd_status "$@" ;;
  logs)   shift; cmd_logs "$@" ;;
  restart)
    shift
    if systemd_managed "$1"; then
      systemctl --user restart "$(unit_for "$1")" && sleep 2
      sync_pidfile_from_systemd "$1"
      echo "restarted ${1%/} via systemd"
    else
      cmd_stop "$1"; cmd_start "$1"
    fi ;;
  *) echo "usage: $0 {start|stop|restart|status|logs} <asset-class>/<short-name>" >&2; exit 2 ;;
esac
