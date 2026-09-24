#!/usr/bin/env bash
# Shared agent-session bookkeeping: the registry, the exit classifier and the slot gate.
# Sourced by launch_research.sh, deploy_agent.sh, revise_agent.sh and resume_aborted.sh.
#
# Every headless Claude run in this harness gets a UUID that WE mint and pass in with
# --session-id, rather than trying to work out afterwards which transcript belonged to
# which agent. That id is the join key between three things:
#
#   harness/state/sessions/<uuid>.json                  what the run was supposed to do
#   harness/logs/<kind>-<target>-<ts>.log               what it printed
#   ~/.claude/projects/-home-seleis-autoQuant/<uuid>.jsonl   the resumable conversation
#
# which is what makes `claude --resume <uuid>` a recovery mechanism instead of a guess.

SL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SL_SESSIONS="$SL_REPO/harness/state/sessions"
SL_SLOTS="$SL_REPO/harness/state/slots"
SL_SIGNATURES="$SL_REPO/harness/limit_signatures.txt"
mkdir -p "$SL_SESSIONS" "$SL_SLOTS"

# Total concurrent agents of ALL kinds. Research, deploy and revise agents all draw on
# one subscription, and each one creates work for the others, so a per-script counter
# (which is what RESEARCH_MAX_CONCURRENT used to be, alone) cannot hold the line.
AGENT_MAX_CONCURRENT="${AGENT_MAX_CONCURRENT:-2}"

# Which claude binary every agent runs on. Pin it here rather than relying on whatever is
# first on PATH, so a shell difference between the poller, systemd and an interactive
# terminal cannot silently change what the agents are.
#
# The user-owned native install (~/.local/bin/claude, from `claude install`) wins over a
# system one. The agents launch on model aliases, which the CLI resolves to the newest
# model IT knows -- so the CLI's age is the models' age. The root-owned npm build this
# machine used to run could not self-update, sat on 2.1.269 while Opus 5.5 shipped, and
# kept resolving `opus` to Opus 5. The native install updates itself without sudo.
if [ -z "${CLAUDE_BIN:-}" ]; then
  if [ -x "$HOME/.local/bin/claude" ]; then CLAUDE_BIN="$HOME/.local/bin/claude"
  else CLAUDE_BIN=claude; fi
fi

# Resolve the interpreter ONCE. The old form was `venv/python "$@" || python3 "$@"`, which
# looks like a harmless fallback but breaks any caller that relies on the exit code: a
# deliberate non-zero exit fell through to a second interpreter that got an already-consumed
# heredoc on stdin, read nothing, and exited 0 -- turning every "no" into a "yes".
SL_PY_BIN="$SL_REPO/.venv/bin/python"
[ -x "$SL_PY_BIN" ] || SL_PY_BIN="$(command -v python3)"
sl_py() { "$SL_PY_BIN" "$@"; }

# --- registry ---------------------------------------------------------------

# session_start <kind> <target> <prompt> <model> <log>  -> prints the uuid
session_start() {
  local kind="$1" target="$2" model="$4" log="$5"
  local uuid; uuid="$(uuidgen)"
  SL_KIND="$kind" SL_TARGET="$target" SL_PROMPT="$3" SL_MODEL="$model" \
  SL_LOG="${5#"$SL_REPO"/}" SL_UUID="$uuid" SL_CWD="$SL_REPO" \
  sl_py - "$SL_SESSIONS/$uuid.json" <<'PYX'
import json, os, sys, datetime
json.dump({
    "id":     os.environ["SL_UUID"],
    "kind":   os.environ["SL_KIND"],
    "target": os.environ["SL_TARGET"],
    "prompt": os.environ["SL_PROMPT"],
    "cwd":    os.environ["SL_CWD"],
    "model":  os.environ["SL_MODEL"],
    "log":    os.environ["SL_LOG"],
    "pid":    None,
    "launched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "ended_at": None, "exit_code": None,
    "status": "running", "reason": None, "resumes": [],
}, open(sys.argv[1], "w"), indent=2)
PYX
  echo "$uuid"
}

session_set() {  # session_set <uuid> <key> <json-value>
  local f="$SL_SESSIONS/$1.json"
  [ -f "$f" ] || return 0
  sl_py - "$f" "$2" "$3" <<'PY'
import json, sys
f, k, v = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(f))
try:    d[k] = json.loads(v)
except json.JSONDecodeError: d[k] = v
json.dump(d, open(f, "w"), indent=2)
PY
}

