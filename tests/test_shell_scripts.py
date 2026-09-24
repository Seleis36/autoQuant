"""Tests for the bash side of the harness.

These run the real scripts. Anything that would touch GitHub, systemd or the venue is
kept out; what is covered is argument handling, the process-discovery logic and the
pidfile behaviour that let a dashboard become unstoppable.
"""
import os
import shutil
import subprocess
import textwrap
import time

import pytest

from conftest import REPO_ROOT

HARNESS = os.path.join(REPO_ROOT, "harness")


def run(script, *args, env=None, timeout=60, cwd=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([os.path.join(HARNESS, script), *args],
                          capture_output=True, text=True, timeout=timeout,
                          env=e, cwd=cwd or REPO_ROOT)


@pytest.mark.parametrize("script", [
    "dashboard.sh", "launch_live.sh", "poll_prs.sh", "launch_research.sh",
    "deploy_agent.sh", "revise_agent.sh", "resume_aborted.sh", "agent_exec.sh",
    "session_lib.sh", "gh_lib.sh", "install_autostart.sh", "nightly_research.sh",
])
def test_script_parses(script):
    p = subprocess.run(["bash", "-n", os.path.join(HARNESS, script)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("script,args", [
    ("dashboard.sh", ["bogus-verb"]),
    ("launch_live.sh", ["bogus-verb"]),
    ("poll_prs.sh", ["--bogus"]),
])
def test_unknown_verb_exits_two_with_usage(script, args):
    p = run(script, *args)
    assert p.returncode == 2
    assert "usage:" in p.stderr


def test_launch_live_rejects_a_missing_runner(tmp_path):
    p = run("launch_live.sh", "start", "no-such-class/no-such-strategy")
    assert p.returncode != 0
    assert "runner.py not found" in p.stderr


def test_launch_research_rejects_an_unknown_asset_class():
    p = run("launch_research.sh", "not-an-asset-class")
    assert p.returncode == 2
    assert "no such asset class" in p.stderr


def test_launch_research_rejects_an_unknown_option():
    p = run("launch_research.sh", "spot-btc", "seed", "--nope", "x")
    assert p.returncode == 2
    assert "unknown option" in p.stderr


# ------------------------------------------------------------------ dashboard.sh
#
# The pidfile is a hint, not the truth. A dashboard whose pidfile was lost still held the
# port: `status` reported STOPPED, `stop` was a no-op and every `start` died on "Address
# already in use", while the poller's watchdog retried it forever. Discovery now goes
# through the process table, as it already did for strategy daemons.

@pytest.fixture
def fake_repo(tmp_path):
    """A throwaway repo laid out like the real one, with a stand-in dashboard.py that
    just sleeps -- so the script's process discovery is what is under test."""
    r = tmp_path / "repo"
    (r / "harness" / "web").mkdir(parents=True)
    (r / "harness" / "logs").mkdir(parents=True)
    (r / "harness" / "state").mkdir(parents=True)
    shutil.copy(os.path.join(HARNESS, "dashboard.sh"), r / "harness" / "dashboard.sh")
    (r / "harness" / "dashboard.py").write_text(textwrap.dedent("""
        import sys, time
        print("listening on http://127.0.0.1:0", flush=True)
        time.sleep(300)
    """))
    return r


def dash(fake_repo, *args):
    return subprocess.run([str(fake_repo / "harness" / "dashboard.sh"), *args],
                          capture_output=True, text=True, timeout=60, cwd=str(fake_repo))


@pytest.fixture
def stopped_dashboard(fake_repo):
    yield fake_repo
    dash(fake_repo, "stop")


def test_start_status_stop_round_trip(stopped_dashboard):
    r = stopped_dashboard
    assert dash(r, "status").stdout.strip() == "dashboard STOPPED"
    assert dash(r, "start").returncode == 0
    assert "RUNNING" in dash(r, "status").stdout
    assert dash(r, "stop").returncode == 0
    assert "STOPPED" in dash(r, "status").stdout


def test_a_lost_pidfile_does_not_hide_a_running_dashboard(stopped_dashboard):
    """The exact state the old script could not recover from."""
    r = stopped_dashboard
    dash(r, "start")
    (r / "harness" / "state" / "dashboard.pid").unlink()

    assert "RUNNING" in dash(r, "status").stdout, (
        "a running dashboard must be found without its pidfile")
    assert dash(r, "stop").returncode == 0
    assert "STOPPED" in dash(r, "status").stdout


def test_start_is_idempotent_and_readopts_the_process(stopped_dashboard):
    r = stopped_dashboard
    dash(r, "start")
    pidfile = r / "harness" / "state" / "dashboard.pid"
    first = pidfile.read_text().strip()
    pidfile.unlink()

    out = dash(r, "start").stdout
    assert "already running" in out, "a second start must not spawn a rival process"
    assert pidfile.read_text().strip() == first, "the pidfile must be re-adopted"


def test_stop_waits_for_the_process_to_actually_exit(stopped_dashboard):
    """`restart` used to sleep a flat 1s and then race its own predecessor for the port."""
    r = stopped_dashboard
    dash(r, "start")
    dash(r, "stop")
    assert dash(r, "status").stdout.strip() == "dashboard STOPPED"


def test_restart_leaves_exactly_one_process(stopped_dashboard):
    r = stopped_dashboard
    dash(r, "start")
    assert dash(r, "restart").returncode == 0
    out = dash(r, "status").stdout
    assert "RUNNING" in out
    pids = out.split("pid ")[1].split(",")[0].split()
    assert len(pids) == 1, f"expected one dashboard process, got {pids}"


def test_stop_when_not_running_is_not_an_error(fake_repo):
    p = dash(fake_repo, "stop")
    assert p.returncode == 0 and "not running" in p.stdout


def test_a_shell_merely_mentioning_the_script_is_not_a_dashboard(stopped_dashboard):
    """Process discovery compares argv element by element. A substring test over the
    flattened command line matched any process that only MENTIONED the path -- a
    `bash -c "... harness/dashboard.py ..."`, a grep, an editor -- and those run from
    the repo root, so the cwd check did not filter them out either. `stop` would then
    signal an innocent process and `start` would refuse to start."""
    r = stopped_dashboard
    decoy = subprocess.Popen(
        ["bash", "-c", "echo harness/dashboard.py >/dev/null; sleep 30"], cwd=str(r))
    try:
        time.sleep(0.5)
        assert dash(r, "status").stdout.strip() == "dashboard STOPPED", (
            "a shell quoting the path is not a running dashboard")
        assert dash(r, "start").returncode == 0
        assert decoy.poll() is None, "the decoy must not have been signalled"
        dash(r, "stop")
        assert decoy.poll() is None, "stop must not kill an unrelated process"
    finally:
        decoy.kill()
        decoy.wait()


def test_concurrent_starts_produce_one_dashboard(stopped_dashboard):
    """check-then-spawn is not atomic, and the poller's watchdog runs this script too:
    a sweep landing between an operator's check and the spawn left two dashboards up."""
    r = stopped_dashboard
    script = str(r / "harness" / "dashboard.sh")
    procs = [subprocess.Popen([script, "start"], cwd=str(r),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(4)]
    for p in procs:
        p.wait(timeout=60)

    out = dash(r, "status").stdout
    assert "RUNNING" in out
    pids = out.split("pid ")[1].split(",")[0].split()
    assert len(pids) == 1, f"expected exactly one dashboard, got {pids}"


def test_pidfile_names_the_process_that_is_actually_serving(stopped_dashboard):
    """$! is the pid of whatever the shell backgrounded; setsid may fork. The poller's
    watchdog treats a pidfile naming a dead pid as a dead dashboard and restarts on a
    loop, so the file has to name the real process."""
    r = stopped_dashboard
    dash(r, "start")
    recorded = (r / "harness" / "state" / "dashboard.pid").read_text().strip()
    running = dash(r, "status").stdout.split("pid ")[1].split(",")[0].split()
    assert recorded in running, f"pidfile says {recorded}, running are {running}"


def test_start_reports_only_this_run(stopped_dashboard):
    """The start report used to grep the whole log, so a warning resolved three restarts
    ago was quoted back as if it had just happened."""
    r = stopped_dashboard
    log = r / "harness" / "logs" / "dashboard.log"
    log.write_text("WARNING: cannot bind 1.2.3.4:8788: [Errno 98] stale and long fixed\n")
    out = dash(r, "start").stdout
    assert "stale and long fixed" not in out


# --------------------------------------------------- what counts as a finished review
#
# `review_outcome` is the authoritative "did the deployment agent finish" test, and it is
# a pure function of the labels and the PR state, so it is driven directly here.
#
# The rule it encodes: every PR ends up merged except one sent back for revision. A
# rejected PR merges as a research record, because the next research agent reads
# `all_ideas.md` on main and repeats whatever never got there.

def _outcome(labels, state):
    script = (f'source {os.path.join(HARNESS, "gh_lib.sh")}; '
              f'review_outcome "{labels}" "{state}"')
    p = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


@pytest.mark.parametrize("labels,state,expected", [
    ("deployed", "MERGED", "deployed"),
    ("archived", "MERGED", "archived"),
    ("archived,wontfix", "MERGED", "archived"),
    ("", "MERGED", "archived"),                  # merged without `deployed` is a record
    ("invalid,needs-revision", "OPEN", "revision"),
    ("deployed", "OPEN", "deployed"),            # labelled before the merge registered
])
def test_a_finished_review_is_recognised(labels, state, expected):
    assert _outcome(labels, state) == expected


@pytest.mark.parametrize("labels,state", [
    ("archived", "OPEN"),                        # decided, but the merge never landed
    ("archived,wontfix", "OPEN"),
    ("invalid", "OPEN"),                         # no verdict beyond "not as submitted"
    ("", "OPEN"),                                # agent left nothing behind
    ("harness:processing", "OPEN"),
])
def test_an_unfinished_review_is_not_mistaken_for_a_decision(labels, state):
    """An archived PR that never merged is the case this exists for: the research is still
    stranded on a branch, so the run is unfinished and the poller must hand it back."""
    assert _outcome(labels, state) == "none"


def test_an_archived_pr_awaiting_its_merge_returns_to_the_review_queue(tmp_path):
    """...and the poller must not filter it out on the way. `wontfix` used to park a PR
    permanently; it now travels with `archived`, so only the merged state is terminal."""
    src = open(os.path.join(HARNESS, "poll_prs.sh")).read()
    review = src.split("--- review queue")[1]
    assert '"wontfix"' not in review, "wontfix must no longer park a PR in the review queue"
    assert '. == "deployed"' in review


# ------------------------------------------------- review queue is research-only

def _review_loop_source():
    """The real review-queue loop, sliced out of poll_prs.sh.

    Running the actual block keeps this honest -- a grep would pass against a comment --
    while leaving out the `gh pr list` above it, so no test touches GitHub.
    """
    src = open(os.path.join(HARNESS, "poll_prs.sh")).read()
    start = src.index('  local skipped=""')
    end = src.index('  [ "$n" -eq 0 ]')
    return src[start:end]


def _sweep_review(tmp_path, rows):
    """Drive that loop over `rows` of (number, branch, title); report what it did."""
    (tmp_path / "harness").mkdir(exist_ok=True)
    agent = tmp_path / "harness" / "deploy_agent.sh"
    agent.write_text('#!/usr/bin/env bash\necho "AGENT_RAN $1"\n')
    agent.chmod(0o755)

    prs = "\n".join("\t".join(r) for r in rows)
    script = textwrap.dedent("""\
        set -uo pipefail
        REPO="$1"
        say() {{ echo "SAY $*"; }}
        sweep() {{
          local n=0
          local prs
          prs="$(cat)"
        {loop}
          echo "HANDLED $n"
        }}
        sweep <<'PRS'
        {prs}
        PRS
        """).format(loop=_review_loop_source(), prs=prs)
    p = subprocess.run(["bash", "-c", script, "bash", str(tmp_path)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_a_research_pr_is_handed_to_the_deployment_agent(tmp_path):
    out = _sweep_review(tmp_path, [("11", "research/crypto-perps-funding-carry", "carry")])
    assert "AGENT_RAN 11" in out
    assert "HANDLED 1" in out


def test_a_harness_pr_is_left_alone_and_said_so(tmp_path):
    """The defect this closes: the label filter cannot tell a harness PR from a research
    one -- an ordinary PR carries no labels at all -- so the deployment agent was handed
    PRs that were never strategies."""
    out = _sweep_review(tmp_path, [("12", "fix/live-runner-late-bar", "poller fix")])
    assert "AGENT_RAN" not in out, "a harness PR must not reach the deployment agent"
    assert "HANDLED 0" in out
    assert "#12(fix/live-runner-late-bar)" in out, "a skipped PR must be named, not dropped"


def test_a_mixed_sweep_deploys_only_the_research_prs(tmp_path):
    out = _sweep_review(tmp_path, [
        ("11", "research/crypto-perps-funding-carry", "carry"),
        ("12", "fix/live-runner-late-bar", "poller fix"),
        ("13", "research/sector-etf-thing", "sector"),
        ("14", "docs/readme", "docs"),
    ])
    assert "AGENT_RAN 11" in out and "AGENT_RAN 13" in out
    assert "AGENT_RAN 12" not in out and "AGENT_RAN 14" not in out
    assert "HANDLED 2" in out
    assert "#12(fix/live-runner-late-bar)" in out and "#14(docs/readme)" in out


def test_a_quiet_sweep_says_nothing_about_skipping(tmp_path):
    out = _sweep_review(tmp_path, [("11", "research/a-b", "x")])
    assert "left alone" not in out
