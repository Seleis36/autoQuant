#!/usr/bin/env bash
# Start, on the trading desk, the strategies the research host's deployment agent merged.
#
#   ./harness/desk_launch.sh             # one pass; the poller runs this on every desk sweep
#   ./harness/desk_launch.sh --dry-run   # name what it would launch, change nothing
#
# The deployment agent runs on the research host (AQ_ROLE=research). It reviews the PR,
# writes live/<asset>/<name>/runner.py + meta.json, validates with --check, merges and
# labels the PR `deployed` -- and stops there, because the strategy has to run HERE, the
# one machine that is always on. This script is the other half:
#
#   1. pull main into the working tree the daemons run from (fast-forward only)
#   2. reserve the capital meta.json names, in this host's allocations.json -- the only
#      authoritative copy; the research host decided against a snapshot of it
#   3. enable the strategy's systemd unit (reboot survival), start it, confirm RUNNING
#   4. label the PR `vps:launched`, or `vps:launch-failed` with a comment saying why
#
# Which PRs: merged, labelled `deployed`, carrying neither vps:* outcome label, and merged
# at or after AQ_DESK_SINCE (.env, set when this host became the desk). Every PR merged
# before that was launched by the old single-host deployment agent and is already running,
# so the cutoff is what keeps a first pass from relabelling the whole history.
#
# No agent runs here: every step is deterministic, and a failure is reported rather than
# improvised around. A failed launch is not retried -- requeue it by removing the label.
set -uo pipefail

main() {
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/harness/session_lib.sh"
# shellcheck source=/dev/null
. "$REPO/harness/gh_lib.sh"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
SETTLE="${DESK_LAUNCH_SETTLE:-20}"

say() { echo "[$(date -u +%FT%TZ)] desk: $*"; }

if [ "$(aq_role)" != desk ]; then
  say "not the desk (AQ_ROLE=$(aq_role)) -- the deployment agent launches its own strategies"
  return 0
fi

SINCE="${AQ_DESK_SINCE:-$(sed -n 's/^[[:space:]]*AQ_DESK_SINCE[[:space:]]*=[[:space:]]*//p' \
                            "$REPO/.env" 2>/dev/null | tail -1 | tr -d "\"'[:space:]")}"
