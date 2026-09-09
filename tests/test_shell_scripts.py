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
    "session_lib.sh", "gh_lib.sh", "install_autostart.sh",
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
