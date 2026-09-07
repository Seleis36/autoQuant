#!/usr/bin/env bash
# Launch a quant-research agent for one asset class, detached.
#
#   ./harness/launch_research.sh spot-btc
#   ./harness/launch_research.sh fx-majors "carry unwind around NFP"
#
# Runs the repo's own /<asset-class>-quant-research command headlessly under a hard
# dollar cap. The agent opens a PR when it is done; the poller picks that up and the
# deployment agent takes it from there.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$REPO/harness/logs"
STATE="$REPO/harness/state"
mkdir -p "$LOGS" "$STATE/run"

AC="${1:?usage: launch_research.sh <asset-class> [seed idea]}"
SEED="${2:-}"
MODEL="${RESEARCH_AGENT_MODEL:-opus}"
# Deliberately uncapped: this runs on a Claude subscription, not metered API credit.
# The timeout below is the safety net -- it reaps a hung agent, not an expensive one.
TIMEOUT="${RESEARCH_AGENT_TIMEOUT:-14400}"
MAX_CONCURRENT="${RESEARCH_MAX_CONCURRENT:-2}"

CMD_FILE="$REPO/.claude/commands/${AC}-quant-research.md"
[ -f "$CMD_FILE" ] || { echo "ERROR: no such asset class '$AC' (${CMD_FILE#"$REPO"/} missing)" >&2; exit 2; }

running=$(find "$STATE/run" -name 'research-*.pid' 2>/dev/null | while read -r f; do
            p=$(cat "$f" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && echo x; done | wc -l)
if [ "$running" -ge "$MAX_CONCURRENT" ]; then
  echo "ERROR: $running research agent(s) already running (max $MAX_CONCURRENT)" >&2; exit 3
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGS/research-${AC}-${TS}.log"
PIDFILE="$STATE/run/research-${AC}-${TS}.pid"

cd "$REPO" || exit 1
{
  echo "[$(date -u +%FT%TZ)] research agent: /$AC-quant-research ${SEED:-(no seed)}"
  echo "[$(date -u +%FT%TZ)] model=$MODEL timeout=${TIMEOUT}s (no spend cap)"
} >> "$LOG"

setsid nohup timeout --signal=TERM --kill-after=60 "$TIMEOUT" \
  claude -p "/${AC}-quant-research ${SEED}" \
    --model "$MODEL" \
    --permission-mode bypassPermissions \
    --output-format text \
  >> "$LOG" 2>&1 < /dev/null &
pid=$!
echo "$pid" > "$PIDFILE"
sleep 2
if kill -0 "$pid" 2>/dev/null; then
  echo "started research agent for $AC (pid $pid) -- log: harness/logs/$(basename "$LOG")"
else
  echo "ERROR: agent exited immediately; see harness/logs/$(basename "$LOG")" >&2
  tail -n 20 "$LOG" >&2
  rm -f "$PIDFILE"
  exit 1
fi
