#!/usr/bin/env bash
# Run the revision agent against ONE pull request the deployment agent sent back.
#
#   ./harness/revise_agent.sh 3
#
# Only PRs labelled `needs-revision` get here -- a `wontfix` blocker is structural and no
# amount of research fixes it. Two rounds, tracked by the `revision:<n>` label, then
# `harness:exhausted`: a blocker that survived two targeted fixes will not yield to a
# third, and each round costs a full research session.
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
STATE="$REPO/harness/state"; LOGS="$REPO/harness/logs"
mkdir -p "$STATE" "$LOGS"

PR="${1:?usage: revise_agent.sh <pr-number>}"
MODEL="${REVISE_AGENT_MODEL:-opus}"
TIMEOUT="${REVISE_AGENT_TIMEOUT:-14400}"     # a revision is research, not packaging
MAX_ROUNDS="${REVISE_MAX_ROUNDS:-2}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGS/revise-${PR}-${TS}.log"
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

labels="$(pr_labels "$PR")"
round=0
for n in $(seq 1 20); do
  case ",$labels," in *",revision:$n,"*) round="$n" ;; esac
done
if [ "$round" -ge "$MAX_ROUNDS" ]; then
  say "PR #$PR: $round revision rounds used (max $MAX_ROUNDS) -- exhausted"
  ensure_labels; add_label "$PR" "harness:exhausted"
  exit 3
fi
next=$((round + 1))

if ! slot_acquire revise; then
  say "PR #$PR: $(slot_report) -- deferring to the next sweep"
  exit 4
fi

cd "$REPO" || exit 1
ensure_labels
gh label create "revision:$next" --color 1D76DB --description "Revision round $next" >/dev/null 2>&1
add_label "$PR" "harness:processing"
trap 'remove_label "$PR" "harness:processing"' EXIT

say "PR #$PR: launching revision agent (round $next/$MAX_ROUNDS, model=$MODEL)"
PROMPT="/revise-strategy $PR"
UUID="$(session_start revise "pr-$PR" "$PROMPT" "$MODEL" "$LOG")"
say "PR #$PR: session $UUID"

"$REPO/harness/agent_exec.sh" start "$UUID" "$LOG" "$TIMEOUT" "$MODEL" "$PROMPT"
rc=$?

# The revision agent's side effect: either it cleared `needs-revision` (pushed a fix, PR
# goes back to the deploy queue) or it closed the PR as a genuine dead end. Anything else
# means it did not finish.
labels="$(pr_labels "$PR")"
state="$(gh pr view "$PR" --json state --jq .state 2>/dev/null)"
terminal=1
case ",$labels," in *",needs-revision,"*) ;; *) terminal=0 ;; esac
[ "$state" = "CLOSED" ] && terminal=0

session_side_effect_override "$UUID" "$terminal"
status="$(session_status "$UUID")"

if [ "$terminal" -eq 0 ]; then
  add_label "$PR" "revision:$next"
  say "PR #$PR: revision round $next complete (state=$state labels=$labels)"
  case "$(enforce_wontfix_closed "$PR" "$labels" "$state")" in
    closed)       say "PR #$PR: wontfix -- closed" ;;
    close-failed) say "PR #$PR: wontfix, but closing it failed -- close it by hand" ;;
  esac
  echo "$PR revised-$next $TS" >> "$STATE/processed.log"
  exit 0
fi

if [ "$status" = "aborted" ]; then
  reason="$(sl_py -c 'import json,sys;print(json.load(open(sys.argv[1]))["reason"])' \
            "$SL_SESSIONS/$UUID.json" 2>/dev/null)"
  say "PR #$PR: revision agent CUT OFF ($reason) -- parking, round not counted"
  say "PR #$PR: resume with ./harness/resume_aborted.sh $UUID"
  add_label "$PR" "harness:paused"
  exit 2
fi

# A failed round still counts: an agent that crashes twice on the same PR is telling us
# something, and not counting it would loop forever.
add_label "$PR" "revision:$next"
say "PR #$PR: revision agent failed (rc=$rc, status=$status) -- round $next spent"
exit 1

}

main "$@"
