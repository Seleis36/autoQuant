#!/usr/bin/env bash
# Run ONE headless Claude agent to completion and record how it ended.
#
#   agent_exec.sh start  <uuid> <log> <timeout> <model> <prompt>
#   agent_exec.sh resume <uuid> <log> <timeout> <model> <nudge>
#
# Not called by hand -- launch_research.sh, deploy_agent.sh, revise_agent.sh and
# resume_aborted.sh all funnel through here so that the session registry is written in
# exactly one place and the three launchers cannot drift apart.
#
# This process is the one that holds the concurrency slot: its parent opens the flock and
# execs us with the fd still open, so the slot is held for exactly as long as the agent
# lives and is released by the kernel when it dies -- including on a crash, a SIGKILL or a
# reboot. There is no slot cleanup path anywhere, by design.
#
# Everything runs inside main(), called on the last line. Bash reads a script incrementally
# from a byte offset, so editing this file while an agent is running it makes bash resume at
# a stale position and execute garbage. That happened during a real deployment run: the log
# gained a bogus "Permission denied" and rc came back 126 while the agent had in fact
# completed and merged the PR. It survived only because session_classify() trusts the
# structured JSON result over the exit code. Bash parses a function body in full before
# running any of it, so main() makes an in-flight edit harmless -- and this harness edits
# its own scripts while agents are running.
set -uo pipefail

main() {
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"

MODE="${1:?mode}"; UUID="${2:?uuid}"; LOG="${3:?log}"; TIMEOUT="${4:?timeout}"
MODEL="${5:?model}"; PROMPT="${6:?prompt}"
JSONF="$SL_SESSIONS/$UUID.result.json"

say() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

session_set "$UUID" pid "$$"

if [ "$MODE" = "resume" ]; then
  say "resuming session $UUID (model=$MODEL)"
  set -- --resume "$UUID"
else
  say "starting session $UUID (model=$MODEL, timeout=${TIMEOUT}s)"
  set -- --session-id "$UUID"
fi

cd "$REPO" || exit 1

# Research-only knobs, decided from the registry so a resumed session gets them too.
# The Stop hook refuses to let the agent finish before it has worked RESEARCH_MIN_IDEAS
# distinct ideas (at most RESEARCH_MAX_STOP_BLOCKS refusals) -- see research_stop_hook.py
# for why. Deploy and revise agents have one job each and are left alone.
kind="$(sl_py -c 'import json,sys; print(json.load(open(sys.argv[1])).get("kind",""))' \
        "$SL_SESSIONS/$UUID.json" 2>/dev/null)"
if [ "$kind" = "research" ]; then
  hook="$SL_PY_BIN $REPO/harness/research_stop_hook.py"
  set -- "$@" --effort "${RESEARCH_AGENT_EFFORT:-xhigh}" \
    --settings "{\"hooks\":{\"Stop\":[{\"hooks\":[{\"type\":\"command\",\"command\":\"$hook\",\"timeout\":60}]}]}}"
  say "research: effort=${RESEARCH_AGENT_EFFORT:-xhigh}, stop hook needs ${RESEARCH_MIN_IDEAS:-5} ideas (max ${RESEARCH_MAX_STOP_BLOCKS:-5} refusals)"
fi

# --output-format json gives us is_error / subtype / terminal_reason, which is the strongest
# abort signal available. The human-readable answer is pulled back out of it afterwards so
# the log stays readable -- text mode threw all the structure away.
#
# < /dev/null because a foreground caller (deploy_agent) passes its own stdin through, and
# claude then waits 3s for piped input that never comes, on every single agent launch.
timeout --signal=TERM --kill-after=60 "$TIMEOUT" \
  "$CLAUDE_BIN" -p "$PROMPT" "$@" \
    --model "$MODEL" \
    --permission-mode bypassPermissions \
    --output-format json \
  > "$JSONF" 2>>"$LOG" < /dev/null
rc=$?

# Surface the prose into the log; keep the raw JSON beside the registry entry.
sl_py - "$JSONF" >> "$LOG" 2>/dev/null <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
if isinstance(d, list):
    d = d[-1] if d else {}
print(d.get("result") or "")
PYEOF

reason="$(session_classify "$rc" "$LOG" "$JSONF")"
case "$reason" in
  clean)               status=done ;;
  usage_limit|timeout) status=aborted ;;     # resumable: the work so far is in the transcript
  *)                   status=abandoned ;;   # a real crash -- resuming would just repeat it
esac

if [ "$MODE" = "resume" ]; then
  session_append_resume "$UUID" "$rc" "$reason"
fi
session_end "$UUID" "$rc" "$reason" "$status"
say "session $UUID ended rc=$rc reason=$reason status=$status"

# The caller (deploy_agent / revise_agent) may still override this from a side-effect check
# -- see session_side_effect_override in session_lib.sh.
exit "$rc"
}

main "$@"
