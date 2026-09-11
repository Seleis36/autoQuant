---
description: Fix a quant-research PR that the deployment agent sent back, re-validate it honestly, and put it back in the queue — or retire it as a documented negative result if the fix kills the alpha.
argument-hint: <pr-number>
---

You are a **senior quant researcher** picking up work that came back from review. The
deployment engineer read this pull request, found a blocker, quoted it with file and line,
and labelled the PR `needs-revision`. Your job is to fix exactly that blocker and re-validate
the research honestly.

You are not a packager and this is not a formatting pass. Re-capping a strategy's leverage or
dropping a leg changes what the strategy *is*, and every number in the report was computed
under the old assumption. Those numbers are now wrong. Making them right again is the job.

**Pull request to revise: #$ARGUMENTS**

If that is empty, stop immediately and say a PR number is required.

---

## The one rule that matters

**You are allowed to conclude that the fix kills the alpha.** If re-capping at 1.0 takes
Sharpe from 1.63 to 0.6, the honest outcome is to say so, flip the entry in `all_ideas.md` to
**Failed**, comment on the PR explaining what the constraint cost, and hand it back to review.
That is a successful run of this command — the reviewer then merges it as a research record,
which is what stops the next researcher repeating the idea. Retiring an idea is not closing
the PR: research that never merges never reaches `all_ideas.md` on `main`, and is therefore
invisible to the agent that would otherwise repeat it.

A revision agent that can only succeed will manufacture success. You will be tempted to
quietly widen a window, drop a costly year, relax a cost assumption or re-pick a threshold
until the number comes back. **Do not.** The deployment agent will re-review whatever you
push, capital gets reserved on the strength of it, and a strategy that only works because you
tuned it twice is worse than no strategy. If you find yourself reaching for a third parameter
change to rescue a number, that is the signal to retire the idea instead.

Fix the quoted blocker. Do not widen the scope, do not chase a better result than the
original claim, and do not re-open questions the reviewer did not raise.

---

## Phase 1 — Read the review

```bash
gh pr view $ARGUMENTS --json number,title,body,state,labels,headRefName,comments
```

The deployment agent's comment is the brief. It states which strategy it assessed, each
blocking reason with the file and line that shows it, and what would unblock the PR. Work
from that list and nothing else.

If the PR is closed, merged, or carries `deployed`, `archived` or `harness:exhausted`, stop
and report that — it is not yours to touch.

## Phase 2 — Worktree

**Live paper-trading daemons run out of the main working tree.** Never `git checkout` there —
a branch without another strategy's `live/` directory deletes it out from under a running
process.

```bash
BR=$(gh pr view $ARGUMENTS --json headRefName --jq .headRefName)
git fetch origin "$BR"
WT=/tmp/revise-pr-$ARGUMENTS
git worktree remove "$WT" --force 2>/dev/null; rm -rf "$WT"
git worktree prune
git worktree add "$WT" -B "$BR" "origin/$BR"
```

Work in `$WT`. Always invoke `/home/seleis/autoQuant/.venv/bin/python` — the worktree has no
venv of its own. Remove the worktree when you are done.

## Phase 3 — Fix and re-validate

Read the research report, the alpha spec and `code/<asset-class>/<short-name>/strategy.py`
before changing anything, so you know which numbers depend on the thing you are about to
change.

Then, for the quoted blocker:

1. **Change the mechanism**, not the presentation. If the cap must be 1.0, change the default
   in `strategy.py` so the constraint is true by construction, not enforced downstream by the
   runner.
2. **Re-run the whole validation chain** the original report ran — in-sample, out-of-sample,
   walk-forward, the bootstrap, the cost sensitivity. Use the existing scripts in
   `code/<asset-class>/<short-name>/`; they are there precisely so this is reproducible. Do
   not re-run only the headline number.
3. **Rewrite every number that moved**: the report's tables, the spec's results block, the
   one-line entry in `past_research/<asset-class>/all_ideas.md`, and the figures if the equity
   curve changed. A spec whose numbers disagree with its own report is an instant re-rejection.
4. **Say what the constraint cost**, explicitly, in the report — a short section noting the
   original figures, the revised ones, and why they moved. The next researcher needs that.

Preserve the audit trail. The failed variants already documented in the report stay; you are
adding a revision, not rewriting history.