if ! [[ "$SINCE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
  # Refuse rather than guess: without the cutoff every historical `deployed` PR qualifies.
  say "AQ_DESK_SINCE missing or not YYYY-MM-DDTHH:MM:SSZ ('$SINCE') -- launching nothing"
  return 1
fi

local pending
pending="$(gh pr list --state merged --limit 50 --json number,title,labels,mergedAt \
  --jq ".[]
        | select(.mergedAt >= \"$SINCE\")
        | select([.labels[].name] | any(. == \"deployed\"))
        | select([.labels[].name] | any(. == \"vps:launched\" or . == \"vps:launch-failed\") | not)
        | \"\(.number)\t\(.title)\"" 2>/dev/null)"
local grc=$?
if [ $grc -ne 0 ]; then say "gh pr list failed (rc=$grc)"; return 1; fi
if [ -z "$pending" ]; then say "nothing merged to launch"; return 0; fi

if [ "$DRY" = 1 ]; then
  while IFS=$'\t' read -r num title; do
    say "would launch PR #$num: $title ($(pr_strategies "$num" | tr '\n' ' '))"
  done <<< "$pending"
  return 0
fi

# One pull for the whole pass. The daemons run out of this tree, so never anything but a
# fast-forward of main: a failure here (local edits in the way, a branch checked out) is
# left for a human and retried next sweep, not forced.
if [ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" != main ]; then
  say "working tree is not on main -- not pulling, retrying next sweep"; return 1
fi
if ! out="$(git -C "$REPO" pull --ff-only -q origin main 2>&1)"; then
  say "git pull --ff-only failed, retrying next sweep: $(echo "$out" | tail -3 | tr '\n' ' ')"
  return 1
fi

gh label create "vps:launched"      --color 0E8A16 --description "Running on the trading desk" >/dev/null 2>&1
gh label create "vps:launch-failed" --color B60205 --description "Merged as deployed, but the desk could not start it" >/dev/null 2>&1

while IFS=$'\t' read -r num title; do
  [ -z "${num:-}" ] && continue
  launch_pr "$num" "$title"
done <<< "$pending"
}

# pr_strategies <pr> -> the live/<asset>/<name> directories whose runner the PR adds or edits
pr_strategies() {
  gh api "repos/$GH_SLUG/pulls/$1/files" --paginate \
     --jq '.[] | select(.status != "removed") | .filename' 2>/dev/null \
    | sed -nE 's#^live/([^/]+/[^/]+)/runner\.py$#\1#p' | sort -u
}

comment() {  # comment <pr> <body>
  gh api -X POST "repos/$GH_SLUG/issues/$1/comments" -f body="$2" >/dev/null 2>&1
}

launch_pr() {
  local num="$1" title="$2" names name report="" failed=0
  say "-> PR #$num: $title"
  names="$(pr_strategies "$num")"
  if [ -z "$names" ]; then
    failed=1; report="The PR is labelled \`deployed\` but adds no \`live/<asset>/<name>/runner.py\`."
  fi
  for name in $names; do
    local r
    if r="$(launch_one "$name" 2>&1)"; then
      report+=$'\n'"**$name** -- running."$'\n```\n'"$r"$'\n```'
    else
      failed=1
      report+=$'\n'"**$name** -- NOT started."$'\n```\n'"$(echo "$r" | tail -25)"$'\n```'
    fi
  done
  if [ "$failed" = 0 ]; then
    add_label "$num" "vps:launched"
    comment "$num" "Desk: started on the trading desk.$report"
    say "<- PR #$num launched: $(echo "$names" | tr '\n' ' ')"
  else
    add_label "$num" "vps:launch-failed"
    comment "$num" "Desk: launch FAILED -- nothing is trading for the part marked NOT started. Fix, then remove \`vps:launch-failed\` to retry.$report"
    say "<- PR #$num launch FAILED: $(echo "$report" | grep -m1 -E 'NOT started|adds no' )"
  fi
}

launch_one() {  # launch_one <asset>/<name>; prints what happened, non-zero on failure
  local name="$1" d="$REPO/live/$1"
  [ -f "$d/runner.py" ] || { echo "live/$name/runner.py is not in main after the pull"; return 1; }
  [ -f "$d/meta.json" ] || { echo "live/$name/meta.json is not in main after the pull"; return 1; }

  # The capital the runner was written for, reserved in the book it was written for. A
  # refusal (a capped venue pool already committed) is the real constraint, reported.
  sl_py - "$REPO" "$name" <<'PY' || return 1
import json, os, sys
repo, name = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(repo, "harness"))
from live_lib import allocate
meta = json.load(open(os.path.join(repo, "live", name, "meta.json")))
cap, book = meta.get("capital_usdt"), meta.get("book")
if not cap or book not in ("venue", "sim"):
    sys.exit(f"meta.json must name capital_usdt and book (venue|sim); has {cap!r} / {book!r}")
try:
    print("allocated:", allocate(name, float(cap), book=book))
except ValueError as e:
    sys.exit(f"allocation refused: {e}")
PY

  if systemctl --user is-enabled autoquant.target >/dev/null 2>&1; then
    systemctl --user enable "autoquant-strategy@$(systemd-escape "$name").service" 2>&1 || return 1
  fi
  "$REPO/harness/launch_live.sh" start "$name" 2>&1 || return 1
  sleep "$SETTLE"
  local st; st="$("$REPO/harness/launch_live.sh" status "$name" 2>&1)"
  echo "$st"
  case "$st" in
    RUNNING*) return 0 ;;
    *) echo "--- runner.log (tail)"; tail -n 15 "$d/runner.log" 2>/dev/null; return 1 ;;
  esac
}

main "$@"
