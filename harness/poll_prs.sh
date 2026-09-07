#!/usr/bin/env bash
# Poll this repo for new open pull requests and hand each one to the deployment
# agent (see harness/deploy_agent.sh and .claude/commands/deploy-strategy.md).
#
#   ./harness/poll_prs.sh --once      # a single sweep (use this from cron)
#   ./harness/poll_prs.sh --daemon    # self-scheduling loop, every 30 min
#   ./harness/poll_prs.sh --start     # launch the daemon detached
#   ./harness/poll_prs.sh --stop      # stop the detached daemon
#   ./harness/poll_prs.sh --status
#
# A PR is picked up when it is open, not a draft, and carries none of the
# terminal labels the agent applies: deployed / invalid / harness:failed.
# `harness:processing` marks an in-flight PR so overlapping sweeps never
# double-launch an agent on the same one.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$REPO/harness/state"
LOGS="$REPO/harness/logs"
mkdir -p "$STATE" "$LOGS"

INTERVAL="${POLL_INTERVAL:-1800}"          # 30 minutes
LOCK="$STATE/poll.lock"
PIDFILE="$STATE/poller.pid"
POLL_LOG="$LOGS/poller.log"

say() { echo "[$(date -u +%FT%TZ)] $*"; }

# Restart any strategy that is registered but dead, and any dead dashboard. This
# rides on the poller because it is the one thing already running all the time --
# which means nothing restarts the POLLER itself. That is systemd's job; until the
# units exist, a dead poller stays dead.
watchdog() {
  cd "$REPO" || return 1
  shopt -s nullglob
  for pidfile in "$STATE/run"/*.pid; do
    case "$(basename "$pidfile")" in research-*) continue ;; esac
    local slug name pid
    slug="$(basename "$pidfile" .pid)"
    pid="$(cat "$pidfile" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then continue; fi
    name="$(find "$REPO/live" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | while read -r d; do
              n="${d#"$REPO/live/"}"; [ "$(echo "$n" | tr '/' '_')" = "$slug" ] && echo "$n"; done | head -1)"
    [ -z "$name" ] && continue
    say "WATCHDOG: $name is dead, restarting"
    "$REPO/harness/launch_live.sh" start "$name"
  done
  if [ -f "$STATE/dashboard.pid" ] && ! kill -0 "$(cat "$STATE/dashboard.pid" 2>/dev/null)" 2>/dev/null; then
    say "WATCHDOG: dashboard is dead, restarting"
    "$REPO/harness/dashboard.sh" start
  fi
}

sweep() {
  cd "$REPO" || return 1

  watchdog

  if ! gh auth status >/dev/null 2>&1; then
    say "gh is not authenticated -- skipping sweep"; return 1
  fi

  local prs
  prs="$(gh pr list --state open --limit 50 \
          --json number,title,isDraft,labels,headRefName \
          --jq '.[]
                | select(.isDraft | not)
                | select([.labels[].name]
                         | any(. == "deployed" or . == "invalid"
                               or . == "harness:failed" or . == "harness:processing")
                         | not)
                | "\(.number)\t\(.headRefName)\t\(.title)"' 2>/dev/null)"
  local grc=$?
  if [ $grc -ne 0 ]; then say "gh pr list failed (rc=$grc)"; return 1; fi

  if [ -z "$prs" ]; then say "no eligible open PRs"; return 0; fi

  local n=0
  while IFS=$'\t' read -r num branch title; do
    [ -z "${num:-}" ] && continue
    n=$((n + 1))
    say "-> PR #$num ($branch): $title"
    "$REPO/harness/deploy_agent.sh" "$num"
    say "<- PR #$num finished with rc=$?"
  done <<< "$prs"
  say "sweep done, $n PR(s) handled"
}

locked_sweep() {
  # Never let two sweeps overlap; a long agent run just delays the next tick.
  exec 9>"$LOCK"
  if ! flock -n 9; then say "another sweep is still running -- skipping this tick"; return 0; fi
  sweep
}

daemon_loop() {
  echo $$ > "$PIDFILE"
  trap 'say "poller stopping"; rm -f "$PIDFILE"; exit 0' TERM INT
  say "poller started (pid $$, interval ${INTERVAL}s)"
  while true; do
    locked_sweep
    say "sleeping ${INTERVAL}s"
    sleep "$INTERVAL" &
    wait $!            # keeps SIGTERM responsive during the sleep
  done
}

case "${1:---once}" in
  --once)   locked_sweep ;;
  --daemon) daemon_loop ;;
  --start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "poller already running (pid $(cat "$PIDFILE"))"; exit 0
    fi
    setsid nohup "$0" --daemon >> "$POLL_LOG" 2>&1 < /dev/null &
    sleep 2
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "poller started (pid $(cat "$PIDFILE")) -- log: harness/logs/poller.log"
    else
      echo "ERROR: poller failed to start; see harness/logs/poller.log" >&2; exit 1
    fi ;;
  --stop)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      kill -TERM "$(cat "$PIDFILE")"; sleep 1; rm -f "$PIDFILE"; echo "poller stopped"
    else
      echo "poller not running"; rm -f "$PIDFILE"
    fi ;;
  --status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "poller RUNNING (pid $(cat "$PIDFILE"), interval ${INTERVAL}s)"
    else
      echo "poller STOPPED"
    fi
    "$REPO/harness/launch_live.sh" status ;;
  *) echo "usage: $0 {--once|--daemon|--start|--stop|--status}" >&2; exit 2 ;;
esac
