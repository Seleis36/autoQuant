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
close_pr() {     # close_pr <pr>
  gh api -X PATCH "repos/$GH_SLUG/pulls/$1" -f state=closed >/dev/null 2>&1
}
# enforce_wontfix_closed <pr> <comma-joined labels> <state>
#   prints nothing (not applicable), `closed`, or `close-failed` (and returns 1)
#
# A `wontfix` PR is closed: the verdict is structural, nothing in the loop will ever pick
# it up again, and an open PR reads as work still in flight. Both agent briefs say so, but
# an invariant this cheap belongs to the harness rather than to an agent's memory -- and
# an agent cut off between applying the label and closing the PR would otherwise leave it
# open forever. The briefs comment BEFORE labelling, so a PR carrying `wontfix` already
# has its explanation on it and closing here is never a silent close.
enforce_wontfix_closed() {
  [[ ",$2," == *",wontfix,"* ]] || return 0
  [ "$3" = "OPEN" ] || return 0
  if close_pr "$1"; then echo closed; else echo close-failed; return 1; fi
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
}
