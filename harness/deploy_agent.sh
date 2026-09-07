#!/usr/bin/env bash
# Run the deployment agent against ONE pull request.
#
#   ./harness/deploy_agent.sh 7
#
# Claims the PR with the `harness:processing` label, launches a headless Claude
# Code session on the /deploy-strategy command, and releases the claim afterwards.
# The agent itself is what applies the `deployed` / `invalid` label and merges;
# this script only supervises it.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$REPO/harness/state"
LOGS="$REPO/harness/logs"
mkdir -p "$STATE" "$LOGS"

PR="${1:?usage: deploy_agent.sh <pr-number>}"
MODEL="${DEPLOY_AGENT_MODEL:-opus}"
TIMEOUT="${DEPLOY_AGENT_TIMEOUT:-3600}"
MAX_BUDGET="${DEPLOY_AGENT_MAX_BUDGET_USD:-10}"   # hard per-run API spend cap
MAX_ATTEMPTS="${DEPLOY_AGENT_MAX_ATTEMPTS:-3}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGS/pr-${PR}-${TS}.log"
ATTEMPT_FILE="$STATE/attempts-${PR}"

say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

attempts="$(cat "$ATTEMPT_FILE" 2>/dev/null || echo 0)"
if [ "$attempts" -ge "$MAX_ATTEMPTS" ]; then
  say "PR #$PR: $attempts attempts already made (max $MAX_ATTEMPTS), giving up"
  gh label create "harness:failed" --color B60205 \
     --description "Deployment agent could not complete" >/dev/null 2>&1
  gh pr edit "$PR" --add-label "harness:failed" >/dev/null 2>&1
  exit 3
fi
echo $((attempts + 1)) > "$ATTEMPT_FILE"

cd "$REPO" || exit 1

# --- claim ------------------------------------------------------------------
gh label create "harness:processing" --color FBCA04 \
   --description "Deployment agent is reviewing this PR" >/dev/null 2>&1
gh pr edit "$PR" --add-label "harness:processing" >/dev/null 2>&1

release() { gh pr edit "$PR" --remove-label "harness:processing" >/dev/null 2>&1; }
trap release EXIT

say "PR #$PR: launching deployment agent (attempt $((attempts + 1))/$MAX_ATTEMPTS, model=$MODEL, budget=\$$MAX_BUDGET)"

timeout --signal=TERM --kill-after=60 "$TIMEOUT" \
  claude -p "/deploy-strategy $PR" \
    --model "$MODEL" \
    --permission-mode bypassPermissions \
    --output-format text \
    --max-budget-usd "$MAX_BUDGET" \
    >> "$LOG" 2>&1
rc=$?

# --- verify the agent reached a terminal decision ---------------------------
labels="$(gh pr view "$PR" --json labels --jq '[.labels[].name] | join(",")' 2>/dev/null)"
state="$(gh pr view "$PR" --json state --jq .state 2>/dev/null)"

if [ "$state" = "MERGED" ] || [[ ",$labels," == *",deployed,"* ]]; then
  say "PR #$PR: DEPLOYED (state=$state labels=$labels)"
  rm -f "$ATTEMPT_FILE"
  echo "$PR deployed $TS" >> "$STATE/processed.log"
  exit 0
fi
if [[ ",$labels," == *",invalid,"* ]]; then
  say "PR #$PR: flagged INVALID by the agent (labels=$labels)"
  rm -f "$ATTEMPT_FILE"
  echo "$PR invalid $TS" >> "$STATE/processed.log"
  exit 0
fi

if [ $rc -eq 124 ] || [ $rc -eq 137 ]; then
  say "PR #$PR: agent TIMED OUT after ${TIMEOUT}s -- will retry next cycle"
else
  say "PR #$PR: agent exited $rc without a terminal label -- will retry next cycle"
fi
say "PR #$PR: log at ${LOG#"$REPO"/}"
exit 1
