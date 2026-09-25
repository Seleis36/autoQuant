"""Tests for harness/research_stop_hook.py -- the effort floor on research sessions.

Nightly research runs were ending after one idea and a few minutes (PRs #14, #15). The
hook refuses the stop until enough distinct ideas were worked, and gives up refusing
after a fixed number of tries so a session can never be trapped.
"""
import datetime as dt
import json
import os
import subprocess
import sys

import pytest

from conftest import REPO_ROOT

sys.path.insert(0, os.path.join(REPO_ROOT, "harness"))
import research_stop_hook as hook  # noqa: E402

UUID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "harness" / "state" / "sessions").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    return r


def register(repo, kind="research", target="spot-btc", minutes_ago=5):
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
    (repo / "harness" / "state" / "sessions" / f"{UUID}.json").write_text(json.dumps(
        {"id": UUID, "kind": kind, "target": target, "launched_at": t.isoformat()}))


def idea(repo, name, root="code", ac="spot-btc"):
    d = repo / root / ac / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "x.py").write_text("print(1)\n")


def decide(repo):
    return hook.decide({"session_id": UUID},
                       sessions=str(repo / "harness" / "state" / "sessions"), repo=str(repo))


def test_one_idea_is_refused_with_a_reason(repo):
    register(repo)
    idea(repo, "weekday-trend")
    out = decide(repo)
    assert out and out["decision"] == "block"
    assert "1 of the minimum 5" in out["reason"]
    assert "weekday-trend" in out["reason"]


def test_five_ideas_may_stop(repo):
    register(repo)
    for n in ("a", "b", "c", "d"):
        idea(repo, n)
    idea(repo, "e", root="past_research")
    assert decide(repo) is None


def test_refusals_are_capped(repo):
    register(repo)
    for _ in range(hook.MAX_BLOCKS):
        assert decide(repo) is not None
    assert decide(repo) is None, "the sixth stop must go through"


def test_shared_and_old_folders_do_not_count(repo):
    register(repo, minutes_ago=5)
    idea(repo, "shared")
    idea(repo, "old-idea")
    old = (dt.datetime.now() - dt.timedelta(days=3)).timestamp()
    f = repo / "code" / "spot-btc" / "old-idea" / "x.py"
    os.utime(f, (old, old))
    assert "none yet" in decide(repo)["reason"]


def test_another_asset_class_does_not_count(repo):
    register(repo)
    for n in "abcde":
        idea(repo, n, ac="fx-majors")
    assert decide(repo) is not None


def test_ideas_committed_and_checked_out_of_the_tree_still_count(repo):
    """Phase 6 commits on a branch and returns to main, which removes the files."""
    register(repo)
    g = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "root"], check=True)
    subprocess.run(g + ["checkout", "-q", "-b", "research/spot-btc-x"], check=True)
    for n in "abcde":
        idea(repo, n)
    subprocess.run(g + ["add", "code"], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "ideas"], check=True)
    subprocess.run(g + ["checkout", "-q", "main"], check=True)
    assert not (repo / "code" / "spot-btc" / "a").exists()
    assert decide(repo) is None


@pytest.mark.parametrize("kind", ["deploy", "revise"])
def test_other_agents_are_never_blocked(repo, kind):
    register(repo, kind=kind)
    assert decide(repo) is None


def test_unknown_session_is_never_blocked(repo):
    assert decide(repo) is None


def test_script_prints_nothing_for_garbage_input():
    p = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "harness", "research_stop_hook.py")],
                       input="not json", capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout == ""
