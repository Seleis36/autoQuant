#!/usr/bin/env bash
# Launch a quant-research agent for one asset class, detached.
#
#   ./harness/launch_research.sh spot-btc
#   ./harness/launch_research.sh fx-majors "carry unwind around NFP"
#   ./harness/launch_research.sh spot-btc "" --require "OOS Sharpe >= 2.0 after 10bp/side"
#   ./harness/launch_research.sh fx-majors "" --model sonnet
#
# A seed says where to look; --require says what counts as having found something. The
# seed has never been a gate -- PR #3 was launched with the seed "2+ sharpe strat", the
# brief told the agent to treat that as "the starting idea, theme or paper", and it
# shipped 1.63 and said so in its own log. Criteria passed with --require are held to by
# the deployment agent, which sends the PR back for revision if the headline numbers miss.
#
# Runs the repo's own /<asset-class>-quant-research command headlessly. The agent opens a
# PR when it is done; the poller picks that up and the deployment agent takes it from there.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"
LOGS="$REPO/harness/logs"
mkdir -p "$LOGS"

AC="${1:?usage: launch_research.sh <asset-class> [seed idea] [--require <criteria>]}"
SEED="${2:-}"
REQUIRE=""
shift $(( $# > 2 ? 2 : $# ))
MODEL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --require) REQUIRE="${2:-}"; shift 2 ;;
    --model)   MODEL="${2:-}"; shift 2 ;;
    *) echo "ERROR: unknown option '$1'" >&2; exit 2 ;;
  esac
done

# An alias by default, so a new Opus is picked up the day the CLI learns about it. The
# model it actually resolved to is recorded in the session's result JSON and shown on the
# dashboard, which is what keeps two runs months apart comparable. A full id still works.
MODEL="${MODEL:-${RESEARCH_AGENT_MODEL:-opus}}"
case "$MODEL" in
  -*|"") echo "ERROR: --model needs a model alias or id (e.g. opus, sonnet), got '$MODEL'" >&2; exit 2 ;;
esac
# Deliberately uncapped: this runs on a Claude subscription, not metered API credit.
# The timeout below is the safety net -- it reaps a hung agent, not an expensive one.
TIMEOUT="${RESEARCH_AGENT_TIMEOUT:-14400}"

CMD_FILE="$REPO/.claude/commands/${AC}-quant-research.md"
[ -f "$CMD_FILE" ] || { echo "ERROR: no such asset class '$AC' (${CMD_FILE#"$REPO"/} missing)" >&2; exit 2; }

# One global gate for research, deploy and revise agents alike -- they share a single
# subscription and each one makes work for the others. Research is barred from the last
# free slot on purpose: draining the PR queue has to outrank filling it.
if ! slot_acquire research; then
  echo "ERROR: $(slot_report) -- research is capped at $((AGENT_MAX_CONCURRENT - 1)) so PR work can always start" >&2
  exit 3
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGS/research-${AC}-${TS}.log"
PROMPT="/${AC}-quant-research ${SEED}"
if [ -n "$REQUIRE" ]; then
  PROMPT="$PROMPT

ACCEPTANCE CRITERIA (hard gate on what you may call Working, see the brief):
$REQUIRE"
fi

UUID="$(session_start research "$AC" "$PROMPT" "$MODEL" "$LOG")"

cd "$REPO" || exit 1
setsid nohup "$REPO/harness/agent_exec.sh" start "$UUID" "$LOG" "$TIMEOUT" "$MODEL" "$PROMPT" \
  >> "$LOG" 2>&1 < /dev/null &
pid=$!
sleep 2
if kill -0 "$pid" 2>/dev/null; then
  echo "started research agent for $AC on $MODEL"
  [ -n "$REQUIRE" ] && echo "  criteria: $REQUIRE"
  echo "  session $UUID   log: harness/logs/$(basename "$LOG")"
  echo "  $(slot_report)"
else
  echo "ERROR: agent exited immediately; see harness/logs/$(basename "$LOG")" >&2
  tail -n 20 "$LOG" >&2
  exit 1
fi
