#!/usr/bin/env bash
# Run the deployment agent against ONE pull request.
#
#   ./harness/deploy_agent.sh 7
#
# Claims the PR with `harness:processing`, runs a headless Claude session on the
# /deploy-strategy command, and releases the claim afterwards. The agent itself applies
# the terminal outcome (deployed / invalid+needs-revision / archived) and merges;
# this script only supervises it and decides what a non-terminal exit meant.
set -uo pipefail

# Body wrapped in main() so that editing this script while it is supervising a live agent
# cannot corrupt the run: bash reads a script incrementally and would otherwise resume from
# a stale byte offset, but it parses a function body in full before executing any of it.
main() {

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"
# shellcheck source=/dev/null
. "$REPO/harness/gh_lib.sh"
STATE="$REPO/harness/state"
LOGS="$REPO/harness/logs"
mkdir -p "$STATE" "$LOGS"

PR="${1:?usage: deploy_agent.sh <pr-number>}"
# The `opus` alias: the newest Opus the CLI knows (see CLAUDE_BIN in session_lib.sh). The
# model it resolved to lands in the session's result JSON and on the dashboard.
MODEL="${DEPLOY_AGENT_MODEL:-opus}"
TIMEOUT="${DEPLOY_AGENT_TIMEOUT:-3600}"
MAX_ATTEMPTS="${DEPLOY_AGENT_MAX_ATTEMPTS:-3}"
# No spend cap: this runs on a Claude subscription, not metered API credit, so a dollar
# limit would be a cap on a number nobody is paying. The timeout is the safety net.

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGS/pr-${PR}-${TS}.log"
ATTEMPT_FILE="$STATE/attempts-${PR}"

say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

attempts="$(cat "$ATTEMPT_FILE" 2>/dev/null || echo 0)"
if [ "$attempts" -ge "$MAX_ATTEMPTS" ]; then
  say "PR #$PR: $attempts genuine failures already (max $MAX_ATTEMPTS), giving up"
  ensure_labels; add_label "$PR" "harness:failed"
  has_label "$PR" "harness:failed" \
    || say "PR #$PR: WARNING could not apply harness:failed -- the poller will keep retrying it"
  exit 3
fi

if ! slot_acquire deploy; then
  say "PR #$PR: $(slot_report) -- deferring to the next sweep"
  exit 4
fi

cd "$REPO" || exit 1

ensure_labels
add_label "$PR" "harness:processing"
trap 'remove_label "$PR" "harness:processing"' EXIT

say "PR #$PR: launching deployment agent (attempt $((attempts + 1))/$MAX_ATTEMPTS, model=$MODEL)"

PROMPT="/deploy-strategy $PR"
UUID="$(session_start deploy "pr-$PR" "$PROMPT" "$MODEL" "$LOG")"
say "PR #$PR: session $UUID"

"$REPO/harness/agent_exec.sh" start "$UUID" "$LOG" "$TIMEOUT" "$MODEL" "$PROMPT"
rc=$?

# --- did the agent reach a terminal decision? -------------------------------
# This is the authoritative check. The agent's whole job is to leave a terminal label
# behind; if one is not there the run did not finish, whatever its exit code claimed.
labels="$(pr_labels "$PR")"
state="$(gh pr view "$PR" --json state --jq .state 2>/dev/null)"
outcome="$(review_outcome "$labels" "$state")"
terminal=1
[ "$outcome" != "none" ] && terminal=0

session_side_effect_override "$UUID" "$terminal"
status="$(session_status "$UUID")"

if [ "$terminal" -eq 0 ]; then
  say "PR #$PR: terminal decision reached ($outcome; state=$state labels=$labels)"
  rm -f "$ATTEMPT_FILE"
  echo "$PR $outcome $TS" >> "$STATE/processed.log"
  exit 0
fi

# --- non-terminal: was it cut off, or did it genuinely fail? ----------------
# An agent killed by a usage limit looks exactly like one that crashed, so this used to
# burn an attempt either way -- three limit collisions would permanently kill a healthy
# PR. A cut-off run is parked instead: no attempt spent, and harness:paused keeps the
# poller off it until the resume button clears it.
if [ "$status" = "aborted" ]; then
  reason="$(sl_py -c 'import json,sys;print(json.load(open(sys.argv[1]))["reason"])' \
            "$SL_SESSIONS/$UUID.json" 2>/dev/null)"
  say "PR #$PR: agent CUT OFF ($reason) -- parking, no attempt spent"
  say "PR #$PR: resume with ./harness/resume_aborted.sh $UUID"
  add_label "$PR" "harness:paused"
  exit 2
fi

echo $((attempts + 1)) > "$ATTEMPT_FILE"
say "PR #$PR: agent failed (rc=$rc, status=$status) -- attempt $((attempts + 1))/$MAX_ATTEMPTS, will retry next cycle"
say "PR #$PR: log at ${LOG#"$REPO"/}"
exit 1

}

main "$@"
