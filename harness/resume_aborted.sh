#!/usr/bin/env bash
# Resume agent sessions that were cut off rather than restarting them.
#
#   ./harness/resume_aborted.sh --list        # what is parked, and why
#   ./harness/resume_aborted.sh               # resume everything cut off by a usage limit
#   ./harness/resume_aborted.sh --all         # ...including timeouts and unfinished runs
#   ./harness/resume_aborted.sh <uuid>        # resume exactly one
#
# Why resume rather than relaunch: a research agent killed at hour three has already pulled
# its data, run its failed variants and written down its reasoning. All of that is in the
# transcript, and `claude --resume` reads it back. Relaunching pays for it a second time.
#
# On "is there usage available?": we cannot know from out here. The dashboard's own
# refresh_usage() docstring is candid that local token counts are not subscription quota,
# and building a governor on a number the code documents as unreliable would be worse than
# not having one. So this is deliberately human-gated -- you check /usage and press the
# button. A premature resume is cheap and self-correcting: it is cut off again within
# seconds, goes back to `aborted` with one more entry in resumes[], and nothing is lost.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"
# shellcheck source=/dev/null
. "$REPO/harness/gh_lib.sh"

NUDGE_DEFAULT="Continue where you left off and finish the job.

Time has passed since your last message -- possibly hours -- so before you act, re-verify
the current state rather than trusting what you remember: re-read any file you were part
way through, re-check the PR's labels and comments, and confirm your git worktree still
exists and still points where you think it does. \`main\` may have moved. If a worktree you
created is stale or missing, remove and recreate it rather than working in a half-state.

Do not start over: the work you already did is above, and repeating it wastes the session.
Pick up from the last completed step and carry on to your terminal action -- the label,
the comment, the push, the PR."

list_sessions() {  # prints: uuid<TAB>kind<TAB>target<TAB>reason<TAB>launched<TAB>resumes
  sl_py - "$SL_SESSIONS" <<'PY'
import glob, json, os, sys
rows = []
for f in glob.glob(os.path.join(sys.argv[1], "*.json")):
    if f.endswith(".result.json"):
        continue
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if d.get("status") != "aborted":
        continue
    rows.append((d.get("launched_at") or "", d.get("id", ""), d.get("kind", ""),
                 d.get("target", ""), d.get("reason") or "?", len(d.get("resumes") or [])))
rows.sort()
for launched, uid, kind, target, reason, n in rows:
    print(f"{uid}\t{kind}\t{target}\t{reason}\t{launched[:19]}\t{n}")
PY
}

resume_one() {
  local uuid="$1"
  no_agents_on_desk "resuming session $uuid"
  local f="$SL_SESSIONS/$uuid.json"
  [ -f "$f" ] || { echo "no such session: $uuid" >&2; return 1; }

  local kind target model log reason
  eval "$(sl_py - "$f" <<'PY'
import json, sys, shlex
d = json.load(open(sys.argv[1]))
for k in ("kind", "target", "model", "log", "reason"):
    print(f"{k}={shlex.quote(str(d.get(k) or ''))}")
PY
)"
  local timeout="${RESUME_TIMEOUT:-14400}"
  # The registry stores a repo-relative path for anything under the repo and an absolute
  # one otherwise; blindly prefixing $REPO turns the latter into a junk directory inside
  # the working tree.
  local logpath
  case "$log" in /*) logpath="$log" ;; *) logpath="$REPO/$log" ;; esac
  mkdir -p "$(dirname "$logpath")"

  if ! slot_acquire "$kind"; then
    echo "  $uuid: $(slot_report) -- skipped, try again when one frees up"
    return 4
  fi

  echo "  resuming $uuid ($kind/$target, cut off by $reason)"
  session_set "$uuid" status '"running"'

  # A parked PR is invisible to the poller; clearing the label now means that if this
  # resume is itself cut off, the PR is re-parked, and if it succeeds the PR rejoins the
  # normal flow without anyone having to remember to unpark it.
  case "$target" in
    pr-*) remove_label "${target#pr-}" "harness:paused" ;;
  esac

  setsid nohup "$REPO/harness/agent_exec.sh" resume "$uuid" "$logpath" "$timeout" \
      "$model" "$NUDGE_DEFAULT" >> "$logpath" 2>&1 < /dev/null &
  sleep 2
  return 0
}

case "${1:---usage-limit}" in
  --list)
    session_reap_orphans
    printf '%-38s %-8s %-10s %-12s %-20s %s\n' UUID KIND TARGET REASON LAUNCHED RESUMES
    out="$(list_sessions)"
    if [ -z "$out" ]; then echo "(nothing parked)"; else
      while IFS=$'\t' read -r u k t r l n; do
        printf '%-38s %-8s %-10s %-12s %-20s %s\n' "$u" "$k" "$t" "$r" "$l" "$n"
      done <<< "$out"
    fi
    slot_report ;;
  --all|--usage-limit)
    session_reap_orphans
    filter="usage_limit"; [ "$1" = "--all" ] && filter="."
    out="$(list_sessions | awk -F'\t' -v f="$filter" '$4 ~ f')"
    if [ -z "$out" ]; then echo "nothing to resume"; exit 0; fi
    echo "$(echo "$out" | wc -l) session(s) to resume"
    while IFS=$'\t' read -r u _ _ _ _ _; do
      [ -n "$u" ] && resume_one "$u"
    done <<< "$out"
    echo "done -- $(slot_report)" ;;
  -h|--help) sed -n '2,20p' "$0" ;;
  *) resume_one "$1" ;;
esac
