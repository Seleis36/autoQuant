#!/usr/bin/env python3
"""Stop hook for research agents: no session ends after one idea.

Headless `claude -p` ends the moment the model writes a final answer, and the research
brief -- rightly -- says an honest Failed is a valid result. Together those let a nightly
run pick one idea, grid it for five minutes, write it up as Failed and stop, with nine
hours of the night left unused (PRs #14 and #15: 6 and 17 minutes).

This hook refuses the stop until the session has worked on RESEARCH_MIN_IDEAS distinct
short names, and it refuses at most RESEARCH_MAX_STOP_BLOCKS times, so an agent that
cannot find another idea still ends -- it is a floor on effort, not a trap.

Wired in by agent_exec.sh for kind=research only, via --settings. Input is the hook JSON
on stdin (we only need `session_id`, which is the registry uuid we minted). Output is
Claude Code's block decision on stdout, or nothing to let the stop through.

An idea counts once anything under code/<ac>/<name>/ or past_research/<ac>/<name>/ was
written since the session launched -- either still in the working tree, or committed on
a local branch (Phase 6 checks back out to main, which takes committed ideas out of the
tree). `shared/` is not an idea.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS = os.path.join(REPO, "harness", "state", "sessions")
MIN_IDEAS = int(os.environ.get("RESEARCH_MIN_IDEAS", "5"))
MAX_BLOCKS = int(os.environ.get("RESEARCH_MAX_STOP_BLOCKS", "5"))
ROOTS = ("code", "past_research")


def ideas_since(ac: str, since: dt.datetime, repo: str = REPO) -> set[str]:
    found: set[str] = set()
    t0 = since.timestamp()
    # Working tree: any file under the idea folder touched since launch.
    for root in ROOTS:
        base = os.path.join(repo, root, ac)
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            d = os.path.join(base, name)
            if name == "shared" or not os.path.isdir(d):
                continue
            for dirpath, _, files in os.walk(d):
                if any(os.path.getmtime(os.path.join(dirpath, f)) >= t0 for f in files):
                    found.add(name)
                    break
    # Local branches: ideas already committed and checked out of the tree.
    try:
        out = subprocess.run(
            ["git", "-C", repo, "log", "--branches", f"--since={since.isoformat()}",
             "--name-only", "--format=", "--", *(f"{r}/{ac}/" for r in ROOTS)],
            capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for path in out.splitlines():
        parts = path.split("/")
        if len(parts) >= 4 and parts[2] != "shared":
            found.add(parts[2])
    return found


def decide(payload: dict, sessions: str = SESSIONS, repo: str = REPO) -> dict | None:
    uuid = str(payload.get("session_id") or "")
    reg_path = os.path.join(sessions, f"{uuid}.json")
    try:
        reg = json.load(open(reg_path))
    except (OSError, ValueError):
        return None                       # not a harness session: never block
    if reg.get("kind") != "research":
        return None
    ac = str(reg.get("target") or "")
    try:
        since = dt.datetime.fromisoformat(str(reg["launched_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None

    counter = os.path.join(sessions, f"{uuid}.stop_blocks")
    try:
        blocks = int(open(counter).read().strip() or 0)
    except (OSError, ValueError):
        blocks = 0
    if blocks >= MAX_BLOCKS:
        return None

    ideas = sorted(ideas_since(ac, since, repo))
    if len(ideas) >= MIN_IDEAS:
        return None

    with open(counter, "w") as f:
        f.write(str(blocks + 1))
    done = ", ".join(ideas) if ideas else "none yet"
    return {
        "decision": "block",
        "reason": (
            f"Not finished: this session has worked on {len(ideas)} of the minimum "
            f"{MIN_IDEAS} distinct ideas for {ac} ({done}). A Failed idea is a valid "
            "result for that idea, not for the session. Go back to Phase 2: take the next "
            "idea from your shortlist (or find a new one -- a different mechanism, not a "
            "re-parameterisation of one you already tried), give it its own short name "
            "and folders, and run it through Phases 3-4. "
            "If you already opened the PR: `git checkout` the research branch YOU created "
            "this session (that one is allowed), add the new idea there with its own "
            "`git add` block, commit, push, update the PR title/body to cover every idea, "
            "then `git checkout main` again. "
            f"(stop refused {blocks + 1}/{MAX_BLOCKS})"
        ),
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    try:
        out = decide(payload)
    except Exception as e:                # a broken hook must never wedge a session
        print(f"research_stop_hook: {e}", file=sys.stderr)
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