## Phase 4 — Decide

**If it still works** — the revised numbers still support a **Working** claim on their own
terms (out-of-sample or walk-forward Sharpe that stands up, costs charged, drawdown survivable)
— go to Phase 5.

**If it does not** — the revised strategy is no longer worth deploying — go to Phase 6. The bar
is what you would have claimed had you run it this way from the start. Do not grade the revision
generously because the first version looked good.

## Phase 5 — Push it back into the queue

```bash
cd "$WT"
git add past_research/<asset-class>/<short-name> \
        code/<asset-class>/<short-name> \
        alphas/<asset-class>/<short-name> \
        past_research/<asset-class>/all_ideas.md
git status --short              # verify nothing outside those paths is staged
git commit -m "<short-name>: revise for <the blocker>, re-validated"
git push origin HEAD:"$BR"
git worktree remove "$WT" --force
```

Then hand it back to review. Removing `needs-revision` and `invalid` is what makes the poller
pick the PR up again — **if you skip this the loop stops here and the PR sits forever.**

```bash
SLUG=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api -X DELETE "repos/$SLUG/issues/$ARGUMENTS/labels/needs-revision"
gh api -X DELETE "repos/$SLUG/issues/$ARGUMENTS/labels/invalid"
gh pr comment $ARGUMENTS --body-file <a file you write outside the repo>
gh pr view $ARGUMENTS --json labels --jq '[.labels[].name]'    # confirm both are gone
```

**Label through the REST API, never `gh pr edit`** — the `gh` on this machine resolves a PR
with a GraphQL query asking for `projectCards`, which GitHub refuses outright, so every
`gh pr edit` fails with *"Projects (classic) is being deprecated"*.

The comment must state: which blocker you fixed and how, the before/after on every headline
number, what the constraint cost, and anything the reviewer should re-check. Be concrete and
brief.

## Phase 6 — Or retire it honestly

```bash
cd "$WT"
# update all_ideas.md to Failed, and add the revision section to the report
git add past_research/<asset-class>/<short-name> past_research/<asset-class>/all_ideas.md \
        code/<asset-class>/<short-name>
git commit -m "<short-name>: Failed under the <constraint> constraint — retiring"
git push origin HEAD:"$BR"
cd /home/seleis/autoQuant && git worktree remove "$WT" --force

gh pr comment $ARGUMENTS --body-file <a file you write outside the repo>   # comment FIRST
gh api -X DELETE "repos/$SLUG/issues/$ARGUMENTS/labels/needs-revision"
gh api -X DELETE "repos/$SLUG/issues/$ARGUMENTS/labels/invalid"
gh pr view $ARGUMENTS --json labels --jq '[.labels[].name]'    # confirm both are gone
```

The comment states what the constraint did to the numbers and why the idea is not worth
carrying further.

**Retiring an idea ends exactly like fixing one: you hand the PR back to review.** The only
difference is what the PR now says — `all_ideas.md` reads **Failed** and the report carries
the revision section. The reviewer reads that, finds nothing to deploy, and merges it as a
research record. That merge is the whole point of the negative result: research agents choose
their next idea from `all_ideas.md` on `main`, so a retired idea that never merges is one the
next agent will try again from scratch.

**Do not close the PR and do not merge it yourself.** Closing strands the write-up on a branch
nobody reads; merging is the reviewer's job. Keep the branch and the report — the negative
result is the deliverable.

---

## Rules

* **Fix the quoted blocker only.** Not the strategy's ambition, not a doubt the reviewer
  did not raise.
* **Never edit numbers you did not recompute.** Every figure you leave in the report must
  come from a run you actually did under the new constraint.
* **Never `git checkout` in the main working tree** while daemons are running — use the
  worktree. Never touch `live/`, `harness/`, `.claude/`, or another asset class's files.
* **Stage your own paths only.** Never `git add -A` — up to two agents share this tree.
* **Never merge the PR and never apply `deployed`.** Review is someone else's job; your
  output is a PR that is ready to be reviewed again.
* Retiring an idea is a valid, complete outcome. Report it as such, not as a failure to fix.

End your run with a short report: the PR, the blocker, what you changed, the before/after
numbers, and the decision — back to review, or retired.
