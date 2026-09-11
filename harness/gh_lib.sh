#!/usr/bin/env bash
# PR label helpers. Sourced by deploy_agent.sh, revise_agent.sh, resume_aborted.sh.
#
# Labels go through the REST API, never `gh pr edit`. The gh on this machine resolves a
# PR through a GraphQL query that still asks for projectCards, which GitHub now rejects
# outright -- every `gh pr edit` fails with "Projects (classic) is being deprecated".
# Silently losing a label would leave a PR without a terminal state and the poller would
# hand it back every 30 minutes forever, so this is not a cosmetic preference.

GH_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GH_SLUG="$(git -C "$GH_REPO" remote get-url origin 2>/dev/null \
           | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"

add_label() {    # add_label <pr> <label>
  printf '{"labels":["%s"]}' "$2" \
    | gh api -X POST "repos/$GH_SLUG/issues/$1/labels" --input - >/dev/null 2>&1
}
remove_label() { # remove_label <pr> <label>
  gh api -X DELETE "repos/$GH_SLUG/issues/$1/labels/$(printf '%s' "$2" | sed 's/:/%3A/g')" \
    >/dev/null 2>&1
}
pr_labels() {    # pr_labels <pr> -> comma-joined
  gh pr view "$1" --json labels --jq '[.labels[].name] | join(",")' 2>/dev/null
}
has_label() {    # has_label <pr> <label>
  [[ ",$(pr_labels "$1")," == *",$2,"* ]]
}
# review_outcome <comma-joined labels> <state>
#   -> deployed | archived | revision | none
#
# What the deployment agent is DEFINED to leave behind, and therefore the authoritative
# test of whether a run finished. `none` means it did not, whatever its exit code said.
#
# Every PR ends up merged except one that is sent back: a deployed strategy merges with
# its runner, and a rejected one merges as a RESEARCH RECORD with nothing in `live/`.
# That is the point -- research agents read `past_research/<asset>/all_ideas.md` on main
# before choosing an idea, so a rejection that never lands there is a rejection the next
# agent repeats. Only `needs-revision` stays open, because the revision agent still has
# work to do on it.
#
# `archived` on an OPEN PR is therefore NOT terminal: the agent decided but the merge has
# not landed, so the run is unfinished and the poller hands it back to finish. Merging is
# left to the agent rather than enforced here because the usual failure is a conflict in
# `all_ideas.md` -- two ideas appended to one table -- and resolving that needs judgement,
# not a script.
review_outcome() {
  local labels=",$1," state="$2"
  if [ "$state" = "MERGED" ]; then
    case "$labels" in *,deployed,*) echo deployed ;; *) echo archived ;; esac
    return 0
  fi
  case "$labels" in
    *,deployed,*)       echo deployed ;;
    *,needs-revision,*) echo revision ;;
    *)                  echo none ;;
  esac
}
ensure_labels() {
  gh label create "harness:processing" --color FBCA04 --description "Agent is working on this PR"      >/dev/null 2>&1
  gh label create "harness:paused"     --color C5DEF5 --description "Agent cut off by a usage limit"   >/dev/null 2>&1
  gh label create "harness:failed"     --color B60205 --description "Agent could not complete"         >/dev/null 2>&1
  gh label create "harness:exhausted"  --color 5319E7 --description "Revision rounds used up"          >/dev/null 2>&1
  gh label create "invalid"            --color E4E669 --description "Cannot be deployed as submitted"  >/dev/null 2>&1
  gh label create "needs-revision"     --color D93F0B --description "Fixable blocker -- back to research" >/dev/null 2>&1
  gh label create "wontfix"            --color FFFFFF --description "Structurally undeployable here"   >/dev/null 2>&1
  gh label create "deployed"           --color 0E8A16 --description "Strategy is running live (paper)" >/dev/null 2>&1
  gh label create "archived"           --color C2E0C6 --description "Merged as a research record -- nothing deployed" >/dev/null 2>&1
}