session_append_resume() {  # <uuid> <exit_code> <reason>
  local f="$SL_SESSIONS/$1.json"
  [ -f "$f" ] || return 0
  sl_py - "$f" "$2" "$3" <<'PY'
import json, sys, datetime
f, rc, reason = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(f))
d.setdefault("resumes", []).append({
    "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "exit_code": int(rc), "reason": reason})
json.dump(d, open(f, "w"), indent=2)
PY
}

# --- classification ---------------------------------------------------------
#
# The only limit wording observed on this machine so far is Fable's "out of usage credits"
# (2026-09-24); the subscription-limit wording is still unverified and layer 2 below WILL need correcting the first time a real one lands --
# that is why the patterns live in an editable text file rather than in this script.
# Layer 3 (the caller's side-effect check) is the part that does not depend on knowing
# Anthropic's error strings, and it is what actually makes this safe.

# session_classify <exit_code> <log> <json-result-file> -> prints one of
#   clean | usage_limit | timeout | crash
session_classify() {
  local rc="$1" log="$2" jsonf="${3:-}"

  # layer 1: the structured result object
  if [ -n "$jsonf" ] && [ -s "$jsonf" ]; then
    local verdict
    verdict="$(sl_py - "$jsonf" <<'PY'
import json, sys
try:    d = json.load(open(sys.argv[1]))
except Exception: sys.exit(0)
if isinstance(d, list): d = d[-1] if d else {}
sub  = str(d.get("subtype") or "")
term = str(d.get("terminal_reason") or "")
err  = bool(d.get("is_error"))
blob = (sub + " " + term + " " + str(d.get("result") or "")).lower()
if any(s in blob for s in ("usage limit", "rate_limit", "rate limit",
                           "quota", "limit reached", "upgrade to",
                           # Observed 2026-09-24 on a Fable run with no credits left. It
                           # arrives as subtype "success" with is_error set, so without this
                           # it fell through to layer 2 and was filed as a crash.
                           "out of usage credits", "usage credits")):
    print("usage_limit")
elif not err and (term == "completed" or sub == "success"):
    print("clean")
PY
)"
    [ -n "$verdict" ] && { echo "$verdict"; return; }
  fi

  # layer 2: exit code + a signature list that is meant to be edited
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then echo "timeout"; return; fi
  if [ -f "$SL_SIGNATURES" ] && [ -f "$log" ] &&
     tail -c 20000 "$log" | grep -qiEf <(grep -vE '^\s*(#|$)' "$SL_SIGNATURES"); then
    echo "usage_limit"; return
  fi

  [ "$rc" -eq 0 ] && { echo "clean"; return; }
  echo "crash"
}

# session_end <uuid> <exit_code> <reason> <status>
session_end() {
  session_set "$1" exit_code "$2"
  session_set "$1" reason "\"$3\""
  session_set "$1" status "\"$4\""
  session_set "$1" ended_at "\"$(date -u +%FT%TZ)\""
}

# --- slot gate --------------------------------------------------------------
#
# Slots are numbered 1..N and held by an flock on a file for the life of the agent.
# Research agents are barred from the LAST free slot: deploy and revise work drains the
# PR queue and ends in a running strategy, while new research only fills it, so when
# capacity is tight finishing must beat starting. Reserving a slot by rank is enough to
# guarantee that without any of the launchers having to query the PR queue.
#
# Usage:  slot_acquire deploy || exit 0   ;   trap slot_release EXIT

# slot_acquire <kind>  -- sets $SLOT_FD and returns 0, or returns 1 if the gate is full.
# NOT usable as $(slot_acquire ...): command substitution forks, and an flock held by a
# subshell dies with it. It has to run in the caller's own shell.
slot_acquire() {
  local kind="$1" top="$AGENT_MAX_CONCURRENT" i fd
  [ "$kind" = "research" ] && top=$((AGENT_MAX_CONCURRENT - 1))
  [ "$top" -lt 1 ] && return 1
  for i in $(seq 1 "$top"); do
    exec {fd}>"$SL_SLOTS/slot-$i"
    if flock -n "$fd"; then SLOT_FD="$fd"; SLOT_N="$i"; return 0; fi
    exec {fd}>&-
  done
  return 1
}

slot_release() { [ -n "${SLOT_FD:-}" ] && eval "exec ${SLOT_FD}>&-"; SLOT_FD=""; }

slot_report() {
  local i held=0
  for i in $(seq 1 "$AGENT_MAX_CONCURRENT"); do
    ( exec {fd}>"$SL_SLOTS/slot-$i"; flock -n "$fd" ) || held=$((held + 1))
  done
  echo "$held/$AGENT_MAX_CONCURRENT agent slots in use"
}

# --- layer 3: the side-effect check ----------------------------------------
#
# The only abort test that needs no knowledge of Anthropic's error wording. Every agent
# here is DEFINED by a side effect -- a researcher opens a PR, a deployment agent applies
# a terminal label, a revision agent pushes a commit. If the process is gone and the side
# effect is not there, the run did not finish, whatever the log says. An agent that exits
# 0 having done nothing is the case string-matching would miss entirely.
#
#   session_side_effect_override <uuid> <0 if the side effect landed, 1 if not>
session_side_effect_override() {
  local uuid="$1" missing="$2" cur
  cur="$(sl_py -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' \
         "$SL_SESSIONS/$uuid.json" 2>/dev/null)"
  if [ "$missing" -ne 0 ] && [ "$cur" = "done" ]; then
    session_set "$uuid" status '"aborted"'
    session_set "$uuid" reason '"incomplete"'
    return 1
  fi
  return 0
}

# session_status <uuid> -> running|done|aborted|abandoned
session_status() {
  sl_py -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' \
    "$SL_SESSIONS/$1.json" 2>/dev/null
}

# --- orphan reaping ---------------------------------------------------------
#
# If the supervisor itself is killed -- kill -9, a reboot, the terminal going away --
# session_end never runs and the entry stays "running" forever, invisible to the resume
# path precisely when it most needs resuming. A dead pid with no verdict is an orphan.
session_reap_orphans() {
  sl_py - "$SL_SESSIONS" <<'PY'
import glob, json, os, sys
for f in glob.glob(os.path.join(sys.argv[1], "*.json")):
    if f.endswith(".result.json"):
        continue
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if d.get("status") != "running":
        continue
    pid = d.get("pid")
    alive = False
    if pid:
        try:
            os.kill(int(pid), 0); alive = True
        except (OSError, ValueError):
            alive = False
    if not alive:
        d["status"], d["reason"] = "aborted", "orphaned"
        json.dump(d, open(f, "w"), indent=2)
        print(f"reaped orphan: {d.get('id','')[:8]} ({d.get('kind')}/{d.get('target')})",
              file=sys.stderr)
PY
}
