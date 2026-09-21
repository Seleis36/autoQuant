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
# Two queues, swept in that order:
#
#   review    open, not a draft, no terminal label,     -> deploy_agent.sh
#             pushed from a research/* branch
#   revision  labelled needs-revision, not exhausted    -> revise_agent.sh
#
# Revision runs first: it drains PRs back into the review queue, and the slot gate in
# session_lib.sh gives PR work priority over new research for the same reason.
#
# Terminal labels the agents apply: deployed / archived (merged) / harness:failed /
# harness:exhausted. `harness:processing` marks an in-flight PR so overlapping sweeps
# never double-launch an agent on the same one, and `harness:paused` holds a PR whose
# agent was cut off by a usage limit -- the resume button clears that, not the poller.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"
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
              n="${d#"$REPO/live/"}"; [ "$(echo "$n" | tr '/' '_')" = "$slug" ] && echo "$n" ; done | head -1)"
    [ -z "$name" ] && continue
    # systemd restarts its own units in seconds; stepping in here would just race it.
    if systemctl --user is-enabled "autoquant-strategy@$(systemd-escape "$name").service" >/dev/null 2>&1; then
      continue
    fi
    say "WATCHDOG: $name is dead, restarting"
    "$REPO/harness/launch_live.sh" start "$name"
  done
  if systemctl --user is-enabled autoquant-dashboard.service >/dev/null 2>&1; then
    # systemd owns the dashboard, so do not restart it -- but do let dashboard.sh refresh
    # the pidfile from the process table. The unit execs dashboard.py directly and never
    # writes that file, so without this it keeps whatever a long-gone hand-start left.
    "$REPO/harness/dashboard.sh" status >/dev/null 2>&1 || true
  elif ! "$REPO/harness/dashboard.sh" status | grep -q RUNNING; then
    # Ask the script, which consults the process table. Reading the pidfile here meant a
    # dashboard whose pidfile went stale was "restarted" every 30 minutes forever, each
    # attempt dying on "Address already in use" while status insisted it was stopped.
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

  local n=0

  # --- revision queue first ------------------------------------------------
  local rev
  rev="$(gh pr list --state open --limit 50 \
          --json number,title,isDraft,labels,headRefName \
          --jq '.[]
                | select(.isDraft | not)
                | select([.labels[].name] | any(. == "needs-revision"))
                | select([.labels[].name]
                         | any(. == "harness:processing" or . == "harness:paused"
                               or . == "harness:exhausted" or . == "archived"
                               or . == "deployed")
                         | not)
                | "\(.number)\t\(.headRefName)\t\(.title)"' 2>/dev/null)"
  while IFS=$'\t' read -r num branch title; do
    [ -z "${num:-}" ] && continue
    n=$((n + 1))
    # Detached, unlike the deployment agent. A revision is a full research cycle (4h
    # timeout, not 1h), and the sweep holds the poll lock for as long as it blocks -- a
    # synchronous revision would stall every deployment behind it for half a day. The
    # harness:processing claim stops a later sweep double-launching it, and the slot gate
    # bounds how many can run at once, so nothing here needs the sweep to wait.
    say "-> REVISE PR #$num ($branch): $title"
    setsid nohup "$REPO/harness/revise_agent.sh" "$num" >/dev/null 2>&1 < /dev/null &
    say "<- PR #$num revision agent launched"
  done <<< "$rev"

  # --- review queue --------------------------------------------------------
  local prs
  prs="$(gh pr list --state open --limit 50 \
          --json number,title,isDraft,labels,headRefName \
          --jq '.[]
                | select(.isDraft | not)
                | select([.labels[].name]
                         | any(. == "deployed"
                               or . == "harness:failed" or . == "harness:exhausted"
                               or . == "harness:processing" or . == "harness:paused"
                               or . == "needs-revision" or . == "invalid")
                         | not)
                | "\(.number)\t\(.headRefName)\t\(.title)"' 2>/dev/null)"
  local grc=$?
  if [ $grc -ne 0 ]; then say "gh pr list failed (rc=$grc)"; return 1; fi

  # The deployment agent reviews research: a spec, a backtest, a runner to daemonise.
  # Handing it a harness or docs PR burns a session and ends with a bogus `invalid` on a
  # PR that was never a strategy. The label filter above cannot tell the difference --
  # an ordinary PR carries no labels at all -- so scope the queue to the branches the
  # research commands actually open (every one of them does `git checkout -b research/...`).
  #
  # Skipped PRs are named rather than dropped in silence: a research PR pushed from an
  # off-convention branch would otherwise sit in the queue forever with nothing saying
  # why, which is the same silent-skip failure this filter exists to prevent elsewhere.
  local skipped=""
  while IFS=$'\t' read -r num branch title; do
    [ -z "${num:-}" ] && continue
    case "$branch" in
      research/*) ;;
      *) skipped="$skipped #$num($branch)"; continue ;;
    esac
    n=$((n + 1))
    say "-> DEPLOY PR #$num ($branch): $title"
    "$REPO/harness/deploy_agent.sh" "$num"
    say "<- PR #$num finished with rc=$?"
  done <<< "$prs"

  [ -n "$skipped" ] && say "not on a research/* branch, left alone:$skipped"
  [ "$n" -eq 0 ] && say "no eligible open PRs"
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
    echo "$(slot_report)"
    parked="$("$REPO/harness/resume_aborted.sh" --list | grep -cvE '^(UUID|\(nothing|[0-9]+/)' || true)"
    [ "${parked:-0}" -gt 0 ] && echo "$parked session(s) parked -- ./harness/resume_aborted.sh --list"
    "$REPO/harness/launch_live.sh" status ;;
  *) echo "usage: $0 {--once|--daemon|--start|--stop|--status}" >&2; exit 2 ;;
esac
